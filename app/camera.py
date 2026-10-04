"""Thin wrapper around cv2.VideoCapture."""
import cv2

from . import config


class Camera:
    def __init__(self, index=None):
        self.index = config.CAMERA_INDEX if index is None else index
        self._cap = None

    def open(self):
        if self._cap is not None:
            return
        self._cap = cv2.VideoCapture(self.index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise RuntimeError(
                f"Could not open camera index {self.index}. "
                "Check that it is connected and not in use by another app."
            )

    def read(self):
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok:
            return None
        return frame

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_open(self):
        return self._cap is not None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
