# Face Track - Face Recognition Attendance System

A Tkinter desktop app for Raspberry Pi (also runs on Windows/macOS/Linux for
development) that takes attendance by recognizing students' faces.

- **Add Student** - enter ID + name, capture ~40 face photos from the camera,
  automatically trains the recognition model.
- **Start Session** - opens the camera and continuously recognizes faces;
  each recognized student is marked present **once** per session (duplicate
  recognitions in the same session are ignored).
- **Student List** - view/delete enrolled students (deleting retrains the
  model automatically).
- **Attendance History** - browse past sessions, see who attended and when,
  export a session to CSV.

Data is stored in SQLite (`data/attendance.db`). Face photos live in
`data/dataset/<student_pk>/`, and the trained model in
`data/trainer/trainer.yml`.

## How recognition works

Detection uses OpenCV's **YuNet** (`cv2.FaceDetectorYN`), a small ONNX DNN
from OpenCV Zoo bundled in `app/models/face_detection_yunet_2023mar.onnx`;
recognition uses OpenCV's **LBPH** (`cv2.face.LBPHFaceRecognizer`). This
combo was chosen over `dlib` / `face_recognition` because dlib is slow and
often painful to build from source on a Raspberry Pi. YuNet in particular
replaced an earlier Haar-cascade detector because it handles angled faces,
partial occlusion and uneven lighting far more reliably, while still
running comfortably on a Pi CPU with no GPU required.

## Setup - development machine (Windows/macOS/Linux)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
python main.py
```

## Setup - Raspberry Pi (Raspberry Pi OS, Bookworm/Bullseye)

1. System packages (OpenCV's Python wheel on ARM can be slow to build from
   pip; installing the apt version is usually faster and more reliable):

   ```bash
   sudo apt update
   sudo apt install -y python3-opencv python3-pil python3-pil.imagetk python3-tk python3-pip
   ```

   If `python3-opencv` on your Pi OS version doesn't include the `cv2.face`
   module, install the contrib wheel via pip instead inside a venv:

   ```bash
   python3 -m venv venv --system-site-packages
   source venv/bin/activate
   pip install opencv-contrib-python Pillow numpy
   ```

2. Camera:
   - **USB webcam**: works out of the box with `cv2.VideoCapture(0)`.
   - **Raspberry Pi Camera Module (V2/HQ)**: on recent Raspberry Pi OS
     (libcamera stack), enable the V4L2 compatibility layer so OpenCV can
     see it as `/dev/video0`:
     ```bash
     sudo modprobe bcm2835-v4l2
     # make it permanent:
     echo "bcm2835-v4l2" | sudo tee -a /etc/modules
     ```
     Then `CAMERA_INDEX = 0` in `app/config.py` should work. If you have
     both a USB cam and the Pi camera, check `ls /dev/video*` and adjust
     `CAMERA_INDEX` accordingly.

3. Run:

   ```bash
   python3 main.py
   ```

   For a touchscreen/kiosk setup, you can autostart this with a `.desktop`
   entry or a systemd user service pointed at `python3 main.py`.

## Tuning

Edit `app/config.py`:

- `SAMPLES_PER_STUDENT` - number of photos captured per student (default 40).
- `DETECTION_SCORE_THRESHOLD` - YuNet confidence threshold; **higher value =
  stricter match** (default 0.7). Lower it if faces aren't being detected;
  raise it if it's picking up false positives.
- `RECOGNITION_CONFIDENCE_THRESHOLD` - LBPH distance threshold; **lower
  value = stricter match**. If the system misidentifies people, lower this
  (e.g. 55-60). If it fails to recognize enrolled students, raise it
  (e.g. 80-90).
- `CAMERA_INDEX`, `FRAME_WIDTH`, `FRAME_HEIGHT` - camera settings.

## Project layout

```
main.py                     entry point
app/
  config.py                 paths & tunables
  database.py                SQLite access (students, sessions, attendance)
  camera.py                  cv2.VideoCapture wrapper
  face_engine.py              YuNet detection + LBPH train/recognize
  models/
    face_detection_yunet_2023mar.onnx  bundled YuNet detector weights
  gui/
    main_window.py            sidebar nav + frame switching
    dashboard_view.py
    add_student_view.py       enrollment + capture + auto-train
    session_view.py            live recognition + mark-once-per-session
    student_list_view.py
    history_view.py            session history + CSV export
data/                        created at runtime (db, dataset, trained model)
```
