"""Central configuration and filesystem paths for Face Track."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATASET_DIR = os.path.join(DATA_DIR, "dataset")
TRAINER_DIR = os.path.join(DATA_DIR, "trainer")
TRAINER_FILE = os.path.join(TRAINER_DIR, "trainer.yml")
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

# Recognition. LBPH confidence is a DISTANCE: lower = better match.
RECOGNITION_CONFIDENCE_THRESHOLD = 70

for _dir in (DATA_DIR, DATASET_DIR, TRAINER_DIR):
    os.makedirs(_dir, exist_ok=True)
