"""Round 15 — two tuner modes (Rundum + Quick), driver-reset looks without gaps,
Afterburner slots: what they hold, the history knows each run's profile.
Pure logic on fakes: no stress worker, no Afterburner, no event log."""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)


import core.nvtune_tuner as NT
from core.nvtune_tuner import StressTester, TuneMode, TunerState

# ── 1) driver resets: every second of a step is looked at, also its last ones ──
print("driver-reset looks (event log) during a step")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def monotonic(self):
        return self.t


class CR:
    """Fake event log: one reset at `at` (clock time). A look takes `cost` s."""
    def __init__(self, clock, at=None, cost=0.0):
        self.clock, self.at, self.cost, self.looks = clock, at, cost, []

    def check_tdr_since(self, seconds_back=15):
        now = self.clock.t
        self.looks.append((now - seconds_back, now))
        self.clock.t += self.cost                      # the look itself takes a while
        return self.at is not None and now - seconds_back <= self.at <= now


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=55, voltage_mv=1000, core_mhz=2700, gpu_usage=99,
                                     power_capped=False, gpu_power_w=250, throttle_protective=False,
                                     throttle="", mem_mhz=10500)


def step(at=None, cost=0.0, dur=45):
    clock = Clock()
    NT.time = clock
    st = StressTester(Mon(), CR(clock, at, cost))
    st.start = lambda mode="gemm": None               # no worker process
    t0 = clock.t
    r = st.run(dur, 85)
    return r, st.cr.looks, t0, clock.t


def covered(looks, a, b) -> bool:
    """[a, b] lies inside the union of the looked-at windows."""
    x = a
    for lo, hi in sorted(looks):
        if lo > x + 1e-6:
            return False
        x = max(x, hi)
    return x >= b - 1e-6


r, looks, t0, t1 = step()
check(r.passed and not r.tdr_detected, "no reset: the step passes")
check(covered(looks, t0, t1), f"the whole step was looked at, up to its end ({len(looks)} looks)")
r, looks, t0, t1 = step(cost=2.0)
check(covered(looks, t0, t1 - 2.0), "looks that take 2 s each leave no gap (the old '% 10' skipped some)")
r, looks, t0, t1 = step(at=1043.0)                    # 43 s into a 45-s step: after the last 10-s look
check(r.tdr_detected and r.crash_detected and not r.passed and "TDR" in r.abort_reason,
      "a reset in the step's last seconds fails THIS step (was: blamed on the next one)")
r, looks, t0, t1 = step(at=1021.0, cost=1.5)
check(r.tdr_detected and t1 - t0 < 40, "a reset in the middle ends the step at the next look")
r, looks, t0, t1 = step(at=990.0)                     # 10 s before the step: an earlier step's reset
check(not r.tdr_detected, "a reset well before the step is not blamed on it")
NT.time = __import__("time")

# ── 2) two modes ──────────────────────────────────────────────────────────────
print("modes")
check([m.value for m in TuneMode] == ["oc_uv", "curve"], "TuneMode: Quick (OC + UV) and Rundum")
check(not hasattr(TunerState, "STAGE3"), "the V/F-undervolt stage of the never-shown FULL mode is gone")
check(not os.path.exists(os.path.join(ROOT, "core", "vf_curve.py")), "its curve builder module is gone")
cfg = NT.TunerConfig()
check(not any(hasattr(cfg, k) for k in ("vf_enabled", "vf_step_mv", "vf_min_mv", "mem_oc_enabled")),
      "its settings are gone; memory = 'mem_stage' in both modes")
import ui.tab_gpu as TG
check([m[0] for m in TG.MODES] == ["curve", "oc_uv"] and TG.MODES[1][1] == "Schnell (OC + UV)",
      "GPU tab: Rundum first, then Schnell (OC + UV)")
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check("every 50 mV" not in src and "every 25 mV" in src, "Rundum docstring: points every 25 mV")

# ── 3) Afterburner slots: what each one holds ────────────────────────────────
print("Afterburner slots")
from core.ab_profile import ProfileFile, slot_summary
TEXT = """[Startup]
Format=2
PowerLimit=100
[Profile1]
Format=2
PowerLimit=100
CoreClkBoost=0
MemClkBoost=0
[Profile2]
Format=2
PowerLimit=100
CoreClkBoost=1000000
MemClkBoost=1000000
[Profile3]
Format=2
PowerLimit=96
CoreClkBoost=-50500
MemClkBoost=500000
"""
pf = ProfileFile(TEXT)
s = {i: slot_summary(pf, i) for i in range(1, 6)}
check(s[1] == "Core +0 · Speicher +0 · Power 100 %", f"slot 1: {s[1]}")
check(s[2] == "Kurve · Speicher +1000 · Power 100 %", f"slot 2 (own curve): {s[2]}")
check(s[3] == "Core -50 · Speicher +500 · Power 96 %", f"slot 3 (negative offset rounds right): {s[3]}")
check(s[4] == s[5] == "leer" and slot_summary(pf, 4, de=False) == "empty", "slots 4/5: empty")
check(slot_summary(ProfileFile("[Profile1]\nFormat=2\n"), 1) == "belegt", "a slot without values: 'belegt'")

from core.nvtune_core import AfterburnerController
tmp = tempfile.mkdtemp(prefix="gop_r15_")
cfgfile = os.path.join(tmp, "VEN_10DE&DEV_2704.cfg")
with open(cfgfile, "w", encoding="utf-8") as f:
    f.write(TEXT)
before = open(cfgfile, "rb").read()


class AB(AfterburnerController):
    def _detect(self):
        self.exe, self.profile_dir = r"C:\fake\MSIAfterburner.exe", tmp

    def find_gpu_profile(self):
        return cfgfile, ""


ab = AB()
check(ab.slot_summaries()[2] == "Kurve · Speicher +1000 · Power 100 %" and len(ab.slot_summaries()) == 5,
      "AfterburnerController.slot_summaries reads all five slots")
check(open(cfgfile, "rb").read() == before, "... read-only (the file is unchanged)")


class NoFile(AB):
    def find_gpu_profile(self):
        return None, "kein Profil"


check(NoFile().slot_summaries() == {}, "no profile file: {} (the menu then shows '?')")

# ── 4) the history knows each run's saved profile ─────────────────────────────
print("history -> profile")
from core.tune_history import TuneHistory
with open(os.path.join(tmp, "tune_20261002_154619.log"), "w", encoding="utf-8") as f:
    f.write("2026-10-02 15:46:19,000 [INFO]   GameOptimizerPro Auto-Tune [CURVE]\n"
            "2026-10-02 16:50:00,000 [INFO] Profile saved: GOP_CURVE_BAL_1002_1650\n"
            "2026-10-02 16:50:00,000 [INFO]   Core offset:  +164MHz (Kurve, oberster Punkt)\n")
with open(os.path.join(tmp, "tune_20261002_120000.log"), "w", encoding="utf-8") as f:
    f.write("2026-10-02 12:00:00,000 [INFO]   GameOptimizerPro Auto-Tune [OC UV]\n"
            "2026-10-02 12:05:00,000 [WARNING] Abbruch angefordert — GPU wird auf Standard zurückgesetzt …\n")
runs = {r.filename: r for r in TuneHistory(tmp).get_runs()}
check(runs["tune_20261002_154619.log"].profile_name == "GOP_CURVE_BAL_1002_1650", "finished run: its profile")
check(runs["tune_20261002_120000.log"].profile_name == "" and runs["tune_20261002_120000.log"].mode == "OC+UV",
      "stopped run: no profile; the Quick mode is shown as OC+UV")

# ── 5) profiles: only real ones in the lists, renaming ───────────────────────
print("profiles: only real ones, renaming")
import json
from core.nvtune_core import ProfileManager, TuneProfile
pdir = os.path.join(tmp, "profiles")
pm = ProfileManager(pdir)
pm.save(TuneProfile(name="GOP_CURVE_BAL_1002_1628", core_offset_mhz=134, mem_offset_mhz=1000))
pm.save(TuneProfile(name="Alt", core_offset_mhz=100))
with open(os.path.join(pdir, "language.json"), "w", encoding="utf-8") as f:
    json.dump({"lang": "de"}, f)                       # what core/i18n writes there
with open(os.path.join(pdir, "game_profiles.json"), "w", encoding="utf-8") as f:
    json.dump({"Hunt": {"exe": "hunt.exe"}}, f)       # left over from the removed games page
names = sorted(p.name for p in pm.list_all())
check(names == ["Alt", "GOP_CURVE_BAL_1002_1628"],
      f"language.json / game_profiles.json are not profiles (they showed up as 'Default'): {names}")
check(pm.load("language") is None, "... and load() doesn't turn them into one either")
ok, err = pm.rename("GOP_CURVE_BAL_1002_1628", "Rundum heute")
check(ok and pm.load("Rundum heute").core_offset_mhz == 134
      and not os.path.exists(os.path.join(pdir, "GOP_CURVE_BAL_1002_1628.json")),
      "renamed: saved under the new name, the old file is gone")
check(pm.load("GOP_CURVE_BAL_1002_1628").name == "Rundum heute",
      "the old name (the tune history knows the run by it) still finds the profile")
ok, err = pm.rename("Alt", "Rundum heute")
check(not ok and err and pm.load("Alt") is not None, f"a name that exists is refused, nothing lost: {err!r}")
ok, err = pm.rename("Rundum heute", "Rundum 2")
check(ok and pm.load("GOP_CURVE_BAL_1002_1628").name == "Rundum 2" and pm.load("Rundum heute").name == "Rundum 2",
      "renamed twice: both earlier names still find it")
ok, err = pm.rename("Rundum 2", "GOP_CURVE_BAL_1002_1628")
check(ok and pm.load("GOP_CURVE_BAL_1002_1628").name == "GOP_CURVE_BAL_1002_1628"
      and pm.load("Rundum 2").name == "GOP_CURVE_BAL_1002_1628", "back to the first name: no loop")
ok, err = pm.rename("Alt", "ALT")
check(ok and [p.name for p in pm.list_all()].count("ALT") == 1 and pm.load("Alt").name == "ALT",
      "only the case changed (the same file on Windows): renamed, not 'already exists'")
check(not pm.rename("ALT", "__tray_default__")[0] and not pm.rename("ALT", "  ")[0]
      and not pm.rename("nope", "x")[0], "reserved / empty names and unknown profiles are refused")
check(not any(f.endswith(".json") and "renamed" in f for f in os.listdir(pdir)),
      "the rename map is no *.json (never read as a profile)")
pm.delete("GOP_CURVE_BAL_1002_1628")
check(pm.load("Rundum 2") is None and pm.load("Rundum heute") is None,
      "deleted: its old names lead nowhere any more")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
