"""Round 10 — findings from the first real use: either-or tweaks (power plan /
DNS), runner supersede + legacy clean-up + one batch at a time, power-plan
scripts, final-test back-off in the tuner, console-less start, keep-awake,
24-h rule of the temp cleaner, optimizer UI (select all, toggling, mouse wheel
over the rows, batch lock, 'einmalig' badge). Nothing on the real system is
changed: PowerShell is faked wherever a tweak would run."""
import json, os, sys, tempfile, threading, time, types, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

# ── 1) either-or groups ──────────────────────────────────────────────────────
print("either-or groups")
from core.tweaks import EXCLUSIVE_GROUPS, alternatives_of, resolve_selection, get_by_id, ALL_TWEAKS
check(all(get_by_id(t) for g in EXCLUSIVE_GROUPS for t in g), "every either-or id is a real tweak")
check(alternatives_of("dns_google") == ["dns_cloudflare"], "DNS: Google <-> Cloudflare")
check(set(alternatives_of("power_high")) == {"ultimate_performance", "power_balanced"}, "power plans")
check(alternatives_of("disable_telemetry") == [], "normal tweak has no alternatives")
ids = ["power_balanced", "dns_google", "ultimate_performance", "power_high", "dns_cloudflare", "disable_telemetry"]
check(resolve_selection(ids) == ["ultimate_performance", "dns_cloudflare", "disable_telemetry"],
      f"select all -> the presets' choice (Ultimate, Cloudflare): {resolve_selection(ids)}")
check(resolve_selection(ids, applied={"power_high", "dns_google"}) == ["dns_google", "power_high", "disable_telemetry"],
      "an already applied choice is kept")
from core.tweak_presets import get_all_safe_ids, get_preset
safe = get_all_safe_ids()
check("ultimate_performance" in safe and "dns_cloudflare" in safe and
      not {"power_high", "power_balanced", "dns_google"} & set(safe), "'All Safe' has no contradicting choices")
check(get_preset("all_safe").tweak_ids == safe, "preset object uses the same list")

# ── 2) power-plan scripts ────────────────────────────────────────────────────
print("power-plan scripts")
ult = get_by_id("ultimate_performance").ps_command
check("if($ult.Count -eq 0)" in ult and ult.count("duplicatescheme") == 1,
      "Ultimate is only duplicated when no copy exists (15 copies found on the test PC)")
check("powercfg -delete $g" in ult and "if($g -ne $keep)" in ult, "extra copies are removed, never the active one")
for tid in ("ultimate_performance", "power_high"):
    c = get_by_id(tid).ps_command
    check(all(x in c for x in ("VIDEOIDLE 0", "STANDBYIDLE 0", "HIBERNATEIDLE 0")) and "SETDCVALUEINDEX" not in c,
          f"{tid}: screen / standby / hibernate 'never' on mains power only (battery untouched)")
disp = get_by_id("power_display_sleep_15")
check("Ultimat" in disp.ps_command and "8c5e7fda" in disp.ps_command and "continue" in disp.ps_command,
      "'Display 15 min' skips the high-performance plans")
check("Ultimat" in disp.revert_cmd, "... its revert too")
from core.tweak_verifier import VERIFY_MAP
check("VIDEOIDLE" in VERIFY_MAP["ultimate_performance"] and "STANDBYIDLE" in VERIFY_MAP["power_high"],
      "plan checks include 'screen/standby never' (old copies -> drift -> re-apply once)")
check("381b4222" in VERIFY_MAP["power_display_sleep_15"], "display check reads 'Ausbalanciert'")
nic = get_by_id("nic_power_saving")
check(r"'^\d{4}$'" in nic.ps_command and "exit 0" in nic.ps_command,
      "NIC power saving: only numbered adapter keys (the locked 'Properties' key made it 'fail')")
rss = get_by_id("enable_rss")
check("Get-NetAdapterRss" in rss.ps_command and "exit 1" in rss.ps_command and "$msg" in rss.ps_command,
      "RSS: only adapters that offer it, reasons in the log")
mc = get_by_id("disable_memory_compression")
check("SysMain" in mc.ps_command and "Set-Service SysMain -StartupType Disabled" in mc.ps_command,
      "memory compression: SysMain started briefly and disabled again")

# ── 3) runner ────────────────────────────────────────────────────────────────
print("tweak runner")
from core.tweak_runner import TweakRunner
tmp = tempfile.mkdtemp(prefix="gop_r10_")
json.dump({"dns_cloudflare": "2026-09-30T10:09:25", "dns_google": "2026-09-30T10:09:26",
           "ultimate_performance": "2026-09-30T10:09:20", "power_high": "2026-09-29T10:00:00",
           "disable_telemetry": "2026-09-30T10:09:18"},
          open(os.path.join(tmp, "applied_tweaks.json"), "w"))
r = TweakRunner(log_dir=tmp)
check(sorted(r.normalized) == ["dns_cloudflare", "power_high"],
      f"legacy state: the older of each either-or pair dropped ({r.normalized})")
check(set(r._applied) == {"dns_google", "ultimate_performance", "disable_telemetry"}, "the newest one stays")
check(json.load(open(os.path.join(tmp, "applied_tweaks.json"))) == r._applied, "cleaned state saved")
calls = []
r._run_ps = lambda cmd, timeout=60: (calls.append(cmd), (True, "ok"))[1]
ok, _ = r.apply(get_by_id("dns_cloudflare"))
check(ok and r.last_superseded == ["dns_google"] and "dns_google" not in r._applied
      and "dns_cloudflare" in r._applied, "applying Cloudflare replaces Google")
r.apply(get_by_id("disable_advertising_id"))
check(r.last_superseded == [], "a normal tweak replaces nothing")
r._run_ps = lambda cmd, timeout=60: (False, "boom")
ok, _ = r.apply(get_by_id("power_high"))
check(not ok and "ultimate_performance" in r._applied and r.last_superseded == [],
      "a FAILED apply replaces nothing")
r._run_ps = lambda cmd, timeout=60: (time.sleep(0.001), (True, "ok"))[1]
ts = [threading.Thread(target=r.apply, args=(t,)) for t in ALL_TWEAKS[:30]]
[t.start() for t in ts]; [t.join() for t in ts]
st = json.load(open(os.path.join(tmp, "applied_tweaks.json")))
check(all(t.id in st for t in ALL_TWEAKS[:30]), "30 parallel applies: state file complete and valid")
r._applied["dns_google"] = "2026-09-30T10:09:26"
r._applied.pop("dns_cloudflare", None)
r.adopt("dns_google", "dns_cloudflare")
check("dns_cloudflare" in r._applied and "dns_google" not in r._applied, "adopt(): the active choice is taken over")

print("drift vs. a choice changed outside the app")
from core import optimization_score as osc
from core.tweak_verifier import VerifyResult
class FV:
    def __init__(self, active): self.active = set(active); self.asked = []
    def verify_all(self, ids, exp):
        self.asked.append(list(ids))
        return {i: VerifyResult(i, True, i in self.active, False, "") for i in ids}
class HW2:
    is_nvidia, is_amd_gpu, has_nvme = True, False, True
fv = FV(active={"dns_cloudflare", "disable_telemetry"})
drifted, switched = osc.check_applied(["dns_google", "ultimate_performance", "disable_telemetry"], HW2(), fv)
check(switched == [("dns_google", "dns_cloudflare")],
      f"DNS changed by hand -> 'switched', not drift: {switched}")
check(drifted == ["ultimate_performance"], f"a plan with no active alternative is real drift: {drifted}")
check("dns_cloudflare" in fv.asked[0] and "power_high" in fv.asked[0], "alternatives are checked too")
check(osc.find_drift(["dns_google"], HW2(), FV(active={"dns_cloudflare"})) == [],
      "find_drift never offers to switch a choice back")
import ui.main_window as mw
class FakeOpt:
    def __init__(self):
        import tkinter as _tk
        self._root = _tk.Tk(); self._root.withdraw()
        self._vars = {"dns_google": _tk.BooleanVar(value=True), "dns_cloudflare": _tk.BooleanVar(value=False)}
        self._bulk = False
fo = FakeOpt()
fake = types.SimpleNamespace(runner=r, _tab_frames={"optimizer": fo}, set_status=lambda s: STAT.append(s))
STAT = []
r._applied["dns_google"] = "x"; r._applied.pop("dns_cloudflare", None)
mw.GameOptimizerWindow._adopt_switched(fake, [("dns_google", "dns_cloudflare")])
check("dns_cloudflare" in r._applied and fo._vars["dns_cloudflare"].get() and not fo._vars["dns_google"].get()
      and STAT and "Cloudflare" in STAT[-1], "main window: taken over quietly, list + status updated")
fo._root.destroy()
ok, out = TweakRunner._run_ps("Write-Output 'Größe: Löschen'")
check(ok and "Größe: Löschen" in out, f"PowerShell output decoded correctly (umlauts): {out!r}")
shutil.rmtree(tmp, ignore_errors=True)

# ── 4) tuner: failed final test -> step back and test again ──────────────────
print("tuner final test")
import core.nvtune_tuner as NT
import core.i18n as I18N
_lang_before = I18N._current_lang
I18N._current_lang = "de"          # the tuner logs in the app's language; these checks read German
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState, StressResult
NT.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time, monotonic=time.monotonic)


class GPU:
    """Steps (45 s) pass up to +175 MHz; the 120-s final test needs <= limit."""
    def __init__(self, final_limit=160, mem_limit=10_000, never=False):
        self.core = self.mem = 0; self.pwr = 100
        self.final_limit, self.mem_limit, self.never = final_limit, mem_limit, never
        self.finals = []
    def apply(self, p):
        self.core, self.mem, self.pwr = p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct
    def run(self, d, max_temp, on_tick=None, mode="gemm"):
        r = StressResult(passed=True, avg_temp=65, max_temp=68, avg_voltage_mv=1000,
                         avg_gpu_usage=99, power_capped_pct=100.0)
        r.avg_core_mhz = 2700 + self.core
        r.avg_rate_tflops = 40.0
        final = d == 120
        if final:
            self.finals.append((self.core, self.mem, self.pwr))
        bad = (self.core > 175 or (final and (self.never or self.core > self.final_limit
                                              or self.mem > self.mem_limit)))
        if bad:
            r.passed, r.compute_error = False, True
            r.abort_reason = "Rechenfehler unter Last (GPU instabil)"
        return r


class AB:
    available = True
    def __init__(self, g): self.g = g; self.log = []
    def write_and_apply(self, slot, p, startup="same"):
        self.log.append((p.name, p.core_offset_mhz, p.mem_offset_mhz, p.power_limit_pct))
        self.g.apply(p); return True, ""


class Mon:
    def read(self):
        return types.SimpleNamespace(name="NVIDIA GeForce RTX 4080", temp=50, voltage_mv=1000,
                                     core_mhz=2700, gpu_power_w=250, gpu_usage=99, throttle="None")
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


def tune(gpu, **cfg):
    NT.StressTester.run = lambda self, d, m, on_tick=None, mode="gemm": gpu.run(d, m, on_tick, mode)
    tmp = tempfile.mkdtemp(prefix="gop_r10t_")
    ab = AB(gpu)
    pm = NT.ProfileManager(os.path.join(tmp, "p"))
    t = AutoTuner(Mon(), ab, pm, TunerConfig(mode=TuneMode.OC_UV, core_step_mhz=15, core_max_mhz=300, game_test=False, core_safety_mhz=0, mem_safety_mhz=0,
                                             power_min_pct=100, **cfg), log_dir=os.path.join(tmp, "l"))
    logs = []
    t.on_log(lambda m, l: logs.append(m))
    t._run_safe()
    saved = pm.load_all() if hasattr(pm, "load_all") else None
    shutil.rmtree(tmp, ignore_errors=True)
    return t, logs, ab, saved


# Stage 1 (steps unstable above +175): +165 ok, +180 x -> 7 MHz: +172 ok, +179 x -> 5: +177 x -> +172
g = GPU(final_limit=160)
t, logs, ab, saved = tune(g)
bp = t.best_profile
check([c for c, m, p in g.finals] == [172, 157], f"final at +172 fails -> back to +157 -> passes: {g.finals}")
check(t.state == TunerState.DONE and bp and bp.core_offset_mhz == 157 and bp.is_stable,
      f"saved profile = the one that PASSED (+{bp.core_offset_mhz if bp else None})")
check(any("Endtest bestanden nach 1 Rücknahme" in m for m in logs) and "Rücknahme" in (bp.notes if bp else ""),
      "log + profile notes say it was backed off")
check(not any("Conservative" in m or "conservative" in m for m in logs), "no untested 'conservative' profile any more")

g = GPU(final_limit=160, mem_limit=900)
t, logs, ab, saved = tune(g, mem_offset_mhz=1000)
check([(c, m) for c, m, p in g.finals] == [(172, 1000), (157, 1000), (157, 900)],
      f"with a memory offset: core first, then memory one 100-MHz step back (was: halved): {g.finals}")
check(t.best_profile and t.best_profile.mem_offset_mhz == 900 and t.best_profile.core_offset_mhz == 157,
      "saved: +157 core / +900 memory (what passed)")

g = GPU(never=True)
t, logs, ab, saved = tune(g)
check(len(g.finals) == 1 + NT.AutoTuner.FINAL_RETRIES, f"gives up after {NT.AutoTuner.FINAL_RETRIES} step-backs")
check(t.state == TunerState.ERROR and t.best_profile is None, "nothing saved when no final test passed")
check(ab.log[-1][0] == "__reset__" and ab.log[-1][1:4] == (0, 0, 100), f"GPU back to stock: {ab.log[-1]}")
check(any("KEIN Profil gespeichert" in m for m in logs), "clear message")

b = NT.AutoTuner._final_backoff
cfg = TunerConfig(core_step_mhz=15, power_step_pct=5, power_min_pct=65, max_temp_c=85)
hot = StressResult(passed=False, max_temp=86, throttle_hit=True)
err = StressResult(passed=False, compute_error=True)
check(b(cfg, hot, 1, 100, 0, 90)[2] == 85, "thermal failure -> power limit -5 % first")
check(b(cfg, err, 1, 100, 0, 100)[0] == 85, "instability -> core offset one step back")
check(b(cfg, err, 2, 100, 500, 100)[1] == 400, "... alternating with the memory offset")
check(b(cfg, err, 1, 0, 0, 100) is None, "stock settings failing: nothing left to take back")
check(b(cfg, err, 1, 0, 0, 90)[2] == 95, "power limit only: power limit back up")

I18N._current_lang = _lang_before

# ── 5) start without console, keep awake, 24-h temp rule ───────────────────
print("launch / power / cleaner")
from core.app_launch import gui_python, owns_console
w = gui_python()
check(os.path.basename(w).lower() == "pythonw.exe" and os.path.exists(w), f"pythonw found: {w}")
check(owns_console() is False, "a process started from a terminal does not 'own' its console")
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check('"runas", gui_python()' in src and "python = gui_python()" in src, "admin relaunch + language restart use pythonw")
check("if owns_console():" in src and "NO_ADMIN_PROMPT" in src, "double-click start continues windowless, asks once")
from core.power_state import keep_awake
check(keep_awake(True) and keep_awake(False), "SetThreadExecutionState accepted")
tsrc = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check("keep_awake(True)" in tsrc and "keep_awake(False)" in tsrc, "tuner keeps the PC awake")
import core.system_cleaner as sc
d = tempfile.mkdtemp(prefix="gop_r10c_")
tdir = os.path.join(d, "Temp"); os.makedirs(tdir)
fresh = os.path.join(tdir, "fresh.tmp"); old = os.path.join(tdir, "old.tmp")
open(fresh, "w").write("x"); open(old, "w").write("x")
past = time.time() - 3 * 86400
os.utime(old, (past, past))
t = sc.CleanTarget("Benutzer-Temp", tdir, exists=True, min_age_h=24)
names = [f for _r, f in sc._files(t)]
# creation time of 'old' is now (it was just written) -> it is NOT old: the rule uses the newest time
check(names == [], f"a file created now counts as new even with an old mtime: {names}")
_real_time = sc.time.time
sc.time.time = lambda: _real_time() + 3 * 86400          # two days later ...
names = sorted(f for _r, f in sc._files(t))
sc.time.time = _real_time
check(names == ["fresh.tmp", "old.tmp"], f"... both are old enough and get cleaned: {names}")
check(all(x.min_age_h == 24 for x in sc.get_targets()), "standard temp targets: 24 h")
check(all(x.min_age_h == 0 for x in sc.get_deep_targets(list(sc.DEEP_GROUPS))), "deep-clean caches: no age rule")
shutil.rmtree(d, ignore_errors=True)

# ── 6) optimizer UI (real mainloop, invisible) ───────────────────────────────
print("optimizer UI")
import tkinter as tk
from tkinter import messagebox
BOXES = []
messagebox.showinfo = lambda *a, **k: BOXES.append(a)
messagebox.askyesno = lambda *a, **k: True
from core.tweak_verifier import TweakVerifier
TweakVerifier.verify_all = lambda self, ids, exp: {}
from core.hardware import HardwareInfo
hw = HardwareInfo(); hw.is_nvidia = True; hw.has_nvme = True
tmp = tempfile.mkdtemp(prefix="gop_r10u_")
json.dump({"dns_google": "2026-09-30T10:09:26"}, open(os.path.join(tmp, "applied_tweaks.json"), "w"))
runner = TweakRunner(log_dir=tmp)
runner.backup_registry = lambda label: None
APPLIED = []
def slow_ps(cmd, timeout=60):
    APPLIED.append(cmd); time.sleep(0.05); return True, "ok"
runner._run_ps = slow_ps

root = tk.Tk(); root.geometry("1100x800"); root.attributes("-alpha", 0.0)
from ui.tab_optimizer import OptimizerTab
opt = OptimizerTab(root, runner, hw, profiles_dir=os.path.join(tmp, "p"), logs_dir=tmp)
opt.pack(fill="both", expand=True)
STEPS = []
def step(ms):
    def deco(fn): STEPS.append((ms, fn)); return fn
    return deco

@step(400)
def s1():
    v = opt._vars
    opt._select_all()
    plans = [t for t in ("ultimate_performance", "power_high", "power_balanced") if v[t].get()]
    dns = [t for t in ("dns_cloudflare", "dns_google") if v[t].get()]
    check(plans == ["ultimate_performance"], f"select all: ONE power plan ({plans})")
    check(dns == ["dns_google"], f"select all: ONE DNS — the applied one ({dns})")
    check(sum(x.get() for x in v.values()) == len(v) - 3, "everything else selected")
    v["power_balanced"].set(True)
    check(not v["ultimate_performance"].get() and not v["power_high"].get(),
          "ticking 'Balanced' unticks the other plans")
    v["dns_cloudflare"].set(True)
    check(not v["dns_google"].get(), "ticking Cloudflare unticks Google")

@step(200)
def s2():
    # mouse wheel over a ROW (not only the strip next to the tweaks) scrolls the list
    opt._show_section("windows")
    root.update()
    area = opt._lists["windows"]
    canv = area._parent_canvas
    rowlbl = opt._name_labels["disable_telemetry"]
    y0 = canv.yview()[0]
    area._mouse_wheel_all(type("E", (), {"widget": rowlbl, "delta": -120})())
    check(canv.yview()[0] > y0, f"wheel over a tweak row scrolls the list ({y0:.3f} -> {canv.yview()[0]:.3f})")
    other = opt._lists["gaming"]
    y1 = canv.yview()[0]
    other._mouse_wheel_all(type("E", (), {"widget": rowlbl, "delta": -120})())
    check(canv.yview()[0] == y1 and other._parent_canvas.yview()[0] == 0.0,
          "... and only that list (the hidden sections stay put)")

@step(200)
def s3():
    opt._deselect_all()
    for t in ("disable_telemetry", "dns_cloudflare", "disable_advertising_id"):
        opt._vars[t].set(True)
    APPLIED.clear()
    opt._apply_selected()
    check(opt._batch_running and all(str(b.cget("state")) == "disabled" for b in opt._action_btns),
          "batch running: Apply / Revert disabled")
    n = len(BOXES)
    opt._apply_selected()
    check(len(BOXES) == n + 1 and "Bitte warten" in BOXES[-1][0], "second click -> 'please wait', no 2nd batch")

@step(1500)
def s4():
    check(not opt._batch_running and all(str(b.cget("state")) == "normal" for b in opt._action_btns),
          "batch finished: buttons back")
    check(len(APPLIED) == 3, f"each tweak applied exactly once ({len(APPLIED)})")
    check("dns_google" not in runner._applied and "dns_cloudflare" in runner._applied,
          "Google replaced by Cloudflare in the state")
    check(not opt._vars["dns_google"].get(), "replaced alternative unticked in the list")
    # 'einmalig' only on one-way tweaks
    def badges(tid):
        row = opt._name_labels[tid].master.master
        return [w.cget("text") for f in row.winfo_children() if isinstance(f, tk.Frame)
                for w in f.winfo_children() if isinstance(w, tk.Label)]
    check("⟳ einmalig" in badges("remove_cortana"), "'einmalig' on a one-way removal")
    check("⟳ einmalig" not in badges("disable_telemetry"), "no 'einmalig' on a revertible tweak")
    check("⇄ entweder-oder" in badges("power_high") and "⟳ einmalig" not in badges("power_high"),
          "power plans are marked 'entweder-oder'")
    root.after(100, root.quit)

def run(i=0):
    if i >= len(STEPS):
        return
    ms, fn = STEPS[i]
    def go():
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(False, f"{fn.__name__} raised {e!r}")
        run(i + 1)
    root.after(ms, go)

run()
root.after(20000, root.quit)
root.mainloop()
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
