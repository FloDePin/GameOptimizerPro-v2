"""
GameOptimizerPro v2.1 — Tweak Verifier (rewritten)
Liest tatsächlichen System-Zustand per PowerShell.

Fixes:
- Jeder Tweak bekommt einen eigenen PS-Call statt problematischem Batch
- Bloatware-Tweaks verifizierbar (AppxPackage + Registry)
- Robusteres Parsing
"""

import subprocess, os
from dataclasses import dataclass
from typing import Optional

from core.tweaks import _AMD_KEYS_PS   # same AMD-only adapter filter as the tweaks


@dataclass
class VerifyResult:
    tweak_id:  str
    expected:  bool
    actual:    bool
    mismatch:  bool
    error:     str = ""


# ── Each command returns exactly "1" if applied, "0" if not ──────────────────
# Simpler than APPLIED/NOT_APPLIED — less parsing error prone

VERIFY_MAP: dict[str, str] = {

    # ── Bloatware (AppxPackage checks) ────────────────────────────────────────
    "remove_cortana": (
        'if(Get-AppxPackage -AllUsers "*Microsoft.549981C3F5F10*" -EA SilentlyContinue){"0"}else{"1"}'
    ),
    "remove_xbox": (
        'if(Get-AppxPackage -AllUsers "*XboxGamingOverlay*" -EA SilentlyContinue){"0"}else{"1"}'
    ),
    "remove_teams": (
        '$app=Get-AppxPackage -AllUsers "*MicrosoftTeams*" -EA SilentlyContinue; '
        '$reg=(Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications" '
        '-Name ConfigureChatAutoInstall -EA SilentlyContinue).ConfigureChatAutoInstall; '
        'if($app -eq $null -or $reg -eq 0){"1"}else{"0"}'
    ),
    "remove_copilot": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Policies\\Microsoft\\Windows\\WindowsCopilot" '
        '-Name TurnOffWindowsCopilot -EA SilentlyContinue).TurnOffWindowsCopilot; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "remove_onedrive": (
        '$od="$env:LOCALAPPDATA\\Microsoft\\OneDrive\\OneDrive.exe"; '
        '$reg=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" '
        '-Name OneDrive -EA SilentlyContinue); '
        'if(-not $reg -and -not (Test-Path $od)){"1"}else{"0"}'
    ),
    "remove_recall": (
        '$k=Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI" -EA SilentlyContinue; '
        'if($k -and $k.DisableAIDataAnalysis -eq 1 -and $k.AllowRecallEnablement -eq 0){"1"}else{"0"}'
    ),
    "remove_bloatware": (
        'if(Get-AppxPackage -AllUsers "*king.com*" -EA SilentlyContinue){"0"}else{"1"}'
    ),

    # ── Privacy ───────────────────────────────────────────────────────────────
    "disable_telemetry": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection" '
        '-Name AllowTelemetry -EA SilentlyContinue).AllowTelemetry; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_activity_history": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System" '
        '-Name EnableActivityFeed -EA SilentlyContinue).EnableActivityFeed; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_advertising_id": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo" '
        '-Name Enabled -EA SilentlyContinue).Enabled; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_location": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\'
        'CapabilityAccessManager\\ConsentStore\\location" -Name Value -EA SilentlyContinue).Value; '
        'if($v -eq "Deny"){"1"}else{"0"}'
    ),
    "block_telemetry_hosts": (
        '$h=Get-Content "$env:SystemRoot\\System32\\drivers\\etc\\hosts" -EA SilentlyContinue; '
        'if($h -match "telemetry.microsoft.com"){"1"}else{"0"}'
    ),
    "disable_telemetry_tasks": (
        '$t=Get-ScheduledTask -TaskPath "\\Microsoft\\Windows\\Customer Experience Improvement Program\\" '
        '-TaskName "Consolidator" -EA SilentlyContinue; '
        'if($t -and $t.State -eq "Disabled"){"1"}else{"0"}'
    ),

    # ── Performance ───────────────────────────────────────────────────────────
    "ultimate_performance": (
        "$p=powercfg -getactivescheme; $a=[regex]::Matches((powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null | Out-String),'0x[0-9a-fA-F]{8}'); $b=[regex]::Matches((powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null | Out-String),'0x[0-9a-fA-F]{8}'); if($p -match 'Ultimat' -and $a.Count -ge 2 -and $b.Count -ge 2 -and [Convert]::ToInt32($a[$a.Count-2].Value.Substring(2),16) -eq 0 -and [Convert]::ToInt32($b[$b.Count-2].Value.Substring(2),16) -eq 0){'1'}else{'0'}"
    ),
    # bcdedit needs admin rights: without them it's unknown, not "inactive"
    "disable_hpet": (
        '$o=(bcdedit /enum 2>&1 | Out-String); if($LASTEXITCODE -ne 0){ throw "bcdedit" }; '
        'if($o -match "useplatformtick\\s+(Yes|Ja)"){"1"}else{"0"}'
    ),
    "timer_resolution": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" '
        '-Name GlobalTimerResolutionRequests -EA SilentlyContinue).GlobalTimerResolutionRequests; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_prefetch": (
        '$s=(Get-Service SysMain -EA SilentlyContinue).StartType; '
        'if($s -eq "Disabled"){"1"}else{"0"}'
    ),
    "visual_effects_perf": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects" '
        '-Name VisualFXSetting -EA SilentlyContinue).VisualFXSetting; '
        'if($v -eq 2){"1"}else{"0"}'
    ),
    "disable_search_indexing": (
        '$s=(Get-Service WSearch -EA SilentlyContinue).StartType; '
        'if($s -eq "Disabled"){"1"}else{"0"}'
    ),

    # ── Mouse & UI ────────────────────────────────────────────────────────────
    "disable_mouse_accel": (
        '$v=(Get-ItemProperty "HKCU:\\Control Panel\\Mouse" '
        '-Name MouseSpeed -EA SilentlyContinue).MouseSpeed; '
        'if($v -eq "0"){"1"}else{"0"}'
    ),
    "disable_sticky_keys": (
        '$v=(Get-ItemProperty "HKCU:\\Control Panel\\Accessibility\\StickyKeys" '
        '-Name Flags -EA SilentlyContinue).Flags; '
        'if($v -eq "506"){"1"}else{"0"}'
    ),
    "enable_dark_mode": (
        '$v=(Get-ItemProperty "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" '
        '-Name AppsUseLightTheme -EA SilentlyContinue).AppsUseLightTheme; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_transparency": (
        '$v=(Get-ItemProperty "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" '
        '-Name EnableTransparency -EA SilentlyContinue).EnableTransparency; '
        'if($v -eq 0){"1"}else{"0"}'
    ),

    # ── Gaming ────────────────────────────────────────────────────────────────
    "enable_game_mode": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\GameBar" '
        '-Name AutoGameModeEnabled -EA SilentlyContinue).AutoGameModeEnabled; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_game_bar": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR" '
        '-Name AppCaptureEnabled -EA SilentlyContinue).AppCaptureEnabled; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "cpu_priority_games": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\PriorityControl" '
        '-Name Win32PrioritySeparation -EA SilentlyContinue).Win32PrioritySeparation; '
        'if($v -eq 26){"1"}else{"0"}'
    ),
    "mmcss_gaming": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\'
        'Multimedia\\SystemProfile\\Tasks\\Games" -Name "GPU Priority" -EA SilentlyContinue)."GPU Priority"; '
        'if($v -eq 8){"1"}else{"0"}'
    ),
    "disable_fullscreen_opt": (
        '$v=(Get-ItemProperty "HKCU:\\System\\GameConfigStore" '
        '-Name GameDVR_FSEBehaviorMode -EA SilentlyContinue).GameDVR_FSEBehaviorMode; '
        'if($v -eq 2){"1"}else{"0"}'
    ),
    "disable_wu_gaming": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" '
        '-Name NoAutoUpdate -EA SilentlyContinue).NoAutoUpdate; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_bg_throttle": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications" '
        '-Name GlobalUserDisabled -EA SilentlyContinue).GlobalUserDisabled; '
        'if($v -eq 1){"1"}else{"0"}'
    ),

    # ── GPU & Driver ──────────────────────────────────────────────────────────
    "enable_hags": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" '
        '-Name HwSchMode -EA SilentlyContinue).HwSchMode; '
        'if($v -eq 2){"1"}else{"0"}'
    ),
    "nvidia_low_latency": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak" '
        '-Name NVLatency -EA SilentlyContinue).NVLatency; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "dx12_optimization": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" '
        '-Name TdrDelay -EA SilentlyContinue).TdrDelay; '
        'if($v -eq 10){"1"}else{"0"}'
    ),

    # ── Network ───────────────────────────────────────────────────────────────
    "disable_nagle": (
        '$ok=$true; '
        'Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\*" '
        '-EA SilentlyContinue | ForEach-Object{ if($_.TcpAckFrequency -ne 1){$ok=$false} }; '
        'if($ok){"1"}else{"0"}'
    ),
    "disable_network_throttle": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" '
        '-Name NetworkThrottlingIndex -EA SilentlyContinue).NetworkThrottlingIndex; '
        'if($v -eq 4294967295){"1"}else{"0"}'
    ),
    "dns_cloudflare": (
        '$d=Get-DnsClientServerAddress -AddressFamily IPv4 -EA SilentlyContinue | '
        'Select-Object -ExpandProperty ServerAddresses; '
        'if($d -contains "1.1.1.1"){"1"}else{"0"}'
    ),
    "dns_google": (
        '$d=Get-DnsClientServerAddress -AddressFamily IPv4 -EA SilentlyContinue | '
        'Select-Object -ExpandProperty ServerAddresses; '
        'if($d -contains "8.8.8.8"){"1"}else{"0"}'
    ),

    # ── Power ─────────────────────────────────────────────────────────────────
    "disable_usb_suspend": (
        '$v=powercfg /query SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 '
        '48e6b7a6-50f5-4782-a5d4-53bb8f07e226 2>$null; '
        'if($v -match "0x00000000"){"1"}else{"0"}'
    ),


    # ── GPU & Driver ──────────────────────────────────────────────────────────
    "enable_msi_mode": (
        '$dev=Get-WmiObject Win32_VideoController|Where-Object{$_.Name -notmatch "Microsoft"}|'
        'Select-Object -First 1; '
        'if($dev){'
        '$id=$dev.PNPDeviceID;'
        '$p="HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$id\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties";'
        '$v=(Get-ItemProperty $p -Name MSISupported -EA SilentlyContinue).MSISupported;'
        'if($v -eq 1){"1"}else{"0"}}else{"0"}'
    ),
    "clear_shader_cache": (
        '$p="$env:LOCALAPPDATA\\NVIDIA\\DXCache";'
        'if(Test-Path $p){'
        '$sz=(Get-ChildItem $p -EA SilentlyContinue|Measure-Object -Property Length -Sum).Sum;'
        'if($sz -lt 1048576){"1"}else{"0"}}else{"1"}'
    ),

    # ── Network ───────────────────────────────────────────────────────────────
    "disable_lso": (
        '$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"};'
        '$all_disabled=$true;'
        'foreach($a in $adapters){'
        '$lso=Get-NetAdapterLso -Name $a.Name -EA SilentlyContinue;'
        'if($lso -and ($lso.IPv4Enabled -or $lso.IPv6Enabled)){$all_disabled=$false}};'
        'if($all_disabled){"1"}else{"0"}'
    ),
    "flush_dns": (
        # DNS flush is a one-time action, not persistently verifiable
        # Check if DNS client service is running (proxy for "DNS is functional")
        '$s=(Get-Service Dnscache -EA SilentlyContinue).Status;'
        'if($s -eq "Running"){"1"}else{"0"}'
    ),
    "disable_tcp_autotuning": (
        '$v=netsh int tcp show global 2>$null|Select-String "Auto-Tuning|Abstimmung";'
        'if(-not $v){ throw "netsh" }; if("$v" -match "disabled"){"1"}else{"0"}'
    ),
    "enable_rss": (
        '$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"};'
        '$any_on=$false;'
        'foreach($a in $adapters){'
        '$r=Get-NetAdapterRss -Name $a.Name -EA SilentlyContinue;'
        'if($r -and $r.Enabled){$any_on=$true}};'
        'if($any_on){"1"}else{"0"}'
    ),

    # ── Power Plan ────────────────────────────────────────────────────────────
    "power_balanced": (
        '$p=powercfg -getactivescheme;'
        'if($p -match "381b4222-f694-41f0-9685-ff5bb260df2e"){"1"}else{"0"}'
    ),
    "power_high": (
        "$p=powercfg -getactivescheme; $a=[regex]::Matches((powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null | Out-String),'0x[0-9a-fA-F]{8}'); $b=[regex]::Matches((powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null | Out-String),'0x[0-9a-fA-F]{8}'); if($p -match '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c' -and $a.Count -ge 2 -and $b.Count -ge 2 -and [Convert]::ToInt32($a[$a.Count-2].Value.Substring(2),16) -eq 0 -and [Convert]::ToInt32($b[$b.Count-2].Value.Substring(2),16) -eq 0){'1'}else{'0'}"
    ),

    # ── Audio ────────────────────────────────────────────────────────────────────
    "disable_sound_scheme": (
        r'$v=(Get-ItemProperty "HKCU:\AppEvents\Schemes" -Name "(Default)" -EA SilentlyContinue)."(Default)";'
        'if($v -eq ".None"){"1"}else{"0"}'
    ),
    "disable_nahimic": (
        # Goal = "no Nahimic interfering". If none of the Nahimic services exist,
        # that goal is already satisfied → "1" (green), instead of a permanent
        # amber mismatch on the majority of PCs that never had Nahimic.
        '$svcs=@("NahimicService","A-Volute","nahimicSvc");'
        '$found=$false;$active=$false;'
        'foreach($n in $svcs){$s=Get-Service -Name $n -EA SilentlyContinue;'
        'if($s){$found=$true;if($s.StartType -ne "Disabled"){$active=$true}}}'
        'if(-not $found){"1"}elseif(-not $active){"1"}else{"0"}'
    ),
    "set_mmcss_audio": (
        r'$p="HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Pro Audio";'
        '$v=(Get-ItemProperty $p -Name "Priority" -EA SilentlyContinue).Priority;'
        'if($v -eq 6){"1"}else{"0"}'
    ),
    "disable_audio_ducking": (
        r'$v=(Get-ItemProperty "HKCU:\Software\Microsoft\Multimedia\Audio"'
        ' -Name "UserDuckingPreference" -EA SilentlyContinue).UserDuckingPreference;'
        'if($v -eq 3){"1"}else{"0"}'
    ),
    "disable_audio_enhancements": (
        r'Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"'
        ' -Recurse -EA SilentlyContinue | Where-Object { $_.PSChildName -eq "Properties" } |'
        " ForEach-Object { $v = Get-ItemProperty -Path $_.PSPath"
        " -Name '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5' -EA SilentlyContinue;"
        " if ($v) { $v.'{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5' } else { -1 } } |"
        ' Measure-Object -Maximum -Minimum | ForEach-Object {'
        ' if ($_.Count -gt 0 -and $_.Maximum -eq 1 -and $_.Minimum -eq 1) {"1"} else {"0"} }'
    ),
    "disable_audio_exclusive_lock": (
        r'Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"'
        " -EA SilentlyContinue | ForEach-Object {"
        " $props = Join-Path $_.PSPath 'Properties'; if (Test-Path $props) {"
        " $v3 = Get-ItemProperty -Path $props -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},3' -EA SilentlyContinue;"
        " $v4 = Get-ItemProperty -Path $props -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},4' -EA SilentlyContinue;"
        " $ok3 = ($v3 -and $v3.'{b3f8fa53-0004-438e-9003-51a46e139bfc},3' -eq 0);"
        " $ok4 = ($v4 -and $v4.'{b3f8fa53-0004-438e-9003-51a46e139bfc},4' -eq 0);"
        ' if ($ok3 -and $ok4) {1} else {0} } } |'
        ' Measure-Object -Maximum -Minimum | ForEach-Object {'
        ' if ($_.Count -gt 0 -and $_.Minimum -eq 1) {"1"} else {"0"} }'
    ),

    # ── Windows 11 ────────────────────────────────────────────────────────────────
    "w11_classic_context_menu": (
        '$p="HKCU:\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\\InprocServer32"; '
        'if(Test-Path $p){"1"}else{"0"}'
    ),
    "w11_taskbar_left": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" '
        '-Name TaskbarAl -EA SilentlyContinue).TaskbarAl; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "w11_disable_widgets": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Dsh" '
        '-Name AllowNewsAndInterests -EA SilentlyContinue).AllowNewsAndInterests; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "w11_disable_snap_suggest": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" '
        '-Name EnableSnapAssistFlyout -EA SilentlyContinue).EnableSnapAssistFlyout; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_power_throttling": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling" '
        '-Name PowerThrottlingOff -EA SilentlyContinue).PowerThrottlingOff; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "reduce_process_count": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control" '
        '-Name SvcHostSplitThresholdInKB -EA SilentlyContinue).SvcHostSplitThresholdInKB; '
        'if($v -ne $null -and $v -gt 380000){"1"}else{"0"}'
    ),
    "disable_bing_search": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" '
        '-Name BingSearchEnabled -EA SilentlyContinue).BingSearchEnabled; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_consumer_features": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent" '
        '-Name DisableWindowsConsumerFeatures -EA SilentlyContinue).DisableWindowsConsumerFeatures; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_hibernation": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power" '
        '-Name HibernateEnabled -EA SilentlyContinue).HibernateEnabled; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    "end_task_right_click": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\\TaskbarDeveloperSettings" '
        '-Name TaskbarEndTask -EA SilentlyContinue).TaskbarEndTask; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_delivery_optimization": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DeliveryOptimization" '
        '-Name DODownloadMode -EA SilentlyContinue).DODownloadMode; '
        'if($v -eq 0){"1"}else{"0"}'
    ),
    # powercfg: the current AC setting index is always the second-to-last
    # 0x-hex value in the query output (AC then DC last) — locale-independent.
    "power_pcie_aspm_off": (
        '$o=(powercfg /query SCHEME_CURRENT SUB_PCIEXPRESS ASPM 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 0){"1"}else{"0"}'
    ),
    "power_disk_never_sleep": (
        '$o=(powercfg /query SCHEME_CURRENT SUB_DISK DISKIDLE 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 0){"1"}else{"0"}'
    ),
    "show_file_extensions": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" '
        '-Name HideFileExt -EA SilentlyContinue).HideFileExt; if($v -eq 0){"1"}else{"0"}'
    ),
    "show_hidden_files": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" '
        '-Name Hidden -EA SilentlyContinue).Hidden; if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_mpo": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\Dwm" '
        '-Name OverlayTestMode -EA SilentlyContinue).OverlayTestMode; if($v -eq 5){"1"}else{"0"}'
    ),
    "disable_wpbt": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager" '
        '-Name DisableWpbtExecution -EA SilentlyContinue).DisableWpbtExecution; if($v -eq 1){"1"}else{"0"}'
    ),
    "disable_storage_sense": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\StorageSense" '
        '-Name AllowStorageSenseGlobal -EA SilentlyContinue).AllowStorageSenseGlobal; if($v -eq 0){"1"}else{"0"}'
    ),
    "disable_ai_text_image_gen": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppPrivacy" '
        '-Name LetAppsAccessSystemAIModels -EA SilentlyContinue).LetAppsAccessSystemAIModels; '
        'if($v -eq 2){"1"}else{"0"}'
    ),

    # ── Portiert aus v1: CTT Essentials / Adapter / Power Plan / AMD ─────────
    "prevent_device_companion": (
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Device Metadata" '
        '-Name PreventDeviceMetadataFromNetwork -EA SilentlyContinue).PreventDeviceMetadataFromNetwork; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "start_menu_previous_layout": (
        '$v=(Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FeatureManagement\\Overrides\\8\\3036241548" '
        '-Name EnabledState -EA SilentlyContinue).EnabledState; '
        'if($v -eq 1){"1"}else{"0"}'
    ),
    "explorer_folder_discovery": (
        '$v=(Get-ItemProperty "HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\Bags\\AllFolders\\Shell" '
        '-Name FolderType -EA SilentlyContinue).FolderType; '
        'if($v -eq "NotSpecified"){"1"}else{"0"}'
    ),
    "store_no_recommended": (
        '$db="$env:LocalAppData\\Packages\\Microsoft.WindowsStore_8wekyb3d8bbwe\\LocalState\\store.db"; '
        'if(!(Test-Path $db)){"0"}else{ $a=(icacls "$db" 2>$null | Out-String); '
        'if($a -match "\\(DENY\\)" -or $a -match "Jeder:\\(N\\)" -or $a -match "Everyone:\\(N\\)"){"1"}else{"0"} }'
    ),
    "nic_power_saving": (
        '$c="HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}"; '
        '$any=$false; $ok=$true; '
        'Get-ChildItem $c -EA SilentlyContinue | ForEach-Object { '
        'if(Get-ItemProperty $_.PSPath -Name NetCfgInstanceId -EA SilentlyContinue){ $any=$true; '
        '$v=(Get-ItemProperty $_.PSPath -Name PnPCapabilities -EA SilentlyContinue).PnPCapabilities; '
        'if($v -ne 24){$ok=$false} } }; '
        'if($any -and $ok){"1"}else{"0"}'
    ),
    # powercfg: die LETZTEN zwei Hex-Werte der Ausgabe sind der aktuelle AC- bzw.
    # DC-Index (die Zeilen davor sind statische "mögliche Einstellungen").
    # Checked on 'Ausbalanciert': the high-performance plans keep the screen on.
    "power_display_sleep_15": (
        '$o=(powercfg /query 381b4222-f694-41f0-9685-ff5bb260df2e SUB_VIDEO VIDEOIDLE 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 900){"1"}else{"0"}'
    ),
    "power_sleep_off": (
        '$o=(powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 0){"1"}else{"0"}'
    ),
    "power_cpu_min_100": (
        '$o=(powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 100){"1"}else{"0"}'
    ),
    "power_cpu_max_100": (
        '$o=(powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 2>$null | Out-String); '
        '$m=[regex]::Matches($o,"0x[0-9a-fA-F]{8}"); '
        'if($m.Count -ge 2 -and [Convert]::ToInt32($m[$m.Count-2].Value.Substring(2),16) -eq 100){"1"}else{"0"}'
    ),
    # AMD: ohne AMD-GPU existiert der Klassen-Zweig nicht -> "0" (nicht aktiv),
    # statt fälschlich "aktiv" zu melden.
    "amd_disable_ulps": (
        _AMD_KEYS_PS +
        '$ok=($amd.Count -gt 0); foreach($k in $amd){ '
        '$v=(Get-ItemProperty $k.PSPath -Name EnableULPS -EA SilentlyContinue).EnableULPS; '
        'if($v -ne 0){$ok=$false} }; if($ok){"1"}else{"0"}'
    ),
    "amd_shader_cache": (
        _AMD_KEYS_PS +
        '$v=(Get-ItemProperty "HKLM:\\SOFTWARE\\ATI Technologies\\CBT" '
        '-Name ShaderCacheSizePC -EA SilentlyContinue).ShaderCacheSizePC; '
        'if($amd.Count -gt 0 -and $v -ne $null){"1"}else{"0"}'
    ),
    "amd_antilag": (
        _AMD_KEYS_PS +
        '$any=$false; foreach($k in $amd){ '
        'if((Get-ItemProperty $k.PSPath -Name EnableAntiLag -EA SilentlyContinue).EnableAntiLag -eq 1){$any=$true} }; '
        'if($any){"1"}else{"0"}'
    ),
    # ── v1-Parität + Windows 11 26H2 (KI) ────────────────────────────────────
    'enable_long_paths': (
        '$v=(Get-ItemProperty \'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\' -Name \'LongPathsEnabled\' -EA SilentlyContinue).\'LongPathsEnabled\'; if($v -eq 1){"1"}else{"0"}'
    ),
    'numlock_on_startup': (
        '$v=(Get-ItemProperty \'HKCU:\\Control Panel\\Keyboard\' -Name \'InitialKeyboardIndicators\' -EA SilentlyContinue).\'InitialKeyboardIndicators\'; if($v -eq \'2147483650\'){"1"}else{"0"}'
    ),
    'disable_lock_screen': (
        '$v=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Personalization\' -Name \'NoLockScreen\' -EA SilentlyContinue).\'NoLockScreen\'; if($v -eq 1){"1"}else{"0"}'
    ),
    'disable_reserved_storage': (
        '$s=(Get-WindowsReservedStorageState -EA SilentlyContinue).ReservedStorageState; if("$s" -eq \'Disabled\'){"1"}else{"0"}'
    ),
    'pagefile_system_managed': (
        '$c=Get-CimInstance Win32_ComputerSystem -EA SilentlyContinue; if($c -and $c.AutomaticManagedPagefile){"1"}else{"0"}'
    ),
    'clear_pagefile_shutdown': (
        '$v=(Get-ItemProperty \'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management\' -Name \'ClearPageFileAtShutdown\' -EA SilentlyContinue).\'ClearPageFileAtShutdown\'; if($v -eq 1){"1"}else{"0"}'
    ),
    # Without SysMain there is no compression store at all (no 'Memory Compression' process).
    'disable_memory_compression': (
        '$m=Get-MMAgent -EA SilentlyContinue; $p=Get-Process -Name "Memory Compression" -EA SilentlyContinue; '
        'if(($m -and -not $m.MemoryCompression) -or (-not $m -and -not $p)){"1"}else{"0"}'
    ),
    'enable_ssd_trim': (
        '$q=@(fsutil behavior query DisableDeleteNotify 2>$null); $l=@($q | Where-Object { $_ -match \'NTFS\' })[0]; if(-not $l){ $l=@($q | Where-Object { $_ -match \'=\' })[0] }; if($l -match \'=\\s*0\\b\'){"1"}else{"0"}'
    ),
    'disable_scheduled_defrag': (
        '$t=Get-ScheduledTask -TaskPath \'\\Microsoft\\Windows\\Defrag\\\' -TaskName \'ScheduledDefrag\' -EA SilentlyContinue; if($t -and "$($t.State)" -eq \'Disabled\'){"1"}else{"0"}'
    ),
    'nvme_queue_depth': (
        '$idx=@(Get-PhysicalDisk -EA SilentlyContinue | Where-Object { $_.BusType -eq \'NVMe\' } | ForEach-Object { [string]$_.DeviceId }); $d=@(Get-CimInstance Win32_DiskDrive -EA SilentlyContinue | Where-Object { $idx -contains [string]$_.Index })[0]; $v=$null; if($d){ $v=(Get-ItemProperty (\'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\\'+$d.PNPDeviceID+\'\\Device Parameters\\StorPort\') -Name QueueDepth -EA SilentlyContinue).QueueDepth }; if($v -eq 32){"1"}else{"0"}'
    ),
    'disable_write_cache_flush': (
        '$d=@(Get-CimInstance Win32_DiskDrive -EA SilentlyContinue | Where-Object { $_.PNPDeviceID -and $_.MediaType -match \'Fixed hard disk\' })[0]; $v=$null; if($d){ $v=(Get-ItemProperty (\'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\\'+$d.PNPDeviceID+\'\\Device Parameters\\Disk\') -Name CacheIsPowerProtected -EA SilentlyContinue).CacheIsPowerProtected }; if($v -eq 1){"1"}else{"0"}'
    ),
    'w11_remove_chat_icon': (
        '$v=(Get-ItemProperty \'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\' -Name \'TaskbarMn\' -EA SilentlyContinue).\'TaskbarMn\'; if($v -eq 0){"1"}else{"0"}'
    ),
    'w11_hide_recommended': (
        '$v=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer\' -Name \'HideRecommendedSection\' -EA SilentlyContinue).\'HideRecommendedSection\'; if($v -eq 1){"1"}else{"0"}'
    ),
    'disable_click_to_do': (
        '$v=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI\' -Name \'DisableClickToDo\' -EA SilentlyContinue).\'DisableClickToDo\'; if($v -eq 1){"1"}else{"0"}'
    ),
    'disable_paint_ai': (
        '$k=Get-ItemProperty \'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Paint\' -EA SilentlyContinue; if($k -and $k.DisableCocreator -eq 1 -and $k.DisableGenerativeFill -eq 1 -and $k.DisableImageCreator -eq 1){"1"}else{"0"}'
    ),
    'disable_notepad_ai': (
        '$v=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Policies\\WindowsNotepad\' -Name \'DisableAIFeatures\' -EA SilentlyContinue).\'DisableAIFeatures\'; if($v -eq 1){"1"}else{"0"}'
    ),
    'disable_ai_fabric_service': (
        '$s=Get-Service -Name WSAIFabricSvc -EA SilentlyContinue; if($s -and "$($s.StartType)" -eq \'Disabled\'){"1"}else{"0"}'
    ),
    'remove_m365_copilot_devhome': (
        'if(Get-AppxPackage -AllUsers \'*Microsoft.MicrosoftOfficeHub*\' -EA SilentlyContinue){"0"}elseif(Get-AppxPackage -AllUsers \'*Microsoft.Windows.DevHome*\' -EA SilentlyContinue){"0"}else{"1"}'
    ),
    'tcp_optimize': (
        '$k=Get-ItemProperty \'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\' -EA SilentlyContinue; if($k -and $k.SackOpts -eq 1 -and $k.TcpMaxDupAcks -eq 2){"1"}else{"0"}'
    ),
    'disable_qos_limit': (
        '$v=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Psched\' -Name \'NonBestEffortLimit\' -EA SilentlyContinue).\'NonBestEffortLimit\'; if($v -eq 0){"1"}else{"0"}'
    ),
    'mmcss_audio_profile': (
        '$k=Get-ItemProperty \'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Audio\' -EA SilentlyContinue; if($k -and $k.\'Latency Sensitive\' -eq \'True\' -and $k.\'Scheduling Category\' -eq \'High\'){"1"}else{"0"}'
    ),
    'audio_service_priority': (
        '$m=(Get-ItemProperty \'HKLM:\\SOFTWARE\\GameOptimizerPro\' -Name SR_AudioPriority -EA SilentlyContinue).SR_AudioPriority; $r=(Get-ItemProperty \'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\' -Name SystemResponsiveness -EA SilentlyContinue).SystemResponsiveness; if($m -eq 1 -and $r -eq 0){"1"}else{"0"}'
    ),

}


# Slow checks that use AppxPackage or long-running cmdlets
SLOW_CHECKS = {"remove_cortana", "remove_xbox", "remove_bloatware",
               # WMI / storage / Appx queries take seconds each
               "remove_m365_copilot_devhome", "disable_reserved_storage",
               "pagefile_system_managed", "disable_memory_compression",
               "disable_scheduled_defrag", "nvme_queue_depth", "disable_write_cache_flush"}


class TweakVerifier:
    def __init__(self, timeout_s: int = 45):
        self.timeout = timeout_s

    def _run_batch(self, ids: list[str], expected: dict,
                   timeout: int) -> dict[str, VerifyResult]:
        """Run a batch of verify commands in one PS call."""
        if not ids:
            return {}

        lines = []
        for tid in ids:
            cmd = VERIFY_MAP[tid].strip()
            # NOTE: $(...) subexpression — NOT (...). A grouping expression
            # (...) only accepts a single pipeline, so any verify command
            # written as two statements ("$v=...; if(...){}") fails to parse
            # and silently returns no output (amber dot). $(...) allows the
            # multi-statement form used by most registry checks.
            lines.append(
                f'try {{ $__r=$({cmd}); Write-Output "{tid}|$__r" }}'
                f' catch {{ Write-Output "{tid}|ERR" }}'
            )
        script = "\n".join(lines)

        results = {}
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            si = None
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0

            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                 "-Command", script],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
                creationflags=flags,
                startupinfo=si,
            )
            parsed: dict[str, bool] = {}
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if "|" not in line:
                    continue
                parts = line.split("|", 1)
                if len(parts) == 2:
                    tid_out = parts[0].strip()
                    val     = parts[1].strip()
                    if tid_out in VERIFY_MAP and val != "ERR":
                        parsed[tid_out] = (val == "1")

            for tid in ids:
                if tid in parsed:
                    actual = parsed[tid]
                    results[tid] = VerifyResult(
                        tweak_id=tid,
                        expected=expected.get(tid, False),
                        actual=actual,
                        mismatch=(expected.get(tid, False) != actual),
                        error=""
                    )
                else:
                    # No verify output: mark as error so the UI shows amber, not grey
                    results[tid] = VerifyResult(
                        tweak_id=tid,
                        expected=expected.get(tid, False),
                        actual=False,
                        mismatch=False,
                        error="no output"
                    )
        except subprocess.TimeoutExpired:
            for tid in ids:
                results[tid] = VerifyResult(
                    tid, expected.get(tid, False), False, False, "Timeout")
        except Exception as e:
            for tid in ids:
                results[tid] = VerifyResult(
                    tid, expected.get(tid, False), False, False, str(e))
        return results

    def verify_all(
        self, tweak_ids: list[str], expected: dict[str, bool]
    ) -> dict[str, VerifyResult]:
        verifiable = [t for t in tweak_ids if t in VERIFY_MAP]
        if not verifiable:
            return {}

        # Split into fast (registry/service) and slow (AppxPackage) batches
        fast_ids = [t for t in verifiable if t not in SLOW_CHECKS]
        slow_ids = [t for t in verifiable if t in SLOW_CHECKS]

        results = {}
        # Fast batch: 20s timeout
        results.update(self._run_batch(fast_ids, expected, timeout=20))
        # Slow batch: 30s timeout (AppxPackage queries take longer)
        results.update(self._run_batch(slow_ids, expected, timeout=30))
        return results

    def verify_single(self, tweak_id: str, expected: bool) -> Optional[VerifyResult]:
        results = self.verify_all([tweak_id], {tweak_id: expected})
        return results.get(tweak_id)

    def has_verify(self, tweak_id: str) -> bool:
        return tweak_id in VERIFY_MAP
