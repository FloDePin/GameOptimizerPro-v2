"""
GameOptimizerPro v2.0 — Diagnose page
Measure, don't guess:
  • Health Report    — 30 days of what Windows already recorded (read-only)
  • Remnant Scan     — leftovers of other tweak tools (read-only)

Threading: worker threads write results straight into the thread-safe LogView
(queue-backed). All other widget updates go through a main-thread pump queue —
never after() from a worker (raises RuntimeError on Python 3.14).
"""

import queue
import threading
import tkinter as tk

import customtkinter as ctk

from core import health_report, remnant_detector
from ui.components import LogView, Page, WrapLabel, button
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, F_S, GREEN,
                      INPUT_BG, TEXT2, ctk_font, icon_image, mix, on_color, tr)

HEALTH_COLOR = GREEN
REMN_COLOR   = AMBER


class DiagnoseTab(Page):
    def __init__(self, parent, **kw):
        super().__init__(parent, "Diagnose",
                         tr("Messen statt raten: Windows-Fehlerprotokoll und Reste anderer "
                            "Tweak-Tools — alles nur lesend",
                            "Measure, don't guess: the Windows error log and leftovers of other "
                            "tweak tools — all read-only"),
                         color=ACC, scroll=False, **kw)
        self._ui_q: queue.Queue = queue.Queue()
        self._build()
        self._pump_id = self.after(150, self._pump)

    def destroy(self):
        try:
            if self._pump_id:
                self.after_cancel(self._pump_id)
        except Exception:
            pass
        self._pump_id = None
        super().destroy()

    # cross-thread → main-thread UI updates (after() from a worker raises on 3.14)
    def _on_main(self, fn):
        self._ui_q.put(fn)

    def _pump(self):
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self._pump_id = self.after(150, self._pump)
        except (tk.TclError, RuntimeError):
            self._pump_id = None

    def _build(self):
        bar = tk.Frame(self.body, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 10))
        self._view_keys = {"Health-Report": "health", "Remnant-Scan": "remn"}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._view_keys), height=32,
                                          font=ctk_font(12), selected_color=mix(CARD_BG2, ACC, 0.45),
                                          selected_hover_color=mix(CARD_BG2, ACC, 0.6),
                                          command=lambda v: self._show_view(self._view_keys[v]))
        self.seg.pack(side="left")
        holder = tk.Frame(self.body, bg=APP_BG)
        holder.pack(fill="both", expand=True)
        self._views = {}
        for key, builder in (("health", self._build_health), ("remn", self._build_remnants)):
            card = ctk.CTkFrame(holder, fg_color=CARD_BG, corner_radius=12, border_width=1,
                                border_color=BORDER)
            inner = tk.Frame(card, bg=CARD_BG)
            inner.pack(fill="both", expand=True, padx=16, pady=14)
            builder(inner)
            self._views[key] = card
        self._show_view("health")

    def _show_view(self, key):
        for k, f in self._views.items():
            if k != key:
                f.pack_forget()
        self._views[key].pack(fill="both", expand=True)
        self.seg.set(next(lbl for lbl, k in self._view_keys.items() if k == key))

    @staticmethod
    def _head(p, title, color, text):
        tk.Label(p, text=title, font=("Segoe UI Semibold", 12), fg=color, bg=CARD_BG,
                 anchor="w").pack(fill="x")
        WrapLabel(p, text=text, font=F_S, fg=TEXT2, bg=CARD_BG).pack(fill="x", pady=(2, 10))

    @staticmethod
    def _logbox(p, height=10):
        box = ctk.CTkFrame(p, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True, pady=(10, 0))
        log = LogView(box, height=height)
        log.pack(fill="both", expand=True, padx=6, pady=6)
        return log

    # ── Health Report ─────────────────────────────────────────────────────────
    def _build_health(self, p):
        self._head(p, tr("PC-Health-Report — letzte 30 Tage", "PC health report — last 30 days"),
                   HEALTH_COLOR, tr(
            "Liest nur, was Windows ohnehin protokolliert hat: Hardwarefehler (WHEA), Bluescreens, "
            "unerwartete Neustarts, GPU-Timeouts, Datenträgerfehler und App-Abstürze. Es wird nichts "
            "geändert.",
            "Reads only what Windows recorded anyway: hardware errors (WHEA), blue screens, unexpected "
            "restarts, GPU timeouts, disk errors and app crashes. Nothing is changed."))
        self.btn_health = button(p, tr("Report erstellen", "Create report"), self._run_health,
                                 kind="primary", color=HEALTH_COLOR, height=32,
                                 image=icon_image("diagnose", on_color(HEALTH_COLOR), 14), compound="left")
        self.btn_health.pack(anchor="w")
        self.health_log = self._logbox(p)

    def _run_health(self):
        self.btn_health.configure(state="disabled")
        self.health_log.clear()
        self.health_log.append("Lese Windows-Ereignisprotokoll … (kann einige Sekunden dauern)", "header")

        def work():
            rep = health_report.generate()
            if not rep.ok:
                self.health_log.append(f"✗ {rep.error}", "error")
            else:
                self.health_log.append(rep.summary,
                                       "success" if "✓" in rep.summary else "warning")
                for it in rep.items:
                    lvl = {"ok": "info", "warn": "warning", "critical": "error"}[it.severity]
                    when = f"  (zuletzt: {it.last})" if it.last else ""
                    self.health_log.append(f"{it.label}: {it.count}{when}", lvl)
                    if it.count > 0:
                        self.health_log.append(f"    → {it.note}", lvl)
            self._on_main(lambda: self.btn_health.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()

    # ── Remnant Scan ────────────────────────────────────────────────────────────
    def _build_remnants(self, p):
        self._head(p, tr("Remnant-Scan — Reste anderer Tweak-Tools", "Remnant scan — leftovers of other tools"),
                   REMN_COLOR, tr(
            "Sucht nur lesend nach Überbleibseln fremder Optimierungs-Tools (WinRing0/inpout-Treiber, "
            "ISLC, TimerResolution-Autostarts, Fremd-Energiepläne, Razer Cortex). Es wird nichts "
            "entfernt — nur gemeldet.",
            "Looks (read-only) for leftovers of other optimisation tools (WinRing0/inpout drivers, "
            "ISLC, TimerResolution autostarts, foreign power plans, Razer Cortex). Nothing is removed "
            "— only reported."))
        self.btn_remn = button(p, tr("Scan starten", "Start scan"), self._run_remnants, kind="primary",
                               color=REMN_COLOR, height=32,
                               image=icon_image("search", on_color(REMN_COLOR), 14), compound="left")
        self.btn_remn.pack(anchor="w")
        self.remn_log = self._logbox(p)

    def _run_remnants(self):
        self.btn_remn.configure(state="disabled")
        self.remn_log.clear()
        self.remn_log.append("Scanne nach Fremd-Tweak-Resten …", "header")

        def work():
            res = remnant_detector.scan()
            if not res.ok:
                self.remn_log.append(f"✗ {res.error}", "error")
            else:
                self.remn_log.append(res.summary,
                                     "warning" if "mögliche" in res.summary else "success")
                for it in res.items:
                    if it.present:
                        self.remn_log.append(f"⚠ {it.label}: {it.detail}", "warning")
                        self.remn_log.append(f"    → {it.advice}", "info")
                    else:
                        self.remn_log.append(f"✓ {it.label}: nichts gefunden", "info")
            self._on_main(lambda: self.btn_remn.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()
