"""Drives the 16x2 LCD: a resting screen that says whether a session is
running, plus short result messages (recorded, already recorded, unknown
face/card/finger) that go back to the resting screen after a few seconds.

Called from the camera loop, the RFID and fingerprint polling threads and
request handlers, so every write goes through one lock.
"""
import threading
import time

from ..lcd import LCDDisplay, fit

RESULT_HOLD_SECONDS = 3.0

# Resting screens. "No session active" is 17 characters, one too many for a
# 16-character row, so it's split over the two rows.
NO_SESSION_SCREEN = ("No session", "active")
SESSION_SCREEN = ("Session active", "Scan to check in")


class LCDNotifier:
    def __init__(self, display=None):
        self.display = display or LCDDisplay()
        self.hardware_available = self.display.hardware_available
        self._lock = threading.Lock()
        self._idle = NO_SESSION_SCREEN
        self._revert_at = None
        self.display.show(*self._idle)
        threading.Thread(target=self._revert_loop, daemon=True).start()

    def set_idle(self, line1, line2):
        with self._lock:
            self._idle = (line1, line2)
            if self._revert_at is None:
                self.display.show(line1, line2)

    def show_result(self, line1, line2, hold=None):
        hold = RESULT_HOLD_SECONDS if hold is None else hold
        with self._lock:
            # The face loop re-reports the same result every frame; only
            # extend the timer then, instead of rewriting the I2C display.
            if self.display.lines != (fit(line1), fit(line2)) or self._revert_at is None:
                self.display.show(line1, line2)
            self._revert_at = time.monotonic() + hold

    def _revert_loop(self):
        while True:
            time.sleep(0.2)
            with self._lock:
                if self._revert_at is not None and time.monotonic() >= self._revert_at:
                    self._revert_at = None
                    self.display.show(*self._idle)
