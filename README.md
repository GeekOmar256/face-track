# Face Track - Face Recognition Attendance System

A Flask web app for Raspberry Pi (also runs on Windows/macOS/Linux for
development) that takes attendance by recognizing students' faces. The
camera is attached to the Pi; the admin UI runs in a regular web browser -
on the Pi's own screen, or remotely from any device on the same network.

- **Add Student** - enter ID + name, then click **Capture Photo** to take
  one photo at a time from the live preview (click it again for more
  angles), and optionally **Scan Card** to link an RC522 RFID card to the
  student. **Finish Enrollment** saves and trains the model once at least
  one photo or a card is set.
- **Start Session** - opens the camera and continuously recognizes faces,
  *and* listens for RFID cards at the same time; a student can check in
  with either. Each student is marked present **once** per session
  (duplicate recognitions/taps in the same session are ignored).
- **Student List** - view/delete enrolled students (deleting retrains the
  model automatically).
- **Attendance History** - browse past sessions, see who attended and when,
  export a session to CSV.

Data is stored in SQLite (`data/attendance.db`) - students, sessions, and
attendance rows (each tagged with how the student checked in: `face` or
`rfid`). Face photos live in `data/dataset/<student_pk>/`, and the trained
model in `data/trainer/trainer.yml`. Existing databases are migrated
automatically on startup when upgrading from a version before RFID support.

## How recognition works

Detection uses OpenCV's **YuNet** (`cv2.FaceDetectorYN`), a small ONNX DNN
from OpenCV Zoo bundled in `app/models/face_detection_yunet_2023mar.onnx`;
recognition uses OpenCV's **LBPH** (`cv2.face.LBPHFaceRecognizer`). This
combo was chosen over `dlib` / `face_recognition` because dlib is slow and
often painful to build from source on a Raspberry Pi. YuNet handles angled
faces, partial occlusion and uneven lighting far more reliably than a Haar
cascade, while still running comfortably on a Pi CPU with no GPU required.

The camera itself is owned by the server (the Pi), not the browser: only
the admin UI is remote, the live video is captured and processed on the Pi
and streamed to the browser as an MJPEG feed.

## RFID card reader (RC522)

An RC522 module can be wired to the Pi's SPI header so students can also
(or instead) check in by tapping a card. It's read via the `mfrc522`
Python package.

### Wiring (RC522 -> Raspberry Pi 40-pin header)

| RC522 pin | Pi pin           |
|-----------|------------------|
| SDA (SS)  | GPIO8 / CE0 (pin 24) |
| SCK       | GPIO11 / SCLK (pin 23) |
| MOSI      | GPIO10 / MOSI (pin 19) |
| MISO      | GPIO9 / MISO (pin 21) |
| IRQ       | not connected |
| GND       | GND (pin 6)      |
| RST       | GPIO25 (pin 22)  |
| 3.3V      | 3.3V (pin 1) - **not** 5V, the RC522 is 3.3V-only |

### Setup

1. Enable SPI:
   ```bash
   sudo raspi-config  # Interface Options -> SPI -> Enable
   sudo reboot
   ```
2. Install the Python packages (already in `requirements.txt`, auto-skipped
   on non-Pi machines via environment markers):
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app as usual. On startup it checks the reader; the `/rfid/hardware`
   status is visible in the Add Student and Session pages.

### No reader attached yet?

The app doesn't require the RC522 to run - `app/rfid.py` falls back to a
reader that never sees a card, and both the Add Student and Session pages
then show a **"Simulate Scan"** text box so you can type a fake UID and
test the whole enrollment/attendance flow without the hardware.

## Setup - development machine (Windows/macOS/Linux)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
python main.py
```

Then open http://localhost:5000 in a browser.

## Setup - Raspberry Pi (Raspberry Pi OS, Bookworm/Bullseye)

1. System packages (OpenCV's Python wheel on ARM can be slow to build from
   pip; installing the apt version is usually faster and more reliable):

   ```bash
   sudo apt update
   sudo apt install -y python3-opencv python3-pip
   ```

   Check that your OpenCV build includes the contrib `face` module and the
   YuNet DNN detector:

   ```bash
   python3 -c "import cv2; print(hasattr(cv2,'face'), hasattr(cv2,'FaceDetectorYN_create'))"
   ```

   If either prints `False`, install the contrib wheel via pip instead
   inside a venv:

   ```bash
   python3 -m venv venv --system-site-packages
   source venv/bin/activate
   pip install -r requirements.txt
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

   This starts a web server on port 5000. Open `http://<pi-ip-address>:5000`
   from any browser on the same network, or `http://localhost:5000` if
   you're using a browser on the Pi itself. Find the Pi's address with
   `hostname -I`.

   Unlike a desktop GUI app, this does **not** need an X session or
   `$DISPLAY` to run - it's fine over a plain SSH connection with no X
   forwarding, since nothing is drawn locally on the Pi.

### Optional: kiosk mode on the Pi's own screen

If the Pi has a monitor attached and you want it to boot straight into the
attendance UI full-screen:

```bash
chromium-browser --noerrdialogs --kiosk http://localhost:5000
```

### Optional: run on boot with systemd

Create `/etc/systemd/system/facetrack.service`:

```ini
[Unit]
Description=Face Track Attendance System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/face-track/main.py
WorkingDirectory=/home/pi/face-track
User=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable facetrack.service
sudo systemctl start facetrack.service
```

## Tuning

Edit `app/config.py`:

- `DETECTION_SCORE_THRESHOLD` - YuNet confidence threshold; **higher value =
  stricter match** (default 0.7). Lower it if faces aren't being detected;
  raise it if it's picking up false positives.
- `RECOGNITION_CONFIDENCE_THRESHOLD` - LBPH distance threshold; **lower
  value = stricter match**. If the system misidentifies people, lower this
  (e.g. 55-60). If it fails to recognize enrolled students, raise it
  (e.g. 80-90).
- `CAMERA_INDEX`, `FRAME_WIDTH`, `FRAME_HEIGHT` - camera settings.

There's no fixed photo count per student - capture as many as you like
during enrollment (at least one is required). More photos from different
angles generally improve recognition accuracy.

## Project layout

```
main.py                     entry point - starts the Flask server
app/
  config.py                 paths & tunables
  database.py                SQLite access (students, sessions, attendance)
  camera.py                  cv2.VideoCapture wrapper
  face_engine.py              YuNet detection + LBPH train/recognize
  rfid.py                     RC522 reader wrapper (mfrc522), mock when no hardware
  models/
    face_detection_yunet_2023mar.onnx  bundled YuNet detector weights
  web/
    __init__.py                Flask app factory
    worker.py                  background camera worker (enroll / session state machine, MJPEG frames)
    rfid_worker.py              background RFID polling (enroll scan / session scan)
    routes.py                  HTTP routes
    templates/                  Jinja2 pages (dashboard, add student, session, students, history)
    static/style.css
data/                        created at runtime (db, dataset, trained model)
```
