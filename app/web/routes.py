"""HTTP routes for the Face Track web interface."""
import csv
import io
import threading

from flask import (
    Blueprint, Response, current_app, flash, jsonify, redirect,
    render_template, request, send_file, url_for,
)

bp = Blueprint("facetrack", __name__)


def _db():
    return current_app.config["DB"]


def _face_engine():
    return current_app.config["FACE_ENGINE"]


def _worker():
    return current_app.config["WORKER"]


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
    try:
        pk, count = _worker().finish_enrollment()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"pk": pk, "count": count})


@bp.route("/add-student/status")
def add_student_status():
    return jsonify(_worker().status())


@bp.route("/add-student/cancel", methods=["POST"])
def add_student_cancel():
    _worker().cancel_enrollment()
    return jsonify({"ok": True})


# -------------------------------------------------------------------- session
@bp.route("/session")
def session_page():
    return render_template("session.html", active="session")


@bp.route("/session/start", methods=["POST"])
def session_start():
    try:
        session_id = _worker().start_session()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"session_id": session_id})


@bp.route("/session/status")
def session_status():
    return jsonify(_worker().status())


@bp.route("/session/stop", methods=["POST"])
def session_stop():
    session_id, present = _worker().stop_session()
    return jsonify({"session_id": session_id, "present_count": present})


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
    writer.writerow(["Student ID", "Name", "Timestamp"])
    for att in rows:
        writer.writerow([att["student_id"], att["name"], att["timestamp"]])

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(
        mem, mimetype="text/csv", as_attachment=True,
        download_name=f"session_{session_id}_attendance.csv",
    )
