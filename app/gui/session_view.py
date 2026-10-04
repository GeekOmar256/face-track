"""Start Session: live recognition that marks attendance exactly once per student per session."""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

import cv2
from PIL import Image, ImageTk

from .. import config
from ..camera import Camera


class SessionView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self.camera = None
        self.running = False
        self.after_id = None
        self.session_id = None
        self.marked_pks = set()

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg="white")
        header.pack(fill="x", padx=30, pady=(25, 10))

        tk.Label(header, text="Attendance Session", bg="white", font=("Segoe UI", 20, "bold")).pack(side="left")

        self.session_lbl = tk.Label(header, text="No active session", bg="white", fg="#6b7280", font=("Segoe UI", 11))
        self.session_lbl.pack(side="left", padx=20)

        btn_frame = tk.Frame(self, bg="white")
        btn_frame.pack(anchor="w", padx=30)

        self.start_btn = tk.Button(
            btn_frame, text="Start Session", bg="#16a34a", fg="white",
            font=("Segoe UI", 11, "bold"), padx=15, pady=8, relief="flat",
            command=self.start_session,
        )
        self.start_btn.pack(side="left")

        self.end_btn = tk.Button(
            btn_frame, text="End Session", bg="#ef4444", fg="white",
            font=("Segoe UI", 11, "bold"), padx=15, pady=8, relief="flat",
            command=self.end_session, state="disabled",
        )
        self.end_btn.pack(side="left", padx=10)

        body = tk.Frame(self, bg="white")
        body.pack(fill="both", expand=True, padx=30, pady=15)

        self.video_lbl = tk.Label(body, bg="black", width=480, height=360)
        self.video_lbl.pack(side="left")

        log_frame = tk.Frame(body, bg="white")
        log_frame.pack(side="left", fill="both", expand=True, padx=(20, 0))

        tk.Label(log_frame, text="Present this session", bg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.log_list = tk.Listbox(log_frame, font=("Segoe UI", 10))
        self.log_list.pack(fill="both", expand=True, pady=5)

    # ------------------------------------------------------------- lifecycle
    def on_hide(self):
        if self.running:
            self.end_session()

    # --------------------------------------------------------------- actions
    def start_session(self):
        if not self.controller.face_engine.model_loaded:
            messagebox.showwarning(
                "No trained model",
                "No students have been enrolled yet. Add at least one student before starting a session.",
            )
            return

        try:
            self.camera = Camera()
            self.camera.open()
        except RuntimeError as exc:
            messagebox.showerror("Camera error", str(exc))
            return

        self.session_id = self.controller.db.create_session(
            name=datetime.now().strftime("Session %Y-%m-%d %H:%M")
        )
        self.marked_pks = set()
        self.log_list.delete(0, tk.END)
        self.session_lbl.config(text=f"Session #{self.session_id} - recording")
        self.start_btn.config(state="disabled")
        self.end_btn.config(state="normal")

        self.running = True
        self._tick()

    def end_session(self):
        self.running = False
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        if self.session_id is not None:
            self.controller.db.end_session(self.session_id)
            self.session_lbl.config(text=f"Session #{self.session_id} ended - {len(self.marked_pks)} present")
        self.session_id = None
        self.start_btn.config(state="normal")
        self.end_btn.config(state="disabled")
        self.video_lbl.configure(image="")

    # ---------------------------------------------------------------- camera
    def _tick(self):
        if not self.running:
            return
        frame = self.camera.read()
        if frame is None:
            self.after_id = self.after(30, self._tick)
            return

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.controller.face_engine.detect_faces(gray)

        for (x, y, w, h) in faces:
            label, confidence = self.controller.face_engine.predict(gray[y:y + h, x:x + w])
            box_color = (0, 0, 255)
            caption = "Unknown"

            if label is not None and confidence is not None and confidence <= config.RECOGNITION_CONFIDENCE_THRESHOLD:
                student = self.controller.db.get_student_by_pk(label)
                if student is not None:
                    if label in self.marked_pks:
                        box_color = (255, 165, 0)
                        caption = f"{student['name']} (marked)"
                    else:
                        newly_marked = self.controller.db.mark_attendance(self.session_id, label)
                        if newly_marked:
                            self.marked_pks.add(label)
                            box_color = (0, 200, 0)
                            caption = f"{student['name']} - present"
                            self._log_entry(student)

            cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 2)
            cv2.putText(
                frame, caption, (x, max(0, y - 10)), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, box_color, 2,
            )

        self._show_frame(frame)
        self.after_id = self.after(30, self._tick)

    def _log_entry(self, student):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_list.insert(tk.END, f"{ts}  {student['name']}  (ID {student['student_id']})")
        self.log_list.see(tk.END)

    def _show_frame(self, bgr_frame):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((480, 360))
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_lbl.imgtk = imgtk
        self.video_lbl.configure(image=imgtk)
