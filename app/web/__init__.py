"""Flask app factory for the BioAttendance web interface."""
import os

from flask import Flask

from .worker import CameraWorker
from .rfid_worker import RFIDWorker
from .fingerprint_worker import FingerprintWorker
from .ultrasonic_worker import UltrasonicWorker
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
    camera_worker.ultrasonic_worker = ultrasonic_worker
    camera_worker.firebase = firebase

    app.config["DB"] = db
    app.config["FACE_ENGINE"] = face_engine
    app.config["WORKER"] = camera_worker
    app.config["RFID_WORKER"] = RFIDWorker()
    app.config["FINGERPRINT_WORKER"] = FingerprintWorker()
    app.config["ULTRASONIC_WORKER"] = ultrasonic_worker
    app.config["FIREBASE"] = firebase

    from .routes import bp
    app.register_blueprint(bp)

    return app
