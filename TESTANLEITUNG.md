# Schritt für Schritt: GameOptimizerPro + Afterburner einrichten, testen, tunen

Diese Anleitung führt vom Installieren bis zum ersten fertigen GPU-Profil. Die
Afterburner-Anbindung ist offline gründlich getestet (Dateiformat, Abläufe,
Prozesssteuerung, Oberfläche) **und live auf deinem PC** (RTX 4080, Afterburner 4.6.6):
Der Live-Test in Schritt 5 hat +15 MHz / 90 % in Slot 2 geschrieben, Afterburner hat das
Profil übernommen (NVML las **288 W** zurück), gleiche Werte gingen ohne Neustart,
„Reset“ klappte, und die Originaldatei kam Byte für Byte zurück.

| # | Schritt | Ändert etwas? | Dauer | Stand bei dir |
|---|---|---|---|---|
| 1 | GameOptimizerPro installieren (`install.bat`, mit cupy) | Python-Pakete | 5–10 min | ✅ erledigt |
| 2 | MSI Afterburner installieren und einstellen | Afterburner | 5 min | ✅ erledigt |
| 3 | Lese-Check `info` | **nein** | 1 min | ✅ alles OK |
| 4 | Trockenlauf `dryrun` | **nein** | 1 min | ✅ alles OK |
| 5 | Live-Test `live` | kurz, danach automatisch zurück | 2 min | ✅ 0 Fehler |
| 6 | Kurven-Test `live --curve` (optional) | kurz, danach automatisch zurück | 2 min | offen |
| 7 | Test in der App | ja, Reset-Knopf vorhanden | 3 min | ✅ erledigt |
| 7b | Neue Funktionen prüfen (Dashboard, Dienste, Deep Clean, 26H2-Tweaks) | teils | 10 min | ✅ erledigt — Befunde siehe unten |
| 8 | Erster Auto-Tune | ja, Abbruch setzt zurück | 20–30 min | ✅ zweimal gelaufen (+179 MHz / 97 %; 2. Lauf mit Mem +1000 im Endtest durchgefallen) |
| 8b | Nach dem Update (Runde 12): neue Oberfläche, FurMark/3DMark, Audio | ja | 30 min | ✅ erledigt |
| 8c | **Rundum-Tuner (Runde 13) — Punkte unten** | ja, Abbruch setzt zurück | 40–60 min | ✅ Lauf 3 bestanden (+3,7 % FurMark) |
| 9 | Danach: im Alltag prüfen und als Standard setzen | ja | — | offen |

**Wichtig für alle Schritte ab 3:** Kein Spiel und keine 3D-Anwendung offen lassen.

---

## Jetzt (nach dem Update von Runde 13) — Rundum-Tuner

Der neue Modus **„Rundum“** misst jeden Spannungspunkt der Kurve einzeln und baut daraus eine
eigene Kurve. Bei dir ist er schon einmal komplett durchgelaufen (Lauf 3: FurMark 7269 → 7538
Punkte, Speicher +1000, Endtest bestanden). App einmal **schließen** (Tray → Beenden) und als
**Administrator** neu starten, Afterburner laufen lassen, kein Spiel offen.

1. **GPU-Tuner → Auto-Tune → Modus „Rundum“**, Ziel wählen:
   - **Max. Leistung** — volle Kurve, höchste Punktzahl
   - **Ausgewogen** — mindestens die Hälfte des Gewinns, davon die meisten Punkte pro Watt
   - **Effizienz** — Standard-Leistung bei möglichst wenig Watt (Undervolting)
2. In der Karte „Rundum-Parameter“ muss grün **„✓ FurMark 2 (v…)“** stehen. Die Standardwerte
   passen (Core max 250, 45 s je Punkt, 30 MHz Sicherheit, 5 min FurMark-Endtest, Speicher max
   1000). Im Start-Dialog steht der Startwert — bei dir jetzt dein gespeichertes Profil.
3. **Tune starten → Ja.** Dauer ca. 40–60 min. Afterburner startet bei jedem Schritt kurz neu
   (minimiert), FurMark-Fenster gehen auf — nicht schließen. Siehst du **Bildfehler** (z. B. grüne
   Stippen): sofort **Abbrechen** und mir Bescheid geben.
4. Am Ende: **„Bericht“** öffnet den Bericht (Punkte, Kandidaten, Vorher/Nachher, Empfehlungen).
   Das Profil heißt `GOP_CURVE_…` und liegt in Afterburner-Slot 2.
5. Gegenprobe im Spiel oder mit 3DMark (Speed Way lag nach Lauf 3 bei 7622, Durchschnitt aller
   RTX 4080: 7424). Stürzt ein Spiel ab: den Tune mit größerer „Sicherheit (MHz)“ wiederholen.

Außerdem neu: Die Meldung „NumLock beim Start einschalten — nicht mehr aktiv“ kommt nach einem
Neustart nicht mehr (Windows schreibt den Wert beim Abmelden um, die Prüfung akzeptiert beide
Schreibweisen).

---

## Davor (Runde 12) — neue Oberfläche

Die ganze Oberfläche ist neu (CustomTkinter). App einmal **schließen** (Tray-Symbol → Beenden)
und über **`GameOptimizerPro.bat`** neu starten. Fehlt das neue Paket `customtkinter`, fragt die
App beim Start einmal, ob sie es installieren soll → **Ja** (dauert 10–30 s).

1. **Oberfläche:** Links ist jetzt eine Seitenleiste. Zieh das Fenster schmaler und breiter —
   Texte brechen um, Karten ordnen sich in 1–4 Spalten an (Presets, BIOS-Guide, Dashboard),
   nichts wird mehr abgeschnitten. **Strg+1 … Strg+9** springen zu den Seiten. Größe und
   Position des Fensters bleiben nach einem Neustart erhalten.
2. **GPU-Tuner:** Das **Tuner-Log** steht rechts und ist sofort sichtbar, auch im kleinen
   Fenster. Das Mausrad über „Auto-Tune / Profile / Manuell“ schaltet nichts mehr um.
3. **Stresstest → FurMark:** zeigt „✓ FurMark 2 (v2.10.2)“. Demo, Auflösung und Dauer wählen →
   **FurMark starten**. Wenn FurMark fertig ist, steht unter „Live-GPU während des Tests“ die
   Zusammenfassung (Spitzentemperatur, Takt unter Last, max. Leistung, Treiber-Reset ja/nein).
   Nach einem Neustart der App ist FurMark weiterhin verknüpft. Kantenglättung bleibt auf
   **„8× (volle Last)“**: Mit G-SYNC + VSync im Treiber (und/oder FPS-Limit) rendert FurMark sonst
   nur bis zur Bildwiederholrate und lastet die GPU nur halb aus (im Test: 162–165 FPS, 45 %).
   Mit 8× lief sie trotz VSync auf 100 % (274 W). Deine NVIDIA-Einstellungen musst du dafür nicht
   ändern.
4. **Stresstest → 3DMark:** **3DMark starten** öffnet 3DMark über Steam. Den Test wählst du in
   3DMark (z. B. einen Stresstest). GameOptimizerPro zeichnet mit, bis du 3DMark schließt.
5. **Audio-Tweaks:** Optimizer → Audio → „Disable Audio Enhancements“ und „Exclusive Audio Lock“
   anhaken → **Ausgewählte anwenden**. Im Log steht jetzt „… 3 von 3 Wiedergabegeraet(en)“;
   nach **Status prüfen** sind beide grün, und nach einem PC-Neustart fragt der Dialog „Tweaks
   nicht mehr aktiv“ nicht mehr danach.
6. **Autostart** und **Dienste** sind jetzt Seiten in der Seitenleiste (keine eigenen Fenster).
7. **Einstellungen:** Der Schalter „Tray-Standard-GPU-Profil beim Start automatisch laden“ wirkt
   jetzt wirklich (vorher hatte der Haken keine Funktion).
8. Sieht etwas abgeschnitten oder verrutscht aus: Screenshot an mich.

---

## Davor (Runde 10) — zur Erinnerung

Deine Tests haben einiges aufgedeckt, alles ist behoben (Details: CHANGELOG, Runde 10).
Der Ordner auf deinem PC ist schon aktuell — die App nur **einmal schließen** (Tray-Symbol →
Beenden) und über **`GameOptimizerPro.bat`** neu starten.

1. **Kein schwarzes Python-Fenster mehr.** Auch ein Doppelklick auf `GameOptimizerPro.py`
   startet jetzt ohne Konsole (es blitzt höchstens kurz auf).
2. **Dialog „Tweaks nicht mehr aktiv“** erscheint ein paar Sekunden nach dem Start — jetzt
   mit **einem Haken pro Tweak**:
   - **Ultimate Performance Plan** → Haken lassen. Die neue Version entfernt die **14
     überzähligen Kopien** des Plans und stellt im Netzbetrieb **Bildschirm und Standby auf
     „nie“** (vorher: Bildschirm aus nach 15 min).
   - **Disable Audio Enhancements / Exclusive Audio Lock** → Haken lassen. Kommt danach
     „Windows hat die Einstellung nicht übernommen“, ist das die ehrliche Meldung (vorher
     stand fälschlich ✓) — das klären wir im nächsten Live-Test.
   - **Win11: Taskbar Icons Left-Aligned** → Haken **weg**, falls du die Taskleiste bewusst
     wieder mittig hast; dann fragt die App nicht mehr.
   - **Store-Empfehlungen** → nach Wunsch.
   - „Übernehmen“ klicken.
3. **Monitore 2 und 3** laufen immer noch mit 50 Hz → Einstellungen → System → Bildschirm →
   Monitor anklicken → Erweiterte Anzeige → **60 Hz** (Dashboard zeigt es an).
4. **DNS:** bei dir ist Cloudflare aktiv. „Alle auswählen“ nimmt jetzt nur noch *einen*
   DNS-Anbieter und *einen* Energieplan.
5. **Neuer Auto-Tune — jetzt mit Speicher-OC** (OC + UV, Haken **„Speicher mit übertakten“**
   ist gesetzt, „Mem Max“ steht auf +1500). Das alte Feld „Mem Offset“ gibt es nicht mehr: Es
   setzte einen festen, nie gesuchten Wert. Jetzt sucht Stufe 4 den Speicher-Offset selbst und
   misst dabei die Bandbreite (Dauer insgesamt ca. 30–45 min). Fällt der Endtest durch, nimmt
   der Tuner selbst einen Schritt zurück (Core −15, dann Speicher halbieren) und testet erneut;
   gespeichert wird nur, was bestanden hat. Der PC geht währenddessen nicht in den Standby.
6. **System Cleaner:** löscht Temp-Dateien jetzt nur, wenn sie älter als 24 Stunden sind
   (vorher alles — das hat u. a. die Testdateien dieser Sitzung gelöscht).

---

## Schritt 1 — GameOptimizerPro installieren

1. Du brauchst **nichts neu herunterzuladen**: Der GameOptimizerPro-Ordner auf deinem PC ist
   die aktuelle Version.
2. Im Ordner **`install.bat`** doppelklicken. Das Skript installiert die Python-Pakete
   und fragt dann:
   ```
   cupy jetzt installieren (J = ja, N = nein)
   ```
   → **J** drücken. cupy ist ein Download von ca. 1–2 GB und braucht kein CUDA-Toolkit.
   Der Auto-Tuner braucht es, um die Grafikkarte wirklich auszulasten, Rechenfehler zu
   erkennen und Leistung und Bandbreite zu messen. Ohne cupy ginge das nur mit parallel
   laufendem FurMark.
3. Warten, bis „Fertig!“ erscheint, dann das Fenster schließen.

---

## Schritt 2 — MSI Afterburner installieren und einstellen

1. **Installieren** von der offiziellen Seite:
   <https://www.msi.com/Landing/afterburner/graphics-cards>. Den RivaTuner Statistics
   Server (RTSS), den der Installer anbietet, brauchst du hierfür nicht.
2. Afterburner starten → **Einstellungen (Zahnrad) → Allgemein**:
   - ☑ **Spannungssteuerung freischalten** (*Unlock voltage control*)
   - ☑ **Spannungsüberwachung freischalten** (*Unlock voltage monitoring*)
   - ☑ **Minimiert starten** (*Start minimized*). Afterburner wird beim Anwenden neuer
     Werte kurz neu gestartet und soll dabei nicht aufpoppen.
   - OK. Den Neustart, den Afterburner anbietet, mit **Ja** bestätigen.
3. **Einstellungen → Überwachung:** Haken bei **GPU-Spannung** (*GPU voltage*) und
   **Leistung** (*Power*) setzen.
4. **Nichts an den Reglern ändern.** Unten auf **Speichern** (Disketten-Symbol) klicken und
   dann auf **1**. Das hat zwei Effekte:
   - Afterburner legt die Profildatei deiner Karte samt V/F-Kurve an
     (`…\MSI Afterburner\Profiles\VEN_10DE&DEV_….cfg`).
   - Slot 1 enthält danach deine Werkseinstellungen. GameOptimizerPro benutzt **Slot 2**.
5. **„Übertaktung beim Systemstart anwenden“** (Windows-Logo-Knopf) vorerst **aus** lassen.
6. Afterburner offen lassen (Fenster oder Tray).

---

## Schritt 3 — Lese-Check (ändert nichts)

Eine normale PowerShell im GameOptimizerPro-Ordner öffnen (im Explorer in die Adresszeile
`powershell` tippen und Enter drücken):

```powershell
python tools\ab_selftest.py info
```

Diese Zeilen sollten mit **[OK ]** erscheinen:

```
  [OK ] NVML verfügbar — NVIDIA GeForce RTX …
  [OK ] installiert — C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe
  [OK ] Spannungssteuerung freigeschaltet
  [OK ] Spannungsüberwachung freigeschaltet
  [OK ] gefunden — VEN_10DE&DEV_….cfg (per PCI-ID zugeordnet)
  [OK ] V/F-Kurve lesbar — Basis für neue Kurven: [Startup]   (oder [Defaults])
  [OK ] Shared Memory lesbar — NN Quellen
  [OK ] Graph 'GPU-Spannung' aktiv (Monitoring liefert Spannung) — 0.xxx V
```

Steht bei „GPU-Spannung“ **FEHLER**: In Afterburner unter **Einstellungen → Überwachung**
in der Liste „Aktive Hardware-Überwachungsgraphen“ den Haken bei **GPU-Spannung** setzen
und mit **OK** bestätigen.

Das Protokoll landet in `logs\ab_selftest_info_<Zeit>.txt`.

---

## Schritt 4 — Trockenlauf (ändert nichts)

```powershell
python tools\ab_selftest.py dryrun
```

Der Trockenlauf zeigt genau, was in Slot 2 geschrieben **würde** (+15 MHz, 90 %), schreibt
aber nichts. Erwartet wird:

```
  • Core +15 MHz auf allen Kurvenpunkten (Basis-Kurve aus [Defaults])
  • Mem +0 MHz, Power-Limit 90 %
  [OK ] … Zeile(n) neu/geändert, alle anderen Abschnitte unverändert
```

Existiert Slot 2 noch nicht, steht dort außerdem „[Profile2] neu angelegt“.

---

## Schritt 5 — Live-Test (ändert kurz etwas, stellt alles zurück)

Braucht **Administrator-Rechte**, weil Afterburners Profilordner in `C:\Program Files (x86)`
liegt.

1. Alle Spiele schließen.
2. `Win + X` → **Terminal (Administrator)**.
3. In den GameOptimizerPro-Ordner wechseln und starten:

```powershell
cd "<Pfad zu GameOptimizerPro>"
python tools\ab_selftest.py live --pause
```

| Schritt | Ablauf | Deine Aufgabe |
|---|---|---|
| **A** | Afterburner wird geschlossen, Slot 2 bekommt +15 MHz und 90 %, dann startet Afterburner mit `-Profile2` neu. NVML misst das Power-Limit (bei 320 W Standard → **288 W**). | In den 20 s Wartezeit in Afterburner nachsehen: **Core Clock +15**, **Power Limit 90 %**? |
| **A2** | Gleiche Werte noch einmal. Diesmal darf Afterburner **nicht** neu starten. | — |
| **Reset** | Slot 2 bekommt die Werkswerte, das Power-Limit wird wieder gemessen (→ 320 W). | — |
| **Wiederherstellen** | Die Originaldatei wird byte-genau zurückgeschrieben, Afterburner startet normal. | — |

Am Ende muss **„0 Fehler.“** stehen, dann mit Enter schließen. Auch bei einem Abbruch
(Strg+C) stellt das Tool die Werkswerte und die Originaldatei wieder her.
**Merk dir**, was Afterburner in Schritt A angezeigt hat. Das kann das Tool nicht prüfen.

---

## Schritt 6 — Kurven-Test (optional, nur wenn Schritt 5 klappt)

```powershell
python tools\ab_selftest.py live --curve --pause
```

Zusätzlicher Schritt **B**: eine **flache V/F-Kurve** (Undervolt-Deckel ab ca. 1000 mV auf
dem Stock-Takt an diesem Punkt, also kein Übertakten). Während der 20 s in Afterburner
**Strg + F** drücken: Ab dieser Spannung muss die Kurve waagerecht verlaufen. Danach
wird alles zurückgesetzt.

---

## Schritt 7 — In der App testen

1. **`GameOptimizerPro.bat`** starten (fragt nach Admin-Rechten → **Ja**).
2. **Einstellungen → Afterburner-Einrichtung:** Alle Afterburner-Zeilen sollten ✓ zeigen.
3. **GPU-Tuner → Manuell:** Core **+15**, Mem **0**, Power **90** → **Anwenden**. Afterburner
   startet kurz neu, und unten steht „Applied — … (slot 2)“. In Afterburner nachsehen.
4. **Auf Standard zurücksetzen:** Afterburner steht danach wieder auf 0 / 100 %.
5. **Stresstest → Interner Test:** Dauer auf **60** stellen → **Test starten**. Erwartet wird
   „✓ PASSED“ mit einer GPU-Last von über 90 %. Das beweist, dass cupy arbeitet.

---

## Schritt 7b — Neue Funktionen prüfen

1. **Dashboard → „Optimierung & Monitor“:**
   - Der **Optimierungs-Score** erscheint nach ein paar Sekunden (bei dir zuletzt **80 %**, 66 von 82).
     Er zählt nur *sichere* Tweaks, die laut Systemprüfung wirklich aktiv sind.
   - **Monitor-Zeilen:** Bei dir laufen **Monitor 2 und 3 mit 50 Hz**, obwohl **60 Hz**
     gehen. Beheben: Windows-Einstellungen → System → Bildschirm → den Monitor oben
     anklicken → Erweiterte Anzeige → Bildwiederholrate **60 Hz**. Danach im Dashboard auf
     **⟳ Neu prüfen** klicken — die Zeilen werden wieder weiß statt orange.
   - Der Hauptmonitor läuft korrekt mit **165 Hz**.
2. **Dienste** (Seitenleiste): Die Seite listet 27 Dienste mit Status und
   Starttyp. Die meisten sind bei dir schon deaktiviert (aus v1). Nur ansehen reicht — wer
   etwas ändert: „Aktivieren“ stellt den ursprünglichen Starttyp wieder her (oder den
   Windows-Standard, wenn der Dienst schon vorher aus war).
   **Hinweis:** Bei dir sind **Druckwarteschlange** (Drucken, auch „Als PDF drucken“)
   und die **Xbox-Dienste** (Game Pass) aus. Falls du etwas davon brauchst: markieren →
   **Aktivieren (Original)**.
3. **Einstellungen → System Cleaner & Deep Clean:** erst ohne Haken **Scannen**, dann z. B.
   ☑ Browser-Caches (Browser vorher schließen) → **Scannen**. Die Liste zeigt je Gruppe
   Dateien und Größe. **Bereinigen** fragt vorher nach; der Papierkorb hat eine
   zusätzliche Rückfrage.
4. **Optimizer → neue Tweaks (optional):** Unter *Privacy* stehen die 26H2-KI-Tweaks
   (Click to Do, Paint-KI, Notepad-KI, KI-Dienst), unter *Bloatware* „Microsoft-365-Copilot-App
   & Dev Home entfernen“, unter *Speicher & RAM* die Speicher-Tweaks. Anhaken → **Ausgewählte
   anwenden** (davor läuft automatisch ein Registry-Backup) → danach **Status prüfen**:
   die Punkte müssen grün werden. „Recall“ braucht einen Neustart. Das Suchfeld oben rechts
   findet Tweaks nach Name oder Beschreibung.
5. **Drift-Prüfung:** erscheint nur, wenn ein früher angewendeter Tweak nicht mehr aktiv
   ist (z. B. nach einem Windows-Update). Dann: **Haken** = erneut anwenden, **ohne Haken** =
   als nicht angewendet markieren, **Später fragen** = beim nächsten Start wieder fragen.
   Klappt das erneute Anwenden nicht, wird der Tweak als nicht angewendet markiert und nicht
   bei jedem Start wieder nachgefragt.

---

## Schritt 8 — Erster Auto-Tune

1. **GPU Tuner → Auto-Tune**, Modus **„🚀 OC + UV (Recommended)“**.
2. Die vorgeschlagenen Werte übernehmen. Für eine RTX 4080 sind das: Core Step 15,
   Core Max +220, Power Min 65 %, Max Temp 85 °C, Step Test 45 s, Final Test 120 s,
   AB Slot 2.
3. **▶ START TUNE**. Den PC ca. **20–30 Minuten** nicht benutzen. Afterburner startet bei
   jedem Schritt kurz neu, das ist so gewollt.

**Was dabei passiert:**
- **Stufe 1, Takt:** +15, +30, +45 … MHz, jeweils mit **spielähnlicher Wechsellast**
  (10 s Volllast, 10 s halbe Last — in der halben Last boostet die Karte auf den
  Hochtakt-Punkt, an dem Spiele abstürzen; bei dir ~2790 MHz @ 1075 mV wie in Hunt).
  Scheitert ein Schritt (Rechenfehler, Absturz, Treiber-Reset oder Temperatur-Limit),
  geht es auf den **letzten stabilen Wert** zurück, und die **Schrittweite halbiert**
  sich (15 → 7 → 5 MHz). Ergebnis: die Stabilitätsgrenze mit ±5 MHz Genauigkeit.
  Beispiel: +45 ✓ → +60 ✗ → zurück auf +45, +52 ✓ → +59 ✗ → +57 ✗ → **+52 MHz**.
- **Stufe 2, Power-Limit:** Zuerst eine Referenzmessung bei 100 % mit warmer Karte, dann
  wird so weit gesenkt, wie es höchstens **3 % Leistung** kostet (gemessen, nicht
  geschätzt).
- **Endtest:** 2 Minuten Wechsellast mit genau dem Profil, das gespeichert wird.
- **ABORT** setzt jederzeit sofort auf Standard zurück.
- Das Dashboard zeigt währenddessen echte Werte — auch direkt nach jedem
  Afterburner-Neustart (früher froren die Werte dabei ein, das ist behoben).

Das Ergebnis erscheint im Tab **Profiles** (z. B. `GOP_OC+UV_0930_2015`) und ist bereits aktiv.

---

## Schritt 9 — Danach

1. **Ein, zwei Abende normal spielen.** Ein Stresstest mit Volllast prüft nicht jede
   Situation. Gibt es in einem Spiel Abstürze oder Bildfehler: **Manual** → Core
   **15 MHz niedriger** als im Profil, Mem und Power wie im Profil (stehen im Tab
   **Profiles**) → **Apply** → **Save as Profile...**
2. Läuft alles stabil: **Profiles** → Profil wählen → **📌 Set Tray Default**, dann unter
   **Settings** den Haken „Tray-Default GPU-Profil beim Start automatisch laden“ setzen
   (und bei Bedarf „Mit Windows starten“).

---

## Rückmeldung an mich

Die Protokolle liegen in `logs\` (`ab_selftest_*.txt`, `tune_*.log`), die kann ich selbst
lesen. Schreib mir einfach, was du gemacht hast, und dazu:
- was Afterburner in Schritt 5A angezeigt hat (Core Clock, Power Limit) — das ist noch offen,
- bei Schritt 6, ob die Kurve flach war,
- ob irgendwo ein Fenster oder eine Fehlermeldung auftauchte.

---

## Notfall: alles auf Werkszustand

1. **In Afterburner:** den **Reset**-Knopf (↺) drücken oder **Slot 1** laden (deine
   Werkseinstellungen aus Schritt 2).
2. **Originaldatei zurückspielen** (Administrator-Terminal):
   ```powershell
   python tools\ab_selftest.py restore
   ```
   Die Backups liegen unter `%LOCALAPPDATA%\GameOptimizerPro\AfterburnerBackups\`.
3. **PC neu starten:** Takt-Offsets verfallen dabei, solange in Afterburner „Übertaktung
   beim Systemstart anwenden“ aus ist.

---

## Typische Meldungen

| Meldung | Bedeutung / Lösung |
|---|---|
| `installiert — nicht gefunden` | Afterburner ist nicht (oder in einem ungewöhnlichen Ordner) installiert. |
| `Profildatei … noch kein Profil für die NVIDIA-Karte` | Schritt 2.4: **Speichern → 1** klicken. |
| `V/F-Kurve lesbar — keine` | Ebenfalls Schritt 2.4. |
| `Kein Afterburner-Profil passt zur Karte` | Es gibt nur Dateien einer anderen, alten Karte. Afterburner einmal starten und speichern. |
| `Admin-Rechte — bitte in einem Administrator-Terminal starten` | `Win + X` → *Terminal (Administrator)*. |
| `GPU im Leerlauf — GPU-Last bis NN %` | Spiel oder Video läuft noch. Schließen und erneut starten. |
| `Afterburner ließ sich nicht beenden` | Das Terminal oder GameOptimizerPro läuft ohne Admin-Rechte. |
| `Power-Limit laut Treiber … (erwartet 288 W)` **FEHLER** | Afterburner hat das Profil nicht übernommen. Protokoll liegt in `logs\`, bitte melden. |
| `Core-Offset nicht per NVML auslesbar` / `[INFO] … NVML meldet …` | Kein Fehler: Maßgeblich ist die Anzeige in Afterburner. |
| Tuner: `Baseline: GPU-Auslastung nur Ø NN %` | cupy fehlt oder funktioniert nicht. `install.bat` erneut ausführen und **J** wählen. |
| Tuner: `Rechenfehler unter Last (GPU instabil)` | Kein Programmfehler: Der Schritt war zu hoch. Der Tuner geht automatisch zurück. |
| Tuner: `Anwenden fehlgeschlagen — Tune abgebrochen` | Afterburner konnte die Werte nicht setzen. Die Meldung sagt warum, sonst Schritt 3 wiederholen. |

## Bekannte Grenzen

- **Lüfter** werden nicht über Profile gesetzt. Die Quellen widersprechen sich bei
  Afterburners `FanMode`-Kodierung, also bleibt der Lüfter in Afterburner.
- Beim Anwenden **neuer** Werte startet Afterburner kurz neu (einige Sekunden), weil er
  seine Profildatei nur beim Start liest.
- Der Tuner enthält auch eine V/F-Kurven-Stufe; die ist im GPU-Tab noch nicht auswählbar.
  (Die Speicher-Stufe schon: Haken „Speicher mit übertakten“.)
- **Audio-Verbesserungen / Exklusiver Modus:** Windows 11 26H2 sperrt diese Werte in der
  Registry sogar für Administratoren. Die Tweaks gehen deshalb über die Windows-Audio-API
  (wie die Sound-Systemsteuerung) und gelten für alle aktiven und abgesteckten
  Wiedergabegeräte. Ein **später neu angeschlossenes** Gerät bekommt die Einstellung erst,
  wenn du den Tweak erneut anwendest.
- **3DMark:** Stresstests per Kommandozeile gibt es nur in der Professional Edition. Mit der
  normalen Version startet GameOptimizerPro 3DMark über Steam, den Test wählst du selbst —
  die App zeichnet währenddessen auf.
- Der **Core-Offset** lässt sich nicht per NVML zurücklesen (der Treiber meldet
  Afterburners Offset dort nicht) — maßgeblich ist die Anzeige in Afterburner. Das
  **Power-Limit** wird dagegen per NVML geprüft.
