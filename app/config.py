"""Central configuration and filesystem paths for Face Track."""
import os
import cv2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATASET_DIR = os.path.join(DATA_DIR, "dataset")
TRAINER_DIR = os.path.join(DATA_DIR, "trainer")
TRAINER_FILE = os.path.join(TRAINER_DIR, "trainer.yml")
DB_PATH = os.path.join(DATA_DIR, "attendance.db")

CASCADE_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")

# Camera: 0 is usually the first USB webcam / the Pi camera exposed via V4L2.
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Enrollment
SAMPLES_PER_STUDENT = 40
FACE_IMG_SIZE = (200, 200)
CAPTURE_INTERVAL_MS = 150  # minimum time between saved samples, for variety

# Recognition. LBPH confidence is a DISTANCE: lower = better match.
RECOGNITION_CONFIDENCE_THRESHOLD = 70

for _dir in (DATA_DIR, DATASET_DIR, TRAINER_DIR):
    os.makedirs(_dir, exist_ok=True)
