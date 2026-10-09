"""core/services.py — logic with a FAKE PowerShell runner (nothing on the real
system is changed), plus a real read-only listing and a PowerShell PARSE check
of the generated scripts (parsed, never executed)."""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pathlib import Path
import core.services as sv

FAILS = []
def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)

tmp = tempfile.mkdtemp(prefix="gop_svc_")
sv.STATE_FILE = Path(tmp) / "services_state.json"

# fake registry + fake PowerShell
REG = {"SysMain": (2, False), "WSearch": (2, True), "Spooler": (4, False),
       "RemoteRegistry": (4, False), "BITS": (2, True), "HvHost": (3, False)}
sv._read_start = lambda n: REG.get(n)
SCRIPTS = []
MODE = {"fail": set()}

def fake_ps(script, timeout=120):
    SCRIPTS.append(script)
    out = []
    for n in sv.KNOWN_SERVICES:
        if f"'{n}'" in script:
            if n in MODE["fail"]:
                out.append(f"{n}|ERR|[SC] OpenService FEHLER 5: Zugriff verweigert")
            else:
                out.append(f"{n}|OK|reboot" if n == "WSearch" and "disabled" in script else f"{n}|OK|")
                if "disabled" in script:
                    REG[n] = (4, False)
    return "\n".join(out)
sv._run_ps = fake_ps

print("disable: remembers the ORIGINAL start type once")
res = sv.disable(["WSearch", "SysMain", "NotAService", "SysMain"])
st = sv.load_state()
check(set(res) == {"WSearch", "SysMain"}, f"unknown/duplicate names ignored: {sorted(res)}")
check(st["WSearch"]["start"] == 2 and st["WSearch"]["delayed"] is True, "WSearch: Automatisch (verzögert) remembered")
check(st["SysMain"] == {**st["SysMain"], "start": 2, "delayed": False}, "SysMain: Automatisch remembered")
check(res["WSearch"] == (True, "läuft noch bis zum Neustart"), f"'reboot' note translated: {res['WSearch']}")
check("start= disabled" in SCRIPTS[-1] and "Stop-Service" in SCRIPTS[-1], "script: sc config disabled + Stop-Service")
REG["SysMain"] = (4, False)
sv.disable(["SysMain"])
check(sv.load_state()["SysMain"]["start"] == 2, "second disable does NOT overwrite the original with 'disabled'")

print("disable failure: nothing remembered for a service that wasn't changed")
MODE["fail"] = {"HvHost"}
res = sv.disable(["HvHost"])
check(res["HvHost"][0] is False and "Zugriff verweigert" in res["HvHost"][1], f"error surfaced: {res['HvHost']}")
check("HvHost" not in sv.load_state(), "no stale record after a failed disable")
MODE["fail"] = set()

print("enable: restores remembered type, else the Windows default")
res = sv.enable(["WSearch", "Spooler", "RemoteRegistry"])
script = SCRIPTS[-1]
check("@('WSearch','delayed-auto')" in script, "WSearch -> delayed-auto (remembered)")
check("@('Spooler','auto')" in script, "Spooler (disabled by v1, nothing remembered) -> Windows default auto")
check("@('RemoteRegistry','demand')" in script, "RemoteRegistry (default Disabled) -> Manual, never 'disabled'")
check(res["WSearch"] == (True, "Automatisch (verzögert) (gemerkt)"), f"result text: {res['WSearch']}")
check(res["Spooler"] == (True, "Automatisch (Windows-Standard)"), f"result text: {res['Spooler']}")
check("WSearch" not in sv.load_state() and "SysMain" in sv.load_state(), "record removed only for the restored one")
check("Start-Service" in script and "if($m -ne 'demand')" in script, "auto-start services are started again")

print("enable failure keeps the record")
MODE["fail"] = {"SysMain"}
res = sv.enable(["SysMain"])
check(res["SysMain"][0] is False and "SysMain" in sv.load_state(), "failed restore -> original still remembered")
MODE["fail"] = set()

print("name validation")
sv.KNOWN_SERVICES["bad;name"] = ("x", True, "x")
try:
    sv.disable(["bad;name"])
    check(False, "injection-like name rejected")
except ValueError:
    check(True, "injection-like name rejected (ValueError)")
del sv.KNOWN_SERVICES["bad;name"]

print("PowerShell parses the generated scripts (not executed)")
scripts = SCRIPTS[:]
pf = Path(tmp) / "scripts.json"
pf.write_text(json.dumps(scripts), encoding="utf-8")
ps = ("$s = Get-Content -Raw -Encoding UTF8 '%s' | ConvertFrom-Json; $bad=0; "
      "foreach($x in $s){ $e=$null; [void][System.Management.Automation.Language.Parser]::ParseInput($x,[ref]$null,[ref]$e); "
      "if($e.Count){ $bad++; $e | ForEach-Object { $_.Message } } }; \"BAD=$bad\"" % pf)
r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, text=True, timeout=60)
check("BAD=0" in r.stdout, f"{len(scripts)} scripts parse cleanly: {r.stdout.strip()[-200:]}")

print("real system, read-only")
import importlib
real = importlib.reload(sv)
real.STATE_FILE = Path(tmp) / "none.json"
lst = real.list_services()
names = {s.name for s in lst}
check(len(lst) >= 20, f"{len(lst)} known services present on this PC")
check("TabletInputService" not in real.KNOWN_SERVICES and "TextInputManagementService" not in real.KNOWN_SERVICES,
      "text-input service never offered (breaks typing on Win11 24H2+)")
check(all(s.start in (2, 3, 4) for s in lst), "start types read from the registry")
check(all(s.status for s in lst), "status from the service manager")
check(set(real.WINDOWS_DEFAULT) == set(real.KNOWN_SERVICES), "a Windows default exists for every known service")
check(not real.is_admin() or True, f"is_admin() -> {real.is_admin()}")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
