"""LIVE check of the Stress Test page with the real app (VISIBLE window, real GPU):
1. internal stress test (60 s, GPU load via cupy) -> expects PASSED and >= 70 % load
2. FurMark 2 via the page's launcher (60 s) -> the recording must end by itself
   and summarise peak temperature, clocks, power and driver resets.
Loads the GPU fully for ~2.5 minutes — only run it when the user asks for it.
Nothing is changed on the system; settings go to a TEMP file (the saved FurMark
location is copied from the real settings).

    python tests\\live_stress_check.py [seconds]
"""
import os, sys, tempfile, time, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
FAILS = []


def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)


from tkinter import messagebox
DIALOGS = []
for n in ("askyesno", "askyesnocancel", "showinfo", "showwarning", "showerror", "askokcancel"):
    setattr(messagebox, n, (lambda n: lambda *a, **k: DIALOGS.append((n, a[:2])) or False)(n))
import tkinter as tk
ERRORS = []
tk.Tk.report_callback_exception = lambda self, e, v, tb: ERRORS.append(
    "".join(traceback.format_exception(e, v, tb))[-900:])

tmp = tempfile.mkdtemp(prefix="gop_live_stress_")
from pathlib import Path
from core import app_settings
real = app_settings.load()
app_settings.SETTINGS_FILE = Path(tmp) / "settings.json"
for k in ("furmark_path", "3dmark_path"):
    if k in real:
        app_settings.set(k, real[k])
from core import i18n
i18n.init_lang()
from GameOptimizerPro import detect_hw
from core.nvtune_core import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner, TunerConfig
from core.tweak_runner import TweakRunner
from core.crash_recovery import CrashRecovery
from core.startup_loader import StartupLoader
import ui.main_window as mw
from PIL import ImageGrab

hw = detect_hw()
mon = GpuMonitor()
ab = AfterburnerController(mon.nvml.get_pci_identity())
pm = ProfileManager(os.path.join(ROOT, "profiles"))
cr = CrashRecovery(tmp)
w = mw.GameOptimizerWindow(hw, mon, ab, pm, AutoTuner(mon, ab, pm, TunerConfig(), log_dir=tmp),
                           TweakRunner(log_dir=tmp), startup_loader=StartupLoader(tmp, ab, pm, cr))
w.geometry("1400x900+40+40")
w.unbind_all("<MouseWheel>")
OUT = os.path.join(ROOT, "logs", "shots")
os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def shot(name):
    w.update()
    x, y = w.winfo_rootx(), w.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height()), all_screens=True).save(
        os.path.join(OUT, name))


def page():
    return w._tab_frames["stress"]


def start():
    w._show_tab("stress")
    st = page()
    print(f"FurMark: {st.lbl_furmark_path.cget('text').splitlines()[0]}")
    print(f"[{time.time() - T0:5.1f}s] internal stress test, {SECS} s …", flush=True)
    st.v_int_dur.set(SECS)
    st.v_max_temp.set(90)
    st._start_internal()
    w.after(2000, wait_internal)


def wait_internal():
    st = page()
    if st._running_internal:
        w.after(1000, wait_internal)
        return
    txt = st.lbl_int_status.cget("text")
    print(f"[{time.time() - T0:5.1f}s] internal: {txt}", flush=True)
    check("PASSED" in txt, "internal stress test PASSED")
    try:
        load = float(txt.split("Ø GPU-Last:")[1].split("%")[0])
    except Exception:
        load = 0.0
    check(load >= 70, f"real GPU load during the internal test (Ø {load:.0f} %)")
    shot("live_stress_internal.png")
    w.after(5000, start_furmark)          # let the GPU settle


def start_furmark():
    st = page()
    if not st._furmark_path:
        check(False, "FurMark found")
        w.after(500, finish)
        return
    st.v_fur_dur.set(SECS)
    st.v_fur_res.set("1920x1080")
    print(f"[{time.time() - T0:5.1f}s] FurMark {SECS} s …", flush=True)
    st._launch_furmark()
    check(st._ext is not None, "recording of the FurMark run started")
    w.after(3000, wait_furmark)


def wait_furmark():
    st = page()
    if st._ext is not None and time.time() - T0 < SECS * 2 + 240:
        w.after(1000, wait_furmark)
        return
    txt = st.lbl_session.cget("text")
    print(f"[{time.time() - T0:5.1f}s] FurMark: {txt}", flush=True)
    check(st._ext is None, "recording ended by itself when FurMark closed")
    check("Peak" in txt and "Ø Takt" in txt, "summary with peak temperature and clocks under load")
    check("kein Treiber-Reset" in txt, "no driver reset (TDR) during FurMark")
    check("FurMark: Ø" in txt, "FurMark's own FPS / max GPU load read")
    check("nicht voll ausgelastet" not in txt,
          "GPU fully loaded by FurMark (8x MSAA default — also under an FPS cap / forced VSync)")
    shot("live_stress_furmark.png")
    w.after(500, finish)


def finish():
    print("dialogs:", DIALOGS)
    print("Tk callback errors:", len(ERRORS))
    for e in ERRORS:
        print("-----\n" + e)
    w.quit()


w.after(1500, start)
w.after((SECS * 4 + 400) * 1000, w.quit)
w.mainloop()
try:
    mon.close()
except Exception:
    pass
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS or ERRORS else 0)
