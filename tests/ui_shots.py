"""Screenshots of every page of the REAL app (real hardware readers, read-only;
temp log dir and temp settings; nothing is applied, no dialog is answered).
The window is VISIBLE (topmost) while it runs — not part of run_all_tests.

    python tests\\ui_shots.py [width height]      -> logs\\shots\\NN_page_WIDTH.png
"""
import json, os, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "logs", "shots")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from tkinter import messagebox
DIALOGS = []
for n in ("askyesno", "askyesnocancel", "showinfo", "showwarning", "showerror", "askokcancel"):
    setattr(messagebox, n, (lambda n: lambda *a, **k: DIALOGS.append((n, a[:1])) or False)(n))
import tkinter as tk
ERRORS = []
tk.Tk.report_callback_exception = lambda self, e, v, tb: ERRORS.append(
    "".join(traceback.format_exception(e, v, tb))[-900:])

tmp = tempfile.mkdtemp(prefix="gop_shots_")
from pathlib import Path
from core import app_settings
real_settings = app_settings.load()
app_settings.SETTINGS_FILE = Path(tmp) / "settings.json"
for k in ("furmark_path", "3dmark_path"):           # keep the user's links, never write back
    if k in real_settings:
        app_settings.set(k, real_settings[k])
from core import i18n
i18n.init_lang()
from GameOptimizerPro import detect_hw
from core.nvtune_core import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner, TunerConfig
from core.tweak_runner import TweakRunner
from core.crash_recovery import CrashRecovery
from core.startup_loader import StartupLoader
from core.game_monitor import GameMonitor
import ui.main_window as mw
from PIL import ImageGrab

hw = detect_hw()
mon = GpuMonitor()
ab = AfterburnerController(mon.nvml.get_pci_identity())
pm = ProfileManager(os.path.join(ROOT, "profiles"))
cr = CrashRecovery(tmp)
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=tmp, crash_recovery=cr)
runner = TweakRunner(log_dir=tmp)
try:            # show the user's real applied state (read-only copy)
    runner._applied = json.load(open(os.path.join(ROOT, "logs", "applied_tweaks.json"), encoding="utf-8"))
except Exception:
    pass
runner._save_state = lambda: None
sl = StartupLoader(tmp, ab, pm, cr)
gm = GameMonitor(tmp, ab, pm, cr)

W = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
H = int(sys.argv[2]) if len(sys.argv) > 2 else 900
w = mw.GameOptimizerWindow(hw, mon, ab, pm, tuner, runner, startup_loader=sl, game_monitor=gm)
w.geometry(f"{W}x{H}+40+40")
w.attributes("-topmost", True)
w.unbind_all("<MouseWheel>")          # a wheel turned over the window must not scroll the shots
suffix = f"_{W}"

PLAN = [
    ("dashboard", None, 5500), ("optimizer", None, 1200), ("optimizer", "windows", 2500),
    ("optimizer", "verify", 600), ("optimizer", "exim", 600), ("gpu", None, 1200),
    ("gpu", "profiles", 600), ("gpu", "manual", 600), ("stress", None, 1500), ("compare", None, 800),
    ("bios", None, 4000), ("games", None, 800), ("games", "history", 600), ("diagnose", None, 800),
    ("startup", None, 2500), ("services", None, 4000), ("settings", None, 2500),
]


def grab(name):
    w.update()
    x, y = w.winfo_rootx(), w.winfo_rooty()
    img = ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height()), all_screens=True)
    img.save(os.path.join(OUT, f"{name}{suffix}.png"))


def step(i=0):
    if i >= len(PLAN):
        w.after(200, finish)
        return
    key, sub, wait = PLAN[i]
    w._show_tab(key)
    page = w._tab_frames[key]
    if sub:
        if key == "optimizer":
            page._show_section(sub)
        else:
            page._show_view(sub)
    w.after(wait, lambda: (grab(f"{i:02d}_{key}" + (f"_{sub}" if sub else "")), step(i + 1)))


def finish():
    print("screenshots:", OUT)
    print("dialogs:", DIALOGS)
    print("errors:", len(ERRORS))
    for e in ERRORS:
        print("-----\n" + e)
    w.quit()


w.after(1500, step)
w.after(120000, w.quit)
w.mainloop()
try:
    mon.close()
except Exception:
    pass
sys.stdout.flush()
os._exit(1 if ERRORS else 0)
