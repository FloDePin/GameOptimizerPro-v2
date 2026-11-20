"""
GameOptimizerPro — System Restore Point creator.
Erstellt einen Windows-Wiederherstellungspunkt als Sicherheitsnetz, bevor
man Tweaks anwendet. Benötigt Admin-Rechte und aktivierten Computerschutz
auf dem Systemlaufwerk. Rein additiv — löscht/ändert nichts.

Round 47 (found in v1's review):
  * Windows makes at most one point per 24 hours and then only WARNS — that warning was reported as
    "created". The documented SystemRestorePointCreationFrequency value is set to 0 for this one call
    (and put back right after), so the point really is made now.
  * create_ex() says WHY there is no point ("off" = System Protection is off, "denied", "error"):
    app removals ask before they go on without one.
"""

import os
import re
import subprocess

from core.i18n import tr as _tr

_SR_KEY = r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore"


def _clean_desc(desc: str) -> str:
    # Nur harmlose Zeichen zulassen (verhindert PS-Quoting-Probleme)
    d = re.sub(r"[^A-Za-z0-9 _.\-]", "", desc or "").strip()
    return d[:60] or "GameOptimizerPro"


def _script(desc: str) -> str:
    return (
        f"$k='{_SR_KEY}'; $old=$null; $had=$false; "
        "try { $old=(Get-ItemProperty $k -Name SystemRestorePointCreationFrequency -EA Stop).SystemRestorePointCreationFrequency; "
        "$had=$true } catch {}; "
        "try { Set-ItemProperty $k -Name SystemRestorePointCreationFrequency -Value 0 -Type DWord -EA Stop } catch {}; "
        "try { "
        f"Checkpoint-Computer -Description '{desc}' -RestorePointType 'MODIFY_SETTINGS' -EA Stop "
        "-WarningVariable w -WarningAction SilentlyContinue; "
        "if($w){ Write-Output ('WARN:' + ($w -join ' ')) } else { Write-Output 'OK' } "
        "} catch { Write-Output ('ERR:' + $_.Exception.Message) } "
        "finally { try { if($had){ Set-ItemProperty $k -Name SystemRestorePointCreationFrequency -Value $old -Type DWord } "
        "else { Remove-ItemProperty $k -Name SystemRestorePointCreationFrequency -EA SilentlyContinue } } catch {} }"
    )


def classify(out: str, returncode: int = 0) -> tuple[bool, str, str]:
    """(ok, message, reason) from the script's output — reason: ok | skipped | off | denied | error."""
    low = (out or "").lower()
    if out and "OK" in out and "ERR:" not in out and "WARN:" not in out and returncode == 0:
        return True, _tr("✓ Wiederherstellungspunkt erstellt.", "✓ Restore point created."), "ok"
    if "WARN:" in out and ("1440" in out or "frequency" in low or "24" in out):
        return False, _tr("Windows hat keinen neuen Punkt angelegt — es gibt schon einen aus den letzten 24 Stunden.",
                          "Windows made no new point — there is one from the last 24 hours already."), "skipped"
    if ("disabled" in low or "deaktiviert" in low or "turned off" in low or "ausgeschaltet" in low
            or "system restore" in low or "systemwiederherstellung" in low or "0x80042306" in low):
        return False, _tr("Computerschutz ist auf dem Systemlaufwerk aus. Einschalten: Systemsteuerung → System → "
                          "Computerschutz → Laufwerk C: → Konfigurieren → Schutz aktivieren.",
                          "System protection is off on the system drive. Turn it on: Control Panel → System → "
                          "System protection → drive C: → Configure → Turn on system protection."), "off"
    if "access" in low or "denied" in low or "verweigert" in low or "0x80070005" in out:
        return False, _tr("Zugriff verweigert — GameOptimizerPro muss als Administrator laufen.",
                          "Access denied — GameOptimizerPro has to run as administrator."), "denied"
    return False, _tr(f"Fehlgeschlagen: {(out or '')[:200] or 'unbekannter Fehler'}",
                      f"Failed: {(out or '')[:200] or 'unknown error'}"), "error"


def create_ex(description: str = "GameOptimizerPro Tweaks") -> tuple[bool, str, str]:
    """Erstellt einen Wiederherstellungspunkt. (erfolg, meldung, grund) — grund siehe classify()."""
    if os.name != "nt":
        return False, _tr("Nur unter Windows verfügbar.", "Only available on Windows."), "error"
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", _script(_clean_desc(description))],
            capture_output=True, text=True, encoding="oem", errors="replace", timeout=180,
            stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return classify(((r.stdout or "") + (r.stderr or "")).strip(), r.returncode)
    except subprocess.TimeoutExpired:
        return False, _tr("Timeout (über 180s) — Systemwiederherstellung reagiert nicht.",
                          "Timeout (over 180 s) — System Restore does not respond."), "error"
    except Exception as e:
        return False, str(e), "error"


def create(description: str = "GameOptimizerPro Tweaks") -> tuple[bool, str]:
    """Erstellt einen Wiederherstellungspunkt. Gibt (erfolg, meldung) zurück."""
    ok, msg, _why = create_ex(description)
    return ok, msg


def ask_text(msg: str) -> str:
    """The question before apps are removed without a restore point."""
    return _tr(f"Kein Wiederherstellungspunkt: {msg}\n\nOhne ihn bringt nur der Microsoft Store eine entfernte "
               "App zurück. Trotzdem entfernen?",
               f"No restore point: {msg}\n\nWithout one only the Microsoft Store brings a removed app back. "
               "Remove anyway?")
