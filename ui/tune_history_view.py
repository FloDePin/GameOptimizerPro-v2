"""
GameOptimizerPro v2.0 — Auto-Tune history: every tune run (logs/tune_*.log) with
its values and result, the reason when a run has no profile, the log of the
selected run, and deleting runs (selected ones or all). A view of the GPU tuner
page (it was a part of the removed "Games & history" page).
"""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.tune_history import TuneHistory
from ui.components import LogView, Table, WrapLabel, button
from ui.theme import APP_BG, BORDER, CARD_BG, DIM, ERR, F_S, GREEN, MUTED, TEXT2, icon_image, tr


def _fmt(v, kind: str) -> str:
    if v is None:
        return "--"
    if kind == "mhz":
        return f"{v:+d}"
    if kind == "pct":
        return f"{v}%"
    if kind == "mv":
        return f"{v}mV"
    if kind == "temp":
        return f"{v:.0f}°C"
    return str(v)


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
        button(head, tr("Alle löschen", "Delete all"), self.delete_all, kind="ghost", height=28,
               image=icon_image("delete", ERR, 14), compound="left").pack(side="right")
        self.btn_delete = button(head, tr("Auswahl löschen", "Delete selected"), self.delete_selected,
                                 kind="ghost", height=28, image=icon_image("delete", ERR, 14), compound="left",
                                 state="disabled")
        self.btn_delete.pack(side="right", padx=(0, 6))
        button(head, tr("Aktualisieren", "Refresh"), self.refresh, kind="ghost", height=28,
               image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right", padx=(0, 6))
        WrapLabel(head, text=tr("Alle Auto-Tune-Läufe — Zeile auswählen, um das Protokoll zu sehen "
                                "(Strg-/Umschalt-Klick: mehrere). Bei Läufen ohne Profil stehen die zuletzt "
                                "getesteten Werte da, der Grund unter „Hinweis“.",
                                "All Auto-Tune runs — select a row to see its log (Ctrl / Shift click: "
                                "several). Runs without a profile show the values tested last, the reason "
                                "under 'Note'."),
                  font=F_S, fg=TEXT2, bg=CARD_BG).pack(side="left", fill="x", expand=True)

        tbl = Table(inner, [
            ("date",   tr("Datum", "Date"),         140, "w"),
            ("mode",   tr("Modus", "Mode"),          75, "center"),
            ("core",   "Core MHz",                   75, "center"),
            ("mem",    tr("Speicher MHz", "Mem MHz"), 90, "center"),
            ("power",  "Power",                      60, "center"),
            ("volt",   "Ø Volt",                     70, "center"),
            ("temp",   "Max Temp",                   70, "center"),
            ("result", tr("Ergebnis", "Result"),     70, "center"),
            ("note",   tr("Hinweis", "Note"),       260, "w"),
        ], height=9, selectmode="extended")
        tbl.pack(fill="x")
        self.tree = tbl.tree
        self.tree.tag_configure("pass", foreground=GREEN)
        self.tree.tag_configure("fail", foreground=ERR)
        self.tree.tag_configure("none", foreground=MUTED)

        tk.Label(inner, text=tr("PROTOKOLL", "LOG"), font=("Segoe UI Semibold", 8), fg=MUTED,
                 bg=CARD_BG).pack(anchor="w", pady=(12, 4))
        self.log = LogView(inner, height=8)
        self.log.pack(fill="both", expand=True)
        self.lbl_status = tk.Label(inner, text="", font=F_S, fg=DIM, bg=CARD_BG, anchor="w")
        self.lbl_status.pack(fill="x", pady=(6, 0))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

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
        self.btn_delete.configure(state="disabled")
        if not runs:
            self.tree.insert("", "end", values=(tr("Noch kein Auto-Tune gelaufen", "No Auto-Tune run yet"),
                                                "", "", "", "", "", "", "", ""), tags=("none",))
            return
        for run in runs:
            self.tree.insert("", "end", iid=run.filename, values=(
                run.date,
                run.mode,
                _fmt(run.core_offset, "mhz"),
                _fmt(run.mem_offset, "mhz"),
                _fmt(run.power_pct, "pct"),
                _fmt(run.avg_volt_mv, "mv"),
                _fmt(run.max_temp, "temp"),
                "✓ OK" if run.passed else "✗",
                run.reason,
            ), tags=("pass" if run.passed else "fail",))

    def _selected(self) -> list:
        return [i for i in self.tree.selection() if i in self._runs]

    def _on_select(self, _e=None):
        sel = self._selected()
        self.btn_delete.configure(state="normal" if sel else "disabled")
        run = self._runs.get(sel[-1]) if sel else None
        if run is None:
            return
        self.log.clear()
        if run.reason:
            self.log.append(tr("Kein Profil: ", "No profile: ") + run.reason, "error")
        for line in run.log_lines[-60:]:
            lvl = ("success" if "✓" in line or " OK" in line else
                   "error" if "✗" in line or "FAIL" in line or "[ERROR]" in line else
                   "warning" if "[WARNING]" in line else "info")
            self.log.append(line, lvl)

    # ── deleting ──────────────────────────────────────────────────────────────

    def delete_selected(self):
        sel = self._selected()
        if not sel:
            return
        dates = ", ".join(self._runs[s].date for s in sel[:3]) + (" …" if len(sel) > 3 else "")
        if not messagebox.askyesno(tr("Verlauf löschen", "Delete history"), tr(
                f"{len(sel)} Lauf/Läufe aus dem Verlauf löschen?\n{dates}\n\nDas Protokoll (und beim "
                f"Rundum-Tuner der Bericht) wird gelöscht. Gespeicherte GPU-Profile bleiben.",
                f"Delete {len(sel)} run(s) from the history?\n{dates}\n\nThe log (and, for the All-round "
                f"tuner, the report) is deleted. Saved GPU profiles stay."), parent=self):
            return
        self._done(self.history.delete(sel), len(sel))

    def delete_all(self):
        n = len(self._runs) if self._loaded else len(self.history.get_runs())
        if not n:
            return
        if not messagebox.askyesno(tr("Verlauf löschen", "Delete history"), tr(
                f"Den ganzen Verlauf löschen ({n} Läufe)?\n\nAlle Tune-Protokolle und Rundum-Berichte "
                f"werden gelöscht. Gespeicherte GPU-Profile bleiben.",
                f"Delete the whole history ({n} runs)?\n\nAll tune logs and All-round reports are "
                f"deleted. Saved GPU profiles stay."), parent=self):
            return
        self._done(self.history.delete_all(), n)

    def _done(self, deleted: int, wanted: int):
        self.log.clear()
        self.refresh()
        if deleted == wanted:
            self.lbl_status.config(text=tr(f"{deleted} Lauf/Läufe gelöscht.", f"{deleted} run(s) deleted."),
                                   fg=GREEN)
        else:
            self.lbl_status.config(text=tr(
                f"{deleted} von {wanted} gelöscht — ein laufender Tune schreibt gerade in sein Protokoll.",
                f"{deleted} of {wanted} deleted — a running tune is still writing its log."), fg=ERR)
