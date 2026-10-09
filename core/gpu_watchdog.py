"""
GameOptimizerPro v2.0 — GPU watchdog (round 16).

A game can hang (D3D12 "device hung") on a tuned profile without anything
telling the user. Windows records such events in
the System log:

  nvlddmkm 13 / 14   graphics exception (the GPU hit an error)
  nvlddmkm 153       a GPU engine was reset: the GPU hung, or a program was ended
                     while it had GPU work in flight (e.g. a game that hung and was
                     closed)
  Display 4101       the driver was reset (TDR)

GameOptimizerPro causes 153 itself: its stress worker is ended at the end of
every tune step / stress test. Those windows (tune logs, recorded stress
sessions) are left out. What is left after the active profile was applied is
reported at the next app start — with "make the profile safer" and "back to
stock" (GameOptimizerPro._watchdog_*).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# Where own GPU-load sessions (stress tab) are recorded. None = not recorded: the
# app sets it at start, so tests never write into the user's logs folder.
SESSIONS_FILE: Optional[Path] = None
MAX_SESSIONS = 300
NV_IDS = (13, 14, 153)
SLACK_S = 15            # an own session's events may land a few seconds after it ended


def record_own_load(start: float, end: float):
    """An own GPU load (stress test, FurMark from the app) — its events are ours."""
    if SESSIONS_FILE is None:
        return
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8")) if SESSIONS_FILE.exists() else []
        if not isinstance(data, list):
            data = []
    except (OSError, ValueError):
        data = []
    data.append([round(float(start), 1), round(float(end), 1)])
    try:
        SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_FILE.write_text(json.dumps(data[-MAX_SESSIONS:]), encoding="utf-8")
    except OSError:
        pass


def own_windows(logs_dir) -> list:
    """[(start, end)] epoch seconds of GameOptimizerPro's own GPU loads: every tune
    (tune_YYYYMMDD_HHMMSS.log: from its name to its last write) and the recorded
    stress sessions."""
    out = []
    for f in Path(logs_dir).glob("tune_*.log"):
        try:
            start = datetime.strptime(f.name[5:20], "%Y%m%d_%H%M%S").timestamp()
            out.append((start, f.stat().st_mtime))
        except (ValueError, OSError):
            continue
    if SESSIONS_FILE is not None and SESSIONS_FILE.exists():
        try:
            for a, b in json.loads(SESSIONS_FILE.read_text(encoding="utf-8")):
                out.append((float(a), float(b)))
        except (OSError, ValueError, TypeError):
            pass
    return out


_PS = (
    "$s=[DateTime]::Parse('{since}'); "
    "$e=@(Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='nvlddmkm'; StartTime=$s}} "
    "-EA SilentlyContinue | Where-Object {{ @(13,14,153) -contains $_.Id }}); "
    "$e+=@(Get-WinEvent -FilterHashtable @{{LogName='System'; Id=4101; StartTime=$s}} -EA SilentlyContinue); "
    "$e | ForEach-Object {{ '{{0}}|{{1}}' -f ([DateTimeOffset]$_.TimeCreated).ToUnixTimeSeconds(), $_.Id }}"
)


def read_events(since: float) -> list:
    """[(epoch, event id)] GPU hang / reset events in the System log since `since`."""
    if os.name != "nt":
        return []
    ps = _PS.format(since=datetime.fromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        try:
            t, i = line.strip().split("|")
            out.append((float(t), int(i)))
        except ValueError:
            continue
    return sorted(out)


def trouble_since(since: float, logs_dir, read: Callable[[float], list] = read_events) -> list:
    """The GPU events since `since` that no own tune / stress test explains."""
    wins = own_windows(logs_dir)
    return [(t, i) for t, i in read(since)
            if not any(a - SLACK_S <= t <= b + SLACK_S for a, b in wins)]


def check(cr, logs_dir, seen_until: float = 0.0,
          read: Callable[[float], list] = read_events) -> Optional[dict]:
    """GPU trouble since the active profile was applied (and since the user last
    dismissed it) -> {"profile", "applied", "events": [(epoch, id)], "last"} or None.
    Nothing to check without an applied profile (stock: "__…" names)."""
    try:
        last = cr.load_last_applied()
        path = Path(getattr(cr, "_last_applied"))
        applied = path.stat().st_mtime
    except Exception:
        return None
    if not last or str(last.get("name", "")).startswith("__"):
        return None
    seen = float(seen_until or 0)
    # events strictly after the last one the user saw (it is logged to the second)
    ev = [e for e in trouble_since(max(applied, seen), logs_dir, read) if e[0] > seen]
    if not ev:
        return None
    return {"profile": last.get("name", ""), "applied": applied, "events": ev, "last": ev[-1][0],
            "data": last}


def describe(found: dict, de: bool = True) -> str:
    """The dialog text."""
    when = lambda t: time.strftime("%d.%m. %H:%M", time.localtime(t))   # noqa: E731
    n = len(found["events"])
    ids = sorted({i for _t, i in found["events"]})
    kinds = []
    if any(i in (13, 14) for i in ids):
        kinds.append("GPU-Fehler (Grafik-Exception)" if de else "GPU error (graphics exception)")
    if 153 in ids:
        kinds.append("GPU-Hänger / abgebrochene GPU-Arbeit" if de else "GPU hang / aborted GPU work")
    if 4101 in ids:
        kinds.append("Treiber-Reset" if de else "driver reset")
    if de:
        return (f"Seit du „{found['profile']}“ am {when(found['applied'])} übernommen hast, hat Windows "
                f"{n} GPU-Ereignis(se) außerhalb unserer Tests protokolliert — zuletzt am "
                f"{when(found['last'])}: {', '.join(kinds)}.\n\n"
                f"Das passiert, wenn sich ein Spiel aufhängt oder abstürzt (z. B. „device hung“) — "
                f"oft ein Zeichen, dass die Übertaktung im Spiel zu knapp ist.\n\n"
                f"„Entschärfen“ legt eine sicherere Kopie an (Kurve −30 MHz, Speicher −200 MHz) und "
                f"wendet sie an. „Standard“ setzt die Grafikkarte auf Werkseinstellungen.")
    return (f"Since you applied '{found['profile']}' on {when(found['applied'])}, Windows logged {n} "
            f"GPU event(s) outside our tests — the last on {when(found['last'])}: {', '.join(kinds)}.\n\n"
            f"That happens when a game hangs or crashes (e.g. 'device hung') — often a sign that the "
            f"overclock is too tight for that game.\n\n"
            f"'Make safer' creates a safer copy (curve −30 MHz, memory −200 MHz) and applies it. "
            f"'Stock' puts the graphics card back to factory settings.")
