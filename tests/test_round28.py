"""Round 28 — an external audit checked against the code; the confirmed points, each with
the situation it describes: a second start while an update waits, the language switch
restart, the tray menu (language, slot), a load that never delivers a result, the stress
worker after the GUI is gone, NVML closed twice, the drift dialog's state changes, an
empty V/F curve, an event from the second a profile was applied in, autostart failures."""
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r28_")
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the app's own file
import core.i18n as I18N
I18N._save_lang = lambda lang: None                            # never the app's language file
I18N._current_lang = "de"
import GameOptimizerPro as G
import core.updater as UPD

# ── 1) a second start while an update waits ─────────────────────────────────
print("start order: the instance lock before a pending update")
calls = []
G.is_admin = lambda: True
G.owns_console = lambda: False
G.ensure_ui_package = lambda: (calls.append("ui"), True)[1]
UPD.pending = lambda *a, **k: (calls.append("pending"), {"build": 99, "dir": "x"})[1]
UPD.launch_apply = lambda *a, **k: (calls.append("apply"), True)[1]
LOCK = [False]
G.single_instance = lambda wait_s=0.0: (calls.append("lock"), LOCK[0])[1]
APP = G.GameOptimizerApp
G.GameOptimizerApp = lambda: (_ for _ in ()).throw(AssertionError("the app must not start"))


def run_main():
    try:
        G.main()
    except SystemExit as e:
        return e.code
    return None


code = run_main()
check(calls == ["lock"] and code == 0,
      f"the app already runs (tray): the second start hands over, installs NOTHING under it: {calls}")
calls.clear()
LOCK[0] = True
code = run_main()
check(calls == ["lock", "ui", "pending", "apply"] and code == 0,
      f"the only instance: the pending update is installed, then the installer restarts it: {calls}")
G.GameOptimizerApp = APP
I18N._current_lang = "de"

# ── 2) the language switch restarts through the app ──────────────────────────
print("language switch")
from ui import main_window as MW
asked = []
MW.messagebox.askyesno = lambda *a, **k: (asked.append(1), True)[1]
exits = []
_os_exit = os._exit
os._exit = lambda code=0: (_ for _ in ()).throw(AssertionError("os._exit in the window"))
win = types.SimpleNamespace(request_exit=lambda relaunch=False: exits.append(relaunch),
                            tuner=types.SimpleNamespace(is_running=False, abort=lambda: None),
                            monitor=types.SimpleNamespace(close=lambda: None))
try:
    MW.GameOptimizerWindow._toggle_lang(win)
    err = ""
except AssertionError as e:
    err = str(e)
finally:
    os._exit = _os_exit
check(asked and exits == [True] and not err and I18N._current_lang == "en",
      f"the app's own exit with a relaunch (tuner reset, tray icon gone, new instance waits): {exits} {err}")
I18N._current_lang = "de"
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check("def restart_app" not in src, "the unused restart without the wait flag is gone")
mw_src = open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8").read()
check('"--after-restart"]' in mw_src and '"_prebuild_id")' in mw_src and "_applied.pop" not in mw_src,
      "window fallback waits too; destroy cancels the page pre-build; the drift dialog uses the runner's lock")

# the exit's restart: the main thread waits for it after mainloop()
print("restart after the window closed")
popens, exits2 = [], []
_popen = subprocess.Popen
_osx = G.os._exit
subprocess.Popen = lambda args, **k: popens.append(list(args))
G.os._exit = lambda code=0: exits2.append(code)


class SlowTray:
    def stop(self):
        time.sleep(0.2)


app = types.SimpleNamespace(_running=True, _tray=SlowTray(), _window=None,
                            _abort_tuning_if_running=lambda: None,
                            temp_monitor=types.SimpleNamespace(stop=lambda: None),
                            monitor=types.SimpleNamespace(close=lambda: None))
app._finish = lambda relaunch: G.GameOptimizerApp._finish(app, relaunch)
try:
    G.GameOptimizerApp._shutdown(app, relaunch=True)
    G.GameOptimizerApp._after_mainloop(app)        # mainloop() just ended (window destroyed)
finally:
    subprocess.Popen = _popen
    G.os._exit = _osx
check(len(popens) == 1 and popens[0][-1] == G.AFTER_RESTART and exits2 == [0] and not app._stop_thread.is_alive(),
      f"mainloop over: the main thread waits for the stop thread — exactly one relaunch (with the wait "
      f"flag), one exit: {popens} {exits2}")


class HungTray:
    def stop(self):
        time.sleep(30)


popens.clear()
exits2.clear()
subprocess.Popen = lambda args, **k: popens.append(list(args))
G.os._exit = lambda code=0: exits2.append(code)
app2 = types.SimpleNamespace(_running=True, _tray=HungTray(), _window=None,
                             _abort_tuning_if_running=lambda: None,
                             temp_monitor=types.SimpleNamespace(stop=lambda: None),
                             monitor=types.SimpleNamespace(close=lambda: None))
app2._finish = lambda relaunch: G.GameOptimizerApp._finish(app2, relaunch)
t0 = time.time()
try:
    G.GameOptimizerApp._shutdown(app2, relaunch=True)
    G.GameOptimizerApp._after_mainloop(app2)
finally:
    subprocess.Popen = _popen
    G.os._exit = _osx
check(len(popens) == 1 and exits2 == [0] and time.time() - t0 < 8,
      f"the tray icon's stop hangs: the main thread relaunches after 5 s: {popens} ({time.time() - t0:.1f} s)")

# ── 3) the tray menu: language, the profile's own slot ───────────────────────
print("tray menu")
try:
    import pystray  # noqa: F401
    from core.nvtune_core import TuneProfile
    prof = TuneProfile(name="Rundum Max")
    applied, saved = [], []
    RESULT = [(True, "")]
    fake = types.SimpleNamespace(
        pm=types.SimpleNamespace(list_all=lambda: [prof], load=lambda n: prof),
        _volt=0, _temp=50, _clk=2000.0, _power=100.0, _open=lambda *a: None, _reset_gpu=lambda *a: None,
        _exit=lambda *a: None,
        ab=types.SimpleNamespace(available=True,
                                 write_and_apply=lambda slot, p: (applied.append(slot), RESULT[0])[1]),
        cr=types.SimpleNamespace(save_last_applied=lambda d: saved.append(d["name"])),
        sl=types.SimpleNamespace(_startup_slot=lambda p: 5))
    menu = G.GameOptimizerApp._build_menu(fake)
    item = list(list(menu.items)[2].submenu.items)[0]

    def click():
        n = len(applied)
        item(None)
        t0 = time.time()
        while len(applied) == n and time.time() - t0 < 5:
            time.sleep(0.05)
        time.sleep(0.1)

    click()
    check(applied == [5] and saved == ["Rundum Max"],
          f"a profile from the tray: from the slot that holds it (5), recorded as applied: {applied} {saved}")
    RESULT[0] = (False, "Afterburner antwortet nicht")
    click()
    check(applied == [5, 5] and saved == ["Rundum Max"], "a failed apply is not recorded as applied")
    I18N._current_lang = "en"
    texts = [str(i.text) for i in G.GameOptimizerApp._build_menu(fake).items]
    I18N._current_lang = "de"
    check(texts[0].endswith("Open GameOptimizerPro") and "Exit" in texts and "Reset GPU to Stock" in texts,
          f"English app: English tray menu: {texts}")
except ImportError:
    print("  (pystray missing: tray checks skipped)")

titles = []
u32 = G.ctypes.windll.user32
_mb = u32.MessageBoxW
u32.MessageBoxW = lambda h, msg, title, flags: titles.append(title)
try:
    app = types.SimpleNamespace(_window=None)
    I18N._current_lang = "en"
    G.GameOptimizerApp._show_crash_dialog(app, "x")
    I18N._current_lang = "de"
    G.GameOptimizerApp._show_crash_dialog(app, "x")
finally:
    u32.MessageBoxW = _mb
check(titles == ["GameOptimizerPro — crash detected", "GameOptimizerPro — Crash erkannt"],
      f"the crash dialog's title in the app's language: {titles}")

# ── 4) a load that never delivers a result ───────────────────────────────────
print("stress tester: no result since the start")
from core.nvtune_tuner import AutoTuner, StressTester, TunerApplyError, TunerConfig


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=55, voltage_mv=1050, core_mhz=2900, gpu_usage=99, power_capped=False,
                                     gpu_power_w=250, throttle_protective=False, throttle="", mem_mhz=10500,
                                     name="NVIDIA GeForce RTX 4080")

    def power_pct_to_watts(self, pct):
        return round(320 * pct / 100, 1)

    def set_power_limit(self, w):
        return True


QUIET = os.path.join(TMP, "quiet.py")
with open(QUIET, "w", encoding="utf-8") as f:
    f.write("import time\ntime.sleep(60)\n")
TALK = os.path.join(TMP, "talk.py")
with open(TALK, "w", encoding="utf-8") as f:
    f.write("import time\nfor _ in range(120):\n    print('RATE 1.0', flush=True)\n    time.sleep(0.5)\n")
st = StressTester(Mon())
st._worker_path = lambda: TALK
st.START_HANG_S = 2.0
r = st.run(3, 85)
check(r.passed and st._delivered, "a run with results: passed, the tester knows the load works here")
st._worker_path = lambda: QUIET
t0 = time.time()
r = st.run(15, 85)
check(not r.passed and r.hang_detected and "seit dem Start" in r.abort_reason and time.time() - t0 < 9,
      f"then a step whose load never delivers (hung on its first product / CUDA did not start): failed, "
      f"not passed on an untested GPU ({r.abort_reason}, {time.time() - t0:.1f} s)")
fresh = StressTester(Mon())
fresh._worker_path = lambda: QUIET
fresh.START_HANG_S = 1.0
r = fresh.run(3, 85)
check(r.passed and not r.hang_detected, "a tester that never got a result is left to the baseline check (no cupy)")
check(StressTester.START_HANG_S == 30.0 and StressTester.HANG_S == 8.0, "30 s for a start, 8 s between results")

# ── 5) the stress worker after the GUI is gone ───────────────────────────────
print("stress worker: GUI gone during the full-load phase")
dead = subprocess.Popen([sys.executable, "-c", "pass"])
dead.wait()
env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "fakecupy"), GOP_STRESS_N="64", GOP_STRESS_BOOST_N="32",
           GOP_STRESS_HEAVY_S="40", GOP_STRESS_BOOST_S="40")
t0 = time.time()
w = subprocess.Popen([sys.executable, os.path.join(ROOT, "_stress_worker.py"), str(dead.pid), "mixed"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
try:
    w.wait(timeout=12)
    took = time.time() - t0
except subprocess.TimeoutExpired:
    w.kill()
    took = 99
check(took < 12, f"'mixed' stops within a second or two of the full phase, not after it ({took:.1f} s of 40)")

# ── 6) NVML closed twice ─────────────────────────────────────────────────────
print("NVML close")
from core.nvtune_core import NvmlMonitor
nv = NvmlMonitor.__new__(NvmlMonitor)
shut = []
nv._ok, nv._nv = True, types.SimpleNamespace(nvmlShutdown=lambda: shut.append(1))
nv.close()
nv.close()
check(shut == [1] and not nv.available, "window close + app shutdown: one nvmlShutdown, no NVML calls after it")

# ── 7) the drift dialog's state changes ──────────────────────────────────────
print("tweak runner: forget")
from core.tweak_runner import TweakRunner
tr_dir = os.path.join(TMP, "tweaks")
runner = TweakRunner(log_dir=tr_dir)
runner._applied = {"a": "1", "b": "2", "c": "3"}
runner._save_state()
gone = runner.forget(["a", "zz", "c"])
state = json.load(open(os.path.join(tr_dir, "applied_tweaks.json"), encoding="utf-8"))
check(gone == ["a", "c"] and state == {"b": "2"}, f"dropped and saved together, under the lock: {gone} {state}")
errs = []


def writer():
    try:
        for i in range(300):
            with runner._lock:
                runner._applied[f"x{i}"] = "t"
                runner._save_state()
    except Exception as e:
        errs.append(repr(e))


def dropper():
    try:
        for i in range(300):
            runner.forget([f"x{i}"])
    except Exception as e:
        errs.append(repr(e))


ths = [threading.Thread(target=writer), threading.Thread(target=dropper)]
for t in ths:
    t.start()
for t in ths:
    t.join()
check(not errs, f"apply and forget at the same time: no 'dict changed size' while saving {errs[:1]}")

# ── 8) an empty V/F curve ────────────────────────────────────────────────────
print("all-round tuner: empty curve")


class EmptyCurve:
    def active_points(self):
        return []


ab = types.SimpleNamespace(base_curve=lambda slot: (EmptyCurve(), "Defaults"))
tuner = AutoTuner(Mon(), ab, None, TunerConfig(), log_dir=os.path.join(TMP, "tlogs"))
try:
    tuner._run_curve(None, None)
    msg = "no error"
except TunerApplyError as e:
    msg = str(e)
except Exception as e:
    msg = "wrong: " + repr(e)
check("keine aktiven Punkte" in msg, f"a clear message instead of 'list index out of range': {msg}")

# ── 9) an event from the second a profile was applied in ─────────────────────
print("GPU watchdog: the second of the apply")
from core import gpu_watchdog as WD
WD.SESSIONS_FILE = None
last_file = os.path.join(TMP, "last_applied.json")
with open(last_file, "w", encoding="utf-8") as f:
    json.dump({"name": "Rundum Max"}, f)
X = 1791000000
os.utime(last_file, (X + 0.8, X + 0.8))
cr = types.SimpleNamespace(load_last_applied=lambda: {"name": "Rundum Max"}, _last_applied=last_file)
wd_logs = os.path.join(TMP, "wdlogs")
os.makedirs(wd_logs, exist_ok=True)
found = WD.check(cr, wd_logs, 0, read=lambda since: [(float(X), 153), (float(X + 3), 13)])
check(found and found["events"] == [(float(X + 3), 13)],
      f"an event logged in the apply's own second (it may be from before it) is left out: "
      f"{found and found['events']}")

# ── 10) autostart failures are logged ───────────────────────────────────────
print("autostart: why it failed")
from core import startup_loader as SL
recs = []


class H(logging.Handler):
    def emit(self, rec):
        recs.append(rec.getMessage())


logging.getLogger("gop.startup").addHandler(H())
loader = SL.StartupLoader(os.path.join(TMP, "sl"), None, None, None)
loader._remove_legacy_run = lambda: None                     # never the user's registry
_run = SL.subprocess.run
SL.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "FEHLER: Zugriff verweigert")
try:
    ok = loader.set_autostart(True)
finally:
    SL.subprocess.run = _run
check(ok is False and any("Zugriff verweigert" in m for m in recs),
      f"schtasks refused: 'failed' on the page, the reason in the log: {recs[-1:]}")

import shutil
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
