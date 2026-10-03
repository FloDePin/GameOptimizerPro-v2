"""Round 13 — Rundum-Tuner: per-point curve search (core/curve_tune.py), the own
curve in Afterburner's profile, the FurMark 2 benchmark run, the worker's boost
mode, and the WHOLE tune against a simulated card.

The simulated card reads its V/F curve from the Afterburner profile file the
real code wrote (a throwaway copy in %TEMP% — Afterburner itself, FurMark and
the real GPU are never touched): it runs the highest clock its curve allows up
to its voltage limit, drops down the curve when a load would exceed the power
limit, and is unstable above a true per-voltage limit."""
import io, os, shutil, struct, subprocess, sys, tempfile, threading, time, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

import core.i18n as I18N
I18N._current_lang = "de"          # in memory only — the saved language is not touched

from core import ab_profile as AP
from core import curve_tune as CT
from core import furmark as FM
import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult
from core.nvtune_core import AfterburnerController, ProfileManager, TuneProfile

TMP = tempfile.mkdtemp(prefix="gop_r13_")

# ── A: pure logic ────────────────────────────────────────────────────────────
print("A  search per voltage point")


def scripted(limit, reach_max=10 ** 9, tdr_over=None):
    calls = []

    def test(mv, f):
        calls.append(f)
        ok = f <= limit
        return CT.PointTest(ok, reached=f <= reach_max,
                            tdr=(not ok and tdr_over is not None and f > limit + tdr_over))
    return test, calls


t, calls = scripted(2917)
r = CT.search_anchor(t, 1050, 2790, 2900)
check(r.best_mhz == 2915 and calls == [2900, 2915, 2930, 2922, 2920],
      f"+15 until a failure, then 7 and 5 from the last pass: {calls} -> {r.best_mhz}")
check(all(c < 2930 for c in calls[3:]), "never tests at or above a clock that already failed")
check(r.offset == 125 and not r.tdr and r.reachable, "offset against the stock clock")
t, calls = scripted(2850)
r = CT.search_anchor(t, 1050, 2790, 2969)
check(calls[:5] == [2969, 2939, 2909, 2879, 2849] and r.best_mhz == 2849,
      f"start too high: down in 30-MHz steps to the first pass, then up again: {calls}")
check(2850 - r.best_mhz < 5, "result within the 5-MHz precision of the true limit")
t, calls = scripted(2967)
r = CT.search_anchor(t, 1050, 2795, 2795, step=30)
check(calls[:7] == [2795, 2825, 2855, 2885, 2915, 2945, 2975] and r.best_mhz == 2967,
      f"no start value: coarse 30-MHz steps, halved to 15/7/5: {calls} -> {r.best_mhz}")
t, calls = scripted(3000, reach_max=2800)
r = CT.search_anchor(t, 1100, 2800, 2900)
check(not r.reachable and r.best_mhz == 0 and calls == [2900],
      "passed but NOT at the point (power/voltage limit) before any pass -> unreachable")
t, calls = scripted(3000, reach_max=2920)
r = CT.search_anchor(t, 1050, 2800, 2900)
check(r.reachable and r.best_mhz == 2915 and calls == [2900, 2915, 2930],
      "not at the point later in the search -> keeps the last real pass")
r = CT.search_anchor(lambda mv, f: CT.PointTest(f <= 2900, reached=f <= 2900), 1050, 2800, 2900)
check(r.reachable and r.best_mhz == 2900,
      "a FAILED step is a failure, never 'unreachable' (a crash can drop the voltage)")
t, calls = scripted(5000)
r = CT.search_anchor(t, 900, 2400, 2700, max_mhz=2620)
check(calls[0] == 2620 and max(calls) == 2620 and r.best_mhz == 2620,
      "start value above 'Core max' starts at the limit, never above it")
r = CT.search_anchor(scripted(5000)[0], 900, 2400, 2500, stop=lambda: True)
check(r.best_mhz == 0 and not r.steps, "abort: no step at all")
t, calls = scripted(2917, tdr_over=10)
r = CT.search_anchor(t, 1050, 2790, 2900)
check(r.tdr and r.best_mhz == 2915, "a driver reset during the search is remembered")
t, calls = scripted(1000)
r = CT.search_anchor(t, 1050, 2790, 2900, max_down=3)
check(r.best_mhz == 0 and len(calls) == 4, "nothing stable within the downward budget -> no result")

print("A  margins, measured points, cap voltages")
rs = [CT.AnchorResult(1050, 2805, best_mhz=2977), CT.AnchorResult(1000, 2690, best_mhz=2995, tdr=True),
      CT.AnchorResult(950, 2575, best_mhz=2784), CT.AnchorResult(900, 2460, reachable=False)]
CT.apply_margins(rs)
check([x.target_mhz for x in rs] == [2917, 2905, 2739, 0] and [x.margin_mhz for x in rs] == [60, 90, 45, 0],
      f"−60 at the top points (within 75 mV of the highest: where games boost), −45 below, +30 where "
      f"a driver reset happened: {[x.target_mhz for x in rs]}")
rs2 = [CT.AnchorResult(1050, 2805, best_mhz=2977), CT.AnchorResult(1000, 2690, best_mhz=3010)]
CT.apply_margins(rs2)
check(rs2[1].target_mhz == rs2[0].target_mhz == 2917, "never faster than a point above (monotonic)")
check(CT.curve_anchors(rs) == [(950, 2739), (1000, 2905), (1050, 2917)],
      "the curve uses only points with a result, sorted by voltage")
rs3 = [CT.AnchorResult(1050, 2805, best_mhz=2977), CT.AnchorResult(950, 2575, best_mhz=2784)]
CT.apply_margins(rs3, 30, 30, 30)
check([x.target_mhz for x in rs3] == [2947, 2754], "the old flat 30 MHz is still possible (all three settable)")
VOLTS = [600 + 5 * i for i in range(91)] + [1060 + 10 * i for i in range(19)]   # like a real RTX 40
check(CT.anchor_voltages(VOLTS, 1052, 850, 50) == [1050, 1000, 950, 900, 850],
      "measured points: from the highest voltage reached, every 50 mV down to 850")
check(CT.anchor_voltages(VOLTS, 1047, 850, 50) == [1045, 995, 945, 895],
      "ceiling between two points -> the point below it")
check(CT.anchor_voltages(VOLTS, 1050, 850, 25) == [1050, 1025, 1000, 975, 950, 925, 900, 875, 850],
      "cap voltages every 25 mV")
check(CT.anchor_voltages([], 1050) == [], "no curve -> nothing to measure")
check(CT.anchor_voltages(VOLTS, 1052) == [1050, 1025, 1000, 975, 950, 925, 900, 875, 850],
      "default: a point every 25 mV (finer than the old 50)")
ra = CT.search_anchor(lambda v, f: CT.PointTest(True, False, measured_mv=920.0), 875, 2160, 2380)
check(not ra.reachable and ra.ran_mv == 920 and ra.below_floor and len(ra.steps) == 1,
      "875 mV, the card stays at 920: below its floor under load (one step, no more)")
rb = CT.search_anchor(lambda v, f: CT.PointTest(True, False, measured_mv=1040.0), 1075, 2805, 2900)
check(not rb.reachable and not rb.below_floor,
      "1075 mV, the card only gets to 1040 (power limit): not reachable, but no floor")

print("A  goals")
stock = CT.Candidate("Standard", score=1900, power_w=280, temp_c=66, clock_mhz=2760, passed=True)
mk = lambda cap, sc, w: CT.Candidate("", cap, 100, sc, w, 66, 2800, passed=True)
cands = [mk(0, 2000, 300), mk(1025, 1965, 280), mk(1000, 1930, 262), mk(975, 1905, 246),
         mk(950, 1870, 232)]
check([c.label() for c in CT.plan_candidates("max", [1050, 1025, 1000], 111, True)]
      == ["volle Kurve", "volle Kurve, Power-Limit 111 %"],
      "max: the full curve, and with the highest power limit when stock ran into the limit")
check([c.label() for c in CT.plan_candidates("max", [1050, 1025], 111, False)] == ["volle Kurve"],
      "max without power limiting: no higher limit (it would only cost power)")
check([c.cap_mv for c in CT.plan_candidates("balanced", [1050, 1025, 1000])] == [0, 1025, 1000],
      "balanced: full curve, then each lower cap")
check([c.cap_mv for c in CT.plan_candidates("efficiency", [1050, 1025, 1000])] == [1025, 1000],
      "efficiency: only capped curves, highest first")
check([c.cap_mv for c in CT.plan_candidates("efficiency", [1050])] == [0],
      "efficiency with a single point: the full curve")
ch = {g: CT.choose_candidate(g, cands, stock) for g in CT.GOALS}
check(ch["max"].cap_mv == 0, "max -> the fastest (full curve)")
check(ch["balanced"].cap_mv == 1025,
      f"balanced -> most points/W among those keeping half the gain (≥ 1950): {ch['balanced'].cap_mv}")
check(ch["efficiency"].cap_mv == 975,
      f"efficiency -> least power with ≥ 99 % of stock (≥ 1881): {ch['efficiency'].cap_mv}")
check(len({ch[g].cap_mv for g in CT.GOALS}) == 3, "the three goals pick three different settings")
noisy = [mk(0, 2000, 300), CT.Candidate("", 0, 111, 2010, 330, 70, 2900, passed=True)]
check(CT.choose_candidate("max", noisy, stock).pwr_pct == 100,
      "max: +0.5 % (measuring noise) for 30 W more is NOT taken")
noisy[1].score = 2060
check(CT.choose_candidate("max", noisy, stock).pwr_pct == 111, "max: +3 % with the higher limit is taken")
check(CT.choose_candidate("efficiency", [mk(1000, 1850, 250), mk(975, 1800, 230)], stock).cap_mv == 1000,
      "efficiency when nothing keeps stock speed: the one that loses least")
check(CT.choose_candidate("balanced", [CT.Candidate("", 0, passed=False)], stock) is None,
      "nothing passed -> no choice")
check([CT.stop_testing("balanced", cands[:i + 1], stock) for i in range(4)] == [False, False, True, True],
      "balanced stops at the first cap below half the gain")
check([CT.stop_testing("efficiency", cands[1:i + 1], stock) for i in range(1, 5)]
      == [False, False, False, True], "efficiency stops at the first cap below stock speed")
check(not CT.stop_testing("max", cands, stock), "max never stops early")

print("A  final-test step-backs")
an = [(1050, 2920), (1000, 2900), (950, 2770)]
steps = [CT.final_backoff(a, an, 1000, 0, 100, True, False) for a in range(1, 5)]
check([s[4] for s in steps] == ["Kurve −15 MHz auf allen Punkten", "Speicher +1000→+900 MHz",
                                "Kurve −15 MHz auf allen Punkten", "Speicher +1000→+900 MHz"],
      "unstable: curve −15 and memory −100 alternate")
t1 = CT.final_backoff(1, an, 0, 0, 100, True, False, crash_mv=1047)
check(t1[0] == [(1050, 2905), (1000, 2900), (950, 2770)] and "bei 1050 mV" in t1[4],
      f"crash voltage known: only the points around it are lowered: {t1[4]}")
check(CT.final_backoff(1, an, 0, 0, 100, True, False, crash_mv=1020)[0]
      == [(1050, 2905), (1000, 2885), (950, 2770)], "between two points: both of them")
check(CT.final_backoff(1, an, 0, 0, 100, True, False, crash_mv=1075)[0]
      == [(1050, 2905), (1000, 2900), (950, 2770)], "above the measured range: the top point")
check(CT.final_backoff(1, an, 0, 0, 100, True, False)[0] == steps[0][0],
      "crash voltage unknown: the whole curve")
r = CT.search_anchor(scripted(5000)[0], 925, 2370, 2561, max_mhz=2590)
check(r.best_mhz == 2590 and r.limit_hit and r.steps[-1][0] == 2590,
      f"'Core max' is tested itself (2590), then the search stops and says so: {[x[0] for x in r.steps]}")
rr = [CT.AnchorResult(925, 2370, best_mhz=2590, limit_hit=True)]
CT.apply_margins(rr)
rep_l = CT.build_report("balanced", rr, None, None, None, 0, core_max=220, lang="de")
check(any("Grenze „Takt-Plus max. je Punkt“ erreicht" in line for line in rep_l["lines"])
      and any("Takt-Plus max. je Punkt“ (+220 MHz) die Suche beendet" in x for x in rep_l["recommendations"]),
      "report: limit reached at that point + recommendation")
check(steps[0][0] == [(1050, 2905), (1000, 2885), (950, 2755)], "−15 MHz on every point")
check(CT.final_backoff(2, an, 0, 0, 100, True, False)[4].startswith("Kurve"),
      "no memory offset -> the curve again")
b1 = CT.final_backoff(1, an, 0, 0, 111, False, True)
b2 = CT.final_backoff(1, an, 0, 0, 100, False, True, cap_mvs=[1050, 1025, 1000])
b3 = CT.final_backoff(1, an, 0, 1025, 100, False, True, cap_mvs=[1050, 1025, 1000])
check(b1[3] == 100 and b2[2] == 1025 and b3[2] == 1000,
      "too hot: power limit back to 100 %, then flat from the next lower cap")

print("A  report")
rep = CT.build_report("balanced", rs, stock, cands[1], cands[1], 1000, cands=cands, endurance=cands[1],
                      endurance_s=300, verify_s=120, retries=["Kurve −15 MHz auf allen Punkten"],
                      lang="de")
txt = "\n".join(rep["lines"])
check(rep["title"] == "Rundum-Tuner — Ziel: Ausgewogen" and "Regel: mindestens die Hälfte" in txt,
      "German title and the goal's rule")
check("1050 mV: 2977 MHz (+172 ggü. Stock 2805) → 2917 MHz (−60)" in txt
      and "1000 mV: 2995 MHz (+305 ggü. Stock 2690) → 2905 MHz (−90) — Treiber-Reset" in txt,
      "per point: found, offset, used with the margin taken off, reset note")
check("900 mV: unter der Mindestspannung der Karte unter Last" in txt,
      "unreachable point below the measured ones named as such")
check("flach ab 1025 mV: 1965 Punkte, 280 W" in txt and "← gewählt" in txt,
      "every candidate with score/W, the chosen one marked")
check("Punkte: 1900 → 1965 (+3.4 %)" in txt and "Leistung: 280 W → 280 W" in txt,
      "fair before/after with the same benchmark")
check("Endtest 5 min: bestanden" in txt and "Rechen-Prüfung 2 min" in txt and "Nach Rücknahme(n)" in txt,
      "final 5-min test, compute check and step-backs listed")
check(any("Treiber-Reset" in x for x in rep["recommendations"]) and
      any("Sicherheitsabstand" in x for x in rep["recommendations"]), "recommendations")
check(rep["summary"] == "+3.4 % Punkte, +0.0 % Leistung", f"summary: {rep['summary']}")
rep_en = CT.build_report("efficiency", rs, stock, cands[3], cands[3], 0, cands=cands, lang="en")
txt_en = "\n".join(rep_en["lines"])
check(rep_en["title"] == "All-round tuner — goal: Efficiency (undervolt)" and "stock performance" in txt_en
      and "flat from 975 mV: 1905 points" in txt_en and "Ziel" not in txt_en and "Punkte" not in txt_en,
      "English report has no German left")
lowrs = [CT.AnchorResult(1075, 2805, best_mhz=2970), CT.AnchorResult(925, 2370, best_mhz=2590),
         CT.AnchorResult(875, 2160, reachable=False)]
CT.apply_margins(lowrs)
rep_low = CT.build_report("balanced", lowrs, None, None, None, 0, lang="de")
check(any("875 mV: unter der Mindestspannung der Karte unter Last" in x for x in rep_low["lines"])
      and any("875 mV liegt unter der Mindestspannung" in x for x in rep_low["recommendations"])
      and not any("und darüber" in x for x in rep_low["recommendations"]),
      "a point below the card's minimum load voltage is explained as such (live: 875 asked, 920 ran)")
slow = CT.Candidate("", 0, 100, 1910, 300, 70, 2900, passed=True)
rep_s = CT.build_report("max", rs, stock, slow, slow, 0, lang="de")
check(any("Clock" in x for x in rep_s["recommendations"]),
      "score rising much less than the clock -> clock-stretching hint")

print("A  GPU table: cautious start values per generation")
from core.gpu_defaults import get_defaults
g = {n: get_defaults(n) for n in (
    "NVIDIA GeForce RTX 5080", "NVIDIA GeForce RTX 5090", "NVIDIA GeForce RTX 5070 Ti",
    "NVIDIA RTX 5000 Ada Generation", "NVIDIA GeForce RTX 4080", "NVIDIA GeForce RTX 3080 Ti",
    "NVIDIA GeForce RTX 2070 SUPER", "NVIDIA GeForce GTX 1660 SUPER", "NVIDIA GeForce GTX 1080 Ti",
    "AMD Radeon RX 9070 XT", "AMD Radeon RX 7900 XTX", "Intel(R) Arc(TM) B580 Graphics", "Weird GPU")}
b = g["NVIDIA GeForce RTX 5080"]
check(b.generation == "Blackwell" and b.core_start_mhz == 150 and b.core_max_mhz == 400
      and b.mem_start_mhz == 250 and b.mem_max_mhz == 1000 and b.tuner_supported,
      "RTX 5080: Blackwell, start +150 (FE did +350), memory +250 … +1000")
check(g["NVIDIA GeForce RTX 5090"].core_max_mhz == 300 and g["NVIDIA GeForce RTX 5070 Ti"].generation == "Blackwell",
      "RTX 5090 less core headroom; 5070 Ti found")
check(g["NVIDIA RTX 5000 Ada Generation"].generation == "Unknown",
      "workstation 'RTX 5000 Ada' is NOT taken for an RTX 50 card")
a = g["NVIDIA GeForce RTX 4080"]
check(a.core_start_mhz == 90 and a.mem_start_mhz == 500 and a.mem_max_mhz == 1000 and a.core_max_mhz == 250,
      "RTX 4080: start +90 / memory +500 … +1000, core max +250 (live: +220 hit the old limit)")
check(g["NVIDIA GeForce RTX 3080 Ti"].mem_max_mhz == 800, "RTX 3080 Ti: hot GDDR6X -> memory max +800")
check(g["NVIDIA GeForce RTX 2070 SUPER"].generation == "Turing" and g["NVIDIA GeForce GTX 1660 SUPER"].generation == "Turing"
      and g["NVIDIA GeForce GTX 1080 Ti"].generation == "Pascal", "Turing / GTX 16 / Pascal recognised")
check(all(x.core_start_mhz < x.core_max_mhz and x.mem_start_mhz <= x.mem_max_mhz
          for x in g.values() if x.tuner_supported), "every start value below its limit")
for n in ("AMD Radeon RX 9070 XT", "AMD Radeon RX 7900 XTX", "Intel(R) Arc(TM) B580 Graphics"):
    check(not g[n].tuner_supported and g[n].vendor in ("AMD", "Intel"), f"{n}: tuner not supported ({g[n].generation})")
check(g["AMD Radeon RX 9070 XT"].generation == "AMD RDNA 4", "RX 9070 XT = RDNA 4")
check(g["Weird GPU"].generation == "Unknown" and g["Weird GPU"].core_start_mhz == 0, "unknown: no start value (coarse search)")
check(a.curve_core_max_mhz == 350 and b.curve_core_max_mhz == 500,
      "Rundum 'Core max' per point: +100 over the classic limit (RTX 4080 +350, RTX 5080 +500)")
check(all(x.curve_core_max_mhz == x.core_max_mhz + 100 for x in g.values() if x.tuner_supported)
      and all(x.curve_core_max_mhz == 0 for x in g.values() if not x.tuner_supported),
      "every NVIDIA generation gets the extra room, AMD / Intel nothing")

# ── B: own curve in the Afterburner profile ──────────────────────────────────
print("B  own curve (VFCurve.with_anchor_curve / apply_slot)")


def stock_mhz(v):
    return 1955 + (v - 700) * 2.4             # integer MHz on the 5-mV grid; 1050 mV -> 2795


def curve_hex(frac=False):
    pts = [(450.0, 225.0, 0.0), (500.0, 225.0, 0.0)]                 # unused by the GPU
    pts += [(float(v), stock_mhz(v) + (0.5 if frac and v % 10 == 5 else 0.0), 0.0) for v in VOLTS]
    raw = struct.pack("<II", AP.VF_VERSION, len(pts)) + bytes(4)
    for p in pts:
        raw += struct.pack("<fff", *p)
    return (raw + bytes(24)).hex().upper()


HEX = curve_hex()
base = AP.VFCurve.from_hex(HEX)
anchors = [(850, 2531), (900, 2629), (950, 2734), (1000, 2832), (1050, 2937)]
own = base.with_anchor_curve(anchors)
eff = {p.voltage_mv: p.effective_mhz for p in own.active_points()}
check(all(eff[float(mv)] == f for mv, f in anchors), "every measured point gets exactly its clock")
check(eff[925.0] == stock_mhz(925) + 186,
      f"between two points the OFFSET is interpolated (925 mV: +194/+179 -> +186: {eff[925.0]})")
check(eff[1050.0] == 2937 and all(2836 <= eff[float(v)] <= 2837 for v in VOLTS if v > 1050),
      "highest point = top of the curve, every point above it 100 MHz lower (GPU can't pass it)")
act = [p for p in own.active_points() if p.voltage_mv <= 1050]
check(all(a.effective_mhz <= b.effective_mhz for a, b in zip(act, act[1:])), "monotonic up to the top")
check(eff[800.0] == stock_mhz(800) + 142,
      "below the lowest point: the SMALLEST measured offset (untested = safe side)")
inactive = [p for p in own.points() if not p.active and p.voltage_mv > 0]
check(inactive and all(p.offset_mhz == 142 for p in inactive), "unused points kept tame")
capd = base.with_anchor_curve(anchors, cap_mv=975)
ceff = {p.voltage_mv: p.effective_mhz for p in capd.active_points()}
top = max(capd.active_points(), key=lambda q: (q.effective_mhz, -q.voltage_mv))
check(top.voltage_mv == 975.0 and all(ceff[float(v)] <= ceff[975.0] for v in VOLTS if v > 975),
      f"cap 975 mV: the GPU's top point is 975 mV ({top.voltage_mv:.0f} mV, {top.effective_mhz:.0f} MHz)")
fr = AP.VFCurve.from_hex(curve_hex(frac=True)).with_anchor_curve(anchors, cap_mv=1025)
ftop = max(fr.active_points(), key=lambda q: (q.effective_mhz, -q.voltage_mv))
check(ftop.voltage_mv == 1025.0,
      f"bases with fractions: rounding never makes a point above the cap faster ({ftop.voltage_mv:.0f} mV)")
try:
    base.with_anchor_curve([(1050, 2795 + 1200)])
    check(False, "an absurd offset is refused")
except AP.ProfileError:
    check(True, "an absurd offset is refused")
try:
    base.with_anchor_curve([(1400, 3000)])
    check(False, "a voltage outside the curve is refused")
except AP.ProfileError:
    check(True, "a voltage outside the curve is refused")

text = ("[Startup]\r\nFormat=2\r\nPowerLimit=100\r\nThermalLimit=83\r\nCoreClkBoost=0\r\n"
        f"VFCurve={HEX}\r\nMemClkBoost=0\r\nFanMode=1\r\nFanSpeed=0\r\n"
        "[Settings]\r\nUnlockVoltageControl=1\r\n")
new, notes = AP.apply_slot(text, 2, AP.SlotSettings(mem_mhz=1000, power_pct=100,
                                                     curve=tuple(anchors), cap_mv=975))
pf = AP.ProfileFile(new)
check(pf.get("Profile2", "CoreClkBoost") == "1000000" and pf.get("Profile2", "MemClkBoost") == "1000000",
      "slot marked as custom curve, memory +1000")
check(AP.VFCurve.from_hex(pf.get("Profile2", "VFCurve")).to_hex() == capd.to_hex(),
      "the slot holds exactly the computed curve")
check(any("Eigene V/F-Kurve aus 5 Messpunkten (850–1050 mV)" in n and "flach ab 975 mV" in n
          for n in notes), f"note explains the curve: {notes[0][:90]}")
check(AP.slot_equivalent(new, AP.apply_slot(new, 2, AP.SlotSettings(
    mem_mhz=1000, curve=tuple(anchors), cap_mv=975))[0], 2), "re-applying the same curve = no change")
check(pf.get("Startup", "CoreClkBoost") == "0", "[Startup] (applied at boot) untouched")
p = TuneProfile(name="x", curve_points=[[850, 2531], [1050, 2937]], curve_cap_mv=975, mem_offset_mhz=500)
q = TuneProfile.from_dict(p.to_dict())
check(q.curve_points == [[850, 2531], [1050, 2937]] and q.curve_cap_mv == 975,
      "profile JSON keeps the curve")
spec = AfterburnerController.__new__(AfterburnerController)._settings_for(
    TuneProfile(curve_points=[[850, 2531], ["x", 5], [5000, 99999]], curve_cap_mv=2000))
check(spec.curve == ((850, 2531), (1300, 4000)) and spec.cap_mv == 1300 and spec.uses_curve,
      f"hand-edited JSON: invalid points dropped, values clamped: {spec.curve}")
check(not AfterburnerController.__new__(AfterburnerController)._settings_for(TuneProfile()).uses_curve,
      "a normal profile still uses the plain offset")

# ── C: FurMark 2 benchmark run ───────────────────────────────────────────────
print("C  FurMark 2 benchmark (fake process — nothing is started)")
fm_dir = os.path.join(TMP, "FurMark_win64")
os.makedirs(fm_dir)
for n in ("FurMark_GUI.exe", "furmark.exe"):
    open(os.path.join(fm_dir, n), "wb").close()
FAKE_FURMARK = os.path.join(fm_dir, "furmark.exe")
args = FM.benchmark_args(FAKE_FURMARK, 60)
check(args[0] == FAKE_FURMARK and "--benchmark" in args and "--no-score-box" in args
      and args[args.index("--duration-ms") + 1] == "60000" and args[args.index("--msaa") + 1] == "8"
      and args[args.index("--vsync") + 1] == "0", f"benchmark arguments: {args[1:]}")
check("--msaa" not in FM.benchmark_args(FAKE_FURMARK, 10, msaa=0), "MSAA off -> no --msaa")
OUT = ("[ Demo Quick Stats ]\n- frames               : 7600\n- duration             : 60004 ms\n"
       "- FPS (min/avg/max)    : 118 / 127 / 132\n- SCORE                : 1918\n"
       "- GPU 0: NVIDIA GeForce RTX 4080 [10DE-2704]\n  .max temperature: 66°C\n  .max usage: 100%\n")


class FakeProc:
    def __init__(self, out, rc=0, polls=2):
        self.stdout = io.StringIO(out)
        self._rc, self._polls = rc, polls
        self.returncode = None
        self.killed = False

    def poll(self):
        if self.killed:
            return self.returncode
        if self._polls > 0:
            self._polls -= 1
            return None
        self.returncode = self._rc
        return self._rc

    def kill(self):
        self.killed, self.returncode = True, -9

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode


_real_popen = subprocess.Popen
LAUNCHED = []


def fake_popen(out, rc=0, polls=2):
    def popen(argv, **kw):
        p = FakeProc(out, rc, polls)
        LAUNCHED.append((argv, kw, p))
        return p
    return popen


try:
    ticks = []
    subprocess.Popen = fake_popen(OUT)
    res = FM.run_benchmark(FAKE_FURMARK, 60, on_tick=ticks.append)
    argv, kw, _p = LAUNCHED[-1]
    check(res["ok"] and res["score"] == 1918 and res["fps_avg"] == 127 and res["max_temp"] == 66,
          f"score and stats read from FurMark's own summary: {res}")
    si = kw.get("startupinfo")
    check(si is not None and si.wShowWindow == 4 and si.dwFlags & subprocess.STARTF_USESHOWWINDOW,
          "the tuner's FurMark opens without taking the focus (SW_SHOWNOACTIVATE) — Windows gives the "
          "window in front priority on the GPU")
    locks = []
    real_lock = FM._lock_foreground
    FM._lock_foreground = lambda on: (locks.append(on), True)[1]
    subprocess.Popen = fake_popen(OUT)
    FM.run_benchmark(FAKE_FURMARK, 60)
    check(locks == [True, False], f"foreground locked while FurMark starts, released after: {locks}")
    locks.clear()
    FM.run_benchmark(FAKE_FURMARK, 60, focus=True)
    check(locks == [] and LAUNCHED[-1][1].get("startupinfo") is None, "focus=True: a normal window, no lock")
    subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(OSError("denied"))
    FM._lock_foreground = lambda on: (locks.append(on), True)[1]
    res = FM.run_benchmark(FAKE_FURMARK, 60)
    check(not res["ok"] and locks == [True, False], "start failed: the lock is released all the same")
    FM._lock_foreground = real_lock
    subprocess.Popen = fake_popen(OUT)
    res = FM.run_benchmark(FAKE_FURMARK, 60)
    argv, kw, _p = LAUNCHED[-1]
    check(kw.get("cwd") == fm_dir and kw.get("stdin") == subprocess.DEVNULL
          and kw.get("creationflags", 0) & getattr(subprocess, "CREATE_NO_WINDOW", 0) ==
          getattr(subprocess, "CREATE_NO_WINDOW", 0), "started in its folder, no console window")
    subprocess.Popen = fake_popen(OUT, rc=3221225477)
    res = FM.run_benchmark(FAKE_FURMARK, 60)
    check(not res["ok"] and "Absturz" in res["error"], f"crash (exit code) = not ok: {res['error']}")
    subprocess.Popen = fake_popen(OUT.replace("SCORE", "SC0RE"))
    res = FM.run_benchmark(FAKE_FURMARK, 60)
    check(not res["ok"] and "keine Punktzahl" in res["error"], "no score printed = not ok")
    subprocess.Popen = fake_popen(OUT, polls=10 ** 9)
    t0 = time.time()
    res = FM.run_benchmark(FAKE_FURMARK, 0, grace_s=0.3)
    check(not res["ok"] and "hängt" in res["error"] and LAUNCHED[-1][2].killed and time.time() - t0 < 5,
          "hanging FurMark is killed after the grace time")
    ev = threading.Event()
    ev.set()
    subprocess.Popen = fake_popen(OUT, polls=10 ** 9)
    res = FM.run_benchmark(FAKE_FURMARK, 60, stop_event=ev)
    check(res["aborted"] and not res["ok"] and LAUNCHED[-1][2].killed, "abort kills FurMark at once")
    check(getattr(LAUNCHED[-1][2], "waited", False) and getattr(LAUNCHED[-2][2], "waited", False),
          "... and waits for it to be gone (abort and hang) — the next benchmark starts seconds later")
    res = FM.run_benchmark(os.path.join(TMP, "nope.exe"), 60)
    check(not res["ok"] and "nicht gefunden" in res["error"], "missing FurMark 2 -> clear error")
finally:
    subprocess.Popen = _real_popen

# ── D: stress worker 'boost' mode ────────────────────────────────────────────
print("D  stress worker 'boost' mode (numpy fake cupy — no GPU load)")
WORKER = os.path.join(ROOT, "_stress_worker.py")
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tests", "fakecupy"), GOP_STRESS_N="64",
           GOP_STRESS_BOOST_N="64", GOP_STRESS_MEM_MB="4")


def run_worker(mode, extra=None, seconds=3.5):
    p = _real_popen([sys.executable, WORKER, str(os.getpid()), mode], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, env=dict(ENV, **(extra or {})))
    lines = []
    th = threading.Thread(target=lambda: lines.extend(l.strip() for l in p.stdout), daemon=True)
    th.start()
    try:
        p.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        p.terminate()
        p.wait(5)
    th.join(2)
    return p.returncode, lines


rc, lines = run_worker("boost")
rates = [float(l.split()[1]) for l in lines if l.startswith("RATE")]
check(rc not in (0, 3) and len(rates) >= 2 and all(x > 0 for x in rates),
      f"keeps running, RATE every second ({len(rates)} lines)")
rc, lines = run_worker("boost", {"FAKE_CORRUPT_DOT": "40"})
check(rc == 3 and any(l.startswith("ERR") for l in lines), f"wrong result under boost load -> exit 3 (rc={rc})")

# ── C2: which driver events count as a crash ─────────────────────────────────
print("C2 driver events that count as a crash")
import core.crash_recovery as CRM
_seen = []
_real_run = CRM.subprocess.run
CRM.subprocess.run = lambda args, **kw: (_seen.append(args), types.SimpleNamespace(stdout="NO_TDR"))[1]
try:
    CRM.CrashRecovery(os.path.join(TMP, "cr")).check_tdr_since(20)
finally:
    CRM.subprocess.run = _real_run
cmd = " ".join(_seen[-1]) if _seen else ""
check("Id=4101,13,14;" in cmd and "153" not in cmd and "nvlddmkm" in cmd,
      "4101 + nvlddmkm 13/14 count; 153 does NOT (the driver logs it at the end of every stress step)")

# ── E: the whole Rundum-Tuner against a simulated card ───────────────────────
print("E  Rundum-Tuner against a simulated card")
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)
GPU_FILE = "VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg"
K = 0.0886                       # W per V² per MHz: 1050 mV / 2795 MHz = 273 W in FurMark


class SimGPU:
    CEILING = 1050.0              # voltage limit under load

    def __init__(self, folder, pl_w=320.0, boost_factor=0.78, tdr_volts=(), long_margin=0,
                 voltage=True, fm_broken=False, mem_limit=5000, fm_mem_limit=None,
                 check_crash_once=False, short_once=False, floor_mv=0.0, game_margin=0):
        self.folder, self.pl_w, self.boost_factor = folder, pl_w, boost_factor
        self.floor_mv = floor_mv              # lowest voltage the card runs at under load
        self.tdr_volts, self.long_margin, self.voltage = tdr_volts, long_margin, voltage
        self.fm_broken = fm_broken
        self.mem_limit = mem_limit            # memory errors above this (any load)
        self.fm_mem_limit = fm_mem_limit      # ... and above this in a 60-s FurMark candidate run
        self.check_crash_once = check_crash_once
        # round 16: weaker under LOAD CHANGES than under the steady boost load (what
        # Hunt: Showdown found after 2 h) — only the game test's "transient" phase sees it
        self.game_margin = game_margin
        self.short_once = short_once
        self.curve = [(float(v), float(stock_mhz(v))) for v in VOLTS]
        self.mem, self.pwr_pct = 0, 100
        self.load, self.load_s = None, 0
        self.runs, self.benches, self.applies = [], [], 0
        self.on_run = None

    def limit(self, v):           # true stability limit
        return stock_mhz(v) + 172 + (1050 - v) * 0.37

    def load_slot(self, slot):
        text, _enc = AP.decode_cfg(open(os.path.join(self.folder, GPU_FILE), "rb").read())
        pf = AP.ProfileFile(text)
        sec = f"Profile{slot}"
        c = AP.VFCurve.from_hex(pf.get(sec, "VFCurve"))
        self.curve = [(p.voltage_mv, p.effective_mhz) for p in c.active_points()]
        self.mem = int(pf.get(sec, "MemClkBoost") or 0) // 1000
        self.pwr_pct = int(pf.get(sec, "PowerLimit") or 100)
        self.applies += 1

    def power(self, v, f, factor):
        return factor * K * (v / 1000) ** 2 * f

    def point(self, factor):
        """Highest clock up to the voltage limit (lowest voltage for it); down
        the curve while the load would exceed the power limit."""
        pl = self.pl_w * self.pwr_pct / 100
        pts = sorted(((v, f) for v, f in self.curve
                      if self.floor_mv - 0.01 <= v <= self.CEILING + 0.01),
                     key=lambda p: (-p[1], p[0]))
        for i, (v, f) in enumerate(pts):
            if self.power(v, f, factor) <= pl:
                return v, f, self.power(v, f, factor), i > 0
        v, f = min(pts)
        return v, f, self.power(v, f, factor), True

    def temp(self, w, seconds):
        return 30 + 0.1 * w + 0.04 * min(seconds, 300)

    def stats(self):
        if self.load is None:
            v, f, w, capped = 750.0, 210.0, 30.0, False
        else:
            v, f, w, capped = self.point(1.0)
        return types.SimpleNamespace(
            name="NVIDIA GeForce RTX 4080", temp=int(self.temp(w, self.load_s)),
            voltage_mv=v if self.voltage else 0.0, core_mhz=f, gpu_power_w=round(w, 1),
            power_w=round(w, 1), gpu_usage=100.0 if self.load else 0.0, mem_mhz=11200.0 + self.mem,
            power_capped=capped, throttle="None", throttle_protective=False)

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        if self.on_run:
            self.on_run(self, mode)
        factor = {"gemm": 1.25, "mixed": 1.25, "boost": self.boost_factor, "transient": self.boost_factor,
                  "mem": 0.7}[mode]
        v, f, w, capped = self.point(factor)
        r = StressResult(passed=True)
        r.avg_gpu_usage = 64.0 if mode == "boost" else 99.0
        r.avg_core_mhz = r.max_core_mhz = f
        vv = v if self.voltage else 0.0
        r.avg_voltage_mv = r.max_voltage_mv = r.min_voltage_mv = r.steady_voltage_mv = vv
        r.avg_power_w, r.power_capped_pct = round(w, 1), (100.0 if capped else 0.0)
        r.max_temp = r.avg_temp = round(self.temp(w, d), 1)
        r.avg_rate_tflops = (round(f * 0.0145, 2) if mode in ("gemm", "mixed")
                             else round(f * 0.009, 2) if mode == "boost" else 0.0)
        if mode == "mem":
            m = self.mem
            r.avg_bw_gbs = 700 + 0.05 * m if m <= 1000 else 750 - 0.3 * (m - 1000)
            r.avg_mem_mhz = 11200 + m
            if m > self.mem_limit:
                self.runs.append((mode, d, v, f, False))
                r.passed, r.crash_detected, r.compute_error = False, True, True
                r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
                return r
        pts = [(v, f)]
        if mode == "mixed":
            bv, bf, _w, _c = self.point(self.boost_factor)
            pts.append((bv, bf))                 # boost phase: the top of the curve
        if getattr(self, "force_hang", False):
            self.force_hang = False
            self.runs.append((mode, d, v, f, False))
            r.passed, r.crash_detected, r.hang_detected = False, True, True
            r.abort_reason = "GPU hängt — seit 8 s keine Ergebnisse der Last"
            r.last_voltage_mv = vv
            return r
        weaker = self.game_margin if mode == "transient" else 0
        bad = [(pv, pf_) for pv, pf_ in pts if pf_ > self.limit(pv) - weaker]
        self.runs.append((mode, d, v, f, not bad))
        if bad:
            r.passed = r.crash_detected = True
            r.passed = False
            if any(abs(bad[0][0] - tv) < 0.1 for tv in self.tdr_volts):
                r.tdr_detected, r.abort_reason = True, "TDR (GPU driver timeout) detected"
            else:
                r.compute_error, r.abort_reason = True, "Rechenfehler unter Last (GPU instabil)"
        elif r.max_temp >= max_temp:
            r.passed, r.abort_reason = False, f"Temp {r.max_temp}°C >= limit {max_temp}°C"
        if on_tick:
            on_tick(1, d, types.SimpleNamespace(**dict(vars(self.stats()), core_mhz=f,
                                                       voltage_mv=vv, temp=int(r.max_temp))))
        return r

    def furmark(self, path, seconds, width=1920, height=1080, msaa=8, demo="furmark-gl",
                stop_event=None, on_tick=None, grace_s=90.0):
        none = dict(ok=False, score=0, fps_avg=0, fps_min=0, max_temp=0, max_usage=0,
                    exit_code=None, aborted=False, error="")
        if self.fm_broken:
            return dict(none, error="FurMark ließ sich nicht starten: [WinError 2]")
        self.load, self.load_s = "furmark", seconds
        try:
            for el in (1, 2, 3):
                if on_tick:
                    on_tick(el)
                if stop_event is not None and stop_event.is_set():
                    return dict(none, aborted=True, error="abgebrochen")
            v, f, w, _c = self.point(1.0)
            lim = self.limit(v) - (self.long_margin if seconds >= 300 else 0)
            crash = (f > lim or self.mem > self.mem_limit
                     or (self.fm_mem_limit is not None and seconds == 60 and self.mem > self.fm_mem_limit)
                     or (self.check_crash_once and seconds == 30))
            if seconds == 30:
                self.check_crash_once = False
            self.benches.append((seconds, v, f, not crash))
            if crash:
                return dict(none, exit_code=3221226505, elapsed_s=8.0,
                            error="FurMark endete mit Code 3221226505 (Absturz?)")
            dur = seconds * 1000
            if self.short_once and seconds == 60 and self.benches[0] != self.benches[-1]:
                self.short_once, dur = False, 10000
            score = round(f * 0.68 * (1 + self.mem / 50000) * dur / 60000)   # frames: grows with time
            return dict(none, ok=True, score=score, fps_avg=round(f * 0.045), fps_min=round(f * 0.04),
                        max_temp=int(self.temp(w, seconds)), max_usage=100, exit_code=0,
                        duration_ms=dur, elapsed_s=dur / 1000 + 3)
        finally:
            self.load = None


class SimMon:
    def __init__(self, gpu):
        self.gpu = gpu

    def read(self):
        return self.gpu.stats()

    def power_pct_to_watts(self, pct):
        return round(self.gpu.pl_w * pct / 100, 1)

    def set_power_limit(self, w):
        return True

    def get_power_constraints(self):
        return self.gpu.pl_w, 150.0, round(self.gpu.pl_w * 1.11, 1)

    def get_default_power_limit(self):
        return self.gpu.pl_w


class SimAB(AfterburnerController):
    """The real profile writer on a throwaway folder; 'starting Afterburner with
    -ProfileN' = the simulated card loads that slot. No process is touched."""
    def __init__(self, gpu, folder):
        self.gpu, self._folder = gpu, folder
        super().__init__(None)

    def _detect(self):
        self.exe = os.path.join(self._folder, "MSIAfterburner.exe")
        self.profile_dir = self._folder

    def is_running(self):
        return False

    def close(self):
        return True, ""

    def start(self, slot=None):
        if slot:
            self.gpu.load_slot(slot)
        return True, ""

    def load_profile_slot(self, slot):
        return self.start(slot)

    @staticmethod
    def backup_dir():
        return os.path.join(TMP, "ab_backups")


def tune(gpu_kw=None, furmark=True, on_run=None, lang="de", **cfg):
    I18N._current_lang = lang
    folder = tempfile.mkdtemp(prefix="sim_", dir=TMP)
    with open(os.path.join(folder, GPU_FILE), "wb") as f:
        f.write(text.encode("latin-1"))
    gpu = SimGPU(folder, **(gpu_kw or {}))
    gpu.on_run = on_run
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    FM.run_benchmark = gpu.furmark
    ab = SimAB(gpu, folder)
    conf = dict(mode=TuneMode.CURVE, goal="balanced", core_max_mhz=300, max_temp_c=85,
                mem_stage=False, furmark_path=FAKE_FURMARK if furmark else "", ab_slot=2,
                crash_pause_s=0, mem_oc_max_mhz=1000,
                curve_anchor_step_mv=50,       # the E scenarios were built on 50 mV; E19/E20: 25
                # ... and on round 13's margins (30 everywhere, +30 after a reset); round 16's
                # 45 / 60 / +30 are checked in test_round16
                curve_safety_mhz=30, curve_safety_top_mhz=30, curve_reset_extra_mhz=30,
                game_test=False,               # round 16's game test: test_round16
                mem_safety_mhz=0)              # round 13's memory rule (round 16: −200, EDC)
    conf.update(cfg)
    t = AutoTuner(SimMon(gpu), ab, ProfileManager(os.path.join(folder, "profiles")),
                  TunerConfig(**conf), log_dir=os.path.join(folder, "logs"))
    logs = []
    t.on_log(lambda m, lvl: logs.append(m))
    t.last_report = None
    t._run_safe()
    return t, gpu, ab, logs, folder


def slot_curve(folder, slot=2):
    textf, _ = AP.decode_cfg(open(os.path.join(folder, GPU_FILE), "rb").read())
    pf = AP.ProfileFile(textf)
    return pf, AP.VFCurve.from_hex(pf.get(f"Profile{slot}", "VFCurve"))


# E1 balanced
t, gpu, ab, logs, folder = tune()
bp = t.best_profile
L = "\n".join(logs)
check(t.state == TunerState.DONE and bp is not None, f"tune finished: {t.state}")
check(bp.curve_points == [[850, 2531], [900, 2629], [950, 2734], [1000, 2832], [1050, 2937]],
      f"each point = true limit found to ±5 MHz, minus 30: {bp.curve_points}")
check("Messpunkte: 1050, 1000, 950, 900, 850 mV" in L, "points from the measured ceiling (1050 mV) down")
boost = [x for x in gpu.runs if x[0] == "boost"]
check(boost and all(abs(x[2] - 1050) < 0.1 or x[2] in (1000, 950, 900, 850) for x in boost),
      "every point test ran the GPU exactly at its voltage point")
first = [x[3] for x in boost[1:12]]
check(first == [2795, 2825, 2855, 2885, 2915, 2945, 2975, 2960, 2967, 2974, 2972],
      f"first point: coarse 30, failure, 15/7/5 from the last pass: {first}")
check(bp.curve_cap_mv == 1025 and bp.power_limit_pct == 100,
      f"balanced -> flat from 1025 mV (keeps half the gain, most points/W): {bp.curve_cap_mv}")
pf2, sc = slot_curve(folder)
top = max(sc.active_points(), key=lambda q: (q.effective_mhz, -q.voltage_mv))
check(pf2.get("Profile2", "CoreClkBoost") == "1000000" and top.voltage_mv == 1025.0,
      f"the saved curve is what Afterburner's slot holds: top {top.voltage_mv:.0f} mV / {top.effective_mhz:.0f} MHz")
check(t.last_report and t.last_report["summary"].startswith("+3.2 % Punkte"),
      f"report summary: {t.last_report and t.last_report['summary']}")
rep_files = [f for f in os.listdir(os.path.join(folder, "logs")) if f.startswith("curve_report_")]
check(len(rep_files) == 1 and "Empfehlungen:" in open(os.path.join(folder, "logs", rep_files[0]),
                                                       encoding="utf-8").read(),
      "report saved next to the tune log")
fin = [b for b in gpu.benches if b[0] == 300]
check(len(fin) == 1 and fin[0][3], "one 5-minute FurMark final test, passed")
check(any(x[0] == "mixed" and x[1] == 120 for x in gpu.runs), "plus the 2-min compute-checked run")
check("Profile saved: GOP_CURVE_BAL_" in L and "Gewählt für „Ausgewogen“" in L, "log names the choice")
check(abs(gpu.curve[0][1] - (stock_mhz(600) + 142)) < 1 and gpu.pwr_pct == 100,
      "the card ends up running the saved profile")

from core.tune_history import TuneHistory
runs = TuneHistory(os.path.join(folder, "logs")).get_runs()
check(runs and runs[0].mode == "Rundum" and runs[0].passed and runs[0].core_offset == 142,
      f"Tune History lists the run: {runs and (runs[0].mode, runs[0].passed, runs[0].core_offset)}")

# E2 max with a power-limited card
t, gpu, ab, logs, folder = tune({"pl_w": 260.0}, goal="max")
bp = t.best_profile
check(t.state == TunerState.DONE and bp.power_limit_pct == 111 and bp.curve_cap_mv == 0,
      f"max on a power-limited card: full curve + highest power limit ({bp and bp.power_limit_pct} %)")
check(slot_curve(folder)[0].get("Profile2", "PowerLimit") == "111", "power limit written to the slot")

# E3 efficiency
t, gpu, ab, logs, folder = tune(goal="efficiency")
bp = t.best_profile
rep = t.last_report
check(t.state == TunerState.DONE and bp.curve_cap_mv == 975, f"efficiency -> flat from 975 mV: {bp.curve_cap_mv}")
import re as _re
pct = lambda prefix: float(_re.search(r"\(([+-][\d.]+) %\)",
                                      next(l for l in rep["lines"] if l.startswith(prefix))).group(1))
check(pct("  Punkte:") >= -1.0 and pct("  Leistung:") <= -10.0,
      f"stock speed kept (≥ −1 %), power clearly lower: {pct('  Punkte:')} % / {pct('  Leistung:')} %")

# E4 driver reset at one point -> 60 MHz margin there
t, gpu, ab, logs, folder = tune({"tdr_volts": (1000,)})
bp = t.best_profile
check(t.state == TunerState.DONE and [1000, 2862 - 60] in bp.curve_points,
      f"reset at 1000 mV -> 60 MHz off that point: {bp.curve_points}")
check(any("Treiber-Reset" in x for x in t.last_report["recommendations"]), "report explains it")

# E5 final test fails once -> one step back, test again, fair 'after' benchmark
t, gpu, ab, logs, folder = tune({"long_margin": 40})
bp = t.best_profile
fin = [b for b in gpu.benches if b[0] == 300]
check(t.state == TunerState.DONE and len(fin) == 2 and not fin[0][3] and fin[1][3],
      f"5-min test failed, curve −15, passed on the second try: {[(b[3]) for b in fin]}")
check(bp.curve_points == [[850, 2531], [900, 2629], [950, 2734], [1000, 2817], [1050, 2922]],
      f"targeted: the card failed at 1025 mV (cap) -> only 1000 + 1050 −15, the SAVED curve: {bp.curve_points}")
check(sum(1 for b in gpu.benches if b[0] == 60) >= 4 and "Nach Rücknahme(n)" in "\n".join(t.last_report["lines"]),
      "after a step-back the 'after' benchmark is run again (fair comparison)")

# E6 abort in the middle of the point search
def abort_later(g, mode, box={"n": 0}):
    box["n"] += 1
    if box["n"] == 8:
        threading.Thread(target=TUNER[0].abort).start()
        time.sleep(0.5)


TUNER = [None]
_orig_init = AutoTuner.__init__


def _grab(self, *a, **k):
    _orig_init(self, *a, **k)
    TUNER[0] = self


AutoTuner.__init__ = _grab
t, gpu, ab, logs, folder = tune(on_run=abort_later)
AutoTuner.__init__ = _orig_init
check(t.state == TunerState.ABORTED and t.best_profile is None and t.last_report is None,
      "abort: no profile, no report")
check(all(abs(f - stock_mhz(v)) < 0.5 for v, f in gpu.curve) and gpu.pwr_pct == 100,
      "abort: the card is back on the stock curve")
check(not os.listdir(os.path.join(folder, "profiles")), "abort: nothing saved")

# E7 without FurMark -> internal benchmark
t, gpu, ab, logs, folder = tune(furmark=False)
L = "\n".join(logs)
check(t.state == TunerState.DONE and t.best_profile and not gpu.benches and "TFLOPS" in L,
      "no FurMark: benchmarked with the worker's measured TFLOPS")
check("interner Rechen-Benchmark" in "\n".join(t.last_report["lines"]), "report names the benchmark")

# E8 FurMark broken at stock -> falls back, says so
t, gpu, ab, logs, folder = tune({"fm_broken": True})
L = "\n".join(logs)
check(t.state == TunerState.DONE and "FurMark lief bei Standard nicht" in L,
      "FurMark failing at stock -> internal benchmark, explained")

# E9 no voltage readings (Afterburner monitoring off)
t, gpu, ab, logs, folder = tune({"voltage": False})
L = "\n".join(logs)
check(t.state == TunerState.DONE and "Keine Spannungswerte" in L and
      t.best_profile.curve_points[-1] == [1050, 2937], "no voltage readings: ceiling from the clock, same result")

# E10 power limit pushes the GPU down the curve under the boost load
t, gpu, ab, logs, folder = tune({"pl_w": 262.0, "boost_factor": 0.95})
L = "\n".join(logs)
check(t.state == TunerState.DONE and "Punkt nicht erreicht" in L,
      "GPU dropped below the tested point -> 'not reached', the step proves nothing")
check(t.best_profile.curve_points[-1][1] <= 2885 - 30,
      f"top point only as high as really tested at that voltage: {t.best_profile.curve_points[-1]}")

# E11 English
t, gpu, ab, logs, folder = tune(lang="en")
L = "\n".join(logs)
check(t.state == TunerState.DONE and "All-round tuner — goal: Balanced" in L and "Chosen for 'Balanced'" in L
      and "Gewählt" not in L and "Punkt " not in L, "English run log")
I18N._current_lang = "de"

# E13 memory: +500 first, +100 steps, the whole card under load; edge at +750
t, gpu, ab, logs, folder = tune({"mem_limit": 750}, mem_stage=True)
L = "\n".join(logs)
mem_runs = [x for x in gpu.runs if x[0] == "mem"]
check(t.state == TunerState.DONE and t.best_profile.mem_offset_mhz == 600,
      f"+500 ✓ +600 ✓ +700 ✓ +800 ✗ -> +700 minus 100 safety = +600: {t.best_profile.mem_offset_mhz}")
check([b[0] for b in gpu.benches].count(51) == 4 and len(mem_runs) == 4,
      "every memory step ran FurMark AND the verified copies at the same time")
check("Speicher: +700 MHz bestanden, +800 nicht → +600 MHz übernommen" in "\n".join(t.last_report["lines"]),
      "report explains the memory result")
check("ganze Karte unter Last (FurMark + geprüfte Speicherkopien)" in L, "log names the whole-card load")

# E14 the start value already fails -> down in 100 steps
t, gpu, ab, logs, folder = tune({"mem_limit": 350}, mem_stage=True)
check(t.state == TunerState.DONE and t.best_profile.mem_offset_mhz == 200,
      f"+500 ✗ +400 ✗ +300 ✓ -> +200: {t.best_profile.mem_offset_mhz}")
tested = [int(l.split("Mem+")[1].split("MHz")[0]) for l in logs if l.strip().startswith("Mem+")]
check(tested == [500, 400, 300], f"no offset tested twice, never above a failure: {tested}")

# E15 no failure up to 'Mem max' -> 'Mem max' itself
t, gpu, ab, logs, folder = tune(mem_stage=True)
check(t.state == TunerState.DONE and t.best_profile.mem_offset_mhz == 1000,
      f"+500…+1000 all passed -> +1000 (the cap, not an edge): {t.best_profile.mem_offset_mhz}")

# E16 a candidate crashes (FurMark alone at mem +1000) -> memory back, ALL candidates again
t, gpu, ab, logs, folder = tune({"fm_mem_limit": 950}, mem_stage=True)
L = "\n".join(logs)
check(t.state == TunerState.DONE and t.best_profile.mem_offset_mhz == 900,
      f"crash -> memory one step back first: {t.best_profile.mem_offset_mhz}")
check("abgestürzt" in "\n".join(t.last_report["lines"]) and "Kandidaten werden neu gemessen" in L,
      "the step back is logged and in the report")
check([b for b in gpu.benches if b[0] == 60 and not b[3]] and gpu.benches[-1][3],
      "the crashed run did not end the tune; the final test passed")

# E17 a benchmark that ended far too early (driver not clean) stops the tune
t, gpu, ab, logs, folder = tune({"short_once": True})
L = "\n".join(logs)
check(t.state == TunerState.ERROR and t.best_profile is None and "unplausibel" in L
      and "PC neu starten" in L, "implausible benchmark -> stop, no profile, 'restart the PC'")
check(all(abs(f - stock_mhz(v)) < 0.5 for v, f in gpu.curve), "and the card is back on stock")

# E18 the curve check (FurMark, memory +0) fails once -> only the point where the card ran
t, gpu, ab, logs, folder = tune({"check_crash_once": True})
L = "\n".join(logs)
check(t.state == TunerState.DONE and t.best_profile.curve_points[-1] == [1050, 2922]
      and t.best_profile.curve_points[-2] == [1000, 2832],
      f"curve check crash at 1050 mV -> 1050 −15, the rest untouched: {t.best_profile.curve_points}")
check("Kurven-Check ✗" in L and "Kurven-Check ✓" in L, "logged: failed, stepped back, passed")

# E19 the default now: a point every 25 mV, each one starting at its neighbour's result
from collections import Counter
t, gpu, ab, logs, folder = tune(curve_anchor_step_mv=25)
bp = t.best_profile
L = "\n".join(logs)
check(t.state == TunerState.DONE and "Messpunkte: 1050, 1025, 1000, 975, 950, 925, 900, 875, 850 mV" in L,
      "25-mV run: nine points from the ceiling down")
pts = dict((v, f) for v, f in bp.curve_points)
check(sorted(pts) == [850, 875, 900, 925, 950, 975, 1000, 1025, 1050]
      and all(abs(pts[v] - (gpu.limit(v) - 30)) <= 6 for v in pts),
      f"every point = its own limit found to ±5 MHz, minus 30: {bp.curve_points}")
check(all(a[1] <= b[1] for a, b in zip(bp.curve_points, bp.curve_points[1:])), "monotonic curve")
per_pt = Counter(round(x[2]) for x in gpu.runs if x[0] == "boost")
check(max(c for v, c in per_pt.items() if v != 1050) <= 6,
      f"closer points need fewer steps (they start at the neighbour's offset): {dict(per_pt)}")

# E20 a card that never goes below 920 mV under load: one test at 900 mV, the rest skipped
t, gpu, ab, logs, folder = tune({"floor_mv": 920.0}, curve_anchor_step_mv=25)
bp = t.best_profile
L = "\n".join(logs)
check(t.state == TunerState.DONE and [v for v, f in bp.curve_points] == [925, 950, 975, 1000, 1025, 1050],
      f"points down to 925 mV, nothing below the card's floor: {bp.curve_points}")
check("lief bei 920 mV" in L and "→ 900 mV: unter Last nicht erreichbar" in L
      and "Punkt 8/9: 875 mV — übersprungen" in L and "Punkt 9/9: 850 mV — übersprungen" in L
      and "Punkt 8/9: 875 mV (Stock" not in L,
      "900 mV tested once (ran 920), 875 / 850 skipped without a test")
rep = "\n".join(t.last_report["lines"] + t.last_report["recommendations"])
check("875 mV: unter der Mindestspannung der Karte unter Last" in rep
      and "900 mV liegt unter der Mindestspannung" in rep, "the report says why")

# E21 round 16: the game test finds what the steady tests can't. The card is 40 MHz
# weaker under load changes; on round 13's 30-MHz margins the transient phase fails ->
# one step back (−15 where the card ran) -> passes; the report says so.
t, gpu, ab, logs, folder = tune({"game_margin": 40}, game_test=True)
bp = t.best_profile
L = "\n".join(logs)
modes = [m for m, *_ in gpu.runs]
check(t.state == TunerState.DONE and bp is not None
      and "Spiel-Endtest ✗ (Lastwechsel)" in L and "Endtest ✗" in L,
      "E21: the game test's load changes fail on 30-MHz margins, the tune steps back")
check(modes.count("transient") >= 2 and modes[-2:] == ["transient", "boost"]
      and modes.index("transient") > modes.index("mixed"),
      f"after FurMark + compute check: load changes, then the boost point — again after the step back: "
      f"{modes[-6:]}")
rep = "\n".join(t.last_report["lines"])
check("Spiel-Endtest (60 s abkühlen, 5 min Lastwechsel, 4 min Boost-Punkt): bestanden" in rep
      and "Kurve −15 MHz" in rep, "the report: game test passed, after a curve step back")
top = max(bp.curve_points)
check(top[1] <= gpu.limit(top[0]) - 40, f"saved top point below the load-change limit: {top}")

# E22 round 16's margins (45, 60 at the top) cover that weakness at once
t, gpu, ab, logs, folder = tune({"game_margin": 40}, game_test=True, curve_safety_mhz=45,
                                curve_safety_top_mhz=60, curve_reset_extra_mhz=30)
L = "\n".join(logs)
check(t.state == TunerState.DONE and "Spiel-Endtest ✗" not in L and "Spiel-Endtest Boost-Punkt ✓" in L,
      "E22: with 60 MHz at the top the game test passes the first time")
check("−60 an den oberen Punkten" in L, "the log names the margins")

# E23 a hang in the game test (no results any more) is a failure like a crash
def hang_once(g, mode, box={"n": 0}):
    if mode == "transient" and box["n"] == 0:
        box["n"] = 1
        g.force_hang = True
t, gpu, ab, logs, folder = tune(game_test=True, on_run=hang_once)
L = "\n".join(logs)
check(t.state == TunerState.DONE and "GPU hängt" in L and "Endtest wird wiederholt" in L,
      "E23: a hung GPU in the game test -> step back, final test again")

# E12 old modes are untouched by the new mode
check(TunerConfig().mode == TuneMode.OC_UV and TunerConfig().goal == "balanced", "defaults unchanged")

print("F  live values between steps (GPU page)")
# The GPU page's tiles only got values from inside a measured step: between the
# memory steps (Afterburner restart, FurMark starting / ending) they stood still
# for up to ~20 s while FurMark visibly ran. A running tune fills such gaps.


class LiveMon:
    reads = 0

    def read(self):
        LiveMon.reads += 1
        return types.SimpleNamespace(temp=60, voltage_mv=0.0, core_mhz=2800.0, gpu_power_w=260.0)


lt = AutoTuner(LiveMon(), types.SimpleNamespace(available=False),
               ProfileManager(os.path.join(TMP, "live")), TunerConfig(),
               log_dir=os.path.join(TMP, "live_logs"))
ticks, phase = [], {}
lt.on_tick(lambda s: ticks.append(time.monotonic()))


def fake_run():
    for _ in range(6):                     # a measured step: its own tick every 0.25 s
        lt._tick(types.SimpleNamespace(temp=61))
        time.sleep(0.25)
    phase["step_end"], phase["step_reads"] = time.monotonic(), LiveMon.reads
    time.sleep(3.2)                        # Afterburner restart + FurMark start: no step ticks
    phase["gap_end"] = time.monotonic()


lt._run = fake_run
lt.start()
lt._thread.join(15)
n_end = len(ticks)
time.sleep(1.2)
gap = [x for x in ticks if x > phase["step_end"]]
marks = [phase["step_end"]] + gap + [phase["gap_end"]]
worst = max(b - a for a, b in zip(marks, marks[1:]))
check(phase["step_reads"] == 0, "during a step with its own ticks the live loop stays out of the way")
check(len(gap) >= 1 and worst <= 2.5,
      f"between steps a live value at least every ~2 s ({len(gap)} live, longest gap {worst:.1f} s)")
check(len(ticks) == n_end, "nothing after the run has ended")

prog = []
lt.on_progress(lambda pct, msg: prog.append((pct, msg)))
lt.ab = types.SimpleNamespace(available=True, write_and_apply=lambda slot, prof: (True, ""))
lt._progress(37, "Stufe")
ok, _err = lt._ab_write(TuneProfile(name="x"))
check(ok and prog[-1][0] == 37 and "Afterburner" in prog[-1][1]
      and ("Neustart" in prog[-1][1] or "restart" in prog[-1][1]),
      f"the Afterburner restart is announced on the GPU page, progress kept: {prog[-1]}")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
