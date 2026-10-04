"""Face detection, dataset capture and LBPH recognition.

Uses OpenCV's YuNet (a small ONNX DNN, via cv2.FaceDetectorYN) for
detection and the LBPH recognizer for recognition. Both run comfortably on
a Raspberry Pi without needing dlib / the `face_recognition` package,
which are slow to build on Pi hardware. YuNet replaced an earlier Haar
cascade here because it handles angled/partially-occluded faces and
varied lighting far more reliably.
"""
import os
import shutil

import cv2
import numpy as np

from . import config


class FaceEngine:
    def __init__(self):
        if not os.path.isfile(config.YUNET_MODEL_PATH):
            raise RuntimeError(f"Could not find YuNet model at {config.YUNET_MODEL_PATH}")
        self.detector = cv2.FaceDetectorYN_create(
            config.YUNET_MODEL_PATH,
            "",
            (config.FRAME_WIDTH, config.FRAME_HEIGHT),
            score_threshold=config.DETECTION_SCORE_THRESHOLD,
        )
        self._detector_size = (config.FRAME_WIDTH, config.FRAME_HEIGHT)
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.model_loaded = False
        self.load_model()

    # ------------------------------------------------------------------ model
    def load_model(self):
        if os.path.isfile(config.TRAINER_FILE):
            self.recognizer.read(config.TRAINER_FILE)
            self.model_loaded = True
        else:
            self.model_loaded = False
        return self.model_loaded

    def train(self):
        """(Re)train the recognizer from every image under DATASET_DIR.

        Each student's photos live in DATASET_DIR/<student_pk>/*.jpg, so the
        folder name doubles as the integer label LBPH requires.
        """
        faces, labels = [], []
        if os.path.isdir(config.DATASET_DIR):
            for folder in os.listdir(config.DATASET_DIR):
                folder_path = os.path.join(config.DATASET_DIR, folder)
                if not os.path.isdir(folder_path):
                    continue
                try:
                    label = int(folder)
                except ValueError:
                    continue
                for fname in os.listdir(folder_path):
                    if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    img_path = os.path.join(folder_path, fname)
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        continue
                    faces.append(img)
                    labels.append(label)

        if not faces:
            # No data left (e.g. last student deleted) - drop any stale model.
            if os.path.isfile(config.TRAINER_FILE):
                os.remove(config.TRAINER_FILE)
            self.model_loaded = False
            return 0

        self.recognizer.train(faces, np.array(labels))
        self.recognizer.save(config.TRAINER_FILE)
        self.model_loaded = True
        return len(faces)

    # --------------------------------------------------------------- dataset
    def student_dataset_dir(self, pk):
        path = os.path.join(config.DATASET_DIR, str(pk))
        os.makedirs(path, exist_ok=True)
        return path

    def save_face_sample(self, pk, index, gray_face):
        face = cv2.resize(gray_face, config.FACE_IMG_SIZE)
        path = os.path.join(self.student_dataset_dir(pk), f"img_{index:03d}.jpg")
        cv2.imwrite(path, face)

    def delete_student_data(self, pk):
        path = os.path.join(config.DATASET_DIR, str(pk))
        if os.path.isdir(path):
            shutil.rmtree(path)

    # --------------------------------------------------------------- runtime
    def detect_faces(self, bgr_frame):
        """Detect faces in a BGR frame. Returns a list of (x, y, w, h) ints,
        clipped to the frame bounds."""
        h, w = bgr_frame.shape[:2]
        if (w, h) != self._detector_size:
            self.detector.setInputSize((w, h))
            self._detector_size = (w, h)

        _, raw_faces = self.detector.detect(bgr_frame)
        if raw_faces is None:
            return []

        boxes = []
        for f in raw_faces:
            x, y, bw, bh = f[:4]
            x = max(0, int(round(x)))
            y = max(0, int(round(y)))
            x2 = min(w, x + int(round(bw)))
            y2 = min(h, y + int(round(bh)))
            if x2 > x and y2 > y:
                boxes.append((x, y, x2 - x, y2 - y))
        return boxes

    def largest_face(self, faces):
        if not faces:
            return None
        return max(faces, key=lambda f: f[2] * f[3])

    def predict(self, gray_face):
        """Returns (label, confidence). Confidence is a distance: lower is
        a better match. Caller compares against RECOGNITION_CONFIDENCE_THRESHOLD."""
        if not self.model_loaded:
            return None, None
        face = cv2.resize(gray_face, config.FACE_IMG_SIZE)
        return self.recognizer.predict(face)
