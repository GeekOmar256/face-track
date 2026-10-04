"""Face detection, dataset capture and LBPH recognition.

Uses OpenCV's Haar cascade for detection and the LBPH recognizer for
recognition. Both run comfortably on a Raspberry Pi without needing dlib /
the `face_recognition` package, which are slow to build on Pi hardware.
"""
import os
import shutil

import cv2
import numpy as np

from . import config


class FaceEngine:
    def __init__(self):
        self.detector = cv2.CascadeClassifier(config.CASCADE_PATH)
        if self.detector.empty():
            raise RuntimeError(f"Could not load Haar cascade from {config.CASCADE_PATH}")
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
    def detect_faces(self, gray_frame):
        return self.detector.detectMultiScale(
            gray_frame, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80)
        )

    def largest_face(self, faces):
        if len(faces) == 0:
            return None
        return max(faces, key=lambda f: f[2] * f[3])

    def predict(self, gray_face):
        """Returns (label, confidence). Confidence is a distance: lower is
        a better match. Caller compares against RECOGNITION_CONFIDENCE_THRESHOLD."""
        if not self.model_loaded:
            return None, None
        face = cv2.resize(gray_face, config.FACE_IMG_SIZE)
        return self.recognizer.predict(face)
