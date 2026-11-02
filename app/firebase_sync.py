"""Optional, one-way Firestore sync: pushes students, sessions and
attendance to Firebase so a separate teacher/student-facing app can read
live data from this Pi.

This never reads back from Firestore and never blocks local operation:
if `firebase-admin` isn't installed, or no credentials file is configured,
every method here is a silent no-op and the SQLite-backed app behaves
exactly as it does without Firebase. Any Firestore error during a push is
swallowed the same way - sync is best-effort, not a dependency.

Credentials: point FIREBASE_CREDENTIALS_PATH at a Firebase service-account
JSON file (Firebase Console -> Project settings -> Service accounts ->
Generate new private key). Never commit that file or paste its contents
anywhere; data/ is already gitignored, which is where it's expected to
live by default.
"""
import os

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "firebase_credentials.json"),
)


class FirebaseSync:
    def __init__(self):
        self.available = False
        self._db = None
        if firebase_admin is None:
            return
        path = os.path.abspath(CREDENTIALS_PATH)
        if not os.path.isfile(path):
            return
        try:
            cred = credentials.Certificate(path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self._db = firestore.client()
            self.available = True
        except Exception:
            self.available = False

    def _set(self, collection, doc_id, data):
        if not self.available:
            return
        try:
            self._db.collection(collection).document(str(doc_id)).set(data, merge=True)
        except Exception:
            pass

    def _delete(self, collection, doc_id):
        if not self.available:
            return
        try:
            self._db.collection(collection).document(str(doc_id)).delete()
        except Exception:
            pass

    # -------------------------------------------------------------- students
    def push_student(self, student_row):
        self._set("students", student_row["id"], {
            "student_id": student_row["student_id"],
            "name": student_row["name"],
            "date_added": student_row["date_added"],
            "photo_count": student_row["photo_count"],
            "has_rfid": bool(student_row["rfid_uid"]),
            "has_fingerprint": student_row["fingerprint_id"] is not None,
            "status": student_row["status"],
        })

    def delete_student(self, pk):
        self._delete("students", pk)

    # ---------------------------------------------------------- student portal
    # Keyed by the human-chosen student_id (not the internal pk) and kept
    # deliberately thin - this is the one doc a student can read without
    # logging in (see webapp/firestore.rules: get-only, no list), so it
    # only ever holds this one student's own name/attendance, never RFID
    # UIDs, fingerprint slots, or anything about other students.
    def push_student_stats(self, student_row, attendance_rows):
        records = [
            {
                "session_id": a["session_id"],
                "session_name": a["session_name"],
                "timestamp": a["timestamp"],
                "method": a["method"],
            }
            for a in attendance_rows
        ][:100]
        self._set("student_stats", student_row["student_id"], {
            "student_id": student_row["student_id"],
            "name": student_row["name"],
            "total_present": len(attendance_rows),
            "records": records,
        })

    def delete_student_stats(self, student_id):
        self._delete("student_stats", student_id)

    # -------------------------------------------------------------- sessions
    def push_session(self, session_row):
        self._set("sessions", session_row["id"], {
            "name": session_row["name"],
            "start_time": session_row["start_time"],
            "end_time": session_row["end_time"],
        })

    # ------------------------------------------------------------ attendance
    def push_attendance(self, session_id, student_row, timestamp, method):
        doc_id = f"{session_id}_{student_row['id']}"
        self._set("attendance", doc_id, {
            "session_id": session_id,
            "student_pk": student_row["id"],
            "student_id": student_row["student_id"],
            "name": student_row["name"],
            "timestamp": timestamp,
            "method": method,
        })
