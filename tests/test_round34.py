"""Round 34 — the live tweak status as in v1: every check really runs (one PowerShell call per part,
never past Windows' command-line limit), and the optimizer counts what is active on the system —
group headers, preset cards and the preview — not only what the app applied itself."""
import os
import re
import sys
import tempfile
import time
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


TMP = tempfile.mkdtemp(prefix="gop_r34_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

# ── 1) the status check is split below the command-line limit ────────────────
print("status check: parts")
from core import tweak_verifier as TV  # noqa: E402
ids = list(TV.VERIFY_MAP)
parts = TV.split_batch(ids)
whole = len("\n".join(TV._check_line(t) for t in ids))
check([t for p in parts for t in p] == ids, f"every check in one of {len(parts)} parts, in order")
check(all(sum(len(TV._check_line(t)) + 1 for t in p) <= TV.MAX_SCRIPT_CHARS for p in parts)
      and TV.MAX_SCRIPT_CHARS < 32767 - 200,
      f"every part stays below the limit (all in one: {whole} characters — Windows allows 32767 for the "
      f"whole command line)")
check(TV.split_batch(["disable_eee"] * 3, limit=10) == [["disable_eee"]] * 3,
      "a check longer than the limit gets a part of its own (never dropped)")

calls = []
_real_run = TV.subprocess.run


def fake_run(cmd, **kw):
    script = cmd[-1]
    calls.append(len(script))
    out = "\n".join(f"{tid}|1" for tid in re.findall(r'Write-Output "([A-Za-z0-9_]+)\|\$__r"', script))
    return types.SimpleNamespace(stdout=out, stderr="", returncode=0)


TV.subprocess.run = fake_run
res = TV.TweakVerifier()._run_batch(ids, {t: False for t in ids}, timeout=5)
TV.subprocess.run = _real_run
check(len(calls) == len(parts) and max(calls) <= TV.MAX_SCRIPT_CHARS and len(res) == len(ids)
      and all(r.actual and not r.error for r in res.values()),
      "one PowerShell call per part, the answers of all parts together")

if os.name == "nt":
    print("status check: the real one (read-only)")
    t0 = time.time()
    real = TV.TweakVerifier().verify_all(ids, {t: False for t in ids})
    answered = sum(1 for r in real.values() if not r.error)
    # without admin rights a few checks (bcdedit, packages of all users) can't answer; the app runs as admin
    check(answered >= len(ids) * 0.85,
          f"{answered} of {len(ids)} checks answered on this PC in {time.time() - t0:.1f} s (before: 5)")

# ── 2) "Stop auto-installed suggested apps" works on Home / Pro ──────────────
print("suggested apps")
from core.registry_backup import BACKUP_KEYS  # noqa: E402
from core.tweak_i18n import tweak_name  # noqa: E402
from core.tweaks import get_by_id  # noqa: E402
t = get_by_id("disable_consumer_features")
check(all(v in t.ps_command and v in t.revert_cmd for v in
          ("SilentInstalledAppsEnabled", "OemPreInstalledAppsEnabled", "PreInstalledAppsEnabled"))
      and "ContentDeliveryManager" in TV.VERIFY_MAP[t.id] and "DisableWindowsConsumerFeatures" in t.ps_command,
      "the Content Delivery Manager values (every edition) + the policy (Enterprise / Education); the check "
      "reads the part that works everywhere")
check("Enterprise" in t.desc and tweak_name(t, "en") == "Stop Auto-Installed Suggested Apps",
      "says honestly where the policy alone counts; English name")
check(any(k.endswith("ContentDeliveryManager") for k in BACKUP_KEYS), "its key is in the registry backup")

# ── 3) the optimizer counts the live state ───────────────────────────────────
print("optimizer: live state")
import customtkinter as ctk  # noqa: E402
from tkinter import messagebox  # noqa: E402
from core.hardware import HardwareInfo  # noqa: E402
from core.tweak_presets import get_all_presets  # noqa: E402
from core.tweak_runner import TweakRunner  # noqa: E402
from ui.tab_optimizer import OptimizerTab  # noqa: E402

hw = HardwareInfo(cpu_name="AMD Ryzen 7 7800X3D", cpu_cores=8, cpu_threads=16, gpu_name="NVIDIA GeForce RTX 4080",
                  gpu_vendor="NVIDIA", is_nvidia=True, ram_total_gb=32, os_name="Windows 11 Pro", os_build=26300,
                  is_win11=True, has_nvme=True, nvme_count=1)
runner = TweakRunner(log_dir=TMP)
runner.backup_registry = lambda label: None
runner._run_ps = lambda cmd, timeout=60: (True, "ok")
preset = get_all_presets([])[0]
usable = [i for i in preset.tweak_ids if get_by_id(i) and i in TV.VERIFY_MAP]
ACTIVE = set(usable[:3])                         # set outside the app (by hand, v1, before a reinstall)
TV.TweakVerifier.verify_all = lambda self, ids_, exp: {
    i: TV.VerifyResult(i, False, i in ACTIVE, False) for i in ids_}

import threading  # noqa: E402
import ui.tab_optimizer as TO  # noqa: E402


class _SyncThread:
    """The page's workers run right away on this thread: Tk calls from a worker need the app's
    running main loop, which a test that pumps with update() doesn't have between its calls."""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._run = lambda: target(*args, **(kwargs or {}))

    def start(self):
        self._run()


TO.threading = types.SimpleNamespace(**{**vars(threading), "Thread": _SyncThread})
root = ctk.CTk()
root.withdraw()                                  # never mapped
tab = OptimizerTab(root, runner, hw, profiles_dir=TMP, logs_dir=TMP)
tab._live_verify()
for _ in range(10):
    root.update()
check(not runner._applied and all(tab._is_active(i) for i in ACTIVE),
      "active on the system, not applied by the app: active (ownership unchanged)")
group = get_by_id(usable[0]).group
key = next(k for (k, g) in tab._group_heads if g == group)
n_active = sum(1 for i in ACTIVE if get_by_id(i).group == group)
txt = tab._group_heads[(key, group)]["count"].cget("text")
check(txt.endswith(f"{n_active} aktiv"), f"group header counts the live state: '{txt}'")
check("geprüft" in tab.lbl_verify_hint.cget("text"), f"the status line says when it checked: "
      f"'{tab.lbl_verify_hint.cget('text')}'")

shown, asked = [], []
_si, _ay = messagebox.showinfo, messagebox.askyesno
messagebox.showinfo = lambda title, msg, **k: shown.append(msg)
messagebox.askyesno = lambda title, msg, **k: (asked.append(msg), False)[1]
tab._preview_preset(preset)
check(shown and shown[-1].count("✓ aktiv") == len(ACTIVE), "preview: the live state")
tab._apply_preset(preset)
n_left = sum(1 for i in preset.tweak_ids if get_by_id(i) and tab._is_applicable(get_by_id(i))
             and i not in ACTIVE)
check(asked and f"{n_left} Tweak(s) werden aktiviert" in asked[-1],
      f"a preset leaves what is already active alone ({n_left} to apply)")
I18N._current_lang = "en"
tab._preview_preset(preset)
check("✓ active" in shown[-1] and "aktiv" not in shown[-1], "preview in English too")
I18N._current_lang = "de"

# ── 4) a restore point before app removals (v1: before every apply) ──────────
print("restore point before app removals")
import core.restore_point as RP  # noqa: E402
made = []
_rp = RP.create
RP.create = lambda description="": (made.append(description), (True, "✓ ok"))[1]
tab._backup_before("PreApply", [get_by_id("disable_telemetry")])
check(not made, "no app removal: only the registry backup")
tab._backup_before("PreApply", [get_by_id("disable_telemetry"), get_by_id("remove_xbox")])
check(len(made) == 1, "a batch that removes apps: a restore point first (only it brings them back)")
check("Wiederherstellungspunkt" in tab._removal_note([get_by_id("remove_xbox")])
      and tab._removal_note([get_by_id("disable_telemetry")]) == "",
      "the confirmation says so — only when apps are removed")
RP.create = _rp
messagebox.showinfo, messagebox.askyesno = _si, _ay

# ── 5) snapshot & compare (v1's dashboard tool, kept across a restart) ───────
print("snapshot & compare")
from core import tweak_snapshot as SN  # noqa: E402
R = TV.VerifyResult
snap = SN.take({"a": R("a", False, True, False), "b": R("b", False, False, False),
                "c": R("c", False, False, False, error="Timeout")})
check(snap["states"] == {"a": True, "b": False, "c": None}, "a snapshot: on / off / no answer")
check(SN.save(TMP, snap) and SN.load(TMP)["states"] == snap["states"], "saved next to the logs, read back")
changed, unknown = SN.compare(snap, {"a": R("a", False, False, False), "b": R("b", False, False, False),
                                     "c": R("c", False, True, False)})
check(changed == [("a", True, False)] and unknown == 1,
      "compare: what changed; a check without an answer is no change (counted)")
(Path(TMP) / SN.FILE_NAME).write_text("[1, 2]", encoding="utf-8")
check(SN.load(TMP) is None, "a broken file is no snapshot")
SNAP_STATE = {i: (i in ACTIVE) for i in TV.VERIFY_MAP}
TV.TweakVerifier.verify_all = lambda self, ids_, exp: {
    i: TV.VerifyResult(i, False, SNAP_STATE[i], False) for i in ids_}


def pump(cond, n=20):
    for _ in range(n):
        root.update()
        if cond():
            return True
    return False


tab._take_snapshot()
pump(lambda: str(tab.btn_snap_take.cget("state")) == "normal" and "Snapshot vom" in tab.lbl_snap.cget("text"))
check("Snapshot vom" in tab.lbl_snap.cget("text") and SN.load(TMP) is not None,
      f"'Take snapshot': saved and shown ({tab.lbl_snap.cget('text')})")
flip = next(iter(ACTIVE))
SNAP_STATE[flip] = False                         # e.g. a Windows update switched it back
tab._compare_snapshot()
pump(lambda: "geändert" in tab.lbl_snap.cget("text"))
rows = [tab.snap_tree.item(r, "values") for r in tab.snap_tree.get_children()]
check("1 Tweak(s) geändert" in tab.lbl_snap.cget("text") and len(rows) == 1
      and tuple(rows[0][1:]) == ("aktiv", "inaktiv"), f"'Compare': exactly the tweak that changed: {rows}")
root.destroy()

# ── 6) Windows 11 only tweaks are hidden on Windows 10 (v1 greys them out) ────
print("Windows 11 only")
from core.optimization_score import applicable  # noqa: E402
from core.tweaks import WIN11_ONLY  # noqa: E402
w10 = HardwareInfo(os_name="Windows 10 Pro", os_build=19045, is_win10=True)
w11 = HardwareInfo(os_name="Windows 11 Pro", os_build=26300, is_win11=True)
unknown_os = HardwareInfo()
check(len(WIN11_ONLY) == 6 and all(get_by_id(i).requires_win11 for i in WIN11_ONLY),
      "the 6 taskbar / Start / Explorer tweaks of Windows 11 are marked (round 44: the Chat button is gone)")
check(not any(applicable(get_by_id(i), w10) for i in WIN11_ONLY)
      and all(applicable(get_by_id(i), w11) and applicable(get_by_id(i), unknown_os) for i in WIN11_ONLY)
      and applicable(get_by_id("disable_telemetry"), w10),
      "Windows 10: not offered (score, drift check, list, presets); Windows 11 or unknown: offered")

# ── 7) dashboard: disk and network throughput (v1's live monitor) ────────────
print("dashboard: throughput")
from ui.tab_dashboard import DashboardTab  # noqa: E402


class _L:
    def __init__(self):
        self.text = ""

    def config(self, **kw):
        self.text = kw.get("text", self.text)


fake = types.SimpleNamespace(_sys_tiles={k: _L() for k in ("cpu", "ram", "disk", "io", "net")})
DashboardTab._update_sys(fake, 12, 40, 55, 3.456, 87.2)
check(fake._sys_tiles["io"].text == "3.5" and fake._sys_tiles["net"].text == "87",
      "disk MB/s and network Mbit/s shown")
DashboardTab._update_sys(fake, 12, 40, 55)
check(fake._sys_tiles["net"].text == "--", "no measurement yet: '--'")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
