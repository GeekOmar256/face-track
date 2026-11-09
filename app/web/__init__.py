"""Flask app factory for the BioAttendance web interface."""
import os
import threading

from flask import Flask

from .worker import CameraWorker
from .rfid_worker import RFIDWorker
from .fingerprint_worker import FingerprintWorker
from .ultrasonic_worker import UltrasonicWorker
from .firebase_command_worker import FirebaseCommandWorker
from .lcd_worker import LCDNotifier
from ..firebase_sync import FirebaseSync


def create_app(db, face_engine):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    # This app is intended for use on a trusted local network (classroom /
    # single admin). If you expose it beyond that, set FLASK_SECRET_KEY.
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "bioattendance-local-dev-key")

    firebase = FirebaseSync()
    camera_worker = CameraWorker(db, face_engine)
    ultrasonic_worker = UltrasonicWorker()
    rfid_worker = RFIDWorker()
    fingerprint_worker = FingerprintWorker()
    camera_worker.ultrasonic_worker = ultrasonic_worker
    camera_worker.firebase = firebase
    lcd = LCDNotifier()
    camera_worker.lcd = lcd

    # Lets the Firebase admin web app remotely start/stop sessions,
    # pre-register students, and edit/remove students. A no-op unless
    # real Firebase credentials are configured (see firebase_sync.py).
    command_worker = FirebaseCommandWorker(
        firebase, db, face_engine, camera_worker, rfid_worker,
        fingerprint_worker, ultrasonic_worker,
    )
    command_worker.start()

    # Upload whatever is already in the local database, in the background
    # so a slow network never delays startup.
    threading.Thread(target=firebase.sync_all, args=(db,), daemon=True).start()

    app.config["DB"] = db
    app.config["FACE_ENGINE"] = face_engine
    app.config["WORKER"] = camera_worker
    app.config["RFID_WORKER"] = rfid_worker
    app.config["FINGERPRINT_WORKER"] = fingerprint_worker
    app.config["ULTRASONIC_WORKER"] = ultrasonic_worker
    app.config["FIREBASE"] = firebase
    app.config["FIREBASE_COMMANDS"] = command_worker
    app.config["LCD"] = lcd

    from .routes import bp
    app.register_blueprint(bp)

    return app
