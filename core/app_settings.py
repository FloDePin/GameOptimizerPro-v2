"""
GameOptimizerPro — small persistent app settings (JSON next to the other
state files in logs/). Used for things the user picks once and expects to be
remembered after a restart (e.g. the FurMark location).

Read and written through core/safe_json (audit 2026-10-23): a settings file that can't be read
for a moment is never overwritten with just the one value being saved — that used to wipe every
other setting.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from core import safe_json

# GOP_SETTINGS_FILE: tests (run_all_tests.py) — never the app's own settings
SETTINGS_FILE = (Path(os.environ["GOP_SETTINGS_FILE"]) if os.environ.get("GOP_SETTINGS_FILE")
                 else Path(__file__).resolve().parent.parent / "logs" / "settings.json")
_lock = threading.Lock()


def load() -> dict:
    data = safe_json.read(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> bool:            # noqa: A001 — mirrors dict API
    """-> False when the value could not be saved — and then nothing else was touched either."""
    with _lock:
        try:
            data = safe_json.read(SETTINGS_FILE, {}, strict=True)
        except safe_json.Unreadable:
            return False                     # never write over settings we could not read
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        return safe_json.write(SETTINGS_FILE, data)
