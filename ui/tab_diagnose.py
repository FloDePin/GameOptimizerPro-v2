"""
GameOptimizerPro v2.0 — Diagnose page
Measure, don't guess:
  • FPS / Frametime  — live PresentMon capture or analyze an existing CSV
                       (Avg / 1% low / 0.1% low / stutters / CPU-vs-GPU bottleneck)
  • Health Report    — 30 days of what Windows already recorded (read-only)
  • Remnant Scan     — leftovers of other tweak tools (read-only)

Threading: worker threads write results straight into the thread-safe LogView
(queue-backed). All other widget updates go through a main-thread pump queue —
never after() from a worker (raises RuntimeError on Python 3.14).
"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from core import fps_capture, health_report, remnant_detector
from ui.components import LogView, Page, WrapLabel, button
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, DIM, F_S, F_XS, GREEN,
                      INPUT_BG, TEXT, TEXT2, ctk_font, icon_image, mix, on_color, tr)

FPS_COLOR    = ACC
HEALTH_COLOR = GREEN
REMN_COLOR   = AMBER


class DiagnoseTab(Page):
    def __init__(self, parent, **kw):
        super().__init__(parent, "Diagnose",
                         tr("Messen statt raten: FPS & Frametimes, Windows-Fehlerprotokoll und Reste "
                            "anderer Tweak-Tools — alles nur lesend",
                            "Measure, don't guess: FPS & frame times, the Windows error log and "
                            "leftovers of other tweak tools — all read-only"),
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
        self._view_keys = {"FPS / Frametime": "fps", "Health-Report": "health", "Remnant-Scan": "remn"}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._view_keys), height=32,
                                          font=ctk_font(12), selected_color=mix(CARD_BG2, ACC, 0.45),
                                          selected_hover_color=mix(CARD_BG2, ACC, 0.6),
                                          command=lambda v: self._show_view(self._view_keys[v]))
        self.seg.pack(side="left")
        holder = tk.Frame(self.body, bg=APP_BG)
        holder.pack(fill="both", expand=True)
        self._views = {}
        for key, builder in (("fps", self._build_fps), ("health", self._build_health),
                             ("remn", self._build_remnants)):
            card = ctk.CTkFrame(holder, fg_color=CARD_BG, corner_radius=12, border_width=1,
                                border_color=BORDER)
            inner = tk.Frame(card, bg=CARD_BG)
            inner.pack(fill="both", expand=True, padx=16, pady=14)
            builder(inner)
            self._views[key] = card
        self._show_view("fps")

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

    # ── FPS / Frametime ─────────────────────────────────────────────────────
    def _build_fps(self, p):
        self._head(p, tr("FPS / Frametime-Messung", "FPS / frame-time measurement"), FPS_COLOR, tr(
            "Miss den echten Effekt deiner Tweaks: Ø FPS, 1 %- und 0,1 %-Lows, Stutters und ob du CPU- "
            "oder GPU-limitiert bist. Entweder live via PresentMon aufzeichnen oder eine vorhandene "
            "PresentMon/CapFrameX-CSV auswerten.",
            "Measure the real effect of your tweaks: avg FPS, 1 % and 0.1 % lows, stutters and whether "
            "you are CPU- or GPU-bound. Record live via PresentMon or analyse an existing "
            "PresentMon/CapFrameX CSV."))

        row = tk.Frame(p, bg=CARD_BG)
        row.pack(fill="x")
        tk.Label(row, text=tr("Prozess (.exe)", "Process (.exe)"), font=F_S, fg=TEXT2, bg=CARD_BG).pack(side="left")
        self.fps_exe = ctk.CTkEntry(row, width=220, height=30)
        self.fps_exe.insert(0, "Cyberpunk2077.exe")
        self.fps_exe.pack(side="left", padx=(8, 16))
        tk.Label(row, text=tr("Dauer (s)", "Duration (s)"), font=F_S, fg=TEXT2, bg=CARD_BG).pack(side="left")
        self.fps_dur = ctk.CTkEntry(row, width=70, height=30, justify="center")
        self.fps_dur.insert(0, "30")
        self.fps_dur.pack(side="left", padx=8)

        btns = tk.Frame(p, bg=CARD_BG)
        btns.pack(fill="x", pady=(10, 0))
        self.btn_capture = button(btns, tr("Live-Capture (PresentMon)", "Live capture (PresentMon)"),
                                  self._start_capture, kind="primary", color=FPS_COLOR, height=32,
                                  image=icon_image("play", on_color(FPS_COLOR), 14), compound="left")
        self.btn_capture.pack(side="left", padx=(0, 6))
        self.btn_csv = button(btns, tr("CSV analysieren", "Analyse CSV"), self._analyze_csv, height=32,
                              image=icon_image("folder", TEXT, 14), compound="left")
        self.btn_csv.pack(side="left")

        pm = fps_capture.find_presentmon()
        pm_txt = (f"PresentMon gefunden: {pm}" if pm else
                  "PresentMon nicht gefunden — für Live-Capture PresentMon.exe in den "
                  "'tools'-Ordner legen (github.com/GameTechDev/PresentMon). CSV-Analyse "
                  "geht immer.")
        WrapLabel(p, text=pm_txt, font=F_XS, fg=(GREEN if pm else DIM), bg=CARD_BG).pack(fill="x", pady=(8, 0))
        self.fps_log = self._logbox(p)

    def _start_capture(self):
        exe = self.fps_exe.get().strip()
        if not exe:
            self.fps_log.append("Bitte einen Prozessnamen angeben (z.B. game.exe).", "warning")
            return
        try:
            dur = max(5, min(600, int(self.fps_dur.get().strip() or "30")))
        except ValueError:
            dur = 30
        self.btn_capture.configure(state="disabled")
        self.fps_log.append(f"Capture läuft: {exe} für {dur}s … (Spiel muss laufen)", "header")

        def work():
            stats = fps_capture.capture_live(exe, dur)
            for line in fps_capture.format_summary(stats):
                self.fps_log.append(line, "success" if stats.ok else "error")
            self._on_main(lambda: self.btn_capture.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()

    def _analyze_csv(self):
        path = filedialog.askopenfilename(
            title="PresentMon / CapFrameX CSV wählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")])
        if not path:
            return
        self.btn_csv.configure(state="disabled")
        self.fps_log.append(f"Analysiere: {path}", "header")

        def work():
            stats = fps_capture.parse_csv(path)
            for line in fps_capture.format_summary(stats):
                self.fps_log.append(line, "success" if stats.ok else "error")
            self._on_main(lambda: self.btn_csv.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()

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
