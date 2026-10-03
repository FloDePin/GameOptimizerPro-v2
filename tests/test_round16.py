"""Round 16 — tests that find what a game finds. Hunt: Showdown hung (D3D12
"device hung") after 2 h on a tuned profile that had passed every test:
a load-change test, hang detection, a game test after the final test (both
modes), bigger margins (45 / 60 at the top / +30 after a reset; Quick: 60 off the
offset), memory −200 + the EDC rule, "make safer", a GPU watchdog at app start,
and the applied profile recorded wherever the app applies one.
No real GPU load: fake cupy / fake cards / fake event log."""
import json
import os
import shutil
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


def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r16_")
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the user's file
import core.i18n as I18N
I18N._current_lang = "de"

# ── 1) the worker's load-change mode ─────────────────────────────────────────
print("worker: load changes ('transient')")
WORKER = os.path.join(ROOT, "_stress_worker.py")
ENV = dict(os.environ, PYTHONPATH=os.path.join(HERE, "fakecupy"), GOP_STRESS_N="64",
           GOP_STRESS_BOOST_N="32", GOP_STRESS_TRANS_MAX_S="0.02")


def run_worker(extra=None, seconds=3.0):
    p = subprocess.Popen([sys.executable, WORKER, str(os.getpid()), "transient"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=dict(ENV, **(extra or {})))
    lines = []
    th = threading.Thread(target=lambda: lines.extend(l.strip() for l in p.stdout), daemon=True)
    th.start()
    try:
        p.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        p.terminate()
        p.wait(5)
    th.join(2)
    return p.returncode, lines


rc, lines = run_worker()
rates = [l for l in lines if l.startswith("RATE")]
check(rc not in (0, 3) and len(rates) >= 2, f"runs bursts with pauses and reports RATE ({len(rates)} lines)")
rc, lines = run_worker({"FAKE_CORRUPT_DOT": "25"})
check(rc == 3 and any(l.startswith("ERR") for l in lines), f"a wrong result in a burst -> ERR, exit 3 (rc={rc})")

# ── 2) a hung load is a failure ──────────────────────────────────────────────
print("hang detection")
import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, StressResult, StressTester, TunerConfig, TuneMode, TunerState
HANGER = os.path.join(TMP, "hanger.py")
with open(HANGER, "w", encoding="utf-8") as f:
    f.write("import sys, time\nprint('RATE 1.0', flush=True)\nprint('RATE 1.0', flush=True)\ntime.sleep(60)\n")


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=55, voltage_mv=1050, core_mhz=2900, gpu_usage=99, power_capped=False,
                                     gpu_power_w=250, throttle_protective=False, throttle="", mem_mhz=10500,
                                     name="NVIDIA GeForce RTX 4080")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


st = StressTester(Mon())
st._worker_path = lambda: HANGER
st.HANG_S = 2.0
t0 = time.time()
r = st.run(20, 85)
check(not r.passed and r.hang_detected and r.crash_detected and "GPU hängt" in r.abort_reason
      and time.time() - t0 < 10,
      f"no results for {st.HANG_S:.0f} s -> 'GPU hängt', the step fails at once ({time.time() - t0:.1f} s)")
check(st._proc is None, "the hung worker is ended")
QUIET = os.path.join(TMP, "quiet.py")
with open(QUIET, "w", encoding="utf-8") as f:
    f.write("import time\ntime.sleep(60)\n")       # e.g. no cupy: the CPU fallback prints nothing
st2 = StressTester(Mon())
st2._worker_path = lambda: QUIET
st2.HANG_S = 1.0
r2 = st2.run(3, 85)
check(r2.passed and not r2.hang_detected, "a worker that never printed is not a 'hang' (the baseline catches it)")
check(NT.StressTester.HANG_S == 8.0, "8 s without results = hung (below the user's 10-s TDR delay)")

# ── 3) margins and settings ──────────────────────────────────────────────────
print("margins")
cfg = TunerConfig()
check((cfg.curve_safety_mhz, cfg.curve_safety_top_mhz, cfg.curve_reset_extra_mhz) == (45, 60, 30)
      and cfg.core_safety_mhz == 60 and cfg.mem_safety_mhz == 200 and cfg.game_test
      and (cfg.game_cool_s, cfg.game_transient_s, cfg.game_boost_s) == (60, 300, 240),
      "defaults: 45 / 60 at the top / +30 after a reset; Quick −60; memory −200; game test 1+5+4 min")
from core import curve_tune as CT
rs = [CT.AnchorResult(1075, 2805, best_mhz=2969), CT.AnchorResult(1050, 2760, best_mhz=2939),
      CT.AnchorResult(1000, 2640, best_mhz=2831), CT.AnchorResult(975, 2565, best_mhz=2771),
      CT.AnchorResult(925, 2370, best_mhz=2606)]
CT.apply_margins(rs)
check([(x.mv, x.target_mhz) for x in rs] == [(1075, 2909), (1050, 2879), (1000, 2771), (975, 2726), (925, 2561)],
      f"the user's run on the new margins: 1050 mV (where Hunt ran) 2909 -> 2879: "
      f"{[(x.mv, x.target_mhz) for x in rs]}")

# ── 4) Quick mode: margin, game test, memory rules ──────────────────────────
print("Quick mode")
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class GPU:
    """Core unstable above +100 (steady) / +70 under load changes; memory errors
    above mem_limit; the bandwidth drops from edc_from on (EDC retries)."""
    def __init__(self, transient_limit=70, mem_limit=5000, edc_from=None, weak=False):
        self.core = self.mem = 0
        self.pwr = 100
        self.transient_limit, self.mem_limit, self.edc_from, self.weak = transient_limit, mem_limit, edc_from, weak
        self.runs = []

    def apply(self, p):
        self.core, self.mem, self.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        self.runs.append((mode, self.core, self.mem))
        r = StressResult(passed=True, avg_temp=60, max_temp=64, avg_voltage_mv=1050, steady_voltage_mv=1050,
                         avg_gpu_usage=99, avg_core_mhz=2800 + self.core, max_core_mhz=2900 + self.core,
                         avg_rate_tflops=40.0 * (1 - max(0.0, (95 - self.pwr) * 0.004)), last_voltage_mv=1050)
        lim = self.transient_limit if mode == "transient" else 100
        if self.core > lim:
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        if mode == "mem":
            r.avg_rate_tflops = 0.0
            r.avg_bw_gbs = 13.0 if self.weak else (700 + 0.05 * self.mem if self.edc_from is None
                                                   or self.mem < self.edc_from else 650.0)
            if self.mem > self.mem_limit:
                r.passed, r.crash_detected, r.compute_error = False, True, True
        return r


class AB:
    available = True
    def __init__(self, gpu): self.gpu = gpu
    def write_and_apply(self, slot, p):
        self.gpu.apply(p)
        return True, ""


def quick(gpu, **kw):
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    tmp = tempfile.mkdtemp(prefix="q_", dir=TMP)
    conf = dict(mode=TuneMode.OC_UV, core_step_mhz=15, core_max_mhz=300, power_min_pct=100, crash_pause_s=0)
    conf.update(kw)
    t = AutoTuner(Mon(), AB(gpu), NT.ProfileManager(os.path.join(tmp, "p")), TunerConfig(**conf),
                  log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    return t, logs


g = GPU()
t, logs = quick(g)
L = "\n".join(logs)
check(t.state == TunerState.DONE and t.best_profile.core_offset_mhz == 37
      and "Sicherheitsabzug: +97 → +37 MHz" in L,
      f"Stage 1 finds +97 (edge +100, ±5), 60 MHz off -> +37 (game-safe under load changes, +70): "
      f"+{t.best_profile.core_offset_mhz if t.best_profile else None}")
modes = [m for m, *_ in g.runs]
check(modes[-3:] == ["mixed", "transient", "boost"] and "Spiel-Endtest Boost-Punkt ✓" in L,
      "final test, then the game test: load changes, boost point")
g = GPU()
t, logs = quick(g, core_safety_mhz=15)
L = "\n".join(logs)
check(t.state == TunerState.DONE and t.best_profile.core_offset_mhz == 67
      and "Spiel-Endtest ✗ (Lastwechsel)" in L and "Core +82→+67 MHz" in L,
      f"too little margin: the game test fails, core one step back, passes: "
      f"+{t.best_profile.core_offset_mhz if t.best_profile else None}")
g = GPU()
t, logs = quick(g, game_test=False)
check([m for m, *_ in g.runs][-1] == "mixed", "game test off: the final test is the last load")

g = GPU()
t, logs = quick(g, core_max_mhz=0, mem_stage=True, mem_oc_max_mhz=1000, mem_curve_start_mhz=500)
L = "\n".join(logs)
check(t.best_profile.mem_offset_mhz == 800 and "(200 MHz Sicherheit)" in L,
      f"memory: +1000 passed -> +800 (200 MHz safety): +{t.best_profile.mem_offset_mhz}")
g = GPU(edc_from=800)
t, logs = quick(g, core_max_mhz=0, mem_stage=True, mem_oc_max_mhz=1000, mem_curve_start_mhz=500)
L = "\n".join(logs)
check(t.best_profile.mem_offset_mhz == 500 and "Bandbreite sinkt" in L and "Fehlerkorrektur" in L,
      f"bandwidth drops at +800 (EDC): the edge -> +700 passed, −200 = +500: +{t.best_profile.mem_offset_mhz}")
g = GPU(weak=True)
t, logs = quick(g, core_max_mhz=0, mem_stage=True, mem_oc_max_mhz=1000, mem_curve_start_mhz=500)
check(t.best_profile.mem_offset_mhz == 0, "copies starved from the start: memory stays at stock")

# ── 5) make a profile safer ──────────────────────────────────────────────────
print("make safer")
from core.nvtune_core import ProfileManager, TuneProfile
pm = ProfileManager(os.path.join(TMP, "profiles"))
pm.save(TuneProfile(name="GOP_CURVE_BAL_1002_1628", core_offset_mhz=134, mem_offset_mhz=1000,
                    curve_points=[[925, 2576], [1050, 2909], [1075, 2939]], curve_cap_mv=1050, is_stable=True))
p1 = pm.derate("GOP_CURVE_BAL_1002_1628")
check(p1.name == "GOP_CURVE_BAL_1002_1628_sicher" and p1.curve_points == [[925, 2546], [1050, 2879], [1075, 2909]]
      and p1.mem_offset_mhz == 800 and p1.core_offset_mhz == 104 and p1.curve_cap_mv == 1050
      and "Entschärft aus GOP_CURVE_BAL_1002_1628" in p1.notes,
      "copy '…_sicher': every point −30, memory +1000 → +800, cap kept, note says where from")
p2 = pm.derate(p1.name)
check(p2.name == "GOP_CURVE_BAL_1002_1628_sicher2" and p2.curve_points[1] == [1050, 2849] and p2.mem_offset_mhz == 600,
      "a copy of the copy: '…_sicher2', another −30 / −200")
pm.save(TuneProfile(name="Manual", core_offset_mhz=20, mem_offset_mhz=100))
p3 = pm.derate("Manual")
check(p3.core_offset_mhz == -10 and p3.mem_offset_mhz == 0, "an offset profile: core −30, memory not below 0")
check(pm.derate("nope") is None, "unknown profile: None")

# ── 6) GPU watchdog ──────────────────────────────────────────────────────────
print("GPU watchdog")
from core import gpu_watchdog as W
check(W.SESSIONS_FILE is None, "sessions are only recorded once the app sets the file (tests never write)")
W.record_own_load(1.0, 2.0)
logs_dir = os.path.join(TMP, "logs")
os.makedirs(logs_dir)
ts = lambda s: time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))      # noqa: E731
tune_log = os.path.join(logs_dir, "tune_20261002_154619.log")
open(tune_log, "w").close()
os.utime(tune_log, (ts("2026-10-02 16:28:36"), ts("2026-10-02 16:28:36")))
W.SESSIONS_FILE = Path(logs_dir) / "gpu_sessions.json"
W.record_own_load(ts("2026-10-03 18:00:00"), ts("2026-10-03 18:05:00"))       # a stress test from the app
W.SESSIONS_FILE.write_text(W.SESSIONS_FILE.read_text())                         # (valid json)
EVENTS = [(ts("2026-10-02 16:10:00"), 153), (ts("2026-10-02 16:28:36"), 153),   # the tune itself
          (ts("2026-10-03 18:04:59"), 153),                                     # the stress test
          (ts("2026-10-03 21:33:25"), 153), (ts("2026-10-03 21:33:36"), 153)]   # Hunt hung
read = lambda since: [e for e in EVENTS if e[0] >= since]                       # noqa: E731
left = W.trouble_since(ts("2026-10-02 15:00:00"), logs_dir, read)
check([i for _t, i in left] == [153, 153] and left[0][0] == ts("2026-10-03 21:33:25"),
      "own tune and stress-test events are left out, the game hang stays")


class CR:
    def __init__(self, name, applied):
        self._last_applied = Path(TMP) / "last_applied.json"
        self._last_applied.write_text(json.dumps({"name": name}))
        os.utime(self._last_applied, (applied, applied))
    def load_last_applied(self):
        return json.loads(self._last_applied.read_text())


cr = CR("GOP_CURVE_BAL_1002_1628", ts("2026-10-02 16:28:36"))
found = W.check(cr, logs_dir, 0, read)
check(found and found["profile"] == "GOP_CURVE_BAL_1002_1628" and len(found["events"]) == 2
      and found["last"] == ts("2026-10-03 21:33:36"), "since the profile was applied: the 2 Hunt events")
txt = W.describe(found, True)
check("GOP_CURVE_BAL_1002_1628" in txt and "03.10. 21:33" in txt and "GPU-Hänger" in txt
      and "Entschärfen" in txt, "the dialog text names profile, time, kind and the way out")
check(W.check(cr, logs_dir, found["last"], read) is None, "dismissed ('keep'): quiet until the next event")
check(W.check(CR("__stock__", ts("2026-10-02 16:28:36")), logs_dir, 0, read) is None, "stock: nothing to check")
check(W.check(CR("X", ts("2026-10-04 01:13:00")), logs_dir, 0, read) is None,
      "applied after the events (the safe profile): nothing to report")

# ── 7) the app's watchdog dialog ─────────────────────────────────────────────
print("app: watchdog dialog")
import GameOptimizerPro as G
import ui.components as UC


class FakeWin:
    def __init__(self): self.q = []
    def after(self, ms, fn): self.q.append(fn)
    def pump(self, limit=5.0):
        end = time.time() + limit
        while self.q and time.time() < end:
            fn = self.q.pop(0)
            fn()
            time.sleep(0.01)


class AppAB:
    def __init__(self): self.writes = []
    def write_and_apply(self, slot, p):
        self.writes.append((slot, p.name, p.mem_offset_mhz)); return True, ""
    def reset_to_stock(self, slot):
        self.writes.append((slot, "__stock__", 0)); return True, ""


class AppCR:
    def __init__(self): self.saved = []
    def save_last_applied(self, d): self.saved.append(d["name"])


boxes = []
G.messagebox = types.SimpleNamespace(showinfo=lambda *a, **k: boxes.append(("info", a)),
                                     showerror=lambda *a, **k: boxes.append(("error", a)))


def app_with(choice):
    app = object.__new__(G.GameOptimizerApp)
    app._window, app.pm, app.ab, app.cr = FakeWin(), pm, AppAB(), AppCR()
    app.monitor = types.SimpleNamespace(power_pct_to_watts=lambda p: 320.0, set_power_limit=lambda w: True)
    UC.ChoiceDialog = lambda *a, **k: types.SimpleNamespace(show=lambda: choice)
    return app


f2 = dict(found, profile="GOP_CURVE_BAL_1002_1628")
app = app_with("safer")
app._watchdog_dialog(f2)
app._window.pump()
check(app.ab.writes and app.ab.writes[0][0] == 2 and app.ab.writes[0][1].startswith("GOP_CURVE_BAL_1002_1628_sicher")
      and app.cr.saved == [app.ab.writes[0][1]] and boxes and boxes[-1][0] == "info",
      f"'make safer': a safer copy written to slot 2, recorded as applied: {app.ab.writes}")
check(app_settings.get("watchdog_seen_until") == found["last"], "those events count as seen")
app = app_with("stock")
app._watchdog_dialog(f2)
app._window.pump()
check(app.ab.writes == [(2, "__stock__", 0)] and app.cr.saved == ["__stock__"], "'stock': reset, recorded")
app_settings.set("watchdog_seen_until", 0)
app = app_with("keep")
app._watchdog_dialog(f2)
check(app.ab.writes == [] and app_settings.get("watchdog_seen_until") == found["last"],
      "'keep': nothing changed, asked again only after a new event")
app_settings.set("watchdog_seen_until", 0)
app = app_with(None)
app._watchdog_dialog(f2)
check(app.ab.writes == [] and not app_settings.get("watchdog_seen_until"), "closed: asked again at the next start")
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check("gpu_watchdog.SESSIONS_FILE = Path(logs_dir)" in src and "after(5000, self._watchdog_start)" in src,
      "the app records its own stress sessions and checks 5 s after the start")

W.SESSIONS_FILE = None
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
