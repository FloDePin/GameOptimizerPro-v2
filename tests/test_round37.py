"""Round 37 — audit 2026-10-23 + proposals: the app's JSON state safe against locks, crashes and
broken files (settings, applied tweaks, services), one error log, notifications through the tray
icon, the driver-reset checks without PowerShell, the app's GPU loads in a Windows job, plain
registry checks through winreg, the network test in parallel. Reads the real System log and
registry (read only); writes only temp files and a scratch key HKCU\\Software\\GameOptimizerPro-Test-r37."""
import json
import os
import subprocess
import sys
import tempfile
import threading
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


TMP = Path(tempfile.mkdtemp(prefix="gop_r37_"))
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = TMP / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"
from core import safe_json  # noqa: E402
from core import errlog  # noqa: E402

errlog.install(TMP / "logs")
ERRLOG = TMP / "logs" / "app_errors.log"


def lock_exclusive(path):
    """Open a file with no sharing at all (like a virus scanner in the middle of a scan)."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    h = k.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)     # GENERIC_READ, no share
    return h, (lambda: k.CloseHandle(h))


# ── 1) safe_json ─────────────────────────────────────────────────────────────
print("safe JSON files")
f = TMP / "a.json"
check(safe_json.read(f, {"d": 1}) == {"d": 1}, "missing: the default")
check(safe_json.write(f, {"x": 1}) and json.loads(f.read_text(encoding="utf-8")) == {"x": 1}
      and not (TMP / "a.json.tmp").exists(), "written atomically, no temp file left")
check(safe_json.write(f, {"x": 2}) and json.loads((TMP / "a.json.bak").read_text(encoding="utf-8")) == {"x": 1},
      "the last good content kept as .bak")
f.write_text('{"x": 2, broken', encoding="utf-8")
got = safe_json.read(f, {})
broken = list(TMP.glob("a.json.broken-*"))
check(got == {"x": 1} and json.loads(f.read_text(encoding="utf-8")) == {"x": 1} and len(broken) == 1,
      f"broken file (power cut): the last good copy restored, the broken one kept aside: {got}")
check("broken" in ERRLOG.read_text(encoding="utf-8") and "restored from its last good copy" in ERRLOG.read_text(encoding="utf-8"),
      "... and noted in logs/app_errors.log")
g = TMP / "b.json"
g.write_text("not json", encoding="utf-8")
try:
    safe_json.read(g, {}, strict=True)
    raised = False
except safe_json.Unreadable:
    raised = True
check(raised and not g.exists(), "broken without a good copy: strict readers get Unreadable (the file kept aside)")
check(safe_json.read(g, {"d": 0}) == {"d": 0}, "... a normal reader the default")
if os.name == "nt":
    h = TMP / "locked.json"
    safe_json.write(h, {"keep": True})
    hd, close = lock_exclusive(h)
    t0 = time.time()
    try:
        safe_json.read(h, {}, strict=True)
        raised = False
    except safe_json.Unreadable:
        raised = True
    took = time.time() - t0
    check(raised and 0.8 < took < 5, f"locked by another process: a few tries ({took:.1f} s), then Unreadable — "
                                     f"never an empty result for a writer")
    ok = safe_json.write(h, {"new": 1})
    check(not ok and not (TMP / "locked.json.tmp").exists(), "... a write fails cleanly (no temp file left)")
    close()
    check(safe_json.read(h, {}) == {"keep": True}, "after the lock: the old content is intact")
    # the lock goes while the reader still tries: it gets the content
    hd, close = lock_exclusive(h)
    threading.Timer(0.3, close).start()
    check(safe_json.read(h, {}, strict=True) == {"keep": True}, "a lock that goes within a second: read fine")

# ── 2) settings: never wiped ──────────────────────────────────────────────────
print("settings")
app_settings.set("a", 1)
app_settings.set("b", 2)
check(app_settings.load() == {"a": 1, "b": 2}, "normal: every key kept")
_real = safe_json.read


def _unreadable(*a, **k):
    if k.get("strict"):
        raise safe_json.Unreadable("test")
    return {}


safe_json.read = _unreadable
try:
    r = app_settings.set("c", 3)
finally:
    safe_json.read = _real
check(r is False and app_settings.load() == {"a": 1, "b": 2},
      "settings not readable for a moment: the new value is not saved — and NOTHING else is wiped "
      "(it used to write {c: 3} over everything)")
errs = []


def hammer(i):
    try:
        for n in range(30):
            app_settings.set(f"k{i}", n)
            app_settings.get("a")
    except Exception as e:
        errs.append(e)


ths = [threading.Thread(target=hammer, args=(i,)) for i in range(4)]
[t.start() for t in ths]
[t.join() for t in ths]
fin = app_settings.load()
check(not errs and fin.get("a") == 1 and all(fin.get(f"k{i}") == 29 for i in range(4)),
      f"4 threads setting and reading at once: no error, nothing lost: {errs[:1]}")

# ── 3) applied tweaks: the app never forgets what it applied ─────────────────
print("applied tweaks")
from core.tweak_runner import TweakRunner  # noqa: E402
from core.tweaks import ALL_TWEAKS, get_by_id  # noqa: E402
T1, T2, T3 = [t.id for t in ALL_TWEAKS if t.revert_cmd and not t.id.startswith(("dns_", "power_"))][:3]
tl = TMP / "tw"
tl.mkdir()
state = tl / "applied_tweaks.json"
state.write_text(json.dumps({T1: "2026-10-01T10:00:00", T2: "2026-10-01T10:00:00"}), encoding="utf-8")
if os.name == "nt":
    hd, close = lock_exclusive(state)
    tr = TweakRunner(str(tl))
    close()
    check(tr._state_ok is False and tr._applied == {}, "state file locked at start: starts empty, flagged")
    tr._run_ps = lambda cmd, timeout=60: (True, "ok")
    tw = get_by_id(T3)
    tr.apply(tw)
    disk = json.loads(state.read_text(encoding="utf-8"))
    check(set(disk) == {T1, T2, tw.id} and tr._state_ok,
          f"the next save reads it again and MERGES — the tweaks applied before are still the app's: {sorted(disk)}")
    tr.revert(get_by_id(T2))
    disk = json.loads(state.read_text(encoding="utf-8"))
    check(set(disk) == {T1, tw.id}, "a revert is still recorded")
    hd, close = lock_exclusive(state)
    tr2 = TweakRunner(str(tl))
    tr2._run_ps = lambda cmd, timeout=60: (True, "ok")
    tr2.revert(get_by_id(T1))                         # while the file is still locked
    close()
    tr2.apply(tw)
    disk = json.loads(state.read_text(encoding="utf-8"))
    check(set(disk) == {tw.id}, f"reverted while the file was locked: it does not come back with the merge: {sorted(disk)}")
state.write_text("{broken", encoding="utf-8")
(tl / "applied_tweaks.json.bak").write_text(json.dumps({T1: "x"}), encoding="utf-8")
tr3 = TweakRunner(str(tl))
check(tr3._state_ok and tr3._applied == {T1: "x"}, "a broken state file: the last good copy")

# ── 4) services: the original start types are not lost ───────────────────────
print("services")
import core.services as SV  # noqa: E402
SV.STATE_FILE = TMP / "services_state.json"
SV.STATE_FILE.write_text(json.dumps({"SysMain": {"start": 2, "delayed": False}}), encoding="utf-8")
calls = []
_rs, _ps, _cn = SV._read_start, SV._run_ps, SV._check_names
SV._read_start = lambda n: (3, False)
SV._run_ps = lambda script, *a, **k: (calls.append(script), "WSearch|OK|")[1]
SV._check_names = lambda names: list(names)
safe_json.read = _unreadable
try:
    res = SV.disable(["WSearch"])
finally:
    safe_json.read = _real
    SV._read_start, SV._run_ps, SV._check_names = _rs, _ps, _cn
check(res["WSearch"][0] is False and "nicht lesbar" in res["WSearch"][1] and not calls
      and json.loads(SV.STATE_FILE.read_text(encoding="utf-8")) == {"SysMain": {"start": 2, "delayed": False}},
      "list of changed services not readable: nothing is changed, the originals stay recorded")

# ── 5) the error log ──────────────────────────────────────────────────────────
print("error log")


def boom():
    raise ValueError("thread boom r37")


th = threading.Thread(target=boom, name="r37-worker")
th.start()
th.join()
txt = ERRLOG.read_text(encoding="utf-8")
check("unhandled in thread r37-worker" in txt and "ValueError: thread boom r37" in txt,
      "an exception in a worker thread lands in logs/app_errors.log (pythonw has no console)")
import tkinter as tk  # noqa: E402
root = tk.Tk()
root.withdraw()
errlog.tk_hook(root)
_stderr = sys.stderr
sys.stderr = open(os.devnull, "w")
try:
    root.after(0, lambda: (_ for _ in ()).throw(KeyError("tk boom r37")))
    root.update()
    root.after(10)
    root.update()
finally:
    sys.stderr.close()
    sys.stderr = _stderr
root.destroy()
txt = ERRLOG.read_text(encoding="utf-8")
check("Tk callback" in txt and "tk boom r37" in txt, "... and one in a button's / timer's handler (Tk)")
big = TMP / "logs" / "rot.log"
errlog._file = big
big.write_text("x" * (errlog.MAX_BYTES + 10), encoding="utf-8")
errlog.note("after the limit")
check(big.stat().st_size < 200 and (TMP / "logs" / "rot.log.1").exists(), "at most two files of MAX_BYTES")
errlog._file = ERRLOG

# ── 6) notifications through the tray icon ────────────────────────────────────
print("notifications")
from core import notify  # noqa: E402
shown, fell = [], []


class Tray:
    visible = True

    def notify(self, msg, title=None):
        shown.append((title, msg))


notify.set_tray(Tray())
check(notify.show("T", "M", fallback=lambda: fell.append(1)) and shown == [("T", "M")] and not fell,
      "with the tray icon: shown through it, no PowerShell")
notify.set_tray(None)
check(not notify.show("T", "M", fallback=lambda: fell.append(1)) and fell == [1], "no tray icon: the old toast")


class BadTray(Tray):
    def notify(self, msg, title=None):
        raise OSError("no shell")


notify.set_tray(BadTray())
fell.clear()
notify.show("T", "M", fallback=lambda: fell.append(1))
check(fell == [1], "the tray icon fails: the old toast")
notify.set_tray(None)
from core import gpu_flight as GF  # noqa: E402
_toast = GF._toast_ps
GF._toast_ps = lambda t, m: fell.append(("ps", t))
notify.set_tray(Tray())
shown.clear()
GF.toast("GPU", "hang")
GF._toast_ps = _toast
notify.set_tray(None)
check(shown == [("GPU", "hang")] and ("ps", "GPU") not in fell, "the watchdog's notification uses the tray icon")

# ── 7) the network test in parallel ───────────────────────────────────────────
print("network test")
import core.network_test as NTW  # noqa: E402
_ping, _gw = NTW.ping, NTW.get_default_gateway
NTW.ping = lambda label, host, count=10: (time.sleep(0.4), NTW.PingResult(label=label, host=host, reachable=True))[1]
NTW.get_default_gateway = lambda: "192.168.0.1"
t0 = time.time()
res = NTW.run_all(3)
took = time.time() - t0
check(took < 1.0 and [r.label for r in res] == ["Gateway (Router)", "Cloudflare", "Google DNS"],
      f"three targets at once ({took:.1f} s, not 1.2 s), the order kept")
NTW.get_default_gateway = lambda: None
res = NTW.run_all(3)
check([r.label for r in res] == ["Gateway (Router)", "Cloudflare", "Google DNS"] and res[0].error,
      "no gateway: said, the public targets still tested")
NTW.ping, NTW.get_default_gateway = _ping, _gw

if os.name == "nt":
    # ── 8) the app's GPU loads end with the app (job object) ──────────────────
    print("job object")
    parent = (
        "import sys, subprocess, os\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "from core import proc_job\n"
        "N = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], **N)\n"
        "b = proc_job.bind(c)\n"
        "u = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(6)'], **N)\n"
        "print(c.pid, b, u.pid, flush=True)\n"
        "os._exit(0)\n")
    r = subprocess.run([sys.executable, "-c", parent], capture_output=True, text=True, timeout=60)
    pid, bound, upid = r.stdout.split()
    time.sleep(1.5)
    import psutil  # noqa: E402
    check(bound == "True" and not psutil.pid_exists(int(pid)) and psutil.pid_exists(int(upid)),
          "a bound load ends the moment the app's process ends (crash / kill too); an unbound process "
          "(Afterburner, the updater, the restart) lives on")
    src = "".join(open(os.path.join(ROOT, p), encoding="utf-8").read() for p in
                  ("core/furmark.py", "core/hardness_test.py", "core/nvtune_tuner.py", "ui/tab_stress.py"))
    check(src.count("proc_job.bind(") == 5 and "proc_job" not in open(os.path.join(ROOT, "core", "updater.py"),
                                                                        encoding="utf-8").read()
          and "proc_job" not in open(os.path.join(ROOT, "core", "nvtune_core.py"), encoding="utf-8").read(),
          "bound: the tuner's worker + encoder load, the hardness test's loads, a benchmark's FurMark, the "
          "stress page's internal test — never the updater or Afterburner")

    # ── 9) driver resets read natively ────────────────────────────────────────
    print("event log without PowerShell")
    import core.gpu_watchdog as W  # noqa: E402
    from datetime import datetime  # noqa: E402
    since = time.time() - 30 * 86400
    t0 = time.time()
    nat = W.read_events(since)
    tn = time.time() - t0
    ps = W._PS.format(since=datetime.fromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%S"))
    rr = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                        capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    pw = []
    for line in (rr.stdout or "").splitlines():
        try:
            a, b = line.strip().split("|")
            pw.append((float(a), int(b)))
        except ValueError:
            pass
    check(nat == sorted(pw) and tn < 1.0,
          f"the watchdog's events (30 days, real System log): native = Get-WinEvent ({len(nat)} events, "
          f"{tn * 1000:.0f} ms)")
    from core.crash_recovery import CrashRecovery  # noqa: E402
    cr = CrashRecovery(str(TMP / "cr"))
    _run = subprocess.run
    spawned = []
    subprocess.run = lambda *a, **k: (spawned.append(a), _run(*a, **k))[1]
    try:
        hit = cr.check_tdr_since(30 * 86400)
    finally:
        subprocess.run = _run
    ref = any(i in (13, 14, 4101) for _t, i in pw)
    check(hit == ref and not spawned, f"the tuner's driver-reset check: same answer ({hit}), no powershell.exe started")

    # ── 10) plain registry checks through winreg ──────────────────────────────
    print("registry checks without PowerShell")
    from core import tweak_verifier as TV  # noqa: E402
    ids = [t for t in TV.VERIFY_MAP if TV.reg_spec(t) is not None and t not in TV.SLOW_CHECKS]
    direct = {t: TV.reg_check(t) for t in ids}
    psr = TV.TweakVerifier()._run_batch(ids, {t: True for t in ids}, timeout=60)
    bad = [t for t in ids if direct[t] is None or psr[t].error or direct[t] != psr[t].actual]
    check(len(ids) >= 45 and not bad, f"{len(ids)} plain registry checks: winreg = PowerShell on this system "
                                      f"(read only), differences: {bad}")
    import winreg  # noqa: E402
    KEY = r"Software\GameOptimizerPro-Test-r37"
    try:
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY)
        winreg.SetValueEx(k, "D1", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "Dmax", 0, winreg.REG_DWORD, 0xFFFFFFFF)
        winreg.SetValueEx(k, "S", 0, winreg.REG_SZ, "Deny")
        winreg.SetValueEx(k, "N", 0, winreg.REG_SZ, "506")
        winreg.SetValueEx(k, "E", 0, winreg.REG_EXPAND_SZ, "%SystemRoot%")
        winreg.SetValueEx(k, "B", 0, winreg.REG_BINARY, b"\x01")
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, ".None")
        winreg.CloseKey(k)
        sysroot = os.environ.get("SystemRoot", "C:\\Windows")
        cases = {
            "c1": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name D1 -EA SilentlyContinue).D1; if($v -eq 1){{"1"}}else{{"0"}}',
            "c2": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name D1 -EA SilentlyContinue).D1; if($v -eq 0){{"1"}}else{{"0"}}',
            "c3": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name Gone -EA SilentlyContinue).Gone; if($v -eq 0){{"1"}}else{{"0"}}',
            "c4": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name Gone -EA SilentlyContinue).Gone; if($v -ne 0){{"1"}}else{{"0"}}',
            "c5": f'$v=(Get-ItemProperty "HKCU:\\{KEY}\\Nope" -Name D1 -EA SilentlyContinue).D1; if($v -eq 1){{"1"}}else{{"0"}}',
            "c6": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name Dmax -EA SilentlyContinue).Dmax; if($v -eq 4294967295){{"1"}}else{{"0"}}',
            "c7": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name Dmax -EA SilentlyContinue).Dmax; if($v -eq -1){{"1"}}else{{"0"}}',
            "c8": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name S -EA SilentlyContinue).S; if($v -eq "deny"){{"1"}}else{{"0"}}',
            "c9": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name N -EA SilentlyContinue).N; if($v -eq "506"){{"1"}}else{{"0"}}',
            "c10": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name N -EA SilentlyContinue).N; if($v -eq 506){{"1"}}else{{"0"}}',
            "c11": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name E -EA SilentlyContinue).E; if($v -eq "{sysroot}"){{"1"}}else{{"0"}}',
            "c12": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name D1 -EA SilentlyContinue).D1; if($v -eq "1"){{"1"}}else{{"0"}}',
            "c13": f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name "(Default)" -EA SilentlyContinue)."(Default)"; if($v -eq ".None"){{"1"}}else{{"0"}}',
            "c14": f"$k=Get-ItemProperty 'HKCU:\\{KEY}' -EA SilentlyContinue; if($k -and $k.D1 -eq 1 -and $k.Dmax -eq -1){{\"1\"}}else{{\"0\"}}",
            "c15": f"$k=Get-ItemProperty 'HKCU:\\{KEY}\\Nope' -EA SilentlyContinue; if($k -and $k.D1 -eq 1){{\"1\"}}else{{\"0\"}}",
            "c16": f"$k=Get-ItemProperty 'HKCU:\\{KEY}' -EA SilentlyContinue; if($k -and $k.D1 -eq 1 -and $k.Gone -eq 1){{\"1\"}}else{{\"0\"}}",
        }
        binary = f'$v=(Get-ItemProperty "HKCU:\\{KEY}" -Name B -EA SilentlyContinue).B; if($v -eq 1){{"1"}}else{{"0"}}'
        saved = dict(TV.VERIFY_MAP)
        TV.VERIFY_MAP.clear()
        TV.VERIFY_MAP.update(cases)
        TV.VERIFY_MAP["cbin"] = binary
        TV.reg_spec.cache_clear()
        try:
            direct = {t: TV.reg_check(t) for t in cases}
            psr = TV.TweakVerifier()._run_batch(list(cases), {t: True for t in cases}, timeout=60)
            diff = {t: (direct[t], psr[t].actual, psr[t].error) for t in cases
                    if direct[t] is None or psr[t].error or direct[t] != psr[t].actual}
            check(not diff and all(TV.reg_spec(t) for t in cases),
                  f"scratch key, 16 shapes (missing key / value, -ne, 0xFFFFFFFF is 4294967295, not -1, text in "
                  f"any case, a number as text, an expandable string, the default value, several values): "
                  f"winreg = PowerShell — differences: {diff}")
            check(TV.reg_check("cbin") is None, "a binary value: left to PowerShell (it compares it differently)")
            _run = TV.subprocess.run
            ran = []
            TV.subprocess.run = lambda *a, **k: (ran.append(1), _run(*a, **k))[1]
            try:
                out = TV.TweakVerifier().verify_all(list(cases), {t: True for t in cases})
            finally:
                TV.subprocess.run = _run
            check(not ran and len(out) == len(cases), "only plain registry checks: no PowerShell at all")
        finally:
            TV.VERIFY_MAP.clear()
            TV.VERIFY_MAP.update(saved)
            TV.reg_spec.cache_clear()
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
        except OSError:
            pass

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
