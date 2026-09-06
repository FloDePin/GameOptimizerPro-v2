"""
GameOptimizerPro v2.0 — Diagnose Tab
Measure, don't guess:
  • FPS / Frametime  — live PresentMon capture or analyze an existing CSV
                       (Avg / 1% low / 0.1% low / stutters / CPU-vs-GPU bottleneck)
  • Health Report    — 30 days of what Windows already recorded (read-only)
  • Remnant Scan     — leftovers of other tweak tools (read-only)

Threading: worker threads write results straight into the thread-safe LogBox
(queue-backed). All other widget updates go through a main-thread pump queue —
never after() from a worker (raises RuntimeError on Python 3.14).
"""

import tkinter as tk
from tkinter import ttk, filedialog
import threading
import queue

from ui.widgets import *
from core import fps_capture, health_report, remnant_detector

DARK  = BG1
FPS_COLOR    = "#00d9ff"
HEALTH_COLOR = "#22c55e"
REMN_COLOR   = "#f59e0b"


class DiagnoseTab(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=DARK, **kw)
        self._ui_q: queue.Queue = queue.Queue()
        self._build()
        self.after(150, self._pump)

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
        self.after(150, self._pump)

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        f_fps    = tk.Frame(nb, bg=DARK)
        f_health = tk.Frame(nb, bg=DARK)
        f_remn   = tk.Frame(nb, bg=DARK)
        nb.add(f_fps,    text="  🎯 FPS / Frametime  ")
        nb.add(f_health, text="  🩺 Health Report  ")
        nb.add(f_remn,   text="  🧹 Remnant-Scan  ")
        self._build_fps(f_fps)
        self._build_health(f_health)
        self._build_remnants(f_remn)

    # ── FPS / Frametime ─────────────────────────────────────────────────────
    def _build_fps(self, p):
        tk.Label(p, text="🎯  FPS / Frametime Messung", font=("Segoe UI", 10, "bold"),
                 fg=FPS_COLOR, bg=DARK).pack(padx=14, pady=(10, 2), anchor="w")
        tk.Label(p, text="Miss den echten Effekt deiner Tweaks: Ø FPS, 1%- und 0.1%-Lows, "
                         "Stutters und ob du CPU- oder GPU-limitiert bist. Entweder live via "
                         "PresentMon aufzeichnen oder eine vorhandene PresentMon/CapFrameX-CSV auswerten.",
                 font=("Segoe UI", 8), fg=DIM, bg=DARK, wraplength=820, justify="left"
                 ).pack(padx=14, anchor="w")

        row = tk.Frame(p, bg=DARK); row.pack(fill="x", padx=14, pady=(8, 2))
        tk.Label(row, text="Prozess (.exe):", font=FM, fg=TXT, bg=DARK).pack(side="left")
        self.fps_exe = tk.Entry(row, font=FM, bg=BG2, fg=TXT, insertbackground=TXT,
                                relief="flat", width=26)
        self.fps_exe.insert(0, "Cyberpunk2077.exe")
        self.fps_exe.pack(side="left", padx=(6, 12))
        tk.Label(row, text="Dauer (s):", font=FM, fg=TXT, bg=DARK).pack(side="left")
        self.fps_dur = tk.Entry(row, font=FM, bg=BG2, fg=TXT, insertbackground=TXT,
                                relief="flat", width=6)
        self.fps_dur.insert(0, "30")
        self.fps_dur.pack(side="left", padx=6)

        btns = tk.Frame(p, bg=DARK); btns.pack(fill="x", padx=14, pady=4)
        self.btn_capture = mk_btn(btns, "▶ Live-Capture (PresentMon)", self._start_capture,
                                  FPS_COLOR, "#001018", bold=True)
        self.btn_capture.pack(side="left", padx=(0, 6))
        self.btn_csv = mk_btn(btns, "📂 CSV analysieren", self._analyze_csv, BG3, TXT)
        self.btn_csv.pack(side="left")

        pm = fps_capture.find_presentmon()
        pm_txt = (f"PresentMon gefunden: {pm}" if pm else
                  "PresentMon nicht gefunden — für Live-Capture PresentMon.exe in den "
                  "'tools'-Ordner legen (github.com/GameTechDev/PresentMon). CSV-Analyse "
                  "geht immer.")
        tk.Label(p, text=pm_txt, font=("Segoe UI", 8),
                 fg=(OK if pm else DIM), bg=DARK, wraplength=820, justify="left"
                 ).pack(padx=14, anchor="w", pady=(0, 2))

        SecHdr(p, "Ergebnis").pack(fill="x", padx=14, pady=(6, 0))
        self.fps_log = LogBox(p)
        self.fps_log.pack(fill="both", expand=True, padx=14, pady=(2, 10))

    def _start_capture(self):
        exe = self.fps_exe.get().strip()
        if not exe:
            self.fps_log.append("Bitte einen Prozessnamen angeben (z.B. game.exe).", "warning")
            return
        try:
            dur = max(5, min(600, int(self.fps_dur.get().strip() or "30")))
        except ValueError:
            dur = 30
        self.btn_capture.config(state="disabled")
        self.fps_log.append(f"Capture läuft: {exe} für {dur}s … (Spiel muss laufen)", "header")

        def work():
            stats = fps_capture.capture_live(exe, dur)
            for line in fps_capture.format_summary(stats):
                self.fps_log.append(line, "success" if stats.ok else "error")
            self._on_main(lambda: self.btn_capture.config(state="normal"))
        threading.Thread(target=work, daemon=True).start()

    def _analyze_csv(self):
        path = filedialog.askopenfilename(
            title="PresentMon / CapFrameX CSV wählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")])
        if not path:
            return
        self.btn_csv.config(state="disabled")
        self.fps_log.append(f"Analysiere: {path}", "header")

        def work():
            stats = fps_capture.parse_csv(path)
            for line in fps_capture.format_summary(stats):
                self.fps_log.append(line, "success" if stats.ok else "error")
            self._on_main(lambda: self.btn_csv.config(state="normal"))
        threading.Thread(target=work, daemon=True).start()

    # ── Health Report ─────────────────────────────────────────────────────────
    def _build_health(self, p):
        tk.Label(p, text="🩺  PC Health Report — letzte 30 Tage", font=("Segoe UI", 10, "bold"),
                 fg=HEALTH_COLOR, bg=DARK).pack(padx=14, pady=(10, 2), anchor="w")
        tk.Label(p, text="Liest read-only, was Windows ohnehin protokolliert hat: "
                         "Hardwarefehler (WHEA), Bluescreens, unerwartete Neustarts, GPU-Timeouts, "
                         "Datenträgerfehler und App-Abstürze. Es wird nichts geändert.",
                 font=("Segoe UI", 8), fg=DIM, bg=DARK, wraplength=820, justify="left"
                 ).pack(padx=14, anchor="w")
        self.btn_health = mk_btn(p, "🩺 Report erstellen", self._run_health, HEALTH_COLOR, "#001008", bold=True)
        self.btn_health.pack(anchor="w", padx=14, pady=6)
        self.health_log = LogBox(p)
        self.health_log.pack(fill="both", expand=True, padx=14, pady=(2, 10))

    def _run_health(self):
        self.btn_health.config(state="disabled")
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
            self._on_main(lambda: self.btn_health.config(state="normal"))
        threading.Thread(target=work, daemon=True).start()

    # ── Remnant Scan ────────────────────────────────────────────────────────────
    def _build_remnants(self, p):
        tk.Label(p, text="🧹  Remnant-Scan — Reste anderer Tweak-Tools", font=("Segoe UI", 10, "bold"),
                 fg=REMN_COLOR, bg=DARK).pack(padx=14, pady=(10, 2), anchor="w")
        tk.Label(p, text="Sucht read-only nach Überbleibseln fremder Optimierungs-Tools "
                         "(WinRing0/inpout-Treiber, ISLC, TimerResolution-Autostarts, "
                         "Fremd-Energiepläne, Razer Cortex). Es wird nichts entfernt — nur gemeldet.",
                 font=("Segoe UI", 8), fg=DIM, bg=DARK, wraplength=820, justify="left"
                 ).pack(padx=14, anchor="w")
        self.btn_remn = mk_btn(p, "🧹 Scan starten", self._run_remnants, REMN_COLOR, "#100a00", bold=True)
        self.btn_remn.pack(anchor="w", padx=14, pady=6)
        self.remn_log = LogBox(p)
        self.remn_log.pack(fill="both", expand=True, padx=14, pady=(2, 10))

    def _run_remnants(self):
        self.btn_remn.config(state="disabled")
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
            self._on_main(lambda: self.btn_remn.config(state="normal"))
        threading.Thread(target=work, daemon=True).start()
