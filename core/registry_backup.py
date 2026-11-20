r"""
GameOptimizerPro — Registry Backup

Portiert aus GameOptimizerPro v1 (Backup-Registry). Exportiert vor dem Anwenden
oder Zurücksetzen von Tweaks alle Registry-Zweige, die die Tweaks anfassen
können, als .reg-Dateien — damit man notfalls per Doppelklick zurück kann.

Rein additiv: es wird nur gelesen und exportiert, nie etwas geändert.
Zielordner:  %LOCALAPPDATA%\GameOptimizerPro-v2\RegistryBackups\<stamp>_<label>\

Round 47 (found in v1's review): the folder was the one v1 uses too — v1's limit of 20 deleted v2's
backups and v2's limit of 10 deleted v1's. Backups made before stay in the old folder
(%LOCALAPPDATA%\GameOptimizerPro\RegistryBackups), untouched. And not the whole
HKLM\...\Control key any more (35 MB per backup): only the branches the tweaks touch, plus the one
value they set on Control itself.
"""

from __future__ import annotations
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from core.i18n import tr as _tr

# Wie viele Backup-Ordner aufgehoben werden (ältere werden automatisch gelöscht).
KEEP_BACKUPS = 10

# Registry-Zweige, die von den Tweaks berührt werden (1:1 aus v1 übernommen).
BACKUP_KEYS: list[str] = [
    r"HKCU\AppEvents\Schemes",
    r"HKCU\Control Panel",
    r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Search",
    r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
    r"HKCU\SOFTWARE\NVIDIA Corporation\Global\NVTweak",
    r"HKCU\SOFTWARE\Policies\Microsoft\Windows\Explorer",
    r"HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}",
    # Per-folder Explorer views (Bags/BagMRU) — "Disable File Explorer Automatic
    # Folder Discovery" DELETES these trees (v1 added this after the port).
    r"HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell",
    r"HKCU\Software\Microsoft\GameBar",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
    r"HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot",
    r"HKCU\SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
    r"HKCU\System\GameConfigStore",
    r"HKLM\SOFTWARE\ATI Technologies\CBT",
    r"HKLM\SOFTWARE\Microsoft\Dfrg\BootOptimizeFunction",
    r"HKLM\SOFTWARE\Microsoft\DirectX",
    r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia",
    # game profiles (CPU / I/O priority per .exe, fullscreen flag per path)
    r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options",
    r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Communications",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
    r"HKLM\SOFTWARE\Policies\Microsoft\Dsh",
    r"HKLM\SOFTWARE\Policies\Microsoft\Windows",
    r"HKLM\SOFTWARE\Policies\WindowsNotepad",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint",
    r"HKLM\SOFTWARE\GameOptimizerPro",
    # the branches of HKLM\...\Control the tweaks touch (the whole key is 35 MB per backup)
    r"HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",   # display adapters
    r"HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}",   # network adapters
    r"HKLM\SYSTEM\CurrentControlSet\Control\FeatureManagement\Overrides",
    r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem",
    r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
    r"HKLM\SYSTEM\CurrentControlSet\Control\Power",
    r"HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl",
    r"HKLM\SYSTEM\CurrentControlSet\Control\Remote Assistance",
    r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager",
    r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
    r"HKLM\SYSTEM\CurrentControlSet\Services\nvlddmkm\Global\NVTweak",
    r"HKLM\SYSTEM\CurrentControlSet\Services\stornvme\Parameters\Device",
    r"HKLM\SYSTEM\CurrentControlSet\Services\usbaudio",
    r"HKLM\SYSTEM\CurrentControlSet\Services\usbaudio2",
    r"HKLM\SYSTEM\CurrentControlSet\Services\WSAIFabricSvc",
    r"HKU\.DEFAULT\Control Panel\Keyboard",
]


def _device_keys() -> list[str]:
    """Per-device keys can't be listed statically (the path holds the PnP
    instance ID): MSI mode writes under the GPU, NVMe queue depth and the
    write-cache setting under each disk. Their 'Device Parameters' (v1 too)."""
    # Through PowerShell, not the wmi module: the optimizer backs up from a worker thread, where
    # wmi.WMI() failed without COM set up for the thread — the GPU and disk keys were never in a
    # backup. In a subprocess the thread doesn't matter.
    ids: list[str] = []
    ps = ("Get-CimInstance Win32_VideoController | Where-Object { $_.PNPDeviceID -and $_.Name -notmatch "
          "'Microsoft' } | ForEach-Object { $_.PNPDeviceID }; Get-CimInstance Win32_DiskDrive | "
          "Where-Object { $_.PNPDeviceID } | ForEach-Object { $_.PNPDeviceID }")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ids = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        if not ids:
            print(f"[registry backup] no device keys found (exit {r.returncode}): {(r.stderr or '')[:200]}")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[registry backup] device keys not read: {e}")
    seen, out = set(), []
    for i in ids:
        if i.lower() not in seen:
            seen.add(i.lower())
            out.append(rf"HKLM\SYSTEM\CurrentControlSet\Enum\{i}\Device Parameters")
    return out

# Zeichen, die in einem Dateinamen nicht vorkommen duerfen. Bewusst ueber
# re.escape() aus einer Zeichenkette gebaut statt als handgeschriebene
# Zeichenklasse — sonst faellt beim Escapen leicht der Backslash heraus, und
# genau dann legt reg.exe Unterordner statt einer Datei an und schlaegt fehl.
_UNSAFE_FILE_CHARS = re.compile("[" + re.escape('\\/:*?"<>|') + "]")


@dataclass
class BackupResult:
    ok:      bool = False
    path:    str = ""
    saved:   int = 0
    skipped: int = 0          # Key existiert auf diesem System nicht
    error:   str = ""
    files:   list = field(default_factory=list)

    def summary(self) -> str:
        if not self.ok:
            return _tr(f"✗ Registry-Backup fehlgeschlagen: {self.error}", f"✗ Registry backup failed: {self.error}")
        return (_tr(f"✓ Registry-Backup: {self.saved} Zweige gesichert",
                    f"✓ Registry backup: {self.saved} branches saved")
                + (_tr(f", {self.skipped} nicht vorhanden", f", {self.skipped} not present") if self.skipped else "")
                + f" → {self.path}")


def backup_root() -> str:
    """Wurzelordner aller Registry-Backups — ein eigener für v2 (v1 räumt seinen Ordner selbst auf)."""
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "GameOptimizerPro-v2", "RegistryBackups")


# Values the tweaks set on HKLM\...\Control itself: reg.exe can only export a key WITH all its subkeys
# (the whole 35 MB), so these few go into a small .reg of their own.
CONTROL_KEY = r"HKLM\SYSTEM\CurrentControlSet\Control"
CONTROL_VALUES = ("SvcHostSplitThresholdInKB",)


def _reg_string(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def export_values(key: str, names, out: str) -> bool:
    """A .reg file with only these values of one key (UTF-16 like reg.exe's). A value that isn't there
    is written as `"name"=-`: double-clicking the backup removes it again — that is the state before."""
    import winreg
    hive_name, sub = key.split("\\", 1)
    hives = {"HKLM": (winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE"),
             "HKCU": (winreg.HKEY_CURRENT_USER, "HKEY_CURRENT_USER")}
    hive, full = hives[hive_name]
    lines = ["Windows Registry Editor Version 5.00", "", f"[{full}\\{sub}]"]
    try:
        k = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return False
    with k:
        for n in names:
            try:
                v, t = winreg.QueryValueEx(k, n)
            except FileNotFoundError:
                lines.append(f"{_reg_string(n)}=-")
                continue
            except OSError:
                continue
            if t == winreg.REG_DWORD:
                lines.append(f"{_reg_string(n)}=dword:{v & 0xFFFFFFFF:08x}")
            elif t == winreg.REG_SZ:
                lines.append(f"{_reg_string(n)}={_reg_string(v)}")
    try:
        with open(out, "w", encoding="utf-16", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        return False
    return True


def create(label: str = "Backup") -> BackupResult:
    """Exportiert alle BACKUP_KEYS als .reg in einen neuen Zeitstempel-Ordner."""
    res = BackupResult()
    if os.name != "nt":
        res.error = _tr("Registry-Backup nur unter Windows verfügbar.", "Registry backup is only available on Windows.")
        return res

    safe_label = re.sub(r"[^A-Za-z0-9_-]", "", label or "Backup")[:40] or "Backup"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = os.path.join(backup_root(), f"{stamp}_{safe_label}")
    try:
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        res.error = str(e)
        return res

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for key in BACKUP_KEYS + _device_keys():
        fname = _UNSAFE_FILE_CHARS.sub("_", key) + ".reg"
        out = os.path.join(dest_dir, fname)
        try:
            # reg.exe export akzeptiert KEINE doppelten Backslashes — der Key
            # wird deshalb exakt so übergeben, wie er oben notiert ist.
            r = subprocess.run(
                ["reg.exe", "export", key, out, "/y"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, creationflags=flags,
            )
            if r.returncode == 0 and os.path.exists(out):
                res.saved += 1
                res.files.append(out)
            else:
                res.skipped += 1
        except Exception:
            res.skipped += 1
    out = os.path.join(dest_dir, _UNSAFE_FILE_CHARS.sub("_", CONTROL_KEY) + "_values.reg")
    if export_values(CONTROL_KEY, CONTROL_VALUES, out):
        res.saved += 1
        res.files.append(out)
    else:
        res.skipped += 1

    res.path = dest_dir
    res.ok = res.saved > 0
    if not res.ok:
        res.error = (_tr("Kein einziger Zweig konnte exportiert werden "
                     "(Adminrechte fehlen?).", "Not a single branch could be exported (missing admin rights?)."))
    else:
        # It runs before EVERY apply / revert batch: without a limit the disk would fill up over time.
        prune(KEEP_BACKUPS)
    return res


def prune(keep: int = KEEP_BACKUPS) -> int:
    """Behaelt die `keep` neuesten Backups, loescht aeltere. Gibt die Anzahl der
    geloeschten Ordner zurueck. Best-effort — Fehler werden ignoriert."""
    import shutil
    removed = 0
    try:
        backups = list_backups()          # neueste zuerst
    except Exception:
        return 0
    for _name, full, _n in backups[max(0, keep):]:
        try:
            shutil.rmtree(full, ignore_errors=True)
            if not os.path.isdir(full):
                removed += 1
        except Exception:
            pass
    return removed


def list_backups() -> list[tuple[str, str, int]]:
    """Vorhandene Backups: (Ordnername, voller Pfad, Anzahl .reg-Dateien), neueste zuerst."""
    root = backup_root()
    out: list[tuple[str, str, int]] = []
    try:
        for name in sorted(os.listdir(root), reverse=True):
            full = os.path.join(root, name)
            if os.path.isdir(full):
                try:
                    n = len([f for f in os.listdir(full) if f.lower().endswith(".reg")])
                except OSError:
                    n = 0
                out.append((name, full, n))
    except OSError:
        pass
    return out


if __name__ == "__main__":
    r = create("SelfTest")
    print(r.summary())
    for name, path, n in list_backups()[:5]:
        print(f"  {name}: {n} .reg")
