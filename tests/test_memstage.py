"""Memory OC inside the Auto-Tune (OC / UV / OC+UV / MEM_ONLY). Round 11 searched
the bandwidth peak of a memory-only load; since round 13 every mode uses the
Rundum-Tuner's whole-card stage: +500 first, 100-MHz steps up to 'Mem max', each
step with FurMark and the verified memory copies at once, 100 MHz safety after a
failure (the bandwidth peak gave +1500 and green speckles in the live run).
Scripted GPU (nothing is applied to the real card); the GPU tab runs under a real
mainloop."""
import os, sys, tempfile, time, types, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

import core.i18n as I18N
I18N._current_lang = "de"                  # in memory only
import core.nvtune_tuner as NT
from core import furmark as FMOD
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult
_real_time = NT.time
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class GPU:
    """Core unstable above +175 (steps); memory errors above `mem_limit` under the
    whole-card load (the worker's verified copies), FurMark crashes above
    `fm_mem_limit`, the final test fails above `final_mem_limit`."""
    def __init__(self, mem_limit=800, fm_mem_limit=None, final_mem_limit=None, weak_from=None,
                 weak_times=10 ** 6):
        self.weak_from, self.weak_times = weak_from, weak_times    # copies starved from this offset on
        self.core = self.mem = 0; self.pwr = 100
        self.mem_limit, self.fm_mem_limit, self.final_mem_limit = mem_limit, fm_mem_limit, final_mem_limit
        self.mem_tests = []; self.finals = []; self.furmarks = []; self.applied = []
    def apply(self, p):
        self.core, self.mem, self.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
        self.applied.append((self.core, self.mem, self.pwr))
    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        r = StressResult(passed=True, avg_temp=65, max_temp=68, avg_voltage_mv=1000,
                         avg_gpu_usage=99, power_capped_pct=100.0)
        r.avg_core_mhz = 2700 + self.core
        r.avg_rate_tflops = 40.0 * (1 - max(0.0, (95 - self.pwr) * 0.004))
        if mode == "mem":
            m = self.mem
            self.mem_tests.append(m)
            r.avg_rate_tflops = 0.0
            r.avg_bw_gbs = 700 + 0.05 * m
            if self.weak_from is not None and m >= self.weak_from and self.weak_times > 0:
                self.weak_times -= 1
                r.avg_bw_gbs = 13.0                 # live: FurMark in front, copies starved
            r.avg_mem_mhz = 11200 + m
            if m > self.mem_limit:
                r.passed, r.crash_detected, r.compute_error = False, True, True
                r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
                return r
        if d == 120:
            self.finals.append((self.core, self.mem, self.pwr))
            if self.final_mem_limit is not None and self.mem > self.final_mem_limit:
                r.passed, r.crash_detected, r.compute_error = False, True, True
                r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
                return r
        if self.core > 175:
            r.passed, r.compute_error = False, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r
    def furmark(self, path, seconds, width=1920, height=1080, msaa=8, demo="furmark-gl",
                stop_event=None, on_tick=None, grace_s=90.0):
        self.furmarks.append((self.mem, seconds, msaa))
        if self.fm_mem_limit is not None and self.mem > self.fm_mem_limit:
            return dict(ok=False, score=0, fps_avg=0, exit_code=3221226505, elapsed_s=8.0,
                        duration_ms=0, error="FurMark endete mit Code 3221226505 (Absturz?)")
        return dict(ok=True, score=7000, fps_avg=67, exit_code=0, error="",
                    duration_ms=seconds * 1000, elapsed_s=seconds + 3)


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


def tune(gpu, furmark=False, **cfg):
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    FMOD.run_benchmark = gpu.furmark
    tmp = tempfile.mkdtemp(prefix="gop_mem_")
    conf = dict(core_step_mhz=15, core_max_mhz=300, power_min_pct=90, crash_pause_s=0, game_test=False, core_safety_mhz=0, mem_safety_mhz=0,
                furmark_path=r"C:\fake\FurMark_win64\furmark.exe" if furmark else "",
                mem_curve_start_mhz=500)
    conf.update(cfg)
    t = AutoTuner(Mon(), AB(gpu), NT.ProfileManager(os.path.join(tmp, "p")), TunerConfig(**conf),
                  log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    shutil.rmtree(tmp, ignore_errors=True)
    return t, logs


print("OC + UV with the memory stage: the whole card under load")
g = GPU(mem_limit=800)
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(g.mem_tests == [500, 600, 700, 800, 900], f"+500 first, then 100-MHz steps until a failure: {g.mem_tests}")
bp = t.best_profile
check(t.state == TunerState.DONE and bp and bp.mem_offset_mhz == 700,
      f"+800 passed, +900 failed -> +700 (100 MHz safety): {bp.mem_offset_mhz if bp else None}")
check(g.finals and g.finals[-1][1] == 700, f"final test ran WITH the memory offset: {g.finals}")
check(any("+800 MHz bestanden, +900 nicht → +700 MHz übernommen" in m for m in logs), "log explains the choice")
check(not any("Bandbreiten-Maximum" in m for m in logs), "no bandwidth-peak search any more")
cores = {c for c, m, p in g.applied if m in (500, 600, 700, 800, 900)}
check(len(cores) == 1 and min(cores) > 0, f"every memory step on the found core offset: {cores}")

print("with FurMark 2: it runs during every memory step")
g = GPU(mem_limit=5000, fm_mem_limit=650)
t, logs = tune(g, furmark=True, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check([m for m, s, a in g.furmarks] == [500, 600, 700] and all(a == 8 for m, s, a in g.furmarks),
      f"FurMark (8x MSAA) with each memory step: {g.furmarks}")
check(t.best_profile and t.best_profile.mem_offset_mhz == 500,
      "FurMark crashed at +700 while the copies passed -> +500")
check(any("Mem+700MHz ✗" in m and "FurMark" in m for m in logs), "the failure names FurMark")

print("the start value fails: down from +500")
g = GPU(mem_limit=300)
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(g.mem_tests == [500, 400, 300] and t.best_profile and t.best_profile.mem_offset_mhz == 200,
      f"+500 / +400 failed, +300 passed -> +200: {g.mem_tests}")

print("the copies get no GPU time next to FurMark: the check is too weak")
g = GPU(mem_limit=5000, weak_from=700)
t, logs = tune(g, furmark=True, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(g.mem_tests == [500, 600, 700, 700] and t.best_profile and t.best_profile.mem_offset_mhz == 600,
      f"+700 weak, tried once more, still weak -> stays at +600 (last real check): {g.mem_tests}")
check(any("Prüfung zu schwach" in m or "check too weak" in m for m in logs)
      and any("keine aussagekräftige Prüfung" in m or "no meaningful check" in m for m in logs),
      "the log says why")
g = GPU(mem_limit=5000, weak_from=700, weak_times=1)
t, logs = tune(g, furmark=True, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(g.mem_tests == [500, 600, 700, 700, 800, 900, 1000] and t.best_profile.mem_offset_mhz == 1000,
      f"weak once (e.g. the FurMark window was clicked), fine on the repeat -> goes on: {g.mem_tests}")
g = GPU(mem_limit=5000, weak_from=0)
t, logs = tune(g, furmark=True, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(t.state == TunerState.DONE and t.best_profile and t.best_profile.mem_offset_mhz == 0
      and g.mem_tests == [500, 500],
      "weak from the start: memory stays at stock, the tune still finishes (not 'even +0 fails')")

print("even +0 fails: no profile, back to stock")
g = GPU(mem_limit=-1)
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(g.mem_tests == [500, 400, 300, 200, 100, 0] and t.state == TunerState.ERROR
      and t.best_profile is None and any("schon +0 MHz" in m for m in logs),
      "the core setting fails the whole-card load: error, no profile")
check(g.applied[-1] == (0, 0, 100) and not g.finals, "card back on stock, no final test")

print("memory stage off")
g = GPU()
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=False)
check(g.mem_tests == [] and t.best_profile and t.best_profile.mem_offset_mhz == 0,
      "no memory steps, profile memory +0")
check(any("Stage 4 skipped" in m or "Stage 4 übersprungen" in m for m in logs), "log says so")

print("'Mem Max' is respected")
g = GPU(mem_limit=5000)
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1100)
check(g.mem_tests == [500, 600, 700, 800, 900, 1000, 1100] and t.best_profile.mem_offset_mhz == 1100,
      f"up to the limit, tested once, kept without a failure: {g.mem_tests}")

print("memory only (no clock gain, power limit kept) uses the same stage")
g = GPU(mem_limit=800)
t, logs = tune(g, mode=TuneMode.OC_UV, core_max_mhz=0, power_min_pct=100, mem_stage=True,
               mem_oc_max_mhz=1000)
check(t.best_profile and t.best_profile.mem_offset_mhz == 700, "memory only: +700 as well")

print("final test fails on memory: one 100-MHz step back")
g = GPU(mem_limit=5000, final_mem_limit=900)
t, logs = tune(g, mode=TuneMode.OC_UV, mem_stage=True, mem_oc_max_mhz=1000)
check(t.state == TunerState.DONE and t.best_profile and t.best_profile.mem_offset_mhz == 900
      and any("Speicher +1000→+900 MHz" in m for m in logs),
      f"memory +1000 → +900 (was: halved): {t.best_profile.mem_offset_mhz if t.best_profile else None}")

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
check(gpu.v_mode.get() == "curve" and gpu.v_mem_stage.get() is True,
      "Rundum is the start mode, 'Speicher mit übertakten' on")
check(gpu.v_mem_max.get() == min(1000, get_defaults(name).mem_max_mhz),
      f"Rundum: memory up to +1000 (whole-card test): +{gpu.v_mem_max.get()} MHz")
check(not hasattr(gpu, "v_mem_off"), "the fixed 'Mem Offset' field is gone")
gpu.v_mem_stage.set(False)
gpu._select_mode("oc_uv")
check(gpu.v_mem_stage.get() is True and gpu.v_mem_max.get() == get_defaults(name).mem_max_mhz,
      f"'Schnell (OC + UV)': memory on, 'Mem Max' from the generation table for {name!r}")
gpu._start_tune()
cfg = started[-1] if started else None
check(cfg is not None and cfg.mem_stage and cfg.mem_oc_max_mhz == gpu.v_mem_max.get()
      and cfg.mem_curve_start_mhz == gpu._mem_start() and cfg.mem_curve_step_mhz == 100
      and cfg.furmark_path == gpu._furmark_v2() and cfg.mem_offset_mhz == 0,
      "tuner config: whole-card memory stage (cautious start, 100-MHz steps, FurMark), no fixed offset")
check(ASKED and f"Speicher: +{gpu._mem_start()} bis +{gpu.v_mem_max.get()} MHz in 100er-Schritten, "
      f"ganze Karte unter Last" in ASKED[-1] and "40-55" in ASKED[-1],
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
