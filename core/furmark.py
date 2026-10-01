"""
GameOptimizerPro v2.0 — FurMark launcher logic (FurMark 1 and FurMark 2)

FurMark 2 (2023+) is a different program: a command-line runner `furmark.exe`
next to `FurMark_GUI.exe`, with options like
    furmark --demo furmark-gl --width 1920 --height 1080 --max-time 60
FurMark 1 was a single `FurMark.exe` with `/width= /height= /max_time= /nogui`.
The launcher used to pass the FurMark-1 switches to whatever it found — and it
never remembered a location picked with "Browse".
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from core import app_settings

APP_DIR = Path(__file__).resolve().parent.parent
SETTING_KEY = "furmark_path"

# FurMark 2 demos (from `furmark --demolist`, v2.8)
DEMOS = {
    "furmark-gl": "FurMark (OpenGL)",
    "furmark-vk": "FurMark (Vulkan)",
    "furmark-knot-gl": "FurMark Knot (OpenGL)",
    "furmark-knot-vk": "FurMark Knot (Vulkan)",
}

_INSTALL_PATHS = [
    # FurMark 2 installer
    r"C:\Program Files\Geeks3D\FurMark2_x64\furmark.exe",
    r"C:\Program Files\Geeks3D\FurMark2\furmark.exe",
    r"C:\Program Files\Geeks3D\FurMark_win64\furmark.exe",
    # FurMark 1
    r"C:\Program Files\Geeks3D\Benchmarks\FurMark\FurMark.exe",
    r"C:\Program Files (x86)\Geeks3D\Benchmarks\FurMark\FurMark.exe",
    r"C:\Program Files\FurMark\FurMark.exe",
    r"C:\Program Files (x86)\FurMark\FurMark.exe",
]


def normalize(path: str) -> str:
    """FurMark 2's GUI exe -> the command-line runner next to it."""
    p = Path(path)
    if p.name.lower() == "furmark_gui.exe":
        cli = p.with_name("furmark.exe")
        if cli.exists():
            return str(cli)
    return str(p)


def is_v2(path: str) -> bool:
    p = Path(path)
    if (p.parent / "FurMark_GUI.exe").exists():
        return True
    help_txt = p.parent / "help.txt"
    try:
        return "furmark v2" in help_txt.read_text(encoding="utf-8", errors="ignore")[:200].lower()
    except OSError:
        return False


def file_version(path: str) -> str:
    """Windows file version of an .exe ("2.8.0.0"), "" if unknown."""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return ""
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)) or not ptr.value:
            return ""

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [("sig", wintypes.DWORD), ("struc", wintypes.DWORD),
                        ("ms", wintypes.DWORD), ("ls", wintypes.DWORD)]
        info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        if info.sig != 0xFEEF04BD:
            return ""
        return f"{info.ms >> 16}.{info.ms & 0xFFFF}.{info.ls >> 16}.{info.ls & 0xFFFF}"
    except Exception:
        return ""


def describe(path: str) -> str:
    """'FurMark 2 (v2.10.2)' / 'FurMark 1 (v1.38.1)' for the UI. FurMark 2's
    furmark.exe carries no version (0.0.0.0) — the GUI exe next to it does."""
    gen = 2 if is_v2(path) else 1
    v = ""
    gui = Path(path).with_name("FurMark_GUI.exe")
    for exe in ([str(gui)] if gui.exists() else []) + [path]:
        v = file_version(exe)
        if v and v != "0.0.0.0":
            break
        v = ""
    if v.endswith(".0"):
        v = v[:-2]
    return f"FurMark {gen}" + (f" (v{v})" if v else "")


def detect() -> str | None:
    """Saved choice first, then a FurMark folder next to the app (portable zip
    extracted there), then the usual install locations."""
    saved = app_settings.get(SETTING_KEY)
    if saved and os.path.exists(saved):
        return normalize(saved)
    # real file names (glob would echo the pattern's case: FurMark 1 is "FurMark.exe");
    # FurMark 2 first when both are there
    local = [p for base in (APP_DIR, APP_DIR / "tools")
             for p in sorted(glob.glob(str(base / "FurMark*" / "*.exe")))
             if os.path.basename(p).lower() == "furmark.exe"]
    local.sort(key=lambda p: not is_v2(p))
    for p in local + _INSTALL_PATHS:
        if os.path.exists(p):
            return normalize(p)
    return None


def remember(path: str) -> str:
    path = normalize(path)
    app_settings.set(SETTING_KEY, path)
    return path


MSAA_CHOICES = (0, 2, 4, 8)


def build_args(path: str, width: int, height: int, seconds: int,
               demo: str = "furmark-gl", msaa: int = 0) -> list[str]:
    """FurMark 2: its own command line; --vsync 0 (a driver-forced VSync still
    wins — then only a heavier load helps: MSAA). FurMark 1: its switches."""
    if is_v2(path):
        args = [path, "--demo", demo if demo in DEMOS else "furmark-gl",
                "--width", str(width), "--height", str(height),
                "--max-time", str(int(seconds)), "--vsync", "0"]
        if msaa in MSAA_CHOICES and msaa:
            args += ["--msaa", str(msaa)]
        return args
    return [path, f"/width={width}", f"/height={height}",
            f"/max_time={int(seconds) * 1000}", "/nogui", "/run_mode=1"]


def parse_stats(text: str) -> dict:
    """FurMark 2 prints 'Demo Quick Stats' when it ends: frames, FPS
    min/avg/max and per GPU the max temperature / usage and core clocks."""
    import re
    out: dict = {}
    m = re.search(r"FPS \(min/avg/max\)\s*:\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", text or "")
    if m:
        out["fps_min"], out["fps_avg"], out["fps_max"] = (int(x) for x in m.groups())
    for key, pat in (("score", r"SCORE\s*:\s*(\d+)"), ("duration_ms", r"duration\s*:\s*(\d+)\s*ms"),
                     ("frames", r"frames\s*:\s*(\d+)"), ("max_temp", r"max temperature:\s*(\d+)"),
                     ("max_usage", r"max usage:\s*(\d+)"), ("clock_max", r"max core clock:\s*(\d+)"),
                     ("clock_min", r"min core clock:\s*(\d+)")):
        m = re.search(pat, text or "")
        if m:
            out[key] = int(m.group(1))
    return out


def benchmark_args(path: str, seconds: float, width: int = 1920, height: int = 1080,
                   msaa: int = 8, demo: str = "furmark-gl") -> list[str]:
    """FurMark 2 scored benchmark: fixed duration, no score box at the end."""
    args = [path, "--demo", demo if demo in DEMOS else "furmark-gl", "--benchmark",
            "--no-score-box", "--duration-ms", str(int(seconds * 1000)),
            "--width", str(width), "--height", str(height), "--vsync", "0"]
    if msaa in MSAA_CHOICES and msaa:
        args += ["--msaa", str(msaa)]
    return args


def run_benchmark(path: str, seconds: float, width: int = 1920, height: int = 1080,
                  msaa: int = 8, demo: str = "furmark-gl", stop_event=None,
                  on_tick=None, grace_s: float = 90.0) -> dict:
    """Run a FurMark 2 benchmark and wait for it (blocks ~seconds + start-up).
    -> {"ok", "score", "fps_avg", "fps_min", "max_temp", "max_usage", "exit_code",
        "aborted", "error", "elapsed_s", "duration_ms"}. FurMark crashing (non-zero
    exit), hanging past the grace time or printing no score counts as NOT ok.
    elapsed_s (wall time) and duration_ms (FurMark's own) let the caller spot a
    run that ended far too early. on_tick(elapsed_s) is called about once a
    second (e.g. to record power and temperature)."""
    import subprocess
    import threading
    import time
    res = {"ok": False, "score": 0, "fps_avg": 0, "fps_min": 0, "max_temp": 0,
           "max_usage": 0, "exit_code": None, "aborted": False, "error": "",
           "elapsed_s": 0.0, "duration_ms": 0}
    if not path or not os.path.exists(path) or not is_v2(path):
        res["error"] = "FurMark 2 nicht gefunden"
        return res
    try:
        proc = subprocess.Popen(benchmark_args(path, seconds, width, height, msaa, demo),
                                cwd=os.path.dirname(path), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as e:
        res["error"] = f"FurMark ließ sich nicht starten: {e}"
        return res
    out: list = []
    reader = threading.Thread(target=lambda: out.append(proc.stdout.read() or ""), daemon=True)
    reader.start()
    t0 = time.time()
    last_tick = 0.0
    while proc.poll() is None:
        el = time.time() - t0
        if stop_event is not None and stop_event.is_set():
            proc.kill()
            res.update(aborted=True, error="abgebrochen", elapsed_s=round(el, 1))
            return res
        if el > seconds + grace_s:
            proc.kill()
            res.update(error=f"FurMark hängt ({el:.0f} s) — abgebrochen", elapsed_s=round(el, 1))
            return res
        if on_tick is not None and el - last_tick >= 1.0:
            last_tick = el
            try:
                on_tick(el)
            except Exception:
                pass
        time.sleep(0.2)
    res["elapsed_s"] = round(time.time() - t0, 1)
    reader.join(timeout=5)
    stats = parse_stats("".join(out))
    res["exit_code"] = proc.returncode
    for k in ("score", "fps_avg", "fps_min", "max_temp", "max_usage", "duration_ms"):
        res[k] = stats.get(k, 0)
    if proc.returncode != 0:
        res["error"] = f"FurMark endete mit Code {proc.returncode} (Absturz?)"
    elif not res["score"]:
        res["error"] = "FurMark lieferte keine Punktzahl"
    else:
        res["ok"] = True
    return res
