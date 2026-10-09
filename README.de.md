<div align="center">

# ⚡ GameOptimizerPro v2.0

**Windows & Gaming Optimizer v2.0 von FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 [English](README.md) | 🇩🇪 **Deutsch**

*All-in-one PC-Optimierungstool — GPU Auto-Tuner, Audio-Optimierung, Windows-Tweaks, BIOS-Guide und mehr.*

</div>

---

## ✨ Features

### 🖥 Oberfläche
- **Moderne dunkle Oberfläche mit CustomTkinter** — Seitenleiste mit Symbolen, abgerundete Karten, dunkle Titelleiste
- **Passt sich der Fensterbreite an** — Texte brechen um, Kartenraster ordnen sich in 1 bis 4 Spalten an (Preset-Liste, BIOS-Guide, Dashboard); nichts wird mehr bei festen Breiten abgeschnitten
- Das **Log des GPU-Tuners ist bei jeder Fenstergröße sichtbar**; Unterseiten wechseln über Umschaltleisten (das Mausrad blättert nicht mehr versehentlich Tabs um)
- Merkt sich Fenstergröße und -position; **Strg+1 … Strg+9** springen zu den Seiten; Seiten entstehen beim ersten Öffnen, ausgeblendete Seiten fragen keine Sensoren ab
- Die Optimizer-Liste hat ein **Suchfeld**; Zeilen werden unter dem Mauszeiger hervorgehoben, ein Klick auf die ganze Zeile setzt den Haken

### 🎮 GPU Auto-Tuner
- **2 Tune-Modi:** **Rundum** (Standard, siehe unten) und **Schnell (OC + UV)**. Die früheren Modi „Übertakten“ / „Undervolten“ decken die Rundum-Ziele *Max. Leistung* / *Effizienz* ab — je Spannungspunkt statt eines Offsets für die ganze Kurve, und als echtes Undervolting statt eines niedrigeren Power-Limits
- **Jedes Ergebnis in jeden Afterburner-Platz:** Rechtsklick auf einen Lauf im Tune-Verlauf (oder auf ein Profil, oder dessen Knopf „In Afterburner-Platz … ▾“) → Platz 1–5. Das Menü zeigt, was auf jedem Platz gerade liegt („Kurve · Speicher +1000 · Power 100 %“, „leer“), fragt vor dem Überschreiben, Platz 1 ist als deiner markiert; Afterburner startet kurz neu und wendet es an. Profile lassen sich **umbenennen** (Knopf oder Rechtsklick — der Tune-Verlauf findet sie unter dem alten Namen weiter)
- **Schnell (OC + UV, 20–45 min) — so sucht er:** erhöht den Core-Offset schrittweise (z. B. +15 MHz); bei einem Fehlschlag geht er auf den **letzten stabilen Wert zurück und halbiert die Schrittweite** (15 → 7 → 5 MHz) und landet so mit ±5 MHz Genauigkeit an der Stabilitätsgrenze. Das Power-Limit sinkt bis zum **niedrigsten Wert, der unter Volllast höchstens 3 % Leistung kostet**. Danach gehen **60 MHz vom gefundenen Offset ab** (ein einheitlicher Offset verschiebt auch die Spitze der Kurve, wo Spiele boosten). Ein 2-Minuten-Endtest plus der **Spiel-Endtest** (unten) prüfen genau das Profil, das gespeichert wird.
- **Rundum-Modus (neu, am gründlichsten — 50–80 min)** — nach dem Vorbild von Yuri „1usmus“ Bubliys HYDRA: statt eines Offsets für die ganze Kurve wird **jeder Spannungspunkt einzeln gemessen** (alle 25 mV — 50 mV ist wählbar und schneller — von der höchsten Spannung, die die Karte erreicht, bis 850 mV; Punkte unter der Mindestspannung der Karte unter Last werden nach einem Test übersprungen; die Kurve wird dort flach gesetzt, eine leichte Boost-Last hält die Karte genau auf dem Punkt, jedes Ergebnis wird geprüft; +15 MHz bis zum Fehler, dann halbiert bis 5 MHz; „Core max“ ist hier nur die Obergrenze je Punkt, 100 MHz über der Grenze der klassischen Modi). Aus den Punkten baut der Tuner **eine eigene V/F-Kurve** (**45 MHz Sicherheit, 60 MHz an den oberen Punkten**, wo Spiele boosten, +30 wo der Treiber neu starten musste oder die GPU hing), prüft sie unter FurMark, übertaktet den Speicher **mit der ganzen Karte unter Last** (FurMark und geprüfte Speicherkopien gleichzeitig: bei RTX 40 +500 → +1000 in 100er-Schritten, 100 MHz Sicherheit, wenn ein Schritt scheiterte), **vergleicht Kurven-Kappungen alle 25 mV per FurMark-2-Benchmark** und wählt nach deinem **Ziel**:
  - **Max. Leistung** — höchste Punktzahl (gleich schnell im Messrauschen: die sparsamere Einstellung; höheres Power-Limit nur, wenn die Karte bei Standard daran hing)
  - **Ausgewogen** — mindestens die Hälfte des gemessenen Gewinns, davon die meisten Punkte pro Watt
  - **Effizienz (Undervolt)** — Standard-Leistung (≥ 99 %) bei der geringsten Leistungsaufnahme

  Endtest: **5 Minuten FurMark plus 2 Minuten Last mit Rechenprüfung, danach der Spiel-Endtest**; bei einem Fehler ein gezielter Schritt zurück (nur die Punkte um die Spannung, bei der es scheiterte, oder Speicher −100 MHz) und erneut. Ein abgestürzter Benchmark-Kandidat führt zur Rücknahme und Neumessung aller Kandidaten; ein Benchmark, der viel zu früh endet oder weit unter Standard liegt (Treiber nach einem Absturz nicht sauber), stoppt den Tune mit „PC neu starten“. Am Ende ein **Bericht** (Log, Textdatei, Knopf „Bericht“): jeder Punkt gefunden → übernommen, jeder Kandidat mit Punkten/W, ein fairer **Vorher → Nachher**-Vergleich mit demselben Benchmark, Empfehlungen. Ohne gespeichertes Profil beginnt die Suche bei einem **vorsichtigen Startwert der Kartengeneration**. *Live auf einer RTX 4080: FurMark 7269 → 7538 Punkte (+3,7 %), Ø Takt 2790 → 2880 MHz, Kurve 1075 mV → 2940 MHz … 925 mV → 2560 MHz, Speicher +1000, Endtest bestanden. Runde 15 (Punkte alle 25 mV, Takt-Plus max. +350 je Punkt): 7415 → 7542 Punkte (+1,7 % — der Standard-Lauf lag 2 % höher als am Vortag; das getunte Ergebnis ist gleich, 7542 zu 7538), 2790 → 2880 MHz, 925 mV jetzt 2576 MHz (vorher an der Grenze 2560), 900–850 mV übersprungen (die Karte läuft unter dieser Last ≥ 925 mV), Speicher +1000, Endtest bestanden.*
- **Speicher-OC („Speicher mit übertakten“, in beiden Modi standardmäßig an):** dieselbe Stufe wie im Rundum-Modus — nach Core und Power-Limit startet der Speicher-Offset bei einem vorsichtigen Wert je Kartengeneration (+500 bei RTX 40) und steigt in 100er-Schritten bis „Mem Max“ (+1000 bei RTX 40), jeder Schritt mit **der ganzen Karte unter Last** (FurMark 2 und die geprüften Speicherkopien des Stress-Workers gleichzeitig, damit Fehler sofort auffallen). Übernommen: **der höchste bestandene Schritt minus 200 MHz**; sinkt die Bandbreite, obwohl der Takt steigt, wiederholt der Speicher schon fehlerhafte Übertragungen (EDC) — das gilt als Grenze; fällt der Endtest durch, geht der Speicher 100 MHz zurück. **Die Prüfung kann nicht verhungern:** Windows gibt dem Fenster vorne Vorrang auf der GPU — live gemessen: mit FurMark vorne fielen die geprüften Kopien von 244 auf 13 GB/s, also ein Vergleich alle ~8 s. Der Tuner startet FurMark deshalb ohne Fokus, verglichen wird mindestens zweimal pro Sekunde, und ein Schritt mit zu wenig GPU-Zeit für die Prüfung wird einmal wiederholt und erhöht den Speicher nie. Dauert etwa 6–10 Minuten länger. (Bis Runde 13 nahm diese Stufe das Bandbreiten-Maximum einer reinen Speicherlast — im Live-Lauf waren das +1500 MHz und grüne Stippen in FurMark.) *(Der Tuner enthält außerdem eine V/F-Kurven-Stufe — im GPU-Tab noch nicht auswählbar.)*
- **Spielähnliche Last bei der OC-Suche:** Dauer-Volllast hält die Karte am Power-Limit (~2500 MHz), Spiele stürzen aber am *Boost*-Punkt ab. Die OC-Schritte und der Endtest wechseln deshalb zwischen Volllast und halber Last, die den Hochtakt-/Hochspannungs-Punkt von Spielen erreicht (gemessen auf einer RTX 4080: 2790 MHz @ 1075 mV — der Punkt, an dem Spiele boosten)
- **Instabilität wird an falschen Ergebnissen erkannt, nicht erst am Absturz** — der Stress-Worker wiederholt dieselbe Matrix-Rechnung und vergleicht jedes Ergebnis mit dem ersten (Methode von gpu-burn / OCCT); ein einziger falscher Wert lässt den Schritt scheitern. Das Power-Limit zu erreichen gilt als normal; nur thermische / Hardware-Drosselung zählt als Grenze
- Automatisierter, schrittweiser Stabilitätstest mit Stress-Worker — **verweigert das Tunen ohne echte GPU-Last** (gemessen in der Baseline; ≥ 70 %), weil ein OC/UV-Test bei leerlaufender GPU instabile Werte als „stabil" speichern würde. GPU-Last liefert der Stress-Worker über `cupy` (`pip install "cupy-cuda12x[ctk]"` — `install.bat` bietet es an) oder ein parallel laufendes FurMark
- **Ein durchgefallener Endtest ist nicht das Ende:** Der Tuner nimmt einen Schritt zurück (Core, dann einen Speicher-Offset oder bei Hitze das Power-Limit) und testet erneut — gespeichert wird nur, was den Endtest bestanden hat. Während Tune und Stresstest bleibt der PC wach
- **Abbruch stoppt wirklich**: Der laufende Stress-Schritt endet sofort, die GPU geht auf Standard zurück (Offsets 0, Werks-Power-Limit), und danach wird nichts mehr angewendet; Beenden der App oder Sprachwechsel während eines Tunes tun dasselbe
- **Spiel-Endtest nach dem Endtest (beide Modi)** — was ein Spiel macht und Dauerlast-Tests nicht: 1 min Abkühlen mit den Einstellungen (eine kalte Karte fährt ihre Kurve höher), 5 min **Lastwechsel beim höchsten Takt** (Lastspitzen zufälliger Länge mit kurzen Pausen — dort sackt die Spannung ab), 4 min Boost-Punkt. Jedes Ergebnis geprüft; ein Fehler nimmt einen Schritt zurück und wiederholt den Endtest. *(Ein Spiel kann auch mit einem Profil hängen — D3D12 „device hung“ —, das jeden Dauerlast-Test bestanden hat; das hier fängt mehr davon ab.)*
- **Hänger-Erkennung:** Liefert eine Testlast 8 s keine Ergebnisse mehr, fällt der Schritt als „GPU hängt“ durch (zählte früher als bestanden, bis ein Treiber-Reset sie beendete)
- **GPU-Wächter:** bei jedem App-Start GPU-Hänger / Treiber-Resets seit dem Übernehmen des Profils (eigene Tunes und Stresstests ausgenommen) → „Entschärfen“, „Standard“ oder „Behalten“
- **Entschärfen** (Profile: Knopf oder Rechtsklick): eine Kopie mit Kurve / Takt −30 MHz und Speicher −200 MHz, danach das Slot-Menü zum Anwenden. Wer ein Profil anwendet, zu dem es so eine entschärfte Kopie gibt, wird vorher gefragt („die sichere nehmen?“)
- **Nur eine Instanz:** „Im Tray weiterlaufen“ versteckt das Fenster nur — ein zweiter Start holt jetzt die laufende App nach vorne, statt eine zweite daneben zu starten
- **Womit der PC startet:** Afterburner wendet bei jedem Windows-Start seinen eigenen Boot-Eintrag an
  (wenn „Übertaktung beim Systemstart anwenden“ an ist). Die App setzt ihn jetzt auf das Profil, das du
  anwendest; während ein Tune Schritte testet, steht dort dein bisheriges Profil (nie ein Testschritt),
  am Ende das gespeicherte. Nach dem Anwenden sagt der GPU-Tab, ob Afterburner es auch beim Windows-Start lädt
- TDR-Erkennung (GPU-Treiber-Timeout) über das Windows-Ereignisprotokoll — jede Sekunde eines Testschritts wird geprüft, bis zur letzten (ein Reset in den letzten Sekunden wurde früher dem nächsten Schritt angelastet)
- Crash Recovery — stellt beim nächsten Systemstart automatisch das letzte stabile Profil wieder her
- Live-Diagramm für Spannung/Takt/Temperatur während des Tunings
- Integration mit **MSI Afterburner** (MAHM Shared Memory für echte mV-Werte — der Parser folgt Afterburners dokumentiertem Layout; verbindet sich automatisch, wenn Afterburner später gestartet wird; ein Monitoring-Speicher, der nicht mehr aktualisiert wird — z. B. nachdem Afterburner abgeschossen wurde —, wird nach 8 s erkannt und verworfen statt eingefrorene Werte zu zeigen; GPU-Werte kommen zuerst aus NVML)
- Automatische GPU-Generationserkennung (Pascal → Blackwell / RTX 50) mit **vorsichtigen Startwerten und Obergrenzen je Generation**. AMD (RX 5000–9000) und Intel Arc werden erkannt, aber vom Tuner **nicht unterstützt** (er braucht Afterburners NVIDIA-V/F-Kurve und NVML) — der GPU-Tab sagt das und verweist auf das eigene Auto-Tuning von AMD Adrenalin bzw. der Intel Graphics Software, statt zu scheitern
- **Wendet Profile über Afterburners echtes Profil pro Grafikkarte an** (`Profiles\VEN_…cfg`, per PCI-ID der Karte ausgewählt): Core-/Speicher-Offset, Power-Limit und eine echte flache V/F-Kurve fürs Undervolting. Afterburner liest diese Datei nur beim Start, deshalb wird er beim Anwenden neuer Werte **kurz neu gestartet** (minimiert); gleiche Werte werden nur erneut gesendet. Die Originaldatei wird einmal pro Sitzung gesichert. *Stand: live verifiziert auf einer RTX 4080 mit Afterburner 4.6.6 — ein von der App geschriebenes Profil wurde von Afterburner übernommen (Power-Limit per NVML zurückgelesen), gleiche Werte ohne Neustart erneut angewendet, „Reset auf Standard“ funktionierte, und die Originaldatei kam Byte für Byte zurück. Komplette Tunes auf echter Hardware: OC + UV (Runde 10) und der Rundum-Tuner (Runde 13, siehe oben).* Lüfter-Einstellungen bleiben in Afterburner.

### ⚡ Stress Test
- **Interner Stabilitätstest** — eingebauter GPU/CPU-Stress-Worker mit einstellbarer Dauer und **Auto-Abbruch bei Max-Temperatur**; inkl. Dead-Man-Switch, damit nie ein verwaister 100%-CPU-Prozess zurückbleibt. Schlägt bei **falschen Ergebnissen (Rechenfehlern)**, **Worker-Absturz oder TDR** fehl, meldet die **durchschnittliche GPU-Last** und sagt klar „kein GPU-Stress" statt „bestanden", wenn die GPU nicht ausgelastet war (kein `cupy`); ein gestoppter Test liefert kein Ergebnis
- **FurMark 1 und FurMark 2** — gefunden neben der App, in den üblichen Installationsordnern oder dort, wohin du zeigst (bleibt nach einem Neustart gespeichert), mit Versionsanzeige; FurMark 2 bekommt seine eigene Kommandozeile (`--demo … --max-time …`) mit **Demo-Auswahl** (OpenGL / Vulkan, Knot), Auflösung inkl. deiner nativen und Dauer. **Standard: 8× Kantenglättung** — mit FPS-Limit oder im Treiber erzwungenem VSync/G-SYNC (normales Gaming-Setup) rendert FurMark sonst am Limit und lastet die GPU nur ~45 % aus; die App liest FurMarks eigene FPS/Last mit und sagt das
- **3DMark** — in jeder Steam-Bibliothek gefunden (oder als Standalone-Installation), Start über Steam; den Test wählst du in 3DMark (Stresstests per Kommandozeile gibt es nur in der Professional Edition)
- **Aufzeichnung während FurMark / 3DMark läuft** — Spitzentemperatur, durchschnittlicher und minimaler Takt unter Last, maximale Leistung und **Treiber-Resets (TDR)**, mit Zusammenfassung am Ende („kein Treiber-Reset“ / „nicht stabil!“)

### 🔊 Audio-Optimierung
- **Low-Latency-Audio-Tweaks** für Gaming — Audio-Verbesserungen deaktivieren, exklusive Audio-Sperre aufheben. Windows 11 (26H2) sperrt diese Geräte-Einstellungen in der Registry sogar für Administratoren — beide Tweaks gehen deshalb über die **Windows-Audio-API** (IPolicyConfig, wie die Sound-Systemsteuerung) und lesen den Wert danach zurück
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
- **107 Tweaks** in den Kategorien Windows, Gaming, Network, Audio (inkl. AMD-GPU-Tweaks)
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
- **Jede Desktop-Plattform seit Intel 8. Gen / Ryzen 1000** — 16 Plattformen: Ryzen 9000X3D / 9000 / 7000X3D / 7000 / 8000G (AM5), Ryzen 5000X3D / 5000 / APUs / 3000 / 1000–2000 (AM4), Core Ultra 200S, Core 12. / 13.–14. Gen, 10.–11. Gen, 8.–9. Gen, dazu die Grundlagen für alles andere (Laptops, Workstations)
- Die Hardware-Erkennung **wählt nur vor** — deine Plattform und deinen Board-Hersteller (ASUS / MSI / Gigabyte / ASRock); jede Plattform lässt sich öffnen
- Jede Einstellung mit dem **Menüpfad für deinen Board-Hersteller**, Standard- und Empfehlungswert, Risiko und Wirkung — und dem, was auf der Plattform zählt (EXPO 6000 + FCLK 2000 bei AM5, Curve Optimizer, der Microcode-0x12F-Fix für 13./14. Gen, Intel Default Settings, 200S Boost, X3D-Kernzuteilung, Secure Boot für Anti-Cheats …)
- **Live-Status nur, wo Windows es wirklich weiß** (grün = gesetzt, rot = noch offen, grau = nicht prüfbar): RAM-Profil (eingestellter Takt gegen die JEDEC-Obergrenze des DDR-Typs), Resizable BAR (BAR1-Fenster aus dem NVIDIA-Treiber), Secure Boot und CSM (UEFI-Zustand). Die alten Schätzungen (ReBAR aus HAGS, XMP aus „> 3200 MHz“, PBO aus dem Maximaltakt) sind raus

### 🩺 Diagnose
- **Health Report** — read-only-Übersicht dessen, was Windows in den letzten 30 Tagen schon protokolliert hat: WHEA-Hardwarefehler, Bluescreens, unerwartete Neustarts, GPU-Treiber-Timeouts (TDR), Datenträgerfehler, App-Abstürze — mit Schweregrad und letztem Auftreten
- **Remnant-Scan** — read-only-Erkennung von Resten *anderer* Tweak-Tools (WinRing0-/inpout-Treiber, ISLC, TimerResolution-Autostarts, Fremd-Energiepläne, Razer Cortex). Meldet nur — entfernt nichts

### 📊 Profil-Vergleich
- Vergleicht bis zu **4 gespeicherte GPU-Profile nebeneinander** danach, was sie **gegenüber Standard im selben Benchmark** bringen: Leistung (Punkte ggü. Standard) und Effizienz (Punkte pro Watt ggü. Standard), das beste markiert — dazu Takt (oberster Punkt der eigenen Kurve oder der Offset), Speicher, Power-Limit, Leistungsaufnahme im Test, Modus und Datum. Beide Tune-Modi messen das (je 60 s FurMark 2 bei Standard und mit dem Ergebnis)

### 📋 Tune-Verlauf (GPU-Tuner → Verlauf)
- Jeder Auto-Tune-Lauf (Datum, Modus, Core- und Speicher-Offset, Power, Spannung, Temperatur, Ergebnis); Standardwerte stehen als solche da (+0 MHz, 100 %)
- Läufe ohne Profil zeigen die zuletzt getesteten Werte und **warum** (Endtest nicht bestanden, abgebrochen, Treiber-Reset …)
- Klick auf einen Lauf zeigt sein Protokoll; **Rechtsklick: sein Profil in einen Afterburner-Platz** (1–5, mit dem, was dort gerade liegt); **Löschen** einzelner Läufe oder des ganzen Verlaufs (Protokoll + Rundum-Bericht; gespeicherte GPU-Profile bleiben)

### 🌡 Temperaturwarnung
- Windows-Toast-Benachrichtigung, wenn die GPU 90 °C erreicht
- 5 Minuten Abklingzeit zwischen Warnungen, konfigurierbares Limit

### 🔄 Updates von GitHub
- **Einstellungen → „Beim Start auf Updates prüfen“** (standardmäßig an) und **„Jetzt auf Updates prüfen“**
- Eine Version erkennt die App an der Build-Nummer in `build.json`. Eine neuere wird im Hintergrund geladen, geprüft und nach kurzer Frage installiert („Jetzt neu starten?“ — „Nein“ installiert beim nächsten Start; nie während eines Tunes): `tools/apply_update.py` wartet, bis die App beendet ist, **sichert jede ersetzte Datei** (`logs/update_backup_<Build>/`), kopiert die neuen Dateien, stellt bei einem Fehler den alten Stand wieder her und startet die App neu. `logs/` und `profiles/` werden nie angefasst
- Ein Git-Checkout wird per `git pull --ff-only` aktualisiert (nur ohne lokale Änderungen)

### 🌐 Sprachunterstützung
- **Englisch** (Standard) und **Deutsch** — Umschaltung per `EN/DE`-Button in der Titelleiste
- Sofortiger Wechsel, kein Neustart nötig

### 🔽 System-Tray
- Das X schickt die App in den Tray (Einstellungen → „Beim Schließen im Infobereich (Tray) weiterlaufen“ — aus: das X beendet sie); der Tray-Tooltip zeigt **live GPU-Temp / Takt / Spannung / Power**
- **Nach dem Tweaken / Tunen muss die App nicht laufen:** Die Tweaks sind Windows-Einstellungen, das GPU-Profil liegt in Afterburner — dort „Mit Windows starten“ und „Übertaktung beim Systemstart anwenden“ einschalten (Einstellungen → Afterburner-Einrichtung prüft beides). Bei geschlossener App gibt es keine 90-°C-Warnung und kein Tray-Menü
- Gespeicherte GPU-Profile schnell anwenden, GPU auf Stock zurücksetzen oder öffnen/beenden — alles aus dem Tray-Menü

### ⚙ Services Manager
- Seite in der Seitenleiste mit 29 selten benötigten Windows-Diensten (Telemetrie, Xbox, Fax, Karten, Hyper-V, der KI-Host aus 24H2/26H2 …) — Live-Status, Starttyp, Kategorie und Einstufung sicher/Vorsicht
- **Deaktivieren merkt sich den ursprünglichen Starttyp** (inkl. „Automatisch (verzögert)“), **Aktivieren stellt ihn wieder her** (oder den Windows-Standard) — nicht einfach „Manuell“
- Extra-Rückfrage bei Diensten, die eine Funktion abschalten (Druckwarteschlange, Windows Update, BITS, die Xbox-Dienste für Game-Pass-Spiele); ohne Admin-Rechte nur Anzeige; Link zu `services.msc`

### 🚀 Startup Manager
- Seite in der Seitenleiste mit allen Autostart-Einträgen — **Run-Keys (HKCU, HKLM, HKLM 32-Bit) und beide Autostart-Ordner** (Benutzer + alle Nutzer, `.lnk`-Ziele aufgelöst)
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
| **customtkinter** | Installiert `install.bat` (`requirements.txt`); fehlt es nach einem Update, bietet die App beim Start an, es zu installieren |
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
7. Prüfen: `python tools\ab_selftest.py info` (nur lesend)

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
- 🧠 **Speicher-OC im Auto-Tune** — Schritt für Schritt mit der ganzen Karte unter Last gesucht (ersetzt das feste Feld „Mem Offset“)
- 🎮 **Afterburner-Profile live auf echter Hardware verifiziert**; ein dabei gefundener echter Bug — eingefrorenes Monitoring nach einem Afterburner-Neustart — ist behoben; OC-Schritte laufen jetzt mit **spielähnlicher Wechsellast**
- 🔁 **v1-Parität ehrlich vervollständigt** — eine Prüfung zeigte, dass die frühere „volle Parität“ nicht stimmte: 18 weitere Tweaks, **Deep Clean**, **Services Manager**, **Optimierungs-Score**, **Monitor-Berater** und die **Drift-Prüfung** sind portiert; 6 v1-Tweaks bewusst nicht (wirkungslos mit aktuellen Treibern/Windows)
- 🪟 **Windows 11 26H2:** neue Tweaks gegen die wieder installierte Copilot-App / Dev Home, Click to Do, Paint-/Notepad-KI und den neuen KI-Hostdienst; Recall und geräteinterne KI jetzt über die offiziellen Richtlinien
- 🧪 Nach dem ersten echten Einsatz: kein Konsolenfenster mehr, Endtest mit Rücknahme im Tuner, Energieplan/DNS als Entweder-oder, Drift-Dialog pro Tweak, mehrere falsch meldende Tweaks behoben — siehe CHANGELOG, Runde 10
- 🖥 **Neue Oberfläche (CustomTkinter)** — Seitenleiste, Karten passen sich der Fensterbreite an, Tuner-Log immer sichtbar, Suche im Optimizer; Autostart- und Dienste-Manager sind jetzt Seiten
- 🔥 **FurMark 1/2 + 3DMark** mit Aufzeichnung von Temperatur, Takt, Leistung und Treiber-Resets während des Tests; FurMark-Pfad bleibt gespeichert
- 🔊 **Audio-Tweaks funktionieren unter Windows 11 26H2** — über die Windows-Audio-API statt gesperrter Registry-Schlüssel
- 🎯 **Rundum-Tuner** — eigene V/F-Kurve alle 25 mV Punkt für Punkt gemessen (nach HYDRA-Vorbild), Speicher mit der ganzen Karte unter Last geprüft (jetzt in allen Modi), Ziel-Schalter Max / Ausgewogen / Effizienz, 5-min-FurMark-Endtest und Vorher/Nachher-Bericht, Live-Werte während des ganzen Tunes; GPU-Tabelle mit RTX 50 und vorsichtigen Startwerten; AMD/Intel bekommen ein klares „nicht unterstützt“
- ❓ **Verständliche Tuner-Einstellungen:** jedes Feld des GPU-Tuners hat einen sprechenden Namen (z. B. „Takt-Plus max. je Punkt“, „Testdauer je Schritt“, „Abstand der Messpunkte“, „Sicherheitsabzug“) und ein **„?“**, das es erklärt (Deutsch / Englisch); der Rundum-Modus zeigt **Schritt für Schritt, wie der Tune abläuft — mit den aktuellen Werten**
- 🧹 **Runde 14 — schlanker:** Spiele-Profile, CPU-Pinning und die FPS-Messung entfernt (samt Hintergrund-Prozessüberwachung); der Tune-Verlauf sitzt jetzt im GPU-Tuner; Seitenwechsel **2–3× schneller** (Seiten bleiben gestapelt und werden im Hintergrund vorgebaut); **BIOS-Guide für jede Plattform** mit Menüpfaden je Board-Hersteller und ehrlichem Live-Status; **Updates von GitHub**; Schalter „Beim Schließen im Tray weiterlaufen“; die Afterburner-Einrichtung prüft „Mit Windows starten“ / „Beim Systemstart anwenden“
- 🎛 **Runde 15 — zwei Modi:** Rundum (Standard) und Schnell (OC + UV) statt vier; die nie angezeigten Modi FULL / nur V/F / nur Speicher und ihr Code sind weg. **Jedes Ergebnis in jeden Afterburner-Platz** aus dem Verlauf oder den Profilen (mit dem, was dort gerade liegt). Die **Punkte AB / NVML / MAHM erklären sich** beim Draufzeigen (blaues MAHM = Afterburner startet absichtlich neu). **Die Speicherprüfung kann nicht mehr verhungern** — im Live-Test gefunden: das FurMark-Fenster vorne bekam auf der GPU Vorrang, die geprüften Kopien fielen von 244 auf 13 GB/s; FurMark startet jetzt ohne Fokus, verglichen wird zweimal pro Sekunde, eine zu schwache Prüfung erhöht den Speicher nie. Treiber-Resets werden bis zur letzten Sekunde jedes Schritts gesucht; FurMark wird nach einem Stopp abgewartet; die letzten nur englischen Meldungen des GPU-Tuners sprechen jetzt auch Deutsch; der Nagle-Tweak meldet wegen eines unbenutzten Bluetooth-Adapters nicht mehr „nicht aktiv“. **Profile lassen sich umbenennen**, „Löschen“ hat einen Rahmen wie die anderen Knöpfe, der **Profilvergleich ist bei jedem Öffnen aktuell** (ein Tune nach dem Start fehlte), und die Listen zeigen **nur echte Profile** (language.json und die alte game_profiles.json im Profil-Ordner erschienen als Profil „Default“)
- 🛡 **Runde 16 — Tests, die finden, was ein Spiel findet:** weil ein Spiel auch mit einem Profil hängen kann (D3D12-„device hung“), das jeden Dauertest bestanden hat — Spiel-Endtest nach jedem Endtest (Abkühlen, Lastwechsel beim höchsten Takt, Boost-Punkt), Hänger-Erkennung, größere Abzüge (45 / 60 oben; Schnell −60), Speicher −200 mit EDC-Prüfung, GPU-Wächter beim App-Start, „Entschärfen“ mit einem Klick, und jedes angewendete Profil wird vermerkt (die App holte beim nächsten Start sonst ein älteres zurück)
- 🧪 1052 automatische Prüfungen in 28 Test-Suiten (in `tests/`), inkl. PowerShell-Syntaxprüfung jedes Befehls, der ganzen Oberfläche unter echter Hauptschleife (auf einem unsichtbaren Desktop — läuft auch, während du spielst), des Rundum-Tuners gegen eine simulierte Karte und des Updaters gegen Testordner

Vollständige Details in [CHANGELOG.md](CHANGELOG.md).

## 🚀 Erste Schritte

1. **Optimizer** in der Seitenleiste öffnen → **„Status prüfen“** zeigt, welche Tweaks schon aktiv sind (● geprüft aktiv, ◑ angewendet, nicht bestätigt, ○ inaktiv)
2. Das **🎮 Gaming-Preset** anwenden für eine schnelle All-in-One-Optimierung
3. Die **Audio-Tweaks** unter **Optimizer → Audio** finden — Low-Latency-Audio-Tweaks aktivieren
4. Den **BIOS-Guide** prüfen — erkennt deine Hardware und zeigt an, was geändert werden sollte
5. Falls Afterburner läuft, den **GPU-Tuner** ausprobieren → **Rundum**, Ziel *Ausgewogen* (50–80 min) — oder **Schnell (OC + UV)** für einen Lauf von 20–45 Minuten

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
│   ├── nvtune_tuner.py       ← Auto-Tuner: Rundum (eigene V/F-Kurve) + Schnell (OC + UV), Speicher; TDR- + Fehlererkennung
│   ├── curve_tune.py         ← Rundum-Logik: Punktsuche, Sicherheitsabzug, Ziele, Bericht
│   ├── hardware.py           ← WMI-Hardware-Erkennung
│   ├── tweaks.py             ← 107-Tweaks-Datenbank (Windows, Gaming, Network, Audio)
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
│   ├── bios_guide.py         ← BIOS-Guide: 16 Plattformen, Menüpfade je Board-Hersteller
│   ├── bios_detector.py      ← Was Windows weiß (RAM-Profil, ReBAR, Secure Boot, CSM)
│   ├── health_report.py      ← 30-Tage Windows-Health-Report
│   ├── remnant_detector.py   ← Erkennung von Tweak-Tool-Resten
│   ├── crash_recovery.py     ← TDR-Erkennung, Crash-Flag-System
│   ├── temp_monitor.py       ← GPU-Temperatur-Toast-Benachrichtigungen
│   ├── updater.py            ← Updates von GitHub (build.json, Download, git pull)
│   ├── export_import.py      ← .nextune Export/Import
│   ├── tune_history.py       ← Tune-Log-Parser
│   ├── startup_loader.py     ← Autostart + Startprofil-Loader
│   ├── gpu_defaults.py       ← GPU-Generationen-Standardwerte-Tabelle
│   ├── app_settings.py       ← Kleine dauerhafte Einstellungen (logs/settings.json)
│   ├── audio_policy.py       ← Audio-Geräteeinstellungen über die Windows-Audio-API
│   ├── furmark.py            ← FurMark-1/2-Erkennung + Kommandozeile
│   ├── threedmark.py         ← 3DMark-Erkennung (Steam-Bibliotheken) + Start
│   ├── mahm_reader.py        ← MSI-Afterburner-Shared-Memory-Reader
│   ├── ab_profile.py         ← Afterburner-Profil pro GPU + V/F-Kurven-Editor
│   └── i18n.py               ← EN/DE-Sprachmodul
└── ui/
    ├── main_window.py        ← Hauptfenster: Seitenleiste, Seiten bei Bedarf, Statusleiste
    ├── theme.py              ← Farben, Schriften, Symbole, CustomTkinter-Vorgaben
    ├── components.py         ← Bausteine (Karten, umbrechende Texte, Raster, Log, Tabellen …)
    ├── tab_dashboard.py      ← Systemübersicht + Live-GPU-Telemetrie
    ├── tab_optimizer.py      ← Windows-Optimizer mit Sidebar (inkl. Audio-Tweaks)
    ├── tab_gpu.py            ← GPU-Tuner-UI
    ├── tab_stress.py         ← Stresstest, FurMark 1/2 + 3DMark, Aufzeichnung externer Tests
    ├── tab_compare.py        ← Profilvergleich
    ├── tab_bios.py           ← BIOS-Guide mit Live-Erkennung
    ├── tune_history_view.py  ← Tune-Verlauf (Ansicht im GPU-Tuner)
    ├── update_flow.py        ← Update-Prüfung / -Frage (Start + Einstellungen)
    ├── tab_diagnose.py       ← Health-Report + Remnant-Scan
    ├── tab_settings.py       ← Autostart, Setup-Checker, Über
    ├── live_graph.py         ← Rollierendes Spannungs-/Takt-/Temperatur-Diagramm
    ├── startup_manager.py    ← Autostart-Manager (Seite)
    ├── services_manager.py   ← Dienste-Manager (Seite)
    └── drift_dialog.py       ← Dialog „Tweaks nicht mehr aktiv“ (ein Haken pro Tweak)
tests/                        ← Windows-Testbatterie: python tests\run_all_tests.py
tools/
    ├── ab_selftest.py        ← Afterburner-Selbsttest (info / dryrun / live / restore)
    └── apply_update.py       ← Spielt ein geladenes Update ein (Sicherung, Rücknahme, Neustart)
build.json                    ← Build-Nummer dieser Version (der Updater vergleicht sie)
```

---

## ⚙️ Architektur

```
Main-Thread   → CustomTkinter/tkinter mainloop() — einziger Thread, der die UI anfasst
Thread 2      → pystray.run() — System-Tray-Icon
Thread 3      → GPU-Stats-Loop (4s Intervall)
Thread 4      → Startup (Crash-Check + Profil-Laden)
Thread 5      → Menü-Refresh (20s Intervall)
Thread 6      → Game-Prozess-Monitor (3s Intervall, psutil)
Thread 7      → Temperatur-Monitor (10s Intervall)
Thread 8+     → Auto-Tune-Stages, Stress-Worker-Subprozess
```

Thread-übergreifende Kommunikation läuft über `widget.after(0, callback)` oder eine Warteschlange, die der Main-Thread abfragt (Log-Ansichten, `ui.components.run_async`) — Tk darf nur vom Main-Thread angefasst werden.

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
