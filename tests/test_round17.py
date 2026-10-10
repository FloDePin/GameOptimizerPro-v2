"""Round 17 — what the PC BOOTS with. Live (RTX 4080, 08.10.): after the Quick tune
Afterburner's [Startup] (applied at every Windows start) held core +119 / memory +0
/ 100 % — one of the tune's steps — while the saved and "active" profile was
+119 / +700 / 96 %; four days of boots ran the step (nvidia-smi: memory 11201 MHz,
320 W). The app now sets [Startup]: to what the user applies, to the known-good
profile while a tune tests steps, to the saved profile at the end.
No process is started: a fake Afterburner install in a temp folder."""
import os
import shutil
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


src = open(os.path.join(SCR, "test_ab_profile.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(SCR, "test_ab_profile.py")}
exec(compile(src.split('print("VFCurve")')[0], "fixtures", "exec"), ns)
make_profile, make_curve = ns["make_profile"], ns["make_curve"]

TMP = tempfile.mkdtemp(prefix="gop_r17_")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "LocalAppData")      # backups: never the user's
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N
I18N._current_lang = "de"
import core.ab_profile as AP
from core.ab_profile import ProfileFile, SlotSettings, VFCurve
from core.nvtune_core import AfterburnerController, TuneProfile


def boot_on(text):
    """'Apply overclocking at system startup' switched on, as Afterburner writes it."""
    pf = ProfileFile(text)
    pf.set_values("Startup", {"PowerLimit": "100", "CoreClkBoost": "0", "MemClkBoost": "0",
                              "VFCurve": make_curve().hex().upper()})
    return pf.text()


def startup(text):
    it = ProfileFile(text).items("Startup")
    return (it.get("coreclkboost"), it.get("memclkboost"), it.get("powerlimit"))


def offsets(text, section):
    c = ProfileFile(text).get(section, "VFCurve")
    return sorted({round(p.offset_mhz) for p in VFCurve.from_hex(c).active_points()}) if c else None


# ── 1) the file logic ────────────────────────────────────────────────────────
print("[Startup] in the profile file")
off = make_profile(with_p2=True)                     # the fixture: option OFF (empty values)
check(not AP.startup_enabled(off) and AP.copy_slot_to_startup(off, 2) == off
      and AP.apply_startup(off, SlotSettings(core_mhz=30)) == off and AP.startup_matches_slot(off, 2) is None,
      "option off: [Startup] is never written (the app does not switch it on)")
on = boot_on(off)
check(AP.startup_enabled(on), "option on: detected")
c2 = AP.copy_slot_to_startup(on, 2)
check(startup(c2) == ("-350000", "600000", "80") and offsets(c2, "Startup") == [-350]
      and AP.startup_matches_slot(c2, 2) is True and AP.startup_matches_slot(c2, 1) is False,
      f"copy slot 2 -> boot: {startup(c2)}")
check(ProfileFile(c2).get("Startup", "FanMode") == "" and ProfileFile(c2).get("Profile2", "UnknownKey") == "keepme",
      "fan values and unknown keys stay as Afterburner wrote them")
s96 = AP.apply_startup(on, SlotSettings(core_mhz=119, mem_mhz=700, power_pct=96))
check(startup(s96) == ("119000", "700000", "96") and offsets(s96, "Startup") == [119],
      f"settings -> boot: {startup(s96)}, curve +119 on every point")
check(AP.section_equivalent(s96, s96, "Startup") and not AP.section_equivalent(on, s96, "Startup")
      and AP.section_equivalent(off, off, "NoSuchSection"), "section_equivalent")

# ── 2) the controller ────────────────────────────────────────────────────────
print("AfterburnerController.write_and_apply and the boot entry")
inst = os.path.join(TMP, "MSI Afterburner")
prof = os.path.join(inst, "Profiles")
os.makedirs(prof)
open(os.path.join(inst, "MSIAfterburner.exe"), "wb").close()
GPU = "VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg"
gpu_path = os.path.join(prof, GPU)
with open(os.path.join(prof, "MSIAfterburner.cfg"), "wb") as f:
    f.write(b"[Settings]\r\nLockProfiles=0\r\nStartMinimized=1\r\n")


def put(text):
    with open(gpu_path, "wb") as f:
        f.write(text.encode("latin-1"))


def file_text():
    return open(gpu_path, "rb").read().decode("latin-1")


class FakeAB(AfterburnerController):
    """Real file logic. 'Afterburner' saves its own [Startup] when it is closed
    (exit_startup) — what the live file suggested: a tune's step ended up there."""
    def __init__(self):
        self.log, self.running, self.exit_startup = [], False, None
        super().__init__((0x2704, 0xF2981569, 1))

    def _detect(self):
        self.exe, self.profile_dir = os.path.join(inst, "MSIAfterburner.exe"), prof

    def is_running(self):
        return self.running

    def close(self):
        self.log.append("close")
        if self.exit_startup:
            pf = ProfileFile(file_text())
            pf.set_values("Startup", self.exit_startup)
            put(pf.text())
        self.running = False
        return True, ""

    def start(self, slot=None):
        self.log.append(f"start:{slot}")
        self.running = True
        return True, ""

    def load_profile_slot(self, slot):
        self.log.append(f"send:{slot}" if self.running else f"start:{slot}")
        self.running = True
        return True, ""


put(boot_on(make_profile(with_p2=True)))
ab = FakeAB()
quick = TuneProfile(name="GOP_OC+UV_1004_1342", core_offset_mhz=119, mem_offset_mhz=700, power_limit_pct=96)
ok, err = ab.write_and_apply(5, quick)
check(ok and startup(file_text()) == ("119000", "700000", "96") and ab.startup_state(5) is True,
      f"applying a profile: the PC boots with it too: {startup(file_text())}")
ab.log.clear()
ok, _ = ab.write_and_apply(5, quick)
check(ok and ab.log == ["send:5"], f"the same again: no restart ({ab.log})")
ok, _ = ab.write_and_apply(3, TuneProfile(core_offset_mhz=15), startup=None)
check(ok and startup(file_text()) == ("119000", "700000", "96"), "startup=None: the boot entry is left alone")
good = TuneProfile(name="GOP_CURVE_BAL_1002_1628_sicher", core_offset_mhz=50, mem_offset_mhz=300)
ok, _ = ab.write_and_apply(3, TuneProfile(name="__tuning__", core_offset_mhz=184), startup=good)
check(ok and startup(file_text()) == ("50000", "300000", "100") and offsets(file_text(), "Profile3") == [184],
      f"a step in the slot, the known-good profile at boot: {startup(file_text())}")
# Afterburner saves a step into [Startup] when it is closed — ours is written after that
ab.running = True
ab.exit_startup = {"CoreClkBoost": "184000", "MemClkBoost": "0", "PowerLimit": "100"}
ab.log.clear()
ok, _ = ab.write_and_apply(3, TuneProfile(name="__tuning__", core_offset_mhz=170), startup=good)
check(ok and ab.log == ["close", "start:3"] and startup(file_text()) == ("50000", "300000", "100"),
      f"Afterburner wrote a step into [Startup] on exit: overwritten with the known-good one ({ab.log})")
# the slot already holds the profile, but the boot entry does not (the tune's end)
ab.exit_startup = None
pf = ProfileFile(file_text())
pf.set_values("Startup", {"CoreClkBoost": "119000", "MemClkBoost": "0", "PowerLimit": "100"})
put(pf.text())
ab.running = True
ab.log.clear()
ok, _ = ab.write_and_apply(5, quick)
check(ok and ab.log == ["close", "start:5"] and startup(file_text()) == ("119000", "700000", "96"),
      f"slot right, boot entry wrong (live: +119 / +0 / 100 %): rewritten, not only re-sent ({ab.log})")
ok, _ = ab.reset_to_stock(2)
check(ok and startup(file_text()) == ("0", "0", "100") and offsets(file_text(), "Startup") == [0],
      "reset to stock: the PC boots at stock")
put(make_profile(with_p2=True))                      # option off
ok, _ = ab.write_and_apply(5, quick)
check(ok and not AP.startup_enabled(file_text()) and ab.startup_state(5) is None,
      "option off in Afterburner: still off after applying")

# ── 3) the tuner ─────────────────────────────────────────────────────────────
print("tuner: the boot entry during and after a tune")
import core.nvtune_tuner as NT
from core.nvtune_tuner import AutoTuner, StressResult, TunerConfig, TuneMode, TunerState
from core.nvtune_core import ProfileManager
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)
_REAL_RUN = NT.StressTester.run             # the tune tests below replace it


class Card:
    """Core edge +100 (steady), +70 under load changes; reads what the slot holds."""
    def __init__(self):
        self.core = self.mem = 0
        self.pwr = 100
        self.on_run = None

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        if self.on_run:
            self.on_run(mode, self.core)
        r = StressResult(passed=True, avg_temp=60, max_temp=64, avg_voltage_mv=1050, steady_voltage_mv=1050,
                         avg_gpu_usage=99, avg_core_mhz=2800 + self.core, max_core_mhz=2900 + self.core,
                         avg_rate_tflops=40.0, last_voltage_mv=1050)
        if self.core > (70 if mode == "transient" else 100):
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        if mode == "mem":
            r.avg_rate_tflops, r.avg_bw_gbs = 0.0, 700 + 0.05 * self.mem
        return r


class TunerAB(FakeAB):
    def __init__(self, card):
        self.card, self.boots = card, []
        super().__init__()

    def write_and_apply(self, slot, p, startup="same"):
        r = super().write_and_apply(slot, p, startup)
        self.card.core, self.card.mem, self.card.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
        self.boots.append((p.name, _boot()))       # what the PC would boot with now
        return r


def _boot():
    return startup(file_text())


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=55, voltage_mv=1050, core_mhz=2900, gpu_usage=99, power_capped=False,
                                     gpu_power_w=250, throttle_protective=False, throttle="", mem_mhz=10500,
                                     name="NVIDIA GeForce RTX 4080")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


class CR:
    def __init__(self, last):
        self.last, self.saved = last, []
    def load_last_applied(self): return self.last
    def save_last_applied(self, d): self.saved.append(d["name"])
    def set_tuning_active(self, d): pass
    def clear_tuning_flag(self): pass
    def check_tdr_since(self, seconds_back=0): return False
    def __getattr__(self, name):           # the other crash-recovery hooks: nothing to do
        return lambda *a, **k: None


def run_tune(last, abort_at=None, **kw):
    put(boot_on(make_profile(with_p2=True)))
    card = Card()
    ab = TunerAB(card)
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": card.run(d, m, on_tick, mode)
    conf = dict(mode=TuneMode.OC_UV, core_step_mhz=15, core_max_mhz=300, power_min_pct=100, crash_pause_s=0,
                ab_slot=5)
    conf.update(kw)
    tmp = tempfile.mkdtemp(prefix="t_", dir=TMP)
    cr = CR(last)
    t = AutoTuner(Mon(), ab, ProfileManager(os.path.join(tmp, "p")), TunerConfig(**conf), crash_recovery=cr,
                  log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    if abort_at is not None:
        card.on_run = lambda mode, core: t.abort() if core >= abort_at and not t._stop.is_set() else None
    t._run_safe()
    return t, ab, cr, logs


GOOD = good.to_dict()
t, ab, cr, logs = run_tune(GOOD)
during = [b for n, b in ab.boots if n != t.best_profile.name]
check(t.state == TunerState.DONE and during and all(b == ("50000", "300000", "100") for b in during),
      f"every step of the tune: the PC would boot with the known-good profile ({len(during)} writes)")
bp = t.best_profile
check(ab.boots[-1][0] == bp.name and ab.startup_state(5) is True
      and startup(file_text()) == ("1000000", "0", "100") and bp.core_offset_mhz == 37
      and bp.curve_cap_mv > 0 and bp.curve_points == [[bp.curve_cap_mv, bp.curve_points[0][1]]]
      and any("flach ab" in l or "flat from" in l for l in logs),
      f"after the tune: the saved profile is what the PC boots with — round 24: the +37 offset as a curve "
      f"flat from the game test's voltage ({startup(file_text())}, {bp.curve_points})")
check(cr.saved == [t.best_profile.name], "and it is recorded as the last applied profile")

t, ab, cr, logs = run_tune(None)
during = [b for n, b in ab.boots if n != t.best_profile.name]
check(all(b == ("0", "0", "100") for b in during), "no profile applied before: stock at boot while tuning")

t, ab, cr, logs = run_tune(GOOD, abort_at=60)
check(t.state == TunerState.ABORTED and startup(file_text()) == ("50000", "300000", "100")
      and offsets(file_text(), "Profile5") == [0],
      f"aborted: the slot back to stock, the PC boots with the known-good profile ({startup(file_text())})")

# the GPU tab says after applying whether the PC boots with it
import ui.tab_gpu as TG
put(boot_on(make_profile(with_p2=True)))
fake_tab = types.SimpleNamespace(ab=FakeAB())
fake_tab.ab.write_and_apply(4, quick)
note_on = TG.GpuTunerTab._boot_note(fake_tab, 4)
pf = ProfileFile(file_text())
pf.set_values("Startup", {"MemClkBoost": "0"})
put(pf.text())
note_other = TG.GpuTunerTab._boot_note(fake_tab, 4)
put(make_profile(with_p2=True))
fake_tab.ab.write_and_apply(4, quick)
note_off = TG.GpuTunerTab._boot_note(fake_tab, 4)
check("auch beim Windows-Start" in note_on and "noch etwas anderes" in note_other
      and "Systemstart anwenden" in note_off and TG.GpuTunerTab._boot_note(types.SimpleNamespace(ab=object()), 4) == "",
      f"GPU tab after applying: boots with it / something else / option off: {note_on!r}")

# ── 4) a compute error that comes with GPU errors in the event log ───────────
print("a compute error + GPU errors in the event log (live: 1025 mV, +194, 24 x nvlddmkm 13)")
import subprocess as _sp
from core.nvtune_tuner import StressTester
CRASHER = os.path.join(TMP, "crasher.py")
with open(CRASHER, "w", encoding="utf-8") as f:
    f.write("import sys, time\nfor _ in range(3):\n    print('RATE 1.0', flush=True); time.sleep(0.3)\n"
            "print('ERR 7', flush=True)\nsys.exit(3)\n")


class EvCR:
    def __init__(self, hit):
        self.hit, self.asked = hit, []
    def check_tdr_since(self, seconds_back=0):
        self.asked.append(seconds_back)
        return self.hit


real_time = NT.time
NT.StressTester.run = _REAL_RUN
NT.time = time                                       # this part runs on the real clock
results = {}
for hit in (True, False):
    st = StressTester(Mon(), EvCR(hit))
    st._worker_path = lambda: CRASHER
    st.EVENT_SETTLE_S = 0.2
    t_s = time.time()
    r = st.run(20, 85)
    results[hit] = (r, time.time() - t_s, st.cr.asked)
NT.time = real_time
r, dt, asked = results[True]
check(not r.passed and r.compute_error and r.tdr_detected and "GPU-Fehler im Ereignisprotokoll" in r.abort_reason
      and asked and dt < 10,
      f"compute error + GPU errors logged: counted as a driver-level failure ({r.abort_reason!r})")
r, dt, asked = results[False]
check(not r.passed and r.compute_error and not r.tdr_detected and asked,
      "compute error without GPU errors: the event log was looked at, nothing added")
check(NT.StressTester.EVENT_SETTLE_S == 2.0, "2 s for the event log to catch up after the worker died")

# the last-applied record follows a rename, its time stays (the watchdog counts from it)
from core.crash_recovery import CrashRecovery
crd = os.path.join(TMP, "cr")
os.makedirs(crd)
crr = CrashRecovery(crd)
crr.save_last_applied(TuneProfile(name="GOP_CURVE_BAL_1009_0905", core_offset_mhz=119).to_dict())
p_la = os.path.join(crd, ".last_applied_profile.json")
os.utime(p_la, (1_700_000_000, 1_700_000_000))
check(crr.rename_last_applied("GOP_CURVE_BAL_1009_0905", "Rundum Ausgewogen 09.10.")
      and crr.load_last_applied()["name"] == "Rundum Ausgewogen 09.10."
      and int(os.path.getmtime(p_la)) == 1_700_000_000
      and not crr.rename_last_applied("other", "x"),
      "renaming the applied profile: the record follows, its time (= applied at) stays")

src_t = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check(src_t.count("self._persist(profile)") == 2, "both modes (Quick, Rundum) make the saved profile the boot profile")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
