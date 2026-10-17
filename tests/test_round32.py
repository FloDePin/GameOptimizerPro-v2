"""Round 32 — an external review checked against the code: the GPU watchdog's start check and
a live fault can't open two dialogs; a CUDA error while the stress worker sets up counts as
instability (at once) when the tester's earlier runs delivered — on the first run it still
falls back to the CPU load (a PC where CUDA doesn't start)."""
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r32_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

# ── 1) one watchdog check / dialog at a time ─────────────────────────────────
print("watchdog: one dialog at a time")
import GameOptimizerPro as G  # noqa: E402
from core import gpu_watchdog as W  # noqa: E402


class FakeWin:
    def __init__(self): self.q = []
    def after(self, ms, fn): self.q.append(fn)
    def state(self): return "normal"
    def focus_displayof(self): return object()
    def pump(self, limit=3.0):
        end = time.time() + limit
        while self.q and time.time() < end:
            self.q.pop(0)()
            time.sleep(0.01)


CHECKS, DIALOGS, OPEN = [], [], [False]
W.check = lambda cr, logs, seen: (CHECKS.append(OPEN[0]), {"profile": "P", "last": 1.0, "events": [(1.0, 153)]})[1]
app = object.__new__(G.GameOptimizerApp)
app._window, app.cr, app._logs_dir = FakeWin(), None, TMP
app.tuner = types.SimpleNamespace(is_running=False)
app._watchdog_pending = False


def dialog(found):
    DIALOGS.append(found)
    OPEN[0] = True
    if len(DIALOGS) == 1:
        # the dialog waits in its own event loop: a live fault comes in, the start timer and
        # the pending poll run meanwhile
        app._watchdog_pending = True
        app._watchdog_start()
        app._watchdog_pending_poll()
        mid.append((len(CHECKS), app._watchdog_pending))
    OPEN[0] = False


mid = []
app._watchdog_dialog = dialog
app._watchdog_start()
app._watchdog_start()                         # the 5-s start timer and a live fault at once
app._window.pump()
check(mid == [(1, True)], f"while the dialog is open: no second check, the live fault waits ({mid})")
check(len(CHECKS) == 2 and len(DIALOGS) == 2 and CHECKS == [False, False] and not app._watchdog_pending
      and not app._watchdog_busy,
      f"the waiting fault gets its own check after the dialog closed ({len(CHECKS)} / {len(DIALOGS)})")
check(len(DIALOGS) == 2, "never two dialogs at the same time")
W.check = lambda cr, logs, seen: (_ for _ in ()).throw(RuntimeError("event log"))
app._watchdog_start()
app._window.pump()
check(not app._watchdog_busy, "a failing check frees the watchdog too")

# ── 2) stress worker: a CUDA error while setting up ──────────────────────────
print("stress worker: CUDA error while setting up")
BAD = Path(TMP, "badcupy", "cupy")
BAD.mkdir(parents=True)
(BAD / "__init__.py").write_text(
    "class _R:\n"
    "    def rand(self, *a, **k):\n"
    "        raise RuntimeError('cudaErrorLaunchFailure: unspecified launch failure')\n"
    "random = _R()\nfloat32 = 'float32'\n", encoding="utf-8")
WORKER = os.path.join(ROOT, "_stress_worker.py")
dead = subprocess.Popen([sys.executable, "-c", "pass"])
dead.wait()                                   # a PID that is gone: the CPU fallback ends at once


def worker(mode, gpu_ok):
    env = dict(os.environ, PYTHONPATH=str(BAD.parent), OMP_NUM_THREADS="1")
    env.pop("GOP_STRESS_GPU_OK", None)
    if gpu_ok:
        env["GOP_STRESS_GPU_OK"] = "1"
    r = subprocess.run([sys.executable, WORKER, str(dead.pid), mode], capture_output=True, text=True,
                       env=env, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, r.stdout, r.stderr


for mode in ("mixed", "boost", "transient", "gemm", "mem"):
    rc, out, err = worker(mode, True)
    check(rc == 3 and "ERR cuda" in out and "under a working GPU" in err,
          f"{mode}: after delivered runs -> compute error at once (exit {rc})")
rc, out, err = worker("mixed", False)
check(rc == 0 and "ERR" not in out and "CUDA stress failed" in err,
      f"first run (CUDA may not work on this PC): the CPU fallback as before (exit {rc})")

# ── 3) the tester passes the flag only after a delivered run ─────────────────
print("stress tester")
import core.nvtune_tuner as NT  # noqa: E402
SEEN = []


class P:
    stdout = iter(())
    returncode = None
    def poll(self): return None
    def terminate(self): pass
    def wait(self, timeout=None): return 0


real_popen = NT.subprocess.Popen
NT.subprocess.Popen = lambda *a, **k: (SEEN.append(k.get("env")), P())[1]
try:
    st = NT.StressTester(monitor=None)
    st.start("mixed")
    st._delivered = True
    st.start("mixed")
finally:
    NT.subprocess.Popen = real_popen
check(SEEN[0] is None and SEEN[1] and SEEN[1].get("GOP_STRESS_GPU_OK") == "1"
      and SEEN[1].get("PATH") == os.environ.get("PATH"),
      "first run: the normal environment; after a delivered run: + GOP_STRESS_GPU_OK=1 (the rest kept)")

# ── 4) left unchanged on purpose ─────────────────────────────────────────────
print("checked, not changed")
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
fin = src[src.index("    def _finish("):src.index("    def _after_mainloop(")]
check("release_single_instance" not in fin and "r in (0, 0x80)" in src,
      "the restart: the new instance takes the abandoned mutex right when this process ends — "
      "no release before Popen (and ReleaseMutex only works on the owning thread)")

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
