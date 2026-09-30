"""Read-only smoke test: build the REAL main window with the real components the
app uses (NVML, MAHM, Afterburner controller, tweak runner in a TEMP log dir),
open every tab, open the Startup + Services manager windows, run the mainloop
for a few seconds and close. Nothing is applied; no dialog is answered."""
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
_orig_report = tk.Tk.report_callback_exception
def report(self, exc, val, tb):
    errors.append("".join(traceback.format_exception(exc, val, tb))[-800:])
tk.Tk.report_callback_exception = report

from core import i18n
i18n.init_lang()
from GameOptimizerPro import detect_hw
from core.nvtune_core import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner, TunerConfig
from core.tweak_runner import TweakRunner
from core.crash_recovery import CrashRecovery
from core.startup_loader import StartupLoader
from ui.main_window import GameOptimizerWindow

tmp = tempfile.mkdtemp(prefix="gop_smoke_")
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
w = GameOptimizerWindow(hw, mon, ab, pm, tuner, runner, startup_loader=sl, game_monitor=gm)
w.attributes("-alpha", 0.0)          # invisible on the desktop
from core.tweak_runner import TweakRunner as _TR
tabs = list(w._tab_frames)
print("tabs:", tabs)

def cycle(i=0):
    if i < len(tabs):
        w._show_tab(tabs[i])
        w.after(700, cycle, i + 1)
    else:
        w._open_startup_mgr()
        w._open_services()
        for t in w.winfo_children():
            if isinstance(t, tk.Toplevel):
                t.attributes("-alpha", 0.0)
        w.after(4000, finish)

def finish():
    tops = [c for c in w.winfo_children() if isinstance(c, tk.Toplevel)]
    print("toplevels:", [t.title() for t in tops])
    dash = w._tab_frames["dashboard"]
    print("dashboard score:", repr(dash.lbl_score.cget("text")))
    print("monitor rows:", len(dash._mon_rows.winfo_children()))
    svc = [t for t in tops if "Services" in t.title()]
    if svc:
        print("services rows:", len(svc[0].tree.get_children()), "|", svc[0].lbl_count.cget("text"))
    for t in tops:
        t.destroy()
    try:
        dash._running = False
    except Exception:
        pass
    w.after(300, w.quit)

w.after(800, cycle)
w.after(60000, w.quit)
w.mainloop()
print("dialogs shown:", DIALOGS)
print("Tk callback errors:", len(errors))
for e in errors:
    print("-----\n" + e)
sys.stdout.flush()
os._exit(1 if errors else 0)
