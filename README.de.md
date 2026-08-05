<div align="center">

# ⚡ GameOptimizerPro v2.2

**Windows & Gaming Optimizer v2.2 von FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.2-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 [English](README.md) | 🇩🇪 **Deutsch**

*All-in-one PC-Optimierungstool — GPU Auto-Tuner, Audio-Optimierung, Windows-Tweaks, BIOS-Guide, Per-Game-Profile und mehr.*

</div>

---

## 🆕 Neu in v2.2

**Neue Features**
- **Netzwerk-Latenz-Test** (Dashboard) — Ein-Klick-Ping zu Gateway + Cloudflare (1.1.1.1) & Google (8.8.8.8) mit Ø/min/max-Latenz, Jitter und Paketverlust
- **Live-Systemüberwachung** — CPU-, RAM- und Disk-Auslastung als Tiles neben der GPU-Telemetrie
- **System Cleaner** (Einstellungen) — leert sicher nur Temp-/Dump-Ordner; fasst nie Dokumente, Browser oder den Papierkorb an
- **iGPU-Abschalt-Tipp** für AM5 (Zen 4/5) im BIOS-Guide — ehrlich mit echten Vor-/Nachteilen, nicht die Hype-Version
- **2 neue Power-Tweaks** — PCIe Link State Power Management aus, Festplatte nie schlafen
- Größeres Startfenster, damit das komplette Dashboard sofort sichtbar ist

**Fixes**
- **Verifier-Engine repariert** — ein PowerShell-Gruppierungsbug (`(...)` statt `$(...)`) ließ die meisten Registry-Statuschecks still auf Amber „ungeprüft" stehen; die grünen/amber/grauen Punkte lesen jetzt für alle 65 Tweaks den echten Zustand
- Ping-Test crasht nicht mehr bei nicht-englischer `ping`-Ausgabe (latin-1-Dekodierung)

**Seit v2.1.1:** Launcher-Fenster-Fix, Registry-Backslash-Fix, vollständige Audio-Tweak-Verifizierung & Revert, 4 Gaming-Tweaks, deutsche README + CI.

---

## ✨ Features

### 🎮 GPU Auto-Tuner
- **3 Tune-Modi:** Nur Overclock, Nur Undervolt, OC + UV (empfohlen)
- Automatisierter, schrittweiser Stabilitätstest mit Stress-Worker
- TDR-Erkennung (GPU-Treiber-Timeout) über das Windows-Ereignisprotokoll
- Crash Recovery — stellt beim nächsten Systemstart automatisch das letzte stabile Profil wieder her
- Live-Diagramm für Spannung/Takt/Temperatur während des Tunings
- Integration mit **MSI Afterburner** (MAHM Shared Memory für echte mV-Werte)
- Automatische GPU-Generationserkennung (Pascal → Ada Lovelace, RDNA 1–3)

### 🔊 Audio-Optimierung
- **Low-Latency-Audio-Tweaks** für Gaming — Audio-Verbesserungen deaktivieren, exklusive Audio-Sperre aufheben
- **System-Sound-Optimierung** — Nahimic-Dienst deaktivieren, Windows-Soundschema deaktivieren
- **Audio-CPU-Priorität** — MMCSS Pro-Audio-Priorität maximieren für verzerrungsfreies Audio unter Last
- **Audio-Ducking-Kontrolle** — verhindert, dass Discord/Musik von Spielen stummgeschaltet wird
- **Entfernung der Windows-Audioverbesserungen** — reduziert Audio-Latenz und CPU-Last
- Alle Audio-Tweaks sind direkt in den **Windows Optimizer** integriert, per Klick an/aus

### 📊 Live-Dashboard
- Echtzeit-**GPU-Telemetrie** (Spannung, Temp, Takte, Power, Last) + Balkenanzeigen
- **CPU- / RAM- / Disk-Auslastung** als Tiles neben den GPU-Werten (via psutil)
- **Netzwerk-Latenz-Test** — Ein-Klick-Ping zu Gateway + Cloudflare & Google mit Ø/min/max-Latenz, Jitter, Paketverlust

### 🧹 System Cleaner
- Leert sicher nur Temp-/Dump-Ordner (`%TEMP%`, `Windows\Temp`, `CrashDumps`)
- Fasst **nie** Dokumente, Browserprofile oder den Papierkorb an; überspringt Dateien in Benutzung
- Erst scannen (zeigt freigebbaren Speicher), dann per Klick bereinigen

### 🛠 Windows Optimizer
- **65 Tweaks** in den Kategorien Windows, Gaming, Network, Audio
- Live-Statusverifizierung — liest den tatsächlichen Registry-/Dienst-Zustand (nicht nur die JSON-Datei)
- 3-stufige Statusanzeige: ● Grün (verifiziert aktiv) / ◑ Amber (angewendet, ungeprüft) / ○ Grau (inaktiv)
- **7 integrierte Presets:** Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, Alle sicheren Tweaks
- Export/Import der Einstellungen als `.nextune`-Dateien
- Tooltips (Hover über `?`) für jeden einzelnen Tweak

### 🖥 BIOS Guide
- Hardware-bewusste Empfehlungen (erkennt automatisch CPU, GPU, Mainboard)
- Live-Systemzustandserkennung — zeigt, was bereits aktiv ist (grün ●) vs. was noch nötig ist (rot ●)
- Deckt ab: AMD Zen 3/4/5, Intel 12./13./14. Gen, X670/B650/Z790/Z690
- Einstellungen enthalten exakte BIOS-Menüpfade + Windows-Registry-Äquivalente

### 🎮 Per-Game-Profile
- Hintergrund-Prozessüberwachung (psutil, ~3s Intervall, ressourcenschonend)
- Lädt automatisch das GPU-Profil beim Spielstart, stellt das Standardprofil beim Beenden wieder her
- 15 vorkonfigurierte Spiele (CS2, Cyberpunk 2077, Apex Legends, Valorant, Fortnite …)
- Beliebige `.exe`-Prozesse können manuell hinzugefügt werden

### 📋 Tune-Verlauf
- Protokolliert jeden Auto-Tune-Durchlauf (Datum, Modus, Core-Offset, Power, Spannung, Score)
- Klick auf einen Durchlauf zeigt das vollständige Log

### 🌡 Temperaturwarnung
- Windows-Toast-Benachrichtigung, wenn die GPU 90 °C erreicht
- 5 Minuten Abklingzeit zwischen Warnungen, konfigurierbares Limit

### 🔄 Update-Checker
- Prüft beim Start im Hintergrund (nicht blockierend) auf neue GitHub-Releases
- Zeigt einen Download-Link an, wenn eine neue Version verfügbar ist

### 🌐 Sprachunterstützung
- **Englisch** (Standard) und **Deutsch** — Umschaltung per `EN/DE`-Button in der Titelleiste
- Sofortiger Wechsel, kein Neustart nötig

### 🚀 Startup Manager
- Eigenes Fenster mit allen Autostart-Einträgen aus der Registry
- Status je Eintrag: Sicher ✓ / Vorsicht ⚠ / System ⚙ / Unbekannt ?
- 40+ vorklassifizierte bekannte Prozesse (Discord, Steam, Corsair, NVIDIA usw.)

---

## 📋 Voraussetzungen

| Anforderung | Details |
|---|---|
| **Betriebssystem** | Windows 10 / Windows 11 |
| **Python** | 3.10 oder neuer |
| **GPU** | NVIDIA (voller Support) oder AMD (Tweaks + BIOS-Guide) |
| **MSI Afterburner** | Optional — erforderlich für Spannungswerte (mV) und OC-Profile |
| **Admin-Rechte** | Erforderlich für Registry-Tweaks und GPU-Power-Control |

---

## 📦 Installation

### 1. Python installieren
Python 3.10+ von [python.org/downloads](https://python.org/downloads) herunterladen.

> ⚠️ **Wichtig:** Während der Installation **"Add Python to PATH"** aktivieren.

### 2. GameOptimizerPro herunterladen
Auf dieser Seite **Code → Download ZIP** klicken, oder das Repo klonen:
```bash
git clone https://github.com/FloDePin/GameOptimizerPro-v2.git
```
In einen dauerhaften Ordner entpacken, z. B. `C:\Tools\GameOptimizerPro\`

### 3. Abhängigkeiten installieren
`install.bat` doppelklicken — installiert alles automatisch:
```
pystray, Pillow, nvidia-ml-py, numpy, wmi, psutil
```

### 4. (Optional) MSI Afterburner einrichten
Für Spannungswerte und GPU-Overclocking:
1. [MSI Afterburner](https://www.msi.com/Landing/afterburner/graphics-cards) herunterladen und installieren
2. Afterburner öffnen → Settings → **General** → **"Unlock voltage control"** aktivieren
3. Settings → **General** → **"Unlock voltage monitoring"** aktivieren
4. Settings → **Monitoring** → **GPU Core Voltage** aktivieren
5. Auf das 🔒-Schloss-Symbol bei Profile Slot 2 klicken, um es zu entsperren
6. Afterburner im System-Tray laufen lassen

### 5. Starten
`GameOptimizerPro.bat` doppelklicken

> Der Launcher nutzt einen versteckten PowerShell-`Start-Process -Verb RunAs`-Aufruf, um `pythonw.exe` unsichtbar zu starten und über UAC Administrator-Rechte anzufordern. Es erscheint kein CMD-Fenster.

---

## 🚀 Erste Schritte

1. **[WIN] Optimizer** öffnen → **"⟳ Check Status"** klicken, um zu sehen welche Tweaks bereits aktiv sind
2. Das **🎮 Gaming-Preset** anwenden für eine schnelle All-in-One-Optimierung
3. **Audio-Tweaks** unter **[WIN] Optimizer** finden (Kategorie: Audio) — Low-Latency-Audio-Tweaks aktivieren
4. **[BIOS] BIOS Guide** prüfen — erkennt deine Hardware und zeigt an, was geändert werden sollte
5. Falls Afterburner läuft, den **[GPU] GPU Tuner** ausprobieren → Start Tune (OC+UV empfohlen)

---

## 🗂 Projektstruktur

```
GameOptimizerPro/
├── GameOptimizerPro.py       ← Haupteinstiegspunkt
├── GameOptimizerPro.bat      ← Launcher (PowerShell Start-Process, versteckt, UAC)
├── install.bat               ← Abhängigkeits-Installer
├── _stress_worker.py         ← GPU-Stresstest-Subprozess
├── core/
│   ├── nvtune_core.py        ← GPU-Monitor (NVML + MAHM), Afterburner-Controller
│   ├── nvtune_tuner.py       ← Auto-Tuner (Stage 1 OC, Stage 2 UV, TDR-Erkennung)
│   ├── vf_curve.py           ← Spannungs-Frequenz-Kurven-Optimierung
│   ├── hardware.py           ← WMI-Hardware-Erkennung
│   ├── tweaks.py             ← 50+ Tweaks-Datenbank (Windows, Gaming, Network, Audio)
│   ├── tweak_runner.py       ← PowerShell-Executor (versteckt)
│   ├── tweak_verifier.py     ← Registry-Verifizierung (100% Abdeckung)
│   ├── tweak_presets.py      ← 7 integrierte Presets
│   ├── tweak_i18n.py         ← Mehrsprachige Tweak-Beschreibungen (EN/DE)
│   ├── bios_guide.py         ← BIOS-Empfehlungsdatenbank
│   ├── bios_detector.py      ← Live-BIOS-Zustandserkennung
│   ├── game_monitor.py       ← Per-Game-Profil-Monitor (psutil)
│   ├── crash_recovery.py     ← TDR-Erkennung, Crash-Flag-System
│   ├── temp_monitor.py       ← GPU-Temperatur-Toast-Benachrichtigungen
│   ├── update_checker.py     ← GitHub-Releases-API
│   ├── export_import.py      ← .nextune Export/Import
│   ├── tune_history.py       ← Tune-Log-Parser
│   ├── startup_loader.py     ← Autostart + Startprofil-Loader
│   ├── gpu_defaults.py       ← GPU-Generationen-Standardwerte-Tabelle
│   ├── mahm_reader.py        ← MSI-Afterburner-Shared-Memory-Reader
│   └── i18n.py               ← EN/DE-Sprachmodul
└── ui/
    ├── main_window.py        ← Hauptfenster, Tab-Router
    ├── widgets.py            ← Gemeinsame Widgets, Farben, Styles
    ├── tab_dashboard.py      ← Systemübersicht + Live-GPU-Telemetrie
    ├── tab_optimizer.py      ← Windows-Optimizer mit Sidebar (inkl. Audio-Tweaks)
    ├── tab_gpu.py            ← GPU-Tuner-UI
    ├── tab_stress.py         ← Stresstest + FurMark-Launcher
    ├── tab_compare.py        ← Profilvergleich
    ├── tab_bios.py           ← BIOS-Guide mit Live-Erkennung
    ├── tab_games.py          ← Per-Game-Profile + Tune-Verlauf
    ├── tab_settings.py       ← Autostart, Setup-Checker, Über
    ├── live_graph.py         ← Rollierendes Spannungs-/Takt-/Temperatur-Diagramm
    └── startup_manager.py    ← Startup-Manager-Fenster
```

---

## ⚙️ Architektur

```
Main-Thread   → tkinter mainloop() — einziger Thread, der die UI anfasst
Thread 2      → pystray.run() — System-Tray-Icon
Thread 3      → GPU-Stats-Loop (4s Intervall)
Thread 4      → Startup (Crash-Check + Profil-Laden)
Thread 5      → Menü-Refresh (20s Intervall)
Thread 6      → Game-Prozess-Monitor (3s Intervall, psutil)
Thread 7      → Temperatur-Monitor (10s Intervall)
Thread 8+     → Auto-Tune-Stages, Stress-Worker-Subprozess
```

Thread-übergreifende Kommunikation läuft über `widget.after(0, callback)` — der einzige sichere Weg, tkinter aus Hintergrund-Threads heraus zu aktualisieren.

---

## 🛡 Sicherheit

- **Keine BIOS-Schreibzugriffe** — BIOS Guide gibt nur schreibgeschützte Empfehlungen
- **Keine Treiber-Modifikationen** — läuft über MSI Afterburner und das offizielle NVML
- **Registry-Tweaks sind reversibel** — "Revert All" stellt die Standardwerte wieder her
- **Crash Recovery** — TDR-Erkennung setzt die GPU automatisch auf sichere Einstellungen zurück
- **Admin-Rechte** werden per UAC angefragt, nicht fest einprogrammiert
- **Audio-Tweaks sind reversibel** — alle Änderungen können über "Revert" rückgängig gemacht werden

---

## 🤝 Mitwirken

Pull Requests sind willkommen. Für größere Änderungen bitte zuerst ein Issue eröffnen.

---

## 📄 Lizenz

MIT-Lizenz — Details siehe [LICENSE](LICENSE).

---

<div align="center">
Mit ❤️ gemacht von FloDePin
</div>
