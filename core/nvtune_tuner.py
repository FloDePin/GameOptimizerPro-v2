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

import time, threading, os, sys, subprocess, logging, json
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
    fault_mv:       float = 0.0    # hardness test: the recorded voltage just before the fault, 0 = unknown
    mem_fault:      bool  = False  # hardness test: the memory load failed (the step back takes memory)
    stage:          str   = ""     # final tests: the test this result is from (AutoTuner._stage_name)
    invalid:        bool  = False  # final FurMark run: implausible (driver not clean) — the run ends

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
    # Round 33 hardness test after the game test (both modes, _hard_test): several loads at once,
    # like a game that is recorded or streamed — 3D + the video encoder + compute / memory
    # (core/hardness_test.py). The single loads before it never had them together. Off here, on
    # from the GPU tab: it starts real loads (FurMark, NVENC) — a simulated tune must never.
    hard_test:           bool = False
    hard_test_min:       float = 10
    # Final tests (both modes): a failed test is checked once more with the memory at stock
    # before the step back — it fails again: the core / curve, it passes: the memory. The next
    # try starts with the test that failed (minutes, not the whole half hour); the first try
    # starts with the hardness test's harshest phase (load_check_phase) when the hardness test is on.
    # Point search (23.10.): the last point_transient_s of every step_test_s step are load changes
    # at the point (worker "boost_trans") — no extra time; 0 = the boost load alone (round 13).
    # Live, a point found with the steady load alone failed ~100 MHz lower under load changes.
    point_transient_s:   int  = 15
    final_cross_check:   bool = True
    final_fail_fast:     bool = True
    load_check_phase:    str  = "game_rec_compute"
    # Round 33: the video encoder next to every stability step (curve points, OC steps, final and
    # game test) — the limit found is the one that holds while recording / streaming. No extra
    # time (it runs in parallel); without NVENC the steps run as before. Off here, on from the
    # GPU tab (a simulated tune never starts it).
    encoder_companion:   bool = False
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
    reset_pause_s:       int = 30      # after a driver reset in the point search (round 33)
    start_cool_c:        float = 45.0  # round 33: every tune starts at most this warm ...
    start_cool_max_s:    int = 0       # ... idling at most this long first (GPU tab: 180; 0 = off)
    curve_prior_mhz:     int = 0       # start offset of the first point (e.g. last tune's core offset)
    curve_probe_s:       int = 20      # stock boost-load run: highest voltage the card reaches
    bench_s:             int = 60      # FurMark benchmark per candidate (and the stock run)
    bench_cool_max_s:    int = 90      # before a comparison benchmark: cool down to the stock
    bench_cool_tol_c:    float = 2.0   # run's starting temperature (+ this), at most that long
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
    # "SW thermal" ALONE far below the temperature limit is that same driver signal, not heat:
    # the point search's load changes (23.10.) end the load every second, and live it stayed
    # on for 3+ samples at 52-58 °C (slowdown point 94 °C) and failed good steps. It counts
    # from this close to the limit on; the hardware slowdowns always count.
    SW_THERMAL_NEAR_C = 15

    @classmethod
    def _protective(cls, stats, max_temp: float) -> bool:
        """A thermal / hardware slowdown that means the card protects itself."""
        if not getattr(stats, "throttle_protective", False):
            return False
        from core.nvtune_core import THR_PROTECTIVE, THR_SW_THERMAL
        bits = int(getattr(stats, "throttle_bits", 0) or 0)
        if bits & THR_PROTECTIVE == THR_SW_THERMAL:
            return float(getattr(stats, "temp", 0) or 0) >= max_temp - cls.SW_THERMAL_NEAR_C
        return True

    # A load that stops delivering results is a hung GPU. A game can end with
    # D3D12 "device hung" on a profile that passed every test; a hang in our
    # own load used to count as passed until the driver reset killed the worker
    # (TdrDelay — 10 s on the test PC, if it fires at all).
    HANG_S = 8.0
    # No result at all since the worker started — while an earlier run of this
    # tester (the tune's baseline) delivered: it hung on its very first product
    # (where a too-high clock fails first), or CUDA did not start and the worker fell
    # back to the CPU. Either way no GPU load was tested, and the step passed. A
    # start-up takes a few seconds (cupy, CUDA context, the first product).
    START_HANG_S = 30.0
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
        self._delivered = False        # a run of this tester got results (the load works here)
        # Round 33: a second load next to the steps that allow it — "encode" = the video
        # encoder, as when a game is recorded or streamed (TunerConfig.encoder_companion).
        # Measured: a tuned curve that passed every single load computed wrong within
        # minutes with the encoder running next to it; stock never did.
        self.companion: Optional[str] = None
        self.companion_off = ""        # why it can't run on this PC (no NVENC) — then without it
        self._comp: Optional[subprocess.Popen] = None
        self._comp_m: dict = {}
        self._main_stop = self._comp_stop = ""
        self.split_s = 30.0            # "boost_trans": seconds of the boost load before the load changes

    def _worker_path(self):
        # Worker lives at project root, not in core/
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "_stress_worker.py"
        )

    def _stop_path(self, tag: str) -> str:
        import tempfile
        p = os.path.join(tempfile.gettempdir(), f"gop_tstop_{os.getpid()}_{id(self)}_{tag}")
        try:
            os.remove(p)                       # a leftover of an earlier run
        except OSError:
            pass
        return p

    def start(self, mode: str = "gemm", stop_file: str = ""):
        wp = self._worker_path()
        self._metrics = {"RATE": [], "BW": [], "ERR": [], "LAST": 0.0}
        self._t0 = time.time()
        self._main_stop = stop_file
        if os.path.exists(wp):
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                # an earlier run delivered: CUDA works here, a start-up error is instability
                env = dict(os.environ, GOP_STRESS_GPU_OK="1") if self._delivered else None
                if stop_file:                 # it can be asked to end (next to the companion)
                    env = dict(env or os.environ, GOP_STRESS_STOP_FILE=stop_file)
                if mode == "boost_trans":
                    env = dict(env or os.environ, GOP_STRESS_SPLIT_S=f"{self.split_s:.0f}")
                self._proc = subprocess.Popen(
                    [sys.executable, wp, str(os.getpid()), mode],  # GUI PID → dead-man switch
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=flags, env=env
                )
                from core import proc_job
                proc_job.bind(self._proc)        # ends with the app, however the app ends
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

    # ── round 33: the companion load ──────────────────────────────────────────
    COMPANION_HANG_S = 10.0

    def _start_companion(self):
        self._comp_m = {"LAST": 0.0, "ERR": [], "NOENC": "", "T0": time.time()}
        self._comp_stop = self._stop_path("c")
        env = dict(os.environ, GOP_STRESS_STOP_FILE=self._comp_stop)
        if self._delivered:
            env["GOP_STRESS_GPU_OK"] = "1"
        try:
            self._comp = subprocess.Popen(
                [sys.executable, self._worker_path(), str(os.getpid()), self.companion],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            from core import proc_job
            proc_job.bind(self._comp)
        except Exception:
            self._comp = None
            return
        threading.Thread(target=self._read_companion, args=(self._comp, self._comp_m), daemon=True).start()

    @staticmethod
    def _read_companion(proc, m: dict):
        try:
            for line in proc.stdout:
                m["LAST"] = time.time()
                parts = line.split()
                if parts and parts[0] == "ERR":
                    m["ERR"].append(" ".join(parts[1:]))
                elif parts and parts[0] == "NOENC":
                    m["NOENC"] = " ".join(parts[1:]) or "no encoder"
        except Exception:
            pass

    def companion_state(self) -> Optional[tuple]:
        """None = fine / none running; ("off", why) = not possible on this PC;
        ("error" | "hang" | "crash", detail) = a failure next to the step."""
        p = self._comp
        if p is None:
            return None
        m = self._comp_m
        rc = p.poll()
        if rc is not None:
            if rc == 4 or m.get("NOENC"):
                return ("off", m.get("NOENC") or "exit 4")
            if m.get("ERR"):
                e = m["ERR"][-1]
                return ("hang" if e.startswith("stall") else "error", e)
            return ("error" if rc == self.EXIT_COMPUTE_ERROR else "crash", f"exit {rc}")
        now = time.time()
        if m.get("LAST") and now - m["LAST"] >= self.COMPANION_HANG_S:
            return ("hang", f"{now - m['LAST']:.0f} s")
        if not m.get("LAST") and now - m.get("T0", now) >= self.START_HANG_S:
            return ("hang", f"{now - m.get('T0', now):.0f} s")
        return None

    def stop(self):
        """A load with a stop file is asked to end (its product finishes, the encoder closes
        its session) — a kill in the middle of GPU work while another process encodes makes
        the driver log nvlddmkm 153; the others as before."""
        procs = [(self._proc, self._main_stop), (self._comp, self._comp_stop)]
        for p, f in procs:
            if p is not None and f:
                try:
                    Path(f).touch()
                except OSError:
                    pass
        for p, f in procs:
            if p is None:
                continue
            try:
                if not f:
                    p.terminate()
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                    p.wait(timeout=5)
                except Exception:
                    pass
            except Exception:
                pass
        for f in (self._main_stop, self._comp_stop):
            if f:
                try:
                    os.remove(f)
                except OSError:
                    pass
        self._proc = self._comp = None
        self._main_stop = self._comp_stop = ""

    def run(
        self,
        duration_s: int,
        max_temp: int,
        on_tick: Optional[Callable] = None,
        mode: str = "gemm",
        companion: bool = False,
    ) -> StressResult:
        """companion=True: the tester's companion load (self.companion) runs next to it — a
        failure there fails the step like one of its own."""
        result = StressResult()
        temps, voltages, clocks, usages, mem_clocks = [], [], [], [], []
        steady_volts, powers = [], []
        recent_v: list = []                 # last few voltages (the loaded state before a crash)
        samples = capped = prot_run = 0

        use_comp = bool(companion and self.companion and not self.companion_off)
        if use_comp:                         # it can be asked to end, next to the companion
            self.start(mode, stop_file=self._stop_path("m"))
        else:
            self.start(mode)
        if use_comp:
            self._start_companion()
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
            if elapsed >= self.RAMP_S and self._protective(stats, max_temp):
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
            # Nothing at all since the start (START_HANG_S). A tester that never got a
            # result is left to the baseline check (no cupy: no GPU load at all).
            since = time.time() - start
            if self._proc and not quiet_since and self._delivered and since >= self.START_HANG_S:
                result.crash_detected = result.hang_detected = True
                result.abort_reason = CT.T(f"GPU hängt — seit dem Start ({since:.0f} s) keine Ergebnisse der "
                                           f"Last (oder CUDA startete nicht)",
                                           f"GPU hung — no results from the load since its start ({since:.0f} s; "
                                           f"or CUDA did not start)")
                break

            # The companion load (round 33): its wrong result, hang or crash is the step's
            if use_comp:
                st = self.companion_state()
                if st and st[0] == "off":
                    self.companion_off = st[1] or "off"       # no encoder here: on without it
                    use_comp = False
                elif st:
                    result.crash_detected = True
                    result.compute_error = st[0] == "error"
                    result.hang_detected = st[0] == "hang"
                    result.abort_reason = CT.T(f"Fehler in der Encoder-Last daneben ({st[1]})",
                                               f"failure in the encoder load next to it ({st[1]})")
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

        comp, comp_m = (self._comp, self._comp_m) if use_comp else (None, {})
        self.stop()
        if comp is not None and not result.crash_detected and (comp_m.get("ERR") or comp.returncode == 3):
            # its last frame / product was wrong as the loads ended (a load step down)
            result.crash_detected = result.compute_error = True
            result.abort_reason = CT.T("Fehler in der Encoder-Last daneben (beim Lastende)",
                                       "failure in the encoder load next to it (as the loads ended)")
        if self._metrics.get("LAST"):
            self._delivered = True
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

    def _log(self, msg, lvl="info", touch=True):
        if touch:
            self._last_activity = time.monotonic()
        getattr(self.logger, lvl)(msg)
        if self._cb_log:
            self._cb_log(msg, lvl)

    def _progress(self, pct, msg):
        self._last_activity = time.monotonic()
        if pct >= 0:
            self._last_pct = pct
        if self._cb_progress:
            self._cb_progress(pct, msg)

    # Stall watchdog: every step reports progress at least every few seconds and an
    # Afterburner restart takes ~5–30 s — no log / progress from the tuner thread for
    # this long means a call is stuck (live 10.10.: ~19 min, PC idle, Windows'
    # automatic maintenance running; afterwards nothing told where it had waited).
    STALL_S = 120.0
    STALL_CHECK_S = 5.0

    def _stall_loop(self, done: threading.Event):
        stalled_at = None                    # the activity time a stall was reported for
        while not done.wait(self.STALL_CHECK_S):
            last = getattr(self, "_last_activity", None)
            if last is None:
                continue
            quiet = time.monotonic() - last
            if stalled_at is None and quiet >= self.STALL_S:
                stalled_at = last
                path = self._dump_stall(quiet)
                self._log(CT.T(f"⚠ Der Tuner wartet seit {quiet / 60:.0f} min ohne Rückmeldung — "
                               f"die Stelle steht in {os.path.basename(path) if path else 'keiner Datei'}",
                               f"⚠ The tuner has been waiting {quiet / 60:.0f} min without a sign of life — "
                               f"where it waits is in {os.path.basename(path) if path else 'no file'}"),
                          "warning", touch=False)
            elif stalled_at is not None and last != stalled_at:
                self._log(CT.T(f"  Tuner läuft weiter (nach {(last - stalled_at) / 60:.0f} min Stillstand)",
                               f"  Tuner going on (after a {(last - stalled_at) / 60:.0f}-min stall)"),
                          "warning", touch=False)
                stalled_at = None

    def _dump_stall(self, quiet: float) -> str:
        """Every thread's stack into logs/stall_<time>.txt — "" when it can't be written."""
        import faulthandler
        try:
            Path(self._log_dir).mkdir(parents=True, exist_ok=True)
            path = os.path.join(self._log_dir, f"stall_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Tuner {quiet:.0f} s without log / progress — state {getattr(self, 'state', '?')}\n\n")
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
            return path
        except Exception:
            return ""

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

    # A failed final test is not the end: take one step back and run ALL final tests again
    # (FurMark, compute check, game test, hardness test) — only a configuration that passed
    # them in one go is ever saved. Round 33: up to 12 tries (was 5) — the user's rule: go on
    # until everything holds, no shortcut.
    FINAL_RETRIES = 11

    # Stage 2: a step that lost more than allowed, but at most this many times the
    # allowed loss, gets a cross-check — the 100 % reference measured again.
    PWR_RECHECK_X = 3

    @staticmethod
    def _final_backoff(cfg: "TunerConfig", r: StressResult, attempt: int,
                       core: int, mem: int, pwr: int, core_backs: int = 0):
        """One step back after failed final test number `attempt` (1-based).
        -> (core, mem, pwr, what) or None when nothing is left to take back.
        Thermal failures lower the power limit first; instability (wrong results,
        crash, driver reset) takes back the core offset (found with 45-s steps, right at
        the edge); the memory offset when the memory is the cause (r.mem_fault: its own load failed,
        or the final loop's cross-check passed with the memory at stock — 23.10.), when there is no
        core offset left, or — only without that cross-check — after CT.MEM_AFTER core step-backs
        in a row that did not help (core_backs; round 33)."""
        unstable = r.compute_error or r.crash_detected or r.tdr_detected
        thermal = not unstable and (r.throttle_hit or r.max_temp >= cfg.max_temp_c)
        if thermal and pwr - cfg.power_step_pct >= cfg.power_min_pct:
            p2 = pwr - cfg.power_step_pct
            return core, mem, p2, f"Power-Limit {pwr}→{p2} % ({CT.T('Temperatur', 'temperature')})"
        if mem > 0 and (getattr(r, "mem_fault", False) or core_backs >= CT.MEM_AFTER or core <= 0):
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

    # ── remaining time (idea 4, 23.10.) ─────────────────────────────────────────
    eta_end: float = 0.0                      # epoch the run should end at, 0 = unknown

    def _set_eta(self, seconds: float):
        self.eta_end = time.time() + max(0.0, float(seconds))

    def _final_est(self, with_bench: bool, crit: str = "") -> float:
        """Seconds of the final tests in one go (+ the failed / first test before them) + the after
        benchmark."""
        cfg = self.config
        s = cfg.final_test_s + 10
        if cfg.hard_test:
            s += cfg.hard_test_min * 60 + 70
        if cfg.game_test:
            s += cfg.game_cool_s + cfg.game_transient_s + cfg.game_boost_s + 10
        if with_bench:
            s += cfg.final_bench_s + 15
        if crit.startswith("hard:"):
            s += 170
        elif crit.startswith("game"):
            s += cfg.game_cool_s + max(cfg.game_transient_s, cfg.game_boost_s) + 10
        elif crit == "bench":
            s += cfg.final_bench_s + 15
        return s + cfg.bench_s + 60            # the after benchmark + its cool-down

    def _run_safe(self):
        self._boot_profile = None             # the known-good profile is looked up per run
        self.eta_end = 0.0
        self._open_run_log()
        # The whole run is own GPU load for the watchdog — recorded in its session list, not
        # only through the tune log's name (an archived log took the run's driver events with
        # it: they counted as a game's afterwards).
        from core import gpu_watchdog as WD
        t_run = time.time()
        WD.own_load_started(t_run)
        from core.power_state import keep_awake
        keep_awake(True)          # no sleep / screen-off in the middle of a step
        live_done = threading.Event()
        self._last_tick = self._last_activity = time.monotonic()
        threading.Thread(target=self._live_loop, args=(live_done,), daemon=True).start()
        threading.Thread(target=self._stall_loop, args=(live_done,), daemon=True).start()
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
            WD.record_own_load(t_run, time.time())
            self._close_run_log()

    # Minimum average GPU load during the baseline for a meaningful test.
    MIN_GPU_LOAD_PCT = 70.0

    def _run(self):
        cfg     = self.config
        mode    = cfg.mode
        stress  = StressTester(self.monitor, self.cr, stop_event=self._stop)
        stress.companion = "encode" if cfg.encoder_companion else None
        self._comp_noted = False
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
        self._start_cool()
        if self._stop.is_set():
            return

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
            q_stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 13, 2, ref=True)
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

            result = self._srun(stress, cfg.step_test_s, cfg.max_temp_c, on_tick=_tick1,
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

        try:
            q_gpu = self.monitor.read().name or ""
        except Exception:
            q_gpu = ""
        best_core = self._learned_quick(best_core, q_gpu)

        # ── Final Test ─────────────────────────────────────────────────────────
        # Verify the EXACT configuration that will be saved — including the
        # Stage-4 memory OC. If it fails, take one
        # step back and run the final test again (it used to save an UNTESTED
        # "conservative" profile and stop).
        self._set_state(TunerState.FINAL_TEST)
        attempt, retries_used, core_backs = 1, [], 0
        game_top_mv = 0.0             # the game test's boost voltage: the Quick curve is flat from it
        crit = self._first_check()    # fail fast: the harshest test first, after a failure the failed one

        def q_profile(m: int) -> dict:
            return {"name": T("Kandidat", "candidate"), "core_offset_mhz": best_core, "mem_offset_mhz": m,
                    "power_limit_pct": best_pwr}
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
            self._set_eta(self._final_est(False, crit if crit != "verify" else "")
                          - (0 if (q_stock is not None and q_stock.passed) else cfg.bench_s + 60))
            self._apply(best_core, best_mem_offset, best_pwr)
            time.sleep(2)
            final = None
            if crit and crit != "verify":        # the compute check opens the full set anyway
                name = self._stage_name(crit)
                if attempt == 1:
                    self._log(T(f"  Lastwechsel-Check: zuerst {name} (150 s) — dort scheitern knappe Einstellungen "
                                f"am ehesten", f"  Load-change check: first {name} (150 s) — where tight "
                                f"settings fail first"))
                else:
                    self._log(T(f"  Zuerst {name} — dort scheiterte der letzte Versuch",
                                f"  First {name} — where the last try failed"))
                final = self._run_stage(stress, crit, 75, q_profile(best_mem_offset))
                if final is None:
                    return
                if final.passed:
                    self._log(T(f"  ✓ {name} bestanden — jetzt alle Endtests am Stück",
                                f"  ✓ {name} passed — now every final test in one go"))
            game_top_mv = 0.0
            if final is None or final.passed:
                out = self._final_set(stress, False, 75, q_profile(best_mem_offset))
                if out is None:   # aborted mid-step: don't act on it
                    return
                final, _verify, game, _hard = out
                if final.passed and game is not None:
                    game_top_mv = float(game.steady_voltage_mv or 0)
            if final.passed:
                break
            tdr_note = " [TDR!]" if final.tdr_detected else ""
            if final.crash_detected or final.tdr_detected or final.compute_error:
                self._crash_pause()
            back, cause = None, ""
            if attempt <= self.FINAL_RETRIES:
                self._log(T(f"  Endtest ✗{tdr_note}  {self._fail_reason(final)}",
                            f"  Final test ✗{tdr_note}  {self._fail_reason(final)}"), "warning")
                got = self._cross_check(stress, final, best_mem_offset,
                                        lambda: self._apply(best_core, 0, best_pwr), 75, q_profile(best_mem_offset))
                if got is None:
                    return
                cause = got[0]
                if cause == "core" and best_core > 0:
                    self._learned_book_quick(q_gpu, best_core, got[1], self._stage_name(final.stage))
                measured = cause == "mem" and not final.mem_fault
                final.mem_fault = final.mem_fault or cause == "mem"
                back = self._final_backoff(cfg, final, attempt, best_core, best_mem_offset, best_pwr,
                                           core_backs=0 if cfg.final_cross_check else core_backs)
                if back is not None:
                    core_backs = core_backs + 1 if back[0] != best_core else 0
                if back is not None and measured and back[1] != best_mem_offset:
                    back = back[:3] + (back[3] + T(" (Ursache Speicher: ohne Speicher-Übertaktung bestanden)",
                                                   " (the memory is the cause: passed without the memory "
                                                   "overclock)"),)
            if back is None:
                self._log(T(f"  Endtest ✗{tdr_note}  {self._fail_reason(final)} — nichts mehr zurückzunehmen",
                            f"  Final test ✗{tdr_note}  {self._fail_reason(final)} — nothing left to take back"),
                          "warning")
                break
            best_core, best_mem_offset, best_pwr, what = back
            retries_used.append(what)
            crit = final.stage if cfg.final_fail_fast else ""
            self._set_state(TunerState.BACKOFF)
            nxt = (T(f"zuerst {self._stage_name(crit)}, dann alle Tests", f"first {self._stage_name(crit)}, "
                     f"then every test") if crit and crit != "verify" else T("alle Tests", "every test"))
            self._log(T(f"  → zurück: {what} → Endtest wird wiederholt ({nxt})",
                        f"  → back: {what} → final test again ({nxt})"), "warning")
            attempt += 1
            self._set_state(TunerState.FINAL_TEST)

        # The offset shifts the WHOLE curve — also the points above the highest voltage
        # any test reached (an RTX 4080: 1075 → 1100 mV at +134 MHz, untested; a light
        # load can boost there). Flat from the game test's boost voltage instead: below
        # it exactly what was tested, above it lower than tested.
        quick_cap = None
        if final.passed and game_top_mv > 0:
            quick_cap = self._quick_cap(best_core, game_top_mv)
            if quick_cap:
                pts, cap_mv = quick_cap
                ok, err = self._ab_write(TuneProfile(name="__quick_cap__", core_offset_mhz=best_core,
                                                     mem_offset_mhz=best_mem_offset, power_limit_pct=best_pwr,
                                                     curve_points=pts, curve_cap_mv=cap_mv))
                if ok:
                    self._log(T(f"  Kurve flach ab {cap_mv} mV (höchste Spannung im Spiel-Endtest): darüber "
                                f"nichts Ungetestetes",
                                f"  Curve flat from {cap_mv} mV (the game test's highest voltage): nothing "
                                f"untested above it"))
                else:
                    quick_cap = None
                    self._apply(best_core, best_mem_offset, best_pwr)
                    self._log(T(f"  Kurve flach ab der Höchstspannung nicht schreibbar ({err}) — Profil mit "
                                f"Takt-Offset", f"  Curve flat from the top voltage not writable ({err}) — "
                                f"profile with the clock offset"), "warning")

        q_after = None
        if final.passed and q_stock is not None and q_stock.passed:
            q_after = self._bench(stress, cfg.bench_s, T("Nachher-Benchmark", "After benchmark"), 98, 1,
                                  cool=True)
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
                    + (T(f"flach ab {quick_cap[1]} mV | ", f"flat from {quick_cap[1]} mV | ") if quick_cap else "") +
                    f"MaxTemp {final.max_temp:.0f}°C | "
                    f"AvgVolt {final.avg_voltage_mv:.0f}mV | Score {score}/100"
                ),
                created_at=datetime.now().isoformat(),
                gpu_name=gpu_name,
            )
            if quick_cap:
                profile.curve_points, profile.curve_cap_mv = quick_cap
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

    def _start_temp(self) -> float:
        try:
            return float(self.monitor.read().temp or 0)
        except Exception:
            return 0.0

    def _quick_cap(self, core: int, top_mv: float):
        """Quick mode: the offset curve, flat from top_mv -> (curve_points, cap_mv) or None
        (no Afterburner curve). One point is enough: below the highest measured point the
        curve keeps the smallest offset there is — here the one offset of the whole curve."""
        getter = getattr(self.ab, "base_curve", None)
        if getter is None:
            return None
        try:
            curve, _src = getter(self.config.ab_slot)
            if curve is None:
                return None
            p = curve.lock_point(top_mv)
        except Exception:
            return None
        if not p or p.voltage_mv <= 0:
            return None
        mv = int(round(p.voltage_mv))
        return [[mv, int(round(p.base_mhz + core))]], mv

    def _start_cool(self):
        """Round 33: every tune starts at the same temperature — at stock, idle until the card is
        at most start_cool_c, at most start_cool_max_s: the stock run (the reference of every gain)
        always starts from the same temperature. (The highest voltage reached at stock moved between
        1070 and 1075 mV warm or cool alike — jitter, not temperature.)"""
        cfg = self.config
        target, limit = float(cfg.start_cool_c or 0), int(cfg.start_cool_max_s or 0)
        t = self._start_temp()
        if target <= 0 or limit <= 0 or not t or t <= target:
            return
        T = CT.T
        self._log(T(f"Abkühlen vor dem Start: {t:.0f} → {target:.0f} °C (jeder Tune startet gleich warm)",
                    f"Cooling down before the start: {t:.0f} → {target:.0f} °C (every tune starts equally warm)"))
        t0 = time.time()
        while time.time() - t0 < limit:
            if self._stop.wait(1.0):
                return
            t = self._start_temp()
            self._progress(4, T(f"Abkühlen vor dem Start: {t:.0f} → {target:.0f} °C",
                                f"Cooling down before the start: {t:.0f} → {target:.0f} °C"))
            if t and t <= target:
                return
        self._log(T(f"  nach {limit} s noch {t:.0f} °C — der Tune startet trotzdem",
                    f"  still {t:.0f} °C after {limit} s — the tune starts anyway"), "warning")

    def _cool_down(self, label: str, prog: int):
        """Before a comparison benchmark: idle until the card is back at the stock run's
        starting temperature (+ bench_cool_tol_c), at most bench_cool_max_s — the same
        start for every run (a warm card clocks a bin lower and draws more)."""
        cfg = self.config
        ref = getattr(self, "_bench_ref_temp", 0.0)
        t = self._start_temp()
        if not ref or not t or t <= ref + cfg.bench_cool_tol_c:
            return
        T = CT.T
        target = ref + cfg.bench_cool_tol_c
        self._log(T(f"  Abkühlen auf {target:.0f} °C (Start der Standard-Messung) — jetzt {t:.0f} °C",
                    f"  Cooling down to {target:.0f} °C (start of the stock run) — now {t:.0f} °C"))
        t0 = time.time()
        while time.time() - t0 < cfg.bench_cool_max_s:
            if self._stop.wait(1.0):
                return
            t = self._start_temp()
            self._progress(prog, T(f"{label}: abkühlen {t:.0f} → {target:.0f} °C",
                                   f"{label}: cooling {t:.0f} → {target:.0f} °C"))
            if t and t <= target:
                return
        self._log(T(f"  nach {cfg.bench_cool_max_s} s noch {t:.0f} °C — Messung startet trotzdem",
                    f"  still {t:.0f} °C after {cfg.bench_cool_max_s} s — measuring anyway"), "warning")

    def _bench(self, stress: "StressTester", seconds: int, label: str, prog: int,
               prog_span: int = 0, plausible: bool = True, ref: bool = False,
               cool: bool = False) -> Optional["CT.Candidate"]:
        """One benchmark run with the settings applied right now -> Candidate
        (score, average power and clock while loaded, highest temperature,
        voltage right before the end), or None when the tune was aborted.
        FurMark 2's own score when it is set up (cfg.furmark_path), else the
        stress worker's measured work rate (TFLOPS) under full load. Too hot ends
        the run (thermal); FurMark dying, hanging, printing no score or a driver
        reset / GPU error counts as unstable — then the driver gets
        cfg.crash_pause_s to recover. A run that ended far too early or scored
        far below stock is `invalid`: after a crash in the live run FurMark ran
        ~10 of 60 s and printed 398 instead of ~7200 points.
        ref: the stock run — its starting temperature is the reference; cool: a
        comparison run — first back to that temperature (_cool_down)."""
        cfg = self.config
        if ref:
            self._bench_ref_temp = self._start_temp()
        elif cool:
            self._cool_down(label, prog)
            if self._stop.is_set():
                return None
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
                # a normal rate for the time it ran: FurMark was ended (its window closed), the
                # driver is fine — live 23.10. (17 of 300 s) the message said "restart the PC"
                c.closed = bool(stock_rate and c.score / ran >= stock_rate * 0.5)
                c.ran_s = ran
            elif stock_rate and c.score / max(seconds, 1) < stock_rate * 0.5:
                c.invalid = True
                c.note = CT.T(f"nur {c.score:.0f} Punkte — weniger als halb so viel wie Standard",
                              f"only {c.score:.0f} points — less than half of stock")
            if c.invalid:
                c.passed, c.unstable = False, True
        if c.invalid and c.closed and not getattr(self, "_closed_retry", False) and not self._stop.is_set():
            # FurMark ended at a normal points rate: its window was closed — the run once more
            # instead of ending the tune (live 23.10. that ended 1.5 h of tuning)
            self._log(CT.T(f"  {label}: FurMark wurde nach {c.ran_s:.0f} s beendet (Fenster geschlossen?) — "
                           f"der Lauf wird wiederholt. Die FurMark-Fenster bitte offen lassen.",
                           f"  {label}: FurMark ended after {c.ran_s:.0f} s (window closed?) — the run is "
                           f"repeated. Please leave the FurMark windows open."), "warning")
            self._closed_retry = True
            try:
                return self._bench(stress, seconds, label, prog, prog_span, plausible, ref, cool)
            finally:
                self._closed_retry = False
        if c.unstable and not c.invalid:
            self._crash_pause()
        return c

    def _crash_pause(self):
        """After a crash the driver needs a moment: right after the live crash
        the next FurMark runs ended early with nonsense scores."""
        pause = int(getattr(self.config, "crash_pause_s", 0) or 0)
        # one pause per crash: the game test pauses after its failure, the final test's step
        # back would pause a second time right after (live 19.10.: twice 20 s)
        if time.time() - getattr(self, "_paused_at", 0.0) < 5:
            return
        if pause > 0 and not self._stop.is_set():
            self._log(CT.T(f"  Pause {pause} s — der Treiber erholt sich nach dem Absturz",
                           f"  {pause} s pause — the driver recovers from the crash"))
            self._stop.wait(pause)
            self._paused_at = time.time()

    def _reset_pause(self):
        """After a driver reset in the point search: reset_pause_s before the next step."""
        pause = int(getattr(self.config, "reset_pause_s", 0) or 0)
        if pause > 0 and not self._stop.is_set():
            self._log(CT.T(f"      Pause {pause} s — der Treiber erholt sich nach dem Reset",
                           f"      {pause} s pause — the driver recovers from the reset"))
            self._stop.wait(pause)

    def _test_point(self, stress: "StressTester", mv: int, mhz: int, base_mhz: float,
                    label: str, prog: int) -> "CT.PointTest":
        """One search step: the curve flat from `mv` at `mhz` (the GPU can't go
        past that point), then the boost load — light enough to stay below the
        power limit, so the GPU sits exactly on that point — with every result
        checked. Passed only counts when the GPU really ran at the point."""
        cfg = self.config
        after_reset, self._after_reset = getattr(self, "_after_reset", False), False
        self._apply_vf(0, mv, mhz, 0)
        time.sleep(2)
        off = mhz - base_mhz

        def tick(e, d, s):
            self._progress(prog, f"{label}: {mv} mV → {mhz} MHz ({off:+.0f}) | {e}/{d}s | "
                                 f"{s.temp}°C | {s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz")
            self._tick(s)

        trans = int(cfg.point_transient_s or 0)
        mode = "boost"
        if 0 < trans < cfg.step_test_s:
            mode = "boost_trans"
            try:
                stress.split_s = max(10, cfg.step_test_s - trans)
            except AttributeError:             # a test's stand-in without it
                pass
        r = self._srun(stress, cfg.step_test_s, cfg.max_temp_c, on_tick=tick, mode=mode)
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
            if r.tdr_detected:
                # The driver reset itself: it needs time. Live (19.10.) the next step, 5 s
                # later, failed at a clock that had passed before.
                self._reset_pause()
                self._after_reset = True
            else:
                time.sleep(5 if r.crash_detected else 1)   # let the driver settle
                if after_reset and not self._stop.is_set():
                    # the first step after a reset failed: once more after the pause — a failure
                    # that only came from the reset must not lower the point
                    self._log(CT.T("      direkt nach dem Treiber-Reset — wird nach einer Pause einmal "
                                   "wiederholt", "      right after the driver reset — once more after "
                                   "a pause"))
                    self._reset_pause()
                    return self._test_point(stress, mv, mhz, base_mhz, label, prog)
        return CT.PointTest(passed, reached, r.tdr_detected or r.hang_detected,
                            "" if passed else self._fail_reason(r),
                            r.steady_voltage_mv, r.avg_core_mhz)

    # Rundum-Tuner safety limits (after the first live run, see _mem_stage_full)
    CURVE_CHECK_TRIES  = 3      # curve check: up to 2 step-backs
    CANDIDATE_BACKOFFS = 3      # crashed candidates: up to 3 step-backs

    @staticmethod
    def _invalid_msg(c: "CT.Candidate") -> str:
        if getattr(c, "closed", False):
            return CT.T(f"Benchmark vorzeitig beendet ({c.note}, mit normaler Punktrate — FurMark-Fenster "
                        f"geschlossen?). Kein Profil gespeichert, GPU auf Standard: den Tune neu starten und "
                        f"die FurMark-Fenster währenddessen nicht schließen.",
                        f"Benchmark ended early ({c.note}, at a normal points rate — FurMark window "
                        f"closed?). No profile saved, GPU back to stock: start the tune again and leave the "
                        f"FurMark windows open while it runs.")
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

    def _game_test(self, stress: "StressTester", prog: int, modes: tuple = ("transient", "boost")
                   ) -> Optional[StressResult]:
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
        parts_de, parts_en = [f"{cfg.game_cool_s} s abkühlen"], [f"{cfg.game_cool_s} s cool-down"]
        if "transient" in modes:
            parts_de.append(f"{cfg.game_transient_s // 60} min Lastwechsel")
            parts_en.append(f"{cfg.game_transient_s // 60} min load changes")
        if "boost" in modes:
            parts_de.append(f"{cfg.game_boost_s // 60} min Boost-Punkt")
            parts_en.append(f"{cfg.game_boost_s // 60} min boost point")
        self._log(T("Spiel-Endtest: " + ", ".join(parts_de), "Game test: " + ", ".join(parts_en)))
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
            if secs <= 0 or mode not in modes:
                continue

            def tick(e, d, s, n=name):
                self._progress(prog, T(f"Spiel-Endtest ({n}): {e}/{d}s | {s.temp}°C | "
                                       f"{s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz",
                                       f"Game test ({n}): {e}/{d}s | {s.temp}°C | "
                                       f"{s.voltage_mv:.0f} mV | {s.core_mhz:.0f} MHz"))
                self._tick(s)
            last = self._srun(stress, secs, cfg.max_temp_c, on_tick=tick, mode=mode)
            if self._stop.is_set():
                return None
            last.stage = f"game:{mode}"
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

    def _srun(self, stress: "StressTester", *args, **kw) -> StressResult:
        """A stability step with the companion load next to it (round 33); said once when the
        encoder can't run on this PC."""
        r = stress.run(*args, companion=True, **kw) if getattr(stress, "companion", None) else stress.run(*args, **kw)
        if stress.companion and stress.companion_off and not getattr(self, "_comp_noted", False):
            self._comp_noted = True
            self._log(CT.T(f"  Encoder-Last nicht möglich ({stress.companion_off}) — die Schritte laufen ohne sie",
                           f"  Encoder load not possible ({stress.companion_off}) — the steps run without it"),
                      "warning")
        return r

    def _hard_test(self, prog: int, profile: dict, only: str = "") -> Optional[StressResult]:
        """Round 33 — the hardness test on the settings to be saved (applied now): 3D, the
        video encoder, compute and memory at once (core/hardness_test.py). only: one phase on its
        own (its key). -> a StressResult the final test's step back understands (the failure's
        voltage in last_voltage_mv, the phase in .stage), None = aborted."""
        from core.hardness_test import PHASE_S, HardnessTest
        cfg = self.config
        T = CT.T
        minutes = PHASE_S / 60 if only else cfg.hard_test_min
        if not only:
            self._log(T(f"Härtetest: {cfg.hard_test_min:.0f} min mehrere Lasten zugleich — 3D, Video-Encoder "
                        f"(wie Aufnahme / Stream), Rechnen, Speicher",
                        f"Hardness test: {cfg.hard_test_min:.0f} min of several loads at once — 3D, the video "
                        f"encoder (like recording / streaming), compute, memory"))
        levels = {"warning": "warning", "error": "error"}

        def on_log(text, tag):
            if tag != "dim":                    # the 10-s value lines stay in hard_*.log
                self._log("  " + text, levels.get(tag, "info"))
        try:
            gpu = self.monitor.read().name or ""
        except Exception:
            gpu = ""
        ht = (getattr(self, "hardness_factory", None) or HardnessTest)(
                          self.monitor.read, self._log_dir, minutes=minutes, only=(only,) if only else None,
                          furmark_path=cfg.furmark_path, max_temp=cfg.max_temp_c, profile=profile,
                          stop_event=self._stop, gpu_name=gpu, record_field=False, on_log=on_log,
                          on_progress=lambda pct, text: self._progress(prog, T("Härtetest", "Hardness test")
                                                                       + f" {pct} %: {text}"))
        r = ht.run()
        if self._stop.is_set():
            return None
        if r.aborted and r.kind == "stopped" and not getattr(self, "_hard_retry", False):
            # FurMark closed by hand: the hardness test once more before it is given up
            self._log(T("  FurMark wurde geschlossen — der Härtetest wird wiederholt. Die FurMark-Fenster bitte "
                        "offen lassen.", "  FurMark was closed — the hardness test is repeated. Please leave the "
                        "FurMark windows open."), "warning")
            self._hard_retry = True
            try:
                return self._hard_test(prog, profile, only)
            finally:
                self._hard_retry = False
        key = getattr(r, "phase_key", "") or only
        res = StressResult(passed=r.passed, max_temp=r.peak_temp, max_core_mhz=r.max_mhz,
                           steady_voltage_mv=r.max_mv, abort_reason=r.reason,
                           stage=f"hard:{key}" if key else "hard")
        if r.aborted:                            # FurMark closed by hand: no verdict either way
            self._log(T("  Härtetest nicht abgeschlossen — das Profil wird ohne ihn gespeichert",
                        "  Hardness test not finished — the profile is saved without it"), "warning")
            res.passed = True
            res.aborted = True
        elif r.unstable:
            res.crash_detected = True
            res.compute_error = r.kind in ("compute", "frame")
            res.hang_detected = r.kind in ("hang", "stall")
            res.tdr_detected = r.kind == "driver"
            res.fault_mv = float((r.point or {}).get("mv") or 0)
            res.last_voltage_mv = res.fault_mv        # 0 = unknown: the step back takes the whole curve
            res.mem_fault = r.load == "mem"
        return res

    # ── final tests: one test on its own, all of them in one go, the cross-check ──────────────
    def _stage_name(self, key: str) -> str:
        """A final test's name in the log: "Rechenprüfung 120 s", "Härtetest-Phase „…“", …"""
        cfg = self.config
        T = CT.T
        if key == "bench":
            return T(f"FurMark {cfg.final_bench_s // 60} min", f"FurMark {cfg.final_bench_s // 60} min")
        if key == "verify":
            return T(f"Rechenprüfung {cfg.final_test_s} s", f"compute check {cfg.final_test_s} s")
        if key == "game:transient":
            return T("Spiel-Endtest Lastwechsel", "game test load changes")
        if key == "game:boost":
            return T("Spiel-Endtest Boost-Punkt", "game test boost point")
        if key.startswith("hard:"):
            from core.hardness_test import phase_name
            de, en = phase_name(key[5:])
            if de:
                return T(f"Härtetest-Phase „{de}“", f"hardness test phase '{en}'")
        return T("Härtetest", "hardness test") if key.startswith("hard") else key

    def _run_stage(self, stress: "StressTester", key: str, prog: int, profile: dict
                   ) -> Optional[StressResult]:
        """One final test on its own, on what is applied now. -> its result (.stage = key),
        None = aborted. key: bench | verify | game:transient | game:boost | hard | hard:<phase>."""
        cfg = self.config
        T = CT.T
        if key == "bench":
            c = self._bench(stress, cfg.final_bench_s, T("Endtest", "Final test"), prog, 12)
            if c is None:
                return None
            self._endurance = c                  # the report shows the last FurMark run of the final test
            note = self._invalid_msg(c) if c.invalid else (c.note or "")
            return StressResult(passed=bool(c.passed), crash_detected=bool(c.unstable),
                                tdr_detected="TDR" in note, throttle_hit=bool(c.thermal),
                                max_temp=float(getattr(c, "temp_c", 0) or 0), abort_reason=note,
                                last_voltage_mv=float(c.last_mv or 0), stage="bench",
                                invalid=bool(c.invalid))
        if key == "verify":
            def _tick_v(e, d, s):
                self._progress(prog + int(e / max(d, 1) * 6),
                               T(f"Rechen-Prüfung: {e}/{d}s | {s.temp}°C | {s.core_mhz:.0f} MHz",
                                 f"Compute check: {e}/{d}s | {s.temp}°C | {s.core_mhz:.0f} MHz"))
                self._tick(s)
            r = self._srun(stress, cfg.final_test_s, cfg.max_temp_c, on_tick=_tick_v, mode="mixed")
            if self._stop.is_set():
                return None
            r.stage = "verify"
            return r
        if key.startswith("game"):
            return self._game_test(stress, prog, (key[5:],) if ":" in key else ("transient", "boost"))
        if key.startswith("hard"):
            return self._hard_test(prog, profile, key[5:] if ":" in key else "")
        raise ValueError(key)

    def _final_set(self, stress: "StressTester", with_bench: bool, prog: int, profile: dict):
        """Every final test in one go on what is applied now, the most sensitive first (live
        23.10.: the compute check and the hardness test failed, the game test and the 5-min
        FurMark never — a failure comes after minutes, not after the long passing tests): the
        compute check, the hardness test, the game test, (FurMark). -> (result, verify, game,
        hard): result.passed when all passed, else the failed test's result; None = aborted."""
        cfg = self.config
        verify = self._run_stage(stress, "verify", prog, profile)
        if verify is None or not verify.passed:
            return None if verify is None else (verify, verify, None, None)
        hard = None
        if cfg.hard_test:
            hard = self._run_stage(stress, "hard", prog + 5, profile)
            if hard is None or not hard.passed:
                return None if hard is None else (hard, verify, None, hard)
        game = None
        if cfg.game_test:
            game = self._run_stage(stress, "game", prog + 10, profile)
            if game is None or not game.passed:
                return None if game is None else (game, verify, game, hard)
        if with_bench:
            res = self._run_stage(stress, "bench", prog + 15, profile)
            if res is None or not res.passed:
                return None if res is None else (res, verify, game, hard)
        return verify, verify, game, hard

    def _cross_check(self, stress: "StressTester", res: StressResult, mem: int, apply_mem0: Callable,
                     prog: int, profile: dict) -> Optional[tuple]:
        """A test failed with wrong results / a crash: the memory overclock or the core? The same
        test once more with the memory at stock — fails again: the core (the curve), passes: the
        memory. Instead of guessing (round 33 took the memory after three curve step-backs, live
        23.10. after two of them had already helped). -> (cause "mem" | "core" | "", the fault's
        voltage), None = aborted. Not unstable (too hot) / memory at stock: no test, cause known."""
        cfg = self.config
        T = CT.T
        unstable = bool(res.crash_detected or res.tdr_detected or res.compute_error)
        mv = float(res.last_voltage_mv or 0)
        if not unstable:
            return "", mv
        if res.mem_fault:
            return "mem", mv
        if mem <= 0 or not cfg.final_cross_check or not res.stage:
            return "core", mv
        name = self._stage_name(res.stage)
        self._log(T(f"  Ursache prüfen: {name} noch einmal mit Speicher +0 MHz (Kern-Einstellung gleich)",
                    f"  Finding the cause: {name} once more with memory at +0 MHz (same core setting)"))
        self._crash_pause()
        apply_mem0()
        time.sleep(2)
        d = self._run_stage(stress, res.stage, prog, dict(profile, mem_offset_mhz=0))
        if d is None:
            return None
        if d.passed:
            self._log(T("  → ohne Speicher-Übertaktung bestanden: Ursache ist der Speicher",
                        "  → passed without the memory overclock: the memory is the cause"))
            return "mem", mv
        d_unstable = bool(d.crash_detected or d.tdr_detected or d.compute_error)
        if d_unstable:
            self._crash_pause()
        mv2 = float(d.last_voltage_mv or 0) or mv
        self._log(T("  → auch ohne Speicher-Übertaktung: Ursache ist die Kern-Einstellung"
                    + (f" (bei {mv2:.0f} mV)" if mv2 else ""),
                    "  → fails without the memory overclock too: the core setting is the cause"
                    + (f" (at {mv2:.0f} mV)" if mv2 else "")), "warning")
        return "core", mv2

    @staticmethod
    def _goal_after(goal: str, retries: list, stock, after) -> str:
        """Idea 3 (23.10.): the final tests' step-backs lower the curve AFTER the variant was picked
        by its goal — the after benchmark shows whether the goal still holds. -> a note, "" = fine."""
        T = CT.T
        if not retries or not stock or not after or not after.score or not stock.score:
            return ""
        perf = after.score / stock.score * 100
        eff = (after.per_watt / stock.per_watt * 100) if stock.per_watt and after.per_watt else 0.0
        if goal == "efficiency" and perf < 99.0:
            return T(f"Nach den Rücknahmen schafft das Profil {perf:.1f} % der Standard-Leistung — unter den 99 %, "
                     f"die „Effizienz“ verlangt (Effizienz {eff - 100:+.1f} %). Mehr Leistung: Ziel „Ausgewogen“.",
                     f"After the step-backs the profile reaches {perf:.1f} % of stock performance — below the "
                     f"99 % 'Efficiency' asks for (efficiency {eff - 100:+.1f} %). More performance: goal "
                     f"'Balanced'.")
        if goal == "balanced" and (perf <= 100.0 or (eff and eff <= 100.0)):
            return T(f"Nach den Rücknahmen liegt das Profil nicht mehr in beidem über Standard (Leistung "
                     f"{perf - 100:+.1f} %, Effizienz {eff - 100:+.1f} %).",
                     f"After the step-backs the profile is no longer above stock in both (performance "
                     f"{perf - 100:+.1f} %, efficiency {eff - 100:+.1f} %).")
        return ""

    def _learned_quick(self, core: int, gpu: str) -> int:
        """Quick mode: the offset no point that failed a final test before can reach (learned limits)."""
        from core import learned_limits as LL
        learned = LL.load(self._log_dir, gpu) if gpu else {}
        getter = getattr(self.ab, "base_curve", None)
        if not learned or getter is None:
            return core
        try:
            curve, _src = getter(self.config.ab_slot)
            limits = [(mv, int(e["fail_mhz"]) - LL.STEP_MHZ - int(round(curve.lock_point(mv).base_mhz)))
                      for mv, e in learned.items()]
        except Exception:
            return core
        mv, allowed = min(limits, key=lambda x: x[1])
        if allowed >= core:
            return core
        new = max(0, allowed)
        self._log(CT.T(f"  Gelernt aus früheren Endtests: {mv} mV scheiterte schon einmal einen Schritt höher — "
                       f"Takt-Offset +{core} → +{new} MHz",
                       f"  Learned from earlier final tests: {mv} mV failed one step higher before — clock "
                       f"offset +{core} → +{new} MHz"))
        return new

    def _learned_book_quick(self, gpu: str, core: int, fault_mv: float, test: str):
        """Quick mode: a core failure of a final test booked on the curve point it ran at."""
        from core import learned_limits as LL
        getter = getattr(self.ab, "base_curve", None)
        if not gpu or not fault_mv or getter is None:
            return
        try:
            curve, _src = getter(self.config.ab_slot)
            p = curve.lock_point(fault_mv)
            LL.record(self._log_dir, gpu, int(round(p.voltage_mv)), int(round(p.base_mhz + core)), test)
        except Exception:
            pass

    def _first_check(self) -> str:
        """The test the final tests start with (fail fast): the hardness test's harshest phase —
        3D + encoder + verified bursts at the top clock, where tight curves failed live — "" =
        straight to the full set."""
        cfg = self.config
        if not (cfg.final_fail_fast and cfg.hard_test and cfg.load_check_phase):
            return ""
        return f"hard:{cfg.load_check_phase}"

    def _curve_fail(self, msg: str):
        """End a run without a profile (Rundum, or a memory stage where even +0
        fails): log, back to stock, error state."""
        self._log(msg, "error")
        self._reset_locked()
        if self.cr:
            self.cr.clear_tuning_flag()
        self._progress(100, "✗ " + msg.split(" — ")[0])
        self._set_state(TunerState.ERROR)

    # The card's minimum voltage under the boost load (an RTX 4080: ~920 mV) — found by the
    # first point it could not reach; remembered per GPU next to the tune logs, so the next
    # tune plans its points down to it instead of testing one it never reaches.
    def _floor_file(self) -> str:
        return os.path.join(self._log_dir, "gpu_floor.json")

    def _known_floor(self, gpu: str) -> float:
        if not gpu:
            return 0.0
        try:
            with open(self._floor_file(), encoding="utf-8") as f:
                d = json.load(f)
            v = float((d.get(gpu) or {}).get("floor_mv") or 0)
            return v if 300 <= v <= 1300 else 0.0
        except (OSError, ValueError, TypeError, AttributeError):
            return 0.0

    def _save_floor(self, gpu: str, mv: float):
        from core import safe_json
        path = self._floor_file()
        try:                                   # never write over a file that could not be read
            d = safe_json.read(path, {}, strict=True)
        except safe_json.Unreadable:
            return
        if not isinstance(d, dict):
            d = {}
        d[gpu] = {"floor_mv": int(round(mv)), "at": datetime.now().isoformat(timespec="seconds")}
        safe_json.write(path, d, ensure_ascii=True)

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
        self._after_reset = False             # no reset of an earlier run counts here
        de = CT.is_de()
        goal = cfg.goal if cfg.goal in CT.GOALS else "balanced"
        gname = CT.GOAL_TEXT[goal][0 if de else 1]

        # 1) the curve Afterburner applies offsets to
        getter = getattr(self.ab, "base_curve", None)
        curve, src = getter(cfg.ab_slot) if getter else (None, "Afterburner")
        if curve is None:
            raise TunerApplyError(T(f"Rundum-Tuner: {src}", f"All-round tuner: {src}"))
        points = curve.active_points()
        if not points:
            raise TunerApplyError(T("Rundum-Tuner: die V/F-Kurve in Afterburner hat keine aktiven Punkte",
                                    "All-round tuner: Afterburner's V/F curve has no active points"))
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
        try:
            gpu_key = self.monitor.read().name or ""
        except Exception:
            gpu_key = ""
        known_floor = self._known_floor(gpu_key)
        curve_mvs = [p.voltage_mv for p in points]
        anchors_mv = CT.anchor_voltages(curve_mvs, ceiling, cfg.curve_min_mv, cfg.curve_anchor_step_mv)
        if known_floor and known_floor > cfg.curve_min_mv:
            anchors_mv = CT.with_floor(anchors_mv, curve_mvs, known_floor, cfg.curve_anchor_step_mv)
            self._log(T(f"  Mindestspannung der Karte unter Last (vom letzten Tune gespeichert): "
                        f"{known_floor:.0f} mV — Messpunkte nur bis dorthin (tiefer läuft die Karte "
                        f"unter Last nicht)",
                        f"  The card's minimum voltage under load (saved by the last tune): "
                        f"{known_floor:.0f} mV — points only down to it (the card doesn't go lower "
                        f"under load)"))
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
        stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 17, 3, ref=True)
        if stock is None:
            return
        if not stock.passed and cfg.furmark_path and not stock.thermal:
            self._log(T(f"  FurMark lief bei Standard nicht ({stock.note}) — weiter mit dem internen "
                        f"Rechen-Benchmark",
                        f"  FurMark failed at stock ({stock.note}) — continuing with the internal "
                        f"compute benchmark"), "warning")
            cfg.furmark_path = ""
            stock = self._bench(stress, cfg.bench_s, T("Standard-Benchmark", "Stock benchmark"), 17, 3, ref=True)
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
        mem_steps = (max(1, (cfg.mem_oc_max_mhz - cfg.mem_curve_start_mhz) // max(25, cfg.mem_curve_step_mhz) + 1)
                     if cfg.mem_stage else 0)
        rest_after_pts = (40 + mem_steps * (cfg.step_test_s + 15) + 6 * (cfg.bench_s + 20)
                          + self._final_est(True, self._first_check()))
        per_pt = 4.5 * (cfg.step_test_s + 9) + 5
        t_pts = time.time()
        self._set_eta(len(anchors_mv) * per_pt + rest_after_pts)
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
            if i > 1:                           # the points so far tell the time per point
                per_pt = (time.time() - t_pts) / (i - 1)
                self._set_eta((len(anchors_mv) - i + 1) * per_pt + rest_after_pts)
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
        if floor_mv and gpu_key:
            self._save_floor(gpu_key, floor_mv)
            if abs(floor_mv - (known_floor or 0)) >= 1:
                self._log(T(f"  Mindestspannung der Karte unter Last: {floor_mv:.0f} mV — für den nächsten "
                            f"Tune gespeichert (Messpunkte nur bis dorthin)",
                            f"  The card's minimum voltage under load: {floor_mv:.0f} mV — saved for the "
                            f"next tune (points only down to it)"))
        # where games hung on this card before (GPU watchdog, seen live): the same extra
        # margin as after a reset in the search
        from core import gpu_watchdog as WD
        field_mv = WD.field_voltages(self._log_dir, gpu_key) if gpu_key else []
        CT.apply_margins(results, cfg.curve_safety_mhz, cfg.curve_safety_top_mhz,
                         cfg.curve_reset_extra_mhz, field_mv=field_mv)
        near = [r.mv for r in results if getattr(r, "field_fault", False) and r.best_mhz]
        if near:
            self._log(T(f"  Im Spiel gab es auf dieser Karte schon GPU-Hänger bei {', '.join(map(str, field_mv))} mV "
                        f"— dort +{cfg.curve_reset_extra_mhz} MHz Sicherheit ({', '.join(map(str, near))} mV)",
                        f"  Games hung on this card before at {', '.join(map(str, field_mv))} mV — "
                        f"+{cfg.curve_reset_extra_mhz} MHz margin there ({', '.join(map(str, near))} mV)"))
        anchors = CT.curve_anchors(results)
        if not anchors:
            return self._curve_fail(T("Kein Spannungspunkt stabil messbar — kein Profil gespeichert",
                                      "No voltage point measurably stable — no profile saved"))
        self._log(T(f"Eigene Kurve (−{cfg.curve_safety_mhz} MHz Sicherheit, −{cfg.curve_safety_top_mhz} an "
                    f"den oberen Punkten, +{cfg.curve_reset_extra_mhz} nach GPU-Fehler/Hänger): ",
                    f"Own curve (−{cfg.curve_safety_mhz} MHz safety, −{cfg.curve_safety_top_mhz} at the top "
                    f"points, +{cfg.curve_reset_extra_mhz} after a GPU error / hang): ")
                  + ", ".join(f"{mv} mV → {f} MHz" for mv, f in sorted(anchors, reverse=True)))

        # 4b) Curve check — FurMark (heavy, the whole card) on the new curve with
        #     memory at stock. The points were searched with the light boost
        #     load; whatever FurMark still breaks is lowered HERE, before the
        #     memory is touched — so a later crash points at the memory.
        notes: list = []
        # what earlier final tests learned about this card (core/learned_limits.py): a point that
        # failed there starts one step below that clock — the load-change check confirms it
        from core import learned_limits as LL
        learned = LL.load(self._log_dir, gpu_key) if gpu_key else {}
        if learned:
            anchors, capped = LL.apply(anchors, learned)
            if capped:
                what = ", ".join(f"{mv} mV {a}→{b} MHz" for mv, a, b in capped)
                self._log(T(f"  Gelernt aus früheren Endtests (gemischte Last): {what} — dort scheiterte die Karte "
                            f"schon einmal einen Schritt höher",
                            f"  Learned from earlier final tests (mixed load): {what} — the card failed there "
                            f"one step higher before"))
                notes.append(T(f"Gelernt aus früheren Endtests: {what}", f"Learned from earlier final tests: {what}"))
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
        self._set_eta(rest_after_pts - 40)
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
                                68 + int(k / max(len(plan), 1) * 10), 2, cool=True)
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
                # fine search: the cap halfway to the neighbour (balanced / efficiency)
                first = CT.choose_candidate(goal, tested, stock)
                fine = CT.fine_cap(goal, first, tested, stock, cap_mvs, curve_mvs)
                if fine:
                    mid, lo, hi = fine
                    c = CT.Candidate("", mid, first.pwr_pct)
                    lbl = c.label(de)
                    self._log(T(f"  Feinsuche: {lbl} (zwischen {lo} und {hi} mV)",
                                f"  Fine search: {lbl} (between {lo} and {hi} mV)"))
                    self._apply_curve(anchors, c.cap_mv, mem, c.pwr_pct)
                    time.sleep(2)
                    b = self._bench(stress, cfg.bench_s, T(f"Feinsuche ({lbl})", f"Fine search ({lbl})"), 79, 1,
                                    cool=True)
                    if b is None:
                        return
                    if b.invalid:
                        return self._curve_fail(self._invalid_msg(b))
                    b.cap_mv, b.pwr_pct = c.cap_mv, c.pwr_pct
                    b.name = T(f"{lbl} (Feinsuche)", f"{lbl} (fine search)")
                    if b.unstable:
                        crashed = (b.name, b)
                    else:
                        tested.append(b)
                        if b.passed:
                            self._log(f"  {b.name}: {b.score:.0f} {unit}, Ø {b.power_w:.0f} W, "
                                      f"max. {b.temp_c:.0f} °C, {b.per_watt:.2f} {unit}/W")
                        else:
                            self._log(f"  {b.name}: ✗ {b.note}", "warning")
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
            rule = CT.rule_text(goal, tested, stock, de)
            self._log(T(f"  Gewählt für „{gname}“ ({rule}): {chosen.label(de)}",
                        f"  Chosen for '{gname}' ({rule}): {chosen.label(de)}"))
        cap, pwr = chosen.cap_mv, chosen.pwr_pct
        self._set_eta(self._final_est(True, self._first_check()))

        # 7) final test — only what passed it is saved. It starts with the hardness test's harshest
        #    phase (fail fast); a failure is cross-checked with the memory at stock (memory or
        #    curve?), stepped back there, and the next try starts with the test that failed —
        #    only when that passes do ALL tests run again, in one go.
        cur = list(anchors)
        attempt, retries, curve_backs = 1, [], 0
        causes, learned_now = [], []          # the cross-checks' answers, the points booked (report)
        verify: Optional[StressResult] = None
        hard = game = None
        crit = self._first_check()

        def profile_of(m: int) -> dict:
            return {"name": T("Kandidat", "candidate"),
                    "curve_points": [[int(mv), int(f)] for mv, f in sorted(cur)],
                    "curve_cap_mv": int(cap or 0), "mem_offset_mhz": m, "power_limit_pct": pwr}
        while True:
            self._set_state(TunerState.FINAL_TEST)
            tries = (T(f" | Versuch {attempt}/{self.FINAL_RETRIES + 1}",
                       f" | attempt {attempt}/{self.FINAL_RETRIES + 1}") if attempt > 1 else "")
            what_now = CT.Candidate("", cap, pwr).label(de)
            self._set_eta(self._final_est(True, crit if crit != "verify" else ""))
            self._log(T(f"Endtest: {what_now}, Mem+{mem}MHz | {bench_name} {cfg.final_bench_s}s + "
                        f"Rechen-Prüfung {cfg.final_test_s}s{tries}",
                        f"Final test: {what_now}, Mem+{mem}MHz | {bench_name} {cfg.final_bench_s}s + "
                        f"compute check {cfg.final_test_s}s{tries}"))
            self._apply_curve(cur, cap, mem, pwr)
            time.sleep(2)
            res = None
            if crit and crit != "verify":        # the compute check opens the full set anyway
                name = self._stage_name(crit)
                if attempt == 1:
                    self._log(T(f"  Lastwechsel-Check: zuerst {name} (150 s) — dort scheitern knappe Kurven "
                                f"am ehesten", f"  Load-change check: first {name} (150 s) — where tight "
                                f"curves fail first"))
                else:
                    self._log(T(f"  Zuerst {name} — dort scheiterte der letzte Versuch",
                                f"  First {name} — where the last try failed"))
                res = self._run_stage(stress, crit, 80, profile_of(mem))
                if res is None:
                    return
                if res.passed:
                    self._log(T(f"  ✓ {name} bestanden — jetzt alle Endtests am Stück",
                                f"  ✓ {name} passed — now every final test in one go"))
            if res is None or res.passed:
                out = self._final_set(stress, True, 80, profile_of(mem))
                if out is None:
                    return
                res, verify, game, hard = out
                if res.invalid:
                    return self._curve_fail(res.abort_reason)
            if res.passed:
                if hard is not None and not hard.aborted:
                    notes.append(T(f"Härtetest ({cfg.hard_test_min:.0f} min 3D + Video-Encoder + Rechnen/Speicher "
                                   f"zugleich): bestanden",
                                   f"Hardness test ({cfg.hard_test_min:.0f} min 3D + video encoder + "
                                   f"compute/memory at once): passed"))
                if game is not None:
                    notes.append(T(f"Spiel-Endtest ({cfg.game_cool_s} s abkühlen, {cfg.game_transient_s // 60} "
                                   f"min Lastwechsel, {cfg.game_boost_s // 60} min Boost-Punkt): bestanden",
                                   f"Game test ({cfg.game_cool_s} s cool-down, {cfg.game_transient_s // 60} "
                                   f"min load changes, {cfg.game_boost_s // 60} min boost point): passed"))
                endurance = self._endurance
                break
            if res.invalid:
                return self._curve_fail(res.abort_reason)
            why = self._fail_reason(res)
            unstable = bool(res.crash_detected or res.tdr_detected or res.compute_error)
            thermal = not unstable and (res.throttle_hit or res.max_temp >= cfg.max_temp_c)
            tdr_note = " [TDR!]" if res.tdr_detected else ""
            if unstable:
                self._crash_pause()
            if attempt > self.FINAL_RETRIES:
                return self._curve_fail(T(f"Endtest nicht bestanden ({why}), auch nach {len(retries)} "
                                          f"Rücknahme(n) — KEIN Profil gespeichert, GPU auf Standard",
                                          f"Final test failed ({why}), even after {len(retries)} "
                                          f"step-back(s) — NO profile saved, GPU back to stock"))
            self._log(T(f"  Endtest ✗{tdr_note}  {why}", f"  Final test ✗{tdr_note}  {why}"), "warning")
            got = self._cross_check(stress, res, mem, lambda: self._apply_curve(cur, cap, 0, pwr), 80,
                                    profile_of(mem))
            if got is None:
                return
            cause, crash_mv = got
            causes.append((self._stage_name(res.stage), cause))
            if cause == "core" and unstable and gpu_key:
                pt = LL.point_at(cur, crash_mv)
                if pt and LL.record(self._log_dir, gpu_key, pt[0], pt[1], self._stage_name(res.stage)):
                    learned_now.append((pt[0], pt[1], self._stage_name(res.stage)))
            mem_was = mem
            cur, mem, cap, pwr, what = CT.final_backoff(
                attempt, cur, mem, cap, pwr, unstable, thermal, cfg.curve_step_mhz, de, cap_mvs,
                crash_mv=crash_mv, mem_step=cfg.mem_curve_step_mhz, mem_fault=cause == "mem",
                window_mv=cfg.curve_anchor_step_mv,
                # without the cross-check: round 33's count (the memory after MEM_AFTER curve
                # step-backs in a row that did not help) — with it the cause is measured
                curve_backs=0 if cfg.final_cross_check else curve_backs,
                mem_why=T("Ursache Speicher: ohne Speicher-Übertaktung bestanden",
                          "the memory is the cause: passed without the memory overclock")
                if cause == "mem" and not res.mem_fault else "")
            curve_backs = curve_backs + 1 if (unstable and mem == mem_was) else 0
            retries.append(what)
            crit = res.stage if cfg.final_fail_fast else ""
            self._set_state(TunerState.BACKOFF)
            nxt = (T(f"zuerst {self._stage_name(crit)}, dann alle Tests", f"first {self._stage_name(crit)}, "
                     f"then every test") if crit and crit != "verify" else T("alle Tests", "every test"))
            self._log(T(f"  → zurück: {what} → Endtest wird wiederholt ({nxt})",
                        f"  → step back: {what} → final test again ({nxt})"), "warning")
            attempt += 1

        # The fair "after": the same short benchmark as the stock run — always at the very end, on
        # exactly what is saved (after every final test and step back), cooled down like the stock
        # run. The candidates' numbers above only pick the variant.
        after = self._bench(stress, cfg.bench_s, T("Nachher-Benchmark", "After benchmark"), 98, 1,
                            cool=True)
        if after is None:
            return
        if not after.passed:              # the profile passed the final test — keep it, say so
            notes.append(T(f"Nachher-Benchmark ✗ ({after.note}) — Vergleich vorher/nachher fehlt",
                           f"After benchmark ✗ ({after.note}) — no before/after comparison"))
            after = CT.Candidate(T("nicht gemessen", "not measured"))
        if causes:
            n_mem = sum(1 for _s, c in causes if c == "mem")
            n_core = sum(1 for _s, c in causes if c == "core")
            notes.append(T(f"Ursachen der Endtest-Fehler (gemessen, gleicher Test mit Speicher auf Standard): "
                           f"{n_core}× Kurve, {n_mem}× Speicher",
                           f"Causes of the final-test failures (measured, the same test with memory at stock): "
                           f"{n_core}× curve, {n_mem}× memory"))
        for mv, mhz, test in learned_now:
            notes.append(T(f"Gelernt: {mv} mV hielt {mhz} MHz in {test} nicht — der nächste Tune setzt den Punkt "
                           f"auf höchstens {mhz - LL.STEP_MHZ} MHz (vergessen: GPU-Seite, z. B. nach einer "
                           f"Reinigung)",
                           f"Learned: {mv} mV did not hold {mhz} MHz in {test} — the next tune sets the point "
                           f"to {mhz - LL.STEP_MHZ} MHz at most (forget it on the GPU page, e.g. after a "
                           f"cleaning)"))
        goal_note = self._goal_after(goal, retries, stock, after)
        if goal_note:
            notes.append(goal_note)
            self._log("  " + goal_note, "warning")

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
