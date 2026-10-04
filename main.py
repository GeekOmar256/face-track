"""Face Track - entry point.

Run with:  python3 main.py
Then open http://<this-machine's-ip>:5000 in a browser on the same network
(or http://localhost:5000 if you're on the Pi itself).
"""
import os

from app import config
from app.database import Database
from app.face_engine import FaceEngine
from app.web import create_app


def main():
    db = Database(config.DB_PATH)
    face_engine = FaceEngine()
    app = create_app(db, face_engine)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
