"""Round 33 — the hardness test: several loads at once like a game that is recorded or
streamed (3D + NVENC encoder + compute / memory), phases with idle gaps, every result checked.
No real GPU load here: the NVENC binding is checked by its struct layout, the workers run on
the numpy fake cupy, the controller on fake loads / a fake event log."""
import ctypes
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r33_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

# ── 1) NVENC binding: the header's struct layout ─────────────────────────────
print("NVENC binding")
from core import nvenc as NV  # noqa: E402
check(all(ctypes.sizeof(c) == s for c, s in NV.STRUCT_SIZES.items()),
      "every struct has the size of NVIDIA's header (x64)")
check(NV._InitParams.tuningInfo.offset == 136 and NV._InitParams.encodeConfig.offset == 88,
      "NV_ENC_INITIALIZE_PARAMS: encodeConfig at 88, tuningInfo right after the ME hints (136)")
check(NV._PicParams.codecPicParams.offset == 76 and NV._PicParams.inputBuffer.offset == 40,
      "NV_ENC_PIC_PARAMS: inputBuffer at 40, the codec union at 76")
check(NV._LockBitstream.bitstreamSizeInBytes.offset == 36 and NV._LockBitstream.bitstreamBufferPtr.offset == 56,
      "NV_ENC_LOCK_BITSTREAM: size at 36, data pointer at 56")
check(NV._sv(5) | (1 << 31) == (10 | (5 << 16) | (7 << 28) | (1 << 31)),
      "struct version = API 10.0 | version << 16 | 7 << 28 (NVENCAPI_STRUCT_VERSION)")
g = NV.PRESETS[5]
check(len(NV.PRESETS) == 7 and (g.d1, g.d2, g.d3) == (0x21c6e6b4, 0x297a, 0x4cba),
      "presets P1–P7 (P5 = OBS' default: 21c6e6b4-297a-4cba-…)")
mx = NV.max_api()
check(isinstance(mx, tuple) and len(mx) == 2, f"the driver's newest NVENC API is read without an error ({mx})")
check(NV.available() is None or isinstance(NV.available(), str), "available(): None or why not")

print("flight recorder: clock and voltage from one poll")
from core.gpu_flight import sample_of  # noqa: E402
from core.nvtune_core import GpuStats  # noqa: E402
s = sample_of(GpuStats(core_mhz=2805, voltage_mv=970, ab_core_mhz=2730, temp=60))
check(s["mhz"] == 2730 and s["mv"] == 970,
      "with Afterburner's voltage: its clock of the same poll (not NVML's instant: '2805 MHz at 970 mV')")
check(sample_of(GpuStats(core_mhz=2805, temp=60))["mhz"] == 2805, "no voltage reading: NVML's clock as before")

# ── 2) the stress worker: stop on request, encode mode without cupy ──────────
print("stress worker")
WORKER = os.path.join(ROOT, "_stress_worker.py")
spec = importlib.util.spec_from_file_location("gop_worker_r33", WORKER)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
sf = os.path.join(TMP, "stop_flag")
flag = W._StopFlag(sf)
check(not flag.is_set() and not W._StopFlag("").is_set(), "no stop file / no path: running")
Path(sf).touch()
time.sleep(0.15)
check(flag.is_set(), "the stop file appears: stop (looked at every 0.1 s)")
os.remove(sf)
check(flag.is_set(), "a stop stays a stop")

NOCUPY = Path(TMP, "nocupy", "cupy")
NOCUPY.mkdir(parents=True)
(NOCUPY / "__init__.py").write_text("raise ImportError('no cupy (test)')\n", encoding="utf-8")
r = subprocess.run([sys.executable, WORKER, str(os.getpid()), "encode"], capture_output=True, text=True,
                   env=dict(os.environ, PYTHONPATH=str(NOCUPY.parent)), timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
check(r.returncode == W.EXIT_NO_ENCODER and r.stdout.startswith("NOENC"),
      f"encode without cupy: 'NOENC', exit 4 — never the CPU fallback (exit {r.returncode})")

FAKE = os.path.join(HERE, "fakecupy")
for mode in ("transient", "mixed", "boost", "gemm", "mem"):
    stop = os.path.join(TMP, f"stop_{mode}")
    env = dict(os.environ, PYTHONPATH=FAKE, GOP_STRESS_N="64", GOP_STRESS_BOOST_N="32", GOP_STRESS_MEM_MB="1",
               GOP_STRESS_HEAVY_S="0.3", GOP_STRESS_BOOST_S="0.3", GOP_STRESS_STOP_FILE=stop, OMP_NUM_THREADS="1")
    p = subprocess.Popen([sys.executable, WORKER, str(os.getpid()), mode], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, env=env,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    first = p.stdout.readline().strip()
    time.sleep(0.5)
    t0 = time.time()
    Path(stop).touch()
    try:
        rc = p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = "hung"
    took = time.time() - t0
    check(first and rc == 0 and took < 3, f"{mode}: ends by itself on its stop file (exit {rc}, {took:.1f} s)")

# ── 3) the plan ──────────────────────────────────────────────────────────────
print("hardness test: phases")
from core import gpu_watchdog as WD  # noqa: E402
from core import hardness_test as H  # noqa: E402
p20 = H.plan(20)
check(len(p20) == 8 and all(s[3] == 150 for s in p20), "20 min: 8 phases of 150 s")
check([s[0] for s in p20[:5]] == ["game_rec", "changes_rec", "game_rec_compute", "game_rec_mem", "game_rec"],
      "the four combinations in turn")
check(len(H.plan(10)) == 4 and len(H.plan(45)) == 18 and H.plan(1)[0][3] == 150,
      "10 min: 4 · 45 min: 18 · shorter than a phase: one whole phase")
check(all("encode" in s[2] for s in p20) and {"game", "transient", "mem"} <= {k for s in p20 for k in s[2]},
      "every phase records (encoder); 3D, load changes and memory all come up")
check([d for d, _m in H.FURMARK_VARIANTS] == ["furmark-gl", "furmark-vk", "furmark-vk", "furmark-gl"]
      and {m for _d, m in H.FURMARK_VARIANTS} == {0, 8}, "FurMark: OpenGL / Vulkan, light / heavy in turn")


# ── 4) one load's verdict ────────────────────────────────────────────────────
class FP:
    def __init__(self, rc=None):
        self.rc, self.pid = rc, 0
    def poll(self): return self.rc


def load(kind="transient", talks=True, rc=None, err=(), noenc="", last=None, t0=None):
    ld = H._Load(kind, ["x"], talks=talks)
    ld.proc, ld.err, ld.noenc = FP(rc), list(err), noenc
    now = time.time()
    ld.t0 = now - 1 if t0 is None else t0
    ld.last = now if last is None else last
    return ld


now = time.time()
check(load().check(now) is None, "running and answering: fine")
check(load(rc=3, err=["17"]).check(now) == ("compute", "17"), "wrong result (ERR n, exit 3): computation error")
check(load(kind="encode", rc=3, err=["stall 6s"]).check(now)[0] == "stall", "encoder frame too slow: stall")
check(load(kind="encode", rc=3, err=["frame"]).check(now)[0] == "frame", "converted frame differs: frame")
check(load(kind="encode", rc=4, noenc="open session: busy").check(now) == ("noenc", "open session: busy"),
      "no encoder here: noenc (not a fault)")
check(load(kind="game", talks=False, rc=0).check(now) == ("stopped", ""), "FurMark closed by hand: stopped")
check(load(kind="game", talks=False, rc=-1073741819).check(now)[0] == "crash", "FurMark crashed: crash")
check(load(last=now - H.HANG_S - 1).check(now)[0] == "hang", f"silent for {H.HANG_S:.0f} s: hung GPU")
check(load(last=0, t0=now - H.START_S - 1).check(now)[0] == "hang" and load(last=0).check(now) is None,
      "no first answer within START_S: hung (a start-up in progress is fine)")
check(load(rc=3, err=["4"]).ended_badly() == ("compute", "4") and load(rc=0).ended_badly() is None,
      "after the end: a last wrong result still counts")


# ── 5) the controller ────────────────────────────────────────────────────────
print("hardness test: the run")
H.POLL_S, H.SETTLE_S = 0.05, 0.05
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"
PROFILE = {"name": "Testprofil", "curve_points": [[925, 2576], [950, 2681], [975, 2734],
           [1000, 2774], [1025, 2834], [1050, 2894], [1075, 2939]], "curve_cap_mv": 1050, "mem_offset_mhz": 500,
           "power_limit_pct": 100}
QUEUE: list = []       # events the fake log returns at its next poll
STARTED: list = []


class FakeTail:
    def poll(self):
        out = list(QUEUE)
        QUEUE.clear()
        return out
    def close(self): pass


class FakeLoad:
    def __init__(self, kind, script):
        self.kind, self.script = kind, script
        self.vals, self.err, self.last, self.t0 = {"ENC": 60.0} if kind == "encode" else {}, [], 0.0, 0.0
    def start(self):
        self.t0 = self.last = time.time()
        STARTED.append(self.kind)
    def check(self, now):
        s = self.script.get(self.kind, {})
        if s.get("noenc"):
            return ("noenc", "test")
        if s.get("fail_after") is not None and now - self.t0 >= s["fail_after"] and len(STARTED) >= s.get("from", 0):
            return ("compute", "5")
        return None
    def ask_stop(self): pass
    def stop(self, grace_s=0):
        s = self.script.get(self.kind, {})
        if s.get("event_on_stop"):
            QUEUE.append((int(time.time()), "nvlddmkm", 153))
        return bool(s.get("killed"))
    def ended_badly(self):
        return ("compute", "7") if self.script.get(self.kind, {}).get("bad_end") else None


def stats(temp=60):
    return lambda: types.SimpleNamespace(core_mhz=2880, mem_mhz=11301, voltage_mv=1050, gpu_power_w=250.0,
                                         power_w=250.0, temp=temp, gpu_usage=90)


def run(script=None, minutes=0.05, temp=60, **kw):
    STARTED.clear()
    QUEUE.clear()
    logs = Path(TMP, f"logs_{len(os.listdir(TMP))}")
    logs_seen = []
    t = H.HardnessTest(stats(temp), logs, minutes=minutes, profile=PROFILE, phase_s=0.4, idle_s=0.15,
                       tail_factory=FakeTail, load_factory=lambda k, s: FakeLoad(k, script or {}),
                       on_log=lambda s, tag: logs_seen.append(s), gpu_name="Test GPU", **kw)
    return t, t.run(), logs, logs_seen


t, r, logs, seen = run(minutes=0.005)                    # shorter than a phase -> one phase of 0.4 s
check(r.passed and not r.aborted and r.kind == "" and STARTED == ["game", "encode"],
      f"all loads fine: passed ({STARTED})")
check(r.log_path and Path(r.log_path).exists() and "bestanden" in Path(r.log_path).read_text(encoding="utf-8"),
      "a log file in the logs folder (hard_*.log)")
check(WD.SESSIONS_FILE.exists() and not WD.own_load_active(), "an own GPU load: recorded, not active any more")

t, r, logs, seen = run({"transient": {"fail_after": 0.1}}, minutes=0.2)
check(not r.passed and r.kind == "compute" and r.load == "transient" and r.phase == "Lastwechsel + Aufnahme",
      f"a wrong result in phase 2: computation error, phase and load named ({r.kind}, {r.phase})")
check(r.point.get("mv") == 1050 and r.anchors == [1025, 1050, 1075],
      f"the state just before it and the curve points involved ({r.point.get('mv')}, {r.anchors})")
rows = WD.field_faults(logs)
check(len(rows) == 1 and rows[0]["mv"] == 1050 and (logs / "gpu_faults").exists(),
      "into the field list (the next tune keeps more margin there) + the recording")
check(r.unstable and "Rechenfehler" in r.reason, "unstable, the reason in words")


class EventSoon(FakeLoad):
    def check(self, now):
        if now - self.t0 > 0.1 and not getattr(self, "_sent", False):
            self._sent = True
            QUEUE.append((time.time(), "nvlddmkm", 153))
        return None


t = H.HardnessTest(stats(), Path(TMP, "logs_ev"), minutes=0.005, profile=PROFILE, phase_s=0.4, idle_s=0.15,
                   tail_factory=FakeTail, load_factory=lambda k, s: EventSoon(k, {}))
STARTED.clear()
r = t.run()
check(r.kind == "driver" and "nvlddmkm 153" in r.reason, f"a driver event during a phase: failed ({r.reason})")

t, r, logs, seen = run({"encode": {"killed": True, "event_on_stop": True}}, minutes=0.005)
check(r.passed and any("endete nicht von selbst" in s for s in seen),
      "a load that had to be killed: the event of that second is the kill's, not the profile's")

t, r, logs, seen = run({"game": {"event_on_stop": True}}, minutes=0.005)
check(not r.passed and r.kind == "driver",
      "an event right after the last phase (no kill): caught by the final look, not missed")

t, r, logs, seen = run({"transient": {"bad_end": True}}, minutes=0.1)
check(not r.passed and r.kind == "compute" and "beim Lastende" in r.reason,
      f"a wrong result as the loads end (a load step down): counts ({r.reason})")

t, r, logs, seen = run({"encode": {"noenc": True}}, minutes=0.1)
check(r.passed and not r.encoder and STARTED.count("encode") == 1,
      f"no encoder here: once tried, then on without it, still a result ({STARTED})")

stop_t = H.HardnessTest(stats(), Path(TMP, "logs_stop"), minutes=0.2, profile=PROFILE, phase_s=0.4, idle_s=0.15,
                        tail_factory=FakeTail, load_factory=lambda k, s: FakeLoad(k, {}))
stop_t._progress = lambda pct, text: stop_t.stop_event.set()
r = stop_t.run()
check(r.aborted and r.kind == "stopped" and not r.unstable, "Stop: aborted, no result, no fault")

t, r, logs, seen = run(minutes=0.005, temp=90, max_temp=85)
check(r.kind == "temp" and not r.passed and not r.unstable and not WD.field_faults(logs),
      "temperature limit: the test ends — not a stability fault, nothing recorded")

# ── 6) the tuner's last stage ────────────────────────────────────────────────
print("tuner: hardness test as the last stage")
import core.nvtune_tuner as NT  # noqa: E402
check(NT.TunerConfig().hard_test is False and NT.TunerConfig(hard_test=True).hard_test_min == 10,
      "off unless the GPU tab turns it on — a simulated tune never starts real loads")
SEEN_PROFILES = []


def fake_factory(result):
    class F:
        def __init__(self, *a, **k):
            SEEN_PROFILES.append((k.get("profile"), k.get("record_field"), k.get("minutes")))
        def run(self):
            return result
    return F


tn = object.__new__(NT.AutoTuner)
tn.config = NT.TunerConfig(hard_test=True, furmark_path="")
tn._stop = __import__("threading").Event()
tn._log_dir = TMP
tn.monitor = Mon = types.SimpleNamespace(read=lambda: types.SimpleNamespace(name="Test GPU"))
tn._log = lambda *a, **k: None
tn._progress = lambda *a, **k: None
tn.hardness_factory = fake_factory(H.HardResult(kind="compute", reason="x", point={"mv": 1050}, max_mv=1060))
res = tn._hard_test(97, {"name": "cand", "curve_points": PROFILE["curve_points"], "curve_cap_mv": 1050})
check(not res.passed and res.crash_detected and res.compute_error and res.last_voltage_mv == 1050,
      "a failure -> a failed StressResult with the failure's voltage (the final test steps back there)")
check(SEEN_PROFILES[-1][1] is False and SEEN_PROFILES[-1][2] == 10 and SEEN_PROFILES[-1][0]["curve_cap_mv"] == 1050,
      "the candidate's curve is tested; a tune's failure is not a game's (no field-list row)")
tn.hardness_factory = fake_factory(H.HardResult(kind="driver", reason="x", point={"mv": 975}))
res = tn._hard_test(97, {})
check(res.tdr_detected and not res.compute_error and res.last_voltage_mv == 975, "a driver event: TDR-like")
tn.hardness_factory = fake_factory(H.HardResult(passed=True, max_mhz=2880, max_mv=1050))
check(tn._hard_test(97, {}).passed, "passed: passed")
tn.hardness_factory = fake_factory(H.HardResult(aborted=True, kind="stopped", reason="FurMark closed"))
res = tn._hard_test(97, {})
check(res.passed and res.aborted, "FurMark closed by hand: no verdict, the profile is not thrown away")
tn._stop.set()
check(tn._hard_test(97, {}) is None, "the tune aborted: None (the run ends)")
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check(src.count("self._hard_test(") == 2 and "verify = hard" in src and "final = hard" in src,
      "both modes run it after the game test; its failure decides the step back")
gsrc = open(os.path.join(ROOT, "ui", "tab_gpu.py"), encoding="utf-8").read()
check(gsrc.count("hard_test=hard_on") == 2 and '"hard_test"' in gsrc,
      "the GPU tab: one switch for both modes, remembered with the other tuner settings")

print("tuner: a driver reset in the point search gets time")
# Live 19.10.: a reset at 1050 mV, 5 s later the next point's first step failed at a clock that had
# passed that morning. Now: a pause after the reset, and that first failure gets one repeat.
pt = object.__new__(NT.AutoTuner)
pt.config = NT.TunerConfig(reset_pause_s=1, crash_pause_s=0)
pt._stop = __import__("threading").Event()
PLOG, RUNS = [], []
pt._log = lambda m, *a, **k: PLOG.append(m)
pt._progress = pt._tick = lambda *a, **k: None
pt._apply_vf = lambda *a, **k: None
pt._perf_note = lambda r: ""
_orig_time = NT.time
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


def queue(*results):
    q = list(results)

    def srun(stress, d, m, on_tick=None, mode="gemm"):
        RUNS.append(mode)
        return q.pop(0)
    pt._srun = srun


def sres(ok, tdr=False):
    r = NT.StressResult(passed=ok, steady_voltage_mv=1025, avg_core_mhz=2870, max_core_mhz=2880)
    if not ok:
        r.crash_detected = True
        r.tdr_detected = tdr
        r.compute_error = not tdr
        r.abort_reason = "TDR" if tdr else "Rechenfehler unter Last (GPU instabil)"
    return r


queue(sres(False, tdr=True))
t0 = time.time()
p1 = pt._test_point(None, 1050, 2944, 2760, "P", 0)
paused = time.time() - t0
queue(sres(False), sres(True))
p2 = pt._test_point(None, 1025, 2879, 2700, "P", 0)
check(not p1.passed and p1.tdr and paused >= 0.9 and any("Pause 1 s" in m for m in PLOG),
      f"a reset: the pause before the next step ({paused:.1f} s)")
check(p2.passed and len(RUNS) == 3 and any("direkt nach dem Treiber-Reset" in m for m in PLOG),
      "the first step after it failed: repeated once after a pause — passed, the point is not lowered")
RUNS.clear()
queue(sres(False), sres(True))
p3 = pt._test_point(None, 1025, 2894, 2700, "P", 0)
check(not p3.passed and len(RUNS) == 1, "a later failure (no reset before it) is not repeated")
queue(sres(False, tdr=True), sres(False), sres(False), sres(True))
RUNS.clear()
pt._test_point(None, 1000, 2834, 2640, "P", 0)
p5 = pt._test_point(None, 1000, 2826, 2640, "P", 0)
check(not p5.passed and len(RUNS) == 3, "only once: failing again after the repeat counts")
check(NT.TunerConfig().reset_pause_s == 30, "default: 30 s after a reset")
NT.time = _orig_time

PLOG.clear()
pt.config = NT.TunerConfig(crash_pause_s=1)
pt._crash_pause()
pt._crash_pause()
check(sum("der Treiber erholt sich nach dem Absturz" in m for m in PLOG) == 1,
      "one crash, one pause: the step back right after the game test's pause does not pause again")

from core import curve_tune as CT  # noqa: E402
LIVE = [(1070, 2894), (1045, 2834), (1020, 2819), (995, 2764), (970, 2726), (945, 2641), (920, 2578)]
new, hit = CT.lower_near(LIVE, 15, 1015, 25)
check(hit == {995, 1020} and dict(new)[1020] == 2804 and dict(new)[995] == 2749 and dict(new)[1045] == 2834,
      f"hardness step back: the points around the fault (live: 1015 mV -> 995 and 1020) −15, the rest kept: {new}")
check(CT.lower_near(LIVE, 15, 0, 25)[1] == {mv for mv, _f in LIVE}, "the fault's voltage unknown: every point")
c = LIVE
for _i in range(6):
    c, _h = CT.lower_near(c, 15, 1020, 10)
check(dict(c)[1020] == 2729 and dict(c)[995] == 2729 and all(a[1] >= b[1] for a, b in zip(c, c[1:])),
      f"a point lowered far: never slower above than below it (the curve stays rising): {c}")

print("tuner: every tune starts equally warm")
# Live 19.10.: started 5 min after another run, the card reached 1070 instead of 1075 mV at stock
# (other measuring points) and scored 7192 instead of ~7250 at stock.
ct = object.__new__(NT.AutoTuner)
ct._stop = __import__("threading").Event()
CLOG, TEMPS = [], [60, 55, 50, 44, 40]
ct._log = lambda m, *a, **k: CLOG.append(m)
ct._progress = lambda *a, **k: None
ct.monitor = types.SimpleNamespace(read=lambda: types.SimpleNamespace(temp=TEMPS.pop(0) if len(TEMPS) > 1 else TEMPS[0]))
ct.config = NT.TunerConfig(start_cool_max_s=30)
t0 = time.time()
ct._start_cool()
check(any("Abkühlen vor dem Start: 60 → 45 °C" in m for m in CLOG) and TEMPS == [40] and time.time() - t0 < 6,
      f"60 °C: idles until 45 °C or less, then the tune starts ({time.time() - t0:.1f} s)")
CLOG.clear()
TEMPS[:] = [60]
ct.config = NT.TunerConfig(start_cool_max_s=1)
ct._start_cool()
check(any("nach 1 s noch 60 °C" in m for m in CLOG), "never longer than the limit, says so")
CLOG.clear()
TEMPS[:] = [41]
ct.config = NT.TunerConfig(start_cool_max_s=180)
ct._start_cool()
check(not CLOG, "already cool: no wait, nothing logged")
check(NT.TunerConfig().start_cool_max_s == 0 and NT.TunerConfig().start_cool_c == 45
      and gsrc.count("start_cool_max_s=180") == 2,
      "off in code (simulated tunes never wait), the GPU tab turns it on for both modes (3 min at most)")

print("tuner: the encoder next to every stability step")
check(NT.TunerConfig().encoder_companion is False, "off unless the GPU tab turns it on (simulated tunes unchanged)")


class FMon:
    def read(self):
        return GpuStats(temp=55, voltage_mv=1000, core_mhz=2700, gpu_usage=95, gpu_power_w=250)


saved_env = dict(os.environ)
os.environ.update(PYTHONPATH=FAKE, GOP_STRESS_N="64", GOP_STRESS_BOOST_N="32", GOP_STRESS_MEM_MB="1",
                  OMP_NUM_THREADS="1", FAKE_CORRUPT_DOT="40")
try:
    st = NT.StressTester(FMon())
    st.companion = "transient"                  # any worker mode: here one whose 40th product is wrong
    r = st.run(6, 90, mode="mem", companion=True)
    check(not r.passed and r.compute_error and "Encoder-Last daneben" in r.abort_reason,
          f"a wrong result in the companion fails the step like its own ({r.abort_reason})")
    left = [f for f in os.listdir(tempfile.gettempdir()) if f.startswith(f"gop_tstop_{os.getpid()}_")]
    check(st._proc is None and st._comp is None and not left, "both loads ended, no stop files left")
    os.environ.pop("FAKE_CORRUPT_DOT")
    st2 = NT.StressTester(FMon())
    st2.companion = "encode"                    # the fake cupy has no RawModule: like a PC without NVENC
    r2 = st2.run(4, 90, mode="mem", companion=True)
    check(r2.passed and st2.companion_off, f"no encoder here: the step runs without it ({st2.companion_off!r})")
    r3 = st2.run(3, 90, mode="mem", companion=True)
    check(r3.passed and st2._comp is None, "… and it is not tried again for every step")
    st3 = NT.StressTester(FMon())
    st3.companion = "transient"
    r4 = st3.run(3, 90, mode="mem")
    check(r4.passed and st3._comp is None, "steps that compare performance run without it (companion=False)")
finally:
    os.environ.clear()
    os.environ.update(saved_env)
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check(src.count("self._srun(stress") == 5 and 'stress.companion = "encode" if cfg.encoder_companion' in src,
      "curve points, OC steps, final and game test run with it; baseline, power and benchmarks don't")
check(gsrc.count("encoder_companion=self._enc_on()") == 2 and '"enc_comp"' in gsrc,
      "GPU tab: one switch for both modes, remembered")

# ── 7) the stress page ───────────────────────────────────────────────────────
print("stress page")
src = open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8").read()
check("StressTab(parent, self.monitor, ab=self.ab, pm=self.pm, tuner=self.tuner)" in src,
      "the stress page gets Afterburner, profiles and the tuner (make-safer after a failure)")
import customtkinter as ctk  # noqa: E402
root = ctk.CTk()
root.withdraw()                                       # never mapped
from ui.tab_stress import StressTab  # noqa: E402


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=40, voltage_mv=900, core_mhz=210, gpu_power_w=20, gpu_usage=1,
                                     temp_limit_c=90, power_max_w=320, name="Test GPU")


cr = types.SimpleNamespace(load_last_applied=lambda: dict(PROFILE))
page = StressTab(root, Mon(), tuner=types.SimpleNamespace(is_running=False, cr=cr))
page._alive = False
root.update_idletasks()
check("Testprofil" in page.lbl_hard_profile.cget("text"), "it names the profile it tests")
check(page._busy_text() == "", "nothing else running: can start")
page.tuner.is_running = True
check("Tuner" in page._busy_text(), "while the tuner runs: no hardness test")
page.tuner.is_running = False
page._hard_done(H.HardResult(passed=True, seconds=1200, max_mhz=2880, max_mv=1050, peak_temp=66))
check(page.lbl_hard_status.cget("text").startswith("✓ Bestanden"), "passed: shown")
page._hard_done(H.HardResult(kind="temp", reason="Temperaturgrenze erreicht"))
check(page.lbl_hard_status.cget("text").startswith("■"), "temperature limit: shown as ended, no dialog")
root.destroy()

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
