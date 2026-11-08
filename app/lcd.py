"""16x2 character LCD (HD44780) behind a PCF8574 I2C backpack, via RPLCD.

Same pattern as rfid.py, fingerprint.py and ultrasonic.py: if RPLCD/smbus2
isn't installed or no display answers on the I2C bus, this becomes a mock
that only remembers the last two lines, so nothing else breaks.
"""
import os
import unicodedata

try:
    from RPLCD.i2c import CharLCD
except Exception:
    CharLCD = None

# Most PCF8574 backpacks are 0x27; some are 0x3F. `i2cdetect -y 1` shows it.
LCD_I2C_ADDRESS = int(os.environ.get("LCD_I2C_ADDRESS", "0x27"), 16)
LCD_I2C_PORT = int(os.environ.get("LCD_I2C_PORT", "1"))
COLS = 16
ROWS = 2


def to_lcd_text(text):
    """ASCII-only version of `text`. The HD44780 character ROM has no
    accented or Arabic glyphs, so accents are stripped and anything else
    non-ASCII is dropped."""
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").strip()


def fit(text):
    return to_lcd_text(text)[:COLS].ljust(COLS)


class LCDDisplay:
    def __init__(self):
        self.hardware_available = False
        self.lines = (fit(""), fit(""))
        self._lcd = None
        if CharLCD is None:
            return
        try:
            self._lcd = CharLCD(
                "PCF8574", LCD_I2C_ADDRESS, port=LCD_I2C_PORT,
                cols=COLS, rows=ROWS, charmap="A00",
            )
            self._lcd.clear()
            self.hardware_available = True
        except Exception:
            self._lcd = None

    def show(self, line1, line2=""):
        """Overwrite both rows. Rows are padded to full width instead of
        calling clear(), which avoids a visible blink on every update."""
        self.lines = (fit(line1), fit(line2))
        if self._lcd is None:
            return
        try:
            for row, text in enumerate(self.lines):
                self._lcd.cursor_pos = (row, 0)
                self._lcd.write_string(text)
        except Exception:
            pass  # a loose wire mid-session shouldn't take attendance down with it
