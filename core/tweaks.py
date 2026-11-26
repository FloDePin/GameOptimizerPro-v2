"""
GameOptimizerPro Tweaks Database
All tweaks as Python dataclasses with PowerShell commands.
Preserves all original GameOptimizerPro tweaks + new additions.
"""

from dataclasses import dataclass, field


@dataclass
class Tweak:
    id:          str
    name:        str
    desc:        str
    category:    str        # "Windows" | "Gaming" | "Network" | "GPU"
    group:       str        # Subgroup label
    ps_command:  str        # PowerShell command(s) to apply
    revert_cmd:  str = ""   # PowerShell to revert (optional)
    requires_nvidia: bool = False
    requires_amd:    bool = False
    requires_nvme:   bool = False
    requires_win11:  bool = False      # set from WIN11_ONLY below
    requires_pro:    bool = False      # set from PRO_ONLY below (Home ignores the policy)
    requires_reboot: bool = False
    risk:        str = "safe"   # "safe" | "moderate" | "advanced"
    tags:        list = field(default_factory=list)
    timeout_s:   int = 60       # long one-time actions (Disk Cleanup/DISM) need more


from core import audio_policy   # noqa: E402 — audio tweaks use the API
from core.i18n import tr as _tr  # noqa: E402


def _power_all(sub: str, setting: str, ac: int, dc: int) -> str:
    """Baut ein PowerShell-Kommando, das eine powercfg-Einstellung in JEDES
    Energieschema schreibt (portiert aus v1: Set-PowerAllSchemes).

    Windows aktiviert nach einem Neustart auf vielen Systemen ein anderes
    Schema — ein Wert, der nur ins aktive Schema geschrieben wurde, wirkt danach
    "zurückgesetzt". Die GUIDs werden aus `powercfg /L` gelesen, nie der
    lokalisierte Planname (dadurch sprachunabhängig)."""
    return (
        "$g=@(); foreach($l in (powercfg /L 2>$null)){ "
        "if($l -match '([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})')"
        "{$g+=$matches[1]} }; "
        "if($g.Count -eq 0){$g=@('SCHEME_CURRENT')}; "
        "foreach($s in $g){ "
        f"powercfg /SETACVALUEINDEX $s {sub} {setting} {ac} 2>$null | Out-Null; "
        f"powercfg /SETDCVALUEINDEX $s {sub} {setting} {dc} 2>$null | Out-Null"
        " }; powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null"
    )


# ── Vendor guards for GPU-specific tweaks ───────────────────────────────────
# The display-adapter class {4d36e968-…} exists on EVERY system — NVIDIA and
# Intel adapters live there too. An AMD tweak that loops over all its subkeys
# (as the first port from v1 did, minus v1's `if ($IsAMD)`) would write AMD
# driver values into an NVIDIA/Intel adapter key. So each AMD tweak only touches
# subkeys whose ProviderName is AMD — on hybrid systems just the AMD adapter —
# and REFUSES (exit 1 → not recorded as applied) when there is no AMD adapter.
_AMD_KEYS_PS = (
    "$c='HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'; "
    "$amd=@(Get-ChildItem $c -EA SilentlyContinue | Where-Object { "
    "(Get-ItemProperty $_.PSPath -Name ProviderName -EA SilentlyContinue).ProviderName "
    "-match 'Advanced Micro Devices|ATI Technologies|^AMD' }); "
)
_AMD_REQUIRED_PS = ("if($amd.Count -eq 0){ Write-Output '"
                    + _tr("Kein AMD-Grafikadapter gefunden", "No AMD graphics adapter found") + "'; exit 1 }; ")

_AMD_ULPS_APPLY = _AMD_KEYS_PS + _AMD_REQUIRED_PS + (
    "foreach($k in $amd){ "
    "Set-ItemProperty -Path $k.PSPath -Name EnableULPS -Value 0 -Type DWord -EA SilentlyContinue; "
    "Set-ItemProperty -Path $k.PSPath -Name EnableULPS_NA -Value 0 -Type DWord -EA SilentlyContinue }"
)
_AMD_ULPS_REVERT = _AMD_KEYS_PS + (
    "foreach($k in $amd){ "
    "Set-ItemProperty -Path $k.PSPath -Name EnableULPS -Value 1 -Type DWord -EA SilentlyContinue; "
    "Set-ItemProperty -Path $k.PSPath -Name EnableULPS_NA -Value 1 -Type DWord -EA SilentlyContinue }"
)
# (The "NVIDIA Low Latency Mode" tweak that wrote NVTweak\NVLatency is retired since round 45: no file
# of the NVIDIA driver contains that value name — the low-latency mode lives in the driver profile.)



# ── Helpers for the v1-parity / 26H2 tweaks ──────────────────────────────────

# ── Advanced settings of the wired network adapters ─────────────────────────
# Only physical (NCF_PHYSICAL) Ethernet adapters (*IfType 6), and only keywords the
# driver itself declares in Ndi\params with "0" as a valid choice — vendors name the
# same setting differently. All registry access goes through the .NET API: the
# PowerShell cmdlets treat "*" in "*EEE" as a wildcard (Remove-ItemProperty would
# delete every value ending in EEE). The value found before the first apply is kept
# under HKLM\SOFTWARE\GameOptimizerPro\NicOrig and put back on revert. The driver
# reads the values when the adapter starts: no connection drop now, effective after a
# restart.
NIC_EEE_KEYWORDS = ("*EEE", "EEE", "EEELinkAdvertisement", "AdvancedEEE",
                    "EnableGreenEthernet", "GreenEthernet")
NIC_IM_KEYWORDS = ("*InterruptModeration",)

_NIC_LOOP_PS = (
    "$kws=@(__KWS__); $tag='__TAG__'; $n=0; "
    "$lm=[Microsoft.Win32.Registry]::LocalMachine; "
    "$cls='SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}'; "
    "$c=$lm.OpenSubKey($cls); $subs=@(); if($c){ $subs=@($c.GetSubKeyNames() | Where-Object { $_ -match '^\\d{4}$' }) }; "
    "foreach($s in $subs){ "
    "$k=$lm.OpenSubKey(\"$cls\\$s\", __WRITE__); if(-not $k){ continue }; "
    "if(-not $k.GetValue('NetCfgInstanceId') -or -not ([int64]$k.GetValue('Characteristics',0) -band 4) "
    "-or \"$($k.GetValue('*IfType'))\" -ne '6'){ continue }; "
    "foreach($kw in $kws){ "
    "$e=$lm.OpenSubKey(\"$cls\\$s\\Ndi\\params\\$kw\\enum\"); if(-not $e -or $null -eq $e.GetValue('0')){ continue }; "
    "$def=$lm.OpenSubKey(\"$cls\\$s\\Ndi\\params\\$kw\").GetValue('default'); $cur=$k.GetValue($kw); "
    "__BODY__ } }; "
)


def _nic_ps(mode: str, tag: str, keywords) -> str:
    """apply / revert / verify script for one adapter setting (see above)."""
    kws = ",".join(f"'{k}'" for k in keywords)
    if mode == "apply":
        body = ("$id=\"$tag|$s|$kw\"; "
                "if($null -eq $st.GetValue($id)){ $st.SetValue($id, $(if($null -eq $cur){'*none*'}else{\"$cur\"})) }; "
                "$k.SetValue($kw,'0',[Microsoft.Win32.RegistryValueKind]::String); $n++")
        head = "$st=[Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('SOFTWARE\\GameOptimizerPro\\NicOrig'); "
        tail = ("if($n -gt 0){ Write-Output \"$n adapter setting(s) set to 0 (effective after a restart)\"; exit 0 }; "
                "Write-Output 'Kein LAN-Adapter bietet diese Einstellung an / no wired adapter offers this setting'; exit 1")
        write = "$true"
    elif mode == "revert":
        body = ("$id=\"$tag|$s|$kw\"; $o=$null; if($st){ $o=$st.GetValue($id) }; "
                "if($null -ne $o){ if($o -eq '*none*'){ $k.DeleteValue($kw,$false) } "
                "else { $k.SetValue($kw,\"$o\",[Microsoft.Win32.RegistryValueKind]::String) }; $st.DeleteValue($id,$false) } "
                "elseif(\"$cur\" -eq '0' -and $null -ne $def -and \"$def\" -ne '0'){ "
                "$k.SetValue($kw,\"$def\",[Microsoft.Win32.RegistryValueKind]::String) }; $n++")
        head = "$st=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('SOFTWARE\\GameOptimizerPro\\NicOrig', $true); "
        tail = "exit 0"
        write = "$true"
    else:   # verify: every offered setting is 0 (a missing value counts as the driver default)
        body = "$n++; $v=$(if($null -ne $cur){\"$cur\"}else{\"$def\"}); if($v -ne '0'){ $bad=$true }"
        head = "$bad=$false; "
        tail = "if($n -gt 0 -and -not $bad){'1'}else{'0'}"
        write = "$false"
    loop = (_NIC_LOOP_PS.replace("__KWS__", kws).replace("__TAG__", tag)
            .replace("__WRITE__", write).replace("__BODY__", body))
    return head + loop + tail


XBOX_APPS = ("*Microsoft.XboxApp*", "*Microsoft.XboxGameOverlay*", "*Microsoft.XboxGamingOverlay*",
             "*Microsoft.XboxIdentityProvider*", "*Microsoft.XboxSpeechToTextOverlay*", "*Microsoft.Xbox.TCUI*")


def _remove_apps_ps(patterns: list[str]) -> str:
    """Remove Store apps for ALL users AND their provisioned package — a feature
    update (e.g. 26H2) re-installs apps that are only removed per user."""
    pats = ",".join(f"'{p}'" for p in patterns)
    return (
        f"$pats=@({pats}); foreach($p in $pats){{ "
        "Get-AppxPackage -AllUsers $p -EA SilentlyContinue | Remove-AppxPackage -AllUsers -EA SilentlyContinue; "
        "Get-AppxProvisionedPackage -Online -EA SilentlyContinue | Where-Object { $_.DisplayName -like $p } | "
        "Remove-AppxProvisionedPackage -Online -EA SilentlyContinue | Out-Null }; exit 0"
    )


# NVMe drives as Win32_DiskDrive rows, matched to the storage stack's BusType by
# disk number — the model name rarely says "NVMe" (e.g. "Samsung SSD 980 PRO").
_NVME_DISKS_PS = (
    r"$idx=@(Get-PhysicalDisk -EA SilentlyContinue | Where-Object { $_.BusType -eq 'NVMe' } | "
    r"ForEach-Object { [string]$_.DeviceId }); "
    r"$nv=@(Get-CimInstance Win32_DiskDrive -EA SilentlyContinue | Where-Object { $idx -contains [string]$_.Index }); "
)
# Internal fixed disks only (never removable/external media).
_FIXED_DISKS_PS = (
    r"$dd=@(Get-CimInstance Win32_DiskDrive -EA SilentlyContinue | "
    r"Where-Object { $_.PNPDeviceID -and $_.MediaType -match 'Fixed hard disk' }); "
)
# "Turn off Windows write-cache buffer flushing" = CacheIsPowerProtected=1.
# (v1 wrote UserWriteCacheSetting=1, which only ENABLES write caching.)
_WCACHE_APPLY = _FIXED_DISKS_PS + (
    "if($dd.Count -eq 0){ Write-Output '" + _tr("Keine internen Laufwerke gefunden", "No internal drives found")
    + "'; exit 1 }; "
    r"foreach($d in $dd){ reg add ('HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters\Disk') "
    r"/v CacheIsPowerProtected /t REG_DWORD /d 1 /f | Out-Null }; exit 0"
)
_WCACHE_REVERT = _FIXED_DISKS_PS + (
    r"foreach($d in $dd){ reg delete ('HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters\Disk') "
    r"/v CacheIsPowerProtected /f 2>$null | Out-Null }; exit 0"
)

# Paint AI policies (Windows Components > Paint): the three the WindowsAI Policy CSP documents —
# the status check reads the same list. Generative Erase / Remove Background have no policy: the
# two values set for them up to build 53 were in no Windows file and no documentation (nothing
# reads them); the revert still deletes them.
_PAINT_AI_KEY = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint"
_PAINT_AI_VALUES = ("DisableCocreator", "DisableGenerativeFill", "DisableImageCreator")
_PAINT_AI_OLD = ("DisableGenerativeErase", "DisableRemoveBackground")
_PAINT_AI_APPLY = "\n".join(
    f'reg add "{_PAINT_AI_KEY}" /v {v} /t REG_DWORD /d 1 /f'
    + (" | Out-Null" if i < len(_PAINT_AI_VALUES) - 1 else "")
    for i, v in enumerate(_PAINT_AI_VALUES))
_PAINT_AI_REVERT = "\n".join(
    f'reg delete "{_PAINT_AI_KEY}" /v {v} /f 2>$null' for v in _PAINT_AI_VALUES + _PAINT_AI_OLD) + "\nexit 0"

# SystemResponsiveness is shared by 'Network Throttling Index' and 'Audio-Priorität'.
# Each revert only restores the Windows default (20) if the OTHER tweak isn't
# still relying on 0 (v1's ownership-marker approach).
_SR_AUDIO_REVERT = (
    r"reg delete 'HKLM\SOFTWARE\GameOptimizerPro' /v SR_AudioPriority /f 2>$null | Out-Null; "
    r"$n=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile' "
    r"-Name NetworkThrottlingIndex -EA SilentlyContinue).NetworkThrottlingIndex; "
    r"if(-not ($n -eq -1 -or $n -eq 4294967295)){ "
    r"reg add 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile' "
    r"/v SystemResponsiveness /t REG_DWORD /d 20 /f | Out-Null }; exit 0"
)

# Disk Cleanup with an explicit ALLOW-list via /sagerun (silent). v1 used
# /VERYLOWDISK = every category, which depending on the build includes the
# Downloads folder and "Previous Installations" (Windows.old — the way back
# after a feature update). Also left out: Recycle Bin (Deep Clean asks for it),
# D3D Shader Cache (games would re-stutter), driver packages, install media.
_CLEANMGR_SAFE = (
    "Active Setup Temp Folders", "Delivery Optimization Files",
    "Diagnostic Data Viewer database files", "Downloaded Program Files",
    "Feedback Hub Archive log files", "Internet Cache Files", "Old ChkDsk Files",
    "RetailDemo Offline Content", "Setup Log Files", "System error memory dump files",
    "System error minidump files", "Temporary Files", "Temporary Setup Files",
    "Thumbnail Cache", "Update Cleanup", "Windows Defender",
    "Windows Error Reporting Files", "Windows Upgrade Log Files",
)
_DISK_CLEANUP_PS = (
    r"$vc='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches'; "
    "$safe=@(" + ",".join(f"'{n}'" for n in _CLEANMGR_SAFE) + "); "
    r"Get-ChildItem $vc -EA SilentlyContinue | ForEach-Object { "
    r"if($safe -contains $_.PSChildName){ Set-ItemProperty -Path $_.PSPath -Name StateFlags0077 -Value 2 -Type DWord -EA SilentlyContinue } "
    r"else { Remove-ItemProperty -Path $_.PSPath -Name StateFlags0077 -EA SilentlyContinue } }; "
    r"if(Test-Path (Join-Path $env:SystemRoot 'System32\cleanmgr.exe')){ Start-Process -FilePath cleanmgr.exe -ArgumentList '/sagerun:77' -Wait }; "
    r"Start-Process -FilePath Dism.exe -ArgumentList '/Online /Cleanup-Image /StartComponentCleanup' -Wait -WindowStyle Hidden; "
    r"exit 0"
)

# Telemetry tasks (v1's list + the newer appraiser). Windows 11 24H2+ no longer has "Microsoft
# Compatibility Appraiser" and "ProgramDataUpdater" (26H2 runs "...Appraiser Exp" instead): tasks a build
# does not have are skipped — apply, revert and the status check work on the ones that exist ($found).
_TELEMETRY_TASKS_PS = (
    "$tasks=@('\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser',"
    "'\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser Exp',"
    "'\\Microsoft\\Windows\\Application Experience\\ProgramDataUpdater',"
    "'\\Microsoft\\Windows\\Autochk\\Proxy',"
    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator',"
    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip',"
    "'\\Microsoft\\Windows\\DiskDiagnostic\\Microsoft-Windows-DiskDiagnosticDataCollector',"
    # round 45: Feedback-Hub data, the error report upload queue, SQM, the energy diagnosis (all four
    # exist on 26H2 except Sqm-Tasks; administrators have full access to them)
    "'\\Microsoft\\Windows\\Feedback\\Siuf\\DmClient',"
    "'\\Microsoft\\Windows\\Feedback\\Siuf\\DmClientOnScenarioDownload',"
    "'\\Microsoft\\Windows\\Windows Error Reporting\\QueueReporting',"
    "'\\Microsoft\\Windows\\PI\\Sqm-Tasks',"
    "'\\Microsoft\\Windows\\Power Efficiency Diagnostics\\AnalyzeSystem'); "
    "$found=@(foreach($t in $tasks){ $i=$t.LastIndexOf('\\'); "
    "Get-ScheduledTask -TaskPath $t.Substring(0,$i+1) -TaskName $t.Substring($i+1) -EA SilentlyContinue }); "
)
# Round 47: the same list for the status check, read through the Task Scheduler's own COM interface.
# Get-ScheduledTask loads its module and asks CIM per task — 3.7 s for the twelve, two thirds of the whole
# status check; this reads them in about 0.1 s with the same answers. A task that is missing or can't be
# read is skipped, as with -EA SilentlyContinue. ($found: the tasks, .Enabled false = disabled.)
_TASK_COM_PS = "$svc=New-Object -ComObject Schedule.Service; $svc.Connect(); "
_TELEMETRY_TASKS_COM_PS = (
    _TELEMETRY_TASKS_PS.split("$found=")[0] + _TASK_COM_PS +
    "$found=@(foreach($t in $tasks){ $i=$t.LastIndexOf('\\'); "
    "try { $svc.GetFolder($t.Substring(0,$i)).GetTask($t.Substring($i+1)) } catch {} }); "
)


# ── Registry values the user may have chosen: revert brings THEIR value back (round 45) ─────────────
# Privacy switches, Start and Explorer options — Windows setup or the user often set some of them
# already. Apply keeps every value as it was (…\Software\GameOptimizerPro\RegOrig in the same hive;
# "*none*" = it did not exist), revert writes exactly that back instead of a "Windows default" that can
# be worse than what was there (e.g. sending typing data back ON). Without a kept value (applied by an
# older version, or the store is gone) revert uses the item's fallback: None = delete the value, so
# Windows uses its default. The .NET registry API, not the cmdlets: names like
# "SubscribedContent-338389Enabled" need no escaping there.
# item: (hive "HKCU" | "HKLM", subkey, value name, "DWord" | "String", value, fallback or None)
_REG_HIVE_PS = ("$h=$(if($i[0] -eq 'HKLM'){[Microsoft.Win32.Registry]::LocalMachine}"
                "else{[Microsoft.Win32.Registry]::CurrentUser}); ")


def _ps_quote(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _reg_items_ps(items) -> str:
    rows = []
    for hive, path, name, kind, value, fallback in items:
        fb = "*del*" if fallback is None else f"{kind}|{fallback}"
        rows.append("@(" + ",".join(_ps_quote(x) for x in (hive, path, name, kind, value, fb)) + ")")
    # ONE row needs the comma operator: @(@('a','b')) is the flat list 'a','b' — the loop would walk
    # over the strings and index their characters (found by the round-45 test)
    return "@(," + rows[0] + ")" if len(rows) == 1 else "@(" + ",".join(rows) + ")"


# every loop also skips anything that is not a 6-field row (never index into a string)
_ROW_GUARD = "if($i.Count -ne 6){ continue }; "


def _reg_saved_ps(mode: str, tag: str, items, check=None) -> str:
    """apply / revert / verify for `items` (see above). verify: every value (or the names in `check`)
    has its target value."""
    if mode == "verify":
        rows = _reg_items_ps([i for i in items if check is None or i[2] in check])
        return ("$ok=$true; foreach($i in " + rows + "){ " + _ROW_GUARD + _REG_HIVE_PS +
                "$k=$h.OpenSubKey($i[1]); $v=$null; if($k){ $v=$k.GetValue($i[2],$null); $k.Close() }; "
                "if($null -eq $v -or \"$v\" -ne $i[4]){ $ok=$false } }; if($ok){'1'}else{'0'}")
    rows = _reg_items_ps(items)
    store = "'Software\\GameOptimizerPro\\RegOrig'"
    ident = f"$id='{tag}|'+$i[1]+'|'+$i[2]; "
    # every item on its own: one that can't be written (no rights) is reported, never changed without
    # its old value kept first; the others go on
    fail = (f"if($bad.Count){{ Write-Output ('{_tr('Nicht geändert', 'Not changed')}: ' + ($bad -join ', ')); "
            "exit 1 }; exit 0")
    if mode == "apply":
        return ("$bad=@(); foreach($i in " + rows + "){ " + _ROW_GUARD + "try { " + _REG_HIVE_PS +
                f"$st=$h.CreateSubKey({store}); $k=$h.CreateSubKey($i[1]); " + ident +
                "if($null -eq $st.GetValue($id)){ $cur=$k.GetValue($i[2],$null,'DoNotExpandEnvironmentNames'); "
                "if($null -eq $cur){ $o='*none*' } else { $kd=[string]$k.GetValueKind($i[2]); "
                "$o=$(if($kd -in 'DWord','QWord','String','ExpandString'){ $kd+'|'+$cur }else{ '*keep*' }) }; "
                "$st.SetValue($id,$o) }; "
                "if($i[3] -eq 'DWord'){ $k.SetValue($i[2],[int]$i[4],'DWord') }else{ $k.SetValue($i[2],[string]$i[4],'String') }; "
                "$k.Close(); $st.Close() } catch { $bad+=$i[2] } }; " + fail)
    return ("$bad=@(); foreach($i in " + rows + "){ " + _ROW_GUARD + "try { " + _REG_HIVE_PS +
            f"$st=$h.OpenSubKey({store},$true); $k=$h.OpenSubKey($i[1],$true); " + ident +
            "$o=$null; if($st){ $o=$st.GetValue($id,$null) }; if($null -eq $o){ $o=$i[5] }; "
            "if($k){ if($o -eq '*none*' -or $o -eq '*del*'){ $k.DeleteValue($i[2],$false) } "
            "elseif($o -ne '*keep*'){ $p=$o.IndexOf('|'); $kd=$o.Substring(0,$p); $v=$o.Substring($p+1); "
            "switch($kd){ 'DWord' { $k.SetValue($i[2],[int]$v,'DWord') } 'QWord' { $k.SetValue($i[2],[long]$v,'QWord') } "
            "'ExpandString' { $k.SetValue($i[2],$v,'ExpandString') } default { $k.SetValue($i[2],$v,'String') } } }; "
            "$k.Close() }; if($st){ $st.DeleteValue($id,$false); $st.Close() } } catch { $bad+=$i[2] } }; " + fail)


# ── Power settings with the plans' own values kept (round 45, DC + skipped plans since round 47) ──────
# Written into EVERY plan (like _power_all), on mains power (and on battery when `dc` is given). Apply keeps
# each plan's value (HKLM\SOFTWARE\GameOptimizerPro\PowerOrig, "ac" or "ac|dc"), revert puts it back.
# Without a kept value (applied by an older version) a plan goes back to its Windows default
# (DefaultPowerSchemeValues) — and only when it still has the tweak's value: a plan the old version never
# touched, or one the user changed since, stays as it is. Plans without a Windows default (a copy such as
# "Ultimate Performance") stay too. `skip`: a PowerShell condition on the `powercfg /L` line ($l) for plans
# the tweak leaves alone. Queried with /qh: "USB 3 Link Power Management" is a hidden setting, /query does
# not list it at all. sub / setting are GUIDs: the defaults are read from the registry by GUID.
def _power_saved_ps(mode: str, tag: str, sub: str, setting: str, ac: int, dc: int | None = None,
                    skip: str = "") -> str:
    plans = ("$g=@(); foreach($l in (powercfg /L 2>$null)){ "
             + (f"if({skip}){{ continue }}; " if skip else "") +
             "if($l -match '([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'){ $g+=$matches[1] } }; ")
    cur = (f"$o=(powercfg /qh $s {sub} {setting} 2>$null | Out-String); "
           "$m=[regex]::Matches($o,'0x[0-9a-fA-F]{8}'); ")
    read_ac = "[Convert]::ToInt64($m[$m.Count-2].Value.Substring(2),16)"
    read_dc = "[Convert]::ToInt64($m[$m.Count-1].Value.Substring(2),16)"
    if mode == "verify":
        return (cur.replace("$s", "SCHEME_CURRENT") +
                f"if($m.Count -ge 2 -and {read_ac} -eq {ac})" "{'1'}else{'0'}")
    if mode == "apply":
        keep = f"[string]{read_ac}" if dc is None else f"([string]{read_ac}+'|'+[string]{read_dc})"
        set_dc = ("" if dc is None else
                  f"powercfg /SETDCVALUEINDEX $s {sub} {setting} {dc} 2>$null | Out-Null; ")
        # the old values must be kept before anything changes: without the store (no admin) nothing is set
        return ("try { $st=[Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('SOFTWARE\\GameOptimizerPro\\PowerOrig') } "
                f"catch {{ Write-Output '{_tr('Keine Administratorrechte', 'No administrator rights')}'; exit 1 }}; "
                + plans + "$n=0; foreach($s in $g){ " + cur +
                "if($m.Count -lt 2){ continue }; "
                f"$id='{tag}|'+$s; if($null -eq $st.GetValue($id)){{ $st.SetValue($id,{keep}) }}; "
                f"powercfg /SETACVALUEINDEX $s {sub} {setting} {ac} 2>$null | Out-Null; $ok=($LASTEXITCODE -eq 0); "
                + set_dc + "if($ok){ $n++ } }; $st.Close(); powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null; "
                f"if($n -eq 0){{ Write-Output '{_tr('Diese Energieoption gibt es auf diesem PC nicht', 'This power setting does not exist on this PC')}'; exit 1 }}; "
                f"Write-Output \"$n {_tr('Energieplan(e) gesetzt', 'power plan(s) set')}\"; exit 0")
    defaults = (f"HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerSettings\\{sub}\\{setting}"
                "\\DefaultPowerSchemeValues")
    dc_default = ("" if dc is None else
                  f"if($m.Count -ge 2 -and {read_dc} -eq {dc}){{ $d=$def.DCSettingIndex }}; ")
    put_dc = ("" if dc is None else
              f"if($null -ne $d){{ powercfg /SETDCVALUEINDEX $s {sub} {setting} ([int64]$d) 2>$null | Out-Null }}; ")
    return ("$st=$null; try { $st=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('SOFTWARE\\GameOptimizerPro\\PowerOrig',$true) } catch {}; "
            + plans + "foreach($s in $g){ "
            f"$id='{tag}|'+$s; $v=$null; if($st){{ $v=$st.GetValue($id,$null) }}; $a=$null; $d=$null; "
            "if($null -ne $v){ $p=\"$v\".Split('|'); $a=$p[0]; if($p.Count -gt 1){ $d=$p[1] } } "
            f"else {{ $def=Get-ItemProperty \"{defaults}\\$s\" -EA SilentlyContinue; if($def){{ " + cur +
            f"if($m.Count -ge 2 -and {read_ac} -eq {ac}){{ $a=$def.ACSettingIndex }}; " + dc_default + "} }; "
            f"if($null -ne $a){{ powercfg /SETACVALUEINDEX $s {sub} {setting} ([int64]$a) 2>$null | Out-Null }}; "
            + put_dc +
            "if($st){ $st.DeleteValue($id,$false) } }; if($st){ $st.Close() }; "
            "powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null; exit 0")


_USB_SUB, _USB3_LPM = "2a737441-1930-4402-8d77-b2bebba308a3", "d4e98f31-5ffe-4ce1-be31-1b38b384c009"
_USB_SS = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"                                 # USB selective suspend
_SLEEP_SUB, _RTC_WAKE = "238c9fa8-0aad-41ed-83f4-97be242c8f20", "bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d"
_STANDBY_IDLE = "29f6c1db-86da-48c5-9fdb-f2b67b1f44da"                          # sleep after
_PCIE_SUB, _ASPM = "501a4d13-42af-4429-9fd1-a8218c268e20", "ee12f906-d277-404b-b6da-e5fa1a576df5"
_DISK_SUB, _DISK_IDLE = "0012ee47-9041-4b5d-9b77-535fba8b1442", "6738e2c4-e8a5-4a42-b16a-e040e769756e"
_CPU_SUB, _CPU_MIN = "54533251-82be-4824-96c1-47b60b740d00", "893dee8e-2bef-41e0-89c6-b55d0929964c"
_VIDEO_SUB, _VIDEO_IDLE = "7516b95f-f776-4464-8c53-06167f40cc99", "3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e"
# 'High performance' and copies of 'Ultimate Performance' (a copy has a GUID of its own: matched by name)
_SKIP_PERF_PLANS = "$l -match 'Ultimat' -or $l -match '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'"

# ── DNS provider (round 47): IPv4 AND IPv6, physical adapters only ─────────────────────────────────
# Only IPv4 was set: with IPv6 the router's DNS kept answering. VPN / virtual adapters are left alone.
# Round 49: apply keeps each adapter's servers from before (HKLM\SOFTWARE\GameOptimizerPro\DnsOrig,
# "<InterfaceGuid>|4" / "|6": the static list from the TCP/IP interface key, "" = automatic) and revert
# puts exactly that back — a DNS that was set by hand (Pi-hole, a company DNS) is no longer lost. Revert
# only touches adapters that still have this provider's addresses; one without a kept value (applied by
# an older version, which set virtual adapters too) goes back to automatic, as before.
DNS_PROVIDERS = {
    "dns_cloudflare": (("1.1.1.1", "1.0.0.1"), ("2606:4700:4700::1111", "2606:4700:4700::1001")),
    "dns_google": (("8.8.8.8", "8.8.4.4"), ("2001:4860:4860::8888", "2001:4860:4860::8844")),
}
# The adapters that are up, straight from CIM: the NetAdapter / DnsClient modules took ~0.4 s each to load in
# every status check (round 47, same answers). $na: MSFT_NetAdapter rows (Name, InterfaceGuid, InterfaceIndex).
_UP_ADAPTERS_CIM_PS = ("$na=@(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetAdapter -EA SilentlyContinue | "
                       "Where-Object { $_.InterfaceOperationalStatus -eq 1 }); ")
# physical: ConnectorPresent (Microsoft: TRUE for a physical adapter — what Get-NetAdapter -Physical returns)
_PHYS_UP = "@($na | Where-Object { $_.ConnectorPresent })"
_DNS_CIM_PS = "$dns=@(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_DNSClientServerAddress -EA SilentlyContinue); "
_DNS_STORE = "SOFTWARE\\GameOptimizerPro\\DnsOrig"
# the static servers of an interface (empty = from DHCP / automatic), IPv4 and IPv6
_DNS_IF_KEYS = (("4", "SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\"),
                ("6", "SYSTEM\\CurrentControlSet\\Services\\Tcpip6\\Parameters\\Interfaces\\"))


def _dns_ps(mode: str, tid: str) -> str:
    v4, v6 = DNS_PROVIDERS[tid]
    q4 = ",".join(f"'{a}'" for a in v4)
    q46 = ",".join(f"'{a}'" for a in v4 + v6)
    if mode == "apply":
        # keep what each adapter had before — once: a second apply (or the other provider) keeps the first
        keep = "".join(
            f"$id=$g+'|{fam}'; if($null -eq $st.GetValue($id)){{ $v=''; "
            f"$k=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('{root}'+$g); "
            "if($k){ $v=[string]$k.GetValue('NameServer',''); $k.Close() }; $st.SetValue($id,$v) }; "
            for fam, root in _DNS_IF_KEYS)
        return (_UP_ADAPTERS_CIM_PS + f"$a={_PHYS_UP}; if($a.Count -eq 0){{ Write-Output '"
                + _tr("Kein aktiver physischer Netzwerkadapter", "No active physical network adapter") +
                "'; exit 1 }; "
                f"$st=$null; try {{ $st=[Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('{_DNS_STORE}') }} catch {{}}; "
                "$bad=@(); foreach($x in $a){ $g=[string]$x.InterfaceGuid; "
                "if($st -and $g){ try { " + keep + "} catch {} }; "
                f"try {{ Set-DnsClientServerAddress -InterfaceIndex $x.InterfaceIndex -ServerAddresses @({q46}) -EA Stop }} "
                # an adapter without IPv6: IPv4 only
                f"catch {{ try {{ Set-DnsClientServerAddress -InterfaceIndex $x.InterfaceIndex -ServerAddresses @({q4}) -EA Stop }} "
                "catch { $bad+=$x.Name } } }; if($st){ $st.Close() }; "
                "if($bad.Count -ge $a.Count){ Write-Output ('" + _tr("Nicht gesetzt", "Not set") +
                ": ' + ($bad -join ', ')); exit 1 }; exit 0")
    if mode == "revert":
        # per adapter: automatic first (Windows resets both families at once), then the kept static servers
        # — a kept list that holds this provider's addresses itself (set by an older version) counts as automatic
        return (f"$ours=@({q46}); " + _DNS_CIM_PS +
                "$na0=@(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetAdapter -EA SilentlyContinue); "
                f"$st=$null; try {{ $st=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey('{_DNS_STORE}',$true) }} catch {{}}; "
                "$done=@(); foreach($d in $dns){ $ix=$d.InterfaceIndex; if($done -contains $ix){ continue }; "
                "if(-not @($d.ServerAddresses | Where-Object { $ours -contains $_ }).Count){ continue }; $done+=$ix; "
                "$g=[string](@($na0 | Where-Object { $_.InterfaceIndex -eq $ix } | ForEach-Object { $_.InterfaceGuid }) | Select-Object -First 1); "
                "$srv=@(); foreach($f in '4','6'){ $v=$null; if($st -and $g){ $v=$st.GetValue($g+'|'+$f,$null) }; "
                "if($null -ne $v){ $l=@(\"$v\" -split '[,\\s]+' | Where-Object { $_ }); "
                "if(-not @($l | Where-Object { $ours -contains $_ }).Count){ $srv+=$l } } }; "
                "Set-DnsClientServerAddress -InterfaceIndex $ix -ResetServerAddresses -EA SilentlyContinue; "
                "if($srv.Count){ try { Set-DnsClientServerAddress -InterfaceIndex $ix -ServerAddresses $srv -EA Stop } "
                "catch { Set-DnsClientServerAddress -InterfaceIndex $ix -ServerAddresses @($srv | Where-Object { $_ -notmatch ':' }) -EA SilentlyContinue } }; "
                "if($st -and $g){ $st.DeleteValue($g+'|4',$false); $st.DeleteValue($g+'|6',$false) } }; "
                "if($st){ $st.Close() }; exit 0")
    # verify: every active physical adapter asks this provider over IPv4 — and over IPv6 too when it has
    # IPv6 DNS servers at all (the router's IPv6 DNS would answer otherwise). AddressFamily 2 = IPv4, 23 = IPv6.
    return (_UP_ADAPTERS_CIM_PS + _DNS_CIM_PS + f"$a={_PHYS_UP}; $ok=($a.Count -gt 0); foreach($x in $a){{ "
            "$v4=@($dns | Where-Object { $_.InterfaceIndex -eq $x.InterfaceIndex -and $_.AddressFamily -eq 2 } | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ }); "
            "$v6=@($dns | Where-Object { $_.InterfaceIndex -eq $x.InterfaceIndex -and $_.AddressFamily -eq 23 } | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ }); "
            f"if(-not ($v4 -contains '{v4[0]}')){{ $ok=$false }}; "
            f"if($v6.Count -gt 0 -and -not ($v6 -contains '{v6[0]}')){{ $ok=$false }} }}; "
            "if($ok){'1'}else{'0'}")

# round 47: values whose previous state revert has to put back exactly (see _reg_saved_ps)
HAGS_ITEMS = [("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", "DWord", 2, None)]
BGAPPS_ITEMS = [("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
                 "GlobalUserDisabled", "DWord", 1, None)]
SVCHOST_DEFAULT_KB = 0x380000          # Windows' own threshold (3.5 GB) — not the decimal 380000
SVCHOST_ITEMS = [("HKLM", r"SYSTEM\CurrentControlSet\Control", "SvcHostSplitThresholdInKB", "DWord", "__RAM__",
                  SVCHOST_DEFAULT_KB)]   # __RAM__: the installed memory in KB, filled in by the apply script

_ADV_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
_CDM_KEY = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"

# Windows' own switches for its tips, suggestions and ads (Settings → System → Notifications,
# Privacy → General, Personalization → Start / Lock screen, Explorer options). Home and Pro.
TIPS_ITEMS = [
    ("HKCU", _CDM_KEY, "SubscribedContent-338389Enabled", "DWord", 0, None),   # tips & suggestions
    ("HKCU", _CDM_KEY, "SubscribedContent-310093Enabled", "DWord", 0, None),   # welcome page after updates
    ("HKCU", _CDM_KEY, "SubscribedContent-338393Enabled", "DWord", 0, None),   # suggested content in Settings
    ("HKCU", _CDM_KEY, "SubscribedContent-353694Enabled", "DWord", 0, None),
    ("HKCU", _CDM_KEY, "SubscribedContent-353696Enabled", "DWord", 0, None),
    ("HKCU", _CDM_KEY, "SubscribedContent-338387Enabled", "DWord", 0, None),   # lock screen: fun facts & tips
    ("HKCU", _CDM_KEY, "RotatingLockScreenOverlayEnabled", "DWord", 0, None),
    ("HKCU", _CDM_KEY, "SoftLandingEnabled", "DWord", 0, None),                # tips about Windows
    ("HKCU", _CDM_KEY, "SubscribedContent-338388Enabled", "DWord", 0, None),   # suggestions in Start (Win10)
    ("HKCU", _CDM_KEY, "SystemPaneSuggestionsEnabled", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement",
     "ScoobeSystemSettingEnabled", "DWord", 0, None),                           # "finish setting up your device"
    ("HKCU", _ADV_KEY, "Start_AccountNotifications", "DWord", 0, None),        # account hints in Start
    ("HKCU", _ADV_KEY, "ShowSyncProviderNotifications", "DWord", 0, None),     # OneDrive ads in Explorer
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\SystemSettings\AccountNotifications",
     "EnableAccountNotifications", "DWord", 0, None),                          # account hints in Settings
]
# the lock-screen pair is left out of the status check: with Windows Spotlight Windows manages it
TIPS_CHECK = [i[2] for i in TIPS_ITEMS if i[2] not in ("SubscribedContent-338387Enabled",
                                                       "RotatingLockScreenOverlayEnabled")]

# Typing, inking and speech data, tailored experiences, feedback requests (Settings → Privacy).
INPUT_ITEMS = [
    ("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", "DWord", 1, None),
    ("HKCU", r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", "DWord", 1, None),
    ("HKCU", r"Software\Microsoft\InputPersonalization\TrainedDataStore", "HarvestContacts", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Input\TIPC", "Enabled", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Privacy",
     "TailoredExperiencesWithDiagnosticDataEnabled", "DWord", 0, None),
    ("HKCU", r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", "DWord", 0, None),
    ("HKCU", r"Control Panel\International\User Profile", "HttpAcceptLanguageOptOut", "DWord", 1, None),
    ("HKCU", _ADV_KEY, "Start_TrackProgs", "DWord", 0, None),
]

# Search highlights and the cloud content search (Microsoft / work account) in Windows Search.
SEARCH_ITEMS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\SearchSettings", n, "DWord", 0, None)
    for n in ("IsDynamicSearchBoxEnabled", "IsMSACloudSearchEnabled", "IsAADCloudSearchEnabled")
]

# 'Recommended' in Start on every edition: no recent files, no tips / app suggestions.
RECO_ITEMS = [
    ("HKCU", _ADV_KEY, "Start_TrackDocs", "DWord", 0, None),
    ("HKCU", _ADV_KEY, "Start_IrisRecommendations", "DWord", 0, None),
]

LIGHTING_ITEMS = [("HKCU", r"Software\Microsoft\Lighting", "AmbientLightingEnabled", "DWord", 0, 1)]
ALTTAB_ITEMS = [("HKCU", _ADV_KEY, "MultiTaskingAltTabFilter", "DWord", 3, None)]
NEXUS_ITEMS = [("HKCU", r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled", "DWord", 0, None)]
LAUNCHTO_ITEMS = [("HKCU", _ADV_KEY, "LaunchTo", "DWord", 1, None)]
REMOTE_ASSIST_ITEMS = [
    ("HKLM", r"SYSTEM\CurrentControlSet\Control\Remote Assistance", "fAllowToGetHelp", "DWord", 0, 1),
    ("HKLM", r"SYSTEM\CurrentControlSet\Control\Remote Assistance", "fAllowFullControl", "DWord", 0, 1),
]

# OneDrive's documented policy "Prevent users from moving their Windows known folders to OneDrive"
# (any account, personal too). With the folders ALREADY in OneDrive it would also lock the "Manage
# backup" button that moves them back — so it refuses then and says what to do first.
_KFM_APPLY = (
    "$p=Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders' -EA SilentlyContinue; "
    "$moved=@(foreach($n in 'Desktop','Personal','My Pictures'){ if([string]$p.$n -match 'OneDrive'){ $n } }); "
    f"if($moved.Count){{ Write-Output ('{_tr('Ordner liegen schon in OneDrive', 'Folders are already in OneDrive')} (' + ($moved -join ', ') + "
    f"'). {_tr('Erst zurückholen: OneDrive-Einstellungen > Synchronisierung und Sicherung > Sicherung verwalten, dann erneut anwenden', 'Move them back first: OneDrive settings > Sync and backup > Manage backup, then apply again')}'); exit 1 }}; "
    "reg add 'HKLM\\SOFTWARE\\Policies\\Microsoft\\OneDrive' /v KFMBlockOptIn /t REG_DWORD /d 1 /f | Out-Null; exit 0"
)

# TargetReleaseVersion + ProductVersion (Policy CSP Update, Pro/Enterprise/Education): stay on the
# installed version (DisplayVersion, e.g. 26H2) — security and quality updates keep coming.
_PIN_KEY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
_PIN_APPLY = (
    "$cv=Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'; $ver=[string]$cv.DisplayVersion; "
    f"if($ver -notmatch '^\\d{{2}}H\\d$'){{ Write-Output ('{_tr('Windows-Version unbekannt', 'Windows version unknown')}: ' + $ver); exit 1 }}; "
    "$prod=$(if([int]$cv.CurrentBuild -ge 22000){'Windows 11'}else{'Windows 10'}); "
    f"reg add '{_PIN_KEY}' /v ProductVersion /t REG_SZ /d $prod /f | Out-Null; "
    f"reg add '{_PIN_KEY}' /v TargetReleaseVersion /t REG_DWORD /d 1 /f | Out-Null; "
    f"reg add '{_PIN_KEY}' /v TargetReleaseVersionInfo /t REG_SZ /d $ver /f | Out-Null; "
    f"Write-Output ('{_tr('Festgehalten auf', 'Staying on')} ' + $prod + ' ' + $ver); exit 0"
)
_PIN_REVERT = "; ".join(f"reg delete '{_PIN_KEY}' /v {v} /f 2>$null | Out-Null"
                        for v in ("TargetReleaseVersion", "TargetReleaseVersionInfo", "ProductVersion")) + "; exit 0"

# Visual effects: the animations off through SystemParametersInfo (written to the profile AND in
# effect at once, like the Performance Options dialog does), the useful look kept: smooth fonts,
# window contents while dragging, thumbnails, selection rectangle, icon label shadows. VisualFXSetting
# alone only selects the dialog's radio button — the individual switches are what Windows uses.
_VFX_ANIMS = "0x1003,0x1005,0x1007,0x1013,0x1015,0x1017,0x1019,0x101B,0x1043"  # menu, combo box, list box, menu / selection / tooltip fades, tooltip, cursor shadow, controls
_VFX_HEAD = (
    "Add-Type -Namespace GOPVfx -Name Spi -MemberDefinition "
    "'[DllImport(\"user32.dll\")] public static extern bool SystemParametersInfo(uint a, uint u, System.IntPtr p, uint f);'; "
    "function Set-MinAnimate($on){ $ai=[Runtime.InteropServices.Marshal]::AllocHGlobal(8); "
    "[Runtime.InteropServices.Marshal]::WriteInt32($ai,0,8); [Runtime.InteropServices.Marshal]::WriteInt32($ai,4,$on); "
    "[void][GOPVfx.Spi]::SystemParametersInfo(0x49,8,$ai,3); [Runtime.InteropServices.Marshal]::FreeHGlobal($ai) }; "
    "$adv='HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced'; "
    "$vfx='HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects'; "
)
_VFX_APPLY = _VFX_HEAD + (
    f"foreach($a in @({_VFX_ANIMS})){{ [void][GOPVfx.Spi]::SystemParametersInfo($a,0,[IntPtr]::Zero,3) }}; "
    "Set-MinAnimate 0; "
    "[void][GOPVfx.Spi]::SystemParametersInfo(0x25,1,[IntPtr]::Zero,3); "      # keep: window contents while dragging
    "[void][GOPVfx.Spi]::SystemParametersInfo(0x4B,1,[IntPtr]::Zero,3); "      # keep: smooth screen fonts
    "reg add $vfx /v VisualFXSetting /t REG_DWORD /d 3 /f | Out-Null; "
    "reg add $adv /v TaskbarAnimations /t REG_DWORD /d 0 /f | Out-Null; "
    "foreach($n in 'ListviewAlphaSelect','ListviewShadow'){ reg add $adv /v $n /t REG_DWORD /d 1 /f | Out-Null }; "
    "reg add $adv /v IconsOnly /t REG_DWORD /d 0 /f | Out-Null; exit 0"
)
_VFX_REVERT = _VFX_HEAD + (
    f"foreach($a in @({_VFX_ANIMS})){{ [void][GOPVfx.Spi]::SystemParametersInfo($a,0,[IntPtr]1,3) }}; "
    "Set-MinAnimate 1; "
    "reg add $vfx /v VisualFXSetting /t REG_DWORD /d 0 /f | Out-Null; "
    "reg add $adv /v TaskbarAnimations /t REG_DWORD /d 1 /f | Out-Null; exit 0"
)


ALL_TWEAKS: list[Tweak] = [

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — BLOATWARE
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="remove_xbox",
        name="Remove Xbox Apps",
        desc="Entfernt Xbox Game Bar, Xbox Identity Provider und Xbox TCUI. Laufen im Hintergrund auch ohne Xbox. "
             "Nicht anwenden, wenn du Spiele mit Xbox-Anmeldung (Game Pass, Microsoft Store), den Xbox-Modus "
             "oder Game-Bar-Aufnahmen nutzt — die fehlen danach, bis die Apps aus dem Store neu installiert sind.",
        category="Windows", group="Bloatware",
        # round 47: the package is "Microsoft.Xbox.TCUI" — "*XboxTCUI*" never matched it (found in v1). For
        # every user AND the provisioned package (a feature update re-installs per-user removals).
        ps_command=_remove_apps_ps(list(XBOX_APPS)),
        risk="moderate",
    ),
    Tweak(
        id="remove_copilot",
        name="Remove Copilot",
        desc="Deaktiviert Windows Copilot und verhindert dass er im Hintergrund Daten sendet.",
        category="Windows", group="Bloatware",
        ps_command='''
reg add "HKCU\\Software\\Policies\\Microsoft\\Windows\\WindowsCopilot" /v TurnOffWindowsCopilot /t REG_DWORD /d 1 /f
Get-AppxPackage -AllUsers "*Copilot*"|Remove-AppxPackage -ErrorAction SilentlyContinue
''',
        revert_cmd='reg delete "HKCU\\Software\\Policies\\Microsoft\\Windows\\WindowsCopilot" /v TurnOffWindowsCopilot /f 2>$null',
    ),
    Tweak(
        id="remove_onedrive",
        name="Remove OneDrive",
        desc="Deinstalliert OneDrive komplett inkl. Autostart. Lokale Dateien bleiben erhalten.",
        category="Windows", group="Bloatware",
        ps_command=(
            r'Stop-Process -Name "OneDrive" -Force -EA SilentlyContinue; '
            r'Start-Sleep 1; '
            r'$od = "$env:SYSTEMROOT\SysWOW64\OneDriveSetup.exe"; '
            r'if (-not (Test-Path $od)) { $od = "$env:SYSTEMROOT\System32\OneDriveSetup.exe" }; '
            r'if (Test-Path $od) { Start-Process -FilePath $od -ArgumentList "/uninstall" -NoNewWindow -Wait -EA SilentlyContinue }; '
            r'Get-AppxPackage -AllUsers "*OneDrive*" -EA SilentlyContinue | Remove-AppxPackage -EA SilentlyContinue; '
            r'Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name OneDrive -EA SilentlyContinue; '
            r'Write-Output "OneDrive removal completed"; '
            r'exit 0'
        ),
    ),
    Tweak(
        id="remove_recall",
        name="Remove Windows Recall",
        desc="Schaltet Windows Recall per offizieller Richtlinie ab (keine Screenshots deiner Aktivitäten mehr) "
             "und ENTFERNT beim nächsten Neustart die Recall-Komponenten samt gespeicherter Snapshots. "
             "Datenschutzkritisch.",
        category="Windows", group="Bloatware",
        # AllowRecallEnablement=0 is the documented policy that also REMOVES the
        # Recall bits (and saved snapshots) on the next restart; DisableAIDataAnalysis
        # is machine AND user scope (WindowsAI Policy CSP).
        ps_command=r'''
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableAIDataAnalysis /t REG_DWORD /d 1 /f | Out-Null
reg add "HKCU\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableAIDataAnalysis /t REG_DWORD /d 1 /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v AllowRecallEnablement /t REG_DWORD /d 0 /f
Disable-WindowsOptionalFeature -Online -FeatureName "Recall" -NoRestart -ErrorAction SilentlyContinue | Out-Null
''',
        revert_cmd=r'''
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableAIDataAnalysis /f 2>$null
reg delete "HKCU\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableAIDataAnalysis /f 2>$null
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v AllowRecallEnablement /f 2>$null
exit 0
''',
        requires_reboot=True,
    ),
    Tweak(
        id="remove_bloatware",
        name="Remove Bloatware (Candy Crush etc.)",
        desc="Entfernt die vorinstallierten Extras von Microsoft und die mitgelieferten Spiele: Candy Crush & Co., "
             "Solitaire, News, Wetter, Clipchamp, To Do, Feedback-Hub, Paint 3D, Mixed Reality u. a. — auch die "
             "bereitgestellten Pakete, damit Funktionsupdates sie nicht wieder installieren. Bewusst nicht: Apps, "
             "die viele selbst installieren (Spotify, Netflix, Disney+, TikTok, Instagram, Facebook, X), die "
             "Medienwiedergabe (unter Windows 11 der Standard-Player) und 'Hilfe anfordern' (über sie laufen die "
             "Problembehandlungen) — die entfernst du bei Bedarf einzeln auf der Seite Apps.",
        category="Windows", group="Bloatware",
        # Also removes the provisioned packages: feature updates re-install
        # apps that were only removed per user (seen with 26H2).
        # Round 45: Microsoft.ZuneMusic (Windows 11's Media Player, the default player for music and video —
        # the old "Groove") and Microsoft.GetHelp (Settings' troubleshooters run through it) are out.
        # Round 47 (found in v1): Spotify, Netflix, Disney+, TikTok, Instagram, Facebook and X are out — a
        # pattern can't tell Windows' pinned copy from the one the user installed and uses.
        ps_command=_remove_apps_ps([
            "*king.com*", "*BubbleWitch*", "*MarchofEmpires*", "*CandyCrush*",
            "*Microsoft.News*", "*Microsoft.BingWeather*", "*Microsoft.BingNews*",
            "*Microsoft.MicrosoftSolitaireCollection*",
            "*Microsoft.ZuneVideo*", "*Microsoft.WindowsFeedbackHub*", "*Microsoft.Todos*",
            "*Microsoft.Paint3D*", "*Microsoft.MixedReality*", "*Clipchamp*",
            "*Microsoft.Getstarted*", "*Microsoft.PowerAutomateDesktop*",
        ]),
    ),
    Tweak(
        id="disable_consumer_features",
        name="Vorgeschlagene Apps nicht still installieren",
        desc="Verhindert, dass Windows vorgeschlagene Apps und Spiele (Candy Crush, TikTok & Co.) still "
             "nachinstalliert — auch die vom Hersteller und von Microsoft vorgesehenen. Wirkt auf allen Editionen "
             "inkl. Home und Pro (Content Delivery Manager); dazu die Richtlinie „Microsoft-Verbrauchererlebnisse "
             "aus“, die Windows nur in Enterprise / Education beachtet. Bereits installierte Apps bleiben — dafür "
             "gibt es „Remove Bloatware“.",
        category="Windows", group="Bloatware",
        ps_command=('$c="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager"; '
                    'foreach($n in "SilentInstalledAppsEnabled","OemPreInstalledAppsEnabled","PreInstalledAppsEnabled")'
                    '{ reg add $c /v $n /t REG_DWORD /d 0 /f | Out-Null }; '
                    'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent" '
                    '/v DisableWindowsConsumerFeatures /t REG_DWORD /d 1 /f | Out-Null'),
        revert_cmd=('$c="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager"; '
                    'foreach($n in "SilentInstalledAppsEnabled","OemPreInstalledAppsEnabled","PreInstalledAppsEnabled")'
                    '{ reg add $c /v $n /t REG_DWORD /d 1 /f | Out-Null }; '
                    'reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent" '
                    '/v DisableWindowsConsumerFeatures /f 2>$null | Out-Null; exit 0'),
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — PRIVACY
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_telemetry",
        name="Disable Telemetry & Data Collection",
        desc="Deaktiviert alle Windows-Telemetriedienste (DiagTrack, dmwappushservice). Empfohlen für alle Nutzer.",
        category="Windows", group="Privacy",
        ps_command='''
Stop-Service DiagTrack -Force -ErrorAction SilentlyContinue
Set-Service DiagTrack -StartupType Disabled -ErrorAction SilentlyContinue
Stop-Service dmwappushservice -Force -ErrorAction SilentlyContinue
Set-Service dmwappushservice -StartupType Disabled -ErrorAction SilentlyContinue
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection" /v AllowTelemetry /t REG_DWORD /d 0 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\DataCollection" /v AllowTelemetry /t REG_DWORD /d 0 /f
''',
        revert_cmd='''
Set-Service DiagTrack -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service DiagTrack -ErrorAction SilentlyContinue
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection" /v AllowTelemetry /f 2>$null
''',
    ),
    Tweak(
        id="disable_activity_history",
        name="Disable Activity History",
        desc="Deaktiviert Windows Timeline. Windows speichert nicht mehr welche Apps und Dateien du geöffnet hast.",
        category="Windows", group="Privacy",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\System" /v EnableActivityFeed /t REG_DWORD /d 0 /f
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\System" /v PublishUserActivities /t REG_DWORD /d 0 /f
''',
        revert_cmd='''
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\System" /v EnableActivityFeed /f 2>$null
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\System" /v PublishUserActivities /f 2>$null
''',
    ),
    Tweak(
        id="disable_advertising_id",
        name="Disable Advertising ID",
        desc="Deaktiviert die Windows Werbe-ID. Apps können dich nicht mehr geräteübergreifend tracken.",
        category="Windows", group="Privacy",
        ps_command='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo" /v Enabled /t REG_DWORD /d 0 /f
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\AdvertisingInfo" /v DisabledByGroupPolicy /t REG_DWORD /d 1 /f
''',
        revert_cmd='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo" /v Enabled /t REG_DWORD /d 1 /f
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\AdvertisingInfo" /v DisabledByGroupPolicy /f 2>$null
''',
    ),
    Tweak(
        id="disable_bing_search",
        name="Disable Bing in Windows Search",
        desc="Deaktiviert die Bing-Web-Integration in der Windows-Suche. Die Startmenü-Suche bleibt lokal "
             "und lädt keine Web-Ergebnisse mehr nach. Dazu aus: Suchhervorhebungen (Bilder und Themen des "
             "Tages im Suchfeld) und die Cloud-Inhaltssuche (Ergebnisse aus OneDrive/Outlook des Microsoft- "
             "oder Arbeitskontos). Reduziert kleine Verzögerungen beim Öffnen des Startmenüs.",
        category="Windows", group="Privacy",
        ps_command=(
            r'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Search" '
            r'-Name BingSearchEnabled -Value 0 -Type DWord -EA SilentlyContinue; '
            r'$p="HKCU:\Software\Policies\Microsoft\Windows\Explorer"; '
            r'if(-not (Test-Path $p)){New-Item -Path $p -Force -EA SilentlyContinue | Out-Null}; '
            r'Set-ItemProperty -Path $p -Name DisableSearchBoxSuggestions -Value 1 -Type DWord -EA SilentlyContinue; '
            + _reg_saved_ps("apply", "SEARCH", SEARCH_ITEMS)
        ),
        revert_cmd=(
            r'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Search" '
            r'-Name BingSearchEnabled -Value 1 -Type DWord -EA SilentlyContinue; '
            r'Remove-ItemProperty -Path "HKCU:\Software\Policies\Microsoft\Windows\Explorer" '
            r'-Name DisableSearchBoxSuggestions -EA SilentlyContinue; '
            + _reg_saved_ps("revert", "SEARCH", SEARCH_ITEMS)
        ),
        risk="safe",
    ),
    Tweak(
        id="disable_location",
        name="Disable Location Tracking",
        desc="Deaktiviert den Windows Standortdienst systemweit.",
        category="Windows", group="Privacy",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location" /v Value /t REG_SZ /d Deny /f
Set-Service lfsvc -StartupType Disabled -ErrorAction SilentlyContinue
''',
        revert_cmd='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location" /v Value /t REG_SZ /d Allow /f
Set-Service lfsvc -StartupType Manual -ErrorAction SilentlyContinue
''',
    ),
    Tweak(
        id="disable_telemetry_tasks",
        name="Disable Scheduled Telemetry Tasks",
        desc="Deaktiviert die geplanten Windows-Aufgaben, die Telemetrie- und Diagnosedaten sammeln oder "
             "senden: Kompatibilitäts-Bewertung, Programm zur Verbesserung der Benutzerfreundlichkeit, "
             "Feedback-Daten, Warteschlange der Fehlerberichte, Datenträger- und Energiediagnose. Aufgaben, die "
             "es auf diesem Windows nicht gibt, werden übersprungen; der Revert schaltet sie wieder ein.",
        category="Windows", group="Privacy",
        ps_command=_TELEMETRY_TASKS_PS + (
            "$bad=@(); foreach($x in $found){ if(\"$($x.State)\" -ne 'Disabled'){ "
            "try { $x | Disable-ScheduledTask -EA Stop | Out-Null } catch { $bad += $x.TaskName } } }; "
            f"if($found.Count -eq 0){{ Write-Output '{_tr('Keine der Aufgaben gibt es auf diesem Windows', 'None of the tasks exists on this Windows')}'; exit 1 }}; "
            f"if($bad.Count){{ Write-Output ('{_tr('Nicht deaktiviert', 'Not disabled')}: ' + ($bad -join ', ')); exit 1 }}; "
            f"Write-Output \"$($found.Count) {_tr('Aufgaben deaktiviert', 'tasks disabled')}\"; exit 0"
        ),
        revert_cmd=_TELEMETRY_TASKS_PS + (
            "foreach($x in $found){ if(\"$($x.State)\" -eq 'Disabled'){ $x | Enable-ScheduledTask | Out-Null } }; exit 0"
        ),
    ),
    Tweak(
        id="disable_wpbt",
        name="Windows Platform Binary Table (WPBT) deaktivieren",
        desc="Verhindert, dass die Firmware/das Mainboard beim Start Programme ins Windows einschleusen "
             "kann (WPBT). Blockt vom Hersteller vorinstallierte Hintergrund-Software auf UEFI-Ebene. "
             "Sicher, reversibel.",
        category="Windows", group="Privacy",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager" /v DisableWpbtExecution /t REG_DWORD /d 1 /f',
        revert_cmd='reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager" /v DisableWpbtExecution /f 2>$null',
        risk="safe",
    ),
    Tweak(
        id="disable_ai_text_image_gen",
        name="Text- & Bildgenerierung (On-Device-KI) deaktivieren",
        desc="Sperrt die geräteinterne generative KI von Windows (Einstellungen → Datenschutz → "
             "Text- und Bildgenerierung) für alle Apps — den Schalter UND die Richtlinie (Force Deny), "
             "die Apps und Nutzer nicht wieder aufheben können. Betrifft nicht Cloud-KI-Dienste. Reversibel.",
        category="Windows", group="Privacy",
        # Consent switch (what Settings shows) + v1's policy (Force Deny), which
        # apps and users can't switch back on.
        ps_command=r'''
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\systemAIModels" /v Value /t REG_SZ /d Deny /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsAccessSystemAIModels /t REG_DWORD /d 2 /f
''',
        revert_cmd=r'''
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\systemAIModels" /v Value /t REG_SZ /d Allow /f | Out-Null
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsAccessSystemAIModels /f 2>$null
exit 0
''',
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — PERFORMANCE
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="ultimate_performance",
        name="Ultimate Performance Plan",
        desc="Aktiviert den 'Ultimative Leistung' Energiesparplan. CPU-Kerne werden nicht mehr gedrosselt, "
             "und im Netzbetrieb gehen Bildschirm und PC nie aus bzw. in den Standby. Erhöht Stromverbrauch. "
             "(Legt den Plan nur einmal an — früher kam bei jedem Anwenden eine weitere Kopie dazu; "
             "überzählige Kopien werden entfernt.)",
        category="Windows", group="Performance",
        ps_command=r'''
$re='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
$ult=@(powercfg /L 2>$null | Where-Object { $_ -match 'Ultimat' } | ForEach-Object { [regex]::Match($_,$re).Value } | Where-Object { $_ })
$act=[regex]::Match((powercfg /getactivescheme 2>$null | Out-String),$re).Value
if($ult.Count -eq 0){
    $o=(powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>&1 | Out-String)
    $new=[regex]::Match($o,$re).Value
    if(-not $new){ Write-Output "__ULT_NA__: $o"; exit 1 }
    $ult=@($new)
}
$keep=$(if($ult -contains $act){ $act } else { $ult[0] })
powercfg -setactive $keep
# Every earlier apply added one more copy of the plan: remove the extra ones.
foreach($g in $ult){ if($g -ne $keep){ powercfg -delete $g 2>$null | Out-Null } }
# High-performance plan: on mains power the screen never turns off and the PC never sleeps.
powercfg /SETACVALUEINDEX $keep SUB_VIDEO VIDEOIDLE 0
powercfg /SETACVALUEINDEX $keep SUB_SLEEP STANDBYIDLE 0
powercfg /SETACVALUEINDEX $keep SUB_SLEEP HIBERNATEIDLE 0
powercfg -setactive $keep
$now=[regex]::Match((powercfg /getactivescheme 2>$null | Out-String),$re).Value
if($now -ne $keep){ Write-Output "__ULT_NOT_ACTIVE__"; exit 1 }
Write-Output "__ULT_ACTIVE__ ($keep), __ULT_NEVER__: $($ult.Count - 1)"
'''.replace("__ULT_NA__", _tr("Plan 'Ultimative Leistung' nicht verfügbar", "Plan 'Ultimate Performance' not available"))
         .replace("__ULT_NOT_ACTIVE__", _tr("Plan ließ sich nicht aktivieren", "The plan could not be activated"))
         .replace("__ULT_ACTIVE__", _tr("Aktiv: Ultimative Leistung", "Active: Ultimate Performance"))
         .replace("__ULT_NEVER__", _tr("Bildschirm/Standby im Netzbetrieb: nie; entfernte Kopien",
                                       "screen/sleep on mains power: never; copies removed")),
        revert_cmd='powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
    ),
    Tweak(
        id="disable_hpet",
        name="Disable HPET",
        desc="Deaktiviert den High Precision Event Timer. Reduziert System-Latenz, bessere Frame-Zeiten in Spielen.",
        category="Windows", group="Performance",
        ps_command='''
bcdedit /deletevalue useplatformclock 2>$null
bcdedit /set useplatformtick yes
bcdedit /set disabledynamictick yes
''',
        revert_cmd='''
bcdedit /deletevalue useplatformclock 2>$null
bcdedit /deletevalue useplatformtick 2>$null
bcdedit /deletevalue disabledynamictick 2>$null
''',
        requires_reboot=True, risk="moderate",
    ),
    # The value sets no resolution itself — only a running program can (timeBeginPeriod /
    # NtSetTimerResolution). It brings back the system-wide effect of such requests.
    Tweak(
        id="timer_resolution",
        name="Timer-Anfragen systemweit gelten lassen",
        desc="Seit Windows 10 2004 gilt eine feinere Timer-Auflösung (z. B. 0,5 ms statt 15,6 ms) nur für "
             "das Programm, das sie anfordert, und Windows 11 ignoriert sie bei minimierten Fenstern. Der "
             "Wert stellt das frühere systemweite Verhalten wieder her. Ehrlich: Er setzt selbst keine "
             "Auflösung — die fordern Spiele und Tools beim Start selbst an. Wirkt nach einem Neustart.",
        category="Windows", group="Performance",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v GlobalTimerResolutionRequests /t REG_DWORD /d 1 /f',
        revert_cmd='reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v GlobalTimerResolutionRequests /f 2>$null; exit 0',
        requires_reboot=True,
    ),
    Tweak(
        id="disable_prefetch",
        name="Disable Prefetch & Superfetch",
        desc="Deaktiviert SysMain. Sinnvoll bei SSDs — auf HDDs nicht empfohlen.",
        category="Windows", group="Performance",
        ps_command='''
Stop-Service SysMain -Force -ErrorAction SilentlyContinue
Set-Service SysMain -StartupType Disabled -ErrorAction SilentlyContinue
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management\\PrefetchParameters" /v EnablePrefetcher /t REG_DWORD /d 0 /f
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management\\PrefetchParameters" /v EnableSuperfetch /t REG_DWORD /d 0 /f
''',
        revert_cmd='''
Set-Service SysMain -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service SysMain -ErrorAction SilentlyContinue
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management\\PrefetchParameters" /v EnablePrefetcher /t REG_DWORD /d 3 /f
''',
    ),
    Tweak(
        id="visual_effects_perf",
        name="Optimize Visual Effects (Performance)",
        desc="Schaltet die Windows-Animationen aus — Fenster minimieren/maximieren, Menüs, QuickInfos, Listen, "
             "Steuerelemente, Taskleiste — sofort, ohne Abmelden. Bewusst AN bleiben Kantenglättung der "
             "Schrift, Fensterinhalt beim Ziehen, Miniaturansichten und die Schatten unter Symbolnamen: die "
             "kosten praktisch nichts, ohne sie wird Windows nur unleserlicher. Windows reagiert spürbar "
             "direkter.",
        category="Windows", group="Performance",
        ps_command=_VFX_APPLY,
        revert_cmd=_VFX_REVERT,
    ),
    Tweak(
        id="disable_search_indexing",
        name="Disable Windows Search Indexing",
        desc="Deaktiviert WSearch. Reduziert Hintergrund-Festplattenzugriffe. Suche funktioniert weiter, aber langsamer.",
        category="Windows", group="Performance",
        ps_command='''
Stop-Service WSearch -Force -ErrorAction SilentlyContinue
Set-Service WSearch -StartupType Disabled -ErrorAction SilentlyContinue
''',
        revert_cmd='''
Set-Service WSearch -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service WSearch -ErrorAction SilentlyContinue
''',
    ),
    Tweak(
        id="disable_hibernation",
        name="Disable Hibernation",
        desc="Deaktiviert den Ruhezustand und löscht die hiberfil.sys (belegt sonst RAM-Größe auf der SSD, "
             "z.B. 32 GB). Schaltet auch das oft fehleranfällige Fast-Startup ab. Auf Desktop-Gaming-PCs unkritisch.",
        category="Windows", group="Performance",
        requires_reboot=True,
        ps_command='powercfg /hibernate off',
        revert_cmd='powercfg /hibernate on',
        risk="safe",
    ),
    Tweak(
        id="disable_storage_sense",
        name="Storage Sense deaktivieren",
        desc="Schaltet die automatische Speicherbereinigung von Windows ab, die im Hintergrund "
             "Dateien löschen kann. Wer selbst aufräumt (z.B. über den System Cleaner) braucht sie nicht.",
        category="Windows", group="Performance",
        ps_command='reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\StorageSense" /v AllowStorageSenseGlobal /t REG_DWORD /d 0 /f',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\StorageSense" /v AllowStorageSenseGlobal /f 2>$null',
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — MOUSE & UI
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_mouse_accel",
        name="Disable Mouse Acceleration",
        desc="Deaktiviert 'Enhance Pointer Precision'. Wichtig für FPS: 1:1 Mausbewegung ohne dynamische Verstärkung.",
        category="Windows", group="Mouse & UI",
        ps_command='''
reg add "HKCU\\Control Panel\\Mouse" /v MouseSpeed /t REG_SZ /d 0 /f
reg add "HKCU\\Control Panel\\Mouse" /v MouseThreshold1 /t REG_SZ /d 0 /f
reg add "HKCU\\Control Panel\\Mouse" /v MouseThreshold2 /t REG_SZ /d 0 /f
''',
        revert_cmd='''
reg add "HKCU\\Control Panel\\Mouse" /v MouseSpeed /t REG_SZ /d 1 /f
reg add "HKCU\\Control Panel\\Mouse" /v MouseThreshold1 /t REG_SZ /d 6 /f
reg add "HKCU\\Control Panel\\Mouse" /v MouseThreshold2 /t REG_SZ /d 10 /f
''',
    ),
    Tweak(
        id="disable_sticky_keys",
        name="Disable Sticky Keys",
        desc="Deaktiviert den Sticky Keys Dialog (5x Shift). Verhindert Unterbrechungen mitten im Spiel.",
        category="Windows", group="Mouse & UI",
        ps_command='''
reg add "HKCU\\Control Panel\\Accessibility\\StickyKeys" /v Flags /t REG_SZ /d 506 /f
reg add "HKCU\\Control Panel\\Accessibility\\Keyboard Response" /v Flags /t REG_SZ /d 122 /f
reg add "HKCU\\Control Panel\\Accessibility\\ToggleKeys" /v Flags /t REG_SZ /d 58 /f
''',
        revert_cmd='''
reg add "HKCU\\Control Panel\\Accessibility\\StickyKeys" /v Flags /t REG_SZ /d 510 /f
reg add "HKCU\\Control Panel\\Accessibility\\Keyboard Response" /v Flags /t REG_SZ /d 126 /f
reg add "HKCU\\Control Panel\\Accessibility\\ToggleKeys" /v Flags /t REG_SZ /d 62 /f
''',
    ),
    Tweak(
        id="enable_dark_mode",
        name="Enable Dark Mode",
        desc="Aktiviert dunklen Modus für Windows und Apps systemweit.",
        category="Windows", group="Mouse & UI",
        ps_command='''
reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme /t REG_DWORD /d 0 /f
reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v SystemUsesLightTheme /t REG_DWORD /d 0 /f
''',
        revert_cmd='''
reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme /t REG_DWORD /d 1 /f
reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v SystemUsesLightTheme /t REG_DWORD /d 1 /f
''',
    ),
    Tweak(
        id="disable_transparency",
        name="Disable Transparency Effects",
        desc="Deaktiviert Transparenz in Taskleiste und Startmenü. Spart GPU-Ressourcen.",
        category="Windows", group="Mouse & UI",
        ps_command='reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v EnableTransparency /t REG_DWORD /d 0 /f',
        revert_cmd='reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v EnableTransparency /t REG_DWORD /d 1 /f',
    ),
    Tweak(
        id="end_task_right_click",
        name="End Task per Rechtsklick (Taskleiste)",
        desc="Fügt der Taskleisten-Rechtsklick den Eintrag 'Task beenden' hinzu — ein eingefrorenes Spiel "
             "lässt sich damit sofort killen, ohne den Task-Manager zu öffnen. Windows 11 22H2+.",
        category="Windows", group="Mouse & UI",
        ps_command='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\\TaskbarDeveloperSettings" /v TaskbarEndTask /t REG_DWORD /d 1 /f',
        revert_cmd='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\\TaskbarDeveloperSettings" /v TaskbarEndTask /t REG_DWORD /d 0 /f',
        risk="safe",
    ),
    Tweak(
        id="show_file_extensions",
        name="Dateiendungen anzeigen",
        desc="Blendet die Dateiendungen (.exe, .txt, .cfg …) im Explorer ein. Hilft, getarnte "
             "Dateien wie 'setup.exe.scr' zu erkennen — kleiner Sicherheits- und Komfortgewinn.",
        category="Windows", group="Mouse & UI",
        ps_command='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v HideFileExt /t REG_DWORD /d 0 /f',
        revert_cmd='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v HideFileExt /t REG_DWORD /d 1 /f',
        risk="safe",
    ),
    Tweak(
        id="show_hidden_files",
        name="Versteckte Dateien anzeigen",
        desc="Zeigt versteckte Dateien und Ordner im Explorer an. Praktisch beim Aufräumen und "
             "Bearbeiten von App-Configs in versteckten Ordnern.",
        category="Windows", group="Mouse & UI",
        ps_command='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v Hidden /t REG_DWORD /d 1 /f',
        revert_cmd='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v Hidden /t REG_DWORD /d 2 /f',
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # GAMING — IN-GAME BOOSTS
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="enable_game_mode",
        name="Enable Game Mode",
        desc="Aktiviert Windows Game Mode. Priorisiert CPU/GPU für das aktive Spiel, unterbindet WU-Neustarts.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKCU\\Software\\Microsoft\\GameBar" /v AllowAutoGameMode /t REG_DWORD /d 1 /f
reg add "HKCU\\Software\\Microsoft\\GameBar" /v AutoGameModeEnabled /t REG_DWORD /d 1 /f
''',
        revert_cmd='''
reg add "HKCU\\Software\\Microsoft\\GameBar" /v AllowAutoGameMode /t REG_DWORD /d 0 /f
reg add "HKCU\\Software\\Microsoft\\GameBar" /v AutoGameModeEnabled /t REG_DWORD /d 0 /f
''',
    ),
    Tweak(
        id="disable_game_bar",
        name="Disable Xbox Game Bar",
        desc="Deaktiviert Xbox Game Bar (Win+G). Verhindert Hintergrundlast. Game Mode bleibt aktiv.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR" /v AppCaptureEnabled /t REG_DWORD /d 0 /f
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR" /v AllowGameDVR /t REG_DWORD /d 0 /f
''',
        revert_cmd='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR" /v AppCaptureEnabled /t REG_DWORD /d 1 /f
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR" /v AllowGameDVR /f 2>$null
''',
    ),
    Tweak(
        id="cpu_priority_games",
        name="CPU Priority for Games",
        desc="Setzt Win32PrioritySeparation auf 26. Windows gibt aktiven Spielen deutlich mehr CPU-Zeit.",
        category="Gaming", group="In-Game Boosts",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\PriorityControl" /v Win32PrioritySeparation /t REG_DWORD /d 26 /f',
        revert_cmd='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\PriorityControl" /v Win32PrioritySeparation /t REG_DWORD /d 2 /f',
    ),
    # MMCSS task "Games" (Microsoft Learn, Multimedia Class Scheduler Service): what counts is the
    # Scheduling Category — High = thread priority 23–26 instead of Medium's 16–22. "GPU Priority" is
    # "not yet used", and with the category High the Priority value "is always treated as 2" — the old
    # version wrote both and its status check looked at GPU Priority = 8, the Windows default (so the
    # tweak showed as active on every PC); the revert left the category on High.
    Tweak(
        id="mmcss_gaming",
        name="MMCSS Gaming Profile (High Priority)",
        desc="Setzt die MMCSS-Kategorie des Tasks 'Games' auf High: Threads, die sich bei Windows als "
             "Spiele-Task anmelden, laufen mit Priorität 23–26 statt 16–22. Ehrlich: Das tun nur manche Spiele "
             "und Programme; die oft mitgesetzten Werte 'GPU Priority' und 'Priority' liest Windows laut "
             "Microsoft dafür nicht (GPU Priority wird nicht verwendet, Priority gilt bei High immer als 2).",
        category="Gaming", group="In-Game Boosts",
        ps_command='reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Scheduling Category" /t REG_SZ /d High /f',
        revert_cmd='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Scheduling Category" /t REG_SZ /d Medium /f | Out-Null
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Priority" /t REG_DWORD /d 2 /f | Out-Null
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "GPU Priority" /t REG_DWORD /d 8 /f | Out-Null
exit 0
''',
    ),
    Tweak(
        id="disable_fullscreen_opt",
        name="Disable Fullscreen Optimizations",
        desc="Deaktiviert Windows Fullscreen Optimizations global. Erzwingt echtes Fullscreen für niedrigeren Input-Lag.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKCU\\System\\GameConfigStore" /v GameDVR_FSEBehaviorMode /t REG_DWORD /d 2 /f
reg add "HKCU\\System\\GameConfigStore" /v GameDVR_HonorUserFSEBehaviorMode /t REG_DWORD /d 1 /f
reg add "HKCU\\System\\GameConfigStore" /v GameDVR_FSEBehavior /t REG_DWORD /d 2 /f
''',
        revert_cmd='''
reg delete "HKCU\\System\\GameConfigStore" /v GameDVR_FSEBehaviorMode /f 2>$null
reg delete "HKCU\\System\\GameConfigStore" /v GameDVR_HonorUserFSEBehaviorMode /f 2>$null
reg delete "HKCU\\System\\GameConfigStore" /v GameDVR_FSEBehavior /f 2>$null
''',
    ),
    Tweak(
        id="disable_wu_gaming",
        name="Automatische Windows-Updates aus",
        desc="Windows lädt und installiert Updates nicht mehr von selbst, sondern meldet nur, dass welche da sind — "
             "dauerhaft, nicht nur beim Spielen. Keine Neustarts und Downloads mitten im Spiel, aber auch "
             "Sicherheitsupdates kommen erst, wenn du sie unter Einstellungen → Windows Update selbst startest. "
             "Nur, wenn du das regelmäßig machst. (Neustarts während der Nutzungszeit verhindert Windows ohnehin.)",
        category="Gaming", group="In-Game Boosts",
        # round 47 (found in v1): it was named "...during gaming" but turns automatic updates off for good
        # — honest name, risk advanced, in no preset any more
        ps_command='''
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v AUOptions /t REG_DWORD /d 2 /f
''',
        revert_cmd='''
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoUpdate /f 2>$null
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v AUOptions /f 2>$null
''',
        risk="advanced",
    ),
    Tweak(
        # id kept: what the app applied stays recognised. Round 47 (found in v1): it was named "background
        # app throttling" but GlobalUserDisabled switches background Store apps off, and the second value
        # (kernel\DisableLowQosTimerResolution) is documented nowhere — not set any more, the revert still
        # removes it. The value the user had is kept and put back.
        id="disable_bg_throttle",
        name="Hintergrund-Apps stoppen (alle Editionen)",
        desc="Store-Apps laufen nicht mehr im Hintergrund weiter (Windows' Schalter „Apps im Hintergrund "
             "ausführen“ für deinen Benutzer, auch auf Home). Spart etwas Arbeitsspeicher und CPU-Zeit. Folge: "
             "Geschlossene Store-Apps wie WhatsApp, Phone Link oder Mail melden keine neuen Nachrichten. Das "
             "Drosseln von Prozessen durch Windows ist ein anderer Tweak („Disable Power Throttling“). Dasselbe "
             "als Richtlinie für alle Benutzer (nur Pro): „Store-Apps nicht im Hintergrund laufen lassen“ — "
             "einer von beiden reicht.",
        category="Gaming", group="In-Game Boosts",
        ps_command=_reg_saved_ps("apply", "disable_bg_throttle", BGAPPS_ITEMS),
        revert_cmd=('$p="HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel"; '
                    'if((Get-ItemProperty $p -Name DisableLowQosTimerResolution -EA SilentlyContinue).DisableLowQosTimerResolution -eq 1)'
                    '{ Remove-ItemProperty $p -Name DisableLowQosTimerResolution -EA SilentlyContinue }; '
                    + _reg_saved_ps("revert", "disable_bg_throttle", BGAPPS_ITEMS)),
        risk="moderate",
    ),
    Tweak(
        id="disable_power_throttling",
        name="Disable Power Throttling",
        desc="Verhindert dass Windows Prozesse zur Energieeinsparung drosselt. Nützlich bei Spielen "
             "mit mehreren Prozessen, deren Nebenprozesse sonst gedrosselt werden können.",
        category="Gaming", group="In-Game Boosts",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling" /v PowerThrottlingOff /t REG_DWORD /d 1 /f',
        revert_cmd='reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling" /v PowerThrottlingOff /f 2>$null',
        risk="safe",
    ),
    Tweak(
        id="reduce_process_count",
        name="Process Count Reduction (Svchost)",
        desc="Setzt den Svchost-Split-Schwellwert auf die RAM-Größe, sodass Windows Dienste in weniger "
             "separate Prozesse aufteilt. Reduziert die Gesamtzahl der Hintergrundprozesse. Bei 16GB+ RAM unkritisch.",
        category="Gaming", group="In-Game Boosts",
        requires_reboot=True,
        # round 47 (found in v1): the revert wrote "380000" — decimal for reg.exe, not Windows' 0x380000
        # (3.5 GB) — and the check called every untouched Windows "active" (0x380000 > 380000). The value
        # before is kept and put back; without one, Windows' 0x380000.
        ps_command=("$ramKB=[math]::Round((Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1024); "
                    + _reg_saved_ps("apply", "reduce_process_count", SVCHOST_ITEMS).replace("'__RAM__'", '"$ramKB"')),
        revert_cmd=_reg_saved_ps("revert", "reduce_process_count", SVCHOST_ITEMS),
        risk="moderate",
    ),

    # ══════════════════════════════════════════════════════════════
    # GAMING — GPU & DRIVER
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="enable_msi_mode",
        name="Enable MSI Mode (Interrupts)",
        desc="Aktiviert Message Signaled Interrupts für die GPU. Reduziert Interrupt-Latenz. Reboot nötig.",
        category="Gaming", group="GPU & Driver",
        ps_command='''
$dev=Get-WmiObject Win32_VideoController|Where-Object{$_.Name -notmatch "Microsoft"}|Select-Object -First 1
if($dev){
  $p="HKLM\\SYSTEM\\CurrentControlSet\\Enum\\$($dev.PNPDeviceID)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"
  reg add $p /v MSISupported /t REG_DWORD /d 1 /f
}
''',
        revert_cmd='''
$dev=Get-WmiObject Win32_VideoController|Where-Object{$_.Name -notmatch "Microsoft"}|Select-Object -First 1
if($dev){
  $p="HKLM\\SYSTEM\\CurrentControlSet\\Enum\\$($dev.PNPDeviceID)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"
  reg delete $p /v MSISupported /f 2>$null
}
''',
        requires_reboot=True,
    ),
    Tweak(
        id="enable_hags",
        name="Enable HAGS (HW-Accelerated GPU Scheduling)",
        desc="Übergibt GPU-Scheduling direkt an Hardware. Weniger CPU-Overhead, geringerer Input-Lag. Braucht RTX "
             "2000+ oder RX 5000+; DLSS Frame Generation setzt es voraus. Zurücksetzen stellt den Zustand von "
             "vorher wieder her (vorher nicht gesetzt: Windows entscheidet wieder selbst).",
        category="Gaming", group="GPU & Driver",
        # round 47 (found in v1): the revert switched HAGS OFF (1) even where it had been on before
        ps_command=_reg_saved_ps("apply", "enable_hags", HAGS_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "enable_hags", HAGS_ITEMS),
        requires_reboot=True,
    ),
    Tweak(
        id="windowed_game_optimizations",
        name="Optimierungen für Spiele im Fenstermodus",
        desc="Schaltet die Windows-Einstellung „Optimierungen für Spiele im Fenstermodus“ ein "
             "(Einstellungen → System → Anzeige → Grafik): DirectX-10/11-Spiele im Fenster oder randlosen "
             "Fenster nutzen das moderne Flip-Modell statt der alten Ausgabe — weniger Latenz, VRR "
             "(G-Sync/FreeSync) und Auto HDR auch im Fenster. DX12-Spiele nutzen es bereits. Reversibel.",
        category="Gaming", group="GPU & Driver",
        ps_command='''
$k="HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"
if(-not (Test-Path $k)){New-Item -Path $k -Force | Out-Null}
$cur=(Get-ItemProperty $k -Name DirectXUserGlobalSettings -EA SilentlyContinue).DirectXUserGlobalSettings
$parts=@(); if($cur){$parts=@($cur.Split(';') | Where-Object { $_ -and $_ -notmatch '^SwapEffectUpgradeEnable=' })}
$parts+='SwapEffectUpgradeEnable=1'
Set-ItemProperty -Path $k -Name DirectXUserGlobalSettings -Value (($parts -join ';') + ';') -Type String
''',
        revert_cmd='''
$k="HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"
$cur=(Get-ItemProperty $k -Name DirectXUserGlobalSettings -EA SilentlyContinue).DirectXUserGlobalSettings
if($cur){
  $parts=@($cur.Split(';') | Where-Object { $_ -and $_ -notmatch '^SwapEffectUpgradeEnable=' })
  if($parts.Count){Set-ItemProperty -Path $k -Name DirectXUserGlobalSettings -Value (($parts -join ';') + ';') -Type String}
  else{Remove-ItemProperty -Path $k -Name DirectXUserGlobalSettings -EA SilentlyContinue}
}
''',
    ),
    Tweak(
        id="clear_shader_cache",
        name="Clear Shader Cache",
        desc="Leert NVIDIA/AMD Shader-Cache (einmalige Aktion). Nur nach Treiberupdates oder bei "
             "Grafikfehlern — danach baut jedes Spiel seine Shader neu (die ersten Minuten ruckeln).",
        category="Gaming", group="GPU & Driver",
        ps_command='''
$paths=@("$env:LOCALAPPDATA\\NVIDIA\\DXCache","$env:LOCALAPPDATA\\NVIDIA\\GLCache",
"$env:LOCALAPPDATA\\D3DSCache","$env:TEMP\\AMD")
foreach($p in $paths){if(Test-Path $p){Remove-Item "$p\\*" -Recurse -Force -ErrorAction SilentlyContinue}}
''',
    ),
    Tweak(
        id="dx12_optimization",
        name="GPU-Timeout erhöhen (TDR-Delay)",
        desc="Erhöht den GPU-Watchdog-Timeout (TdrDelay/TdrDdiDelay auf 10s), damit anspruchsvolle "
             "DX12-Szenen unter Last nicht fälschlich einen Treiber-Reset (TDR) auslösen. "
             "KEIN FPS-Boost — verhindert nur unnötige Timeouts/Freezes. Reversibel.",
        category="Gaming", group="GPU & Driver",
        ps_command='''
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDelay /t REG_DWORD /d 10 /f
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDdiDelay /t REG_DWORD /d 10 /f
''',
        revert_cmd='''
reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDelay /f 2>$null
reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDdiDelay /f 2>$null
''',
    ),
    Tweak(
        id="disable_mpo",
        name="Multiplane Overlay (MPO) deaktivieren",
        desc="Schaltet MPO ab (Registry OverlayTestMode=5). Bekannter Fix gegen Bild-Flackern und "
             "Mikroruckler, v.a. bei NVIDIA + Multi-Monitor. HINWEIS: neuere Treiber haben MPO-Bugs "
             "großteils behoben — nur aktivieren wenn du solche Flacker-/Ruckel-Probleme hast. Neustart nötig.",
        category="Gaming", group="GPU & Driver",
        requires_reboot=True,
        ps_command='reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\Dwm" /v OverlayTestMode /t REG_DWORD /d 5 /f',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows\\Dwm" /v OverlayTestMode /f 2>$null',
        risk="moderate",
    ),

    # ══════════════════════════════════════════════════════════════
    # NETWORK — LATENCY
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_nagle",
        name="Disable Nagle's Algorithm (TCPNoDelay)",
        desc="Deaktiviert Nagle auf allen Netzwerkadaptern. Weniger Latenz in Online-Spielen — spürbarer Ping-Unterschied.",
        category="Network", group="Latency",
        ps_command='''
$adapters=Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\*"
foreach($a in $adapters){
  Set-ItemProperty -Path $a.PSPath -Name "TcpAckFrequency" -Value 1 -Type DWord -ErrorAction SilentlyContinue
  Set-ItemProperty -Path $a.PSPath -Name "TCPNoDelay" -Value 1 -Type DWord -ErrorAction SilentlyContinue
}
''',
        revert_cmd='''
$adapters=Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\*"
foreach($a in $adapters){
  Remove-ItemProperty -Path $a.PSPath -Name "TcpAckFrequency" -ErrorAction SilentlyContinue
  Remove-ItemProperty -Path $a.PSPath -Name "TCPNoDelay" -ErrorAction SilentlyContinue
}
''',
    ),
    Tweak(
        id="disable_lso",
        name="Disable Large Send Offload (LSO)",
        desc="Deaktiviert LSO auf aktiven Adaptern. Hilft bei instabilem Ping in Online-Spielen.",
        category="Network", group="Latency",
        ps_command='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Disable-NetAdapterLso -Name $a.Name -ErrorAction SilentlyContinue}
''',
        revert_cmd='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Enable-NetAdapterLso -Name $a.Name -ErrorAction SilentlyContinue}
''',
    ),
    Tweak(
        id="disable_network_throttle",
        name="Disable Network Throttling Index",
        desc="Deaktiviert Netzwerk-Throttling bei hoher CPU-Last. Gibt dem Netzwerk-Stack höchste Priorität. "
             "Setzt dazu SystemResponsiveness auf 10 (der kleinste Wert, den Windows annimmt).",
        category="Network", group="Latency",
        # SystemResponsiveness: Microsoft — "values below 10 and above 100 are clamped to 20" (the
        # default). The 0 written up to round 44 therefore changed nothing; 10 is the lowest that counts.
        ps_command='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v NetworkThrottlingIndex /t REG_DWORD /d 0xffffffff /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 10 /f
''',
        revert_cmd=r'''
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v NetworkThrottlingIndex /t REG_DWORD /d 10 /f | Out-Null
if (-not (Get-ItemProperty 'HKLM:\SOFTWARE\GameOptimizerPro' -Name SR_AudioPriority -EA SilentlyContinue)) {
  reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 20 /f | Out-Null
}
exit 0
''',
    ),
    Tweak(
        id="disable_delivery_optimization",
        name="Disable Delivery Optimization (P2P Updates)",
        desc="Schaltet das Peer-to-Peer-Teilen von Windows-Updates ab, das sonst im Hintergrund Upload- und "
             "Download-Bandbreite frisst — spürbar für stabilere Pings beim Online-Gaming. Reine Richtlinie.",
        category="Network", group="Latency",
        ps_command='reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\DeliveryOptimization" /v DODownloadMode /t REG_DWORD /d 0 /f',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\DeliveryOptimization" /v DODownloadMode /f 2>$null',
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # NETWORK — DNS
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="dns_cloudflare",
        name="Set DNS to Cloudflare (1.1.1.1)",
        desc="Setzt DNS auf Cloudflare — IPv4 (1.1.1.1 / 1.0.0.1) und IPv6 (2606:4700:4700::1111 / ::1001), nur "
             "an den physischen Netzwerkadaptern (VPN und virtuelle Adapter bleiben, wie sie sind). Einer der "
             "schnellsten und datenschutzfreundlichsten DNS-Dienste.",
        category="Network", group="DNS",
        ps_command=_dns_ps("apply", "dns_cloudflare"),
        revert_cmd=_dns_ps("revert", "dns_cloudflare"),
    ),
    Tweak(
        id="dns_google",
        name="Set DNS to Google (8.8.8.8)",
        desc="Setzt DNS auf Google — IPv4 (8.8.8.8 / 8.8.4.4) und IPv6 (2001:4860:4860::8888 / ::8844), nur an den "
             "physischen Netzwerkadaptern (VPN und virtuelle Adapter bleiben, wie sie sind). Global verteilt, "
             "schnell und zuverlässig.",
        category="Network", group="DNS",
        ps_command=_dns_ps("apply", "dns_google"),
        revert_cmd=_dns_ps("revert", "dns_google"),
    ),
    Tweak(
        id="flush_dns",
        name="Flush DNS Cache",
        desc="Leert den lokalen DNS-Cache. Schnell, ohne Nebenwirkungen.",
        category="Network", group="DNS",
        ps_command='ipconfig /flushdns',
    ),

    # ══════════════════════════════════════════════════════════════
    # NETWORK — TCP
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_tcp_autotuning",
        name="Disable TCP Auto-Tuning",
        desc="Schaltet das automatische TCP-Empfangsfenster ab — es bleibt bei 64 KB. Ehrlich: Downloads werden "
             "dadurch deutlich langsamer (bei 20 ms Ping höchstens rund 25 Mbit/s pro Verbindung), einen belegten "
             "Nutzen für den Ping in Spielen gibt es nicht. Nur zur Fehlersuche mit sehr alten Routern.",
        category="Network", group="TCP",
        ps_command='netsh int tcp set global autotuninglevel=disabled',
        revert_cmd='netsh int tcp set global autotuninglevel=normal',
        risk="moderate",
    ),
    Tweak(
        id="enable_rss",
        name="Enable Receive-Side Scaling (RSS)",
        desc="Aktiviert RSS auf allen Adaptern, die es anbieten. Verteilt Netzwerkverarbeitung auf mehrere "
             "CPU-Kerne. Besser bei schnellen Verbindungen. (Meldet ehrlich, wenn der Treiber RSS nicht über "
             "Windows einstellbar macht.)",
        category="Network", group="TCP",
        ps_command=r'''
$n=0; $ok=0; $msg=@()
foreach($a in @(Get-NetAdapter -EA SilentlyContinue | Where-Object { $_.Status -eq 'Up' })){
    $r=Get-NetAdapterRss -Name $a.Name -EA SilentlyContinue
    if(-not $r){ $msg+="$($a.Name): __RSS_NONE__"; continue }
    $n++
    try { Enable-NetAdapterRss -Name $a.Name -EA Stop; $ok++ } catch { $msg+="$($a.Name): $($_.Exception.Message)" }
}
$msg
if($ok -gt 0){ Write-Output "__RSS_ON__"; exit 0 }
if($n -eq 0){ Write-Output "__RSS_NO_ADAPTER__"; exit 1 }
exit 1
'''.replace("__RSS_NONE__", _tr("Treiber meldet keine RSS-Einstellung", "the driver reports no RSS setting"))
         .replace("__RSS_ON__", _tr("RSS aktiv auf $ok von $n Adapter(n)", "RSS on for $ok of $n adapter(s)"))
         .replace("__RSS_NO_ADAPTER__", _tr("Kein aktiver Adapter bietet RSS über Windows an (Treiber)",
                                            "No active adapter offers RSS through Windows (driver)")),
        # RSS is enabled by default on virtually all modern adapters, so the
        # honest "revert" is to leave it enabled (the Windows default) rather
        # than force it off — which would leave the PC worse than before.
        revert_cmd=r'''
foreach($a in @(Get-NetAdapter -EA SilentlyContinue | Where-Object { $_.Status -eq 'Up' })){
    if(Get-NetAdapterRss -Name $a.Name -EA SilentlyContinue){ Enable-NetAdapterRss -Name $a.Name -EA SilentlyContinue }
}
exit 0
''',
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS 11 SPECIFIC
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="w11_classic_context_menu",
        name="Win11: Classic Right-Click Menu",
        desc="Stellt das klassische Rechtsklick-Kontextmenü in Windows 11 wieder her. Kein 'Weitere Optionen anzeigen' mehr. "
             "Hinweis: Mit dem Windows-Update KB5127936 (Okt. 2026) wird das neue Menü schrittweise selbst anpassbar "
             "(Rechtsklick → 'Menü anpassen'). Wirkt der Tweak danach nicht mehr, einfach zurücksetzen.",
        category="Windows", group="Windows 11",
        ps_command='reg add "HKCU\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\\InprocServer32" /ve /t REG_SZ /d "" /f',
        revert_cmd='reg delete "HKCU\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f 2>$null',
    ),
    Tweak(
        id="w11_taskbar_left",
        name="Win11: Taskbar Icons Left-Aligned",
        desc="Verschiebt Taskbar-Icons nach links (klassisches Layout wie Win10).",
        category="Windows", group="Windows 11",
        ps_command='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v TaskbarAl /t REG_DWORD /d 0 /f',
        revert_cmd='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v TaskbarAl /t REG_DWORD /d 1 /f',
    ),
    Tweak(
        id="w11_disable_widgets",
        name="Win11: Disable Widgets",
        desc="Deaktiviert das Windows 11 Widgets-Panel. Spart RAM und reduziert Hintergrundaktivität.",
        category="Windows", group="Windows 11",
        ps_command='''
$key = "HKLM:\\\\SOFTWARE\\\\Policies\\\\Microsoft\\\\Dsh"
try {
    if (-not (Test-Path $key)) { New-Item -Path $key -Force -EA SilentlyContinue | Out-Null }
    Set-ItemProperty -Path $key -Name AllowNewsAndInterests -Value 0 -Type DWord -EA SilentlyContinue
    Write-Output "Widgets disabled"
} catch {
    $ukey = "HKCU:\\\\Software\\\\Policies\\\\Microsoft\\\\Dsh"
    if (-not (Test-Path $ukey)) { New-Item -Path $ukey -Force -EA SilentlyContinue | Out-Null }
    Set-ItemProperty -Path $ukey -Name AllowNewsAndInterests -Value 0 -Type DWord -EA SilentlyContinue
}
exit 0
''',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Dsh" /v AllowNewsAndInterests /f 2>$null',
    ),
    Tweak(
        id="w11_disable_snap_suggest",
        name="Win11: Disable Snap Layout Suggestions",
        desc="Deaktiviert das automatische Snap-Layout-Popup beim Hovern über den Maximieren-Button.",
        category="Windows", group="Windows 11",
        ps_command='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v EnableSnapAssistFlyout /t REG_DWORD /d 0 /f',
        revert_cmd='reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v EnableSnapAssistFlyout /t REG_DWORD /d 1 /f',
    ),

    # ══════════════════════════════════════════════════════════════
    # POWER PLAN
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="power_balanced",
        name="Power Plan: Balanced",
        desc="Setzt den Energiesparplan auf 'Ausbalanciert' (Windows Standard). Alternative zu 'Höchstleistung' "
             "und 'Ultimative Leistung' — es kann nur ein Plan aktiv sein. Für AMD-X3D-CPUs die Empfehlung von AMD.",
        category="Windows", group="Power Plan",
        ps_command='powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
    ),
    Tweak(
        id="power_high",
        name="Power Plan: High Performance",
        desc="Aktiviert 'Höchstleistung'. Guter Kompromiss zwischen Performance und Stromverbrauch; im "
             "Netzbetrieb gehen Bildschirm und PC nie aus bzw. in den Standby. (Alternative zu "
             "'Ultimative Leistung' und 'Ausbalanciert' — es kann nur ein Plan aktiv sein.)",
        category="Windows", group="Power Plan",
        ps_command=r'''
$g='8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
if(-not (powercfg /L 2>$null | Select-String $g)){ powercfg -duplicatescheme $g $g 2>$null | Out-Null }
powercfg -setactive $g
# High-performance plan: on mains power the screen never turns off and the PC never sleeps.
powercfg /SETACVALUEINDEX $g SUB_VIDEO VIDEOIDLE 0
powercfg /SETACVALUEINDEX $g SUB_SLEEP STANDBYIDLE 0
powercfg /SETACVALUEINDEX $g SUB_SLEEP HIBERNATEIDLE 0
powercfg -setactive $g
''',
    ),
    Tweak(
        id="disable_usb_suspend",
        name="Disable USB Selective Suspend",
        desc="Verhindert, dass USB-Geräte (Maus, Headset) in den Stromsparmodus versetzt werden — in allen "
             "Energieplänen, im Netzbetrieb. Kein plötzliches Trennen mehr. Zurücksetzen stellt den Wert jedes "
             "Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        # round 47: every plan with the plans' own values kept (it changed the active plan only, put "on"
        # back instead of the value before, and switched sleep off on the side without saying so)
        ps_command=_power_saved_ps("apply", "disable_usb_suspend", _USB_SUB, _USB_SS, 0),
        revert_cmd=_power_saved_ps("revert", "disable_usb_suspend", _USB_SUB, _USB_SS, 0),
    ),
    Tweak(
        id="power_pcie_aspm_off",
        name="PCIe Link State Power Management aus",
        desc="Deaktiviert das Energiesparen des PCIe-Links (ASPM) in allen Energieplänen, im Netzbetrieb. Der "
             "PCIe-Bus zur Grafikkarte bleibt dauerhaft auf voller Leistung statt in Sparzustände zu wechseln — "
             "minimal konsistentere Latenz, dafür etwas mehr Idle-Verbrauch. Zurücksetzen stellt den Wert jedes "
             "Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        # round 47 (found in v1): the revert wrote "maximum power savings" (2) — Windows' default is
        # "moderate" (1) in Balanced and "off" (0) in High performance
        ps_command=_power_saved_ps("apply", "power_pcie_aspm_off", _PCIE_SUB, _ASPM, 0),
        revert_cmd=_power_saved_ps("revert", "power_pcie_aspm_off", _PCIE_SUB, _ASPM, 0),
        risk="safe",
    ),
    Tweak(
        id="power_disk_never_sleep",
        name="Festplatte nie schlafen legen",
        desc="Verhindert, dass Windows Laufwerke nach Inaktivität abschaltet — in allen Energieplänen, im "
             "Netzbetrieb. Auf Systemen mit HDD(s) verhindert das Mikro-Ruckler, wenn ein Hintergrundprozess ein "
             "eingeschlafenes Laufwerk aufwecken muss. Zurücksetzen stellt den Wert jedes Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        ps_command=_power_saved_ps("apply", "power_disk_never_sleep", _DISK_SUB, _DISK_IDLE, 0),
        revert_cmd=_power_saved_ps("revert", "power_disk_never_sleep", _DISK_SUB, _DISK_IDLE, 0),
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # AUDIO
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_audio_enhancements",
        name="Disable Audio Enhancements",
        desc="Deaktiviert Windows Audio-Verbesserungen (Bass Boost, EQ etc.) auf allen "
             "Wiedergabegeräten — über die Windows-Audio-Schnittstelle wie in den Sound-Einstellungen. "
             "Reduziert Audio-Latenz und CPU-Last. Empfohlen für Gaming.",
        category="Audio", group="Latency",
        # Windows 11 locks the endpoint stores in the registry even for admins
        # (probe: access denied). Set through the audio API like the Sound
        # settings do: PKEY_AudioEndpoint_Disable_SysFx, 1 = disabled.
        ps_command=audio_policy.ps_sysfx(True),
        revert_cmd=audio_policy.ps_sysfx(False),
        risk="safe",
    ),

    Tweak(
        id="disable_audio_exclusive_lock",
        name="Disable Exclusive Audio Lock",
        desc="Verhindert, dass Spiele das Audiogerät exklusiv sperren und Discord/Spotify stumm machen "
             "(„Exklusiver Modus“ aus, über die Windows-Audio-Schnittstelle).",
        category="Audio", group="Latency",
        # Through the audio API as well (the registry store is locked).
        ps_command=audio_policy.ps_exclusive(False),
        revert_cmd=audio_policy.ps_exclusive(True),
        risk="safe",
    ),

    Tweak(
        id="disable_sound_scheme",
        name="Disable Windows Sound Scheme",
        desc="Schaltet alle Windows-Systemtoene aus (Startup, Error, Notifications). "
             "Verhindert Audio-Unterbrechungen beim Gaming.",
        category="Audio", group="System Sounds",
        ps_command=(
            "Set-ItemProperty -Path 'HKCU:\\AppEvents\\Schemes' -Name '(Default)' -Value '.None';"
            " Get-ChildItem 'HKCU:\\AppEvents\\Schemes\\Apps' -EA SilentlyContinue |"
            " ForEach-Object { Get-ChildItem $_.PSPath -EA SilentlyContinue |"
            " ForEach-Object { $cur = Join-Path $_.PSPath '.Current';"
            " if (Test-Path $cur) { Set-ItemProperty -Path $cur -Name '(Default)' -Value '' -EA SilentlyContinue } } }"
        ),
        revert_cmd="Set-ItemProperty -Path 'HKCU:\\AppEvents\\Schemes' -Name '(Default)' -Value '.Default'",
        risk="safe",
    ),

    Tweak(
        id="disable_nahimic",
        name="Disable Nahimic Audio Service",
        desc="Deaktiviert Nahimic Audio (vorinstalliert auf MSI-Boards/Gaming-Laptops). "
             "Verursacht CPU-Spikes und Audio-Artefakte. Sicher wenn nicht benoetigt.",
        category="Audio", group="System Sounds",
        ps_command=(
            "$svcs = @('NahimicService','A-Volute','nahimicSvc');"
            " $found = $false;"
            " foreach ($s in $svcs) {"
            " $svc = Get-Service -Name $s -EA SilentlyContinue;"
            " if ($svc) { $found = $true;"
            " Stop-Service -Name $s -Force -EA SilentlyContinue;"
            " Set-Service -Name $s -StartupType Disabled -EA SilentlyContinue } };"
            " if (-not $found) { Write-Output 'Nahimic not installed - nothing to do' };"
            " exit 0"
        ),
        revert_cmd=(
            "$svcs = @('NahimicService','A-Volute','nahimicSvc');"
            " foreach ($s in $svcs) {"
            " $svc = Get-Service -Name $s -EA SilentlyContinue;"
            " if ($svc) { Set-Service -Name $s -StartupType Automatic -EA SilentlyContinue } }"
        ),
        risk="safe",
    ),

    Tweak(
        id="disable_audio_ducking",
        name="Disable Audio Ducking (Communications)",
        desc="Verhindert dass Windows andere Toene bei Anrufen/Kommunikation leiser macht. "
             "Oft stoerend beim Gaming mit Discord waehrend andere Sounds gedaempft werden.",
        category="Audio", group="Performance",
        ps_command=(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Multimedia\\Audio'"
            " -Name 'UserDuckingPreference' -Value 3 -Type DWord"
        ),
        revert_cmd=(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Multimedia\\Audio'"
            " -Name 'UserDuckingPreference' -Value 0 -Type DWord"
        ),
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — CTT ESSENTIALS  (portiert aus GameOptimizerPro v1)
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="prevent_device_companion",
        name="Prevent Device Companion Apps",
        desc="Verhindert, dass Windows Geräte-Metadaten aus dem Netz lädt und automatisch Companion-Apps für angeschlossene Geräte installiert oder vorschlägt. Spart Hintergrund-Traffic und ungewollte App-Installationen.",
        category="Windows", group="CTT Essentials",
        ps_command=r"""$p='HKLM:\SOFTWARE\Policies\Microsoft\Windows\Device Metadata'; if(!(Test-Path $p)){New-Item -Path $p -Force|Out-Null}; Set-ItemProperty -Path $p -Name PreventDeviceMetadataFromNetwork -Value 1 -Type DWord""",
        revert_cmd=r"""Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Device Metadata' -Name PreventDeviceMetadataFromNetwork -EA SilentlyContinue""",
        tags=["privacy", "ctt"],
    ),
    Tweak(
        id="explorer_folder_discovery",
        name="Disable File Explorer Automatic Folder Discovery",
        desc="Setzt alle Ordner auf 'Allgemeine Elemente'. Der Explorer verschwendet keine Zeit mehr damit, "
             "Ordnertypen automatisch zu erkennen — große Ordner öffnen deutlich schneller. Achtung: Beim Anwenden "
             "gehen die gespeicherten Ansichten aller Ordner verloren (Sortierung, Spalten, Ansicht). Zurücksetzen "
             "nimmt nur die Vorgabe zurück — die Ansichten von vorher kommen nicht wieder. Abmelden/Neustart nötig.",
        category="Windows", group="CTT Essentials",
        ps_command=r"""$b='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags'; $m='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU'; Remove-Item -Path $b -Recurse -Force -EA SilentlyContinue; Remove-Item -Path $m -Recurse -Force -EA SilentlyContinue; $a='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell'; if(!(Test-Path $a)){New-Item -Path $a -Force|Out-Null}; Set-ItemProperty -Path $a -Name FolderType -Value 'NotSpecified' -Type String""",
        # round 47 (found in v1): the revert deleted every saved folder view a second time — now it only
        # takes back the default it set; views made since stay
        revert_cmd=r"""Remove-ItemProperty -Path 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell' -Name FolderType -EA SilentlyContinue; exit 0""",
        requires_reboot=True,
        risk="moderate",          # it wipes the saved folder views: not for "All safe tweaks"
        tags=["performance", "ctt"],
    ),
    Tweak(
        id="store_no_recommended",
        name="Disable Store Recommended Search Results",
        desc="Sperrt die store.db der Microsoft-Store-App per Dateiberechtigung. Der Store zeigt dann keine empfohlenen/gesponserten Suchergebnisse mehr. Vollständig reversibel.",
        category="Windows", group="CTT Essentials",
        ps_command=r"""$db="$env:LocalAppData\Packages\Microsoft.WindowsStore_8wekyb3d8bbwe\LocalState\store.db"; if(Test-Path $db){ icacls "$db" /deny "*S-1-1-0:F" 2>$null | Out-Null }""",
        revert_cmd=r"""$db="$env:LocalAppData\Packages\Microsoft.WindowsStore_8wekyb3d8bbwe\LocalState\store.db"; if(Test-Path $db){ icacls "$db" /remove:d "*S-1-1-0" 2>$null | Out-Null }""",
        risk="moderate",
        tags=["privacy", "ctt"],
    ),

    # ══════════════════════════════════════════════════════════════
    # NETWORK — ADAPTER  (portiert aus v1)
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="nic_power_saving",
        name="Disable Network Adapter Power Saving",
        desc="Deaktiviert 'Computer kann das Gerät ausschalten, um Energie zu sparen' für alle Netzwerkadapter. Verhindert Verbindungsabbrüche und Latenz-Spitzen durch Energiesparfunktionen des Adapters.",
        category="Network", group="Adapter",
        ps_command='$c=\'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}\'; $n=0; foreach($k in @(Get-ChildItem $c -EA SilentlyContinue | Where-Object { $_.PSChildName -match \'^\\d{4}$\' })){ if((Get-ItemProperty $k.PSPath -EA SilentlyContinue).NetCfgInstanceId){ Set-ItemProperty -Path $k.PSPath -Name PnPCapabilities -Value 24 -Type DWord -Force -EA SilentlyContinue; if($?){ $n++ } } }; if($n -gt 0){ Write-Output "Energiesparen aus für $n Netzwerkadapter / power saving off for $n network adapter(s)"; exit 0 } else { exit 1 }',
        revert_cmd="$c='HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}'; $n=0; foreach($k in @(Get-ChildItem $c -EA SilentlyContinue | Where-Object { $_.PSChildName -match '^\\d{4}$' })){ if((Get-ItemProperty $k.PSPath -EA SilentlyContinue).NetCfgInstanceId){ Remove-ItemProperty -Path $k.PSPath -Name PnPCapabilities -Force -EA SilentlyContinue; if($?){ $n++ } } }; exit 0",
        requires_reboot=True,
        tags=["latency", "network"],
    ),
    Tweak(
        id="disable_eee",
        name="Energy-Efficient Ethernet aus",
        desc="Schaltet Energy-Efficient Ethernet (EEE, 'Green Ethernet') an allen LAN-Adaptern ab, die es "
             "anbieten. Mit EEE geht die Leitung in Sendepausen in einen Stromsparzustand und muss für das "
             "nächste Paket erst aufwachen — das kann kleine Latenzspitzen geben. Am Desktop kostet das "
             "Abschalten praktisch nichts. Geändert wird nur, was der Treiber selbst anbietet; der Revert "
             "stellt den vorherigen Wert wieder her. Kein Verbindungsabbruch jetzt, wirkt nach einem Neustart.",
        category="Network", group="Adapter",
        ps_command=_nic_ps("apply", "EEE", NIC_EEE_KEYWORDS),
        revert_cmd=_nic_ps("revert", "EEE", NIC_EEE_KEYWORDS),
        requires_reboot=True,
        tags=["latency", "network"],
    ),
    Tweak(
        id="disable_interrupt_moderation",
        name="Interrupt Moderation aus",
        desc="Der LAN-Adapter meldet jedes Paket sofort, statt mehrere zu sammeln und gebündelt zu melden. "
             "Senkt die Netzwerk-Latenz um Bruchteile einer Millisekunde, erzeugt aber bei hohen "
             "Download-Raten deutlich mehr CPU-Last. Gedacht für Online-Spiele — wer oft große Dateien lädt "
             "oder streamt, lässt es besser an. Geändert wird nur, was der Treiber selbst anbietet; der "
             "Revert stellt den vorherigen Wert wieder her. Wirkt nach einem Neustart.",
        category="Network", group="Adapter",
        ps_command=_nic_ps("apply", "IM", NIC_IM_KEYWORDS),
        revert_cmd=_nic_ps("revert", "IM", NIC_IM_KEYWORDS),
        requires_reboot=True, risk="moderate",
        tags=["latency", "network"],
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — POWER PLAN  (portiert aus v1; schreibt in ALLE Schemata)
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="power_display_sleep_15",
        name="Display Sleep = 15 Minuten",
        desc="Setzt den Monitor-Schlaf-Timer auf 15 Minuten (Netz) und 5 Minuten (Akku) — in allen Plänen "
             "AUSSER 'Höchstleistung' und 'Ultimative Leistung': dort bleibt der Bildschirm im Netzbetrieb an. "
             "Zurücksetzen stellt die Werte jedes Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        # round 47 (found in v1): the revert wrote fixed values (10 / 2 min) instead of each plan's own
        ps_command=_power_saved_ps("apply", "power_display_sleep_15", _VIDEO_SUB, _VIDEO_IDLE, 900, 300,
                                   skip=_SKIP_PERF_PLANS),
        revert_cmd=_power_saved_ps("revert", "power_display_sleep_15", _VIDEO_SUB, _VIDEO_IDLE, 900, 300,
                                   skip=_SKIP_PERF_PLANS),
        tags=["power"],
    ),
    Tweak(
        id="power_sleep_off",
        name="System-Schlafmodus deaktivieren",
        desc="Deaktiviert den System-Schlafmodus komplett (alle Energiepläne, Netz und Akku). Der PC schläft nicht "
             "mehr nach Inaktivität ein — empfohlen für Desktops, die im Hintergrund weiterlaufen sollen (Downloads, "
             "Server). Zurücksetzen stellt die Werte jedes Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        # round 47 (found in v1): the revert wrote 60 / 30 min — Balanced's own is 30 / 15
        ps_command=_power_saved_ps("apply", "power_sleep_off", _SLEEP_SUB, _STANDBY_IDLE, 0, 0),
        revert_cmd=_power_saved_ps("revert", "power_sleep_off", _SLEEP_SUB, _STANDBY_IDLE, 0, 0),
        tags=["power"],
    ),
    Tweak(
        id="power_cpu_min_100",
        name="CPU Minimum Processor State = 100%",
        desc="Setzt den minimalen CPU-Zustand auf 100% (alle Energiepläne). Die CPU regelt nicht mehr herunter — "
             "das eliminiert die kurze Verzögerung beim Hochtakten aus dem Idle. Gut für konstante FPS, erhöht "
             "aber Idle-Verbrauch und Temperatur. Zurücksetzen stellt die Werte jedes Plans von vorher wieder her.",
        category="Windows", group="Power Plan",
        # round 47 (found in v1): the revert wrote 5 % everywhere — High performance's own minimum is 100 %
        ps_command=_power_saved_ps("apply", "power_cpu_min_100", _CPU_SUB, _CPU_MIN, 100, 100),
        revert_cmd=_power_saved_ps("revert", "power_cpu_min_100", _CPU_SUB, _CPU_MIN, 100, 100),
        risk="moderate",
        tags=["performance", "power"],
    ),
    Tweak(
        id="power_cpu_max_100",
        name="CPU Maximum Processor State = 100%",
        desc="Stellt sicher, dass Windows die CPU nie künstlich deckelt. Relevant auf Laptops und Systemen mit aggressiver Thermal-Policy. 100% ist zugleich der Windows-Standard — deshalb gibt es hier ehrlicherweise nichts zurückzusetzen.",
        category="Windows", group="Power Plan",
        ps_command=_power_all("SUB_PROCESSOR", "PROCTHROTTLEMAX", 100, 100),
        revert_cmd="",   # 100% IST der Windows-Default — ein "Revert" wäre derselbe Wert
        tags=["performance", "power"],
    ),

    # ══════════════════════════════════════════════════════════════
    # GAMING — AMD GPU  (portiert aus v1; greifen nur auf AMD-Systemen)
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="amd_disable_ulps",
        name="AMD: ULPS deaktivieren (Ultra Low Power State)",
        desc="Nur AMD: Deaktiviert Ultra Low Power State. ULPS versetzt inaktive GPUs in einen extremen Stromsparmodus und kann beim Aufwachen zu Stottern führen. Auch bei Single-GPU sinnvoll.",
        category="Gaming", group="AMD GPU",
        ps_command=_AMD_ULPS_APPLY,
        revert_cmd=_AMD_ULPS_REVERT,
        requires_amd=True, requires_reboot=True,
        tags=["gpu", "amd"],
    ),

    # ══════════════════════════════════════════════════════════════
    # v1-PARITÄT (portiert aus GameOptimizerPro v1, ehrlich geprüft)
    # + WINDOWS 11 26H2: KI-Funktionen & Bloat, die das Funktionsupdate bringt
    # ══════════════════════════════════════════════════════════════

    # ── Windows · Komfort ─────────────────────────────────────────────
    Tweak(
        id="enable_long_paths",
        name="Lange Pfade aktivieren (> 260 Zeichen)",
        desc="Erlaubt Dateipfade länger als 260 Zeichen. Verhindert 'Pfad zu lang'-Fehler bei tiefen "
             "Ordnerstrukturen, Game-Mods, Node-Projekten usw.",
        category="Windows", group="Komfort",
        ps_command=r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 0 /f',
        risk="safe",
    ),
    Tweak(
        id="numlock_on_startup",
        name="NumLock beim Start einschalten",
        desc="Schaltet NumLock beim Systemstart und am Anmeldebildschirm automatisch ein.",
        category="Windows", group="Komfort",
        ps_command=r'''
reg add "HKCU\Control Panel\Keyboard" /v InitialKeyboardIndicators /t REG_SZ /d 2147483650 /f | Out-Null
reg add "HKU\.DEFAULT\Control Panel\Keyboard" /v InitialKeyboardIndicators /t REG_SZ /d 2147483650 /f
''',
        revert_cmd=r'''
reg add "HKCU\Control Panel\Keyboard" /v InitialKeyboardIndicators /t REG_SZ /d 2147483648 /f | Out-Null
reg add "HKU\.DEFAULT\Control Panel\Keyboard" /v InitialKeyboardIndicators /t REG_SZ /d 2147483648 /f
''',
        risk="safe",
    ),
    Tweak(
        id="disable_lock_screen",
        name="Sperrbildschirm überspringen",
        desc="Beim Start/Aufwachen direkt zum Anmeldefeld statt erst zum Sperrbildschirm. Ehrlich: "
             "Microsoft garantiert diese Richtlinie nur für Enterprise/Education — auf Home/Pro wirkt "
             "sie je nach Build.",
        category="Windows", group="Komfort",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization" /v NoLockScreen /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization" /v NoLockScreen /f 2>$null; exit 0',
        risk="moderate",
    ),
    Tweak(
        id="run_disk_cleanup",
        name="Datenträgerbereinigung ausführen (einmalig)",
        desc="Räumt mit der Windows-Datenträgerbereinigung nur SICHERE Kategorien auf (Temp, Update-Reste, "
             "Fehlerberichte, Speicherabbilder, Übermittlungsoptimierung, Miniaturansichten …) und danach "
             "alte Update-Komponenten per DISM. Bewusst NICHT: Downloads-Ordner, Papierkorb, Windows.old "
             "(Rückkehr zum vorherigen Windows), Shader-Cache (sonst Nachruckler in Spielen), alte Treiber. "
             "Einmalige Aktion, dauert einige Minuten.",
        category="Windows", group="CTT Essentials",
        ps_command=_DISK_CLEANUP_PS,
        revert_cmd='',
        risk="moderate", timeout_s=1800,
    ),

    # ── Windows · Speicher & RAM ──────────────────────────────────────
    Tweak(
        id="disable_reserved_storage",
        name="Reservierten Speicher freigeben (~7 GB)",
        desc="Gibt den Speicher frei, den Windows für Updates reserviert (typisch ~7 GB). Windows "
             "verwaltet den Update-Platz danach dynamisch. Klappt nur, wenn gerade kein Update ansteht.",
        category="Windows", group="Speicher & RAM",
        ps_command='Set-WindowsReservedStorageState -State Disabled -ErrorAction Stop',
        revert_cmd='Set-WindowsReservedStorageState -State Enabled -ErrorAction Stop',
        risk="safe",
    ),
    Tweak(
        id="pagefile_system_managed",
        name="Auslagerungsdatei von Windows verwalten lassen",
        desc="Stellt die Auslagerungsdatei auf 'automatisch verwalten'. Windows passt die Größe an den "
             "Bedarf an — verhindert zu kleine (Abstürze bei RAM-Spitzen) und unnötig große Dateien. "
             "Entspricht dem Windows-Standard.",
        category="Windows", group="Speicher & RAM",
        ps_command=r'$cs = Get-CimInstance Win32_ComputerSystem; Set-CimInstance -InputObject $cs -Property @{AutomaticManagedPagefile=$true} -ErrorAction Stop',
        revert_cmd='',
        requires_reboot=True, risk="safe",
    ),
    Tweak(
        id="clear_pagefile_shutdown",
        name="Auslagerungsdatei beim Herunterfahren leeren",
        desc="Überschreibt die Auslagerungsdatei bei jedem Herunterfahren — keine Speicherreste bleiben "
             "auf der Platte (Datenschutz). Macht das Herunterfahren langsamer, bei großer Datei spürbar.",
        category="Windows", group="Speicher & RAM",
        ps_command=r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" /v ClearPageFileAtShutdown /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" /v ClearPageFileAtShutdown /t REG_DWORD /d 0 /f',
        requires_reboot=True, risk="moderate",
    ),
    Tweak(
        id="disable_memory_compression",
        name="Speicherkomprimierung deaktivieren",
        desc="Schaltet die RAM-Komprimierung ab und spart damit CPU-Zeit beim Spielen. Nur mit genug RAM "
             "sinnvoll (16 GB+) — sonst lagert Windows früher auf die Platte aus. (Ist SysMain deaktiviert, "
             "wird der Dienst dafür kurz gestartet und danach wieder deaktiviert.)",
        category="Windows", group="Speicher & RAM",
        ps_command="$s=Get-Service SysMain -EA SilentlyContinue; $was=$(if($s){ [string]$s.StartType } else { '' }); if($was -eq 'Disabled'){ Set-Service SysMain -StartupType Manual -EA SilentlyContinue; Start-Service SysMain -EA SilentlyContinue }; $err=$null; try { Disable-MMAgent -MemoryCompression -EA Stop } catch { $err=$_.Exception.Message }; if($was -eq 'Disabled'){ Stop-Service SysMain -Force -EA SilentlyContinue; Set-Service SysMain -StartupType Disabled -EA SilentlyContinue }; if($err){ Write-Output $err; exit 1 }; if($was -eq 'Disabled'){ Write-Output '" + _tr("SysMain kurz gestartet und wieder deaktiviert", "SysMain started briefly and disabled again") + "' }",
        revert_cmd="$s=Get-Service SysMain -EA SilentlyContinue; $was=$(if($s){ [string]$s.StartType } else { '' }); if($was -eq 'Disabled'){ Set-Service SysMain -StartupType Manual -EA SilentlyContinue; Start-Service SysMain -EA SilentlyContinue }; $err=$null; try { Enable-MMAgent -MemoryCompression -EA Stop } catch { $err=$_.Exception.Message }; if($was -eq 'Disabled'){ Stop-Service SysMain -Force -EA SilentlyContinue; Set-Service SysMain -StartupType Disabled -EA SilentlyContinue }; if($err){ Write-Output $err; exit 1 }; if($was -eq 'Disabled'){ Write-Output '" + _tr("SysMain kurz gestartet und wieder deaktiviert", "SysMain started briefly and disabled again") + "' }",
        requires_reboot=True, risk="moderate",
    ),
    Tweak(
        id="enable_ssd_trim",
        name="SSD-TRIM sicherstellen",
        desc="Stellt sicher, dass Windows SSDs über gelöschte Blöcke informiert (TRIM) — hält die "
             "SSD-Leistung langfristig hoch. Normalerweise schon aktiv; der Tweak prüft und erzwingt es.",
        category="Windows", group="Speicher & RAM",
        ps_command='fsutil behavior set DisableDeleteNotify 0',
        revert_cmd='',
        risk="safe",
    ),
    Tweak(
        id="disable_scheduled_defrag",
        name="Geplante Laufwerksoptimierung deaktivieren",
        desc="Deaktiviert die wöchentliche Laufwerksoptimierung. Ehrlich: Auf SSDs defragmentiert Windows "
             "nicht, sondern schickt nur ein erneutes TRIM — das entfällt dann (das TRIM beim Löschen "
             "bleibt). Nur sinnvoll, wenn du die Optimierung selbst steuern willst.",
        category="Windows", group="Speicher & RAM",
        ps_command=r'''
schtasks /Change /TN "\Microsoft\Windows\Defrag\ScheduledDefrag" /Disable | Out-Null
reg add "HKLM\SOFTWARE\Microsoft\Dfrg\BootOptimizeFunction" /v Enable /t REG_SZ /d N /f
''',
        revert_cmd=r'''
schtasks /Change /TN "\Microsoft\Windows\Defrag\ScheduledDefrag" /Enable | Out-Null
reg delete "HKLM\SOFTWARE\Microsoft\Dfrg\BootOptimizeFunction" /v Enable /f 2>$null
exit 0
''',
        risk="moderate",
    ),
    Tweak(
        id="disable_write_cache_flush",
        name="Schreibcache-Leerung deaktivieren (nur Desktop + USV)",
        desc="Wie das Häkchen 'Leeren des Windows-Schreibcachepuffers deaktivieren' im Gerätemanager: "
             "schnelleres Schreiben, aber bei Stromausfall oder Absturz drohen Datenverlust und "
             "Dateisystemfehler. Nur für Desktop-PCs mit stabiler Stromversorgung (am besten USV). "
             "(v1 hatte hier den falschen Registry-Wert gesetzt.)",
        category="Windows", group="Speicher & RAM",
        ps_command=_WCACHE_APPLY,
        revert_cmd=_WCACHE_REVERT,
        requires_reboot=True, risk="advanced",
    ),

    # ── Windows 11 ────────────────────────────────────────────────────
    Tweak(
        id="w11_hide_recommended",
        name="Win11: 'Empfohlen' im Startmenü ausblenden",
        desc="Blendet den Bereich 'Empfohlen' im Startmenü per Richtlinie aus — die gilt laut Microsoft nur "
             "für Education/SE. Damit er auch auf Home und Pro leer bleibt, zusätzlich aus: zuletzt geöffnete "
             "Dateien (auch im Explorer-Start und in den Sprunglisten der Taskleiste) und Tipps/App-"
             "Empfehlungen im Start. Der Revert stellt deine vorherigen Einstellungen wieder her.",
        category="Windows", group="Windows 11",
        ps_command=(r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v HideRecommendedSection /t REG_DWORD /d 1 /f | Out-Null; '
                    + _reg_saved_ps("apply", "RECO", RECO_ITEMS)),
        revert_cmd=(r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v HideRecommendedSection /f 2>$null | Out-Null; '
                    + _reg_saved_ps("revert", "RECO", RECO_ITEMS)),
        risk="safe",
    ),

    # ── Windows · Privacy: KI-Funktionen (Windows 11 24H2–26H2) ───────
    Tweak(
        id="disable_click_to_do",
        name="Click to Do deaktivieren (KI-Bildschirmanalyse)",
        desc="Schaltet 'Click to Do' ab — die Funktion macht auf Tastendruck einen Screenshot und lässt "
             "ihn von einer KI analysieren, um Aktionen vorzuschlagen. Offizielle Windows-KI-Richtlinie "
             "(auch für Pro dokumentiert), für Computer und Benutzer.",
        category="Windows", group="Privacy",
        ps_command=r'''
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableClickToDo /t REG_DWORD /d 1 /f | Out-Null
reg add "HKCU\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableClickToDo /t REG_DWORD /d 1 /f
''',
        revert_cmd=r'''
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableClickToDo /f 2>$null
reg delete "HKCU\SOFTWARE\Policies\Microsoft\Windows\WindowsAI" /v DisableClickToDo /f 2>$null
exit 0
''',
        risk="safe",
    ),
    Tweak(
        id="disable_paint_ai",
        name="Paint-KI deaktivieren",
        desc="Schaltet die KI-Funktionen in Paint per offizieller Richtlinie ab: Cocreator, Image Creator und "
             "generatives Füllen. Für generatives Löschen und Hintergrund entfernen gibt es keine Richtlinie.",
        category="Windows", group="Privacy",
        ps_command=_PAINT_AI_APPLY,
        revert_cmd=_PAINT_AI_REVERT,
        risk="safe",
    ),
    Tweak(
        id="disable_notepad_ai",
        name="Notepad-KI deaktivieren",
        desc="Schaltet die Copilot-Funktionen in Notepad (Umschreiben, Zusammenfassen, Schreiben) per "
             "offizieller Richtlinie ab.",
        category="Windows", group="Privacy",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\WindowsNotepad" /v DisableAIFeatures /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\WindowsNotepad" /v DisableAIFeatures /f 2>$null; exit 0',
        risk="safe",
    ),
    Tweak(
        id="disable_ai_fabric_service",
        name="Windows-KI-Dienst abschalten (WSAIFabricSvc)",
        desc="Deaktiviert den 'Host für Windows KI-Komponenten'. Er startet seit 24H2/26H2 automatisch "
             "und stellt lokale KI-Modelle bereit (KI-Suche in den Einstellungen, Click to Do, "
             "KI-Aktionen). Spart RAM und CPU im Hintergrund; diese KI-Funktionen sind danach aus. "
             "Rückgängig machbar.",
        category="Windows", group="Privacy",
        ps_command=r'''
Stop-Service -Name WSAIFabricSvc -Force -ErrorAction SilentlyContinue
Set-Service -Name WSAIFabricSvc -StartupType Disabled -ErrorAction Stop
''',
        revert_cmd=r'''
Set-Service -Name WSAIFabricSvc -StartupType Automatic -ErrorAction Stop
Start-Service -Name WSAIFabricSvc -ErrorAction SilentlyContinue
''',
        risk="moderate",
    ),
    Tweak(
        id="remove_m365_copilot_devhome",
        name="Microsoft-365-Copilot-App & Dev Home entfernen",
        desc="Entfernt die 'Microsoft 365 Copilot'-App (Office Hub) und das von Microsoft eingestellte "
             "Dev Home — Funktionsupdates wie 26H2 installieren beide neu. Entfernt auch die "
             "bereitgestellten Pakete, damit sie für neue Benutzer nicht wiederkommen. Office im "
             "Browser bleibt nutzbar.",
        category="Windows", group="Bloatware",
        ps_command=_remove_apps_ps(["*Microsoft.MicrosoftOfficeHub*", "*Microsoft.Windows.DevHome*"]),
        risk="safe",
    ),

    # ── Network · TCP ─────────────────────────────────────────────────

    # ── Audio ─────────────────────────────────────────────────────────
    Tweak(
        id="mmcss_audio_profile",
        name="MMCSS-Audioprofil optimieren",
        desc="Setzt den MMCSS-Task 'Audio' auf latenzempfindlich mit hoher Scheduling-Priorität — weniger "
             "Knacken und Aussetzer unter CPU-Last.",
        category="Audio", group="Performance",
        # "SFIO Priority" is "not used" (Microsoft Learn, MMCSS) — no longer set; revert normalizes it
        ps_command=r'''
$p='HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio'
reg add $p /v "Latency Sensitive" /t REG_SZ /d True /f | Out-Null
reg add $p /v "Scheduling Category" /t REG_SZ /d High /f
''',
        revert_cmd=r'''
$p='HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio'
reg delete $p /v "Latency Sensitive" /f 2>$null | Out-Null
reg add $p /v "Scheduling Category" /t REG_SZ /d Medium /f | Out-Null
reg add $p /v "SFIO Priority" /t REG_SZ /d Normal /f
''',
        risk="safe",
    ),
    Tweak(
        id="audio_service_priority",
        name="Audio-Priorität systemweit erhöhen",
        desc="Setzt SystemResponsiveness auf 10 — MMCSS hält nur noch 10 % statt 20 % CPU-Zeit für "
             "Hintergrundaufgaben frei, Audio und Spiele bekommen mehr. Gegen Aussetzer bei Spielen + "
             "Streamen. Ehrlich: 10 ist das Minimum — Werte darunter (oft empfohlen: 0) behandelt Windows "
             "laut Microsoft wie den Standard 20. (Den Wert nutzt auch 'Network Throttling Index' — "
             "zurückgesetzt wird er erst, wenn keiner der beiden Tweaks ihn mehr braucht.)",
        category="Audio", group="Performance",
        ps_command=r'''
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 10 /f | Out-Null
reg add "HKLM\SOFTWARE\GameOptimizerPro" /v SR_AudioPriority /t REG_DWORD /d 1 /f
''',
        revert_cmd=_SR_AUDIO_REVERT,
        risk="safe",
    ),

    # ══════════════════════════════════════════════════════════════
    # ROUND 45 — checked against Windows 11 26H2 (each value is still read there)
    # and Microsoft's edition tables (Pro-only policies are hidden on Home)
    # ══════════════════════════════════════════════════════════════

    # ── Windows · Privacy ─────────────────────────────────────────────
    Tweak(
        id="disable_tips_suggestions",
        name="Tipps, Vorschläge & Werbung in Windows aus",
        desc="Schaltet die eingebaute Werbung von Windows ab: 'Tipps und Vorschläge', die Willkommensseite nach "
             "Updates, 'Gerät fertig einrichten'-Hinweise, vorgeschlagene Inhalte in den Einstellungen, Tipps "
             "und Fun Facts auf dem Sperrbildschirm (die Spotlight-Bilder bleiben), Konto-Hinweise im Start und "
             "in den Einstellungen sowie die OneDrive-Werbung im Explorer. Alles Schalter, die Windows selbst "
             "anbietet (Home und Pro); der Revert stellt deine vorherigen Werte wieder her.",
        category="Windows", group="Privacy",
        ps_command=_reg_saved_ps("apply", "TIPS", TIPS_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "TIPS", TIPS_ITEMS),
        risk="safe",
    ),
    Tweak(
        id="disable_input_speech_data",
        name="Tipp-, Freihand- & Sprachdaten nicht senden",
        desc="Schaltet die Datenschutz-Schalter rund um Eingabe und Sprache ab: persönliches Freihand- und "
             "Eingabewörterbuch (Windows sammelt dafür, was du tippst und schreibst), 'Freihand- und "
             "Eingabeerkennung verbessern', Online-Spracherkennung, 'Maßgeschneiderte Erfahrungen' mit "
             "Diagnosedaten, Feedback-Anfragen, die Sprachliste für Websites und das Verfolgen von "
             "App-Starts (Start zeigt dann keine 'Meistverwendet'-Liste mehr). Der Revert stellt deine "
             "vorherigen Werte wieder her.",
        category="Windows", group="Privacy",
        ps_command=_reg_saved_ps("apply", "INPUT", INPUT_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "INPUT", INPUT_ITEMS),
        risk="safe",
    ),
    Tweak(
        id="onedrive_block_kfm",
        name="OneDrive: Ordner nicht in die Cloud verschieben",
        desc="Verhindert, dass OneDrive Desktop, Dokumente und Bilder in die Cloud verschiebt ('Ordner "
             "sichern') — und fragt auch nicht mehr danach. Offizielle OneDrive-Richtlinie, gilt für jedes "
             "Konto inkl. privatem Microsoft-Konto. Liegen die Ordner schon in OneDrive, bricht der Tweak ab "
             "und sagt, wie du sie zuerst zurückholst (sonst wäre genau dieser Knopf gesperrt). Ohne "
             "OneDrive wirkungslos.",
        category="Windows", group="Privacy",
        ps_command=_KFM_APPLY,
        revert_cmd=r"reg delete 'HKLM\SOFTWARE\Policies\Microsoft\OneDrive' /v KFMBlockOptIn /f 2>$null | Out-Null; exit 0",
        risk="safe",
    ),
    Tweak(
        id="disable_remote_assistance",
        name="Remoteunterstützung deaktivieren",
        desc="Schaltet die alte Windows-Remoteunterstützung ab (Systemeigenschaften → Remote): niemand kann "
             "darüber eine Hilfe-Sitzung auf diesen PC aufbauen. Wird praktisch nur noch in Firmennetzen "
             "genutzt; Schnellhilfe, TeamViewer & Co. sind nicht betroffen. Weniger Angriffsfläche. Der "
             "Revert stellt die vorherigen Werte wieder her.",
        category="Windows", group="Privacy",
        ps_command=_reg_saved_ps("apply", "RA", REMOTE_ASSIST_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "RA", REMOTE_ASSIST_ITEMS),
        risk="safe",
    ),

    # ── Windows · Updates (Pro / Enterprise / Education) ─────────────
    Tweak(
        id="exclude_wu_drivers",
        name="Keine Treiber über Windows Update",
        desc="Windows Update installiert mit den monatlichen Updates keine Treiber mehr (offizielle "
             "Richtlinie). Schützt den selbst installierten Grafiktreiber davor, durch eine ältere oder "
             "generische Version ersetzt zu werden. Dafür kommen auch für Chipsatz, WLAN, Bluetooth & Co. "
             "keine Treiber mehr über Windows Update — die dann beim Hersteller holen. Nur Pro, Enterprise "
             "und Education (Windows Home beachtet die Richtlinie nicht, dort ausgeblendet).",
        category="Windows", group="Updates",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" /v ExcludeWUDriversInQualityUpdate /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" /v ExcludeWUDriversInQualityUpdate /f 2>$null; exit 0',
        risk="moderate",
    ),
    Tweak(
        id="wu_pin_feature_version",
        name="Auf dieser Windows-Version bleiben",
        desc="Hält Windows auf der installierten Version (z. B. 26H2): Funktionsupdates, die Apps neu "
             "installieren und Einstellungen zurücksetzen können, kommen erst, wenn du das wieder aufhebst. "
             "Sicherheits- und Qualitätsupdates kommen weiter. Offizielle Richtlinie, nur Pro, Enterprise und "
             "Education (Home: ausgeblendet). Vor dem Supportende der Version zurücksetzen — danach gäbe es "
             "keine Sicherheitsupdates mehr.",
        category="Windows", group="Updates",
        ps_command=_PIN_APPLY,
        revert_cmd=_PIN_REVERT,
        risk="moderate",
    ),
    Tweak(
        id="disable_background_apps",
        name="Store-Apps nicht im Hintergrund laufen lassen",
        desc="Offizielle Richtlinie 'Windows-Apps im Hintergrund ausführen: verweigern': Store-Apps "
             "(Smartphone-Link, Mail und Kalender, Wetter …) laufen nur noch, solange sie offen sind — spart "
             "RAM und Hintergrund-CPU. Danach melden sich solche Apps im geschlossenen Zustand nicht mehr, "
             "z. B. WhatsApp aus dem Store. Normale Programme (Steam, Discord, Afterburner) sind nicht "
             "betroffen. Nur Pro, Enterprise und Education (Home: ausgeblendet). Dasselbe nur für deinen "
             "Benutzer, auf jeder Edition: „Hintergrund-Apps stoppen (alle Editionen)“ — einer von beiden reicht.",
        category="Windows", group="Performance",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsRunInBackground /t REG_DWORD /d 2 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsRunInBackground /f 2>$null; exit 0',
        risk="moderate",
    ),

    # ── Windows · Power Plan ──────────────────────────────────────────
    Tweak(
        id="usb3_link_power_off",
        name="USB 3: Link-Energiesparen aus",
        desc="Schaltet das Energiesparen der USB-3-Verbindung im Netzbetrieb ab (versteckte Energieoption "
             "'USB 3 Link Power Management', Windows-Standard: mittlere Einsparung). Der Link bleibt wach — "
             "gegen kurze Aussetzer und verzögertes Aufwachen von USB-3-Geräten wie Headset, DAC, "
             "Capture-Karte oder externer SSD. Etwas mehr Stromverbrauch. Gilt für jeden Energieplan; der "
             "Revert stellt die vorherigen Werte wieder her. Ergänzt 'USB Selective Suspend' (das betrifft die "
             "Geräte, nicht den Link).",
        category="Windows", group="Power Plan",
        ps_command=_power_saved_ps("apply", "USB3LPM", _USB_SUB, _USB3_LPM, 0),
        revert_cmd=_power_saved_ps("revert", "USB3LPM", _USB_SUB, _USB3_LPM, 0),
        risk="safe",
    ),
    Tweak(
        id="disable_wake_timers",
        name="Weck-Timer deaktivieren",
        desc="Geplante Aufgaben (Update-Neustarts, Wartung) wecken den PC nicht mehr aus dem Energiesparmodus "
             "(Energieoption 'Zeitgeber zur Aktivierung zulassen' im Netzbetrieb; Windows-Standard: an). Ein "
             "schlafender PC bleibt nachts aus; Updates installieren sich, wenn er an ist. Gilt für jeden "
             "Energieplan; der Revert stellt die vorherigen Werte wieder her.",
        category="Windows", group="Power Plan",
        ps_command=_power_saved_ps("apply", "RTCWAKE", _SLEEP_SUB, _RTC_WAKE, 0),
        revert_cmd=_power_saved_ps("revert", "RTCWAKE", _SLEEP_SUB, _RTC_WAKE, 0),
        risk="safe",
    ),

    # ── Windows · Komfort / Mouse & UI ───────────────────────────────
    Tweak(
        id="startup_delay_off",
        name="Autostart-Programme ohne Verzögerung",
        desc="Windows startet Autostart-Programme (Run-Einträge und Autostart-Ordner) erst einige Sekunden "
             "nach der Anmeldung. Ohne die Verzögerung sind Discord & Co. sofort da; bei sehr vielen "
             "Autostarts wirkt die Anmeldung dafür kurz zäher. Programme mit eigener Aufgabe (z. B. "
             "Afterburner) betrifft das nicht.",
        category="Windows", group="Komfort",
        ps_command=r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" /v StartupDelayInMSec /t REG_DWORD /d 0 /f',
        revert_cmd=r'reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" /v StartupDelayInMSec /f 2>$null; exit 0',
        risk="safe",
    ),
    Tweak(
        id="explorer_open_this_pc",
        name="Explorer öffnet 'Dieser PC'",
        desc="Der Explorer startet mit 'Dieser PC' (Laufwerke und Ordner) statt mit 'Start' und den zuletzt "
             "verwendeten Dateien. Geschmackssache; zählt nicht zum Score.",
        category="Windows", group="Mouse & UI",
        ps_command=_reg_saved_ps("apply", "LAUNCHTO", LAUNCHTO_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "LAUNCHTO", LAUNCHTO_ITEMS),
        risk="safe",
    ),
    Tweak(
        id="alt_tab_windows_only",
        name="Alt+Tab ohne Browser-Tabs",
        desc="Alt+Tab und das Andocken zeigen nur noch Fenster, keine einzelnen Edge-Tabs (Einstellungen → "
             "System → Multitasking). Aus dem Spiel heraus ist man so schneller beim richtigen Fenster. Wirkt "
             "nach dem Abmelden. Geschmackssache; zählt nicht zum Score.",
        category="Windows", group="Mouse & UI",
        ps_command=_reg_saved_ps("apply", "ALTTAB", ALTTAB_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "ALTTAB", ALTTAB_ITEMS),
        risk="safe",
    ),
    Tweak(
        id="disable_dynamic_lighting",
        name="Dynamic Lighting aus (RGB-Steuerung durch Windows)",
        desc="Schaltet 'Dynamische Beleuchtung' ab (Einstellungen → Personalisierung): Windows steuert die "
             "RGB-Beleuchtung von Tastatur, Maus & Co. nicht mehr — gegen Konflikte mit der Hersteller-Software "
             "(iCUE, G HUB, Armoury Crate, SignalRGB …), die sonst flackern oder ihre Effekte verlieren kann. "
             "Wer die Beleuchtung über Windows steuert, lässt es an. Wirkt spätestens nach dem Abmelden; "
             "zählt nicht zum Score.",
        category="Windows", group="Mouse & UI",
        ps_command=_reg_saved_ps("apply", "LIGHT", LIGHTING_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "LIGHT", LIGHTING_ITEMS),
        risk="safe",
    ),

    # ── Gaming ────────────────────────────────────────────────────────
    Tweak(
        id="controller_no_game_bar",
        name="Xbox-Taste öffnet keine Game Bar",
        desc="Die Xbox-/Guide-Taste am Controller öffnet nicht mehr die Game Bar — sie reißt einen so nicht "
             "mehr aus dem Spiel oder aus Steam Big Picture (Einstellungen → Gaming → Game Bar). Der Revert "
             "stellt den vorherigen Wert wieder her.",
        category="Gaming", group="In-Game Boosts",
        ps_command=_reg_saved_ps("apply", "NEXUS", NEXUS_ITEMS),
        revert_cmd=_reg_saved_ps("revert", "NEXUS", NEXUS_ITEMS),
        risk="safe",
    ),
]


# ── Either-or choices ───────────────────────────────────────────────────────
# Only ONE tweak of each group can be in effect — applying one replaces the
# others (the last one wins; "select all" once applied Cloudflare AND Google DNS,
# and ticked all three power plans). The first entry is the one the presets use.
EXCLUSIVE_GROUPS: list[tuple[str, ...]] = [
    ("ultimate_performance", "power_high", "power_balanced"),   # power plan
    ("dns_cloudflare", "dns_google"),                           # DNS provider
]


def alternatives_of(tweak_id: str) -> list[str]:
    """The other members of `tweak_id`'s either-or group(s)."""
    out: list[str] = []
    for group in EXCLUSIVE_GROUPS:
        if tweak_id in group:
            out += [t for t in group if t != tweak_id and t not in out]
    return out


def resolve_selection(ids, applied=()) -> list[str]:
    """A selection without contradictions (order kept): per either-or group the
    member that is already applied, else the first selected one in group order."""
    ids = list(dict.fromkeys(ids))
    chosen = set(ids)
    applied = set(applied)
    for group in EXCLUSIVE_GROUPS:
        members = [t for t in group if t in chosen]
        if len(members) > 1:
            keep = next((t for t in members if t in applied), members[0])
            chosen -= set(members) - {keep}
    return [t for t in ids if t in chosen]


def get_by_category(category: str) -> list[Tweak]:
    return [t for t in ALL_TWEAKS if t.category == category]

def get_by_group(category: str, group: str) -> list[Tweak]:
    return [t for t in ALL_TWEAKS if t.category == category and t.group == group]

def get_groups(category: str) -> list[str]:
    seen, groups = set(), []
    for t in ALL_TWEAKS:
        if t.category == category and t.group not in seen:
            seen.add(t.group)
            groups.append(t.group)
    return groups

# Windows 11 only (v1 greys them out on Windows 10): taskbar, Start and Explorer settings that exist
# only in Windows 11 — on Windows 10 they write values nothing reads. Hidden there like the
# tweaks for another GPU.
WIN11_ONLY = {"w11_classic_context_menu", "w11_taskbar_left", "w11_disable_widgets", "w11_disable_snap_suggest",
              "w11_hide_recommended", "end_task_right_click", "disable_dynamic_lighting"}
# Policies Microsoft documents for Pro, Enterprise and Education only (Policy CSP edition tables) —
# Windows Home ignores them, so they are hidden there.
PRO_ONLY = {"exclude_wu_drivers", "wu_pin_feature_version", "disable_background_apps"}
for _t in ALL_TWEAKS:
    if _t.id in WIN11_ONLY:
        _t.requires_win11 = True
    if _t.id in PRO_ONLY:
        _t.requires_pro = True


# Tweaks taken out because Windows 11 24H2+ no longer has what they changed: Cortana is gone, Teams
# (personal) is no longer preinstalled and its registry key belongs to TrustedInstaller (administrators
# may only read it — the old tweak wrote nothing and still reported success), the taskbar Chat button
# does not exist any more. An applied-state entry of one of them is ignored everywhere (no Tweak for the
# id); "Revert all" removes what the old tweak left behind — only the value it set — and forgets it.
# id -> (name DE, name EN, PowerShell cleanup or "" when nothing is left)
RETIRED_TWEAKS: dict[str, tuple[str, str, str]] = {
    "remove_cortana": ("Cortana entfernen", "Remove Cortana", ""),        # an app removal: nothing to undo
    "remove_teams": (
        "Microsoft Teams (privat) entfernen", "Remove Microsoft Teams (Personal)",
        "$k='HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications'; "
        "if((Get-ItemProperty $k -Name ConfigureChatAutoInstall -EA SilentlyContinue).ConfigureChatAutoInstall -eq 0)"
        "{ Remove-ItemProperty $k -Name ConfigureChatAutoInstall -EA SilentlyContinue }; exit 0"),
    "w11_remove_chat_icon": (
        "Win11: Chat-Symbol aus der Taskleiste", "Win11: Chat icon off the taskbar",
        "$k='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced'; "
        "if((Get-ItemProperty $k -Name TaskbarMn -EA SilentlyContinue).TaskbarMn -eq 0)"
        "{ Remove-ItemProperty $k -Name TaskbarMn -EA SilentlyContinue }; exit 0"),
    # round 45, found by tools/windows_watch.py --scan: they never did anything.
    # NVTweak\NVLatency is in no file of the NVIDIA driver (NVTweak itself is) — the low-latency mode lives
    # in the driver profile (NVIDIA app → Graphics → Low Latency Mode, or Reflex in the game).
    "nvidia_low_latency": (
        "NVIDIA Low Latency Mode (Reflex)", "NVIDIA Low Latency Mode (Reflex)",
        "$p='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak'; "
        "if((Get-ItemProperty $p -Name NVLatency -EA SilentlyContinue).NVLatency -eq 1)"
        "{ Remove-ItemProperty $p -Name NVLatency -EA SilentlyContinue }; exit 0"),
    # MMCSS "Pro Audio" already has the category High (so Priority "is always treated as 2"), SFIO Priority
    # "is not used" (Microsoft Learn) — the tweak changed nothing that Windows reads.
    "set_mmcss_audio": (
        "MMCSS Audio Priority (Pro Audio)", "MMCSS Audio Priority (Pro Audio)",
        "$p='HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Pro Audio'; "
        "$k=Get-ItemProperty $p -EA SilentlyContinue; if($k){ "
        "if($k.Priority -eq 6){ Set-ItemProperty $p -Name Priority -Value 1 -Type DWord }; "
        "if($k.'SFIO Priority' -eq 'High'){ Set-ItemProperty $p -Name 'SFIO Priority' -Value 'Normal' -Type String } }; exit 0"),
    # round 47 — checked again with v1's review: no documented effect, retired in both versions. Each
    # clean-up only removes the value the tweak itself wrote.
    # StorPort QueueDepth / DevicePriority: nothing documents a gain for NVMe (StorNVMe manages its own queues)
    "nvme_queue_depth": (
        "NVMe: Queue-Tiefe & Interrupt-Priorität", "NVMe: queue depth & interrupt priority",
        _NVME_DISKS_PS +
        "foreach($d in $nv){ $b='HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\'+$d.PNPDeviceID+'\\Device Parameters'; "
        "if((Get-ItemProperty ($b+'\\StorPort') -Name QueueDepth -EA SilentlyContinue).QueueDepth -eq 32)"
        "{ Remove-ItemProperty ($b+'\\StorPort') -Name QueueDepth -EA SilentlyContinue }; "
        "if((Get-ItemProperty ($b+'\\Interrupt Management\\Affinity Policy') -Name DevicePriority -EA SilentlyContinue).DevicePriority -eq 2)"
        "{ Remove-ItemProperty ($b+'\\Interrupt Management\\Affinity Policy') -Name DevicePriority -EA SilentlyContinue } }; "
        "Remove-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\stornvme\\Parameters\\Device' "
        "-Name IdlePowerEnabled -EA SilentlyContinue; exit 0"),
    # ECN and TCP timestamps are already off in Windows' own TCP settings — it changed nothing
    "tcp_optimize": (
        "TCP optimieren (ECN & Timestamps aus)", "Optimize TCP (ECN & timestamps off)",
        "netsh int tcp set global ecncapability=default | Out-Null; netsh int tcp set global timestamps=default | Out-Null; "
        "Remove-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters' -Name SackOpts,TcpMaxDupAcks "
        "-EA SilentlyContinue; exit 0"),
    # the 20 % reserve only applies when a QoS application reserves bandwidth — nothing measurable
    "disable_qos_limit": (
        "QoS-Bandbreitenreserve auf 0 %", "QoS bandwidth reserve to 0 %",
        "$p='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Psched'; "
        "if((Get-ItemProperty $p -Name NonBestEffortLimit -EA SilentlyContinue).NonBestEffortLimit -eq 0)"
        "{ Remove-ItemProperty $p -Name NonBestEffortLimit -EA SilentlyContinue }; exit 0"),
    # driver values AMD documents nowhere (Anti-Lag and the shader cache are set in the AMD software)
    "amd_shader_cache": (
        "AMD: Shader-Cache unbegrenzt", "AMD: unlimited shader cache",
        "$p='HKLM:\\SOFTWARE\\ATI Technologies\\CBT'; "
        "if((Get-ItemProperty $p -Name ShaderCacheSizePC -EA SilentlyContinue).ShaderCacheSizePC -eq 4294967295)"
        "{ Remove-ItemProperty $p -Name ShaderCacheSizePC -EA SilentlyContinue }; " + _AMD_KEYS_PS +
        "foreach($k in $amd){ if((Get-ItemProperty $k.PSPath -Name KMD_EnableComputePreemption -EA SilentlyContinue)"
        ".KMD_EnableComputePreemption -eq 0){ Remove-ItemProperty $k.PSPath -Name KMD_EnableComputePreemption -EA SilentlyContinue } }; exit 0"),
    "amd_antilag": (
        "AMD: Anti-Lag (Low Latency Mode)", "AMD: Anti-Lag (low latency mode)",
        _AMD_KEYS_PS + "foreach($k in $amd){ if((Get-ItemProperty $k.PSPath -Name EnableAntiLag -EA SilentlyContinue)"
        ".EnableAntiLag -eq 1){ Remove-ItemProperty $k.PSPath -Name EnableAntiLag -EA SilentlyContinue } }; exit 0"),
    # round 49: none of its nine names is a Windows 11 diagnostic endpoint (Microsoft Learn lists
    # v10.events / v10c.events / self.events / watson.events.data.microsoft.com — a hosts line blocks one exact
    # name only), and Microsoft Defender reports such entries as SettingsModifier:Win32/HostsFileHijack and
    # resets the WHOLE hosts file when it cleans it (own entries too). The documented way stays: the
    # diagnostic-data policy (Disable Telemetry). The clean-up removes only the nine lines it wrote — also
    # one glued to the end of the line before it (it appended without a line break) — and nothing else.
    "block_telemetry_hosts": (
        "Telemetrie-Hosts blockieren (hosts-Datei)", "Block Telemetry Hosts (hosts file)",
        "$f=\"$env:SystemRoot\\System32\\drivers\\etc\\hosts\"; "
        "$ours=@('0.0.0.0 telemetry.microsoft.com','0.0.0.0 vortex.data.microsoft.com',"
        "'0.0.0.0 vortex-win.data.microsoft.com','0.0.0.0 telecommand.telemetry.microsoft.com',"
        "'0.0.0.0 oca.telemetry.microsoft.com','0.0.0.0 sqm.telemetry.microsoft.com',"
        "'0.0.0.0 watson.telemetry.microsoft.com','0.0.0.0 redir.metaservices.microsoft.com',"
        "'0.0.0.0 df.telemetry.microsoft.com'); "
        "if(-not (Test-Path -LiteralPath $f)){ exit 0 }; "
        "try { $l=@(Get-Content -LiteralPath $f -EA Stop) } catch { Write-Output $_.Exception.Message; exit 1 }; "
        "$n=0; $keep=foreach($x in $l){ $t=\"$x\".Trim(); if($ours -contains $t){ $n++; continue }; "
        "foreach($e in $ours){ if($t.Length -gt $e.Length -and $t.EndsWith($e)){ $x=$t.Substring(0,$t.Length-$e.Length); $n++; break } }; $x }; "
        "if($n -eq 0){ exit 0 }; "
        "try { Set-Content -LiteralPath $f -Value @($keep) -EA Stop } catch { Write-Output $_.Exception.Message; exit 1 }; exit 0"),
    # a feature override current Windows 11 builds no longer know — the check showed "active" anyway
    "start_menu_previous_layout": (
        "Startmenü: vorheriges Layout", "Enable Start Menu Previous Layout",
        "$p='HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FeatureManagement\\Overrides\\8\\3036241548'; "
        "if((Get-ItemProperty $p -Name EnabledState -EA SilentlyContinue).EnabledState -eq 1)"
        "{ Remove-ItemProperty $p -Name EnabledState -EA SilentlyContinue }; exit 0"),
}


def get_categories() -> list[str]:
    seen, cats = set(), []
    for t in ALL_TWEAKS:
        if t.category not in seen:
            seen.add(t.category)
            cats.append(t.category)
    return cats

def get_by_id(tweak_id: str) -> Tweak | None:
    for t in ALL_TWEAKS:
        if t.id == tweak_id:
            return t
    return None
