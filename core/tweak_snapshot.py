"""
GameOptimizerPro — tweak snapshot & compare (from v1's dashboard, kept across restarts).

"Take snapshot" saves the live state of every tweak with a status check; "Compare" checks again
and lists every tweak whose state changed since — what a Windows update, another tool or a
change by hand did. v1 kept the snapshot in memory only; here it is a file next to the logs, so
a snapshot taken before an update can be compared after the restart.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

FILE_NAME = "tweak_snapshot.json"


def take(results: dict) -> dict:
    """results: {tweak id: VerifyResult} -> a snapshot. A check without an answer is None."""
    return {"t": round(time.time(), 1),
            "states": {tid: (None if getattr(r, "error", "") else bool(r.actual)) for tid, r in results.items()}}


def save(logs_dir, snap: dict) -> bool:
    try:
        p = Path(logs_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / FILE_NAME).write_text(json.dumps(snap), encoding="utf-8")
        return True
    except OSError:
        return False


def load(logs_dir) -> Optional[dict]:
    try:
        d = json.loads((Path(logs_dir) / FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("states"), dict):
        return None
    return d


def compare(snap: dict, results: dict) -> tuple[list, int]:
    """-> ([(tweak id, before, now)] of every tweak whose state changed, number of checks without an
    answer on either side). A check that did not answer is no change of state — it is only counted."""
    now = take(results)["states"]
    before = snap.get("states", {})
    changed, unknown = [], 0
    for tid in sorted(set(before) | set(now)):
        a, b = before.get(tid), now.get(tid)
        if a is None or b is None:
            unknown += tid in before and tid in now
            continue
        if a != b:
            changed.append((tid, a, b))
    return changed, unknown
