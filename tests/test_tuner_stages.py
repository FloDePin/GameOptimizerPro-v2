"""Tuner stage logic with a scripted 'GPU': power limit is normal, Stage 2 finds the
lowest limit with <= 3 % loss, Stage 4 loads the whole card (+500, 100-MHz steps)."""
import os, sys, time, types, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class GPU:
    """Scripted card: core unstable above +52 MHz, perf drops below 95 % PL,
    memory bandwidth scales until +600 MHz and then falls (EDC retries)."""
    def __init__(self, thermal=False):
        self.core = self.mem = 0
        self.pwr = 100
        self.lock = 0
        self.thermal = thermal
        self.runs = []

    def apply(self, p):
        self.core, self.mem, self.pwr, self.lock = (p.core_offset_mhz, p.mem_offset_mhz,
                                                    p.power_limit_pct, p.lock_voltage_mv)

    def run(self, duration_s, max_temp, on_tick=None, mode="gemm"):
        self.runs.append((mode, self.core, self.mem, self.pwr))
        r = StressResult(passed=True, avg_temp=65, max_temp=68, avg_voltage_mv=1050,
                         avg_gpu_usage=99, power_capped_pct=100.0)
        if self.core > 52:                                  # unstable OC
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
            return r
        r.throttle_hit = self.thermal
        loss = max(0.0, (95 - self.pwr) * 0.004)            # 90 % -> -2 %, 85 % -> -4 %
        r.avg_core_mhz = (2700 + self.core) * (1 - loss)
        r.avg_rate_tflops = 40.0 * (1 + self.core / 2700) * (1 - loss)
        if mode == "mem":
            r.avg_rate_tflops = 0.0
            m = self.mem
            r.avg_bw_gbs = 700 + 0.06 * m if m <= 600 else 736 - (m - 600) * 0.2
            r.avg_mem_mhz = 11200 + m / 2
        return r


class AB:
    available = True
    def __init__(self, gpu): self.gpu = gpu
    def write_and_apply(self, slot, p):
        self.gpu.apply(p); return True, ""


class Mon:
    def __init__(self): self.w = []
    def read(self):
        return types.SimpleNamespace(name="NVIDIA GeForce RTX 4080", temp=50, voltage_mv=1050,
                                     core_mhz=2700, gpu_power_w=250, gpu_usage=99, throttle="None")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): self.w.append(w); return True


def tune(mode, gpu, **cfg):
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    tmp = tempfile.mkdtemp(prefix="gop_st_")
    t = AutoTuner(Mon(), AB(gpu), NT.ProfileManager(os.path.join(tmp, "p")),
                  TunerConfig(mode=mode, **cfg), log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    shutil.rmtree(tmp, ignore_errors=True)
    return t, logs

print("OC only: power limit active the whole time is NOT a failure")
gpu = GPU()
t, logs = tune(TuneMode.OC_ONLY, gpu, core_step_mhz=15, core_max_mhz=120)
bp = t.best_profile
check(t.state == TunerState.DONE and bp and bp.core_offset_mhz == 52 - (52 % 1) and bp.core_offset_mhz in (50, 52),
      f"finds the edge of stability: +{bp.core_offset_mhz if bp else None} MHz (unstable above +52)")
check(any("Rechenfehler" in m for m in logs), "failed steps name the compute error")
check(any("TFLOPS" in m for m in logs), "work rate is logged")

print("OC only on a thermally throttling card")
t, logs = tune(TuneMode.OC_ONLY, GPU(thermal=True), core_step_mhz=15, core_max_mhz=120)
check(t.best_profile and t.best_profile.core_offset_mhz == 0 and
      any("Thermische/Hardware-Drosselung" in m for m in logs),
      "thermal/HW slowdown still stops the OC search (and says why)")

print("UV only: lowest power limit with <= 3 % loss")
gpu = GPU()
t, logs = tune(TuneMode.UV_ONLY, gpu, power_step_pct=5, power_min_pct=60)
check(t.state == TunerState.DONE and t.best_profile.power_limit_pct == 88,
      f"power limit {t.best_profile.power_limit_pct}% (loss at 88 % = 2.8 %, at 87 % = 3.2 %)")
check(any("Leistung -3.2%" in m or "Leistung −3.2%" in m or "-3.2%" in m for m in logs),
      "the too-expensive step is explained with its loss")
check(gpu.runs[-1][3] == 88, "final verification ran at 88 %")

print("UV only with a 5 % budget")
t, logs = tune(TuneMode.UV_ONLY, GPU(), power_step_pct=5, power_min_pct=60, power_max_loss_pct=5.0)
check(t.best_profile.power_limit_pct == 83, f"5 % budget -> {t.best_profile.power_limit_pct}% (83 % = 4.8 %)")

print("OC+UV: Stage 2 compares against the OC result, not stock")
gpu = GPU()
t, logs = tune(TuneMode.OC_UV, gpu, core_step_mhz=15, core_max_mhz=120, power_step_pct=5, power_min_pct=60)
check(t.best_profile.core_offset_mhz in (50, 52) and t.best_profile.power_limit_pct == 88,
      f"+{t.best_profile.core_offset_mhz} MHz @ {t.best_profile.power_limit_pct}%")

print("MEM only: the whole card under load, +500 then 100-MHz steps (as in Rundum)")
class MemGPU(GPU):
    def run(self, duration_s, max_temp, on_tick=None, mode="gemm"):
        r = super().run(duration_s, max_temp, on_tick, mode)
        if mode == "mem" and self.mem > 650:
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r
gpu = MemGPU()
t, logs = tune(TuneMode.MEM_ONLY, gpu, mem_oc_max_mhz=1000, crash_pause_s=0)
m = t.best_profile.mem_offset_mhz
check(t.state == TunerState.DONE and m == 500, f"memory +{m} MHz (+600 passed, +700 failed -> 100 MHz safety)")
check([r[2] for r in gpu.runs if r[0] == "mem"] == [500, 600, 700], "steps +500, +600, +700")
check(gpu.runs[-1][0] == "mixed", "the final test runs the mixed game-like load")
check(any("+600 MHz bestanden, +700 nicht" in x or "+600 MHz passed, +700 did not" in x for x in logs),
      "the result is explained")

print("MEM only without cupy (no bandwidth numbers) -> still checked for errors")
class NoBW(GPU):
    def run(self, *a, **k):
        r = super().run(*a, **k); r.avg_bw_gbs = 0.0; return r
t, logs = tune(TuneMode.MEM_ONLY, NoBW(), mem_oc_max_mhz=400, crash_pause_s=0)
check(t.best_profile.mem_offset_mhz == 400 and not any("0 GB/s" in x for x in logs),
      "'Mem max' below the start value: +400 tested and kept, no '0 GB/s' noise")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
