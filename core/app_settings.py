"""
GameOptimizerPro v2.0 — small persistent app settings (JSON next to the other
state files in logs/). Used for things the user picks once and expects to be
remembered after a restart (e.g. the FurMark location).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

# GOP_SETTINGS_FILE: tests (run_all_tests.py) — never the app's own settings
SETTINGS_FILE = (Path(os.environ["GOP_SETTINGS_FILE"]) if os.environ.get("GOP_SETTINGS_FILE")
                 else Path(__file__).resolve().parent.parent / "logs" / "settings.json")
_lock = threading.Lock()


def load() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> bool:            # noqa: A001 — mirrors dict API
    with _lock:
        data = load()
        data[key] = value
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, SETTINGS_FILE)
            return True
        except OSError:
            return False
