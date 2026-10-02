"""_stress_worker.py (gpu-burn style check, rates, mem mode) + StressTester, with a
numpy-backed fake cupy. No real GPU load is generated."""
import os, sys, subprocess, time, types, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(SCR, "fakecupy")
sys.path.insert(0, ROOT)
WORKER = os.path.join(ROOT, "_stress_worker.py")

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

BASE_ENV = dict(os.environ, PYTHONPATH=FAKE, GOP_STRESS_N="64", GOP_STRESS_MEM_MB="4")


def run_worker(mode, extra=None, seconds=3.5):
    """Start the worker with THIS process as 'GUI'; collect output for a while."""
    env = dict(BASE_ENV, **(extra or {}))
    p = subprocess.Popen([sys.executable, WORKER, str(os.getpid()), mode],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    lines = []
    def rd():
        for l in p.stdout:
            lines.append(l.strip())
    t = threading.Thread(target=rd, daemon=True); t.start()
    try:
        p.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        p.terminate(); p.wait(5)
    t.join(2)
    return p.returncode, lines, p.stderr.read()

print("worker: gemm mode")
rc, lines, err = run_worker("gemm")
rates = [float(l.split()[1]) for l in lines if l.startswith("RATE")]
check(rc not in (0, 3) and len(rates) >= 2 and all(r > 0 for r in rates),
      f"keeps running, prints RATE every second ({len(rates)} lines, e.g. {rates[:1]})")
rc, lines, err = run_worker("gemm", {"FAKE_CORRUPT_DOT": "40"})
check(rc == 3 and any(l.startswith("ERR 1") for l in lines), f"one corrupted element -> 'ERR 1', exit 3 (rc={rc})")
rc, lines, err = run_worker("gemm", {"FAKE_RAISE_DOT": "30"})
check(rc == 3 and "ERR cuda" in lines and "CUDA error under load" in err,
      f"CUDA error AFTER the load started -> instability, exit 3 (rc={rc})")
rc, lines, err = run_worker("gemm", {"FAKE_INIT_FAIL": "1"}, seconds=2.5)
check(rc not in (3,) and "CUDA stress failed" in err and not any(l.startswith("RATE") for l in lines),
      f"CUDA failing at START -> CPU fallback, no false 'error' (rc={rc})")

print("worker: mem mode")
rc, lines, err = run_worker("mem")
bws = [float(l.split()[1]) for l in lines if l.startswith("BW")]
check(rc not in (0, 3) and len(bws) >= 2 and all(b > 0 for b in bws), f"prints BW GB/s ({len(bws)} lines)")
rc, lines, err = run_worker("mem", {"FAKE_CORRUPT_COPY": "3"})
check(rc == 3 and "ERR 1" in lines,
      f"corruption in the FIRST copy (copied back!) still caught via the reference (rc={rc})")
t0 = time.time()
rc, lines, err = run_worker("mem", {"FAKE_CORRUPT_COPY": "3", "FAKE_SLOW_COPY_S": "0.15"}, seconds=6)
check(rc == 3 and "ERR 1" in lines and time.time() - t0 < 5,
      f"starved copies (0.3 s per round trip, live: 13 GB/s next to FurMark): the error is still found "
      f"within seconds — compared twice a second, not only every 50th round trip ({time.time() - t0:.1f} s)")

print("worker: dead-man switch")
dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
p = subprocess.Popen([sys.executable, WORKER, str(dummy.pid), "gemm"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, env=BASE_ENV)
try:
    p.wait(timeout=8)
    check(True, f"worker ends on its own when the GUI process is gone (rc={p.returncode})")
except subprocess.TimeoutExpired:
    p.kill(); check(False, "worker ends on its own when the GUI process is gone")

print("StressTester (real subprocess, fake cupy)")
os.environ.update(BASE_ENV)
from core.nvtune_tuner import StressTester

class Mon:
    def __init__(self, protective=False):
        self.protective = protective
    def read(self):
        return types.SimpleNamespace(temp=60, voltage_mv=1000, core_mhz=2700, mem_mhz=11200,
                                     gpu_usage=99, throttle="Power-Limit",
                                     throttle_protective=self.protective, power_capped=True)

st = StressTester(Mon())
r = st.run(6, 90)
check(r.passed and not r.throttle_hit and r.avg_rate_tflops > 0 and r.power_capped_pct == 100,
      f"passes under the power limit (capped {r.power_capped_pct}%), rate {r.avg_rate_tflops}")
check(r.avg_core_mhz == 2700 and r.avg_mem_mhz == 11200, "averages after the ramp-up")
r = StressTester(Mon(protective=True)).run(8, 90)
check(r.passed and r.throttle_hit, "lasting thermal/HW slowdown -> throttle_hit")


class Blip(Mon):
    """Slowdown flag only in the given samples (0-based) — like the second NVIDIA
    sets 'SW thermal' when a load ends or Afterburner applies a profile."""
    def __init__(self, on):
        super().__init__()
        self.n, self.on = -1, set(on)

    def read(self):
        self.n += 1
        st = super().read()
        st.throttle_protective = self.n in self.on
        st.throttle = "SW-Thermal" if self.n in self.on else "Power-Limit"
        return st


r = StressTester(Blip({0, 1, 2})).run(8, 90)
check(r.passed and not r.throttle_hit, "slowdown flag only during the ramp-up -> ignored")
r = StressTester(Blip({4, 5})).run(8, 90)
check(r.passed and not r.throttle_hit, "a 2-s blip after the ramp-up -> ignored")
r = StressTester(Blip({4, 5, 6})).run(9, 90)
check(r.throttle_hit and r.throttle_note == "SW-Thermal", f"3 s in a row -> counted, named: {r.throttle_note!r}")
check(r.last_voltage_mv == 1000, "voltage just before the end recorded")
os.environ["FAKE_CORRUPT_DOT"] = "60"
r = StressTester(Mon()).run(8, 90)
os.environ.pop("FAKE_CORRUPT_DOT")
check(not r.passed and r.crash_detected and r.compute_error and "Rechenfehler" in r.abort_reason,
      f"compute error -> failed step: {r.abort_reason!r}")
r = StressTester(Mon()).run(6, 90, mode="mem")
check(r.passed and r.avg_bw_gbs > 0 and r.avg_rate_tflops == 0, f"mem mode -> bandwidth {r.avg_bw_gbs} GB/s")
ev = threading.Event()
st = StressTester(Mon(), stop_event=ev)
threading.Timer(1.5, ev.set).start()
t = time.time(); r = st.run(30, 90)
check(r.aborted and time.time() - t < 4 and st._proc is None, "abort ends the step at once, worker stopped")

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
