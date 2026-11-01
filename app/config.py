"""Central configuration and filesystem paths for BioAttendance."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATASET_DIR = os.path.join(DATA_DIR, "dataset")
TRAINER_DIR = os.path.join(DATA_DIR, "trainer")
ENCODINGS_FILE = os.path.join(TRAINER_DIR, "encodings.pickle")
DB_PATH = os.path.join(DATA_DIR, "attendance.db")

MODELS_DIR = os.path.join(BASE_DIR, "app", "models")
YUNET_MODEL_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")

# Camera: 0 is usually the first USB webcam / the Pi camera exposed via V4L2.
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Enrollment
FACE_IMG_SIZE = (200, 200)

# Detection. YuNet score is a confidence in [0, 1]: higher = more certain it's a face.
DETECTION_SCORE_THRESHOLD = 0.7

# Recognition (dlib ResNet face encodings via face_recognition). Distance
# is Euclidean over 128-d embeddings: lower = better match. ~0.6 is the
# face_recognition project's usual default; lower it (e.g. 0.45-0.5) for a
# stricter match, raise it (e.g. 0.65-0.7) if enrolled students aren't
# being recognized.
RECOGNITION_CONFIDENCE_THRESHOLD = 0.6

# Ultrasonic proximity gate (HC-SR04). Face recognition during a session
# only runs while someone is within this distance; RFID/fingerprint are
# unaffected since a deliberate tap/scan doesn't need proximity gating.
PROXIMITY_THRESHOLD_CM = 100

for _dir in (DATA_DIR, DATASET_DIR, TRAINER_DIR):
    os.makedirs(_dir, exist_ok=True)
