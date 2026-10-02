"""The real start-up path: GameOptimizerPro.main() -> GameOptimizerApp().run()
with the real tray menu (pystray builds and validates every menu action) and
the real main window. Round 14 shipped a tray action with three parameters:
pystray raised ValueError while building the menu — Afterburner had already
been restarted, the window never came up, and pythonw showed no error.

Runs in a child process (the app ends with os._exit). Nothing is applied: no
start-up profile (no Afterburner restart), no crash check, no update check, the
tray icon is built but never shown, settings go to a temp file. Run it via
run_hidden_desktop.py (run_all_tests.py does) — the window never appears."""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)


CHILD = r'''
import os, sys, threading, json, traceback
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.argv = [os.path.join(ROOT, "GameOptimizerPro.py"), "--no-admin-prompt"]
from pathlib import Path
from core import app_settings
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
app_settings.set("check_updates", False)
import tkinter as tk
ERR = []
tk.Tk.report_callback_exception = lambda self, e, v, tb: ERR.append("".join(traceback.format_exception(e, v, tb)))
import GameOptimizerPro as G
G.StartupLoader.load_startup_profile = lambda self: (False, "test: not loaded")
G.StartupLoader.check_and_handle_crash = lambda self, on_crash_detected=None: False
G.StartupLoader.repair_autostart_task = lambda self: None
G.TempMonitor.start = lambda self: None
try:
    import pystray
    pystray.Icon.run = lambda self, setup=None: None       # built and validated, never shown
except ImportError:
    pass
APP = []
real_init = G.GameOptimizerApp.__init__
def init(self, *a, **k):
    real_init(self, *a, **k)
    APP.append(self)
G.GameOptimizerApp.__init__ = init
def report():
    app = APP[0] if APP else None
    w = app._window if app else None
    info = {
        "window": bool(w and w.winfo_exists()),
        "title": w.title() if w else "",
        "tray": app is not None and app._tray is not None,
        "menu_items": len(list(app._tray.menu.items)) if app and app._tray and app._tray.menu else 0,
        "pages": sorted(w._tab_frames) if w else [],
        "request_exit": callable(getattr(w, "request_exit", None)),
        "update_flow": hasattr(w, "update_flow"),
        "errors": ERR,
    }
    print("STARTED " + json.dumps(info), flush=True)
    os._exit(0)
threading.Timer(7.0, lambda: w_after(report)).start()
def w_after(fn):
    app = APP[0] if APP else None
    if app and app._window:
        app._window.after(0, fn)
    else:
        fn()
G.main()
'''

tmp = tempfile.mkdtemp(prefix="gop_start_")
code = "ROOT = %r\nTMP = %r\n" % (ROOT, tmp) + CHILD
cmd = [sys.executable, "-c", code]
if os.name == "nt" and os.path.exists(os.path.join(ROOT, "tests", "run_hidden_desktop.py")):
    script = os.path.join(tmp, "child.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(code)
    cmd = [sys.executable, os.path.join(ROOT, "tests", "run_hidden_desktop.py"), script]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
out = r.stdout + r.stderr
line = next((l for l in out.splitlines() if l.startswith("STARTED ")), "")
check(bool(line), "the app starts: main() -> tray menu -> main window" + ("" if line else ":\n" + out[-2500:]))
if line:
    import json
    info = json.loads(line[8:])
    check(info["window"] and "GameOptimizerPro" in info["title"], f"main window up: {info['title']!r}")
    check(info["tray"] and info["menu_items"] >= 5, f"tray icon + menu built ({info['menu_items']} entries)")
    check(info["request_exit"] and info["update_flow"], "update flow and exit hook wired")
    check("dashboard" in info["pages"], f"pages: {info['pages']}")
    check(not info["errors"], f"no Tk callback errors {info['errors'][:1]}")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
