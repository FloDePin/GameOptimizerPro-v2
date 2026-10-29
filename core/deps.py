"""
GameOptimizerPro — first-start setup of the Python packages

A fresh Windows or a new Python has none of the packages in requirements.txt. The app used to
start anyway (pythonw has no console): pages died with "No module named 'PIL'", the sidebar
showed 0 GB RAM, a dialog lost its buttons. This module checks the packages BEFORE anything
imports them and installs what is missing with pip — in the launcher's console
(GameOptimizerPro.bat runs `python -m core.deps`) or with a small progress window when the app
is started another way (autostart, double-click on the .py, restart after an update).

Standard library only: it runs before any package is there.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REQUIREMENTS = BASE / "requirements.txt"
SETUP_LOG = BASE / "logs" / "setup.log"
MIN_PYTHON = (3, 10)

# distribution name (lower case) -> import name, where they differ
_IMPORT_NAME = {"nvidia-ml-py": "pynvml", "pillow": "PIL"}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def requirements(path=REQUIREMENTS) -> list[tuple[str, str, str]]:
    """[(pip spec, distribution name, minimum version or '')] from requirements.txt."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(?:>=\s*([0-9][0-9A-Za-z.]*))?", line)
        if line and m:
            out.append((line, m.group(1), m.group(3) or ""))
    return out


def _vtuple(v: str) -> tuple:
    parts = []
    for p in re.split(r"[.+\-]", v or ""):
        m = re.match(r"\d+", p)
        if not m:
            break
        parts.append(int(m.group()))
    return tuple(parts)


def _installed_version(dist: str) -> str | None:
    from importlib import metadata
    for name in dict.fromkeys((dist, dist.lower(), dist.replace("-", "_"), dist.lower().replace("-", "_"))):
        try:
            return metadata.version(name)
        except Exception:
            continue
    return None


def import_name(dist: str) -> str:
    return _IMPORT_NAME.get(dist.lower(), dist.lower().replace("-", "_"))


def missing(path=REQUIREMENTS) -> list[str]:
    """pip specs of the requirements that are not importable or older than required."""
    import importlib.util
    out = []
    for spec, dist, minver in requirements(path):
        try:
            found = importlib.util.find_spec(import_name(dist)) is not None
        except Exception:                 # e.g. sys.modules[name] = None
            found = False
        if not found:
            out.append(spec)
            continue
        have = _installed_version(dist) if minver else None
        if have and _vtuple(have) < _vtuple(minver):
            out.append(spec)
    return out


def console_python(exe: str | None = None) -> str:
    """python.exe next to pythonw.exe — pip needs an interpreter with standard streams."""
    exe = exe or sys.executable
    folder, name = os.path.split(exe)
    if name.lower() == "pythonw.exe":
        c = os.path.join(folder, "python.exe")
        if os.path.exists(c):
            return c
    return exe


def _run(cmd: list, on_line=None, timeout: float = 900) -> tuple[int, str]:
    """Run cmd, hand every output line to on_line; -> (exit code, whole output)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace", env=env, creationflags=_NO_WINDOW)
    except OSError as e:
        return 1, str(e)
    killer = threading.Timer(timeout, p.kill)
    killer.start()
    lines = []
    try:
        for line in p.stdout:
            line = line.rstrip()
            lines.append(line)
            if on_line and line:
                on_line(line)
        p.wait()
    finally:
        killer.cancel()
    return p.returncode, "\n".join(lines)


def pip_install(specs, on_line=None, python: str | None = None) -> tuple[bool, str]:
    """pip install the specs (pip itself is set up first when this Python has none)."""
    py = python or console_python()
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *specs]
    code, out = _run(cmd, on_line)
    if code != 0 and "no module named pip" in out.lower():
        c2, o2 = _run([py, "-m", "ensurepip", "--upgrade"], on_line)
        out += "\n" + o2
        if c2 == 0:
            code, o3 = _run(cmd, on_line)
            out += "\n" + o3
    return code == 0, out


def _add_user_site():
    """pip falls back to the user's site-packages when the Python folder is not writable; a folder
    that did not exist when Python started is not on sys.path yet."""
    try:
        import site
        p = site.getusersitepackages()
        if p and os.path.isdir(p) and p not in sys.path:
            site.addsitedir(p)
    except Exception:
        pass


def _lang() -> str:
    """The app's saved language; before the first start: Windows' display language."""
    try:
        from core import i18n
        if i18n._LANG_FILE.exists():
            return i18n.init_lang()
    except Exception:
        pass
    try:
        import ctypes
        if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x07:     # LANG_GERMAN
            return "de"
    except Exception:
        pass
    return "en"


def _t(de: str, en: str) -> str:
    return de if _lang() == "de" else en


def explain(output: str) -> str:
    """What went wrong, in plain words."""
    o = (output or "").lower()
    if any(s in o for s in ("getaddrinfo failed", "failed to establish a new connection", "name resolution",
                            "max retries exceeded", "network is unreachable", "connection refused",
                            "read timed out", "connectionerror", "no route to host")):
        return _t("Keine Internetverbindung — GameOptimizerPro braucht beim ersten Start einmalig Internet, "
                  "um seine Komponenten zu laden. Verbindung prüfen und neu starten.",
                  "No internet connection — GameOptimizerPro needs the internet once on its first start to "
                  "download its components. Check the connection and start again.")
    if "could not find a version that satisfies" in o or "no matching distribution" in o:
        ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        return _t(f"Ein benötigtes Paket gibt es für Python {ver} nicht. Bitte Python 3.12 von python.org "
                  "installieren und neu starten.",
                  f"A required package is not available for Python {ver}. Please install Python 3.12 from "
                  "python.org and start again.")
    if "permission" in o or "access is denied" in o or "zugriff verweigert" in o:
        return _t("Keine Schreibrechte im Python-Ordner — GameOptimizerPro.bat starten (fragt nach "
                  "Administratorrechten) oder install.bat als Administrator ausführen.",
                  "No write access to the Python folder — start GameOptimizerPro.bat (asks for administrator "
                  "rights) or run install.bat as administrator.")
    if "no module named pip" in o or "no module named ensurepip" in o:
        return _t("In dieser Python-Installation fehlt pip — Python von python.org neu installieren.",
                  "This Python installation has no pip — reinstall Python from python.org.")
    return _t("Die Einrichtung hat nicht geklappt. Bitte install.bat ausführen.",
              "The setup did not work. Please run install.bat.")


def _write_log(text: str):
    try:
        SETUP_LOG.parent.mkdir(parents=True, exist_ok=True)
        SETUP_LOG.write_text(text or "", encoding="utf-8")
    except OSError:
        pass


def _message(text: str, error: bool = True):
    try:
        import ctypes
        # MB_ICONERROR / MB_ICONINFORMATION | MB_TOPMOST
        ctypes.windll.user32.MessageBoxW(0, text, "GameOptimizerPro", (0x10 if error else 0x40) | 0x40000)
    except Exception:
        print(text)


def _gui_install(specs) -> tuple[bool, str]:
    """pip in a worker thread, a small progress window in this (the main) thread."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:                  # Python without Tk: no window, still install
        return pip_install(specs)
    result, lines = {}, []

    def work():
        result["r"] = pip_install(specs, on_line=lines.append)

    root = tk.Tk()
    root.title("GameOptimizerPro")
    root.configure(bg="#0f1117")
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", lambda: None)        # pip must not be cut off half-way
    frame = tk.Frame(root, bg="#0f1117")
    frame.pack(padx=24, pady=20)
    tk.Label(frame, text=_t("Einmalige Einrichtung", "One-time setup"), font=("Segoe UI Semibold", 14),
             fg="#e6e8ee", bg="#0f1117").pack(anchor="w")
    tk.Label(frame, text=_t("GameOptimizerPro lädt die benötigten Komponenten (ca. 50 MB).\n"
                            "Das dauert meist unter einer Minute — bitte nicht schließen.",
                            "GameOptimizerPro is downloading the components it needs (about 50 MB).\n"
                            "This usually takes less than a minute — please don't close it."),
             font=("Segoe UI", 10), fg="#9aa3b2", bg="#0f1117", justify="left").pack(anchor="w", pady=(6, 12))
    bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
    bar.pack(anchor="w")
    bar.start(12)
    status = tk.Label(frame, text="", font=("Segoe UI", 9), fg="#00d9ff", bg="#0f1117", anchor="w", width=60)
    status.pack(anchor="w", pady=(8, 0))
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f"+{max(0, x)}+{max(0, y)}")
    worker = threading.Thread(target=work, daemon=True)
    worker.start()

    def poll():
        if lines:
            status.config(text=lines[-1][:80])
        if worker.is_alive():
            root.after(150, poll)
        else:
            bar.stop()                   # its own timer must not fire into a destroyed window
            root.destroy()
    root.after(150, poll)
    root.mainloop()
    worker.join()
    return result.get("r", (False, ""))


def ensure(gui: bool = True) -> bool:
    """True when every package is there (installed now if needed). False after telling the user why
    not — the caller ends the start then."""
    if sys.version_info < MIN_PYTHON:
        ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        text = _t(f"Python {ver} ist zu alt für GameOptimizerPro — bitte Python 3.12 von python.org installieren.",
                  f"Python {ver} is too old for GameOptimizerPro — please install Python 3.12 from python.org.")
        _message(text) if gui else print(text)
        return False
    specs = missing()
    if not specs:
        return True
    if gui:
        ok, out = _gui_install(specs)
    else:
        print(_t("Erster Start: GameOptimizerPro installiert die benötigten Komponenten (einmalig, ca. 1 Minute) …",
                 "First start: GameOptimizerPro is installing the components it needs (one time, about 1 minute) …"))
        ok, out = pip_install(specs, on_line=lambda s: print("  " + s))
    _write_log(out)
    import importlib
    importlib.invalidate_caches()
    _add_user_site()
    still = missing()
    if not still:
        if not gui:
            print(_t("Fertig — alle Komponenten sind installiert.", "Done — all components are installed."))
        return True
    text = (explain(out) if not ok else
            _t("Installiert, aber nicht gefunden: ", "Installed, but not found: ") + ", ".join(still))
    text += "\n\n" + _t("Details: ", "Details: ") + str(SETUP_LOG)
    _message(text) if gui else print("\n" + text)
    return False


if __name__ == "__main__":
    try:                                 # a redirected console: never die on a character
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    sys.exit(0 if ensure(gui=False) else 1)
