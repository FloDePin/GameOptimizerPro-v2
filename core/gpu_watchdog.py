"""
GameOptimizerPro — GPU watchdog (round 16).

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

Round 31 — the precise watchdog: while the app runs, core/gpu_flight.py keeps the
last minutes of clock / voltage / power (saved every few seconds, so it survives a
hard crash) and sees a GPU event within seconds. The state just before the event
(fault_point) names the curve points involved: "make safer" can lower only those,
and the next tune keeps extra margin there (field_voltages). An unexpected restart
(Kernel-Power 41) counts only when the recording shows the card under load until
the end — a black-screen crash that restarts the PC leaves no driver event.
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
RESTART_ID = 41         # Kernel-Power: the PC restarted without shutting down
SLACK_S = 15            # an own session's events may land a few seconds after it ended

# Running own loads (stress tab), by start time: an event while one runs is ours —
# record_own_load only writes the window when the session ends.
_ACTIVE: set = set()
_ACTIVE_MAX_S = 6 * 3600


def own_load_started(start: float):
    _ACTIVE.add(round(float(start), 1))


def own_load_active(now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return any(now - t < _ACTIVE_MAX_S for t in _ACTIVE)


def record_own_load(start: float, end: float):
    """An own GPU load (stress test, FurMark from the app) — its events are ours."""
    _ACTIVE.discard(round(float(start), 1))
    if SESSIONS_FILE is None:
        return
    from core import safe_json
    try:                                       # never write over a list that could not be read:
        data = safe_json.read(SESSIONS_FILE, [], strict=True)   # its own loads would count as games
    except safe_json.Unreadable:
        return
    if not isinstance(data, list):
        data = []
    data.append([round(float(start), 1), round(float(end), 1)])
    safe_json.write(SESSIONS_FILE, data[-MAX_SESSIONS:], indent=None, backup=False)


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
    "$e+=@(Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; "
    "Id=41; StartTime=$s}} -EA SilentlyContinue); "
    "$e | ForEach-Object {{ '{{0}}|{{1}}' -f ([DateTimeOffset]$_.TimeCreated).ToUnixTimeSeconds(), $_.Id }}"
)


def read_events(since: float) -> list:
    """[(epoch, event id)] GPU hang / reset events in the System log since `since`."""
    if os.name != "nt":
        return []
    try:                                       # native first: no powershell.exe (23.10.)
        from core.gpu_flight import events_since
        return sorted((t, i) for t, _src, i in events_since(
            since, {"nvlddmkm": set(NV_IDS), "Display": {4101},
                    "Microsoft-Windows-Kernel-Power": {RESTART_ID}}))
    except Exception:
        pass                                   # the native API not usable here: PowerShell
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
    # Events (and the query's start) are logged to the second: one from the second the
    # profile was applied in may be from BEFORE it — only later seconds count. And only
    # those after the last one the user saw.
    ev = [e for e in trouble_since(max(applied, seen), logs_dir, read) if e[0] > max(seen, int(applied))]
    point = None
    if any(i == RESTART_ID for _t, i in ev):
        # an unexpected restart is GPU trouble only when the card was under load until the
        # recording stopped — the crash moment is the recording's end, not the boot time
        crash = restart_crash(logs_dir, [t for t, i in ev if i == RESTART_ID], last)
        ev = [e for e in ev if e[1] != RESTART_ID]
        if crash:
            ev = sorted(ev + [(crash["t_end"], RESTART_ID)])
            point = crash
    ev = [e for e in ev if e[0] > max(seen, int(applied))]
    if not ev:
        return None
    found = {"profile": last.get("name", ""), "applied": applied, "events": ev, "last": ev[-1][0],
             "data": last}
    rec = point or fault_near(logs_dir, ev[0][0] - 90, ev[-1][0] + 90)
    if rec and rec.get("mv"):
        found["point"] = rec
        found["anchors"] = affected_anchors(last, rec["mv"])
        found["escalate"] = repeated(logs_dir, last.get("name", ""), found["anchors"], ev[0][0] - 90)
    return found


# ── the state just before a fault (round 31) ─────────────────────────────────

LOOKBACK_S = 12          # the hang happens seconds before the driver logs it
LOADED_W_FRAC = 0.55     # "under load": this share of the window's peak power …
LOADED_UTIL = 50         # … or this GPU utilisation
BAND_MV = 25             # curve points this close to the fault voltage are involved
FIELD_FILE = "gpu_field_faults.json"
FLIGHT_FILE = "gpu_flight.json"
FAULTS_DIR = "gpu_faults"
MAX_FIELD = 50


def is_loaded(s: dict, peak_w: float) -> bool:
    """Busy GPU: high utilisation, or high power with at least some utilisation (an
    idle card's own power peak alone is no load)."""
    util = s.get("util", 0) or 0
    return util >= LOADED_UTIL or (util >= 20 and peak_w > 0 and (s.get("w", 0) or 0) >= peak_w * LOADED_W_FRAC)


def fault_point(samples: list, t_event: float, profile: Optional[dict] = None) -> Optional[dict]:
    """{"t", "mv", "mhz", "mem", "w", "temp", "util"} — the loaded sample with the
    highest voltage in the seconds before `t_event` (the boost state a game hangs in);
    None when the card was idle then (no GPU load to blame) or nothing was recorded.
    Without a voltage reading (Afterburner not running) the voltage comes from the
    profile's curve at the recorded clock."""
    win = [s for s in samples if t_event - LOOKBACK_S <= s.get("t", 0) <= t_event + 1]
    if not win:
        return None
    peak_w = max((s.get("w", 0) or 0) for s in samples) or 0
    loaded = [s for s in win if is_loaded(s, peak_w)]
    loaded = [s for s in loaded if (s.get("mhz", 0) or 0) > 0]
    if not loaded:
        return None
    top = max(loaded, key=lambda s: ((s.get("mv", 0) or 0), (s.get("mhz", 0) or 0)))
    out = {k: top.get(k, 0) for k in ("t", "mv", "mhz", "mem", "w", "temp", "util")}
    if not out["mv"] and profile:
        out["mv"] = voltage_at_clock(profile, out["mhz"])
    return out


def _curve(profile: dict) -> list:
    return sorted((int(mv), int(f)) for mv, f in (profile.get("curve_points") or []))


def voltage_at_clock(profile: dict, mhz: float) -> int:
    """The lowest curve point that runs at least `mhz` (a clock on the curve), 0 = none."""
    for mv, f in _curve(profile):
        if f >= mhz - 15:
            return mv
    return 0


def affected_anchors(profile: dict, mv: float) -> list:
    """The curve points (their voltages) a fault at `mv` involves: the ones within
    BAND_MV, at least the two around it; in the flat part (from curve_cap_mv) the cap
    point and everything above it. [] = no own curve (offset profile)."""
    pts = [p for p, _f in _curve(profile)]
    if not pts or not mv:
        return []
    cap = int(profile.get("curve_cap_mv") or 0)
    sel = {p for p in pts if abs(p - mv) <= BAND_MV}
    below = [p for p in pts if p <= mv]
    above = [p for p in pts if p >= mv]
    if below:
        sel.add(max(below))
    if above:
        sel.add(min(above))
    if cap and mv >= cap - BAND_MV:
        sel |= {p for p in pts if p >= min(cap, max(below) if below else cap)}
    return sorted(sel)


def _read_json(path: Path, default, strict: bool = False):
    from core import safe_json
    d = safe_json.read(path, default, strict=strict)
    return d if isinstance(d, type(default)) else default


def _write_json(path: Path, data, backup: bool = False):
    from core import safe_json
    safe_json.write(path, data, indent=None, backup=backup)


def record_fault(logs_dir, fault: dict, samples: list):
    """A fault seen live: the recording around it for later + one line in the field
    list (per GPU) that the next tune reads."""
    d = Path(logs_dir)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(fault.get("t", time.time())))
    _write_json(d / FAULTS_DIR / f"fault_{stamp}.json", dict(fault, samples=samples))
    from core import safe_json
    try:                                       # the field list: what the next tune keeps margin for
        rows = _read_json(d / FIELD_FILE, [], strict=True)
    except safe_json.Unreadable:
        return
    row = {k: fault.get(k) for k in ("t", "gpu", "profile", "mv", "mhz", "ids", "anchors")}
    row.update({k: (fault.get("point") or {}).get(k) for k in ("mem", "w", "temp")})
    rows.append(row)
    _write_json(d / FIELD_FILE, rows[-MAX_FIELD:], backup=True)


def field_faults(logs_dir) -> list:
    return _read_json(Path(logs_dir) / FIELD_FILE, [])


def field_voltages(logs_dir, gpu: str) -> list:
    """Voltages where a game hung on this GPU (seen live) — the next tune adds margin."""
    return sorted({int(r["mv"]) for r in field_faults(logs_dir)
                   if r.get("mv") and (not gpu or not r.get("gpu") or r.get("gpu") == gpu)})


def fault_near(logs_dir, t0: float, t1: float) -> Optional[dict]:
    rows = [r for r in field_faults(logs_dir) if t0 <= float(r.get("t") or 0) <= t1]
    return rows[-1] if rows else None


def _base(name: str) -> str:
    import re
    return re.sub(r"_sicher\d*$", "", name or "")


def repeated(logs_dir, profile: str, anchors: list, before: float) -> bool:
    """A fault at the same points of the same profile family happened before — the
    targeted fix was not enough: make the whole profile safer."""
    fam = _base(profile)
    return any(_base(r.get("profile") or "") == fam and set(r.get("anchors") or []) & set(anchors)
               and float(r.get("t") or 0) < before for r in field_faults(logs_dir))


FLIGHT_PREV = "gpu_flight_prev.json"     # the last session's recording (kept at start)


def save_flight(logs_dir, gpu: str, samples: list):
    _write_json(Path(logs_dir) / FLIGHT_FILE, {"gpu": gpu, "samples": samples})


def keep_previous_flight(logs_dir):
    """At start: the last session's recording moves aside before the new one is written
    — after a crash that restarted the PC it holds the seconds before the crash."""
    src = Path(logs_dir) / FLIGHT_FILE
    try:
        if src.exists():
            os.replace(src, Path(logs_dir) / FLIGHT_PREV)
    except OSError:
        pass


def load_flight(logs_dir, name: str = FLIGHT_FILE) -> dict:
    return _read_json(Path(logs_dir) / name, {})


def restart_crash(logs_dir, boot_times: list, profile: Optional[dict] = None) -> Optional[dict]:
    """An unexpected restart after a recording ended, with the card under load in its
    last seconds -> the fault point at the recording's end; else None."""
    for name in (FLIGHT_PREV, FLIGHT_FILE):
        samples = load_flight(logs_dir, name).get("samples") or []
        if not samples:
            continue
        t_end = float(samples[-1].get("t") or 0)
        if any(t_end < b <= t_end + 3600 for b in boot_times):
            p = fault_point(samples, t_end, profile)
            if p:
                return dict(p, t_end=t_end)
    return None


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
    if RESTART_ID in ids:
        kinds.append("unerwarteter Neustart, die Grafikkarte war bis zuletzt unter Last" if de else
                     "unexpected restart, the graphics card was under load until the end")
    pt, anchors = found.get("point"), found.get("anchors") or []
    state = ""
    if pt and pt.get("mv"):
        state = (f"\n\nKurz davor lief die Karte bei etwa {pt['mv']:.0f} mV / {pt.get('mhz', 0):.0f} MHz "
                 f"({pt.get('w', 0):.0f} W, {pt.get('temp', 0):.0f} °C)." if de else
                 f"\n\nJust before, the card ran at about {pt['mv']:.0f} mV / {pt.get('mhz', 0):.0f} MHz "
                 f"({pt.get('w', 0):.0f} W, {pt.get('temp', 0):.0f} °C).")
    pts = ", ".join(str(a) for a in anchors)
    if anchors and found.get("escalate"):
        fix = (f"An diesen Punkten ({pts} mV) gab es schon einmal einen Fehler — deshalb wird diesmal das "
               f"ganze Profil entschärft (Kurve −30 MHz, Speicher −200 MHz)." if de else
               f"These points ({pts} mV) failed once before — so this time the whole profile is made "
               f"safer (curve −30 MHz, memory −200 MHz).")
    elif anchors:
        fix = (f"„Gezielt entschärfen“ senkt nur die betroffenen Kurvenpunkte ({pts} mV) um 30 MHz — der "
               f"Rest der Kurve und der Speicher bleiben. „Ganz entschärfen“: Kurve −30 MHz, Speicher "
               f"−200 MHz." if de else
               f"'Make safer at these points' lowers only the curve points involved ({pts} mV) by 30 MHz "
               f"— the rest of the curve and the memory stay. 'Make all safer': curve −30 MHz, memory "
               f"−200 MHz.")
    else:
        fix = ("„Entschärfen“ legt eine sicherere Kopie an (Kurve −30 MHz, Speicher −200 MHz) und "
               "wendet sie an." if de else
               "'Make safer' creates a safer copy (curve −30 MHz, memory −200 MHz) and applies it.")
    # Round 33, measured: a program ended in the middle of GPU work while another one encodes video
    # (a recording, a stream) makes the driver log 153 by itself — 6 of 6 times. Alone it is no proof.
    only_153 = set(ids) == {153}
    if de:
        why = ("Das passiert, wenn sich ein Spiel aufhängt oder abstürzt (z. B. „device hung“) — "
               "oft ein Zeichen, dass die Übertaktung im Spiel zu knapp ist.")
        if only_153:
            why += (" Ein 153 allein entsteht aber auch, wenn ein Programm mitten in GPU-Arbeit endet, "
                    "während ein anderes Video aufnimmt oder streamt. Ob das Profil wirklich zu knapp ist, "
                    "zeigt der Härtetest im Stresstest.")
        return (f"Seit du „{found['profile']}“ am {when(found['applied'])} übernommen hast, hat Windows "
                f"{n} GPU-Ereignis(se) außerhalb unserer Tests protokolliert — zuletzt am "
                f"{when(found['last'])}: {', '.join(kinds)}.{state}\n\n{why}\n\n"
                f"{fix} „Standard“ setzt die Grafikkarte auf Werkseinstellungen.")
    why = ("That happens when a game hangs or crashes (e.g. 'device hung') — often a sign that the "
           "overclock is too tight for that game.")
    if only_153:
        why += (" A 153 alone also comes when a program ends in the middle of GPU work while another one "
                "records or streams video. The hardness test on the stress test page shows whether the "
                "profile really is too tight.")
    return (f"Since you applied '{found['profile']}' on {when(found['applied'])}, Windows logged {n} "
            f"GPU event(s) outside our tests — the last on {when(found['last'])}: {', '.join(kinds)}.{state}\n\n"
            f"{why}\n\n"
            f"{fix} 'Stock' puts the graphics card back to factory settings.")
