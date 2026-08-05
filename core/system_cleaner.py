"""
GameOptimizerPro v2.1.1 — System Cleaner (Temp / Junk)
Löscht AUSSCHLIESSLICH Dateien aus dedizierten Temp-/Dump-Verzeichnissen.
Fasst NIEMALS Benutzerdokumente, Browserprofile oder den Papierkorb an.
Dateien, die gerade in Benutzung sind, werden übersprungen (kein Fehler).
"""

import os
from dataclasses import dataclass, field


@dataclass
class CleanTarget:
    label:      str
    path:       str
    file_count: int  = 0
    bytes:      int  = 0
    exists:     bool = False


@dataclass
class CleanResult:
    files_deleted: int  = 0
    bytes_freed:   int  = 0
    errors:        int  = 0            # übersprungene (in Benutzung / kein Zugriff)
    per_target:    list = field(default_factory=list)  # (label, files, bytes)


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
        out.append(CleanTarget(label=label, path=p, exists=os.path.isdir(p)))
    return out


def _is_safe(path: str) -> bool:
    """Schutzgitter: nur eindeutige Temp-/Dump-Pfade zulassen."""
    p = os.path.normpath(path).lower()
    return len(p) > 8 and (os.sep + "temp" in p or p.endswith("crashdumps"))


def scan(targets: list[CleanTarget] | None = None) -> list[CleanTarget]:
    """Ermittelt Größe/Anzahl der löschbaren Dateien. Rein lesend."""
    targets = targets or get_targets()
    for t in targets:
        t.file_count, t.bytes = 0, 0
        t.exists = os.path.isdir(t.path)
        if not (t.exists and _is_safe(t.path)):
            continue
        for root, _dirs, files in os.walk(t.path):
            for f in files:
                try:
                    t.bytes += os.path.getsize(os.path.join(root, f))
                    t.file_count += 1
                except OSError:
                    pass
    return targets


def clean(targets: list[CleanTarget] | None = None) -> CleanResult:
    """Löscht Dateien in den (sicheren) Zielen. In-Benutzung → übersprungen."""
    targets = targets or get_targets()
    res = CleanResult()
    for t in targets:
        if not (os.path.isdir(t.path) and _is_safe(t.path)):
            continue
        tf = tb = 0
        for root, _dirs, files in os.walk(t.path, topdown=False):
            for f in files:
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
            # geleerte Unterordner entfernen, aber NIE das Ziel-Wurzelverzeichnis
            if os.path.normpath(root) != os.path.normpath(t.path):
                try:
                    os.rmdir(root)
                except OSError:
                    pass
        res.files_deleted += tf
        res.bytes_freed   += tb
        res.per_target.append((t.label, tf, tb))
    return res


def human_size(nbytes: float) -> str:
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
