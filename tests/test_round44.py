"""Round 44 — Windows 11 24H2+/26H2 and a fresh Windows.

  * Tweaks for things Windows no longer has are taken out (Cortana, Teams personal, the taskbar
    Chat button); their applied-state entries are ignored, "Revert all" removes only the value
    the old tweak set (against a scratch registry key here) and forgets them.
  * Telemetry tasks: the new appraiser task, tasks a build lacks are skipped, the status check
    covers every task that exists, the tweak can be reverted.
  * Audio checks: the same endpoints the tweak writes (state 1 = active or 8 = unplugged, with the
    flag bits masked off) — run against a scratch copy of the endpoint tree.
  * KB5127936 preparation: memory integrity in the health report, the Windows build change named in
    the "tweaks no longer active" dialog, Xbox removal warns (and left 'Mittel'), context menu note.
  * First start on a fresh Python: core/deps.py finds missing / too old packages, installs them
    (progress window, pip set up first when missing), explains failures; the launcher finds Python.
  * A missing Pillow no longer kills a dialog half-built (the checkbox falls back to a plain one).

Windowed (the setup window, the dialog): runs on the hidden desktop. No GPU, no admin."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r44_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

from core import deps  # noqa: E402
from core import health_report as HR  # noqa: E402
from core import optimization_score  # noqa: E402
from core import tweak_presets as TP  # noqa: E402
from core.hardware import windows_build  # noqa: E402
from core.tweak_i18n import PRESET_DESC_EN, TWEAK_DESC_EN, TWEAK_NAME_EN  # noqa: E402
from core.tweak_runner import TweakRunner  # noqa: E402
from core.tweak_verifier import SLOW_CHECKS, VERIFY_MAP  # noqa: E402
from core.tweaks import (ALL_TWEAKS, RETIRED_TWEAKS, WIN11_ONLY, _TELEMETRY_TASKS_PS,  # noqa: E402
                         get_by_id)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEST_KEY = "HKCU:\\Software\\GameOptimizerPro-Test44"


def ps(cmd, timeout=90):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


# ── 1. Retired tweaks ────────────────────────────────────────────────────────────────────────
print("tweaks for things Windows 24H2+ no longer has")
GONE = ("remove_cortana", "remove_teams", "w11_remove_chat_icon")
ids = {t.id for t in ALL_TWEAKS}
check(not any(g in ids or g in VERIFY_MAP or g in TWEAK_DESC_EN or g in TWEAK_NAME_EN or g in WIN11_ONLY
              or g in SLOW_CHECKS for g in GONE), "Cortana / Teams / Chat: no tweak, no check, no text any more")
check(not any(g in p.tweak_ids for p in TP.BUILTIN_PRESETS for g in GONE)
      and all(i in ids for p in TP.BUILTIN_PRESETS for i in p.tweak_ids), "no preset names a missing tweak")
texts = " ".join([p.desc for p in TP.BUILTIN_PRESETS] + list(PRESET_DESC_EN.values()))
check("Cortana" not in texts and "Teams" not in texts, "preset texts no longer promise Cortana / Teams")
check(set(RETIRED_TWEAKS) == set(GONE) and all(de and en for de, en, _c in RETIRED_TWEAKS.values())
      and RETIRED_TWEAKS["remove_cortana"][2] == "", "retired list: names in both languages, nothing to undo for an app")
check(len(ALL_TWEAKS) == 106 and len(ids) == 106, f"106 tweaks, ids unique ({len(ALL_TWEAKS)})")

if os.name == "nt":
    chat = RETIRED_TWEAKS["w11_remove_chat_icon"][2]
    teams = RETIRED_TWEAKS["remove_teams"][2]
    real_adv = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced"
    real_com = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications"
    check(real_adv in chat and real_com in teams, "the cleanups point at the keys the old tweaks wrote")
    chat_t = chat.replace(real_adv, TEST_KEY + "\\Adv")
    teams_t = teams.replace(real_com, TEST_KEY + "\\Comm")
    try:
        ps(f"New-Item '{TEST_KEY}\\Adv' -Force | Out-Null; New-Item '{TEST_KEY}\\Comm' -Force | Out-Null; "
           f"Set-ItemProperty '{TEST_KEY}\\Adv' TaskbarMn 0 -Type DWord; "
           f"Set-ItemProperty '{TEST_KEY}\\Comm' ConfigureChatAutoInstall 0 -Type DWord")
        rc1, _o, _e = ps(chat_t)
        rc2, _o, _e = ps(teams_t)
        _rc, left, _e = ps(f"$a=(Get-ItemProperty '{TEST_KEY}\\Adv').TaskbarMn; "
                           f"$c=(Get-ItemProperty '{TEST_KEY}\\Comm').ConfigureChatAutoInstall; \"[$a][$c]\"")
        check(rc1 == 0 and rc2 == 0 and left == "[][]", f"the value the old tweak set (0) is removed ({left})")
        ps(f"Set-ItemProperty '{TEST_KEY}\\Adv' TaskbarMn 1 -Type DWord")
        ps(chat_t)
        _rc, left, _e = ps(f"(Get-ItemProperty '{TEST_KEY}\\Adv').TaskbarMn")
        check(left == "1", "a value the old tweak did not set (1) stays")
    finally:
        ps(f"Remove-Item '{TEST_KEY}' -Recurse -Force -EA SilentlyContinue")

print("applied state with retired ids")
logs = Path(TMP) / "logs"
logs.mkdir()
(logs / "applied_tweaks.json").write_text(json.dumps({
    "remove_cortana": "2026-10-20T10:00:00", "w11_remove_chat_icon": "2026-10-20T10:00:01",
    "disable_telemetry": "2026-10-20T10:00:02"}), encoding="utf-8")
runner = TweakRunner(log_dir=str(logs))
check(runner.known_applied() == ["disable_telemetry"]
      and sorted(runner.retired_applied()) == ["remove_cortana", "w11_remove_chat_icon"],
      "known vs retired applied ids (an own preset only takes the known ones)")
calls = []
runner._run_ps = lambda cmd, timeout=60: (calls.append(cmd), (True, "ok"))[1]
runner.backup_registry = lambda label="": None
ok, _out = runner.clean_retired("remove_cortana")
check(ok and not calls and not runner.is_applied("remove_cortana"), "Cortana: nothing to run, just forgotten")
res = runner.revert_all()
saved = json.loads((logs / "applied_tweaks.json").read_text(encoding="utf-8"))
check(set(res) == {"disable_telemetry", "w11_remove_chat_icon"} and any("TaskbarMn" in c for c in calls)
      and saved == {}, f"'Revert all' reverts the known tweaks and cleans the retired one ({sorted(res)}, {saved})")


class _NoVerify:
    def verify_all(self, *a, **k):
        raise AssertionError("must not run")


check(optimization_score.check_applied(list(GONE), None, _NoVerify()) == ([], []),
      "the drift check ignores retired ids (no 'no longer active' for them)")
src_opt = open(os.path.join(ROOT, "ui", "tab_optimizer.py"), encoding="utf-8").read()
check("self.runner.retired_applied()" in src_opt and "self.runner.clean_retired(tid)" in src_opt
      and "self.runner.known_applied()" in src_opt, "the Optimizer page: 'Revert all' + own preset use them")

# ── 2. Telemetry tasks ───────────────────────────────────────────────────────────────────────
print("telemetry tasks")
t = get_by_id("disable_telemetry_tasks")
check("Microsoft Compatibility Appraiser Exp" in _TELEMETRY_TASKS_PS and "ProgramDataUpdater" in _TELEMETRY_TASKS_PS
      and "-EA SilentlyContinue" in _TELEMETRY_TASKS_PS, "the new appraiser task is in, missing tasks are skipped")
check(t.ps_command.startswith(_TELEMETRY_TASKS_PS) and "Disable-ScheduledTask" in t.ps_command
      and "exit 1" in t.ps_command and "Enable-ScheduledTask" in (t.revert_cmd or ""),
      "apply disables the existing ones (fails honestly), revert enables them again")
check(VERIFY_MAP["disable_telemetry_tasks"].startswith(_TELEMETRY_TASKS_PS)
      and "$found.Count -gt 0" in VERIFY_MAP["disable_telemetry_tasks"],
      "the status check covers every task this Windows has, not one")
if os.name == "nt":
    rc, out, err = ps(_TELEMETRY_TASKS_PS + "Write-Output $found.Count")
    check(rc == 0 and out.isdigit() and 1 <= int(out) <= 7, f"task lookup on this Windows: {out} of 7 exist, no error")
    rc, out, err = ps(VERIFY_MAP["disable_telemetry_tasks"])
    check(rc == 0 and out in ("0", "1"), f"the real check answers 0/1 ({out})")

# ── 3. Audio checks ──────────────────────────────────────────────────────────────────────────
print("audio checks: the endpoints the tweak writes")
REAL = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render"
NEW_FILTER = "if($st -ne 1 -and $st -ne 8){ continue }"
for tid in ("disable_audio_enhancements", "disable_audio_exclusive_lock"):
    check(REAL in VERIFY_MAP[tid] and "-band 0xF" in VERIFY_MAP[tid] and NEW_FILTER in VERIFY_MAP[tid],
          f"{tid}: state & 0xF in (1, 8) — like audio_policy.RenderIds(1 | 8)")
src_ap = open(os.path.join(ROOT, "core", "audio_policy.py"), encoding="utf-8").read()
check("RenderIds(1 -bor 8)" in src_ap, "audio_policy writes active + unplugged endpoints")
if os.name == "nt":
    setup = (
        f"$b='{TEST_KEY}\\Render'; Remove-Item '{TEST_KEY}' -Recurse -Force -EA SilentlyContinue; "
        "$devs=@(@('{d1}',0x10000001,1),@('{d2}',8,1),@('{d3}',2,0),@('{d4}',4,0),@('{d5}',1,1)); "
        "foreach($d in $devs){ $k=Join-Path $b $d[0]; New-Item $k -Force | Out-Null; "
        "New-ItemProperty $k -Name DeviceState -PropertyType DWord -Value $d[1] -Force | Out-Null; "
        "$fx=Join-Path $k 'FxProperties'; New-Item $fx -Force | Out-Null; "
        "New-ItemProperty -LiteralPath $fx -Name '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5' -PropertyType DWord -Value $d[2] -Force | Out-Null; "
        "$pp=Join-Path $k 'Properties'; New-Item $pp -Force | Out-Null; "
        "New-ItemProperty -LiteralPath $pp -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},3' -PropertyType DWord -Value (1-$d[2]) -Force | Out-Null; "
        "New-ItemProperty -LiteralPath $pp -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},4' -PropertyType DWord -Value (1-$d[2]) -Force | Out-Null }")
    fx = VERIFY_MAP["disable_audio_enhancements"].replace(REAL, TEST_KEY + "\\Render")
    ex = VERIFY_MAP["disable_audio_exclusive_lock"].replace(REAL, TEST_KEY + "\\Render")
    old_fx = fx.replace("$st=(Get-ItemProperty $k.PSPath -Name DeviceState -EA SilentlyContinue).DeviceState -band 0xF; "
                        + NEW_FILTER,
                        "if((Get-ItemProperty $k.PSPath -Name DeviceState -EA SilentlyContinue).DeviceState -ne 1){ continue }")
    try:
        rc, _o, err = ps(setup)
        check(rc == 0, f"scratch endpoints: active (plain + with a flag bit), unplugged, disabled, not present {err[:120]}")
        _rc, a, _e = ps(fx)
        _rc, b, _e = ps(ex)
        check(a == "1" and b == "1", f"all written endpoints set -> active ({a}/{b}); disabled / absent ones ignored")
        ps(f"Set-ItemProperty -LiteralPath '{TEST_KEY}\\Render\\{{d1}}\\FxProperties' "
           "-Name '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5' -Value 0")
        _rc, a, _e = ps(fx)
        _rc, old, _e = ps(old_fx)
        check(a == "0" and old == "1", f"an active endpoint with flag bits off -> not active (old filter missed it: {old})")
    finally:
        ps(f"Remove-Item '{TEST_KEY}' -Recurse -Force -EA SilentlyContinue")

# ── 4. KB5127936 preparation ─────────────────────────────────────────────────────────────────
print("KB5127936: memory integrity, build change, Xbox, context menu")
on = HR._hvci_line({"hvci": {"known": True, "running": True}})
off = HR._hvci_line({"hvci": {"known": True, "running": False}})
check(on and on.value == "an" and "Afterburner" in on.note and on.severity == HR.OK,
      "memory integrity on: shown, with the Afterburner hint (information, no warning)")
check(off and off.value == "aus" and "KB5127936" in off.note, "off: says that the update may switch it on")
check(HR._hvci_line({"hvci": {"known": False}}) is None and HR._hvci_line({}) is None, "unknown: no line")
check("$d.hvci" in HR._BUNDLE_PS and "Win32_DeviceGuard" in HR._BUNDLE_PS, "read in the same read-only call")
b = windows_build()
check(os.name != "nt" or re.fullmatch(r"\d{5}\.\d+", b), f"Windows build with update revision ({b})")
xb = get_by_id("remove_xbox")
check(xb.risk == "moderate" and "Game Pass" in xb.desc and "Game Pass" in TWEAK_DESC_EN["remove_xbox"]
      and "remove_xbox" not in TP._MEDIUM_EXTRA and "remove_xbox" in TP._HARD_EXTRA,
      "Xbox apps: warns about Xbox sign-in / Game Pass, moved from 'Mittel' to 'Hart'")
cm = get_by_id("w11_classic_context_menu")
check("KB5127936" in cm.desc and "KB5127936" in TWEAK_DESC_EN["w11_classic_context_menu"],
      "classic context menu: note about the new customizable menu")

print("drift check remembers the Windows build")
import ctypes  # noqa: E402
import ui.main_window as MW  # noqa: E402
real_admin = ctypes.windll.shell32.IsUserAnAdmin if os.name == "nt" else None
got = []


class FakeWin:
    def __init__(self, applied):
        self.runner = type("R", (), {"_applied": applied})()
        self.hw = None

    def after(self, ms, fn):
        fn()

    def _ask_drift(self, drifted, build_change=None):
        got.append((drifted, build_change))


if os.name == "nt":
    ctypes.windll.shell32.IsUserAnAdmin = lambda: 1
    real_check = optimization_score.check_applied
    optimization_score.check_applied = lambda applied, hw, verifier=None: (["disable_telemetry"], [])
    try:
        app_settings.set("last_windows_build", "26300.1")
        MW.GameOptimizerWindow._start_drift_check(FakeWin({}))
        check(app_settings.get("last_windows_build") == b, "a new build is stored even with no tweaks applied")
        app_settings.set("last_windows_build", "26300.1")
        MW.GameOptimizerWindow._start_drift_check(FakeWin({"disable_telemetry": "x"}))
        deadline = time.time() + 10
        while not got and time.time() < deadline:
            time.sleep(0.05)
        check(got and got[0][1] == ("26300.1", b), f"the dialog gets (old, new) build ({got[:1]})")
        got.clear()
        MW.GameOptimizerWindow._start_drift_check(FakeWin({"disable_telemetry": "x"}))
        deadline = time.time() + 10
        while not got and time.time() < deadline:
            time.sleep(0.05)
        check(got and got[0][1] is None, "same build next start: no update note")
    finally:
        ctypes.windll.shell32.IsUserAnAdmin = real_admin
        optimization_score.check_applied = real_check

# ── 5. First start on a fresh Python ─────────────────────────────────────────────────────────
print("first start: packages")
reqs = deps.requirements()
check(len(reqs) == 7 and {d for _s, d, _v in reqs} >= {"Pillow", "customtkinter", "psutil", "numpy"}
      and all(v for _s, _d, v in reqs), f"requirements.txt read: {len(reqs)} packages with minimum versions")
raw = open(os.path.join(ROOT, "requirements.txt"), "rb").read()
check(all(c < 128 for c in raw), "requirements.txt is ASCII (pip reads it with the system code page)")
check(deps.import_name("nvidia-ml-py") == "pynvml" and deps.import_name("Pillow") == "PIL"
      and deps.import_name("WMI") == "wmi" and deps.import_name("customtkinter") == "customtkinter", "import names")
check(deps.missing() == [], "everything installed here: nothing missing")
fake_req = Path(TMP) / "req.txt"
fake_req.write_text("nonexistent-gop-pkg>=1.0\nPillow>=99.0\nnumpy>=1.0  # a comment\n# only a comment\n", encoding="utf-8")
check(deps.missing(fake_req) == ["nonexistent-gop-pkg>=1.0", "Pillow>=99.0"], "missing AND too old are found")
check(deps._vtuple("13.0.0") > deps._vtuple("9.5") and deps._vtuple("1.26") < deps._vtuple("2.5.4")
      and deps._vtuple("5.2") <= deps._vtuple("5.2.0"), "version comparison")
check(deps.console_python(r"C:\Py\pythonw.exe") in (r"C:\Py\pythonw.exe", r"C:\Py\python.exe")
      and deps.console_python(sys.executable) == sys.executable, "pip runs in the console interpreter")
deps._lang = lambda: "de"
check("Internet" in deps.explain("ERROR: ... getaddrinfo failed ...")
      and "Python 3.12" in deps.explain("ERROR: No matching distribution found for x")
      and "Administrator" in deps.explain("ERROR: [WinError 5] Access is denied")
      and "pip" in deps.explain("python.exe: No module named pip")
      and "install.bat" in deps.explain("something else"), "failures explained in plain words")

if os.name == "nt":
    fake = Path(TMP) / "fakepy.bat"
    marker = Path(TMP) / "pip_ready"
    fake.write_bytes(("@echo off\r\n"
                      "if \"%2\"==\"ensurepip\" (\r\n  echo ensurepip done\r\n  type nul > \"MARK\"\r\n  exit /b 0\r\n)\r\n"
                      "if exist \"MARK\" (\r\n  echo Successfully installed fakepkg\r\n  exit /b 0\r\n)\r\n"
                      "echo C:\\Py\\python.exe: No module named pip\r\nexit /b 1\r\n").replace("MARK", str(marker)).encode())
    ok, out = deps.pip_install(["fakepkg"], python=str(fake))
    check(ok and "ensurepip done" in out and "Successfully installed" in out,
          "a Python without pip: pip is set up first, then the install runs again")

real_missing, real_pip, real_log, real_msg = deps.missing, deps.pip_install, deps.SETUP_LOG, deps._message
deps.SETUP_LOG = Path(TMP) / "setup.log"
msgs = []
deps._message = lambda text, error=True: msgs.append(text)
try:
    deps.missing = lambda path=None: ["fakepkg>=1"]
    deps.pip_install = lambda specs, on_line=None, python=None: (False, "ERROR: getaddrinfo failed")
    import io  # noqa: E402
    import contextlib  # noqa: E402
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = deps.ensure(gui=False)
    check(res is False and "Internet" in buf.getvalue() and "getaddrinfo" in deps.SETUP_LOG.read_text(encoding="utf-8"),
          "no internet: the start ends with that reason, pip's output is in logs/setup.log")
    real_min = deps.MIN_PYTHON
    deps.MIN_PYTHON = (99, 0)
    with contextlib.redirect_stdout(io.StringIO()):
        res = deps.ensure(gui=True)
    deps.MIN_PYTHON = real_min
    check(res is False and msgs and "zu alt" in msgs[-1], "a too old Python: a clear message, no traceback")

    print("the setup window (hidden desktop)")
    state = {"installed": False, "on_line": None}

    def fake_pip(specs, on_line=None, python=None):
        state["on_line"] = on_line
        for line in ("Collecting fakepkg", "Installing collected packages: fakepkg", "Successfully installed fakepkg"):
            on_line(line)
            time.sleep(0.25)
        state["installed"] = True
        return True, "Successfully installed fakepkg"
    deps.missing = lambda path=None: [] if state["installed"] else ["fakepkg>=1"]
    deps.pip_install = fake_pip
    msgs.clear()
    t0 = time.time()
    res = deps.ensure(gui=True)
    check(res is True and state["installed"] and state["on_line"] is not None and not msgs
          and time.time() - t0 >= 0.7, "missing packages: installed behind a progress window, the start goes on")
finally:
    deps.missing, deps.pip_install, deps.SETUP_LOG, deps._message = real_missing, real_pip, real_log, real_msg

print("launcher")
src_main = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
i_hook, i_hw = src_main.find("deps.ensure()"), src_main.find("from core.hardware")
check(0 < i_hook < i_hw and 'if __name__ == "__main__":\n    # A fresh Windows' in src_main,
      "the app checks its packages before importing anything that needs them (only when started)")
bat = open(os.path.join(ROOT, "GameOptimizerPro.bat"), "rb").read()
inst = open(os.path.join(ROOT, "install.bat"), "rb").read()
fp = open(os.path.join(ROOT, "tools", "find_python.cmd"), "rb").read()
check(b'tools\\find_python.cmd" offer' in bat and b"-m core.deps" in bat and b'tools\\find_python.cmd" offer' in inst,
      "both batch files use the shared Python search; the launcher sets up the packages")
check(all(x.count(b"\r\n") == x.count(b"\n") for x in (bat, inst, fp)), "batch files have CRLF line endings")
check(b"WindowsApps" in fp and b"pythoncore-%%V-64" in fp and b"Python.Python.3.12" in fp and b"choice /C JYN" in fp,
      "Python search: never the Store one, the install manager too; installing Python is asked first")
if os.name == "nt":
    wrap = Path(TMP) / "fp_wrap.cmd"
    wrap.write_bytes(("@echo off\r\ncall \"" + os.path.join(ROOT, "tools", "find_python.cmd")
                      + "\"\r\necho PYW=%PYW%\r\necho PY=%PY%\r\n").encode())
    r = subprocess.run(["cmd", "/c", str(wrap)], capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    found = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    pyw, py = found.get("PYW", "").strip(), found.get("PY", "").strip()
    if pyw:
        check(os.path.exists(pyw) and os.path.exists(py) and py.lower().endswith("python.exe")
              and "windowsapps" not in pyw.lower(), f"finds this PC's Python: {pyw}")
    else:
        print("  (no classic Python in the searched places on this machine — search not checked)")

# ── 6. Without Pillow a dialog keeps its buttons ─────────────────────────────────────────────
print("missing Pillow: plain checkbox, the dialog stays usable")
import tkinter as tk  # noqa: E402
import customtkinter as ctk  # noqa: E402
from ui import components  # noqa: E402
from ui.drift_dialog import DriftDialog  # noqa: E402
root = ctk.CTk()
root.withdraw()


def labels(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, tk.Label):
            out.append(str(c.cget("text")))
        out += labels(c)
    return out


def buttons(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, ctk.CTkButton):
            out.append(c)
        out += buttons(c)
    return out


dlg = DriftDialog(root, [("disable_telemetry", "Telemetrie")], on_done=lambda a, b: None,
                  build_change=("26300.9711", "26300.9818"))
root.update()
check(any("26300.9711 → 26300.9818" in s for s in labels(dlg)) and len(buttons(dlg)) == 2,
      "the dialog names the Windows update")
dlg.destroy()
saved_pil = sys.modules.get("PIL")
sys.modules["PIL"] = None
root.__dict__.pop("_gop_check_images", None)
try:
    v = tk.BooleanVar(value=True)
    cb = components.CheckBox(root, v, text="x")
    dlg2 = DriftDialog(root, [("disable_telemetry", "Telemetrie")], on_done=lambda a, b: None)
    root.update()
    check(cb._gop_imgs == () and len(buttons(dlg2)) == 2, "no Pillow: plain checkbox, dialog with both buttons")
    dlg2.destroy()
finally:
    if saved_pil is not None:
        sys.modules["PIL"] = saved_pil
    else:
        sys.modules.pop("PIL", None)
root.destroy()

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
