"""Round 39 — from the tunes of 23./24.10.: the point search (and the Quick offset search) stops at
the learned limit plus the margin taken off afterwards — above it nothing can change the result,
and all four driver resets of 23.10. happened there; a run with driver faults ends with "restart
before playing" (live: FPS drops every ~20 s until the PC was restarted). No GPU: fake cards."""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r39_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"     # never the app's own list
from core import curve_tune as CT  # noqa: E402
from core import gpu_flight  # noqa: E402
from core import learned_limits as LL  # noqa: E402
import core.nvtune_tuner as NT  # noqa: E402
from core.nvtune_tuner import AutoTuner, StressResult, TuneMode, TunerConfig, TunerState  # noqa: E402

GPU = "NVIDIA GeForce RTX 4080"
MVS = [1075, 1050, 1025, 1000, 975, 950, 925]
LEARNED = {1000: {"fail_mhz": 2742}, 1025: {"fail_mhz": 2804}}

print("caps before the point search")
caps = LL.search_caps(MVS, LEARNED)
check(caps == {1025: 2789, 1000: 2727, 975: 2727, 950: 2727, 925: 2727},
      f"1025 and 1000 capped, every point below them too (never faster below): {caps}")
check(LL.search_caps(MVS, {}) == {}, "nothing learned: no cap")
check(LL.search_caps([1070, 1045, 1020, 995, 970], LEARNED) == {1020: 2789, 995: 2727, 970: 2727},
      "the 25-mV grid of the evening tunes: the nearest point at or above a learned one")


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=55, voltage_mv=1050, core_mhz=2900, gpu_usage=99, power_capped=False,
                                     gpu_power_w=250, throttle_protective=False, throttle="", mem_mhz=10500,
                                     name=GPU)

    def power_pct_to_watts(self, pct):
        return round(320 * pct / 100, 1)

    def set_power_limit(self, w):
        return True


def tuner(log_dir, **cfg):
    t = AutoTuner(Mon(), types.SimpleNamespace(), None, TunerConfig(**cfg), log_dir=log_dir)
    t._log_lines = []
    t.on_log(lambda m, lvl: t._log_lines.append(m))
    return t


ld = os.path.join(TMP, "tl")
t = tuner(ld, curve_safety_mhz=30, curve_safety_top_mhz=45, curve_reset_extra_mhz=30)
check(t._learned_search_limits(GPU, MVS) == {}, "nothing learned: the search is not limited")
for mv, e in LEARNED.items():
    LL.record(ld, GPU, mv, e["fail_mhz"], "Härtetest")
lim = t._learned_search_limits(GPU, MVS)
check(lim == {1025: 2789 + 45, 1000: 2727 + 45, 975: 2727 + 30, 950: 2727 + 30, 925: 2727 + 30},
      f"limit = cap + the margin taken off there (−45 within 75 mV of the top, −30 below): {lim}")
import json  # noqa: E402
Path(ld, "gpu_field_faults.json").write_text(json.dumps([{"t": 1, "gpu": GPU, "mv": 1050}]), encoding="utf-8")
lim_f = t._learned_search_limits(GPU, MVS)
check(lim_f[1025] == 2789 + 45 + 30 and lim_f[1000] == 2727 + 45,
      f"a game hung at 1050 mV: +30 more margin at the points within 25 mV of it: {lim_f}")
Path(ld, "gpu_field_faults.json").unlink()

print("the limited search ends at the same curve, without the tests above it")


def card(mv, f):
    """The live card of 23.10. (steady load): what each point held in the search; a driver reset
    above 2770 at 975 mV, as seen at 2774 / 2779."""
    held = {1075: 2977, 1050: 2939, 1025: 2879, 1000: 2824, 975: 2764, 950: 2701, 925: 2608}[mv]
    return CT.PointTest(passed=f <= held, reached=True, reason="" if f <= held else "Rechenfehler",
                        tdr=(mv == 975 and f > 2770))


base = {1075: 2805, 1050: 2760, 1025: 2700, 1000: 2640, 975: 2565, 950: 2490, 925: 2370}


def search(limits):
    res, tested, prior = [], [], 90
    for mv in MVS:
        lmax = limits.get(mv) or base[mv] + 350
        r = CT.search_anchor(lambda v, f: (tested.append((v, f)), card(v, f))[1], mv, base[mv],
                             min(base[mv] + prior, lmax), max_mhz=lmax)
        at = mv in limits and r.best_mhz >= limits[mv]
        prior = max(prior, r.offset) if at else r.offset
        res.append(r)
    CT.apply_margins(res, 30, 45, 30)
    return LL.apply(CT.curve_anchors(res), LEARNED)[0], tested, res


free, t_free, r_free = search({})
capped, t_cap, r_cap = search(lim)
fd, cd = dict(free), dict(capped)
check(all(fd[mv] == cd[mv] for mv in (1075, 1050, 1025, 1000)),
      f"the points down to 1000 mV exactly as with the full search: {capped}")
check(fd[975] == 2704 and cd[975] == 2727 == caps[975],
      "975 mV: the full search's driver reset (2779, far above the cap) cost 30 MHz extra there — without it "
      "the point sits at the learned cap (the final tests check the curve as a whole)")
check(all(abs(fd[mv] - cd[mv]) <= 5 for mv in (950, 925)),
      f"below: within the search's precision (±5 MHz, another start): {fd[950]}/{cd[950]}, {fd[925]}/{cd[925]}")
check(all(f <= lim.get(v, 10 ** 6) for v, f in t_cap) and len(t_cap) < len(t_free),
      f"never a step above the limit; {len(t_free)} → {len(t_cap)} steps")
check(any(r.tdr for r in r_free) and not any(r.tdr for r in r_cap),
      "the driver reset at 975 mV (2779) is not even provoked any more")

print("Quick: the offset search stops at the learned limit")


class Curve:
    def lock_point(self, mv):
        return types.SimpleNamespace(voltage_mv=float(mv), base_mhz=2640.0 if int(mv) == 1000 else 2500.0)


class Card:
    """Core unstable above +100 (steady) / +70 under load changes (test_round16's card)."""
    def __init__(self):
        self.core, self.mem, self.pwr, self.runs = 0, 0, 100, []

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        self.runs.append((mode, self.core))
        r = StressResult(passed=True, avg_temp=60, max_temp=64, avg_voltage_mv=1000, steady_voltage_mv=1000,
                         avg_gpu_usage=99, avg_core_mhz=2800 + self.core, max_core_mhz=2900 + self.core,
                         avg_rate_tflops=40.0, last_voltage_mv=1000)
        if self.core > (70 if mode == "transient" else 100):
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r


class AB:
    available = True

    def __init__(self, gpu):
        self.gpu = gpu

    def write_and_apply(self, slot, p, startup="same"):
        self.gpu.core, self.gpu.mem, self.gpu.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
        return True, ""

    def base_curve(self, slot=2):
        return Curve(), "test"


def quick(learned_fail=0):
    g = Card()
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": g.run(d, m, on_tick, mode)
    tmp = tempfile.mkdtemp(prefix="q_", dir=TMP)
    lg = os.path.join(tmp, "l")
    if learned_fail:
        LL.record(lg, GPU, 1000, learned_fail, "Härtetest")
    q = AutoTuner(Mon(), AB(g), NT.ProfileManager(os.path.join(tmp, "p")),
                  TunerConfig(mode=TuneMode.OC_UV, core_step_mhz=15, core_max_mhz=300, power_min_pct=100,
                              crash_pause_s=0, game_cool_s=0), log_dir=lg)
    logs = []
    q.on_log(lambda m, lvl: logs.append(m))
    q._run_safe()
    return q, g, logs


q0, g0, _l0 = quick()
q1, g1, l1 = quick(2672)                 # +17 allowed at 1000 mV (stock 2640): search up to +77
stage1 = [c for m, c in g1.runs if m == "mixed"][:-1]
check(q1.state == TunerState.DONE and q1.best_profile.core_offset_mhz == 17
      and q0.best_profile.core_offset_mhz == 37,
      "the same capped result (+17) as before; without a learned limit +37 as in round 16")
check(max(stage1) <= 77 and any("Suche nur bis +77 MHz" in m for m in l1)
      and any("bis zur gelernten Grenze +77MHz gesucht" in m for m in l1),
      f"no step above +77 (= +17 + 60 margin): {stage1}")
check(len([1 for m, _c in g1.runs if m == "mixed"]) < len([1 for m, _c in g0.runs if m == "mixed"]),
      "fewer steps than the free search")

print("the memory cross-check runs twice as long as the failure took")
t = tuner(os.path.join(TMP, "cc"), crash_pause_s=0, final_test_s=120)
calls = []


def stage(stress, key, prog, profile, min_s=0, passed=True):
    calls.append((key, min_s, profile.get("mem_offset_mhz")))
    return StressResult(passed=passed, stage=key)


t._run_stage = stage


def fail(key, at):
    return StressResult(passed=False, crash_detected=True, compute_error=True, stage=key, fail_at_s=at,
                        last_voltage_mv=1035)


check(t._cross_check(None, fail("hard:game_rec_compute", 140), 500, lambda: None, 0, {"mem_offset_mhz": 500})
      == ("mem", 1035) and calls[-1] == ("hard:game_rec_compute", 280, 0)
      and any("4.7 min — doppelt so lange wie bis zum Fehler" in m for m in t._log_lines),
      f"live 24.10.: failed after 140 s -> the cross-check runs 280 s with memory +0: {calls[-1]}")
t._cross_check(None, fail("hard:game_rec_compute", 12), 500, lambda: None, 0, {})
check(calls[-1][1] == 0, "failed after 12 s: the phase's own 150 s are enough")
t._cross_check(None, fail("hard:game_rec_compute", 420), 500, lambda: None, 0, {})
check(calls[-1][1] == 600, "at most 10 minutes")
t._cross_check(None, fail("verify", 100), 500, lambda: None, 0, {})
check(calls[-1] == ("verify", 200, 0), "the compute check: 200 s instead of 120")
t._cross_check(None, fail("game:transient", 200), 500, lambda: None, 0, {})
check(calls[-1][1] == 0, "the game test keeps its own length")
t._run_stage = lambda *a, **k: AutoTuner._run_stage(t, *a, **k)
t._run_stage_once = lambda stress, key, prog, profile, min_s: StressResult(passed=False, stage=key)
check(t._run_stage(None, "verify", 0, {}).fail_at_s >= 0 and t._run_stage(None, "verify", 0, {}).stage == "verify",
      "a failure records when it failed")


class Hard:
    made = []

    def __init__(self, read, logs, minutes=10, only=None, **kw):
        Hard.made.append((minutes, only))

    def run(self):
        from core.hardness_test import HardResult
        return HardResult(kind="compute", reason="x", at_s=133.0, point={"mv": 1035})


t = tuner(os.path.join(TMP, "hd"))
t.hardness_factory = Hard
r = t._hard_test(0, {}, "game_rec_compute", 280)
check(Hard.made[-1] == (280 / 60, ("game_rec_compute",)) and r.fail_at_s == 133.0,
      f"the hardness phase runs the longer time (two phases of 140 s); the failure's time kept: {Hard.made[-1]}")
t._hard_test(0, {}, "game_rec_compute")
check(Hard.made[-1][0] == 2.5, "without it: one phase of 150 s as before")

print("restart before playing after driver faults")
t = tuner(os.path.join(TMP, "rh"))
real = gpu_flight.events_since
gpu_flight.events_since = lambda since, ids=None, log="System": [
    (100.0, "nvlddmkm", 153), (101.0, "nvlddmkm", 153), (130.0, "Display", 4101), (900.0, "nvlddmkm", 13)]
check(t._driver_faults_since(0) == 2, "entries within a minute are one fault: 2 faults")
shown = []
import core.notify as notify  # noqa: E402
notify.show = lambda title, msg, fallback=None: shown.append(msg) or True
t._restart_hint(0)
check(t.restart_hint == 2 and any("Vor dem Spielen den PC einmal neu starten" in m for m in t._log_lines)
      and shown and "neu starten" in shown[0],
      f"the log and a tray notification say: restart before playing ({shown})")
gpu_flight.events_since = lambda since, ids=None, log="System": []
t._log_lines.clear()
t._restart_hint(0)
check(t.restart_hint == 0 and not t._log_lines, "no driver fault: nothing said")


def _raise(*a, **k):
    raise OSError("no event log")


gpu_flight.events_since = _raise
check(t._driver_faults_since(0) == 0, "event log not readable: no hint, no error")
gpu_flight.events_since = real

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
