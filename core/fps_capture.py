"""
GameOptimizerPro v2.0 — FPS / Frametime Capture & Analysis

Turns the tool from "apply tweaks blindly" into "measure the actual result".
Two paths, both producing the same metrics:

  1. LIVE capture — drives Intel's open-source **PresentMon** (if the binary is
     present) to record a real play session for N seconds, then parses its CSV.
  2. ANALYZE — ingest any existing PresentMon / CapFrameX / OCAT frametime CSV.

Metrics computed from per-frame frametimes (the same ones the pros quote):
  • Average FPS
  • 1% low  (FPS at the 99th-percentile frametime)
  • 0.1% low (FPS at the 99.9th-percentile frametime)
  • min/max FPS, frame count, capture duration
  • stutter count (frames longer than 2× the median frametime)
  • GPU-busy ratio → a measured CPU-vs-GPU **bottleneck** verdict, when the CSV
    carries a per-frame GPU-active column (PresentMon does).

PresentMon is NOT bundled (it's a separate Intel MIT tool). We look for it and,
if it's missing, say exactly where to get it — nothing is faked.
"""

from __future__ import annotations
import csv
import os
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable

PRESENTMON_URL = "https://github.com/GameTechDev/PresentMon/releases"

# Candidate frametime column names across PresentMon / CapFrameX / OCAT versions
_FRAMETIME_COLS = [
    "msbetweenpresents", "frametime", "frametime_ms", "ms",
    "msbetweendisplaychange", "frame time (ms)",
]
# Candidate per-frame GPU-active (busy) column names (for the bottleneck verdict)
_GPUBUSY_COLS = ["msgpuactive", "gpubusy", "msgpubusy", "gpu busy (ms)"]


@dataclass
class FrameStats:
    ok:            bool = False
    frame_count:   int = 0
    duration_s:    float = 0.0
    avg_fps:       float = 0.0
    fps_1pct_low:  float = 0.0
    fps_01pct_low: float = 0.0
    min_fps:       float = 0.0
    max_fps:       float = 0.0
    avg_frametime_ms: float = 0.0
    stutter_count: int = 0
    gpu_busy_ratio: float = -1.0     # -1 = unknown (no GPU column)
    bottleneck:    str = "unknown"   # "gpu" | "cpu" | "unknown"
    source:        str = ""
    error:         str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── PresentMon discovery ────────────────────────────────────────────────────

def find_presentmon() -> Optional[str]:
    """Locate a PresentMon executable. Checks a bundled tools/ dir, the project
    root, and PATH. Returns the full path or None."""
    base = Path(__file__).resolve().parent.parent
    names = [
        "PresentMon.exe", "presentmon.exe",
        "PresentMon-x64.exe", "PresentMon-2.exe",
    ]
    search_dirs = [base / "tools", base, base / "bin"]
    for d in search_dirs:
        try:
            if d.is_dir():
                # exact names first
                for n in names:
                    p = d / n
                    if p.is_file():
                        return str(p)
                # any PresentMon*.exe
                for p in d.glob("PresentMon*.exe"):
                    if p.is_file():
                        return str(p)
        except Exception:
            continue
    # PATH
    from shutil import which
    for n in names:
        w = which(n)
        if w:
            return w
    return None


# ── Metrics ─────────────────────────────────────────────────────────────────

def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Value at the given percentile (0..100) of an ascending-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def compute_stats(frametimes_ms: list[float],
                  gpu_busy_ms: Optional[list[float]] = None,
                  source: str = "") -> FrameStats:
    """Compute FPS/frametime metrics from a list of per-frame frametimes (ms)."""
    s = FrameStats(source=source)
    ft = [f for f in frametimes_ms if f and f > 0.0]
    if len(ft) < 10:
        s.error = "Zu wenige Frames für eine Auswertung (mindestens 10 nötig)."
        return s

    s.frame_count = len(ft)
    s.duration_s = sum(ft) / 1000.0
    s.avg_frametime_ms = statistics.fmean(ft)
    s.avg_fps = 1000.0 / s.avg_frametime_ms if s.avg_frametime_ms else 0.0

    asc = sorted(ft)
    # Long frametimes = low FPS. 1% low = FPS at the 99th-percentile frametime.
    s.fps_1pct_low  = 1000.0 / _percentile(asc, 99.0)
    s.fps_01pct_low = 1000.0 / _percentile(asc, 99.9)
    s.min_fps = 1000.0 / asc[-1]     # slowest frame
    s.max_fps = 1000.0 / asc[0]      # fastest frame

    median_ft = statistics.median(ft)
    thresh = median_ft * 2.0
    s.stutter_count = sum(1 for f in ft if f > thresh)

    # Bottleneck: fraction of wall-time the GPU was actually busy.
    if gpu_busy_ms:
        gb = [g for g in gpu_busy_ms if g is not None and g >= 0.0]
        if gb and sum(ft) > 0:
            total_ft = sum(ft[:len(gb)]) if len(gb) < len(ft) else sum(ft)
            s.gpu_busy_ratio = min(1.0, sum(gb) / total_ft) if total_ft else -1.0
            if s.gpu_busy_ratio >= 0.0:
                # >=95% GPU-busy → GPU-bound; otherwise the GPU is waiting → CPU-bound
                s.bottleneck = "gpu" if s.gpu_busy_ratio >= 0.95 else "cpu"

    s.ok = True
    return s


# ── CSV parsing ───────────────────────────────────────────────────────────────

def parse_csv(path: str) -> FrameStats:
    """Parse a PresentMon / CapFrameX / OCAT frametime CSV into FrameStats."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except Exception as e:
        return FrameStats(error=f"CSV konnte nicht gelesen werden: {e}")

    # Find the header row (the first row that names a known frametime column)
    header_idx = -1
    for i, row in enumerate(rows[:20]):
        low = [c.strip().lower() for c in row]
        if any(any(fc == c or fc in c for fc in _FRAMETIME_COLS) for c in low):
            header_idx = i
            break
    if header_idx < 0:
        return FrameStats(error="Keine Frametime-Spalte in der CSV gefunden "
                                "(PresentMon/CapFrameX-Format erwartet).")

    header = [c.strip().lower() for c in rows[header_idx]]

    def _col(cands):
        for j, name in enumerate(header):
            if any(c == name for c in cands):
                return j
        for j, name in enumerate(header):
            if any(c in name for c in cands):
                return j
        return -1

    ft_idx = _col(_FRAMETIME_COLS)
    gb_idx = _col(_GPUBUSY_COLS)
    if ft_idx < 0:
        return FrameStats(error="Frametime-Spalte nicht eindeutig bestimmbar.")

    frametimes, gpu_busy = [], []
    for row in rows[header_idx + 1:]:
        if len(row) <= ft_idx:
            continue
        try:
            frametimes.append(float(row[ft_idx]))
        except (ValueError, IndexError):
            continue
        if gb_idx >= 0 and len(row) > gb_idx:
            try:
                gpu_busy.append(float(row[gb_idx]))
            except (ValueError, IndexError):
                gpu_busy.append(-1.0)

    return compute_stats(frametimes, gpu_busy if gb_idx >= 0 else None,
                         source=os.path.basename(path))


# ── Live capture via PresentMon ─────────────────────────────────────────────

def capture_live(process_name: str, duration_s: int = 30,
                 presentmon_path: Optional[str] = None) -> FrameStats:
    """Record `duration_s` seconds of `process_name` via PresentMon, then parse.
    Returns FrameStats (with .error set if PresentMon is missing or fails).
    Blocking — call from a worker thread."""
    exe = presentmon_path or find_presentmon()
    if not exe:
        return FrameStats(error=(
            "PresentMon nicht gefunden. Lege PresentMon.exe in den 'tools'-Ordner "
            f"neben die App (Download: {PRESENTMON_URL}), dann erneut versuchen. "
            "Alternativ eine vorhandene PresentMon/CapFrameX-CSV analysieren."))
    if os.name != "nt":
        return FrameStats(error="Live-Capture nur unter Windows verfügbar.")

    out_csv = os.path.join(tempfile.gettempdir(),
                           f"gop_fps_{int(time.time())}.csv")
    # Flag set that works with the common standalone PresentMon builds. The exact
    # CLI differs across major versions, so we stay defensive and simply parse
    # whatever CSV is produced; if none appears, we report that honestly.
    cmd = [exe,
           "-process_name", process_name,
           "-output_file", out_csv,
           "-timed", str(int(duration_s)),
           "-terminate_after_timed",
           "-stop_existing_session",
           "-no_top"]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=duration_s + 30, creationflags=flags)
    except subprocess.TimeoutExpired:
        return FrameStats(error="PresentMon-Capture hat das Zeitlimit überschritten.")
    except Exception as e:
        return FrameStats(error=f"PresentMon konnte nicht gestartet werden: {e}")

    if not os.path.exists(out_csv):
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        return FrameStats(error=(
            "PresentMon hat keine CSV erzeugt — läuft das Spiel und wurde es "
            f"exakt als '{process_name}' erkannt? "
            + (f"[{detail}]" if detail else "")))

    stats = parse_csv(out_csv)
    try:
        os.remove(out_csv)
    except OSError:
        pass
    return stats


# ── Human-readable summary ────────────────────────────────────────────────────

def format_summary(s: FrameStats) -> list[str]:
    """Return a list of display lines for the UI log box."""
    if not s.ok:
        return [f"✗ {s.error or 'Keine Auswertung möglich.'}"]
    lines = [
        f"Frames: {s.frame_count}   Dauer: {s.duration_s:.1f}s   Quelle: {s.source}",
        f"Ø FPS:        {s.avg_fps:6.1f}",
        f"1% Low:       {s.fps_1pct_low:6.1f}",
        f"0.1% Low:     {s.fps_01pct_low:6.1f}",
        f"Min / Max:    {s.min_fps:6.1f} / {s.max_fps:.1f}",
        f"Ø Frametime:  {s.avg_frametime_ms:6.2f} ms",
        f"Stutters:     {s.stutter_count}  (Frames > 2× Median-Frametime)",
    ]
    if s.gpu_busy_ratio >= 0.0:
        verdict = ("GPU-limitiert (GPU voll ausgelastet)" if s.bottleneck == "gpu"
                   else "CPU-limitiert (GPU wartet auf die CPU)")
        lines.append(f"GPU-Auslastung: {s.gpu_busy_ratio*100:4.0f}%  →  {verdict}")
    else:
        lines.append("Bottleneck: unbekannt (CSV ohne GPU-Spalte)")
    return lines


if __name__ == "__main__":
    # Smoke test with a synthetic frametime series
    import random
    base = [16.6] * 5000 + [16.7, 16.5] * 100
    base += [40.0] * 30      # a few slow frames (stutters / 1% low)
    base += [90.0] * 3       # 0.1% low
    random.shuffle(base)
    st = compute_stats(base, source="synthetic")
    for l in format_summary(st):
        print(l)
