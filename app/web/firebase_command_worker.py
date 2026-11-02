"""Executes remote commands written by the Firebase admin web app.

The web app never writes directly to the `students`/`sessions`/`attendance`
collections - it only creates documents in `commands` (start/stop a
session, pre-register a student, edit a name, delete a student). This
worker listens to that collection in real time via Firestore's `on_snapshot`
and runs each pending command through the exact same objects the local
Flask routes use, so remote and local actions behave identically. It marks
each command "done" or "error" when finished so the web app can show
feedback.

A no-op if Firebase isn't configured (see firebase_sync.py) - nothing here
runs without real credentials.
"""
import threading


class FirebaseCommandWorker:
    def __init__(self, firebase, db, face_engine, camera_worker, rfid_worker,
                 fingerprint_worker, ultrasonic_worker):
        self.firebase = firebase
        self.db = db
        self.face_engine = face_engine
        self.camera_worker = camera_worker
        self.rfid_worker = rfid_worker
        self.fingerprint_worker = fingerprint_worker
        self.ultrasonic_worker = ultrasonic_worker
        self._watch = None
        self._lock = threading.Lock()

    def start(self):
        if not self.firebase.available:
            return
        query = self.firebase._db.collection("commands").where("status", "==", "pending")
        self._watch = query.on_snapshot(self._on_snapshot)

    def stop(self):
        if self._watch is not None:
            self._watch.unsubscribe()
            self._watch = None

    def _on_snapshot(self, docs, changes, read_time):
        for change in changes:
            if change.type.name not in ("ADDED", "MODIFIED"):
                continue
            with self._lock:
                self._handle(change.document)

    def _handle(self, doc):
        data = doc.to_dict() or {}
        if data.get("status") != "pending":
            return
        try:
            result = self._dispatch(data.get("type"), data.get("payload") or {}) or {}
            doc.reference.update({"status": "done", "result": result})
        except Exception as exc:
            doc.reference.update({"status": "error", "error_message": str(exc)})

    def _dispatch(self, cmd_type, payload):
        handlers = {
            "start_session": self._start_session,
            "stop_session": self._stop_session,
            "pre_register_student": self._pre_register_student,
            "update_student": self._update_student,
            "delete_student": self._delete_student,
        }
        handler = handlers.get(cmd_type)
        if handler is None:
            raise ValueError(f"Unknown command type: {cmd_type!r}")
        return handler(payload)

    # ------------------------------------------------------------ session
    def _start_session(self, payload):
        session_id = self.camera_worker.start_session()
        session_row = next((s for s in self.db.get_all_sessions() if s["id"] == session_id), None)
        if session_row is not None:
            self.firebase.push_session(session_row)

        def on_card(uid):
            student = self.db.get_student_by_rfid(uid)
            if student is not None:
                self.camera_worker.mark_present(student["id"], "rfid")

        try:
            self.rfid_worker.start_session_scan(on_card)
        except RuntimeError:
            pass  # reader busy/unavailable - face recognition still works

        def on_fingerprint(position):
            student = self.db.get_student_by_fingerprint(position)
            if student is not None:
                self.camera_worker.mark_present(student["id"], "fingerprint")

        try:
            self.fingerprint_worker.start_session_scan(on_fingerprint)
        except RuntimeError:
            pass  # sensor busy/unavailable - other methods still work

        self.ultrasonic_worker.start()
        return {"session_id": session_id}

    def _stop_session(self, payload):
        self.rfid_worker.stop_session_scan()
        self.fingerprint_worker.stop_session_scan()
        self.ultrasonic_worker.stop()
        session_id, present = self.camera_worker.stop_session()
        if session_id is not None:
            session_row = next((s for s in self.db.get_all_sessions() if s["id"] == session_id), None)
            if session_row is not None:
                self.firebase.push_session(session_row)
        return {"session_id": session_id, "present_count": present}

    # ------------------------------------------------------------ students
    def _pre_register_student(self, payload):
        student_id = (payload.get("student_id") or "").strip()
        name = (payload.get("name") or "").strip()
        if not student_id or not name:
            raise ValueError("student_id and name are required.")
        pk = self.db.add_student(student_id, name, status="pending_biometric")
        student = self.db.get_student_by_pk(pk)
        self.firebase.push_student(student)
        self.firebase.push_student_stats(student, [])
        return {"pk": pk}

    def _update_student(self, payload):
        pk = payload.get("pk")
        name = (payload.get("name") or "").strip()
        if pk is None or not name:
            raise ValueError("pk and name are required.")
        pk = int(pk)
        self.db.update_student_name(pk, name)
        student = self.db.get_student_by_pk(pk)
        if student is None:
            raise ValueError("Student not found.")
        self.firebase.push_student(student)
        self.firebase.push_student_stats(student, self.db.get_attendance_for_student(pk))
        return {"pk": pk}

    def _delete_student(self, payload):
        pk = payload.get("pk")
        if pk is None:
            raise ValueError("pk is required.")
        pk = int(pk)
        student = self.db.get_student_by_pk(pk)
        if student is None:
            raise ValueError("Student not found.")

        self.db.delete_student(pk)
        self.face_engine.delete_student_data(pk)
        self.firebase.delete_student(pk)
        self.firebase.delete_student_stats(student["student_id"])

        def retrain_job():
            self.face_engine.train()

        threading.Thread(target=retrain_job, daemon=True).start()
        return {"pk": pk}
