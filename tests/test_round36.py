"""Round 36 — what a live Efficiency tune taught (23.10.): the point at 1000 mV held 2832 MHz in
the search and failed at 2742 under 3D + encoder + load changes, four tries of half an hour each.
Learned limits kept per card, load changes in the point search, a closed FurMark window repeats
the run, the goal checked after the step-backs, the remaining time, the worker's new mode."""
import io
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


TMP = tempfile.mkdtemp(prefix="gop_r36_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"     # never the app's own list

from core import learned_limits as LL  # noqa: E402
from core import curve_tune as CT  # noqa: E402
import core.nvtune_tuner as NT  # noqa: E402
from core.nvtune_tuner import AutoTuner, StressResult, TunerConfig  # noqa: E402
from core import hardness_test as H  # noqa: E402

GPU = "NVIDIA GeForce RTX 4080"

# ── 1) learned limits ─────────────────────────────────────────────────────────
print("learned limits")
logs = os.path.join(TMP, "logs")
check(LL.load(logs, GPU) == {} and LL.summary({}) == "", "nothing learned yet: empty")
check(LL.record(logs, GPU, 1000, 2772, "Rechenprüfung") and LL.record(logs, GPU, 1000, 2742, "Härtetest")
      and not LL.record(logs, GPU, 1000, 2757, "Härtetest"),
      "per point the LOWEST clock that failed is kept (a higher one later learns nothing)")
got = LL.load(logs, GPU)
check(list(got) == [1000] and got[1000]["fail_mhz"] == 2742 and got[1000]["test"] == "Härtetest"
      and got[1000]["at"], f"read back with int keys, the test and the time: {got}")
check(LL.load(logs, "other GPU") == {} and LL.record(logs, "other GPU", 950, 2700),
      "per GPU: another card has its own list")
check(LL.summary(got).startswith("1000 mV ≤ 2727 MHz (") and LL.summary(got, de=False).startswith("1000 mV ≤ 2727 MHz"),
      f"summary: what the next tune uses (one step below): {LL.summary(got)}")
anchors = [(925, 2578), (950, 2678), (975, 2741), (1000, 2787), (1025, 2802), (1050, 2862)]
new, changed = LL.apply(anchors, got)
check(dict(new)[1000] == 2727 and dict(new)[975] == 2727 and dict(new)[1025] == 2802 and dict(new)[950] == 2678
      and changed == [(975, 2741, 2727), (1000, 2787, 2727)],
      f"applied: 1000 mV one step below the failure, 975 never faster than it, the rest kept: {changed}")
new2, ch2 = LL.apply([(950, 2678), (1050, 2862)], got)
check(dict(new2)[1050] == 2727 and dict(new2)[950] == 2678,
      f"50-mV points: the learned 1000 mV caps the next point above it (1050): {new2}")
check(LL.apply(anchors, {}) == (anchors, []), "nothing learned: the curve unchanged")
check(LL.point_at(anchors, 995) == (1000, 2787) and LL.point_at(anchors, 1080) == (1050, 2862)
      and LL.point_at(anchors, 0) == (),
      "a failure is booked on the point at or above the voltage the card ran (above all: the top point)")
check(LL.forget(logs, GPU) and LL.load(logs, GPU) == {} and LL.load(logs, "other GPU"),
      "forget one card; the other card's list stays")
check(LL.forget(logs) and LL.load(logs, "other GPU") == {}, "forget all")
Path(logs, LL.FILE).write_text("{broken", encoding="utf-8")
check(LL.load(logs, GPU) == {} and LL.record(logs, GPU, 1000, 2742), "a broken file is read as empty, then rewritten")

# ── 2) the goal after the step-backs (idea 3) ─────────────────────────────────
print("goal after the step-backs")
stock = CT.Candidate("Standard", score=7294, power_w=250)
ok_eff = CT.Candidate("", score=7250, power_w=225)
low_eff = CT.Candidate("", score=7150, power_w=215)
check(AutoTuner._goal_after("efficiency", ["Kurve −15"], stock, ok_eff) == "",
      "efficiency: 99.4 % of stock — still the goal, no note")
n = AutoTuner._goal_after("efficiency", ["Kurve −15"], stock, low_eff)
check("98.0 %" in n and "unter den 99 %" in n and "Ausgewogen" in n,
      f"efficiency below 99 % after the step-backs: said, with the way out: {n}")
check(AutoTuner._goal_after("efficiency", [], stock, low_eff) == "",
      "no step-back: the benchmark picked it — nothing to say here")
nb = AutoTuner._goal_after("balanced", ["Kurve −15"], stock, CT.Candidate("", score=7250, power_w=240))
check("nicht mehr in beidem über Standard" in nb, f"balanced: slower than stock after the step-backs: {nb}")
check(AutoTuner._goal_after("balanced", ["x"], stock, CT.Candidate("", score=7400, power_w=245)) == ""
      and AutoTuner._goal_after("max", ["x"], stock, low_eff) == "",
      "balanced above stock in both / max: nothing to say")
I18N._current_lang = "en"
check("below the 99 %" in AutoTuner._goal_after("efficiency", ["x"], stock, low_eff), "the note in English")
I18N._current_lang = "de"


# ── 3) a tuner without hardware ───────────────────────────────────────────────
class Mon:
    def read(self):
        return types.SimpleNamespace(name=GPU, temp=40, core_mhz=210.0, voltage_mv=700.0, gpu_power_w=20.0,
                                     gpu_usage=0.0, mem_mhz=10000.0)


def tuner(**cfg):
    t = AutoTuner(Mon(), types.SimpleNamespace(), None, TunerConfig(**cfg), log_dir=os.path.join(TMP, "tl"))
    t._log_lines = []
    t.on_log(lambda m, lvl: t._log_lines.append(m))
    return t


print("remaining time")
t = tuner(hard_test=True, game_test=True)
c = t.config
full = (c.final_test_s + 10 + c.hard_test_min * 60 + 70 + c.game_cool_s + c.game_transient_s + c.game_boost_s + 10
        + c.final_bench_s + 15 + c.bench_s + 60 + 2 * (c.full_bench_s + 40))
check(t._final_est(True) == full and t._final_est(True, "hard:game_rec_compute") == full + 170
      and t._final_est(False) == full - c.final_bench_s - 15,
      f"final tests: every test + the after benchmark ({full / 60:.0f} min), +170 s for the load-change check, "
      f"Quick without the 5-min FurMark")
import time as _time  # noqa: E402
t._set_eta(600)
check(590 <= t.eta_end - _time.time() <= 600, "the end time: now + the estimate")

print("worker: boost, then load changes")
SEEN = []


class FakeProc:
    def __init__(self, cmd, **kw):
        SEEN.append((cmd, kw.get("env")))
        self.stdout = io.StringIO("")

    def poll(self):
        return 0


real_popen = NT.subprocess.Popen
NT.subprocess.Popen = FakeProc
try:
    st = NT.StressTester(Mon())
    st.split_s = 30
    st.start("boost_trans", stop_file=os.path.join(TMP, "stop"))
    st.start("boost")
finally:
    NT.subprocess.Popen = real_popen
check(SEEN and SEEN[0][0][-1] == "boost_trans" and (SEEN[0][1] or {}).get("GOP_STRESS_SPLIT_S") == "30"
      and "GOP_STRESS_SPLIT_S" not in (SEEN[1][1] or {}),
      "the tester passes the split (seconds of the boost load) only to the point search's mode")

print("point search: load changes in every step")


class FakeStress:
    companion = None
    companion_off = ""

    def __init__(self):
        self.split_s, self.runs = 30.0, []

    def run(self, d, m, on_tick=None, mode="gemm"):
        self.runs.append((d, mode, self.split_s))
        return StressResult(passed=True, steady_voltage_mv=1000.0, avg_core_mhz=2800.0, max_core_mhz=2800.0)


t = tuner(step_test_s=45)
t._apply_vf = lambda *a, **k: True
NT.time.sleep = lambda s: None
fs = FakeStress()
pt = t._test_point(fs, 1000, 2800, 2640, "Punkt 1/1", 20)
check(pt.passed and fs.runs == [(45, "boost_trans", 30)],
      f"45-s step: 30 s boost load (the voltage is read there), then 15 s load changes, one run: {fs.runs}")
t = tuner(step_test_s=45, point_transient_s=0)
t._apply_vf = lambda *a, **k: True
fs = FakeStress()
t._test_point(fs, 1000, 2800, 2640, "Punkt 1/1", 20)
check(fs.runs == [(45, "boost", 30.0)], "point_transient_s=0: the boost load alone, as before")
t = tuner(step_test_s=15)
t._apply_vf = lambda *a, **k: True
fs = FakeStress()
t._test_point(fs, 1000, 2800, 2640, "Punkt 1/1", 20)
check(fs.runs == [(15, "boost", 30.0)], "a 15-s step is too short to split: the boost load alone")
t = tuner(step_test_s=20)
t._apply_vf = lambda *a, **k: True
fs = FakeStress()
t._test_point(fs, 1000, 2800, 2640, "Punkt 1/1", 20)
check(fs.runs == [(20, "boost_trans", 10)], "a 20-s step: at least 10 s boost load, the rest load changes")

print("hardness test: FurMark closed by hand")


class FakeHard:
    results, calls = [], []

    def __init__(self, read_stats, logs_dir, **kw):
        FakeHard.calls.append(kw.get("only"))

    def run(self):
        return FakeHard.results.pop(0)


t = tuner(hard_test=True)
t.hardness_factory = FakeHard
FakeHard.results = [H.HardResult(aborted=True, kind="stopped", reason="FurMark wurde geschlossen"),
                    H.HardResult(passed=True, max_mhz=2800, max_mv=1000)]
r = t._hard_test(97, {"name": "x"})
check(r.passed and not r.aborted and len(FakeHard.calls) == 2
      and any("der Härtetest wird wiederholt" in m for m in t._log_lines),
      "closed once: the hardness test runs again and gives its verdict")
FakeHard.calls = []
FakeHard.results = [H.HardResult(aborted=True, kind="stopped", reason="x"), H.HardResult(aborted=True, kind="stopped",
                                                                                     reason="x")]
r = t._hard_test(97, {"name": "x"})
check(r.passed and r.aborted and len(FakeHard.calls) == 2,
      "closed twice: no verdict (the profile is not thrown away), no third try")
FakeHard.calls = []
FakeHard.results = [H.HardResult(kind="compute", reason="Rechenfehler", phase="Spiel + Aufnahme + Rechnen",
                                 phase_key="game_rec_compute", point={"mv": 995})]
r = t._hard_test(97, {"name": "x"}, "game_rec_compute")
check(not r.passed and r.stage == "hard:game_rec_compute" and FakeHard.calls == [("game_rec_compute",)]
      and r.last_voltage_mv == 995,
      "one phase on its own: the failure names its phase (the next try starts there) and its voltage")
check(t._stage_name("hard:game_rec_compute") == "Härtetest-Phase „Spiel + Aufnahme + Rechnen“"
      and t._stage_name("verify") == "Rechenprüfung 120 s" and t._stage_name("bench") == "FurMark 5 min",
      "the tests' names in the log")
check(H.plan(2.5, 150, ("game_rec_compute",))[0][0] == "game_rec_compute" and len(H.plan(2.5, 150, ("game_rec_compute",))) == 1
      and [p[0] for p in H.plan(10, 150)][:4] == ["game_rec", "changes_rec", "game_rec_compute", "game_rec_mem"],
      "the hardness plan: one phase on its own, or the four in turn as before")

print("Quick mode: learned limits")


class Curve:
    def lock_point(self, mv):
        return types.SimpleNamespace(voltage_mv=float(mv), base_mhz={1000: 2640.0, 1050: 2760.0}.get(int(mv), 2500.0))


t = tuner()
t.ab = types.SimpleNamespace(base_curve=lambda slot: (Curve(), "test"))
LL.forget(t._log_dir)
check(t._learned_quick(150, GPU) == 150, "nothing learned: the offset as found")
LL.record(t._log_dir, GPU, 1000, 2742, "Härtetest")
check(t._learned_quick(150, GPU) == 87 and any("+150 → +87 MHz" in m for m in t._log_lines),
      "1000 mV failed at 2742 (stock 2640): the offset at most +87 (2727 there), said in the log")
check(t._learned_quick(60, GPU) == 60, "an offset below it stays")
LL.forget(t._log_dir)
t._learned_book_quick(GPU, 120, 995.0, "Härtetest")
check(LL.load(t._log_dir, GPU).get(995, {}).get("fail_mhz") == 2620,
      "a Quick failure is booked on the curve point it ran at (its stock clock + the offset)")
t.ab = types.SimpleNamespace()
check(t._learned_quick(150, GPU) == 150, "no Afterburner curve here: the offset unchanged")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
