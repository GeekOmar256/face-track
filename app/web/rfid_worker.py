"""Background RFID (RC522) polling.

Independent of the camera worker - the card reader and the webcam are
different hardware, so enrollment and attendance sessions can use the
card and/or the face recognizer at the same time. The reader device
itself is opened once and kept for the app's lifetime; only the polling
*thread* is started and stopped per operation.
"""
import threading
import time

from ..rfid import RFIDReader

IDLE = "idle"
ENROLL = "enroll"
SESSION = "session"


class RFIDWorker:
    def __init__(self):
        self.reader = RFIDReader()
        self.hardware_available = self.reader.hardware_available

        self.lock = threading.Lock()
        self.mode = IDLE
        self.running = False
        self.thread = None

        # enroll-mode result (set by whatever on_scanned() callback does)
        self.scanned_uid = None
        self.scan_error = None
        self.on_scanned = None

        # session-mode
        self.on_card = None
        self._last_uid = None
        self._last_uid_time = 0

    def status(self):
        with self.lock:
            return {
                "mode": self.mode,
                "hardware_available": self.hardware_available,
                "scanned_uid": self.scanned_uid,
                "scan_error": self.scan_error,
            }

    # ------------------------------------------------------------ enroll
    def start_scan(self, on_scanned):
        """Wait for one card. `on_scanned(uid)` is called from the polling
        thread as soon as a card is seen; raise ValueError from it to
        reject the scan (e.g. duplicate card) and surface that as
        `scan_error`."""
        with self.lock:
            if self.mode != IDLE:
                raise RuntimeError("RFID reader is busy with another operation.")
            self.scanned_uid = None
            self.scan_error = None
            self.on_scanned = on_scanned
            self.mode = ENROLL
            self._start_thread_locked(self._enroll_loop)

    def cancel_scan(self):
        with self.lock:
            if self.mode != ENROLL:
                return
            self._stop_thread_locked()

    # ----------------------------------------------------------- session
    def start_session_scan(self, on_card):
        """Continuously call `on_card(uid)` for every card seen, until
        stop_session_scan() is called."""
        with self.lock:
            if self.mode != IDLE:
                raise RuntimeError("RFID reader is busy with another operation.")
            self.on_card = on_card
            self._last_uid = None
            self._last_uid_time = 0
            self.mode = SESSION
            self._start_thread_locked(self._session_loop)

    def stop_session_scan(self):
        with self.lock:
            if self.mode != SESSION:
                return
            self._stop_thread_locked()
            self.on_card = None

    # ------------------------------------------------------- dev fallback
    def inject_uid(self, uid):
        """Manually supply a UID, as if the reader had just scanned it.
        Used by the web UI's "simulate a scan" box when no RC522 hardware
        is attached, so the rest of the flow can still be tested/used."""
        with self.lock:
            if self.mode == ENROLL:
                self._handle_scanned(uid)
                self._stop_thread_locked()
            elif self.mode == SESSION and self.on_card:
                self.on_card(uid)

    # ----------------------------------------------------------- plumbing
    def _start_thread_locked(self, target):
        self.running = True
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def _stop_thread_locked(self):
        self.running = False
        t = self.thread
        self.thread = None
        if t is not None and t.is_alive():
            t.join(timeout=2)
        self.mode = IDLE

    def _handle_scanned(self, uid):
        try:
            if self.on_scanned:
                self.on_scanned(uid)
            self.scanned_uid = uid
        except ValueError as exc:
            self.scan_error = str(exc)

    # ----------------------------------------------------------- the loops
    def _enroll_loop(self):
        while self.running:
            uid = self.reader.poll_once()
            if uid:
                self._handle_scanned(uid)
                self.running = False
                break
            time.sleep(0.15)
        self.mode = IDLE

    def _session_loop(self):
        while self.running:
            uid = self.reader.poll_once()
            if uid:
                now = time.time()
                if uid != self._last_uid or now - self._last_uid_time > 1.5:
                    self._last_uid = uid
                    self._last_uid_time = now
                    if self.on_card:
                        self.on_card(uid)
            time.sleep(0.15)
