# GameOptimizerPro v2.1 — alle Funktionen

🇬🇧 [English](FEATURES.md) | 🇩🇪 **Deutsch** · [← zurück zur README](../README.de.md)

Alles, was die App macht, im Detail. Zitierte Ergebnisse aus Live-Läufen stammen von einer Testkarte; jede Karte ist anders.

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
- **Schnell (OC + UV, 40–70 min) — so sucht er:** erhöht den Core-Offset schrittweise (z. B. +15 MHz); bei einem Fehlschlag geht er auf den **letzten stabilen Wert zurück und halbiert die Schrittweite** (15 → 7 → 5 MHz) und landet so mit ±5 MHz Genauigkeit an der Stabilitätsgrenze. Das Power-Limit sinkt bis zum **niedrigsten Wert, der unter Volllast höchstens 3 % Leistung kostet**. Danach gehen **60 MHz vom gefundenen Offset ab** (ein einheitlicher Offset verschiebt auch die Spitze der Kurve, wo Spiele boosten). Ein 2-Minuten-Endtest plus der **Spiel-Endtest** (unten) prüfen genau das Profil, das gespeichert wird.
- **Rundum-Modus (am gründlichsten — 70–105 min)** — nach dem Vorbild von Yuri „1usmus“ Bubliys HYDRA: statt eines Offsets für die ganze Kurve wird **jeder Spannungspunkt einzeln gemessen** (alle 25 mV — 50 mV ist wählbar und schneller — von der höchsten Spannung, die die Karte erreicht, bis 850 mV; Punkte unter der Mindestspannung der Karte unter Last werden nach einem Test übersprungen, und diese Mindestspannung wird pro Karte gespeichert — der nächste Tune plant seine Punkte nur bis dorthin; die Kurve wird dort flach gesetzt, eine leichte Boost-Last hält die Karte genau auf dem Punkt, die letzten 15 s jedes Schritts sind **Lastwechsel** an diesem Punkt (dort scheitern knappe Punkte — live scheiterte ein Punkt, den die gleichmäßige Last allein gefunden hatte, unter 3D + Encoder + Lastwechseln ~100 MHz tiefer), jedes Ergebnis wird geprüft; +15 MHz bis zum Fehler, dann halbiert bis 5 MHz; „Core max“ ist hier nur die Obergrenze je Punkt, 100 MHz über der Grenze der klassischen Modi). Aus den Punkten baut der Tuner **eine eigene V/F-Kurve** (**45 MHz Sicherheit, 60 MHz an den oberen Punkten**, wo Spiele boosten, +30 wo der Treiber neu starten musste oder die GPU hing), prüft sie unter FurMark, übertaktet den Speicher **mit der ganzen Karte unter Last** (FurMark und geprüfte Speicherkopien gleichzeitig: bei RTX 40 +500 → +1000 in 100er-Schritten; übernommen: höchster bestandener Schritt minus 200 MHz), **vergleicht Kurven-Kappungen alle 25 mV per FurMark-2-Benchmark** (Ausgewogen und Effizienz: dazu eine Feinsuche in der Mitte zur Nachbar-Kappung) und wählt nach deinem **Ziel**:
  - **Max. Leistung** — höchste Punktzahl (gleich schnell im Messrauschen: die sparsamere Einstellung; höheres Power-Limit nur, wenn die Karte bei Standard daran hing)
  - **Ausgewogen** — Leistung **und** Effizienz über Standard, beides so gleichmäßig wie möglich (es zählt der kleinere der beiden Gewinne); ist keine Einstellung in beidem besser: mindestens die Hälfte des gemessenen Gewinns, davon die meisten Punkte pro Watt
  - **Effizienz (Undervolt)** — Standard-Leistung (≥ 99 %) bei der geringsten Leistungsaufnahme; danach sinkt das **Power-Limit** so weit, wie die Kurve unter der Rechenlast noch Standard-Leistung bringt (die hängt wie 3DMark und schwere Spiele am Power-Limit — dort spart die Kurve allein kaum; live: 3DMark am Power-Limit, die Kurvenprofile brauchten 313–315 W wie Standard mit 316 W, ein Limit von 95 % 299 W)

  Endtest: **5 Minuten FurMark plus 2 Minuten Last mit Rechenprüfung, danach der Spiel-Endtest**; bei jedem Fehler läuft derselbe Test noch einmal mit Speicher auf Standard — scheitert er wieder, liegt es an der Kurve (die Punkte um die Spannung, bei der es scheiterte, −15 MHz), besteht er, am Speicher (−100 MHz). Der nächste Versuch beginnt mit dem gescheiterten Test (Minuten statt einer halben Stunde); besteht er, laufen alle Endtests noch einmal am Stück — gespeichert wird nur, was alle bestanden hat (bis zu 12 Versuche). Ein abgestürzter Benchmark-Kandidat führt zur Rücknahme und Neumessung aller Kandidaten; ein Benchmark, der viel zu früh endet oder weit unter Standard liegt (Treiber nach einem Absturz nicht sauber), stoppt den Tune mit „PC neu starten“. Am Ende ein **Bericht** (Log, Textdatei, Knopf „Bericht“): jeder Punkt gefunden → übernommen, jeder Kandidat mit Punkten/W, ein fairer **Vorher → Nachher**-Vergleich mit demselben Benchmark, Empfehlungen. Ohne gespeichertes Profil beginnt die Suche bei einem **vorsichtigen Startwert der Kartengeneration**. *Live auf einer Testkarte (RTX-40-Serie): FurMark 7269 → 7538 Punkte (+3,7 %), Ø Takt 2790 → 2880 MHz, Kurve 1075 mV → 2940 MHz … 925 mV → 2560 MHz, Speicher +1000, Endtest bestanden. Runde 15 (Punkte alle 25 mV, Takt-Plus max. +350 je Punkt): 7415 → 7542 Punkte (+1,7 % — der Standard-Lauf lag 2 % höher als am Vortag; das getunte Ergebnis ist gleich, 7542 zu 7538), 2790 → 2880 MHz, 925 mV jetzt 2576 MHz (vorher an der Grenze 2560), 900–850 mV übersprungen (die Karte läuft unter dieser Last ≥ 925 mV), Speicher +1000, Endtest bestanden.*
- **Speicher-OC („Speicher mit übertakten“, in beiden Modi standardmäßig an):** dieselbe Stufe wie im Rundum-Modus — nach Core und Power-Limit startet der Speicher-Offset bei einem vorsichtigen Wert je Kartengeneration (+500 bei RTX 40) und steigt in 100er-Schritten bis „Mem Max“ (+1000 bei RTX 40), jeder Schritt mit **der ganzen Karte unter Last** (FurMark 2 und die geprüften Speicherkopien des Stress-Workers gleichzeitig, damit Fehler sofort auffallen). Übernommen: **der höchste bestandene Schritt minus 200 MHz**; sinkt die Bandbreite, obwohl der Takt steigt, wiederholt der Speicher schon fehlerhafte Übertragungen (EDC) — das gilt als Grenze; fällt der Endtest durch, geht der Speicher 100 MHz zurück. **Die Prüfung kann nicht verhungern:** Windows gibt dem Fenster vorne Vorrang auf der GPU — live gemessen: mit FurMark vorne fielen die geprüften Kopien von 244 auf 13 GB/s, also ein Vergleich alle ~8 s. Der Tuner startet FurMark deshalb ohne Fokus, verglichen wird mindestens zweimal pro Sekunde, und ein Schritt mit zu wenig GPU-Zeit für die Prüfung wird einmal wiederholt und erhöht den Speicher nie. Dauert etwa 6–10 Minuten länger. (Bis Runde 13 nahm diese Stufe das Bandbreiten-Maximum einer reinen Speicherlast — im Live-Lauf waren das +1500 MHz und grüne Stippen in FurMark.) *(Der Tuner enthält außerdem eine V/F-Kurven-Stufe — im GPU-Tab noch nicht auswählbar.)*
- **Spielähnliche Last bei der OC-Suche:** Dauer-Volllast hält die Karte am Power-Limit (~2500 MHz), Spiele stürzen aber am *Boost*-Punkt ab. Die OC-Schritte und der Endtest wechseln deshalb zwischen Volllast und halber Last, die den Hochtakt-/Hochspannungs-Punkt von Spielen erreicht (gemessen auf der Testkarte: 2790 MHz @ 1075 mV — der Punkt, an dem Spiele boosten)
- **Instabilität wird an falschen Ergebnissen erkannt, nicht erst am Absturz** — der Stress-Worker wiederholt dieselbe Matrix-Rechnung und vergleicht jedes Ergebnis mit dem ersten (Methode von gpu-burn / OCCT); ein einziger falscher Wert lässt den Schritt scheitern. Das Power-Limit zu erreichen gilt als normal; nur thermische / Hardware-Drosselung zählt als Grenze
- Automatisierter, schrittweiser Stabilitätstest mit Stress-Worker — **verweigert das Tunen ohne echte GPU-Last** (gemessen in der Baseline; ≥ 70 %), weil ein OC/UV-Test bei leerlaufender GPU instabile Werte als „stabil" speichern würde. GPU-Last liefert der Stress-Worker über `cupy` (`pip install "cupy-cuda12x[ctk]"` — `install.bat` bietet es an) oder ein parallel laufendes FurMark
- **Ein durchgefallener Endtest ist nicht das Ende:** Der Tuner sucht die Ursache (der gescheiterte Test noch einmal mit Speicher auf Standard, mindestens doppelt so lange, wie es bis zum Fehler dauerte: Takt oder Speicher?), nimmt genau dort einen Schritt zurück (bei Hitze das Power-Limit) und testet erneut — gespeichert wird nur, was den Endtest bestanden hat. Die Endtests laufen die empfindlichsten zuerst (Rechenprüfung, Härtetest, Spiel-Endtest, dann FurMark). Ein von Hand geschlossenes FurMark-Fenster wiederholt diesen Lauf einmal, statt den Tune zu beenden.
- **Pro Karte gelernt:** Ein Punkt, der in einem Endtest scheiterte, wird gemerkt (mit dem Takt, der scheiterte) — der nächste Tune setzt ihn einen Schritt tiefer an, sein Lastwechsel-Check bestätigt es, und die Suche steigt nicht mehr über das, was ohnehin gekappt würde (genau dort kamen die Treiber-Resets); *GPU-Seite → Vergessen* nach einer Reinigung, neuer Wärmeleitpaste oder einem neuen Treiber. Drücken die Rücknahmen das Profil unter sein Ziel (Effizienz: 99 % der Standard-Leistung), sagt es der Bericht. Vor dem Start warnt ein **Vorab-Check** vor einer ausgelasteten GPU oder einem Treiber-Fehler in der letzten Stunde; während des Tunes zeigt die GPU-Seite die **Restzeit** (sie lernt die Zeit je Punkt unterwegs). Gab es während eines Tunes Treiber-Resets, sagt die App am Ende: **vor dem Spielen neu starten** (Log und Tray). Während Tune und Stresstest bleibt der PC wach
- **Abbruch stoppt wirklich**: Der laufende Stress-Schritt endet sofort, die GPU geht auf Standard zurück (Offsets 0, Werks-Power-Limit), und danach wird nichts mehr angewendet; Beenden der App oder Sprachwechsel während eines Tunes tun dasselbe
- **Spiel-Endtest nach dem Endtest (beide Modi)** — was ein Spiel macht und Dauerlast-Tests nicht: 1 min Abkühlen mit den Einstellungen (eine kalte Karte fährt ihre Kurve höher), 5 min **Lastwechsel beim höchsten Takt** (Lastspitzen zufälliger Länge mit kurzen Pausen — dort sackt die Spannung ab), 4 min Boost-Punkt. Jedes Ergebnis geprüft; ein Fehler nimmt einen Schritt zurück und wiederholt den Endtest. *(Ein Spiel kann auch mit einem Profil hängen — D3D12 „device hung“ —, das jeden Dauerlast-Test bestanden hat; das hier fängt mehr davon ab.)*
- **Mit Video-Encoder daneben testen (beide Modi, standardmäßig an, keine Extra-Zeit):** jeder Stabilitätsschritt — jeder Kurvenpunkt, die OC-Schritte, Endtest und Spiel-Endtest — läuft mit der Encoder-Last (NVENC, 60 Bilder/s) daneben; ein falsches Bild, ein hängender Encoder oder ein falsches Ergebnis lässt den Schritt durchfallen. *Warum: Eine mit Einzellasten gefundene Kurve rechnete mit dem Encoder daneben nach Minuten falsch — wegen der Kern-Kurve, nicht wegen der Speicher-Übertaktung, und auf Standard nie.* Messung auf Standard, Power-Limit-Schritte und Benchmarks laufen ohne sie, damit die Leistungswerte vergleichbar bleiben. Ohne NVENC laufen die Schritte wie bisher
- **Härtetest am Ende (beide Modi, +13 min, standardmäßig an):** nach dem Spiel-Endtest mehrere Lasten gleichzeitig — 3D (FurMark), der Video-Encoder (NVENC), Rechnen und Speicher — wie ein Spiel, das aufgenommen oder gestreamt wird (siehe *Stress Test*). Seine härteste Phase (Spiel + Aufnahme + Rechnen, 150 s) eröffnet schon die Endtests als **Lastwechsel-Check**: Knappe Einstellungen scheitern dort am ehesten, ein Fehler kostet so nur Minuten. Ein Fehler wird mit Speicher auf Standard gegengeprüft und senkt dann entweder die Punkte um die Fehlerspannung um einen Schritt (Spannung unbekannt: die ganze Kurve; Schnell: den Takt-Offset) oder den Speicher, wie bei jedem anderen Fehler. Danach im Rundum-Modus der Nachher-Benchmark — immer ganz am Ende, mit genau dem Profil, das gespeichert wird
- **Hänger-Erkennung:** Liefert eine Testlast 8 s keine Ergebnisse mehr, fällt der Schritt als „GPU hängt“ durch (zählte früher als bestanden, bis ein Treiber-Reset sie beendete)
- **GPU-Wächter:** bei jedem App-Start GPU-Hänger / Treiber-Resets seit dem Übernehmen des Profils (eigene Tunes und Stresstests ausgenommen) → „Entschärfen“, „Standard“ oder „Behalten“
- **Flugschreiber + Live-Wächter:** solange die App läuft (Fenster oder Tray), werden Takt, Spannung, Leistung, Temperatur und Auslastung einmal pro Sekunde aufgezeichnet (die letzte Minute auch auf der Platte — ein Absturz, der den PC neu startet, hinterlässt sie), und das Ereignisprotokoll wird alle paar Sekunden gelesen. Ein GPU-Hänger im Spiel gibt eine Windows-Benachrichtigung — kein Fenster über dem Spiel; der Dialog kommt, wenn du wieder in der App bist. Er nennt den Zustand kurz vor dem Hänger (z. B. „1050 mV / 2880 MHz“) und bietet an, **nur die betroffenen Kurvenpunkte** um 30 MHz zu senken; hakt es an denselben Punkten erneut, wird das ganze Profil entschärft. Ein unerwarteter Neustart zählt nur, wenn die Karte bis zum Ende der Aufzeichnung unter Last war. Wo Spiele gehakt haben, hält der nächste Tune 30 MHz mehr Abstand
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
- **Wendet Profile über Afterburners echtes Profil pro Grafikkarte an** (`Profiles\VEN_…cfg`, per PCI-ID der Karte ausgewählt): Core-/Speicher-Offset, Power-Limit und eine echte flache V/F-Kurve fürs Undervolting. Afterburner liest diese Datei nur beim Start, deshalb wird er beim Anwenden neuer Werte **kurz neu gestartet** (minimiert); gleiche Werte werden nur erneut gesendet. Die Originaldatei wird einmal pro Sitzung gesichert. *Stand: live verifiziert auf einer RTX-40-Karte mit Afterburner 4.6.6 — ein von der App geschriebenes Profil wurde von Afterburner übernommen (Power-Limit per NVML zurückgelesen), gleiche Werte ohne Neustart erneut angewendet, „Reset auf Standard“ funktionierte, und die Originaldatei kam Byte für Byte zurück. Komplette Tunes auf echter Hardware: OC + UV (Runde 10) und der Rundum-Tuner (Runde 13, siehe oben).* Lüfter-Einstellungen bleiben in Afterburner.

### ⚡ Stress Test
- **Härtetest — wie Spielen mit Aufnahme / Stream** (10 / 20 / 45 min): mehrere Lasten gleichzeitig in Kombinationen, die alle 2,5 min wechseln — 3D (FurMark: OpenGL / Vulkan, leicht wie ein Spiel mit FPS-Limit und schwer mit 8x MSAA), der **Video-Encoder** (NVENC, H.264 mit 60 Bildern/s, jedes Bild vorher per CUDA gezeichnet und skaliert, wie OBS mit „GPU-Skalierung“), geprüfte Lastwechsel oben auf der Kurve und geprüfte Speicherkopien. Eine kurze Leerlauf-Pause zwischen den Phasen zwingt die Karte, aus dem Leerlauf hochzuschalten, während alles gleichzeitig startet. Jedes Rechenergebnis und jedes umgerechnete Bild wird geprüft; eine Last, die nicht mehr antwortet, ist eine hängende GPU; das Systemprotokoll wird alle 2 s gelesen. Getestet wird das gerade aktive Profil, geändert wird nichts — nach einem Fehler nennt er die Phase und den Zustand kurz davor und bietet an, **nur die betroffenen Kurvenpunkte** zu entschärfen. *Warum: Ein Profil kann jeden Einzeltest bestehen und trotzdem falsch rechnen, wenn der Encoder daneben läuft — gemessen in etwa einem von vier 25-s-Läufen, auf Standard nie.* Die Encoder-Last nutzt die `nvEncodeAPI64.dll` des Treibers (kein Zusatzpaket); ohne NVENC läuft der Test ohne diesen Teil. Die Lasten enden auf Anfrage, nicht per Abbruch: GPU-Arbeit hart zu beenden, während ein anderes Programm encodiert, lässt den Treiber selbst ein nvlddmkm 153 protokollieren
- **Interner Stabilitätstest** — eingebauter GPU/CPU-Stress-Worker mit einstellbarer Dauer und **Auto-Abbruch bei Max-Temperatur**; inkl. Dead-Man-Switch, damit nie ein verwaister 100%-CPU-Prozess zurückbleibt. Schlägt bei **falschen Ergebnissen (Rechenfehlern)**, **Worker-Absturz oder TDR** fehl, meldet die **durchschnittliche GPU-Last** und sagt klar „kein GPU-Stress" statt „bestanden", wenn die GPU nicht ausgelastet war (kein `cupy`); ein gestoppter Test liefert kein Ergebnis
- **FurMark 1 und FurMark 2** — gefunden neben der App, in den üblichen Installationsordnern oder dort, wohin du zeigst (bleibt nach einem Neustart gespeichert), mit Versionsanzeige; FurMark 2 bekommt seine eigene Kommandozeile (`--demo … --max-time …`) mit **Demo-Auswahl** (OpenGL / Vulkan, Knot), Auflösung inkl. deiner nativen und Dauer. **Standard: 8× Kantenglättung** — mit FPS-Limit oder im Treiber erzwungenem VSync/G-SYNC (normales Gaming-Setup) rendert FurMark sonst am Limit und lastet die GPU nur ~45 % aus; die App liest FurMarks eigene FPS/Last mit und sagt das
- **3DMark** — in jeder Steam-Bibliothek gefunden (oder als Standalone-Installation), Start über Steam; den Test wählst du in 3DMark (Stresstests per Kommandozeile gibt es nur in der Professional Edition)
- **3DMark-Vergleich der Profile** — die Profile anhaken, die in Afterburner-Plätzen liegen: Die App aktiviert eins nach dem anderen (Standard zuletzt, in einem geliehenen Platz, der danach zurückkommt), wartet, bis die Karte höchstens 45 °C hat, du startest den Test in 3DMark (z. B. Speed Way, Demo aus), die App liest jedes Ergebnis selbst ein (die Grafik-Wertung), misst den Strom, während die Karte ausgelastet ist, und bucht beides auf das aktive Profil — je zwei oder drei Läufe; am Ende ist das Profil von vorher wieder aktiv, und der Profilvergleich zeigt *3DMark … ggü. Standard*
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
- **Der eigene Zustand der App ist absturzsicher:** Einstellungen, die angewendeten Tweaks (darauf baut *Zurücksetzen* auf), die geänderten Dienste, Profile und die Listen des Wächters werden atomar mit letzter guter Kopie (`.bak`) geschrieben; eine Datei, die kurz nicht lesbar ist (Virenscanner beim Start), wird nie überschrieben, eine kaputte aus der Kopie wiederhergestellt. Unerwartete Fehler landen in `logs/app_errors.log` (die App hat keine Konsole). Die Stresslasten der App (Worker, FurMark eines Tunes / Härtetests) laufen in einem Windows-Job: Sie enden mit der App, auch nach einem Absturz

### 🛠 Windows Optimizer
- **109 Tweaks** in den Kategorien Windows, Gaming, Network, Audio (inkl. AMD-GPU-Tweaks)
- **Netzwerkadapter-Einstellungen:** Energy-Efficient Ethernet aus und Interrupt Moderation aus — nur an physischen LAN-Adaptern und nur mit den Schlüsselwörtern, die der Treiber selbst anbietet (jeder Hersteller nennt sie anders); der vorherige Wert wird gemerkt und beim Revert zurückgeschrieben. Kein Verbindungsabbruch beim Anwenden, wirkt nach einem Neustart
- **Ehrlicher Timer-Tweak:** *Timer-Anfragen systemweit gelten lassen* (`GlobalTimerResolutionRequests`) stellt unter Windows 11 die systemweite Wirkung der Timer-Anfrage eines Programms wieder her — er setzt selbst keine Auflösung (das braucht ein laufendes Programm) und sagt das auch
- **Windows 11 24H2/26H2 — KI & Bloat:** Recall (Richtlinie + Entfernen der Komponente), Click to Do, Paint-KI (Cocreator, Image Creator, generatives Füllen/Löschen), Notepad-KI, geräteinterne Text-/Bildgenerierung, der KI-Hostdienst (`WSAIFabricSvc`) und das Entfernen der Microsoft-365-Copilot-App / Dev Home, die Funktionsupdates wieder installieren — über Microsofts dokumentierte Richtlinien, wo es sie gibt
- **Speicher & RAM:** lange Pfade, reservierter Speicher, Auslagerungsdatei, Speicherkomprimierung, SSD-TRIM, geplante Defragmentierung, NVMe-Queue-Tiefe (nur mit NVMe-Laufwerk angeboten), Schreibcache-Leerung (fortgeschritten), dazu eine einmalige **sichere Datenträgerbereinigung** (kein Downloads-Ordner, kein Papierkorb, kein Windows.old)
- **Drift-Prüfung beim Start:** Tweaks, die du angewendet hast und die ein Windows-Update zurückgesetzt hat, werden mit je einem Haken aufgelistet — mit Haken erneut anwenden (vorher Registry-Backup), ohne Haken nicht mehr nachfragen; „Später“ fragt beim nächsten Start wieder
- **Entweder-oder:** nur ein Energieplan und ein DNS-Anbieter wählbar („⇄ entweder-oder“); ein Haken nimmt den anderen weg, und die Höchstleistungs-Pläne schalten im Netzbetrieb weder Bildschirm noch PC ab
- **Immer nur ein Durchlauf gleichzeitig**, mit sichtbarem Fortschritt bei langen Tweaks (die Datenträgerbereinigung dauert Minuten); Mausrad funktioniert über der ganzen Liste
- Live-Statusverifizierung — liest den tatsächlichen Registry-/Dienst-Zustand (nicht nur die JSON-Datei), alle Prüfungen wenige Sekunden nach dem Start; Gruppen-Überschriften, Preset-Karten („x/n aktiv“) und die Preset-Vorschau zählen, was auf dem System aktiv ist — auch wenn es außerhalb der App gesetzt wurde
- **Snapshot & Vergleich:** speichert den Zustand aller Tweaks (z. B. vor einem Windows-Update) und listet später jeden Tweak, der sich seitdem geändert hat — der Snapshot bleibt über einen Neustart erhalten
- **App-Entfernungen** sind markiert („🗑 entfernt Apps“) und bekommen vorher einen Wiederherstellungspunkt — das Einzige, was *Alles zurücksetzen* nicht zurückholt; reine Windows-11-Tweaks (Taskleiste, Start, Explorer) sind unter Windows 10 ausgeblendet
- 3-stufige Statusanzeige: ● Grün (verifiziert aktiv) / ◑ Amber (angewendet, ungeprüft) / ○ Grau (inaktiv)
- **Abgestufte Ein-Klick-Presets — 🟢 Minimal → 🟡 Mittel → 🔴 Hart (Debloat)** — kumulative Intensitätsstufen, die ein kuratiertes, ansteigendes Tweak-Set anwenden
- **10 integrierte Presets:** die 3 Intensitätsstufen + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, Alle sicheren Tweaks
- **AMD-GPU-Tweaks** — ULPS deaktivieren, Shader-Cache unbegrenzt, Anti-Lag (Low-Latency-Modus); erscheinen für AMD-Systeme und werden auf NVIDIA ehrlich als inaktiv gemeldet. Herstellerspezifische GPU-Tweaks (AMD und NVIDIA) sind **doppelt abgesichert**: Presets überspringen sie auf der falschen GPU, und der Befehl selbst verweigert ohne passenden Adapter — AMD-Werte landen nur im Treiberschlüssel des AMD-Adapters
- **Power-Plan-Tweaks schreiben in *alle* Energieschemata** — Windows kann nach einem Neustart ein anderes Schema aktivieren, wodurch eine Einstellung sonst „zurückgesetzt" aussieht. Die Plan-GUIDs kommen aus `powercfg /L`, nie der lokalisierte Planname — also sprachunabhängig
- Export/Import der Einstellungen als `.nextune`-Dateien
- Tooltips (Hover über `?`) für jeden einzelnen Tweak
- **Spiel-Profile** (Optimizer → Spiele): die `.exe` eines Spiels wählen — Windows startet es danach mit CPU-Priorität *Hoch* oder *Höher als normal* und hoher Datenträger-Priorität (Image File Execution Options), auf Wunsch ohne Vollbildoptimierungen nur für dieses Spiel. Kein Hintergrundprozess; Windows setzt das bei jedem Start selbst. Läuft das Spiel, zeigt der Status, welche Priorität es wirklich bekommen hat (manche Anti-Cheat-Systeme setzen sie zurück). Nie *Echtzeit*; Windows- und Systemprogramme werden abgelehnt; Entfernen — oder *Alles zurücksetzen* — stellt den vorherigen Zustand wieder her

### 🖥 BIOS Guide
- **Jede Desktop-Plattform seit Intel 8. Gen / Ryzen 1000** — 16 Plattformen: Ryzen 9000X3D / 9000 / 7000X3D / 7000 / 8000G (AM5), Ryzen 5000X3D / 5000 / APUs / 3000 / 1000–2000 (AM4), Core Ultra 200S, Core 12. / 13.–14. Gen, 10.–11. Gen, 8.–9. Gen, dazu die Grundlagen für alles andere (Laptops, Workstations)
- Die Hardware-Erkennung **wählt nur vor** — deine Plattform und deinen Board-Hersteller (ASUS / MSI / Gigabyte / ASRock); jede Plattform lässt sich öffnen
- Jede Einstellung mit dem **Menüpfad für deinen Board-Hersteller**, Standard- und Empfehlungswert, Risiko und Wirkung — und dem, was auf der Plattform zählt (EXPO 6000 + FCLK 2000 bei AM5, Curve Optimizer, der Microcode-0x12F-Fix für 13./14. Gen, Intel Default Settings, 200S Boost, X3D-Kernzuteilung, Secure Boot für Anti-Cheats …)
- **Live-Status nur, wo Windows es wirklich weiß** (grün = gesetzt, rot = noch offen, grau = nicht prüfbar): RAM-Profil (eingestellter Takt gegen die JEDEC-Obergrenze des DDR-Typs), Resizable BAR (BAR1-Fenster aus dem NVIDIA-Treiber), Secure Boot und CSM (UEFI-Zustand). Die alten Schätzungen (ReBAR aus HAGS, XMP aus „> 3200 MHz“, PBO aus dem Maximaltakt) sind raus

### 🩺 Diagnose
- **Health Report** — read-only-Übersicht dessen, was Windows in den letzten 30 Tagen schon protokolliert hat: WHEA-Hardwarefehler, Bluescreens, unerwartete Neustarts, GPU-Treiber-Timeouts (TDR), Datenträgerfehler, App-Abstürze — mit Schweregrad und letztem Auftreten
- **Remnant-Scan** — read-only-Erkennung von Resten *anderer* Tweak-Tools (WinRing0-/inpout-Treiber, ISLC, TimerResolution-Autostarts, Fremd-Energiepläne, Razer Cortex). Meldet nur — entfernt nichts
- **Interrupts** — je PCI-Gerät: MSI oder der alte Leitungs-Interrupt (gelesen aus dem, was Windows wirklich zugeteilt hat, nicht nur aus dem Registry-Wert), Zahl der Meldungen, Interrupt-Priorität und Kern-Zuordnung, geteilte Leitungs-Interrupts — mit Hinweis, wo es zählt (eine GPU ohne MSI verweist auf den MSI-Tweak; ein Treiber, der MSI absichtlich abschaltet, bleibt in Ruhe). Nur lesend

### 📊 Profil-Vergleich
- Vergleicht bis zu **4 gespeicherte GPU-Profile nebeneinander** danach, was sie **gegenüber Standard im selben Benchmark** bringen: eine **Standard-Spalte** als Punkt 0, Leistung (Punkte ggü. Standard) und Effizienz (Punkte pro Watt ggü. Standard) mit ▲ / ▼ / ≈ (innerhalb des Messrauschens von ±0,7 %), dazu die FurMark-Punkte selbst, Leistungsaufnahme, Speicher und Modus; ★ markiert das beste der gewählten Profile, und der **beste Allrounder** ist das, das gegenüber Standard keine Leistung verliert und dabei am sparsamsten ist (eine einfache Summe würde einen tiefen, spürbar langsameren Undervolt vorn sehen); *In beidem besser* nennt ein Profil, das ein anderes bei Leistung und Effizienz zugleich schlägt, und die Zeile Stabilitätstests sagt, ob ein Profil den **Härtetest** bestanden hat (Profile von vor seiner Zeit sagen das auch); **Volllast ggü. Standard** — jeder Tune endet mit der Rechenlast am Power-Limit (wie 3DMark und schwere Spiele; FurMark 2 in 1080p bleibt darunter), mit dem Profil und bei Standard; dazu die Ergebnisse des 3DMark-Vergleichs
- Ein **V/F-Kurven-Diagramm** wie Afterburners Kurven-Editor: Standard gestrichelt, jedes Profil in eigener Farbe und Linienart, die gemessenen Punkte als Punkte, der Bereich, in dem die Karte unter Last läuft, schattiert; Mauszeiger drauf zeigt die Takte bei dieser Spannung
- Beide Tune-Modi messen das (je 60 s FurMark 2 bei Standard und mit dem Ergebnis; vor jedem Vergleichslauf kühlt die Karte auf die Starttemperatur des Standard-Laufs ab)

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
- **Englisch** (Standard) und **Deutsch** — Umschaltung per `EN/DE`-Button in der Seitenleiste
- Die App startet dafür kurz neu und baut jede Seite in der neuen Sprache auf (ein laufender Tune wird vorher auf Standard gesetzt)

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
│   ├── tweaks.py             ← 109-Tweaks-Datenbank (Windows, Gaming, Network, Audio)
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
│   ├── gpu_watchdog.py       ← GPU-Hänger / Resets seit dem übernommenen Profil, Fehlerpunkt
│   ├── hardness_test.py      ← Härtetest: 3D + Encoder + Rechnen / Speicher gleichzeitig, in Phasen
│   ├── nvenc.py              ← NVIDIA-Video-Encoder über die nvEncodeAPI64.dll des Treibers (ctypes)
│   ├── gpu_flight.py         ← Flugschreiber + Live-Ereignisprüfung (solange die App läuft)
│   ├── interrupts.py         ← Interrupt-Ansicht: MSI / Leitung je PCI-Gerät (nur lesend)
│   ├── game_profiles.py      ← Spiel-Profile: CPU-/Datenträger-Priorität je .exe, Vollbild-Flag
│   ├── remnant_detector.py   ← Erkennung von Tweak-Tool-Resten
│   ├── crash_recovery.py     ← TDR-Erkennung, Crash-Flag-System
│   ├── temp_monitor.py       ← GPU-Temperatur-Toast-Benachrichtigungen
│   ├── updater.py            ← Updates von GitHub (build.json, Download, git pull)
│   ├── export_import.py      ← .nextune Export/Import
│   ├── tune_history.py       ← Tune-Log-Parser
│   ├── startup_loader.py     ← Autostart + Startprofil-Loader
│   ├── gpu_defaults.py       ← GPU-Generationen-Standardwerte-Tabelle
│   ├── app_settings.py       ← Kleine dauerhafte Einstellungen (logs/settings.json)
│   ├── safe_json.py          ← Absturzsichere JSON-Zustandsdateien (atomar, letzte gute Kopie, nie {} über eine gesperrte Datei)
│   ├── errlog.py             ← Unerwartete Fehler -> logs/app_errors.log
│   ├── proc_job.py           ← Windows-Job: die GPU-Lasten der App enden mit der App
│   ├── notify.py             ← Benachrichtigungen über das Tray-Icon
│   ├── learned_limits.py     ← Punkte, die einen Endtest nicht bestanden, pro Karte (der nächste Tune startet darunter)
│   ├── audio_policy.py       ← Audio-Geräteeinstellungen über die Windows-Audio-API
│   ├── furmark.py            ← FurMark-1/2-Erkennung + Kommandozeile
│   ├── threedmark.py         ← 3DMark-Erkennung (Steam-Bibliotheken) + Start + Ergebnisdateien
│   ├── bench_compare.py      ← Der 3DMark-Vergleich der Profile (aktivieren, abkühlen, einlesen, buchen)
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
    ├── tab_compare.py        ← Profilvergleich (gegen Standard, V/F-Kurven-Diagramm)
    ├── tab_bios.py           ← BIOS-Guide mit Live-Erkennung
    ├── tune_history_view.py  ← Tune-Verlauf (Ansicht im GPU-Tuner)
    ├── update_flow.py        ← Update-Prüfung / -Frage (Start + Einstellungen)
    ├── tab_diagnose.py       ← Health-Report + Remnant-Scan + Interrupts
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
Thread 5      → Tray-Menü-Refresh (60s Intervall)
Thread 6      → Temperatur-Monitor (10s Intervall)
Thread 7+     → Auto-Tune-Stages, Stress-Worker-Subprozess
```

Thread-übergreifende Kommunikation läuft über `widget.after(0, callback)` oder eine Warteschlange, die der Main-Thread abfragt (Log-Ansichten, `ui.components.run_async`) — Tk darf nur vom Main-Thread angefasst werden.

---
