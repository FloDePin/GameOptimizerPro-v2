"""GameOptimizerPro Stress Test page — internal stress worker, FurMark 1/2 and
3DMark launchers, and a recording of the GPU values while an external test runs
(peak temperature, clocks, power, driver resets)."""

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import furmark, gpu_watchdog, threedmark
from core.nvtune_core import GpuMonitor
from ui.components import (Card, GaugeBar, LogView, NumberField, Page, ResponsiveGrid, WrapLabel, swap_button,
                           button, tile)
from ui.theme import (ACC, AMBER, BORDER, CARD_BG, CYAN, DIM, ERR, F_MONO, F_S, F_XS, GREEN,
                      INPUT_BG, MUTED, PURPLE, TEXT, TEXT2, VIOLET, icon_image, on_color, tr)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOLUTIONS = ["1280x720", "1920x1080", "2560x1440", "3440x1440", "3840x2160"]


class StressTab(Page):
    # A result only counts as a GPU stability test if the GPU was really loaded.
    MIN_GPU_LOAD_PCT = 70.0

    def __init__(self, parent, monitor: GpuMonitor, ab=None, pm=None, tuner=None, **kw):
        super().__init__(parent, tr("Stresstest", "Stress test"),
                         tr("Stabilität prüfen — intern, mit FurMark oder 3DMark. Bei externen Tests "
                            "zeichnet GameOptimizerPro Temperatur, Takt, Leistung und Treiber-Resets auf.",
                            "Check stability — internally, with FurMark or 3DMark. During external "
                            "tests GameOptimizerPro records temperature, clocks, power and driver resets."),
                         color=AMBER, **kw)
        self.monitor = monitor
        self.ab, self.pm, self.tuner = ab, pm, tuner     # hardness test: make the profile safer
        self._hard = None                # running hardness test: its stop event
        self._hard_q: queue.Queue = queue.Queue()
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
        self.end_gpu_tests()

    def end_gpu_tests(self, wait_s: float = 15.0):
        """The app ends: a running hardness test or internal test ends with it. Without this the
        hardness test's FurMark windows went on for up to 3 min after the app had gone, and the
        run was never recorded as own GPU load (the watchdog could take its driver events for a
        game's). No Tk here — it is also called from the exit path's thread."""
        stop, th = self._hard, getattr(self, "_hard_thread", None)
        if stop is not None:
            stop.set()                       # the test asks its loads to end, records its own load
            if th is not None:
                th.join(wait_s)
        if self._running_internal:
            self._running_internal = False
            self._run_gen += 1               # the running thread stops reporting
            gpu_watchdog.record_own_load(getattr(self, "_int_t0", time.time()), time.time())
            self._stop_internal_worker()

    def _detect_furmark(self):
        # saved choice, a FurMark folder next to the app, install locations
        return furmark.detect()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        from core import app_settings
        b = self.body
        self._build_hard(b)
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
        # Start and Stop share one place: while the test runs the button turns into "Stop test"
        self.btn_int_start = button(row, tr("Test starten", "Start test"), self._start_internal,
                                    kind="primary", color=ACC, height=32, width=140,
                                    image=icon_image("play", on_color(ACC), 14), compound="left")
        self.btn_int_stop = button(row, tr("Test stoppen", "Stop test"), self._stop_internal, kind="danger",
                                   height=32, width=140, image=icon_image("stop", "#ffffff", 13),
                                   compound="left")
        swap_button(self.btn_int_start, self.btn_int_stop)
        self.int_prog = tk.DoubleVar()
        self._int_bar = ctk.CTkProgressBar(ic.body, height=6, corner_radius=3, progress_color=ACC)
        self._int_bar.set(0)
        self._int_bar.pack(fill="x", pady=(4, 4))
        self.int_prog.trace_add("write", lambda *_: self._int_bar.set(
            max(0.0, min(1.0, self.int_prog.get() / 100))))
        self.lbl_int_status = WrapLabel(ic.body, text=tr("Bereit", "Idle"), font=F_MONO, fg=DIM, bg=CARD_BG)
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
        self._msaa_labels = {tr("aus", "off"): 0, "2×": 2, "4×": 4, tr("8× (volle Last)", "8× (full load)"): 8}
        saved_msaa = int(app_settings.get("furmark_msaa", 8))
        self.v_fur_msaa = tk.StringVar(value=next((k for k, v in self._msaa_labels.items() if v == saved_msaa),
                                                  tr("8× (volle Last)", "8× (full load)")))
        self.opt_msaa = self._option(fc.body, tr("Kantenglättung", "Anti-aliasing"), self.v_fur_msaa,
                                     list(self._msaa_labels))
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
        self.lbl_fur_status = WrapLabel(fc.body, text=tr("Bereit", "Idle"), font=F_MONO, fg=DIM, bg=CARD_BG)
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
        self.lbl_3dm_status = WrapLabel(tc.body, text=tr("Bereit", "Idle"), font=F_MONO, fg=DIM, bg=CARD_BG)
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

    # ── Hardness test (round 33) ──────────────────────────────────────────────
    # Several loads at once, like a game that is recorded or streamed — see
    # core/hardness_test.py. It tests the profile applied now and changes nothing;
    # after a failure it offers to lower the curve points involved.

    HARD_MINUTES = (10, 20, 45)

    def _build_hard(self, b):
        hc = Card(b, tr("Härtetest — wie Spielen mit Aufnahme / Stream",
                        "Hardness test — like gaming while recording / streaming"), accent=VIOLET)
        hc.pack(fill="x", padx=10, pady=(0, 14))
        WrapLabel(hc.body, text=tr(
            "Mehrere Lasten gleichzeitig, wie ein Spiel, das aufgenommen oder gestreamt wird: 3D (FurMark, "
            "leicht und schwer, OpenGL und Vulkan), der Video-Encoder (NVENC, 60 Bilder/s), Rechen- und "
            "Speicherlast — in Phasen mit kurzen Pausen dazwischen, damit die Karte auch aus dem Leerlauf "
            "hochschalten muss. Jedes Ergebnis wird geprüft. Getestet wird das gerade aktive Profil; nach "
            "einem Fehler kann GameOptimizerPro genau die betroffenen Kurvenpunkte entschärfen.",
            "Several loads at once, like a game that is recorded or streamed: 3D (FurMark, light and heavy, "
            "OpenGL and Vulkan), the video encoder (NVENC, 60 frames/s), compute and memory load — in phases "
            "with short pauses between them, so the card also has to clock up from idle. Every result is "
            "checked. It tests the profile active now; after a failure GameOptimizerPro can make exactly "
            "the curve points involved safer."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(0, 8))
        self.lbl_hard_profile = WrapLabel(hc.body, text="", font=F_S, fg=TEXT2, bg=CARD_BG)
        self.lbl_hard_profile.pack(fill="x", pady=(0, 6))
        self._mins = {tr(f"{m} min", f"{m} min"): m for m in self.HARD_MINUTES}
        self.v_hard_min = tk.StringVar(value=next(iter(k for k, v in self._mins.items() if v == 20)))
        self._option(hc.body, tr("Dauer", "Duration"), self.v_hard_min, list(self._mins))
        row = tk.Frame(hc.body, bg=CARD_BG)
        row.pack(fill="x", pady=(8, 6))
        self.btn_hard_start = button(row, tr("Härtetest starten", "Start hardness test"), self._start_hard,
                                     kind="primary", color=VIOLET, height=32, width=190,
                                     image=icon_image("play", on_color(VIOLET), 14), compound="left")
        self.btn_hard_stop = button(row, tr("Härtetest stoppen", "Stop hardness test"), self._stop_hard,
                                    kind="danger", height=32, width=190,
                                    image=icon_image("stop", "#ffffff", 13), compound="left")
        swap_button(self.btn_hard_start, self.btn_hard_stop)
        self._hard_bar = ctk.CTkProgressBar(hc.body, height=6, corner_radius=3, progress_color=VIOLET)
        self._hard_bar.set(0)
        self._hard_bar.pack(fill="x", pady=(4, 4))
        self.lbl_hard_status = WrapLabel(hc.body, text=tr("Bereit", "Ready"), font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_hard_status.pack(fill="x")
        self._show_hard_profile()

    def _applied_profile(self):
        cr = getattr(self.tuner, "cr", None)
        try:
            p = cr.load_last_applied() if cr else None
        except Exception:
            p = None
        return p if p and not str(p.get("name", "")).startswith("__") else None

    def _show_hard_profile(self):
        p = self._applied_profile()
        self.lbl_hard_profile.config(text=tr(f"Geprüft wird: „{p['name']}“ (zuletzt übernommen)",
                                             f"Tested: '{p['name']}' (last applied)") if p else tr(
            "Kein übernommenes Profil — getestet werden die aktuellen Werte der Karte.",
            "No applied profile — the card's current settings are tested."))

    def _busy_text(self):
        if self.tuner is not None and getattr(self.tuner, "is_running", False):
            return tr("Der GPU-Tuner läuft gerade.", "The GPU tuner is running.")
        if self._running_internal:
            return tr("Der interne Test läuft gerade.", "The internal test is running.")
        if self._ext is not None:
            return tr("Eine FurMark-/3DMark-Aufzeichnung läuft gerade.", "A FurMark / 3DMark recording is running.")
        if self._hard is not None:
            return tr("Der Härtetest läuft gerade.", "The hardness test is running.")
        return ""

    def _start_hard(self):
        busy = self._busy_text()
        if busy:
            messagebox.showinfo("GameOptimizerPro", busy, parent=self.winfo_toplevel())
            return
        try:
            import cupy  # noqa: F401 — the loads need CUDA
        except Exception:
            messagebox.showerror("GameOptimizerPro", tr(
                "Für den Härtetest fehlt CUDA für Python: pip install \"cupy-cuda12x[ctk]\"",
                "The hardness test needs CUDA for Python: pip install \"cupy-cuda12x[ctk]\""),
                parent=self.winfo_toplevel())
            return
        from core.hardness_test import HardnessTest
        minutes = self._mins.get(self.v_hard_min.get(), 20)
        profile = self._applied_profile()
        fm_note = (tr("FurMark-Fenster gehen auf (ohne den Fokus zu nehmen) — nicht schließen, sonst bricht der "
                      "Test ab. ", "FurMark windows open (without taking the focus) — don't close them or the "
                      "test stops. ") if self._furmark_path else
                   tr("FurMark nicht gefunden — die 3D-Last übernimmt eine Rechenlast. ",
                      "FurMark not found — a compute load stands in for the 3D load. "))
        if not messagebox.askyesno(tr("Härtetest starten", "Start hardness test"), tr(
                f"{minutes} min Härtetest auf „{profile['name'] if profile else 'den aktuellen Werten'}“.\n\n"
                f"{fm_note}Während des Tests nicht spielen. Ein Browser oder Video daneben ist in Ordnung.\n\n"
                f"Start?",
                f"{minutes} min hardness test on '{profile['name'] if profile else 'the current settings'}'.\n\n"
                f"{fm_note}Don't play during the test. A browser or a video next to it is fine.\n\nStart?"),
                parent=self.winfo_toplevel()):
            return
        self._show_hard_profile()
        stop = threading.Event()
        self._hard = stop
        q = self._hard_q
        try:
            gpu = self.monitor.read().name or ""
        except Exception:
            gpu = ""
        test = HardnessTest(self.monitor.read, os.path.join(BASE, "logs"), minutes=minutes,
                            furmark_path=self._furmark_path, max_temp=min(int(self.v_max_temp.get()), 88),
                            profile=profile, stop_event=stop, gpu_name=gpu,
                            on_progress=lambda p, t: q.put(("prog", p, t)),
                            on_log=lambda s, tag: q.put(("log", s, tag)))
        self.btn_hard_stop.configure(state="normal")
        swap_button(self.btn_hard_stop, self.btn_hard_start)
        self.btn_int_start.configure(state="disabled")
        self.btn_fur_start.configure(state="disabled")
        self.lbl_hard_status.config(text=tr("Startet …", "Starting …"), fg=VIOLET)

        def run():
            from core.power_state import keep_awake
            keep_awake(True)
            try:
                res = test.run()
            except Exception as e:                # never leave the buttons dead
                res = e
            finally:
                keep_awake(False)
            q.put(("done", res))
        self._hard_thread = threading.Thread(target=run, daemon=True)
        self._hard_thread.start()
        self.after(300, self._hard_poll)

    def _stop_hard(self):
        if self._hard is not None:
            self._hard.set()
            self.btn_hard_stop.configure(state="disabled")
            self.lbl_hard_status.config(text=tr("Wird beendet …", "Stopping …"), fg=AMBER)

    def _hard_poll(self):
        done = None
        try:
            while True:
                item = self._hard_q.get_nowait()
                if item[0] == "prog":
                    self._hard_bar.set(item[1] / 100)
                    self.lbl_hard_status.config(text=item[2], fg=VIOLET)
                elif item[0] == "log":
                    tag = {"dim": "info"}.get(item[2], item[2])
                    if item[2] != "dim":               # the 10-s value lines stay in the log file
                        self.log.append(item[1], tag)
                else:
                    done = item[1]
        except queue.Empty:
            pass
        if done is None:
            try:
                self.after(300, self._hard_poll)
            except (tk.TclError, RuntimeError):
                pass
            return
        self._hard = None
        self._hard_bar.set(0)
        self.btn_hard_start.configure(state="normal")
        swap_button(self.btn_hard_start, self.btn_hard_stop)
        self.btn_int_start.configure(state="normal")
        if self._furmark_path:
            self.btn_fur_start.configure(state="normal")
        self._hard_done(done)

    def _hard_done(self, res):
        if isinstance(res, Exception):
            self.lbl_hard_status.config(text=tr(f"Fehler: {res}", f"Error: {res}"), fg=ERR)
            return
        if res.passed:
            text, col = tr(f"✓ Bestanden — {res.seconds / 60:.0f} min, max. {res.max_mhz:.0f} MHz / "
                           f"{res.max_mv:.0f} mV, {res.peak_temp} °C",
                           f"✓ Passed — {res.seconds / 60:.0f} min, max {res.max_mhz:.0f} MHz / "
                           f"{res.max_mv:.0f} mV, {res.peak_temp} °C"), GREEN
        elif res.aborted or res.kind == "temp":
            text, col = f"■ {res.reason}", AMBER
        else:
            text, col = tr(f"✗ Nicht bestanden ({res.phase}): {res.reason}",
                           f"✗ Failed ({res.phase}): {res.reason}"), ERR
        self.lbl_hard_status.config(text=text, fg=col)
        if res.unstable:
            self._offer_safer(res)

    def _offer_safer(self, res):
        """The same choice as the GPU watchdog: only the points involved, the whole profile,
        or nothing."""
        from ui.components import ChoiceDialog
        p = self._applied_profile()
        if not p or self.pm is None or self.ab is None:
            return
        pts = ", ".join(str(a) for a in res.anchors)
        opts = []
        if res.anchors:
            opts.append(("point", tr(f"Gezielt entschärfen: {pts} mV −30 MHz (empfohlen)",
                                     f"Make safer at these points: {pts} mV −30 MHz (recommended)")))
        opts += [("safer", tr("Ganzes Profil entschärfen (Kurve −30 MHz, Speicher −200 MHz)",
                              "Make the whole profile safer (curve −30 MHz, memory −200 MHz)")),
                 ("keep", tr("Nichts ändern", "Change nothing"))]
        pt = res.point or {}
        where = (tr(f"\n\nKurz davor lief die Karte bei etwa {pt['mv']:.0f} mV / {pt['mhz']:.0f} MHz.",
                    f"\n\nJust before, the card ran at about {pt['mv']:.0f} mV / {pt['mhz']:.0f} MHz.")
                 if pt.get("mv") else "")
        choice = ChoiceDialog(self.winfo_toplevel(), tr("Härtetest", "Hardness test"), tr(
            f"„{p['name']}“ hat den Härtetest nicht bestanden: {res.reason} (Phase „{res.phase}“).{where}\n\n"
            f"Eine entschärfte Kopie wird angelegt und angewendet (Afterburner-Platz 2) — danach den "
            f"Härtetest am besten noch einmal laufen lassen.",
            f"'{p['name']}' failed the hardness test: {res.reason} (phase '{res.phase}').{where}\n\n"
            f"A safer copy is created and applied (Afterburner slot 2) — then best run the hardness test "
            f"again."), opts, current=opts[0][0], ok_text="OK", accent=VIOLET).show()
        if choice in (None, "keep"):
            return
        from core.nvtune_core import TuneProfile
        if self.pm.load(p["name"]) is None:
            self.pm.save(TuneProfile.from_dict(p))         # e.g. manual offsets: no saved profile
        new = self.pm.derate_points(p["name"], res.anchors) if choice == "point" else None
        new = new or self.pm.derate(p["name"])
        if new is None:
            return
        box: dict = {}
        th = threading.Thread(target=lambda: box.update(r=self.ab.write_and_apply(2, new)), daemon=True)
        th.start()

        def wait():
            if th.is_alive():
                self.after(400, wait)
                return
            ok, err = box.get("r", (False, "?"))
            if ok:
                cr = getattr(self.tuner, "cr", None)
                if cr is not None:
                    cr.save_last_applied(new.to_dict())
                self._show_hard_profile()
                self.log.append(tr(f"„{new.name}“ ist jetzt aktiv (Afterburner-Platz 2).",
                                   f"'{new.name}' is active now (Afterburner slot 2)."), "success")
            else:
                messagebox.showerror("GameOptimizerPro", str(err), parent=self.winfo_toplevel())
        self.after(400, wait)

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

    def _gpu_taken(self) -> bool:
        """The GPU tuner or the hardness test has the GPU: a second load would spoil both
        (said in a box) -> True."""
        why = ""
        if self.tuner is not None and getattr(self.tuner, "is_running", False):
            why = tr("Der GPU-Tuner läuft gerade — erst abwarten oder abbrechen.",
                     "The GPU tuner is running — wait for it or abort it first.")
        elif self._hard is not None:
            why = tr("Der Härtetest läuft gerade — erst abwarten oder stoppen.",
                     "The hardness test is running — wait for it or stop it first.")
        if why:
            messagebox.showinfo("GameOptimizerPro", why, parent=self.winfo_toplevel())
        return bool(why)

    def _start_internal(self):
        if self._running_internal or self._gpu_taken():
            return
        self._running_internal = True
        self._run_gen += 1
        gen = self._run_gen
        self.btn_int_stop.configure(state="normal")
        swap_button(self.btn_int_stop, self.btn_int_start)
        self._int_t0 = time.time()           # own GPU load: the GPU watchdog leaves it out
        gpu_watchdog.own_load_started(self._int_t0)
        self.log.append(tr("Interner Stresstest gestartet.", "Internal stress test started."), "header")
        self.log.append(tr(f"Dauer: {self.v_int_dur.get()} s | Max. Temperatur: {self.v_max_temp.get()} °C",
                           f"Duration: {self.v_int_dur.get()} s | Max temp: {self.v_max_temp.get()} °C"))

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
        self.lbl_int_status.config(text=tr(f"Läuft: {elapsed}/{dur} s", f"Running: {elapsed}/{dur} s"), fg=ACC)

    def _int_done(self, reason, peak_temp, avg_usage, max_t):
        gpu_watchdog.record_own_load(getattr(self, "_int_t0", time.time()), time.time())
        self._running_internal = False
        self.btn_int_start.configure(state="normal")
        swap_button(self.btn_int_start, self.btn_int_stop)
        self.int_prog.set(0)
        if reason == "temp":
            result, color, tag = tr(f"✗ NICHT BESTANDEN (Temperaturgrenze {max_t} °C erreicht)",
                                    f"✗ FAILED (temperature limit {max_t} °C reached)"), ERR, "error"
        elif reason == "errors":
            result, color, tag = tr("✗ NICHT BESTANDEN (Rechenfehler unter Last — GPU instabil)",
                                    "✗ FAILED (computation error under load — GPU unstable)"), ERR, "error"
        elif reason == "worker":
            result, color, tag = tr("✗ NICHT BESTANDEN (Last-Prozess abgestürzt)",
                                    "✗ FAILED (stress worker crashed)"), ERR, "error"
        elif reason == "tdr":
            result, color, tag = tr("✗ NICHT BESTANDEN (GPU-Treiber-Timeout / TDR)",
                                    "✗ FAILED (GPU driver timeout / TDR)"), ERR, "error"
        elif avg_usage < self.MIN_GPU_LOAD_PCT:
            # "Passed" would be meaningless: without 'cupy' the worker only
            # burns the CPU, the GPU idles and nothing about its stability is shown.
            result, color, tag = (tr(f"⚠ KEIN GPU-STRESS (Ø {avg_usage:.0f} % GPU-Last) — nur die CPU wurde "
                                     f"belastet", f"⚠ NO GPU STRESS (avg {avg_usage:.0f} % GPU load) — only the CPU "
                                     f"was loaded"), AMBER, "warning")
        else:
            result, color, tag = tr("✓ BESTANDEN", "✓ PASSED"), GREEN, "success"
        self.lbl_int_status.config(
            text=tr(f"{result} | Spitze: {peak_temp} °C | Ø GPU-Last: {avg_usage:.0f} %",
                    f"{result} | Peak: {peak_temp} °C | avg GPU load: {avg_usage:.0f} %"), fg=color)
        self.log.append(tr(f"Interner Test: {result} | Spitze: {peak_temp} °C | Ø GPU-Last: {avg_usage:.0f} %",
                           f"Internal test: {result} | Peak temp: {peak_temp} °C | avg GPU load: "
                           f"{avg_usage:.0f} %"), tag)
        if reason == "" and avg_usage < self.MIN_GPU_LOAD_PCT:
            self.log.append(tr("Für echte GPU-Last: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) "
                            "oder FurMark / 3DMark starten.", "For real GPU load: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) or start FurMark / 3DMark."), "warning")

    def _stop_internal(self):
        gpu_watchdog.record_own_load(getattr(self, "_int_t0", time.time()), time.time())
        self._running_internal = False
        self._run_gen += 1                   # the running thread stops reporting
        self._stop_internal_worker()
        self.btn_int_start.configure(state="normal")
        swap_button(self.btn_int_start, self.btn_int_stop)
        self.int_prog.set(0)
        self.lbl_int_status.config(text=tr("Stopped (kein Ergebnis).", "Stopped (no result)."), fg=AMBER)
        self.log.append(tr("Interner Test abgebrochen — kein Ergebnis.",
                           "Internal stress test stopped by user — no result."), "warning")

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
            self.opt_msaa.configure(state="normal" if v2 else "disabled")
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
        if self._gpu_taken():
            return
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
        msaa = self._msaa_labels.get(self.v_fur_msaa.get(), 8)
        app_settings.set("furmark_res", res)
        app_settings.set("furmark_seconds", secs)
        app_settings.set("furmark_demo", demo)
        app_settings.set("furmark_msaa", msaa)
        try:
            # FurMark 2 has its own command line (--demo/--width/--max-time/--msaa).
            # furmark.exe is a console program: no console window, and its own
            # stats (FPS, max GPU usage) are read when it ends.
            proc = subprocess.Popen(furmark.build_args(self._furmark_path, int(w), int(h), secs, demo, msaa),
                                    cwd=os.path.dirname(self._furmark_path),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, errors="replace",
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))
            return
        what = furmark.describe(self._furmark_path)
        self.lbl_fur_status.config(text=tr(f"{what}: {res}, {secs}s — läuft", f"{what}: {res}, {secs}s — running"), fg=GREEN)
        self.log.append(tr(f"FurMark gestartet: {what}, {res}, {secs} s", f"FurMark launched: {what}, {res}, {secs} s")
                        + (f", {self.v_fur_demo.get()}" if furmark.is_v2(self._furmark_path) else ""),
                        "success")
        self._start_session("FurMark", proc=proc, planned_s=secs, status=self.lbl_fur_status)

    def _browse_furmark(self):
        path = filedialog.askopenfilename(
            title=tr("FurMark wählen (furmark.exe, FurMark_GUI.exe oder FurMark.exe)", "Choose FurMark (furmark.exe, FurMark_GUI.exe or FurMark.exe)"),
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
        if not self._3dmark_path or self._gpu_taken():
            return
        ok, msg = threedmark.launch(self._3dmark_path)
        self.lbl_3dm_status.config(text=msg, fg=GREEN if ok else ERR)
        self.log.append(f"3DMark: {msg}", "success" if ok else "error")
        if ok:
            self._start_session("3DMark", prefix=threedmark.PROCESS_PREFIXES, status=self.lbl_3dm_status)

    def _browse_3dmark(self):
        path = filedialog.askopenfilename(title=tr("3DMark.exe wählen", "Choose 3DMark.exe"), filetypes=[("3DMark", "*.exe")])
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
             "use_all": [], "tdr": False, "status": status, "stopped": False, "out": []}
        gpu_watchdog.own_load_started(s["t0"])
        pipe = getattr(proc, "stdout", None)
        if pipe is not None:           # drain continuously: a full pipe would block FurMark
            threading.Thread(target=lambda: s["out"].append(pipe.read() or ""), daemon=True).start()
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
                        s["use_all"].append(float(st.gpu_usage or 0))
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
        gpu_watchdog.record_own_load(s["t0"], time.time())   # FurMark / 3DMark from the app
        self.btn_rec_stop.pack_forget()
        self._ext = None
        dur = int(time.time() - s["t0"])
        if s.get("never"):
            text, col, tag = (tr(f"{s['name']}: kein Testprozess gesehen — nichts aufgezeichnet.",
                                 f"{s['name']}: no test process seen — nothing recorded."),
                              DIM, "warning")
        else:
            clk = s["clk"]
            if clk:
                load = (tr(f"Ø Takt {sum(clk) / len(clk):.0f} MHz (min {min(clk):.0f}), "
                        f"Ø Last {sum(s['use']) / len(s['use']):.0f} %", f"avg clock {sum(clk) / len(clk):.0f} MHz (min {min(clk):.0f}), avg load {sum(s['use']) / len(s['use']):.0f} %"))
            else:
                load = tr("keine GPU-Last über 50 % gemessen", "no GPU load above 50 % measured")
            text = tr(f"{s['name']}: {dur} s aufgezeichnet — Peak {s['peak']} °C, max. {s['pwr']:.0f} W, "
                      f"{load}",
                      f"{s['name']}: {dur} s recorded — peak {s['peak']} °C, max. {s['pwr']:.0f} W, {load}")
            stats = furmark.parse_stats("".join(s.get("out") or [])) if s.get("out") else {}
            if stats.get("fps_avg"):
                text += tr(f" — FurMark: Ø {stats['fps_avg']} FPS (min {stats.get('fps_min', '?')}), "
                           f"max. GPU-Last {stats.get('max_usage', '?')} %",
                           f" — FurMark: avg {stats['fps_avg']} FPS (min {stats.get('fps_min', '?')}), "
                           f"max GPU load {stats.get('max_usage', '?')} %")
            use_all = s.get("use_all") or []
            avg_all = sum(use_all) / len(use_all) if use_all else 0.0
            low = (stats.get("max_usage", 100) < 90) or (use_all and avg_all < 85)
            if s["tdr"]:
                text += tr(" — ⚠ Treiber-Reset (TDR) erkannt: nicht stabil!", " — ⚠ driver reset (TDR) detected: not stable!")
                col, tag = ERR, "error"
            else:
                text += tr(" — kein Treiber-Reset", " — no driver reset")
                col, tag = (GREEN, "success") if clk and not low else (AMBER, "warning")
            if low and not s["tdr"]:
                text += (tr(f"\n⚠ Die GPU war nicht voll ausgelastet (Ø {avg_all:.0f} %) — dann ist das kein "
                         "Stresstest. Häufige Ursache: ein FPS-Limit oder erzwungenes VSync/G-Sync "
                         "(NVIDIA App → Grafik → Max. Bildfrequenz / Vertikale Synchronisierung). "
                         "Abhilfe: Kantenglättung „8×“ wählen — damit arbeitet die GPU unter dem Limit "
                         "voll — oder das Limit für den Test ausschalten.", f"\n⚠ The GPU was not fully loaded (avg {avg_all:.0f} %) — then this is no stress test. A common cause: an FPS cap or forced VSync/G-Sync (NVIDIA App → Graphics → Max frame rate / Vertical sync). Fix: choose anti-aliasing \u201c8×\u201d — the GPU then works fully under the cap — or turn the cap off for the test."))
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
