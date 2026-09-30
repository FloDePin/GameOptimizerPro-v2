"""Round 11 — memory OC inside the Auto-Tune (OC / OC+UV): searched with a
bandwidth measurement instead of a fixed, unsearched 'Mem Offset'. Scripted GPU
(nothing is applied to the real card); the GPU tab runs under a real mainloop."""
import os, sys, tempfile, time, types, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult
_real_time = NT.time
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class GPU:
    """Core unstable above +175 (steps); memory bandwidth rises until +1000 and
    then falls (GDDR6X error correction), final test always passes."""
    def __init__(self):
        self.core = self.mem = 0; self.pwr = 100
        self.mem_tests = []; self.finals = []
    def apply(self, p):
        self.core, self.mem, self.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        r = StressResult(passed=True, avg_temp=65, max_temp=68, avg_voltage_mv=1000,
                         avg_gpu_usage=99, power_capped_pct=100.0)
        r.avg_core_mhz = 2700 + self.core
        r.avg_rate_tflops = 40.0 * (1 - max(0.0, (95 - self.pwr) * 0.004))
        if mode == "mem":
            m = self.mem
            self.mem_tests.append(m)
            r.avg_rate_tflops = 0.0
            r.avg_bw_gbs = 700 + 0.05 * m if m <= 1000 else 750 - 0.3 * (m - 1000)
            r.avg_mem_mhz = 11200 + m
        if d == 120:
            self.finals.append((self.core, self.mem, self.pwr))
        if self.core > 175:
            r.passed, r.compute_error = False, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r


class AB:
    available = True
    def __init__(self, g): self.g = g
    def write_and_apply(self, slot, p):
        self.g.apply(p); return True, ""


class Mon:
    def read(self):
        return types.SimpleNamespace(name="NVIDIA GeForce RTX 4080", temp=50, voltage_mv=1000,
                                     core_mhz=2700, gpu_power_w=250, gpu_usage=99, throttle="None")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


def tune(gpu, **cfg):
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    tmp = tempfile.mkdtemp(prefix="gop_mem_")
    t = AutoTuner(Mon(), AB(gpu), NT.ProfileManager(os.path.join(tmp, "p")),
                  TunerConfig(core_step_mhz=15, core_max_mhz=300, power_min_pct=90, **cfg),
                  log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    shutil.rmtree(tmp, ignore_errors=True)
    return t, logs


print("OC + UV with the memory stage")
g = GPU()
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1500,
               mem_oc_step_mhz=250, mem_min_step_mhz=25)
check(g.mem_tests[1:] == [250, 500, 750, 1000, 1250, 1125, 1062, 1031, 1037],
      f"coarse 250-MHz steps, halved after the first drop, ±25 MHz: {g.mem_tests[1:]}")
check(g.mem_tests[0] == 0, "reference bandwidth at stock memory first")
check(len(set(g.mem_tests)) == len(g.mem_tests), "no offset tested twice")
bp = t.best_profile
check(t.state == TunerState.DONE and bp and bp.mem_offset_mhz == 1000,
      f"result = bandwidth peak +1000 (not +1031 inside the noise band): {bp.mem_offset_mhz if bp else None}")
check(g.finals and g.finals[-1][1] == 1000, f"final test ran WITH the memory offset: {g.finals}")
check(any("Bandbreiten-Maximum" in m for m in logs), "log explains the choice")
check(any("Fehlerkorrektur" in m for m in logs), "log names the EDC slowdown")

print("memory stage off")
g = GPU()
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=False)
check(g.mem_tests == [] and t.best_profile and t.best_profile.mem_offset_mhz == 0,
      "no memory steps, profile memory +0")
check(any("Stage 4 skipped" in m for m in logs), "log says so")

print("'Mem Max' is respected and tested once")
g = GPU()
t, logs = tune(g, mode=TuneMode.OC_ONLY, mem_stage=True, mem_oc_max_mhz=1100,
               mem_oc_step_mhz=250, mem_min_step_mhz=25)
check(max(g.mem_tests) == 1100 and g.mem_tests.count(1100) == 1
      and g.mem_tests[1:] == [250, 500, 750, 1000, 1100, 1075, 1050],
      f"the limit itself is tested exactly once, never above or right next to it: {g.mem_tests[1:]}")
check(t.best_profile and t.best_profile.mem_offset_mhz == 1000, "result still the peak")

print("old modes unchanged")
g = GPU()
t, logs = tune(g, mode=TuneMode.MEM_ONLY, mem_oc_max_mhz=1500, mem_oc_step_mhz=250)
check(t.best_profile and t.best_profile.mem_offset_mhz == 1000, "MEM_ONLY finds the same peak")

# ── GPU tab ──────────────────────────────────────────────────────────────────
print("GPU tab")
NT.time = _real_time
import tkinter as tk
from tkinter import messagebox
ASKED = []
messagebox.askyesno = lambda title, msg, **k: (ASKED.append(msg), True)[1]
from core.nvtune_core import AfterburnerController, GpuMonitor, ProfileManager
tmp = tempfile.mkdtemp(prefix="gop_memui_")
root = tk.Tk(); root.withdraw()
mon = GpuMonitor()


class FakeAB(AfterburnerController):
    def _detect(self):
        self.exe, self.profile_dir = r"C:\fake\MSIAfterburner.exe", None


ab = FakeAB()
pm = ProfileManager(os.path.join(tmp, "profiles"))
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=os.path.join(tmp, "logs"))
started = []
tuner.start = lambda: started.append(tuner.config)
from ui.tab_gpu import GpuTunerTab
gpu = GpuTunerTab(root, mon, ab, pm, tuner)
name = mon.read().name
from core.gpu_defaults import get_defaults
check(gpu.v_mem_stage.get() is True, "'Speicher mit übertakten' is on by default (OC + UV)")
check(gpu.v_mem_max.get() == get_defaults(name).mem_max_mhz,
      f"'Mem Max' from the generation table for {name!r}: +{gpu.v_mem_max.get()} MHz")
check(not hasattr(gpu, "v_mem_off"), "the fixed 'Mem Offset' field is gone")
gpu._apply_mode_to_config("uv_only")
check(gpu.v_mem_stage.get() is False, "'Nur UV' switches the memory stage off")
gpu._apply_mode_to_config("oc_uv")
check(gpu.v_mem_stage.get() is True, "'OC + UV' switches it back on")
gpu._start_tune()
cfg = started[-1] if started else None
check(cfg is not None and cfg.mem_stage and cfg.mem_oc_max_mhz == gpu.v_mem_max.get()
      and cfg.mem_oc_step_mhz == 250 and cfg.mem_min_step_mhz == 25 and cfg.mem_offset_mhz == 0,
      "tuner config: memory stage on, 250-MHz steps to ±25, no fixed offset")
check(ASKED and f"Speicher: bis +{gpu.v_mem_max.get()}MHz" in ASKED[-1] and "30-45" in ASKED[-1],
      "start dialog names the memory stage and the longer duration")
gpu.v_mem_stage.set(False)
gpu._start_tune()
check(not started[-1].mem_stage and "wird nicht übertaktet" in ASKED[-1], "unticked -> no memory stage")
root.destroy()
try:
    mon.close()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
