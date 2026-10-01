"""
GameOptimizerPro v2.0 — Auto-Tune history: every tune run (logs/tune_*.log) with
its result, and the log of the selected run. A view of the GPU tuner page (it was
a part of the removed "Games & history" page).
"""

import tkinter as tk

import customtkinter as ctk

from core.tune_history import TuneHistory
from ui.components import LogView, Table, WrapLabel, button
from ui.theme import APP_BG, BORDER, CARD_BG, ERR, F_S, GREEN, MUTED, TEXT2, icon_image, tr


class TuneHistoryView(tk.Frame):
    def __init__(self, parent, logs_dir: str, **kw):
        super().__init__(parent, bg=APP_BG, **kw)
        self.history = TuneHistory(logs_dir)
        self._runs: dict = {}
        self._loaded = False
        self._build()

    def _build(self):
        card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        head = tk.Frame(inner, bg=CARD_BG)
        head.pack(fill="x", pady=(0, 10))
        button(head, tr("Aktualisieren", "Refresh"), self.refresh, kind="ghost", height=28,
               image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right")
        WrapLabel(head, text=tr("Alle Auto-Tune-Läufe — Zeile auswählen, um das Protokoll zu sehen.",
                                "All Auto-Tune runs — select a row to see its log."),
                  font=F_S, fg=TEXT2, bg=CARD_BG).pack(side="left", fill="x", expand=True)

        tbl = Table(inner, [
            ("date",   tr("Datum", "Date"),        150, "w"),
            ("mode",   tr("Modus", "Mode"),         90, "center"),
            ("core",   "Core +MHz",                 85, "center"),
            ("mem",    "Mem +MHz",                  85, "center"),
            ("power",  "Power %",                   75, "center"),
            ("volt",   "Avg Volt",                  85, "center"),
            ("temp",   "Max Temp",                  80, "center"),
            ("result", tr("Ergebnis", "Result"),    80, "center"),
        ], height=9, selectmode="browse")
        tbl.pack(fill="x")
        self.tree = tbl.tree
        self.tree.tag_configure("pass", foreground=GREEN)
        self.tree.tag_configure("fail", foreground=ERR)
        self.tree.tag_configure("none", foreground=MUTED)

        tk.Label(inner, text=tr("PROTOKOLL", "LOG"), font=("Segoe UI Semibold", 8), fg=MUTED,
                 bg=CARD_BG).pack(anchor="w", pady=(12, 4))
        self.log = LogView(inner, height=8)
        self.log.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def ensure_loaded(self):
        """Read the logs the first time the view is opened (not at app start)."""
        if not self._loaded:
            self.refresh()

    def refresh(self):
        self._loaded = True
        for row in self.tree.get_children():
            self.tree.delete(row)
        try:
            runs = self.history.get_runs()
        except Exception:
            runs = []
        self._runs = {r.filename: r for r in runs}
        if not runs:
            self.tree.insert("", "end", values=(tr("Noch kein Auto-Tune gelaufen", "No Auto-Tune run yet"),
                                                "", "", "", "", "", "", ""), tags=("none",))
            return
        for run in runs:
            self.tree.insert("", "end", iid=run.filename, values=(
                run.date,
                run.mode,
                f"+{run.core_offset}" if run.core_offset else "--",
                f"+{run.mem_offset}" if run.mem_offset else "--",
                f"{run.power_pct}%" if run.power_pct < 100 else "--",
                f"{run.avg_volt_mv}mV" if run.avg_volt_mv else "--",
                f"{run.max_temp:.0f}°C" if run.max_temp else "--",
                "✓ OK" if run.passed else "✗",
            ), tags=("pass" if run.passed else "fail",))

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        run = self._runs.get(sel[0]) if sel else None
        if run is None:
            return
        self.log.clear()
        for line in run.log_lines[-60:]:
            lvl = ("success" if "✓" in line or " OK" in line else
                   "error" if "✗" in line or "FAIL" in line or "[ERROR]" in line else
                   "warning" if "[WARNING]" in line else "info")
            self.log.append(line, lvl)
