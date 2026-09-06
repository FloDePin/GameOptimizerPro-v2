<div align="center">

# ⚡ GameOptimizerPro v2.0

**Windows & Gaming Optimizer v2.0 von FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 [English](README.md) | 🇩🇪 **Deutsch**

*All-in-one PC-Optimierungstool — GPU Auto-Tuner, Audio-Optimierung, Windows-Tweaks, BIOS-Guide, Per-Game-Profile und mehr.*

</div>

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

### ⚡ Stress Test
- **Interner Stabilitätstest** — eingebauter GPU/CPU-Stress-Worker mit einstellbarer Dauer und **Auto-Abbruch bei Max-Temperatur**; inkl. Dead-Man-Switch, damit nie ein verwaister 100%-CPU-Prozess zurückbleibt
- **FurMark-Launcher** — erkennt eine FurMark-Installation automatisch, Auflösung wählen, Ein-Klick-Start für einen härteren GPU-Burn-in

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

### 🧹 System Cleaner & Sicherheit
- Leert sicher nur Temp-/Dump-Ordner (`%TEMP%`, `Windows\Temp`, `CrashDumps`)
- Fasst **nie** Dokumente, Browserprofile oder den Papierkorb an; überspringt Dateien in Benutzung
- Erst scannen (zeigt freigebbaren Speicher), dann per Klick bereinigen
- **Wiederherstellungspunkt erstellen** — Ein-Klick-Sicherheitsnetz vor dem Anwenden von Tweaks

### 🛠 Windows Optimizer
- **71 Tweaks** in den Kategorien Windows, Gaming, Network, Audio
- Live-Statusverifizierung — liest den tatsächlichen Registry-/Dienst-Zustand (nicht nur die JSON-Datei)
- 3-stufige Statusanzeige: ● Grün (verifiziert aktiv) / ◑ Amber (angewendet, ungeprüft) / ○ Grau (inaktiv)
- **Abgestufte Ein-Klick-Presets — 🟢 Minimal → 🟡 Mittel → 🔴 Hart (Debloat)** — kumulative Intensitätsstufen, die ein kuratiertes, ansteigendes Tweak-Set anwenden
- **10 integrierte Presets:** die 3 Intensitätsstufen + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, Alle sicheren Tweaks
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
- **Per-Game-CPU-Pinning (CPU Sets)** — lenkt ein Spiel optional auf bestimmte Kerne: das **X3D-Cache-Chiplet** bei Dual-CCD-AMD oder die **P-Cores** bei Intel Hybrid. Weicher Scheduler-Hinweis (bremst das Spiel nie aus); auf Single-Chiplet-CPUs ehrlich deaktiviert, wo es nichts bringt
- 15 vorkonfigurierte Spiele (CS2, Cyberpunk 2077, Apex Legends, Valorant, Fortnite …)
- Beliebige `.exe`-Prozesse können manuell hinzugefügt werden

### 🩺 Diagnose & Messung
- **FPS-/Frametime-Messung** — miss den *echten* Effekt deiner Tweaks: **Ø FPS, 1%- und 0.1%-Lows, Stutters** und ein gemessenes **CPU-vs-GPU-Bottleneck**-Urteil. Live via [PresentMon](https://github.com/GameTechDev/PresentMon) (optional, in `tools/` legen) oder Auswertung einer vorhandenen PresentMon-/CapFrameX-/OCAT-CSV — für die CSV-Analyse ist keine Binary nötig
- **Health Report** — read-only-Übersicht dessen, was Windows in den letzten 30 Tagen schon protokolliert hat: WHEA-Hardwarefehler, Bluescreens, unerwartete Neustarts, GPU-Treiber-Timeouts (TDR), Datenträgerfehler, App-Abstürze — mit Schweregrad und letztem Auftreten
- **Remnant-Scan** — read-only-Erkennung von Resten *anderer* Tweak-Tools (WinRing0-/inpout-Treiber, ISLC, TimerResolution-Autostarts, Fremd-Energiepläne, Razer Cortex). Meldet nur — entfernt nichts

### 📊 Profil-Vergleich
- Vergleicht bis zu **4 gespeicherte GPU-Profile nebeneinander** (Core-/Memory-Offset, Power-Limit, Spannungs-Lock, Stabilitäts-Score) — das beste auf einen Blick

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

### 🔽 System-Tray
- Minimiert in den Tray statt zu schließen; der Tray-Tooltip zeigt **live GPU-Temp / Takt / Spannung / Power**
- Gespeicherte GPU-Profile schnell anwenden, GPU auf Stock zurücksetzen oder öffnen/beenden — alles aus dem Tray-Menü

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

## 📜 Änderungsverlauf

### v2.0 — Final — 05.09.2026
GameOptimizerPro **2.0** ist der finalisierte Release: der komplette Funktionsumfang unten, gehärtet über viele interne Iterationen und **zwei vollständige externe Code-Review-Runden** — jeder verifizierte Bug ehrlich gefixt.

**Highlights**
- 🩺 **Diagnose-Tab (messen statt raten):** FPS-/Frametime-Capture mit **1%- & 0.1%-Lows**, Stutters und gemessenem **CPU-vs-GPU-Bottleneck** (PresentMon live oder CSV); ein 30-Tage-**Health-Report** aus Windows' eigenen Logs; und ein **Remnant-Scan** für Reste anderer Tweak-Tools. Alles read-only. *(Nebenbei einen latenten Bug gefixt, der die Games-/Settings-Tab-Buttons versteckte.)*
- 🎮 **GPU Auto-Tuner** (OC / UV / OC+UV) mit automatischem Stabilitätstest, Live-Graph, TDR-Erkennung und Crash-Recovery — plus MSI-Afterburner-(MAHM)-Integration
- 🛠 **71 verifizierte Tweaks** mit Live-Status (grün/amber/grau), abgestuften Minimal→Mittel→Hart-Presets und kuratierten Gaming/Privacy/Debloat/Network/Performance/Win11-Presets
- 🎮 **Per-Game-Profile + CPU-Pinning (CPU Sets)** — lenkt Spiele auf das X3D-Cache-Chiplet (AMD) oder die P-Cores (Intel), mit Anti-Cheat- & CCD-Parking-Warnungen und ehrlichem "bringt nichts" auf Single-Chiplet-CPUs
- 🖥 **BIOS-Guide**, 📊 **Live-Dashboard** (GPU + CPU/RAM/Disk + Latenz-Test), 🧹 **System Cleaner & Wiederherstellungspunkt**, 📋 **Tune-Verlauf**, 🚀 **Startup Manager**, 🌐 **DE/EN**

**Zuverlässigkeit & Ehrlichkeit (in 2.0 eingeflossene Fixes)**
- Stress-Worker-Dead-Man-Switch auf allen Pfaden (kein verwaister 100%-CPU-Prozess); thread-sichere Log-/UI-Ausgabe; UAC-freier Autostart via Task Scheduler
- Ehrliche Tweak-Reverts (inkl. 12 zuvor einseitiger Tweaks), sodass "Revert All" wirklich alles zurücksetzt
- DX12-Tweak ehrlich neu als "GPU-Timeout erhöhen (TDR-Delay)" (der alte Wert war ein wirkungsloses Placebo); Nahimic-Verifier zeigt auf PCs ohne Nahimic kein Falsch-Amber mehr
- Robustes Versions-Parsing im Update-Checker, konfigurierbarer Stabilitäts-Score, absoluter State-Datei-Pfad und diverse Topologie- / MAHM- / wmic- / Encoding-Edge-Cases gefixt
- "Geprüft und als kein Bug bestätigt"-Punkte wurden bewusst nicht verändert statt übertüncht

Vollständige Details in [CHANGELOG.md](CHANGELOG.md).

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
│   ├── cpu_topology.py       ← CPU-Topologie (CCDs, P/E-Cores, X3D-Cache-Die)
│   ├── cpu_pinning.py        ← Per-Game-CPU-Pinning via CPU Sets API
│   ├── fps_capture.py        ← FPS/Frametime-Metriken (PresentMon + CSV)
│   ├── health_report.py      ← 30-Tage Windows-Health-Report
│   ├── remnant_detector.py   ← Erkennung von Tweak-Tool-Resten
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
    ├── tab_diagnose.py       ← FPS-Capture + Health-Report + Remnant-Scan
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
