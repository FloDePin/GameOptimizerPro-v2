"""
GameOptimizerPro v2.0 — Remnant Detection

Scans (read-only) for leftovers of *other* PC-tweaking tools that commonly stay
behind after use or uninstall and can quietly affect stability/latency. It only
reports findings with their location — it never removes anything, and it never
flags GameOptimizerPro's own tweaks or autostart.

Detected:
  • WinRing0 / inppout kernel drivers  — shipped by many OC/timer tools; WinRing0
    is a known-vulnerable driver worth removing when its owner is gone.
  • ISLC (Intelligent Standby List Cleaner) autostart / task.
  • TimerResolution / SetTimerResolution autostart (fixed timer-res hacks).
  • Third-party / custom Windows power plans (non-standard GUIDs) left behind.
  • Razer Cortex "Game Booster" install remnants.

One bundled, read-only PowerShell call returning JSON.
"""

from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional
from core.i18n import tr as _tr

# Standard Windows power-scheme GUIDs — anything else is third-party/custom.
_STD_POWER_GUIDS = {
    "381b4222-f694-41f0-9685-ff5bb260df2e",  # Balanced
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # High performance
    "a1841308-3541-4fab-bc81-f71556f20b4a",  # Power saver
    "e9a42b02-d5df-448d-aa00-03f14749eb61",  # Ultimate performance
}

_BUNDLE_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$drv="$env:SystemRoot\System32\drivers"
$out=[ordered]@{}

$out.winring0 = @{
  present = [bool]((Test-Path "$drv\WinRing0x64.sys") -or (Test-Path "$drv\WinRing0.sys"))
  detail  = (@("$drv\WinRing0x64.sys","$drv\WinRing0.sys") | Where-Object { Test-Path $_ }) -join '; '
}
$out.inpout = @{
  present = [bool]((Test-Path "$drv\inpoutx64.sys") -or (Test-Path "$drv\inpout32.sys"))
  detail  = (@("$drv\inpoutx64.sys","$drv\inpout32.sys") | Where-Object { Test-Path $_ }) -join '; '
}

$tasks = @(Get-ScheduledTask -EA SilentlyContinue |
  Where-Object { $_.TaskName -match 'ISLC|StandbyList' } | Select-Object -Expand TaskName)
$out.islc = @{ present=[bool]($tasks.Count -gt 0); detail=($tasks -join ', ') }

$ttasks = @(Get-ScheduledTask -EA SilentlyContinue |
  Where-Object { $_.TaskName -match 'TimerResolution|SetTimerResolution' } | Select-Object -Expand TaskName)
$runkeys = @()
foreach($rk in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run')){
  $p = Get-ItemProperty $rk -EA SilentlyContinue
  if($p){ $p.PSObject.Properties | ForEach-Object {
    if($_.Value -match 'timerresolution|SetTimerResolution|ISLC'){ $runkeys += $_.Name } } }
}
$out.timerres = @{ present=[bool](($ttasks.Count + $runkeys.Count) -gt 0);
                   detail=(($ttasks + $runkeys) -join ', ') }

$plans = @()
foreach($line in (powercfg /list)){
  if($line -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'){
    $g=$Matches[1].ToLower()
    $name=''
    if($line -match '\(([^)]+)\)'){ $name=$Matches[1] }
    $plans += ("{0}|{1}" -f $g,$name)
  }
}
$out.powerplans = @{ list = ($plans -join ';;') }

$rc = @("$env:ProgramFiles\Razer\Razer Cortex","${env:ProgramFiles(x86)}\Razer\Razer Cortex") |
      Where-Object { Test-Path $_ }
$out.razer_cortex = @{ present=[bool]($rc.Count -gt 0); detail=($rc -join '; ') }

$out | ConvertTo-Json -Compress -Depth 4
"""


@dataclass
class RemnantItem:
    key:     str
    label:   str
    present: bool
    detail:  str
    advice:  str


@dataclass
class RemnantScan:
    ok:    bool = False
    items: list = None
    error: str = ""
    summary: str = ""


def _gather() -> Optional[dict]:
    if os.name != "nt":
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", _BUNDLE_PS],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45, creationflags=flags,
        )
        out = (r.stdout or "").strip()
        return json.loads(out) if out else None
    except Exception:
        return None


def scan() -> RemnantScan:
    """Scan for third-party tweak-tool remnants. Read-only."""
    res = RemnantScan(items=[])
    if os.name != "nt":
        res.error = _tr("Remnant-Scan nur unter Windows verfügbar.", "Remnant scan is only available on Windows.")
        return res
    data = _gather()
    if data is None:
        res.error = _tr("Scan konnte nicht ausgeführt werden (PowerShell/Rechte?).", "The scan could not run (PowerShell / rights?).")
        return res

    items: list[RemnantItem] = []

    def g(key):
        return data.get(key, {}) if data else {}

    wr = g("winring0")
    items.append(RemnantItem(
        "winring0", _tr("WinRing0-Treiber", "WinRing0 driver"), bool(wr.get("present")),
        wr.get("detail", ""),
        _tr("Von OC-/Timer-Tools mitgeliefert und als angreifbar bekannt. Wenn du das "
        "zugehörige Tool nicht mehr nutzt: Treiberdienst entfernen.", "Shipped with OC / timer tools and known to be exploitable. If you no longer use the tool: remove the driver service.")))

    ip = g("inpout")
    items.append(RemnantItem(
        "inpout", _tr("inpout32/x64-Treiber", "inpout32/x64 driver"), bool(ip.get("present")),
        ip.get("detail", ""),
        _tr("Legacy-I/O-Treiber alter Tweak-Tools. Bei Nichtgebrauch entfernbar.", "Legacy I/O driver of old tweak tools. Can be removed when not in use.")))

    islc = g("islc")
    items.append(RemnantItem(
        "islc", "ISLC Standby-List-Cleaner", bool(islc.get("present")),
        islc.get("detail", ""),
        _tr("Intelligent Standby List Cleaner als Task gefunden — nur behalten wenn "
        "bewusst genutzt.", "Intelligent Standby List Cleaner found as a task — keep it only if you use it on purpose.")))

    tr = g("timerres")
    items.append(RemnantItem(
        "timerres", "TimerResolution-Autostart", bool(tr.get("present")),
        tr.get("detail", ""),
        _tr("Fester Timer-Resolution-Hack im Autostart — auf Win11 meist unnötig.", "Fixed timer-resolution hack in the autostart — usually unnecessary on Windows 11.")))

    rc = g("razer_cortex")
    items.append(RemnantItem(
        "razer_cortex", "Razer Cortex (Game Booster)", bool(rc.get("present")),
        rc.get("detail", ""),
        _tr("Game-Booster-Suite gefunden — häufig ohne messbaren Nutzen, viel Hintergrundlast.", "Game booster suite found — often no measurable benefit, a lot of background load.")))

    # Third-party power plans (non-standard GUIDs). Duplicated plans (e.g. many
    # "Ultimate Performance" copies) share a name but each has its own GUID, so
    # collapse by name with a count to keep the report readable.
    raw = g("powerplans").get("list", "") or ""
    counts: dict[str, int] = {}
    ultimate: list[str] = []
    for entry in [e for e in raw.split(";;") if e]:
        guid, _, name = entry.partition("|")
        if guid.strip().lower() in _STD_POWER_GUIDS:
            continue
        label = name.strip() or guid.strip()
        # "Ultimate Performance" is Windows' own hidden plan: activating it
        # (also GameOptimizerPro's tweak) creates a copy with a new GUID. One
        # copy is normal — only duplicates are worth reporting.
        if "ultimat" in label.lower():
            ultimate.append(label)
            continue
        counts[label] = counts.get(label, 0) + 1
    extra = [f"{name} ×{n}" if n > 1 else name for name, n in counts.items()]
    if len(ultimate) > 1:
        extra.append(f"{ultimate[0]} ×{len(ultimate)} "
                     + _tr("(Duplikate — eine Kopie reicht)", "(duplicates — one copy is enough)"))
    items.append(RemnantItem(
        "powerplans", _tr("Fremd-Energiepläne", "Third-party power plans"), bool(extra),
        ", ".join(extra),
        _tr("Nicht-Standard-Energiepläne (oft von Tweak-Tools/Duplikate angelegt). "
        "Prüfen ob gewollt; sonst über 'powercfg /delete <GUID>' entfernbar.", "Non-standard power plans (often created by tweak tools / duplicates). Check whether you want them; otherwise remove with 'powercfg /delete <GUID>'.")))

    res.items = items
    found = [i for i in items if i.present]
    if found:
        res.summary = _tr(f"{len(found)} mögliche(r) Rest/Fund: ", f"{len(found)} possible leftover(s): ") + ", ".join(i.label for i in found)
    else:
        res.summary = _tr("✓ Keine Reste bekannter Fremd-Tweak-Tools gefunden.", "✓ No leftovers of known third-party tweak tools found.")
    res.ok = True
    return res


if __name__ == "__main__":
    r = scan()
    print("ok:", r.ok, "| error:", r.error)
    print("summary:", r.summary)
    for it in (r.items or []):
        mark = "FOUND" if it.present else "  -  "
        print(f"  [{mark}] {it.label}: {it.detail!r}")
