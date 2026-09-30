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
- **So sucht er:** erhöht den Core-Offset schrittweise (z. B. +15 MHz); bei einem Fehlschlag geht er auf den **letzten stabilen Wert zurück und halbiert die Schrittweite** (15 → 7 → 5 MHz) und landet so mit ±5 MHz Genauigkeit an der Stabilitätsgrenze. Das Power-Limit sinkt bis zum **niedrigsten Wert, der unter Volllast höchstens 3 % Leistung kostet**. Ein 2-Minuten-Endtest prüft genau das Profil, das gespeichert wird. *(Der Tuner enthält außerdem eine V/F-Kurven-Stufe und eine Speicher-Stufe — der Speicher steigt nur, solange seine Bandbreite weiter steigt, weil GDDR6X über dem Limit langsamer wird statt abzustürzen, und übernommen wird der Offset mit der höchsten gemessenen Bandbreite —, diese Modi sind im GPU-Tab aber noch nicht auswählbar.)*
- **Spielähnliche Last bei der OC-Suche:** Dauer-Volllast hält die Karte am Power-Limit (~2500 MHz), Spiele stürzen aber am *Boost*-Punkt ab. Die OC-Schritte und der Endtest wechseln deshalb zwischen Volllast und halber Last, die den Hochtakt-/Hochspannungs-Punkt von Spielen erreicht (gemessen auf einer RTX 4080: 2790 MHz @ 1075 mV — genau der Arbeitspunkt in Hunt: Showdown)
- **Instabilität wird an falschen Ergebnissen erkannt, nicht erst am Absturz** — der Stress-Worker wiederholt dieselbe Matrix-Rechnung und vergleicht jedes Ergebnis mit dem ersten (Methode von gpu-burn / OCCT); ein einziger falscher Wert lässt den Schritt scheitern. Das Power-Limit zu erreichen gilt als normal; nur thermische / Hardware-Drosselung zählt als Grenze
- Automatisierter, schrittweiser Stabilitätstest mit Stress-Worker — **verweigert das Tunen ohne echte GPU-Last** (gemessen in der Baseline; ≥ 70 %), weil ein OC/UV-Test bei leerlaufender GPU instabile Werte als „stabil" speichern würde. GPU-Last liefert der Stress-Worker über `cupy` (`pip install "cupy-cuda12x[ctk]"` — `install.bat` bietet es an) oder ein parallel laufendes FurMark
- **Ein durchgefallener Endtest ist nicht das Ende:** Der Tuner nimmt einen Schritt zurück (Core, dann einen Speicher-Offset, die V/F-Spannung oder bei Hitze das Power-Limit) und testet erneut — gespeichert wird nur, was den Endtest bestanden hat. Während Tune und Stresstest bleibt der PC wach
- **Abbruch stoppt wirklich**: Der laufende Stress-Schritt endet sofort, die GPU geht auf Standard zurück (Offsets 0, Werks-Power-Limit), und danach wird nichts mehr angewendet; Beenden der App oder Sprachwechsel während eines Tunes tun dasselbe
- TDR-Erkennung (GPU-Treiber-Timeout) über das Windows-Ereignisprotokoll
- Crash Recovery — stellt beim nächsten Systemstart automatisch das letzte stabile Profil wieder her
- Live-Diagramm für Spannung/Takt/Temperatur während des Tunings
- Integration mit **MSI Afterburner** (MAHM Shared Memory für echte mV-Werte — der Parser folgt Afterburners dokumentiertem Layout; verbindet sich automatisch, wenn Afterburner später gestartet wird; ein Monitoring-Speicher, der nicht mehr aktualisiert wird — z. B. nachdem Afterburner abgeschossen wurde —, wird nach 8 s erkannt und verworfen statt eingefrorene Werte zu zeigen; GPU-Werte kommen zuerst aus NVML)
- Automatische GPU-Generationserkennung (Pascal → Ada Lovelace, RDNA 1–3)
- **Wendet Profile über Afterburners echtes Profil pro Grafikkarte an** (`Profiles\VEN_…cfg`, per PCI-ID der Karte ausgewählt): Core-/Speicher-Offset, Power-Limit und eine echte flache V/F-Kurve fürs Undervolting. Afterburner liest diese Datei nur beim Start, deshalb wird er beim Anwenden neuer Werte **kurz neu gestartet** (minimiert); gleiche Werte werden nur erneut gesendet. Die Originaldatei wird einmal pro Sitzung gesichert. *Stand: live verifiziert auf einer RTX 4080 mit Afterburner 4.6.6 — ein von der App geschriebenes Profil wurde von Afterburner übernommen (Power-Limit per NVML zurückgelesen), gleiche Werte ohne Neustart erneut angewendet, „Reset auf Standard“ funktionierte, und die Originaldatei kam Byte für Byte zurück. Ein kompletter Auto-Tune auf echter Hardware ist der nächste Schritt ([TESTANLEITUNG.md](TESTANLEITUNG.md)).* Lüfter-Einstellungen bleiben in Afterburner.

### ⚡ Stress Test
- **Interner Stabilitätstest** — eingebauter GPU/CPU-Stress-Worker mit einstellbarer Dauer und **Auto-Abbruch bei Max-Temperatur**; inkl. Dead-Man-Switch, damit nie ein verwaister 100%-CPU-Prozess zurückbleibt. Schlägt bei **falschen Ergebnissen (Rechenfehlern)**, **Worker-Absturz oder TDR** fehl, meldet die **durchschnittliche GPU-Last** und sagt klar „kein GPU-Stress" statt „bestanden", wenn die GPU nicht ausgelastet war (kein `cupy`); ein gestoppter Test liefert kein Ergebnis
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
- **Optimierungs-Score** — Anteil der *sicheren*, auf diesem PC anwendbaren Tweaks, die laut Systemprüfung gerade wirklich aktiv sind (moderate/riskante zählen nicht — der Score verleitet nie zu riskanten Eingriffen)
- **Monitor-Berater** — warnt, wenn ein Bildschirm unter der höchsten Bildwiederholrate läuft, die sein Treiber bei der aktuellen Auflösung anbietet (z. B. 50 statt 60 Hz, 60 statt 144/165 Hz)
- **Netzwerk-Latenz-Test** — Ein-Klick-Ping zu Gateway + Cloudflare & Google mit Ø/min/max-Latenz, Jitter, Paketverlust

### 🧹 System Cleaner & Sicherheit
- Immer: Temp-/Dump-Ordner (`%TEMP%`, `Windows\Temp`, `CrashDumps`) — nur Dateien, die älter als 24 Stunden sind, damit laufende Programme ihre frischen Temp-Dateien behalten
- **Deep Clean (freiwillig, jedes Ziel einzeln):** Browser-*Caches* (Chrome, Edge, Firefox), Windows-Update-Downloadcache, Miniaturansichten, Prefetch, System-Logs & Fehlerberichte und der Papierkorb (mit Extra-Rückfrage)
- Fasst **nie** Dokumente oder Browserprofile an (Passwörter, Verlauf, Lesezeichen, Cookies); überspringt Dateien in Benutzung und zählt nur, was wirklich gelöscht wurde
- Erst scannen (zeigt freigebbaren Speicher je Gruppe), dann per Klick bereinigen
- **Wiederherstellungspunkt erstellen** — Ein-Klick-Sicherheitsnetz vor dem Anwenden von Tweaks
- **Registry-Backup** — exportiert alle Registry-Zweige, die die Tweaks anfassen können, als `.reg`-Dateien (zum Zurückspielen genügt ein Doppelklick). Läuft **automatisch vor jedem „Apply Selected", Preset, „Revert All" und „Abweichungen beheben"** sowie auf Knopfdruck; behält die 10 neuesten Backups und löscht ältere automatisch, damit die Platte nicht vollläuft

### 🛠 Windows Optimizer
- **106 Tweaks** in den Kategorien Windows, Gaming, Network, Audio (inkl. AMD-GPU-Tweaks)
- **Windows 11 24H2/26H2 — KI & Bloat:** Recall (Richtlinie + Entfernen der Komponente), Click to Do, Paint-KI (Cocreator, Image Creator, generatives Füllen/Löschen), Notepad-KI, geräteinterne Text-/Bildgenerierung, der KI-Hostdienst (`WSAIFabricSvc`) und das Entfernen der Microsoft-365-Copilot-App / Dev Home, die Funktionsupdates wieder installieren — über Microsofts dokumentierte Richtlinien, wo es sie gibt
- **Speicher & RAM:** lange Pfade, reservierter Speicher, Auslagerungsdatei, Speicherkomprimierung, SSD-TRIM, geplante Defragmentierung, NVMe-Queue-Tiefe (nur mit NVMe-Laufwerk angeboten), Schreibcache-Leerung (fortgeschritten), dazu eine einmalige **sichere Datenträgerbereinigung** (kein Downloads-Ordner, kein Papierkorb, kein Windows.old)
- **Drift-Prüfung beim Start:** Tweaks, die du angewendet hast und die ein Windows-Update zurückgesetzt hat, werden mit je einem Haken aufgelistet — mit Haken erneut anwenden (vorher Registry-Backup), ohne Haken nicht mehr nachfragen; „Später“ fragt beim nächsten Start wieder
- **Entweder-oder:** nur ein Energieplan und ein DNS-Anbieter wählbar („⇄ entweder-oder“); ein Haken nimmt den anderen weg, und die Höchstleistungs-Pläne schalten im Netzbetrieb weder Bildschirm noch PC ab
- **Immer nur ein Durchlauf gleichzeitig**, mit sichtbarem Fortschritt bei langen Tweaks (die Datenträgerbereinigung dauert Minuten); Mausrad funktioniert über der ganzen Liste
- Live-Statusverifizierung — liest den tatsächlichen Registry-/Dienst-Zustand (nicht nur die JSON-Datei)
- 3-stufige Statusanzeige: ● Grün (verifiziert aktiv) / ◑ Amber (angewendet, ungeprüft) / ○ Grau (inaktiv)
- **Abgestufte Ein-Klick-Presets — 🟢 Minimal → 🟡 Mittel → 🔴 Hart (Debloat)** — kumulative Intensitätsstufen, die ein kuratiertes, ansteigendes Tweak-Set anwenden
- **10 integrierte Presets:** die 3 Intensitätsstufen + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, Alle sicheren Tweaks
- **AMD-GPU-Tweaks** — ULPS deaktivieren, Shader-Cache unbegrenzt, Anti-Lag (Low-Latency-Modus); erscheinen für AMD-Systeme und werden auf NVIDIA ehrlich als inaktiv gemeldet. Herstellerspezifische GPU-Tweaks (AMD und NVIDIA) sind **doppelt abgesichert**: Presets überspringen sie auf der falschen GPU, und der Befehl selbst verweigert ohne passenden Adapter — AMD-Werte landen nur im Treiberschlüssel des AMD-Adapters
- **Power-Plan-Tweaks schreiben in *alle* Energieschemata** — Windows kann nach einem Neustart ein anderes Schema aktivieren, wodurch eine Einstellung sonst „zurückgesetzt" aussieht. Die Plan-GUIDs kommen aus `powercfg /L`, nie der lokalisierte Planname — also sprachunabhängig
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

### ⚙ Services Manager
- Eigenes Fenster mit 29 selten benötigten Windows-Diensten (Telemetrie, Xbox, Fax, Karten, Hyper-V, der KI-Host aus 24H2/26H2 …) — Live-Status, Starttyp, Kategorie und Einstufung sicher/Vorsicht
- **Deaktivieren merkt sich den ursprünglichen Starttyp** (inkl. „Automatisch (verzögert)“), **Aktivieren stellt ihn wieder her** (oder den Windows-Standard) — nicht einfach „Manuell“
- Extra-Rückfrage bei Diensten, die eine Funktion abschalten (Druckwarteschlange, Windows Update, BITS, die Xbox-Dienste für Game-Pass-Spiele); ohne Admin-Rechte nur Anzeige; Link zu `services.msc`

### 🚀 Startup Manager
- Eigenes Fenster mit allen Autostart-Einträgen — **Run-Keys (HKCU, HKLM, HKLM 32-Bit) und beide Autostart-Ordner** (Benutzer + alle Nutzer, `.lnk`-Ziele aufgelöst)
- Zeigt den **echten An/Aus-Zustand** und kann Einträge **aktivieren / deaktivieren** (Mehrfachauswahl) — genau wie der Task-Manager: gesetzt wird nur das Windows-`StartupApproved`-Flag, nichts wird gelöscht, jede Änderung ist hier oder im Task-Manager umkehrbar
- Rückfrage vor dem Deaktivieren, mit Extra-Warnung bei System-/nicht empfohlenen Einträgen; Filter für deaktivierte Einträge
- Status je Eintrag: Sicher ✓ / Vorsicht ⚠ / System ⚙ / Unbekannt ?
- 40+ vorklassifizierte bekannte Prozesse (Discord, Steam, Corsair, NVIDIA usw.)

---

## 📋 Voraussetzungen

| Anforderung | Details |
|---|---|
| **Betriebssystem** | Windows 10 / Windows 11 |
| **Python** | 3.10 oder neuer |
| **GPU** | NVIDIA (voller Support) oder AMD (Tweaks + BIOS-Guide) |
| **MSI Afterburner** | Optional — erforderlich für Spannungswerte (mV) und OC-Profile (beim Anwenden eines Profils wird er kurz neu gestartet) |
| **cupy** | Optional — `pip install "cupy-cuda12x[ctk]"` (kein CUDA-Toolkit nötig; `install.bat` fragt nach) gibt dem Stress-Worker echte **GPU**-Last samt Fehler- und Bandbreitenprüfung (NVIDIA). Ohne cupy (oder parallel laufendes FurMark) verweigert der Auto-Tuner den Start |
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
`install.bat` doppelklicken — installiert alles automatisch und bietet danach `cupy` an (GPU-Last für den Auto-Tuner, mit **J** bestätigen):
```
pystray, Pillow, nvidia-ml-py, numpy, wmi, psutil
```

### 4. (Optional) MSI Afterburner einrichten
Für Spannungswerte und GPU-Overclocking:
1. [MSI Afterburner](https://www.msi.com/Landing/afterburner/graphics-cards) herunterladen und installieren
2. Afterburner öffnen → Settings → **General** → **"Unlock voltage control"** aktivieren
3. Settings → **General** → **"Unlock voltage monitoring"** aktivieren (empfohlen außerdem **"Minimiert starten"**)
4. Settings → **Monitoring** → die Graphen **GPU-Spannung** und **Leistung** aktivieren
5. Ohne etwas zu ändern auf **Speichern** und dann auf **Slot 1** klicken — das legt die Profildatei der Karte (`Profiles\VEN_…cfg`) samt V/F-Kurve an, und Slot 1 behält deine Werkseinstellungen. GameOptimizerPro schreibt in **Slot 2** (im GPU-Tab änderbar)
6. Afterburner im System-Tray laufen lassen
7. Prüfen: `python tools\ab_selftest.py info` (nur lesend) — siehe [TESTANLEITUNG.md](TESTANLEITUNG.md)

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
- 🛠 **83 verifizierte Tweaks** (heute 106 — siehe unten) mit Live-Status (grün/amber/grau), abgestuften Minimal→Mittel→Hart-Presets und kuratierten Gaming/Privacy/Debloat/Network/Performance/Win11-Presets
- 🎮 **Per-Game-Profile + CPU-Pinning (CPU Sets)** — lenkt Spiele auf das X3D-Cache-Chiplet (AMD) oder die P-Cores (Intel), mit Anti-Cheat- & CCD-Parking-Warnungen und ehrlichem "bringt nichts" auf Single-Chiplet-CPUs
- 🖥 **BIOS-Guide**, 📊 **Live-Dashboard** (GPU + CPU/RAM/Disk + Latenz-Test), 🧹 **System Cleaner & Wiederherstellungspunkt**, 📋 **Tune-Verlauf**, 🚀 **Startup Manager**, 🌐 **DE/EN**

**Zuverlässigkeit & Ehrlichkeit (in 2.0 eingeflossene Fixes)**
- Stress-Worker-Dead-Man-Switch auf allen Pfaden (kein verwaister 100%-CPU-Prozess); thread-sichere Log-/UI-Ausgabe; UAC-freier Autostart via Task Scheduler
- Ehrliche Tweak-Reverts (inkl. 12 zuvor einseitiger Tweaks), sodass "Revert All" wirklich alles zurücksetzt
- DX12-Tweak ehrlich neu als "GPU-Timeout erhöhen (TDR-Delay)" (der alte Wert war ein wirkungsloses Placebo); Nahimic-Verifier zeigt auf PCs ohne Nahimic kein Falsch-Amber mehr
- Robustes Versions-Parsing im Update-Checker, konfigurierbarer Stabilitäts-Score, absoluter State-Datei-Pfad und diverse Topologie- / MAHM- / wmic- / Encoding-Edge-Cases gefixt
- Auto-Tuner: **der Final-Test prüft jetzt exakt das Profil, das gespeichert wird** — inklusive V/F-Undervolt und Memory-OC (vorher lief der Final-Test mit Stock-Spannung, der gespeicherte Undervolt wurde also nie als Ganzes verifiziert)
- Header-**Uhr und die AB- / NVML- / MAHM-Anzeigen aktualisieren sich wieder zuverlässig** — der alte Hintergrund-Updater konnte beim ersten Tick sterben (Tk `after()` aus einem Worker-Thread vor der mainloop auf Python 3.14); läuft jetzt im Main-Thread
- Per-Game-Prozess-Scan nutzt den gecachten Prozessnamen (kein Komplett-Ausfall des Scans, wenn ein Prozess mitten im Scan stirbt); GPU-Spalte der FPS-CSV bleibt bei kurzen Zeilen index-treu
- **„Revert All" fasst nur noch an, was GameOptimizerPro selbst angewendet hat** — „Status prüfen" hat jede bereits aktive Einstellung des PCs vereinnahmt (Dark Mode, Dateiendungen, …), sodass Revert All selbst eingestellte Dinge abschalten konnte; der `.nextune`-Import hat Tweaks als angewendet markiert, ohne sie anzuwenden; „Abweichungen beheben" hat nie gewählte Einstellungen angewendet. Der Verifier *zeigt* jetzt nur an, der Verify-Tab trennt „hinter unserem Rücken zurückgesetzt" von „aktiv, aber nicht von uns", und der Import wählt Tweaks zur Prüfung vor
- **GPU-Tweaks landen nicht mehr auf der falschen GPU** — Presets haben NVIDIA-/AMD-only-Tweaks auf jeder Hardware angewendet, und die AMD-Tweaks liefen über *alle* Grafikadapter (auch NVIDIA/Intel). Jetzt in der UI gefiltert **und** im Befehl selbst abgesichert
- **Kein Besetzen von Afterburners Shared Memory mehr** — der MAHM-Reader hat eine 1-MB-Section `MAHMSharedMemory` *angelegt*, sobald Afterburner nicht lief, und sie offen gehalten; jetzt öffnet er nur eine vorhandene, mappt sie in jeder Größe und verbindet sich automatisch, wenn Afterburner später gestartet wird
- **Registry-Backup läuft wirklich automatisch** — es hing an Batch-Methoden, die die UI nie aufgerufen hat
- **Afterburner-Telemetrie funktioniert** — der MAHM-Parser nutzte ein falsches Layout (284-Byte-Einträge; echt sind 1324) und lieferte für jeden Sensor 0; leere MAHM-Werte überschreiben keine gültigen NVML-Werte mehr (Lüfter %, Power-Limit), und CPU-Power wird nicht mehr als GPU-Temperatur angezeigt
- **Auto-Tune-Sicherheit** — „Abort" konnte vom noch laufenden Schritt überschrieben werden (nach dem Reset wurde wieder ein OC angelegt); Beenden während eines Tunes hinterließ ein ungetestetes OC; „Reset to stock" setzte das *maximale* Power-Limit; ohne GPU-Last (kein `cupy`) „verifizierte" der Tuner OCs bei leerlaufender GPU — alles behoben
- **Autostart bleibt aktiv** — Windows' Task-Standardwerte haben die Tray-App nach 3 Tagen beendet und im Akkubetrieb blockiert; der Stresstest meldet einen gestoppten Lauf nicht mehr als „PASSED"; der Tune-Verlauf zeigt den echten Modus; die primäre GPU wird auf iGPU+dGPU-Systemen erkannt
- "Geprüft und als kein Bug bestätigt"-Punkte wurden bewusst nicht verändert statt übertüncht

**Seit dem Release (weiterhin 2.0)**
- 🎮 **Afterburner-Profile live auf echter Hardware verifiziert**; ein dabei gefundener echter Bug — eingefrorenes Monitoring nach einem Afterburner-Neustart — ist behoben; OC-Schritte laufen jetzt mit **spielähnlicher Wechsellast**; die Speicher-Stufe übernimmt das Bandbreiten-Maximum
- 🔁 **v1-Parität ehrlich vervollständigt** — eine Prüfung zeigte, dass die frühere „volle Parität“ nicht stimmte: 18 weitere Tweaks, **Deep Clean**, **Services Manager**, **Optimierungs-Score**, **Monitor-Berater** und die **Drift-Prüfung** sind portiert; 6 v1-Tweaks bewusst nicht (wirkungslos mit aktuellen Treibern/Windows)
- 🪟 **Windows 11 26H2:** neue Tweaks gegen die wieder installierte Copilot-App / Dev Home, Click to Do, Paint-/Notepad-KI und den neuen KI-Hostdienst; Recall und geräteinterne KI jetzt über die offiziellen Richtlinien
- 🧪 Nach dem ersten echten Einsatz: kein Konsolenfenster mehr, Endtest mit Rücknahme im Tuner, Energieplan/DNS als Entweder-oder, Drift-Dialog pro Tweak, mehrere falsch meldende Tweaks behoben — siehe CHANGELOG, Runde 10
- 🧪 389 automatische Prüfungen in 16 Test-Suiten (in `tests/`), inkl. PowerShell-Syntaxprüfung jedes Befehls

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
│   ├── nvtune_tuner.py       ← Auto-Tuner (OC, Power-Limit, V/F-Kurve, Speicher; TDR- + Fehlererkennung)
│   ├── vf_curve.py           ← Spannungs-Frequenz-Kurven-Optimierung
│   ├── hardware.py           ← WMI-Hardware-Erkennung
│   ├── tweaks.py             ← 106-Tweaks-Datenbank (Windows, Gaming, Network, Audio)
│   ├── network_test.py       ← Gateway/DNS-Ping-Latenztest
│   ├── system_cleaner.py     ← Sicherer Temp-/Junk-Cleaner + freiwilliger Deep Clean
│   ├── services.py           ← Services-Manager-Logik (merkt sich Original-Starttypen)
│   ├── optimization_score.py ← Optimierungs-Score + Drift-Prüfung
│   ├── display_info.py       ← Monitor-Berater (Bildwiederholrate)
│   ├── app_launch.py         ← Start ohne Konsolenfenster (pythonw)
│   ├── power_state.py        ← PC während Tune/Stresstest wach halten
│   ├── registry_backup.py    ← Exportiert betroffene Registry-Zweige als .reg
│   ├── startup_control.py    ← Autostart-Liste + an/aus (StartupApproved-Flags)
│   ├── restore_point.py      ← Wiederherstellungspunkt erstellen
│   ├── tweak_runner.py       ← PowerShell-Executor (versteckt)
│   ├── tweak_verifier.py     ← Registry-Verifizierung (100% Abdeckung)
│   ├── tweak_presets.py      ← 10 integrierte Presets
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
│   ├── ab_profile.py         ← Afterburner-Profil pro GPU + V/F-Kurven-Editor
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
    ├── startup_manager.py    ← Startup-Manager-Fenster
    ├── services_manager.py   ← Services-Manager-Fenster
    └── drift_dialog.py       ← Dialog „Tweaks nicht mehr aktiv“ (ein Haken pro Tweak)
tests/                        ← Windows-Testbatterie: python tests\run_all_tests.py
tools/
    └── ab_selftest.py        ← Afterburner-Selbsttest (info / dryrun / live / restore)
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
- **Dienste behalten ihre Vorgeschichte** — der ursprüngliche Starttyp wird gemerkt, bevor ein Dienst deaktiviert wird

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
