"""
GameOptimizerPro — the user's own tweak presets, kept after a restart

They lived only in memory: a preset made in the app ("Custom preset") was gone after a restart
unless it had been exported. Now in profiles/user_presets.json (the updater never touches
profiles/), read and written through core/safe_json — a file that can't be read is never written
over with an empty list.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core import safe_json
from core.tweak_presets import TweakPreset

# GOP_USER_PRESETS_FILE: tests (run_all_tests.py) — never the user's own presets
PRESETS_FILE = (Path(os.environ["GOP_USER_PRESETS_FILE"]) if os.environ.get("GOP_USER_PRESETS_FILE")
                else Path(__file__).resolve().parent.parent / "profiles" / "user_presets.json")
DEFAULT_ICON = "⭐"
DEFAULT_COLOR = "#a78bfa"


def make_id(name: str) -> str:
    """The id of a preset made under this name — the same name gives the same id (it replaces)."""
    return "user_" + re.sub(r"\s+", "_", str(name).strip().lower())


def to_dict(p: TweakPreset) -> dict:
    return {"id": p.id, "name": p.name, "icon": p.icon, "desc": p.desc,
            "tweak_ids": list(p.tweak_ids), "color": p.color}


def from_dict(d, color: str = DEFAULT_COLOR) -> TweakPreset | None:
    """A preset from a saved / imported entry; None for anything that is not one."""
    if not isinstance(d, dict):
        return None
    name = str(d.get("name") or "").strip()
    ids = d.get("tweak_ids")
    ids = [t for t in ids if isinstance(t, str) and t] if isinstance(ids, list) else []
    if not name or not ids:
        return None
    # the id always from the name: the same name is the same preset (an import replaces it), and
    # an imported id can never shadow a built-in preset
    return TweakPreset(id=make_id(name), name=name, icon=str(d.get("icon") or DEFAULT_ICON), desc=str(d.get("desc") or ""),
                       tweak_ids=ids, color=str(d.get("color") or color), builtin=False)


def merge(presets: list, new: list) -> list:
    """presets with new added — one with the same id is replaced in its place."""
    out = list(presets)
    for p in new:
        for i, q in enumerate(out):
            if q.id == p.id:
                out[i] = p
                break
        else:
            out.append(p)
    return out


def load(color: str = DEFAULT_COLOR) -> tuple[list, bool]:
    """(presets, ok). ok False: the file is there but could not be read — then nothing may be
    written over it (the caller reads it again before it saves)."""
    try:
        data = safe_json.read(PRESETS_FILE, [], strict=True)
    except safe_json.Unreadable:
        return [], False
    if not isinstance(data, list):
        data = []
    return merge([], [p for p in (from_dict(d, color) for d in data) if p]), True


def save(presets: list) -> bool:
    """-> True when the presets are on disk."""
    return safe_json.write(PRESETS_FILE, [to_dict(p) for p in presets if not p.builtin])
