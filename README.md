# BioAttendance - Multi-Biometric Attendance System

A Flask web app for Raspberry Pi (also runs on Windows/macOS/Linux for
development) that takes attendance via face recognition, an RFID card, or
a fingerprint - whichever a student has enrolled. The camera/reader/sensor
are attached to the Pi; the admin UI runs in a regular web browser - on
the Pi's own screen, or remotely from any device on the same network.

- **Add Student** - enter ID + name, then click **Capture Photo** to take
  one photo at a time from the live preview (click it again for more
  angles). Optionally also **Scan Card** to link an RC522 RFID card, and/or
  **Enroll Fingerprint** (place the same finger twice) to link an AS608/
  R307/FPM10A sensor reading. **Finish Enrollment** saves and trains once
  at least one of these three credentials is set.
- **Start Session** - opens the camera and continuously recognizes faces,
  *and* listens for RFID taps and fingerprint scans at the same time; a
  student can check in with any of the three. An optional HC-SR04
  ultrasonic sensor gates face recognition to only run once someone is
  within about a meter, saving CPU when nobody's there. Each student is
  marked present **once** per session, regardless of method (duplicate
  recognitions/taps/scans in the same session are ignored).
- **Student List** - view/delete enrolled students (deleting retrains the
  model automatically).
- **Attendance History** - browse past sessions, see who attended, when,
  and by which method; export a session to CSV.

Data is stored in SQLite (`data/attendance.db`) - students, sessions, and
attendance rows (each tagged with how the student checked in: `face`,
`rfid` or `fingerprint`). Face photos live in `data/dataset/<student_pk>/`,
and the trained model in `data/trainer/encodings.pickle`. Existing
databases are migrated automatically on startup when upgrading from an
older version. Optionally, the same data can be pushed one-way to Firebase
for a separate app to read - see "Firebase sync" below.

## How recognition works

Detection uses OpenCV's **YuNet** (`cv2.FaceDetectorYN`), a small ONNX DNN
from OpenCV Zoo bundled in `app/models/face_detection_yunet_2023mar.onnx` -
fast and accurate enough to run every frame on a Pi CPU, handling angled
faces, partial occlusion and uneven lighting far better than a Haar
cascade. Recognition uses **dlib**'s ResNet face-embedding model via the
`face_recognition` package: each enrolled photo becomes a 128-d encoding,
and a live face is identified by nearest Euclidean distance to those
encodings. This is more accurate than the LBPH recognizer it replaced, but
genuinely heavier - expect more CPU use per frame on a Pi, and note the
dlib install caveats in `requirements.txt` (piwheels usually has a
prebuilt wheel; `numpy` is pinned below 2.0 since dlib's wheel is built
against numpy's 1.x ABI and raises a cryptic
`"Unsupported image type"` error under numpy 2.x otherwise - confirmed
directly against this project's code, not a hypothetical).

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

## Ultrasonic proximity sensor (HC-SR04)

An optional HC-SR04 distance sensor gates face recognition during a
session: recognition only runs while someone is within range (1 meter by
default), saving CPU when nobody's in front of the camera. RFID and
fingerprint check-ins are unaffected - a deliberate tap/scan doesn't need
proximity gating.

### Wiring

| HC-SR04 pin | Raspberry Pi pin |
|---|---|
| VCC | 5V - physical pin 2 |
| TRIG | GPIO23 - physical pin 16 |
| ECHO | **via a voltage divider** (see below) -> GPIO24 - physical pin 18 |
| GND | GND - physical pin 6 |

**ECHO is a 5V output from the sensor, but Pi GPIO inputs are only 3.3V
tolerant.** Connecting ECHO directly can damage the GPIO pin. Use a simple
voltage divider: a 1kΩ resistor in series between ECHO and GPIO24, and a
2kΩ resistor from GPIO24 to GND. That divides the 5V signal down to
~3.3V before it reaches the Pi.

### Setup

No extra OS configuration is needed (just GPIO, no SPI/I2C to enable).
`RPi.GPIO` is already in `requirements.txt` (shared with the RFID reader).
The pins above are the defaults; override with the `ULTRASONIC_TRIG_PIN`
/ `ULTRASONIC_ECHO_PIN` environment variables if wired differently, and
`PROXIMITY_THRESHOLD_CM` in `app/config.py` to change the 1-meter default.

Without the sensor attached, the proximity gate fails open (recognition
always runs, exactly like before this feature existed) - `app/ultrasonic.py`
degrades the same way `rfid.py` and `fingerprint.py` do.

## Fingerprint sensor (AS608 / R307 / FPM10A)

These optical sensors share the same UART protocol, read via the
`pyfingerprint` package. Enrollment is a two-step wizard on the Add
Student page - place the same finger twice - since that's what the sensor
itself requires to build a reliable template.

### Wiring

| Sensor pin | Raspberry Pi pin |
|---|---|
| VCC (red) | 3.3V - physical pin 1 |
| TX (sensor's transmit -> Pi's receive) | GPIO15 / RXD - physical pin 10 |
| RX (sensor's receive <- Pi's transmit) | GPIO14 / TXD - physical pin 8 |
| GND (black) | GND - physical pin 9 |

Most of these modules run on 3.3-6V and have 3.3V-logic UART, so direct
connection to the Pi's UART pins is normally fine - double-check your
specific module's datasheet/listing before wiring, since some variants
need 5V power with a separate 3.3V logic line.

### Setup

1. Free up the Pi's primary UART (by default it's used for the Linux
   console):
   ```bash
   sudo raspi-config  # Interface Options -> Serial Port
   #   "Would you like a login shell over serial?" -> No
   #   "Would you like the serial port hardware enabled?" -> Yes
   sudo reboot
   ```
2. The sensor should now be reachable at `/dev/serial0` (aliased to
   `/dev/ttyAMA0` or `/dev/ttyS0` depending on Pi model). If
   `app/fingerprint.py` can't find it automatically, point it there
   explicitly with the `FINGERPRINT_SERIAL_PORT` environment variable, and
   `FINGERPRINT_BAUD_RATE` if your module isn't the common 57600 default.
3. `pyfingerprint` is already in `requirements.txt` and installs
   everywhere (pure Python, no compiled extension), so no platform
   markers are needed for it.

Without the sensor attached, both the Add Student and Session pages show
a **"Simulate"** control (advance the enroll wizard a step; pick a student
to simulate a match for during a session) so the flow is testable without
hardware.

## Firebase sync (optional)

The Pi can optionally push students, sessions and attendance to Firebase
Firestore, one-way (Pi -> Firestore), so a separate teacher/student-facing
app can read live attendance data. This repository does not include that
app - only the Pi-side sync that a separate app's backend/frontend can
read from. It's entirely optional: without it configured, the app works
exactly as described above, purely on local SQLite.

### Setup

1. In the [Firebase Console](https://console.firebase.google.com/), open
   your project -> Project settings -> Service accounts -> **Generate new
   private key**. This downloads a JSON file - treat it like a password,
   it grants full admin access to your Firestore data.
2. Copy that file to the Pi as `data/firebase_credentials.json` (this path
   is already gitignored - never commit it), or point
   `FIREBASE_CREDENTIALS_PATH` at wherever you put it instead.
3. `firebase-admin` is already in `requirements.txt`. Nothing else to
   configure - on startup, `app/firebase_sync.py` checks for that file and
   silently stays disabled if it's missing, so there's no error if you
   haven't set it up yet.

### Firestore schema

A separate app reading this data should expect three collections:

- **`students`** (doc id = the student's internal numeric id): `student_id`,
  `name`, `date_added`, `photo_count`, `has_rfid` (bool), `has_fingerprint`
  (bool).
- **`sessions`** (doc id = session id): `name`, `start_time`, `end_time`
  (`null` while a session is in progress).
- **`attendance`** (doc id = `"<session_id>_<student_id>"`): `session_id`,
  `student_pk`, `student_id`, `name`, `timestamp`, `method` (`"face"`,
  `"rfid"` or `"fingerprint"`).

Every write is best-effort: a Firestore hiccup is logged nowhere and never
blocks or fails the local operation (enrollment, session, attendance mark
all still work against SQLite even if Firestore is unreachable).

### What this doesn't do

This only pushes data outward. It does not pull anything back from
Firebase - there's no remote "add a student from the mobile app" flow
built here, since that would need photo upload handling, moderation/
consent decisions and a defined contract with that app's own data model,
none of which exist yet. The natural extension point, if you build that
app, is a Cloud Function or scheduled job on the Pi that watches a
`pending_enrollments` collection and calls the same `Database`/`FaceEngine`
methods this app's routes already use.

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

Create `/etc/systemd/system/bioattendance.service`:

```ini
[Unit]
Description=BioAttendance System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/bioattendance/main.py
WorkingDirectory=/home/pi/bioattendance
User=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable bioattendance.service
sudo systemctl start bioattendance.service
```

## Tuning

Edit `app/config.py`:

- `DETECTION_SCORE_THRESHOLD` - YuNet confidence threshold; **higher value =
  stricter match** (default 0.7). Lower it if faces aren't being detected;
  raise it if it's picking up false positives.
- `RECOGNITION_CONFIDENCE_THRESHOLD` - dlib face-encoding distance; **lower
  value = stricter match** (default 0.6, the face_recognition project's
  usual default). If the system misidentifies people, lower this (e.g.
  0.45-0.5). If it fails to recognize enrolled students, raise it (e.g.
  0.65-0.7).
- `CAMERA_INDEX`, `FRAME_WIDTH`, `FRAME_HEIGHT` - camera settings.
- `PROXIMITY_THRESHOLD_CM` - how close (in cm) someone needs to be, per the
  HC-SR04, before face recognition runs during a session (default 100).

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
  face_engine.py              YuNet detection + dlib (face_recognition) recognition
  rfid.py                     RC522 reader wrapper (mfrc522), mock when no hardware
  fingerprint.py               AS608/R307/FPM10A wrapper (pyfingerprint), mock when no hardware
  ultrasonic.py                HC-SR04 wrapper (RPi.GPIO), mock when no hardware
  firebase_sync.py             optional one-way push to Firestore, no-op when unconfigured
  models/
    face_detection_yunet_2023mar.onnx  bundled YuNet detector weights
  web/
    __init__.py                Flask app factory
    worker.py                  background camera worker (enroll / session state machine, MJPEG frames)
    rfid_worker.py              background RFID polling (enroll scan / session scan)
    fingerprint_worker.py        background fingerprint polling (two-step enroll wizard / session scan)
    ultrasonic_worker.py         background distance polling (session-scoped)
    routes.py                  HTTP routes
    templates/                  Jinja2 pages (dashboard, add student, session, students, history)
    static/style.css
data/                        created at runtime (db, dataset, trained model);
                              also where firebase_credentials.json goes if used (gitignored)
```
