"""Drive tools/ab_selftest.py (info / dryrun / live / restore) against a fake install."""
import os, sys, glob, shutil, tempfile, types, importlib.util, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

ns = {"__file__": os.path.join(SCR, "test_ab_profile.py")}
src = open(os.path.join(SCR, "test_ab_profile.py"), encoding="utf-8").read()
exec(compile(src.split('print("VFCurve")')[0], "fixtures", "exec"), ns)
make_profile = ns["make_profile"]

spec = importlib.util.spec_from_file_location("ab_selftest", os.path.join(ROOT, "tools", "ab_selftest.py"))
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)

from core.nvtune_core import AfterburnerController, GpuMonitor, TuneProfile
PRE_EXISTING = set(glob.glob(os.path.join(ROOT, "logs", "ab_selftest_*.txt")))

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

tmp = tempfile.mkdtemp(prefix="gop_tool_")
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "LA")
inst = os.path.join(tmp, "MSI Afterburner"); prof = os.path.join(inst, "Profiles"); os.makedirs(prof)
exe = os.path.join(inst, "MSIAfterburner.exe"); open(exe, "wb").close()
GPU = "VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg"
gpu_path = os.path.join(prof, GPU)
ORIG = make_profile(with_p2=True).encode("latin-1")
open(gpu_path, "wb").write(ORIG)
open(os.path.join(prof, "MSIAfterburner.cfg"), "wb").write(
    b"[Settings]\r\nUnlockVoltageControl=1\r\nUnlockVoltageMonitoring=0\r\nLockProfiles=0\r\n"
    b"StartMinimized=0\r\nSources=+GPU temperature,+GPU usage,-GPU voltage\r\n")
open(os.path.join(prof, "MSIAfterburner2.cfg"), "wb").write(b"CoreClockOffset=15\n")  # old-version junk


class FakeAB(AfterburnerController):
    applied = {"power_pct": 100, "core": 0}
    def __init__(self, *a, **k):
        self.running = True; self.log = []
        super().__init__(*a, **k)
    def _detect(self): self.exe, self.profile_dir = exe, prof
    def is_running(self): return self.running
    def close(self):
        self.log.append("close"); self.running = False; return True, ""
    def start(self, slot=None):
        self.log.append(f"start:{slot}"); self.running = True
        if slot:   # "Afterburner applies the slot" -> what NVML would then report
            from core.ab_profile import ProfileFile, decode_cfg
            it = ProfileFile(decode_cfg(open(gpu_path, "rb").read())[0]).items(f"Profile{slot}")
            FakeAB.applied = {"power_pct": int(it["powerlimit"]),
                              "core": 0 if it["coreclkboost"] == "1000000" else int(it["coreclkboost"]) // 1000}
        return True, ""
    def load_profile_slot(self, slot):
        self.log.append(f"send:{slot}"); return True, ""


mon = GpuMonitor()
dflt = mon.get_default_power_limit()
T.nvml_power = lambda m: (round(dflt * FakeAB.applied["power_pct"] / 100.0, 1), 150.0, dflt, dflt)
T.nvml_offsets = lambda m: (FakeAB.applied["core"], 0)
T.is_admin = lambda: True
T.gpu_busy = lambda m, seconds=3.0: 3.0

def run(cmd, fn, *a):
    out = T.Out(cmd)
    try:
        fn(out, *a)
    finally:
        out.close()
    return out, open(out.path, encoding="utf-8").read()

ab = FakeAB(mon.nvml.get_pci_identity())
# Deterministic monitoring (the real Afterburner may be running on this PC):
# first WITHOUT a voltage source, later with one.
FAKE_ENTRIES = [("GPU temperature", "C", 55.0, 0, 0x00), ("Power", "W", 250.0, 0, 0x61),
                ("CPU power", "W", 90.0, 0xFFFFFFFF, 0x100)]
mon.mahm.debug_entries = lambda: list(FAKE_ENTRIES)
print("info")
out, log = run("info", T.cmd_info, ab, mon)
for needle in ("RTX 4080", "DEV_2704 SUBSYS_F2981569 BUS_1", "[OK ] gefunden", "[Profile2] Power 80 %",
               "Core -350 MHz", "Basis für neue Kurven: [Defaults]", "alten GameOptimizerPro-Version",
               "[FEHLER] Spannungsüberwachung freigeschaltet", "[FEHLER] Graph 'GPU-Spannung' aktiv",
               "UnlockVoltageControl=1", "mV  Basis"):
    check(needle in log, f"info shows {needle!r}")
check(open(gpu_path, "rb").read() == ORIG, "info wrote nothing")
check("Leistung laut Afterburner: 250.0 W (Quelle 0x61)" in log, "absolute power source 0x61 shown")
FAKE_ENTRIES.append(("GPU voltage", "V", 1.050, 0, 0x40))
out, log = run("info", T.cmd_info, ab, mon)
check("[OK ] Graph 'GPU-Spannung' aktiv" in log and "1.050 V" in log,
      "voltage graph judged by what the monitoring really delivers")

print("dryrun")
args = types.SimpleNamespace(slot=2, core=15, mem=0, power=90, lock_mv=0, lock_mhz=0)
out, log = run("dryrun", T.cmd_dryrun, ab, args)
check("-PowerLimit=80" in log and "+PowerLimit=90" in log and "+CoreClkBoost=15000" in log,
      "dryrun diff shows the slot changes")
check("[OK ] 4 Zeile(n) neu/geändert, alle anderen Abschnitte unverändert" in log,
      "dryrun: 4 lines of [Profile2] change, other sections verified untouched")
check(open(gpu_path, "rb").read() == ORIG and ab.log == [], "dryrun wrote nothing, no restart")
args = types.SimpleNamespace(slot=4, core=0, mem=0, power=100, lock_mv=950, lock_mhz=2400)
out, log = run("dryrun", T.cmd_dryrun, ab, args)
check("neu angelegt" in log and "+CoreClkBoost=1000000" in log and "Kurve nachher: " in log,
      "dryrun curve into a new slot")

print("live (simulated Afterburner + NVML)")
largs = types.SimpleNamespace(slot=2, hold=0, curve=True, pause=False)
out, log = run("live", T.cmd_live, ab, mon, largs)
print("   log:", ab.log)
check(out.fails == 0, f"live test: 0 failures ({out.fails})")
check("A: Power-Limit laut Treiber" in log and "A: Core-Offset laut Treiber — +15 MHz" in log,
      "A measured power + core offset")
check("[OK ] Nur -Profile gesendet, kein Neustart" in log, "A2 took the no-restart path")
check("B: Power-Limit laut Treiber" in log and "flach bei" in log, "B curve step ran")
check("[OK ] Originale Profildatei wiederhergestellt" in log, "original restored (reported)")
check(open(gpu_path, "rb").read() == ORIG, "original profile file byte-identical after the test")
check(ab.log[-1] == "start:None", "Afterburner started normally at the end")
bk = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "GameOptimizerPro", "AfterburnerBackups", "*.cfg"))
check(len(bk) == 1 and open(bk[0], "rb").read() == ORIG, "backup = original")

print("live aborts cleanly on an exception mid-test")
ab2 = FakeAB(mon.nvml.get_pci_identity())
real_w = ab2.write_and_apply
calls = {"n": 0, "boot": []}
def boom(slot, p, startup="same"):
    calls["n"] += 1
    calls["boot"].append(startup)
    if calls["n"] == 2:
        raise KeyboardInterrupt()
    return real_w(slot, p, startup=startup)
ab2.write_and_apply = boom
try:
    run("live", T.cmd_live, ab2, mon, largs)
    check(False, "KeyboardInterrupt propagated")
except KeyboardInterrupt:
    check(True, "KeyboardInterrupt propagated after cleanup")
check(open(gpu_path, "rb").read() == ORIG and ab2.log[-1] == "start:None",
      "Ctrl+C mid-test: stock applied, original restored, Afterburner restarted")
check(calls["boot"] and all(s is None for s in calls["boot"]),
      f"the self-test never touches what the PC boots with (Afterburner [Startup]): {calls['boot']}")

print("restore")
open(gpu_path, "wb").write(b"[Profile2]\r\nbroken=1\r\n")
out, log = run("restore", T.cmd_restore, FakeAB(mon.nvml.get_pci_identity()),
               types.SimpleNamespace(file=None))
check(open(gpu_path, "rb").read() == ORIG, "restore puts the newest backup back")

print("GPU busy -> refuses")
T.gpu_busy = lambda m, seconds=3.0: 97.0
ab3 = FakeAB(mon.nvml.get_pci_identity())
out, log = run("live", T.cmd_live, ab3, mon, largs)
check("GPU-Last bis 97 %" in log and ab3.log == [], "refuses while a game runs, touches nothing")

mon.close()
for f in set(glob.glob(os.path.join(ROOT, "logs", "ab_selftest_*.txt"))) - PRE_EXISTING:
    os.remove(f)                     # only the logs THIS test wrote
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
