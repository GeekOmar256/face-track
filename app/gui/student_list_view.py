"""Student List: view enrolled students and remove them if needed."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox


class StudentListView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg="white")
        header.pack(fill="x", padx=30, pady=(25, 10))

        tk.Label(header, text="Student List", bg="white", font=("Segoe UI", 20, "bold")).pack(side="left")

        tk.Button(
            header, text="Refresh", command=self.refresh, relief="flat",
            bg="#e5e7eb", padx=10, pady=5,
        ).pack(side="left", padx=10)

        tk.Button(
            header, text="Delete Selected", command=self.delete_selected, relief="flat",
            bg="#ef4444", fg="white", padx=10, pady=5,
        ).pack(side="left")

        columns = ("student_id", "name", "date_added", "photo_count")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=18)
        for col, label, width in (
            ("student_id", "Student ID", 140),
            ("name", "Name", 260),
            ("date_added", "Date Added", 180),
            ("photo_count", "Photos", 80),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=30, pady=10)

    def on_show(self):
        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for student in self.controller.db.get_all_students():
            self.tree.insert(
                "", "end", iid=str(student["id"]),
                values=(student["student_id"], student["name"], student["date_added"], student["photo_count"]),
            )

    def delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a student to delete first.")
            return
        pk = int(selection[0])
        student = self.controller.db.get_student_by_pk(pk)
        if student is None:
            return
        if not messagebox.askyesno(
            "Confirm delete",
            f"Delete {student['name']} (ID {student['student_id']})? "
            "This removes their photos and attendance history, and retrains the model.",
        ):
            return

        self.controller.db.delete_student(pk)
        self.controller.face_engine.delete_student_data(pk)
        self.refresh()

        def retrain_job():
            self.controller.face_engine.train()

        threading.Thread(target=retrain_job, daemon=True).start()
