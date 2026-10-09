"""Headless UI test: GPU tab + Settings tab with a slow fake Afterburner."""
import os, sys, time, tempfile, threading, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import tempfile as _tf                     # never the app's own settings (run on their own too)
from pathlib import Path as _P
from core import app_settings as _AS
_AS.SETTINGS_FILE = _P(_tf.mkdtemp(prefix="gop_set_")) / "settings.json"
import tkinter as tk
from tkinter import messagebox

from core.nvtune_core import AfterburnerController, GpuMonitor, ProfileManager, TuneProfile
from core.nvtune_tuner import AutoTuner, TunerConfig

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

boxes = []
messagebox.showinfo = lambda *a, **k: boxes.append(("info",) + a)
messagebox.showerror = lambda *a, **k: boxes.append(("error",) + a)
messagebox.showwarning = lambda *a, **k: boxes.append(("warning",) + a)


class SlowAB(AfterburnerController):
    def __init__(self):
        self.calls = []
        super().__init__()
    def _detect(self):
        self.exe, self.profile_dir = r"C:\fake\MSIAfterburner.exe", None
    def write_and_apply(self, slot, p):
        self.calls.append(("apply", slot, p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct,
                           threading.current_thread() is threading.main_thread()))
        time.sleep(1.5)                      # Afterburner restart
        self.last_notes = ["Core +25 MHz auf allen Kurvenpunkten"]
        return True, ""
    def reset_to_stock(self, slot=2):
        self.calls.append(("reset", slot, threading.current_thread() is threading.main_thread()))
        time.sleep(1.0)
        return False, "Afterburner-Profil: simulierter Fehler"
    def find_gpu_profile(self):
        return None, "Afterburner hat noch kein Profil für die NVIDIA-Karte angelegt"
    def check_ab_setup(self):
        return {"cfg_found": True, "voltage_control": True, "voltage_monitoring": False,
                "profiles_locked": False, "start_minimized": False, "voltage_graph": False}


tmp = tempfile.mkdtemp(prefix="gop_ui_")
root = tk.Tk(); root.withdraw()
mon = GpuMonitor()
ab = SlowAB()
pm = ProfileManager(os.path.join(tmp, "profiles"))
pm.save(TuneProfile(name="Test OC", core_offset_mhz=25, mem_offset_mhz=100, power_limit_pct=95))
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=os.path.join(tmp, "logs"))

from ui.tab_gpu import GpuTunerTab
from ui.tab_settings import SettingsTab
gpu = GpuTunerTab(root, mon, ab, pm, tuner)
gpu.pack()

STEPS = []
def step(delay):
    def deco(fn):
        STEPS.append((delay, fn)); return fn
    return deco

@step(0)
def s1():
    print("manual apply runs off the UI thread")
    gpu.v_m_core.set(25); gpu.v_m_mem.set(100); gpu.v_m_pwr.set(95); gpu.v_ab_slot.set(3)
    t = time.monotonic(); gpu._manual_apply(); dt = time.monotonic() - t
    check(dt < 0.3, f"button handler returns immediately ({dt:.2f} s)")
    check("Applying" in gpu.lbl_manual_st.cget("text"), "status shows 'Applying via Afterburner ...'")
    gpu._manual_apply()
    check(boxes and "still running" in boxes[-1][2], "second click while busy -> 'still running'")

@step(2200)
def s2():
    check(ab.calls[0][:5] == ("apply", 3, 25, 100, 95) and ab.calls[0][5] is False,
          f"write_and_apply(slot 3, 25/100/95) on a worker thread: {ab.calls[0]}")
    check(gpu.lbl_manual_st.cget("text").startswith("Applied — Core +25 Mem +100 Pwr 95% (slot 3)"),
          f"result label: {gpu.lbl_manual_st.cget('text')}")
    check(not hasattr(gpu, "v_m_fan"), "fan slider removed (not written via Afterburner)")
    print("reset shows the error instead of claiming success")
    gpu._manual_reset()

@step(1600)
def s3():
    check(ab.calls[-1][:2] == ("reset", 3) and ab.calls[-1][2] is False, "reset_to_stock(slot 3) on a worker thread")
    check("simulierter Fehler" in gpu.lbl_manual_st.cget("text"), f"error shown: {gpu.lbl_manual_st.cget('text')}")
    check(gpu.v_m_core.get() == 0 and gpu.v_m_pwr.get() == 100, "sliders back to stock")
    print("profile apply: the button opens the slot menu, the chosen slot is written")
    gpu.tree.selection_set("Test OC")
    posted = []
    real_post = gpu._post
    gpu._post = lambda menu, x, y: posted.append(menu)
    gpu._apply_profile()
    gpu._post = real_post
    check(posted and posted[-1].index("end") == 6, "button -> menu with the five slots (no direct write)")
    import ui.tab_gpu as TG
    TG.messagebox.askyesno = lambda *a, **k: True
    boxes.clear(); gpu._export_to_slot(gpu.pm.load("Test OC"), 3, "leer")

@step(2000)
def s4():
    check(boxes and boxes[-1][0] == "info" and "Test OC" in boxes[-1][2] and "Core +25" in boxes[-1][2],
          f"success box with notes: {boxes[-1][2][:60] if boxes else None!r}")
    print("blocked while Auto-Tune runs")
    tuner._thread = threading.Thread(target=lambda: time.sleep(1.0)); tuner._thread.start()
    boxes.clear(); n = len(ab.calls); gpu._manual_apply()
    check(len(ab.calls) == n and boxes and "abort it first" in boxes[-1][2], "no Afterburner write during tuning")
    tuner._thread.join()
    print("settings tab: setup check rows")
    global st
    st = SettingsTab(root, ab, mon, None)
    st._run_setup_check()

@step(400)
def s5():
    texts = []
    def walk(w):
        for c in w.winfo_children():
            try:
                texts.append(c.cget("text"))
            except tk.TclError:
                pass
            walk(c)
    walk(st.setup_frame)
    joined = " | ".join(str(x) for x in texts)
    for needle in ("AB: Unlock Voltage Monitoring", "Spannungsüberwachung freischalten",
                   "AB: Graph 'GPU-Spannung' aktiv", "AB: Profildatei der Grafikkarte",
                   "noch kein Profil für die NVIDIA-Karte"):
        check(needle in joined, f"setup row: {needle!r}")
    check("Slot 2" not in joined, "old per-slot lock row gone")
    root.after(100, root.destroy)

def run_steps(i=0):
    if i >= len(STEPS):
        return
    delay, fn = STEPS[i]
    def go():
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc(); check(False, f"step {fn.__name__} raised {e}")
            root.destroy(); return
        run_steps(i + 1)
    root.after(delay, go)

run_steps()
root.after(20000, root.destroy)   # watchdog
root.mainloop()
mon.close()
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
