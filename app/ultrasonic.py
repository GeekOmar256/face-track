"""HC-SR04 ultrasonic distance sensor abstraction.

Trigger/echo pulse timing over GPIO (via RPi.GPIO). As with camera.py,
rfid.py and fingerprint.py: wrapped in try/except so a machine without
RPi.GPIO or the physical sensor just gets a sensor that never reports a
distance, which fails open (face recognition's proximity gate stays open,
i.e. always runs) rather than breaking anything.
"""
import os
import time

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

TRIG_PIN = int(os.environ.get("ULTRASONIC_TRIG_PIN", "23"))
ECHO_PIN = int(os.environ.get("ULTRASONIC_ECHO_PIN", "24"))
_PULSE_TIMEOUT = 0.04  # ~6.8m round trip worth of wait - generous margin


class UltrasonicSensor:
    def __init__(self):
        self.hardware_available = False
        if GPIO is not None:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(TRIG_PIN, GPIO.OUT)
                GPIO.setup(ECHO_PIN, GPIO.IN)
                GPIO.output(TRIG_PIN, False)
                time.sleep(0.2)  # let the sensor settle
                self.hardware_available = True
            except Exception:
                self.hardware_available = False

    def measure_cm(self):
        """One blocking distance reading in centimeters, or None on
        timeout / no hardware."""
        if not self.hardware_available:
            return None
        try:
            GPIO.output(TRIG_PIN, True)
            time.sleep(0.00001)
            GPIO.output(TRIG_PIN, False)

            start = time.time()
            timeout_at = start + _PULSE_TIMEOUT
            while GPIO.input(ECHO_PIN) == 0:
                start = time.time()
                if start > timeout_at:
                    return None

            end = time.time()
            timeout_at = end + _PULSE_TIMEOUT
            while GPIO.input(ECHO_PIN) == 1:
                end = time.time()
                if end > timeout_at:
                    return None

            elapsed = end - start
            return (elapsed * 34300) / 2  # speed of sound ~343 m/s, round trip
        except Exception:
            return None
