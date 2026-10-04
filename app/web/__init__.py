"""Flask app factory for the Face Track web interface."""
import os

from flask import Flask

from .worker import CameraWorker


def create_app(db, face_engine):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    # This app is intended for use on a trusted local network (classroom /
    # single admin). If you expose it beyond that, set FLASK_SECRET_KEY.
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "face-track-local-dev-key")

    app.config["DB"] = db
    app.config["FACE_ENGINE"] = face_engine
    app.config["WORKER"] = CameraWorker(db, face_engine)

    from .routes import bp
    app.register_blueprint(bp)

    return app
