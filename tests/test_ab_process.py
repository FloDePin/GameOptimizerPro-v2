"""Real process-control test of AfterburnerController with a DUMMY process (a
copy of ping.exe) under a TEST image name and a TEST monitoring-section name —
so it runs safely next to a real, running Afterburner (never touches it)."""
import os, sys, shutil, subprocess, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.nvtune_core import AfterburnerController
import core.mahm_reader as mr
from core.mahm_reader import section_ready
FAKE_EXE = "GopFakeAB.exe"
mr.MAHM_SHARED_MEMORY_NAME = f"GopTestMAHM_{os.getpid()}"   # never the real section
AfterburnerController.EXE_NAME = FAKE_EXE

FAILS = []
def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)

probe = AfterburnerController()
if probe.is_running():
    print(f"A process named {FAKE_EXE} is running — test skipped.")
    sys.exit(2)

tmp = tempfile.mkdtemp(prefix="gop_abproc_")
dummy = os.path.join(tmp, FAKE_EXE)
shutil.copy(r"C:\Windows\System32\PING.EXE", dummy)

ab = AfterburnerController()
ab.exe = dummy
ab.MIN_AGE_S = 3.0          # keep the test short (real value 8 s)
ab.CLOSE_TIMEOUT_S = 2.0
ab.READY_TIMEOUT_S = 3.0
events = []
ab.on_ab_closing = lambda: events.append(("closing", ab.is_running()))
ab.on_ab_started = lambda: events.append(("started", ab.is_running()))

print("launch / is_running")
p = ab._launch(["-n", "120", "127.0.0.1"])      # dummy keeps running ~2 min
time.sleep(0.5)
check(p.poll() is None and ab.is_running(), "dummy started via _launch (STARTUPINFO ok), is_running() True")
check(not section_ready(), "section_ready() False (no Afterburner monitoring)")

print("close(): young process -> waits MIN_AGE, WM_CLOSE ignored -> terminated")
t = time.monotonic()
ok, err = ab.close()
dt = time.monotonic() - t
check(ok and err == "", f"close ok ({dt:.1f} s)")
check(not ab.is_running() and p.poll() is not None, "process gone")
check(dt >= 2.4, "did not kill it before MIN_AGE (start-up protection)")
check(events == [("closing", True)], f"on_ab_closing called once, BEFORE the kill: {events}")

print("close() when nothing runs")
t = time.monotonic()
ok, err = ab.close()
check(ok and time.monotonic() - t < 1.0, "no-op, immediate")

print("start(): process runs but no monitoring -> ok with note after READY_TIMEOUT")
ab_args = []
orig_launch = ab._launch
def spy(args):
    ab_args.append(args)
    return orig_launch(["-n", "120", "127.0.0.1"])   # ping ignores -Profile; keep it alive
ab._launch = spy
ok, err = ab.start(2)
check(ok and "Monitoring" in err and ab_args[-1] == ["-Profile2"], f"start(2) passes -Profile2; note: {err[:50]}…")
check(events[-1] == ("started", True), f"on_ab_started called with the process up: {events[-1]}")
print("load_profile_slot(): running -> hands -Profile over (second launch) without closing")
n_before = len(events)
ok, err = ab.load_profile_slot(3)
check(ok and ab_args[-1] == ["-Profile3"] and ab.is_running(), "second launch with -Profile3, first instance still running")
ab.close()
check(not ab.is_running(), "cleanup: all dummies closed")

print("start() with a non-existent exe")
ab._launch = orig_launch
ab.exe = os.path.join(tmp, "missing", FAKE_EXE)
ok, err = ab.start(1)
check(not ok and "fehlgeschlagen" in err, f"clean error: {err[:60]}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
