"""Round 38 — from the evening tunes 2026-10-23: the comparison's "best all-rounder" (no
performance lost against stock, the most efficient of those) and the point search no longer
failing good steps on NVIDIA's short "SW thermal" signal during load changes (52-58 °C).
Pure logic, no GPU."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


from core import profile_score as PS  # noqa: E402
from core.nvtune_core import (THR_HW_SLOWDOWN, THR_HW_THERMAL, THR_POWER_CAP,  # noqa: E402
                              THR_SW_THERMAL, TuneProfile)
from core.nvtune_tuner import StressTester  # noqa: E402


def sc(perf, eff):
    return {"perf_pct": perf, "eff_pct": eff}


print("best all-rounder")
# the user's profiles of 23.10.: Ausgewogen 19.10., Effizienz 23.10., Max 23.10.
real = {0: sc(0.2, 6.9), 1: sc(-0.1, 5.8), 2: sc(2.9, -1.0)}
check(PS.best_allround(real) == {0}, f"23.10.: Ausgewogen 19.10. (+0.2 % / +6.9 %) -> {PS.best_allround(real)}")
deep = {0: sc(0.2, 6.9), 1: sc(-5.0, 18.0)}
check(PS.best_allround(deep) == {0}, "a deep undervolt that is clearly slower never wins (a plain sum would)")
tie = {0: sc(0.3, 6.0), 1: sc(1.5, 5.6), 2: sc(0.0, 4.0)}
check(PS.best_allround(tie) == {0, 1}, f"within the noise of the best: both marked -> {PS.best_allround(tie)}")
check(PS.best_allround({0: sc(0.2, 6.9), 1: None}) == set(), "only one measured profile -> nothing to compare")
check(PS.best_allround({0: sc(2.0, 0.3), 1: sc(1.0, -0.5)}) == set(),
      "no profile beats stock's efficiency -> no all-rounder")
check(PS.best_allround({0: sc(-1.0, 8.0), 1: sc(-2.0, 9.0)}) == set(),
      "every profile slower than stock -> no all-rounder")
check(PS.best_allround({0: sc(-0.6, 7.0), 1: sc(0.4, 6.0)}) == {0},
      "-0.6 % is within the noise: still 'no performance lost'")
p = TuneProfile(name="x", bench=PS.bench_record("FurMark", 60, 7256, 237, 7266, 251))
s = PS.score_of(p)
check(PS.best_allround({0: s, 1: sc(2.9, -1.0)}) == {0}, f"works on score_of() values: {s['perf_pct']} / {s['eff_pct']}")

print("SW thermal far below the limit")
ns = types.SimpleNamespace
P = StressTester._protective
check(not P(ns(throttle_protective=True, throttle_bits=THR_SW_THERMAL | THR_POWER_CAP, temp=58), 85),
      "SW thermal + power cap at 58 °C (live 23.10., point search) -> not a slowdown")
check(P(ns(throttle_protective=True, throttle_bits=THR_SW_THERMAL, temp=70), 85),
      "SW thermal within 15 °C of the limit -> counts")
check(P(ns(throttle_protective=True, throttle_bits=THR_HW_SLOWDOWN | THR_POWER_CAP, temp=45), 85)
      and P(ns(throttle_protective=True, throttle_bits=THR_HW_THERMAL, temp=45), 85),
      "hardware slowdowns count at any temperature")
check(not P(ns(throttle_protective=False, throttle_bits=0x04, temp=80), 85), "the power limit alone never counts")
check(P(ns(throttle_protective=True, temp=50), 85), "no reason bits read (old monitor) -> the old rule")

print("boot entry rewritten by Afterburner itself")
import struct  # noqa: E402
import core.ab_profile as AP  # noqa: E402
from core.ab_profile import ProfileFile, SlotSettings, VFCurve  # noqa: E402
SCR = os.path.dirname(os.path.abspath(__file__))
_src = open(os.path.join(SCR, "test_ab_profile.py"), encoding="utf-8").read()
_ns = {"__file__": os.path.join(SCR, "test_ab_profile.py")}
exec(compile(_src.split('print("VFCurve")')[0], "fixtures", "exec"), _ns)
_pf = ProfileFile(_ns["make_profile"](with_p2=True))
_pf.set_values("Startup", {"PowerLimit": "100", "CoreClkBoost": "0", "MemClkBoost": "0",
                           "VFCurve": _ns["make_curve"]().hex().upper()})
on = _pf.text()
own = SlotSettings(curve=((925, 2560), (1020, 2789), (1045, 2804)), cap_mv=1045, mem_mhz=500)
txt = AP.copy_slot_to_startup(AP.apply_slot(on, 2, own)[0], 2)
check(AP.startup_matches_slot(txt, 2) is True, "the app's copy of slot 2 -> boots slot 2")


def ab_rewrite(text, core="-251000", base_shift=15.0, mem=None):
    """[Startup] as Afterburner wrote it at 21:09 (23.10.): its slider value in CoreClkBoost and
    the base clocks of another temperature bin, the per-point offsets unchanged."""
    p = ProfileFile(text)
    c = VFCurve.from_hex(p.get("Startup", "VFCurve"))
    raw = bytearray(bytes.fromhex(c.to_hex()))
    for i, q in enumerate(c.points()):
        if q.active:
            struct.pack_into("<f", raw, AP.VF_HEADER_SIZE + i * AP.VF_POINT_SIZE + 4, q.base_mhz + base_shift)
    upd = {"CoreClkBoost": core, "VFCurve": raw.hex().upper()}
    if mem is not None:
        upd["MemClkBoost"] = mem
    p.set_values("Startup", upd)
    return p.text()


rw = ab_rewrite(txt)
check(AP.startup_matches_slot(rw, 2) is True,
      "Afterburner's own rewrite (CoreClkBoost -251000, base +15 MHz, same offsets) -> still slot 2")
check(AP.startup_matches_slot(ab_rewrite(txt, mem="400000"), 2) is False, "another memory offset -> not slot 2")
other = AP.copy_slot_to_startup(AP.apply_slot(on, 4, SlotSettings(curve=((925, 2578), (1025, 2789)),
                                                                     cap_mv=1025, mem_mhz=500))[0], 4)
check(AP.startup_matches_slot(AP.apply_slot(other, 2, own)[0], 2) is False,
      "another curve's offsets in the boot entry -> not slot 2")
nocurve = ProfileFile(rw)
nocurve.set_values("Startup", {"VFCurve": ""})
check(AP.startup_matches_slot(nocurve.text(), 2) is False,
      "boot entry without a curve -> CoreClkBoost is compared as before")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
