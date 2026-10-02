"""
GameOptimizerPro v2.0 — Rundum-Tuner: pure logic (no hardware, fully testable)

Ideas taken from Yuri "1usmus" Bubliy's HYDRA / ClockTuner for Ryzen:
  * the V/F curve is tuned PER VOLTAGE POINT (HYDRA's NVIDIA diagnostic builds
    its own curve) instead of one offset for every point;
  * 15 MHz search steps; safety margins taken off the edge (30 MHz, 60 MHz where
    a driver reset happened — HYDRA 2.3B's numbers), because games vary more
    than any stress test and the card boosts higher when cold;
  * performance is MEASURED before/after (CTR's Cinebench comparison — here
    FurMark 2's benchmark score), not assumed from the clock readout: a curve
    that is too tight can lose performance while the clock looks the same.

The tuner (core/nvtune_tuner.AutoTuner._run_curve) supplies the hardware
callbacks; everything here only decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

GOALS = ("max", "balanced", "efficiency")


def is_de() -> bool:
    try:
        from core.i18n import current_lang
        return current_lang() == "de"
    except Exception:
        return True


def T(de: str, en: str) -> str:
    """Log / report text in the app's language."""
    return de if is_de() else en


# ── one point of the curve ───────────────────────────────────────────────────

# A step counts for a point when the card's median voltage was within this of it
# (two points of Ada's 5-mV grid).
REACH_TOL_MV = 10


@dataclass
class PointTest:
    """Outcome of one stress step at (voltage point, frequency)."""
    passed: bool
    reached: bool = True        # the GPU really ran at that voltage point
    tdr: bool = False           # a driver reset happened
    reason: str = ""
    measured_mv: float = 0.0
    measured_mhz: float = 0.0


@dataclass
class AnchorResult:
    mv: int
    base_mhz: float
    best_mhz: int = 0            # highest frequency that passed (0 = none)
    target_mhz: int = 0          # best minus the safety margin
    tdr: bool = False
    reachable: bool = True
    limit_hit: bool = False      # stopped by 'Core max', not by a failure
    ran_mv: float = 0.0          # not reachable: the voltage the card ran at instead
    steps: list = field(default_factory=list)   # (mhz, passed, reason)

    @property
    def offset(self) -> int:
        return int(self.best_mhz - self.base_mhz) if self.best_mhz else 0

    @property
    def below_floor(self) -> bool:
        """Not reachable because the card ran ABOVE the point: under this load it
        never goes that low (RTX 4080: ~920 mV), so no lower point is reachable
        either — the tuner skips them instead of testing each one."""
        return not self.reachable and self.ran_mv > self.mv + REACH_TOL_MV


def search_anchor(test: Callable[[int, int], PointTest], mv: int, base_mhz: float,
                  start_mhz: int, step: int = 15, min_step: int = 5, down_step: int = 30,
                  max_down: int = 8, max_mhz: int = 0,
                  stop: Callable[[], bool] = lambda: False) -> AnchorResult:
    """Highest stable frequency at one voltage point.

    Starts at a prior (e.g. the neighbour point's offset), walks DOWN in
    down_step until a frequency passes, then UP from the last pass in `step`;
    a failure halves the step (15 -> 7 -> 5) and the search continues from the
    last pass — never at or above a frequency that already failed. Stops when
    the smallest step fails. A step that passed while the GPU did NOT run at
    the voltage point (power / voltage limit) proves nothing: it ends the
    search (before the first pass: the point can't be tested under this load).
    A failed step is a failure whether the point was reached or not."""
    r = AnchorResult(int(mv), float(base_mhz))
    f = min(int(start_mhz), int(max_mhz)) if max_mhz else int(start_mhz)
    lo: Optional[int] = None
    hi: Optional[int] = None
    for _ in range(max_down + 1):
        if stop():
            return r
        t = test(mv, f)
        r.steps.append((f, t.passed, t.reason))
        r.tdr |= t.tdr
        if t.passed and not t.reached:
            r.reachable = False
            r.ran_mv = float(t.measured_mv or 0.0)
            return r
        if t.passed:
            lo = f
            break
        hi = f
        f -= down_step
    if lo is None:
        return r
    cur = step
    while not stop():
        cand = lo + cur
        if max_mhz and cand > max_mhz:
            cand = max_mhz                   # the limit itself is still tested, once
            if cand <= lo:
                r.limit_hit = True
                break
        if hi is not None and cand >= hi:
            if cur <= min_step:
                break
            cur = max(min_step, cur // 2)
            continue
        t = test(mv, cand)
        r.steps.append((cand, t.passed, t.reason))
        r.tdr |= t.tdr
        if t.passed and not t.reached:
            break                    # ran below the point: proves nothing, keep the last pass
        if t.passed:
            lo = cand
        else:
            hi = cand
            if cur <= min_step:
                break
            cur = max(min_step, cur // 2)
    r.best_mhz = lo
    return r


def apply_margins(results: list[AnchorResult], safety: int = 30, recovery: int = 60) -> list[AnchorResult]:
    """target = best - safety (recovery where a driver reset happened), and no
    point faster than a point above it (monotonic from the top, only lowering)."""
    for r in results:
        if r.best_mhz:
            r.target_mhz = int(r.best_mhz - (recovery if r.tdr else safety))
    usable = sorted((r for r in results if r.best_mhz), key=lambda r: r.mv)
    for hi, lo in zip(reversed(usable), list(reversed(usable))[1:]):
        if lo.target_mhz > hi.target_mhz:
            lo.target_mhz = hi.target_mhz
    return results


def curve_anchors(results: list[AnchorResult]) -> list[tuple[int, int]]:
    return sorted((r.mv, r.target_mhz) for r in results if r.best_mhz and r.target_mhz > 0)


def anchor_voltages(point_voltages: list[float], ceiling_mv: float, floor_mv: float = 850,
                    step_mv: int = 25) -> list[int]:
    """Voltage points to measure, top-down: the highest curve point at or below
    the ceiling (the highest voltage the card reached), then every `step_mv`
    down to `floor_mv` — each snapped to a real curve point."""
    pts = sorted(v for v in point_voltages if v > 0)
    if not pts:
        return []
    def snap(v):
        below = [p for p in pts if p <= v + 0.5]
        return below[-1] if below else pts[0]
    out, v = [], snap(ceiling_mv)
    while v >= floor_mv - 0.5:
        s = int(round(snap(v)))
        if not out or s < out[-1]:
            out.append(s)
        v -= step_mv
    return out


# ── candidates (curve caps) and the goal ─────────────────────────────────────

@dataclass
class Candidate:
    name: str
    cap_mv: int = 0              # 0 = the full measured curve
    pwr_pct: int = 100           # power limit
    score: float = 0.0           # FurMark benchmark score (or worker rate)
    power_w: float = 0.0         # average board power during the benchmark
    temp_c: float = 0.0          # highest temperature
    clock_mhz: float = 0.0
    power_capped_pct: float = 0.0
    passed: bool = False
    unstable: bool = False       # crash / driver reset / benchmark died
    thermal: bool = False        # hit the temperature limit
    invalid: bool = False        # ran far too short / far too few points: driver not clean
    last_mv: float = 0.0         # voltage the card ran right before the end / the crash
    note: str = ""

    @property
    def per_watt(self) -> float:
        return self.score / self.power_w if self.power_w > 0 else 0.0

    def label(self, de: bool = True) -> str:
        if self.name:
            return self.name
        s = ((f"flach ab {self.cap_mv} mV" if de else f"flat from {self.cap_mv} mV")
             if self.cap_mv else ("volle Kurve" if de else "full curve"))
        if self.pwr_pct != 100:
            s += f", Power-Limit {self.pwr_pct} %" if de else f", power limit {self.pwr_pct} %"
        return s


# What each goal still accepts. Relative to what THIS card gained: a fixed
# "within x % of the best" made balanced and efficiency pick the same cap,
# because the whole overclock is only worth ~4–7 % on RTX 40 cards.
BALANCED_GAIN_SHARE = 0.5    # keep at least half of the measured gain over stock
EFFICIENCY_KEEP_PCT = 99.0   # of STOCK: same performance as before, less power
MAX_NOISE_PCT       = 1.0    # FurMark 60-s runs repeat within ~0.5 %


def plan_candidates(goal: str, cap_mvs: list, max_pwr_pct: int = 100,
                    power_limited: bool = False) -> list[Candidate]:
    """What to benchmark for the goal, in test order. cap_mvs: the voltages the
    curve may be capped at, the highest one being the top of the measured
    curve (= no cap). Capping lower only ever makes the card slower, so the
    order allows stopping early (stop_testing).
    max:        the full curve — and, when the stock run hit the power limit,
                also with the highest power limit the card allows;
    balanced:   the full curve, then flat from each lower cap voltage;
    efficiency: flat from each cap voltage below the top, highest first (the
                full curve only when there is nothing below it)."""
    tops = sorted({int(v) for v in cap_mvs}, reverse=True)
    if not tops:
        return []
    if goal == "max":
        plan = [Candidate("", 0, 100)]
        if power_limited and max_pwr_pct > 100:
            plan.append(Candidate("", 0, int(max_pwr_pct)))
        return plan
    capped = [Candidate("", mv, 100) for mv in tops[1:]]
    if goal == "efficiency":
        return capped or [Candidate("", 0, 100)]
    return [Candidate("", 0, 100)] + capped


def _efficiency_ref(stock: Optional[Candidate], best: Candidate) -> float:
    return (stock.score * EFFICIENCY_KEEP_PCT / 100) if (stock and stock.score) else best.score * 0.95


def _balanced_ref(stock: Optional[Candidate], best: Candidate) -> float:
    if stock and stock.score and best.score > stock.score:
        return stock.score + BALANCED_GAIN_SHARE * (best.score - stock.score)
    return best.score * 0.97


def stop_testing(goal: str, tested: list[Candidate], stock: Optional[Candidate] = None) -> bool:
    """After each benchmarked candidate: the next (lower) caps can only be
    slower — stop once the last one fell below what the goal still accepts."""
    if goal == "max" or not tested or not tested[-1].passed:
        return False
    ok = [c for c in tested if c.passed and c.score > 0]
    if not ok:
        return False
    last, best = tested[-1], max(ok, key=lambda c: c.score)
    if goal == "balanced":
        return last.score < _balanced_ref(stock, best)
    return last.score < _efficiency_ref(stock, best)


def choose_candidate(goal: str, cands: list[Candidate],
                     stock: Optional[Candidate] = None) -> Optional[Candidate]:
    """max:        highest score; within the measuring noise the one that needs
                   less power (a setting that isn't measurably faster only costs
                   power and heat).
    balanced:   best score per watt among those that keep at least half of the
                gain over stock (without a stock run: 97 % of the best).
    efficiency: least power among those that keep stock performance
                (EFFICIENCY_KEEP_PCT % of the stock score); if none does, the
                fastest of them (the least performance lost)."""
    ok = [c for c in cands if c.passed and c.score > 0]
    if not ok:
        return None
    best = max(ok, key=lambda c: c.score)
    if goal == "max":
        pool = [c for c in ok if c.score >= best.score * (1 - MAX_NOISE_PCT / 100)]
        return min(pool, key=lambda c: (c.power_w or 1e9, c.cap_mv or 1e9))
    if goal == "efficiency":
        pool = [c for c in ok if c.score >= _efficiency_ref(stock, best)] or [best]
        return min(pool, key=lambda c: (c.power_w or 1e9, -c.score))
    pool = [c for c in ok if c.score >= _balanced_ref(stock, best)]
    return max(pool, key=lambda c: (c.per_watt, c.score))


def lower_curve(anchors: list, step: int, crash_mv: float = 0, near_mv: int = 10) -> list:
    """−step MHz where the card was running when it failed: the measured point
    at that voltage (within near_mv), else the two points around it — they set
    the curve in between — or the nearest end point outside the measured range.
    Without a known voltage: every point."""
    mvs = sorted(mv for mv, _f in anchors)
    if not crash_mv or not mvs:
        hit = set(mvs)
    else:
        hit = {mv for mv in mvs if abs(mv - crash_mv) <= near_mv}
        if not hit:
            below = [mv for mv in mvs if mv < crash_mv]
            above = [mv for mv in mvs if mv > crash_mv]
            hit = ({below[-1]} if below else set()) | ({above[0]} if above else set())
    return [(mv, f - step) if mv in hit else (mv, f) for mv, f in anchors]


def final_backoff(attempt: int, anchors: list, mem: int, cap_mv: int, pwr_pct: int,
                  unstable: bool, thermal: bool, step: int = 15, de: bool = True,
                  cap_mvs: Optional[list] = None, crash_mv: float = 0, mem_step: int = 100):
    """One step back after failed final test number `attempt` (1-based).
    -> (anchors, mem, cap_mv, pwr_pct, what). Too hot (and nothing crashed):
    first the power limit back to 100 %, then flat from the next lower cap
    voltage (cap_mvs; default: the measured points). Unstable: alternately the
    curve −step MHz — only around crash_mv, the voltage the card ran when it
    failed, if known — and the memory offset −mem_step (errors that slip past
    GDDR6X's error correction look like core instability)."""
    if thermal and not unstable:
        if pwr_pct > 100:
            return (anchors, mem, cap_mv, 100,
                    "Power-Limit → 100 % (Temperatur)" if de else "power limit → 100 % (temperature)")
        mvs = sorted({int(v) for v in (cap_mvs or [mv for mv, _f in anchors])}, reverse=True)
        top = cap_mv or (mvs[0] if mvs else 0)
        lower = [v for v in mvs if v < top]
        if lower:
            return (anchors, mem, lower[0], pwr_pct,
                    f"Kurve flach ab {lower[0]} mV (Temperatur)" if de
                    else f"curve flat from {lower[0]} mV (temperature)")
    if attempt % 2 == 0 and mem > 0:
        m2 = max(0, mem - mem_step)
        return anchors, m2, cap_mv, pwr_pct, (f"Speicher +{mem}→+{m2} MHz" if de
                                               else f"memory +{mem}→+{m2} MHz")
    new = lower_curve(anchors, step, crash_mv)
    changed = [mv for (mv, f), (_m, f2) in zip(anchors, new) if f2 != f]
    if len(changed) == len(anchors):
        what = (f"Kurve −{step} MHz auf allen Punkten" if de else f"curve −{step} MHz on every point")
    else:
        pts = ", ".join(str(v) for v in sorted(changed))
        what = (f"Kurve −{step} MHz bei {pts} mV (dort lief die Karte beim Fehler)" if de
                else f"curve −{step} MHz at {pts} mV (where the card ran when it failed)")
    return new, mem, cap_mv, pwr_pct, what


# ── report ───────────────────────────────────────────────────────────────────

GOAL_TEXT = {"max": ("Maximale Leistung", "Maximum performance"),
             "balanced": ("Ausgewogen", "Balanced"),
             "efficiency": ("Effizienz (Undervolt)", "Efficiency (undervolt)")}
GOAL_RULE = {"max": ("höchste Punktzahl (gleich schnell im Messrauschen: die sparsamere Einstellung)",
                     "highest score (equal within the noise: the more frugal setting)"),
             "balanced": ("mindestens die Hälfte des Leistungsgewinns, davon die meisten Punkte pro Watt",
                          "at least half of the performance gain, the most points per watt of those"),
             "efficiency": ("Standard-Leistung (≥ 99 %) bei der geringsten Leistungsaufnahme",
                            "stock performance (≥ 99 %) at the lowest power draw")}


def _pct(a: float, b: float) -> str:
    return f"{(a / b - 1) * 100:+.1f} %" if a and b else "–"


def _duration(seconds: int, de: bool) -> str:
    if seconds >= 60:
        return f"{seconds // 60} min" + (f" {seconds % 60} s" if seconds % 60 else "")
    return f"{seconds} s"


def build_report(goal: str, results: list[AnchorResult], stock: Optional[Candidate],
                 after: Optional[Candidate], chosen: Optional[Candidate], mem_offset: int,
                 cands: Optional[list] = None, endurance: Optional[Candidate] = None,
                 endurance_s: int = 0, verify_s: int = 0, bench_name: str = "FurMark",
                 mem_note: str = "", max_temp_limit: int = 85, safety_mhz: int = 30,
                 retries: Optional[list] = None, saved: Optional[Candidate] = None,
                 notes: Optional[list] = None, core_max: int = 0,
                 lang: str = "de") -> dict:
    """The HYDRA-style result report.
    stock / after: the SAME short benchmark before and with the saved settings
    (a fair before/after); endurance: the long final run (endurance_s long);
    cands: every benchmarked curve cap; chosen: the one the goal picked;
    saved: cap / power limit actually saved, when a final-test step-back
    changed them; notes: lines about the run (curve check, memory stage,
    step-backs before the final test); core_max: the 'Core max' setting.
    -> {"title", "lines", "recommendations", "summary"}"""
    de = lang == "de"
    g = GOAL_TEXT.get(goal, (goal, goal))[0 if de else 1]
    pts = "Punkte" if de else "points"
    rule = GOAL_RULE.get(goal, ("", ""))[0 if de else 1]
    lines = [("Rundum-Tuner — Ziel: " if de else "All-round tuner — goal: ") + g,
             ("Regel: " if de else "Rule: ") + rule, ""]

    lines.append("Messpunkte der Kurve (Spannung: stabil gefunden → übernommen):" if de
                 else "Curve points (voltage: found stable → used):")
    for r in sorted(results, key=lambda r: -r.mv):
        if not r.best_mhz:
            ok_mvs = [x.mv for x in results if x.best_mhz]
            if r.reachable:
                why = "kein stabiler Takt gefunden" if de else "no stable clock found"
            elif ok_mvs and r.mv < min(ok_mvs):
                why = ("unter der Mindestspannung der Karte unter Last" if de
                       else "below the card's minimum voltage under load")
            else:
                why = "unter dieser Last nicht erreichbar" if de else "not reachable under this load"
            lines.append(f"  {r.mv} mV: {why}")
            continue
        extra = ((" — Treiber-Reset bei der Suche, 60 MHz Abstand" if de
                  else " — driver reset while searching, 60 MHz margin") if r.tdr else "")
        if r.limit_hit:
            extra += (" — Grenze „Takt-Plus max. je Punkt“ erreicht" if de
                      else " — 'max clock gain per point' limit reached")
        lines.append(f"  {r.mv} mV: {r.best_mhz} MHz ({r.offset:+d} ggü. Stock {r.base_mhz:.0f}) → "
                     f"{r.target_mhz} MHz{extra}" if de else
                     f"  {r.mv} mV: {r.best_mhz} MHz ({r.offset:+d} vs stock {r.base_mhz:.0f}) → "
                     f"{r.target_mhz} MHz{extra}")

    if cands:
        lines += ["", (f"Kandidaten ({bench_name}-Benchmark):" if de
                       else f"Candidates ({bench_name} benchmark):")]
        for c in cands:
            if c.passed:
                mark = ("  ← gewählt" if de else "  ← chosen") if c is chosen else ""
                lines.append(f"  {c.label(de)}: {c.score:.0f} {pts}, {c.power_w:.0f} W, "
                             f"{c.temp_c:.0f} °C, {c.per_watt:.2f} {pts}/W{mark}")
            else:
                lines.append(f"  {c.label(de)}: ✗" + (f" {c.note}" if c.note else ""))

    if stock and after and stock.score and after.score:
        lines += ["", ("Vorher → nachher (gleicher Benchmark):" if de
                       else "Before → after (same benchmark):")]
        lines.append(f"  {'Punkte' if de else 'Score'}: {stock.score:.0f} → {after.score:.0f} "
                     f"({_pct(after.score, stock.score)})")
        if stock.power_w and after.power_w:
            lines.append(f"  {'Leistung' if de else 'Power'}: {stock.power_w:.0f} W → "
                         f"{after.power_w:.0f} W ({_pct(after.power_w, stock.power_w)})")
        if stock.temp_c and after.temp_c:
            lines.append(f"  {'Temperatur (max.)' if de else 'Temperature (max)'}: "
                         f"{stock.temp_c:.0f} °C → {after.temp_c:.0f} °C "
                         f"({after.temp_c - stock.temp_c:+.0f} °C)")
        if stock.per_watt and after.per_watt:
            lines.append(f"  {'Effizienz' if de else 'Efficiency'}: {stock.per_watt:.2f} → "
                         f"{after.per_watt:.2f} {pts}/W ({_pct(after.per_watt, stock.per_watt)})")
        if stock.clock_mhz and after.clock_mhz:
            lines.append(f"  {'Ø Takt' if de else 'Avg clock'}: {stock.clock_mhz:.0f} → "
                         f"{after.clock_mhz:.0f} MHz")

    lines.append("")
    if saved or chosen:
        lines.append(("Gespeichert: " if de else "Saved: ") + (saved or chosen).label(de)
                     + (f", Speicher +{mem_offset} MHz" if de else f", memory +{mem_offset} MHz")
                     + (f" ({mem_note})" if mem_note else ""))
    if endurance:
        d = _duration(endurance_s, de) if endurance_s else ""
        lines.append((f"Endtest {d}: bestanden — {endurance.score:.0f} {pts}, max. "
                      f"{endurance.temp_c:.0f} °C, Ø {endurance.power_w:.0f} W" if de else
                      f"Final test {d}: passed — {endurance.score:.0f} {pts}, max "
                      f"{endurance.temp_c:.0f} °C, avg {endurance.power_w:.0f} W"))
    if verify_s:
        lines.append((f"Rechen-Prüfung {_duration(verify_s, de)} (Ergebnisse verglichen): bestanden"
                      if de else
                      f"Compute check {_duration(verify_s, de)} (results compared): passed"))
    if retries:
        lines.append(("Nach Rücknahme(n): " if de else "After step-backs: ") + "; ".join(retries))
    if notes:
        lines += ["", "Ablauf:" if de else "Run:"] + [f"  {n}" for n in notes]

    rec = []
    if any(r.tdr for r in results):
        rec.append("Bei der Suche gab es einen Treiber-Reset — an diesem Punkt ist der größere "
                   "Abstand (60 MHz) eingerechnet." if de else
                   "A driver reset happened during the search — the larger margin (60 MHz) is used "
                   "at that point.")
    capped_pts = [r.mv for r in results if r.limit_hit]
    if capped_pts:
        lim = f" (+{core_max} MHz)" if core_max else ""
        pts = ", ".join(str(v) for v in sorted(capped_pts))
        rec.append((f"Bei {pts} mV hat die Grenze „Takt-Plus max. je Punkt“{lim} die Suche beendet, nicht "
                    f"ein Fehler — mit einer höheren Grenze findet der Tuner dort vermutlich mehr." if de else
                    f"At {pts} mV the 'max clock gain per point' limit{lim} ended the search, not a "
                    f"failure — with a higher limit the tuner probably finds more there."))
    unreach = [r.mv for r in results if not r.reachable]
    ok_mvs = [r.mv for r in results if r.best_mhz]
    low = [v for v in unreach if ok_mvs and v < min(ok_mvs)]
    high = [v for v in unreach if v not in low]
    if high:
        rec.append((f"{min(high)} mV und darüber erreicht die Karte unter Last nicht (Spannungs- "
                    f"oder Power-Limit) — dort ist die Kurve flach." if de else
                    f"The card doesn't reach {min(high)} mV and above under load (voltage or "
                    f"power limit) — the curve is flat there."))
    if low:
        rec.append((f"{max(low)} mV liegt unter der Mindestspannung der Karte unter Last (sie lief "
                    f"dort mit mehr) — so tief geht sie im Spiel nicht; darunter nimmt die Kurve den "
                    f"kleinsten gemessenen Offset." if de else
                    f"{max(low)} mV is below the card's minimum voltage under load (it ran higher "
                    f"there) — it never goes that low in games; below the measured points the curve "
                    f"uses the smallest measured offset."))
    capped = max((c.power_capped_pct for c in (endurance, after) if c), default=0.0)
    if capped >= 50 and goal == "max":
        rec.append((f"Im Test hing die Karte {capped:.0f} % der Zeit im Power-Limit — mehr Takt "
                    f"gibt es nur mit höherem Limit (Kühlung/Netzteil beachten)." if de else
                    f"In the test the card sat at the power limit {capped:.0f} % of the time — "
                    f"more clock speed needs a higher limit (mind cooling / PSU)."))
    hot = max((c.temp_c for c in (endurance, after) if c), default=0.0)
    if hot and hot >= max_temp_limit - 5:
        rec.append(("Die Temperatur kam nah ans Limit — Lüfterkurve/Airflow prüfen; kühler taktet "
                    "die Karte auch höher." if de else
                    "The temperature came close to the limit — check the fan curve / airflow; a "
                    "cooler card also boosts higher."))
    if (stock and after and stock.score and after.score and stock.clock_mhz and after.clock_mhz
            and not mem_offset):
        if after.score / after.clock_mhz < stock.score / stock.clock_mhz * 0.98:
            rec.append(("Die Punkte stiegen weniger als der angezeigte Takt — typisch für „Clock "
                        "Stretching“ (knappe Spannung, die Karte taktet intern niedriger). Der "
                        "Sicherheitsabstand fängt das meist ab; sonst mit größerem Abstand "
                        "wiederholen." if de else
                        "The score rose less than the reported clock — typical of clock stretching "
                        "(tight voltage, the card runs slower internally). The safety margin usually "
                        "covers it; otherwise re-run with a larger margin."))
    rec.append((f"Kalt taktet die Karte etwas höher als im warmen Test — die {safety_mhz} MHz "
                f"Sicherheitsabstand decken das ab. Stürzt ein Spiel trotzdem ab: den Tune mit "
                f"größerem Sicherheitsabstand wiederholen." if de else
                f"A cold card boosts a little higher than in the warm test — the {safety_mhz} MHz "
                f"safety margin covers that. If a game still crashes: re-run the tune with a larger "
                f"safety margin."))
    summary = ""
    if stock and after and stock.score and after.score:
        summary = (f"{_pct(after.score, stock.score)} {pts}, "
                   f"{_pct(after.power_w, stock.power_w)} {'Leistung' if de else 'power'}")
    return {"title": lines[0], "lines": lines, "recommendations": rec, "summary": summary}
