"""Face Track - entry point.

Run with:  python main.py
"""
from app import config
from app.database import Database
from app.face_engine import FaceEngine
from app.gui.main_window import App


def main():
    db = Database(config.DB_PATH)
    face_engine = FaceEngine()
    app = App(db, face_engine)
    app.mainloop()


if __name__ == "__main__":
    main()
