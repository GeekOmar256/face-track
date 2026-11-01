"""Background polling for the HC-SR04 distance sensor.

Runs only while an attendance session is active (started/stopped by
routes.py alongside the session itself) and caches the latest reading for
CameraWorker's session loop to check cheaply every frame.
"""
import threading
import time

from ..ultrasonic import UltrasonicSensor

POLL_INTERVAL = 0.2


class UltrasonicWorker:
    def __init__(self):
        self.sensor = UltrasonicSensor()
        self.hardware_available = self.sensor.hardware_available

        self.lock = threading.Lock()
        self.distance_cm = None
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        with self.lock:
            self.distance_cm = None
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        t = self.thread
        self.thread = None
        if t is not None and t.is_alive():
            t.join(timeout=2)
        with self.lock:
            self.distance_cm = None

    def get_distance_cm(self):
        with self.lock:
            return self.distance_cm

    def _loop(self):
        while self.running:
            d = self.sensor.measure_cm()
            with self.lock:
                self.distance_cm = d
            time.sleep(POLL_INTERVAL)
