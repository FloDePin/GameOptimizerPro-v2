"""Round 18 — profiles compared by what they do against stock: performance and
efficiency from the same benchmark (core/profile_score.py), stored by both tune
modes (TuneProfile.bench), read from older All-round profiles' notes.
No real GPU load: a scripted card and a fake FurMark."""
import os
import shutil
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r18_")
from core import app_settings
from pathlib import Path
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the app's own file
import core.i18n as I18N
I18N._current_lang = "de"
from core import profile_score as PS
from core.nvtune_core import ProfileManager, TuneProfile

# ── 1) the numbers ───────────────────────────────────────────────────────────
print("performance and efficiency against stock")
old = TuneProfile(name="GOP_CURVE_BAL_1009_0905",
                  notes="[Rundum Ausgewogen] Kurve 7 Punkte 925–1075 mV, flach ab 1050 mV | Mem+500MHz | Pwr 100% "
                        "| FurMark 7295→7446 (+2.1 %) | 252→257 W | MaxTemp 65°C | Score 100/100")
s = PS.score_of(old)
check(s and s["perf_pct"] == 2.1 and s["eff_pct"] == 0.1 and s["power_w"] == 257 and s["stock_power_w"] == 252
      and s["label"] == "FurMark 60 s" and s["source"] == "notes",
      f"an older All-round profile: read from its notes: {s}")
quick = TuneProfile(name="GOP_OC+UV_1004_1342", bench=PS.bench_record(
    "FurMark", 300, 37522, 266.1, 7295, 252, stock_seconds=60))
s = PS.score_of(quick)
check(s and s["perf_pct"] == 2.9 and s["eff_pct"] == -2.6 and s["label"] == "FurMark 5 min" and s["source"] == "measured",
      f"a 5-min run against a 60-s stock run: compared per second: {s}")
check(PS.score_of(TuneProfile(name="P1", core_offset_mhz=120)) is None
      and PS.score_of(TuneProfile(name="x", bench={"score": 0})) is None
      and PS.score_of(TuneProfile(name="y", notes="[Entschärft aus …] Kurve −30 MHz")) is None,
      "never measured (or nothing usable): no score, not a made-up one")
pm = ProfileManager(os.path.join(TMP, "p"))
pm.save(quick)
check(pm.load("GOP_OC+UV_1004_1342").bench == quick.bench, "stored with the profile and loaded back")
check(TuneProfile.from_dict({"name": "alt", "core_offset_mhz": 1}).bench == {}, "profiles from before: empty bench")

# ── 2) the Quick mode measures it (FurMark 2 set up) ─────────────────────────
print("Quick mode: 60 s FurMark at stock and at the end")
import core.nvtune_tuner as NT
from core import furmark as FMOD
from core.nvtune_tuner import AutoTuner, StressResult, TunerConfig, TuneMode, TunerState
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class Card:
    def __init__(self):
        self.core = self.mem = 0
        self.pwr = 100
        self.bench = []

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        r = StressResult(passed=True, avg_temp=60, max_temp=64, avg_voltage_mv=1050, steady_voltage_mv=1050,
                         avg_gpu_usage=99, avg_core_mhz=2800 + self.core, max_core_mhz=2900 + self.core,
                         avg_rate_tflops=40.0, last_voltage_mv=1050)
        if self.core > (70 if mode == "transient" else 100):
            r.passed, r.crash_detected, r.compute_error = False, True, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r

    def furmark(self, path, seconds, width=1920, height=1080, msaa=8, demo="furmark-gl", stop_event=None,
                on_tick=None, focus=False):
        for el in range(0, int(seconds), 10):
            if on_tick:
                on_tick(float(el))
        self.bench.append((self.core, self.pwr))
        return {"ok": True, "score": int(7295 * (1 + self.core / 2800)), "max_temp": 62,
                "duration_ms": int(seconds * 1000), "fps_avg": 120, "elapsed_s": seconds}


class AB:
    available = True
    def __init__(self, card): self.card = card
    def write_and_apply(self, slot, p, startup="same"):
        self.card.core, self.card.mem, self.card.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
        return True, ""


class Mon:
    def __init__(self, card): self.card = card
    def read(self):
        return types.SimpleNamespace(temp=60, voltage_mv=1050, core_mhz=2800 + self.card.core, gpu_usage=99,
                                     power_capped=False, gpu_power_w=252 + self.card.core * 0.05,
                                     throttle_protective=False, throttle="", mem_mhz=10500,
                                     name="NVIDIA GeForce RTX 4080")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


def quick_tune(furmark_path):
    card = Card()
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": card.run(d, m, on_tick, mode)
    FMOD.run_benchmark = card.furmark
    tmp = tempfile.mkdtemp(prefix="q_", dir=TMP)
    t = AutoTuner(Mon(card), AB(card), ProfileManager(os.path.join(tmp, "p")),
                  TunerConfig(mode=TuneMode.OC_UV, core_step_mhz=15, core_max_mhz=300, power_min_pct=100,
                              crash_pause_s=0, furmark_path=furmark_path), log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    return t, card, logs


t, card, logs = quick_tune("C:/FurMark2/furmark.exe")
L = "\n".join(logs)
bp = t.best_profile
s = PS.score_of(bp) if bp else None
check(t.state == TunerState.DONE and card.bench == [(0, 100), (bp.core_offset_mhz, 100)],
      f"stock first, the result at the end — the same 60-s FurMark: {card.bench}")
check(bp.bench and bp.bench["stock_score"] == 7295 and bp.bench["seconds"] == 60 and s and s["perf_pct"] > 0
      and "Vorher → nachher (FurMark 60 s): 7295 →" in L and "Effizienz" in L,
      f"stored with the profile, logged: {s}")
t, card, logs = quick_tune("")
check(t.state == TunerState.DONE and card.bench == [] and t.best_profile.bench == {},
      "without FurMark 2: no benchmark, no score (nothing made up)")

# ── 3) the GPU tab passes FurMark to the Quick mode also without the memory stage ──
src = open(os.path.join(ROOT, "ui", "tab_gpu.py"), encoding="utf-8").read()
check("fm = self._furmark_v2()           # memory steps + the comparison with stock" in src
      and "Vergleich mit Standard: je 60 s FurMark" in src,
      "Quick mode: FurMark for the comparison even with memory off; the dialog says so")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
