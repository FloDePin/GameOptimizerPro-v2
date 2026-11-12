"""
GameOptimizerPro — install the usual programs of a gaming PC through winget

A short, hand-picked list (launchers, the runtimes games need, tuning / monitoring tools, chat and
recording, a few tools) installed with Windows' own package manager winget from its official source
— silently, one after the other. Nothing is installed without the user ticking it.

"Installed" = winget knows it (winget export, ~1 s) OR the program's file is where its installer puts
it — programs installed by hand are often not matched by winget (e.g. MSI Afterburner).

Not in the list on purpose: the NVIDIA / AMD graphics driver and the NVIDIA app (not in winget's
source — get them from the manufacturer), programs that refuse to install from an elevated process
(Spotify), anything with bundled offers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field

from core.i18n import tr as _tr

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_\-]*$")

GROUPS = [
    ("launcher", "Spiele-Launcher", "Game launchers"),
    ("runtime",  "Laufzeiten für Spiele", "Runtimes for games"),
    ("tuning",   "Tuning & Monitoring", "Tuning & monitoring"),
    ("chat",     "Chat & Aufnahme", "Chat & recording"),
    ("tools",    "Werkzeuge", "Tools"),
]

_PF, _PF86 = os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
_LAD = os.environ.get("LOCALAPPDATA", "")


@dataclass
class Program:
    id:      str                   # winget id (checked against the winget source)
    name:    str                   # product name (the same in both languages)
    group:   str
    notes:   tuple = ("", "")      # (German, English)
    paths:   tuple = field(default_factory=tuple)    # where its installer puts it (installed by hand)

    @property
    def note(self) -> str:
        return _tr(*self.notes)


CATALOG: list[Program] = [
    # launchers
    Program("Valve.Steam", "Steam", "launcher", paths=(rf"{_PF86}\Steam\steam.exe",)),
    Program("EpicGames.EpicGamesLauncher", "Epic Games Launcher", "launcher",
            paths=(rf"{_PF86}\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",)),
    Program("GOG.Galaxy", "GOG GALAXY", "launcher", paths=(rf"{_PF86}\GOG Galaxy\GalaxyClient.exe",)),
    Program("ElectronicArts.EADesktop", "EA app", "launcher",
            paths=(rf"{_PF}\Electronic Arts\EA Desktop\EA Desktop\EADesktop.exe",)),
    Program("Ubisoft.Connect", "Ubisoft Connect", "launcher",
            paths=(rf"{_PF86}\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe",)),
    Program("Blizzard.BattleNet", "Battle.net", "launcher", paths=(rf"{_PF86}\Battle.net\Battle.net.exe",)),
    # runtimes
    Program("Microsoft.VCRedist.2015+.x64", "Visual C++ 2015–2022 (x64)", "runtime",
            ("Brauchen fast alle Spiele.", "Almost every game needs it.")),
    Program("Microsoft.VCRedist.2015+.x86", "Visual C++ 2015–2022 (x86)", "runtime",
            ("Für 32-Bit-Spiele und -Launcher.", "For 32-bit games and launchers.")),
    Program("Microsoft.DirectX", "DirectX End-User Runtime", "runtime",
            ("Ältere DirectX-9/10/11-Teile, die manche Spiele noch brauchen.",
             "Older DirectX 9/10/11 parts some games still need.")),
    Program("Microsoft.DotNet.DesktopRuntime.8", ".NET Desktop Runtime 8", "runtime",
            ("Für viele Tools und Mod-Manager.", "For many tools and mod managers.")),
    # tuning & monitoring
    Program("Guru3D.Afterburner", "MSI Afterburner", "tuning",
            ("Der GPU-Tuner von GameOptimizerPro braucht es.", "GameOptimizerPro's GPU tuner needs it."),
            paths=(rf"{_PF86}\MSI Afterburner\MSIAfterburner.exe", rf"{_PF}\MSI Afterburner\MSIAfterburner.exe")),
    Program("Guru3D.RTSS", "RivaTuner Statistics Server", "tuning",
            ("FPS-Anzeige und FPS-Limit im Spiel (gehört zu Afterburner).",
             "FPS overlay and FPS limit in games (belongs to Afterburner)."),
            paths=(rf"{_PF86}\RivaTuner Statistics Server\RTSS.exe",)),
    Program("Geeks3D.FurMark.2", "FurMark 2", "tuning",
            ("GPU-Belastungstest; der Stresstest von GameOptimizerPro findet es.",
             "GPU stress test; GameOptimizerPro's stress test finds it."),
            paths=(rf"{_PF}\Geeks3D\FurMark2_x64\furmark.exe", rf"{_PF}\Geeks3D\FurMark2\furmark.exe")),
    Program("REALiX.HWiNFO", "HWiNFO", "tuning",
            ("Alle Sensoren (Temperaturen, Spannungen).", "Every sensor (temperatures, voltages)."),
            paths=(rf"{_PF}\HWiNFO64\HWiNFO64.exe",)),
    Program("CPUID.CPU-Z", "CPU-Z", "tuning", paths=(rf"{_PF}\CPUID\CPU-Z\cpuz.exe",)),
    Program("TechPowerUp.GPU-Z", "GPU-Z", "tuning"),
    Program("CrystalDewWorld.CrystalDiskInfo", "CrystalDiskInfo", "tuning",
            ("Zustand (SMART) der SSDs/HDDs.", "Health (SMART) of the SSDs / HDDs."),
            paths=(rf"{_PF}\CrystalDiskInfo\DiskInfo64.exe",)),
    Program("Wagnardsoft.DisplayDriverUninstaller", "Display Driver Uninstaller (DDU)", "tuning",
            ("Entfernt Grafiktreiber restlos — nur für eine saubere Neuinstallation, am besten im abgesicherten Modus.",
             "Removes graphics drivers completely — only for a clean reinstall, ideally in safe mode.")),
    # chat & recording
    Program("Discord.Discord", "Discord", "chat", paths=(rf"{_LAD}\Discord\Update.exe",)),
    Program("TeamSpeakSystems.TeamSpeakClient", "TeamSpeak 3", "chat",
            paths=(rf"{_PF}\TeamSpeak 3 Client\ts3client_win64.exe",)),
    Program("OBSProject.OBSStudio", "OBS Studio", "chat", ("Aufnehmen und Streamen.", "Recording and streaming."),
            paths=(rf"{_PF}\obs-studio\bin\64bit\obs64.exe",)),
    # tools
    Program("7zip.7zip", "7-Zip", "tools", paths=(rf"{_PF}\7-Zip\7zFM.exe",)),
    Program("VideoLAN.VLC", "VLC media player", "tools", paths=(rf"{_PF}\VideoLAN\VLC\vlc.exe",)),
    Program("Mozilla.Firefox", "Firefox", "tools", paths=(rf"{_PF}\Mozilla Firefox\firefox.exe",)),
    # older installs stay in the 32-bit folder; without admin rights Chrome installs for the user only
    Program("Google.Chrome", "Google Chrome", "tools",
            paths=(rf"{_PF}\Google\Chrome\Application\chrome.exe", rf"{_PF86}\Google\Chrome\Application\chrome.exe",
                   rf"{_LAD}\Google\Chrome\Application\chrome.exe")),
    Program("Brave.Brave", "Brave", "tools"),
    Program("Notepad++.Notepad++", "Notepad++", "tools", paths=(rf"{_PF}\Notepad++\notepad++.exe",)),
    Program("Microsoft.PowerToys", "PowerToys", "tools"),
    Program("ShareX.ShareX", "ShareX", "tools", ("Bildschirmfotos und kurze Aufnahmen.", "Screenshots and short recordings.")),
]

# winget results that mean "nothing to do / done" (hex as winget documents them)
_OK_CODES = {
    0,
    0x8A15002B,     # no applicable upgrade: installed and up to date
    0x8A150061,     # package already installed
    0x8A150109,     # installed, a restart finishes it
}


def winget_exe() -> str | None:
    p = shutil.which("winget")
    if p:
        return p
    cand = os.path.join(_LAD, "Microsoft", "WindowsApps", "winget.exe") if _LAD else ""
    return cand if cand and os.path.exists(cand) else None


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TAIL_S = 10.0       # after winget ended: how long the rest of its output may take


def _kill_tree(p: subprocess.Popen):
    """winget AND what it started: a hanging setup under it keeps the output pipe open, so
    killing winget alone would not end the read."""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=30,
                       creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def _run(args: list[str], timeout: int = 900, on_line=None) -> tuple[int, str]:
    """(exit code as an unsigned 32-bit number, output) — replaced by the tests.
    The output is read in a thread of its own and the time limit watched here: reading in this
    thread waited for the end of the output, so a setup that hung (and kept the output open) was
    never timed out. on_line is called from that reader thread."""
    exe = winget_exe()
    if not exe:
        return -1, _tr("winget nicht gefunden (App-Installer aus dem Microsoft Store)",
                       "winget not found (App Installer from the Microsoft Store)")
    try:
        p = subprocess.Popen([exe] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                             creationflags=_NO_WINDOW)
    except OSError as e:
        return -1, str(e)
    lines: list[str] = []

    def read():
        try:
            for raw in p.stdout:
                for line in raw.replace("\r", "\n").split("\n"):
                    line = line.strip()
                    # winget draws progress bars and spinners: only text lines are kept
                    if not line or set(line) <= set("-\\|/ █▒░") or re.fullmatch(r"[█▒░\s]+.*\d+(\.\d+)?\s*(%|[KMG]B.*)", line):
                        continue
                    lines.append(line)
                    if on_line:
                        try:
                            on_line(line)
                        except Exception:
                            pass
        except (OSError, ValueError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        reader.join(5)
        return -2, "\n".join(list(lines) + [_tr("Zeitüberschreitung", "Timed out")])
    # a program the setup started may still hold the output: never wait for it
    reader.join(TAIL_S)
    return (p.returncode or 0) & 0xFFFFFFFF, "\n".join(list(lines))


def installed_ids(programs=None) -> set[str]:
    """Ids of the catalog that are installed (winget's own list + the known install paths)."""
    programs = CATALOG if programs is None else programs
    found: set[str] = set()
    tmp = os.path.join(tempfile.mkdtemp(prefix="gop_winget_"), "export.json")
    try:
        _run(["export", "-o", tmp, "--source", "winget", "--accept-source-agreements",
              "--disable-interactivity"], timeout=120)
        if os.path.exists(tmp):
            with open(tmp, encoding="utf-8-sig") as f:
                data = json.load(f)
            ids = {str(p.get("PackageIdentifier", "")).lower()
                   for s in data.get("Sources", []) for p in s.get("Packages", [])}
            found |= {p.id for p in programs if p.id.lower() in ids}
    except (OSError, ValueError):
        pass
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    found |= {p.id for p in programs if any(os.path.exists(x) for x in p.paths)}
    return found


def install(pid: str, on_line=None) -> tuple[bool, str]:
    """Install one program silently from winget's source. (ok, message)."""
    if pid not in {p.id for p in CATALOG} or not _ID.match(pid):
        return False, _tr("Nicht in der Liste", "Not in the list")
    rc, out = _run(["install", "--id", pid, "-e", "--source", "winget", "--silent",
                    "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"],
                   on_line=on_line)
    if rc in _OK_CODES:
        if rc == 0x8A150109:
            return True, _tr("installiert — ein Neustart schließt es ab", "installed — a restart finishes it")
        if rc in (0x8A15002B, 0x8A150061):
            return True, _tr("war schon installiert und aktuell", "was already installed and up to date")
        return True, ""
    last = [l for l in out.splitlines() if l][-2:]
    return False, (" · ".join(last)[:240] or f"winget {rc:#x}")
