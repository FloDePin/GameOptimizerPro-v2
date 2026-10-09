"""
GameOptimizerPro Auto-Tuner — two modes:
Rundum-Tuner (TuneMode.CURVE, the default): own V/F curve measured point by
         point, the curve cap chosen by FurMark benchmark for the goal (max /
         balanced / efficiency), 5-min FurMark + compute-checked final test, report
Quick (TuneMode.OC_UV): Stage 1 max stable core offset, Stage 2 lowest power
         limit with <= 3 % loss, Stage 4 memory (optional), compute-checked final test
Both: crash recovery, TDR detection, per-step flag writing, only a configuration
that passed the final test is saved.
(Round 15: the separate "overclock only" / "undervolt only" modes and the
never-shown FULL / V/F-only / memory-only modes are gone — the Rundum goals
max / efficiency cover the first two, and do it per voltage point.)
"""

import time, threading, os, sys, subprocess, logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime
from pathlib import Path

from core import curve_tune as CT
from core.nvtune_core import GpuMonitor, AfterburnerController, TuneProfile, ProfileManager


class TunerApplyError(RuntimeError):
    """A tuning step could not be applied — the tune must stop, not test it."""


class TuneMode(Enum):
    OC_UV     = "oc_uv"      # Quick: core offset (Stage 1) + power limit (Stage 2) + memory
    CURVE     = "curve"      # Rundum-Tuner: own curve per voltage point + goal + benchmark


class TunerState(Enum):
    IDLE       = auto()
    BASELINE   = auto()
    STAGE1     = auto()    # Core offset OC
    STAGE2     = auto()    # Power limit UV (indirect)
    STAGE4     = auto()    # Memory OC
    CURVE      = auto()    # Rundum-Tuner: measuring the voltage points
    BENCH      = auto()    # Rundum-Tuner: FurMark benchmark (stock / candidates)
    FINAL_TEST = auto()
    BACKOFF    = auto()
    SAVING     = auto()
    DONE       = auto()
    ERROR      = auto()
    ABORTED    = auto()


@dataclass
class StressResult:
    passed:         bool  = False
    max_temp:       float = 0.0
    avg_temp:       float = 0.0
    min_voltage_mv: float = 0.0
    max_voltage_mv: float = 0.0
    avg_voltage_mv: float = 0.0
    throttle_hit:   bool  = False  # THERMAL / hardware slowdown (not the power limit)
    crash_detected: bool  = False
    tdr_detected:   bool  = False
    compute_error:  bool  = False  # the worker saw a wrong result (gpu-burn check)
    abort_reason:   str   = ""
    avg_core_mhz:   float = 0.0
    core_clocks:    list  = field(default_factory=list)
    avg_gpu_usage:  float = 0.0    # measured GPU load during the run (%)
    aborted:        bool  = False  # stopped by the user, NOT a completed test
    avg_rate_tflops: float = 0.0   # work done per second ("gemm" mode, needs cupy)
    avg_bw_gbs:     float = 0.0    # memory bandwidth ("mem" mode, needs cupy)
    avg_mem_mhz:    float = 0.0
    max_core_mhz:   float = 0.0    # highest clock seen (boost phases: top of the curve)
    power_capped_pct: float = 0.0  # share of samples at the power limit (normal)
    steady_voltage_mv: float = 0.0  # median voltage after the ramp-up (the point the GPU ran)
    avg_power_w:    float = 0.0    # board power after the ramp-up
    throttle_note:  str   = ""     # which slowdown (NVML reason names) made throttle_hit
    last_voltage_mv: float = 0.0   # voltage just before the end / the failure (loaded)
    hang_detected:  bool  = False  # the load stopped delivering results (GPU hung)

    def perf(self, ref: "StressResult") -> float:
        """Performance relative to `ref` (1.0 = same). Work rate when both runs
        measured it, else the average core clock."""
        if self.avg_rate_tflops > 0 and ref.avg_rate_tflops > 0:
            return self.avg_rate_tflops / ref.avg_rate_tflops
        if self.avg_core_mhz > 0 and ref.avg_core_mhz > 0:
            return self.avg_core_mhz / ref.avg_core_mhz
        return 1.0


@dataclass
class TunerConfig:
    mode:            TuneMode = TuneMode.OC_UV
    core_step_mhz:   int = 15
    core_max_mhz:    int = 300
    core_start_mhz:  int = 0
    power_step_pct:  int = 5
    power_min_pct:   int = 65
    power_start_pct: int = 100
    max_temp_c:      int = 85
    baseline_s:      int = 30
    step_test_s:     int = 45
    final_test_s:    int = 120
    ab_slot:         int = 2
    mem_offset_mhz:  int = 0
    # Memory stage of both modes (GPU tab: "Speicher mit übertakten") — the
    # whole card under load (_mem_stage_full), up to mem_oc_max_mhz.
    mem_stage:        bool = False
    mem_oc_max_mhz:  int  = 1000
    # Stage 2: lowest power limit that costs at most this much performance
    # under full load (RTX 40: ~70-80 % PL costs only a few % in games).
    power_max_loss_pct: float = 3.0
    # Rundum-Tuner (TuneMode.CURVE) — see core/curve_tune.py. The points are
    # tested with step_test_s each, the compute-checked final run is final_test_s.
    goal:                str = "balanced"   # "max" | "balanced" | "efficiency"
    curve_step_mhz:      int = 15      # search step per voltage point, halved on a failure ...
    curve_min_step_mhz:  int = 5       # ... down to this precision
    curve_coarse_step_mhz: int = 30    # first point without a known start value
    curve_down_mhz:      int = 30      # start value failed: down in these steps
    curve_safety_mhz:    int = 45      # taken off every point (workload, hours of play, cold boost) ...
    curve_safety_top_mhz: int = 60     # ... the top points, where games boost (curve_tune.apply_margins)
    curve_reset_extra_mhz: int = 30    # ... more where the search caused a driver reset / a hang
    # Round 16 game test after the final test (both modes, _game_test): what games do
    # that the steady tests don't — a cool-down (a cold card runs its curve higher),
    # load changes at the top clock, then the boost point steady. Every result checked.
    game_test:           bool = True
    game_cool_s:         int = 60
    game_transient_s:    int = 300
    game_boost_s:        int = 240
    # Quick mode: taken off the core offset found in Stage 1 (a uniform offset also
    # moves the top of the curve, where games boost — the Rundum top margin).
    core_safety_mhz:     int = 60
    # Memory: taken off the highest step that passed (0 = round 13: one step below a
    # failure, the top kept). A bandwidth drop of more than mem_edc_drop_pct to the
    # step before counts as the edge: GDDR6X retries bad transfers (EDC) before it
    # shows errors.
    mem_safety_mhz:      int = 200
    mem_edc_drop_pct:    float = 2.0
    curve_anchor_step_mv: int = 25     # measured points: every 25 mV from the top (GPU tab: 25/50) ...
    curve_min_mv:        int = 850     # ... down to this voltage
    curve_cap_step_mv:   int = 25      # benchmarked curve caps: every 25 mV below the top
    curve_check_s:       int = 30      # FurMark on the new curve (memory +0) before the memory stage
    mem_curve_start_mhz: int = 500     # memory stage (whole card under load): first offset ...
    mem_curve_step_mhz:  int = 100     # ... then these steps up to mem_oc_max_mhz; also the margin
    crash_pause_s:       int = 20      # after a crash: give the driver time before the next run
    curve_prior_mhz:     int = 0       # start offset of the first point (e.g. last tune's core offset)
    curve_probe_s:       int = 20      # stock boost-load run: highest voltage the card reaches
    bench_s:             int = 60      # FurMark benchmark per candidate (and the stock run)
    final_bench_s:       int = 300     # FurMark part of the final test (5 min)
    furmark_path:        str = ""      # FurMark 2 console exe; empty = internal benchmark
    bench_width:         int = 1920
    bench_height:        int = 1080
    bench_msaa:          int = 8       # 8x: GPU-bound even under a driver FPS cap / VSync


class StressTester:
    RAMP_S = 3            # ignore the worker's start-up for averages
    EXIT_COMPUTE_ERROR = 3  # _stress_worker.py: wrong result / CUDA error under load
    # A slowdown only counts when it lasts: NVIDIA sets "SW thermal" for about a
    # second whenever a load ends or Afterburner applies a profile (seen live at
    # 46-53 °C) — counted at once, that failed a good step as "throttling".
    THROTTLE_SAMPLES = 3
    # A load that stops delivering results is a hung GPU. A game can end with
    # D3D12 "device hung" on a profile that passed every test; a hang in our
    # own load used to count as passed until the driver reset killed the worker
    # (TdrDelay — 10 s on the test PC, if it fires at all).
    HANG_S = 8.0
    # After the worker died, wait this long before the step's last look at the event
    # log: the driver's error entries come right with the failure (live: 24 x
    # nvlddmkm 13 two seconds before the compute error was reported).
    EVENT_SETTLE_S = 2.0

    def __init__(self, monitor: GpuMonitor, crash_recovery=None,
                 stop_event: Optional[threading.Event] = None):
        self.monitor = monitor
        self.cr      = crash_recovery
        self.stop_event = stop_event   # set by AutoTuner.abort() -> end the step NOW
        self._proc: Optional[subprocess.Popen] = None
        self._metrics: dict = {"RATE": [], "BW": [], "ERR": [], "LAST": 0.0}
        self._t0 = 0.0

    def _worker_path(self):
        # Worker lives at project root, not in core/
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "_stress_worker.py"
        )

    def start(self, mode: str = "gemm"):
        wp = self._worker_path()
        self._metrics = {"RATE": [], "BW": [], "ERR": [], "LAST": 0.0}
        self._t0 = time.time()
        if os.path.exists(wp):
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self._proc = subprocess.Popen(
                    [sys.executable, wp, str(os.getpid()), mode],  # GUI PID → dead-man switch
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=flags
                )
                threading.Thread(target=self._read_worker,
                                 args=(self._proc, self._metrics, self._t0),
                                 daemon=True).start()
            except Exception:
                pass

    @staticmethod
    def _read_worker(proc, metrics: dict, t0: float):
        """Collect the worker's "RATE x" / "BW x" / "ERR n" lines. Always drains
        the pipe, so the worker can never block on a full stdout buffer."""
        try:
            for line in proc.stdout:
                metrics["LAST"] = time.time()          # any output: the load is alive
                parts = line.split()
                if len(parts) < 2 or parts[0] not in metrics:
                    continue
                if parts[0] == "ERR":
                    metrics["ERR"].append(parts[1])
                    continue
                try:
                    metrics[parts[0]].append((time.time() - t0, float(parts[1])))
                except ValueError:
                    pass
        except Exception:
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    def _avg(self, key: str) -> float:
        vals = [v for t, v in self._metrics.get(key, []) if t >= self.RAMP_S]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def _tdr_since(self, since: float) -> bool:
        """Driver reset / NVIDIA GPU error in the event log since `since`
        (time.time()); never raises."""
        try:
            return bool(self.cr.check_tdr_since(seconds_back=int(time.time() - since) + 2))
        except Exception:
            return False

    @staticmethod
    def _mark_tdr(result: "StressResult"):
        result.tdr_detected   = True
        result.crash_detected = True
        result.abort_reason   = CT.T("Treiber-Reset (TDR) erkannt", "TDR (GPU driver timeout) detected")

    def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                pass
            self._proc = None

    def run(
        self,
        duration_s: int,
        max_temp: int,
        on_tick: Optional[Callable] = None,
        mode: str = "gemm",
    ) -> StressResult:
        result = StressResult()
        temps, voltages, clocks, usages, mem_clocks = [], [], [], [], []
        steady_volts, powers = [], []
        recent_v: list = []                 # last few voltages (the loaded state before a crash)
        samples = capped = prot_run = 0

        self.start(mode)
        start = time.time()
        # The event log is read up to here (driver resets). 5 s before the step:
        # the step's own start-up belongs to it, as before.
        checked_to = start - 5

        while True:
            # Abort must end the step immediately. Before, the step (and the
            # stress worker's 100 % load) ran on for up to a minute after
            # "Abort", and its result was then acted on.
            if self.stop_event is not None and self.stop_event.is_set():
                self.stop()
                result.aborted = True
                result.passed = False
                result.abort_reason = CT.T("Abgebrochen", "Aborted")
                return result

            elapsed = int(time.time() - start)
            if elapsed >= duration_s:
                break

            stats = self.monitor.read()
            temps.append(stats.temp)
            if stats.voltage_mv > 0:
                voltages.append(stats.voltage_mv)
                recent_v = (recent_v + [stats.voltage_mv])[-3:]
                result.last_voltage_mv = max(recent_v)
            if elapsed >= self.RAMP_S:            # skip the worker's ramp-up
                clocks.append(stats.core_mhz)
                mem_clocks.append(float(getattr(stats, "mem_mhz", 0.0) or 0.0))
                usages.append(float(stats.gpu_usage or 0.0))
                samples += 1
                capped += bool(getattr(stats, "power_capped", False))
                if stats.voltage_mv > 0:
                    steady_volts.append(stats.voltage_mv)
                pw = float(getattr(stats, "gpu_power_w", 0.0) or 0.0)
                if pw > 0:
                    powers.append(pw)

            if on_tick:
                try:
                    on_tick(elapsed, duration_s, stats)
                except Exception:
                    pass

            if stats.temp >= max_temp:
                self.stop()
                result.abort_reason = CT.T(f"Temp {stats.temp}°C ≥ Grenze {max_temp}°C",
                                           f"Temp {stats.temp}°C >= limit {max_temp}°C")
                result.max_temp = stats.temp
                result.passed   = False
                return result

            # Only thermal / hardware slowdowns count. Running into the power
            # limit is normal GPU Boost behaviour under full load — counting it
            # (as before, with mislabelled bits) failed OC steps for no reason and
            # made the power-limit stage unable to lower anything. And only a
            # lasting one after the ramp-up (THROTTLE_SAMPLES).
            if elapsed >= self.RAMP_S and getattr(stats, "throttle_protective", False):
                prot_run += 1
                if prot_run >= self.THROTTLE_SAMPLES and not result.throttle_hit:
                    result.throttle_hit = True
                    result.throttle_note = str(getattr(stats, "throttle", "") or "")
            else:
                prot_run = 0

            # Worker gone = GPU instability (exit 3: it saw a wrong result)
            if self._proc and self._proc.poll() is not None:
                result.crash_detected = True
                if self._proc.returncode == self.EXIT_COMPUTE_ERROR or self._metrics["ERR"]:
                    result.compute_error = True
                    result.abort_reason = CT.T("Rechenfehler unter Last (GPU instabil)",
                                               "computation error under load (GPU unstable)")
                else:
                    result.abort_reason = CT.T("Last-Prozess abgestürzt (GPU instabil)",
                                               "stress worker crashed (GPU unstable)")
                break

            # The load stopped delivering results: the GPU hangs.
            quiet_since = self._metrics.get("LAST") or 0.0
            if self._proc and quiet_since and time.time() - quiet_since >= self.HANG_S:
                result.crash_detected = result.hang_detected = True
                quiet = time.time() - quiet_since
                result.abort_reason = CT.T(f"GPU hängt — seit {quiet:.0f} s keine Ergebnisse der Last",
                                           f"GPU hung — no results from the load for {quiet:.0f} s")
                break

            # Driver reset (event log) every 10 s, each look from where the last
            # one ended. It used to look only at "elapsed % 10 == 0": a look takes
            # a second or two itself, so later ones were skipped now and then,
            # and a reset in a step's last seconds was never looked for in that
            # step — the next step got the blame (or nobody did).
            if self.cr and time.time() - checked_to >= 15:
                now = time.time()
                hit = self._tdr_since(checked_to)
                checked_to = now
                if hit:
                    self._mark_tdr(result)
                    break

            time.sleep(1.0)

        self.stop()
        # The step's last seconds (after the last look) — a step only passes
        # when nothing happened up to its very end. Also when the worker died:
        # live (round 17, 1025 mV, +194 MHz) a compute error came with 24 GPU
        # errors in the event log (nvlddmkm 13) — a
        # driver-level failure that earns the point the extra margin
        # (curve_reset_extra_mhz). The look was skipped then, so it never counted.
        if self.cr and not result.tdr_detected:
            if result.crash_detected:
                time.sleep(self.EVENT_SETTLE_S)
            if self._tdr_since(checked_to):
                if result.crash_detected:
                    result.tdr_detected = True
                    result.abort_reason = (result.abort_reason or "") + CT.T(
                        " + GPU-Fehler im Ereignisprotokoll", " + GPU error in the event log")
                else:
                    self._mark_tdr(result)

        result.max_temp     = max(temps) if temps else 0
        result.avg_temp     = round(sum(temps) / len(temps), 1) if temps else 0
        result.avg_core_mhz = round(sum(clocks) / len(clocks), 1) if clocks else 0
        result.avg_gpu_usage = round(sum(usages) / len(usages), 1) if usages else 0.0
        result.avg_mem_mhz  = round(sum(mem_clocks) / len(mem_clocks), 1) if mem_clocks else 0
        result.max_core_mhz = max(clocks) if clocks else 0
        result.power_capped_pct = round(100.0 * capped / samples, 1) if samples else 0.0
        result.avg_rate_tflops = self._avg("RATE")
        result.avg_bw_gbs   = self._avg("BW")
        if steady_volts:
            sv = sorted(steady_volts)
            result.steady_voltage_mv = sv[len(sv) // 2]
        result.avg_power_w  = round(sum(powers) / len(powers), 1) if powers else 0.0
        if voltages:
            result.min_voltage_mv = min(voltages)
            result.max_voltage_mv = max(voltages)
            result.avg_voltage_mv = round(sum(voltages) / len(voltages), 1)

        result.passed = (
            not result.crash_detected
            and not result.tdr_detected
            and result.max_temp < max_temp
        )
        return result


class AutoTuner:
    def __init__(
        self,
        monitor:  GpuMonitor,
        ab:       AfterburnerController,
        pm:       ProfileManager,
        config:   TunerConfig,
        log_dir:  str = "logs",
        crash_recovery=None
    ):
        self.monitor = monitor
        self.ab      = ab
        self.pm      = pm
        self.config  = config
        self.cr      = crash_recovery

        self.state        = TunerState.IDLE
        self._stop        = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.best_profile: Optional[TuneProfile] = None

        self._cb_state:    Optional[Callable] = None
        self._cb_log:      Optional[Callable] = None
        self._cb_progress: Optional[Callable] = None
        self._cb_tick:     Optional[Callable] = None
        self._last_tick = 0.0             # when the GPU page last got live values
        self._last_pct = 0                # last progress value (for status-only texts)

        # Serializes every Afterburner/NVML write. abort() takes it too, so no
        # tuning write can land AFTER the reset (the old race re-applied an OC).
        self._ab_lock = threading.Lock()

        # One log FILE PER TUNE RUN (opened in _run_safe). It used to be created
        # here, i.e. once per app start: every launch left an empty tune_*.log,
        # and all runs of a session were merged into one Tune-History entry.
        self._log_dir = log_dir
        self._run_handler: Optional[logging.Handler] = None
        self.logger = logging.getLogger(f"gop.tuner.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False   # keep tune logs out of the tweak log

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _open_run_log(self):
        try:
            Path(self._log_dir).mkdir(parents=True, exist_ok=True)
            logfile = os.path.join(
                self._log_dir, f"tune_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            fh = logging.FileHandler(logfile, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(fh)
            self._run_handler = fh
        except Exception:
            self._run_handler = None

    def _close_run_log(self):
        h, self._run_handler = self._run_handler, None
        if h is not None:
            try:
                self.logger.removeHandler(h)
                h.close()
            except Exception:
                pass

    def on_state(self,    cb): self._cb_state    = cb
    def on_log(self,      cb): self._cb_log      = cb
    def on_progress(self, cb): self._cb_progress = cb
    def on_tick(self,     cb): self._cb_tick     = cb

    def _set_state(self, s):
        # Once aborted, the worker thread must not overwrite ABORTED (it used to
        # end on BACKOFF, which the GPU tab treats as "still running" — Start
        # stayed greyed out for good).
        if (self.state == TunerState.ABORTED and self._stop.is_set()
                and s != TunerState.ABORTED):
            return
        self.state = s
        if self._cb_state:
            try:
                self._cb_state(s)
            except Exception:
                pass

    def _log(self, msg, lvl="info"):
        getattr(self.logger, lvl)(msg)
        if self._cb_log:
            self._cb_log(msg, lvl)

    def _progress(self, pct, msg):
        if pct >= 0:
            self._last_pct = pct
        if self._cb_progress:
            self._cb_progress(pct, msg)

    # The GPU page's tiles and graph only got values from inside a measured step.
    # Between steps (Afterburner restart, FurMark starting, waiting for FurMark to
    # end) nothing came for up to ~20 s while FurMark visibly ran — the values
    # stood still during the memory test. While a tune runs,
    # _live_loop fills such gaps: no tick for LIVE_GAP_S -> read and send one.
    LIVE_GAP_S = 1.5

    def _tick(self, s):
        self._last_tick = time.monotonic()
        if self._cb_tick:
            try:
                self._cb_tick(s)
            except Exception:
                pass

    def _live_loop(self, done: threading.Event):
        while not done.wait(0.5):
            if self._cb_tick is None or time.monotonic() - self._last_tick < self.LIVE_GAP_S:
                continue
            try:
                s = self.monitor.read()
            except Exception:
                continue
            if not done.is_set():
                self._tick(s)

    def _known_good(self) -> TuneProfile:
        """What Afterburner applies at BOOT while a tune runs: the profile the
        user had applied before it (crash recovery's "last applied"), else stock —
        never a step under test. Live (round 17) Afterburner's own [Startup] held
        a step of the Quick tune afterwards (+119 / +0 / 100 %) for days of boots;
        a crash mid-tune could have booted into a failing step."""
        try:
            d = self.cr.load_last_applied() if self.cr else None
            if d and not str(d.get("name", "")).startswith("__"):
                return TuneProfile.from_dict(d)
        except Exception:
            pass
        return TuneProfile(name="__stock__")

    def _boot(self) -> TuneProfile:
        if getattr(self, "_boot_profile", None) is None:
            self._boot_profile = self._known_good()
        return self._boot_profile

    def _persist(self, profile: TuneProfile):
        """The saved profile becomes what the PC boots with (Afterburner's
        [Startup]) — the steps never did. Nothing is written after an abort."""
        with self._ab_lock:
            if self._stop.is_set() or not getattr(self.ab, "available", False):
                return
            self._boot_profile = profile
            try:
                ok, err = self.ab.write_and_apply(self.config.ab_slot, profile, startup="same")
            except Exception as e:
                ok, err = False, str(e)
        if not ok:
            self._log(CT.T(f"Boot-Profil in Afterburner nicht gesetzt: {err} — das Profil ist aktiv, "
                           f"beim nächsten Windows-Start lädt Afterburner aber evtl. etwas anderes",
                           f"Boot profile not set in Afterburner: {err} — the profile is active, but "
                           f"at the next Windows start Afterburner may load something else"), "warning")

    def _ab_write(self, p: TuneProfile):
        """Afterburner write + restart, announced on the GPU page: for those
        seconds its monitoring (voltage) is gone on purpose."""
        self._progress(self._last_pct, CT.T("Afterburner übernimmt die Einstellungen (Neustart) …",
                                            "Afterburner applies the settings (restart) …"))
        return self.ab.write_and_apply(self.config.ab_slot, p, startup=self._boot())

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_safe, daemon=True)
        self._thread.start()

    def abort(self):
        """Stop tuning and put the GPU back to stock. Safe to call from any
        thread, including on app exit. Order matters: set the stop flag first,
        then take the write lock — an in-flight write finishes, and every later
        _apply()/_apply_vf() sees the flag and does nothing, so nothing can
        overwrite the reset any more."""
        self._stop.set()
        # Into the run's log file while it is still open (the tuner thread
        # closes it as soon as it sees the stop flag).
        self._log(CT.T("Abbruch angefordert — GPU wird auf Standard zurückgesetzt …",
                       "Abort requested — putting the GPU back to stock …"), "warning")
        with self._ab_lock:
            self._safe_reset()
            if self.cr:
                try:
                    self.cr.clear_tuning_flag()
                except Exception:
                    pass
        self._set_state(TunerState.ABORTED)
        self._log(CT.T("Vom Nutzer abgebrochen — GPU auf Standard zurückgesetzt",
                       "Aborted by user — GPU back to stock"), "warning")

    def _safe_reset(self):
        """Stock offsets + the card's FACTORY power limit. (Caller holds
        _ab_lock.) Used to set the MAXIMUM power limit, which on cards whose
        maximum is above stock raised the limit instead of resetting it."""
        try:
            reset = TuneProfile(
                name="__reset__",
                core_offset_mhz=0,
                mem_offset_mhz=0,
                power_limit_pct=100
            )
            self.ab.write_and_apply(self.config.ab_slot, reset, startup=self._boot())
        except Exception:
            pass
        try:
            watts = self.monitor.power_pct_to_watts(100)
            if watts > 0:
                self.monitor.set_power_limit(watts)
        except Exception:
            pass

    def _reset_locked(self):
        with self._ab_lock:
            self._safe_reset()

    def _apply(self, core=0, mem=0, pwr_pct=100) -> bool:
        """Apply one step. A step that could NOT be applied must never be
        tested: it would run on the previous settings and be saved as "stable"
        (the result used to be ignored) — so a failure raises TunerApplyError,
        which ends the tune with an error and resets to stock."""
        p = TuneProfile(
            name="__tuning__",
            core_offset_mhz=core,
            mem_offset_mhz=mem,
            power_limit_pct=pwr_pct,
        )
        with self._ab_lock:
            if self._stop.is_set():
                return False           # aborted: never write after the reset
            # Write crash flag before applying
            if self.cr:
                self.cr.set_tuning_active(p.to_dict())
            via_ab = self.ab.available
            if via_ab:
                ok, err = self._ab_write(p)
                if not ok:
                    raise TunerApplyError(f"Afterburner: {err}")
            elif core or mem:
                raise TunerApplyError(
                    "MSI Afterburner nicht gefunden — für Core-/Speicher-Offsets nötig")
            # Always set the limit (incl. 100 %): a later 100 % step used to
            # leave a previously reduced limit in place. 100 % = stock. Without
            # Afterburner (power-only undervolt) NVML is the only way it's applied.
            watts = self.monitor.power_pct_to_watts(pwr_pct)
            nv_ok = watts > 0 and self.monitor.set_power_limit(watts)
            if not via_ab and not nv_ok:
                raise TunerApplyError(
                    f"Power-Limit {pwr_pct} % ließ sich per NVML nicht setzen (Admin-Rechte?)")
            return True

    @staticmethod
    def _perf_note(r: StressResult) -> str:
        """E.g. "  41.3 TFLOPS" — only when the worker measured its work rate (cupy)."""
        return f"  {r.avg_rate_tflops:.1f} TFLOPS" if r.avg_rate_tflops > 0 else ""

    @staticmethod
    def _fail_reason(r: StressResult) -> str:
        if r.abort_reason:
            return r.abort_reason
        if r.throttle_hit:
            return (CT.T("Thermische/Hardware-Drosselung", "thermal/hardware slowdown")
                    + (f" ({r.throttle_note})" if getattr(r, "throttle_note", "") else ""))
        return CT.T("Absturz", "Crash") if r.crash_detected else CT.T("Instabil", "Unstable")

    # A failed final test is not the end: take one step back and run the final
    # test again — only a configuration that PASSED it is ever saved.
    FINAL_RETRIES = 4

    # Stage 2: a step that lost more than allowed, but at most this many times the
    # allowed loss, gets a cross-check — the 100 % reference measured again.
    PWR_RECHECK_X = 3

    @staticmethod
    def _final_backoff(cfg: "TunerConfig", r: StressResult, attempt: int,
                       core: int, mem: int, pwr: int):
        """One step back after failed final test number `attempt` (1-based).
        -> (core, mem, pwr, what) or None when nothing is left to take back.
        Thermal failures lower the power limit first; instability (wrong results,
        crash, driver reset) takes back what is most likely at its edge: the core
        offset (found with 45-s steps, right at the edge), alternating with the
        memory offset (errors that slip past GDDR6X's error correction also show
        up as wrong results)."""
        unstable = r.compute_error or r.crash_detected or r.tdr_detected
        thermal = not unstable and (r.throttle_hit or r.max_temp >= cfg.max_temp_c)
        if thermal and pwr - cfg.power_step_pct >= cfg.power_min_pct:
            p2 = pwr - cfg.power_step_pct
            return core, mem, p2, f"Power-Limit {pwr}→{p2} % ({CT.T('Temperatur', 'temperature')})"
        mem_turn = attempt % 2 == 0 and mem > 0
        if core > 0 and not mem_turn:
            c2 = max(0, core - cfg.core_step_mhz)
            return c2, mem, pwr, f"Core +{core}→+{c2} MHz"
        if mem > 0:
            m2 = max(0, mem - cfg.mem_curve_step_mhz)
            return core, m2, pwr, f"{CT.T('Speicher', 'Memory')} +{mem}→+{m2} MHz"
        if core > 0:
            c2 = max(0, core - cfg.core_step_mhz)
            return c2, mem, pwr, f"Core +{core}→+{c2} MHz"
        if pwr < 100:
            p2 = min(100, pwr + cfg.power_step_pct)
            return core, mem, p2, f"Power-Limit {pwr}→{p2} %"
        return None

    def _save_stable(self, core, mem, pwr):
        """Save current values as last-known-stable for crash recovery."""
        if self.cr:
            p = TuneProfile(
                name="__last_stable__",
                core_offset_mhz=core,
                mem_offset_mhz=mem,
                power_limit_pct=pwr
            )
            self.cr.save_last_stable(p.to_dict())

    def _apply_vf(self, core_offset: int, lock_voltage_mv: int,
                  lock_freq_mhz: int, mem: int = 0) -> bool:
        """One point of the curve locked (flat from `lock_voltage_mv` at
        `lock_freq_mhz`) via Afterburner — the Rundum point search."""
        p = TuneProfile(
            name="__vf_tuning__",
            core_offset_mhz=core_offset,
            mem_offset_mhz=mem,
            power_limit_pct=100,           # Power limit irrelevant with V/F curve
            lock_voltage_mv=lock_voltage_mv,
            lock_freq_mhz=lock_freq_mhz,
        )
        with self._ab_lock:
            if self._stop.is_set():
                return False           # aborted: never write after the reset
            if self.cr:
                self.cr.set_tuning_active(p.to_dict())
            if not self.ab.available:
                raise TunerApplyError("MSI Afterburner nicht gefunden — für die V/F-Kurve nötig")
            ok, err = self._ab_write(p)
        if not ok:
            # Same rule as _apply(): an unapplied curve step must not be tested.
            raise TunerApplyError(f"V/F-Kurve: {err}")
        return ok

    def _run_safe(self):
        self._boot_profile = None             # the known-good profile is looked up per run
        self._open_run_log()
        from core.power_state import keep_awake
        keep_awake(True)          # no sleep / screen-off in the middle of a step
        live_done = threading.Event()
        self._last_tick = time.monotonic()
        threading.Thread(target=self._live_loop, args=(live_done,), daemon=True).start()
        try:
            self._run()
        except TunerApplyError as e:
            self._log(CT.T(f"Anwenden fehlgeschlagen — Tune abgebrochen: {e}",
                           f"Applying failed — tune stopped: {e}"), "error")
            self._set_state(TunerState.ERROR)
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
        except Exception as e:
            self._log(CT.T(f"Tuner-Fehler: {e}", f"Tuner exception: {e}"), "error")
            self._set_state(TunerState.ERROR)
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
        finally:
            live_done.set()
            keep_awake(False)
            self._close_run_log()

    # Minimum average GPU load during the baseline for a meaningful test.
    MIN_GPU_LOAD_PCT = 70.0

    def _run(self):
        cfg     = self.config
        mode    = cfg.mode
        stress  = StressTester(self.monitor, self.cr, stop_event=self._stop)
        T = CT.T

        self._log("═══════════════════════════════════════")
        self._log(f"  GameOptimizerPro Auto-Tune [{mode.value.upper().replace('_',' ')}]")
        self._log("═══════════════════════════════════════")
        try:
            self._log(f"GPU: {self.monitor.read().name}")
        except Exception:
            pass

        # ── Baseline ──────────────────────────────────────────────────────────
        self._set_state(TunerState.BASELINE)
        self._progress(5, T("Standard-Messung (Werkseinstellungen) …", "Measuring baseline (stock settings)..."))
        self._apply(0, 0, 100)
        time.sleep(2)

        base = stress.run(
            cfg.baseline_s, cfg.max_temp_c,
            on_tick=lambda e, d, s: (
                self._progress(
                    5 + int(e / d * 10),
                    T("Standard-Messung", "Baseline") + f": {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                ),
                self._tick(s)
            )
        )
        if self._stop.is_set(): return
        if not base.passed:
            self._log(T(f"Standard-Messung FEHLGESCHLAGEN: {base.abort_reason}",
                        f"Baseline FAILED: {base.abort_reason}"), "error")
            self._set_state(TunerState.ERROR)
            if self.cr: self.cr.clear_tuning_flag()
            return

        # A stability test is only meaningful under real GPU load. The internal
        # stress worker loads the GPU only via 'cupy'; without it, it silently
        # burns the CPU instead and every OC/UV step would "pass" on an idle GPU.
        if base.avg_gpu_usage < self.MIN_GPU_LOAD_PCT:
            import importlib.util
            has_cupy = importlib.util.find_spec("cupy") is not None
            why = (T("'cupy' ist nicht installiert — der Stress-Worker belastet dann nur die CPU.",
                     "'cupy' is not installed — the stress worker then loads only the CPU.")
                   if not has_cupy else
                   T("Der Stress-Worker hat die GPU nicht ausgelastet.",
                     "The stress worker did not load the GPU."))
            self._log(T(
                f"Standard-Messung: GPU-Auslastung nur Ø {base.avg_gpu_usage:.0f} % "
                f"(nötig ≥ {self.MIN_GPU_LOAD_PCT:.0f} %). {why} Ein OC/UV-Test ohne "
                f"GPU-Last würde instabile Werte als 'stabil' speichern — Tune abgebrochen.",
                f"Baseline: GPU load only {base.avg_gpu_usage:.0f} % on average "
                f"(needed ≥ {self.MIN_GPU_LOAD_PCT:.0f} %). {why} An OC/UV test without "
                f"GPU load would save unstable values as 'stable' — tune stopped."),
                "error")
            self._log(T("Lösung: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) ODER parallel eine "
                        "GPU-Last starten (z.B. FurMark im Stress-Tab) und den Tune neu starten.",
                        "Fix: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) OR start a GPU load next "
                        "to it (e.g. FurMark in the stress tab) and start the tune again."),
                      "warning")
            self._set_state(TunerState.ERROR)
            self._progress(0, T(f"Abgebrochen: keine GPU-Last (Ø {base.avg_gpu_usage:.0f} %)",
                                f"Stopped: no GPU load ({base.avg_gpu_usage:.0f} % on average)"))
            self._reset_locked()
            if self.cr: self.cr.clear_tuning_flag()
            return

        # "Standard-Messung OK" / "Baseline OK" and "volt=…mV": read by the tune history
        self._log(T(
            f"Standard-Messung OK | temp={base.avg_temp}°C | GPU-Last={base.avg_gpu_usage:.0f}% | "
            f"volt={base.avg_voltage_mv:.0f}mV | clk={base.avg_core_mhz:.0f}MHz"
            f"{self._perf_note(base)} | Power-Limit erreicht {base.power_capped_pct:.0f}% der Zeit",
            f"Baseline OK | temp={base.avg_temp}°C | GPU load={base.avg_gpu_usage:.0f}% | "
            f"volt={base.avg_voltage_mv:.0f}mV | clk={base.avg_core_mhz:.0f}MHz"
            f"{self._perf_note(base)} | power limit reached {base.power_capped_pct:.0f}% of the time"
        ))
        # Baseline is our first "stable" point
        self._save_stable(0, 0, 100)

        if self._stop.is_set(): return

        if mode == TuneMode.CURVE:
            self._run_curve(stress, base)
            return

        # The same short benchmark at stock and at the end (FurMark 2 only): how the
        # profile compares in performance and efficiency (profile comparison page).
        q_stock = None
        self._stock_rate = 0.0             # points per second at stock (plausibility of the end run)
        if cfg.furmark_path:
            q_stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 13, 2)
            if q_stock is None:
                return
            if q_stock.passed:
                self._stock_rate = q_stock.score / max(cfg.bench_s, 1)
                self._log(T(f"  Standard: {q_stock.score:.0f} Punkte, Ø {q_stock.power_w:.0f} W, "
                            f"max. {q_stock.temp_c:.0f} °C (FurMark, Vergleichswert)",
                            f"  Stock: {q_stock.score:.0f} points, avg {q_stock.power_w:.0f} W, "
                            f"max {q_stock.temp_c:.0f} °C (FurMark, the reference)"))
            else:
                self._log(T(f"  Standard-Benchmark ✗ ({q_stock.note}) — kein Vergleich mit Standard",
                            f"  Stock benchmark ✗ ({q_stock.note}) — no comparison with stock"), "warning")

        # ── Stage 1: Core Clock Offset ─────────────────────────────────────────
        best_core = cfg.core_start_mhz
        ref_result = base          # last passing run at (best_core, 100 %) — Stage 2's yardstick

        self._set_state(TunerState.STAGE1)
        self._log(T("Stufe 1: höchster stabiler Takt-Offset (Schrittweite passt sich an) …",
                    "Stage 1: Finding max stable core offset (adaptive stepping)..."))
        self._progress(15, T("Stufe 1: Takt", "Stage 1: Core clock optimization"))

        # Adaptive stepping: on fail, halve step. Stop when step < MIN_STEP_MHZ.
        MIN_STEP_MHZ = 5
        cur_core  = cfg.core_start_mhz
        cur_step  = cfg.core_step_mhz
        step_n    = 0
        # Estimate total steps for progress (assumes ~4 halvings)
        est_steps = max(cfg.core_max_mhz // cfg.core_step_mhz, 1) + 8

        while not self._stop.is_set():
            candidate = cur_core + cur_step
            if candidate > cfg.core_max_mhz:
                self._log(T(f"Stufe 1: Obergrenze +{cfg.core_max_mhz}MHz erreicht",
                            f"Stage 1: Hard limit +{cfg.core_max_mhz}MHz reached"))
                break

            self._apply(candidate, cfg.mem_offset_mhz, 100)
            time.sleep(2)

            sn_cap = step_n
            def _tick1(e, d, s, c=candidate, sn=sn_cap):
                self._progress(
                    15 + int(min(sn / est_steps, 1.0) * 35),
                    T(f"Stufe 1: +{c}MHz (Schritt {cur_step}MHz)", f"Stage 1: +{c}MHz (step {cur_step}MHz)")
                    + f" | {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                )
                self._tick(s)

            result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick1,
                                mode="mixed")
            if self._stop.is_set():   # aborted mid-step: don't act on it
                return
            step_n += 1

            if result.passed and not result.throttle_hit:
                best_core = candidate
                cur_core  = candidate
                ref_result = result
                self._save_stable(best_core, cfg.mem_offset_mhz, 100)
                self._log(T(
                    f"  +{candidate}MHz ✓  Schritt {cur_step}MHz  Ø {result.avg_temp:.1f}°C  "
                    f"{result.avg_voltage_mv:.0f} mV  "
                    f"Takt {result.avg_core_mhz:.0f}/{result.max_core_mhz:.0f} MHz{self._perf_note(result)}",
                    f"  +{candidate}MHz ✓  step={cur_step}MHz  avg={result.avg_temp:.1f}°C  "
                    f"volt={result.avg_voltage_mv:.0f}mV  "
                    f"clk={result.avg_core_mhz:.0f}/{result.max_core_mhz:.0f}MHz{self._perf_note(result)}"))
                # After a success, try to push a little further
                # Step stays the same unless we've been reducing it
            else:
                tdr_note = " [TDR!]" if result.tdr_detected else ""
                reason = self._fail_reason(result)

                # Halve the step and try again from best_core
                new_step = max(MIN_STEP_MHZ, cur_step // 2)
                if new_step < cur_step:
                    self._log(T(
                        f"  +{candidate}MHz ✗{tdr_note}  {reason} — Schritt halbiert: {cur_step}→{new_step}MHz",
                        f"  +{candidate}MHz ✗{tdr_note}  {reason} — halving step: {cur_step}→{new_step}MHz"),
                        "warning")
                    self._set_state(TunerState.BACKOFF)
                    self._apply(best_core, cfg.mem_offset_mhz, 100)
                    time.sleep(1)
                    cur_step = new_step
                    cur_core = best_core   # resume from last stable
                else:
                    # Step already at minimum — we are done
                    self._log(T(
                        f"  +{candidate}MHz ✗{tdr_note}  {reason} — kleinster Schritt ({MIN_STEP_MHZ}MHz), Ende",
                        f"  +{candidate}MHz ✗{tdr_note}  {reason} — at min step ({MIN_STEP_MHZ}MHz), stopping"),
                        "warning")
                    self._set_state(TunerState.BACKOFF)
                    self._apply(best_core, cfg.mem_offset_mhz, 100)
                    time.sleep(1)
                    break

        # "Stufe 1 fertig" / "Stage 1 done" + "+…MHz": read by the tune history
        self._log(T(f"Stufe 1 fertig: bester Takt = +{best_core}MHz (Genauigkeit ±{MIN_STEP_MHZ}MHz)",
                    f"Stage 1 done: best core = +{best_core}MHz (precision ±{MIN_STEP_MHZ}MHz)"))
        if best_core > 0 and cfg.core_safety_mhz > 0:
            safe = max(0, best_core - cfg.core_safety_mhz)
            self._log(CT.T(f"  Sicherheitsabzug: +{best_core} → +{safe} MHz (−{cfg.core_safety_mhz} MHz: "
                           f"Stunden Spielzeit, Lastwechsel, kalte Karte)",
                           f"  Safety margin: +{best_core} → +{safe} MHz (−{cfg.core_safety_mhz} MHz: "
                           f"hours of play, load changes, a cold card)"))
            best_core = safe

        if self._stop.is_set(): return

        # ── Stage 2: Power Limit Reduction ─────────────────────────────────────
        best_pwr = cfg.power_start_pct

        self._set_state(TunerState.STAGE2)
        # A lower power limit is always "stable" — the driver just runs lower
        # clocks. What matters is how much performance it costs, so the stage
        # looks for the lowest limit that stays within power_max_loss_pct of the
        # 100 % run. (It used to count the power limiting itself as a failure,
        # so it could never lower anything.)
        self._log(T(f"Stufe 2: Power-Limit senken — das niedrigste mit ≤ {cfg.power_max_loss_pct:g} % "
                    f"Leistungsverlust (Schrittweite passt sich an) …",
                    f"Stage 2: Power limit reduction — lowest limit with ≤ "
                    f"{cfg.power_max_loss_pct:g} % performance loss (adaptive stepping)..."))
        s2_base    = 50
        MIN_PWR_STEP = 1   # 1% minimum step for power limit
        cur_pwr    = cfg.power_start_pct
        cur_step   = cfg.power_step_pct
        pwr_step_n = 0
        est_pwr_steps = max(
            (cfg.power_start_pct - cfg.power_min_pct) // cfg.power_step_pct, 1) + 5

        self._progress(s2_base, T("Stufe 2: Power-Limit", "Stage 2: Power limit optimization"))

        # Reference at 100 % with the chosen core offset, in the same load the
        # steps use. The baseline ran on a cold card (~2 % slower in the live
        # calibration) and Stage 1 runs the mixed load — comparing against
        # either would have mis-measured the loss.
        self._apply(best_core, cfg.mem_offset_mhz, 100)
        time.sleep(2)
        ref_result = stress.run(cfg.step_test_s, cfg.max_temp_c,
                                on_tick=lambda e, d, s: (
                                    self._progress(s2_base, T(f"Stufe 2: Referenz 100 % {e}/{d}s",
                                                              f"Stage 2: reference 100 % {e}/{d}s")),
                                    self._tick(s)))
        if self._stop.is_set():
            return
        if not ref_result.passed:
            raise TunerApplyError(T(f"Referenzlauf bei 100 % fehlgeschlagen: {self._fail_reason(ref_result)}",
                                    f"reference run at 100 % failed: {self._fail_reason(ref_result)}"))
        self._log(T(f"  Referenz 100 %: Takt {ref_result.avg_core_mhz:.0f} MHz{self._perf_note(ref_result)}",
                    f"  Reference 100 %: clk={ref_result.avg_core_mhz:.0f}MHz{self._perf_note(ref_result)}"))

        while not self._stop.is_set():
            candidate = cur_pwr - cur_step
            if candidate < cfg.power_min_pct:
                self._log(T(f"Stufe 2: Untergrenze {cfg.power_min_pct} % erreicht",
                            f"Stage 2: Min {cfg.power_min_pct}% reached"))
                break

            self._apply(best_core, cfg.mem_offset_mhz, candidate)
            time.sleep(2)

            sn_cap = pwr_step_n
            def _tick2(e, d, s, p=candidate, sn=sn_cap):
                self._progress(
                    s2_base + int(min(sn / est_pwr_steps, 1.0) * 25),
                    T(f"Stufe 2: {p} % (Schritt {cur_step} %)", f"Stage 2: {p}% (step {cur_step}%)")
                    + f" | {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                )
                self._tick(s)

            result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick2)
            if self._stop.is_set():   # aborted mid-step: don't act on it
                return
            pwr_step_n += 1

            loss = (1.0 - result.perf(ref_result)) * 100.0
            if (result.passed and not result.throttle_hit
                    and cfg.power_max_loss_pct < loss <= cfg.power_max_loss_pct * self.PWR_RECHECK_X):
                # Live (RTX 4080, round 16): 95 % measured −3.6 % and, four minutes
                # later, −7.1 % — against a reference from the start of the stage. The
                # card keeps changing under minutes of full load; a loss is judged
                # against a 100 % run measured NOW (one per step, only near the limit).
                self._log(T(f"  {candidate} %: Leistung {-loss:+.1f}% — Gegenprobe: 100 % neu messen",
                            f"  {candidate}%: performance {-loss:+.1f}% — cross-check: measuring 100 % again"))
                self._apply(best_core, cfg.mem_offset_mhz, 100)
                time.sleep(2)
                fresh = stress.run(cfg.step_test_s, cfg.max_temp_c,
                                   on_tick=lambda e, d, s: (
                                       self._progress(s2_base, T(f"Stufe 2: Gegenprobe 100 % {e}/{d}s",
                                                                 f"Stage 2: cross-check 100 % {e}/{d}s")),
                                       self._tick(s)))
                if self._stop.is_set():
                    return
                if fresh.passed and not fresh.throttle_hit:
                    old = ref_result
                    ref_result = fresh
                    loss = (1.0 - result.perf(ref_result)) * 100.0
                    self._log(T(f"  Referenz 100 % jetzt {(fresh.perf(old) - 1) * 100:+.1f}% ggü. vorher"
                                f"{self._perf_note(fresh)} → {candidate} %: Leistung {-loss:+.1f}%",
                                f"  Reference 100 % now {(fresh.perf(old) - 1) * 100:+.1f}% vs before"
                                f"{self._perf_note(fresh)} → {candidate}%: performance {-loss:+.1f}%"))
            if result.passed and not result.throttle_hit and loss <= cfg.power_max_loss_pct:
                best_pwr = candidate
                cur_pwr  = candidate
                self._save_stable(best_core, cfg.mem_offset_mhz, best_pwr)
                self._log(T(
                    f"  {candidate}% ✓  Schritt {cur_step}%  Ø {result.avg_temp:.1f}°C  "
                    f"{result.avg_voltage_mv:.0f} mV  Leistung {-loss:+.1f}%{self._perf_note(result)}",
                    f"  {candidate}% ✓  step={cur_step}%  avg={result.avg_temp:.1f}°C  "
                    f"volt={result.avg_voltage_mv:.0f}mV  performance {-loss:+.1f}%{self._perf_note(result)}"))
            else:
                tdr_note = " [TDR!]" if result.tdr_detected else ""
                reason   = (self._fail_reason(result)
                            if not result.passed or result.throttle_hit else
                            T(f"Leistung {-loss:+.1f}% (erlaubt −{cfg.power_max_loss_pct:g}%)",
                              f"performance {-loss:+.1f}% (allowed −{cfg.power_max_loss_pct:g}%)"))
                new_step = max(MIN_PWR_STEP, cur_step // 2)
                if new_step < cur_step:
                    self._log(T(
                        f"  {candidate}%{tdr_note} ✗  {reason} — Schritt halbiert: {cur_step}→{new_step}%",
                        f"  {candidate}%{tdr_note} ✗  {reason} — halving step: {cur_step}→{new_step}%"),
                        "warning")
                    self._set_state(TunerState.BACKOFF)
                    self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                    time.sleep(1)
                    cur_step = new_step
                    cur_pwr  = best_pwr
                else:
                    self._log(T(
                        f"  {candidate}%{tdr_note} ✗  {reason} — kleinster Schritt ({MIN_PWR_STEP}%), Ende",
                        f"  {candidate}%{tdr_note} ✗  {reason} — at min step ({MIN_PWR_STEP}%), stopping"),
                        "warning")
                    self._set_state(TunerState.BACKOFF)
                    self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                    time.sleep(1)
                    break

        # "Stufe 2 fertig" / "Stage 2 done" + "…%": read by the tune history
        self._log(T(f"Stufe 2 fertig: bestes Power-Limit = {best_pwr}% (Genauigkeit ±{MIN_PWR_STEP}%)",
                    f"Stage 2 done: best power = {best_pwr}% (precision ±{MIN_PWR_STEP}%)"))

        if self._stop.is_set(): return

        # ── Stage 4: Memory Overclock ──────────────────────────────────────────
        best_mem_offset = cfg.mem_offset_mhz  # start from configured value

        if cfg.mem_stage:
            # The whole card under load, as in the Rundum-Tuner. The old stage took the
            # bandwidth peak of a memory-only load: in the live run that was +1500 —
            # green speckles in FurMark and a driver reset.
            got = self._mem_stage_full(stress, lambda m: self._apply(best_core, m, best_pwr),
                                       prog_base=86)
            if got is None:                      # aborted
                return
            best_mem_offset, _note = got
            if best_mem_offset < 0:              # even +0 fails: the core setting is too tight
                return self._curve_fail(_note)
        else:
            self._log(CT.T("Stufe 4 übersprungen (Speicher nicht ausgewählt)",
                           "Stage 4 skipped (memory not ticked)"))

        if self._stop.is_set(): return

        # ── Final Test ─────────────────────────────────────────────────────────
        # Verify the EXACT configuration that will be saved — including the
        # Stage-4 memory OC. If it fails, take one
        # step back and run the final test again (it used to save an UNTESTED
        # "conservative" profile and stop).
        self._set_state(TunerState.FINAL_TEST)
        attempt, retries_used = 1, []
        while True:
            mem_note = f" | Mem+{best_mem_offset}MHz" if best_mem_offset else ""
            tries    = (T(f" | Versuch {attempt}/{self.FINAL_RETRIES + 1}",
                            f" | attempt {attempt}/{self.FINAL_RETRIES + 1}") if attempt > 1 else "")
            # "Endtest: +…MHz | …% Power-Limit | Mem+…MHz" / "Final test: … pwr": read by the tune history
            self._log(T(f"Endtest: +{best_core}MHz | {best_pwr}% Power-Limit{mem_note} | {cfg.final_test_s}s{tries}",
                        f"Final test: +{best_core}MHz | {best_pwr}% pwr{mem_note} | {cfg.final_test_s}s{tries}"))
            self._progress(75, T(f"Endtest: +{best_core}MHz | {best_pwr} %{mem_note} ({cfg.final_test_s}s){tries}",
                                 f"Final verification: +{best_core}MHz | {best_pwr}%{mem_note} "
                                 f"({cfg.final_test_s}s){tries}"))
            self._apply(best_core, best_mem_offset, best_pwr)
            time.sleep(2)

            def _tick_final(e, d, s):
                self._progress(
                    75 + int(e / d * 20),
                    T("Endtest", "Final") + f": {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV | "
                                            f"{s.core_mhz:.0f}MHz"
                )
                self._tick(s)

            final = stress.run(cfg.final_test_s, cfg.max_temp_c, on_tick=_tick_final,
                               mode="mixed")
            if self._stop.is_set():   # aborted mid-step: don't act on it
                return
            if final.passed and cfg.game_test:
                game = self._game_test(stress, 96)
                if game is None:
                    return
                if not game.passed:
                    final = game              # the failed phase decides the step back
            if final.passed:
                break
            back = (self._final_backoff(cfg, final, attempt, best_core, best_mem_offset, best_pwr)
                    if attempt <= self.FINAL_RETRIES else None)
            tdr_note = " [TDR!]" if final.tdr_detected else ""
            if back is None:
                self._log(T(f"  Endtest ✗{tdr_note}  {self._fail_reason(final)} — nichts mehr zurückzunehmen",
                            f"  Final test ✗{tdr_note}  {self._fail_reason(final)} — nothing left to take back"),
                          "warning")
                break
            best_core, best_mem_offset, best_pwr, what = back
            retries_used.append(what)
            self._set_state(TunerState.BACKOFF)
            self._log(T(f"  Endtest ✗{tdr_note}  {self._fail_reason(final)} — zurück: {what} → "
                        f"Endtest wird wiederholt",
                        f"  Final test ✗{tdr_note}  {self._fail_reason(final)} — back: {what} → "
                        f"final test again"), "warning")
            attempt += 1
            self._set_state(TunerState.FINAL_TEST)

        q_after = None
        if final.passed and q_stock is not None and q_stock.passed:
            q_after = self._bench(stress, cfg.bench_s, T("Nachher-Benchmark", "After benchmark"), 98, 1)
            if q_after is None:
                return

        # ── Save ───────────────────────────────────────────────────────────────
        self._set_state(TunerState.SAVING)
        mode_tag = "OC+UV"

        try:
            gpu_name = self.monitor.read().name
        except Exception:
            gpu_name = "Unknown"

        if final.passed:
            score = self._score(final)
            profile = TuneProfile(
                name=f"GOP_{mode_tag}_{datetime.now().strftime('%m%d_%H%M')}",
                core_offset_mhz=best_core,
                power_limit_pct=best_pwr,
                is_stable=True,
                stability_score=score,
                stage1_freq=int(final.avg_core_mhz),
                stage1_voltage=int(final.avg_voltage_mv),
                mem_offset_mhz=best_mem_offset,
                notes=(
                    f"[{mode_tag}] Core+{best_core}MHz | "
                    f"Mem+{best_mem_offset}MHz | "
                    + (T(f"Endtest nach {len(retries_used)} Rücknahme(n) | ",
                           f"final test after {len(retries_used)} step(s) back | ") if retries_used else "") +
                    f"Pwr {best_pwr}% | "
                    f"MaxTemp {final.max_temp:.0f}°C | "
                    f"AvgVolt {final.avg_voltage_mv:.0f}mV | Score {score}/100"
                ),
                created_at=datetime.now().isoformat(),
                gpu_name=gpu_name,
            )
            if q_after is not None and q_after.passed and min(q_after.power_w, q_stock.power_w) > 0:
                from core import profile_score as PS
                profile.bench = PS.bench_record("FurMark", cfg.bench_s, q_after.score, q_after.power_w,
                                                q_stock.score, q_stock.power_w, at=profile.created_at)
                sc = PS.score_of(profile)
                self._log(T(f"Vorher → nachher (FurMark {cfg.bench_s} s): {q_stock.score:.0f} → "
                            f"{q_after.score:.0f} Punkte ({sc['perf_pct']:+.1f} %), {q_stock.power_w:.0f} → "
                            f"{q_after.power_w:.0f} W, Effizienz {sc['eff_pct']:+.1f} %",
                            f"Before → after (FurMark {cfg.bench_s} s): {q_stock.score:.0f} → "
                            f"{q_after.score:.0f} points ({sc['perf_pct']:+.1f} %), {q_stock.power_w:.0f} → "
                            f"{q_after.power_w:.0f} W, efficiency {sc['eff_pct']:+.1f} %"))
            elif q_after is not None:
                self._log(T(f"Nachher-Benchmark ✗ ({q_after.note}) — kein Vergleich mit Standard",
                            f"After benchmark ✗ ({q_after.note}) — no comparison with stock"), "warning")
            self.best_profile = profile
            self.pm.save(profile)
            self._persist(profile)            # what the PC boots with (Afterburner [Startup])
            # Track as last applied for startup loader
            if self.cr:
                self.cr.save_last_applied(profile.to_dict())
            if retries_used:
                self._log(T(f"Endtest bestanden nach {len(retries_used)} Rücknahme(n): ",
                            f"Final test passed after {len(retries_used)} step(s) back: ")
                          + "; ".join(retries_used))
            self._log_summary(profile.name, mode_tag, f"+{best_core}MHz", best_mem_offset, best_pwr,
                              final.avg_voltage_mv, final.max_temp, score)
            self._progress(100, f"✓ {T('Fertig', 'Done')}! [{mode_tag}] +{best_core}MHz | "
                                f"Mem+{best_mem_offset}MHz | Score {score}/100")
        else:
            # Never save something that did not pass: back to stock, say so.
            self._log(T(
                f"Endtest nicht bestanden ({self._fail_reason(final)}), auch nach "
                f"{len(retries_used)} Rücknahme(n) — KEIN Profil gespeichert, GPU auf "
                f"Standard zurückgesetzt. Temperaturen/Kühlung prüfen oder mit kleinerem "
                f"'Takt-Plus max.' bzw. ohne Speicher-Offset erneut tunen.",
                f"Final test failed ({self._fail_reason(final)}), also after "
                f"{len(retries_used)} step(s) back — NO profile saved, GPU back to stock. "
                f"Check temperatures / cooling or tune again with a smaller 'max clock gain' "
                f"or without a memory offset."), "error")
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
            self._progress(100, T("✗ Endtest nicht bestanden — kein Profil gespeichert, GPU auf Standard",
                                  "✗ Final test failed — no profile saved, GPU at stock"))
            self._set_state(TunerState.ERROR)
            return

        # Clean up crash flag — we finished cleanly
        if self.cr:
            self.cr.clear_tuning_flag()

        self._log("═══════════════════════════════════════")
        self._log(T("        Auto-Tune abgeschlossen", "        Auto-Tune Complete"))
        self._log("═══════════════════════════════════════")
        self._set_state(TunerState.DONE)

    def _log_summary(self, name, mode, core, mem, pwr, volt, temp, score):
        """The closing summary of a saved run, in the app's language. The tune
        history reads these lines (core/tune_history.py: both languages)."""
        T = CT.T
        self._log(T("Profil gespeichert: ", "Profile saved: ") + name)
        self._log(T(f"  Modus:            {mode}", f"  Mode:        {mode}"))
        self._log(T(f"  Takt-Offset:      {core}", f"  Core offset:  {core}"))
        self._log(T(f"  Speicher-Offset:  +{mem}MHz", f"  Memory offset:+{mem}MHz"))
        self._log(T(f"  Power-Limit:      {pwr}%", f"  Power limit:  {pwr}%"))
        self._log(T(f"  Ø Spannung:       {volt:.0f}mV", f"  Avg voltage:  {volt:.0f}mV"))
        self._log(T(f"  Max. Temperatur:  {temp:.0f}°C", f"  Max temp:     {temp:.0f}°C"))
        self._log(f"  Score:            {score}/100" if CT.is_de() else f"  Score:        {score}/100")

    # ── Rundum-Tuner (TuneMode.CURVE) ─────────────────────────────────────────

    def _apply_curve(self, anchors, cap_mv: int = 0, mem: int = 0, pwr_pct: int = 100) -> bool:
        """Own V/F curve from the measured points (+ memory offset, power limit)
        via Afterburner. Same rules as _apply(): nothing is written after an
        abort, and a step that could not be applied raises TunerApplyError."""
        p = TuneProfile(name="__curve_tuning__", mem_offset_mhz=int(mem),
                        power_limit_pct=int(pwr_pct),
                        curve_points=[[int(mv), int(f)] for mv, f in anchors],
                        curve_cap_mv=int(cap_mv or 0))
        with self._ab_lock:
            if self._stop.is_set():
                return False
            if self.cr:
                self.cr.set_tuning_active(p.to_dict())
            if not self.ab.available:
                raise TunerApplyError("MSI Afterburner nicht gefunden — für die V/F-Kurve nötig")
            ok, err = self._ab_write(p)
            if not ok:
                raise TunerApplyError(f"V/F-Kurve: {err}")
            watts = self.monitor.power_pct_to_watts(pwr_pct)
            if watts > 0:
                self.monitor.set_power_limit(watts)
            return True

    def _max_power_pct(self) -> int:
        """Highest power limit the card allows, in % of its stock limit."""
        try:
            _cur, _mn, mx = self.monitor.get_power_constraints()
            base = self.monitor.get_default_power_limit()
        except Exception:
            return 100
        if mx > 0 and base > 0:
            return max(100, min(AfterburnerController.POWER_RANGE[1], int(mx / base * 100 + 1e-6)))
        return 100

    def _bench(self, stress: "StressTester", seconds: int, label: str, prog: int,
               prog_span: int = 0, plausible: bool = True) -> Optional["CT.Candidate"]:
        """One benchmark run with the settings applied right now -> Candidate
        (score, average power and clock while loaded, highest temperature,
        voltage right before the end), or None when the tune was aborted.
        FurMark 2's own score when it is set up (cfg.furmark_path), else the
        stress worker's measured work rate (TFLOPS) under full load. Too hot ends
        the run (thermal); FurMark dying, hanging, printing no score or a driver
        reset / GPU error counts as unstable — then the driver gets
        cfg.crash_pause_s to recover. A run that ended far too early or scored
        far below stock is `invalid`: after a crash in the live run FurMark ran
        ~10 of 60 s and printed 398 instead of ~7200 points."""
        cfg = self.config
        c = CT.Candidate("")
        if not cfg.furmark_path:
            def _tick(e, d, s):
                self._progress(prog + int(min(e / max(d, 1), 1.0) * prog_span),
                               f"{label}: {e}/{d}s | {s.temp}°C | {s.gpu_power_w:.0f} W | "
                               f"{s.core_mhz:.0f} MHz")
                self._tick(s)
            r = stress.run(seconds, cfg.max_temp_c, on_tick=_tick, mode="gemm")
            if self._stop.is_set():
                return None
            c.score, c.power_w, c.clock_mhz = r.avg_rate_tflops, r.avg_power_w, r.avg_core_mhz
            c.temp_c, c.power_capped_pct = float(r.max_temp), r.power_capped_pct
            c.last_mv = r.last_voltage_mv
            c.unstable = bool(r.crash_detected or r.tdr_detected or r.compute_error)
            c.thermal = not c.unstable and (r.throttle_hit or r.max_temp >= cfg.max_temp_c)
            c.passed = r.passed and not r.throttle_hit and c.score > 0
            if not c.passed:
                c.note = (self._fail_reason(r) if not r.passed or r.throttle_hit
                          else CT.T("keine Messwerte (cupy fehlt?)", "no readings (cupy missing?)"))
            if c.unstable:
                self._crash_pause()
            return c

        from core import furmark
        ev = threading.Event()
        samples, hot = [], []
        t0 = time.time()

        def tick(el):
            if self._stop.is_set():
                ev.set()
                return
            try:
                s = self.monitor.read()
            except Exception:
                return
            samples.append(s)
            if s.temp >= cfg.max_temp_c:
                hot.append(s.temp)
                ev.set()
            self._progress(prog + int(min(el / max(seconds, 1), 1.0) * prog_span),
                           f"{label}: {el:.0f}/{seconds}s | {s.temp}°C | "
                           f"{s.gpu_power_w:.0f} W | {s.core_mhz:.0f} MHz")
            self._tick(s)

        res = furmark.run_benchmark(cfg.furmark_path, seconds, cfg.bench_width, cfg.bench_height,
                                    cfg.bench_msaa, stop_event=ev, on_tick=tick)
        if self._stop.is_set():
            return None
        loaded = [s for s in samples if (s.gpu_usage or 0) >= 90] or samples
        powers = [s.gpu_power_w for s in loaded if s.gpu_power_w > 0]
        clocks = [s.core_mhz for s in loaded if s.core_mhz > 0]
        volts = [s.voltage_mv for s in samples if (s.voltage_mv or 0) > 0]
        c.score = float(res.get("score") or 0)
        c.power_w = round(sum(powers) / len(powers), 1) if powers else 0.0
        c.clock_mhz = round(sum(clocks) / len(clocks), 1) if clocks else 0.0
        c.temp_c = float(max([s.temp for s in samples] + [res.get("max_temp") or 0]))
        c.last_mv = float(max(volts[-3:])) if volts else 0.0
        c.power_capped_pct = (round(100.0 * sum(bool(getattr(s, "power_capped", False))
                                                for s in loaded) / len(loaded), 1)
                              if loaded else 0.0)
        # Only this run's window: a reset from the step before (an AB restart + a few s
        # earlier) must not be blamed on this benchmark.
        tdr = bool(self.cr and self.cr.check_tdr_since(int(time.time() - t0) + 3))
        if hot:
            c.thermal = True
            c.note = CT.T(f"Temperatur {max(hot)} °C ≥ Limit {cfg.max_temp_c} °C",
                          f"temperature {max(hot)} °C ≥ limit {cfg.max_temp_c} °C")
        elif tdr:
            c.unstable = True
            c.note = CT.T("Treiber-Reset / GPU-Fehler (Ereignisprotokoll)",
                          "driver reset / GPU error (event log)")
        elif not res.get("ok"):
            c.unstable = True
            c.note = res.get("error") or "FurMark"
        c.passed = bool(res.get("ok")) and not hot and not tdr
        if c.passed and plausible:
            ran = (res.get("duration_ms") or 0) / 1000.0 or float(res.get("elapsed_s") or 0)
            stock_rate = getattr(self, "_stock_rate", 0.0)
            if ran and seconds >= 20 and ran < seconds * 0.9:
                c.invalid = True
                c.note = CT.T(f"FurMark lief nur {ran:.0f} von {seconds} s",
                              f"FurMark ran only {ran:.0f} of {seconds} s")
            elif stock_rate and c.score / max(seconds, 1) < stock_rate * 0.5:
                c.invalid = True
                c.note = CT.T(f"nur {c.score:.0f} Punkte — weniger als halb so viel wie Standard",
                              f"only {c.score:.0f} points — less than half of stock")
            if c.invalid:
                c.passed, c.unstable = False, True
        if c.unstable and not c.invalid:
            self._crash_pause()
        return c

    def _crash_pause(self):
        """After a crash the driver needs a moment: right after the live crash
        the next FurMark runs ended early with nonsense scores."""
        pause = int(getattr(self.config, "crash_pause_s", 0) or 0)
        if pause > 0 and not self._stop.is_set():
            self._log(CT.T(f"  Pause {pause} s — der Treiber erholt sich nach dem Absturz",
                           f"  {pause} s pause — the driver recovers from the crash"))
            self._stop.wait(pause)

    def _test_point(self, stress: "StressTester", mv: int, mhz: int, base_mhz: float,
                    label: str, prog: int) -> "CT.PointTest":
        """One search step: the curve flat from `mv` at `mhz` (the GPU can't go
        past that point), then the boost load — light enough to stay below the
        power limit, so the GPU sits exactly on that point — with every result
        checked. Passed only counts when the GPU really ran at the point."""
        cfg = self.config
        self._apply_vf(0, mv, mhz, 0)
        time.sleep(2)
        off = mhz - base_mhz

        def tick(e, d, s):
            self._progress(prog, f"{label}: {mv} mV → {mhz} MHz ({off:+.0f}) | {e}/{d}s | "
                                 f"{s.temp}°C | {s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz")
            self._tick(s)

        r = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=tick, mode="boost")
        if self._stop.is_set():
            return CT.PointTest(False, reason="abgebrochen")
        passed = r.passed and not r.throttle_hit
        reached = True
        if passed:
            # At the point = the median voltage within 2 points of Ada's 5-mV grid.
            # Below it means the power limit pushed the GPU down the curve: the
            # step tested a LOWER point and proves nothing for this one.
            # Both ways: ABOVE it means the live curve put a faster point higher
            # up (seen live: 875 mV under test, the card ran 920 mV).
            if r.steady_voltage_mv > 0:
                reached = abs(r.steady_voltage_mv - mv) <= CT.REACH_TOL_MV
            elif r.max_core_mhz > 0:          # no voltage readings: only this point runs that fast
                reached = r.max_core_mhz >= mhz - 60
        seen = (f"{r.steady_voltage_mv:.0f} mV" if r.steady_voltage_mv > 0 else "? mV")
        if passed and reached:
            self._log(f"    {mhz} MHz ({off:+.0f}) ✓  {seen}, {r.avg_core_mhz:.0f} MHz, "
                      f"{r.avg_temp:.0f}°C{self._perf_note(r)}")
        elif passed:
            self._log(CT.T(f"    {mhz} MHz ({off:+.0f}) — Punkt nicht erreicht (lief bei {seen}, "
                           f"{r.avg_core_mhz:.0f} MHz)",
                           f"    {mhz} MHz ({off:+.0f}) — point not reached (ran at {seen}, "
                           f"{r.avg_core_mhz:.0f} MHz)"), "warning")
        else:
            tdr_note = " [TDR!]" if r.tdr_detected else ""
            self._log(f"    {mhz} MHz ({off:+.0f}) ✗{tdr_note}  {self._fail_reason(r)}", "warning")
            time.sleep(5 if (r.tdr_detected or r.crash_detected) else 1)   # let the driver settle
        return CT.PointTest(passed, reached, r.tdr_detected or r.hang_detected,
                            "" if passed else self._fail_reason(r),
                            r.steady_voltage_mv, r.avg_core_mhz)

    # Rundum-Tuner safety limits (after the first live run, see _mem_stage_full)
    CURVE_CHECK_TRIES  = 3      # curve check: up to 2 step-backs
    CANDIDATE_BACKOFFS = 3      # crashed candidates: up to 3 step-backs

    @staticmethod
    def _invalid_msg(c: "CT.Candidate") -> str:
        return CT.T(f"Benchmark unplausibel ({c.note}) — der Treiber ist nach einem Absturz "
                    f"vermutlich nicht sauber. Kein Profil gespeichert, GPU auf Standard: bitte den "
                    f"PC neu starten und den Tune wiederholen.",
                    f"Implausible benchmark ({c.note}) — the driver is probably not clean after a "
                    f"crash. No profile saved, GPU back to stock: please restart the PC and run "
                    f"the tune again.")

    # The verified copies are the only thing that SEES a memory error (FurMark just
    # draws speckles). Live, with FurMark in the foreground, they ran at 13 GB/s
    # instead of 231 next to it — one compare every ~8 s, a pass proved little.
    # Below this the step's check counts as too weak (see _mem_stage_full).
    MEM_CHECK_MIN_GBS = 50.0

    def _whole_card_run(self, stress: "StressTester", seconds: int, label: str, prog: int):
        """The whole card under load at once: FurMark (8x MSAA — the load whose
        picture got green speckles at memory +1500) and the stress worker's
        verified memory copies. -> (passed, reason, info, weak); passed None =
        aborted; weak = passed, but the copies got too little GPU time for a
        meaningful check. Without FurMark only the verified copies run."""
        cfg = self.config
        T = CT.T
        res: dict = {}
        ev = threading.Event()
        th = None
        t0 = time.time()
        if cfg.furmark_path:
            from core import furmark

            def _fm():
                try:
                    res.update(furmark.run_benchmark(cfg.furmark_path, seconds + 6, cfg.bench_width,
                                                     cfg.bench_height, cfg.bench_msaa,
                                                     stop_event=ev))
                except Exception as e:                  # never leave the worker alone
                    res.update(ok=False, error=str(e))
            th = threading.Thread(target=_fm, daemon=True)
            th.start()
            self._progress(prog, T(f"{label}: FurMark startet …", f"{label}: FurMark starting …"))
            time.sleep(4)                               # FurMark is up before the copies start

        def tick(e, d, s):
            self._progress(prog, f"{label}: {e}/{d}s | {s.temp}°C | {s.gpu_power_w:.0f} W | "
                                 f"{s.mem_mhz:.0f} MHz")
            self._tick(s)

        r = stress.run(seconds, cfg.max_temp_c, on_tick=tick, mode="mem")
        if not r.passed or self._stop.is_set():
            ev.set()                                    # stop FurMark right away
        if th is not None:
            th.join(timeout=seconds + 120)
        if self._stop.is_set():
            return None, "", "", False, 0.0
        tdr = bool(self.cr and self.cr.check_tdr_since(int(time.time() - t0) + 3))
        reason = ""
        if not r.passed:
            reason = self._fail_reason(r)
        elif th is not None and not res.get("ok"):
            reason = "FurMark: " + (res.get("error") or T("Fehler", "error"))
        elif tdr:
            reason = T("Treiber-Reset / GPU-Fehler (Ereignisprotokoll)", "driver reset / GPU error (event log)")
        elif th is not None:
            ran = (res.get("duration_ms") or 0) / 1000.0 or float(res.get("elapsed_s") or 0)
            if ran and ran < seconds * 0.9:
                reason = T(f"FurMark lief nur {ran:.0f} s", f"FurMark ran only {ran:.0f} s")
        info = ((f"{r.avg_bw_gbs:.0f} GB/s, " if r.avg_bw_gbs > 0 else "") + f"{r.max_temp:.0f}°C"
                + (f", FurMark {res.get('fps_avg')} FPS" if res.get("ok") else ""))
        if reason:
            self._crash_pause()
        weak = not reason and 0 < r.avg_bw_gbs < self.MEM_CHECK_MIN_GBS
        return not reason, reason, info, weak, r.avg_bw_gbs

    def _mem_stage_full(self, stress: "StressTester", apply_mem: Callable[[int], object],
                        prog_base: int = 60, prog_span: int = 8):
        """Memory for every mode — the plan after the first
        live run (memory +1500 taken straight from the bandwidth peak gave green
        speckles and a driver reset in FurMark): +500 first, then +100 steps up
        to 'Mem max' (default 1000), each step with the WHOLE card under load
        (_whole_card_run). apply_mem(offset) applies the found core settings
        (the checked curve, or offset / V/F lock / power limit) with that memory
        offset. Result: the highest step that passed — one step lower when a
        failure marked the edge; reaching 'Mem max' without a failure keeps it.
        -> (offset, report line), (-1, error) when even +0 fails, None = aborted."""
        cfg = self.config
        T = CT.T
        step = max(25, int(cfg.mem_curve_step_mhz))
        top = max(0, int(cfg.mem_oc_max_mhz))
        m = max(0, min(int(cfg.mem_curve_start_mhz), top))
        self._set_state(TunerState.STAGE4)
        load = T("FurMark + geprüfte Speicherkopien", "FurMark + verified memory copies") \
            if cfg.furmark_path else T("geprüfte Speicherkopien", "verified memory copies")
        self._log(T(f"Speicher: Start +{m} MHz, {step}er-Schritte bis +{top} MHz, je {cfg.step_test_s} s "
                    f"die ganze Karte unter Last ({load})",
                    f"Memory: start +{m} MHz, {step}-MHz steps up to +{top} MHz, {cfg.step_test_s} s "
                    f"of load on the whole card each ({load})"))
        best, failed_at, n = None, None, 0
        weak_retry, weak_at = True, None
        prev_bw = 0.0
        edc_checked = None                       # the step whose bandwidth drop was measured again
        while True:
            if self._stop.is_set():
                return None
            apply_mem(m)
            time.sleep(2)
            ok, why, info, weak, bw = self._whole_card_run(stress, cfg.step_test_s, f"Mem+{m}MHz",
                                                           prog_base + min(n, prog_span - 1))
            if ok is None:
                return None
            n += 1
            if ok and not weak and prev_bw > 0 and bw > 0 and bw < prev_bw * (1 - cfg.mem_edc_drop_pct / 100):
                # More clock, LESS bandwidth: the memory retries bad transfers (EDC) —
                # the edge, before any error shows. Live (round 16) the bandwidth
                # wandered ±2 % from step to step (+600: 232, +700: 228, +800: 240 GB/s)
                # and +1000 "dropped" 2.0 %: the step is measured once more, and only
                # the better of the two runs counts.
                if edc_checked != m:
                    edc_checked = m
                    self._log(T(f"  Mem+{m}MHz: Bandbreite {prev_bw:.0f} → {bw:.0f} GB/s — Gegenprobe: "
                                f"derselbe Schritt noch einmal",
                                f"  Mem+{m}MHz: bandwidth {prev_bw:.0f} → {bw:.0f} GB/s — cross-check: "
                                f"the same step once more"))
                    first_bw = bw
                    apply_mem(m)
                    time.sleep(2)
                    ok, why, info, weak, bw = self._whole_card_run(stress, cfg.step_test_s, f"Mem+{m}MHz",
                                                                   prog_base + min(n, prog_span - 1))
                    if ok is None:
                        return None
                    bw = max(bw, first_bw)
            if ok and not weak and prev_bw > 0 and bw > 0 and bw < prev_bw * (1 - cfg.mem_edc_drop_pct / 100):
                ok = False
                why = T(f"Bandbreite sinkt ({prev_bw:.0f} → {bw:.0f} GB/s): die Fehlerkorrektur des "
                        f"Speichers wiederholt Übertragungen — die Grenze",
                        f"bandwidth drops ({prev_bw:.0f} → {bw:.0f} GB/s): the memory's error "
                        f"correction retries transfers — the edge")
            if ok and weak:
                # A pass that proves little must not raise the memory: the same step
                # once more (the window in front may change), then stop here.
                self._log(T(f"  Mem+{m}MHz — Prüfung zu schwach ({info}): die geprüften Speicherkopien "
                            f"bekamen neben FurMark kaum GPU-Zeit",
                            f"  Mem+{m}MHz — check too weak ({info}): the verified memory copies got "
                            f"hardly any GPU time next to FurMark"), "warning")
                if weak_retry:
                    weak_retry = False
                    continue
                weak_at = m
                break
            if ok:
                best = m
                if bw > 0 and not weak:
                    prev_bw = bw
                self._log(f"  Mem+{m}MHz ✓  {info}")
                if m >= top or (failed_at is not None and failed_at > m):
                    break                        # the top, or the edge found going down
                m = min(top, m + step)
            else:
                failed_at = m
                self._log(f"  Mem+{m}MHz ✗  {why}", "warning")
                if best is not None or m <= 0:
                    break
                m = max(0, m - step)             # the start value failed: down from there
        margin = max(0, int(cfg.mem_safety_mhz))
        if weak_at is not None:
            result = max(0, best - margin) if best is not None else 0
            line = T(f"Speicher: ab +{weak_at} MHz keine aussagekräftige Prüfung (die Speicherkopien kamen "
                     f"neben FurMark nicht zum Zug) → +{result} MHz übernommen — bei einem neuen Tune das "
                     f"FurMark-Fenster nicht anklicken",
                     f"Memory: no meaningful check from +{weak_at} MHz on (the memory copies got no GPU "
                     f"time next to FurMark) → +{result} MHz used — in a new tune don't click the FurMark "
                     f"window")
            self._log("  " + line, "warning")
            return result, line
        if best is None:
            return -1, T("Speicher: schon +0 MHz hält die Last auf der ganzen Karte nicht — die "
                         "Kern-Einstellung (Kurve/Offset) oder die Kühlung reicht nicht, kein "
                         "Profil gespeichert",
                         "Memory: even +0 MHz fails the whole-card load — the core setting "
                         "(curve / offset) or the cooling isn't enough, no profile saved")
        edge = failed_at is not None and failed_at > best
        if margin:
            result = max(0, best - margin)
        else:                                    # round 13: one step below a failure, the top kept
            result = max(0, best - step) if edge else best
        cut = best - result
        if edge:
            line = T(f"Speicher: +{best} MHz bestanden, +{failed_at} nicht → +{result} MHz übernommen "
                     f"({cut} MHz Sicherheit)",
                     f"Memory: +{best} MHz passed, +{failed_at} did not → +{result} MHz used "
                     f"({cut} MHz safety)")
        else:
            line = T(f"Speicher: bis +{best} MHz („Speicher-Plus max.“) bestanden → +{result} MHz übernommen"
                     + (f" ({cut} MHz Sicherheit)" if cut else ""),
                     f"Memory: passed up to +{best} MHz ('max memory gain') → +{result} MHz used"
                     + (f" ({cut} MHz safety)" if cut else ""))
        self._log("  " + line)
        return result, line

    def _game_test(self, stress: "StressTester", prog: int) -> Optional[StressResult]:
        """Round 16 — what a game does that the steady tests don't. A game can hang
        (D3D12 "device hung") after hours on a profile that passed them all.
        With the settings to be saved applied:
        1) cfg.game_cool_s idle: the card cools down — a cold card runs its curve
           higher (the stock clock at 925 mV read 49 MHz higher cold than in the test);
        2) cfg.game_transient_s of load changes at the top clock (worker "transient");
        3) cfg.game_boost_s at the boost point, steady (worker "boost").
        Every result checked, a hang detected (StressTester.HANG_S).
        -> the failed phase's result, the last one when all passed, None = aborted."""
        cfg = self.config
        T = CT.T
        self._log(T(f"Spiel-Endtest: {cfg.game_cool_s} s abkühlen, {cfg.game_transient_s // 60} min "
                    f"Lastwechsel, {cfg.game_boost_s // 60} min Boost-Punkt",
                    f"Game test: {cfg.game_cool_s} s cool-down, {cfg.game_transient_s // 60} min load "
                    f"changes, {cfg.game_boost_s // 60} min boost point"))
        for i in range(int(cfg.game_cool_s)):
            if self._stop.is_set():
                return None
            if i % 2 == 0:
                try:
                    s = self.monitor.read()
                    self._progress(prog, T(f"Spiel-Endtest: abkühlen {i}/{cfg.game_cool_s}s | {s.temp}°C",
                                           f"Game test: cooling down {i}/{cfg.game_cool_s}s | {s.temp}°C"))
                    self._tick(s)
                except Exception:
                    pass
            time.sleep(1.0)
        last = StressResult(passed=True)
        for mode, secs, name in (("transient", cfg.game_transient_s, T("Lastwechsel", "load changes")),
                                 ("boost", cfg.game_boost_s, T("Boost-Punkt", "boost point"))):
            if secs <= 0:
                continue

            def tick(e, d, s, n=name):
                self._progress(prog, T(f"Spiel-Endtest ({n}): {e}/{d}s | {s.temp}°C | "
                                       f"{s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz",
                                       f"Game test ({n}): {e}/{d}s | {s.temp}°C | "
                                       f"{s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz"))
                self._tick(s)
            last = stress.run(secs, cfg.max_temp_c, on_tick=tick, mode=mode)
            if self._stop.is_set():
                return None
            if not last.passed:
                self._log(T(f"  Spiel-Endtest ✗ ({name}): {self._fail_reason(last)}",
                            f"  Game test ✗ ({name}): {self._fail_reason(last)}"), "warning")
                if last.crash_detected:
                    self._crash_pause()
                return last
            self._log(T(f"  Spiel-Endtest {name} ✓  bis {last.max_core_mhz:.0f} MHz, "
                        f"{last.steady_voltage_mv:.0f} mV, max. {last.max_temp:.0f} °C",
                        f"  Game test {name} ✓  up to {last.max_core_mhz:.0f} MHz, "
                        f"{last.steady_voltage_mv:.0f} mV, max {last.max_temp:.0f} °C"))
        return last

    def _curve_fail(self, msg: str):
        """End a run without a profile (Rundum, or a memory stage where even +0
        fails): log, back to stock, error state."""
        self._log(msg, "error")
        self._reset_locked()
        if self.cr:
            self.cr.clear_tuning_flag()
        self._progress(100, "✗ " + msg.split(" — ")[0])
        self._set_state(TunerState.ERROR)

    def _run_curve(self, stress: "StressTester", base: StressResult):
        """Rundum-Tuner — after the baseline (see _run):
        1. the card's curve (voltage points, stock clocks) from Afterburner's profile
        2. stock under the boost load: the highest voltage the card reaches
        3. stock benchmark — the "before"
        4. per voltage point (top down, every 25 mV — GPU tab: 25/50): the highest stable clock
           (core/curve_tune.search_anchor), minus the safety margin -> own curve
        5. memory stage (optional, as in the Quick mode)
        6. benchmark the curve caps the goal allows, pick per goal
        7. final test: FurMark (5 min) + compute-checked mixed load, one step
           back and again on a failure; only a configuration that passed is saved
        8. save + report"""
        cfg = self.config
        T = CT.T
        de = CT.is_de()
        goal = cfg.goal if cfg.goal in CT.GOALS else "balanced"
        gname = CT.GOAL_TEXT[goal][0 if de else 1]

        # 1) the curve Afterburner applies offsets to
        getter = getattr(self.ab, "base_curve", None)
        curve, src = getter(cfg.ab_slot) if getter else (None, "Afterburner")
        if curve is None:
            raise TunerApplyError(T(f"Rundum-Tuner: {src}", f"All-round tuner: {src}"))
        points = curve.active_points()
        self._log(T(f"Rundum-Tuner — Ziel: {gname}", f"All-round tuner — goal: {gname}"))
        self._log(T(f"  V/F-Kurve aus [{src}]: {len(points)} aktive Punkte, "
                    f"{points[0].voltage_mv:.0f}–{points[-1].voltage_mv:.0f} mV",
                    f"  V/F curve from [{src}]: {len(points)} active points, "
                    f"{points[0].voltage_mv:.0f}–{points[-1].voltage_mv:.0f} mV"))

        # 2) stock under the boost load: the top of the curve the card reaches
        self._set_state(TunerState.CURVE)
        self._progress(15, T("Höchste Spannung unter Boost-Last messen …",
                             "Measuring the highest voltage under boost load …"))
        probe = stress.run(cfg.curve_probe_s, cfg.max_temp_c, mode="boost",
                           on_tick=lambda e, d, s: (
                               self._progress(15, f"Boost-Probe: {e}/{d}s | {s.voltage_mv:.0f} mV | "
                                                  f"{s.core_mhz:.0f} MHz"),
                               self._tick(s)))
        if self._stop.is_set():
            return
        if not probe.passed:
            return self._curve_fail(T(f"Boost-Probe bei Standard fehlgeschlagen ({self._fail_reason(probe)}) "
                                      f"— Kühlung/Treiber prüfen",
                                      f"Boost probe at stock failed ({self._fail_reason(probe)}) "
                                      f"— check cooling / driver"))
        ceiling = probe.steady_voltage_mv
        if ceiling <= 0:
            # No voltage readings: the point whose stock clock matches the boost clock.
            top = probe.max_core_mhz or probe.avg_core_mhz
            fit = [p for p in points if p.base_mhz >= top - 7]
            ceiling = (fit[0].voltage_mv if fit else points[-1].voltage_mv)
            self._log(T(f"  Keine Spannungswerte (Afterburner-Monitoring 'GPU-Spannung' aus?) — "
                        f"Obergrenze aus dem Takt geschätzt: {ceiling:.0f} mV",
                        f"  No voltage readings (Afterburner monitoring 'GPU voltage' off?) — "
                        f"ceiling estimated from the clock: {ceiling:.0f} mV"), "warning")
        anchors_mv = CT.anchor_voltages([p.voltage_mv for p in points], ceiling,
                                        cfg.curve_min_mv, cfg.curve_anchor_step_mv)
        if not anchors_mv:
            return self._curve_fail(T(f"Keine Messpunkte zwischen {cfg.curve_min_mv} und "
                                      f"{ceiling:.0f} mV", f"No points between {cfg.curve_min_mv} "
                                      f"and {ceiling:.0f} mV"))
        self._log(T(f"  Boost-Last bei Standard: {ceiling:.0f} mV @ {probe.avg_core_mhz:.0f} MHz "
                    f"→ Messpunkte: {', '.join(str(v) for v in anchors_mv)} mV",
                    f"  Boost load at stock: {ceiling:.0f} mV @ {probe.avg_core_mhz:.0f} MHz "
                    f"→ points: {', '.join(str(v) for v in anchors_mv)} mV"))

        # 3) stock benchmark — the "before"
        self._set_state(TunerState.BENCH)
        self._stock_rate = 0.0             # points per second at stock (plausibility of later runs)
        stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 17, 3)
        if stock is None:
            return
        if not stock.passed and cfg.furmark_path and not stock.thermal:
            self._log(T(f"  FurMark lief bei Standard nicht ({stock.note}) — weiter mit dem internen "
                        f"Rechen-Benchmark",
                        f"  FurMark failed at stock ({stock.note}) — continuing with the internal "
                        f"compute benchmark"), "warning")
            cfg.furmark_path = ""
            stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 17, 3)
            if stock is None:
                return
        if not stock.passed:
            return self._curve_fail(T(f"Standard-Benchmark fehlgeschlagen ({stock.note}) — Kühlung "
                                      f"prüfen, keine Änderung vorgenommen",
                                      f"Stock benchmark failed ({stock.note}) — check cooling, "
                                      f"nothing was changed"))
        stock.name = T("Standard", "Stock")
        if cfg.furmark_path:
            self._stock_rate = stock.score / max(cfg.bench_s, 1)
        bench_name = "FurMark" if cfg.furmark_path else T("interner Rechen-Benchmark",
                                                           "internal compute benchmark")
        unit = T("Punkte", "points") if cfg.furmark_path else "TFLOPS"
        self._log(T(f"  Standard: {stock.score:.0f} {unit}, Ø {stock.power_w:.0f} W, max. "
                    f"{stock.temp_c:.0f} °C, Ø {stock.clock_mhz:.0f} MHz ({bench_name})",
                    f"  Stock: {stock.score:.0f} {unit}, avg {stock.power_w:.0f} W, max "
                    f"{stock.temp_c:.0f} °C, avg {stock.clock_mhz:.0f} MHz ({bench_name})"))

        # 4) every voltage point: the highest stable clock
        self._set_state(TunerState.CURVE)
        self._log(T(f"Kurve: {len(anchors_mv)} Spannungspunkte — je Schritt {cfg.step_test_s} s "
                    f"Boost-Last, +{cfg.curve_step_mhz} MHz, bei Fehler halbiert bis "
                    f"{cfg.curve_min_step_mhz} MHz",
                    f"Curve: {len(anchors_mv)} voltage points — {cfg.step_test_s} s boost load per "
                    f"step, +{cfg.curve_step_mhz} MHz, halved on a failure down to "
                    f"{cfg.curve_min_step_mhz} MHz"))
        results: list = []
        prior, known = int(cfg.curve_prior_mhz), bool(cfg.curve_prior_mhz)
        n = len(anchors_mv)
        floor_mv = 0.0          # the card ran ABOVE a point: its minimum voltage under this load
        for i, mv in enumerate(anchors_mv, 1):
            pt = curve.lock_point(mv)
            base_mhz = pt.base_mhz
            if floor_mv:
                results.append(CT.AnchorResult(mv, base_mhz, reachable=False, ran_mv=floor_mv))
                self._log(T(f"  Punkt {i}/{n}: {mv} mV — übersprungen: unter der Mindestspannung "
                            f"der Karte unter Last ({floor_mv:.0f} mV)",
                            f"  Point {i}/{n}: {mv} mV — skipped: below the card's minimum voltage "
                            f"under load ({floor_mv:.0f} mV)"))
                continue
            start = int(round(base_mhz + prior))
            step = cfg.curve_step_mhz if known else cfg.curve_coarse_step_mhz
            self._log(T(f"  Punkt {i}/{n}: {mv} mV (Stock {base_mhz:.0f} MHz) — Start bei "
                        f"{start} MHz ({prior:+d})",
                        f"  Point {i}/{n}: {mv} mV (stock {base_mhz:.0f} MHz) — starting at "
                        f"{start} MHz ({prior:+d})"))
            prog = 20 + int((i - 1) / n * 40)
            label = T(f"Punkt {i}/{n}", f"Point {i}/{n}")
            r = CT.search_anchor(
                lambda v, f, b=base_mhz, lb=label, pg=prog: self._test_point(stress, v, f, b, lb, pg),
                mv, base_mhz, start, step=step, min_step=cfg.curve_min_step_mhz,
                down_step=cfg.curve_down_mhz, max_mhz=int(base_mhz + cfg.core_max_mhz),
                stop=self._stop.is_set)
            if self._stop.is_set():
                return
            results.append(r)
            if r.best_mhz:
                prior, known = r.offset, True
                self._log(T(f"  → {mv} mV: {r.best_mhz} MHz stabil ({r.offset:+d})",
                            f"  → {mv} mV: {r.best_mhz} MHz stable ({r.offset:+d})"))
            elif not r.reachable:
                self._log(T(f"  → {mv} mV: unter Last nicht erreichbar",
                            f"  → {mv} mV: not reachable under load"), "warning")
                if r.below_floor:
                    floor_mv = r.ran_mv
            else:
                self._log(T(f"  → {mv} mV: kein stabiler Takt gefunden",
                            f"  → {mv} mV: no stable clock found"), "warning")
        CT.apply_margins(results, cfg.curve_safety_mhz, cfg.curve_safety_top_mhz,
                         cfg.curve_reset_extra_mhz)
        anchors = CT.curve_anchors(results)
        if not anchors:
            return self._curve_fail(T("Kein Spannungspunkt stabil messbar — kein Profil gespeichert",
                                      "No voltage point measurably stable — no profile saved"))
        self._log(T(f"Eigene Kurve (−{cfg.curve_safety_mhz} MHz Sicherheit, −{cfg.curve_safety_top_mhz} an "
                    f"den oberen Punkten, +{cfg.curve_reset_extra_mhz} nach Treiber-Reset/Hänger): ",
                    f"Own curve (−{cfg.curve_safety_mhz} MHz safety, −{cfg.curve_safety_top_mhz} at the top "
                    f"points, +{cfg.curve_reset_extra_mhz} after a driver reset / hang): ")
                  + ", ".join(f"{mv} mV → {f} MHz" for mv, f in sorted(anchors, reverse=True)))

        # 4b) Curve check — FurMark (heavy, the whole card) on the new curve with
        #     memory at stock. The points were searched with the light boost
        #     load; whatever FurMark still breaks is lowered HERE, before the
        #     memory is touched — so a later crash points at the memory.
        notes: list = []
        self._set_state(TunerState.BENCH)
        for attempt in range(1, self.CURVE_CHECK_TRIES + 1):
            self._apply_curve(anchors, 0, 0, 100)
            time.sleep(2)
            chk = self._bench(stress, cfg.curve_check_s, T("Kurven-Check", "Curve check"), 58, 2)
            if chk is None:
                return
            if chk.invalid:
                return self._curve_fail(self._invalid_msg(chk))
            if chk.passed:
                notes.append(T(f"Kurven-Check (FurMark {cfg.curve_check_s} s, Speicher +0): bestanden",
                               f"Curve check (FurMark {cfg.curve_check_s} s, memory +0): passed"))
                self._log(T(f"  Kurven-Check ✓  {chk.score:.0f} {unit}, max. {chk.temp_c:.0f} °C",
                            f"  Curve check ✓  {chk.score:.0f} {unit}, max {chk.temp_c:.0f} °C"))
                break
            if chk.thermal or not chk.unstable:
                return self._curve_fail(T(f"Kurven-Check: {chk.note} — Kühlung prüfen, kein Profil "
                                          f"gespeichert", f"Curve check: {chk.note} — check the "
                                          f"cooling, no profile saved"))
            if attempt == self.CURVE_CHECK_TRIES:
                return self._curve_fail(T(f"Die Kurve hält FurMark auch nach {attempt - 1} "
                                          f"Rücknahme(n) nicht ({chk.note}) — kein Profil gespeichert",
                                          f"The curve fails FurMark even after {attempt - 1} "
                                          f"step-back(s) ({chk.note}) — no profile saved"))
            new = CT.lower_curve(anchors, cfg.curve_step_mhz, chk.last_mv)
            pts = ", ".join(str(mv) for (mv, f), (_m, f2) in zip(anchors, new) if f2 != f)
            anchors = new
            what = T(f"Kurve −{cfg.curve_step_mhz} MHz bei {pts} mV",
                     f"curve −{cfg.curve_step_mhz} MHz at {pts} mV")
            notes.append(T(f"Kurven-Check ✗ ({chk.note}) → {what}", f"Curve check ✗ ({chk.note}) → {what}"))
            self._log(T(f"  Kurven-Check ✗  {chk.note} — {what}, neuer Versuch",
                        f"  Curve check ✗  {chk.note} — {what}, trying again"), "warning")

        # 5) memory — the whole card under load (see _mem_stage_full)
        mem = 0
        if cfg.mem_stage:
            got = self._mem_stage_full(stress, lambda m: self._apply_curve(anchors, 0, m, 100))
            if got is None:
                return
            mem, mem_note = got
            if mem < 0:
                return self._curve_fail(mem_note)
            notes.append(mem_note)

        # 6) the curve caps the goal allows — benchmarked, picked per goal. Caps
        #    every 25 mV between the measured points (the curve is interpolated).
        #    A candidate that crashes is NOT skipped: memory one step back first
        #    (the likeliest cause of artifacts), then the curve where the card
        #    ran, and all candidates are measured again on the safer settings.
        self._set_state(TunerState.BENCH)
        cap_mvs = CT.anchor_voltages([p.voltage_mv for p in points], max(anchors)[0],
                                     min(anchors)[0], cfg.curve_cap_step_mv)
        plan = CT.plan_candidates(goal, cap_mvs, self._max_power_pct(),
                                  stock.power_capped_pct >= 30)
        backoffs = 0
        while True:
            tested: list = []
            crashed = None
            for k, c in enumerate(plan):
                lbl = c.label(de)
                self._apply_curve(anchors, c.cap_mv, mem, c.pwr_pct)
                time.sleep(2)
                b = self._bench(stress, cfg.bench_s, T(f"Kandidat {k + 1}/{len(plan)} ({lbl})",
                                                       f"Candidate {k + 1}/{len(plan)} ({lbl})"),
                                68 + int(k / max(len(plan), 1) * 10), 2)
                if b is None:
                    return
                if b.invalid:
                    return self._curve_fail(self._invalid_msg(b))
                b.cap_mv, b.pwr_pct = c.cap_mv, c.pwr_pct
                if b.unstable:
                    crashed = (lbl, b)
                    break
                tested.append(b)
                if b.passed:
                    self._log(f"  {lbl}: {b.score:.0f} {unit}, Ø {b.power_w:.0f} W, "
                              f"max. {b.temp_c:.0f} °C, {b.per_watt:.2f} {unit}/W")
                else:
                    self._log(f"  {lbl}: ✗ {b.note}", "warning")
                if CT.stop_testing(goal, tested, stock):
                    if k + 1 < len(plan):
                        self._log(T("  Niedrigere Kappungen wären noch langsamer — Schluss",
                                    "  Lower caps would only be slower — done"))
                    break
            if crashed is None:
                break
            lbl, b = crashed
            if backoffs >= self.CANDIDATE_BACKOFFS:
                return self._curve_fail(T(f"„{lbl}“ stürzt auch nach {backoffs} Rücknahme(n) ab "
                                          f"({b.note}) — kein Profil gespeichert",
                                          f"'{lbl}' still crashes after {backoffs} step-back(s) "
                                          f"({b.note}) — no profile saved"))
            backoffs += 1
            if mem > 0:
                m2 = max(0, mem - cfg.mem_curve_step_mhz)
                what = T(f"Speicher +{mem}→+{m2} MHz", f"memory +{mem}→+{m2} MHz")
                mem = m2
            else:
                new = CT.lower_curve(anchors, cfg.curve_step_mhz, b.last_mv)
                pts = ", ".join(str(mv) for (mv, f), (_m, f2) in zip(anchors, new) if f2 != f)
                anchors = new
                what = T(f"Kurve −{cfg.curve_step_mhz} MHz bei {pts} mV",
                         f"curve −{cfg.curve_step_mhz} MHz at {pts} mV")
            notes.append(T(f"Kandidat „{lbl}“ abgestürzt ({b.note}) → {what}, alle Kandidaten neu",
                           f"Candidate '{lbl}' crashed ({b.note}) → {what}, all candidates again"))
            self._set_state(TunerState.BACKOFF)
            self._log(T(f"  {lbl}: ✗ {b.note} — zurück: {what}, Kandidaten werden neu gemessen",
                        f"  {lbl}: ✗ {b.note} — step back: {what}, measuring the candidates again"),
                      "warning")
            self._set_state(TunerState.BENCH)
        chosen = CT.choose_candidate(goal, tested, stock)
        if chosen is None:
            chosen = tested[0] if tested else CT.Candidate("", 0, 100)
            self._log(T("  Kein Kandidat hat den Benchmark bestanden — Endtest mit der vollen "
                        "Kurve, bei Fehlern wird zurückgenommen",
                        "  No candidate passed the benchmark — final test with the full curve, "
                        "stepping back on failures"), "warning")
        else:
            rule = CT.GOAL_RULE[goal][0 if de else 1]
            self._log(T(f"  Gewählt für „{gname}“ ({rule}): {chosen.label(de)}",
                        f"  Chosen for '{gname}' ({rule}): {chosen.label(de)}"))
        cap, pwr = chosen.cap_mv, chosen.pwr_pct

        # 7) final test — only what passed it is saved
        cur = list(anchors)
        attempt, retries = 1, []
        endurance: Optional[CT.Candidate] = None
        verify: Optional[StressResult] = None
        while True:
            self._set_state(TunerState.FINAL_TEST)
            tries = (T(f" | Versuch {attempt}/{self.FINAL_RETRIES + 1}",
                       f" | attempt {attempt}/{self.FINAL_RETRIES + 1}") if attempt > 1 else "")
            what_now = CT.Candidate("", cap, pwr).label(de)
            self._log(T(f"Endtest: {what_now}, Mem+{mem}MHz | {bench_name} {cfg.final_bench_s}s + "
                        f"Rechen-Prüfung {cfg.final_test_s}s{tries}",
                        f"Final test: {what_now}, Mem+{mem}MHz | {bench_name} {cfg.final_bench_s}s + "
                        f"compute check {cfg.final_test_s}s{tries}"))
            self._apply_curve(cur, cap, mem, pwr)
            time.sleep(2)
            endurance = self._bench(stress, cfg.final_bench_s, T("Endtest", "Final test"), 80, 12)
            if endurance is None:
                return
            if endurance.invalid:
                return self._curve_fail(self._invalid_msg(endurance))
            verify = None
            if endurance.passed:
                def _tick_v(e, d, s):
                    self._progress(92 + int(e / max(d, 1) * 6),
                                   T(f"Rechen-Prüfung: {e}/{d}s | {s.temp}°C | {s.core_mhz:.0f} MHz",
                                     f"Compute check: {e}/{d}s | {s.temp}°C | {s.core_mhz:.0f} MHz"))
                    self._tick(s)
                verify = stress.run(cfg.final_test_s, cfg.max_temp_c, on_tick=_tick_v, mode="mixed")
                if self._stop.is_set():
                    return
            game = None
            if endurance.passed and verify is not None and verify.passed and cfg.game_test:
                game = self._game_test(stress, 97)
                if game is None:
                    return
                if not game.passed:
                    verify = game             # the failed phase decides the step back
            if endurance.passed and verify is not None and verify.passed:
                if game is not None:
                    notes.append(T(f"Spiel-Endtest ({cfg.game_cool_s} s abkühlen, {cfg.game_transient_s // 60} "
                                   f"min Lastwechsel, {cfg.game_boost_s // 60} min Boost-Punkt): bestanden",
                                   f"Game test ({cfg.game_cool_s} s cool-down, {cfg.game_transient_s // 60} "
                                   f"min load changes, {cfg.game_boost_s // 60} min boost point): passed"))
                break
            if verify is not None:
                why = self._fail_reason(verify)
                unstable = bool(verify.crash_detected or verify.tdr_detected or verify.compute_error)
                thermal = not unstable and (verify.throttle_hit or verify.max_temp >= cfg.max_temp_c)
                tdr_note = " [TDR!]" if verify.tdr_detected else ""
                crash_mv = verify.last_voltage_mv
                if unstable:
                    self._crash_pause()
            else:
                why, unstable, thermal = endurance.note, endurance.unstable, endurance.thermal
                tdr_note = " [TDR!]" if "TDR" in (endurance.note or "") else ""
                crash_mv = endurance.last_mv
            if attempt > self.FINAL_RETRIES:
                return self._curve_fail(T(f"Endtest nicht bestanden ({why}), auch nach {len(retries)} "
                                          f"Rücknahme(n) — KEIN Profil gespeichert, GPU auf Standard",
                                          f"Final test failed ({why}), even after {len(retries)} "
                                          f"step-back(s) — NO profile saved, GPU back to stock"))
            cur, mem, cap, pwr, what = CT.final_backoff(attempt, cur, mem, cap, pwr, unstable,
                                                         thermal, cfg.curve_step_mhz, de, cap_mvs,
                                                         crash_mv=crash_mv,
                                                         mem_step=cfg.mem_curve_step_mhz)
            retries.append(what)
            self._set_state(TunerState.BACKOFF)
            self._log(T(f"  Endtest ✗{tdr_note}  {why} — zurück: {what} → Endtest wird wiederholt",
                        f"  Final test ✗{tdr_note}  {why} — step back: {what} → final test again"),
                      "warning")
            attempt += 1

        # The fair "after": the same short benchmark as the stock run.
        after = chosen if (not retries and chosen in tested and chosen.passed) else None
        if after is None:
            after = self._bench(stress, cfg.bench_s, T("Nachher-Benchmark", "After benchmark"), 98, 1)
            if after is None:
                return
            if not after.passed:          # the profile passed the final test — keep it, say so
                notes.append(T(f"Nachher-Benchmark ✗ ({after.note}) — Vergleich vorher/nachher fehlt",
                               f"After benchmark ✗ ({after.note}) — no before/after comparison"))
                after = CT.Candidate(T("nicht gemessen", "not measured"))

        # 8) save + report
        self._set_state(TunerState.SAVING)
        try:
            gpu_name = self.monitor.read().name
        except Exception:
            gpu_name = "Unknown"
        top_mv, top_f = max(cur)
        top_off = int(top_f - curve.lock_point(top_mv).base_mhz)
        saved = CT.Candidate("", cap, pwr)
        tag = {"max": "MAX", "balanced": "BAL", "efficiency": "EFF"}[goal]
        score = self._score(verify)
        gain = CT._pct(after.score, stock.score)
        profile = TuneProfile(
            name=f"GOP_CURVE_{tag}_{datetime.now().strftime('%m%d_%H%M')}",
            core_offset_mhz=top_off,
            mem_offset_mhz=mem,
            power_limit_pct=pwr,
            curve_points=[[int(mv), int(f)] for mv, f in sorted(cur)],
            curve_cap_mv=int(cap),
            is_stable=True,
            stability_score=score,
            stage1_freq=int(endurance.clock_mhz),
            stage1_voltage=int(verify.avg_voltage_mv),
            notes=(f"[{T('Rundum', 'All-round')} {gname}] "
                   + T(f"Kurve {len(cur)} Punkte {min(cur)[0]}–{max(cur)[0]} mV",
                       f"curve {len(cur)} points {min(cur)[0]}–{max(cur)[0]} mV")
                   + (T(f", flach ab {cap} mV", f", flat from {cap} mV") if cap else "")
                   + f" | Mem+{mem}MHz | Pwr {pwr}% | {bench_name} {stock.score:.0f}→{after.score:.0f} "
                     f"({gain}) | {stock.power_w:.0f}→{after.power_w:.0f} W | MaxTemp "
                     f"{endurance.temp_c:.0f}°C | Score {score}/100"
                   + (T(f" | nach {len(retries)} Rücknahme(n)", f" | after {len(retries)} step-back(s)")
                      if retries else "")),
            created_at=datetime.now().isoformat(),
            gpu_name=gpu_name,
        )
        if min(stock.score, after.score, stock.power_w, after.power_w) > 0:
            from core import profile_score as PS
            profile.bench = PS.bench_record(bench_name, cfg.bench_s, after.score, after.power_w,
                                            stock.score, stock.power_w, at=profile.created_at)
        self.best_profile = profile
        self.pm.save(profile)
        self._persist(profile)                # what the PC boots with (Afterburner [Startup])
        if self.cr:
            self.cr.save_last_applied(profile.to_dict())
        rep = CT.build_report(goal, results, stock, after, chosen, mem, cands=tested,
                              endurance=endurance, endurance_s=cfg.final_bench_s,
                              verify_s=cfg.final_test_s, bench_name=bench_name,
                              max_temp_limit=cfg.max_temp_c, safety_mhz=cfg.curve_safety_mhz,
                              top_safety_mhz=cfg.curve_safety_top_mhz,
                              retries=retries,
                              saved=saved if (saved.cap_mv, saved.pwr_pct) != (chosen.cap_mv,
                                                                                chosen.pwr_pct) else None,
                              notes=notes, core_max=cfg.core_max_mhz,
                              lang="de" if de else "en")
        self.last_report = rep
        self.last_report_path = ""
        try:
            Path(self._log_dir).mkdir(parents=True, exist_ok=True)
            path = os.path.join(self._log_dir,
                                f"curve_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join([f"GPU: {gpu_name}", f"Profil: {profile.name}", ""] + rep["lines"]
                                  + ["", T("Empfehlungen:", "Recommendations:")]
                                  + [f"  • {x}" for x in rep["recommendations"]]) + "\n")
            self.last_report_path = path
        except OSError:
            pass

        self._log("═══════════════════════════════════════")
        for line in rep["lines"]:
            if line:
                self._log(line)
        self._log(T("Empfehlungen:", "Recommendations:"))
        for x in rep["recommendations"]:
            self._log(f"  • {x}")
        # Same summary lines as the other modes (Tune History reads them).
        self._log_summary(profile.name, f"{T('Rundum', 'All-round')} ({gname})",
                          f"+{max(0, top_off)}MHz ({T('Kurve, oberster Punkt', 'curve, top point')})",
                          mem, pwr, verify.avg_voltage_mv, endurance.temp_c, score)
        if self.cr:
            self.cr.clear_tuning_flag()
        self._progress(100, f"✓ {T('Fertig', 'Done')}! [{T('Rundum', 'All-round')} {gname}] "
                            f"{rep['summary']}")
        self._log("═══════════════════════════════════════")
        self._log(T("        Auto-Tune abgeschlossen", "        Auto-Tune Complete"))
        self._log("═══════════════════════════════════════")
        self._set_state(TunerState.DONE)

    def _score(self, r: StressResult) -> int:
        score  = 100
        # Use the user-configured temperature limit, not a hardcoded 85 —
        # otherwise a lower max_temp_c (e.g. 75) still scores against 85.
        margin = self.config.max_temp_c - r.max_temp
        if margin < 5:
            score -= 20
        elif margin < 10:
            score -= 10
        if r.throttle_hit:
            score -= 15
        if r.tdr_detected:
            score -= 30
        return max(0, min(100, score))
