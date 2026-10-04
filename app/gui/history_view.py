"""Attendance History: browse past sessions and who was present in each."""
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class HistoryView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg="white")
        header.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(header, text="Attendance History", bg="white", font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Button(
            header, text="Refresh", command=self.refresh, relief="flat",
            bg="#e5e7eb", padx=10, pady=5,
        ).pack(side="left", padx=10)
        tk.Button(
            header, text="Export Selected to CSV", command=self.export_selected, relief="flat",
            bg="#2563eb", fg="white", padx=10, pady=5,
        ).pack(side="left")

        body = tk.Frame(self, bg="white")
        body.pack(fill="both", expand=True, padx=30, pady=10)

        left = tk.Frame(body, bg="white")
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Sessions", bg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        session_cols = ("name", "start_time", "end_time", "present_count")
        self.session_tree = ttk.Treeview(left, columns=session_cols, show="headings", height=16)
        for col, label, width in (
            ("name", "Session", 170),
            ("start_time", "Start", 150),
            ("end_time", "End", 150),
            ("present_count", "Present", 70),
        ):
            self.session_tree.heading(col, text=label)
            self.session_tree.column(col, width=width, anchor="w")
        self.session_tree.pack(fill="both", expand=True, pady=5)
        self.session_tree.bind("<<TreeviewSelect>>", self._on_session_select)

        right = tk.Frame(body, bg="white")
        right.pack(side="left", fill="both", expand=True, padx=(20, 0))
        tk.Label(right, text="Attendees", bg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        attendee_cols = ("student_id", "name", "timestamp")
        self.attendee_tree = ttk.Treeview(right, columns=attendee_cols, show="headings", height=16)
        for col, label, width in (
            ("student_id", "Student ID", 110),
            ("name", "Name", 200),
            ("timestamp", "Marked At", 160),
        ):
            self.attendee_tree.heading(col, text=label)
            self.attendee_tree.column(col, width=width, anchor="w")
        self.attendee_tree.pack(fill="both", expand=True, pady=5)

    def on_show(self):
        self.refresh()

    def refresh(self):
        for row in self.session_tree.get_children():
            self.session_tree.delete(row)
        for row in self.attendee_tree.get_children():
            self.attendee_tree.delete(row)
        for session in self.controller.db.get_all_sessions():
            self.session_tree.insert(
                "", "end", iid=str(session["id"]),
                values=(
                    session["name"] or f"Session #{session['id']}",
                    session["start_time"],
                    session["end_time"] or "(in progress)",
                    session["present_count"],
                ),
            )

    def _on_session_select(self, _event):
        selection = self.session_tree.selection()
        if not selection:
            return
        session_id = int(selection[0])
        for row in self.attendee_tree.get_children():
            self.attendee_tree.delete(row)
        for att in self.controller.db.get_attendance_for_session(session_id):
            self.attendee_tree.insert(
                "", "end",
                values=(att["student_id"], att["name"], att["timestamp"]),
            )

    def export_selected(self):
        selection = self.session_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a session first.")
            return
        session_id = int(selection[0])
        rows = self.controller.db.get_attendance_for_session(session_id)
        if not rows:
            messagebox.showinfo("Nothing to export", "This session has no attendance records.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"session_{session_id}_attendance.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Student ID", "Name", "Timestamp"])
            for att in rows:
                writer.writerow([att["student_id"], att["name"], att["timestamp"]])

        messagebox.showinfo("Export complete", f"Saved to {path}")
