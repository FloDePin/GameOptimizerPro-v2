"""
GameOptimizerPro v2.0 — Startup control (v1 parity)

Lists autostart entries and enables/disables them EXACTLY the way the Windows
Task Manager does: nothing is deleted or moved. Windows keeps a per-entry flag
under ...\\Explorer\\StartupApproved\\<Run|Run32|StartupFolder>:

    first byte 0x02 / 0x06 (even) -> enabled
    first byte 0x03 / 0x07 (odd)  -> disabled; bytes 4..11 = FILETIME of disabling

Verified against a live system. Missing flag = enabled (Windows default).
Disabling is therefore always reversible — from here or from Task Manager.

Sources (same as v1):
    HKCU Run, HKLM Run, HKLM Run (32-bit / WOW6432Node)
    the per-user and the all-users Startup folder (.lnk etc.)
"""

from __future__ import annotations
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import winreg
except ImportError:          # non-Windows: module stays importable, lists nothing
    winreg = None

_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
_RUN      = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN32    = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"

ENABLED_BLOB = bytes([0x02] + [0] * 11)


def _hkcu():
    return winreg.HKEY_CURRENT_USER if winreg else None


def _hklm():
    return winreg.HKEY_LOCAL_MACHINE if winreg else None


@dataclass
class StartupEntry:
    name:     str                 # value name / file name (the StartupApproved key)
    command:  str                 # command line or resolved shortcut target
    source:   str                 # human label, e.g. "HKCU\\Run"
    enabled:  bool = True
    hive_label: str = "HKCU"      # "HKCU" | "HKLM" (HKLM needs admin to change)
    approved_sub: str = "Run"     # Run | Run32 | StartupFolder
    file:     str = ""            # full path for Startup-folder entries
    extra:    dict = field(default_factory=dict)


# ── Flag encoding ─────────────────────────────────────────────────────────────

def is_disabled_blob(blob) -> bool:
    """True when a StartupApproved value marks the entry as disabled."""
    return bool(blob) and (blob[0] & 0x01) == 0x01


def disabled_blob(now: Optional[float] = None) -> bytes:
    """0x03 + 3 zero bytes + FILETIME (100-ns ticks since 1601), like Task Manager."""
    ts = time.time() if now is None else now
    filetime = int((ts + 11644473600) * 10_000_000)
    return bytes([0x03, 0, 0, 0]) + filetime.to_bytes(8, "little")


# ── Registry helpers ─────────────────────────────────────────────────────────

def _hive(label: str):
    return _hkcu() if label == "HKCU" else _hklm()


def _read_flag(hive_label: str, sub: str, name: str):
    """Raw StartupApproved blob for an entry, or None if Windows has none yet."""
    if not winreg:
        return None
    try:
        with winreg.OpenKey(_hive(hive_label), _APPROVED + "\\" + sub, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            val, typ = winreg.QueryValueEx(k, name)
            return val if typ == winreg.REG_BINARY else None
    except OSError:
        return None


def read_enabled(entry: StartupEntry) -> bool:
    return not is_disabled_blob(_read_flag(entry.hive_label, entry.approved_sub, entry.name))


def _enum_values(hive, path: str) -> list[tuple[str, str]]:
    out = []
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            i = 0
            while True:
                try:
                    name, val, typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                if name and typ in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                    out.append((name, str(val)))
    except OSError:
        pass
    return out


def _startup_folders() -> list[tuple[str, str, str]]:
    """(label, folder path, hive label for its StartupApproved flag)."""
    appdata = os.environ.get("APPDATA", "")
    progdata = os.environ.get("ProgramData", r"C:\ProgramData")
    return [
        ("Autostart-Ordner",
         os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"), "HKCU"),
        ("Autostart-Ordner (alle Nutzer)",
         os.path.join(progdata, r"Microsoft\Windows\Start Menu\Programs\StartUp"), "HKLM"),
    ]


def _resolve_shortcuts(paths: list[str]) -> dict[str, str]:
    """Resolve .lnk targets in ONE PowerShell call (WScript.Shell). Best effort."""
    lnks = [p for p in paths if p.lower().endswith(".lnk")]
    if not lnks or os.name != "nt":
        return {}
    ps = (
        "$w=New-Object -ComObject WScript.Shell; $r=@{}; "
        "foreach($p in (ConvertFrom-Json $env:GOP_LNKS)){ "
        "try{ $s=$w.CreateShortcut($p); $t=$s.TargetPath; "
        "if($s.Arguments){ $t=($t + ' ' + $s.Arguments) }; $r[$p]=$t }catch{} }; "
        "$r | ConvertTo-Json -Compress"
    )
    env = dict(os.environ, GOP_LNKS=json.dumps(lnks))   # paths via env: no quoting issues
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads((r.stdout or "").strip() or "{}")
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception:
        return {}


# ── Public API ───────────────────────────────────────────────────────────────

def list_entries() -> list[StartupEntry]:
    """All autostart entries with their real enabled/disabled state."""
    if not winreg:
        return []
    entries: list[StartupEntry] = []
    for label, hive_label, path, sub in (
        ("HKCU\\Run",       "HKCU", _RUN,   "Run"),
        ("HKLM\\Run",       "HKLM", _RUN,   "Run"),
        ("HKLM\\Run (x86)", "HKLM", _RUN32, "Run32"),
    ):
        for name, cmd in _enum_values(_hive(hive_label), path):
            e = StartupEntry(name=name, command=cmd, source=label,
                             hive_label=hive_label, approved_sub=sub)
            e.enabled = read_enabled(e)
            entries.append(e)

    folder_files = []
    for label, folder, hive_label in _startup_folders():
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for fn in names:
            full = os.path.join(folder, fn)
            if fn.lower() == "desktop.ini" or not os.path.isfile(full):
                continue
            e = StartupEntry(name=fn, command=full, source=label, hive_label=hive_label,
                             approved_sub="StartupFolder", file=full)
            e.enabled = read_enabled(e)
            entries.append(e)
            folder_files.append(full)

    targets = _resolve_shortcuts(folder_files)
    for e in entries:
        if e.file and e.file in targets:
            e.command = targets[e.file]
    return entries


def set_enabled(entry: StartupEntry, enabled: bool) -> tuple[bool, str]:
    """Enable/disable like Task Manager (flag only). Verifies by reading back."""
    if not winreg:
        return False, "Nur unter Windows verfügbar."
    blob = ENABLED_BLOB if enabled else disabled_blob()
    try:
        with winreg.CreateKeyEx(_hive(entry.hive_label), _APPROVED + "\\" + entry.approved_sub,
                                0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, entry.name, 0, winreg.REG_BINARY, blob)
    except PermissionError:
        return False, ("Zugriff verweigert — HKLM-/Alle-Nutzer-Einträge brauchen "
                       "Administratorrechte.")
    except OSError as e:
        return False, f"Schreiben fehlgeschlagen: {e}"
    now_enabled = read_enabled(entry)
    entry.enabled = now_enabled
    if now_enabled != enabled:
        return False, "Wert geschrieben, aber beim Zurücklesen nicht übernommen."
    return True, ("aktiviert" if enabled else "deaktiviert")


if __name__ == "__main__":
    for e in list_entries():
        print(f"{'AN ' if e.enabled else 'AUS'}  {e.source:32} {e.name[:34]:34} {e.command[:60]}")
