"""GameOptimizerPro Stress Test page — internal stress worker, FurMark 1/2 and
3DMark launchers, and a recording of the GPU values while an external test runs
(peak temperature, clocks, power, driver resets)."""

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import furmark, threedmark
from core.nvtune_core import GpuMonitor
from ui.components import (Card, GaugeBar, LogView, NumberField, Page, ResponsiveGrid, WrapLabel,
                           button, tile)
from ui.theme import (ACC, AMBER, BORDER, CARD_BG, CYAN, DIM, ERR, F_MONO, F_S, F_XS, GREEN,
                      INPUT_BG, MUTED, PURPLE, TEXT, TEXT2, VIOLET, icon_image, on_color, tr)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOLUTIONS = ["1280x720", "1920x1080", "2560x1440", "3440x1440", "3840x2160"]


class StressTab(Page):
    # A result only counts as a GPU stability test if the GPU was really loaded.
    MIN_GPU_LOAD_PCT = 70.0

    def __init__(self, parent, monitor: GpuMonitor, **kw):
        super().__init__(parent, tr("Stresstest", "Stress test"),
                         tr("Stabilität prüfen — intern, mit FurMark oder 3DMark. Bei externen Tests "
                            "zeichnet GameOptimizerPro Temperatur, Takt, Leistung und Treiber-Resets auf.",
                            "Check stability — internally, with FurMark or 3DMark. During external "
                            "tests GameOptimizerPro records temperature, clocks, power and driver resets."),
                         color=AMBER, **kw)
        self.monitor = monitor
        self._running_internal = False
        self._worker_proc = None
        self._monitor_thread = None
        # Run generation: bumped on every Start and Stop. A test thread only
        # reports (and only kills its OWN worker) while its generation is
        # current — so a quick Stop -> Start can no longer let the old thread
        # kill the new worker or report the stopped run as "PASSED".
        self._run_gen = 0
        self._ext = None                 # running external-test recording
        self._ext_gen = 0
        self._visible = True
        self._alive = True
        self._furmark_path = self._detect_furmark()
        self._3dmark_path = threedmark.detect()
        self._build()

    def on_show(self):
        self._visible = True

    def on_hide(self):
        self._visible = False

    def stop(self):
        self._alive = False

    def _detect_furmark(self):
        # saved choice, a FurMark folder next to the app, install locations
        return furmark.detect()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        from core import app_settings
        b = self.body
        grid = ResponsiveGrid(b, min_width=300, max_cols=3, gap=14)
        grid.pack(fill="x", padx=10, pady=(0, 14))

        # ── Internal ──────────────────────────────────────────────────────────
        ic = Card(grid, tr("Interner Test", "Internal test"), accent=ACC)
        grid.add(ic)
        WrapLabel(ic.body, text=tr(
            "Rechenschleife auf der GPU (CUDA über cupy, sonst nur CPU) mit Ergebnis-Prüfung: "
            "falsche Ergebnisse unter Last = instabil. Gut direkt nach dem GPU-Tuning.",
            "Compute loop on the GPU (CUDA via cupy, otherwise CPU only) with result checks: wrong "
            "results under load = unstable. Good right after GPU tuning."),
            font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(0, 10))
        self.v_int_dur = tk.IntVar(value=300)
        self.v_max_temp = tk.IntVar(value=90)
        self._field(ic.body, tr("Dauer (s)", "Duration (s)"), self.v_int_dur, 30, 3600, 30)
        self._field(ic.body, tr("Max. Temperatur (°C)", "Max temp (°C)"), self.v_max_temp, 70, 100, 1)
        row = tk.Frame(ic.body, bg=CARD_BG)
        row.pack(fill="x", pady=(10, 6))
        self.btn_int_start = button(row, tr("Test starten", "Start test"), self._start_internal,
                                    kind="primary", color=ACC, height=32,
                                    image=icon_image("play", on_color(ACC), 14), compound="left")
        self.btn_int_start.pack(side="left", padx=(0, 6))
        self.btn_int_stop = button(row, "Stop", self._stop_internal, kind="danger", height=32,
                                   state="disabled")
        self.btn_int_stop.pack(side="left")
        self.int_prog = tk.DoubleVar()
        self._int_bar = ctk.CTkProgressBar(ic.body, height=6, corner_radius=3, progress_color=ACC)
        self._int_bar.set(0)
        self._int_bar.pack(fill="x", pady=(4, 4))
        self.int_prog.trace_add("write", lambda *_: self._int_bar.set(
            max(0.0, min(1.0, self.int_prog.get() / 100))))
        self.lbl_int_status = WrapLabel(ic.body, text="Idle", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_int_status.pack(fill="x")

        # ── FurMark ───────────────────────────────────────────────────────────
        fc = Card(grid, "FurMark", accent=AMBER)
        grid.add(fc)
        button(fc.actions, tr("Suchen …", "Browse …"), self._browse_furmark, height=26,
               image=icon_image("folder", TEXT, 13), compound="left").pack(side="right")
        self.lbl_furmark_path = WrapLabel(fc.body, text="", font=F_XS, fg=DIM, bg=CARD_BG)
        self.lbl_furmark_path.pack(fill="x", pady=(0, 10))
        self.v_fur_demo = tk.StringVar(value=furmark.DEMOS.get(
            app_settings.get("furmark_demo", "furmark-gl"), furmark.DEMOS["furmark-gl"]))
        self.opt_demo = self._option(fc.body, "Demo", self.v_fur_demo, list(furmark.DEMOS.values()))
        native = f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}"
        res_opts = RESOLUTIONS + ([native] if native not in RESOLUTIONS else [])
        res_opts.sort(key=lambda r: int(r.split("x")[0]) * int(r.split("x")[1]))
        self.v_fur_res = tk.StringVar(value=app_settings.get("furmark_res", "1920x1080"))
        self._option(fc.body, tr("Auflösung", "Resolution"), self.v_fur_res, res_opts)
        self.v_fur_dur = tk.IntVar(value=int(app_settings.get("furmark_seconds", 300)))
        self._field(fc.body, tr("Dauer (s)", "Duration (s)"), self.v_fur_dur, 30, 3600, 30)
        row = tk.Frame(fc.body, bg=CARD_BG)
        row.pack(fill="x", pady=(10, 6))
        self.btn_fur_start = button(row, tr("FurMark starten", "Launch FurMark"), self._launch_furmark,
                                    kind="primary", color=AMBER, height=32,
                                    image=icon_image("flame", on_color(AMBER), 14), compound="left")
        self.btn_fur_start.pack(side="left", padx=(0, 6))
        self.btn_fur_dl = button(row, "Download", self._open_furmark_dl, kind="ghost", height=32,
                                 image=icon_image("download", TEXT2, 14), compound="left")
        self.lbl_fur_status = WrapLabel(fc.body, text="Idle", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_fur_status.pack(fill="x")
        self._show_furmark()

        # ── 3DMark ────────────────────────────────────────────────────────────
        tc = Card(grid, "3DMark", accent=PURPLE)
        grid.add(tc)
        button(tc.actions, tr("Suchen …", "Browse …"), self._browse_3dmark, height=26,
               image=icon_image("folder", TEXT, 13), compound="left").pack(side="right")
        self.lbl_3dm_path = WrapLabel(tc.body, text="", font=F_XS, fg=DIM, bg=CARD_BG)
        self.lbl_3dm_path.pack(fill="x", pady=(0, 10))
        WrapLabel(tc.body, text=tr(
            "Den Test (Time Spy, Speed Way, Stresstests …) wählst du in 3DMark. GameOptimizerPro "
            "zeichnet währenddessen die GPU-Werte auf und meldet Treiber-Resets. Stresstests per "
            "Kommandozeile gibt es nur in der Professional Edition.",
            "Pick the test (Time Spy, Speed Way, stress tests …) in 3DMark. GameOptimizerPro records "
            "the GPU values meanwhile and reports driver resets. Command-line stress tests exist only "
            "in the Professional Edition."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")
        row = tk.Frame(tc.body, bg=CARD_BG)
        row.pack(fill="x", pady=(12, 6))
        self.btn_3dm_start = button(row, tr("3DMark starten", "Launch 3DMark"), self._launch_3dmark,
                                    kind="primary", color=PURPLE, height=32,
                                    image=icon_image("play", on_color(PURPLE), 14), compound="left")
        self.btn_3dm_start.pack(side="left", padx=(0, 6))
        self.btn_3dm_store = button(row, "Steam-Store", self._open_3dmark_store, kind="ghost",
                                    height=32, image=icon_image("link", TEXT2, 14), compound="left")
        self.lbl_3dm_status = WrapLabel(tc.body, text="Idle", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_3dm_status.pack(fill="x")
        self._show_3dmark()

        # ── Live values + recording ──────────────────────────────────────────
        lc = Card(b, tr("Live-GPU während des Tests", "Live GPU during the test"), accent=CYAN)
        lc.pack(fill="x", padx=10, pady=(0, 14))
        self.btn_rec_stop = button(lc.actions, tr("Aufzeichnung beenden", "Stop recording"),
                                   self._stop_session, kind="ghost", height=26,
                                   image=icon_image("stop", TEXT2, 13), compound="left")
        tiles = ResponsiveGrid(lc.body, min_width=100, max_cols=5, gap=8, bg=CARD_BG)
        tiles.pack(fill="x")
        self._stiles = {}
        for key, label, unit, color in (
            ("temp",  "Temp",                      "°C",  ERR),
            ("volt",  tr("Spannung", "Voltage"),   "mV",  VIOLET),
            ("core",  "Core",                      "MHz", ACC),
            ("power", tr("Leistung", "Power"),     "W",   AMBER),
            ("usage", tr("GPU-Last", "GPU load"),  "%",   GREEN),
        ):
            f, vl = tile(tiles, label, "--", color, unit)
            tiles.add(f)
            self._stiles[key] = vl
        bars = tk.Frame(lc.body, bg=CARD_BG)
        bars.pack(fill="x", pady=(10, 0))
        self.bar_temp  = GaugeBar(bars, tr("Temperatur", "Temperature"), "°C", ERR)
        self.bar_power = GaugeBar(bars, tr("Leistung", "Power draw"), "W", AMBER)
        for bar in (self.bar_temp, self.bar_power):
            bar.pack(fill="x", pady=1)
        self.lbl_session = WrapLabel(lc.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_session.pack(fill="x", pady=(8, 0))

        # ── Log ───────────────────────────────────────────────────────────────
        logc = ctk.CTkFrame(b, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER)
        logc.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(logc, text=tr("Test-Log", "Test log"), font=("Segoe UI Semibold", 8), fg=MUTED,
                 bg=INPUT_BG).pack(anchor="w", padx=12, pady=(8, 0))
        self.log = LogView(logc, height=9)
        self.log.pack(fill="x", padx=6, pady=(0, 6))

        # Start passive monitoring
        self._start_passive_monitor()

    def _field(self, parent, label, var, lo, hi, step):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=F_S, fg=TEXT2, bg=CARD_BG, anchor="w").pack(side="left")
        NumberField(row, var, lo, hi, step, width=64, bg=CARD_BG).pack(side="right")
        return row

    def _option(self, parent, label, var, values):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=F_S, fg=TEXT2, bg=CARD_BG, anchor="w").pack(side="left")
        om = ctk.CTkOptionMenu(row, variable=var, values=values, width=170, height=28,
                               dynamic_resizing=False)
        om.pack(side="right")
        return om

    # ── Internal stress ───────────────────────────────────────────────────────

    def _start_internal(self):
        if self._running_internal:
            return
        self._running_internal = True
        self._run_gen += 1
        gen = self._run_gen
        self.btn_int_start.configure(state="disabled")
        self.btn_int_stop.configure(state="normal")
        self.log.append("Internal stress test started.", "header")
        self.log.append(f"Duration: {self.v_int_dur.get()}s | Max temp: {self.v_max_temp.get()}°C")

        worker = os.path.join(BASE, "_stress_worker.py")
        dur = self.v_int_dur.get()
        max_t = self.v_max_temp.get()

        def _run():
            from core.power_state import keep_awake
            keep_awake(True)                 # released when this thread ends
            proc = None
            if os.path.exists(worker):
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(
                    [sys.executable, worker, str(os.getpid())],  # GUI PID → dead-man switch
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=flags
                )
                self._worker_proc = proc

            try:
                from core.crash_recovery import CrashRecovery
                cr = CrashRecovery(os.path.join(BASE, "logs"))
            except Exception:
                cr = None

            start = time.time()
            last_tdr = start
            peak_temp = 0
            usages = []
            reason = ""          # "" = ran the full duration

            while self._running_internal and gen == self._run_gen:
                elapsed = time.time() - start
                if elapsed >= dur:
                    break
                stats = self.monitor.read()
                peak_temp = max(peak_temp, stats.temp)
                if elapsed >= 3:                     # skip the worker's ramp-up
                    usages.append(float(stats.gpu_usage or 0.0))
                pct = (elapsed / dur) * 100
                self.after(0, lambda e=int(elapsed), d=dur, p=pct:
                           self._int_tick(e, d, p))
                if stats.temp >= max_t:
                    reason = "temp"
                    break
                # A crashed worker is THE instability signal — it used to be
                # ignored, and the run was reported "PASSED" with no load at all.
                if proc is not None and proc.poll() is not None:
                    # exit 3 = the worker saw a WRONG result (gpu-burn style check)
                    reason = "errors" if proc.returncode == 3 else "worker"
                    break
                if cr is not None and time.time() - last_tdr >= 10:
                    last_tdr = time.time()
                    if cr.check_tdr_since(seconds_back=15):
                        reason = "tdr"
                        break
                time.sleep(1.0)

            self._kill_proc(proc)            # only OUR worker, never a newer run's
            keep_awake(False)
            if gen != self._run_gen:
                return                       # stopped/superseded: _stop_internal reported it
            avg_usage = round(sum(usages) / len(usages), 1) if usages else 0.0
            self.after(0, lambda: self._int_done(reason, peak_temp, avg_usage, max_t))

        threading.Thread(target=_run, daemon=True).start()

    def _int_tick(self, elapsed, dur, pct):
        self.int_prog.set(pct)
        self.lbl_int_status.config(text=f"Running: {elapsed}/{dur}s", fg=ACC)

    def _int_done(self, reason, peak_temp, avg_usage, max_t):
        self._running_internal = False
        self.btn_int_start.configure(state="normal")
        self.btn_int_stop.configure(state="disabled")
        self.int_prog.set(0)
        if reason == "temp":
            result, color, tag = f"✗ FAILED (Temp-Limit {max_t}°C erreicht)", ERR, "error"
        elif reason == "errors":
            result, color, tag = "✗ FAILED (Rechenfehler unter Last — GPU instabil)", ERR, "error"
        elif reason == "worker":
            result, color, tag = "✗ FAILED (Stress-Worker abgestürzt)", ERR, "error"
        elif reason == "tdr":
            result, color, tag = "✗ FAILED (GPU-Treiber-Timeout / TDR)", ERR, "error"
        elif avg_usage < self.MIN_GPU_LOAD_PCT:
            # "Passed" would be meaningless: without 'cupy' the worker only
            # burns the CPU, the GPU idles and nothing about its stability is shown.
            result, color, tag = (f"⚠ KEIN GPU-STRESS (Ø {avg_usage:.0f} % GPU-Last) — "
                                  "nur die CPU wurde belastet", AMBER, "warning")
        else:
            result, color, tag = "✓ PASSED", GREEN, "success"
        self.lbl_int_status.config(
            text=f"{result} | Peak: {peak_temp}°C | Ø GPU-Last: {avg_usage:.0f}%", fg=color)
        self.log.append(f"Internal stress: {result} | Peak temp: {peak_temp}°C | "
                        f"Ø GPU-Last: {avg_usage:.0f}%", tag)
        if reason == "" and avg_usage < self.MIN_GPU_LOAD_PCT:
            self.log.append("Für echte GPU-Last: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) "
                            "oder FurMark / 3DMark starten.", "warning")

    def _stop_internal(self):
        self._running_internal = False
        self._run_gen += 1                   # the running thread stops reporting
        self._stop_internal_worker()
        self.btn_int_start.configure(state="normal")
        self.btn_int_stop.configure(state="disabled")
        self.int_prog.set(0)
        self.lbl_int_status.config(text="Stopped (kein Ergebnis).", fg=AMBER)
        self.log.append("Internal stress test stopped by user — no result.", "warning")

    @staticmethod
    def _kill_proc(proc):
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        except Exception:
            pass

    def _stop_internal_worker(self):
        proc, self._worker_proc = self._worker_proc, None
        self._kill_proc(proc)

    # ── FurMark ───────────────────────────────────────────────────────────────

    def _show_furmark(self):
        p = self._furmark_path
        if p:
            v2 = furmark.is_v2(p)
            self.lbl_furmark_path.config(text=f"✓ {furmark.describe(p)}\n{p}", fg=GREEN)
            self.opt_demo.configure(state="normal" if v2 else "disabled")
            self.btn_fur_start.configure(state="normal")
            self.btn_fur_dl.pack_forget()
        else:
            self.lbl_furmark_path.config(text=tr(
                "⚠ Nicht gefunden — FurMark installieren oder den Ordner mit „Suchen …“ wählen "
                "(FurMark 1 und 2 werden erkannt).",
                "⚠ Not found — install FurMark or pick its folder with 'Browse …' "
                "(FurMark 1 and 2 are recognised)."), fg=AMBER)
            self.btn_fur_start.configure(state="disabled")
            self.btn_fur_dl.pack(side="left")

    def _launch_furmark(self):
        if not self._furmark_path:
            messagebox.showerror("FurMark Not Found",
                                 "FurMark.exe not found.\n"
                                 "Install FurMark from geeks3d.com/furmark\n"
                                 "or use Browse to locate it.")
            return
        from core import app_settings
        res = self.v_fur_res.get()
        w, h = res.split("x")
        secs = self.v_fur_dur.get()
        demo = next((k for k, v in furmark.DEMOS.items() if v == self.v_fur_demo.get()), "furmark-gl")
        app_settings.set("furmark_res", res)
        app_settings.set("furmark_seconds", secs)
        app_settings.set("furmark_demo", demo)
        try:
            # FurMark 2 has its own command line (--demo/--width/--max-time)
            proc = subprocess.Popen(furmark.build_args(self._furmark_path, int(w), int(h), secs, demo),
                                    cwd=os.path.dirname(self._furmark_path))
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))
            return
        what = furmark.describe(self._furmark_path)
        self.lbl_fur_status.config(text=f"{what}: {res}, {secs}s — läuft", fg=GREEN)
        self.log.append(f"FurMark launched: {what}, {res}, {secs}s"
                        + (f", {self.v_fur_demo.get()}" if furmark.is_v2(self._furmark_path) else ""),
                        "success")
        self._start_session("FurMark", proc=proc, planned_s=secs, status=self.lbl_fur_status)

    def _browse_furmark(self):
        path = filedialog.askopenfilename(
            title="FurMark wählen (furmark.exe, FurMark_GUI.exe oder FurMark.exe)",
            filetypes=[("Executable", "*.exe")]
        )
        if path:
            self._furmark_path = furmark.remember(path)     # kept after a restart
            self._show_furmark()

    def _open_furmark_dl(self):
        import webbrowser
        webbrowser.open("https://geeks3d.com/furmark/")

    # ── 3DMark ────────────────────────────────────────────────────────────────

    def _show_3dmark(self):
        p = self._3dmark_path
        if p:
            kind = "Steam" if threedmark.is_steam(p) else "Standalone"
            pro = " · Professional (CLI)" if threedmark.cmd_exe(p) else ""
            self.lbl_3dm_path.config(text=f"✓ 3DMark ({kind}{pro})\n{p}", fg=GREEN)
            self.btn_3dm_start.configure(state="normal")
            self.btn_3dm_store.pack_forget()
        else:
            self.lbl_3dm_path.config(text=tr(
                "⚠ Nicht gefunden — über Steam installieren oder 3DMark.exe mit „Suchen …“ wählen.",
                "⚠ Not found — install it via Steam or pick 3DMark.exe with 'Browse …'."), fg=AMBER)
            self.btn_3dm_start.configure(state="disabled")
            self.btn_3dm_store.pack(side="left")

    def _launch_3dmark(self):
        if not self._3dmark_path:
            return
        ok, msg = threedmark.launch(self._3dmark_path)
        self.lbl_3dm_status.config(text=msg, fg=GREEN if ok else ERR)
        self.log.append(f"3DMark: {msg}", "success" if ok else "error")
        if ok:
            self._start_session("3DMark", prefix=threedmark.PROCESS_PREFIXES, status=self.lbl_3dm_status)

    def _browse_3dmark(self):
        path = filedialog.askopenfilename(title="3DMark.exe wählen", filetypes=[("3DMark", "*.exe")])
        if path:
            self._3dmark_path = threedmark.remember(path)
            self._show_3dmark()

    def _open_3dmark_store(self):
        import webbrowser
        webbrowser.open(threedmark.STORE_URL)

    # ── Recording during an external test ─────────────────────────────────────

    def _start_session(self, name, proc=None, prefix=None, planned_s=None, status=None):
        """Record the GPU while FurMark/3DMark runs; the summary names peak
        temperature, clocks, power and driver resets (TDR = unstable)."""
        self._ext_gen += 1
        gen = self._ext_gen
        s = {"name": name, "t0": time.time(), "peak": 0, "clk": [], "pwr": 0.0, "use": [],
             "tdr": False, "status": status, "stopped": False}
        self._ext = s
        self.btn_rec_stop.pack(side="right")
        self.lbl_session.config(text=f"● {name}: {tr('Aufzeichnung läuft …', 'recording …')}", fg=AMBER)

        def run():
            try:
                from core.crash_recovery import CrashRecovery
                cr = CrashRecovery(os.path.join(BASE, "logs"))
            except Exception:
                cr = None
            seen = proc is not None
            gone = 0
            last_tdr = time.time()
            while self._alive and gen == self._ext_gen and not s["stopped"]:
                el = time.time() - s["t0"]
                if proc is not None:
                    running = proc.poll() is None
                else:
                    running = bool(threedmark.running_processes()) if prefix else False
                if running:
                    seen, gone = True, 0
                elif seen:
                    gone += 1
                    if gone >= 3:
                        break
                elif el > 180:
                    s["never"] = True
                    break
                try:
                    st = self.monitor.read()
                    if running:
                        s["peak"] = max(s["peak"], st.temp)
                        s["pwr"] = max(s["pwr"], float(st.gpu_power_w or 0))
                        if (st.gpu_usage or 0) >= 50:          # only under real load
                            s["clk"].append(float(st.core_mhz or 0))
                            s["use"].append(float(st.gpu_usage or 0))
                except Exception:
                    pass
                if cr is not None and time.time() - last_tdr >= 10:
                    last_tdr = time.time()
                    try:
                        if cr.check_tdr_since(seconds_back=15):
                            s["tdr"] = True
                    except Exception:
                        pass
                time.sleep(1.0)
            if gen == self._ext_gen and self._alive:
                self.after(0, lambda: self._session_done(s))

        threading.Thread(target=run, daemon=True).start()

    def _stop_session(self):
        if self._ext is not None:
            self._ext["stopped"] = True

    def _session_done(self, s):
        self.btn_rec_stop.pack_forget()
        self._ext = None
        dur = int(time.time() - s["t0"])
        if s.get("never"):
            text, col, tag = (f"{s['name']}: kein Testprozess gesehen — nichts aufgezeichnet.",
                              DIM, "warning")
        else:
            clk = s["clk"]
            if clk:
                load = (f"Ø Takt {sum(clk) / len(clk):.0f} MHz (min {min(clk):.0f}), "
                        f"Ø Last {sum(s['use']) / len(s['use']):.0f} %")
            else:
                load = "keine GPU-Last über 50 % gemessen"
            text = (f"{s['name']}: {dur} s aufgezeichnet — Peak {s['peak']} °C, max. {s['pwr']:.0f} W, "
                    f"{load}")
            if s["tdr"]:
                text += " — ⚠ Treiber-Reset (TDR) erkannt: nicht stabil!"
                col, tag = ERR, "error"
            else:
                text += " — kein Treiber-Reset"
                col, tag = (GREEN, "success") if clk else (AMBER, "warning")
        self.lbl_session.config(text=text, fg=col)
        self.log.append(text, tag)
        st = s.get("status")
        if st is not None:
            try:
                st.config(text=tr("Beendet — Ergebnis unten", "Finished — result below"), fg=col)
            except tk.TclError:
                pass

    # ── Passive monitor ───────────────────────────────────────────────────────

    def _start_passive_monitor(self):
        def loop():
            while self._alive:
                if self._visible or self._running_internal or self._ext is not None:
                    try:
                        s = self.monitor.read()
                        self.after(0, self._update_live, s)
                    except Exception:
                        pass
                time.sleep(1.5)
        threading.Thread(target=loop, daemon=True).start()

    def _update_live(self, s):
        tc = ERR if s.temp >= 85 else AMBER if s.temp >= 75 else ACC
        self._stiles["temp"].config( text=str(s.temp), fg=tc)
        self._stiles["volt"].config( text=f"{s.voltage_mv:.0f}" if s.voltage_mv > 0 else "--")
        self._stiles["core"].config( text=f"{s.core_mhz:.0f}")
        self._stiles["power"].config(text=f"{s.gpu_power_w:.0f}")
        self._stiles["usage"].config(text=f"{s.gpu_usage:.0f}")
        self.bar_temp.set( s.temp,        s.temp_limit_c or 100)
        self.bar_power.set(s.gpu_power_w, s.power_max_w or 400)
