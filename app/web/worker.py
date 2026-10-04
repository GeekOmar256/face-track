"""Background camera worker shared by the enrollment and session pages.

Only one operation (enrolling a student, or running an attendance session)
can use the camera at a time. The worker owns the camera and a background
thread; routes just call start/stop methods and poll `status()`. Frames are
published as JPEG bytes for MJPEG streaming via /video_feed.
"""
import threading
import time
from datetime import datetime

import cv2

from .. import config
from ..camera import Camera

IDLE = "idle"
ENROLL = "enroll"
SESSION = "session"


class CameraWorker:
    def __init__(self, db, face_engine):
        self.db = db
        self.face_engine = face_engine

        self.state_lock = threading.Lock()   # guards start/stop transitions
        self.frame_lock = threading.Lock()   # guards latest_jpeg

        self.mode = IDLE
        self.camera = None
        self.thread = None
        self.running = False
        self.latest_jpeg = None
        self.error = None

        # enrollment state
        self.enroll_pk = None
        self.enroll_count = 0
        self.enroll_complete = False
        self.enroll_training = False
        self._last_preview_frame = None   # raw BGR frame, for capture_photo()
        self._last_preview_face = None    # (x, y, w, h) of the detected face, or None

        # session state
        self.session_id = None
        self.marked_pks = set()
        self.session_log = []

    # ------------------------------------------------------------- status
    def status(self):
        with self.frame_lock:
            return {
                "mode": self.mode,
                "error": self.error,
                "enroll_count": self.enroll_count,
                "enroll_complete": self.enroll_complete,
                "enroll_training": self.enroll_training,
                "session_id": self.session_id,
                "present_count": len(self.marked_pks),
                "log": list(self.session_log),
            }

    def get_jpeg(self):
        with self.frame_lock:
            return self.latest_jpeg

    # --------------------------------------------------------- enrollment
    def start_enrollment(self, student_id, name):
        with self.state_lock:
            if self.mode != IDLE:
                raise RuntimeError("The camera is busy with another operation.")
            pk = self.db.add_student(student_id, name)  # may raise ValueError
            self.enroll_pk = pk
            self.enroll_count = 0
            self.enroll_complete = False
            self.enroll_training = False
            self.error = None
            self._last_preview_frame = None
            self._last_preview_face = None
            self.mode = ENROLL
            try:
                self._start_thread(self._enroll_preview_loop)
            except RuntimeError:
                self.mode = IDLE
                self.db.delete_student(pk)
                raise
            return pk

    def capture_photo(self):
        """Save exactly one face sample from whatever the camera currently
        sees. Can be called repeatedly to build up the student's photo set."""
        if self.mode != ENROLL:
            raise RuntimeError("No enrollment in progress.")
        with self.frame_lock:
            frame = self._last_preview_frame
            face = self._last_preview_face
        if frame is None or face is None:
            raise RuntimeError("No face detected. Face the camera and try again.")

        x, y, w, h = face
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.enroll_count += 1
        self.face_engine.save_face_sample(self.enroll_pk, self.enroll_count, gray[y:y + h, x:x + w])
        return self.enroll_count

    def finish_enrollment(self):
        """Stop the camera, keep whatever photos were captured, and train."""
        with self.state_lock:
            if self.mode != ENROLL:
                raise RuntimeError("No enrollment in progress.")
            pk = self.enroll_pk
            count = self.enroll_count
            self._stop_thread_locked()

        if count < 1:
            self.face_engine.delete_student_data(pk)
            self.db.delete_student(pk)
            raise RuntimeError("Capture at least one photo before finishing.")

        self.db.update_photo_count(pk, count)
        self.enroll_training = True

        def train_job():
            self.face_engine.train()
            self.enroll_training = False
            self.enroll_complete = True

        threading.Thread(target=train_job, daemon=True).start()
        return pk, count

    def cancel_enrollment(self):
        with self.state_lock:
            if self.mode != ENROLL:
                return
            pk = self.enroll_pk
            self._stop_thread_locked()
        if pk is not None:
            self.face_engine.delete_student_data(pk)
            self.db.delete_student(pk)

    # ------------------------------------------------------------ session
    def start_session(self):
        with self.state_lock:
            if self.mode != IDLE:
                raise RuntimeError("The camera is busy with another operation.")
            if not self.face_engine.model_loaded:
                raise RuntimeError("No trained model yet - enroll at least one student first.")
            self.session_id = self.db.create_session(
                name=datetime.now().strftime("Session %Y-%m-%d %H:%M")
            )
            self.marked_pks = set()
            self.session_log = []
            self.mode = SESSION
            try:
                self._start_thread(self._session_loop)
            except RuntimeError:
                self.mode = IDLE
                raise
            return self.session_id

    def stop_session(self):
        with self.state_lock:
            if self.mode != SESSION:
                return None, 0
            sid = self.session_id
            present = len(self.marked_pks)
            self._stop_thread_locked()
        self.db.end_session(sid)
        return sid, present

    # ------------------------------------------------------------ plumbing
    def _start_thread(self, target):
        try:
            cam = Camera()
            cam.open()
        except RuntimeError as exc:
            self.error = str(exc)
            raise
        self.camera = cam
        self.running = True
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def _stop_thread_locked(self):
        self.running = False
        t = self.thread
        self.thread = None
        if t is not None and t.is_alive():
            t.join(timeout=3)
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.mode = IDLE
        with self.frame_lock:
            self.latest_jpeg = None

    def _publish(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with self.frame_lock:
                self.latest_jpeg = buf.tobytes()

    # ----------------------------------------------------------- the loops
    def _enroll_preview_loop(self):
        """Stream the camera and track the current face box; actual photo
        capture happens on demand via capture_photo(), not automatically."""
        while self.running:
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            faces = self.face_engine.detect_faces(frame)
            face = self.face_engine.largest_face(faces)

            display = frame.copy()
            if face is not None:
                x, y, w, h = face
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 200, 0), 2)

            cv2.putText(
                display, f"Photos captured: {self.enroll_count}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2,
            )

            with self.frame_lock:
                self._last_preview_frame = frame
                self._last_preview_face = face
            self._publish(display)

    def _session_loop(self):
        while self.running:
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_engine.detect_faces(frame)

            for (x, y, w, h) in faces:
                label, confidence = self.face_engine.predict(gray[y:y + h, x:x + w])
                color = (0, 0, 255)
                caption = "Unknown"

                if (
                    label is not None
                    and confidence is not None
                    and confidence <= config.RECOGNITION_CONFIDENCE_THRESHOLD
                ):
                    student = self.db.get_student_by_pk(label)
                    if student is not None:
                        if label in self.marked_pks:
                            color = (255, 165, 0)
                            caption = f"{student['name']} (marked)"
                        else:
                            newly_marked = self.db.mark_attendance(self.session_id, label)
                            if newly_marked:
                                self.marked_pks.add(label)
                                color = (0, 200, 0)
                                caption = f"{student['name']} - present"
                                self.session_log.append({
                                    "time": datetime.now().strftime("%H:%M:%S"),
                                    "name": student["name"],
                                    "student_id": student["student_id"],
                                })

                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(
                    frame, caption, (x, max(0, y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                )

            self._publish(frame)
