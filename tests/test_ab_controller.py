"""AfterburnerController flow tests against a fake Afterburner install (no processes started)."""
import os, sys, tempfile, shutil, glob, time, threading, importlib.util
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

spec = importlib.util.spec_from_file_location("tap", os.path.join(SCR, "test_ab_profile.py"))
# reuse the fixture builders without running the module's tests
src = open(os.path.join(SCR, "test_ab_profile.py"), encoding="utf-8").read()
fixture_src = src.split('print("VFCurve")')[0]
ns = {"__file__": os.path.join(SCR, "test_ab_profile.py")}
exec(compile(fixture_src, "fixtures", "exec"), ns)
make_profile, make_curve = ns["make_profile"], ns["make_curve"]

from core.nvtune_core import AfterburnerController, TuneProfile
from core.ab_profile import ProfileFile, VFCurve

FAILS = []
def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        FAILS.append(label)

tmp = tempfile.mkdtemp(prefix="gop_ab_")
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "LocalAppData")
inst = os.path.join(tmp, "MSI Afterburner")
prof = os.path.join(inst, "Profiles")
os.makedirs(prof)
exe = os.path.join(inst, "MSIAfterburner.exe")
open(exe, "wb").close()
GPU = "VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg"
gpu_path = os.path.join(prof, GPU)
with open(gpu_path, "wb") as f:
    f.write(make_profile(with_p2=True).encode("latin-1"))
with open(os.path.join(prof, "MSIAfterburner.cfg"), "wb") as f:
    f.write(("[Settings]\r\nLockProfiles=0\r\nStartMinimized=1\r\nUnlockVoltageControl=1\r\n"
             "UnlockVoltageMonitoring=1\r\nSources=+GPU temperature,+GPU usage,+GPU voltage,-Power\r\n").encode())
# an old card's leftover file must never be touched
OLD = "VEN_10DE&DEV_2204&SUBSYS_39873842&REV_A1&BUS_10&DEV_0&FN_0.cfg"
with open(os.path.join(prof, OLD), "wb") as f:
    f.write(make_profile().encode("latin-1"))
old_card_bytes = open(os.path.join(prof, OLD), "rb").read()


class FakeAB(AfterburnerController):
    """Real file logic; process control replaced by a simulation."""
    def __init__(self, *a, **k):
        self.log = []
        self.running = False
        self.fail_close = False
        super().__init__(*a, **k)

    def _detect(self):
        self.exe, self.profile_dir = exe, prof

    def is_running(self):
        return self.running

    def close(self):
        self.log.append("close")
        if self.fail_close:
            return False, "cannot close"
        self._call(self.on_ab_closing)
        self.running = False
        return True, ""

    def start(self, slot=None):
        self.log.append(f"start:{slot}")
        self.running = True
        self._call(self.on_ab_started)
        return True, ""

    def load_profile_slot(self, slot):
        self.log.append(f"send:{slot}" if self.running else f"start:{slot}")
        self.running = True
        return True, ""


notified = []
ab = FakeAB((0x2704, 0xF2981569, 1))
ab.on_ab_closing = lambda: notified.append("closing")
ab.on_ab_started = lambda: notified.append("started")

print("setup / discovery")
st = ab.check_ab_setup()
check(st["cfg_found"] and st["voltage_control"] and st["voltage_monitoring"]
      and st["voltage_graph"] and st["start_minimized"] and not st["profiles_locked"],
      f"check_ab_setup reads Profiles\\MSIAfterburner.cfg: {st}")
p, why = ab.find_gpu_profile()
check(p == gpu_path, f"find_gpu_profile -> this card ({why})")

print("apply while Afterburner is NOT running")
before = open(gpu_path, "rb").read()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=15, power_limit_pct=90))
after = open(gpu_path, "rb").read()
check(ok and err == "", "write_and_apply ok")
check(ab.log == ["start:2"], f"no close, started with -Profile2: {ab.log}")
it = ProfileFile(after.decode("latin-1")).items("Profile2")
check(it["coreclkboost"] == "15000" and it["powerlimit"] == "90", "slot 2 written")
bk = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "GameOptimizerPro", "AfterburnerBackups", "*.cfg"))
check(len(bk) == 1 and open(bk[0], "rb").read() == before and ab.last_backup == bk[0],
      "backup of the ORIGINAL file before the first write")
check(not os.path.exists(gpu_path + ".gop.tmp"), "no temp file left")
check(open(os.path.join(prof, OLD), "rb").read() == old_card_bytes, "old card's file untouched")

print("same values again (AB running)")
ab.log.clear()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=15, power_limit_pct=90))
check(ok and ab.log == ["send:2"], f"unchanged -> only -Profile2 sent, no restart: {ab.log}")
check(open(gpu_path, "rb").read() == after, "file not rewritten")

print("new values (AB running)")
ab.log.clear()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=30, mem_offset_mhz=500, power_limit_pct=95))
check(ok and ab.log == ["close", "start:2"], f"close -> write -> start: {ab.log}")
bk2 = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "GameOptimizerPro", "AfterburnerBackups", "*.cfg"))
check(len(bk2) == 1, "only ONE backup per session (the original)")
it = ProfileFile(open(gpu_path, "rb").read().decode("latin-1")).items("Profile2")
check(it["coreclkboost"] == "30000" and it["memclkboost"] == "500000" and it["powerlimit"] == "95", "values")

print("V/F curve lock (Rundum point search path)")
ab.log.clear()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=30, lock_voltage_mv=950, lock_freq_mhz=2400))
it = ProfileFile(open(gpu_path, "rb").read().decode("latin-1")).items("Profile2")
c = VFCurve.from_hex(it["vfcurve"])
check(ok and it["coreclkboost"] == "1000000", "curve marker written")
top = max(c.active_points(), key=lambda q: (q.effective_mhz, -q.voltage_mv))
check(abs(top.effective_mhz - 2400) <= 1 and abs(top.voltage_mv - 950) < 3.2
      and all(p.effective_mhz <= 2301 for p in c.active_points() if p.voltage_mv > top.voltage_mv),
      "lock at 950 mV / 2400 MHz is the top, everything above it 100 MHz lower")

print("clamps for garbage profile JSON")
ab.log.clear()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=9999, mem_offset_mhz="x", power_limit_pct=500))
it = ProfileFile(open(gpu_path, "rb").read().decode("latin-1")).items("Profile2")
check(ok and it["coreclkboost"] == "999000" and it["memclkboost"] == "0" and it["powerlimit"] == "150",
      f"core clamped to +999 (not the 1000000 curve marker), mem garbage -> 0, power -> 150: {it['coreclkboost']}/{it['memclkboost']}/{it['powerlimit']}")

print("reset_to_stock")
ab.log.clear()
ok, err = ab.reset_to_stock(2)
it = ProfileFile(open(gpu_path, "rb").read().decode("latin-1")).items("Profile2")
c = VFCurve.from_hex(it["vfcurve"])
check(ok and it["coreclkboost"] == "0" and it["memclkboost"] == "0" and it["powerlimit"] == "100"
      and all(p.offset_mhz == 0 for p in c.points() if p.voltage_mv > 0),
      "stock: 0 / 0 / 100 %, all curve offsets 0 — written into OUR slot")
ok1 = ProfileFile(open(gpu_path, "rb").read().decode("latin-1")).items("Profile1")
check(ok1["fanmode"] == "1" and ok1["powerlimit"] == "100", "user's slot 1 untouched")

print("error paths")
ab.log.clear(); ab.running = True; ab.fail_close = True
snap = open(gpu_path, "rb").read()
ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=45))
check(not ok and "cannot close" in err and open(gpu_path, "rb").read() == snap,
      "AB won't close -> nothing written, error returned")
ab.fail_close = False
ok, err = ab.write_and_apply(9, TuneProfile())
check(not ok and "ungültig" in err, "slot 9 rejected")
ab2 = FakeAB((0x2504, 0x12345678, 1))       # card without a profile file
ok, err = ab2.write_and_apply(2, TuneProfile())
check(not ok and "Kein Afterburner-Profil passt" in err, f"no file for this card: {err[:60]}…")

# read-only file -> PermissionError path: AB must be restarted, error returned
ab.log.clear(); ab.running = True
os.chmod(gpu_path, 0o444)
try:
    ok, err = ab.write_and_apply(2, TuneProfile(core_offset_mhz=60))
finally:
    os.chmod(gpu_path, 0o666)
check(not os.path.exists(gpu_path + ".gop.tmp"), "failed replace leaves no temp file")
check(not ok and ("Schreibrechte" in err or "fehlgeschlagen" in err) and ab.log[-1].startswith("start"),
      f"write refused -> Afterburner started again + error: {ab.log} / {err[:50]}")

print("restore_file")
ab.log.clear()
ok, err = ab.restore_file(bk[0])
check(ok and open(gpu_path, "rb").read() == before and ab.log[-1] == "start:None",
      "backup restored byte-exact, Afterburner started without a profile switch")

print("thread safety: parallel applies are serialized")
ab.log.clear(); ab.running = True
res = []
def worker(v):
    res.append(ab.write_and_apply(2, TuneProfile(core_offset_mhz=v)))
ts = [threading.Thread(target=worker, args=(v,)) for v in (5, 10, 20, 25)]
[t.start() for t in ts]; [t.join() for t in ts]
seq = [x.split(":")[0] for x in ab.log]
check(all(r[0] for r in res), "all four applies ok")
check(all(seq[i] in ("close", "send") or (seq[i] == "start" and i > 0) for i in range(len(seq))),
      f"no interleaving: {ab.log}")
check("closing" in notified and "started" in notified,
      f"hooks called: on_ab_closing (MAHM suspend) + on_ab_started (resume): {sorted(set(notified))}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f_ in FAILS:
    print("  -", f_)
sys.exit(1 if FAILS else 0)
