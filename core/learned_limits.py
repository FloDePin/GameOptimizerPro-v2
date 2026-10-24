"""
GameOptimizerPro — what the final tests learned about this card (23.10.)

A curve point that passes the point search can still fail the final tests: under 3D, the
video encoder and load changes at once (live: 1000 mV held 2832 MHz in the search and failed
at 2742 MHz in the hardness test, four times in a row). Every tune used to find that out
again, half an hour per step back. This file keeps, per GPU and voltage point, the lowest
clock that FAILED a final test; the next tune starts that point one step below it, and its
load-change check confirms it.

After a cleaning, new thermal paste or another driver the card may hold more — the GPU page
shows what is kept and forgets it with one click.

logs/gpu_learned.json:  {"<gpu name>": {"<mv>": {"fail_mhz": 2742, "at": "2026-10-23T11:38",
                                                  "test": "…"}}}
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

FILE = "gpu_learned.json"
STEP_MHZ = 15            # the next tune: one step below the clock that failed
NEAR_MV = 50             # a learned voltage caps the nearest point at or above it within this


def _path(logs_dir) -> Path:
    return Path(logs_dir) / FILE


def _read(logs_dir, strict: bool = False) -> dict:
    from core import safe_json
    d = safe_json.read(_path(logs_dir), {}, strict=strict)
    return d if isinstance(d, dict) else {}


def _write(logs_dir, d: dict) -> bool:
    from core import safe_json
    return safe_json.write(_path(logs_dir), d)


def load(logs_dir, gpu: str) -> dict:
    """{mv: {"fail_mhz", "at", "test"}} of this GPU (int keys), {} when nothing is kept."""
    out = {}
    for k, v in (_read(logs_dir).get(gpu or "") or {}).items():
        try:
            mv, f = int(k), int((v or {}).get("fail_mhz") or 0)
        except (TypeError, ValueError):
            continue
        if 300 <= mv <= 1300 and f > 0:
            out[mv] = {"fail_mhz": f, "at": str(v.get("at") or ""), "test": str(v.get("test") or "")}
    return out


def record(logs_dir, gpu: str, mv: int, fail_mhz: int, test: str = "") -> bool:
    """A final test failed with the point `mv` at `fail_mhz` (the core, not the memory). Keeps
    the lowest failing clock per point. -> True when something new was learned."""
    if not gpu or not mv or fail_mhz <= 0:
        return False
    from core import safe_json
    try:
        d = _read(logs_dir, strict=True)
    except safe_json.Unreadable:             # never write over what could not be read
        return False
    pts = d.setdefault(gpu, {})
    key = str(int(mv))
    old = pts.get(key) or {}
    if old.get("fail_mhz") and int(old["fail_mhz"]) <= int(fail_mhz):
        return False
    pts[key] = {"fail_mhz": int(fail_mhz), "at": datetime.now().isoformat(timespec="minutes"), "test": test}
    return _write(logs_dir, d)


def forget(logs_dir, gpu: str = "") -> bool:
    """Forget what was learned (one GPU, or every GPU)."""
    from core import safe_json
    try:
        d = _read(logs_dir, strict=True)
    except safe_json.Unreadable:
        d = {} if not gpu else None
    if d is None:
        return False
    if gpu:
        if gpu not in d:
            return True
        d.pop(gpu, None)
    else:
        d = {}
    return _write(logs_dir, d)


def point_at(anchors: list, fault_mv: float) -> tuple:
    """The measured point a failure at `fault_mv` is booked on: the nearest one at or above it
    (the curve is never faster below a point than at it, so capping that one caps the voltage
    the card ran) — the top point when the voltage is above them all. -> (mv, mhz) or ()."""
    if not anchors or not fault_mv:
        return ()
    above = sorted((mv, f) for mv, f in anchors if mv >= fault_mv - 5)
    return above[0] if above else max(anchors)


def apply(anchors: list, learned: dict, step: int = STEP_MHZ) -> tuple:
    """Each learned voltage caps the nearest point at or above it (within NEAR_MV) one step below
    the clock that failed there; a point is never faster than one above it.
    -> (new anchors, [(mv, before, after)])."""
    if not anchors or not learned:
        return list(anchors), []
    new = {mv: f for mv, f in anchors}
    for lmv, e in learned.items():
        tgt = [mv for mv in new if lmv - 5 <= mv <= lmv + NEAR_MV]
        if not tgt:
            continue
        mv = min(tgt)
        new[mv] = min(new[mv], int(e["fail_mhz"]) - step)
    top = float("inf")
    for mv in sorted(new, reverse=True):
        new[mv] = top = min(new[mv], top)
    changed = [(mv, f, new[mv]) for mv, f in anchors if new[mv] != f]
    return [(mv, new[mv]) for mv, _f in anchors], changed


def search_caps(mvs, learned: dict, step: int = STEP_MHZ) -> dict:
    """Before the point search (24.10.): the clock apply() will cap each planned point to anyway —
    also the points BELOW a learned one (the curve is never faster below). Searching above it only
    risks driver resets: all four of 23.10. happened there. -> {mv: cap}, uncapped points left out."""
    big = 10 ** 6
    anchors, _ = apply([(int(mv), big) for mv in mvs], learned, step)
    return {mv: f for mv, f in anchors if f < big}


def summary(learned: dict, de: bool = True) -> str:
    """"1000 mV ≤ 2727 MHz (23.10.)" — what the next tune will use."""
    parts = []
    for mv in sorted(learned):
        e = learned[mv]
        day = ""
        try:
            day = datetime.fromisoformat(e["at"]).strftime("%d.%m." if de else "%m/%d")
        except (ValueError, KeyError):
            pass
        parts.append(f"{mv} mV ≤ {int(e['fail_mhz']) - STEP_MHZ} MHz" + (f" ({day})" if day else ""))
    return " · ".join(parts)
