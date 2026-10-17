"""
GameOptimizerPro — System Restore Point creator.
Erstellt einen Windows-Wiederherstellungspunkt als Sicherheitsnetz, bevor
man Tweaks anwendet. Benötigt Admin-Rechte und aktivierten Computerschutz
auf dem Systemlaufwerk. Rein additiv — löscht/ändert nichts.
"""

import subprocess, os, re
from core.i18n import tr as _tr


def _clean_desc(desc: str) -> str:
    # Nur harmlose Zeichen zulassen (verhindert PS-Quoting-Probleme)
    d = re.sub(r"[^A-Za-z0-9 _.\-]", "", desc or "").strip()
    return d[:60] or "GameOptimizerPro"


def create(description: str = "GameOptimizerPro Tweaks") -> tuple[bool, str]:
    """Erstellt einen Wiederherstellungspunkt. Gibt (erfolg, meldung) zurück."""
    if os.name != "nt":
        return False, _tr("Nur unter Windows verfügbar.", "Only available on Windows.")
    desc = _clean_desc(description)
    ps = (
        "$ErrorActionPreference='Stop'; "
        "try { "
        f"Checkpoint-Computer -Description '{desc}' -RestorePointType 'MODIFY_SETTINGS'; "
        "Write-Output 'OK' "
        "} catch { Write-Output ('ERR:' + $_.Exception.Message) }"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        low = out.lower()
        if "OK" in out and "ERR:" not in out and r.returncode == 0:
            return True, "✓ Wiederherstellungspunkt erstellt."
        # Häufige Fälle klar benennen
        if "1440" in out or "frequency" in low or "429" in out:
            return False, (_tr("Windows hat den Punkt übersprungen — es gibt bereits einen aus den "
                           "letzten 24 Stunden (Standard-Limit von Windows).", "Windows skipped the point — there is already one from the last 24 hours (Windows' default limit)."))
        if ("disabled" in low or "deaktiviert" in low or "turned off" in low
                or "system restore" in low or "systemwiederherstellung" in low):
            return False, (_tr("Computerschutz ist auf dem Systemlaufwerk deaktiviert. Aktiviere ihn: "
                           "Systemsteuerung → System → Computerschutz → Laufwerk C: → Konfigurieren → "
                           "Schutz aktivieren.", "System protection is off on the system drive. Turn it on: Control Panel → System → System protection → drive C: → Configure → Turn on system protection."))
        if "access" in low or "denied" in low or "verweigert" in low or "0x80070005" in out:
            return False, "Zugriff verweigert — GameOptimizerPro muss als Administrator laufen."
        return False, _tr(f"Fehlgeschlagen: {out[:200] or 'unbekannter Fehler'}", f"Failed: {out[:200] or 'unknown error'}")
    except subprocess.TimeoutExpired:
        return False, _tr("Timeout (über 180s) — Systemwiederherstellung reagiert nicht.", "Timeout (over 180 s) — System Restore does not respond.")
    except Exception as e:
        return False, str(e)
