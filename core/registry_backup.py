r"""
GameOptimizerPro v2.0 — Registry Backup

Portiert aus GameOptimizerPro v1 (Backup-Registry). Exportiert vor dem Anwenden
oder Zurücksetzen von Tweaks alle Registry-Zweige, die die Tweaks anfassen
können, als .reg-Dateien — damit man notfalls per Doppelklick zurück kann.

Rein additiv: es wird nur gelesen und exportiert, nie etwas geändert.
Zielordner:  %LOCALAPPDATA%\GameOptimizerPro\RegistryBackups\<stamp>_<label>\
"""

from __future__ import annotations
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

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
    r"HKCU\Software\Microsoft\GameBar",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR",
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
    r"HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot",
    r"HKCU\System\GameConfigStore",
    r"HKLM\SOFTWARE\ATI Technologies\CBT",
    r"HKLM\SOFTWARE\Microsoft\Dfrg\BootOptimizeFunction",
    r"HKLM\SOFTWARE\Microsoft\DirectX",
    r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Communications",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
    r"HKLM\SOFTWARE\Policies\Microsoft\Dsh",
    r"HKLM\SOFTWARE\Policies\Microsoft\Windows",
    r"HKLM\SYSTEM\CurrentControlSet\Control",
    r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
    r"HKLM\SYSTEM\CurrentControlSet\Services\nvlddmkm\Global\NVTweak",
    r"HKLM\SYSTEM\CurrentControlSet\Services\stornvme\Parameters\Device",
    r"HKLM\SYSTEM\CurrentControlSet\Services\usbaudio",
    r"HKLM\SYSTEM\CurrentControlSet\Services\usbaudio2",
]

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
            return f"✗ Registry-Backup fehlgeschlagen: {self.error}"
        return (f"✓ Registry-Backup: {self.saved} Zweige gesichert"
                f"{f', {self.skipped} nicht vorhanden' if self.skipped else ''}"
                f" → {self.path}")


def backup_root() -> str:
    """Wurzelordner aller Registry-Backups."""
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "GameOptimizerPro", "RegistryBackups")


def create(label: str = "Backup") -> BackupResult:
    """Exportiert alle BACKUP_KEYS als .reg in einen neuen Zeitstempel-Ordner."""
    res = BackupResult()
    if os.name != "nt":
        res.error = "Registry-Backup nur unter Windows verfügbar."
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
    for key in BACKUP_KEYS:
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

    res.path = dest_dir
    res.ok = res.saved > 0
    if not res.ok:
        res.error = ("Kein einziger Zweig konnte exportiert werden "
                     "(Adminrechte fehlen?).")
    else:
        # Ein voller Export ist mehrere Dutzend MB gross (HKLM\...\Control allein
        # ist riesig) und laeuft vor JEDEM Stapel-Apply/Revert automatisch. Ohne
        # Begrenzung laeuft die Platte mit der Zeit voll.
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
