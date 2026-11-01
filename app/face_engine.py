"""Face detection, dataset capture and dlib-based recognition.

Detection uses OpenCV's YuNet (a small ONNX DNN, via cv2.FaceDetectorYN) -
it's fast and runs fine on a Pi CPU. Recognition uses dlib's ResNet
face-embedding model via the `face_recognition` package: each enrolled
photo is reduced to a 128-d encoding, and a live face is identified by
nearest Euclidean distance to those encodings. This is more accurate than
the LBPH recognizer this replaced, at a real cost: dlib is slow (and can
be slow to install - see requirements.txt) compared to LBPH, so expect
noticeably heavier CPU use per frame on a Pi.
"""
import os
import pickle
import shutil

import cv2
import face_recognition
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
        self.known_encodings = []  # list of 128-d np arrays
        self.known_labels = []     # parallel list of student pk (int)
        self.model_loaded = False
        self.load_model()

    # ------------------------------------------------------------------ model
    def load_model(self):
        if os.path.isfile(config.ENCODINGS_FILE):
            with open(config.ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
            self.known_encodings = data.get("encodings", [])
            self.known_labels = data.get("labels", [])
            self.model_loaded = len(self.known_encodings) > 0
        else:
            self.known_encodings = []
            self.known_labels = []
            self.model_loaded = False
        return self.model_loaded

    def train(self):
        """(Re)compute face encodings for every image under DATASET_DIR.

        Each student's photos live in DATASET_DIR/<student_pk>/*.jpg, so the
        folder name doubles as the student's integer primary key.
        """
        encodings, labels = [], []
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
                    bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
                    if bgr is None:
                        continue
                    enc = self._encode(bgr)
                    if enc is not None:
                        encodings.append(enc)
                        labels.append(label)

        if not encodings:
            # No data left (e.g. last student deleted) - drop any stale model.
            if os.path.isfile(config.ENCODINGS_FILE):
                os.remove(config.ENCODINGS_FILE)
            self.known_encodings, self.known_labels = [], []
            self.model_loaded = False
            return 0

        with open(config.ENCODINGS_FILE, "wb") as f:
            pickle.dump({"encodings": encodings, "labels": labels}, f)
        self.known_encodings, self.known_labels = encodings, labels
        self.model_loaded = True
        return len(encodings)

    def _encode(self, bgr_face):
        """Returns a 128-d encoding for a BGR face image/crop, or None if
        dlib's landmark detector can't find a face in it."""
        rgb = cv2.cvtColor(bgr_face, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        encs = face_recognition.face_encodings(rgb, known_face_locations=[(0, w, h, 0)])
        return encs[0] if encs else None

    # --------------------------------------------------------------- dataset
    def student_dataset_dir(self, pk):
        path = os.path.join(config.DATASET_DIR, str(pk))
        os.makedirs(path, exist_ok=True)
        return path

    def save_face_sample(self, pk, index, bgr_face):
        face = cv2.resize(bgr_face, config.FACE_IMG_SIZE)
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

    def predict(self, bgr_face):
        """Returns (label, distance). Distance is Euclidean over 128-d
        encodings: lower is a better match. Caller compares against
        RECOGNITION_CONFIDENCE_THRESHOLD. (None, None) if no model is
        trained yet, or dlib can't encode this particular crop."""
        if not self.model_loaded:
            return None, None
        enc = self._encode(bgr_face)
        if enc is None:
            return None, None
        distances = face_recognition.face_distance(self.known_encodings, enc)
        best_idx = int(np.argmin(distances))
        return self.known_labels[best_idx], float(distances[best_idx])
