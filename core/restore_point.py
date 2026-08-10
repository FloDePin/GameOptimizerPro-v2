"""
GameOptimizerPro — System Restore Point creator.
Erstellt einen Windows-Wiederherstellungspunkt als Sicherheitsnetz, bevor
man Tweaks anwendet. Benötigt Admin-Rechte und aktivierten Computerschutz
auf dem Systemlaufwerk. Rein additiv — löscht/ändert nichts.
"""

import subprocess, os, re


def _clean_desc(desc: str) -> str:
    # Nur harmlose Zeichen zulassen (verhindert PS-Quoting-Probleme)
    d = re.sub(r"[^A-Za-z0-9 _.\-]", "", desc or "").strip()
    return d[:60] or "GameOptimizerPro"


def create(description: str = "GameOptimizerPro Tweaks") -> tuple[bool, str]:
    """Erstellt einen Wiederherstellungspunkt. Gibt (erfolg, meldung) zurück."""
    if os.name != "nt":
        return False, "Nur unter Windows verfügbar."
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
            capture_output=True, text=True, encoding="latin-1", timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        low = out.lower()
        if "OK" in out and "ERR:" not in out and r.returncode == 0:
            return True, "✓ Wiederherstellungspunkt erstellt."
        # Häufige Fälle klar benennen
        if "1440" in out or "frequency" in low or "429" in out:
            return False, ("Windows hat den Punkt übersprungen — es gibt bereits einen aus den "
                           "letzten 24 Stunden (Standard-Limit von Windows).")
        if ("disabled" in low or "deaktiviert" in low or "turned off" in low
                or "system restore" in low or "systemwiederherstellung" in low):
            return False, ("Computerschutz ist auf dem Systemlaufwerk deaktiviert. Aktiviere ihn: "
                           "Systemsteuerung → System → Computerschutz → Laufwerk C: → Konfigurieren → "
                           "Schutz aktivieren.")
        if "access" in low or "denied" in low or "verweigert" in low or "0x80070005" in out:
            return False, "Zugriff verweigert — GameOptimizerPro muss als Administrator laufen."
        return False, f"Fehlgeschlagen: {out[:200] or 'unbekannter Fehler'}"
    except subprocess.TimeoutExpired:
        return False, "Timeout (über 180s) — Systemwiederherstellung reagiert nicht."
    except Exception as e:
        return False, str(e)
