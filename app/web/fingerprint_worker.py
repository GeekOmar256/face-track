"""Background fingerprint (AS608/R307/FPM10A) polling.

Independent of the camera and RFID workers - different hardware, so all
three can be used concurrently. Enrollment is a two-step wizard (the
sensor needs the same finger placed twice to build a template), unlike
RFID's single tap; `stage` in status() drives the UI through it.
"""
import threading
import time

from ..fingerprint import FingerprintSensor

IDLE = "idle"
ENROLL = "enroll"
SESSION = "session"

STAGE_PLACE_FIRST = "place_first"
STAGE_REMOVE = "remove"
STAGE_PLACE_SECOND = "place_second"
STAGE_DONE = "done"


class FingerprintWorker:
    def __init__(self):
        self.sensor = FingerprintSensor()
        self.hardware_available = self.sensor.hardware_available

        self.lock = threading.Lock()
        self.mode = IDLE
        self.running = False
        self.thread = None

        # enroll state
        self.stage = None
        self.enrolled_position = None
        self.scan_error = None
        self.on_enrolled = None  # callback(position) -> may raise ValueError

        # session state
        self.on_match = None
        self._last_position = None
        self._last_time = 0

    def status(self):
        with self.lock:
            return {
                "mode": self.mode,
                "hardware_available": self.hardware_available,
                "stage": self.stage,
                "enrolled_position": self.enrolled_position,
                "scan_error": self.scan_error,
            }

    # ------------------------------------------------------------ enroll
    def start_enroll(self, on_enrolled):
        with self.lock:
            if self.mode != IDLE:
                raise RuntimeError("Fingerprint sensor is busy with another operation.")
            self.stage = STAGE_PLACE_FIRST
            self.enrolled_position = None
            self.scan_error = None
            self.on_enrolled = on_enrolled
            self.mode = ENROLL
            self._start_thread_locked(self._enroll_loop)

    def cancel_enroll(self):
        with self.lock:
            if self.mode != ENROLL:
                return
            self._stop_thread_locked()

    # ----------------------------------------------------------- session
    def start_session_scan(self, on_match):
        """Continuously call `on_match(position)` for every recognized
        fingerprint, until stop_session_scan()."""
        with self.lock:
            if self.mode != IDLE:
                raise RuntimeError("Fingerprint sensor is busy with another operation.")
            self.on_match = on_match
            self._last_position = None
            self._last_time = 0
            self.mode = SESSION
            self._start_thread_locked(self._session_loop)

    def stop_session_scan(self):
        with self.lock:
            if self.mode != SESSION:
                return
            self._stop_thread_locked()
            self.on_match = None

    # ------------------------------------------------------- dev fallback
    def simulate_enroll_step(self):
        """Advance the enroll wizard as if a finger had just been read
        successfully. Used by the UI's 'simulate' fallback."""
        with self.lock:
            if self.mode != ENROLL:
                return
            self._advance_enroll_stage(simulated=True)

    def simulate_match(self, position):
        with self.lock:
            if self.mode == SESSION and self.on_match:
                self.on_match(position)

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
        self.stage = None

    def _advance_enroll_stage(self, simulated=False):
        try:
            if self.stage == STAGE_PLACE_FIRST:
                if not simulated:
                    self.sensor.convert(1)
                self.stage = STAGE_REMOVE
            elif self.stage == STAGE_PLACE_SECOND:
                if not simulated:
                    self.sensor.convert(2)
                    position = self.sensor.create_and_store_template()
                else:
                    position = 0
                self.enrolled_position = position
                if self.on_enrolled:
                    self.on_enrolled(position)
                self.stage = STAGE_DONE
                self.running = False
        except ValueError as exc:
            self.scan_error = str(exc)
            self.running = False
        except Exception as exc:
            self.scan_error = f"Sensor error: {exc}"
            self.running = False

    # ----------------------------------------------------------- the loops
    def _enroll_loop(self):
        while self.running:
            if self.stage == STAGE_REMOVE:
                # wait until the finger is lifted before asking for scan 2
                if not self.sensor.finger_present():
                    self.stage = STAGE_PLACE_SECOND
                time.sleep(0.2)
                continue

            if self.sensor.finger_present():
                self._advance_enroll_stage()
            time.sleep(0.15)
        self.mode = IDLE

    def _session_loop(self):
        while self.running:
            if self.sensor.finger_present():
                try:
                    self.sensor.convert(1)
                    position, _score = self.sensor.search()
                except Exception:
                    position = -1

                if position is not None and position >= 0:
                    now = time.time()
                    if position != self._last_position or now - self._last_time > 1.5:
                        self._last_position = position
                        self._last_time = now
                        if self.on_match:
                            self.on_match(position)
            time.sleep(0.15)
