"""
GameOptimizerPro v2.1.1 — System Cleaner (Temp / Junk + Deep Clean)
Standard: löscht AUSSCHLIESSLICH Dateien aus dedizierten Temp-/Dump-Verzeichnissen.
Deep Clean (aus v1 portiert, jedes Ziel einzeln abwählbar, standardmäßig aus):
Browser-Caches, Windows-Update-Cache, Miniaturansichten, Prefetch, System-Logs &
Absturzberichte, Papierkorb. Alle Pfade werden intern aus festen Windows-Wurzeln
gebaut — nie aus Benutzereingaben — und fassen NIE Dokumente oder Browserprofile
(Passwörter, Verlauf, Lesezeichen) an; bei Browsern nur die Cache-Ordner.
Dateien, die gerade in Benutzung sind, werden übersprungen (kein Fehler) und
zählen NICHT als freigegeben. In den Temp-Ordnern nur Dateien, die älter als
24 Stunden sind: laufende Programme halten ihre Temp-Dateien nicht immer offen —
live gesehen, dass sonst frische Arbeitsdateien eines laufenden Programms
verschwanden (so macht es z. B. auch CCleaner).
"""

import time

import fnmatch
import glob
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class CleanTarget:
    label:      str
    path:       str
    file_count: int  = 0
    bytes:      int  = 0
    exists:     bool = False
    pattern:    str  = "*"        # file name filter (deep targets: *.pf, thumbcache_*.db …)
    recursive:  bool = True
    key:        str  = ""         # deep-clean group this folder belongs to
    min_age_h:  float = 0         # only files older than this (temp folders: 24 h)


@dataclass
class CleanResult:
    files_deleted: int  = 0
    bytes_freed:   int  = 0
    errors:        int  = 0            # übersprungene (in Benutzung / kein Zugriff)
    per_target:    list = field(default_factory=list)  # (label, files, bytes)


TEMP_MIN_AGE_H = 24


def _old_enough(fp: str, hours: float, now: float) -> bool:
    """Newest of modification / creation time older than `hours` (a file
    extracted with an old modification date is still new)."""
    if hours <= 0:
        return True
    try:
        st = os.stat(fp)
    except OSError:
        return False
    born = getattr(st, "st_birthtime", st.st_ctime)
    return now - max(st.st_mtime, born) >= hours * 3600


def get_targets() -> list[CleanTarget]:
    """Feste, sichere Ziele. Nur Verzeichnisse, deren kompletter Inhalt
    gefahrlos gelöscht werden kann (reine Temp-/Dump-Ordner)."""
    la  = os.environ.get("LOCALAPPDATA", "")
    win = os.environ.get("SystemRoot", r"C:\Windows")
    tmp = os.environ.get("TEMP") or (os.path.join(la, "Temp") if la else "")
    raw = [
        ("Benutzer-Temp", tmp),
        ("Windows-Temp",  os.path.join(win, "Temp") if win else ""),
        ("Absturz-Dumps", os.path.join(la, "CrashDumps") if la else ""),
    ]
    out, seen = [], set()
    for label, path in raw:
        if not path:
            continue
        p = os.path.normpath(path)
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(CleanTarget(label=label, path=p, exists=os.path.isdir(p),
                               min_age_h=TEMP_MIN_AGE_H))
    return out


# ── Deep Clean (v1: "Deep Clean" tools) ──────────────────────────────────────
# key -> (label, description, needs a confirmation)
DEEP_GROUPS: dict[str, tuple[str, str, bool]] = {
    "browser":   ("Browser-Caches", "Chrome, Edge, Firefox — nur Cache, keine Passwörter/"
                  "Verlauf/Lesezeichen. Browser vorher schließen.", False),
    "wucache":   ("Windows-Update-Cache", "Heruntergeladene Update-Dateien (SoftwareDistribution\\"
                  "Download). Der Update-Dienst wird kurz gestoppt; Windows lädt bei Bedarf neu.", False),
    "thumbs":    ("Miniaturansichten", "Thumbnail-Datenbank des Explorers — wird bei Bedarf neu "
                  "aufgebaut, behebt auch fehlerhafte Vorschaubilder.", False),
    "prefetch":  ("Prefetch-Daten", "Prefetch-Dateien (*.pf) — Windows baut sie neu auf; der erste "
                  "Start danach ist minimal langsamer.", False),
    "logs":      ("System-Logs & Fehlerberichte", "CBS-Logs, Minidumps, Windows-Fehlerberichte "
                  "(reine Diagnosedaten).", False),
    "recyclebin": ("Papierkorb leeren", "Leert den Papierkorb ALLER Laufwerke endgültig — gelöschte "
                   "Dateien sind danach nicht wiederherstellbar.", True),
}


def get_deep_targets(keys) -> list[CleanTarget]:
    """Folders of the chosen deep-clean groups (the Recycle Bin is handled by
    recycle_bin_info()/empty_recycle_bin(), not as folders)."""
    la  = os.environ.get("LOCALAPPDATA", "")
    win = os.environ.get("SystemRoot", r"C:\Windows")
    pd  = os.environ.get("ProgramData", r"C:\ProgramData")
    keys = set(keys or ())
    out: list[CleanTarget] = []

    def add(key, label, path, pattern="*", recursive=True):
        if path and os.path.isdir(path):
            out.append(CleanTarget(label=label, path=os.path.normpath(path), exists=True,
                                   pattern=pattern, recursive=recursive, key=key))

    if "browser" in keys and la:
        for browser, base in (("Chrome", os.path.join(la, "Google", "Chrome", "User Data")),
                              ("Edge", os.path.join(la, "Microsoft", "Edge", "User Data"))):
            for prof in sorted(glob.glob(os.path.join(base, "*"))):
                for sub in ("Cache", "Code Cache"):
                    add("browser", f"{browser}-Cache ({os.path.basename(prof)})",
                        os.path.join(prof, sub))
        for prof in sorted(glob.glob(os.path.join(la, "Mozilla", "Firefox", "Profiles", "*"))):
            add("browser", f"Firefox-Cache ({os.path.basename(prof)})", os.path.join(prof, "cache2"))
    if "wucache" in keys and win:
        add("wucache", "Windows-Update-Download", os.path.join(win, "SoftwareDistribution", "Download"))
    if "thumbs" in keys and la:
        add("thumbs", "Miniaturansichten", os.path.join(la, "Microsoft", "Windows", "Explorer"),
            pattern="thumbcache_*.db", recursive=False)
    if "prefetch" in keys and win:
        add("prefetch", "Prefetch", os.path.join(win, "Prefetch"), pattern="*.pf", recursive=False)
    if "logs" in keys:
        if win:
            add("logs", "CBS-Logs", os.path.join(win, "Logs", "CBS"), pattern="*.log", recursive=False)
            add("logs", "Minidumps", os.path.join(win, "Minidump"))
        if pd:
            add("logs", "Fehlerberichte (Warteschlange)",
                os.path.join(pd, "Microsoft", "Windows", "WER", "ReportQueue"))
            add("logs", "Fehlerberichte (Archiv)",
                os.path.join(pd, "Microsoft", "Windows", "WER", "ReportArchive"))
    return out


# Path segments that make a deep target acceptable — a second guard on top of
# building the paths from fixed roots.
_DEEP_OK = {
    "browser":  ("cache", "code cache", "cache2"),
    "wucache":  ("download",),
    "thumbs":   ("explorer",),
    "prefetch": ("prefetch",),
    "logs":     ("cbs", "minidump", "reportqueue", "reportarchive"),
}


def _is_safe(path: str, key: str = "") -> bool:
    """Schutzgitter: nur eindeutige Temp-/Dump-Pfade zulassen.

    Die Pruefung vergleicht ganze Pfad-SEGMENTE. Ein blosses Substring-'\\temp'
    haette auch Ordner wie '...\\Templates' oder '...\\temp_backup' durchgelassen.
    Deep-Clean-Ziele muessen mit dem erwarteten Ordnernamen ENDEN.
    """
    p = os.path.normpath(path).lower()
    if len(p) <= 8:
        return False
    segments = [s for s in p.split(os.sep) if s]
    if not key:
        return "temp" in segments or "crashdumps" in segments
    return bool(segments) and segments[-1] in _DEEP_OK.get(key, ())


def _files(t: CleanTarget):
    now = time.time()
    if t.recursive:
        for root, _dirs, files in os.walk(t.path, topdown=False):
            for f in files:
                if (fnmatch.fnmatch(f.lower(), t.pattern.lower())
                        and _old_enough(os.path.join(root, f), t.min_age_h, now)):
                    yield root, f
    else:
        try:
            for f in os.listdir(t.path):
                fp = os.path.join(t.path, f)
                if (fnmatch.fnmatch(f.lower(), t.pattern.lower()) and os.path.isfile(fp)
                        and _old_enough(fp, t.min_age_h, now)):
                    yield t.path, f
        except OSError:
            return


def scan(targets: list[CleanTarget] | None = None) -> list[CleanTarget]:
    """Ermittelt Größe/Anzahl der löschbaren Dateien. Rein lesend."""
    targets = targets or get_targets()
    for t in targets:
        t.file_count, t.bytes = 0, 0
        t.exists = os.path.isdir(t.path)
        if not (t.exists and _is_safe(t.path, t.key)):
            continue
        for root, f in _files(t):
            try:
                t.bytes += os.path.getsize(os.path.join(root, f))
                t.file_count += 1
            except OSError:
                pass
    return targets


def _service(action: str, name: str):
    try:
        subprocess.run(["sc.exe", action, name], capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def clean(targets: list[CleanTarget] | None = None) -> CleanResult:
    """Löscht Dateien in den (sicheren) Zielen. In-Benutzung → übersprungen.
    Nur wirklich gelöschte Dateien zählen als freigegeben."""
    targets = targets or get_targets()
    res = CleanResult()
    wu = any(t.key == "wucache" for t in targets)
    if wu:
        _service("stop", "wuauserv")        # its download folder is locked while it runs
    try:
        for t in targets:
            if not (os.path.isdir(t.path) and _is_safe(t.path, t.key)):
                continue
            tf = tb = 0
            for root, f in _files(t):
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    try:
                        os.chmod(fp, 0o777)   # evtl. read-only entfernen
                    except OSError:
                        pass
                    os.remove(fp)
                    tf += 1
                    tb += sz
                except OSError:
                    res.errors += 1           # in Benutzung / Zugriff verweigert
            if t.recursive:
                # geleerte Unterordner entfernen, aber NIE das Ziel-Wurzelverzeichnis
                for root, dirs, _files_ in os.walk(t.path, topdown=False):
                    if os.path.normpath(root) != os.path.normpath(t.path):
                        try:
                            os.rmdir(root)
                        except OSError:
                            pass
            res.files_deleted += tf
            res.bytes_freed   += tb
            res.per_target.append((t.label, tf, tb))
    finally:
        if wu:
            _service("start", "wuauserv")
    return res


# ── Recycle Bin (shell32 — the same API Explorer uses) ───────────────────────

def recycle_bin_info() -> tuple[int, int]:
    """(items, bytes) in the Recycle Bin of all drives; (0, 0) if unknown."""
    if os.name != "nt":
        return 0, 0
    try:
        import ctypes
        from ctypes import wintypes

        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                        ("i64NumItems", ctypes.c_longlong)]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return int(info.i64NumItems), int(info.i64Size)
    except Exception:
        pass
    return 0, 0


def empty_recycle_bin() -> tuple[bool, int]:
    """Empty the Recycle Bin of all drives without Explorer's own prompt (the
    app asks first). -> (ok, bytes freed)."""
    items, size = recycle_bin_info()
    if items == 0:
        return True, 0
    try:
        import ctypes
        SHERB_NOCONFIRMATION, SHERB_NOPROGRESSUI, SHERB_NOSOUND = 0x1, 0x2, 0x4
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        left, left_size = recycle_bin_info()
        return hr == 0 or left == 0, max(0, size - left_size)
    except Exception:
        return False, 0


def human_size(nbytes: float) -> str:
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
