"""GameOptimizerPro Stability Test Tab — Internal stress worker + Furmark launcher."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading, time, subprocess, os, sys
from datetime import datetime

from ui.widgets import *
from core.nvtune_core import GpuMonitor


FURMARK_DEFAULT_PATHS = [
    r"C:\Program Files\Geeks3D\Benchmarks\FurMark\FurMark.exe",
    r"C:\Program Files (x86)\Geeks3D\Benchmarks\FurMark\FurMark.exe",
    r"C:\Program Files\FurMark\FurMark.exe",
    r"C:\Program Files (x86)\FurMark\FurMark.exe",
]


class StressTab(tk.Frame):
    def __init__(self, parent, monitor: GpuMonitor, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self.monitor = monitor
        self._running_internal = False
        self._worker_proc = None
        self._monitor_thread = None
        self._furmark_path = self._detect_furmark()
        self._build()

    def _detect_furmark(self):
        for p in FURMARK_DEFAULT_PATHS:
            if os.path.exists(p):
                return p
        return None

    def _build(self):
        tk.Label(self, text="Stability Tests", font=FT, fg=WHT, bg=BG1
                 ).pack(padx=14, pady=(12, 6), anchor="w")

        # Two columns: internal + furmark
        cols = tk.Frame(self, bg=BG1)
        cols.pack(fill="x", padx=14, pady=(0, 8))
        cols.columnconfigure((0, 1), weight=1)

        # ── Internal Stress ───────────────────────────────────────────────────
        int_f = tk.Frame(cols, bg=BG2, padx=12, pady=12)
        int_f.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        tk.Label(int_f, text="Internal Stress Test", font=FH, fg=WHT, bg=BG2).pack(anchor="w")
        tk.Label(int_f,
                 text="Matrix math compute loop (CPU/NumPy or CUDA if available).\n"
                      "Good for stability checking after GPU tuning.",
                 font=("Segoe UI", 8), fg=DIM, bg=BG2, justify="left"
                 ).pack(anchor="w", pady=(4, 8))

        dur_f = tk.Frame(int_f, bg=BG2)
        dur_f.pack(anchor="w", pady=4)
        tk.Label(dur_f, text="Duration:", font=FL, fg=DIM, bg=BG2).pack(side="left")
        self.v_int_dur = tk.IntVar(value=300)
        tk.Spinbox(dur_f, textvariable=self.v_int_dur, from_=30, to=3600,
                   width=6, font=FM, bg=BG3, fg=TXT, buttonbackground=BG3,
                   relief="flat").pack(side="left", padx=8)
        tk.Label(dur_f, text="seconds", font=FL, fg=DIM, bg=BG2).pack(side="left")

        max_f = tk.Frame(int_f, bg=BG2)
        max_f.pack(anchor="w", pady=4)
        tk.Label(max_f, text="Max Temp:", font=FL, fg=DIM, bg=BG2).pack(side="left")
        self.v_max_temp = tk.IntVar(value=90)
        tk.Spinbox(max_f, textvariable=self.v_max_temp, from_=70, to=100,
                   width=5, font=FM, bg=BG3, fg=TXT, buttonbackground=BG3,
                   relief="flat").pack(side="left", padx=8)
        tk.Label(max_f, text="°C", font=FL, fg=DIM, bg=BG2).pack(side="left")

        btn_if = tk.Frame(int_f, bg=BG2)
        btn_if.pack(anchor="w", pady=8)
        self.btn_int_start = mk_btn(btn_if, "▶ Start Internal Test",
                                    self._start_internal, ACC, "#000", bold=True)
        self.btn_int_start.pack(side="left", padx=(0, 8))
        self.btn_int_stop = mk_btn(btn_if, "■ Stop", self._stop_internal, ERR, WHT)
        self.btn_int_stop.config(state="disabled")
        self.btn_int_stop.pack(side="left")

        self.lbl_int_status = tk.Label(int_f, text="Idle", font=FM, fg=DIM, bg=BG2)
        self.lbl_int_status.pack(anchor="w")

        # Progress
        self.int_prog = tk.DoubleVar()
        ttk.Progressbar(int_f, variable=self.int_prog, maximum=100
                        ).pack(fill="x", pady=(6, 0))

        # ── FurMark ───────────────────────────────────────────────────────────
        fur_f = tk.Frame(cols, bg=BG2, padx=12, pady=12)
        fur_f.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        tk.Label(fur_f, text="FurMark", font=FH, fg=WHT, bg=BG2).pack(anchor="w")
        tk.Label(fur_f,
                 text="Industry-standard GPU burn-in test.\n"
                      "More realistic load than internal worker.\n"
                      "Requires FurMark to be installed.",
                 font=("Segoe UI", 8), fg=DIM, bg=BG2, justify="left"
                 ).pack(anchor="w", pady=(4, 8))

        # Path display
        path_f = tk.Frame(fur_f, bg=BG2)
        path_f.pack(fill="x", pady=4)
        self.lbl_furmark_path = tk.Label(
            path_f,
            text=f"Found: {self._furmark_path}" if self._furmark_path else "⚠ Not found",
            font=FM,
            fg=OK if self._furmark_path else WRN,
            bg=BG2, anchor="w", wraplength=280
        )
        self.lbl_furmark_path.pack(side="left", fill="x", expand=True)
        mk_btn(path_f, "Browse...", self._browse_furmark, BG3, TXT
               ).pack(side="right")

        # FurMark options
        opt_f = tk.Frame(fur_f, bg=BG2)
        opt_f.pack(anchor="w", pady=4)

        res_opts = ["1920x1080", "2560x1440", "3840x2160"]
        tk.Label(opt_f, text="Resolution:", font=FL, fg=DIM, bg=BG2).pack(side="left")
        self.v_fur_res = tk.StringVar(value="1920x1080")
        ttk.Combobox(opt_f, textvariable=self.v_fur_res, values=res_opts,
                     width=12, state="readonly", font=FM).pack(side="left", padx=8)

        dur2_f = tk.Frame(fur_f, bg=BG2)
        dur2_f.pack(anchor="w", pady=4)
        tk.Label(dur2_f, text="Duration:", font=FL, fg=DIM, bg=BG2).pack(side="left")
        self.v_fur_dur = tk.IntVar(value=300)
        tk.Spinbox(dur2_f, textvariable=self.v_fur_dur, from_=30, to=3600,
                   width=6, font=FM, bg=BG3, fg=TXT, buttonbackground=BG3,
                   relief="flat").pack(side="left", padx=8)
        tk.Label(dur2_f, text="seconds", font=FL, fg=DIM, bg=BG2).pack(side="left")

        btn_ff = tk.Frame(fur_f, bg=BG2)
        btn_ff.pack(anchor="w", pady=8)
        self.btn_fur_start = mk_btn(btn_ff, "▶ Launch FurMark",
                                    self._launch_furmark, ACC2, WHT, bold=True)
        self.btn_fur_start.pack(side="left", padx=(0, 8))
        if not self._furmark_path:
            mk_btn(btn_ff, "⬇ Download FurMark", self._open_furmark_dl, BG3, TXT
                   ).pack(side="left")

        self.lbl_fur_status = tk.Label(fur_f, text="Idle", font=FM, fg=DIM, bg=BG2)
        self.lbl_fur_status.pack(anchor="w")

        # ── Live monitoring ───────────────────────────────────────────────────
        SecHdr(self, "Live GPU during Test").pack(fill="x", padx=14, pady=(8, 4))

        live_f = tk.Frame(self, bg=BG2)
        live_f.pack(fill="x", padx=14, pady=(0, 8))
        live_f.columnconfigure((0, 1, 2, 3, 4), weight=1)

        self._stiles = {}
        for i, (key, label, unit, color) in enumerate([
            ("temp",  "Temp",      "°C",  ERR),
            ("volt",  "Voltage",   "mV",  VOLT),
            ("core",  "Core",      "MHz", ACC),
            ("power", "Power",     "W",   WRN),
            ("usage", "GPU Load",  "%",   OK),
        ]):
            f, vl = mk_tile(live_f, label, "--", color, unit)
            f.grid(row=0, column=i, padx=3, pady=8, sticky="nsew")
            self._stiles[key] = vl

        # Bar
        bar_f = tk.Frame(self, bg=BG1)
        bar_f.pack(fill="x", padx=14, pady=4)
        self.bar_temp  = HBar(bar_f, "Temperature", "°C", ERR)
        self.bar_power = HBar(bar_f, "Power Draw",  "W",  WRN)
        for b in (self.bar_temp, self.bar_power):
            b.pack(fill="x", padx=4, pady=2)

        # Log
        SecHdr(self, "Test Log").pack(fill="x", padx=14, pady=(6, 0))
        self.log = LogBox(self)
        self.log.pack(fill="both", expand=True, padx=14, pady=(2, 8))

        # Start passive monitoring
        self._start_passive_monitor()

    # ── Internal stress ───────────────────────────────────────────────────────

    def _start_internal(self):
        if self._running_internal:
            return
        self._running_internal = True
        self.btn_int_start.config(state="disabled")
        self.btn_int_stop.config(state="normal")
        self.log.append("Internal stress test started.", "header")
        self.log.append(f"Duration: {self.v_int_dur.get()}s | Max temp: {self.v_max_temp.get()}°C")

        worker = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_stress_worker.py")

        def _run():
            # Start worker
            if os.path.exists(worker):
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self._worker_proc = subprocess.Popen(
                    [sys.executable, worker, str(os.getpid())],  # GUI PID → dead-man switch
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=flags
                )

            dur = self.v_int_dur.get()
            max_t = self.v_max_temp.get()
            start = time.time()
            peak_temp = 0

            while self._running_internal:
                elapsed = time.time() - start
                if elapsed >= dur:
                    break
                stats = self.monitor.read()
                peak_temp = max(peak_temp, stats.temp)
                pct = (elapsed / dur) * 100
                self.after(0, lambda e=int(elapsed), d=dur, p=pct:
                           self._int_tick(e, d, p))
                if stats.temp >= max_t:
                    self.after(0, lambda t=stats.temp:
                               self.log.append(f"⚠ ABORT: Temp limit {t}°C reached!", "error"))
                    break
                time.sleep(1.0)

            self._stop_internal_worker()
            passed = peak_temp < max_t
            self.after(0, lambda: self._int_done(passed, peak_temp))

        threading.Thread(target=_run, daemon=True).start()

    def _int_tick(self, elapsed, dur, pct):
        self.int_prog.set(pct)
        self.lbl_int_status.config(
            text=f"Running: {elapsed}/{dur}s", fg=ACC)

    def _int_done(self, passed, peak_temp):
        self._running_internal = False
        self.btn_int_start.config(state="normal")
        self.btn_int_stop.config(state="disabled")
        self.int_prog.set(0)
        result = "✓ PASSED" if passed else "✗ FAILED (temp limit)"
        color  = OK if passed else ERR
        self.lbl_int_status.config(text=f"{result} | Peak: {peak_temp}°C", fg=color)
        self.log.append(f"Internal stress: {result} | Peak temp: {peak_temp}°C",
                        "success" if passed else "error")

    def _stop_internal(self):
        self._running_internal = False
        self._stop_internal_worker()
        self.btn_int_start.config(state="normal")
        self.btn_int_stop.config(state="disabled")
        self.int_prog.set(0)
        self.lbl_int_status.config(text="Stopped.", fg=WRN)
        self.log.append("Internal stress test stopped by user.", "warning")

    def _stop_internal_worker(self):
        if self._worker_proc:
            try:
                self._worker_proc.terminate()
                self._worker_proc.wait(timeout=5)
            except: pass
            self._worker_proc = None

    # ── FurMark ───────────────────────────────────────────────────────────────

    def _launch_furmark(self):
        if not self._furmark_path:
            messagebox.showerror("FurMark Not Found",
                                 "FurMark.exe not found.\n"
                                 "Install FurMark from geeks3d.com/furmark\n"
                                 "or use Browse to locate it.")
            return

        res = self.v_fur_res.get()
        w, h = res.split("x")
        dur_ms = self.v_fur_dur.get() * 1000

        try:
            subprocess.Popen([
                self._furmark_path,
                f"/width={w}", f"/height={h}",
                f"/max_time={dur_ms}",
                "/nogui", "/run_mode=1"
            ])
            self.lbl_fur_status.config(text=f"FurMark launched ({res}, {self.v_fur_dur.get()}s)", fg=OK)
            self.log.append(f"FurMark launched: {res}, {self.v_fur_dur.get()}s", "success")
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))

    def _browse_furmark(self):
        path = filedialog.askopenfilename(
            title="Locate FurMark.exe",
            filetypes=[("Executable", "*.exe")]
        )
        if path:
            self._furmark_path = path
            self.lbl_furmark_path.config(text=f"Found: {path}", fg=OK)

    def _open_furmark_dl(self):
        import webbrowser
        webbrowser.open("https://geeks3d.com/furmark/")

    # ── Passive monitor ───────────────────────────────────────────────────────

    def _start_passive_monitor(self):
        def loop():
            while True:
                try:
                    s = self.monitor.read()
                    self.after(0, self._update_live, s)
                except: pass
                time.sleep(1.5)
        threading.Thread(target=loop, daemon=True).start()

    def _update_live(self, s):
        tc = ERR if s.temp >= 85 else WRN if s.temp >= 75 else ACC
        self._stiles["temp"].config( text=str(s.temp), fg=tc)
        self._stiles["volt"].config( text=f"{s.voltage_mv:.0f}" if s.voltage_mv > 0 else "--")
        self._stiles["core"].config( text=f"{s.core_mhz:.0f}")
        self._stiles["power"].config(text=f"{s.gpu_power_w:.0f}")
        self._stiles["usage"].config(text=f"{s.gpu_usage:.0f}")
        self.bar_temp.set( s.temp,        s.temp_limit_c or 100)
        self.bar_power.set(s.gpu_power_w, s.power_max_w or 400)
