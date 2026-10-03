"""Tuner: a failed apply must end the tune (never 'test' an unapplied step)."""
import os, sys, time, types, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult
from core.nvtune_core import TuneProfile

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

# no real sleeping / stress in this simulation
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)
def fake_run(self, duration_s, max_temp, on_tick=None, mode="gemm"):
    r = StressResult(passed=True, avg_temp=60, max_temp=65, avg_core_mhz=2700,
                     avg_voltage_mv=1050, avg_gpu_usage=99)
    return r
NT.StressTester.run = fake_run


class Mon:
    def __init__(self):
        self.power_calls = []
        self.nv_ok = True
    def read(self):
        return types.SimpleNamespace(name="NVIDIA GeForce RTX 4080", temp=50, voltage_mv=1050,
                                     core_mhz=2700, gpu_power_w=250, gpu_usage=99, throttle="None")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w):
        self.power_calls.append(w); return self.nv_ok


class AB:
    def __init__(self, available=True, fail_on=None):
        self.available = available; self.fail_on = fail_on; self.calls = []
    def write_and_apply(self, slot, p):
        self.calls.append((p.name, p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct, p.lock_voltage_mv))
        if self.fail_on and len(self.calls) == self.fail_on:
            return False, "Afterburner-Profil: simulierter Fehler"
        return True, ""


# The Quick mode (OC + UV) is the classic path. "Only overclock" = power limit
# kept at 100 % (power_min_pct=100), "only the power limit" = core_max_mhz=0.
OC = dict(power_min_pct=100)
UV = dict(core_max_mhz=0, power_min_pct=85)


def run(mode, ab, mon, **cfg):
    tmp = tempfile.mkdtemp(prefix="gop_tun_")
    pm = NT.ProfileManager(os.path.join(tmp, "p"))
    base = dict(core_step_mhz=15, core_max_mhz=45, power_min_pct=85, game_test=False, core_safety_mhz=0, mem_safety_mhz=0)
    base.update(cfg)
    t = AutoTuner(mon, ab, pm, TunerConfig(mode=mode, **base), log_dir=os.path.join(tmp, "l"))
    logs, states = [], []
    t.on_log(lambda m, l: logs.append((l, m)))
    t.on_state(lambda s: states.append(s))
    t._run_safe()
    shutil.rmtree(tmp, ignore_errors=True)
    return t, logs, states

print("apply fails in Stage 1 (2nd write)")
ab, mon = AB(fail_on=2), Mon()
t, logs, states = run(TuneMode.OC_UV, ab, mon, **OC)
check(states[-1] == TunerState.ERROR, f"tune ends in ERROR (states: {[s.name for s in states][-3:]})")
check(any("Anwenden fehlgeschlagen" in m and "simulierter Fehler" in m for _, m in logs), "clear error logged")
check(not any("+15MHz ✓" in m for _, m in logs), "the unapplied +15 MHz step was NOT recorded as stable")
check(ab.calls[-1][0] == "__reset__" and ab.calls[-1][1:4] == (0, 0, 100), f"reset to stock afterwards: {ab.calls[-1]}")
check(mon.power_calls[-1] == 320.0, "NVML power back to stock")

print("full OC run with a working Afterburner")
ab, mon = AB(), Mon()
t, logs, states = run(TuneMode.OC_UV, ab, mon, **OC)
check(states[-1] == TunerState.DONE, f"DONE ({[s.name for s in states][-2:]})")
check([c[1] for c in ab.calls if c[0] == "__tuning__"][:4] == [0, 15, 30, 45], "steps 0/15/30/45 applied via Afterburner")

print("power limit only (no clock gain) WITHOUT Afterburner -> NVML only")
ab, mon = AB(available=False), Mon()
t, logs, states = run(TuneMode.OC_UV, ab, mon, **UV)
check(states[-1] == TunerState.DONE and ab.calls == [], "runs without Afterburner, no AB writes")
check(320.0 in mon.power_calls and 304.0 in mon.power_calls and 288.0 in mon.power_calls or
      (320.0 in mon.power_calls and min(mon.power_calls) <= 288.0),
      f"power steps set via NVML: {sorted(set(mon.power_calls), reverse=True)}")

print("power limit only without Afterburner and NVML refuses (no admin)")
ab, mon = AB(available=False), Mon(); mon.nv_ok = False
t, logs, states = run(TuneMode.OC_UV, ab, mon, **UV)
check(states[-1] == TunerState.ERROR and any("NVML nicht setzen" in m for _, m in logs),
      "error instead of 'testing' an unapplied power limit")

print("OC without Afterburner -> refused")
ab, mon = AB(available=False), Mon()
t, logs, states = run(TuneMode.OC_UV, ab, mon, **OC)
check(states[-1] == TunerState.ERROR and any("für Core-/Speicher-Offsets nötig" in m for _, m in logs),
      "clear error: Afterburner needed for offsets")

print("Rundum point lock (_apply_vf): a failed write raises, nothing is written after an abort")
ab, mon = AB(fail_on=1), Mon()
tmp = tempfile.mkdtemp(prefix="gop_tun_")
t = AutoTuner(mon, ab, NT.ProfileManager(os.path.join(tmp, "p")), TunerConfig(mode=TuneMode.CURVE),
              log_dir=os.path.join(tmp, "l"))
try:
    t._apply_vf(0, 975, 2600, 0)
    why = ""
except NT.TunerApplyError as e:
    why = str(e)
check("V/F-Kurve" in why and "simulierter Fehler" in why, f"failed curve write -> TunerApplyError ({why!r})")
t._stop.set()
check(t._apply_vf(0, 950, 2550, 0) is False and len(ab.calls) == 1, "after an abort: no write at all")
shutil.rmtree(tmp, ignore_errors=True)
check(set(m.value for m in TuneMode) == {"oc_uv", "curve"}, "two modes: Quick (OC + UV) and Rundum")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
