"""Read-only smoke test: build the REAL main window with the real components the
app uses (NVML, MAHM, Afterburner controller, tweak runner in a TEMP log dir),
open every page (Autostart + Services manager are pages now), run the mainloop
for a few seconds and close. Nothing is applied; no dialog is answered; the
window position is saved to a TEMP settings file, not the user's."""
import os, sys, tempfile, time, threading, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from tkinter import messagebox
DIALOGS = []
for n in ("askyesno", "askyesnocancel", "showinfo", "showwarning", "showerror", "askokcancel"):
    setattr(messagebox, n, (lambda n: lambda *a, **k: DIALOGS.append((n, a[:1])) or False)(n))

errors = []
import tkinter as tk
def report(self, exc, val, tb):
    errors.append("".join(traceback.format_exception(exc, val, tb))[-800:])
tk.Tk.report_callback_exception = report

tmp = tempfile.mkdtemp(prefix="gop_smoke_")
from pathlib import Path
from core import app_settings
app_settings.SETTINGS_FILE = Path(tmp) / "settings.json"     # never the user's file

from core import i18n
i18n.init_lang()
from GameOptimizerPro import detect_hw
from core.nvtune_core import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner, TunerConfig
from core.tweak_runner import TweakRunner
from core.crash_recovery import CrashRecovery
from core.startup_loader import StartupLoader
import ui.main_window as mw
from ui.main_window import GameOptimizerWindow

t0 = time.time()
hw = detect_hw()
mon = GpuMonitor()
ab = AfterburnerController(mon.nvml.get_pci_identity())
ab.on_ab_closing = mon.mahm.suspend
ab.on_ab_started = mon.mahm.resume
pm = ProfileManager(os.path.join(ROOT, "profiles"))
cr = CrashRecovery(tmp)
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=tmp, crash_recovery=cr)
runner = TweakRunner(log_dir=tmp)
sl = StartupLoader(tmp, ab, pm, cr)
print(f"components up in {time.time() - t0:.1f}s — GPU: {hw.gpu_name}, VRAM {hw.gpu_vram_mb} MB, "
      f"RAM {hw.ram_type}, NVMe {hw.has_nvme}")

from core.game_monitor import GameMonitor
gm = GameMonitor(tmp, ab, pm, cr)          # built like the app does, never started
t0 = time.time()
w = GameOptimizerWindow(hw, mon, ab, pm, tuner, runner, startup_loader=sl, game_monitor=gm)
w.attributes("-alpha", 0.0)          # invisible on the desktop
print(f"main window built in {(time.time() - t0) * 1000:.0f} ms, pages at start: {list(w._tab_frames)}")
tabs = [k for k, *_x in mw.TAB_DEFS]
TIMES = {}

def cycle(i=0):
    if i < len(tabs):
        t = time.perf_counter()
        w._show_tab(tabs[i])
        w.update()
        TIMES[tabs[i]] = (time.perf_counter() - t) * 1000
        w.after(700, cycle, i + 1)
    else:
        w._open_startup_mgr()
        w._open_services()
        w.after(4000, finish)

def finish():
    print("page open times (first visit incl. build):",
          ", ".join(f"{k} {v:.0f} ms" for k, v in TIMES.items()))
    tops = [c for c in w.winfo_children() if isinstance(c, tk.Toplevel)]
    print("toplevels:", [t.title() for t in tops])
    dash = w._tab_frames["dashboard"]
    print("dashboard score:", repr(dash.lbl_score.cget("text")))
    print("monitor rows:", len(dash._mon_rows.winfo_children()))
    svc = w._tab_frames["services"]
    print("services rows:", len(svc.tree.get_children()), "|", svc.lbl_count.cget("text"))
    st = w._tab_frames["startup"]
    print("startup rows:", len(st.tree.get_children()), "|", st.lbl_count.cget("text"))
    opt = w._tab_frames["optimizer"]
    print("optimizer tweaks:", len(opt._vars), "| verify:", opt.lbl_verify_hint.cget("text"))
    stress = w._tab_frames["stress"]
    print("stress:", stress.lbl_furmark_path.cget("text").splitlines()[0], "|",
          stress.lbl_3dm_path.cget("text").splitlines()[0])
    for t in tops:
        t.destroy()
    w.after(300, w.quit)

w.after(800, cycle)
w.after(90000, w.quit)
w.mainloop()
print("dialogs shown:", DIALOGS)
print("Tk callback errors:", len(errors))
for e in errors:
    print("-----\n" + e)
sys.stdout.flush()
os._exit(1 if errors else 0)
