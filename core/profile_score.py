"""
How a GPU profile compares with stock — performance and efficiency from the same
benchmark (pure logic; the profile comparison page shows it).

A tune measures a short benchmark (FurMark 2, 60 s) at stock and with the result:
since round 18 both are stored in TuneProfile.bench. Older All-round profiles carry
the same numbers in their notes ("FurMark 7295→7446 (+2.1 %) | 252→257 W"), which
is read as a fallback. Scores of runs of different length are compared per second.

    performance = score / stock score − 1
    efficiency  = (score / W) / (stock score / stock W) − 1
"""

from __future__ import annotations

import re
from typing import Optional

# "FurMark 7295→7446 (+2.1 %) | 252→257 W" in an All-round profile's notes
_NOTE_RE = re.compile(r"(?P<name>[A-Za-z][\w\- ]*?) (?P<s0>\d+(?:\.\d+)?)→(?P<s1>\d+(?:\.\d+)?) "
                      r"\([^)]*\) \| (?P<w0>\d+(?:\.\d+)?)→(?P<w1>\d+(?:\.\d+)?) W")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def bench_of(profile) -> Optional[dict]:
    """The profile's benchmark against stock, or None when it was never measured.
    -> {name, seconds, score, power_w, stock_seconds, stock_score, stock_power_w,
        at, source ('measured' | 'notes')}"""
    b = getattr(profile, "bench", None)
    if isinstance(b, dict):
        d = {"name": str(b.get("name") or "FurMark"), "seconds": _num(b.get("seconds")) or 60.0,
             "score": _num(b.get("score")), "power_w": _num(b.get("power_w")),
             "stock_score": _num(b.get("stock_score")), "stock_power_w": _num(b.get("stock_power_w")),
             "at": str(b.get("at") or ""), "source": "measured"}
        d["stock_seconds"] = _num(b.get("stock_seconds")) or d["seconds"]
        if d["score"] > 0 and d["stock_score"] > 0 and d["power_w"] > 0 and d["stock_power_w"] > 0:
            return d
    m = _NOTE_RE.search(getattr(profile, "notes", "") or "")
    if m:
        d = {"name": m["name"].strip(), "seconds": 60.0, "stock_seconds": 60.0,
             "score": float(m["s1"]), "stock_score": float(m["s0"]),
             "power_w": float(m["w1"]), "stock_power_w": float(m["w0"]), "at": "", "source": "notes"}
        if min(d["score"], d["stock_score"], d["power_w"], d["stock_power_w"]) > 0:
            return d
    return None


def score_of(profile) -> Optional[dict]:
    """-> {perf_pct, eff_pct, power_w, stock_power_w, points, stock_points, ppw, stock_ppw,
    label, source} (percent vs stock, one decimal; points per 60 s, so runs of another
    length read the same; ppw = those points per watt), None when the profile was never
    measured against stock."""
    b = bench_of(profile)
    if b is None:
        return None
    rate, rate0 = b["score"] / b["seconds"], b["stock_score"] / b["stock_seconds"]
    perf = (rate / rate0 - 1.0) * 100.0
    eff = ((rate / b["power_w"]) / (rate0 / b["stock_power_w"]) - 1.0) * 100.0
    secs = int(round(b["seconds"]))
    length = f"{secs // 60} min" if secs >= 120 and secs % 60 == 0 else f"{secs} s"
    return {"perf_pct": round(perf, 1), "eff_pct": round(eff, 1), "power_w": round(b["power_w"]),
            "stock_power_w": round(b["stock_power_w"]),
            "points": round(rate * 60.0), "stock_points": round(rate0 * 60.0),
            "ppw": round(rate * 60.0 / b["power_w"], 2), "stock_ppw": round(rate0 * 60.0 / b["stock_power_w"], 2),
            "label": f"{b['name']} {length}", "source": b["source"]}


def stock_of(scores) -> Optional[dict]:
    """Stock as one column next to the profiles: the mean of the stock measurements the
    given scores were compared with (every tune measures stock itself, right before)
    -> {points, power_w, ppw, n}, None without a measured score."""
    s = [x for x in scores if x]
    if not s:
        return None
    pts = sum(x["stock_points"] for x in s) / len(s)
    w = sum(x["stock_power_w"] for x in s) / len(s)
    return {"points": round(pts), "power_w": round(w),
            "ppw": round(sum(x["stock_ppw"] for x in s) / len(s), 2), "n": len(s)}


def bench_record(name: str, seconds: float, score: float, power_w: float, stock_score: float,
                 stock_power_w: float, stock_seconds: float = 0.0, at: str = "") -> dict:
    """What a tune stores in TuneProfile.bench."""
    return {"name": name, "seconds": float(seconds), "score": round(float(score), 1),
            "power_w": round(float(power_w), 1), "stock_score": round(float(stock_score), 1),
            "stock_seconds": float(stock_seconds or seconds), "stock_power_w": round(float(stock_power_w), 1),
            "at": at}
