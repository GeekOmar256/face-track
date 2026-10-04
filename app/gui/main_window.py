"""Main application window: sidebar navigation + swappable content frames."""
import tkinter as tk
from tkinter import ttk

from .dashboard_view import DashboardView
from .add_student_view import AddStudentView
from .session_view import SessionView
from .student_list_view import StudentListView
from .history_view import HistoryView


class App(tk.Tk):
    def __init__(self, db, face_engine):
        super().__init__()
        self.db = db
        self.face_engine = face_engine

        self.title("Face Track - Attendance System")
        self.geometry("1000x650")
        self.minsize(900, 600)

        self._build_layout()

        self.frames = {}
        for ViewClass in (DashboardView, AddStudentView, SessionView, StudentListView, HistoryView):
            frame = ViewClass(self.content, self)
            self.frames[ViewClass.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.current_frame_name = None
        self.show_frame("DashboardView")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        sidebar = tk.Frame(self, bg="#1f2937", width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="Face Track", bg="#1f2937", fg="white",
            font=("Segoe UI", 16, "bold"), pady=20,
        ).pack(fill="x")

        nav_items = [
            ("Dashboard", "DashboardView"),
            ("Add Student", "AddStudentView"),
            ("Start Session", "SessionView"),
            ("Student List", "StudentListView"),
            ("Attendance History", "HistoryView"),
        ]
        for label, frame_name in nav_items:
            btn = tk.Button(
                sidebar, text=label, anchor="w", padx=20, pady=12,
                bg="#1f2937", fg="white", activebackground="#374151",
                activeforeground="white", relief="flat", font=("Segoe UI", 11),
                command=lambda n=frame_name: self.show_frame(n),
            )
            btn.pack(fill="x")

        self.content = tk.Frame(self, bg="white")
        self.content.pack(side="right", fill="both", expand=True)

    def show_frame(self, name):
        # Give the outgoing frame a chance to release the camera etc.
        if self.current_frame_name is not None:
            old = self.frames[self.current_frame_name]
            if hasattr(old, "on_hide"):
                old.on_hide()

        frame = self.frames[name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()
        self.current_frame_name = name

    def _on_close(self):
        for frame in self.frames.values():
            if hasattr(frame, "on_hide"):
                try:
                    frame.on_hide()
                except Exception:
                    pass
        self.db.close()
        self.destroy()
