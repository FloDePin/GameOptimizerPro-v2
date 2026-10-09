"""Round 23 — findings of the user's tune series (09.10., RTX 4080, FurMark 2, 60 s):
"Ausgewogen" picked flat from 1050 mV (+2.4 % / −0.5 %) — next to Max (+3.9 % / +1.7 %)
hardly a profile of its own, and between the 25-mV caps the efficiency jumped from −0.5 %
(1050 mV) to +6.2 % (1025 mV).
  * balanced = performance AND efficiency above stock, as evenly as possible (the smaller
    gain counts); the old rule (half the gain, most points per watt) is the fallback
  * a fine search benchmarks the cap halfway to the neighbour (balanced and efficiency)
  * the card's minimum voltage under load (never below ~920 mV) is remembered per GPU:
    the next tune plans its points down to it, the lowest one right at it
Pure logic with the series' real numbers — no GPU load."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r23_")
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the app's own file
import core.i18n as I18N
I18N._current_lang = "de"
from core import curve_tune as CT

mk = lambda cap, sc, w: CT.Candidate("", cap, 100, sc, w, 64, 2850, passed=True)
# a real RTX 40 curve: points ~6 mV apart around the caps
CURVE = [v for v in range(850, 1101) if v % 25 in (0, 6, 12, 18)] + [1075]

# ── 1) balanced: both gains above stock ───────────────────────────────────────
print("balanced: performance AND efficiency above stock (run 2 of the series)")
stock2 = CT.Candidate("Standard", score=7282, power_w=252, passed=True)
full, c1050, c1025 = mk(0, 7563, 264), mk(1050, 7455, 259), mk(1025, 7351, 240)
g = CT.gains(c1050, stock2)
check(g and round(g[0], 1) == 2.4 and -0.6 < g[1] < 0, f"gains vs stock: 1050 mV {g}")
check([CT.stop_testing("balanced", [full, c1050, c1025][:i + 1], stock2) for i in range(3)]
      == [False, False, True], "the same three caps are measured as on the real card (then stop)")
ch = CT.choose_candidate("balanced", [full, c1050, c1025], stock2)
check(ch is c1025, f"on the 25-mV grid: 1025 mV (+0.9 % / +6.2 %: the smaller gain 0.9 is the largest), "
                   f"not 1050 (−0.5 % efficiency): {ch.cap_mv}")
fine = CT.fine_cap("balanced", ch, [full, c1050, c1025], stock2, [1075, 1050, 1025, 1000], CURVE)
check(fine == (1037, 1025, 1050),
      f"fine search towards 1050 mV (performance is the smaller gain at 1025): {fine}")
c1037 = mk(1037, 7403, 250)                    # what the card did in between, interpolated
ch2 = CT.choose_candidate("balanced", [full, c1050, c1025, c1037], stock2)
g2 = CT.gains(c1037, stock2)
check(ch2 is c1037 and min(g2) > 1.5,
      f"the fine cap wins when it is better in both: +{g2[0]:.1f} % / +{g2[1]:.1f} %")
check(not CT.balanced_fallback([full, c1050, c1025], stock2)
      and CT.rule_text("balanced", [full, c1050, c1025], stock2).startswith("Leistung und Effizienz beide"),
      "rule named in log and report: both above stock")

print("balanced: fallback when nothing beats stock in both")
stock = CT.Candidate("Standard", score=1000, power_w=200, passed=True)
a, b, c = mk(0, 1100, 240), mk(1025, 1060, 215), mk(1000, 1010, 203)
check(CT.choose_candidate("balanced", [a, b, c], stock) is b and CT.balanced_fallback([a, b, c], stock),
      "every cap costs efficiency: the old rule (half the gain, most points per watt) — not the "
      "barely faster one")
check(CT.rule_text("balanced", [a, b, c], stock).startswith("keine Einstellung war in beidem besser"),
      "the report says the fallback applied")
check(CT.fine_cap("balanced", b, [a, b, c], stock, [1050, 1025, 1000], CURVE) == (1012, 1000, 1025),
      "fallback: the fine search goes lower (more points per watt)")
check(CT.choose_candidate("balanced", [a, b], None) is a and CT.gains(a, None) is None,
      "without a stock run: the old rule (97 % of the best)")

# ── 2) efficiency: the fine cap below ─────────────────────────────────────────
print("efficiency: fine search below the chosen cap (run 1 of the series)")
stock1 = CT.Candidate("Standard", score=7242, power_w=254, passed=True)
e = [mk(1045, 7439, 256), mk(1020, 7332, 234), mk(995, 7220, 219), mk(970, 7121, 207)]
ch = CT.choose_candidate("efficiency", e, stock1)
check(ch.cap_mv == 995, f"on the grid: 995 mV (970 keeps only 98.3 %): {ch.cap_mv}")
fine = CT.fine_cap("efficiency", ch, e, stock1, [1070, 1045, 1020, 995, 970, 945, 920], CURVE)
check(fine == (981, 970, 995), f"fine search between 970 and 995 mV: {fine}")
check(CT.choose_candidate("efficiency", e + [mk(981, 7175, 213)], stock1).cap_mv == 981,
      "still ≥ 99 % of stock with 6 W less: the fine cap is taken")
check(CT.choose_candidate("efficiency", e + [mk(981, 7160, 213)], stock1).cap_mv == 995,
      "below 99 %: 995 stays")
slow = [mk(1045, 7000, 240), mk(1020, 6900, 225)]
low = mk(920, 7200, 200)
check(CT.fine_cap("efficiency", CT.choose_candidate("efficiency", slow, stock1), slow, stock1,
                  [1070, 1045, 1020, 995], CURVE) is None,
      "nothing kept stock speed (the fastest is taken): no fine search lower")
check(CT.fine_cap("max", full, [full], stock2, [1075, 1050], CURVE) is None
      and CT.fine_cap("efficiency", low, [low], stock1, [945, 920], CURVE) is None
      and CT.fine_cap("balanced", c1050, [c1050], stock2, [1050, 1046], CURVE) is None,
      "no fine search for max, below the lowest cap, or without room for a curve point in between")

# ── 3) the card's floor under load ────────────────────────────────────────────
print("measuring points down to the known minimum voltage")
grid = CT.anchor_voltages(CURVE, 1075, 850, 25)
check(grid == [1075, 1050, 1025, 1000, 975, 950, 925, 900, 875, 850], f"the grid as before: {grid}")
check(CT.with_floor(grid, CURVE, 925, 25) == [1075, 1050, 1025, 1000, 975, 950, 925],
      "floor 925 mV (run 2): nothing below it — no test at 900 that the card never reaches")
check(CT.with_floor(grid, CURVE, 936, 25) == [1075, 1050, 1025, 1000, 975, 950, 937],
      "the grid ends a distinct point above the floor: the lowest point right at it")
check(CT.with_floor(grid, CURVE, 931, 25) == [1075, 1050, 1025, 1000, 975, 950, 925],
      "the grid's last point is within reach of the floor (925 for 931): no extra point")
check(CT.with_floor(grid, CURVE, 0, 25) == grid and CT.with_floor([], CURVE, 925) == [],
      "unknown floor: unchanged")

print("the floor is remembered per GPU")
from core.nvtune_tuner import AutoTuner
t = AutoTuner.__new__(AutoTuner)
t._log_dir = os.path.join(TMP, "logs")
check(t._known_floor("NVIDIA GeForce RTX 4080") == 0.0, "nothing saved yet")
t._save_floor("NVIDIA GeForce RTX 4080", 924.6)
t._save_floor("Other GPU", 880)
d = json.load(open(os.path.join(TMP, "logs", "gpu_floor.json"), encoding="utf-8"))
check(t._known_floor("NVIDIA GeForce RTX 4080") == 925 and t._known_floor("Other GPU") == 880
      and d["NVIDIA GeForce RTX 4080"]["floor_mv"] == 925 and d["NVIDIA GeForce RTX 4080"]["at"],
      f"saved next to the tune logs, one entry per GPU: {d}")
with open(os.path.join(TMP, "logs", "gpu_floor.json"), "w", encoding="utf-8") as f:
    f.write("{kaputt")
check(t._known_floor("NVIDIA GeForce RTX 4080") == 0.0, "a damaged file: unknown, no crash")
t._save_floor("NVIDIA GeForce RTX 4080", 920)
check(t._known_floor("NVIDIA GeForce RTX 4080") == 920, "and is written anew")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
