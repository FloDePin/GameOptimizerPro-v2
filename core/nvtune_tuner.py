"""
GameOptimizerPro Auto-Tuner v2.1
Stage 1: Max stable core offset
Stage 2: Min stable power limit (indirect undervolt)
Final:   2-min verification
Features: TuneMode selector, crash recovery, TDR detection, per-step flag writing
"""

import time, threading, os, sys, subprocess, logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime
from pathlib import Path

from core.nvtune_core import GpuMonitor, AfterburnerController, TuneProfile, ProfileManager
from core.vf_curve    import VFCurveBuilder, get_builder_for_gpu


class TunerApplyError(RuntimeError):
    """A tuning step could not be applied — the tune must stop, not test it."""


class TuneMode(Enum):
    OC_ONLY   = "oc_only"    # Stage 1 only: core offset
    UV_ONLY   = "uv_only"    # Stage 2 only: power limit reduction
    OC_UV     = "oc_uv"      # Stages 1+2: core OC + power UV (current method)
    FULL      = "full"        # Stages 1+2+3+4: OC + V/F curve UV + Memory OC
    VF_ONLY   = "vf_only"    # Stage 3 only: V/F curve undervolt, no OC
    MEM_ONLY  = "mem_only"   # Stage 4 only: memory overclock


class TunerState(Enum):
    IDLE       = auto()
    BASELINE   = auto()
    STAGE1     = auto()    # Core offset OC
    STAGE2     = auto()    # Power limit UV (indirect)
    STAGE3     = auto()    # V/F curve UV (precise, via Afterburner)
    STAGE4     = auto()    # Memory OC
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
    # Stage 3: V/F curve undervolt
    vf_enabled:      bool = True       # Use V/F curve in FULL mode
    vf_step_mv:      int  = 25         # Voltage step (mV) per UV attempt
    vf_min_mv:       int  = 750        # Absolute floor (mV) — safety limit
    vf_step_test_s:  int  = 60         # Test duration per voltage step
    # Stage 4: Memory OC
    mem_oc_enabled:  bool = True       # Run memory OC in FULL mode
    mem_oc_step_mhz: int  = 50         # Memory step size
    mem_oc_max_mhz:  int  = 1000       # Max memory offset
    # Memory stage inside the OC / UV / OC+UV modes (GPU tab: "Speicher mit
    # übertakten") and the search precision of the memory stage.
    mem_stage:        bool = False
    mem_min_step_mhz: int  = 5
    # Stage 2: lowest power limit that costs at most this much performance
    # under full load (RTX 40: ~70-80 % PL costs only a few % in games).
    power_max_loss_pct: float = 3.0
    # Stage 4: GDDR6X retries failed transfers (EDC) instead of crashing — an
    # overclock past the limit LOSES bandwidth. Stop when it drops by more than this.
    # (45 s windows of the bandwidth load varied by 0.8 % on an RTX 4080.)
    mem_bw_drop_pct: float = 2.0


class StressTester:
    RAMP_S = 3            # ignore the worker's start-up for averages
    EXIT_COMPUTE_ERROR = 3  # _stress_worker.py: wrong result / CUDA error under load

    def __init__(self, monitor: GpuMonitor, crash_recovery=None,
                 stop_event: Optional[threading.Event] = None):
        self.monitor = monitor
        self.cr      = crash_recovery
        self.stop_event = stop_event   # set by AutoTuner.abort() -> end the step NOW
        self._proc: Optional[subprocess.Popen] = None
        self._metrics: dict = {"RATE": [], "BW": [], "ERR": []}
        self._t0 = 0.0

    def _worker_path(self):
        # Worker lives at project root, not in core/
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "_stress_worker.py"
        )

    def start(self, mode: str = "gemm"):
        wp = self._worker_path()
        self._metrics = {"RATE": [], "BW": [], "ERR": []}
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
            except:
                pass

    @staticmethod
    def _read_worker(proc, metrics: dict, t0: float):
        """Collect the worker's "RATE x" / "BW x" / "ERR n" lines. Always drains
        the pipe, so the worker can never block on a full stdout buffer."""
        try:
            for line in proc.stdout:
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

    def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except:
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
        samples = capped = 0

        self.start(mode)
        start = time.time()

        while True:
            # Abort must end the step immediately. Before, the step (and the
            # stress worker's 100 % load) ran on for up to a minute after
            # "Abort", and its result was then acted on.
            if self.stop_event is not None and self.stop_event.is_set():
                self.stop()
                result.aborted = True
                result.passed = False
                result.abort_reason = "Abgebrochen"
                return result

            elapsed = int(time.time() - start)
            if elapsed >= duration_s:
                break

            stats = self.monitor.read()
            temps.append(stats.temp)
            if stats.voltage_mv > 0:
                voltages.append(stats.voltage_mv)
            if elapsed >= self.RAMP_S:            # skip the worker's ramp-up
                clocks.append(stats.core_mhz)
                mem_clocks.append(float(getattr(stats, "mem_mhz", 0.0) or 0.0))
                usages.append(float(stats.gpu_usage or 0.0))
                samples += 1
                capped += bool(getattr(stats, "power_capped", False))

            if on_tick:
                try:
                    on_tick(elapsed, duration_s, stats)
                except:
                    pass

            if stats.temp >= max_temp:
                self.stop()
                result.abort_reason = f"Temp {stats.temp}°C >= limit {max_temp}°C"
                result.max_temp = stats.temp
                result.passed   = False
                return result

            # Only thermal / hardware slowdowns count. Running into the power
            # limit is normal GPU Boost behaviour under full load — counting it
            # (as before, with mislabelled bits) failed OC steps for no reason and
            # made the power-limit stage unable to lower anything.
            if getattr(stats, "throttle_protective", False):
                result.throttle_hit = True

            # Worker gone = GPU instability (exit 3: it saw a wrong result)
            if self._proc and self._proc.poll() is not None:
                result.crash_detected = True
                if self._proc.returncode == self.EXIT_COMPUTE_ERROR or self._metrics["ERR"]:
                    result.compute_error = True
                    result.abort_reason = "Rechenfehler unter Last (GPU instabil)"
                else:
                    result.abort_reason = "Stress worker crashed (GPU unstable)"
                break

            # TDR check every 10s
            if elapsed % 10 == 0 and elapsed > 0 and self.cr:
                if self.cr.check_tdr_since(seconds_back=15):
                    result.tdr_detected   = True
                    result.crash_detected = True
                    result.abort_reason   = "TDR (GPU driver timeout) detected"
                    break

            time.sleep(1.0)

        self.stop()

        result.max_temp     = max(temps) if temps else 0
        result.avg_temp     = round(sum(temps) / len(temps), 1) if temps else 0
        result.avg_core_mhz = round(sum(clocks) / len(clocks), 1) if clocks else 0
        result.avg_gpu_usage = round(sum(usages) / len(usages), 1) if usages else 0.0
        result.avg_mem_mhz  = round(sum(mem_clocks) / len(mem_clocks), 1) if mem_clocks else 0
        result.max_core_mhz = max(clocks) if clocks else 0
        result.power_capped_pct = round(100.0 * capped / samples, 1) if samples else 0.0
        result.avg_rate_tflops = self._avg("RATE")
        result.avg_bw_gbs   = self._avg("BW")
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
        if self._cb_progress:
            self._cb_progress(pct, msg)

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
        with self._ab_lock:
            self._safe_reset()
            if self.cr:
                try:
                    self.cr.clear_tuning_flag()
                except Exception:
                    pass
        self._set_state(TunerState.ABORTED)
        self._log("Aborted by user — GPU auf Standard zurückgesetzt", "warning")

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
            self.ab.write_and_apply(self.config.ab_slot, reset)
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
                ok, err = self.ab.write_and_apply(self.config.ab_slot, p)
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
            return "Thermische/Hardware-Drosselung"
        return "Crash" if r.crash_detected else "Unstable"

    # A failed final test is not the end: take one step back and run the final
    # test again — only a configuration that PASSED it is ever saved.
    FINAL_RETRIES = 4

    @staticmethod
    def _final_backoff(cfg: "TunerConfig", r: StressResult, attempt: int,
                       core: int, volt: int, mem: int, pwr: int):
        """One step back after failed final test number `attempt` (1-based).
        -> (core, volt, mem, pwr, what) or None when nothing is left to take back.
        Thermal failures lower the power limit first; instability (wrong results,
        crash, driver reset) takes back what is most likely at its edge: the V/F
        undervolt, then the core offset (found with 45-s steps, right at the edge),
        alternating with the memory offset (errors that slip past GDDR6X's error
        correction also show up as wrong results)."""
        unstable = r.compute_error or r.crash_detected or r.tdr_detected
        thermal = not unstable and (r.throttle_hit or r.max_temp >= cfg.max_temp_c)
        if thermal and pwr - cfg.power_step_pct >= cfg.power_min_pct:
            p2 = pwr - cfg.power_step_pct
            return core, volt, mem, p2, f"Power-Limit {pwr}→{p2} % (Temperatur)"
        if volt > 0:
            v2 = volt + cfg.vf_step_mv
            return core, v2, mem, pwr, f"V/F-Spannung {volt}→{v2} mV"
        mem_turn = attempt % 2 == 0 and mem > 0
        if core > 0 and not mem_turn:
            c2 = max(0, core - cfg.core_step_mhz)
            return c2, volt, mem, pwr, f"Core +{core}→+{c2} MHz"
        if mem > 0:
            m2 = mem // 2 if attempt < 4 and mem > 100 else 0
            return core, volt, m2, pwr, f"Speicher +{mem}→+{m2} MHz"
        if core > 0:
            c2 = max(0, core - cfg.core_step_mhz)
            return c2, volt, mem, pwr, f"Core +{core}→+{c2} MHz"
        if pwr < 100:
            p2 = min(100, pwr + cfg.power_step_pct)
            return core, volt, mem, p2, f"Power-Limit {pwr}→{p2} %"
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
        """
        Apply a V/F curve profile via Afterburner.
        This is Stage 3 — precise undervolt with flatline curve.
        """
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
            ok, err = self.ab.write_and_apply(self.config.ab_slot, p)
        if not ok:
            # Same rule as _apply(): an unapplied curve step must not be tested.
            raise TunerApplyError(f"V/F-Kurve: {err}")
        return ok

    def _run_safe(self):
        self._open_run_log()
        from core.power_state import keep_awake
        keep_awake(True)          # no sleep / screen-off in the middle of a step
        try:
            self._run()
        except TunerApplyError as e:
            self._log(f"Anwenden fehlgeschlagen — Tune abgebrochen: {e}", "error")
            self._set_state(TunerState.ERROR)
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
        except Exception as e:
            self._log(f"Tuner exception: {e}", "error")
            self._set_state(TunerState.ERROR)
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
        finally:
            keep_awake(False)
            self._close_run_log()

    # Minimum average GPU load during the baseline for a meaningful test.
    MIN_GPU_LOAD_PCT = 70.0

    def _run(self):
        cfg     = self.config
        mode    = cfg.mode
        stress  = StressTester(self.monitor, self.cr, stop_event=self._stop)

        self._log("═══════════════════════════════════════")
        self._log(f"  GameOptimizerPro Auto-Tune [{mode.value.upper().replace('_',' ')}]")
        self._log("═══════════════════════════════════════")
        try:
            self._log(f"GPU: {self.monitor.read().name}")
        except Exception:
            pass

        # ── Baseline ──────────────────────────────────────────────────────────
        self._set_state(TunerState.BASELINE)
        self._progress(5, "Measuring baseline (stock settings)...")
        self._apply(0, 0, 100)
        time.sleep(2)

        base = stress.run(
            cfg.baseline_s, cfg.max_temp_c,
            on_tick=lambda e, d, s: (
                self._progress(
                    5 + int(e / d * 10),
                    f"Baseline: {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                ),
                self._cb_tick(s) if self._cb_tick else None
            )
        )
        if self._stop.is_set(): return
        if not base.passed:
            self._log(f"Baseline FAILED: {base.abort_reason}", "error")
            self._set_state(TunerState.ERROR)
            if self.cr: self.cr.clear_tuning_flag()
            return

        # A stability test is only meaningful under real GPU load. The internal
        # stress worker loads the GPU only via 'cupy'; without it, it silently
        # burns the CPU instead and every OC/UV step would "pass" on an idle GPU.
        if base.avg_gpu_usage < self.MIN_GPU_LOAD_PCT:
            import importlib.util
            has_cupy = importlib.util.find_spec("cupy") is not None
            why = ("'cupy' ist nicht installiert — der Stress-Worker belastet dann nur die CPU."
                   if not has_cupy else
                   "Der Stress-Worker hat die GPU nicht ausgelastet.")
            self._log(
                f"Baseline: GPU-Auslastung nur Ø {base.avg_gpu_usage:.0f} % "
                f"(nötig ≥ {self.MIN_GPU_LOAD_PCT:.0f} %). {why} Ein OC/UV-Test ohne "
                f"GPU-Last würde instabile Werte als 'stabil' speichern — Tune abgebrochen.",
                "error")
            self._log("Lösung: 'pip install \"cupy-cuda12x[ctk]\"' (NVIDIA) ODER parallel eine "
                      "GPU-Last starten (z.B. FurMark im Stress-Tab) und den Tune neu starten.",
                      "warning")
            self._set_state(TunerState.ERROR)
            self._progress(0, f"Abgebrochen: keine GPU-Last (Ø {base.avg_gpu_usage:.0f} %)")
            self._reset_locked()
            if self.cr: self.cr.clear_tuning_flag()
            return

        self._log(
            f"Baseline OK | temp={base.avg_temp}°C | GPU-Last={base.avg_gpu_usage:.0f}% | "
            f"volt={base.avg_voltage_mv:.0f}mV | clk={base.avg_core_mhz:.0f}MHz"
            f"{self._perf_note(base)} | Power-Limit erreicht {base.power_capped_pct:.0f}% der Zeit"
        )
        # Baseline is our first "stable" point
        self._save_stable(0, 0, 100)

        if self._stop.is_set(): return

        # ── Stage 1: Core Clock Offset ─────────────────────────────────────────
        best_core = cfg.core_start_mhz
        ref_result = base          # last passing run at (best_core, 100 %) — Stage 2's yardstick

        if mode in (TuneMode.OC_ONLY, TuneMode.OC_UV, TuneMode.FULL):
            self._set_state(TunerState.STAGE1)
            self._log("Stage 1: Finding max stable core offset (adaptive stepping)...")
            self._progress(15, "Stage 1: Core clock optimization")

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
                    self._log(f"Stage 1: Hard limit +{cfg.core_max_mhz}MHz reached")
                    break

                self._apply(candidate, cfg.mem_offset_mhz, 100)
                time.sleep(2)

                sn_cap = step_n
                def _tick1(e, d, s, c=candidate, sn=sn_cap):
                    self._progress(
                        15 + int(min(sn / est_steps, 1.0) * 35),
                        f"Stage 1: +{c}MHz (step {cur_step}MHz) | "
                        f"{e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                    )
                    if self._cb_tick: self._cb_tick(s)

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
                    self._log(
                        f"  +{candidate}MHz ✓  step={cur_step}MHz  "
                        f"avg={result.avg_temp:.1f}°C  "
                        f"volt={result.avg_voltage_mv:.0f}mV  "
                        f"clk={result.avg_core_mhz:.0f}/{result.max_core_mhz:.0f}MHz"
                        f"{self._perf_note(result)}"
                    )
                    # After a success, try to push a little further
                    # Step stays the same unless we've been reducing it
                else:
                    tdr_note = " [TDR!]" if result.tdr_detected else ""
                    reason = self._fail_reason(result)

                    # Halve the step and try again from best_core
                    new_step = max(MIN_STEP_MHZ, cur_step // 2)
                    if new_step < cur_step:
                        self._log(
                            f"  +{candidate}MHz ✗{tdr_note}  {reason} "
                            f"— halving step: {cur_step}→{new_step}MHz", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        self._apply(best_core, cfg.mem_offset_mhz, 100)
                        time.sleep(1)
                        cur_step = new_step
                        cur_core = best_core   # resume from last stable
                    else:
                        # Step already at minimum — we are done
                        self._log(
                            f"  +{candidate}MHz ✗{tdr_note}  {reason} "
                            f"— at min step ({MIN_STEP_MHZ}MHz), stopping", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        self._apply(best_core, cfg.mem_offset_mhz, 100)
                        time.sleep(1)
                        break

            self._log(f"Stage 1 done: best core = +{best_core}MHz "
                      f"(precision ±{MIN_STEP_MHZ}MHz)")
        else:
            self._log("Stage 1 skipped (UV Only mode)")

        if self._stop.is_set(): return

        # ── Stage 2: Power Limit Reduction ─────────────────────────────────────
        best_pwr = cfg.power_start_pct

        if mode in (TuneMode.UV_ONLY, TuneMode.OC_UV, TuneMode.FULL):
            self._set_state(TunerState.STAGE2)
            # A lower power limit is always "stable" — the driver just runs lower
            # clocks. What matters is how much performance it costs, so the stage
            # looks for the lowest limit that stays within power_max_loss_pct of the
            # 100 % run. (It used to count the power limiting itself as a failure,
            # so it could never lower anything.)
            self._log(f"Stage 2: Power limit reduction — lowest limit with ≤ "
                      f"{cfg.power_max_loss_pct:g} % performance loss (adaptive stepping)...")
            s2_base    = 50 if mode in (TuneMode.OC_UV, TuneMode.FULL) else 15
            MIN_PWR_STEP = 1   # 1% minimum step for power limit
            cur_pwr    = cfg.power_start_pct
            cur_step   = cfg.power_step_pct
            pwr_step_n = 0
            est_pwr_steps = max(
                (cfg.power_start_pct - cfg.power_min_pct) // cfg.power_step_pct, 1) + 5

            self._progress(s2_base, "Stage 2: Power limit optimization")

            # Reference at 100 % with the chosen core offset, in the same load the
            # steps use. The baseline ran on a cold card (~2 % slower in the live
            # calibration) and Stage 1 runs the mixed load — comparing against
            # either would have mis-measured the loss.
            self._apply(best_core, cfg.mem_offset_mhz, 100)
            time.sleep(2)
            ref_result = stress.run(cfg.step_test_s, cfg.max_temp_c,
                                    on_tick=lambda e, d, s: (
                                        self._progress(s2_base, f"Stage 2: Referenz 100 % {e}/{d}s"),
                                        self._cb_tick(s) if self._cb_tick else None))
            if self._stop.is_set():
                return
            if not ref_result.passed:
                raise TunerApplyError(f"Referenzlauf bei 100 % fehlgeschlagen: "
                                      f"{self._fail_reason(ref_result)}")
            self._log(f"  Referenz 100 %: clk={ref_result.avg_core_mhz:.0f}MHz"
                      f"{self._perf_note(ref_result)}")

            while not self._stop.is_set():
                candidate = cur_pwr - cur_step
                if candidate < cfg.power_min_pct:
                    self._log(f"Stage 2: Min {cfg.power_min_pct}% reached")
                    break

                self._apply(best_core, cfg.mem_offset_mhz, candidate)
                time.sleep(2)

                sn_cap = pwr_step_n
                def _tick2(e, d, s, p=candidate, sn=sn_cap):
                    self._progress(
                        s2_base + int(min(sn / est_pwr_steps, 1.0) * 25),
                        f"Stage 2: {p}% (step {cur_step}%) | "
                        f"{e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV"
                    )
                    if self._cb_tick: self._cb_tick(s)

                result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick2)
                if self._stop.is_set():   # aborted mid-step: don't act on it
                    return
                pwr_step_n += 1

                loss = (1.0 - result.perf(ref_result)) * 100.0
                if result.passed and not result.throttle_hit and loss <= cfg.power_max_loss_pct:
                    best_pwr = candidate
                    cur_pwr  = candidate
                    self._save_stable(best_core, cfg.mem_offset_mhz, best_pwr)
                    self._log(
                        f"  {candidate}% ✓  step={cur_step}%  "
                        f"avg={result.avg_temp:.1f}°C  "
                        f"volt={result.avg_voltage_mv:.0f}mV  "
                        f"Leistung {-loss:+.1f}%{self._perf_note(result)}"
                    )
                else:
                    tdr_note = " [TDR!]" if result.tdr_detected else ""
                    reason   = (self._fail_reason(result)
                                if not result.passed or result.throttle_hit else
                                f"Leistung {-loss:+.1f}% (erlaubt −{cfg.power_max_loss_pct:g}%)")
                    new_step = max(MIN_PWR_STEP, cur_step // 2)
                    if new_step < cur_step:
                        self._log(
                            f"  {candidate}%{tdr_note} ✗  {reason} "
                            f"— halving step: {cur_step}→{new_step}%", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                        time.sleep(1)
                        cur_step = new_step
                        cur_pwr  = best_pwr
                    else:
                        self._log(
                            f"  {candidate}%{tdr_note} ✗  {reason} "
                            f"— at min step ({MIN_PWR_STEP}%), stopping", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                        time.sleep(1)
                        break

            self._log(f"Stage 2 done: best power = {best_pwr}% (precision ±{MIN_PWR_STEP}%)")
        else:
            self._log("Stage 2 skipped (OC Only mode)")

        if self._stop.is_set(): return

        # ── Stage 3: V/F Curve Undervolt ──────────────────────────────────────
        best_volt_mv   = 0   # 0 = not run / no improvement found
        best_vf_freq   = 0

        run_vf = (
            cfg.vf_enabled and
            mode in (TuneMode.FULL, TuneMode.VF_ONLY) and
            base.avg_voltage_mv > 0   # Need MAHM for voltage readings
        )

        if run_vf:
            self._set_state(TunerState.STAGE3)
            self._log("Stage 3: V/F curve undervolt (precise voltage targeting)...")
            self._log(f"  Baseline voltage: {base.avg_voltage_mv:.0f}mV @ {base.avg_core_mhz:.0f}MHz")

            try:
                gpu_name   = self.monitor.read().name
                vf_builder = get_builder_for_gpu(gpu_name)
            except:
                vf_builder = VFCurveBuilder("Ada")

            # Determine target frequency from Stage 1 result
            target_freq = int(base.avg_core_mhz + best_core)
            self._log(f"  Target frequency: {target_freq}MHz")

            # Start voltage: measured baseline, step down
            start_mv   = vf_builder.recommend_start_voltage(base.avg_voltage_mv)
            test_volts = vf_builder.get_uv_test_voltages(start_mv, cfg.vf_min_mv)
            self._log(f"  Testing from {start_mv}mV down to {cfg.vf_min_mv}mV "
                      f"in {cfg.vf_step_mv}mV steps ({len(test_volts)} steps)")

            # Adaptive stepping for V/F curve: start at cfg.vf_step_mv,
            # halve on failure, stop at 5mV minimum
            MIN_VF_STEP  = 5   # mV
            cur_vf_step  = cfg.vf_step_mv
            cur_mv       = start_mv
            vf_step_n    = 0
            est_vf_steps = max(
                (start_mv - cfg.vf_min_mv) // cfg.vf_step_mv, 1) + 8

            while not self._stop.is_set():
                test_mv = cur_mv - cur_vf_step
                if test_mv < cfg.vf_min_mv:
                    self._log(f"Stage 3: Floor {cfg.vf_min_mv}mV reached")
                    break

                self._apply_vf(best_core, test_mv, target_freq, cfg.mem_offset_mhz)
                time.sleep(2)

                sn_cap = vf_step_n
                def _tick3(e, d, s, mv=test_mv, sn=sn_cap):
                    self._progress(
                        72 + int(min(sn / est_vf_steps, 1.0) * 13),
                        f"Stage 3: {mv}mV (step {cur_vf_step}mV) | "
                        f"{e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV | {s.core_mhz:.0f}MHz"
                    )
                    if self._cb_tick: self._cb_tick(s)

                result = stress.run(cfg.vf_step_test_s, cfg.max_temp_c, on_tick=_tick3,
                                    mode="mixed")
                if self._stop.is_set():   # aborted mid-step: don't act on it
                    return
                vf_step_n += 1

                if result.passed and not result.throttle_hit and not result.crash_detected:
                    best_volt_mv = test_mv
                    best_vf_freq = int(result.avg_core_mhz)
                    cur_mv       = test_mv   # continue going lower
                    self._save_stable(best_core, cfg.mem_offset_mhz, best_pwr)
                    self._log(
                        f"  {test_mv}mV ✓  step={cur_vf_step}mV  "
                        f"avg={result.avg_temp:.1f}°C  "
                        f"clk={result.avg_core_mhz:.0f}MHz  "
                        f"volt={result.avg_voltage_mv:.0f}mV measured"
                    )
                else:
                    tdr_note = " [TDR!]" if result.tdr_detected else ""
                    reason   = self._fail_reason(result)
                    new_step = max(MIN_VF_STEP, cur_vf_step // 2)
                    if new_step < cur_vf_step:
                        self._log(
                            f"  {test_mv}mV ✗{tdr_note}  {reason} "
                            f"— halving step: {cur_vf_step}→{new_step}mV", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        # Restore last good and retry with finer step
                        if best_volt_mv > 0:
                            self._apply_vf(best_core, best_volt_mv, target_freq,
                                           cfg.mem_offset_mhz)
                        else:
                            self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                        time.sleep(1)
                        cur_vf_step = new_step
                        cur_mv = best_volt_mv if best_volt_mv > 0 else start_mv
                    else:
                        self._log(
                            f"  {test_mv}mV ✗{tdr_note}  {reason} "
                            f"— at min step ({MIN_VF_STEP}mV), stopping", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        if best_volt_mv > 0:
                            self._apply_vf(best_core, best_volt_mv, target_freq,
                                           cfg.mem_offset_mhz)
                        else:
                            self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
                        time.sleep(1)
                        break

            if best_volt_mv > 0:
                volt_saved = int(base.avg_voltage_mv - best_volt_mv)
                self._log(
                    f"Stage 3 done: {best_volt_mv}mV stable "
                    f"(saved ~{volt_saved}mV vs baseline)"
                )
            else:
                self._log("Stage 3: No voltage reduction found — baseline voltage is already optimal")
        else:
            if not run_vf and mode in (TuneMode.FULL, TuneMode.VF_ONLY):
                self._log("Stage 3 skipped: MAHM voltage readings unavailable "
                          "(start Afterburner with voltage monitoring enabled)")
            else:
                self._log("Stage 3 skipped (mode doesn't include V/F curve)")

        if self._stop.is_set(): return

        # ── Stage 4: Memory Overclock ──────────────────────────────────────────
        best_mem_offset = cfg.mem_offset_mhz  # start from configured value

        run_mem = (
            cfg.mem_oc_enabled and
            (mode in (TuneMode.FULL, TuneMode.MEM_ONLY) or cfg.mem_stage)
        )

        if run_mem:
            self._set_state(TunerState.STAGE4)
            self._log("Stage 4: Memory overclock — memory load, bandwidth must keep rising "
                      "(GDDR6X corrects errors by retrying: past its limit it gets SLOWER, "
                      "it doesn't crash)...")
            self._progress(86, "Stage 4: Memory clock optimization")

            # Reference bandwidth at the current memory offset.
            if best_volt_mv > 0:
                self._apply_vf(best_core, best_volt_mv, target_freq if run_vf else 0,
                               best_mem_offset)
            else:
                self._apply(best_core, best_mem_offset, best_pwr)
            time.sleep(2)
            mref = stress.run(min(cfg.step_test_s, 30), cfg.max_temp_c, mode="mem",
                              on_tick=lambda e, d, s: (
                                  self._progress(86, f"Stage 4: Referenz-Bandbreite {e}/{d}s"),
                                  self._cb_tick(s) if self._cb_tick else None))
            if self._stop.is_set():
                return
            best_bw = mref.avg_bw_gbs if mref.passed else 0.0
            if best_bw > 0:
                self._log(f"  Referenz: {best_bw:.0f} GB/s @ {mref.avg_mem_mhz:.0f} MHz "
                          f"(Mem+{best_mem_offset}MHz)")
            else:
                self._log("  Bandbreite nicht messbar (cupy fehlt?) — Speicher-OC nur mit "
                          "Absturz-/Fehlererkennung", "warning")

            # Measured bandwidth per accepted offset. The stepping only stops once
            # bandwidth falls OUT of the noise band — by then it has crept past the
            # peak into the range where GDDR6X already corrects errors. The result
            # is therefore the offset with the highest measured bandwidth.
            bw_at = {best_mem_offset: best_bw} if best_bw > 0 else {}

            # Adaptive stepping for Memory OC
            MIN_MEM_STEP = max(1, cfg.mem_min_step_mhz)   # MHz
            cur_mem      = best_mem_offset
            cur_mem_step = cfg.mem_oc_step_mhz
            mem_step_n   = 0
            est_mem_steps = max(cfg.mem_oc_max_mhz // cfg.mem_oc_step_mhz, 1) + 6
            # Highest offset still worth testing: 'Mem Max', then just below
            # every offset that failed (a coarse step must not re-test it).
            upper = cfg.mem_oc_max_mhz

            while not self._stop.is_set():
                candidate_mem = min(cur_mem + cur_mem_step, upper)
                if candidate_mem <= cur_mem:
                    if upper == cfg.mem_oc_max_mhz:
                        self._log(f"Stage 4: Memory limit +{cfg.mem_oc_max_mhz}MHz reached")
                    break

                if best_volt_mv > 0:
                    self._apply_vf(best_core, best_volt_mv,
                                   target_freq if run_vf else 0, candidate_mem)
                else:
                    self._apply(best_core, candidate_mem, best_pwr)
                time.sleep(2)

                sn_cap = mem_step_n
                def _tick4(e, d, s, cm=candidate_mem, sn=sn_cap):
                    self._progress(
                        86 + int(min(sn / est_mem_steps, 1.0) * 8),
                        f"Stage 4: Mem+{cm}MHz (step {cur_mem_step}MHz) | "
                        f"{e}/{d}s | {s.temp}°C | {s.mem_mhz:.0f}MHz"
                    )
                    if self._cb_tick: self._cb_tick(s)

                result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick4,
                                    mode="mem")
                if self._stop.is_set():   # aborted mid-step: don't act on it
                    return
                mem_step_n += 1

                bw = result.avg_bw_gbs
                bw_drop = (best_bw > 0 and bw > 0 and
                           bw < best_bw * (1.0 - cfg.mem_bw_drop_pct / 100.0))
                bw_note = f"  {bw:.0f} GB/s @ {result.avg_mem_mhz:.0f} MHz" if bw > 0 else ""
                if result.passed and not result.crash_detected and not bw_drop:
                    best_mem_offset = candidate_mem
                    cur_mem         = candidate_mem
                    best_bw         = max(best_bw, bw)
                    if bw > 0:
                        bw_at[candidate_mem] = bw
                    self._log(
                        f"  Mem+{candidate_mem}MHz ✓  step={cur_mem_step}MHz  "
                        f"avg={result.avg_temp:.1f}°C{bw_note}"
                    )
                else:
                    upper     = candidate_mem - MIN_MEM_STEP   # never re-test next to a failure
                    tdr_note  = " [TDR!]" if result.tdr_detected else ""
                    reason    = (f"Bandbreite {bw:.0f} < {best_bw:.0f} GB/s — Fehlerkorrektur "
                                 f"(EDC) bremst" if bw_drop and result.passed
                                 else self._fail_reason(result))
                    new_step  = max(MIN_MEM_STEP, cur_mem_step // 2)
                    if new_step < cur_mem_step:
                        self._log(
                            f"  Mem+{candidate_mem}MHz ✗{tdr_note}  {reason} "
                            f"— halving step: {cur_mem_step}→{new_step}MHz", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        if best_volt_mv > 0:
                            self._apply_vf(best_core, best_volt_mv,
                                           target_freq if run_vf else 0, best_mem_offset)
                        else:
                            self._apply(best_core, best_mem_offset, best_pwr)
                        time.sleep(1)
                        cur_mem_step = new_step
                        cur_mem      = best_mem_offset
                    else:
                        self._log(
                            f"  Mem+{candidate_mem}MHz ✗{tdr_note}  {reason} "
                            f"— at min step ({MIN_MEM_STEP}MHz), stopping", "warning"
                        )
                        self._set_state(TunerState.BACKOFF)
                        if best_volt_mv > 0:
                            self._apply_vf(best_core, best_volt_mv,
                                           target_freq if run_vf else 0, best_mem_offset)
                        else:
                            self._apply(best_core, best_mem_offset, best_pwr)
                        time.sleep(1)
                        break

            if len(bw_at) > 1 and not self._stop.is_set():
                peak = max(bw_at, key=lambda o: (bw_at[o], -o))   # tie -> lower offset
                if peak < best_mem_offset:
                    self._log(f"  Bandbreiten-Maximum bei Mem+{peak}MHz ({bw_at[peak]:.0f} GB/s) — "
                              f"darüber (bis +{best_mem_offset}MHz) kein Gewinn mehr, der Speicher "
                              f"korrigiert dort schon Fehler → +{peak}MHz übernommen")
                    best_mem_offset = peak
                    if best_volt_mv > 0:
                        self._apply_vf(best_core, best_volt_mv,
                                       target_freq if run_vf else 0, best_mem_offset)
                    else:
                        self._apply(best_core, best_mem_offset, best_pwr)
            self._log(f"Stage 4 done: best memory = +{best_mem_offset}MHz "
                      f"(precision ±{MIN_MEM_STEP}MHz)")
        else:
            self._log("Stage 4 skipped (mode doesn't include Memory OC)")

        if self._stop.is_set(): return

        # ── Final Test ─────────────────────────────────────────────────────────
        # Verify the EXACT configuration that will be saved — including the
        # Stage-3 V/F undervolt and the Stage-4 memory OC. If it fails, take one
        # step back and run the final test again (it used to save an UNTESTED
        # "conservative" profile and stop).
        self._set_state(TunerState.FINAL_TEST)
        attempt, retries_used = 1, []
        while True:
            vf_note  = f" | VF {best_volt_mv}mV" if best_volt_mv > 0 else ""
            mem_note = f" | Mem+{best_mem_offset}MHz" if best_mem_offset else ""
            tries    = f" | Versuch {attempt}/{self.FINAL_RETRIES + 1}" if attempt > 1 else ""
            self._log(
                f"Final test: +{best_core}MHz | {best_pwr}% pwr{vf_note}{mem_note} "
                f"| {cfg.final_test_s}s{tries}")
            self._progress(
                75,
                f"Final verification: +{best_core}MHz | {best_pwr}%{vf_note}{mem_note} "
                f"({cfg.final_test_s}s){tries}"
            )
            if best_volt_mv > 0:
                self._apply_vf(best_core, best_volt_mv, target_freq, best_mem_offset)
            else:
                self._apply(best_core, best_mem_offset, best_pwr)
            time.sleep(2)

            def _tick_final(e, d, s):
                self._progress(
                    75 + int(e / d * 20),
                    f"Final: {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV | {s.core_mhz:.0f}MHz"
                )
                if self._cb_tick: self._cb_tick(s)

            final = stress.run(cfg.final_test_s, cfg.max_temp_c, on_tick=_tick_final,
                               mode="mixed")
            if self._stop.is_set():   # aborted mid-step: don't act on it
                return
            if final.passed:
                break
            back = (self._final_backoff(cfg, final, attempt, best_core, best_volt_mv,
                                        best_mem_offset, best_pwr)
                    if attempt <= self.FINAL_RETRIES else None)
            tdr_note = " [TDR!]" if final.tdr_detected else ""
            if back is None:
                self._log(f"  Final test ✗{tdr_note}  {self._fail_reason(final)} — "
                          f"nichts mehr zurückzunehmen", "warning")
                break
            best_core, best_volt_mv, best_mem_offset, best_pwr, what = back
            retries_used.append(what)
            self._set_state(TunerState.BACKOFF)
            self._log(f"  Final test ✗{tdr_note}  {self._fail_reason(final)} — zurück: "
                      f"{what} → Endtest wird wiederholt", "warning")
            attempt += 1
            self._set_state(TunerState.FINAL_TEST)

        # ── Save ───────────────────────────────────────────────────────────────
        self._set_state(TunerState.SAVING)
        mode_tag = {
            "oc_only":  "OC",
            "uv_only":  "UV",
            "oc_uv":    "OC+UV",
            "full":     "FULL",
            "vf_only":  "VF",
            "mem_only": "MEM",
        }.get(mode.value, "")

        try:
            gpu_name = self.monitor.read().name
        except:
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
                lock_voltage_mv=best_volt_mv,
                lock_freq_mhz=best_vf_freq,
                mem_offset_mhz=best_mem_offset,
                notes=(
                    f"[{mode_tag}] Core+{best_core}MHz | "
                    f"Mem+{best_mem_offset}MHz | "
                    + (f"Endtest nach {len(retries_used)} Rücknahme(n) | " if retries_used else "") +
                    f"Pwr {best_pwr}% | "
                    + (f"VF {best_volt_mv}mV | " if best_volt_mv > 0 else "") +
                    f"MaxTemp {final.max_temp:.0f}°C | "
                    f"AvgVolt {final.avg_voltage_mv:.0f}mV | Score {score}/100"
                ),
                created_at=datetime.now().isoformat(),
                gpu_name=gpu_name,
            )
            self.best_profile = profile
            self.pm.save(profile)
            # Track as last applied for startup loader
            if self.cr:
                self.cr.save_last_applied(profile.to_dict())
            if retries_used:
                self._log(f"Endtest bestanden nach {len(retries_used)} Rücknahme(n): "
                          + "; ".join(retries_used))
            self._log(f"Profile saved: {profile.name}")
            self._log(f"  Mode:        {mode_tag}")
            self._log(f"  Core offset:  +{best_core}MHz")
            self._log(f"  Memory offset:+{best_mem_offset}MHz")
            self._log(f"  Power limit:  {best_pwr}%")
            if best_volt_mv > 0:
                self._log(f"  V/F lock:     {best_volt_mv}mV → {best_vf_freq}MHz")
            self._log(f"  Avg voltage:  {final.avg_voltage_mv:.0f}mV")
            self._log(f"  Max temp:     {final.max_temp:.0f}°C")
            self._log(f"  Score:        {score}/100")
            vf_str = f" | VF {best_volt_mv}mV" if best_volt_mv > 0 else ""
            self._progress(
                100,
                f"✓ Done! [{mode_tag}] +{best_core}MHz | Mem+{best_mem_offset}MHz"
                f"{vf_str} | Score {score}/100"
            )
        else:
            # Never save something that did not pass: back to stock, say so.
            self._log(
                f"Endtest nicht bestanden ({self._fail_reason(final)}), auch nach "
                f"{len(retries_used)} Rücknahme(n) — KEIN Profil gespeichert, GPU auf "
                f"Standard zurückgesetzt. Temperaturen/Kühlung prüfen oder mit kleinerem "
                f"'Core Max' bzw. ohne Speicher-Offset erneut tunen.", "error")
            self._reset_locked()
            if self.cr:
                self.cr.clear_tuning_flag()
            self._progress(100, "✗ Endtest nicht bestanden — kein Profil gespeichert, GPU auf Standard")
            self._set_state(TunerState.ERROR)
            return

        # Clean up crash flag — we finished cleanly
        if self.cr:
            self.cr.clear_tuning_flag()

        self._log("═══════════════════════════════════════")
        self._log("        Auto-Tune Complete")
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
