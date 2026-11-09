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

# A match must also beat the closest *other* student by at least this much,
# otherwise the face is treated as undecided. Stops look-alikes (or one
# person enrolled under two names) being recorded as whichever student
# happens to be a hair closer on a given frame.
RECOGNITION_MARGIN = 0.06

# A face must be matched to the same student on this many consecutive
# frames before they're recorded. A single misrecognised frame can then no
# longer mark the wrong student present or flash their name on the LCD.
# Each extra frame adds a little delay on a slow Pi.
FACE_CONFIRM_FRAMES = 3

# Ultrasonic proximity gate (HC-SR04). Face recognition during a session
# only runs while someone is within this distance; RFID/fingerprint are
# unaffected since a deliberate tap/scan doesn't need proximity gating.
PROXIMITY_THRESHOLD_CM = 100

# LCD: how long a face must stay unrecognised (seconds) before the LCD shows
# "Unknown face". Recognition misses enrolled students on some frames, so a
# shorter value flashes the message at people about to be recognised.
UNKNOWN_FACE_SECONDS = 2.0

# LCD: after a student's face has been reported (recorded / already
# recorded), stay quiet about that face for this many seconds. Without it,
# every recorded student in view re-triggers "Already recorded" on every
# frame and the LCD keeps cycling through their names. Card and fingerprint
# scans are deliberate and always show a result.
FACE_REPEAT_SECONDS = 30.0

for _dir in (DATA_DIR, DATASET_DIR, TRAINER_DIR):
    os.makedirs(_dir, exist_ok=True)
