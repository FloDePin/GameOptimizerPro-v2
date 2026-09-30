"""
GameOptimizerPro Tweaks Database
All tweaks as Python dataclasses with PowerShell commands.
Preserves all original GameOptimizerPro tweaks + new additions.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


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
    requires_reboot: bool = False
    risk:        str = "safe"   # "safe" | "moderate" | "advanced"
    tags:        list = field(default_factory=list)
    timeout_s:   int = 60       # long one-time actions (Disk Cleanup/DISM) need more


from core import audio_policy   # noqa: E402 — audio tweaks use the API


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
_AMD_REQUIRED_PS = "if($amd.Count -eq 0){ Write-Output 'Kein AMD-Grafikadapter gefunden'; exit 1 }; "

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
_AMD_SHADER_APPLY = _AMD_KEYS_PS + _AMD_REQUIRED_PS + (
    "$p='HKLM:\\SOFTWARE\\ATI Technologies\\CBT'; "
    "if(!(Test-Path $p)){New-Item -Path $p -Force|Out-Null}; "
    "Set-ItemProperty -Path $p -Name ShaderCacheSizePC -Value 0xffffffff -Type DWord; "
    "foreach($k in $amd){ "
    "Set-ItemProperty -Path $k.PSPath -Name KMD_EnableComputePreemption -Value 0 -Type DWord -EA SilentlyContinue }"
)
_AMD_SHADER_REVERT = (
    "Remove-ItemProperty -Path 'HKLM:\\SOFTWARE\\ATI Technologies\\CBT' "
    "-Name ShaderCacheSizePC -EA SilentlyContinue; "
) + _AMD_KEYS_PS + (
    "foreach($k in $amd){ "
    "Remove-ItemProperty -Path $k.PSPath -Name KMD_EnableComputePreemption -EA SilentlyContinue }"
)
_AMD_ANTILAG_APPLY = _AMD_KEYS_PS + _AMD_REQUIRED_PS + (
    "foreach($k in $amd){ "
    "Set-ItemProperty -Path $k.PSPath -Name EnableAntiLag -Value 1 -Type DWord -EA SilentlyContinue }"
)
_AMD_ANTILAG_REVERT = _AMD_KEYS_PS + (
    "foreach($k in $amd){ "
    "Remove-ItemProperty -Path $k.PSPath -Name EnableAntiLag -EA SilentlyContinue }"
)

# NVIDIA: only write when the NVIDIA kernel driver service exists. `reg add /f`
# on an AMD/Intel system would otherwise CREATE a bogus
# Services\nvlddmkm\Global\NVTweak tree for a driver that isn't installed.
_NV_LATENCY_APPLY = (
    "if(!(Test-Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm')){ "
    "Write-Output 'Kein NVIDIA-Treiber gefunden'; exit 1 }; "
    "$p='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak'; "
    "if(!(Test-Path $p)){New-Item -Path $p -Force|Out-Null}; "
    "Set-ItemProperty -Path $p -Name NVLatency -Value 1 -Type DWord"
)
_NV_LATENCY_REVERT = (
    "Remove-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak' "
    "-Name NVLatency -EA SilentlyContinue"
)



# ── Helpers for the v1-parity / 26H2 tweaks ──────────────────────────────────

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
_NVME_QD_APPLY = _NVME_DISKS_PS + (
    r"if($nv.Count -eq 0){ Write-Output 'Kein NVMe-Laufwerk gefunden'; exit 1 }; "
    r"foreach($d in $nv){ $b='HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters'; "
    r"reg add ($b+'\StorPort') /v QueueDepth /t REG_DWORD /d 32 /f | Out-Null; "
    r"reg add ($b+'\Interrupt Management\Affinity Policy') /v DevicePriority /t REG_DWORD /d 2 /f | Out-Null }; "
    r"reg add 'HKLM\SYSTEM\CurrentControlSet\Services\stornvme\Parameters\Device' /v IdlePowerEnabled /t REG_DWORD /d 0 /f"
)
_NVME_QD_REVERT = _NVME_DISKS_PS + (
    r"foreach($d in $nv){ $b='HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters'; "
    r"reg delete ($b+'\StorPort') /v QueueDepth /f 2>$null | Out-Null; "
    r"reg delete ($b+'\Interrupt Management\Affinity Policy') /v DevicePriority /f 2>$null | Out-Null }; "
    r"reg delete 'HKLM\SYSTEM\CurrentControlSet\Services\stornvme\Parameters\Device' /v IdlePowerEnabled /f 2>$null | Out-Null; "
    r"exit 0"
)

# Internal fixed disks only (never removable/external media).
_FIXED_DISKS_PS = (
    r"$dd=@(Get-CimInstance Win32_DiskDrive -EA SilentlyContinue | "
    r"Where-Object { $_.PNPDeviceID -and $_.MediaType -match 'Fixed hard disk' }); "
)
# "Turn off Windows write-cache buffer flushing" = CacheIsPowerProtected=1.
# (v1 wrote UserWriteCacheSetting=1, which only ENABLES write caching.)
_WCACHE_APPLY = _FIXED_DISKS_PS + (
    r"if($dd.Count -eq 0){ Write-Output 'Keine internen Laufwerke gefunden'; exit 1 }; "
    r"foreach($d in $dd){ reg add ('HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters\Disk') "
    r"/v CacheIsPowerProtected /t REG_DWORD /d 1 /f | Out-Null }; exit 0"
)
_WCACHE_REVERT = _FIXED_DISKS_PS + (
    r"foreach($d in $dd){ reg delete ('HKLM\SYSTEM\CurrentControlSet\Enum\'+$d.PNPDeviceID+'\Device Parameters\Disk') "
    r"/v CacheIsPowerProtected /f 2>$null | Out-Null }; exit 0"
)

# Paint AI policies (Windows Components > Paint): the three documented in the
# WindowsAI Policy CSP plus Generative Erase / Remove Background.
_PAINT_AI_KEY = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint"
_PAINT_AI_VALUES = ("DisableCocreator", "DisableGenerativeFill", "DisableImageCreator",
                    "DisableGenerativeErase", "DisableRemoveBackground")
_PAINT_AI_APPLY = "\n".join(
    f'reg add "{_PAINT_AI_KEY}" /v {v} /t REG_DWORD /d 1 /f'
    + (" | Out-Null" if i < len(_PAINT_AI_VALUES) - 1 else "")
    for i, v in enumerate(_PAINT_AI_VALUES))
_PAINT_AI_REVERT = "\n".join(
    f'reg delete "{_PAINT_AI_KEY}" /v {v} /f 2>$null' for v in _PAINT_AI_VALUES) + "\nexit 0"

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

ALL_TWEAKS: list[Tweak] = [

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — BLOATWARE
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="remove_cortana",
        name="Remove Cortana",
        desc="Deinstalliert Cortana. Cortana sendet Daten an Microsoft und wird von den meisten Nutzern nicht verwendet.",
        category="Windows", group="Bloatware",
        ps_command='Get-AppxPackage -AllUsers "*Microsoft.549981C3F5F10*" | Remove-AppxPackage -ErrorAction SilentlyContinue',
        revert_cmd="",
    ),
    Tweak(
        id="remove_xbox",
        name="Remove Xbox Apps",
        desc="Entfernt Xbox Game Bar, Xbox Identity Provider und Xbox TCUI. Laufen im Hintergrund auch ohne Xbox.",
        category="Windows", group="Bloatware",
        ps_command='''
$apps=@("*XboxApp*","*XboxGameOverlay*","*XboxGamingOverlay*","*XboxIdentityProvider*","*XboxSpeechToTextOverlay*","*XboxTCUI*")
foreach($a in $apps){Get-AppxPackage -AllUsers $a|Remove-AppxPackage -ErrorAction SilentlyContinue}
''',
    ),
    Tweak(
        id="remove_teams",
        name="Remove Microsoft Teams (Personal)",
        desc="Entfernt Teams Consumer. Blockiert automatische Neuinstallation via Registry.",
        category="Windows", group="Bloatware",
        ps_command='''
Get-AppxPackage -AllUsers "*MicrosoftTeams*" -EA SilentlyContinue | Remove-AppxPackage -EA SilentlyContinue
Get-AppxPackage -AllUsers "*Teams*" -EA SilentlyContinue | Remove-AppxPackage -EA SilentlyContinue
$key = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications"
try {
    if (-not (Test-Path $key)) { New-Item -Path $key -Force -EA SilentlyContinue | Out-Null }
    Set-ItemProperty -Path $key -Name ConfigureChatAutoInstall -Value 0 -Type DWord -EA SilentlyContinue
} catch { }
Write-Output "Teams removal completed"
exit 0
''',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications" /v ConfigureChatAutoInstall /f 2>$null',
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
        desc="Entfernt vorinstallierte Apps: Candy Crush, TikTok, Disney+, Facebook, Spotify, News, Solitaire, "
             "Clipchamp, ToDo, Paint3D, Mixed Reality u.v.m. — auch die bereitgestellten Pakete, damit "
             "Funktionsupdates sie nicht wieder installieren.",
        category="Windows", group="Bloatware",
        # Also removes the provisioned packages: feature updates re-install
        # apps that were only removed per user (seen with 26H2).
        ps_command=_remove_apps_ps([
            "*king.com*", "*Facebook*", "*Spotify*", "*Disney*", "*TikTok*", "*Instagram*",
            "*Netflix*", "*Twitter*", "*BubbleWitch*", "*MarchofEmpires*", "*CandyCrush*",
            "*Microsoft.News*", "*Microsoft.BingWeather*", "*Microsoft.BingNews*",
            "*Microsoft.MicrosoftSolitaireCollection*", "*Microsoft.ZuneMusic*",
            "*Microsoft.ZuneVideo*", "*Microsoft.WindowsFeedbackHub*", "*Microsoft.Todos*",
            "*Microsoft.Paint3D*", "*Microsoft.MixedReality*", "*Clipchamp*",
            "*Microsoft.GetHelp*", "*Microsoft.Getstarted*", "*Microsoft.PowerAutomateDesktop*",
        ]),
    ),
    Tweak(
        id="disable_consumer_features",
        name="Disable Consumer Features",
        desc="Verhindert dass Windows automatisch vorgeschlagene Apps und Bloatware nachinstalliert "
             "(Candy Crush & Co. tauchen sonst nach Updates wieder auf). Reine Richtlinie, keine Deinstallation.",
        category="Windows", group="Bloatware",
        ps_command='reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent" /v DisableWindowsConsumerFeatures /t REG_DWORD /d 1 /f',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent" /v DisableWindowsConsumerFeatures /f 2>$null',
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
             "und lädt keine Web-Ergebnisse mehr nach. Reduziert kleine Verzögerungen beim Öffnen des Startmenüs.",
        category="Windows", group="Privacy",
        ps_command=(
            r'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Search" '
            r'-Name BingSearchEnabled -Value 0 -Type DWord -EA SilentlyContinue; '
            r'$p="HKCU:\Software\Policies\Microsoft\Windows\Explorer"; '
            r'if(-not (Test-Path $p)){New-Item -Path $p -Force -EA SilentlyContinue | Out-Null}; '
            r'Set-ItemProperty -Path $p -Name DisableSearchBoxSuggestions -Value 1 -Type DWord -EA SilentlyContinue; '
            r'Write-Output "Bing disabled"; exit 0'
        ),
        revert_cmd=(
            r'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Search" '
            r'-Name BingSearchEnabled -Value 1 -Type DWord -EA SilentlyContinue; '
            r'Remove-ItemProperty -Path "HKCU:\Software\Policies\Microsoft\Windows\Explorer" '
            r'-Name DisableSearchBoxSuggestions -EA SilentlyContinue; exit 0'
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
        id="block_telemetry_hosts",
        name="Block Telemetry Hosts (hosts file)",
        desc="Blockiert Microsoft Telemetrie-Server in der hosts-Datei. Funktioniert auch wenn Dienste noch laufen.",
        category="Windows", group="Privacy",
        ps_command='''
$entries=@("0.0.0.0 telemetry.microsoft.com","0.0.0.0 vortex.data.microsoft.com",
"0.0.0.0 vortex-win.data.microsoft.com","0.0.0.0 telecommand.telemetry.microsoft.com",
"0.0.0.0 oca.telemetry.microsoft.com","0.0.0.0 sqm.telemetry.microsoft.com",
"0.0.0.0 watson.telemetry.microsoft.com","0.0.0.0 redir.metaservices.microsoft.com",
"0.0.0.0 df.telemetry.microsoft.com")
$hostsFile="$env:SystemRoot\\System32\\drivers\\etc\\hosts"
$existing=Get-Content $hostsFile
foreach($e in $entries){if($existing -notcontains $e){Add-Content $hostsFile $e}}
''',
        revert_cmd='''
$entries=@("0.0.0.0 telemetry.microsoft.com","0.0.0.0 vortex.data.microsoft.com",
"0.0.0.0 vortex-win.data.microsoft.com","0.0.0.0 telecommand.telemetry.microsoft.com",
"0.0.0.0 oca.telemetry.microsoft.com","0.0.0.0 sqm.telemetry.microsoft.com",
"0.0.0.0 watson.telemetry.microsoft.com","0.0.0.0 redir.metaservices.microsoft.com",
"0.0.0.0 df.telemetry.microsoft.com")
$hostsFile="$env:SystemRoot\\System32\\drivers\\etc\\hosts"
$existing=Get-Content $hostsFile
$filtered=$existing | Where-Object { $entries -notcontains $_ }
Set-Content -Path $hostsFile -Value $filtered
''',
        risk="moderate",
    ),
    Tweak(
        id="disable_telemetry_tasks",
        name="Disable Scheduled Telemetry Tasks",
        desc="Deaktiviert alle geplanten Windows-Aufgaben die Telemetriedaten sammeln.",
        category="Windows", group="Privacy",
        ps_command='''
$tasks=@("\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser",
"\\Microsoft\\Windows\\Application Experience\\ProgramDataUpdater",
"\\Microsoft\\Windows\\Autochk\\Proxy",
"\\Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator",
"\\Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip",
"\\Microsoft\\Windows\\DiskDiagnostic\\Microsoft-Windows-DiskDiagnosticDataCollector")
foreach($t in $tasks){schtasks /Change /TN $t /Disable 2>$null}
''',
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
    if(-not $new){ Write-Output "Plan 'Ultimative Leistung' nicht verfuegbar: $o"; exit 1 }
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
if($now -ne $keep){ Write-Output "Plan liess sich nicht aktivieren"; exit 1 }
Write-Output "Aktiv: Ultimative Leistung ($keep), Bildschirm/Standby im Netzbetrieb: nie; entfernte Kopien: $($ult.Count - 1)"
''',
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
    Tweak(
        id="timer_resolution",
        name="Set 0.5ms Timer Resolution",
        desc="Setzt Windows Timer-Auflösung auf 0.5ms (Standard: 15.6ms). Besseres Frame-Timing, weniger Input-Lag.",
        category="Windows", group="Performance",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v GlobalTimerResolutionRequests /t REG_DWORD /d 1 /f',
        revert_cmd='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v GlobalTimerResolutionRequests /t REG_DWORD /d 0 /f',
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
        desc="Schaltet alle Windows-Animationen aus. Windows reagiert spürbar schneller.",
        category="Windows", group="Performance",
        ps_command='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects" /v VisualFXSetting /t REG_DWORD /d 2 /f
Set-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" -Name "TaskbarAnimations" -Value 0
reg add "HKCU\\Control Panel\\Desktop\\WindowMetrics" /v MinAnimate /t REG_SZ /d 0 /f
''',
        revert_cmd='''
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects" /v VisualFXSetting /t REG_DWORD /d 0 /f
Set-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" -Name "TaskbarAnimations" -Value 1
reg add "HKCU\\Control Panel\\Desktop\\WindowMetrics" /v MinAnimate /t REG_SZ /d 1 /f
''',
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
    Tweak(
        id="mmcss_gaming",
        name="MMCSS Gaming Profile (High Priority)",
        desc="Setzt MMCSS auf High Priority für Spiele. Windows priorisiert Audio und Timer-Interrupts.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "GPU Priority" /t REG_DWORD /d 8 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Priority" /t REG_DWORD /d 6 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Scheduling Category" /t REG_SZ /d High /f
''',
        revert_cmd='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "GPU Priority" /t REG_DWORD /d 8 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Priority" /t REG_DWORD /d 2 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games" /v "Scheduling Category" /t REG_SZ /d High /f
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
        name="Disable Windows Update (Auto-Install)",
        desc="Verhindert automatische WU-Downloads/Installationen. Verhindert Reboots und Performance-Einbrüche beim Gaming.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoUpdate /t REG_DWORD /d 1 /f
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v AUOptions /t REG_DWORD /d 2 /f
''',
        revert_cmd='''
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v NoAutoUpdate /f 2>$null
reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /v AUOptions /f 2>$null
''',
        risk="moderate",
    ),
    Tweak(
        id="disable_bg_throttle",
        name="Disable Background App Throttling",
        desc="Deaktiviert CPU-Throttling für Hintergrundprozesse. Wichtig bei CPU-intensiven Spielen.",
        category="Gaming", group="In-Game Boosts",
        ps_command='''
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v DisableLowQosTimerResolution /t REG_DWORD /d 1 /f
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications" /v GlobalUserDisabled /t REG_DWORD /d 1 /f
''',
        revert_cmd='''
reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\kernel" /v DisableLowQosTimerResolution /f 2>$null
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications" /v GlobalUserDisabled /t REG_DWORD /d 0 /f
''',
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
        ps_command='''
$ramKB = [math]::Round((Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1024)
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control" /v SvcHostSplitThresholdInKB /t REG_DWORD /d $ramKB /f
''',
        revert_cmd='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control" /v SvcHostSplitThresholdInKB /t REG_DWORD /d 380000 /f',
        risk="moderate",
    ),

    # ══════════════════════════════════════════════════════════════
    # GAMING — GPU & DRIVER
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="nvidia_low_latency",
        name="NVIDIA Low Latency Mode (Reflex)",
        desc="Aktiviert NVIDIA Ultra Low Latency Mode. Reduziert Render-Queue auf 1 Frame. Nur auf NVIDIA GPUs wirksam.",
        category="Gaming", group="GPU & Driver",
        requires_nvidia=True,
        ps_command=_NV_LATENCY_APPLY,
        revert_cmd=_NV_LATENCY_REVERT,
    ),
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
        desc="Übergibt GPU-Scheduling direkt an Hardware. Weniger CPU-Overhead, geringerer Input-Lag. Braucht RTX 2000+ oder RX 5000+.",
        category="Gaming", group="GPU & Driver",
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d 2 /f',
        revert_cmd='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d 1 /f',
        requires_reboot=True,
    ),
    Tweak(
        id="clear_shader_cache",
        name="Clear Shader Cache",
        desc="Leert NVIDIA/AMD Shader-Cache. Sinnvoll nach Treiberupdates oder bei Grafikfehlern.",
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
        desc="Deaktiviert Netzwerk-Throttling bei hoher CPU-Last. Gibt dem Netzwerk-Stack höchste Priorität.",
        category="Network", group="Latency",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v NetworkThrottlingIndex /t REG_DWORD /d 0xffffffff /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 0 /f
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
        desc="Setzt DNS auf Cloudflare 1.1.1.1/1.0.0.1. Einer der schnellsten und datenschutzfreundlichsten DNS-Dienste.",
        category="Network", group="DNS",
        ps_command='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses ("1.1.1.1","1.0.0.1") -ErrorAction SilentlyContinue}
''',
        revert_cmd='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ResetServerAddresses -ErrorAction SilentlyContinue}
''',
    ),
    Tweak(
        id="dns_google",
        name="Set DNS to Google (8.8.8.8)",
        desc="Setzt DNS auf Google 8.8.8.8/8.8.4.4. Global verteilt, schnell und zuverlässig.",
        category="Network", group="DNS",
        ps_command='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses ("8.8.8.8","8.8.4.4") -ErrorAction SilentlyContinue}
''',
        revert_cmd='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ResetServerAddresses -ErrorAction SilentlyContinue}
''',
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
        desc="Deaktiviert automatisches TCP-Empfangsfenster. Kann Latenz-Spikes reduzieren. Bei 1Gbit+ leicht schlechterer Durchsatz.",
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
    if(-not $r){ $msg+="$($a.Name): Treiber meldet keine RSS-Einstellung"; continue }
    $n++
    try { Enable-NetAdapterRss -Name $a.Name -EA Stop; $ok++ } catch { $msg+="$($a.Name): $($_.Exception.Message)" }
}
$msg
if($ok -gt 0){ Write-Output "RSS aktiv auf $ok von $n Adapter(n)"; exit 0 }
if($n -eq 0){ Write-Output "Kein aktiver Adapter bietet RSS ueber Windows an (Treiber)"; exit 1 }
exit 1
''',
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
        desc="Stellt das klassische Rechtsklick-Kontextmenü in Windows 11 wieder her. Kein 'Weitere Optionen anzeigen' mehr.",
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
        desc="Verhindert dass USB-Geräte (Maus, Headset) in Stromspar-Modus versetzt werden. Kein plötzliches Disconnect mehr.",
        category="Windows", group="Power Plan",
        ps_command='''
powercfg -change -standby-timeout-ac 0
$guid=(powercfg -getactivescheme).Split()[3]
powercfg -setacvalueindex $guid 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg -setactive $guid
''',
        revert_cmd='''
$guid=(powercfg -getactivescheme).Split()[3]
powercfg -setacvalueindex $guid 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 1
powercfg -setactive $guid
''',
    ),
    Tweak(
        id="power_pcie_aspm_off",
        name="PCIe Link State Power Management aus",
        desc="Deaktiviert das Energiesparen des PCIe-Links (ASPM). Der PCIe-Bus zur Grafikkarte bleibt "
             "dauerhaft auf voller Leistung statt in Sparzustände zu wechseln — minimal konsistentere "
             "Latenz, dafür etwas mehr Idle-Verbrauch. Voll reversibel.",
        category="Windows", group="Power Plan",
        ps_command='''
powercfg -setacvalueindex SCHEME_CURRENT SUB_PCIEXPRESS ASPM 0
powercfg -setactive SCHEME_CURRENT
''',
        revert_cmd='''
powercfg -setacvalueindex SCHEME_CURRENT SUB_PCIEXPRESS ASPM 2
powercfg -setactive SCHEME_CURRENT
''',
        risk="safe",
    ),
    Tweak(
        id="power_disk_never_sleep",
        name="Festplatte nie schlafen legen",
        desc="Verhindert dass Windows Laufwerke nach Inaktivität abschaltet. Auf Systemen mit HDD(s) "
             "verhindert das Mikro-Ruckler, wenn ein Hintergrundprozess ein eingeschlafenes Laufwerk "
             "aufwecken muss. Voll reversibel.",
        category="Windows", group="Power Plan",
        ps_command='''
powercfg -setacvalueindex SCHEME_CURRENT SUB_DISK DISKIDLE 0
powercfg -setactive SCHEME_CURRENT
''',
        revert_cmd='''
powercfg -setacvalueindex SCHEME_CURRENT SUB_DISK DISKIDLE 1200
powercfg -setactive SCHEME_CURRENT
''',
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
        id="set_mmcss_audio",
        name="MMCSS Audio Priority (Pro Audio)",
        desc="Setzt MMCSS Audio-Prioritaet auf maximum. Windows gibt Audio-Threads hoehere CPU-Prioritaet "
             "— weniger Stottern und Knacken bei hoher Systemlast.",
        category="Audio", group="Performance",
        ps_command=(
            "$p = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Pro Audio';"
            " if (!(Test-Path $p)) { New-Item -Path $p -Force | Out-Null };"
            " Set-ItemProperty -Path $p -Name 'Affinity' -Value 0 -Type DWord;"
            " Set-ItemProperty -Path $p -Name 'Clock Rate' -Value 10000 -Type DWord;"
            " Set-ItemProperty -Path $p -Name 'GPU Priority' -Value 8 -Type DWord;"
            " Set-ItemProperty -Path $p -Name 'Priority' -Value 6 -Type DWord;"
            " Set-ItemProperty -Path $p -Name 'Scheduling Category' -Value 'High' -Type String;"
            " Set-ItemProperty -Path $p -Name 'SFIO Priority' -Value 'High' -Type String"
        ),
        revert_cmd=(
            # "Pro Audio" ist ein von Windows MITGELIEFERTER MMCSS-Task. Den Key zu
            # loeschen (wie frueher per Remove-Item -Recurse) wuerde auch Werte
            # entfernen, die dieser Tweak nie gesetzt hat (z.B. "Background Only"),
            # und das Pro-Audio-Scheduling ganz verschwinden lassen statt es
            # zurueckzusetzen. Deshalb: die echten Windows-Defaults zurueckschreiben.
            "$p = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"
            "\\Multimedia\\SystemProfile\\Tasks\\Pro Audio';"
            " if (Test-Path $p) {"
            " Set-ItemProperty -Path $p -Name 'Priority' -Value 1 -Type DWord -EA SilentlyContinue;"
            " Set-ItemProperty -Path $p -Name 'SFIO Priority' -Value 'Normal' -Type String -EA SilentlyContinue;"
            " Set-ItemProperty -Path $p -Name 'Scheduling Category' -Value 'High' -Type String -EA SilentlyContinue;"
            " Set-ItemProperty -Path $p -Name 'Clock Rate' -Value 10000 -Type DWord -EA SilentlyContinue;"
            " Set-ItemProperty -Path $p -Name 'GPU Priority' -Value 8 -Type DWord -EA SilentlyContinue;"
            " Set-ItemProperty -Path $p -Name 'Affinity' -Value 0 -Type DWord -EA SilentlyContinue }"
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
        id="start_menu_previous_layout",
        name="Enable Start Menu Previous Layout",
        desc="Aktiviert auf unterstützten Windows-11-Builds das vorherige Startmenü-Layout über ein Feature-Override. Wirkt nur auf Builds, die dieses Flag kennen — sonst ohne Effekt.",
        category="Windows", group="CTT Essentials",
        ps_command=r"""$p='HKLM:\SYSTEM\CurrentControlSet\Control\FeatureManagement\Overrides\8\3036241548'; if(!(Test-Path $p)){New-Item -Path $p -Force|Out-Null}; Set-ItemProperty -Path $p -Name EnabledState -Value 1 -Type DWord""",
        revert_cmd=r"""Remove-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FeatureManagement\Overrides\8\3036241548' -Name EnabledState -EA SilentlyContinue""",
        requires_reboot=True,
        tags=["ui", "ctt"],
    ),
    Tweak(
        id="explorer_folder_discovery",
        name="Disable File Explorer Automatic Folder Discovery",
        desc="Setzt alle Ordner auf 'Allgemeine Elemente'. Der Explorer verschwendet keine Zeit mehr damit, Ordnertypen automatisch zu erkennen — große Ordner öffnen deutlich schneller. Abmelden/Neustart nötig.",
        category="Windows", group="CTT Essentials",
        ps_command=r"""$b='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags'; $m='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU'; Remove-Item -Path $b -Recurse -Force -EA SilentlyContinue; Remove-Item -Path $m -Recurse -Force -EA SilentlyContinue; $a='HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell'; if(!(Test-Path $a)){New-Item -Path $a -Force|Out-Null}; Set-ItemProperty -Path $a -Name FolderType -Value 'NotSpecified' -Type String""",
        revert_cmd=r"""Remove-Item -Path 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags' -Recurse -Force -EA SilentlyContinue; Remove-Item -Path 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU' -Recurse -Force -EA SilentlyContinue""",
        requires_reboot=True,
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
        ps_command='$c=\'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}\'; $n=0; foreach($k in @(Get-ChildItem $c -EA SilentlyContinue | Where-Object { $_.PSChildName -match \'^\\d{4}$\' })){ if((Get-ItemProperty $k.PSPath -EA SilentlyContinue).NetCfgInstanceId){ Set-ItemProperty -Path $k.PSPath -Name PnPCapabilities -Value 24 -Type DWord -Force -EA SilentlyContinue; if($?){ $n++ } } }; if($n -gt 0){ Write-Output "Energiesparen aus fuer $n Netzwerkadapter"; exit 0 } else { exit 1 }',
        revert_cmd="$c='HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}'; $n=0; foreach($k in @(Get-ChildItem $c -EA SilentlyContinue | Where-Object { $_.PSChildName -match '^\\d{4}$' })){ if((Get-ItemProperty $k.PSPath -EA SilentlyContinue).NetCfgInstanceId){ Remove-ItemProperty -Path $k.PSPath -Name PnPCapabilities -Force -EA SilentlyContinue; if($?){ $n++ } } }; exit 0",
        requires_reboot=True,
        tags=["latency", "network"],
    ),

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — POWER PLAN  (portiert aus v1; schreibt in ALLE Schemata)
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="power_display_sleep_15",
        name="Display Sleep = 15 Minuten",
        desc="Setzt den Monitor-Schlaf-Timer auf 15 Minuten (Netz) und 5 Minuten (Akku) — in allen Plänen "
             "AUSSER 'Höchstleistung' und 'Ultimative Leistung': dort bleibt der Bildschirm im Netzbetrieb an.",
        category="Windows", group="Power Plan",
        ps_command='$re=\'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\'; $n=0; foreach($l in (powercfg /L 2>$null)){ $m=[regex]::Match($l,$re); if(-not $m.Success){ continue }; if($l -match \'Ultimat\' -or $l -match \'8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c\'){ continue }; powercfg /SETACVALUEINDEX $m.Value SUB_VIDEO VIDEOIDLE 900 2>$null | Out-Null; powercfg /SETDCVALUEINDEX $m.Value SUB_VIDEO VIDEOIDLE 300 2>$null | Out-Null; $n++ }; powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null; Write-Output "$n Energieplan(e) gesetzt (Hoechstleistung/Ultimativ bleiben: nie)"',
        revert_cmd='$re=\'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\'; $n=0; foreach($l in (powercfg /L 2>$null)){ $m=[regex]::Match($l,$re); if(-not $m.Success){ continue }; if($l -match \'Ultimat\' -or $l -match \'8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c\'){ continue }; powercfg /SETACVALUEINDEX $m.Value SUB_VIDEO VIDEOIDLE 600 2>$null | Out-Null; powercfg /SETDCVALUEINDEX $m.Value SUB_VIDEO VIDEOIDLE 120 2>$null | Out-Null; $n++ }; powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null; Write-Output "$n Energieplan(e) gesetzt (Hoechstleistung/Ultimativ bleiben: nie)"',
        tags=["power"],
    ),
    Tweak(
        id="power_sleep_off",
        name="System-Schlafmodus deaktivieren",
        desc="Deaktiviert den System-Schlafmodus komplett. Der PC schläft nicht mehr nach Inaktivität ein — empfohlen für Desktops, die im Hintergrund weiterlaufen sollen (Downloads, Server).",
        category="Windows", group="Power Plan",
        ps_command=_power_all("SUB_SLEEP", "STANDBYIDLE", 0, 0),
        revert_cmd=_power_all("SUB_SLEEP", "STANDBYIDLE", 3600, 1800),
        tags=["power"],
    ),
    Tweak(
        id="power_cpu_min_100",
        name="CPU Minimum Processor State = 100%",
        desc="Setzt den minimalen CPU-Zustand auf 100%. Die CPU regelt nicht mehr herunter — das eliminiert die kurze Verzögerung beim Hochtakten aus dem Idle. Gut für konstante FPS, erhöht aber Idle-Verbrauch und Temperatur.",
        category="Windows", group="Power Plan",
        ps_command=_power_all("SUB_PROCESSOR", "PROCTHROTTLEMIN", 100, 100),
        revert_cmd=_power_all("SUB_PROCESSOR", "PROCTHROTTLEMIN", 5, 5),
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
    Tweak(
        id="amd_shader_cache",
        name="AMD: Shader-Cache unbegrenzt",
        desc="Nur AMD: Setzt den AMD-Shader-Cache auf maximale Größe. Verhindert Cache-Eviction und damit erneutes Kompilieren von Shadern — reduziert Stutter besonders in OpenGL/Vulkan-Titeln.",
        category="Gaming", group="AMD GPU",
        ps_command=_AMD_SHADER_APPLY,
        revert_cmd=_AMD_SHADER_REVERT,
        requires_amd=True, requires_reboot=True,
        tags=["gpu", "amd"],
    ),
    Tweak(
        id="amd_antilag",
        name="AMD: Anti-Lag (Low Latency Mode)",
        desc="Nur AMD: Aktiviert AMD Anti-Lag via Registry. Reduziert den Abstand zwischen CPU-Input und GPU-Ausgabe — ähnlich wie NVIDIA Reflex. Wirkt vor allem bei CPU-limitierten Spielen (RX 5000+).",
        category="Gaming", group="AMD GPU",
        ps_command=_AMD_ANTILAG_APPLY,
        revert_cmd=_AMD_ANTILAG_REVERT,
        requires_amd=True, requires_reboot=True,
        tags=["gpu", "amd", "latency"],
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
        ps_command="$s=Get-Service SysMain -EA SilentlyContinue; $was=$(if($s){ [string]$s.StartType } else { '' }); if($was -eq 'Disabled'){ Set-Service SysMain -StartupType Manual -EA SilentlyContinue; Start-Service SysMain -EA SilentlyContinue }; $err=$null; try { Disable-MMAgent -MemoryCompression -EA Stop } catch { $err=$_.Exception.Message }; if($was -eq 'Disabled'){ Stop-Service SysMain -Force -EA SilentlyContinue; Set-Service SysMain -StartupType Disabled -EA SilentlyContinue }; if($err){ Write-Output $err; exit 1 }; if($was -eq 'Disabled'){ Write-Output 'SysMain kurz gestartet und wieder deaktiviert' }",
        revert_cmd="$s=Get-Service SysMain -EA SilentlyContinue; $was=$(if($s){ [string]$s.StartType } else { '' }); if($was -eq 'Disabled'){ Set-Service SysMain -StartupType Manual -EA SilentlyContinue; Start-Service SysMain -EA SilentlyContinue }; $err=$null; try { Enable-MMAgent -MemoryCompression -EA Stop } catch { $err=$_.Exception.Message }; if($was -eq 'Disabled'){ Stop-Service SysMain -Force -EA SilentlyContinue; Set-Service SysMain -StartupType Disabled -EA SilentlyContinue }; if($err){ Write-Output $err; exit 1 }; if($was -eq 'Disabled'){ Write-Output 'SysMain kurz gestartet und wieder deaktiviert' }",
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
        id="nvme_queue_depth",
        name="NVMe: Queue-Tiefe & Idle-Stromsparen",
        desc="Setzt für NVMe-SSDs eine StorPort-Queue-Tiefe von 32 und eine höhere Interrupt-Priorität und "
             "schaltet das Idle-Stromsparen des NVMe-Treibers ab (geringere Latenz, etwas mehr Strom). "
             "Ehrlich: Die Wirkung hängt vom Treiber ab und ist meist nur in Benchmarks messbar. "
             "Ohne NVMe-Laufwerk ausgegraut.",
        category="Windows", group="Speicher & RAM",
        ps_command=_NVME_QD_APPLY,
        revert_cmd=_NVME_QD_REVERT,
        requires_nvme=True, requires_reboot=True, risk="moderate",
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
        id="w11_remove_chat_icon",
        name="Win11: Chat-Symbol aus der Taskleiste",
        desc="Entfernt das Teams-Chat-Symbol aus der Taskleiste (verhindert ungewollte Teams-Installation). "
             "Aktuelle Builds haben das Symbol meist nicht mehr — dann ändert der Tweak nichts.",
        category="Windows", group="Windows 11",
        ps_command=r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v TaskbarMn /t REG_DWORD /d 0 /f',
        revert_cmd=r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v TaskbarMn /t REG_DWORD /d 1 /f',
        risk="safe",
    ),
    Tweak(
        id="w11_hide_recommended",
        name="Win11: 'Empfohlen' im Startmenü ausblenden",
        desc="Blendet den Bereich 'Empfohlen' (zuletzt geöffnete Dateien/Apps) im Startmenü per "
             "Richtlinie aus. Ehrlich: nicht auf allen Editionen/Builds garantiert.",
        category="Windows", group="Windows 11",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v HideRecommendedSection /t REG_DWORD /d 1 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v HideRecommendedSection /f 2>$null; exit 0',
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
        desc="Schaltet die KI-Funktionen in Paint per offizieller Richtlinie ab: Cocreator, Image Creator, "
             "generatives Füllen — dazu generatives Löschen und Hintergrund entfernen.",
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
    Tweak(
        id="tcp_optimize",
        name="TCP optimieren (ECN & Timestamps aus, SACK an)",
        desc="Schaltet ECN und TCP-Timestamps ab und SACK ein — etwas weniger Overhead pro Paket. Ehrlich: "
             "Der Effekt auf den Ping ist klein; ECN-Abschalten hilft vor allem hinter Routern, die "
             "ECN-Pakete falsch behandeln.",
        category="Network", group="TCP",
        ps_command=r'''
netsh int tcp set global ecncapability=disabled | Out-Null
netsh int tcp set global timestamps=disabled | Out-Null
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v SackOpts /t REG_DWORD /d 1 /f | Out-Null
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v TcpMaxDupAcks /t REG_DWORD /d 2 /f
''',
        revert_cmd=r'''
netsh int tcp set global ecncapability=default | Out-Null
netsh int tcp set global timestamps=default | Out-Null
reg delete "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v SackOpts /f 2>$null
reg delete "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v TcpMaxDupAcks /f 2>$null
exit 0
''',
        risk="safe",
    ),
    Tweak(
        id="disable_qos_limit",
        name="QoS-Bandbreitenreserve auf 0 %",
        desc="Setzt die QoS-Richtlinie 'Reservierbare Bandbreite' auf 0 %. Ehrlich: Windows reserviert "
             "entgegen verbreiteter Annahme NICHT dauerhaft 20 % — die Reserve greift nur, wenn eine "
             "QoS-Anwendung Bandbreite anfordert. Meist ohne messbaren Effekt, schadet aber nicht.",
        category="Network", group="TCP",
        ps_command=r'reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Psched" /v NonBestEffortLimit /t REG_DWORD /d 0 /f',
        revert_cmd=r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\Psched" /v NonBestEffortLimit /f 2>$null; exit 0',
        risk="safe",
    ),

    # ── Audio ─────────────────────────────────────────────────────────
    Tweak(
        id="mmcss_audio_profile",
        name="MMCSS-Audioprofil optimieren",
        desc="Setzt den MMCSS-Task 'Audio' auf latenzempfindlich mit hoher Scheduling-Priorität — weniger "
             "Knacken und Aussetzer unter CPU-Last. (Ergänzt 'MMCSS Audio Priority', das den Task "
             "'Pro Audio' betrifft.)",
        category="Audio", group="Performance",
        ps_command=r'''
$p='HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio'
reg add $p /v "Latency Sensitive" /t REG_SZ /d True /f | Out-Null
reg add $p /v "Scheduling Category" /t REG_SZ /d High /f | Out-Null
reg add $p /v "SFIO Priority" /t REG_SZ /d High /f
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
        desc="Setzt SystemResponsiveness auf 0 — MMCSS hält dann keine CPU-Zeit mehr für "
             "Hintergrundaufgaben frei, Audio und Spiele bekommen mehr. Gegen Aussetzer bei Spielen + "
             "Streamen. (Den Wert nutzt auch 'Network Throttling Index' — zurückgesetzt wird er erst, "
             "wenn keiner der beiden Tweaks ihn mehr braucht.)",
        category="Audio", group="Performance",
        ps_command=r'''
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 0 /f | Out-Null
reg add "HKLM\SOFTWARE\GameOptimizerPro" /v SR_AudioPriority /t REG_DWORD /d 1 /f
''',
        revert_cmd=_SR_AUDIO_REVERT,
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
