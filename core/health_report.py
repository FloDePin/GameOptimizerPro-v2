"""
GameOptimizerPro v2.0 — PC Health Report

Reads what Windows has *already* recorded about this machine over the last
30 days and presents it plainly — no changes are made, nothing is installed.

Read-only, one bundled PowerShell call returning JSON. Covers the events that
actually matter for a gaming rig's stability:

  • WHEA hardware errors      (Microsoft-Windows-WHEA-Logger)       → RAM/CPU/PCIe faults
  • Bluescreens / bugchecks   (System 1001 / Kernel-Power BugCheck) → hard crashes
  • Unexpected shutdowns      (Kernel-Power 41)                     → power/instability
  • GPU driver timeouts (TDR) (Display 4101 / 4109)                 → GPU instability
  • Disk errors               (System, source 'disk', 7/11/51)     → failing drive
  • App crashes               (Application 1000)                    → software faults

Each item reports a 30-day count, the most recent occurrence, and a severity.
"""

from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

OK       = "ok"
WARN     = "warn"
CRITICAL = "critical"

# One PowerShell call — count each category in the last 30 days + newest time.
# Get-WinEvent throws when nothing matches, so every query is wrapped and the
# count/last are derived defensively.
_BUNDLE_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$since=(Get-Date).AddDays(-30)
function Q($ht){
  $ev=@(Get-WinEvent -FilterHashtable $ht -MaxEvents 500 -EA SilentlyContinue)
  if($ev -and $ev.Count -gt 0){
    $last=($ev | Sort-Object TimeCreated -Descending | Select-Object -First 1).TimeCreated
    return @{ count=$ev.Count; last=("{0:yyyy-MM-dd HH:mm}" -f $last) }
  }
  return @{ count=0; last="" }
}
$d=[ordered]@{}
$d.whea       = Q @{ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=$since}
$d.bugcheck   = Q @{LogName='System'; Id=1001; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; StartTime=$since}
$d.kpower41   = Q @{LogName='System'; Id=41; StartTime=$since}
$d.tdr        = Q @{LogName='System'; Id=4101,4109; StartTime=$since}
$d.disk       = Q @{LogName='System'; ProviderName='disk'; Id=7,11,51; StartTime=$since}
$d.appcrash   = Q @{LogName='Application'; Id=1000; StartTime=$since}
$d | ConvertTo-Json -Compress
"""


@dataclass
class HealthItem:
    key:      str
    label:    str
    count:    int
    last:     str          # "" if none
    severity: str          # ok | warn | critical
    note:     str


@dataclass
class HealthReport:
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
        if not out:
            return None
        return json.loads(out)
    except Exception:
        return None


def _mk(key, label, data, warn_at, crit_at, note_ok, note_bad) -> HealthItem:
    d = data.get(key, {}) if data else {}
    count = int(d.get("count", 0) or 0)
    last = d.get("last", "") or ""
    if count >= crit_at:
        sev = CRITICAL
    elif count >= warn_at:
        sev = WARN
    else:
        sev = OK
    note = note_ok if count == 0 else note_bad
    return HealthItem(key, label, count, last, sev, note)


def generate() -> HealthReport:
    """Build the 30-day health report. Read-only."""
    rep = HealthReport(items=[])
    if os.name != "nt":
        rep.error = "Health Report nur unter Windows verfügbar."
        return rep

    data = _gather()
    if data is None:
        rep.error = ("Ereignisprotokoll konnte nicht gelesen werden "
                     "(PowerShell/Rechte?).")
        return rep

    items = [
        _mk("whea", "WHEA-Hardwarefehler", data, 1, 5,
            "Keine Hardwarefehler protokolliert.",
            "Hardwarefehler (RAM/CPU/PCIe) — prüfe RAM (MemTest) & Temperaturen."),
        _mk("bugcheck", "Bluescreens (Bugchecks)", data, 1, 3,
            "Keine Bluescreens in 30 Tagen.",
            "Bluescreens aufgetreten — Treiber/RAM/OC prüfen."),
        _mk("kpower41", "Unerwartete Neustarts", data, 1, 3,
            "Keine unerwarteten Neustarts.",
            "Unerwartete Neustarts (Kernel-Power 41) — Netzteil/OC/Temperatur."),
        _mk("tdr", "GPU-Treiber-Timeouts (TDR)", data, 1, 4,
            "Keine GPU-Treiber-Timeouts.",
            "GPU-Timeouts (TDR) — GPU-OC zurücknehmen / Treiber neu."),
        _mk("disk", "Datenträgerfehler", data, 1, 3,
            "Keine Datenträgerfehler.",
            "Datenträgerfehler — SMART/Kabel prüfen, Backup machen."),
        _mk("appcrash", "App-Abstürze", data, 5, 25,
            "Kaum/keine App-Abstürze.",
            "Häufige App-Abstürze — meist unkritisch, aber auffällig."),
    ]
    rep.items = items

    crit = sum(1 for i in items if i.severity == CRITICAL)
    warn = sum(1 for i in items if i.severity == WARN)
    if crit:
        rep.summary = f"⚠ {crit} kritische Auffälligkeit(en), {warn} Warnung(en) — bitte prüfen."
    elif warn:
        rep.summary = f"{warn} Warnung(en) in den letzten 30 Tagen."
    else:
        rep.summary = "✓ Keine relevanten Fehler in den letzten 30 Tagen — System stabil."
    rep.ok = True
    return rep


if __name__ == "__main__":
    r = generate()
    print("ok:", r.ok, "| error:", r.error)
    print("summary:", r.summary)
    for it in (r.items or []):
        print(f"  [{it.severity:8}] {it.label}: count={it.count} last={it.last!r}")
