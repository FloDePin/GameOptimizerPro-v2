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
    requires_reboot: bool = False
    risk:        str = "safe"   # "safe" | "moderate" | "advanced"
    tags:        list = field(default_factory=list)


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
Get-AppxPackage -AllUsers "*MicrosoftTeams*"|Remove-AppxPackage -ErrorAction SilentlyContinue
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Communications" /v ConfigureChatAutoInstall /t REG_DWORD /d 0 /f
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
        ps_command='''
Stop-Process -Name "OneDrive" -Force -ErrorAction SilentlyContinue
Start-Sleep 1
$od="$env:SYSTEMROOT\\SysWOW64\\OneDriveSetup.exe"
if(!(Test-Path $od)){$od="$env:SYSTEMROOT\\System32\\OneDriveSetup.exe"}
if(Test-Path $od){& $od /uninstall}
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v OneDrive /f 2>$null
''',
    ),
    Tweak(
        id="remove_recall",
        name="Remove Windows Recall",
        desc="Deaktiviert Windows Recall — macht keine Screenshots deiner Aktivitäten mehr. Datenschutzkritisch.",
        category="Windows", group="Bloatware",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI" /v DisableAIDataAnalysis /t REG_DWORD /d 1 /f
Disable-WindowsOptionalFeature -Online -FeatureName "Recall" -NoRestart -ErrorAction SilentlyContinue | Out-Null
''',
        revert_cmd='reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI" /v DisableAIDataAnalysis /f 2>$null',
    ),
    Tweak(
        id="remove_bloatware",
        name="Remove Bloatware (Candy Crush etc.)",
        desc="Entfernt vorinstallierte Apps: Candy Crush, TikTok, Disney+, Facebook, Spotify, News, Solitaire, Clipchamp, ToDo, Paint3D u.v.m.",
        category="Windows", group="Bloatware",
        ps_command='''
$bloat=@("*king.com*","*Facebook*","*Spotify*","*Disney*","*TikTok*","*Instagram*",
"*Netflix*","*Twitter*","*BubbleWitch*","*CandyCrush*","*Microsoft.News*",
"*Microsoft.BingWeather*","*Microsoft.BingNews*","*Microsoft.MicrosoftSolitaireCollection*",
"*Microsoft.ZuneMusic*","*Microsoft.ZuneVideo*","*Microsoft.WindowsFeedbackHub*",
"*Microsoft.Todos*","*Microsoft.Paint3D*","*Clipchamp*","*Microsoft.GetHelp*",
"*Microsoft.Getstarted*","*Microsoft.PowerAutomateDesktop*")
foreach($a in $bloat){Get-AppxPackage -AllUsers $a|Remove-AppxPackage -ErrorAction SilentlyContinue}
''',
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

    # ══════════════════════════════════════════════════════════════
    # WINDOWS — PERFORMANCE
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="ultimate_performance",
        name="Ultimate Performance Plan",
        desc="Aktiviert den 'Ultimative Leistung' Energiesparplan. CPU-Kerne werden nicht mehr gedrosselt. Erhöht Stromverbrauch.",
        category="Windows", group="Performance",
        ps_command='''
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null
$plan=powercfg -list|Select-String "Ultimative Leistung|Ultimate Performance"|Select-Object -First 1
if($plan){$guid=$plan.ToString().Split()[3];if($guid){powercfg -setactive $guid}}
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
bcdedit /set useplatformclock true
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
        ps_command='reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak" /v NVLatency /t REG_DWORD /d 1 /f',
        revert_cmd='reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Services\\nvlddmkm\\Global\\NVTweak" /v NVLatency /f 2>$null',
    ),
    Tweak(
        id="enable_msi_mode",
        name="Enable MSI Mode (Interrupts)",
        desc="Aktiviert Message Signaled Interrupts für GPU und NVMe. Reduziert Interrupt-Latenz erheblich. Reboot nötig.",
        category="Gaming", group="GPU & Driver",
        ps_command='''
$dev=Get-WmiObject Win32_VideoController|Where-Object{$_.Name -notmatch "Microsoft"}|Select-Object -First 1
if($dev){
  $p="HKLM\\SYSTEM\\CurrentControlSet\\Enum\\$($dev.PNPDeviceID)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"
  reg add $p /v MSISupported /t REG_DWORD /d 1 /f
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
        name="Enable DirectX 12 Optimization",
        desc="Optimiert DX12 Multi-Threading, reduziert Draw-Call-Overhead. Wirksam bei modernen AAA-Spielen.",
        category="Gaming", group="GPU & Driver",
        ps_command='''
reg add "HKLM\\SOFTWARE\\Microsoft\\DirectX" /v D3D12_ENABLE_UNSAFE_COMMAND_BUFFER_REUSE /t REG_DWORD /d 1 /f
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDelay /t REG_DWORD /d 10 /f
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers" /v TdrDdiDelay /t REG_DWORD /d 10 /f
''',
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
        revert_cmd='''
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v NetworkThrottlingIndex /t REG_DWORD /d 10 /f
reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 20 /f
''',
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
        desc="Aktiviert RSS auf allen Adaptern. Verteilt Netzwerkverarbeitung auf mehrere CPU-Kerne. Besser bei schnellen Verbindungen.",
        category="Network", group="TCP",
        ps_command='''
$adapters=Get-NetAdapter|Where-Object{$_.Status -eq "Up"}
foreach($a in $adapters){Enable-NetAdapterRss -Name $a.Name -ErrorAction SilentlyContinue}
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
        ps_command='reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Dsh" /v AllowNewsAndInterests /t REG_DWORD /d 0 /f',
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
        desc="Setzt den Energiesparplan auf 'Ausbalanciert' (Windows Standard).",
        category="Windows", group="Power Plan",
        ps_command='powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
    ),
    Tweak(
        id="power_high",
        name="Power Plan: High Performance",
        desc="Aktiviert 'Hohe Leistung'. Guter Kompromiss zwischen Performance und Stromverbrauch.",
        category="Windows", group="Power Plan",
        ps_command='powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
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
    ),

    # ══════════════════════════════════════════════════════════════
    # AUDIO
    # ══════════════════════════════════════════════════════════════

    Tweak(
        id="disable_audio_enhancements",
        name="Disable Audio Enhancements",
        desc="Deaktiviert Windows Audio-Verbesserungen (Bass Boost, EQ etc.). "
             "Reduziert Audio-Latenz und CPU-Last. Empfohlen fur Gaming.",
        category="Audio", group="Latency",
        ps_command=(
            "Get-ChildItem 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render'"
            " -Recurse -EA SilentlyContinue | Where-Object {$_.Name -like '*Properties*'} |"
            " ForEach-Object {"
            " Set-ItemProperty -Path $_.PSPath"
            " -Name '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5' -Value 0 -EA SilentlyContinue }"
        ),
        risk="safe",
    ),

    Tweak(
        id="disable_audio_exclusive_lock",
        name="Disable Exclusive Audio Lock",
        desc="Verhindert dass Games das Audiogeraet exklusiv sperren und Discord/Spotify stumm machen.",
        category="Audio", group="Latency",
        ps_command=(
            "Get-ChildItem 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render'"
            " -EA SilentlyContinue | ForEach-Object {"
            " $props = Join-Path $_.PSPath 'Properties';"
            " if (Test-Path $props) {"
            " Set-ItemProperty -Path $props -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},3' -Value 0 -EA SilentlyContinue;"
            " Set-ItemProperty -Path $props -Name '{b3f8fa53-0004-438e-9003-51a46e139bfc},4' -Value 0 -EA SilentlyContinue } }"
        ),
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
            " foreach ($s in $svcs) {"
            " $svc = Get-Service -Name $s -EA SilentlyContinue;"
            " if ($svc) { Stop-Service -Name $s -Force -EA SilentlyContinue;"
            " Set-Service -Name $s -StartupType Disabled -EA SilentlyContinue } }"
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
            "Remove-Item 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"
            "\\Multimedia\\SystemProfile\\Tasks\\Pro Audio' -Recurse -EA SilentlyContinue"
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

]


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
