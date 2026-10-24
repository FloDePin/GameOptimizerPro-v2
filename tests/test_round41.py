"""Round 41 — from the 3DMark comparison of 24.10.: under full load the card runs into its power
limit, where the curve profiles drew what stock drew (313-315 W vs 316 W) and only Quick's 95 %
saved power (299 W at +1.3 %). Efficiency gets a power limit stage: the lowest limit at which the
curve still does stock's work under the compute load. Pure logic, no GPU."""
import os
import sys
import tempfile
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


TMP = tempfile.mkdtemp(prefix="gop_r41_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._current_lang = "de"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"
from core.nvtune_tuner import AutoTuner, StressResult, TunerConfig  # noqa: E402


class Card:
    """Stock does 100 under the compute load; the curve does 102.4 at 100 % and loses 0.7 per % of
    power limit below it (the live card: −3.6 % at 94 % for Quick's offset)."""
    def __init__(self):
        self.mode, self.pwr, self.runs = "stock", 100, []

    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        rate = 100.0 if self.mode == "stock" else 102.4 - 0.7 * (100 - self.pwr)
        self.runs.append((self.mode, self.pwr))
        return StressResult(passed=True, avg_rate_tflops=rate)


def tuner(card, **cfg):
    t = AutoTuner(types.SimpleNamespace(read=lambda: None), types.SimpleNamespace(), None,
                  TunerConfig(step_test_s=1, **cfg), log_dir=os.path.join(TMP, "l"))
    t._log_lines = []
    t.on_log(lambda m, lvl: t._log_lines.append(m))
    t._apply = lambda core=0, mem=0, pwr_pct=100: (setattr(card, "mode", "stock"), setattr(card, "pwr", pwr_pct))
    t._apply_curve = lambda a, cap=0, mem=0, pwr_pct=100: (setattr(card, "mode", "curve"),
                                                           setattr(card, "pwr", pwr_pct))
    return t


print("power limit stage for efficiency")
import time as _time  # noqa: E402
_sleep = _time.sleep
_time.sleep = lambda s: None
try:
    c = Card()
    t = tuner(c)
    got = t._curve_power_stage(types.SimpleNamespace(run=c.run), [(1000, 2727)], 1025, 500)
    tried = [p for m, p in c.runs if m == "curve"]
    check(got == 96 and c.runs[0] == ("stock", 100) and c.mode == "curve" and c.pwr == 96,
          f"stock measured first, the curve at 100 %, then 95 ✗ (98.9 < 99) → 98 ✓ → 96 ✓; 94/95 not tried again: "
          f"{got} %, steps {tried}")
    check(tried == [100, 95, 98, 96], "5-% steps, halved on a miss; nothing at or below a limit that fell short")
    check(any("→ Power-Limit 96 %" in m for m in t._log_lines)
          and any("96 %: +0,0 %" in m.replace(".", ",") or "96 %: -0" in m or "96 %: +0" in m for m in t._log_lines),
          "the log names each step against stock and the result")

    class Weak(Card):
        def run(self, d, max_temp, on_tick=None, mode="gemm"):       # the curve gains nothing under full load
            r = super().run(d, max_temp, on_tick, mode)
            if self.mode == "curve":
                r.avg_rate_tflops -= 2.4
            return r

    w = Weak()
    check(tuner(w)._curve_power_stage(types.SimpleNamespace(run=w.run), [], 0, 0) == 99,
          "a curve that gains nothing under full load: only what keeps 99 % of stock (99 %)")

    class NoRate(Card):
        def run(self, d, max_temp, on_tick=None, mode="gemm"):
            return StressResult(passed=True, avg_rate_tflops=0.0)

    class Slow(Card):
        def run(self, d, max_temp, on_tick=None, mode="gemm"):       # deeply capped: below 99 % already at 100 %
            r = super().run(d, max_temp, on_tick, mode)
            if self.mode == "curve":
                r.avg_rate_tflops -= 4.0
            return r

    sl = Slow()
    t = tuner(sl)
    check(t._curve_power_stage(types.SimpleNamespace(run=sl.run), [], 0, 0) == 100
          and [p for m, p in sl.runs if m == "curve"] == [100] and any("schon da unter 99 %" in m for m in t._log_lines),
          "audit 24.10.: a curve below 99 % of stock already at 100 % — one run, no pointless 95/98/99 steps")

    n = NoRate()
    t = tuner(n)
    check(t._curve_power_stage(types.SimpleNamespace(run=n.run), [], 0, 0) == 100
          and any("Power-Limit bleibt 100 %" in m for m in t._log_lines),
          "no compute rate measured (CPU fallback): nothing changed, said so")
    f = Card()
    got = tuner(f, curve_power_min_pct=97)._curve_power_stage(types.SimpleNamespace(run=f.run), [], 0, 0)
    check(got == 97 and min(p for m, p in f.runs if m == "curve") >= 97, f"never below the floor (97 %): {got}")
    s = Card()
    t = tuner(s)
    t._stop.set()
    check(t._curve_power_stage(types.SimpleNamespace(run=s.run), [], 0, 0) is None, "aborted: None")
finally:
    _time.sleep = _sleep

check(TunerConfig().curve_power_stage and TunerConfig().curve_power_min_pct == 80
      and TunerConfig().curve_power_keep == 0.99, "on by default, down to 80 %, 99 % of stock's work")
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check('if goal == "efficiency" and cfg.curve_power_stage and pwr == 100:' in src
      and src.index("# Efficiency: the power limit — after the final tests") < src.rindex('after = self._bench(stress, cfg.bench_s'),
      "only the efficiency goal runs it (max and balanced keep their power limit)")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
