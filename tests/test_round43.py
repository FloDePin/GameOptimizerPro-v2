"""Round 43 — the last audit of 24.10., the confirmed points: one busy check for every GPU test on
the stress page (3DMark itself may start during the comparison), the comparison's way back (boot
slot when the last profile is unknown, no double load) and a run started too early; the cross-check
as long as the time into the failed hardness PHASE; a cool-down reference for every run; Quick's
flat curve through the guarded apply; Efficiency's power limit after the final tests and not tried
when the curve is short already at 100 %; robust 3DMark score tags; English texts. No GPU."""
import os
import sys
import tempfile
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


TMP = tempfile.mkdtemp(prefix="gop_r43_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"
from core import bench_compare as BC  # noqa: E402
from core import threedmark as TDM  # noqa: E402
from core.hardness_test import HardResult  # noqa: E402
from core.nvtune_core import TuneProfile  # noqa: E402
from core.nvtune_tuner import AutoTuner, StressResult, TuneMode, TunerApplyError, TunerConfig  # noqa: E402

SRC = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()

# ── the comparison: a run started too early, the result names ───────────────
print("3DMark comparison: a run started before the cool-down ended")


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


clock = Clock()
rig = types.SimpleNamespace(temp=60.0, results=[], active=None, restored=0)


def since(t):
    return [r for r in rig.results if r["t"] > t]


sess = BC.CompareSession(["A"], 1, lambda k: (True, ""), lambda: (True, ""),
                         lambda: types.SimpleNamespace(temp=rig.temp, gpu_usage=2, gpu_power_w=20),
                         since, now=clock, names=lambda: ["old.3dmark-result"])
sess.start()
st = None
for _ in range(50):
    st = sess.poll()
    if st.phase == "cooling":
        break
    clock.t += 1
rig.results.append({"test": "Speed Way", "score": 7400, "file": "early", "t": clock.t})
clock.t += 1
st = sess.poll()
check(st.phase == "cooling" and st.note == "early" and not sess.booked,
      "a 3DMark run while the card still cools down: not counted, and said so (it used to be silently lost)")
rig.temp = 40.0
for _ in range(10):
    st = sess.poll()
    if st.phase == "ready":
        break
    clock.t += 1
rig.results.append({"test": "Speed Way", "score": 7613, "file": "ok", "t": clock.t + 1})
clock.t += 2
for _ in range(30):
    st = sess.poll()
    if st.phase == "done":
        break
    clock.t += 1
check(st.phase == "done" and [b.file for b in sess.booked] == ["ok"] and st.note == "",
      f"the next run at ▶ counts: {[b.file for b in sess.booked]}")
RD = os.path.join(TMP, "r")
os.makedirs(RD)
with open(os.path.join(RD, "a.3dmark-result"), "wb") as f:
    f.write(b"not opened")
check(TDM.result_names([RD, os.path.join(TMP, "none")]) == ["a.3dmark-result"],
      "what was there before the start: names only — no result file is opened")


def result(name, xml):
    p = os.path.join(RD, name)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Result.xml", xml)
    return TDM.parse_result(p)


r = result("sn.3dmark-result", "<r><SteelNomadPerformance3DMarkScore>7012</SteelNomadPerformance3DMarkScore></r>")
check(r and r["test"] == "Steel Nomad" and r["score"] == 7012, f"only a 3DMark score in the file: that one: {r}")
r = result("sw.3dmark-result", "<r><SpeedWayPerformance3DMarkScore>7700</SpeedWayPerformance3DMarkScore>"
                               "<SpeedWayPerformanceGraphicsScore>7613</SpeedWayPerformanceGraphicsScore></r>")
check(r and r["score"] == 7613, "the graphics score wins over the test's total")
r = result("x.3dmark-result", "<r><Fire2PerformanceGraphicsScore>123</Fire2PerformanceGraphicsScore>"
                              "<Fire2PerformanceCPUScore>9</Fire2PerformanceCPUScore></r>")
check(r and r["test"] == "Fire2" and r["score"] == 123, "a digit in the test's tag; the CPU score never counts")

# ── the stress page ─────────────────────────────────────────────────────────
print("stress page: one busy check, 3DMark during the comparison, the way back")
import customtkinter as ctk  # noqa: E402
from tkinter import messagebox  # noqa: E402
import ui.tab_stress as TS  # noqa: E402
from core.nvtune_core import ProfileManager  # noqa: E402

boxes = []
messagebox.showinfo = lambda *a, **k: boxes.append(a[1] if len(a) > 1 else "")
pm = ProfileManager(Path(TMP) / "profiles")
for n in ("Effizienz", "Max"):
    pm.save(TuneProfile(name=n, is_stable=True))


class AB:
    available = True
    calls: list = []
    SLOTS = {"Effizienz": 4, "Max": 5}

    def slot_holding(self, p, slots=(2, 3, 4, 5)):
        return self.SLOTS.get(p.name)

    def startup_state(self, slot):
        return slot == 4

    def load_profile_slot(self, slot):
        self.calls.append(("load", slot))
        return True, ""

    def reset_to_stock(self, slot, startup="same"):
        self.calls.append(("stock", slot, startup))
        return True, ""

    def write_and_apply(self, slot, p, startup="same"):
        self.calls.append(("write", slot, p.name, startup))
        return True, ""


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=40, voltage_mv=900, core_mhz=210, gpu_power_w=20, gpu_usage=1,
                                     temp_limit_c=90, power_max_w=320, name="Test GPU")


root = ctk.CTk()
root.withdraw()
ab = AB()
page = TS.StressTab(root, Mon(), ab=ab, pm=pm, tuner=types.SimpleNamespace(is_running=False, cr=None))
page._running_internal = True
check(page._busy_text() and page._gpu_taken() and boxes, "the internal test runs: every other GPU test says so")
page._running_internal = False
page._ext = object()
boxes.clear()
check(page._gpu_taken() and boxes, "a FurMark / 3DMark recording runs: the comparison and the others wait")
page._ext = None
page._cmp = object()
boxes.clear()
check("3DMark-Vergleich" in page._busy_text() and page._gpu_taken() and not page._gpu_taken(allow_cmp=True),
      "the comparison runs: the hardness test etc. wait — 3DMark itself may start (that is what it waits for)")
launched, sessions = [], []
TS.threedmark.launch = lambda path: (launched.append(path) or (True, "ok"))
page._3dmark_path = "C:/3DMark/3DMark.exe"
page._start_session = lambda *a, **k: sessions.append(a)
page._launch_3dmark()
check(launched and not sessions, "'Launch 3DMark' during the comparison: started, no second recording")
page._cmp = None
page._cmp_fill()
page._cmp_vars["Effizienz"].set(False)          # only Max: stock borrows slot 5, the boot slot is 4
page.after = lambda *a, **k: None
page._cmp_start()
sess = page._cmp
check(sess is not None, "started")
apply_, restore_ = sess._apply, sess._restore
AB.calls.clear()
apply_(BC.STOCK)
restore_()
check(AB.calls == [("stock", 5, None), ("write", 5, "Max", None), ("load", 4)],
      f"no profile recorded as applied: back to the boot slot (4) after the borrowed slot 5: {AB.calls}")
AB.SLOTS = {"Effizienz": 4, "Max": 4}
page._cmp = None
page._cmp_fill()
page._cmp_start()
AB.calls.clear()
page._cmp._apply(BC.STOCK)
page._cmp._restore()
check(AB.calls == [("stock", 4, None), ("write", 4, "Max", None)],
      f"the borrowed slot IS the one to go back to: applied once, not loaded a second time: {AB.calls}")
page._cmp = None
page._alive = False
root.destroy()

# ── tuner ───────────────────────────────────────────────────────────────────
print("tuner")


def tuner(**cfg):
    t = AutoTuner(types.SimpleNamespace(read=lambda: types.SimpleNamespace(temp=40)), types.SimpleNamespace(available=False),
                  None, TunerConfig(**cfg), log_dir=os.path.join(TMP, "l"))
    t._log_lines = []
    t.on_log(lambda m, lvl: t._log_lines.append(m))
    return t


class Hard:
    def __init__(self, *a, **k):
        pass

    def run(self):
        return HardResult(kind="compute", reason="x", phase="Spiel + Aufnahme + Rechnen", phase_key="game_rec_compute",
                          at_s=340.0, phase_at_s=20.0, point={"mv": 1035})


t = tuner()
t.hardness_factory = Hard
r = t._hard_test(0, {})
check(r.fail_at_s == 20.0 and r.stage == "hard:game_rec_compute",
      "the full hardness test failed 20 s into phase 3 (340 s into the test): the cross-check counts 20 s")
calls = []
t._run_stage = lambda stress, key, prog, profile, min_s=0: (calls.append(min_s), StressResult(passed=False))[1]
t.config.crash_pause_s = 0
t._cross_check(None, r if not r.passed else r, 500, lambda: None, 0, {})
check(calls == [0], f"so the phase runs its own 150 s — not 10 min: {calls}")
check(HardResult().phase_at_s == 0.0 and "self._phase_t0 = time.time() if phase is not None else 0.0"
      in open(os.path.join(ROOT, "core", "hardness_test.py"), encoding="utf-8").read(),
      "the hardness test keeps when the current phase began")
i = SRC.index("self._start_cool()\n") if "self._start_cool()\n" in SRC else SRC.index("self._start_cool()\r\n")
check("self._bench_ref_temp = self._start_temp()" in SRC[i:i + 600],
      "every run has a cool-down reference from its start (Quick without FurMark had none)")
q = SRC[SRC.index("def _q_profile():"):SRC.index("def _q_profile():") + 400]
check("self._apply_curve(quick_cap[0], quick_cap[1], best_mem_offset, best_pwr)" in q and "_ab_write" not in q,
      "Quick's flat curve through the guarded apply (nothing written after an abort, power limit set)")
check(SRC.count("reapply=False)") == 2, "the full-load pair leaves the profile to the save right after it")
base = tuner(goal="balanced", mode=TuneMode.CURVE)._final_est(True)
eff = tuner(goal="efficiency", mode=TuneMode.CURVE)._final_est(True)
check(eff - base == 6 * (TunerConfig().step_test_s + 5), f"the remaining time includes the power-limit stage: +{eff - base} s")
check("again = not (crit == \"bench\" and res is not None and res.passed)" in SRC,
      "a FurMark that passed as the try's first test does not run a second time")
check("proc.stdout.close()" in SRC, "the companion's pipe is closed with it")

print("English")
I18N._current_lang = "en"
t = tuner()
try:
    t._apply(25, 0, 100)
    msg = ""
except TunerApplyError as e:
    msg = str(e)
check(msg == "MSI Afterburner not found — needed for clock / memory offsets", f"the tuner's apply errors: {msg!r}")
src_ab = open(os.path.join(ROOT, "core", "ab_profile.py"), encoding="utf-8").read()
check('_tr("VFCurve zu kurz", "VFCurve too short")' in src_ab and "Own V/F curve from" in src_ab
      and "on every curve point" in src_ab, "the profile writer's errors and notes (shown after applying a profile)")
for rel, needle in (("ui/services_manager.py", 'tr("Lade …", "Loading …")'), ("ui/startup_manager.py", 'tr("AUS", "OFF")'),
                    ("ui/tab_settings.py", 'tr("Scanne …", "Scanning …")'), ("ui/tab_settings.py", 'tr("Bereinige …", "Cleaning …")')):
    check(needle in open(os.path.join(ROOT, rel), encoding="utf-8").read(), f"{rel}: {needle}")
I18N._current_lang = "de"

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
