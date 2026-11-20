"""Round 47 — v1's review checked against v2 (and the Windows update KB5132057).

  * Power plan tweaks: each plan's own values are kept and put back (AC and battery); without kept values a
    plan goes back to its Windows default only when it still has the tweak's value; copies such as
    "Ultimate Performance" without a default stay — run against a simulated powercfg (never the real plans).
  * HAGS, svchost threshold, background apps: the value before is put back (svchost: 0x380000, not 380000;
    its check no longer calls every untouched Windows "active").
  * DNS: IPv4 and IPv6, physical adapters only; revert resets what has the provider's addresses; the check
    looks at IPv6 too — run against simulated network cmdlets.
  * Xbox apps: the TCUI package really matches now; every user and the provisioned copy.
  * Honest presets / texts: automatic updates off and TCP auto-tuning off in no preset; Remove Bloatware
    leaves apps people install themselves; six tweaks without documented effect retired (clean-ups only
    remove their own values).
  * Apply leaves what is already active alone; without a restore point app removals ask first.
  * Registry backup: its own folder (v1 pruned v2's backups and the other way round), no 35-MB Control key.

Windowed (optimizer, apps page): runs on the hidden desktop. No admin, nothing changed on the real
system: registry work on HKCU\\Software\\GameOptimizerPro-Test47 (removed at the end)."""
import os
import re
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


TMP = tempfile.mkdtemp(prefix="gop_r47_")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "LocalAppData")      # backups: never the user's
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

from core import registry_backup as RB  # noqa: E402
from core import restore_point as RP  # noqa: E402
from core import tweak_presets as TP  # noqa: E402
from core import tweaks as T  # noqa: E402
from core import user_presets as UP  # noqa: E402
from core.tweak_i18n import TWEAK_DESC_EN, TWEAK_NAME_EN  # noqa: E402
from core.tweak_verifier import VERIFY_MAP, reg_spec  # noqa: E402

UP.PRESETS_FILE = Path(TMP) / "presets.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEST = r"Software\GameOptimizerPro-Test47"


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="oem", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def hkcu_keys():
    _rc, out, _e = ps("[Microsoft.Win32.Registry]::CurrentUser.GetSubKeyNames() -join '|'")
    return set(out.split("|"))


HKCU_BEFORE = hkcu_keys() if os.name == "nt" else set()

# ── 1. Power plans: each plan's own values ───────────────────────────────────
print("power plans: each plan's own values kept and put back")
BAL, HIGH, SAVER = "381b4222-f694-41f0-9685-ff5bb260df2e", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "a1841308-3541-4fab-bc81-f71556f20b4a"
ULT = "24673e4c-7810-4939-a5f8-85f2ddd31b1e"       # a copy of 'Ultimate Performance': no Windows default
STORE_PS = (f"$global:ST='{TEST}\\PowerOrig'; ")

# a simulated powercfg: plans and values in $global:P, every change logged in $global:L
MOCK = r"""
$global:P=@{}; $global:L=@()
function powercfg {
  $a=@($args); $global:LASTEXITCODE=0
  switch -Regex ("$($a[0])") {
    '^/L$' { foreach($s in $global:PL){ "GUID des Energieschemas: $($s.g)  ($($s.n))" }; return }
    '^/qh$' { $k="$($a[1])"; $ac=$global:P["$k|ac"]; $dc=$global:P["$k|dc"]; if($null -eq $ac){ return }
              "Index AC: 0x{0:x8}" -f [int64]$ac; "Index DC: 0x{0:x8}" -f [int64]$dc; return }
    '^/SETACVALUEINDEX$' { $global:P["$($a[1])|ac"]=[int64]$a[4]; $global:L+=("AC "+$a[1]+" "+$a[4]); return }
    '^/SETDCVALUEINDEX$' { $global:P["$($a[1])|dc"]=[int64]$a[4]; $global:L+=("DC "+$a[1]+" "+$a[4]); return }
    default { return } } }
"""


def plans_ps(values):
    """values: {guid: (name, ac, dc)} -> PowerShell that sets up the simulated plans"""
    pl = ",".join(f"@{{g='{g}';n='{n}'}}" for g, (n, _a, _d) in values.items())
    pv = "; ".join(f"$global:P['{g}|ac']={a}; $global:P['{g}|dc']={d}" for g, (_n, a, d) in values.items())
    return f"$global:PL=@({pl}); {pv}; "


def to_scratch(cmd):
    return (cmd.replace("[Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('SOFTWARE\\GameOptimizerPro\\PowerOrig')",
                        f"[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{TEST}\\PowerOrig')")
               .replace("[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('SOFTWARE\\GameOptimizerPro\\PowerOrig',$true)",
                        f"[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{TEST}\\PowerOrig',$true)"))


DUMP = ("; Write-Output ('VALS ' + (($global:P.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Name + '=' + $_.Value }) -join ' ')); "
        f"$k=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{TEST}\\PowerOrig'); "
        "Write-Output ('KEPT ' + $(if($k){ ($k.GetValueNames() | Sort-Object | ForEach-Object { $_ + '=' + $k.GetValue($_) }) -join ' ' }))")


def no_exit(script):
    """The scripts end with `exit N` — here they run inside one PowerShell with the checks after them."""
    return re.sub(r"\bexit \d", "return", script)


def run_power(setup, *scripts):
    body = MOCK + setup + "; ".join(f"& {{ {no_exit(to_scratch(s))} }} | Out-Null" for s in scripts) + DUMP
    rc, out, err = ps(body)
    vals = dict(x.split("=", 1) for x in re.search(r"VALS (.*)", out).group(1).split() if "=" in x) if "VALS" in out else {}
    kept_line = re.search(r"KEPT ?(.*)", out)
    kept = dict(x.split("=", 1) for x in kept_line.group(1).split() if "=" in x) if kept_line else {}
    return vals, kept, err


def clear_store():
    ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}\\PowerOrig', $false)")


aspm = T.get_by_id("power_pcie_aspm_off")
plans = {BAL: ("Ausbalanciert", 1, 2), HIGH: ("Höchstleistung", 0, 0), SAVER: ("Energiesparmodus", 2, 2),
         ULT: ("Ultimative Leistung", 0, 0)}
if os.name == "nt":
    clear_store()
    vals, kept, err = run_power(plans_ps(plans), aspm.ps_command)
    check(all(vals.get(f"{g}|ac") == "0" for g in plans) and vals.get(f"{BAL}|dc") == "2"
          and kept.get(f"power_pcie_aspm_off|{BAL}") == "1" and kept.get(f"power_pcie_aspm_off|{SAVER}") == "2",
          f"ASPM off: every plan on mains power, battery untouched, each plan's value kept {kept} {err[:80]}")
    vals, kept, _e = run_power(plans_ps({g: (n, 0, d) for g, (n, _a, d) in plans.items()}), aspm.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "1" and vals.get(f"{HIGH}|ac") == "0" and vals.get(f"{SAVER}|ac") == "2"
          and not kept, f"revert: each plan back to ITS value (Balanced 'moderate', not 'maximum'), store emptied {vals}")
    clear_store()
    # applied by an older version (nothing kept): the Windows default — only where the tweak's value still is
    old = {BAL: ("Ausbalanciert", 0, 2), HIGH: ("Höchstleistung", 0, 0), SAVER: ("Energiesparmodus", 1, 2),
           ULT: ("Ultimative Leistung", 0, 0)}
    vals, kept, _e = run_power(plans_ps(old), aspm.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "1" and vals.get(f"{HIGH}|ac") == "0" and vals.get(f"{SAVER}|ac") == "1"
          and vals.get(f"{ULT}|ac") == "0",
          "nothing kept: Balanced -> its default (moderate); a plan changed since (power saver) and a copy "
          f"without a default stay as they are {vals}")
    slp = T.get_by_id("power_sleep_off")
    p2 = {BAL: ("Ausbalanciert", 1800, 900), HIGH: ("Höchstleistung", 0, 0)}
    clear_store()
    vals, kept, _e = run_power(plans_ps(p2), slp.ps_command)
    check(vals.get(f"{BAL}|ac") == "0" and vals.get(f"{BAL}|dc") == "0" and kept.get(f"power_sleep_off|{BAL}") == "1800|900",
          f"sleep off: mains AND battery, both values kept ({kept})")
    vals, _k, _e = run_power(plans_ps({BAL: ("Ausbalanciert", 0, 0), HIGH: ("Höchstleistung", 0, 0)}), slp.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "1800" and vals.get(f"{BAL}|dc") == "900",
          f"... revert: 30 / 15 min again (it wrote 60 / 30 min before) {vals}")
    clear_store()
    vals, _k, _e = run_power(plans_ps({BAL: ("Ausbalanciert", 0, 0), HIGH: ("Höchstleistung", 0, 0)}), slp.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "1800" and vals.get(f"{BAL}|dc") == "900" and vals.get(f"{HIGH}|ac") == "0",
          f"... nothing kept: Windows' own (Balanced 30 / 15 min, High performance never) {vals}")
    cpu = T.get_by_id("power_cpu_min_100")
    clear_store()
    vals, _k, _e = run_power(plans_ps({BAL: ("Ausbalanciert", 100, 100), HIGH: ("Höchstleistung", 100, 100)}), cpu.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "5" and vals.get(f"{HIGH}|ac") == "100" and vals.get(f"{HIGH}|dc") == "5",
          f"CPU minimum: Balanced 5 %, High performance 100 % on mains (it wrote 5 % everywhere) {vals}")
    disp = T.get_by_id("power_display_sleep_15")
    clear_store()
    p3 = {BAL: ("Ausbalanciert", 600, 300), HIGH: ("Höchstleistung", 900, 600), ULT: ("Ultimative Leistung", 0, 0)}
    vals, kept, _e = run_power(plans_ps(p3), disp.ps_command)
    check(vals.get(f"{BAL}|ac") == "900" and vals.get(f"{BAL}|dc") == "300" and vals.get(f"{HIGH}|ac") == "900"
          and vals.get(f"{HIGH}|dc") == "600" and vals.get(f"{ULT}|ac") == "0" and len(kept) == 1,
          f"display sleep: High performance and the Ultimate copy left alone {vals}")
    vals, kept, _e = run_power(plans_ps({BAL: ("Ausbalanciert", 900, 300), HIGH: ("Höchstleistung", 900, 600)}), disp.revert_cmd)
    check(vals.get(f"{BAL}|ac") == "600" and vals.get(f"{BAL}|dc") == "300" and not kept,
          f"... revert: 10 / 5 min (Balanced's own — it wrote 10 / 2 min) {vals}")
    usb = T.get_by_id("disable_usb_suspend")
    check("standby-timeout" not in usb.ps_command and T._USB_SS in usb.ps_command and "PowerOrig" in usb.revert_cmd,
          "USB selective suspend: no hidden 'sleep never' any more, every plan, value kept")
    clear_store()
check(T.get_by_id("power_disk_never_sleep").revert_cmd.count("1200") == 0
      and "DefaultPowerSchemeValues" in T.get_by_id("power_disk_never_sleep").revert_cmd,
      "disk: no fixed 20 min — the plan's own value")

# ── 2. Kept registry values: HAGS, svchost, background apps ─────────────────
print("HAGS, svchost threshold, background apps: the value before comes back")
STORE_REAL = "'Software\\GameOptimizerPro\\RegOrig'"


def scratch(cmd, items):
    for n, p in enumerate(dict.fromkeys(i[1] for i in items)):
        cmd = cmd.replace("'" + p + "'", f"'{TEST}\\k{n}'")
    return cmd.replace(STORE_REAL, f"'{TEST}\\Store'").replace("@('HKLM',", "@('HKCU',")


def get(path, name):
    _rc, out, _e = ps(f"$k=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{path}'); "
                      f"$v=$(if($k){{ $k.GetValue('{name}',$null) }}); if($null -eq $v){{'<none>'}}else{{\"$v\"}}")
    return out


def setv(path, name, value):
    ps(f"$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{path}'); $k.SetValue('{name}',{value},'DWord')")


if os.name == "nt":
    hags = T.get_by_id("enable_hags")
    setv(f"{TEST}\\k0", "HwSchMode", 2)                 # HAGS was ON before
    ps(scratch(hags.ps_command, T.HAGS_ITEMS))
    ps(scratch(hags.revert_cmd, T.HAGS_ITEMS))
    check(get(f"{TEST}\\k0", "HwSchMode") == "2", "HAGS on before -> still on after revert (it switched it OFF: DLSS Frame Generation needs it)")
    ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}\\k0',$false)")
    ps(scratch(hags.ps_command, T.HAGS_ITEMS))
    ps(scratch(hags.revert_cmd, T.HAGS_ITEMS))
    check(get(f"{TEST}\\k0", "HwSchMode") == "<none>", "not set before -> removed again (Windows decides)")
    ps(scratch(hags.revert_cmd, T.HAGS_ITEMS))         # applied by an older version: nothing kept
    check(get(f"{TEST}\\k0", "HwSchMode") == "<none>", "nothing kept -> removed, never forced off")
    sv = T.get_by_id("reduce_process_count")
    setv(f"{TEST}\\k0", "SvcHostSplitThresholdInKB", 0x380000)
    ps(scratch(sv.ps_command, T.SVCHOST_ITEMS))
    applied = get(f"{TEST}\\k0", "SvcHostSplitThresholdInKB")
    ps(scratch(sv.revert_cmd, T.SVCHOST_ITEMS))
    check(applied.isdigit() and int(applied) > 0x380000 and get(f"{TEST}\\k0", "SvcHostSplitThresholdInKB") == str(0x380000),
          f"svchost: set to the RAM size ({applied} KB), revert -> 0x380000 = 3670016 (it wrote the decimal 380000)")
    ps(scratch(sv.revert_cmd, T.SVCHOST_ITEMS))
    check(get(f"{TEST}\\k0", "SvcHostSplitThresholdInKB") == "3670016", "nothing kept -> Windows' 0x380000")
    vcmd = VERIFY_MAP["reduce_process_count"].replace("HKLM:\\SYSTEM\\CurrentControlSet\\Control", f"HKCU:\\{TEST}\\k0")
    v_default = ps(vcmd)[1]
    setv(f"{TEST}\\k0", "SvcHostSplitThresholdInKB", 33181792)
    check(v_default == "0" and ps(vcmd)[1] == "1", "the check: an untouched Windows (0x380000) is NOT active, the RAM value is")
    bg = T.get_by_id("disable_bg_throttle")
    check("DisableLowQosTimerResolution" not in bg.ps_command and "DisableLowQosTimerResolution" in bg.revert_cmd
          and "-eq 1" in bg.revert_cmd, "background apps: the undocumented kernel value is no longer set; revert removes it only when it is 1")
    ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}\\k0',$false)")
    rv = scratch(bg.revert_cmd, T.BGAPPS_ITEMS).replace("HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel", f"HKCU:\\{TEST}\\kern")
    setv(f"{TEST}\\kern", "DisableLowQosTimerResolution", 1)
    ps(scratch(bg.ps_command, T.BGAPPS_ITEMS))
    on = get(f"{TEST}\\k0", "GlobalUserDisabled")
    ps(rv)
    check(on == "1" and get(f"{TEST}\\k0", "GlobalUserDisabled") == "<none>" and get(f"{TEST}\\kern", "DisableLowQosTimerResolution") == "<none>",
          "apply -> background apps off; revert -> the value before (none) and the old kernel value gone")
check(bg.name.startswith("Hintergrund-Apps") and TWEAK_NAME_EN["disable_bg_throttle"].startswith("Stop background apps")
      and "WhatsApp" in bg.desc and "WhatsApp" in TWEAK_DESC_EN["disable_bg_throttle"],
      "honest name and text: it stops background Store apps (their notifications too) — not 'throttling'")

# ── 3. DNS: IPv4 and IPv6, physical adapters ─────────────────────────────────
print("DNS: IPv4 and IPv6, physical adapters only")
NETMOCK = r"""
$global:ADP=@(); $global:DNS=@(); $global:CALLS=@()
function Get-NetAdapter { [CmdletBinding()] param([switch]$Physical)
  $global:ADP | Where-Object { (-not $Physical) -or $_.Phys } }
function Get-DnsClientServerAddress { [CmdletBinding()] param($InterfaceIndex, $AddressFamily)
  $global:DNS | Where-Object { ($null -eq $InterfaceIndex -or $_.InterfaceIndex -eq $InterfaceIndex) -and ($null -eq $AddressFamily -or $_.AddressFamily -eq $AddressFamily) } }
function Set-DnsClientServerAddress { [CmdletBinding()] param($InterfaceIndex, $ServerAddresses, [switch]$ResetServerAddresses)
  $a=$global:ADP | Where-Object { $_.InterfaceIndex -eq $InterfaceIndex }
  if($ServerAddresses -and @($ServerAddresses | Where-Object { $_ -match ':' }).Count -and $a.NoV6){ throw 'no IPv6' }
  $global:CALLS += ("{0}:{1}" -f $InterfaceIndex, $(if($ResetServerAddresses){'reset'}else{$ServerAddresses -join ','})) }
function A($i,$n,$phys,$nov6){ $global:ADP += [pscustomobject]@{InterfaceIndex=$i; Name=$n; Status='Up'; Phys=$phys; NoV6=$nov6} }
function D($i,$fam,$srv){ $global:DNS += [pscustomobject]@{InterfaceIndex=$i; AddressFamily=$fam; ServerAddresses=@($srv)} }
"""


def dns(setup, script):
    rc, out, err = ps(NETMOCK + setup + "\n$r = & { " + no_exit(script) + " }; Write-Output ('RES ' + ($r -join ' ')); "
                      "Write-Output ('CALLS ' + ($global:CALLS -join ' '))")
    res = re.search(r"RES ?(.*)", out)
    calls = re.search(r"CALLS ?(.*)", out)
    return (res.group(1).strip() if res else None), (calls.group(1).split() if calls else []), err


if os.name == "nt":
    ver = VERIFY_MAP["dns_cloudflare"]
    router = "A 1 'Ethernet' $true $false; D 1 'IPv4' @('1.1.1.1','1.0.0.1'); D 1 'IPv6' @('fd6d::1','2a02::1')"
    check(dns(router, ver)[0] == "0", "IPv4 Cloudflare but IPv6 from the router -> not active (it said active)")
    both = "A 1 'Ethernet' $true $false; D 1 'IPv4' @('1.1.1.1','1.0.0.1'); D 1 'IPv6' @('2606:4700:4700::1111')"
    check(dns(both, ver)[0] == "1", "IPv4 and IPv6 Cloudflare -> active")
    no6 = "A 1 'Ethernet' $true $false; D 1 'IPv4' @('1.1.1.1'); D 1 'IPv6' @()"
    check(dns(no6, ver)[0] == "1", "no IPv6 DNS at all -> IPv4 is enough")
    vpn = both + "; A 7 'vEthernet' $false $false; D 7 'IPv4' @('10.0.0.1')"
    check(dns(vpn, ver)[0] == "1", "a virtual adapter with its own DNS doesn't count")
    check(dns("", ver)[0] == "0", "no active physical adapter -> not active")
    setup = ("A 1 'Ethernet' $true $false; A 2 'WLAN' $true $true; A 7 'vEthernet' $false $false; "
             "D 7 'IPv4' @('1.1.1.1')")
    _r, calls, err = dns(setup, T.get_by_id("dns_cloudflare").ps_command)
    check(calls[:1] == ["1:1.1.1.1,1.0.0.1,2606:4700:4700::1111,2606:4700:4700::1001"] and "2:1.1.1.1,1.0.0.1" in calls
          and not any(c.startswith("7:") for c in calls),
          f"apply: IPv4 + IPv6 on the physical adapters, IPv4 only where IPv6 can't be set, VPN/virtual untouched {calls} {err[:60]}")
    setup = ("A 1 'Ethernet' $true $false; A 7 'vEthernet' $false $false; A 8 'Other' $true $false; "
             "D 1 'IPv4' @('1.1.1.1'); D 7 'IPv4' @('1.0.0.1'); D 8 'IPv4' @('9.9.9.9')")
    _r, calls, _e = dns(setup, T.get_by_id("dns_cloudflare").revert_cmd)
    check(sorted(set(calls)) == ["1:reset", "7:reset"],
          f"revert: every adapter with Cloudflare's addresses (older versions set virtual ones too), no other {calls}")
check(T.DNS_PROVIDERS["dns_google"][1][0] == "2001:4860:4860::8888" and "IPv6" in T.get_by_id("dns_google").desc,
      "Google: IPv6 too")

# ── 4. Xbox apps, bloatware, honest presets, retired tweaks ──────────────────
print("Xbox apps, bloatware, presets, retired tweaks")
if os.name == "nt":
    _rc, like, _e = ps("$n='Microsoft.Xbox.TCUI'; \"$($n -like '*XboxTCUI*') $($n -like '*Microsoft.Xbox.TCUI*')\"")
    check(like == "False True", "the TCUI package: the old pattern never matched it, the new one does")
x = T.get_by_id("remove_xbox")
check("Get-AppxProvisionedPackage" in x.ps_command and all(a in x.ps_command for a in T.XBOX_APPS)
      and all(a in VERIFY_MAP["remove_xbox"] for a in T.XBOX_APPS),
      "Xbox apps: every user AND the provisioned copy; the check looks at all six (not only the Game Bar)")
bl = T.get_by_id("remove_bloatware").ps_command
check(not any(a in bl for a in ("Spotify", "Netflix", "Disney", "TikTok", "Instagram", "Facebook", "Twitter"))
      and "CandyCrush" in bl and "Microsoft.BingWeather" in bl and "Spotify" in TWEAK_DESC_EN["remove_bloatware"],
      "Remove Bloatware leaves apps people install themselves (and says so); Microsoft's extras + pushed games go")
tiers = set(TP._TIER_MINIMAL) | set(TP._MEDIUM_EXTRA) | set(TP._HARD_EXTRA)
in_any = {i for p in TP.BUILTIN_PRESETS for i in p.tweak_ids}
check(not ({"disable_wu_gaming", "disable_tcp_autotuning"} & (tiers | in_any)),
      "automatic updates off and TCP auto-tuning off: in no preset any more")
wu = T.get_by_id("disable_wu_gaming")
check(wu.risk == "advanced" and "dauerhaft" in wu.desc and "Sicherheitsupdates" in wu.desc
      and TWEAK_NAME_EN["disable_wu_gaming"] == "Turn off automatic Windows updates",
      "honest name and text: automatic updates off for good, security updates included")
check("25 Mbit/s" in T.get_by_id("disable_tcp_autotuning").desc, "TCP auto-tuning: says downloads get slower")
check("disable_bg_throttle" in TP._HARD_EXTRA and "disable_bg_throttle" not in TP._MEDIUM_EXTRA
      and "disable_bg_throttle" not in next(p for p in TP.BUILTIN_PRESETS if p.id == "gaming").tweak_ids,
      "background apps off: Hart only (it silences Store apps' notifications)")
RETIRED = ("nvme_queue_depth", "tcp_optimize", "disable_qos_limit", "amd_shader_cache", "amd_antilag",
           "start_menu_previous_layout")
check(all(T.get_by_id(r) is None and r in T.RETIRED_TWEAKS and r not in VERIFY_MAP and r not in TWEAK_DESC_EN
          and r not in in_any for r in RETIRED) and len(T.ALL_TWEAKS) == 112,
      "six tweaks without documented effect retired (no tweak, check, text or preset) — 112 left")
check(all("-eq" in T.RETIRED_TWEAKS[r][2] for r in ("nvme_queue_depth", "disable_qos_limit", "amd_shader_cache",
                                                  "amd_antilag", "start_menu_previous_layout")),
      "their clean-ups remove a value only when it is the one the tweak wrote")
if os.name == "nt":
    qos = T.RETIRED_TWEAKS["disable_qos_limit"][2].replace("HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Psched", f"HKCU:\\{TEST}\\q")
    setv(f"{TEST}\\q", "NonBestEffortLimit", 0)
    ps(qos)
    first = get(f"{TEST}\\q", "NonBestEffortLimit")
    setv(f"{TEST}\\q", "NonBestEffortLimit", 30)          # someone else's value
    ps(qos)
    check(first == "<none>" and get(f"{TEST}\\q", "NonBestEffortLimit") == "30",
          "QoS clean-up: removes its own 0, leaves another value alone")
    sm = T.RETIRED_TWEAKS["start_menu_previous_layout"][2].replace(
        "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FeatureManagement\\Overrides\\8\\3036241548", f"HKCU:\\{TEST}\\sm")
    setv(f"{TEST}\\sm", "EnabledState", 1)
    ps(sm)
    check(get(f"{TEST}\\sm", "EnabledState") == "<none>", "start menu clean-up: the override is gone")
fd = T.get_by_id("explorer_folder_discovery")
check(fd.risk == "moderate" and "Bags'" not in fd.revert_cmd.replace("AllFolders", "") and "FolderType" in fd.revert_cmd
      and "fd" and "explorer_folder_discovery" not in TP.get_all_safe_ids(),
      "folder views: revert only takes its default back (it wiped every view again); not in 'All safe'")
if os.name == "nt":
    BAGS = "HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\Bags"
    rv = fd.revert_cmd.replace(BAGS, f"HKCU:\\{TEST}\\Bags")
    setv(f"{TEST}\\Bags\\1\\Shell", "Mode", 4)
    ps(f"$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{TEST}\\Bags\\AllFolders\\Shell'); $k.SetValue('FolderType','NotSpecified')")
    ps(rv)
    check(get(f"{TEST}\\Bags\\1\\Shell", "Mode") == "4" and get(f"{TEST}\\Bags\\AllFolders\\Shell", "FolderType") == "<none>",
          "... run: a folder's saved view stays, only 'General items for all' goes")
check(not any(re.search(r"Write-Output[^;]*\b(fuer|ueber|Hoechstleistung)\b", t.ps_command) for t in T.ALL_TWEAKS),
      "messages from the tweak scripts with real umlauts")

# ── 5. Restore point before app removals ─────────────────────────────────────
print("restore point")
check(RP.classify("OK")[2] == "ok" and RP.classify("WARN: ... created within the past 1440 minutes")[2] == "skipped"
      and RP.classify("ERR: Die Systemwiederherstellung ist deaktiviert")[2] == "off"
      and RP.classify("ERR: Zugriff verweigert")[2] == "denied" and RP.classify("ERR: kaputt")[2] == "error",
      "made / skipped (24 h) / protection off / no admin / other — told apart (a skipped one was reported as made)")
scr = RP._script("x")
check("SystemRestorePointCreationFrequency -Value 0" in scr and "finally" in scr and "Remove-ItemProperty" in scr,
      "the 24-hour limit is lifted for this one point (documented value) and put back right after")
check("Ohne ihn bringt nur der Microsoft Store" in RP.ask_text("x"), "the question says what is lost without it")

# ── 6. Registry backup: its own folder, small ────────────────────────────────
print("registry backup")
check(r"HKLM\SYSTEM\CurrentControlSet\Control" not in RB.BACKUP_KEYS
      and {r"HKLM\SYSTEM\CurrentControlSet\Control\Power", r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
           r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager"} <= set(RB.BACKUP_KEYS)
      and "SvcHostSplitThresholdInKB" in RB.CONTROL_VALUES,
      "not the whole Control key (35 MB) — the branches the tweaks touch + the one value on Control itself")
check(RB.backup_root().endswith(os.path.join("GameOptimizerPro-v2", "RegistryBackups")),
      "its own folder: v1's limit no longer deletes v2's backups (nor v2's v1's)")
if os.name == "nt":
    old_root = Path(os.environ["LOCALAPPDATA"]) / "GameOptimizerPro" / "RegistryBackups" / "20260101_000000_PreApply"
    old_root.mkdir(parents=True)
    for n in range(12):
        (Path(RB.backup_root()) / f"2026010{n // 10}_{n:06d}_PreApply").mkdir(parents=True)
    RB.prune(10)
    check(len(RB.list_backups()) == 10 and old_root.is_dir(), "pruning keeps 10 in its own folder, the shared one untouched")
    setv(f"{TEST}\\ctl", "SvcHostSplitThresholdInKB", 0x380000)
    out = os.path.join(TMP, "v.reg")
    ok = RB.export_values(f"HKCU\\{TEST}\\ctl", ("SvcHostSplitThresholdInKB", "Missing"), out)
    raw = open(out, "rb").read()
    text = raw.decode("utf-16")
    check(ok and raw[:2] == b"\xff\xfe" and '"SvcHostSplitThresholdInKB"=dword:00380000' in text and '"Missing"=-' in text,
          "values exported like reg.exe (UTF-16), a missing value as '=-'")
    setv(f"{TEST}\\ctl", "SvcHostSplitThresholdInKB", 1)
    setv(f"{TEST}\\ctl", "Missing", 5)
    subprocess.run(["reg.exe", "import", out], capture_output=True, creationflags=NO_WINDOW)
    check(get(f"{TEST}\\ctl", "SvcHostSplitThresholdInKB") == str(0x380000) and get(f"{TEST}\\ctl", "Missing") == "<none>",
          "double-clicking it puts the state back (value restored, the one that wasn't there removed)")
    t0 = time.time()
    res = RB.create("SelfTest47")
    size = sum(os.path.getsize(f) for f in res.files) / 1e6
    check(res.ok and size < 15, f"a whole backup: {res.saved} branches, {size:.1f} MB in {time.time() - t0:.0f} s (was ~37 MB)")

# ── 7. UI: apply leaves active tweaks alone; app removals ask without a restore point ─────
print("UI")
import faulthandler  # noqa: E402
faulthandler.dump_traceback_later(180, exit=True)     # a hang shows where it is instead of waiting for the runner
import tkinter as tk  # noqa: E402
from tkinter import messagebox  # noqa: E402

import customtkinter as ctk  # noqa: E402

from core.hardware import HardwareInfo  # noqa: E402
from core.tweak_runner import TweakRunner  # noqa: E402
from core.tweak_verifier import TweakVerifier  # noqa: E402

BOXES, ANSWERS = [], []
real_mb = {n: getattr(messagebox, n) for n in ("askyesno", "showinfo", "showwarning", "showerror")}
messagebox.askyesno = lambda *a, **k: (BOXES.append(("askyesno",) + a), ANSWERS.pop(0) if ANSWERS else True)[1]
messagebox.showinfo = lambda *a, **k: BOXES.append(("showinfo",) + a)
messagebox.showwarning = lambda *a, **k: BOXES.append(("showwarning",) + a)
messagebox.showerror = lambda *a, **k: BOXES.append(("showerror",) + a)
real_verify, real_rp = TweakVerifier.verify_all, RP.create_ex
TweakVerifier.verify_all = lambda self, ids, exp: {}
RP.create_ex = lambda d="": (False, "Computerschutz ist auf dem Systemlaufwerk aus.", "off")
root = ctk.CTk()
root.geometry("1200x850")
root.attributes("-alpha", 0.0)


def loop_until(cond, secs=10.0):
    end = time.time() + secs

    def done():
        try:
            return cond()
        except Exception as e:                         # a broken condition must not keep the loop running
            print("  (condition failed:", repr(e), ")", flush=True)
            return True

    def tick():
        if done() or time.time() > end:
            root.quit()
        else:
            root.after(30, tick)
    root.after(30, tick)
    root.mainloop()
    return cond()


# the root's first main loop before the pages are built: on the hidden desktop a first main loop with
# the whole optimizer page already in it blocked natively here (bisected — not the app's code)
loop_until(lambda: False, 0.3)
try:
    ran = []
    runner = TweakRunner(log_dir=os.path.join(TMP, "tw"))
    runner.backup_registry = lambda label: None
    runner._run_ps = lambda cmd, timeout=60: (ran.append(cmd), (True, "ok"))[1]
    from ui import tab_optimizer as TO
    opt = TO.OptimizerTab(root, runner, HardwareInfo(), profiles_dir=os.path.join(TMP, "p"), logs_dir=TMP)
    opt.pack(fill="both", expand=True)
    loop_until(lambda: not opt._verifying, 5)
    loop_until(lambda: False, 0.3)
    for v in opt._vars.values():
        v.set(False)
    opt._verify_states["disable_telemetry"] = True        # already on, set outside the app
    opt._verify_states["disable_game_bar"] = False
    opt._vars["disable_telemetry"].set(True)
    opt._vars["disable_game_bar"].set(True)
    BOXES.clear()
    ANSWERS[:] = [True]
    opt._apply_selected()
    loop_until(lambda: not opt._batch_running and ran, 10)
    loop_until(lambda: False, 0.3)
    ask = next((b for b in BOXES if b[0] == "askyesno"), None)
    check(ask is not None and "Schon aktiv" in ask[2] and runner.is_applied("disable_game_bar")
          and not runner.is_applied("disable_telemetry"),
          "'Apply selected' leaves a tweak that is already active alone (and says so) — it ran its script again")
    for v in opt._vars.values():
        v.set(False)
    opt._vars["remove_copilot"].set(True)
    opt._vars["disable_mouse_accel"].set(True)
    opt._verify_states["remove_copilot"] = False
    opt._verify_states["disable_mouse_accel"] = False
    ran.clear()
    BOXES.clear()
    ANSWERS[:] = [True, False]                           # apply: yes — without a restore point: no
    opt._apply_selected()
    loop_until(lambda: not opt._batch_running and len([b for b in BOXES if b[0] == "askyesno"]) >= 2, 10)
    loop_until(lambda: False, 0.5)
    rp_q = [b for b in BOXES if b[0] == "askyesno"][1:2]
    log = opt.log.txt.get("1.0", "end")
    check(rp_q and "Computerschutz" in rp_q[0][2] and runner.is_applied("disable_mouse_accel")
          and not runner.is_applied("remove_copilot") and "Nicht entfernt" in log,
          "no restore point: asked first — on 'no' only the app removal stays out, the rest is applied")
    opt.destroy()

    from core import services
    from core import app_removal as AR
    from ui import apps_page as AP
    real_ap = {"admin": services.is_admin, "list": AR.list_apps, "remove": AR.remove}
    removed = []
    try:
        AP.services.is_admin = lambda: True
        AP.app_removal.list_apps = lambda: AR.parse_list('{"name": "Clipchamp.Clipchamp", "display": "Clipchamp"}')
        AP.app_removal.remove = lambda name: (removed.append(name), (True, ""))[1]
        page = AP.AppsPage(root)
        page.pack(fill="both", expand=True)
        page.on_show()
        loop_until(lambda: page._loaded["apps"] and not page._loading["apps"], 5)
        page.tree_apps.selection_set(["Clipchamp.Clipchamp"])
        BOXES.clear()
        ANSWERS[:] = [True, False]
        page._remove()
        loop_until(lambda: not page._busy, 8)
        loop_until(lambda: False, 0.3)
        check(not removed and len([b for b in BOXES if b[0] == "askyesno"]) == 2 and "Nichts" in page.lbl_apps.cget("text"),
              "Apps page, no restore point and 'no': nothing removed")
        ANSWERS[:] = [True, True]
        page.tree_apps.selection_set(["Clipchamp.Clipchamp"])
        page._remove()
        loop_until(lambda: removed and not page._busy, 8)
        check(removed == ["Clipchamp.Clipchamp"], "... and 'yes': removed without it")
        page.destroy()
    finally:
        AP.services.is_admin = real_ap["admin"]
        AP.app_removal.list_apps, AP.app_removal.remove = real_ap["list"], real_ap["remove"]
finally:
    TweakVerifier.verify_all, RP.create_ex = real_verify, real_rp
    for n, f in real_mb.items():
        setattr(messagebox, n, f)
    try:
        root.destroy()
    except Exception:
        pass
    if os.name == "nt":
        ps(f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{TEST}', $false)")

if os.name == "nt":
    check(hkcu_keys() <= HKCU_BEFORE, "nothing new left under HKCU (scratch keys removed)")

# ── 8. Docs ──────────────────────────────────────────────────────────────────
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
readme_de = open(os.path.join(ROOT, "README.de.md"), encoding="utf-8").read()
check(f"**{len(T.ALL_TWEAKS)} Windows tweaks**" in readme and f"**{len(T.ALL_TWEAKS)} Windows-Tweaks**" in readme_de,
      f"README EN/DE name the tweak count ({len(T.ALL_TWEAKS)})")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
