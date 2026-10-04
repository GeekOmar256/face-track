"""Add Student: register a student and capture face photos to train the model."""
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
from PIL import Image, ImageTk

from .. import config
from ..camera import Camera


class AddStudentView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self.camera = None
        self.capturing = False
        self.sample_count = 0
        self.target_samples = config.SAMPLES_PER_STUDENT
        self.last_capture_time = 0
        self.current_pk = None
        self.after_id = None

        self._build_ui()

    def _build_ui(self):
        tk.Label(self, text="Add Student", bg="white", font=("Segoe UI", 20, "bold")).pack(
            anchor="w", padx=30, pady=(25, 15)
        )

        form = tk.Frame(self, bg="white")
        form.pack(anchor="w", padx=30, fill="x")

        tk.Label(form, text="Student ID", bg="white", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=5)
        self.id_entry = tk.Entry(form, font=("Segoe UI", 11), width=30)
        self.id_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(form, text="Full Name", bg="white", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=5)
        self.name_entry = tk.Entry(form, font=("Segoe UI", 11), width=30)
        self.name_entry.grid(row=1, column=1, padx=10, pady=5)

        btn_frame = tk.Frame(self, bg="white")
        btn_frame.pack(anchor="w", padx=30, pady=15)

        self.start_btn = tk.Button(
            btn_frame, text="Start Capture", bg="#2563eb", fg="white",
            font=("Segoe UI", 11, "bold"), padx=15, pady=8, relief="flat",
            command=self.start_capture,
        )
        self.start_btn.pack(side="left")

        self.cancel_btn = tk.Button(
            btn_frame, text="Cancel", bg="#ef4444", fg="white",
            font=("Segoe UI", 11, "bold"), padx=15, pady=8, relief="flat",
            command=self.cancel_capture, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(self, length=400, maximum=self.target_samples)
        self.progress.pack(anchor="w", padx=30, pady=(0, 5))

        self.status_lbl = tk.Label(self, text="", bg="white", fg="#6b7280", font=("Segoe UI", 10))
        self.status_lbl.pack(anchor="w", padx=30)

        self.video_lbl = tk.Label(self, bg="black", width=480, height=360)
        self.video_lbl.pack(padx=30, pady=15)

    # ------------------------------------------------------------- lifecycle
    def on_hide(self):
        self._stop_camera_loop()

    # --------------------------------------------------------------- actions
    def start_capture(self):
        student_id = self.id_entry.get().strip()
        name = self.name_entry.get().strip()
        if not student_id or not name:
            messagebox.showwarning("Missing info", "Please enter both Student ID and Name.")
            return

        try:
            self.current_pk = self.controller.db.add_student(student_id, name)
        except ValueError as exc:
            messagebox.showerror("Could not add student", str(exc))
            return

        try:
            self.camera = Camera()
            self.camera.open()
        except RuntimeError as exc:
            messagebox.showerror("Camera error", str(exc))
            self.controller.db.delete_student(self.current_pk)
            self.current_pk = None
            return

        self.capturing = True
        self.sample_count = 0
        self.last_capture_time = 0
        self.progress["value"] = 0
        self.id_entry.config(state="disabled")
        self.name_entry.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.status_lbl.config(text="Look at the camera. Move your head slightly for varied angles...")
        self._tick()

    def cancel_capture(self):
        self._stop_camera_loop()
        if self.current_pk is not None:
            self.controller.face_engine.delete_student_data(self.current_pk)
            self.controller.db.delete_student(self.current_pk)
            self.current_pk = None
        self._reset_form()
        self.status_lbl.config(text="Capture cancelled.")

    # ---------------------------------------------------------------- camera
    def _tick(self):
        if not self.capturing:
            return
        frame = self.camera.read()
        if frame is None:
            self.after_id = self.after(30, self._tick)
            return

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.controller.face_engine.detect_faces(gray)
        face = self.controller.face_engine.largest_face(faces)

        if face is not None:
            x, y, w, h = face
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
            now = time.time() * 1000
            if now - self.last_capture_time >= config.CAPTURE_INTERVAL_MS:
                self.last_capture_time = now
                self.sample_count += 1
                self.controller.face_engine.save_face_sample(
                    self.current_pk, self.sample_count, gray[y:y + h, x:x + w]
                )
                self.progress["value"] = self.sample_count
                self.status_lbl.config(text=f"Captured {self.sample_count}/{self.target_samples} photos")

        self._show_frame(frame)

        if self.sample_count >= self.target_samples:
            self._finish_capture()
            return

        self.after_id = self.after(30, self._tick)

    def _finish_capture(self):
        self._stop_camera_loop(release_only=True)
        self.controller.db.update_photo_count(self.current_pk, self.sample_count)
        self.status_lbl.config(text="Training recognition model...")
        self.update_idletasks()

        pk_done = self.current_pk

        def train_job():
            self.controller.face_engine.train()
            self.after(0, lambda: self._training_done(pk_done))

        threading.Thread(target=train_job, daemon=True).start()

    def _training_done(self, pk):
        self.status_lbl.config(text=f"Student enrolled and model trained successfully (ID {pk}).")
        self._reset_form()

    def _show_frame(self, bgr_frame):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((480, 360))
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_lbl.imgtk = imgtk
        self.video_lbl.configure(image=imgtk)

    def _stop_camera_loop(self, release_only=False):
        self.capturing = False
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        if not release_only:
            self.video_lbl.configure(image="")

    def _reset_form(self):
        self._stop_camera_loop()
        self.id_entry.config(state="normal")
        self.name_entry.config(state="normal")
        self.id_entry.delete(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.progress["value"] = 0
        self.current_pk = None
        self.video_lbl.configure(image="")
