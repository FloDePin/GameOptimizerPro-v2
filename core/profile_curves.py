"""
What a GPU profile does to the card's V/F curve — the lines of the curve chart in the
profile comparison (pure logic, no Tk).

The stock curve is Afterburner's own ([Defaults] of the card's profile file: voltage
points and their stock clocks). A Rundum profile is the curve Afterburner gets from it
(core/ab_profile.VFCurve.with_anchor_curve: the offset interpolated between the measured
points, flat from the cap — the points above the cap are written 100 MHz lower so the GPU
never boosts past it; drawn flat, which is what the card runs). A Quick profile is the
stock curve shifted by its clock offset.
"""

from __future__ import annotations

from typing import Optional

LO_MV, HI_MV = 800, 1110          # Afterburner's editor shows more; the card runs ~900–1100


def stock_line(curve, lo: float = LO_MV, hi: float = HI_MV) -> list:
    """[(mV, MHz)] of the stock curve between lo and hi."""
    return [(p.voltage_mv, p.base_mhz) for p in curve.active_points() if lo <= p.voltage_mv <= hi]


def flat_from(profile) -> int:
    """The voltage the profile's curve is flat from (its cap, else its highest measured
    point); 0 for an offset profile (the whole curve shifted)."""
    pts = [int(mv) for mv, _f in (profile.curve_points or []) if isinstance(mv, (int, float))]
    if not pts:
        return 0
    cap = int(profile.curve_cap_mv or 0)
    return cap if cap and cap < max(pts) else max(pts)


def measured_points(profile) -> list:
    """[(mV, MHz)] the tune measured and used (after its safety margins); none for a Quick
    profile (one offset, its single curve point only marks where it is flat from)."""
    if (getattr(profile, "notes", "") or "").startswith("[OC+UV]"):
        return []
    return sorted((float(mv), float(f)) for mv, f in (profile.curve_points or [])
                  if isinstance(mv, (int, float)) and isinstance(f, (int, float)))


def profile_line(curve, profile, lo: float = LO_MV, hi: float = HI_MV) -> list:
    """[(mV, MHz)] the card runs with this profile; [] when the curve can't be built
    (a hand-edited profile out of range)."""
    if profile.curve_points:
        try:
            own = curve.with_anchor_curve(profile.curve_points, profile.curve_cap_mv or 0)
        except Exception:
            return []
        top_mv = flat_from(profile)
        act = own.active_points()
        under = [p.effective_mhz for p in act if p.voltage_mv <= top_mv + 0.5]
        if not under:
            return []
        top = max(under)
        return [(p.voltage_mv, top if p.voltage_mv > top_mv + 0.5 else p.effective_mhz)
                for p in act if lo <= p.voltage_mv <= hi]
    off = float(profile.core_offset_mhz or 0)
    return [(mv, f + off) for mv, f in stock_line(curve, lo, hi)]


def value_at(line: list, mv: float) -> Optional[float]:
    """The line's clock at mv (linear between its points), None outside it."""
    if not line or mv < line[0][0] or mv > line[-1][0]:
        return None
    for (v1, f1), (v2, f2) in zip(line, line[1:]):
        if v1 <= mv <= v2:
            return f1 if v2 == v1 else f1 + (f2 - f1) * (mv - v1) / (v2 - v1)
    return line[-1][1]
