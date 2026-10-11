"""RC522 RFID reader abstraction.

On a Raspberry Pi with an RC522 wired to the SPI pins, this reads real
card UIDs via the `mfrc522` package (SPI + RPi.GPIO). Both the import and
the GPIO setup are wrapped in try/except: on any other machine - or a Pi
where SPI isn't enabled yet, or the reader isn't wired up - this degrades
to a reader that never sees a card, and `hardware_available` is False so
the web UI can offer a manual "simulate a scan" fallback instead.
"""
try:
    from mfrc522 import MFRC522
except Exception:
    MFRC522 = None


class RFIDReader:
    def __init__(self):
        self._reader = None
        self.hardware_available = False
        if MFRC522 is not None:
            try:
                self._reader = MFRC522()
                self.hardware_available = True
            except Exception:
                self._reader = None

    def poll_once(self):
        """Non-blocking check for a card. Returns a UID string such as
        "04-A1-B2-C3" if one is present right now, else None."""
        if self._reader is None:
            return None
        status, _ = self._reader.MFRC522_Request(self._reader.PICC_REQIDL)
        if status != self._reader.MI_OK:
            return None
        status, uid = self._reader.MFRC522_Anticoll()
        if status != self._reader.MI_OK:
            return None
        return "-".join(f"{b:02X}" for b in uid[:4])
