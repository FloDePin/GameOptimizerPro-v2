"""Round 48 — faster and sturdier (v1's speed / robustness work, done for v2).

  * The status check: the telemetry tasks and the defrag task through the Task Scheduler's COM interface
    (Get-ScheduledTask: 3.7 s for twelve tasks), adapters / LSO / RSS / DNS straight from CIM (the NetAdapter
    and DnsClient modules took ~0.4 s each to load) — the same answers as before, read on this PC; the slow
    checks run next to the fast ones, which are spread over a few PowerShell processes. 5.7 s -> under 1 s here.
  * Start: a WMI that doesn't answer no longer keeps the whole start waiting (hardware detection with a time
    limit, the result filled in when WMI answers); a second start while the first one still loads says so.

Not windowed: one hidden (never mapped) Tk window in a child process for the window search. Read only."""
import os
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


TMP = tempfile.mkdtemp(prefix="gop_r48_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

from core import hardware as H  # noqa: E402
from core import tweak_verifier as TV  # noqa: E402
from core import tweaks as T  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="oem", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


# ── 1. Status checks: no slow modules, the same answers ──────────────────────
print("status checks without the slow modules")
slow_cmds = ("Get-ScheduledTask", "Get-NetAdapter", "Get-DnsClientServerAddress", "Get-NetAdapterLso",
             "Get-NetAdapterRss", "Get-NetTCPSetting")
users = {t: [c for c in slow_cmds if c in v] for t, v in TV.VERIFY_MAP.items()}
check(not any(users.values()), f"no status check loads ScheduledTasks / NetAdapter / DnsClient any more {[t for t, u in users.items() if u]}")
check("Schedule.Service" in TV.VERIFY_MAP["disable_telemetry_tasks"] and "Schedule.Service" in TV.VERIFY_MAP["disable_scheduled_defrag"]
      and all("MSFT_NetAdapter" in TV.VERIFY_MAP[t] for t in ("disable_nagle", "disable_lso", "enable_rss", "dns_cloudflare")),
      "tasks through the Task Scheduler's COM interface, adapters / DNS straight from CIM")
check(T.get_by_id("disable_telemetry_tasks").ps_command.startswith(T._TELEMETRY_TASKS_PS)
      and T._TELEMETRY_TASKS_COM_PS.startswith(T._TELEMETRY_TASKS_PS.split("$found=")[0]),
      "the check reads exactly the task list the tweak works on")
if os.name == "nt":
    old_tasks = T._TELEMETRY_TASKS_PS + "($found | ForEach-Object { $_.TaskName + '=' + ($(if(\"$($_.State)\" -eq 'Disabled'){'off'}else{'on'})) } | Sort-Object) -join ','"
    new_tasks = T._TELEMETRY_TASKS_COM_PS + "($found | ForEach-Object { $_.Name + '=' + ($(if($_.Enabled){'on'}else{'off'})) } | Sort-Object) -join ','"
    def timed(script):
        """(output, the faster of two runs) — a first run can meet a busy Task Scheduler / CIM service"""
        best, out = 99.0, ""
        for _ in range(2):
            t = time.time()
            out = ps(script)[1]
            best = min(best, time.time() - t)
        return out, best
    a, ta = timed(old_tasks)
    b, tb = timed(new_tasks)
    check(a == b and a != "", f"telemetry tasks: the same tasks and states ({len(a.split(','))}) — {ta:.1f} s before, {tb:.1f} s now")
    old_net = ("$u=@(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' }); "
               "(@($u | ForEach-Object { $_.Name + '/' + $_.InterfaceIndex + '/' + \"$($_.InterfaceGuid)\".ToUpper() }) -join ',') + ' | ' + "
               "(@(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' } | ForEach-Object { $_.Name }) -join ',') + ' | ' + "
               "(@($u | ForEach-Object { $l=Get-NetAdapterLso -Name $_.Name -EA SilentlyContinue; if($l){ $_.Name + '=' + [bool]($l.IPv4Enabled -or $l.IPv6Enabled) } }) -join ',') + ' | ' + "
               "(@($u | ForEach-Object { $r=Get-NetAdapterRss -Name $_.Name -EA SilentlyContinue; if($r){ $_.Name + '=' + [bool]$r.Enabled } }) -join ',') + ' | ' + "
               "(@($u | ForEach-Object { $i=$_.InterfaceIndex; foreach($f in 'IPv4','IPv6'){ $f + '=' + ((Get-DnsClientServerAddress -InterfaceIndex $i -AddressFamily $f).ServerAddresses -join ';') } }) -join ',')")
    new_net = (T._UP_ADAPTERS_CIM_PS + T._DNS_CIM_PS +
               "(@($na | ForEach-Object { $_.Name + '/' + $_.InterfaceIndex + '/' + \"$($_.InterfaceGuid)\".ToUpper() }) -join ',') + ' | ' + "
               f"(@({T._PHYS_UP} | ForEach-Object {{ $_.Name }}) -join ',') + ' | ' + "
               "(@(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetAdapterLsoSettingData | Where-Object { @($na.Name) -contains $_.Name } | ForEach-Object { $_.Name + '=' + [bool]($_.IPv4Enabled -or $_.IPv6Enabled) }) -join ',') + ' | ' + "
               "(@(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetAdapterRssSettingData | Where-Object { @($na.Name) -contains $_.Name } | ForEach-Object { $_.Name + '=' + [bool]$_.Enabled }) -join ',') + ' | ' + "
               "(@($na | ForEach-Object { $i=$_.InterfaceIndex; foreach($f in @(@('IPv4',2),@('IPv6',23))){ $f[0] + '=' + ((@($dns | Where-Object { $_.InterfaceIndex -eq $i -and $_.AddressFamily -eq $f[1] }) | ForEach-Object { $_.ServerAddresses }) -join ';') } }) -join ',')")
    a, ta = timed(old_net)
    b, tb = timed(new_net)
    check(a == b and a.count("|") == 4, f"adapters, physical ones, LSO, RSS, DNS v4 / v6: the same on this PC — {ta:.1f} s before, {tb:.1f} s now")
    if a != b:
        print("     before:", a[:300], "\n     now:   ", b[:300])

# ── 2. The batches side by side ──────────────────────────────────────────────
print("the batches side by side")
ids = list(TV.VERIFY_MAP)[:10]
parts = TV.spread_parts(ids, 3)
check(sorted(sum(parts, [])) == sorted(ids) and len(parts) == 3 and parts[0] == [ids[0], ids[3], ids[6], ids[9]],
      "spread round-robin into 3 parts, every id once, order kept")
big = list(TV.VERIFY_MAP)
check(all(len("\n".join(TV._check_line(t) for t in p)) < TV.MAX_SCRIPT_CHARS for p in TV.spread_parts(big)),
      "every part stays below the command-line limit")
starts = []
real_part = TV.TweakVerifier._run_part


def fake_part(self, ids_, expected, timeout):
    starts.append(time.time())
    time.sleep(0.6)
    return {i: TV.VerifyResult(i, False, True, True, "") for i in ids_}


TV.TweakVerifier._run_part = fake_part
real_reg = TV.reg_check
TV.reg_check = lambda tid: None                     # everything through the (simulated) PowerShell parts
try:
    t0 = time.time()
    res = TV.TweakVerifier().verify_all(big, {i: False for i in big})
    took = time.time() - t0
finally:
    TV.TweakVerifier._run_part = real_part
    TV.reg_check = real_reg
check(len(res) == len(big) and len(starts) >= 4 and took < 1.5 and max(starts) - min(starts) < 0.3,
      f"{len(starts)} parts (slow ones included) started together: {took:.1f} s instead of {0.6 * len(starts):.1f} s one after the other")
if os.name == "nt":
    t0 = time.time()
    real = TV.TweakVerifier().verify_all(big, {i: False for i in big})
    took = time.time() - t0
    check(len(real) == len(big) and took < 4.0, f"the real status check on this PC: {len(real)} checks in {took:.1f} s (before: 5.7 s)")

# ── 3. Start: WMI that hangs, a second start ─────────────────────────────────
print("start")
real_detect = H.detect
notes = []
import core.errlog as EL  # noqa: E402
real_note = EL.note
EL.note = lambda text: notes.append(text)
try:
    H.detect = lambda: (time.sleep(2.0), H.HardwareInfo(cpu_name="Late CPU", gpu_name="Late GPU", os_build=26300))[1]
    t0 = time.time()
    hw = H.detect_safe(timeout=0.4)
    took = time.time() - t0
    check(took < 1.0 and hw.gpu_name != "Late GPU" and (os.name != "nt" or hw.os_build >= 10240),
          f"WMI doesn't answer: the start goes on after the time limit ({took:.1f} s) with what the registry knows (build {hw.os_build})")
    check(any("WMI did not answer" in n for n in notes), "... and it is noted in the error log")
    end = time.time() + 5
    while hw.gpu_name != "Late GPU" and time.time() < end:
        time.sleep(0.05)
    check(hw.gpu_name == "Late GPU" and hw.cpu_name == "Late CPU", "... the full result is filled into the same object when WMI answers")
    H.detect = lambda: H.HardwareInfo(cpu_name="Quick CPU")
    check(H.detect_safe(timeout=5).cpu_name == "Quick CPU", "WMI answers in time: its result as before")
finally:
    H.detect = real_detect
    EL.note = real_note
if os.name == "nt":
    t0 = time.time()
    hw = H.detect_safe()
    check(hw.cpu_name and hw.os_build >= 10240 and time.time() - t0 < H.DETECT_TIMEOUT_S,
          f"this PC through the time-limited detection: {hw.cpu_name} / {hw.gpu_name} in {time.time() - t0:.1f} s")
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, r'%s'); from core import hardware as H; "
                        "h = H.detect_safe(); print(h.gpu_name)" % ROOT], capture_output=True, text=True, timeout=60)
    check(r.returncode == 0 and "releasing IUnknown" not in (r.stderr or ""),
          "no 'Win32 exception releasing IUnknown' at exit (WMI's COM objects are freed in their own thread)")

import GameOptimizerPro as G  # noqa: E402
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check("detect_safe as detect_hw" in src and "if not instance_window_up():" in src and "say_still_starting()" in src,
      "the app starts with the time-limited detection and tells a second start that it is still loading")
if os.name == "nt":
    check(G.instance_window_up() is False, "no other GameOptimizerPro window: 'still starting' would be said")
    child = subprocess.Popen([sys.executable, "-c",
                              "import tkinter as tk; r = tk.Tk(); r.withdraw(); r.title('GameOptimizerPro Test48'); "
                              "r.after(15000, r.destroy); r.mainloop()"], creationflags=NO_WINDOW)
    try:
        end = time.time() + 10
        up = False
        while not up and time.time() < end:
            time.sleep(0.2)
            up = G.instance_window_up()
        check(up, "the running instance's window (also hidden, e.g. in the tray) is found: nothing extra is said")
    finally:
        child.kill()
    check("startet gerade" in open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read(),
          "the message says it is still starting")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
