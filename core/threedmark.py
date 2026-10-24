"""
GameOptimizerPro — 3DMark detection and launch

3DMark is found in every Steam library (libraryfolders.vdf), in the usual
standalone install folders, or where the user pointed the app to (remembered).
The Steam version is started through Steam (steam://rungameid/223850) — it
refuses to run when started directly. Command-line stress tests
(3DMarkCmd.exe) only exist in the Professional Edition; with the normal
editions the user picks the test in 3DMark and GameOptimizerPro records the
GPU values meanwhile.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from core import app_settings
from core.i18n import tr as _tr

SETTING_KEY = "3dmark_path"
STEAM_APP_ID = "223850"
STORE_URL = "https://store.steampowered.com/app/223850/3DMark/"

_STANDALONE = [
    r"C:\Program Files\UL\3DMark\3DMark.exe",
    r"C:\Program Files\UL\3DMark\bin\x64\3DMark.exe",
    r"C:\Program Files\Futuremark\3DMark\3DMark.exe",
    r"C:\Program Files\Futuremark\3DMark\bin\x64\3DMark.exe",
    r"C:\Program Files (x86)\UL\3DMark\3DMark.exe",
]
# process names of the launcher and its test workloads (lower case prefixes)
PROCESS_PREFIXES = ("3dmark",)


def steam_path() -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            p, _ = winreg.QueryValueEx(k, "SteamPath")
        p = os.path.normpath(p)
        return p if os.path.isdir(p) else None
    except OSError:
        return None


def steam_libraries(steam: str | None = None) -> list[str]:
    """All Steam library folders (the Steam folder itself first)."""
    steam = steam or steam_path()
    if not steam:
        return []
    libs = [steam]
    vdf = Path(steam) / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return libs
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = os.path.normpath(m.group(1).replace("\\\\", "\\"))
        if p.lower() not in (x.lower() for x in libs):
            libs.append(p)
    return libs


def _steam_candidates() -> list[str]:
    out = []
    for lib in steam_libraries():
        base = Path(lib) / "steamapps" / "common" / "3DMark"
        out += [str(base / "bin" / "x64" / "3DMark.exe"), str(base / "3DMark.exe")]
    return out


def _real_case(path: str) -> str:
    """Steam keeps its path lower-case ("c:\\program files (x86)\\steam") —
    show the spelling on disk."""
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def detect() -> str | None:
    saved = app_settings.get(SETTING_KEY)
    if saved and os.path.exists(saved):
        return _real_case(saved)
    for p in _steam_candidates() + _STANDALONE:
        if os.path.exists(p):
            return _real_case(p)
    return None


def remember(path: str) -> str:
    path = os.path.normpath(path)
    app_settings.set(SETTING_KEY, path)
    return path


def is_steam(path: str) -> bool:
    return "steamapps" in path.lower().replace("/", "\\").split("\\")


def cmd_exe(path: str) -> str | None:
    """3DMarkCmd.exe (Professional Edition only) next to 3DMark.exe."""
    p = Path(path)
    for c in (p.with_name("3DMarkCmd.exe"), p.parent.parent.parent / "3DMarkCmd.exe"):
        if c.exists():
            return str(c)
    return None


def launch(path: str) -> tuple[bool, str]:
    """Start 3DMark (via Steam for the Steam version). Returns (ok, message)."""
    try:
        if is_steam(path):
            os.startfile(f"steam://rungameid/{STEAM_APP_ID}")
            return True, _tr("3DMark wird über Steam gestartet …", "Starting 3DMark through Steam …")
        subprocess.Popen([path], cwd=os.path.dirname(path))
        return True, _tr("3DMark gestartet.", "3DMark started.")
    except OSError as e:
        return False, str(e)


def running_processes() -> list[str]:
    """Names of running 3DMark processes (launcher + test workloads)."""
    try:
        import psutil
    except ImportError:
        return []
    names = []
    for p in psutil.process_iter(["name"]):
        n = (p.info.get("name") or "").lower()
        if n.startswith(PROCESS_PREFIXES):
            names.append(p.info["name"])
    return names



# ── Results (24.10.: the 3DMark comparison of the profiles) ──────────────────
# Every run leaves a .3dmark-result (a zip: Result.xml with the scores, Monitoring.csv). 3DMark saves it
# to Documents\3DMark — or, when it can't move it there (live 24.10.), to ProgramData\UL\3DMark\Results.
_SCORE_RE = re.compile(r"<([A-Za-z]+?)Performance(Graphics)?Score>(\d+(?:\.\d+)?)</")


def result_dirs() -> list[str]:
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    prog = os.environ.get("ProgramData") or os.path.join("C:" + os.sep, "ProgramData")
    return [os.path.join(home, "Documents", "3DMark"), os.path.join(prog, "UL", "3DMark", "Results")]


def _test_name(tag: str) -> str:
    """"SpeedWay" -> "Speed Way", "TimeSpyExtreme" -> "Time Spy Extreme"."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tag)


def parse_result(path: str) -> dict | None:
    """{"test": "Speed Way", "score": 7613, "file": name, "t": mtime} — the graphics score (the GPU's
    part; Time Spy's total also counts the CPU), None for a failed / unreadable result."""
    import zipfile
    name = os.path.basename(path)
    if "FAILED" in name.upper():
        return None
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("Result.xml").decode("utf-8", "replace")
        t = os.path.getmtime(path)
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    best = None
    for tag, graphics, val in _SCORE_RE.findall(xml):
        if tag.endswith("ForPass") or float(val) <= 0:
            continue
        if best is None or (graphics and not best[1]):
            best = (tag, graphics, float(val))
    if best is None:
        return None
    return {"test": _test_name(best[0]), "score": int(round(best[2])), "file": name, "t": t}


def results_since(since: float, dirs: list | None = None) -> list[dict]:
    """Every readable result written after `since` (epoch), oldest first."""
    out = []
    for d in dirs if dirs is not None else result_dirs():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if not n.endswith(".3dmark-result"):
                continue
            p = os.path.join(d, n)
            try:
                if os.path.getmtime(p) <= since:
                    continue
            except OSError:
                continue
            r = parse_result(p)
            if r:
                out.append(r)
    return sorted(out, key=lambda r: r["t"])
