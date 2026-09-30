"""
GameOptimizerPro v2.0 — Services Manager (Logik)
Portiert aus v1: eine feste Liste von Windows-Diensten, die ein Gaming-PC meist
nicht braucht — mit Beschreibung, Kategorie und Sicherheits-Einstufung.

Unterschiede zu v1 (bewusst):
  - "Aktivieren" stellt den URSPRÜNGLICHEN Starttyp wieder her (wird vor dem
    Deaktivieren gemerkt, inkl. "Automatisch (verzögert)"). Ohne gemerkten Wert
    gilt der Windows-Standard. v1 setzte pauschal "Manuell" — die
    Druckwarteschlange startete danach z. B. nicht mehr von selbst.
  - Xbox-Dienste gelten als "Vorsicht": Game-Pass-/Xbox-PC-Spiele brauchen sie
    für Anmeldung und Cloud-Spielstände (v1: "unnötig ohne Xbox").
  - "Touch Keyboard & Handwriting" (TabletInputService) fehlt: den Dienst gibt es
    seit Windows 11 24H2 nicht mehr, sein Nachfolger (Texteingabeverwaltung)
    darf NICHT aus — sonst geht die Eingabe in Suche und Apps kaputt.
  - Neu (Windows 11 24H2/26H2): der KI-Host WSAIFabricSvc.
Dienste, die es auf dem System nicht gibt, werden einfach nicht angezeigt.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent.parent / "logs" / "services_state.json"

# name -> (Kategorie, sicher deaktivierbar, Beschreibung)
KNOWN_SERVICES: dict[str, tuple[str, bool, str]] = {
    "DiagTrack":        ("Datenschutz", True,  "Telemetrie & Diagnose — sendet Nutzungsdaten an Microsoft."),
    "dmwappushservice": ("Datenschutz", True,  "WAP-Push-Routing — Teil der Telemetrie-/Geräteverwaltungs-Infrastruktur."),
    "WerSvc":           ("Datenschutz", True,  "Windows-Fehlerberichterstattung — sendet Absturzberichte an Microsoft."),
    "lfsvc":            ("Datenschutz", True,  "Geolocation — Standortabfragen von Apps. Automatische Zeitzone und "
                                               "'Mein Gerät suchen' brauchen ihn."),
    "SysMain":          ("Leistung",    True,  "SysMain (Superfetch) — lädt Apps vorab in den RAM. Auf SSDs kaum Nutzen."),
    "WSearch":          ("Leistung",    True,  "Windows Search — indiziert Laufwerke. Aus: Suche in Start/Explorer wird "
                                               "langsamer, Outlook-Suche eingeschränkt."),
    "CscService":       ("Leistung",    True,  "Offlinedateien — Offline-Kopien von Netzwerkordnern. Meist unnötig."),
    "TrkWks":           ("Leistung",    True,  "Überwachung verteilter Verknüpfungen — verfolgt verschobene Dateien für "
                                               "Verknüpfungen."),
    "RemoteRegistry":   ("Sicherheit",  True,  "Remoteregistrierung — Registry-Zugriff übers Netzwerk. Sicherheitsrisiko, "
                                               "unter Windows 11 ohnehin standardmäßig aus."),
    "SharedAccess":     ("Netzwerk",    True,  "Internetverbindungsfreigabe (ICS) — nur für ICS/Hotspot und das NAT des "
                                               "Hyper-V-'Default Switch'."),
    "icssvc":           ("Netzwerk",    True,  "Mobiler Hotspot — nur wenn der PC einen WLAN-Hotspot aufspannt."),
    "XblAuthManager":   ("Xbox",        False, "Xbox Live-Authentifizierung — Game-Pass-/Xbox-PC-Spiele brauchen ihn "
                                               "für die Anmeldung."),
    "XblGameSave":      ("Xbox",        False, "Xbox Live-Spielstände — Cloud-Saves von Xbox-/Game-Pass-PC-Spielen."),
    "XboxNetApiSvc":    ("Xbox",        False, "Xbox Live-Netzwerk — Mehrspieler/Party von Xbox-/Game-Pass-PC-Spielen."),
    "xbgm":             ("Xbox",        True,  "Xbox Game Monitoring (ältere Windows-Versionen)."),
    "Fax":              ("Unnötig",     True,  "Faxdienst — nutzt fast niemand."),
    "MapsBroker":       ("Unnötig",     True,  "Manager für heruntergeladene Karten — nur für die Karten-App."),
    "RetailDemo":       ("Unnötig",     True,  "Einzelhandelsdemo — nur für Vorführgeräte im Laden."),
    "WMPNetworkSvc":    ("Unnötig",     True,  "Windows Media Player-Netzwerkfreigabe — Medien im Netzwerk teilen."),
    "PhoneSvc":         ("Unnötig",     True,  "Telefondienst — Telefonie, z. B. Anrufe über Smartphone-Link."),
    "wisvc":            ("Unnötig",     True,  "Windows-Insider-Dienst — nur für Insider-Builds."),
    "WpcMonSvc":        ("Unnötig",     True,  "Jugendschutz — Microsoft-Family-Überwachung."),
    "WdiServiceHost":   ("Unnötig",     True,  "Diagnosediensthost — Windows-Problembehandlung/Diagnose."),
    "vmicvss":          ("Unnötig",     True,  "Hyper-V-Volumeschattenkopie — nur INNERHALB einer Hyper-V-VM."),
    "HvHost":           ("Unnötig",     True,  "HV-Hostdienst — Leistungsindikatoren für Hyper-V. Ohne VMs unnötig."),
    "WSAIFabricSvc":    ("KI",          True,  "Host für Windows-KI-Komponenten (seit 24H2/26H2, startet automatisch) — "
                                               "KI-Suche in Einstellungen, Click to Do, KI-Aktionen."),
    "Spooler":          ("System",      False, "Druckwarteschlange — ohne sie kann NICHT gedruckt werden (auch nicht als PDF)."),
    "BITS":             ("System",      False, "Intelligenter Hintergrundübertragungsdienst — Download-Dienst von "
                                               "Windows Update, Store und Defender."),
    "wuauserv":         ("System",      False, "Windows Update — aus = KEINE Sicherheitsupdates mehr."),
}

# Windows-11-Standard-Starttyp (Start, verzögert) — Rückfall für "Aktivieren",
# wenn kein Original gemerkt ist (z. B. mit v1 deaktiviert).
WINDOWS_DEFAULT: dict[str, tuple[int, bool]] = {
    "DiagTrack": (2, False), "dmwappushservice": (3, False), "WerSvc": (3, False),
    "lfsvc": (3, False), "SysMain": (2, False), "WSearch": (2, True),
    "CscService": (3, False), "TrkWks": (2, False), "RemoteRegistry": (3, False),
    "SharedAccess": (3, False), "icssvc": (3, False), "XblAuthManager": (3, False),
    "XblGameSave": (3, False), "XboxNetApiSvc": (3, False), "xbgm": (3, False),
    "Fax": (3, False), "MapsBroker": (2, True), "RetailDemo": (3, False),
    "WMPNetworkSvc": (3, False), "PhoneSvc": (3, False), "wisvc": (3, False),
    "WpcMonSvc": (3, False), "WdiServiceHost": (3, False), "vmicvss": (3, False),
    "HvHost": (3, False), "WSAIFabricSvc": (2, False), "Spooler": (2, False),
    "BITS": (2, True), "wuauserv": (3, False),
}

START_LABEL = {0: "Boot", 1: "System", 2: "Automatisch", 3: "Manuell", 4: "Deaktiviert"}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


def start_label(start: int, delayed: bool = False) -> str:
    if start == 2 and delayed:
        return "Automatisch (verzögert)"
    return START_LABEL.get(start, "Unbekannt")


@dataclass
class ServiceInfo:
    name:     str
    display:  str
    category: str
    safe:     bool
    desc:     str
    status:   str          # "Läuft" / "Beendet" / …
    running:  bool
    start:    int          # registry 'Start' (2 auto, 3 manuell, 4 deaktiviert), -1 = unbekannt
    delayed:  bool
    saved:    dict | None  # gemerkter Original-Starttyp (vor dem Deaktivieren)

    @property
    def disabled(self) -> bool:
        return self.start == 4

    @property
    def start_text(self) -> str:
        return start_label(self.start, self.delayed)

    def restore_target(self) -> tuple[int, bool, str]:
        """(start, delayed, Herkunft) für "Aktivieren"."""
        return restore_target(self.name, self.saved)


def restore_target(name: str, saved: dict | None) -> tuple[int, bool, str]:
    if saved and saved.get("start") in (2, 3):
        return int(saved["start"]), bool(saved.get("delayed")), "gemerkt"
    start, delayed = WINDOWS_DEFAULT.get(name, (3, False))
    if start not in (2, 3):              # Standard "Deaktiviert" -> Aktivieren = Manuell
        start, delayed = 3, False
    return start, delayed, "Windows-Standard"


# ── Lesen ─────────────────────────────────────────────────────────────────────

def _read_start(name: str) -> tuple[int, bool] | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            rf"SYSTEM\CurrentControlSet\Services\{name}") as k:
            start = int(winreg.QueryValueEx(k, "Start")[0])
            try:
                delayed = int(winreg.QueryValueEx(k, "DelayedAutostart")[0]) == 1
            except OSError:
                delayed = False
            return start, delayed and start == 2
    except (OSError, ValueError, ImportError):
        return None


_STATUS_DE = {"running": "Läuft", "stopped": "Beendet", "start_pending": "Startet …",
              "stop_pending": "Stoppt …", "paused": "Angehalten",
              "continue_pending": "Setzt fort …", "pause_pending": "Hält an …"}


def _query(name: str) -> tuple[str, str] | None:
    """(Anzeigename, Status) — None, wenn es den Dienst nicht gibt."""
    try:
        import psutil
        d = psutil.win_service_get(name).as_dict()
        return d.get("display_name") or name, d.get("status") or "unknown"
    except ImportError:
        pass
    except Exception:
        return None
    try:                                  # Rückfall ohne psutil
        r = subprocess.run(["sc.exe", "query", name], capture_output=True, text=True,
                           timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            return None
        m = re.search(r"STATE\s*:\s*\d+\s+(\w+)", r.stdout or "")
        return name, (m.group(1).lower() if m else "unknown")
    except Exception:
        return None


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def list_services() -> list[ServiceInfo]:
    state = load_state()
    out = []
    for name, (cat, safe, desc) in KNOWN_SERVICES.items():
        q = _query(name)
        if q is None:
            continue
        display, status = q
        st = _read_start(name) or (-1, False)
        out.append(ServiceInfo(
            name=name, display=display, category=cat, safe=safe, desc=desc,
            status=_STATUS_DE.get(status, status), running=(status == "running"),
            start=st[0], delayed=st[1], saved=state.get(name)))
    return out


# ── Ändern (Admin) ────────────────────────────────────────────────────────────

def _run_ps(script: str, timeout: int = 120) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-ExecutionPolicy", "Bypass", "-Command", script],
                       # PowerShell 5.1 writes redirected output in the OEM code page
                       # (German sc.exe messages have umlauts).
                       capture_output=True, text=True,
                       encoding="oem" if os.name == "nt" else "utf-8", errors="replace",
                       timeout=timeout, creationflags=flags)
    return (r.stdout or "") + (r.stderr or "")


def _parse(out: str, names: list[str]) -> dict[str, tuple[bool, str]]:
    res = {n: (False, "keine Rückmeldung") for n in names}
    for line in out.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) >= 2 and parts[0] in res:
            ok = parts[1] == "OK"
            res[parts[0]] = (ok, parts[2].strip() if len(parts) > 2 else "")
    return res


def _check_names(names) -> list[str]:
    names = [n for n in dict.fromkeys(names) if n in KNOWN_SERVICES]
    for n in names:
        if not _SAFE_NAME.match(n):
            raise ValueError(f"ungültiger Dienstname: {n!r}")
    return names


def disable(names) -> dict[str, tuple[bool, str]]:
    """Merkt den Original-Starttyp, setzt 'Deaktiviert' und stoppt den Dienst
    (samt abhängiger Dienste, wie v1). -> {name: (ok, hinweis)}"""
    names = _check_names(names)
    if not names:
        return {}
    state = load_state()
    fresh = []
    for n in names:
        cur = _read_start(n)
        if cur and cur[0] in (2, 3) and n not in state:
            state[n] = {"start": cur[0], "delayed": cur[1],
                        "at": datetime.now().isoformat(timespec="seconds")}
            fresh.append(n)
    _save_state(state)

    arr = ",".join(f"'{n}'" for n in names)
    script = (
        f"foreach($n in @({arr})){{ try {{ "
        f"$o = & sc.exe config $n start= disabled 2>&1; "
        f"if($LASTEXITCODE -ne 0){{ throw (($o | Out-String).Trim()) }}; "
        f"Stop-Service -Name $n -Force -ErrorAction SilentlyContinue; "
        f"$s = (Get-Service -Name $n -ErrorAction SilentlyContinue).Status; "
        f"if(\"$s\" -eq 'Running'){{ \"$n|OK|reboot\" }} else {{ \"$n|OK|\" }} "
        f"}} catch {{ \"$n|ERR|$($_.Exception.Message -replace '[\\r\\n]+',' ')\" }} }}"
    )
    try:
        res = _parse(_run_ps(script), names)
    except Exception as e:
        res = {n: (False, str(e)) for n in names}
    res = {n: (ok, "läuft noch bis zum Neustart" if note == "reboot" else note)
           for n, (ok, note) in res.items()}
    failed = [n for n in fresh if not res[n][0]]
    if failed:                            # nichts geändert -> nichts zu merken
        for n in failed:
            state.pop(n, None)
        _save_state(state)
    return res


def enable(names) -> dict[str, tuple[bool, str]]:
    """Stellt den gemerkten Original-Starttyp wieder her (sonst den
    Windows-Standard) und startet automatisch startende Dienste gleich mit."""
    names = _check_names(names)
    if not names:
        return {}
    state = load_state()
    parts, targets = [], {}
    for n in names:
        start, delayed, origin = restore_target(n, state.get(n))
        mode = "delayed-auto" if (start == 2 and delayed) else ("auto" if start == 2 else "demand")
        targets[n] = (start, delayed, origin)
        parts.append(f"@('{n}','{mode}')")
    script = (
        f"foreach($p in @({','.join(parts)})){{ $n=$p[0]; $m=$p[1]; try {{ "
        f"$o = & sc.exe config $n start= $m 2>&1; "
        f"if($LASTEXITCODE -ne 0){{ throw (($o | Out-String).Trim()) }}; "
        f"if($m -ne 'demand'){{ Start-Service -Name $n -ErrorAction SilentlyContinue }}; "
        f"\"$n|OK|\" }} catch {{ \"$n|ERR|$($_.Exception.Message -replace '[\\r\\n]+',' ')\" }} }}"
    )
    try:
        res = _parse(_run_ps(script), names)
    except Exception as e:
        res = {n: (False, str(e)) for n in names}
    changed = False
    for n in names:
        ok, note = res[n]
        if ok:
            start, delayed, origin = targets[n]
            res[n] = (True, f"{start_label(start, delayed)} ({origin})")
            if n in state:
                state.pop(n)
                changed = True
    if changed:
        _save_state(state)
    return res


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
