"""AS608 / R307 / FPM10A-family fingerprint sensor abstraction (UART).

These optical sensors share the same serial protocol, read via the
`pyfingerprint` package. As with camera.py and rfid.py, both the import
and the device handshake are wrapped in try/except: on any machine where
the library or the physical sensor isn't available, this degrades to a
reader that never sees a finger, and `hardware_available` is False so the
web UI can offer a manual "simulate" fallback instead.
"""
import os

try:
    from pyfingerprint.pyfingerprint import PyFingerprint
except Exception:
    PyFingerprint = None

SERIAL_PORT = os.environ.get("FINGERPRINT_SERIAL_PORT", "/dev/ttyUSB0")
BAUD_RATE = int(os.environ.get("FINGERPRINT_BAUD_RATE", "57600"))


class FingerprintSensor:
    def __init__(self):
        self._sensor = None
        self.hardware_available = False
        if PyFingerprint is not None:
            try:
                sensor = PyFingerprint(SERIAL_PORT, BAUD_RATE, 0xFFFFFFFF, 0x00000000)
                if sensor.verifyPassword():
                    self._sensor = sensor
                    self.hardware_available = True
            except Exception:
                self._sensor = None

    def finger_present(self):
        """Checks for a finger right now; if present, also captures the
        image into the sensor's buffer (ready for convert())."""
        if self._sensor is None:
            return False
        try:
            return bool(self._sensor.readImage())
        except Exception:
            return False

    def convert(self, slot):
        """slot: 1 or 2, the two character buffers an enrollment compares."""
        self._sensor.convertImage(slot)

    def create_and_store_template(self):
        """Combines the two converted buffers into a template and stores it
        in the first free slot. Returns that slot's position number."""
        self._sensor.createTemplate()
        return self._sensor.storeTemplate()

    def delete_template(self, position):
        if self._sensor is None:
            return
        try:
            self._sensor.deleteTemplate(position)
        except Exception:
            pass

    def search(self):
        """Searches the just-converted (slot 1) image against all stored
        templates. Returns (position, score); position is -1 if no match."""
        return self._sensor.searchTemplate()
