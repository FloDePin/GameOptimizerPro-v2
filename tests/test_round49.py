"""Round 49 — the full audit of build 56, every point fixed and checked here.

  * Services: "Enable (original)" for exactly ONE service — PowerShell flattened the single row, the loop took
    the first letters as name and mode and nothing came back on. Run for real against a stand-in sc.exe.
  * Block Telemetry Hosts retired: none of its names is a Windows 11 diagnostic endpoint, Defender reports
    such entries (HostsFileHijack) and resets the whole hosts file. Its clean-up removes only its nine lines —
    also one glued to the line before — run against a copy of a hosts file.
  * Language: the PowerShell messages were English in the German app (core.tweaks built them before the
    saved language was loaded); five tweak names were German in the English app.
  * DNS: apply keeps each adapter's servers from before, revert puts exactly those back (a DNS set by hand
    is no longer lost) — against simulated network cmdlets and scratch keys.
  * Import: a GPU profile of the same name is replaced only when asked, the old one kept as .bak; exports
    carry no computer name.
  * Retired tweaks still applied: their own clean-up (start dialog, button on the optimizer page) instead of
    only "Revert all".
  * Late hardware detection: pages built before WMI answered are rebuilt (not while busy / with a pending
    selection). Requirements with upper bounds + pywin32, Tcpip6 in the backup, presets without duplicates and
    without app removals in "All Safe", a warning for a foreign administrator account, a launcher that starts
    from a path with an apostrophe, a status check that counts an empty answer as an error.

Windowed only for the drift dialog (hidden desktop in the battery; GOP_TEST_NO_UI=1 skips it, e.g. in CI).
Nothing on the real system is changed: registry work on HKCU\\Software\\GameOptimizerPro-Test49 (removed at
the end), files in a temp folder, sc.exe / Start-Process / network cmdlets are PowerShell stand-ins."""
import json
import os
import re
import shutil
import subprocess
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


TMP = tempfile.mkdtemp(prefix="gop_r49_")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "LocalAppData")      # backups: never the user's
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

from core import app_launch as AL  # noqa: E402
from core import deps  # noqa: E402
from core import export_import as EX  # noqa: E402
from core import hardware as H  # noqa: E402
from core import registry_backup as RB  # noqa: E402
from core import services as SV  # noqa: E402
from core import tweak_presets as TP  # noqa: E402
from core import tweak_verifier as TV  # noqa: E402
from core import tweaks as T  # noqa: E402
from core.tweak_i18n import PRESET_DESC_EN, TWEAK_DESC_EN, TWEAK_NAME_EN  # noqa: E402

NO_UI = bool(os.environ.get("GOP_TEST_NO_UI"))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEST = r"Software\GameOptimizerPro-Test49"
WIN = os.name == "nt"


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="oem", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def no_exit(script):
    """The scripts end with `exit N` — here they run inside one PowerShell with the checks after them."""
    return re.sub(r"\bexit \d", "return", script)


def hkcu_keys():
    _rc, out, _e = ps("[Microsoft.Win32.Registry]::CurrentUser.GetSubKeyNames() -join '|'")
    return set(out.split("|"))


HKCU_BEFORE = hkcu_keys() if WIN else set()

# ── 1. Services: one service comes back on ───────────────────────────────────
print("services: 'Enable' for exactly one service (ran over the letters of its name)")
SV.STATE_FILE = Path(TMP) / "services_state.json"
REAL_RUN = SV._run_ps
STUB = ("$global:CALLS=@(); "
        "function sc.exe { $global:CALLS += ('sc ' + ($args -join ' ')); $global:LASTEXITCODE = 0 }; "
        "function Start-Service { [CmdletBinding()] param($Name) $global:CALLS += ('start ' + $Name) }; "
        "function Stop-Service { [CmdletBinding()] param($Name, [switch]$Force) $global:CALLS += ('stop ' + $Name) }; "
        "function Get-Service { [CmdletBinding()] param($Name) [pscustomobject]@{Status='Stopped'} }; ")
OUTS = []


def stub_run(script, timeout=120):
    out = REAL_RUN(STUB + script + "; 'CALLS=' + ($global:CALLS -join ';')", timeout)
    OUTS.append(out)
    return out


def calls_of(out):
    m = re.search(r"CALLS=(.*)", out or "")
    return m.group(1).strip().split(";") if m and m.group(1).strip() else []


if WIN:
    SV._run_ps = stub_run
    SV._read_start = lambda n: (2, False)
    try:
        res = SV.enable(["SysMain"])
        calls = calls_of(OUTS[-1])
        check(res.get("SysMain", (False, ""))[0] and "sc config SysMain start= auto" in calls and "start SysMain" in calls,
              f"one service: sc config <its name> + started (it was 'config S start= y') {res} {calls}")
        res = SV.enable(["SysMain", "WSearch"])
        calls = calls_of(OUTS[-1])
        check(all(res.get(n, (False,))[0] for n in ("SysMain", "WSearch"))
              and "sc config SysMain start= auto" in calls and "sc config WSearch start= delayed-auto" in calls,
              f"two services: both, each with its own start type {calls}")
        res = SV.disable(["SysMain"])
        calls = calls_of(OUTS[-1])
        check(res.get("SysMain", (False,))[0] and "sc config SysMain start= disabled" in calls and "stop SysMain" in calls,
              f"disable one: its name, not its letters {calls}")
    finally:
        SV._run_ps = REAL_RUN

# ── 2. Block Telemetry Hosts retired ─────────────────────────────────────────
print("hosts tweak retired, its clean-up removes only its own lines")
HID = "block_telemetry_hosts"
in_presets = [p.id for p in TP.BUILTIN_PRESETS if HID in (p.tweak_ids or [])]
check(T.get_by_id(HID) is None and HID not in TV.VERIFY_MAP and HID not in TWEAK_DESC_EN and not in_presets
      and HID in T.RETIRED_TWEAKS and HID not in TP._TIER_HARD,
      f"no tweak, check, text or preset any more — a retired entry with a clean-up {in_presets}")
check(not any("hosts" in (p.desc or "").lower() for p in TP.BUILTIN_PRESETS)
      and "hosts" not in PRESET_DESC_EN.get("privacy", "").lower(),
      "the Privacy preset no longer promises a hosts-file block")
CLEAN = T.RETIRED_TWEAKS[HID][2]
OURS = re.findall(r"'(0\.0\.0\.0 [^']+)'", CLEAN)
check(len(OURS) == 9 and "telemetry.microsoft.com" in OURS[0], f"the nine lines it wrote ({len(OURS)})")
if WIN:
    hosts = Path(TMP) / "hosts"
    lines = ["# Copyright (c) 1993-2009 Microsoft Corp.", "127.0.0.1 localhost",
             "0.0.0.0 choice.microsoft.com",                        # someone else's line (another tool)
             "192.168.1.5 nas.local" + OURS[0],                     # appended without a line break
             *OURS[1:8], "  " + OURS[8] + "  ",
             "0.0.0.0 xdf.telemetry.microsoft.com"]                 # looks alike, isn't ours
    hosts.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    script = CLEAN.replace('$f="$env:SystemRoot\\System32\\drivers\\etc\\hosts"', f"$f='{hosts}'")
    check(script != CLEAN, "the clean-up's hosts path can be pointed at a copy")
    rc, out, err = ps(script)
    left = hosts.read_text(encoding="ascii").splitlines()
    check(rc == 0 and left == ["# Copyright (c) 1993-2009 Microsoft Corp.", "127.0.0.1 localhost",
                               "0.0.0.0 choice.microsoft.com", "192.168.1.5 nas.local",
                               "0.0.0.0 xdf.telemetry.microsoft.com"],
          f"its nine lines out, the glued one split off again, everything else kept {left} {err[:80]}")
    before = hosts.read_bytes()
    mtime = hosts.stat().st_mtime_ns
    time.sleep(0.05)
    rc, _o, _e = ps(script)
    check(rc == 0 and hosts.read_bytes() == before and hosts.stat().st_mtime_ns == mtime,
          "nothing of its own left: the file is not written at all")
    rc, _o, _e = ps(script.replace(str(hosts), str(Path(TMP) / "no-hosts")))
    check(rc == 0, "no hosts file: nothing to do")

# ── 3. Language: German messages in the German app, English names in the English one ──
print("language: messages built in the saved language, no German tweak names in English")
src = Path(ROOT, "GameOptimizerPro.py").read_text(encoding="utf-8")
check(0 < src.find("_i18n_early.init_lang()") < src.find("from core.tweak_runner"),
      "the start loads the saved language before core.tweaks builds its messages")
lang_dir = Path(TMP) / "lang"
lang_dir.mkdir()
probe = ("import sys, json; from pathlib import Path; sys.path.insert(0, r'%s'); import core.i18n as I; "
         "f = Path(r'%s') / 'language.json'; f.write_text(json.dumps({'lang': sys.argv[1]})); I._LANG_FILE = f; "
         "I.init_lang(); from core import tweaks as T; "
         "print(T.get_by_id('enable_hags').ps_command); print(T.get_by_id('amd_disable_ulps').ps_command)")
for lang, want in (("de", ("Nicht geändert", "Kein AMD-Grafikadapter gefunden")),
                   ("en", ("Not changed", "No AMD graphics adapter found"))):
    r = subprocess.run([sys.executable, "-c", probe % (ROOT, lang_dir), lang], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    check(r.returncode == 0 and all(w in r.stdout for w in want),
          f"{lang}: the tweak messages in that language ({want[0]!r}, {want[1]!r}) {r.stderr[-120:]}")
# every PowerShell text in both languages: no German-only message in the English build (four were found by the
# re-audit) and no typographic quotes — PowerShell reads „ “ ” ‘ ’ as real quotes (the message fell apart)
scan = r'''
import importlib, json, re, sys
sys.path.insert(0, r"%s")
import core.i18n as I
I._current_lang = sys.argv[1]
import core.tweaks as T, core.tweak_verifier as V
snips = {}
for t in T.ALL_TWEAKS:
    snips[t.id + ":apply"] = t.ps_command
    snips[t.id + ":revert"] = t.revert_cmd or ""
for k, v in V.VERIFY_MAP.items():
    snips[k + ":verify"] = v
for k, v in T.RETIRED_TWEAKS.items():
    snips[k + ":retired"] = v[2]
W = re.compile(r"[äöüÄÖÜß]|\b(nicht|keine?|gesetzt|gefunden|geändert|Aufgaben|deaktiviert|verfügbar|Leistung|"
               r"entfernt|Kopien|Netzbetrieb|gestartet|wieder|liess|ließ|Laufwerke|Treiber|meldet)\b")
german, smart = [], []
for k, c in snips.items():
    if re.search("[“”„‘’‚]", c):
        smart.append(k)
    for m in re.finditer(r'"([^"]*)"|\'([^\']*)\'', c):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        if W.search(s) and " / " not in s:
            german.append(k + ": " + s[:50])
print(json.dumps({"german": german, "smart": smart}))
''' % ROOT
for lang in ("en", "de"):
    r = subprocess.run([sys.executable, "-c", scan, lang], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        res = {"german": ["?"], "smart": ["?"], "err": r.stderr[-200:]}
    check(not res["smart"], f"{lang}: no typographic quotes in any PowerShell text {res['smart']}")
    if lang == "en":
        check(not res["german"], f"en: no German-only PowerShell message {res['german']}")
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(aus|nie|deaktivieren|aktivieren|entfernen|legen|Minuten|Festplatte|schlafen|"
                    r"für|und|mit|ohne|nicht|stoppen|laufen|lassen|blockieren|Leistung)\b", re.I)
german = [t.id for t in T.ALL_TWEAKS if t.id not in TWEAK_NAME_EN and GERMAN.search(t.name)]
check(not german, f"every tweak whose name is German has an English one {german}")
check(all(TWEAK_NAME_EN.get(i) for i in ("power_pcie_aspm_off", "power_disk_never_sleep", "power_display_sleep_15",
                                         "power_sleep_off", "amd_disable_ulps")), "the five that were missing")
check(not [t.id for t in T.ALL_TWEAKS if t.id not in TWEAK_DESC_EN], "every tweak has an English description")

# ── 4. DNS: the servers from before come back ────────────────────────────────
print("DNS: apply keeps each adapter's servers, revert puts exactly those back")
NETMOCK = r"""
$global:ADP=@(); $global:DNS=@(); $global:CALLS=@()
function Set-DnsClientServerAddress { [CmdletBinding()] param($InterfaceIndex, $ServerAddresses, [switch]$ResetServerAddresses)
  $a=$global:ADP | Where-Object { $_.InterfaceIndex -eq $InterfaceIndex }
  if($ServerAddresses -and @($ServerAddresses | Where-Object { $_ -match ':' }).Count -and $a.NoV6){ throw 'no IPv6' }
  $global:CALLS += ("{0}:{1}" -f $InterfaceIndex, $(if($ResetServerAddresses){'reset'}else{$ServerAddresses -join ','})) }
function A($i,$n,$phys,$nov6){ $global:ADP += [pscustomobject]@{InterfaceIndex=$i; Name=$n; Status='Up'; Phys=$phys; NoV6=$nov6} }
function D($i,$fam,$srv){ $global:DNS += [pscustomobject]@{InterfaceIndex=$i; AddressFamily=$fam; ServerAddresses=@($srv)} }
function Get-CimInstance { [CmdletBinding()] param($Namespace, $ClassName)
  if($ClassName -eq 'MSFT_NetAdapter'){ $global:ADP | ForEach-Object { [pscustomobject]@{Name=$_.Name; InterfaceIndex=$_.InterfaceIndex;
      InterfaceGuid=('{G' + $_.InterfaceIndex + '}'); ConnectorPresent=$_.Phys; InterfaceOperationalStatus=$(if($_.Status -eq 'Up'){1}else{2})} } }
  elseif($ClassName -eq 'MSFT_DNSClientServerAddress'){ $global:DNS | ForEach-Object { [pscustomobject]@{InterfaceIndex=$_.InterfaceIndex;
      AddressFamily=$(if($_.AddressFamily -eq 'IPv4'){2}else{23}); ServerAddresses=$_.ServerAddresses} } } }
"""


def redirect(script):
    return (script.replace("[Microsoft.Win32.Registry]::LocalMachine", "[Microsoft.Win32.Registry]::CurrentUser")
            .replace("SOFTWARE\\GameOptimizerPro\\DnsOrig", TEST + "\\DnsOrig")
            .replace("SYSTEM\\CurrentControlSet\\Services\\Tcpip", TEST + "\\Tcpip"))


def dns(setup, script):
    _rc, out, err = ps(NETMOCK + setup + "\n$r = & { " + no_exit(redirect(script)) + " }; "
                       "Write-Output ('CALLS ' + ($global:CALLS -join ' '))")
    m = re.search(r"CALLS ?(.*)", out)
    return (m.group(1).split() if m else []), err


def set_if(fam, guid, value):
    sub = "Tcpip" if fam == "4" else "Tcpip6"
    ps(f"$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{TEST}\\{sub}\\Parameters\\Interfaces\\{guid}'); "
       f"$k.SetValue('NameServer','{value}'); $k.Close()")


def store():
    _rc, out, _e = ps(f"$k=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{TEST}\\DnsOrig'); "
                      "if($k){ ($k.GetValueNames() | Sort-Object | ForEach-Object { $_ + '=' + $k.GetValue($_) }) -join ';' }")
    return dict(kv.split("=", 1) for kv in out.split(";") if "=" in kv)


def set_store(values):
    ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}\\DnsOrig', $false); "
       f"$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{TEST}\\DnsOrig'); "
       + "".join(f"$k.SetValue('{n}','{v}'); " for n, v in values.items()) + "$k.Close()")


if WIN:
    CF, GO = T.get_by_id("dns_cloudflare"), T.get_by_id("dns_google")
    set_if("4", "{G1}", "192.168.1.2")          # a DNS set by hand (e.g. Pi-hole) over IPv4, IPv6 automatic
    set_if("6", "{G1}", "")
    eth = "A 1 'Ethernet' $true $false; "
    calls, err = dns(eth + "D 1 'IPv4' @('192.168.1.2'); D 1 'IPv6' @('fd00::1')", CF.ps_command)
    st = store()
    check(calls[:1] == ["1:1.1.1.1,1.0.0.1,2606:4700:4700::1111,2606:4700:4700::1001"]
          and st == {"{G1}|4": "192.168.1.2", "{G1}|6": ""},
          f"apply: Cloudflare set, the servers from before kept per adapter {st} {calls} {err[:80]}")
    set_if("4", "{G1}", "1.1.1.1,1.0.0.1")       # what Windows holds now
    dns(eth + "D 1 'IPv4' @('1.1.1.1','1.0.0.1')", GO.ps_command)
    check(store() == {"{G1}|4": "192.168.1.2", "{G1}|6": ""},
          "a second apply (the other provider) keeps the first kept value, not Cloudflare's")
    calls, _e = dns(eth + "D 1 'IPv4' @('8.8.8.8'); D 1 'IPv6' @('2001:4860:4860::8888')", CF.revert_cmd)
    check(calls == [] and store(), "reverting Cloudflare while Google is set: nothing touched, the kept value stays")
    calls, _e = dns(eth + "D 1 'IPv4' @('8.8.8.8'); D 1 'IPv6' @('2001:4860:4860::8888')", GO.revert_cmd)
    check(calls == ["1:reset", "1:192.168.1.2"] and store() == {},
          f"revert: automatic first, then exactly the hand-set server again — the kept value is used up {calls}")
    set_store({"{G1}|4": "192.168.1.2", "{G1}|6": "fd00::53"})
    calls, _e = dns(eth + "D 1 'IPv4' @('1.1.1.1'); D 1 'IPv6' @('2606:4700:4700::1111')", CF.revert_cmd)
    check(calls == ["1:reset", "1:192.168.1.2,fd00::53"], f"IPv4 and IPv6 set by hand: both back {calls}")
    set_store({"{G1}|4": "1.1.1.1,1.0.0.1", "{G1}|6": ""})
    calls, _e = dns(eth + "D 1 'IPv4' @('1.1.1.1')", CF.revert_cmd)
    check(calls == ["1:reset"], f"a kept value that is the provider itself (an older version set it): automatic {calls}")
    set_store({})
    calls, _e = dns(eth + "A 7 'vEthernet' $false $false; D 1 'IPv4' @('1.1.1.1'); D 7 'IPv4' @('1.0.0.1'); "
                    "D 7 'IPv6' @('2606:4700:4700::1001')", CF.revert_cmd)
    check(calls == ["1:reset", "7:reset"], f"nothing kept (applied by an older version): automatic, each adapter once {calls}")
    calls, _e = dns("A 2 'WLAN' $true $true; D 2 'IPv4' @('192.168.1.2')", CF.ps_command)
    set_store({"{G2}|4": "192.168.1.2", "{G2}|6": ""})
    calls, _e = dns("A 2 'WLAN' $true $true; D 2 'IPv4' @('1.1.1.1')", CF.revert_cmd)
    check(calls == ["2:reset", "2:192.168.1.2"], f"an adapter without IPv6: its IPv4 server back {calls}")
check("DnsOrig" in T.get_by_id("dns_cloudflare").ps_command and RB.BACKUP_KEYS.count(
      r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters") == 1,
      "the kept values live under HKLM\\SOFTWARE\\GameOptimizerPro (in every backup); IPv6 DNS is in the backup too")

# ── 5. Export / import ───────────────────────────────────────────────────────
print("export without the computer name, import asks before replacing a profile")
pdir = Path(TMP) / "profiles"
pdir.mkdir()
ex = EX.ExportImport(profiles_dir=str(pdir), logs_dir=TMP)
mine = {"name": "Daily", "core_offset_mhz": 120, "power_limit_pct": 100}
(pdir / "Daily.json").write_text(json.dumps(mine), encoding="utf-8")
out_file = Path(TMP) / "e.nextune"
ok, _m = ex.export(str(out_file), include_tweaks=True, applied_tweaks={"disable_telemetry": "x"})
data = json.loads(out_file.read_text(encoding="utf-8"))
check(ok and "_host" not in data and os.environ.get("COMPUTERNAME", "§") not in out_file.read_text(encoding="utf-8"),
      "an export carries no computer name")
ok, res, msg = ex.import_file(str(out_file))
check(ok and "Von PC" not in msg, "its preview doesn't ask for one")
old = dict(data, _host="OTHER-PC")
out_file.write_text(json.dumps(old), encoding="utf-8")
ok, res, msg = ex.import_file(str(out_file))
check(ok and "OTHER-PC" in msg, "an older export with one still shows it")
older = {"name": "Daily", "core_offset_mhz": 60, "power_limit_pct": 90}
new = {"name": "Night", "core_offset_mhz": 30, "power_limit_pct": 80}
check(ex.profile_conflicts([older, new, mine]) == ["Daily"], "the same name with other values is a conflict, the same profile isn't")
n_ok, n_skip = ex.apply_imported_profiles([older, new], replace=False)
check((n_ok, n_skip) == (1, 1) and json.loads((pdir / "Daily.json").read_text())["core_offset_mhz"] == 120
      and (pdir / "Night.json").exists(), "'No': the tuned profile stays, only the new one is added")
n_ok, n_skip = ex.apply_imported_profiles([older], replace=True)
check(n_ok == 1 and json.loads((pdir / "Daily.json").read_text())["core_offset_mhz"] == 60
      and json.loads((pdir / "Daily.json.bak").read_text())["core_offset_mhz"] == 120,
      "'Yes': replaced, the one from before kept as Daily.json.bak")
check(sorted(p.name for p in pdir.glob("*.json")) == ["Daily.json", "Night.json"],
      "no .bak / .tmp counts as a profile (*.json)")
check(ex.apply_imported_profiles([{"name": 123}, {"name": "__x", "core_offset_mhz": 1}, "x"]) == (0, 3),
      "no profile, an internal one and junk are skipped")

# ── 6. Retired tweaks: their own clean-up ────────────────────────────────────
print("retired tweaks still applied: cleaned up on their own")
from ui import main_window as MW  # noqa: E402
from ui import tab_optimizer as TO  # noqa: E402


class Runner:
    def __init__(self):
        self._applied = {"tcp_optimize": "t", HID: "t", "disable_telemetry": "t"}
        self.cleaned, self.forgot, self.backups = [], [], []

    def retired_applied(self):
        return [t for t in self._applied if t in T.RETIRED_TWEAKS]

    def clean_retired(self, tid):
        self.cleaned.append(tid)
        self._applied.pop(tid, None)
        return True, ""

    def forget(self, ids):
        self.forgot += list(ids)
        for i in ids:
            self._applied.pop(i, None)

    def backup_registry(self, label):
        self.backups.append(label)

    def is_applied(self, tid):
        return tid in self._applied


fake = types.SimpleNamespace(runner=Runner(), _tab_frames={}, status=[])
fake.set_status = fake.status.append
fake.after = lambda ms, fn, *a: fn(*a)
fake._handle_drift = lambda *a: MW.GameOptimizerWindow._handle_drift(fake, *a)
fake._clean_leftovers = lambda ids, then_reapply=(): MW.GameOptimizerWindow._clean_leftovers(fake, ids, then_reapply)
MW.GameOptimizerWindow._handle_drift(fake, [], [], ["tcp_optimize"], [HID])
deadline = time.time() + 5
while not fake.runner.cleaned and time.time() < deadline:
    time.sleep(0.05)
time.sleep(0.1)
check(fake.runner.forgot == [HID] and HID not in fake.runner._applied,
      "unticked: kept as it is and no longer asked (its values stay)")
check(fake.runner.backups == ["PreLeftoverCleanup"] and fake.runner.cleaned == ["tcp_optimize"]
      and "disable_telemetry" in fake.runner._applied,
      "ticked: registry backup, then only that clean-up — every other tweak stays applied")


class Btn:
    def __init__(self):
        self.mapped, self.text = False, ""

    def configure(self, **kw):
        self.text = kw.get("text", self.text)

    def pack(self, **kw):
        self.mapped = True

    def pack_forget(self):
        self.mapped = False

    def winfo_ismapped(self):
        return self.mapped


page = types.SimpleNamespace(btn_leftovers=Btn(), runner=Runner())
TO.OptimizerTab._refresh_leftovers(page)
check(page.btn_leftovers.mapped and "(2)" in page.btn_leftovers.text,
      f"the optimizer page shows 'Clean up leftovers (2)' while two are applied ({page.btn_leftovers.text})")
page.runner._applied = {"disable_telemetry": "t"}
TO.OptimizerTab._refresh_leftovers(page)
check(not page.btn_leftovers.mapped, "... and hides it when there are none")
csrc = Path(ROOT, "ui", "tab_optimizer.py").read_text(encoding="utf-8")
check("self._refresh_leftovers" in csrc[csrc.find("def _revert_all"):], "'Revert all' updates the button too")
msrc = Path(ROOT, "ui", "main_window.py").read_text(encoding="utf-8")
check("leftovers = self.runner.retired_applied()" in msrc and "if drifted or leftovers:" in msrc,
      "the start dialog offers them (elevated start, like the drift check)")

if not NO_UI:
    import customtkinter as ctk
    from ui.drift_dialog import DriftDialog
    root = ctk.CTk()
    root.withdraw()
    got = []
    dlg = DriftDialog(root, [], on_done=lambda *a: got.append(a), leftovers=[("tcp_optimize", "TCP"), (HID, "Hosts")])
    dlg.attributes("-alpha", 0.0)
    root.update()
    check(list(dlg.left_vars) == ["tcp_optimize", HID] and not dlg.vars, "leftovers only: one tick box each, no drift part")
    dlg.left_vars[HID].set(False)
    dlg.submit()
    check(got == [([], [], ["tcp_optimize"], [HID])], f"submit: (re-apply, drop, clean up, keep) {got}")
    got.clear()
    dlg = DriftDialog(root, [("disable_telemetry", "Telemetrie")], on_done=lambda *a: got.append(a),
                      leftovers=[("tcp_optimize", "TCP")])
    dlg.attributes("-alpha", 0.0)
    root.update()
    dlg.submit()
    check(got == [(["disable_telemetry"], [], ["tcp_optimize"], [])], "drift and leftovers in one dialog")
    root.destroy()
else:
    print("  (drift dialog window skipped: GOP_TEST_NO_UI)")

# ── 7. Hardware detection that came in late ──────────────────────────────────
print("late hardware detection: the pages built without it are rebuilt")
real_detect, real_note = H.detect, None
import core.errlog as EL  # noqa: E402
real_note = EL.note
EL.note = lambda text: None
try:
    H.detect = lambda: (time.sleep(1.0), H.HardwareInfo(cpu_name="Late CPU", gpu_name="NVIDIA Late GPU",
                                                         os_build=26300, is_nvidia=True))[1]
    hw = H.detect_safe(timeout=0.3)
    check(getattr(hw, "wmi_pending", False) and not getattr(hw, "wmi_arrived", True), "WMI still out: pending")
    deadline = time.time() + 5
    while hw.wmi_pending and time.time() < deadline:
        time.sleep(0.05)
    check(not hw.wmi_pending and hw.wmi_arrived and hw.gpu_name == "NVIDIA Late GPU" and hw.is_nvidia,
          "WMI answered: the full result in the same object, arrived")
    H.detect = lambda: H.HardwareInfo(cpu_name="Quick CPU")
    quick = H.detect_safe(timeout=5)
    check(not getattr(quick, "wmi_pending", False), "WMI in time: nothing pending, no polling")
finally:
    H.detect = real_detect
    EL.note = real_note


class Page:
    def __init__(self, busy=False, pending=False):
        self._batch_running = busy
        self.destroyed = False
        if pending:
            self.runner = Runner()
            self._vars = {"disable_telemetry": types.SimpleNamespace(get=lambda: False)}   # unticked, but applied

    def on_hide(self):
        pass

    def destroy(self):
        self.destroyed = True


class Lbl:
    def __init__(self):
        self.text = ""

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class Win:
    HW_PAGES = MW.GameOptimizerWindow.HW_PAGES
    _hw_arrived = MW.GameOptimizerWindow._hw_arrived
    _drop_stale = MW.GameOptimizerWindow._drop_stale
    _hw_lines = MW.GameOptimizerWindow._hw_lines

    def __init__(self):
        self.hw = hw
        self._hw_labels = [Lbl() for _ in range(4)]
        self._stale_pages = set()
        self.dash, self.opt, self.bios = Page(), Page(pending=True), Page(busy=True)
        self._tab_frames = {"dashboard": self.dash, "optimizer": self.opt, "bios": self.bios, "gpu": Page()}
        self._active_tab = "dashboard"
        self.shown, self.status = [], []

    def _show_tab(self, key):
        self.shown.append(key)

    def set_status(self, text):
        self.status.append(text)


w = Win()
w._hw_arrived()
check("NVIDIA Late GPU".split()[-2] in w._hw_labels[0].text or "Late" in w._hw_labels[0].text,
      f"the sidebar shows the detected GPU ({w._hw_labels[0].text})")
check(w.dash.destroyed and "dashboard" not in w._tab_frames and w.shown == ["dashboard"],
      "the visible dashboard is rebuilt right away")
check(not w.opt.destroyed and not w.bios.destroyed and w._stale_pages == {"optimizer", "bios"},
      "a page with a selection not applied yet, or one that is busy, stays (rebuilt later, never losing anything)")
check("gpu" in w._tab_frames and not w._tab_frames["gpu"].destroyed, "pages that don't depend on it are left alone")
w.opt._vars = {}
w.bios._batch_running = False
check(w._drop_stale("optimizer") and w._drop_stale("bios") and not w._stale_pages, "... once free, they are rebuilt")
check("if key in getattr(self, \"_stale_pages\", ()) and key != self._active_tab:" in msrc
      and "self.after(1000, self._poll_late_hw)" in msrc, "a stale page is rebuilt when it is opened; the window polls (Tk on the main thread)")

# ── 8. Requirements, presets, backup, verifier ───────────────────────────────
print("requirements, presets, backup, status check")
reqs = deps.requirements()
check(reqs and all("<" in spec for spec, _d, _m in reqs), f"every requirement has an upper bound {[s for s, _d, _m in reqs if '<' not in s]}")
check(any(d == "pywin32" for _s, d, _m in reqs) and deps.import_name("pywin32") == "pythoncom",
      "pywin32 listed (imported directly), found by its module pythoncom")
if WIN:
    check(deps.missing() == [], f"nothing missing on this PC (pywin32 isn't reinstalled at every start) {deps.missing()}")
hard = set(TP._TIER_HARD)
check(not {"disable_bg_throttle", "disable_background_apps"} <= hard and "disable_bg_throttle" in hard,
      "Hart: one background-apps tweak, the one for every edition")
check("Hintergrund-Apps stoppen" in T.get_by_id("disable_background_apps").desc
      and "Store-Apps nicht im Hintergrund" in T.get_by_id("disable_bg_throttle").desc
      and "one of the two is enough" in TWEAK_DESC_EN["disable_bg_throttle"], "each names its twin")
safe = TP.get_all_safe_ids()
check(not [i for i in safe if i.startswith("remove_")] and "disable_telemetry" in safe,
      "All Safe: no app removal (no revert brings an app back)")

saved_run = TV.subprocess.run
saved_reg = TV.reg_check


class Proc:
    def __init__(self, out):
        self.stdout, self.stderr, self.returncode = out, "", 0


try:
    TV.subprocess.run = lambda *a, **k: Proc("disable_telemetry|1\ndisable_bing_search|\n"
                                            "disable_location|1 1\ndisable_advertising_id|0\n")
    ids = ["disable_telemetry", "disable_bing_search", "disable_location", "disable_advertising_id"]
    r = TV.TweakVerifier()._run_part(ids, {i: True for i in ids}, 5)
    check(r["disable_telemetry"].actual and not r["disable_telemetry"].error
          and not r["disable_advertising_id"].actual and not r["disable_advertising_id"].error,
          "'1' / '0' are answers")
    check(r["disable_bing_search"].error and r["disable_location"].error,
          "an empty or odd answer is an error (amber), not 'inactive'")
    seen = []
    TV.reg_check = lambda t: None
    orig_part = TV.TweakVerifier._run_part
    TV.TweakVerifier._run_part = lambda self, p, e, t: (seen.append(t), {})[1]
    ids = ["disable_telemetry", "remove_xbox"]
    TV.TweakVerifier().verify_all(ids, {})
    default = sorted(set(seen))
    seen.clear()
    TV.TweakVerifier(timeout_s=60).verify_all(ids, {})
    check(default == [20, 30] and set(seen) == {60}, f"timeout_s is used: 20/30 s by default, the given one for every part ({default}, {seen})")
finally:
    TV.subprocess.run = saved_run
    TV.reg_check = saved_reg
    TV.TweakVerifier._run_part = orig_part

# ── 9. Foreign administrator account ─────────────────────────────────────────
print("elevated under another account: noticed")
procs = [{"pid": 11, "name": "explorer.exe", "username": "PC\\anna"}, {"pid": 12, "name": "python.exe", "username": "PC\\admin"}]
sess = lambda pid: {11: 1, 12: 1, 21: 2}.get(pid, 1)
check(AL.foreign_admin(procs, me="PC\\admin", my_session=1, session_of=sess) == "PC\\anna",
      "explorer.exe of this session belongs to someone else: that user")
check(AL.foreign_admin(procs, me="pc\\ANNA", my_session=1, session_of=sess) is None, "the same account (any case): nothing")
check(AL.foreign_admin([{"pid": 21, "name": "explorer.exe", "username": "PC\\bob"}], me="PC\\admin", my_session=1,
                       session_of=sess) is None, "an explorer.exe in another session (another user signed in): nothing")
check(AL.foreign_admin([], me="PC\\admin", my_session=1, session_of=sess) is None, "no explorer.exe at all: nothing")
if WIN:
    check(AL.foreign_admin() is None, "this PC: the app's account is the signed-in one")
check("self.after(2500, self._check_foreign_admin)" in msrc and "IsUserAnAdmin" in msrc[msrc.find("def _check_foreign_admin"):],
      "the window says it once at an elevated start")

# ── 10. Launcher: a path with an apostrophe ──────────────────────────────────
print("launcher: starts from a path with an apostrophe")
bat = Path(ROOT, "GameOptimizerPro.bat").read_text(encoding="ascii")
check("'%PYW%'" not in bat and "'%~dp0'" not in bat and "$env:GOP_PYW" in bat, "no path inside '...' any more")
if WIN:
    d = Path(tempfile.mkdtemp(prefix="gop r49 O'Brien "))
    keep = [ln for ln in bat.splitlines() if ln.startswith('set "GOP_') or ln.startswith("powershell ")]
    fake_ps = ("function Start-Process { param($FilePath,$ArgumentList,$Verb,$WorkingDirectory) "
               "Write-Output ('FP=' + $FilePath); Write-Output ('AL=' + $ArgumentList); "
               "Write-Output ('WD=' + $WorkingDirectory); Write-Output ('VB=' + $Verb) }; Start-Process")
    body = ["@echo off", "set \"PYW=C:\\Users\\O'Brien\\Python\\pythonw.exe\"", 'cd /d "%~dp0"']
    body += [ln.replace('-Command "Start-Process', '-Command "' + fake_ps, 1) for ln in keep]
    (d / "launch.bat").write_text("\r\n".join(body) + "\r\n", encoding="ascii")
    r = subprocess.run(["cmd.exe", "/c", str(d / "launch.bat")], capture_output=True, text=True, encoding="oem",
                       errors="replace", timeout=60, creationflags=NO_WINDOW)
    out = r.stdout
    check(len(keep) == 3 and "FP=C:\\Users\\O'Brien\\Python\\pythonw.exe" in out
          and f'AL="{d}\\GameOptimizerPro.py"' in out and f"WD={d}\\" in out and "VB=RunAs" in out,
          f"pythonw and the app's path arrive whole, quoted, elevated {out[-300:]!r} {r.stderr[-200:]!r}")
    shutil.rmtree(d, ignore_errors=True)

# ── end ──────────────────────────────────────────────────────────────────────
if WIN:
    ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}', $false)")
    check(hkcu_keys() <= HKCU_BEFORE, "nothing new left under HKCU (scratch keys removed)")
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
