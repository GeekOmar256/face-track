"""Simple landing page with headline stats."""
import tkinter as tk


class DashboardView(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller

        tk.Label(
            self, text="Face Track", bg="white", fg="#111827",
            font=("Segoe UI", 26, "bold"),
        ).pack(anchor="w", padx=30, pady=(30, 0))
        tk.Label(
            self, text="Face-recognition attendance system", bg="white",
            fg="#6b7280", font=("Segoe UI", 12),
        ).pack(anchor="w", padx=30, pady=(0, 20))

        self.stats_frame = tk.Frame(self, bg="white")
        self.stats_frame.pack(anchor="w", padx=30, fill="x")

        self.student_count_lbl = self._make_stat_card("Registered students", "0")
        self.session_count_lbl = self._make_stat_card("Sessions recorded", "0")

    def _make_stat_card(self, title, value):
        card = tk.Frame(self.stats_frame, bg="#f3f4f6", padx=20, pady=15)
        card.pack(side="left", padx=(0, 15))
        tk.Label(card, text=title, bg="#f3f4f6", fg="#6b7280", font=("Segoe UI", 10)).pack(anchor="w")
        value_lbl = tk.Label(card, text=value, bg="#f3f4f6", fg="#111827", font=("Segoe UI", 22, "bold"))
        value_lbl.pack(anchor="w")
        return value_lbl

    def on_show(self):
        self.student_count_lbl.config(text=str(self.controller.db.count_students()))
        self.session_count_lbl.config(text=str(len(self.controller.db.get_all_sessions())))
