"""Round 46 — the two reviews of build 53: what held up, built and tested.

  * winget: the time limit works while a setup hangs (the output is read in a thread of its own, the
    whole process tree is ended); no input; a program the setup started can't hold the read open.
  * Update installer: handles typed pointer-sized, only "no such process" counts as ended; no hidden
    pip run any more (the next start installs missing packages with a window).
  * Apps page: one read at a time, nothing removed / installed while a list is read, the install
    button comes back when winget is installed later.
  * Own presets are kept after a restart (never written over a file that can't be read), the same
    name replaces, an import twice gives no duplicates, texts in both languages.
  * After the drift dialog the optimizer checks the state again; a check asked for during a check runs
    after it.
  * Paint AI: only the three documented policies (the check reads the same list); the revert also
    deletes the two undocumented values earlier builds set — run for real on a scratch key.
  * Health report: a critical finding makes the summary red. README and CHANGELOG name the same test
    count, and the suite count is the runner's.

Windowed (optimizer, apps page, diagnose, drift): runs on the hidden desktop. No admin, nothing
installed or removed, never the real Paint key or the user's presets."""
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import winreg
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["PYTHONIOENCODING"] = "utf-8"          # the child processes below print block characters

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r46_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

import psutil  # noqa: E402

from core import health_report as HR  # noqa: E402
from core import tweaks as T  # noqa: E402
from core import user_presets as UP  # noqa: E402
from core import winget_installer as WI  # noqa: E402
from core.tweak_i18n import TWEAK_DESC_EN, preset_desc  # noqa: E402
from core.tweak_presets import TweakPreset, get_preset  # noqa: E402
from core.tweak_verifier import VERIFY_MAP, reg_spec  # noqa: E402

UP.PRESETS_FILE = Path(TMP) / "presets" / "user_presets.json"      # never the user's own presets
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


# ── 1. winget: time limit, process tree, no input ────────────────────────────
print("winget: time limit, process tree, no input")
real_exe, real_tail = WI.winget_exe, WI.TAIL_S
WI.winget_exe = lambda: sys.executable            # a stand-in that behaves like a hanging setup
WI.TAIL_S = 1.0
leftover = []


def pid_from(out, word):
    m = re.search(word + r" (\d+)", out)
    return int(m.group(1)) if m else 0


try:
    t0 = time.time()
    rc, out = WI._run(["-c", "import time; print('working', flush=True); time.sleep(120)"], timeout=2)
    dt = time.time() - t0
    check(rc == -2 and "working" in out and "Zeitüberschreitung" in out and dt < 15,
          f"a run that hangs with its output open is timed out ({dt:.1f} s) — the lines so far are kept")
    code = ("import subprocess, sys, time; "
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdout=sys.stdout); "
            "print('child', c.pid, flush=True); time.sleep(120)")
    t0 = time.time()
    rc, out = WI._run(["-c", code], timeout=2)
    cpid = pid_from(out, "child")
    leftover.append(cpid)
    end = time.time() + 5
    while cpid and psutil.pid_exists(cpid) and time.time() < end:
        time.sleep(0.1)
    check(rc == -2 and cpid > 0 and not psutil.pid_exists(cpid) and time.time() - t0 < 20,
          "a setup under winget that hangs too (and holds the output) is ended with it: the whole tree")
    code = ("import subprocess, sys; "
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdout=sys.stdout); "
            "print('started', c.pid, flush=True)")
    t0 = time.time()
    rc, out = WI._run(["-c", code], timeout=60)
    dt = time.time() - t0
    leftover.append(pid_from(out, "started"))
    check(rc == 0 and "started" in out and dt < 8,
          f"winget ended but a program it started keeps the output: back after {dt:.1f} s, not when that program ends")
    rc, out = WI._run(["-c", "import sys; print('EOF' if sys.stdin.read() == '' else 'input', flush=True)"], timeout=20)
    check(rc == 0 and out.strip() == "EOF", f"no input: a question gets end-of-input at once, never waits ({out!r})")
    got = []

    def cb(s):
        got.append(s)
        raise RuntimeError("page gone")
    rc, out = WI._run(["-c", "print('one'); print('  ██████▒▒▒▒  45%'); print('two')"], timeout=20, on_line=cb)
    check(rc == 0 and got == ["one", "two"] and out.splitlines() == ["one", "two"],
          f"progress bars dropped, every text line handed on, a failing callback stops nothing ({got})")
    rc, _o = WI._run(["-c", "import sys; sys.exit(-1978335189)"], timeout=20)
    check(rc == 0x8A15002B, f"exit code as winget documents it, unsigned ({rc:#x})")
    WI.winget_exe = lambda: None
    check(WI._run(["list"])[0] == -1, "no winget: nothing started")
finally:
    WI.winget_exe, WI.TAIL_S = real_exe, real_tail
    for pid in leftover:
        try:
            if pid and psutil.pid_exists(pid):
                psutil.Process(pid).kill()
        except psutil.Error:
            pass
src_wi = open(os.path.join(ROOT, "core", "winget_installer.py"), encoding="utf-8").read()
check("stdin=subprocess.DEVNULL" in src_wi and '"taskkill", "/F", "/T"' in src_wi,
      "winget gets no input and a time-out ends the whole process tree")
fm = next(p for p in WI.CATALOG if p.id == "Geeks3D.FurMark.2")
src_fm = open(os.path.join(ROOT, "core", "furmark.py"), encoding="utf-8").read()
check(any(x.endswith(r"\Geeks3D\FurMark2\furmark.exe") for x in fm.paths)
      and r"Geeks3D\FurMark2\furmark.exe" in src_fm,
      "FurMark 2: every folder the stress test knows counts as installed")
ch = next(p for p in WI.CATALOG if p.id == "Google.Chrome")
check(len(ch.paths) == 3 and any("(x86)" in x for x in ch.paths) and any(x.lower().startswith(os.environ.get(
      "LOCALAPPDATA", "?").lower()) for x in ch.paths), "Chrome: 64-bit, the old 32-bit folder and the per-user install")

# ── 2. Update installer ──────────────────────────────────────────────────────
print("update installer")
import tools.apply_update as AU  # noqa: E402
src_au = open(os.path.join(ROOT, "tools", "apply_update.py"), encoding="utf-8").read()
check("OpenProcess.restype = wintypes.HANDLE" in src_au and "WaitForSingleObject.argtypes" in src_au
      and "CloseHandle.argtypes" in src_au, "process handles typed pointer-sized (OpenProcess, wait, close)")
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
t0 = time.time()
check(AU.wait_for_exit(p.pid, 10) and time.time() - t0 < 5, "waits until the app process has ended")
p2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
t0 = time.time()
r = AU.wait_for_exit(p2.pid, 0.5)
p2.kill()
check(r is False and time.time() - t0 < 5, "a process that doesn't end in time: no update")
check(AU.wait_for_exit(999999) and AU.wait_for_exit(0), "no such process / no pid: nothing to wait for")
if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    h = k.OpenProcess(0x00100000, False, 4)
    why = "access denied" if not h and ctypes.get_last_error() == 5 else "it never ends"
    if h:
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle(h)
    check(AU.wait_for_exit(4, 0.3) is False,
          f"a process that can't be watched or doesn't end (System: {why}): no update — any failure to open "
          f"it used to count as 'ended'")
body = re.sub(r'""".*?"""', "", src_au, flags=re.S)
check('"pip"' not in body and "requirements.txt geändert" in body,
      "no hidden pip run in the updater (only logged when requirements.txt changed)")
src_gop = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check(src_gop.index("deps.ensure()") < src_gop.index("from core.hardware") and '"--after-restart"' in src_au,
      "the restart after an update runs the package check first (progress window, clear message)")

# ── 3. Own presets: kept after a restart ─────────────────────────────────────
print("own presets")
check(UP.load() == ([], True), "no file yet: none, and readable")
ids = [t.id for t in T.ALL_TWEAKS if T.get_by_id(t.id)][:3]
p1 = TweakPreset(id=UP.make_id(" Mein  Spiel "), name="Mein Spiel", icon="⭐", desc="", tweak_ids=ids[:2],
                 color="#ffffff", builtin=False)
check(p1.id == "user_mein_spiel", f"id from the name ({p1.id})")
check(UP.save([p1]) and [(q.id, q.tweak_ids, q.builtin) for q in UP.load()[0]] == [(p1.id, ids[:2], False)],
      "saved and read back")
bad = [None, "x", {"name": ""}, {"name": "A", "tweak_ids": []}, {"name": "B", "tweak_ids": "game_mode"}]
check(all(UP.from_dict(d) is None for d in bad), "an entry that is not a preset is dropped")
q = UP.from_dict({"id": "minimal", "name": "Minimal", "tweak_ids": [ids[0], 5]})
check(q.id == "user_minimal" and q.tweak_ids == [ids[0]] and not q.builtin,
      "an imported id never shadows a built-in preset; only text ids")
merged = UP.merge([p1], [UP.from_dict({"name": "mein spiel", "tweak_ids": [ids[2]]}),
                         UP.from_dict({"name": "Zwei", "tweak_ids": [ids[0]]})])
check([m.id for m in merged] == ["user_mein_spiel", "user_zwei"] and merged[0].tweak_ids == [ids[2]],
      "the same name replaces in place, a new one is added")
check(preset_desc(p1, "en") == "Custom preset: 2 tweaks" and preset_desc(p1, "de") == "Eigenes Preset: 2 Tweaks"
      and preset_desc(get_preset("tier_minimal"), "en") != preset_desc(get_preset("tier_minimal"), "de"),
      "own presets: the description in the app's language (it was German only)")
probe = [sys.executable, "-c", "from core import user_presets as U; print(U.PRESETS_FILE)"]
r = subprocess.run(probe, cwd=ROOT, capture_output=True, text=True,
                   env=dict(os.environ, GOP_USER_PRESETS_FILE=str(Path(TMP) / "x.json")))
src_run = open(os.path.join(ROOT, "tests", "run_all_tests.py"), encoding="utf-8").read()
check(r.stdout.strip() == str(Path(TMP) / "x.json") and 'env["GOP_USER_PRESETS_FILE"]' in src_run,
      "tests get a presets file of their own (the battery sets it for every suite)")
r = subprocess.run(probe, cwd=ROOT, capture_output=True, text=True,
                   env={k: v for k, v in os.environ.items() if k != "GOP_USER_PRESETS_FILE"})
check(Path(r.stdout.strip()) == Path(ROOT) / "profiles" / "user_presets.json" and "profiles" in AU.SKIP_TOP,
      "the app keeps them in profiles/ — a folder the updater never touches")
UP.PRESETS_FILE.unlink()
UP.PRESETS_FILE.mkdir()                              # a "file" that can't be read
check(UP.load() == ([], False), "a file that can't be read: reported, not taken as empty")
UP.PRESETS_FILE.rmdir()

# ── 4. UI: optimizer (presets, re-check), apps page, diagnose, drift dialog ──
print("UI")
import tkinter as tk  # noqa: E402
from tkinter import messagebox  # noqa: E402

import customtkinter as ctk  # noqa: E402

from core import app_removal as AR  # noqa: E402
from core import services  # noqa: E402
from core.hardware import HardwareInfo  # noqa: E402
from core.tweak_runner import TweakRunner  # noqa: E402
from core.tweak_verifier import TweakVerifier  # noqa: E402

BOXES = []
real_mb = {n: getattr(messagebox, n) for n in ("askyesno", "showinfo", "showwarning", "showerror")}
ANSWER = {"yes": True}
messagebox.askyesno = lambda *a, **k: (BOXES.append(("askyesno",) + a), ANSWER["yes"])[1]
messagebox.showinfo = lambda *a, **k: BOXES.append(("showinfo",) + a)
messagebox.showwarning = lambda *a, **k: BOXES.append(("showwarning",) + a)
messagebox.showerror = lambda *a, **k: BOXES.append(("showerror",) + a)
VCALLS = []
real_verify = TweakVerifier.verify_all


def slow_verify(self, ids, exp):
    VCALLS.append(time.time())
    time.sleep(0.4)
    return {}


TweakVerifier.verify_all = slow_verify
root = ctk.CTk()
root.geometry("1200x850")
root.attributes("-alpha", 0.0)


def loop_until(cond, secs=10.0):
    """The real main loop (worker threads hand over with after()) until cond() or the time is up."""
    end = time.time() + secs

    def tick():
        if cond() or time.time() > end:
            root.quit()
        else:
            root.after(30, tick)
    root.after(30, tick)
    root.mainloop()
    return cond()


def texts(w):
    out = []
    for c in w.winfo_children():
        try:
            out.append(str(c.cget("text")))
        except Exception:
            pass
        out += texts(c)
    return out


real_dialog = ctk.CTkInputDialog
try:
    # -- optimizer: presets kept, replaced, imported, never written over an unreadable file
    UP.save([p1])
    runner = TweakRunner(log_dir=os.path.join(TMP, "tw"))
    runner.backup_registry = lambda label: None
    runner._run_ps = lambda cmd, timeout=60: (True, "ok")
    runner._applied = {ids[0]: "x", ids[1]: "y", ids[2]: "z"}
    from ui import tab_optimizer as TO
    opt = TO.OptimizerTab(root, runner, HardwareInfo(), profiles_dir=os.path.join(TMP, "p"), logs_dir=TMP)
    opt.pack(fill="both", expand=True)
    loop_until(lambda: not opt._verifying and VCALLS, 5)
    loop_until(lambda: False, 0.4)                   # the check's hand-over to the window lands
    check([q.id for q in opt._user_presets] == ["user_mein_spiel"] and opt._presets_ok
          and "Mein Spiel" in texts(opt._preset_inner),
          "a preset made before the restart is there again (and shown)")

    class Dialog:
        name = "Abend"

        def __init__(self, *a, **k):
            pass

        def get_input(self):
            return Dialog.name
    ctk.CTkInputDialog = Dialog
    opt._create_user_preset()
    disk = [q.id for q in UP.load()[0]]
    check(disk == ["user_mein_spiel", "user_abend"] and len(UP.load()[0][1].tweak_ids) == 3,
          "a new preset is saved right away (with every tweak active now)")
    Dialog.name = " mein spiel "
    n_boxes = len(BOXES)
    ANSWER["yes"] = False
    opt._create_user_preset()
    check(len(BOXES) == n_boxes + 1 and "gibt es schon" in BOXES[-1][2] and UP.load()[0][0].tweak_ids == ids[:2],
          "the same name: asked first — 'no' keeps the old one")
    ANSWER["yes"] = True
    opt._create_user_preset()
    check([q.id for q in opt._user_presets] == ["user_mein_spiel", "user_abend"]
          and len(UP.load()[0][0].tweak_ids) == 3, "'yes' replaces it in its place, no second one")
    opt._delete_user_preset(next(q for q in opt._user_presets if q.id == "user_abend"))
    check([q.id for q in UP.load()[0]] == ["user_mein_spiel"], "deleting saves too")
    opt.v_imp_tweaks.set(False)
    opt.v_imp_profiles.set(False)
    opt.v_imp_presets.set(True)
    imp = [{"id": "user_x", "name": "Import", "tweak_ids": [ids[0]]}, {"name": "", "tweak_ids": [ids[0]]}]
    for _ in range(2):
        opt._import_data = {"user_presets": imp}
        opt._do_import()
    check([q.id for q in UP.load()[0]] == ["user_mein_spiel", "user_import"],
          "an import is saved; importing twice gives no duplicates, broken entries are left out")
    # the file could not be read at the start: never written over with this session's presets
    UP.PRESETS_FILE.unlink()
    UP.PRESETS_FILE.mkdir()
    opt._user_presets, opt._presets_ok = UP.load()
    n_boxes = len(BOXES)
    Dialog.name = "Neu"
    opt._create_user_preset()
    check(UP.PRESETS_FILE.is_dir() and len(BOXES) == n_boxes + 1 and BOXES[-1][0] == "showwarning"
          and "Neustart" in BOXES[-1][2], "unreadable file: not written over, the user is told (lasts until restart)")
    UP.PRESETS_FILE.rmdir()
    UP.save([UP.from_dict({"name": "Alt", "tweak_ids": [ids[1]]})])
    Dialog.name = "Neu2"
    opt._create_user_preset()
    check([q.id for q in UP.load()[0]] == ["user_alt", "user_neu", "user_neu2"] and opt._presets_ok,
          "readable again: what is on disk is read first and kept, then saved")
    ctk.CTkInputDialog = real_dialog

    # -- a check asked for during a check runs after it
    loop_until(lambda: not opt._verifying, 5)
    n0 = len(VCALLS)
    opt._live_verify()
    opt._live_verify()                               # e.g. the drift dialog while the start check runs
    check(opt._verify_again, "asked during a check: noted")
    check(loop_until(lambda: len(VCALLS) == n0 + 2 and not opt._verifying and not opt._verify_again, 8),
          f"... and checked once more after it ({len(VCALLS) - n0} checks)")
    loop_until(lambda: False, 0.4)
    opt.destroy()
    TweakVerifier.verify_all = real_verify

    # -- drift dialog: the optimizer checks again afterwards
    import ui.main_window as MW

    class Runner:
        def __init__(self):
            self._applied = {"disable_telemetry": "x", "disable_bing_search": "y"}
            self.applied = []

        def forget(self, ids_):
            return [i for i in ids_ if self._applied.pop(i, None) is not None]

        def backup_registry(self, label):
            pass

        def apply(self, t):
            self.applied.append(t.id)
            return True, ""

    class Opt:
        _vars = {}
        rechecks = 0

        def _live_verify(self):
            Opt.rechecks += 1
    fake = tk.Frame(root)
    fake.runner, fake._tab_frames = Runner(), {"optimizer": Opt()}
    fake.set_status = lambda s: None
    MW.GameOptimizerWindow._handle_drift(fake, [], ["disable_bing_search"])
    check(Opt.rechecks == 1, "drift dialog, 'stop asking' only: the optimizer checks the state again")
    MW.GameOptimizerWindow._handle_drift(fake, ["disable_telemetry"], [])
    check(loop_until(lambda: Opt.rechecks == 2, 8) and fake.runner.applied == ["disable_telemetry"],
          "drift dialog, applied again: checked again once the re-apply is done")
    fake.destroy()

    # -- apps page: one read at a time; the install button comes back with winget
    from ui import apps_page as AP
    real_ap = {"admin": services.is_admin, "list": AR.list_apps, "have": WI.installed_ids, "exe": WI.winget_exe,
               "install": WI.install, "remove": AR.remove}
    gates = {"list": threading.Event(), "have": threading.Event()}
    calls = {"list": 0, "have": 0, "install": 0, "remove": 0}
    exe = {"v": None}

    def slow_list():
        calls["list"] += 1
        gates["list"].wait(5)
        return AR.parse_list('{"name": "Clipchamp.Clipchamp", "display": "Clipchamp"}')

    def slow_have(programs=None):
        calls["have"] += 1
        gates["have"].wait(5)
        return {"Valve.Steam"}
    try:
        AP.services.is_admin = lambda: True
        AP.app_removal.list_apps = slow_list
        AP.app_removal.remove = lambda name: (calls.__setitem__("remove", calls["remove"] + 1), (True, ""))[1]
        AP.winget_installer.installed_ids = slow_have
        AP.winget_installer.winget_exe = lambda: exe["v"]
        AP.winget_installer.install = lambda pid, on_line=None: (calls.__setitem__("install", calls["install"] + 1),
                                                                (True, ""))[1]
        page = AP.AppsPage(root)
        page.pack(fill="both", expand=True)
        page.on_show()
        page._refresh()
        page._refresh()                              # a double click on Refresh
        loop_until(lambda: False, 0.3)
        check(calls["list"] == 1 and page._loading["apps"], f"a double click on Refresh: one read ({calls['list']})")
        check(str(page.btn_refresh.cget("state")) == "disabled" and str(page.btn_remove.cget("state")) == "disabled",
              "while the list is read: Refresh and Remove are off")
        page.tree_apps.selection_set([])
        n_boxes = len(BOXES)
        page._remove()
        check(len(BOXES) == n_boxes and calls["remove"] == 0, "removing while the list is read: refused")
        gates["list"].set()
        check(loop_until(lambda: page._loaded["apps"] and not page._loading["apps"], 5)
              and str(page.btn_remove.cget("state")) == "normal" and str(page.btn_refresh.cget("state")) == "normal",
              "read: the buttons work again")
        page._show_view("install")                   # winget missing
        loop_until(lambda: False, 0.3)
        check(str(page.btn_install.cget("state")) == "disabled" and calls["have"] == 1,
              "install view, no winget: Install off while reading")
        gates["have"].set()
        loop_until(lambda: page._loaded["install"] and not page._loading["install"], 5)
        log = ""
        loop_until(lambda: "winget" in page.log_install.txt.get("1.0", "end"), 2)
        log = page.log_install.txt.get("1.0", "end")
        check(str(page.btn_install.cget("state")) == "disabled" and "App-Installer" in log,
              "no winget: Install stays off, the log says what to do")
        exe["v"] = "winget.exe"                      # App Installer installed meanwhile
        gates["have"].clear()
        page._refresh()
        loop_until(lambda: False, 0.3)
        page.tree_inst.selection_set(["7zip.7zip"])
        n_boxes = len(BOXES)
        page._install()
        check(len(BOXES) == n_boxes and calls["install"] == 0, "installing while the list is read: refused")
        gates["have"].set()
        check(loop_until(lambda: not page._loading["install"], 5) and calls["have"] == 2
              and str(page.btn_install.cget("state")) == "normal",
              "winget installed later: 'Refresh' frees the Install button again")
        page.destroy()
        AP.services.is_admin = lambda: False
        page3 = AP.AppsPage(root)
        page3.pack(fill="both", expand=True)
        page3.on_show()
        loop_until(lambda: page3._loaded["apps"], 5)
        check(all(str(b.cget("state")) == "disabled" for b in (page3.btn_remove, page3.btn_install)),
              "without administrator rights the buttons stay off after reading")
        page3.destroy()
    finally:
        AP.services.is_admin = real_ap["admin"]
        AP.app_removal.list_apps, AP.app_removal.remove = real_ap["list"], real_ap["remove"]
        AP.winget_installer.installed_ids, AP.winget_installer.winget_exe = real_ap["have"], real_ap["exe"]
        AP.winget_installer.install = real_ap["install"]

    # -- diagnose: a critical finding makes the summary red
    from ui import tab_diagnose as TD
    real_gen = TD.health_report.generate
    try:
        diag = TD.DiagnoseTab(root)
        diag.pack(fill="both", expand=True)
        for sev, want in ((HR.CRITICAL, "error"), (HR.WARN, "warning"), (HR.OK, "success")):
            items = [HR.HealthItem("k", "Test", 1 if sev != HR.OK else 0, "", sev, "n")]
            summ = {HR.CRITICAL: "⚠ 1 kritische Auffälligkeit(en), 0 Warnung(en) — bitte prüfen.",
                    HR.WARN: "1 Warnung(en) in den letzten 30 Tagen.", HR.OK: "✓ Keine relevanten Fehler"}[sev]
            TD.health_report.generate = lambda i=items, s=summ: HR.HealthReport(ok=True, items=i, summary=s, status=[])
            rec = []
            orig = diag.health_log.append
            diag.health_log.append = lambda msg, tag="info", o=orig: (rec.append((msg, tag)), o(msg, tag))
            diag._run_health()
            loop_until(lambda: any(m == summ for m, _t in rec), 5)
            tag = next((t for m, t in rec if m == summ), None)
            diag.health_log.append = orig
            check(tag == want, f"health report summary, {sev}: {tag}")
        diag.destroy()
    finally:
        TD.health_report.generate = real_gen
finally:
    ctk.CTkInputDialog = real_dialog
    TweakVerifier.verify_all = real_verify
    for n, f in real_mb.items():
        setattr(messagebox, n, f)
    try:
        root.destroy()
    except Exception:
        pass

# ── 5. Paint AI: the documented policies only ────────────────────────────────
print("Paint AI")
t = T.get_by_id("disable_paint_ai")
check(T._PAINT_AI_VALUES == ("DisableCocreator", "DisableGenerativeFill", "DisableImageCreator"),
      "the three policies Microsoft documents (Policy CSP WindowsAI: Cocreator, generative fill, Image Creator)")
spec = reg_spec("disable_paint_ai")
check(spec is not None and [n for n, _w in spec[3]] == list(T._PAINT_AI_VALUES),
      "the status check reads exactly the values the tweak sets (one list for both)")
check(not any(v in t.ps_command for v in T._PAINT_AI_OLD) and all(v in t.revert_cmd for v in T._PAINT_AI_OLD),
      "the two undocumented values are no longer set; the revert still deletes them")
check("keine Richtlinie" in t.desc and "no policy" in TWEAK_DESC_EN["disable_paint_ai"],
      "the text says erase / remove background have no policy")
SCR = r"Software\GameOptimizerPro-Test46"
KEY = "HKCU\\" + SCR + "\\Paint"
try:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SCR + "\\Paint") as kk:
        for v in T._PAINT_AI_OLD:                        # what an earlier build left
            winreg.SetValueEx(kk, v, 0, winreg.REG_DWORD, 1)
    rc, _o, err = ps(t.ps_command.replace(T._PAINT_AI_KEY, KEY))

    def vals():
        out = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCR + "\\Paint") as kk:
                i = 0
                while True:
                    try:
                        n, v, _t = winreg.EnumValue(kk, i)
                    except OSError:
                        break
                    out[n] = v
                    i += 1
        except OSError:
            pass
        return out
    after = vals()
    check(rc == 0 and all(after.get(v) == 1 for v in T._PAINT_AI_VALUES), f"apply on a scratch key: the three set ({err[:80]})")
    vcmd = VERIFY_MAP["disable_paint_ai"].replace("HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Paint",
                                                  "HKCU:\\" + SCR + "\\Paint")
    check(ps(vcmd)[1] == "1", "the status check reads it as active")
    rc, _o, _e = ps(t.revert_cmd.replace(T._PAINT_AI_KEY, KEY))
    check(rc == 0 and vals() == {}, "revert: all five gone, the two old ones too")
finally:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCR + "\\Paint")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCR)
    except OSError:
        pass

# ── 6. README / CHANGELOG: the same test count ──────────────────────────────
print("docs")
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
readme_de = open(os.path.join(ROOT, "README.de.md"), encoding="utf-8").read()
changelog = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
m_en = re.search(r"(\d+) automated checks in (\d+) test suites", readme)
m_de = re.search(r"(\d+) automatische Prüfungen in (\d+) Test-Suiten", readme_de)
m_cl = re.search(r"(\d+) checks in (\d+) suites", changelog)
sys.path.insert(0, os.path.join(ROOT, "tests"))
n_suites = len(re.search(r"TESTS = \[(.*?)\]", src_run, re.S).group(1).split(","))
nums = [m.groups() if m else None for m in (m_en, m_de, m_cl)]
check(all(nums) and len(set(nums)) == 1 and int(nums[0][1]) == n_suites,
      f"README (EN/DE) and CHANGELOG name the same test count, suites = the runner's ({nums}, {n_suites})")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
