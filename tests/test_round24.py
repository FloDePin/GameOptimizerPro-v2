"""Round 24 — the V/F curves of the profile comparison (core/profile_curves.py): the stock
curve as Afterburner has it, a Rundum profile as Afterburner gets it (flat from its cap),
a Quick profile as the stock curve shifted by its offset. Pure logic, no GPU."""
import os
import shutil
import struct
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


TMP = tempfile.mkdtemp(prefix="gop_r24_")
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the app's own file
import core.i18n as I18N
I18N._current_lang = "de"
from core import ab_profile as AP
from core import profile_curves as PC
from core.nvtune_core import TuneProfile


def stock_mhz(v):                      # a card like the RTX 4080 of the series
    return 1955 + (v - 700) * 2.4


VOLTS = [700 + 5 * i for i in range(81)]                       # 700 … 1100 mV


def curve():
    pts = [(450.0, 225.0, 0.0)] + [(float(v), stock_mhz(v), 0.0) for v in VOLTS]
    raw = struct.pack("<II", AP.VF_VERSION, len(pts)) + bytes(4)
    for p in pts:
        raw += struct.pack("<fff", *p)
    return AP.VFCurve.from_hex((raw + bytes(24)).hex().upper())


C = curve()
print("stock curve")
st = PC.stock_line(C)
check(st[0] == (800.0, stock_mhz(800)) and st[-1] == (1100.0, stock_mhz(1100))
      and all(a[0] < b[0] for a, b in zip(st, st[1:])),
      f"stock: Afterburner's curve between 800 and 1100 mV, ascending: {st[0]} … {st[-1]}")

print("Rundum profile: the curve Afterburner gets, flat from the cap")
bal = TuneProfile(name="Ausgewogen", curve_points=[[925, 2579], [950, 2670], [975, 2725], [1000, 2770],
                                                   [1025, 2823], [1050, 2893], [1075, 2939]],
                  curve_cap_mv=1050)
ln = dict(PC.profile_line(C, bal))
check(PC.flat_from(bal) == 1050 and ln[1050.0] == 2893 and ln[1075.0] == 2893 and ln[1100.0] == 2893,
      "flat from 1050 mV at 2893 MHz — drawn flat (Afterburner writes the points above 100 MHz lower)")
check(ln[1000.0] == 2770 and ln[925.0] == 2579 and stock_mhz(1000) < ln[1000.0],
      "every measured point at its clock, above stock")
vals = [f for _v, f in PC.profile_line(C, bal)]
check(all(a <= b for a, b in zip(vals, vals[1:])), "monotonic, like Afterburner's curve")
check(PC.measured_points(bal)[0] == (925.0, 2579.0) and len(PC.measured_points(bal)) == 7,
      "the measured points as dots")
mx = TuneProfile(name="Max", curve_points=[[920, 2579], [1070, 2924]], curve_cap_mv=0)
check(PC.flat_from(mx) == 1070 and dict(PC.profile_line(C, mx))[1100.0] == 2924,
      "no cap: flat from the highest measured point")

print("Quick profile: the stock curve shifted")
q = TuneProfile(name="Schnell", core_offset_mhz=134, power_limit_pct=96)
ql = PC.profile_line(C, q)
check(PC.flat_from(q) == 0 and ql[0] == (800.0, stock_mhz(800) + 134) and len(ql) == len(st)
      and PC.measured_points(q) == [],
      "+134 MHz on every point, no flat part, no measured points")

print("value at a voltage (the pointer)")
check(PC.value_at(st, 1002.5) == stock_mhz(1002.5) and PC.value_at(st, 700) is None
      and PC.value_at([], 900) is None and PC.value_at(st, 1100) == stock_mhz(1100),
      "linear between points, None outside")
bad = TuneProfile(name="x", curve_points=[[1000, 99999]], curve_cap_mv=0)
check(PC.profile_line(C, bad) == [], "a curve out of range (hand-edited): no line, no crash")

print("Quick profile: flat from the game test's highest voltage (round 24)")
from core.nvtune_tuner import AutoTuner as _AT, TunerConfig as _TC
import types as _types
qt = _AT.__new__(_AT)
qt.config = _TC(ab_slot=3)
qt.ab = _types.SimpleNamespace(base_curve=lambda slot: (C, "Defaults"))
qc = qt._quick_cap(134, 1077.4)
check(qc == ([[1075, round(stock_mhz(1075) + 134)]], 1075),
      f"one point at the game test's voltage (snapped to the curve), the offset on top: {qc}")
qp = TuneProfile(name="Schnell 10.10.", core_offset_mhz=134, curve_points=qc[0], curve_cap_mv=qc[1],
                 notes="[OC+UV] Core+134MHz | Mem+500MHz | Pwr 96% | flach ab 1075 mV")
ql2 = dict(PC.profile_line(C, qp))
check(ql2[900.0] == stock_mhz(900) + 134 and ql2[1075.0] == stock_mhz(1075) + 134
      and ql2[1100.0] == stock_mhz(1075) + 134 and PC.measured_points(qp) == [],
      "below the voltage the same +134 everywhere, flat above it (the old offset gave 1100 mV +134); no dots")
qt.ab = _types.SimpleNamespace()
check(qt._quick_cap(134, 1075) is None, "no Afterburner curve: no cap (the offset profile as before)")

print("comparison benchmarks start at the stock run's temperature")
import threading
import types
from core.nvtune_tuner import AutoTuner, TunerConfig
t = AutoTuner.__new__(AutoTuner)
t.config = TunerConfig(bench_cool_max_s=5, bench_cool_tol_c=2.0)
temps = [67, 66, 63, 60, 57, 56]
t.monitor = types.SimpleNamespace(read=lambda: types.SimpleNamespace(temp=temps.pop(0) if len(temps) > 1 else temps[0]))
t._stop = threading.Event()
logs, prog = [], []
t._log = lambda m, lvl="info": logs.append(m)
t._progress = lambda p, m="": prog.append(m)
t._bench_ref_temp = 55.0
import time as _time
_t0 = _time.time()
t._cool_down("Nachher-Benchmark", 98)
check(logs and "Abkühlen auf 57 °C" in logs[0] and "jetzt 67 °C" in logs[0] and len(prog) == 4
      and _time.time() - _t0 < 5.5,
      f"67 °C after the game test, stock started at 55: idle until 57 °C ({len(prog)} s): {logs}")
logs.clear(); prog.clear()
temps[:] = [56]
t._cool_down("Kandidat", 70)
check(not logs and not prog, "already at the stock run's temperature: starts at once")
logs.clear()
temps[:] = [70]
t.config.bench_cool_max_s = 2
t._cool_down("Kandidat", 70)
check(len(logs) == 2 and "nach 2 s noch 70 °C" in logs[1], "never longer than bench_cool_max_s, says so")
logs.clear()
t._bench_ref_temp = 0.0
temps[:] = [80]
t._cool_down("Kandidat", 70)
check(not logs, "no stock run measured: no waiting")
t._bench_ref_temp = 55.0
temps[:] = [70]
t.config.bench_cool_max_s = 30
t._stop.set()
_t0 = _time.time()
t._cool_down("Kandidat", 70)
check(_time.time() - _t0 < 1.5, "a stop ends the cool-down at once")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
