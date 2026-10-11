"""SQLite data access layer for students, sessions and attendance records."""
import sqlite3
import threading
from datetime import datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    date_added  TEXT NOT NULL,
    photo_count INTEGER NOT NULL DEFAULT 0,
    rfid_uid    TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT,
    start_time TEXT NOT NULL,
    end_time   TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    student_pk INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    timestamp  TEXT NOT NULL,
    method     TEXT NOT NULL DEFAULT 'face',
    UNIQUE(session_id, student_pk)
);
"""

# Columns added after the initial release. Applied with ALTER TABLE on
# existing databases so upgrades don't lose data; CREATE TABLE above
# already includes them for brand-new databases.
_MIGRATIONS = [
    ("students", "rfid_uid", "ALTER TABLE students ADD COLUMN rfid_uid TEXT"),
    ("attendance", "method", "ALTER TABLE attendance ADD COLUMN method TEXT NOT NULL DEFAULT 'face'"),
]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """Thin, thread-safe wrapper around sqlite3.

    A single connection is shared (the GUI's camera loop and button
    handlers both touch it from the same Tk thread in this app), guarded
    by a lock in case that ever changes.
    """

    def __init__(self, db_path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self._run_migrations()

    def _run_migrations(self):
        for table, column, statement in _MIGRATIONS:
            cols = [r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in cols:
                self._conn.execute(statement)
                self._conn.commit()
        # The unique index on rfid_uid is created in SCHEMA for new DBs; make
        # sure it also exists on databases upgraded from before this column.
        self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_rfid ON students(rfid_uid)")
        self._conn.commit()

    # ---------------------------------------------------------------- students
    def add_student(self, student_id, name):
        student_id = student_id.strip()
        name = name.strip()
        if not student_id or not name:
            raise ValueError("Student ID and name are required.")
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO students (student_id, name, date_added, photo_count) "
                    "VALUES (?, ?, ?, 0)",
                    (student_id, name, _now()),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Student ID '{student_id}' already exists.")
            return cur.lastrowid

    def update_photo_count(self, pk, count):
        with self._lock:
            self._conn.execute(
                "UPDATE students SET photo_count = ? WHERE id = ?", (count, pk)
            )
            self._conn.commit()

    def delete_student(self, pk):
        with self._lock:
            self._conn.execute("DELETE FROM students WHERE id = ?", (pk,))
            self._conn.commit()

    def get_all_students(self):
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM students ORDER BY name COLLATE NOCASE ASC"
            )
            return cur.fetchall()

    def get_student_by_pk(self, pk):
        with self._lock:
            cur = self._conn.execute("SELECT * FROM students WHERE id = ?", (pk,))
            return cur.fetchone()

    def count_students(self):
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM students")
            return cur.fetchone()[0]

    def get_student_by_rfid(self, uid):
        with self._lock:
            cur = self._conn.execute("SELECT * FROM students WHERE rfid_uid = ?", (uid,))
            return cur.fetchone()

    def set_student_rfid(self, pk, uid):
        """Attach (or clear, with uid=None) an RFID card UID to a student."""
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE students SET rfid_uid = ? WHERE id = ?", (uid, pk)
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError("This card is already assigned to another student.")

    # ---------------------------------------------------------------- sessions
    def create_session(self, name=None):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO sessions (name, start_time, end_time) VALUES (?, ?, NULL)",
                (name, _now()),
            )
            self._conn.commit()
            return cur.lastrowid

    def end_session(self, session_id):
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET end_time = ? WHERE id = ?", (_now(), session_id)
            )
            self._conn.commit()

    def get_all_sessions(self):
        with self._lock:
            cur = self._conn.execute(
                "SELECT s.*, "
                "(SELECT COUNT(*) FROM attendance a WHERE a.session_id = s.id) AS present_count "
                "FROM sessions s ORDER BY s.start_time DESC"
            )
            return cur.fetchall()

    # -------------------------------------------------------------- attendance
    def mark_attendance(self, session_id, student_pk, method="face"):
        """Insert an attendance row. Returns True if newly marked, False if
        the student was already marked present in this session. `method`
        is 'face' or 'rfid', recorded for the history view."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO attendance (session_id, student_pk, timestamp, method) "
                "VALUES (?, ?, ?, ?)",
                (session_id, student_pk, _now(), method),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def is_marked(self, session_id, student_pk):
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM attendance WHERE session_id = ? AND student_pk = ?",
                (session_id, student_pk),
            )
            return cur.fetchone() is not None

    def get_marked_pks_for_session(self, session_id):
        with self._lock:
            cur = self._conn.execute(
                "SELECT student_pk FROM attendance WHERE session_id = ?", (session_id,)
            )
            return {row["student_pk"] for row in cur.fetchall()}

    def get_attendance_for_session(self, session_id):
        with self._lock:
            cur = self._conn.execute(
                "SELECT a.id, a.timestamp, a.method, st.student_id, st.name, st.id AS student_pk "
                "FROM attendance a JOIN students st ON st.id = a.student_pk "
                "WHERE a.session_id = ? ORDER BY a.timestamp ASC",
                (session_id,),
            )
            return cur.fetchall()

    def get_attendance_for_student(self, student_pk):
        with self._lock:
            cur = self._conn.execute(
                "SELECT a.*, s.name AS session_name, s.start_time AS session_start "
                "FROM attendance a JOIN sessions s ON s.id = a.session_id "
                "WHERE a.student_pk = ? ORDER BY a.timestamp DESC",
                (student_pk,),
            )
            return cur.fetchall()

    def close(self):
        with self._lock:
            self._conn.close()
