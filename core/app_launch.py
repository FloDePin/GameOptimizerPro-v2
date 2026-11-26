"""
GameOptimizerPro — start without a console window

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


def _session_of(pid: int) -> int | None:
    try:
        import ctypes
        sid = ctypes.c_uint32()
        if ctypes.windll.kernel32.ProcessIdToSessionId(int(pid), ctypes.byref(sid)):
            return sid.value
    except Exception:
        pass
    return None


def foreign_admin(processes=None, me: str | None = None, my_session: int | None = None,
                  session_of=_session_of) -> str | None:
    """Round 49: the elevated app runs under ANOTHER account than the one signed in — UAC asked for an
    administrator's name and password ("over the shoulder"). The per-user tweaks (HKCU: taskbar, mouse,
    privacy switches …) then land in that administrator's profile, not in the signed-in user's.
    -> the signed-in user's name (the owner of explorer.exe in this session), None when it is the same
    account or nothing can be told. `processes` / `me` / `my_session` / `session_of`: for the tests."""
    if os.name != "nt" and processes is None:
        return None
    try:
        import psutil
        if me is None:
            me = psutil.Process().username()
        if my_session is None:
            my_session = session_of(os.getpid())
        if processes is None:
            processes = psutil.process_iter(["pid", "name", "username"])
        owners = set()
        for p in processes:
            info = getattr(p, "info", p)
            if str(info.get("name") or "").lower() != "explorer.exe" or not info.get("username"):
                continue
            if my_session is not None and session_of(info.get("pid")) != my_session:
                continue
            owners.add(str(info["username"]))
        if not owners or not me or any(o.lower() == me.lower() for o in owners):
            return None
        return sorted(owners)[0]
    except Exception:
        return None
