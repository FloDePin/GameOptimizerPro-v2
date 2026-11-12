"""
GameOptimizerPro — PC Health Report

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
from core.i18n import tr as _tr

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
$dg=Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard -EA SilentlyContinue
$d.hvci       = @{ known=[bool]$dg; running=[bool]($dg -and (@($dg.SecurityServicesRunning) -contains 2)) }
"""

# BitLocker / device encryption of the system drive (round 45). Win32_EncryptableVolume is documented
# (ProtectionStatus 0 off / 1 on / 2 unknown; ConversionStatus 0 decrypted, 1 encrypted, 2 encrypting,
# 3 decrypting, 4/5 paused) and needs admin rights — the app runs elevated. Without them the Explorer's
# shell property gives at least on/off; only its values 1 (on) and 2 (off) are used.
_BITLOCKER_PS = r"""
$bl=@{ known=$false }
try {
  $ev=Get-CimInstance -Namespace root\cimv2\Security\MicrosoftVolumeEncryption -ClassName Win32_EncryptableVolume -Filter "DriveLetter='$env:SystemDrive'" -EA Stop
  if($ev){
    $cs=$ev.ConversionStatus
    if($null -eq $cs){ $cs=(Invoke-CimMethod -InputObject $ev -MethodName GetConversionStatus -EA SilentlyContinue).ConversionStatus }
    $bl=@{ known=$true; src='wmi'; protection=[int]$ev.ProtectionStatus; conversion=$(if($null -eq $cs){-1}else{[int]$cs}) }
  }
} catch {}
if(-not $bl.known){
  try {
    $p=(New-Object -ComObject Shell.Application).NameSpace($env:SystemDrive + '\').Self.ExtendedProperty('System.Volume.BitLockerProtection')
    if($p -eq 1){ $bl=@{ known=$true; src='shell'; protection=1; conversion=1 } }
    elseif($p -eq 2){ $bl=@{ known=$true; src='shell'; protection=0; conversion=0 } }
  } catch {}
}
"""
_BUNDLE_PS += _BITLOCKER_PS + "$d.bitlocker=$bl\n$d | ConvertTo-Json -Compress\n"


@dataclass
class HealthItem:
    key:      str
    label:    str
    count:    int
    last:     str          # "" if none
    severity: str          # ok | warn | critical
    note:     str


@dataclass
class StatusLine:
    """A state worth knowing, not an event count (e.g. memory integrity on/off)."""
    key:      str
    label:    str
    value:    str
    severity: str
    note:     str


@dataclass
class HealthReport:
    ok:    bool = False
    items: list = None
    error: str = ""
    summary: str = ""
    status: list = None


def _hvci_line(data) -> Optional[StatusLine]:
    """Memory integrity (HVCI). Windows updates from November 2026 (KB5127936) may switch it on
    on supported PCs — a state the user should see after an update, not something this app changes."""
    h = (data or {}).get("hvci") or {}
    if not h.get("known"):
        return None
    label = _tr("Speicherintegrität (Kernisolierung)", "Memory integrity (core isolation)")
    if h.get("running"):
        return StatusLine("hvci", label, _tr("an", "on"), OK, _tr(
            "Sicherheitsfunktion von Windows; kann in manchen Spielen ein paar Prozent Leistung kosten. "
            "Kann MSI Afterburner danach Takt oder Spannung nicht mehr setzen: aktuelle Afterburner-Version installieren.",
            "A Windows security feature; can cost a few percent of performance in some games. If MSI Afterburner "
            "can no longer set clocks or voltage afterwards: install the current Afterburner version."))
    return StatusLine("hvci", label, _tr("aus", "off"), OK, _tr(
        "Windows-Updates ab November 2026 (KB5127936) können sie auf unterstützten PCs einschalten — "
        "dieser Report zeigt es dann an.",
        "Windows updates from November 2026 (KB5127936) may switch it on on supported PCs — this report "
        "shows it then."))


RECOVERY_KEY_URL = "aka.ms/myrecoverykey"


def _bitlocker_line(data) -> Optional[StatusLine]:
    """BitLocker / device encryption of C:. Windows 11 24H2+ switches device encryption on by itself on
    many fresh installs; with it on, a BIOS update or changing fTPM / Secure Boot makes Windows ask for
    the recovery key at the next start — worth knowing BEFORE using the BIOS guide. Shown only, never
    changed (a security feature)."""
    b = (data or {}).get("bitlocker") or {}
    if not b.get("known"):
        return None
    label = _tr("Laufwerksverschlüsselung (BitLocker) auf C:", "Drive encryption (BitLocker) on C:")
    prot, conv = b.get("protection"), b.get("conversion")
    if prot == 1:
        return StatusLine("bitlocker", label, _tr("an", "on"), WARN, _tr(
            f"Vor BIOS-Änderungen, einem BIOS-Update oder dem Umstellen von fTPM/Secure Boot den "
            f"Wiederherstellungsschlüssel sichern ({RECOVERY_KEY_URL}) — sonst fragt Windows beim nächsten Start "
            f"danach. Software-Verschlüsselung kann auf manchen SSDs etwas Schreibleistung kosten.",
            f"Before changing BIOS settings, updating the BIOS or switching fTPM / Secure Boot, save the recovery "
            f"key ({RECOVERY_KEY_URL}) — otherwise Windows asks for it at the next start. Software encryption can "
            f"cost some write speed on some SSDs."))
    if prot == 0 and conv in (1, 2, 4):
        return StatusLine("bitlocker", label, _tr("verschlüsselt, Schutz noch nicht aktiv",
                                                  "encrypted, protection not active yet"), OK, _tr(
            "C: ist verschlüsselt, der Schutz greift aber noch nicht (wartet auf Aktivierung oder ist "
            "pausiert). Er schaltet sich ein, sobald Windows den Schlüssel sichert — z. B. bei der Anmeldung mit "
            "einem Microsoft-Konto. Ab dann vor BIOS-Änderungen den Wiederherstellungsschlüssel sichern.",
            "C: is encrypted, but the protection is not active yet (waiting for activation or paused). It switches "
            "on once Windows saves the key — e.g. when you sign in with a Microsoft account. From then on save the "
            "recovery key before changing BIOS settings."))
    if conv == 3:
        return StatusLine("bitlocker", label, _tr("wird entschlüsselt", "decrypting"), OK, _tr(
            "Windows entschlüsselt C: gerade — danach ist die Verschlüsselung aus.",
            "Windows is decrypting C: right now — encryption is off afterwards."))
    if prot == 0 and conv == 0:
        return StatusLine("bitlocker", label, _tr("aus", "off"), OK, _tr(
            "Keine Verschlüsselung auf C:. Neuinstallationen ab Windows 11 24H2 schalten die Geräteverschlüsselung "
            "oft selbst ein — dieser Report zeigt es dann an.",
            "No encryption on C:. Fresh installs of Windows 11 24H2 and later often switch device encryption on by "
            "themselves — this report shows it then."))
    return None


def _run_json(script: str, timeout: int = 45) -> Optional[dict]:
    if os.name != "nt":
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags,
        )
        out = (r.stdout or "").strip()
        if not out:
            return None
        return json.loads(out)
    except Exception:
        return None


def _gather() -> Optional[dict]:
    return _run_json(_BUNDLE_PS)


def bitlocker_state() -> Optional[dict]:
    """Only the BitLocker part (the BIOS guide asks before BIOS changes): {"known", "protection", ...}."""
    return _run_json(_BITLOCKER_PS + "$bl | ConvertTo-Json -Compress\n", timeout=20)


def bitlocker_protected(state) -> bool:
    """BitLocker protects C: (a BIOS / TPM change then asks for the recovery key)."""
    return bool(state and state.get("known") and state.get("protection") == 1)


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
        rep.error = _tr("Health Report nur unter Windows verfügbar.", "Health report is only available on Windows.")
        return rep

    data = _gather()
    if data is None:
        rep.error = (_tr("Ereignisprotokoll konnte nicht gelesen werden "
                     "(PowerShell/Rechte?).", "The event log could not be read (PowerShell / rights?)."))
        return rep

    items = [
        _mk("whea", _tr("WHEA-Hardwarefehler", "WHEA hardware errors"), data, 1, 5,
            _tr("Keine Hardwarefehler protokolliert.", "No hardware errors logged."),
            _tr("Hardwarefehler (RAM/CPU/PCIe) — prüfe RAM (MemTest) & Temperaturen.", "Hardware errors (RAM/CPU/PCIe) — check the RAM (MemTest) and temperatures.")),
        _mk("bugcheck", "Bluescreens (Bugchecks)", data, 1, 3,
            _tr("Keine Bluescreens in 30 Tagen.", "No bluescreens in 30 days."),
            _tr("Bluescreens aufgetreten — Treiber/RAM/OC prüfen.", "Bluescreens occurred — check drivers / RAM / OC.")),
        _mk("kpower41", "Unerwartete Neustarts", data, 1, 3,
            _tr("Keine unerwarteten Neustarts.", "No unexpected restarts."),
            _tr("Unerwartete Neustarts (Kernel-Power 41) — Netzteil/OC/Temperatur.", "Unexpected restarts (Kernel-Power 41) — power supply / OC / temperature.")),
        _mk("tdr", _tr("GPU-Treiber-Timeouts (TDR)", "GPU driver timeouts (TDR)"), data, 1, 4,
            _tr("Keine GPU-Treiber-Timeouts.", "No GPU driver timeouts."),
            _tr("GPU-Timeouts (TDR) — GPU-OC zurücknehmen / Treiber neu.", "GPU timeouts (TDR) — take the GPU OC back / reinstall the driver.")),
        _mk("disk", _tr("Datenträgerfehler", "Disk errors"), data, 1, 3,
            _tr("Keine Datenträgerfehler.", "No disk errors."),
            _tr("Datenträgerfehler — SMART/Kabel prüfen, Backup machen.", "Disk errors — check SMART / cables, make a backup.")),
        _mk("appcrash", _tr("App-Abstürze", "App crashes"), data, 5, 25,
            _tr("Kaum/keine App-Abstürze.", "Few or no app crashes."),
            _tr("Häufige App-Abstürze — meist unkritisch, aber auffällig.", "Frequent app crashes — usually harmless, but notable.")),
    ]
    rep.items = items
    rep.status = [s for s in (_hvci_line(data), _bitlocker_line(data)) if s]

    crit = sum(1 for i in items if i.severity == CRITICAL)
    warn = sum(1 for i in items if i.severity == WARN)
    if crit:
        rep.summary = _tr(f"⚠ {crit} kritische Auffälligkeit(en), {warn} Warnung(en) — bitte prüfen.", f"⚠ {crit} critical finding(s), {warn} warning(s) — please check.")
    elif warn:
        rep.summary = _tr(f"{warn} Warnung(en) in den letzten 30 Tagen.", f"{warn} warning(s) in the last 30 days.")
    else:
        rep.summary = _tr("✓ Keine relevanten Fehler in den letzten 30 Tagen — System stabil.", "✓ No relevant errors in the last 30 days — the system is stable.")
    rep.ok = True
    return rep


if __name__ == "__main__":
    r = generate()
    print("ok:", r.ok, "| error:", r.error)
    print("summary:", r.summary)
    for it in (r.items or []):
        print(f"  [{it.severity:8}] {it.label}: count={it.count} last={it.last!r}")
    for s in (r.status or []):
        print(f"  [{s.severity:8}] {s.label}: {s.value} — {s.note}")
