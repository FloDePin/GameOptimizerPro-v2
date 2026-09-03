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
    throttle_hit:   bool  = False
    crash_detected: bool  = False
    tdr_detected:   bool  = False
    abort_reason:   str   = ""
    avg_core_mhz:   float = 0.0
    core_clocks:    list  = field(default_factory=list)


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


class StressTester:
    def __init__(self, monitor: GpuMonitor, crash_recovery=None):
        self.monitor = monitor
        self.cr      = crash_recovery
        self._proc: Optional[subprocess.Popen] = None

    def _worker_path(self):
        # Worker lives at project root, not in core/
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "_stress_worker.py"
        )

    def start(self):
        wp = self._worker_path()
        if os.path.exists(wp):
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self._proc = subprocess.Popen(
                    [sys.executable, wp, str(os.getpid())],  # GUI PID → dead-man switch
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags
                )
            except:
                pass

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
        on_tick: Optional[Callable] = None
    ) -> StressResult:
        result = StressResult()
        temps, voltages, clocks = [], [], []

        self.start()
        start = time.time()

        while True:
            elapsed = int(time.time() - start)
            if elapsed >= duration_s:
                break

            stats = self.monitor.read()
            temps.append(stats.temp)
            if stats.voltage_mv > 0:
                voltages.append(stats.voltage_mv)
            clocks.append(stats.core_mhz)

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

            if stats.throttle not in ("None", ""):
                result.throttle_hit = True

            # Worker crash = GPU instability
            if self._proc and self._proc.poll() is not None:
                result.crash_detected = True
                result.abort_reason   = "Stress worker crashed (GPU unstable)"
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

        Path(log_dir).mkdir(parents=True, exist_ok=True)
        logfile = os.path.join(
            log_dir, f"tune_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        # Use a named logger so multiple inits don't conflict
        self.logger = logging.getLogger(f"gop.tuner.{id(self)}")
        if not self.logger.handlers:
            fh = logging.FileHandler(logfile, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(fh)
            self.logger.setLevel(logging.INFO)

    def on_state(self,    cb): self._cb_state    = cb
    def on_log(self,      cb): self._cb_log      = cb
    def on_progress(self, cb): self._cb_progress = cb
    def on_tick(self,     cb): self._cb_tick     = cb

    def _set_state(self, s):
        self.state = s
        if self._cb_state:
            self._cb_state(s)

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
        self._stop.set()
        self._set_state(TunerState.ABORTED)
        self._log("Aborted by user", "warning")
        self._safe_reset()
        if self.cr:
            self.cr.clear_tuning_flag()

    def _safe_reset(self):
        try:
            reset = TuneProfile(
                name="__reset__",
                core_offset_mhz=0,
                mem_offset_mhz=0,
                power_limit_pct=100
            )
            self.ab.write_and_apply(self.config.ab_slot, reset)
            _, _, mx = self.monitor.get_power_constraints()
            if mx > 0:
                self.monitor.set_power_limit(mx)
        except:
            pass

    def _apply(self, core=0, mem=0, pwr_pct=100) -> bool:
        p = TuneProfile(
            name="__tuning__",
            core_offset_mhz=core,
            mem_offset_mhz=mem,
            power_limit_pct=pwr_pct,
        )
        # Write crash flag before applying
        if self.cr:
            self.cr.set_tuning_active(p.to_dict())
        ok, _ = self.ab.write_and_apply(self.config.ab_slot, p)
        if ok:
            _, _, mx = self.monitor.get_power_constraints()
            if mx > 0 and pwr_pct < 100:
                self.monitor.set_power_limit(mx * (pwr_pct / 100.0))
        return ok

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
        if self.cr:
            self.cr.set_tuning_active(p.to_dict())
        ok, err = self.ab.write_and_apply(self.config.ab_slot, p)
        if not ok:
            self._log(f"  V/F apply failed: {err}", "warning")
        return ok

    def _run_safe(self):
        try:
            self._run()
        except Exception as e:
            self._log(f"Tuner exception: {e}", "error")
            self._set_state(TunerState.ERROR)
            self._safe_reset()
            if self.cr:
                self.cr.clear_tuning_flag()

    def _run(self):
        cfg     = self.config
        mode    = cfg.mode
        stress  = StressTester(self.monitor, self.cr)

        self._log("═══════════════════════════════════════")
        self._log(f"  GameOptimizerPro Auto-Tune [{mode.value.upper().replace('_',' ')}]")
        self._log("═══════════════════════════════════════")

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
        if not base.passed:
            self._log(f"Baseline FAILED: {base.abort_reason}", "error")
            self._set_state(TunerState.ERROR)
            if self.cr: self.cr.clear_tuning_flag()
            return

        self._log(
            f"Baseline OK | temp={base.avg_temp}°C | "
            f"volt={base.avg_voltage_mv:.0f}mV | clk={base.avg_core_mhz:.0f}MHz"
        )
        # Baseline is our first "stable" point
        self._save_stable(0, 0, 100)

        if self._stop.is_set(): return

        # ── Stage 1: Core Clock Offset ─────────────────────────────────────────
        best_core = cfg.core_start_mhz

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

                result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick1)
                step_n += 1

                if result.passed and not result.throttle_hit:
                    best_core = candidate
                    cur_core  = candidate
                    self._save_stable(best_core, cfg.mem_offset_mhz, 100)
                    self._log(
                        f"  +{candidate}MHz ✓  step={cur_step}MHz  "
                        f"avg={result.avg_temp:.1f}°C  "
                        f"volt={result.avg_voltage_mv:.0f}mV  "
                        f"clk={result.avg_core_mhz:.0f}MHz"
                    )
                    # After a success, try to push a little further
                    # Step stays the same unless we've been reducing it
                else:
                    tdr_note = " [TDR!]" if result.tdr_detected else ""
                    reason = result.abort_reason or (
                        "Throttle" if result.throttle_hit else "Unstable")

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
            self._log("Stage 2: Power limit reduction (adaptive stepping)...")
            s2_base    = 50 if mode in (TuneMode.OC_UV, TuneMode.FULL) else 15
            MIN_PWR_STEP = 1   # 1% minimum step for power limit
            cur_pwr    = cfg.power_start_pct
            cur_step   = cfg.power_step_pct
            pwr_step_n = 0
            est_pwr_steps = max(
                (cfg.power_start_pct - cfg.power_min_pct) // cfg.power_step_pct, 1) + 5

            self._progress(s2_base, "Stage 2: Power limit optimization")

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
                pwr_step_n += 1

                if result.passed and not result.throttle_hit:
                    best_pwr = candidate
                    cur_pwr  = candidate
                    self._save_stable(best_core, cfg.mem_offset_mhz, best_pwr)
                    self._log(
                        f"  {candidate}% ✓  step={cur_step}%  "
                        f"avg={result.avg_temp:.1f}°C  "
                        f"volt={result.avg_voltage_mv:.0f}mV"
                    )
                else:
                    tdr_note = " [TDR!]" if result.tdr_detected else ""
                    reason   = result.abort_reason or "Unstable"
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

                result = stress.run(cfg.vf_step_test_s, cfg.max_temp_c, on_tick=_tick3)
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
                    reason   = result.abort_reason or (
                        "Crash" if result.crash_detected else "Unstable")
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
            mode in (TuneMode.FULL, TuneMode.MEM_ONLY)
        )

        if run_mem:
            self._set_state(TunerState.STAGE4)
            self._log("Stage 4: Memory overclock (Ada GDDR6X has high headroom)...")
            self._progress(86, "Stage 4: Memory clock optimization")

            # Adaptive stepping for Memory OC
            MIN_MEM_STEP = 5   # MHz
            cur_mem      = best_mem_offset
            cur_mem_step = cfg.mem_oc_step_mhz
            mem_step_n   = 0
            est_mem_steps = max(cfg.mem_oc_max_mhz // cfg.mem_oc_step_mhz, 1) + 6

            while not self._stop.is_set():
                candidate_mem = cur_mem + cur_mem_step
                if candidate_mem > cfg.mem_oc_max_mhz:
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

                result = stress.run(cfg.step_test_s, cfg.max_temp_c, on_tick=_tick4)
                mem_step_n += 1

                if result.passed and not result.crash_detected:
                    best_mem_offset = candidate_mem
                    cur_mem         = candidate_mem
                    self._log(
                        f"  Mem+{candidate_mem}MHz ✓  step={cur_mem_step}MHz  "
                        f"avg={result.avg_temp:.1f}°C"
                    )
                else:
                    tdr_note  = " [TDR!]" if result.tdr_detected else ""
                    reason    = result.abort_reason or (
                        "Crash" if result.crash_detected else "Unstable")
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

            self._log(f"Stage 4 done: best memory = +{best_mem_offset}MHz "
                      f"(precision ±{MIN_MEM_STEP}MHz)")
        else:
            self._log("Stage 4 skipped (mode doesn't include Memory OC)")

        if self._stop.is_set(): return

        # ── Final Test ─────────────────────────────────────────────────────────
        self._set_state(TunerState.FINAL_TEST)
        self._log(
            f"Final test: +{best_core}MHz | {best_pwr}% pwr | {cfg.final_test_s}s")
        self._progress(
            75,
            f"Final verification: +{best_core}MHz | {best_pwr}% ({cfg.final_test_s}s)"
        )

        self._apply(best_core, cfg.mem_offset_mhz, best_pwr)
        time.sleep(2)

        def _tick_final(e, d, s):
            self._progress(
                75 + int(e / d * 20),
                f"Final: {e}/{d}s | {s.temp}°C | {s.voltage_mv:.0f}mV | {s.core_mhz:.0f}MHz"
            )
            if self._cb_tick: self._cb_tick(s)

        final = stress.run(cfg.final_test_s, cfg.max_temp_c, on_tick=_tick_final)

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
            safe_core = (max(0, best_core - cfg.core_step_mhz)
                         if mode != TuneMode.UV_ONLY else 0)
            safe_pwr  = min(100, best_pwr + cfg.power_step_pct)
            self._log(
                f"Final failed ({final.abort_reason}) — saving conservative profile",
                "warning"
            )
            profile = TuneProfile(
                name=f"GOP_{mode_tag}_Safe_{datetime.now().strftime('%m%d_%H%M')}",
                core_offset_mhz=safe_core,
                mem_offset_mhz=0,
                power_limit_pct=safe_pwr,
                is_stable=True,
                stability_score=55,
                notes=f"[{mode_tag}] Conservative | +{safe_core}MHz | {safe_pwr}%",
                created_at=datetime.now().isoformat(),
                gpu_name=gpu_name,
            )
            self.best_profile = profile
            self.pm.save(profile)
            self._apply(safe_core, 0, safe_pwr)
            self._progress(
                100, f"Safe profile: +{safe_core}MHz | {safe_pwr}%")

        # Clean up crash flag — we finished cleanly
        if self.cr:
            self.cr.clear_tuning_flag()

        self._log("═══════════════════════════════════════")
        self._log("        Auto-Tune Complete")
        self._log("═══════════════════════════════════════")
        self._set_state(TunerState.DONE)

    def _score(self, r: StressResult) -> int:
        score  = 100
        margin = 85 - r.max_temp
        if margin < 5:
            score -= 20
        elif margin < 10:
            score -= 10
        if r.throttle_hit:
            score -= 15
        if r.tdr_detected:
            score -= 30
        return max(0, min(100, score))
