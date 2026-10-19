"""Round 29 — English is the default language: no German-only text in the UI or in the
messages the core modules hand to it. A static scan (every string with German words that is
not one half of a translation, a (de, en) pair or a de/en dict) must find only the known,
intended places; plus spot checks of the new English texts."""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


DE = re.compile(r"[äöüÄÖÜß]|\b(und|nicht|kein|keine|keinen|wird|werden|aktiv|aktiviert|deaktiviert|Fehler|läuft|"
                r"bitte|erst|noch|nach|beim|oder|für|mit|Sekunden|Neustart|Grafikkarte|Profil|Speicher|"
                r"gelöscht|übersprungen|Lauf|Wende|erneut|angewendet|Sichere|gefunden|Dienste|Dienst|Eintrag|"
                r"Einträge|ausgewählt|Datei|Dateien|Ordner|konnte|gespeichert|geladen|wählen|Spannung|Takt|"
                r"setzt|Werte|Ziel|Standard|Prüfung|prüfen|Fehlgeschlagen|fehlgeschlagen|Ergebnis|"
                r"Einstellungen|Neu|neu|starten|gestartet|beendet|Abbruch|Zurück|zurück|Bericht|Gerät|"
                r"Treiber|Anwenden|Übernehmen|Laufwerk|Leistung|Verlust|erreichbar|Seit|seit|ohne|"
                r"Gesamt|gesamt|Monat|Tage|Woche|zuletzt|Vorgang|Vorsicht|Achtung|Hinweis|gemerkt|Zustand|"
                r"Empfehlung|Pfad|Quelle|Manuell|Automatisch|Unbekannt|unbekannt|Deaktivierbar|Bereits|"
                r"Ja|Nein|Dauer|Minuten|Stunden|Grafik|Lüfter|Temperatur|Auslastung|Verlauf|Zeitpunkt|"
                r"Aufnahme|gestoppt|bestanden|instabil|Speichern|Löschen|Abbrechen|Schließen|Öffnen|"
                r"Bereinigen|leeren|Papierkorb|Benutzer|Absturz|Daten|Verzeichnis|Auswahl|Hilfe|Weiter|"
                r"\w+(?:ung|ungen|keit|heit|lich|liche|lichen|ieren|iert|ierte)|\w*[Ff]ehler\w*|"
                r"Keine|Kein|Nicht|Tagen|von|erfolgreich|abgeschlossen|geleert|Wiedergabe\w*|"
                r"\w*(?:sch[a-z]|tz|ß)\w*)\b")
TR = {"tr", "T", "t", "_t", "tweak_name", "_tr"}
# Own translation systems (the tuner's CT.T log, the tweak / preset / BIOS texts) are checked elsewhere
SKIP = {"core/nvtune_tuner.py", "core/curve_tune.py", "core/tweaks.py", "core/tweak_i18n.py",
        "core/i18n.py"}
# Intended German strings: data keyed by German with an English table next to it, log / output
# patterns, texts with a German and an English branch
ALLOWED_FILES = {
    "core/services.py": "the German service table; CATEGORY_EN / DESC_EN / _STATUS_EN / START_LABEL_EN",
    "core/tweak_presets.py": "preset texts; English in tweak_i18n",
    "core/gpu_defaults.py": "per-generation notes, not shown (the GPU tab has its own texts)",
    "core/system_cleaner.py": "the German deep-clean table; DEEP_GROUPS_EN + group_text()",
    "core/tweak_verifier.py": "PowerShell check commands (they read German Windows output too)",
}
ALLOWED = [("core/gpu_watchdog.py", "Seit du"),                 # describe(found, de): its de branch
           ("core/gpu_watchdog.py", "Since you"),               # … and its English branch
           ("core/gpu_watchdog.py", "Das passiert"),            # describe(): the "why" of both branches
           ("core/gpu_watchdog.py", " Ein 153 allein"),
           ("core/gpu_watchdog.py", "That happens"),
           ("core/gpu_watchdog.py", " A 153 alone"),
           ("core/startup_loader.py", "Autostart: schtasks"),   # an English log line
           ("core/network_test.py", r"(\d+)%"),                 # ping output pattern (German Windows)
           ("core/tune_history.py", "(?:Speicher|Memory)"),     # log pattern
           ("core/tweak_verifier.py", "$o=(bcdedit"),           # bcdedit output (German Windows: "Ja")
           ("ui/main_window.py", "Sprache auf ")]               # the bilingual language dialog


def text_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def call_name(c):
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def scan(rel):
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    tree = ast.parse(src)
    parents = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parents[c] = p
    out = []
    for n in ast.walk(tree):
        s = text_of(n)
        if not s or not DE.search(s):
            continue
        p = parents.get(n)
        if isinstance(p, (ast.JoinedStr, ast.Expr, ast.FormattedValue)):
            continue
        ok, q, child = False, p, n
        while q is not None:
            if isinstance(q, ast.Call) and call_name(q) in TR:
                ok = True
                break
            if isinstance(q, ast.IfExp):
                other = q.orelse if child is q.body else q.body
                o = text_of(other)
                if o is not None and len(o) > 3 and not DE.search(o):
                    ok = True
                    break
            if isinstance(q, (ast.Tuple, ast.List)) and len(q.elts) >= 2:
                sib = [text_of(e) for e in q.elts if e is not child]
                if any(x and not DE.search(x) and len(x) > 3 for x in sib):
                    ok = True
                    break
            if isinstance(q, ast.Dict):
                keys = {k.value for k in q.keys if isinstance(k, ast.Constant)}
                if {"de", "en"} <= keys or child in q.keys:
                    ok = True
                    break
            if isinstance(q, ast.Compare):
                ok = True
                break
            child, q = q, parents.get(q)
        if not ok:
            out.append((n.lineno, s))
    return out


print("no German-only text in the UI and the core messages")
files = sorted(f"ui/{f}" for f in os.listdir(os.path.join(ROOT, "ui")) if f.endswith(".py"))
files += sorted(f"core/{f}" for f in os.listdir(os.path.join(ROOT, "core")) if f.endswith(".py"))
files += ["GameOptimizerPro.py"]
left = []
for rel in files:
    if rel in SKIP or rel in ALLOWED_FILES:
        continue
    for ln, s in scan(rel):
        if not any(rel == f and s.startswith(pre) for f, pre in ALLOWED):
            left.append(f"{rel}:{ln} {s[:70]!r}")
check(not left, f"every user-facing text has an English version ({len(left)} left): {left[:6]}")

print("spot checks")
import core.i18n as I18N
from core import services
I18N._current_lang = "en"
check(I18N.tr("Ja", "Yes") == "Yes" and services.start_label(2, True) == "Automatic (delayed)"
      and services.start_label(4) == "Disabled", "core tr + service start types in English")
check(set(services.DESC_EN) == set(services.KNOWN_SERVICES)
      and {c for c, _s, _d in services.KNOWN_SERVICES.values()} <= set(services.CATEGORY_EN),
      "every known service has an English description and category")
I18N._current_lang = "de"
check(services.start_label(2, True) == "Automatisch (verzögert)", "German stays German")
I18N._current_lang = "en"

src = open(os.path.join(ROOT, "core", "health_report.py"), encoding="utf-8").read()
check("No disk errors." in src and "Keine Datenträgerfehler." in src, "health report: both languages")
from core import system_cleaner, audio_policy
from core import bios_guide
I18N._current_lang = "en"
en_notes = bios_guide.get_profile("am5_zen5_x3d").notes
I18N._current_lang = "de"
de_notes = bios_guide.get_profile("am5_zen5_x3d").notes
I18N._current_lang = "en"
check(en_notes.startswith("The best gaming CPU family") and de_notes.startswith("Die beste")
      and len(bios_guide.profiles()) == 16, "BIOS guide in both languages (built per language)")
check(set(system_cleaner.DEEP_GROUPS_EN) == set(system_cleaner.DEEP_GROUPS)
      and system_cleaner.group_text("recyclebin")[0] == "Empty the Recycle Bin"
      and [t.label for t in system_cleaner.get_targets()][:1] == ["User temp"],
      "cleaner groups and targets in English")
check("playback device(s)" in audio_policy.ps_sysfx(True) and "Audio enhancements off" in audio_policy.ps_sysfx(True),
      "audio tweak results in English")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
