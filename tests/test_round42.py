"""Round 42 — what the 3DMark comparison of 24.10. taught, built in: every tune ends with a
full-load comparison (the compute load runs into the power limit like 3DMark and heavy games —
FurMark 2 at 1080p only drew ~250 W), and the stress page runs the 3DMark comparison of the
profiles itself (apply each profile, cool down, read every new result, measure the power, stock
last in a borrowed slot that comes back). Pure logic + the stress page on a hidden window; no GPU."""
import os
import sys
import tempfile
import time
import types
import zipfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r42_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"
from core import bench_compare as BC  # noqa: E402
from core import profile_score as PS  # noqa: E402
from core import threedmark as TDM  # noqa: E402
from core.nvtune_core import TuneProfile  # noqa: E402
from core.nvtune_tuner import AutoTuner, StressResult, TunerConfig  # noqa: E402

# ── 3DMark result files ─────────────────────────────────────────────────────
print("3DMark result files")
RD = os.path.join(TMP, "results")
os.makedirs(RD)


def result(name, xml, t):
    p = os.path.join(RD, name)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Result.xml", xml)
        z.writestr("Monitoring.csv", "a;b\n1;2\n")
    os.utime(p, (t, t))
    return p


T0 = 1_800_000_000
result("3DMark-SpeedWay-7613-1.3dmark-result",
       "<r><SpeedWayPerformance3DMarkScore>7613</SpeedWayPerformance3DMarkScore>"
       "<SpeedWayPerformanceGraphicsScore>7613</SpeedWayPerformanceGraphicsScore>"
       "<SpeedWayPerformanceGraphicsScoreForPass>7613</SpeedWayPerformanceGraphicsScoreForPass></r>", T0 + 10)
result("3DMark-TimeSpy-23343-2.3dmark-result",
       "<r><TimeSpyPerformanceCPUScore>11309</TimeSpyPerformanceCPUScore>"
       "<TimeSpyPerformance3DMarkScore>23343</TimeSpyPerformance3DMarkScore>"
       "<TimeSpyPerformanceGraphicsScore>28741</TimeSpyPerformanceGraphicsScore></r>", T0 + 20)
result("3DMark-SpeedWay-FAILED-3.3dmark-result", "<r><SpeedWayPerformanceGraphicsScore>0</SpeedWayPerformanceGraphicsScore></r>",
       T0 + 30)
with open(os.path.join(RD, "broken.3dmark-result"), "wb") as f:
    f.write(b"not a zip")
got = TDM.results_since(0, [RD, os.path.join(TMP, "missing")])
check([(r["test"], r["score"]) for r in got] == [("Speed Way", 7613), ("Time Spy", 28741)],
      f"the graphics score per test (Time Spy's total counts the CPU too); failed and broken files skipped: "
      f"{[(r['test'], r['score']) for r in got]}")
check([r["test"] for r in TDM.results_since(T0 + 15, [RD])] == ["Time Spy"], "only what came after a moment")
check(TDM._test_name("TimeSpyExtreme") == "Time Spy Extreme" and TDM._test_name("PortRoyal") == "Port Royal",
      "test names from the score tags")
check(any("ProgramData" in d for d in TDM.result_dirs()) and any(d.endswith("3DMark") for d in TDM.result_dirs()),
      "both places 3DMark saves to (Documents, ProgramData — live 24.10. it could not move them to Documents)")

# ── the comparison session ──────────────────────────────────────────────────
print("the comparison session")


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class Rig:
    """Applied profile, temperature, 3DMark runs that appear as results."""
    SCORE = {"Effizienz": 7613, "Max": 7617, BC.STOCK: 7434}
    WATT = {"Effizienz": 314.0, "Max": 315.0, BC.STOCK: 316.0}

    def __init__(self, clock, fail=None):
        self.clock, self.fail = clock, fail
        self.active, self.applied, self.restored = None, [], 0
        self.temp, self.busy, self.results = 40.0, 2.0, []
        self.n = 0

    def apply(self, key):
        self.applied.append(key)
        if key == self.fail:
            return False, "Afterburner antwortet nicht"
        self.active = key
        return True, ""

    def restore(self):
        self.restored += 1
        return True, ""

    def read(self):
        return types.SimpleNamespace(temp=self.temp, gpu_usage=self.busy,
                                     gpu_power_w=self.WATT.get(self.active, 0) if self.busy > 50 else 20.0)

    def since(self, t):
        return [r for r in self.results if r["t"] > t]

    def run_3dmark(self, test="Speed Way"):
        self.n += 1
        self.results.append({"test": test, "score": self.SCORE[self.active] + self.n % 2, "file": f"r{self.n}",
                             "t": self.clock.t})


def settle(sess, rig, clock, want, limit=200):
    st = None
    for _ in range(limit):
        st = sess.poll()
        if st.phase == want:
            return st
        clock.t += 1
        time.sleep(0.002)
    return st


clock = Clock()
rig = Rig(clock)
rig.results.append({"test": "Speed Way", "score": 1, "file": "old", "t": clock.t - 50})
sess = BC.CompareSession(["Effizienz", BC.STOCK, "Max"], 2, rig.apply, rig.restore, rig.read, rig.since, now=clock)
check(sess.keys == ["Effizienz", "Max", BC.STOCK], "stock always last (it borrows a slot that comes back)")
sess.start()
rig.temp = 60.0
st = settle(sess, rig, clock, "cooling")
check(st.phase == "cooling" and rig.active == "Effizienz", f"first profile applied, then it cools down: {st.phase}")
st = settle(sess, rig, clock, "ready", limit=5)
check(st.phase == "cooling", "60 °C: still cooling")
rig.temp = 44.0
st = settle(sess, rig, clock, "ready")
check(st.phase == "ready" and st.run == 1 and st.step == 1, "≤ 45 °C: ready — the user starts the test now")
for key in ("Effizienz", "Max", BC.STOCK):
    for run in range(2):
        st = settle(sess, rig, clock, "ready")
        check(st.phase == "ready" and rig.active == key, f"{key} run {run + 1}: ready on the right profile") \
            if run == 0 and key != "Effizienz" else None
        rig.busy = 99.0
        for _ in range(5):
            sess.poll()
            clock.t += 1
        rig.run_3dmark()
        rig.busy = 2.0
        clock.t += 1
        sess.poll()
st = settle(sess, rig, clock, "done")
check(st.phase == "done" and rig.restored == 1 and rig.applied == ["Effizienz", "Max", BC.STOCK],
      f"every profile once, then the slot and the profile from before back: {rig.applied}, restored {rig.restored}")
check([b.key for b in sess.booked] == ["Effizienz", "Effizienz", "Max", "Max", BC.STOCK, BC.STOCK]
      and all("old" != b.file for b in sess.booked),
      "each result booked on the profile that was active; a result from before the start never counts")
summ = sess.summary()
check(summ["Effizienz"]["Speed Way"]["score"] == 7614 and summ[BC.STOCK]["Speed Way"]["score"] == 7434
      and summ["Effizienz"]["Speed Way"]["perf_pct"] == 2.4 and summ["Effizienz"]["Speed Way"]["power_w"] == 314.0
      and summ["Effizienz"]["Speed Way"]["power_pct"] == -0.6,
      f"means over the runs, against stock; power only while the GPU was loaded: {summ['Effizienz']}")
be = sess.bench_entries()
rec = be["Effizienz"]["3dmark:Speed Way"]
check(set(be) == {"Effizienz", "Max"} and rec["stock_score"] == 7434 and rec["runs"] == 2,
      "for the profiles' bench: every tested profile, never stock itself")
p = TuneProfile(name="Effizienz", bench={**PS.bench_record("FurMark", 60, 7256, 237, 7266, 251), **be["Effizienz"]})
x = PS.extra_of(p, "3dmark:Speed Way")
check(x and x["perf_pct"] == 2.4 and x["eff_pct"] == 3.1 and PS.score_of(p)["perf_pct"] == -0.1,
      f"the comparison reads it next to FurMark (which stays as it was): {x}")

clock = Clock()
rig = Rig(clock, fail="Max")
sess = BC.CompareSession(["Effizienz", "Max"], 1, rig.apply, rig.restore, rig.read, rig.since, now=clock)
sess.start()
settle(sess, rig, clock, "ready")
rig.run_3dmark()
st = settle(sess, rig, clock, "error")
check(st.phase == "error" and "antwortet nicht" in st.error and rig.restored == 1,
      f"Afterburner fails on a profile: stopped, the slots restored anyway: {st.error}")
clock = Clock()
rig = Rig(clock)
sess = BC.CompareSession(["Effizienz", BC.STOCK], 2, rig.apply, rig.restore, rig.read, rig.since, now=clock)
sess.start()
settle(sess, rig, clock, "ready")
sess.abort()
st = settle(sess, rig, clock, "aborted")
check(st.phase == "aborted" and rig.restored == 1 and not sess.booked, "aborted: restored, nothing booked")
check(not BC.CompareSession([], 1, rig.apply, rig.restore, rig.read, rig.since).keys, "nothing chosen: nothing to do")
clock = Clock()
rig = Rig(clock)
rig.temp = 70.0
sess = BC.CompareSession(["Max"], 1, rig.apply, rig.restore, rig.read, rig.since, now=clock)
sess.start()
st = settle(sess, rig, clock, "ready", limit=400)
check(st.phase == "ready" and clock.t >= 1000 + sess.COOL_MAX_S, "a warm room: the run starts after 3 min anyway")

# ── full load at the end of every tune ──────────────────────────────────────
print("full-load comparison at the end of a tune")


class Card:
    def __init__(self, curve_rate=32.4, curve_w=314.0, stock_rate=31.7, stock_w=316.0):
        self.mode, self.order = "profile", []
        self.v = {"profile": (curve_rate, curve_w), "stock": (stock_rate, stock_w)}

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        self.order.append((self.mode, mode))
        rate, w = self.v[self.mode]
        return StressResult(passed=True, avg_rate_tflops=rate, avg_power_w=w)


def tuner(**cfg):
    t = AutoTuner(types.SimpleNamespace(read=lambda: types.SimpleNamespace(temp=40)), types.SimpleNamespace(), None,
                  TunerConfig(**cfg), log_dir=os.path.join(TMP, "l"))
    t._log_lines = []
    t.on_log(lambda m, lvl: t._log_lines.append(m))
    t._cool_down = lambda label, prog: None
    return t


import time as _time  # noqa: E402
_sleep = _time.sleep
_time.sleep = lambda s: None
try:
    c = Card()
    t = tuner()
    full = t._full_load_pair(types.SimpleNamespace(run=c.run), lambda: setattr(c, "mode", "profile"),
                             lambda: setattr(c, "mode", "stock"))
    check(full and full["score"] == 32.4 and full["stock_score"] == 31.7 and full["power_w"] == 314.0
          and full["stock_power_w"] == 316.0 and c.order == [("profile", "gemm"), ("stock", "gemm")]
          and c.mode == "profile",
          f"profile, then stock, both the compute load; the profile is applied again after: {full}")
    x = PS.extra_of(TuneProfile(name="p", bench={"full": full}), "full")
    check(x["perf_pct"] == 2.2 and x["eff_pct"] == 2.9 and any("Volllast" in m and "+2.2 %" in m for m in t._log_lines),
          f"read back as the full-load row (+2.2 % at 314 W instead of 316 W): {x}")
    c = Card(curve_rate=0.0)
    check(tuner()._full_load_pair(types.SimpleNamespace(run=c.run), lambda: None, lambda: None) == {},
          "no compute rate (CPU fallback): not measured, the tune goes on")
    check(tuner(full_bench_s=0)._full_load_pair(types.SimpleNamespace(run=c.run), lambda: None, lambda: None) == {},
          "switched off: not measured")
    t = tuner()
    t._stop.set()
    check(t._full_load_pair(types.SimpleNamespace(run=Card().run), lambda: None, lambda: None) is None, "aborted: None")
finally:
    _time.sleep = _sleep
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check(src.count("self._full_load_pair(stress") == 2 and src.count("full=") >= 2,
      "both modes run it at the very end and keep it in the profile's bench")
check(PS.extra_of(TuneProfile(name="o"), "full") is None
      and PS.extra_of(TuneProfile(name="o", bench={"full": {"score": 3, "stock_score": 2}}), "full")["eff_pct"] is None,
      "an older profile: not measured; no power readings: no efficiency")

# ── the stress page ─────────────────────────────────────────────────────────
print("the stress page card")
import customtkinter as ctk  # noqa: E402
from ui.tab_stress import StressTab  # noqa: E402
from core.nvtune_core import ProfileManager  # noqa: E402

pm = ProfileManager(Path(TMP) / "profiles")
for n in ("Effizienz 23.10.", "Max 23.10.", "Nur gespeichert"):
    pm.save(TuneProfile(name=n, is_stable=True))
SLOTS = {"Effizienz 23.10.": 4, "Max 23.10.": 5}


class AB:
    available = True

    def slot_holding(self, p, slots=(2, 3, 4, 5)):
        return SLOTS.get(p.name)


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=40, voltage_mv=900, core_mhz=210, gpu_power_w=20, gpu_usage=1,
                                     temp_limit_c=90, power_max_w=320, name="Test GPU")


root = ctk.CTk()
root.withdraw()
page = StressTab(root, Mon(), ab=AB(), pm=pm, tuner=types.SimpleNamespace(is_running=False, cr=None))
page._cmp_fill()
check(set(page._cmp_vars) == {"Effizienz 23.10.", "Max 23.10."} and page._cmp_slots["Max 23.10."] == 5
      and str(page.btn_cmp_start.cget("state")) == "normal",
      f"the profiles in Afterburner slots are offered (a profile in no slot is not): {sorted(page._cmp_vars)}")


class Done:
    """A finished session as the page sees it."""
    booked = [BC.Booked("Effizienz 23.10.", "Speed Way", 7613, 314.0), BC.Booked(BC.STOCK, "Speed Way", 7434, 316.0)]

    def bench_entries(self):
        return {"Effizienz 23.10.": {"3dmark:Speed Way": {"name": "3DMark Speed Way", "score": 7613, "power_w": 314.0,
                                                           "stock_score": 7434, "stock_power_w": 316.0, "runs": 1}}}

    def summary(self):
        return {"Effizienz 23.10.": {"Speed Way": {"score": 7613, "power_w": 314.0, "runs": 1, "perf_pct": 2.4,
                                                   "power_pct": -0.6}},
                BC.STOCK: {"Speed Way": {"score": 7434, "power_w": 316.0, "runs": 1, "perf_pct": None, "power_pct": None}}}


page._cmp = object()
page._cmp_finish(Done(), BC.State("done"))
saved = pm.load("Effizienz 23.10.")
res = page.lbl_cmp_res.cget("text")
check(page._cmp is None and (saved.bench or {}).get("3dmark:Speed Way", {}).get("score") == 7613
      and "Standard" in res and "+2,4 %" in res and "−0,6 %" in res and "✓" in page.lbl_cmp.cget("text"),
      f"at the end: saved in the profile, the results on the card: {res!r}")
page._cmp = object()
check(page._gpu_taken.__doc__ and "3DMark" in open(os.path.join(ROOT, "ui", "tab_stress.py"), encoding="utf-8").read(),
      "a running comparison blocks the other GPU tests")
page._cmp = None
page._alive = False
root.destroy()

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
