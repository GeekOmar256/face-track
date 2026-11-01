"""HTTP routes for the BioAttendance web interface."""
import csv
import io
import threading

from flask import (
    Blueprint, Response, current_app, flash, jsonify, redirect,
    render_template, request, send_file, url_for,
)

from . import worker as worker_states
from . import rfid_worker as rfid_states
from . import fingerprint_worker as fingerprint_states

bp = Blueprint("facetrack", __name__)


def _db():
    return current_app.config["DB"]


def _face_engine():
    return current_app.config["FACE_ENGINE"]


def _worker():
    return current_app.config["WORKER"]


def _rfid():
    return current_app.config["RFID_WORKER"]


def _ultrasonic():
    return current_app.config["ULTRASONIC_WORKER"]


def _fingerprint():
    return current_app.config["FINGERPRINT_WORKER"]


def _firebase():
    return current_app.config["FIREBASE"]


# ------------------------------------------------------------------ dashboard
@bp.route("/")
def dashboard():
    db = _db()
    return render_template(
        "dashboard.html", active="dashboard",
        student_count=db.count_students(),
        session_count=len(db.get_all_sessions()),
    )


# --------------------------------------------------------------- add student
@bp.route("/add-student")
def add_student():
    return render_template("add_student.html", active="add_student")


@bp.route("/add-student/start", methods=["POST"])
def add_student_start():
    data = request.get_json(force=True)
    student_id = (data.get("student_id") or "").strip()
    name = (data.get("name") or "").strip()
    try:
        pk = _worker().start_enrollment(student_id, name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"pk": pk})


@bp.route("/add-student/capture", methods=["POST"])
def add_student_capture():
    try:
        count = _worker().capture_photo()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"count": count})


@bp.route("/add-student/finish", methods=["POST"])
def add_student_finish():
    worker = _worker()
    _rfid().cancel_scan()  # don't leave a scan dangling once enrollment ends
    _fingerprint().cancel_enroll()

    pk = worker.enroll_pk
    has_other_credential = False
    if pk is not None:
        student = _db().get_student_by_pk(pk)
        has_other_credential = bool(
            student and (student["rfid_uid"] or student["fingerprint_id"] is not None)
        )

    try:
        pk, count = worker.finish_enrollment(allow_zero_photos=has_other_credential)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    finished_student = _db().get_student_by_pk(pk)
    if finished_student is not None:
        _firebase().push_student(finished_student)

    return jsonify({"pk": pk, "count": count})


@bp.route("/add-student/status")
def add_student_status():
    return jsonify(_worker().status())


@bp.route("/add-student/cancel", methods=["POST"])
def add_student_cancel():
    _rfid().cancel_scan()
    _fingerprint().cancel_enroll()
    _worker().cancel_enrollment()
    return jsonify({"ok": True})


# ------------------------------------------------------- add student: RFID
@bp.route("/add-student/rfid/start", methods=["POST"])
def add_student_rfid_start():
    worker = _worker()
    pk = worker.enroll_pk
    if worker.mode != worker_states.ENROLL or pk is None:
        return jsonify({"error": "Start capture first, then scan the card."}), 409

    db = _db()
    firebase = _firebase()

    def on_scanned(uid):
        db.set_student_rfid(pk, uid)  # may raise ValueError on a duplicate card
        firebase.push_student(db.get_student_by_pk(pk))

    try:
        _rfid().start_scan(on_scanned)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"ok": True})


@bp.route("/add-student/rfid/cancel", methods=["POST"])
def add_student_rfid_cancel():
    _rfid().cancel_scan()
    return jsonify({"ok": True})


@bp.route("/add-student/rfid/clear", methods=["POST"])
def add_student_rfid_clear():
    worker = _worker()
    pk = worker.enroll_pk
    if worker.mode != worker_states.ENROLL or pk is None:
        return jsonify({"error": "No enrollment in progress."}), 409
    _db().set_student_rfid(pk, None)
    return jsonify({"ok": True})


@bp.route("/add-student/rfid/status")
def add_student_rfid_status():
    return jsonify(_rfid().status())


# --------------------------------------------------------------- RFID: shared
@bp.route("/rfid/hardware")
def rfid_hardware():
    return jsonify({"hardware_available": _rfid().hardware_available})


@bp.route("/rfid/simulate", methods=["POST"])
def rfid_simulate():
    """Dev/no-hardware fallback: manually supply a UID as if a card had
    just been scanned. Routes to whichever RFID operation is active
    (enrollment scan or a live session)."""
    data = request.get_json(force=True)
    uid = (data.get("uid") or "").strip()
    if not uid:
        return jsonify({"error": "Enter a card UID to simulate."}), 400
    worker = _rfid()
    if worker.mode == rfid_states.IDLE:
        return jsonify({"error": "RFID reader is not currently active."}), 409
    worker.inject_uid(uid)
    return jsonify({"ok": True})


# ------------------------------------------------------- add student: fingerprint
@bp.route("/add-student/fingerprint/start", methods=["POST"])
def add_student_fingerprint_start():
    worker = _worker()
    pk = worker.enroll_pk
    if worker.mode != worker_states.ENROLL or pk is None:
        return jsonify({"error": "Start capture first, then enroll the fingerprint."}), 409

    db = _db()
    firebase = _firebase()

    def on_enrolled(position):
        db.set_student_fingerprint(pk, position)  # may raise ValueError on a duplicate slot
        firebase.push_student(db.get_student_by_pk(pk))

    try:
        _fingerprint().start_enroll(on_enrolled)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"ok": True})


@bp.route("/add-student/fingerprint/cancel", methods=["POST"])
def add_student_fingerprint_cancel():
    _fingerprint().cancel_enroll()
    return jsonify({"ok": True})


@bp.route("/add-student/fingerprint/clear", methods=["POST"])
def add_student_fingerprint_clear():
    worker = _worker()
    pk = worker.enroll_pk
    if worker.mode != worker_states.ENROLL or pk is None:
        return jsonify({"error": "No enrollment in progress."}), 409
    student = _db().get_student_by_pk(pk)
    old_position = student["fingerprint_id"] if student else None
    _db().set_student_fingerprint(pk, None)
    if old_position is not None:
        _fingerprint().sensor.delete_template(old_position)  # best-effort; no-op without hardware
    return jsonify({"ok": True})


@bp.route("/add-student/fingerprint/status")
def add_student_fingerprint_status():
    return jsonify(_fingerprint().status())


# --------------------------------------------------------- fingerprint: shared
@bp.route("/fingerprint/hardware")
def fingerprint_hardware():
    return jsonify({"hardware_available": _fingerprint().hardware_available})


@bp.route("/fingerprint/simulate", methods=["POST"])
def fingerprint_simulate():
    """Dev/no-hardware fallback. During enrollment, advances the two-step
    wizard one step. During a session, pass {"position": N} to simulate a
    match for the student enrolled at that sensor slot."""
    worker = _fingerprint()
    if worker.mode == fingerprint_states.IDLE:
        return jsonify({"error": "Fingerprint sensor is not currently active."}), 409

    if worker.mode == fingerprint_states.ENROLL:
        worker.simulate_enroll_step()
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    position = data.get("position")
    if position is None:
        return jsonify({"error": "Pick a student to simulate a match for."}), 400
    worker.simulate_match(int(position))
    return jsonify({"ok": True})


@bp.route("/fingerprint/enrolled")
def fingerprint_enrolled():
    """Students with a fingerprint on file, for the session page's
    simulate-a-match dropdown."""
    rows = [
        {"pk": s["id"], "name": s["name"], "student_id": s["student_id"], "position": s["fingerprint_id"]}
        for s in _db().get_all_students()
        if s["fingerprint_id"] is not None
    ]
    return jsonify(rows)


# -------------------------------------------------------------------- session
@bp.route("/session")
def session_page():
    return render_template("session.html", active="session")


@bp.route("/session/start", methods=["POST"])
def session_start():
    worker = _worker()
    try:
        session_id = worker.start_session()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    db = _db()
    session_row = next((s for s in db.get_all_sessions() if s["id"] == session_id), None)
    if session_row is not None:
        _firebase().push_session(session_row)

    def on_card(uid):
        student = db.get_student_by_rfid(uid)
        if student is not None:
            worker.mark_present(student["id"], "rfid")

    try:
        _rfid().start_session_scan(on_card)
    except RuntimeError:
        pass  # RFID reader busy/unavailable - face recognition still works on its own

    def on_fingerprint(position):
        student = db.get_student_by_fingerprint(position)
        if student is not None:
            worker.mark_present(student["id"], "fingerprint")

    try:
        _fingerprint().start_session_scan(on_fingerprint)
    except RuntimeError:
        pass  # fingerprint sensor busy/unavailable - other methods still work

    _ultrasonic().start()

    return jsonify({"session_id": session_id})


@bp.route("/session/status")
def session_status():
    return jsonify(_worker().status())


@bp.route("/session/stop", methods=["POST"])
def session_stop():
    _rfid().stop_session_scan()
    _fingerprint().stop_session_scan()
    _ultrasonic().stop()
    session_id, present = _worker().stop_session()

    if session_id is not None:
        db = _db()
        session_row = next((s for s in db.get_all_sessions() if s["id"] == session_id), None)
        if session_row is not None:
            _firebase().push_session(session_row)

    return jsonify({"session_id": session_id, "present_count": present})


@bp.route("/ultrasonic/hardware")
def ultrasonic_hardware():
    return jsonify({"hardware_available": _ultrasonic().hardware_available})


# --------------------------------------------------------------- video stream
@bp.route("/video_feed")
def video_feed():
    worker = _worker()

    def gen():
        import time
        while True:
            jpeg = worker.get_jpeg()
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            time.sleep(0.03)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ----------------------------------------------------------------- students
@bp.route("/students")
def students():
    return render_template("students.html", active="students", students=_db().get_all_students())


@bp.route("/students/<int:pk>/delete", methods=["POST"])
def delete_student(pk):
    db = _db()
    student = db.get_student_by_pk(pk)
    if student is None:
        flash("Student not found.", "error")
        return redirect(url_for("facetrack.students"))

    db.delete_student(pk)
    _face_engine().delete_student_data(pk)
    _firebase().delete_student(pk)
    flash(f"Deleted {student['name']} and retraining the model...", "info")

    def retrain_job():
        _face_engine().train()

    threading.Thread(target=retrain_job, daemon=True).start()
    return redirect(url_for("facetrack.students"))


# ------------------------------------------------------------------- history
@bp.route("/history")
def history():
    return render_template("history.html", active="history", sessions=_db().get_all_sessions())


@bp.route("/history/<int:session_id>")
def history_detail(session_id):
    db = _db()
    attendance = db.get_attendance_for_session(session_id)
    session_row = next((s for s in db.get_all_sessions() if s["id"] == session_id), None)
    if session_row is None:
        flash("Session not found.", "error")
        return redirect(url_for("facetrack.history"))
    return render_template(
        "history_detail.html", active="history",
        session=session_row, attendance=attendance,
    )


@bp.route("/history/<int:session_id>/export.csv")
def history_export(session_id):
    rows = _db().get_attendance_for_session(session_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Student ID", "Name", "Timestamp", "Method"])
    for att in rows:
        writer.writerow([att["student_id"], att["name"], att["timestamp"], att["method"]])

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(
        mem, mimetype="text/csv", as_attachment=True,
        download_name=f"session_{session_id}_attendance.csv",
    )
