"""Round 45 — new tweaks checked against Windows 11 26H2, Store apps, program installer.

  * 14 new tweaks (tips & ads, typing/speech data, OneDrive folder move, Remote Assistance, drivers
    through Windows Update, staying on the Windows version, Store apps in the background, USB 3 link
    power saving, wake timers, autostart delay, Explorer 'This PC', Alt+Tab, Dynamic Lighting, the
    controller's Game Bar button) — texts in both languages, status checks, presets, edition filter.
  * Registry values the user may have chosen: apply keeps them, revert writes exactly them back —
    every such tweak run for real against scratch copies of its keys (never the real keys).
  * Power settings: the plans' own values are kept; without administrator rights nothing changes.
  * Extended tweaks: more telemetry tasks, search highlights / cloud search, 'Recommended' on Home/Pro,
    visual effects through SystemParametersInfo (the readable look kept) — earlier applies stay "active".
  * BitLocker in the health report and as a warning in the BIOS guide.
  * Store apps: rating, protected apps never offered or removed; program installer through winget.

Windowed (BIOS guide, Apps page): runs on the hidden desktop. No GPU, no admin, nothing installed or
removed for real."""
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


TMP = tempfile.mkdtemp(prefix="gop_r45_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"

from core import app_removal as AR  # noqa: E402
from core import hardware  # noqa: E402
from core import health_report as HR  # noqa: E402
from core import optimization_score as OS  # noqa: E402
from core import tweak_presets as TP  # noqa: E402
from core import winget_installer as WI  # noqa: E402
from core import tweaks as T  # noqa: E402
from core.hardware import HardwareInfo  # noqa: E402
from core.tweak_i18n import TWEAK_DESC_EN, TWEAK_NAME_EN  # noqa: E402
from core.tweak_verifier import VERIFY_MAP, reg_check, reg_spec  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEST = r"Software\GameOptimizerPro-Test45"
IS_ADMIN = False
if os.name == "nt":
    import ctypes
    IS_ADMIN = bool(ctypes.windll.shell32.IsUserAnAdmin())


def ps(cmd, timeout=120):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


NEW = ["disable_tips_suggestions", "disable_input_speech_data", "onedrive_block_kfm", "disable_remote_assistance",
       "exclude_wu_drivers", "wu_pin_feature_version", "disable_background_apps", "usb3_link_power_off",
       "disable_wake_timers", "startup_delay_off", "explorer_open_this_pc", "alt_tab_windows_only",
       "disable_dynamic_lighting", "controller_no_game_bar"]

# ── 1. The new tweaks ────────────────────────────────────────────────────────────────────────
print("the new tweaks")
ids = [t.id for t in T.ALL_TWEAKS]
check(len(ids) == 112 and len(set(ids)) == 112 and all(n in ids for n in NEW), f"112 tweaks (round 47: 6 retired), the 14 new ones in ({len(ids)})")
check(all(n in VERIFY_MAP and n in TWEAK_DESC_EN and n in TWEAK_NAME_EN for n in NEW),
      "each: a status check, an English name and description")
check(all(T.get_by_id(n).desc and T.get_by_id(n).revert_cmd for n in NEW), "each: a German description and a revert")
check(T.PRO_ONLY == {"exclude_wu_drivers", "wu_pin_feature_version", "disable_background_apps"}
      and all(T.get_by_id(n).requires_pro for n in T.PRO_ONLY)
      and not any(t.requires_pro for t in T.ALL_TWEAKS if t.id not in T.PRO_ONLY),
      "the three Pro/Enterprise/Education policies are marked")
check(all("Home" in T.get_by_id(n).desc and "Home" in TWEAK_DESC_EN[n] for n in T.PRO_ONLY),
      "... and say that Home ignores them")
check("disable_dynamic_lighting" in T.WIN11_ONLY and len(T.WIN11_ONLY) == 7, "Dynamic Lighting exists on Windows 11 only")
groups = {t.id: (t.category, t.group) for t in T.ALL_TWEAKS}
check(groups["exclude_wu_drivers"] == ("Windows", "Updates") and groups["wu_pin_feature_version"] == ("Windows", "Updates")
      and groups["usb3_link_power_off"] == ("Windows", "Power Plan")
      and groups["controller_no_game_bar"] == ("Gaming", "In-Game Boosts"), "groups")
risk = {n: T.get_by_id(n).risk for n in NEW}
check({n for n, r in risk.items() if r != "safe"} == T.PRO_ONLY, "only the three update / background policies are 'moderate'")
check("NoAutoRebootWithLoggedOnUsers" not in "".join(t.ps_command for t in T.ALL_TWEAKS),
      "no 'no auto-restart' policy: documented to work only with scheduled installs, not read on 26H2")

print("presets")
mini, med, hard = set(TP._TIER_MINIMAL), set(TP._MEDIUM_EXTRA), set(TP._HARD_EXTRA)
check("disable_tips_suggestions" in mini, "Minimal: Windows' own ads off")
check({"disable_input_speech_data", "onedrive_block_kfm", "disable_remote_assistance", "disable_wake_timers",
       "startup_delay_off", "controller_no_game_bar"} <= med, "Mittel: the safe privacy / comfort ones")
check({"usb3_link_power_off", "exclude_wu_drivers", "disable_background_apps"} <= hard, "Hart: the rest")
tiers = mini | med | hard
check(not ({"wu_pin_feature_version", "disable_dynamic_lighting", "alt_tab_windows_only", "explorer_open_this_pc"} & tiers),
      "in no tier: staying on a version (must be lifted before end of support) and the matters of taste")
check(all(i in ids for p in TP.BUILTIN_PRESETS for i in p.tweak_ids), "no preset names a missing tweak")
priv = next(p for p in TP.BUILTIN_PRESETS if p.id == "privacy").tweak_ids
check({"disable_tips_suggestions", "disable_input_speech_data", "onedrive_block_kfm"} <= set(priv), "Privacy preset")
check({"disable_dynamic_lighting", "alt_tab_windows_only", "explorer_open_this_pc"} <= OS.SCORE_EXCLUDE,
      "matters of taste don't count towards the score")

print("Windows edition")
check(hardware.is_home_edition("Core") and hardware.is_home_edition("CoreSingleLanguage")
      and hardware.is_home_edition("CoreCountrySpecific") and hardware.is_home_edition("CoreN"),
      "Home editions recognised")
check(not hardware.is_home_edition("Professional") and not hardware.is_home_edition("Enterprise")
      and not hardware.is_home_edition("Education") and not hardware.is_home_edition(""),
      "Pro / Enterprise / Education / unknown are not Home (unknown keeps the tweak visible)")
if os.name == "nt":
    ed = hardware.windows_edition()
    check(bool(ed) and hardware.is_home_edition() == hardware.is_home_edition(ed), f"edition of this PC: {ed}")
home = HardwareInfo(os_build=26300, is_win11=True, is_home=True)
pro = HardwareInfo(os_build=26300, is_win11=True, is_home=False)
check(not any(OS.applicable(T.get_by_id(n), home) for n in T.PRO_ONLY)
      and all(OS.applicable(T.get_by_id(n), pro) for n in T.PRO_ONLY), "score / drift filter: hidden on Home only")
from ui.tab_optimizer import OptimizerTab  # noqa: E402


class _Opt:
    _is_applicable = OptimizerTab._is_applicable

    def __init__(self, hw):
        self.hw = hw


check(not any(_Opt(home)._is_applicable(T.get_by_id(n)) for n in T.PRO_ONLY)
      and all(_Opt(pro)._is_applicable(T.get_by_id(n)) for n in T.PRO_ONLY)
      and _Opt(home)._is_applicable(T.get_by_id("disable_tips_suggestions")),
      "Optimizer filter (list, presets, import): Pro-only tweaks hidden on Home, the rest stays")

# ── 2. Kept values: the helper itself ──────────────────────────────────────────────────────────
print("registry values the user may have chosen: kept and put back")
STORE_REAL = "'Software\\GameOptimizerPro\\RegOrig'"


def scratch(cmd, items):
    """The tweak's own script, pointed at scratch copies of its keys (and a scratch store)."""
    for n, p in enumerate(dict.fromkeys(i[1] for i in items)):
        cmd = cmd.replace("'" + p + "'", f"'{TEST}\\k{n}'")
    return cmd.replace(STORE_REAL, f"'{TEST}\\Store'").replace("@('HKLM',", "@('HKCU',")


def read_vals(items):
    paths = {p: f"{TEST}\\k{n}" for n, p in enumerate(dict.fromkeys(i[1] for i in items))}
    q = "; ".join(
        f"$k=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{paths[i[1]]}'); "
        f"$v=$(if($k){{ $k.GetValue('{i[2]}',$null) }}); "
        f"Write-Output ('{i[2]}=' + $(if($null -eq $v){{'<none>'}}else{{\"$v\"}}))" for i in items)
    _rc, out, _e = ps(q)
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def seed(items, originals):
    paths = {p: f"{TEST}\\k{n}" for n, p in enumerate(dict.fromkeys(i[1] for i in items))}
    cmd = [f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue"]
    for p in paths.values():
        cmd.append(f"New-Item 'HKCU:\\{p}' -Force | Out-Null")
    for i in items:
        if i[2] in originals:
            cmd.append(f"New-ItemProperty -LiteralPath 'HKCU:\\{paths[i[1]]}' -Name '{i[2]}' -PropertyType DWord "
                       f"-Value {originals[i[2]]} -Force | Out-Null")
    return ps("; ".join(cmd))


ROOT_KEYS = "(Get-ChildItem 'HKCU:\\' | ForEach-Object { $_.PSChildName }) -join '|'"
HKCU_BEFORE = set(ps(ROOT_KEYS)[1].split("|")) if os.name == "nt" else set()
one = [("HKCU", "X\\A", "One", "DWord", 0, None)]
check(T._reg_items_ps(one).startswith("@(,@(") and T._ROW_GUARD in T._reg_saved_ps("apply", "TT", one)
      and T._ROW_GUARD in T._reg_saved_ps("revert", "TT", one) and T._ROW_GUARD in T._reg_saved_ps("verify", "TT", one),
      "one value: the row stays a row (comma operator), and every loop skips anything that is not a row")
if os.name == "nt":
    _rc, cnt, _e = ps("foreach($i in " + T._reg_items_ps(one) + "){ $i.Count }")
    _rc, cnt2, _e = ps("foreach($i in " + T._reg_items_ps(one * 2) + "){ $i.Count }")
    check(cnt == "6" and cnt2.split() == ["6", "6"], f"PowerShell walks rows, not characters ({cnt!r}, {cnt2.split()})")
if os.name == "nt":
    items = [("HKCU", "X\\A", "One", "DWord", 0, None), ("HKCU", "X\\A", "Two", "DWord", 3, None),
             ("HKCU", "X\\B", "Str", "String", "x", "5")]
    try:
        seed(items, {"One": 1})
        ps(f"New-ItemProperty -LiteralPath 'HKCU:\\{TEST}\\k1' -Name Str -PropertyType String -Value old -Force | Out-Null")
        rc, _o, err = ps(scratch(T._reg_saved_ps("apply", "TT", items), items))
        v = read_vals(items)
        check(rc == 0 and v == {"One": "0", "Two": "3", "Str": "x"}, f"apply sets the targets ({v}) {err[:80]}")
        _rc, chk, _e = ps(scratch(T._reg_saved_ps("verify", "TT", items), items))
        check(chk == "1", "verify: all targets set -> active")
        ps(scratch(T._reg_saved_ps("apply", "TT", items), items))       # a second apply keeps the FIRST originals
        rc, _o, _e = ps(scratch(T._reg_saved_ps("revert", "TT", items), items))
        v = read_vals(items)
        check(rc == 0 and v == {"One": "1", "Two": "<none>", "Str": "old"},
              f"revert: the user's own values back, a value that did not exist removed again ({v})")
        _rc, kind, _e = ps(f"[string][Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('{TEST}\\k1').GetValueKind('Str')")
        check(kind == "String", "... with their own value type")
        _rc, chk, _e = ps(scratch(T._reg_saved_ps("verify", "TT", items), items))
        check(chk == "0", "verify after revert: not active")
        _rc, st, _e = ps(f"@((Get-Item 'HKCU:\\{TEST}\\Store').GetValueNames()).Count")
        check(st == "0", "the kept values are forgotten after a revert")
        rc, _o, _e = ps(scratch(T._reg_saved_ps("revert", "TT", items), items))
        v = read_vals(items)
        check(rc == 0 and v == {"One": "<none>", "Two": "<none>", "Str": "5"},
              f"revert without kept values (an older apply): the fallback — delete, or the given value ({v})")
        sub = T._reg_saved_ps("verify", "TT", items, ["Two"])
        check("'One'" not in sub and "'Two'" in sub, "verify can check a subset (values Windows manages itself)")
        bad_items = [("HKLM", "SYSTEM\\GameOptimizerPro-NoAccess", "V", "DWord", 1, None)]
        if not IS_ADMIN:
            rc, out, _e = ps(T._reg_saved_ps("apply", "TT", bad_items).replace(STORE_REAL, f"'{TEST}\\Store'"))
            check(rc == 1 and "V" in out, f"a value that can't be written is reported and the tweak fails ({out[:80]})")
    finally:
        ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")

# ── 3. Each kept-value tweak, for real, against scratch copies of its keys ──────────────────
print("each tweak with kept values, run against scratch keys")
SAVED = {"disable_tips_suggestions": T.TIPS_ITEMS, "disable_input_speech_data": T.INPUT_ITEMS,
         "disable_remote_assistance": T.REMOTE_ASSIST_ITEMS, "disable_dynamic_lighting": T.LIGHTING_ITEMS,
         "alt_tab_windows_only": T.ALTTAB_ITEMS, "controller_no_game_bar": T.NEXUS_ITEMS,
         "explorer_open_this_pc": T.LAUNCHTO_ITEMS}
def tag_of(cmd):
    return re.search(r"\$id='(\w+)\|", cmd).group(1)


check(all(T.get_by_id(tid).ps_command == T._reg_saved_ps("apply", tag_of(T.get_by_id(tid).ps_command), its)
          and T.get_by_id(tid).revert_cmd == T._reg_saved_ps("revert", tag_of(T.get_by_id(tid).ps_command), its)
          for tid, its in SAVED.items()),
      "the tweaks ARE the helper's scripts (what is tested below is what runs)")
paths_ok = all(i[1].startswith(("Software\\Microsoft\\", "Control Panel\\", "SYSTEM\\CurrentControlSet\\Control\\"))
               for its in SAVED.values() for i in its)
check(paths_ok, "they write Windows' own settings keys")
for tid, its in SAVED.items():
    if not VERIFY_MAP[tid].startswith("$ok=$true; foreach"):
        spec = reg_spec(tid)          # a plain check: it must read exactly the tweak's (first) value
        check(spec is not None and spec[0] == "one" and spec[1:4] == (its[0][0], its[0][1], its[0][2])
              and spec[4] == "eq" and spec[5] == its[0][4], f"{tid}: the status check reads the value the tweak sets")
if os.name == "nt":
    for tid, its in SAVED.items():
        t = T.get_by_id(tid)
        vcmd = (VERIFY_MAP[tid] if VERIFY_MAP[tid].startswith("$ok=$true; foreach")
                else T._reg_saved_ps("verify", tag_of(t.ps_command), its))
        orig = {i[2]: (1 if str(i[4]) == "0" else 0) for n, i in enumerate(its) if n % 2 == 0}
        try:
            seed(its, orig)
            rc1, _o, e1 = ps(scratch(t.ps_command, its))
            got = read_vals(its)
            set_ok = all(got[i[2]] == str(i[4]) for i in its)
            _rc, on, _e = ps(scratch(vcmd, its))
            rc2, _o, e2 = ps(scratch(t.revert_cmd, its))
            back = read_vals(its)
            want = {i[2]: (str(orig[i[2]]) if i[2] in orig else "<none>") for i in its}
            _rc, off, _e = ps(scratch(vcmd, its))
            check(rc1 == 0 and set_ok and on == "1" and rc2 == 0 and back == want and off == "0",
                  f"{tid}: apply sets {len(its)} value(s) -> active, revert restores the previous ones -> inactive "
                  f"{(e1 + e2)[:80]}")
        finally:
            ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")

print("the Windows settings the tips tweak leaves to Windows")
check("RotatingLockScreenOverlayEnabled" not in T.TIPS_CHECK and "SubscribedContent-338387Enabled" not in T.TIPS_CHECK
      and "ShowSyncProviderNotifications" in T.TIPS_CHECK and len(T.TIPS_CHECK) == len(T.TIPS_ITEMS) - 2,
      "lock-screen tips are applied but not checked (Windows Spotlight manages them)")
check("RotatingLockScreenEnabled" not in str(T.TIPS_ITEMS) and "ContentDeliveryAllowed" not in str(T.TIPS_ITEMS),
      "Spotlight itself and the whole Content Delivery Manager stay on")

# ── 4. Policies and scripts with their own logic ─────────────────────────────────────────────
print("OneDrive folder move, staying on the version, plain policies")
kfm = T.get_by_id("onedrive_block_kfm").ps_command
USF = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders"
ODK = "HKLM\\SOFTWARE\\Policies\\Microsoft\\OneDrive"
check(USF in kfm and ODK in kfm and "KFMBlockOptIn" in kfm, "KFM: checks the user's folders, then sets the policy")
if os.name == "nt":
    tk_ = f"HKCU:\\{TEST}\\usf"
    test_kfm = kfm.replace(USF, tk_).replace(ODK, f"HKCU\\{TEST}\\od")
    try:
        ps(f"New-Item '{tk_}' -Force | Out-Null; Set-ItemProperty '{tk_}' Desktop 'C:\\Users\\x\\OneDrive\\Desktop'; "
           f"Set-ItemProperty '{tk_}' Personal 'C:\\Users\\x\\Documents'")
        rc, out, _e = ps(test_kfm)
        _rc, setv, _e = ps(f"(Get-ItemProperty 'HKCU:\\{TEST}\\od' -EA SilentlyContinue).KFMBlockOptIn")
        check(rc == 1 and "Desktop" in out and "Sicherung verwalten" in out and setv == "",
              f"folders already in OneDrive: refuses, names them and the way back, sets nothing ({out[:70]})")
        ps(f"Set-ItemProperty '{tk_}' Desktop 'C:\\Users\\x\\Desktop'")
        rc, out, _e = ps(test_kfm)
        _rc, setv, _e = ps(f"(Get-ItemProperty 'HKCU:\\{TEST}\\od').KFMBlockOptIn")
        check(rc == 0 and setv == "1", f"local folders: the policy is set ({setv})")
    finally:
        ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")

pin = T.get_by_id("wu_pin_feature_version")
WUK = "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate"
check(all(v in pin.ps_command for v in ("TargetReleaseVersion", "TargetReleaseVersionInfo", "ProductVersion", "DisplayVersion"))
      and all(v in pin.revert_cmd for v in ("TargetReleaseVersion", "TargetReleaseVersionInfo", "ProductVersion")),
      "staying on the version: the documented trio, read from this PC's own version")
if os.name == "nt":
    tp = pin.ps_command.replace(WUK, f"HKCU\\{TEST}\\wu")
    tv = VERIFY_MAP["wu_pin_feature_version"].replace(WUK.replace("HKLM\\", "HKLM:\\"), f"HKCU:\\{TEST}\\wu")
    tr_ = pin.revert_cmd.replace(WUK, f"HKCU\\{TEST}\\wu")
    try:
        rc, out, _e = ps(tp)
        _rc, vals, _e = ps(f"$k=Get-ItemProperty 'HKCU:\\{TEST}\\wu'; \"$($k.ProductVersion)|$($k.TargetReleaseVersion)|$($k.TargetReleaseVersionInfo)\"")
        _rc, dv, _e = ps("(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').DisplayVersion")
        prod, trv, info = (vals.split("|") + ["", "", ""])[:3]
        check(rc == 0 and prod == "Windows 11" and trv == "1" and info == dv and re.fullmatch(r"\d\dH\d", info or ""),
              f"pins this PC's version: {prod} {info} ({out})")
        _rc, on, _e = ps(tv)
        ps(tr_)
        _rc, off, _e = ps(tv)
        check(on == "1" and off == "0", "status: active after apply, inactive after revert")
    finally:
        ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")

for tid, val in (("exclude_wu_drivers", "ExcludeWUDriversInQualityUpdate"), ("disable_background_apps", "LetAppsRunInBackground"),
                 ("startup_delay_off", "StartupDelayInMSec"), ("onedrive_block_kfm", "KFMBlockOptIn"),
                 ("disable_remote_assistance", "fAllowToGetHelp"), ("alt_tab_windows_only", "MultiTaskingAltTabFilter"),
                 ("disable_dynamic_lighting", "AmbientLightingEnabled"), ("controller_no_game_bar", "UseNexusForGameBarEnabled"),
                 ("explorer_open_this_pc", "LaunchTo")):
    spec = reg_spec(tid)
    check(spec is not None and spec[3] == val, f"{tid}: plain registry check ({val}) — read straight from the registry")
if os.name == "nt":
    for tid in NEW:
        rc, out, err = ps(VERIFY_MAP[tid])
        rg = reg_check(tid)
        check(rc == 0 and out in ("0", "1") and (rg is None or rg == (out == "1")),
              f"{tid}: the real check answers ({out}{'' if rg is None else ', winreg agrees'}) {err[:60]}")

# ── 5. Power settings ──────────────────────────────────────────────────────────────────────────
print("power settings: every plan, mains power only, the plans' own values kept")
for tid, sub_, set_ in (("usb3_link_power_off", T._USB_SUB, T._USB3_LPM), ("disable_wake_timers", T._SLEEP_SUB, T._RTC_WAKE)):
    t = T.get_by_id(tid)
    a, r = t.ps_command, t.revert_cmd
    check(f"/SETACVALUEINDEX $s {sub_} {set_} 0" in a and "SETDCVALUEINDEX" not in a + r
          and "/qh" in a and "PowerOrig" in a and "PowerOrig" in r and "DefaultPowerSchemeValues" in r,
          f"{tid}: AC only, hidden settings read (/qh), old value kept, revert: kept value or the plan's default")
    check("/qh SCHEME_CURRENT" in VERIFY_MAP[tid], f"{tid}: the check reads the active plan with /qh")
check(T._USB3_LPM == "d4e98f31-5ffe-4ce1-be31-1b38b384c009" and T._RTC_WAKE == "bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d",
      "the documented setting GUIDs")
if os.name == "nt" and not IS_ADMIN:
    q = ("$o=(powercfg /qh SCHEME_CURRENT %s %s 2>$null | Out-String); $m=[regex]::Matches($o,'0x[0-9a-fA-F]{8}'); "
         "if($m.Count -ge 2){ $m[$m.Count-2].Value }" % (T._USB_SUB, T._USB3_LPM))
    _rc, before, _e = ps(q)
    rc, out, _e = ps(T.get_by_id("usb3_link_power_off").ps_command)
    _rc, after, _e = ps(q)
    check(rc == 1 and ("Administrator" in out or "administrator" in out) and before == after and before,
          f"without admin rights: refused before anything changes ({before} -> {after})")

# ── 6. Extended tweaks ─────────────────────────────────────────────────────────────────────────
print("extended tweaks")
tasks = T._TELEMETRY_TASKS_PS
check(all(x in tasks for x in ("Feedback\\Siuf\\DmClient", "DmClientOnScenarioDownload",
                               "Windows Error Reporting\\QueueReporting", "PI\\Sqm-Tasks",
                               "Power Efficiency Diagnostics\\AnalyzeSystem"))
      and tasks.count("\\Microsoft\\Windows\\") == 12, "telemetry tasks: 12 (the five new ones in)")
check("MareBackup" not in tasks and "StartupAppTask" not in tasks,
      "not in: the app-backup task and the startup-app check (functions, not telemetry)")
if os.name == "nt":
    rc, out, _e = ps(tasks + "Write-Output $found.Count")
    check(rc == 0 and out.isdigit() and 1 <= int(out) <= 12, f"task lookup on this Windows: {out} of 12 exist")
bing = T.get_by_id("disable_bing_search")
check(T._reg_saved_ps("apply", "SEARCH", T.SEARCH_ITEMS) in bing.ps_command
      and T._reg_saved_ps("revert", "SEARCH", T.SEARCH_ITEMS) in bing.revert_cmd
      and {i[2] for i in T.SEARCH_ITEMS} == {"IsDynamicSearchBoxEnabled", "IsMSACloudSearchEnabled", "IsAADCloudSearchEnabled"},
      "Bing tweak: + search highlights and cloud search (kept values)")
check(reg_spec("disable_bing_search") is not None and "BingSearchEnabled" in VERIFY_MAP["disable_bing_search"],
      "... its check is unchanged: an earlier apply is not reported as 'no longer active'")
reco = T.get_by_id("w11_hide_recommended")
check("HideRecommendedSection" in reco.ps_command and T._reg_saved_ps("apply", "RECO", T.RECO_ITEMS) in reco.ps_command
      and "Education" in reco.desc and "HideRecommendedSection" in VERIFY_MAP["w11_hide_recommended"],
      "'Recommended': the policy (Education/SE per Microsoft) + recent files / tips off on every edition; check unchanged")
vfx = T.get_by_id("visual_effects_perf")
check("SystemParametersInfo" in vfx.ps_command and "0x25,1" in vfx.ps_command and "0x4B,1" in vfx.ps_command
      and "VisualFXSetting /t REG_DWORD /d 3" in vfx.ps_command and "ListviewAlphaSelect" in vfx.ps_command,
      "visual effects: animations off through the API, fonts / window contents / thumbnails / shadows kept")
check(all(c in T._VFX_ANIMS for c in ("0x1003", "0x1043", "0x1015", "0x101B")) and "0x1025" not in T._VFX_ANIMS
      and "0x4B" not in T._VFX_ANIMS, "the animation switches only (no drop shadow, no font smoothing among them)")
check("[IntPtr]1" in vfx.revert_cmd and "Set-MinAnimate 1" in vfx.revert_cmd and "/d 0 /f" in vfx.revert_cmd,
      "revert switches the animations back on ('let Windows decide')")
if os.name == "nt":
    rc, out, err = ps(T._VFX_HEAD + "$p=[Runtime.InteropServices.Marshal]::AllocHGlobal(4); "
                      "$ok=[GOPVfx.Spi]::SystemParametersInfo(0x1042,0,$p,0); $v=[Runtime.InteropServices.Marshal]::ReadInt32($p); "
                      "[Runtime.InteropServices.Marshal]::FreeHGlobal($p); \"$ok|$v\"")
    check(rc == 0 and out.startswith("True|"), f"the API binding works (read-only SPI_GETCLIENTAREAANIMATION: {out}) {err[:60]}")
    VFXK = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects"
    WMK = "HKCU:\\Control Panel\\Desktop\\WindowMetrics"
    ADK = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced"
    vv = VERIFY_MAP["visual_effects_perf"].replace(VFXK, f"HKCU:\\{TEST}\\v").replace(WMK, f"HKCU:\\{TEST}\\w").replace(ADK, f"HKCU:\\{TEST}\\a")
    res = []
    try:
        for fx, mn, tb in ((2, "0", 0), (3, "0", 0), (0, "0", 0), (3, "1", 0), (3, "0", 1)):
            ps(f"New-Item 'HKCU:\\{TEST}\\v' -Force | Out-Null; New-Item 'HKCU:\\{TEST}\\w' -Force | Out-Null; "
               f"New-Item 'HKCU:\\{TEST}\\a' -Force | Out-Null; Set-ItemProperty 'HKCU:\\{TEST}\\v' VisualFXSetting {fx} -Type DWord; "
               f"Set-ItemProperty 'HKCU:\\{TEST}\\w' MinAnimate '{mn}'; Set-ItemProperty 'HKCU:\\{TEST}\\a' TaskbarAnimations {tb} -Type DWord")
            res.append(ps(vv)[1])
    finally:
        ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")
    check(res == ["1", "1", "0", "0", "0"],
          f"status: the old apply (2) and the new one (3) count, animations back on does not ({res})")

# ── 7. BitLocker ───────────────────────────────────────────────────────────────────────────────
print("BitLocker in the health report and the BIOS guide")
on = HR._bitlocker_line({"bitlocker": {"known": True, "protection": 1, "conversion": 1}})
paused = HR._bitlocker_line({"bitlocker": {"known": True, "protection": 0, "conversion": 1}})
dec = HR._bitlocker_line({"bitlocker": {"known": True, "protection": 0, "conversion": 3}})
off = HR._bitlocker_line({"bitlocker": {"known": True, "protection": 0, "conversion": 0}})
check(on and on.value == "an" and on.severity == HR.WARN and HR.RECOVERY_KEY_URL in on.note and "BIOS" in on.note,
      "on: a warning with the recovery key link before BIOS changes")
check(paused and "noch nicht aktiv" in paused.value and paused.severity == HR.OK, "encrypted, protection not yet on (waiting for activation)")
check(dec and dec.value == "wird entschlüsselt" and off and off.value == "aus" and "24H2" in off.note, "decrypting / off")
check(HR._bitlocker_line({}) is None and HR._bitlocker_line({"bitlocker": {"known": False}}) is None
      and HR._bitlocker_line({"bitlocker": {"known": True, "protection": 2, "conversion": 1}}) is None,
      "unknown or locked: no line (nothing guessed)")
check("Win32_EncryptableVolume" in HR._BUNDLE_PS and "$d.bitlocker=$bl" in HR._BUNDLE_PS
      and HR._BUNDLE_PS.rstrip().endswith("ConvertTo-Json -Compress"), "read in the same read-only report call")
check("$p -eq 1" in HR._BITLOCKER_PS and "$p -eq 2" in HR._BITLOCKER_PS,
      "without admin only the shell's documented-by-use values 1 (on) / 2 (off) are taken")
check(HR.bitlocker_protected({"known": True, "protection": 1}) and not HR.bitlocker_protected({"known": True, "protection": 0})
      and not HR.bitlocker_protected(None), "BIOS guide warns only when BitLocker really protects C:")
if os.name == "nt":
    st = HR.bitlocker_state()
    check(st is not None and st.get("known") and st.get("protection") in (0, 1, 2), f"this PC: {st}")
    rep = HR.generate()
    check(rep.ok and any(s.key == "bitlocker" for s in (rep.status or [])) and any(s.key == "hvci" for s in rep.status),
          "the real report has the BitLocker and memory-integrity lines")

# ── 8. Store apps ──────────────────────────────────────────────────────────────────────────────
print("Store apps: rating, protected ones")
fake = json.dumps([
    {"name": "Microsoft.BingWeather", "display": "", "publisher": "CN=Microsoft Corporation, O=x"},
    {"name": "Microsoft.Windows.Photos", "display": "Fotos"},
    {"name": "Microsoft.WindowsStore", "display": "Microsoft Store"},
    {"name": "Microsoft.DesktopAppInstaller", "display": "App Installer"},
    {"name": "Microsoft.HEVCVideoExtension", "display": ""},
    {"name": "Microsoft.LanguageExperiencePackde-DE", "display": ""},
    {"name": "NVIDIACorp.NVIDIAControlPanel", "display": "NVIDIA Control Panel"},
    {"name": "RealtekSemiconductorCorp.RealtekAudioControl", "display": "Realtek Audio Console"},
    {"name": "Microsoft.WindowsTerminal", "display": "Terminal"},
    {"name": "Some.Helper.Part", "display": ""},
    {"name": "Contoso.MyApp", "display": "My App"},
    {"name": "king.com.SomeNewSaga", "display": ""},
    {"name": "bad name; Remove-Item", "display": "x"},
    {"name": "Clipchamp.Clipchamp", "display": "Clipchamp", "provisioned": True},
])
apps = AR.parse_list(fake)
names = [a.name for a in apps]
check(names == ["Clipchamp.Clipchamp", "king.com.SomeNewSaga", "Microsoft.BingWeather", "Microsoft.Windows.Photos",
                "Contoso.MyApp"], f"bloat first, then optional, then the rest; protected / hidden ones left out ({names})")
by = {a.name: a for a in apps}
check(by["Microsoft.BingWeather"].display == "Wetter" and by["Microsoft.BingWeather"].publisher == "Microsoft Corporation"
      and by["Clipchamp.Clipchamp"].provisioned, "known names for apps without a Start entry, publisher, provisioned")
check(by["Microsoft.Windows.Photos"].category == AR.OPTIONAL and "Bild" in by["Microsoft.Windows.Photos"].note
      and by["Contoso.MyApp"].category == AR.OTHER, "optional apps say what goes missing; unknown = your call")
check(all(AR.is_protected(n) for n in ("Microsoft.WindowsStore", "Microsoft.DesktopAppInstaller", "Microsoft.SecHealthUI",
                                       "Microsoft.AV1VideoExtension", "Microsoft.WebpImageExtension", "Microsoft.MicrosoftEdge.Stable",
                                       "Microsoft.GamingServices", "AdvancedMicroDevicesInc-2.AMDRadeonSoftware",
                                       "AppUp.IntelGraphicsExperience", "Microsoft.VCLibs.140.00", "Microsoft.UI.Xaml.2.8"))
      and not AR.is_protected("Microsoft.BingNews") and not AR.is_protected("Microsoft.ZuneMusic"),
      "protected: Store, App Installer, Security, codecs, Edge, Gaming Services, driver apps, frameworks")
check(AR.parse_list("not json") == [] and AR.parse_list("") == [] and AR.parse_list('{"name": "Clipchamp.Clipchamp", "display": "C"}')[0].name == "Clipchamp.Clipchamp",
      "broken output: empty list; a single app (PowerShell gives an object, not a list) works")
calls = []
real_run = AR._run_ps
AR._run_ps = lambda script, timeout=120: (calls.append(script), (0, "GOP-OK"))[1]
try:
    ok1 = AR.remove("Microsoft.WindowsStore")
    ok2 = AR.remove("x'; Remove-Item C:\\ -Recurse; '")
    check(ok1[0] is False and ok2[0] is False and not calls, "protected / invalid names: refused before PowerShell runs")
    ok3 = AR.remove("Microsoft.BingWeather")
    check(ok3 == (True, "") and len(calls) == 1 and "-AllUsers" in calls[0] and "Remove-AppxProvisionedPackage" in calls[0]
          and "$n='Microsoft.BingWeather'" in calls[0], "removal: every user + the provisioned copy, checked afterwards")
    AR._run_ps = lambda script, timeout=120: (0, "GOP-LEFT Zugriff verweigert\n")
    check(AR.remove("Microsoft.BingWeather") == (False, "Zugriff verweigert"), "still installed: the reason is passed on")
finally:
    AR._run_ps = real_run
if os.name == "nt":
    t0 = time.time()
    real = AR.list_apps()
    check(all(not AR.is_protected(a.name) for a in real) and all(a.category in AR.CATEGORY_ORDER for a in real),
          f"this PC: {len(real)} app(s) listed in {time.time() - t0:.1f} s, none of them protected (read only)")

print("program installer")
cat_ids = [p.id for p in WI.CATALOG]
check(len(cat_ids) == len(set(cat_ids)) >= 25 and all(WI._ID.match(i) for i in cat_ids)
      and {p.group for p in WI.CATALOG} <= {g for g, _d, _e in WI.GROUPS}, f"{len(cat_ids)} programs, ids unique, groups known")
check({"Guru3D.Afterburner", "Guru3D.RTSS", "Geeks3D.FurMark.2", "Valve.Steam", "Microsoft.VCRedist.2015+.x64",
       "Microsoft.DirectX"} <= set(cat_ids), "the tools the app works with and the runtimes games need are in")
check("Spotify.Spotify" not in cat_ids and not any("Nvidia" in i or "NVIDIA" in i for i in cat_ids),
      "not in: an installer that refuses elevated installs; NVIDIA (not in winget's source)")
fm = next(p for p in WI.CATALOG if p.id == "Geeks3D.FurMark.2")
src_fm = open(os.path.join(ROOT, "core", "furmark.py"), encoding="utf-8").read()
check(any(x.endswith("FurMark2_x64\\furmark.exe") for x in fm.paths) and "FurMark2_x64\\furmark.exe" in src_fm,
      "FurMark 2 lands where the stress test looks for it")
seen = []
real_wrun = WI._run


def fake_run(args, timeout=900, on_line=None):
    seen.append(args)
    if args[0] == "export":
        with open(args[2], "w", encoding="utf-8") as f:
            json.dump({"Sources": [{"Packages": [{"PackageIdentifier": "valve.steam"}, {"PackageIdentifier": "Other.Thing"}]}]}, f)
        return 0, ""
    if on_line:
        on_line("Successfully installed")
    return codes.pop(0), "Line one\nInstaller failed with exit code: 1603"


try:
    WI._run = fake_run
    marker = Path(TMP) / "ddu.exe"
    marker.write_text("x")
    progs = [WI.Program("Valve.Steam", "Steam", "launcher"), WI.Program("Wagnardsoft.DisplayDriverUninstaller", "DDU", "tuning",
                                                                       paths=(str(marker),)),
             WI.Program("7zip.7zip", "7-Zip", "tools")]
    have = WI.installed_ids(progs)
    check(have == {"Valve.Steam", "Wagnardsoft.DisplayDriverUninstaller"},
          f"installed = winget's own list (any case) OR the program's file exists ({sorted(have)})")
    codes = [0, 0x8A15002B, 0x8A150109, 0x8A150061, 1603]
    lines = []
    r = [WI.install("Valve.Steam", on_line=lines.append) for _ in range(5)]
    check(r[0] == (True, "") and r[1][0] and "schon installiert" in r[1][1] and r[2][0] and "Neustart" in r[2][1]
          and r[3][0] and r[4] == (False, "Line one · Installer failed with exit code: 1603") and lines,
          "results: done / already up to date / restart finishes it / already installed / failed with winget's reason")
    inst = [a for a in seen if a[0] == "install"][0]
    check(inst[:4] == ["install", "--id", "Valve.Steam", "-e"] and "--silent" in inst and "--source" in inst
          and "--accept-package-agreements" in inst and "--disable-interactivity" in inst,
          "exact id, winget's own source, silent, no questions")
    n_before = len(seen)
    check(WI.install("Evil.Package") == (False, "Nicht in der Liste") and len(seen) == n_before,
          "only programs of the list can be installed")
finally:
    WI._run = real_wrun
if os.name == "nt" and WI.winget_exe():
    t0 = time.time()
    have = WI.installed_ids()
    check(isinstance(have, set) and have <= set(cat_ids), f"this PC: {len(have)} of the programs found in {time.time() - t0:.1f} s (read only)")

# ── 8b. Existing tweaks: values Windows does not read (found by tools/windows_watch.py) ─────────
print("existing tweaks without effect: retired or corrected")
from core.tweak_presets import BUILTIN_PRESETS  # noqa: E402
for gone in ("nvidia_low_latency", "set_mmcss_audio"):
    check(gone not in ids and gone not in VERIFY_MAP and gone not in TWEAK_DESC_EN and gone in T.RETIRED_TWEAKS
          and not any(gone in p.tweak_ids for p in BUILTIN_PRESETS),
          f"{gone}: retired (no tweak, check, text or preset; 'Revert all' cleans up after it)")
nvc = T.RETIRED_TWEAKS["nvidia_low_latency"][2]
mmc = T.RETIRED_TWEAKS["set_mmcss_audio"][2]
NVK = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak"
PAK = "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Pro Audio"
check(NVK in nvc and "-eq 1" in nvc and PAK in mmc and "-eq 6" in mmc and "-eq 'High'" in mmc,
      "the cleanups touch only the values the old tweaks set")
if os.name == "nt":
    try:
        ps(f"New-Item 'HKCU:\\{TEST}\\nv' -Force | Out-Null; Set-ItemProperty 'HKCU:\\{TEST}\\nv' NVLatency 1 -Type DWord; "
           f"Set-ItemProperty 'HKCU:\\{TEST}\\nv' Other 7 -Type DWord; New-Item 'HKCU:\\{TEST}\\pa' -Force | Out-Null; "
           f"Set-ItemProperty 'HKCU:\\{TEST}\\pa' Priority 6 -Type DWord; Set-ItemProperty 'HKCU:\\{TEST}\\pa' 'SFIO Priority' High; "
           f"Set-ItemProperty 'HKCU:\\{TEST}\\pa' 'Scheduling Category' High")
        r1 = ps(nvc.replace(NVK, f"HKCU:\\{TEST}\\nv"))[0]
        r2 = ps(mmc.replace(PAK, f"HKCU:\\{TEST}\\pa"))[0]
        _rc, st, _e = ps(f"$a=Get-ItemProperty 'HKCU:\\{TEST}\\nv'; $b=Get-ItemProperty 'HKCU:\\{TEST}\\pa'; "
                         "\"[$($a.NVLatency)][$($a.Other)][$($b.Priority)][$($b.'SFIO Priority')][$($b.'Scheduling Category')]\"")
        check(r1 == 0 and r2 == 0 and st == "[][7][1][Normal][High]",
              f"cleanups on scratch keys: NVLatency gone, other values stay; Pro Audio back to its defaults ({st})")
    finally:
        ps(f"Remove-Item 'HKCU:\\{TEST}' -Recurse -Force -EA SilentlyContinue")
mg = T.get_by_id("mmcss_gaming")
check("Scheduling Category" in mg.ps_command and "GPU Priority" not in mg.ps_command and "Priority\" /t" not in mg.ps_command
      and "/d Medium" in mg.revert_cmd and "Scheduling Category" in VERIFY_MAP["mmcss_gaming"]
      and "GPU Priority" not in VERIFY_MAP["mmcss_gaming"],
      "MMCSS Games: sets the category (what MMCSS reads); the check no longer reads the default GPU Priority; revert -> Medium")
check("SFIO" not in T.get_by_id("mmcss_audio_profile").ps_command and "SFIO" in T.get_by_id("mmcss_audio_profile").revert_cmd,
      "MMCSS Audio: 'SFIO Priority' (not used per Microsoft) no longer set, revert still normalizes it")
for tid in ("audio_service_priority", "disable_network_throttle"):
    cmd = T.get_by_id(tid).ps_command
    check("SystemResponsiveness /t REG_DWORD /d 10" in cmd and "/d 0 /f" not in cmd.split("SystemResponsiveness")[1][:40],
          f"{tid}: SystemResponsiveness 10 (below 10 Windows uses 20, the default)")
check("$r -eq 10" in VERIFY_MAP["audio_service_priority"], "... and the check wants 10 (an old 0 shows as not active: it did nothing)")
# round 47: 'Optimize TCP' and 'NVMe queue depth' are retired (no documented effect) — their clean-ups
# still remove what this round's versions had left
tcp = T.RETIRED_TWEAKS["tcp_optimize"][2]
check(T.get_by_id("tcp_optimize") is None and "SackOpts" in tcp and "ecncapability=default" in tcp,
      "TCP: retired since round 47; 'Revert all' puts ECN / timestamps to Windows' default and removes the XP-era values")
nvme = T.RETIRED_TWEAKS["nvme_queue_depth"][2]
check(T.get_by_id("nvme_queue_depth") is None and "IdlePowerEnabled" in nvme and "-eq 32" in nvme,
      "NVMe: retired since round 47; its clean-up removes only the queue depth it set (32) and the idle-power value")
bl = T.get_by_id("remove_bloatware").ps_command
check("ZuneMusic" not in bl and "GetHelp" not in bl and "ZuneVideo" in bl,
      "Remove Bloatware keeps Media Player (Windows 11's default player) and Get Help (the troubleshooters)")
check(AR.classify("Microsoft.GetHelp")[0] == AR.OPTIONAL and AR.classify("Microsoft.ZuneMusic")[0] == AR.OPTIONAL,
      "... both offered on the Apps page as 'may be in use'")
if os.name == "nt":
    for tid in ("mmcss_gaming", "audio_service_priority"):
        rc, out, err = ps(VERIFY_MAP[tid])
        check(rc == 0 and out in ("0", "1"), f"{tid}: the corrected check answers on this PC ({out}) {err[:60]}")

print("the Windows update check (tools/windows_watch.py)")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import windows_watch as WW  # noqa: E402
tg = WW.targets(T.get_by_id("disable_telemetry_tasks"))
check(len(tg["tasks"]) == 12 and not tg["services"], "targets: the 12 telemetry tasks")
tg = WW.targets(T.get_by_id("disable_telemetry"))
check({"DiagTrack", "dmwappushservice"} <= set(tg["services"]) and "AllowTelemetry" in tg["values"], "targets: services + values")
tg = WW.targets(T.get_by_id("usb3_link_power_off"))
check(tg["power"] == [(T._USB_SUB, T._USB3_LPM)], "targets: the power setting")
tg = WW.targets(T.get_by_id("disable_tips_suggestions"))
check("ScoobeSystemSettingEnabled" in tg["values"] and len(tg["values"]) == len(T.TIPS_ITEMS), "targets: the kept-value rows")
tg = WW.targets(T.get_by_id("remove_xbox"))
check("*Microsoft.XboxGamingOverlay*" in tg["appx"] and "*Microsoft.Xbox.TCUI*" in tg["appx"], "targets: Store app patterns")
check(any(rx.match("SubscribedContent-338389Enabled") for rx, _f in WW._SCAN_AS) and "KFMBlockOptIn" in WW.EXTERNAL,
      "names Windows builds at run time are searched by their fixed part; values other programs read are named")
if os.name == "nt":
    out_dir = Path(TMP) / "watch"
    t0 = time.time()
    report, summ = WW.run(out_dir)
    check(report.exists() and (out_dir / "windows_watch.json").exists() and len(summ["states"]) == len(VERIFY_MAP)
          and all(v in ("active", "inactive", "error") for v in summ["states"].values()),
          f"a run (read only): report + state of every tweak with a check ({len(summ['states'])}, {time.time() - t0:.0f} s)")
    txt = report.read_text(encoding="utf-8")
    check("erster Lauf" in txt and "Ziele, die es auf diesem Windows nicht gibt" in txt, "first run: nothing to compare yet")
    st = json.loads((out_dir / "windows_watch.json").read_text(encoding="utf-8"))
    st["states"] = {k: ("active" if v == "inactive" else v) for k, v in st["states"].items()}
    st["build"] = "1.0"
    (out_dir / "windows_watch.json").write_text(json.dumps(st), encoding="utf-8")
    report2, summ2 = WW.run(out_dir)
    txt2 = report2.read_text(encoding="utf-8")
    check("Windows wurde aktualisiert" in txt2 and summ2["changed"] and "→ inactive" in txt2,
          "second run: names the Windows update and every status change since the last run")

# ── 9. UI: Apps page, BIOS guide warning, main window ───────────────────────────────────────────
print("the Apps page")
import tkinter as tk  # noqa: E402
import customtkinter as ctk  # noqa: E402
import ui.main_window as MW  # noqa: E402
check(any(k == "apps" for k, *_x in MW.TAB_DEFS) and MW.TAB_COLORS.get("apps")
      and '"apps": self._make_apps' in open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8").read(),
      "sidebar entry, colour and page factory")
from ui import theme  # noqa: E402
check("apps" in theme.ICONS, "sidebar icon")
from core import restore_point, services  # noqa: E402
from ui import apps_page as AP  # noqa: E402
root = ctk.CTk()
root.withdraw()
real = {"admin": services.is_admin, "list": AR.list_apps, "remove": AR.remove, "have": WI.installed_ids,
        "install": WI.install, "exe": WI.winget_exe, "ask": AP.messagebox.askyesno, "rp": restore_point.create_ex}
asked = []
try:
    AP.services.is_admin = lambda: True
    AP.app_removal.list_apps = lambda: AR.parse_list(fake)
    removed = []
    AP.app_removal.remove = lambda name: (removed.append(name), (name != "Contoso.MyApp", "Zugriff verweigert"))[1]
    AP.winget_installer.installed_ids = lambda programs=None: {"Valve.Steam"}
    AP.winget_installer.winget_exe = lambda: "winget.exe"
    installed = []
    AP.winget_installer.install = lambda pid, on_line=None: (installed.append(pid), on_line and on_line("Downloading"), (True, ""))[2]
    AP.messagebox.askyesno = lambda *a, **k: (asked.append(a), True)[1]
    restore_point.create_ex = lambda d="": (True, "Wiederherstellungspunkt erstellt.", "ok")
    page = AP.AppsPage(root)
    page.pack(fill="both", expand=True)
    root.update()

    def wait(cond, s=10):
        end = time.time() + s
        while not cond() and time.time() < end:
            root.update()
            time.sleep(0.03)
        return cond()

    check(not page._loaded["apps"], "nothing is read before the page is shown")
    page.on_show()
    check(wait(lambda: page._loaded["apps"]), "shown: the app list is read")
    rows = page.tree_apps.get_children()
    check(list(rows) == names and page.tree_apps.item("Clipchamp.Clipchamp", "tags")[0] == AR.BLOAT
          and "kann weg" in page.tree_apps.item("Clipchamp.Clipchamp", "values")[1], "table: rated, coloured")
    page._select_bloat()
    check(set(page.tree_apps.selection()) == {"Clipchamp.Clipchamp", "king.com.SomeNewSaga", "Microsoft.BingWeather"},
          "'select all green' picks the preinstalled extras only")
    page.tree_apps.selection_set(["Microsoft.BingWeather", "Microsoft.Windows.Photos", "Contoso.MyApp"])
    page._remove()
    check(wait(lambda: not page._busy and removed), "remove: runs in the background")
    wait(lambda: "Entfernt" in page.lbl_apps.cget("text"))
    check(asked and "evtl. genutzt" in asked[-1][1] and "Wiederherstellungspunkt" in asked[-1][1],
          "asks first, says which may be in use and that a restore point comes first")
    check(removed == ["Microsoft.BingWeather", "Microsoft.Windows.Photos", "Contoso.MyApp"]
          and "2 von 3" in page.lbl_apps.cget("text"), f"each one removed, the failure counted ({page.lbl_apps.cget('text')})")
    root.update()
    time.sleep(0.3)
    root.update()
    log = page.log_apps.txt.get("1.0", "end")
    check("Wiederherstellungspunkt" in log and "Zugriff verweigert" in log, "log: restore point, per-app result with the reason")

    page._show_view("install")
    check(wait(lambda: page._loaded["install"]), "install view: the installed programs are read when shown")
    check(page.tree_inst.item("Valve.Steam", "tags")[0] == "installed"
          and len(page.tree_inst.get_children()) == len(WI.CATALOG), "every program listed, installed ones marked")
    page.tree_inst.selection_set(["Valve.Steam", "7zip.7zip", "Discord.Discord"])
    page._install()
    check(wait(lambda: not page._busy and installed), "install: runs in the background")
    wait(lambda: "Installiert" in page.lbl_install.cget("text"))
    check(installed == ["Discord.Discord", "7zip.7zip"] and "übersprungen" in asked[-1][1] and "Steam" in asked[-1][1],
          f"already installed ones are skipped (and named), the others installed one after the other ({installed})")
    page.destroy()

    AP.services.is_admin = lambda: False
    page2 = AP.AppsPage(root)
    check(str(page2.btn_remove.cget("state")) == "disabled" and str(page2.btn_install.cget("state")) == "disabled",
          "without admin rights: view only")
    page2.destroy()
finally:
    AP.services.is_admin = real["admin"]
    AP.app_removal.list_apps, AP.app_removal.remove = real["list"], real["remove"]
    AP.winget_installer.installed_ids, AP.winget_installer.install = real["have"], real["install"]
    AP.winget_installer.winget_exe = real["exe"]
    AP.messagebox.askyesno = real["ask"]
    restore_point.create_ex = real["rp"]

print("BIOS guide: BitLocker warning")
from ui import tab_bios as TB  # noqa: E402
real_bl = TB.health_report.bitlocker_state


def labels(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, tk.Label):
            out.append(str(c.cget("text")))
        out += labels(c)
    return out


try:
    hw = HardwareInfo(cpu_name="AMD Ryzen 7 7800X3D 8-Core Processor", mb_manufacturer="Micro-Star International Co., Ltd.",
                      gpu_name="NVIDIA GeForce RTX 4070", os_build=26300, is_win11=True)
    for prot, want in ((1, True), (0, False)):
        TB.health_report.bitlocker_state = lambda p=prot: {"known": True, "protection": p, "conversion": 1}
        tab = TB.BiosGuideTab(root, hw)
        tab.pack(fill="both", expand=True)
        ok = True
        end = time.time() + 20
        while time.time() < end and (tab._detecting or tab._bitlocker is None):
            root.update()
            time.sleep(0.05)
        root.update()
        shown = any("BitLocker" in s and HR.RECOVERY_KEY_URL in s for s in labels(tab._inner))
        check(shown == want, f"BitLocker {'on' if prot else 'off'}: warning {'shown' if want else 'not shown'}")
        tab.destroy()
finally:
    TB.health_report.bitlocker_state = real_bl
root.destroy()

if os.name == "nt":
    _rc, left, _e = ps(f"Test-Path 'HKCU:\\{TEST}'")
    new_keys = set(ps(ROOT_KEYS)[1].split("|")) - HKCU_BEFORE
    check(left == "False" and not new_keys, f"nothing left behind: no scratch key, no new key under HKCU ({sorted(new_keys)})")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
