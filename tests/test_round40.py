"""Round 40 — after the tune series of 23./24.10.: a failure in the flat part of a curve capped
between two points is not booked on a point that never ran that clock; profiles keep which final
tests they passed and the comparison shows it ("mit Härtetest"); the comparison names the profile
that beats another in both. Pure logic, no GPU."""
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


TMP = tempfile.mkdtemp(prefix="gop_r40_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"
from core import profile_score as PS  # noqa: E402
from core.nvtune_core import TuneProfile  # noqa: E402
from core.nvtune_tuner import AutoTuner, TunerConfig  # noqa: E402

print("what a failure at the cap teaches")
CUR = [(925, 2546), (950, 2666), (975, 2727), (1000, 2727), (1025, 2774), (1050, 2849), (1075, 2909)]
LP = AutoTuner._learn_point
check(LP(CUR, 1035, 1035) == (), "24.10.: flat from 1035 mV (between 1025 and 1050) failed at the cap -> nothing "
                                  "booked (was: 1050 mV at 2864, a clock that never ran)")
check(LP(CUR, 1035, 1038) == () and LP(CUR, 1035, 1031) == (), "a reading a few mV off the cap: still the cap")
check(LP(CUR, 1025, 1025) == (1025, 2774), "23.10.: capped AT a measured point (1025) -> booked there, as before")
check(LP(CUR, 1035, 990) == (1000, 2727), "a failure below the cap, on the curve -> the point at or above it")
check(LP(CUR, 0, 1035) == (1050, 2849), "no cap: the next point above, as before")

print("profiles keep their final tests")
p = TuneProfile(name="x", final_tests=["verify", "furmark", "game", "hard", "encoder"])
check(TuneProfile.from_dict(p.to_dict()).final_tests == p.final_tests, "saved and read back")
check(TuneProfile.from_dict({"name": "alt", "core_offset_mhz": 50}).final_tests == [],
      "an old profile file without the field: nothing recorded")


def tuner(**cfg):
    return AutoTuner(types.SimpleNamespace(read=lambda: None), types.SimpleNamespace(), None,
                     TunerConfig(**cfg), log_dir=os.path.join(TMP, "l"))


t = tuner(hard_test=True, game_test=True, encoder_companion=True)
check(t._passed_tests(True) == ["verify", "furmark", "game", "hard", "encoder"]
      and t._passed_tests(False) == ["verify", "game", "hard", "encoder"],
      "All-round: compute check, 5-min FurMark, game test, hardness test, encoder; Quick without the FurMark")
t._hard_skipped = True
check("hard" not in t._passed_tests(True), "the hardness test could not finish (FurMark closed twice): not listed")
check(tuner(hard_test=False, game_test=False)._passed_tests(True) == ["verify", "furmark"], "switched off: not listed")

print("the comparison says which had the hardness test")
TL = PS.tests_label
check(TL(TuneProfile(name="n", is_stable=True, final_tests=["verify", "hard"])) == "bestanden · mit Härtetest"
      and TL(TuneProfile(name="n", is_stable=True, final_tests=["verify", "game"])) == "bestanden · ohne Härtetest",
      "recorded: with / without the hardness test")
check(TL(TuneProfile(name="o", is_stable=True, created_at="2026-10-10T12:07:00")) == "bestanden · ohne Härtetest (gab es noch nicht)",
      "a profile from before 18.10.: the hardness test did not exist yet")
check(TL(TuneProfile(name="m", is_stable=True, created_at="2026-10-19T12:51:00")) == "bestanden",
      "in between (19.-23.10., not recorded): just 'passed'")
check(TL(TuneProfile(name="u", is_stable=False)) == "nicht bestanden", "not stable: not passed")
check(TL(TuneProfile(name="n", is_stable=True, final_tests=["hard"]), de=False) == "passed · with the hardness test", "English")

print("better in both")
sc = lambda perf, eff: {"perf_pct": perf, "eff_pct": eff}  # noqa: E731
real = {"max": sc(2.9, -1.0), "schnell": sc(1.9, -1.4), "eff": sc(-0.1, 5.8), "bal": sc(0.9, 4.7)}
check(PS.dominated_by(real) == {"schnell": ["max"]},
      f"24.10.: Max beats Schnell in both (faster, not less frugal); the others each win somewhere: "
      f"{PS.dominated_by(real)}")
check(PS.dominated_by({"a": sc(1.0, 3.0), "b": sc(1.3, 3.4)}) == {}, "within the noise in both: nobody beaten")
check(PS.dominated_by({"a": sc(1.0, 3.0), "b": None}) == {}, "an unmeasured profile beats nobody")
check(PS.dominated_by({"old": sc(0.2, 6.9), "eff": sc(-0.1, 5.8)}) == {"eff": ["old"]},
      "honest by the numbers: Ausgewogen 19.10. beats Effizienz 23.10. in both (the tests row tells them apart)")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
