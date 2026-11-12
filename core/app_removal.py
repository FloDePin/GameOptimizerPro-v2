"""
GameOptimizerPro — Store apps: choose which ones to remove

Lists the installed Store apps a user can see (an entry in Start, or a known preinstalled app) with a
plain name and a rating:
  bloat     preinstalled extras (news, weather, games, Clipchamp …) — safe to remove
  optional  apps some people use (Photos, Camera, Snipping Tool, Xbox app …) — asks first and says
            what goes missing
  other     everything else (often installed by the user) — the user decides
Never listed (and refused by remove()): the Store and App Installer (winget), Windows Security, Edge,
Terminal, frameworks and runtimes, codecs and image extensions, language packs, Gaming Services,
driver apps (NVIDIA, AMD, Intel, Realtek, Dolby, Waves) and Windows' own parts (signed "System" or
marked not removable) — removing them breaks Windows features, games or other apps.

Removing: for every user AND the provisioned copy (a feature update or a new user would bring the app
back otherwise), one app at a time. The page makes a System Restore point first — only that brings a
removed app back (the same rule as the app-removal tweaks).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

from core.i18n import tr as _tr

BLOAT, OPTIONAL, OTHER = "bloat", "optional", "other"
CATEGORY_ORDER = {BLOAT: 0, OPTIONAL: 1, OTHER: 2}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")

# Never offered — Windows, games or other apps need them.
_PROTECTED_EXACT = {
    "Microsoft.WindowsStore", "Microsoft.StorePurchaseApp", "Microsoft.DesktopAppInstaller",
    "Microsoft.Winget.Source", "Microsoft.SecHealthUI", "Microsoft.WindowsTerminal",
    "Microsoft.ApplicationCompatibilityEnhancements", "Microsoft.GamingServices",
    "Microsoft.Services.Store.Engagement", "Microsoft.AAD.BrokerPlugin", "Microsoft.AccountsControl",
    "Microsoft.Windows.ShellExperienceHost", "Microsoft.Windows.StartMenuExperienceHost",
    "windows.immersivecontrolpanel", "Microsoft.Windows.CloudExperienceHost",
}
_PROTECTED_PREFIX = (
    "Microsoft.MicrosoftEdge", "Microsoft.LanguageExperiencePack", "Microsoft.WinAppRuntime",
    "MicrosoftCorporationII.WinAppRuntime", "Microsoft.WindowsAppRuntime", "Microsoft.VCLibs",
    "Microsoft.UI.Xaml", "Microsoft.NET.", "Microsoft.DirectXRuntime",
    # driver companion apps: the settings of the graphics / audio driver live there
    "NVIDIACorp.", "AdvancedMicroDevicesInc", "AppUp.Intel", "RealtekSemiconductorCorp.",
    "DolbyLaboratories.", "WavesAudio.",
)
# codecs and image extensions (HEVC, AV1, HEIF, WebP, raw images …): videos and photos stop opening
_PROTECTED_SUFFIX = ("VideoExtension", "VideoExtensions", "ImageExtension", "MediaExtensions",
                     "AudioExtensions")

# name -> (category, German name, English name, German note, English note)
KNOWN: dict[str, tuple[str, str, str, str, str]] = {
    # ── preinstalled extras ─────────────────────────────────────────────────
    "Microsoft.BingNews": (BLOAT, "Microsoft Nachrichten", "Microsoft News", "", ""),
    "Microsoft.BingWeather": (BLOAT, "Wetter", "Weather", "", ""),
    "Microsoft.BingSearch": (BLOAT, "Bing-Suche", "Bing Search", "", ""),
    "Microsoft.BingFinance": (BLOAT, "Finanzen", "Finance", "", ""),
    "Microsoft.BingSports": (BLOAT, "Sport", "Sports", "", ""),
    "Microsoft.GetHelp": (OPTIONAL, "Hilfe anfordern", "Get Help",
                          "Die Problembehandlungen in den Einstellungen laufen darüber.",
                          "The troubleshooters in Settings run through it."),
    "Microsoft.Getstarted": (BLOAT, "Tipps", "Tips", "", ""),
    "Microsoft.MicrosoftSolitaireCollection": (BLOAT, "Solitaire Collection", "Solitaire Collection", "", ""),
    "Microsoft.MicrosoftOfficeHub": (BLOAT, "Microsoft 365 Copilot (Office)", "Microsoft 365 Copilot (Office)",
                                     "Office im Browser bleibt nutzbar.", "Office in the browser keeps working."),
    "Microsoft.Office.Sway": (BLOAT, "Sway", "Sway", "", ""),
    "Microsoft.PowerAutomateDesktop": (BLOAT, "Power Automate", "Power Automate", "", ""),
    "Microsoft.Todos": (BLOAT, "Microsoft To Do", "Microsoft To Do", "", ""),
    "Microsoft.WindowsFeedbackHub": (BLOAT, "Feedback-Hub", "Feedback Hub", "", ""),
    "Microsoft.WindowsMaps": (BLOAT, "Karten", "Maps", "", ""),
    "Microsoft.MixedReality.Portal": (BLOAT, "Mixed-Reality-Portal", "Mixed Reality Portal", "", ""),
    "Microsoft.Microsoft3DViewer": (BLOAT, "3D-Viewer", "3D Viewer", "", ""),
    "Microsoft.MSPaint": (BLOAT, "Paint 3D", "Paint 3D", "Das normale Paint bleibt.", "The regular Paint stays."),
    "Microsoft.People": (BLOAT, "Kontakte", "People", "", ""),
    "Microsoft.windowscommunicationsapps": (BLOAT, "Mail und Kalender (eingestellt)", "Mail and Calendar (retired)",
                                            "Von Microsoft eingestellt, Nachfolger ist das neue Outlook.",
                                            "Retired by Microsoft, the new Outlook replaces it."),
    "Microsoft.ZuneVideo": (BLOAT, "Filme & TV", "Movies & TV", "", ""),
    "Microsoft.SkypeApp": (BLOAT, "Skype (eingestellt)", "Skype (retired)", "", ""),
    "Microsoft.Wallet": (BLOAT, "Wallet", "Wallet", "", ""),
    "Microsoft.Messaging": (BLOAT, "Nachrichten (alt)", "Messaging (old)", "", ""),
    "Microsoft.OneConnect": (BLOAT, "Mobilfunktarife", "Mobile Plans", "", ""),
    "Microsoft.549981C3F5F10": (BLOAT, "Cortana", "Cortana", "", ""),
    "Microsoft.Windows.DevHome": (BLOAT, "Dev Home (eingestellt)", "Dev Home (retired)", "", ""),
    "Microsoft.XboxApp": (BLOAT, "Xbox-Konsolenbegleiter (alt)", "Xbox Console Companion (old)", "", ""),
    "Microsoft.XboxSpeechToTextOverlay": (BLOAT, "Xbox Sprache-zu-Text", "Xbox Speech to Text", "", ""),
    "Clipchamp.Clipchamp": (BLOAT, "Clipchamp", "Clipchamp", "", ""),
    "MicrosoftCorporationII.MicrosoftFamily": (BLOAT, "Microsoft Family", "Microsoft Family", "", ""),
    "king.com.CandyCrushSaga": (BLOAT, "Candy Crush Saga", "Candy Crush Saga", "", ""),
    "king.com.CandyCrushSodaSaga": (BLOAT, "Candy Crush Soda Saga", "Candy Crush Soda Saga", "", ""),
    "king.com.BubbleWitch3Saga": (BLOAT, "Bubble Witch 3", "Bubble Witch 3", "", ""),
    "BytedancePte.Ltd.TikTok": (BLOAT, "TikTok", "TikTok", "", ""),
    "Facebook.Facebook": (BLOAT, "Facebook", "Facebook", "", ""),
    "Facebook.InstagramBeta": (BLOAT, "Instagram", "Instagram", "", ""),
    "7EE7776C.LinkedInforWindows": (BLOAT, "LinkedIn", "LinkedIn", "", ""),
    # ── apps some people use ────────────────────────────────────────────────
    "Microsoft.Windows.Photos": (OPTIONAL, "Fotos", "Photos",
                                 "Standard-Bildbetrachter — Bilder öffnen danach in einer anderen App.",
                                 "The default image viewer — pictures open in another app afterwards."),
    "Microsoft.WindowsCamera": (OPTIONAL, "Kamera", "Camera", "Für Webcam-Fotos und -Videos.",
                                "For webcam photos and videos."),
    "Microsoft.WindowsCalculator": (OPTIONAL, "Rechner", "Calculator", "", ""),
    "Microsoft.WindowsAlarms": (OPTIONAL, "Uhr", "Clock", "Wecker, Timer, Stoppuhr, Fokussitzungen.",
                                "Alarms, timers, stopwatch, focus sessions."),
    "Microsoft.WindowsSoundRecorder": (OPTIONAL, "Audiorekorder", "Sound Recorder", "", ""),
    "Microsoft.WindowsNotepad": (OPTIONAL, "Editor", "Notepad", "Der Texteditor von Windows.",
                                 "Windows' text editor."),
    "Microsoft.Paint": (OPTIONAL, "Paint", "Paint", "", ""),
    "Microsoft.ScreenSketch": (OPTIONAL, "Snipping Tool", "Snipping Tool",
                               "Bildschirmfotos mit Win+Umschalt+S und der Druck-Taste gehen danach nicht mehr.",
                               "Screenshots with Win+Shift+S and the Print key stop working."),
    "Microsoft.MicrosoftStickyNotes": (OPTIONAL, "Kurznotizen", "Sticky Notes", "", ""),
    "Microsoft.YourPhone": (OPTIONAL, "Smartphone-Link", "Phone Link", "Verbindet das Handy mit dem PC.",
                            "Connects the phone to the PC."),
    "MicrosoftWindows.CrossDevice": (OPTIONAL, "Geräteübergreifende Funktionen", "Cross-device experience host",
                                     "Teil von Smartphone-Link (Handy im Startmenü, Dateien teilen).",
                                     "Part of Phone Link (phone in Start, sharing files)."),
    "Microsoft.ZuneMusic": (OPTIONAL, "Medienwiedergabe", "Media Player",
                            "Der Standard-Player für Musik und Videos.", "The default player for music and videos."),
    "Microsoft.OutlookForWindows": (OPTIONAL, "Outlook (neu)", "Outlook (new)", "", ""),
    "MSTeams": (OPTIONAL, "Microsoft Teams", "Microsoft Teams", "", ""),
    "Microsoft.Copilot": (OPTIONAL, "Copilot", "Copilot", "", ""),
    "Microsoft.Office.OneNote": (OPTIONAL, "OneNote", "OneNote", "", ""),
    "MicrosoftCorporationII.QuickAssist": (OPTIONAL, "Schnellhilfe", "Quick Assist",
                                           "Fernhilfe, z. B. von Freunden oder Familie.",
                                           "Remote help, e.g. from friends or family."),
    "MicrosoftWindows.Client.WebExperience": (OPTIONAL, "Widgets", "Widgets", "Die Widgets-Leiste (Win+W).",
                                              "The widgets board (Win+W)."),
    "Microsoft.GamingApp": (OPTIONAL, "Xbox-App", "Xbox app",
                            "Game Pass und PC-Spiele aus dem Xbox-Katalog brauchen sie.",
                            "Game Pass and PC games from the Xbox catalog need it."),
    "Microsoft.XboxGamingOverlay": (OPTIONAL, "Xbox Game Bar", "Xbox Game Bar",
                                    "Aufnahmen, Leistungsanzeige und Xbox-Chat im Spiel (Win+G).",
                                    "Recordings, performance overlay and Xbox chat in games (Win+G)."),
    "Microsoft.XboxGameOverlay": (OPTIONAL, "Xbox Game Bar (Plug-in)", "Xbox Game Bar (plug-in)", "", ""),
    "Microsoft.XboxIdentityProvider": (OPTIONAL, "Xbox-Identitätsanbieter", "Xbox Identity Provider",
                                       "Die Xbox-Anmeldung von Game-Pass- und Store-Spielen hängt daran.",
                                       "The Xbox sign-in of Game Pass and Store games depends on it."),
    "Microsoft.Xbox.TCUI": (OPTIONAL, "Xbox TCUI", "Xbox TCUI",
                            "Xbox-Freundesliste und -Profil in Spielen.", "Xbox friends list and profile in games."),
    "Microsoft.Edge.GameAssist": (OPTIONAL, "Edge Game Assist", "Edge Game Assist", "", ""),
    "SpotifyAB.SpotifyMusic": (OPTIONAL, "Spotify", "Spotify", "", ""),
    "4DF9E0F8.Netflix": (OPTIONAL, "Netflix", "Netflix", "", ""),
    "AmazonVideo.PrimeVideo": (OPTIONAL, "Prime Video", "Prime Video", "", ""),
    "Disney.37853FC22B2CE": (OPTIONAL, "Disney+", "Disney+", "", ""),
}


@dataclass
class AppInfo:
    name:        str          # package name, e.g. Microsoft.BingWeather
    family:      str          # package family name
    display:     str          # plain name (Start menu name, else known name, else the package name)
    publisher:   str
    version:     str
    provisioned: bool         # also provisioned for new users
    category:    str          # bloat | optional | other
    note:        str          # what goes missing (optional apps)


def is_protected(name: str) -> bool:
    if name in _PROTECTED_EXACT or name.startswith(_PROTECTED_PREFIX):
        return True
    return name.startswith("Microsoft.") and name.endswith(_PROTECTED_SUFFIX)


def classify(name: str) -> tuple[str, str]:
    """(category, note) in the app's language."""
    k = KNOWN.get(name)
    if k:
        return k[0], _tr(k[3], k[4])
    if name.startswith("king.com."):
        return BLOAT, ""
    return OTHER, ""


def known_name(name: str) -> str:
    k = KNOWN.get(name)
    return _tr(k[1], k[2]) if k else ""


_LIST_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$pk=@(if($admin){ Get-AppxPackage -AllUsers -PackageTypeFilter Main } else { Get-AppxPackage -PackageTypeFilter Main })
$prov=@(); if($admin){ $prov=@(Get-AppxProvisionedPackage -Online | ForEach-Object { $_.DisplayName }) }
$start=@{}; foreach($s in @(Get-StartApps)){ $f=($s.AppID -split '!')[0]; if($f -and -not $start.ContainsKey($f)){ $start[$f]=$s.Name } }
$seen=@{}
$out=@(foreach($p in $pk){
  if($p.IsFramework -or $p.NonRemovable -or "$($p.SignatureKind)" -eq 'System' -or $seen.ContainsKey($p.Name)){ continue }
  $seen[$p.Name]=1
  [pscustomobject]@{ name=$p.Name; family=$p.PackageFamilyName; version=[string]$p.Version; publisher=[string]$p.Publisher;
                     display=[string]$start[$p.PackageFamilyName]; provisioned=[bool]($prov -contains $p.Name) }
})
ConvertTo-Json -InputObject $out -Compress -Depth 3
"""


def _run_ps(script: str, timeout: int = 120) -> tuple[int, str]:
    """(exit code, stdout) of a hidden PowerShell — replaced by the tests."""
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", script], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def parse_list(raw: str) -> list[AppInfo]:
    """The listing's JSON -> the apps a user can see and may remove, sorted (bloat first)."""
    try:
        rows = json.loads(raw.strip() or "[]")
    except ValueError:
        return []
    if isinstance(rows, dict):
        rows = [rows]
    apps = []
    for r in rows if isinstance(rows, list) else []:
        name = str(r.get("name") or "")
        if not name or not _SAFE_NAME.match(name) or is_protected(name):
            continue
        start_name = str(r.get("display") or "").strip()
        if not start_name and name not in KNOWN and not name.startswith("king.com."):
            continue                       # no Start entry, not a known app: a part of something else
        cat, note = classify(name)
        apps.append(AppInfo(name=name, family=str(r.get("family") or ""),
                            display=start_name or known_name(name) or name,
                            publisher=re.sub(r",.*$", "", str(r.get("publisher") or "")).replace("CN=", ""),
                            version=str(r.get("version") or ""), provisioned=bool(r.get("provisioned")),
                            category=cat, note=note))
    apps.sort(key=lambda a: (CATEGORY_ORDER.get(a.category, 9), a.display.lower()))
    return apps


def list_apps() -> list[AppInfo]:
    if os.name != "nt":
        return []
    _rc, out = _run_ps(_LIST_PS)
    i = out.find("[")
    return parse_list(out[i:] if i >= 0 else "[]")


def _remove_ps(name: str) -> str:
    return (
        f"$n='{name}'; $err=''; "
        "foreach($p in @(Get-AppxPackage -AllUsers -Name $n -EA SilentlyContinue)){ "
        "try { Remove-AppxPackage -Package $p.PackageFullName -AllUsers -EA Stop } catch { $err=$_.Exception.Message } }; "
        "foreach($q in @(Get-AppxProvisionedPackage -Online -EA SilentlyContinue | Where-Object { $_.DisplayName -eq $n })){ "
        "try { Remove-AppxProvisionedPackage -Online -PackageName $q.PackageName -EA Stop | Out-Null } "
        "catch { if(-not $err){ $err=$_.Exception.Message } } }; "
        "$left=@(Get-AppxPackage -AllUsers -Name $n -EA SilentlyContinue).Count; "
        "if($left -eq 0){ Write-Output 'GOP-OK' } else { Write-Output ('GOP-LEFT ' + $err) }"
    )


def remove(name: str) -> tuple[bool, str]:
    """Remove one app for every user plus its provisioned copy. Needs administrator rights."""
    if not _SAFE_NAME.match(name or ""):
        return False, _tr("Ungültiger Paketname", "Invalid package name")
    if is_protected(name):
        return False, _tr("Geschützt — Windows oder andere Apps brauchen es", "Protected — Windows or other apps need it")
    try:
        _rc, out = _run_ps(_remove_ps(name), timeout=300)
    except subprocess.TimeoutExpired:
        return False, _tr("Zeitüberschreitung (5 min)", "Timed out (5 min)")
    except OSError as e:
        return False, str(e)
    if "GOP-OK" in out:
        return True, ""
    msg = out.split("GOP-LEFT", 1)[1].strip() if "GOP-LEFT" in out else out.strip()
    return False, (msg.splitlines()[0][:200] if msg else _tr("noch installiert", "still installed"))
