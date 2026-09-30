"""
GameOptimizerPro v2.0 — start without a console window

The launcher (GameOptimizerPro.bat) starts pythonw.exe. Started any other way —
double-click on GameOptimizerPro.py (file association / py launcher / the new
Python install manager) — the app runs in python.exe and its black console
window stayed open the whole time, because the admin relaunch and the language
restart reused that same python.exe.
"""

from __future__ import annotations

import os
import sys


def gui_python() -> str:
    """pythonw.exe next to the running interpreter (no console window); the
    running interpreter itself if there is none."""
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            return w
    return exe


def owns_console() -> bool:
    """True when this process sits in a console window that exists only for it
    (double-click, file association, py launcher). False without a console
    (pythonw) and when it was started from a terminal the user keeps using —
    that one is never touched."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        if not k32.GetConsoleWindow():
            return False
        ids = (ctypes.c_uint32 * 16)()
        n = k32.GetConsoleProcessList(ids, 16)
        if not 0 < n <= 16:
            return False
        import psutil
        for pid in list(ids)[:n]:
            if not psutil.Process(pid).name().lower().startswith("py"):
                return False          # cmd / PowerShell / bash / a terminal
        return True
    except Exception:
        return False
