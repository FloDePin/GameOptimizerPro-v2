"""
GameOptimizerPro — Game profiles

Per game .exe, written once into the registry and applied by Windows itself every
time the game starts — no background process, works with the app closed:
  • CPU priority  — Image File Execution Options\\<exe>\\PerfOptions\\CpuPriorityClass
                    (3 = High, 6 = Above normal; never Realtime)
  • I/O priority  — PerfOptions\\IoPriority = 3 (High)
  • Fullscreen optimizations off — only for this game: the compatibility flag
    DISABLEDXMAXIMIZEDWINDOWEDMODE in AppCompatFlags\\Layers (value name = full path)

IFEO keys are per file NAME: the profile applies to every file with that name.
What was there before the first change is stored under
HKLM\\SOFTWARE\\GameOptimizerPro\\GameProfiles\\<exe> and put back on remove — values
the user or another tool set before stay untouched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.i18n import tr as _tr

try:
    import winreg
except ImportError:          # not Windows: the module imports, every call fails cleanly
    winreg = None

HKLM = getattr(winreg, "HKEY_LOCAL_MACHINE", None)
HKCU = getattr(winreg, "HKEY_CURRENT_USER", None)

# (hive, path) — tests point these at a scratch key
IFEO_ROOT   = (HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options")
STORE_ROOT  = (HKLM, r"SOFTWARE\GameOptimizerPro\GameProfiles")
LAYERS_ROOT = (HKCU, r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers")

CPU_HIGH, CPU_ABOVE = 3, 6
IO_HIGH = 3
FSO_FLAG = "DISABLEDXMAXIMIZEDWINDOWEDMODE"

# Windows / shell processes, interpreters and this app's own helpers: a priority
# profile there would change the whole system or GameOptimizerPro itself.
BLOCKED = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
    "svchost.exe", "dwm.exe", "explorer.exe", "audiodg.exe", "conhost.exe", "fontdrvhost.exe",
    "sihost.exe", "ctfmon.exe", "taskmgr.exe", "taskhostw.exe", "runtimebroker.exe",
    "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe", "dllhost.exe",
    "rundll32.exe", "regedit.exe", "mmc.exe", "msiexec.exe", "werfault.exe", "spoolsv.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
    "python.exe", "pythonw.exe", "py.exe", "pyw.exe",
}
# Names many games share (launchers, generic binaries): allowed, but worth a warning.
GENERIC = {"game.exe", "launcher.exe", "start.exe", "client.exe", "app.exe", "main.exe",
           "play.exe", "setup.exe", "unitycrashhandler64.exe", "crashreporter.exe"}

_PERF_VALUES = ("CpuPriorityClass", "IoPriority")


@dataclass
class GameProfile:
    exe:  str                 # file name, lower case (the IFEO key)
    path: str                 # full path as chosen (FSO flag + display)
    cpu:  int = CPU_HIGH
    io_high: bool = True
    fso_off: bool = False


@dataclass
class ProfileStatus:
    perf_ok:   bool = False   # registry holds the profile's priorities
    fso_ok:    bool = True    # flag set as the profile wants (True when not wanted)
    running:   int = 0        # processes with this name right now
    run_cpu:   int | None = None   # psutil priority class of the first one
    run_io:    int | None = None   # psutil I/O priority (0..3)
    note:      str = ""


class GameProfileError(Exception):
    pass


# ── registry helpers ──────────────────────────────────────────────────────────

def _open(root, sub="", write=False):
    hive, path = root
    full = path + ("\\" + sub if sub else "")
    access = (winreg.KEY_READ | winreg.KEY_WRITE) if write else winreg.KEY_READ
    try:
        return winreg.OpenKey(hive, full, 0, access | winreg.KEY_WOW64_64KEY)
    except OSError:
        return None


def _create(root, sub=""):
    hive, path = root
    full = path + ("\\" + sub if sub else "")
    return winreg.CreateKeyEx(hive, full, 0,
                              winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)


def _get(key, name):
    if key is None:
        return None
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _delete_value(key, name):
    try:
        winreg.DeleteValue(key, name)
    except OSError:
        pass


def _is_empty(root, sub) -> bool:
    k = _open(root, sub)
    if k is None:
        return True
    with k:
        info = winreg.QueryInfoKey(k)
    return info[0] == 0 and info[1] == 0


def _delete_key(root, sub):
    hive, path = root
    try:
        winreg.DeleteKeyEx(hive, path + "\\" + sub, winreg.KEY_WOW64_64KEY, 0)
    except OSError:
        pass


# ── validation ────────────────────────────────────────────────────────────────

def check_path(path: str) -> str:
    """The IFEO key name for `path`, or GameProfileError with a reason."""
    name = os.path.basename(path or "").strip().lower()
    if not name.endswith(".exe") or len(name) <= 4:
        raise GameProfileError(_tr("Bitte eine .exe-Datei wählen.", "Please choose an .exe file."))
    if name in BLOCKED:
        raise GameProfileError(_tr(
            f"{name} ist ein Windows- oder Systemprogramm — dafür gibt es kein Spiel-Profil.",
            f"{name} is a Windows or system program — no game profile for it."))
    if any(c in name for c in '\\/:*?"<>|'):
        raise GameProfileError(_tr("Ungültiger Dateiname.", "Invalid file name."))
    return name


def is_generic(exe: str) -> bool:
    return exe.lower() in GENERIC


# ── profiles ──────────────────────────────────────────────────────────────────

def list_profiles() -> list[GameProfile]:
    if winreg is None:
        return []
    k = _open(STORE_ROOT)
    if k is None:
        return []
    out = []
    with k:
        i = 0
        while True:
            try:
                exe = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            sk = _open(STORE_ROOT, exe)
            if sk is None:
                continue
            with sk:
                out.append(GameProfile(
                    exe=exe.lower(), path=str(_get(sk, "Path") or exe),
                    cpu=int(_get(sk, "Cpu") or CPU_HIGH), io_high=bool(_get(sk, "Io")),
                    fso_off=bool(_get(sk, "Fso"))))
    return sorted(out, key=lambda p: p.exe)


def get_profile(exe: str) -> GameProfile | None:
    return next((p for p in list_profiles() if p.exe == exe.lower()), None)


def _layer_tokens(path: str) -> list[str]:
    k = _open(LAYERS_ROOT)
    if k is None:
        return []
    with k:
        v = _get(k, path)
    return str(v or "").split()


def _set_layer_tokens(path: str, tokens: list[str]):
    flags = [t for t in tokens if t != "~"]
    k = _create(LAYERS_ROOT)
    with k:
        if flags:
            winreg.SetValueEx(k, path, 0, winreg.REG_SZ, " ".join(["~"] + flags))
        else:
            _delete_value(k, path)


def save(path: str, cpu: int = CPU_HIGH, io_high: bool = True, fso_off: bool = False) -> GameProfile:
    """Create or change the profile for `path`. Records the previous state once."""
    if winreg is None:
        raise GameProfileError(_tr("Nur unter Windows verfügbar.", "Only available on Windows."))
    if cpu not in (CPU_HIGH, CPU_ABOVE):
        raise GameProfileError(f"cpu={cpu}")
    exe = check_path(path)
    path = os.path.normpath(path)
    try:
        store_new = _open(STORE_ROOT, exe) is None
        st = _create(STORE_ROOT, exe)
        with st:
            if store_new:
                # the state before GameOptimizerPro touched it — restored on remove
                had_ifeo = _open(IFEO_ROOT, exe) is not None
                perf = _open(IFEO_ROOT, exe + r"\PerfOptions")
                winreg.SetValueEx(st, "HadIfeo", 0, winreg.REG_DWORD, int(had_ifeo))
                winreg.SetValueEx(st, "HadPerf", 0, winreg.REG_DWORD, int(perf is not None))
                for name in _PERF_VALUES:
                    v = _get(perf, name)
                    if v is not None:
                        winreg.SetValueEx(st, "Prev" + name, 0, winreg.REG_DWORD, int(v))
                if perf is not None:
                    perf.Close()
                winreg.SetValueEx(st, "FsoHad", 0, winreg.REG_DWORD,
                                  int(FSO_FLAG in _layer_tokens(path)))
            old_path = _get(st, "Path")
            winreg.SetValueEx(st, "Path", 0, winreg.REG_SZ, path)
            winreg.SetValueEx(st, "Cpu", 0, winreg.REG_DWORD, int(cpu))
            winreg.SetValueEx(st, "Io", 0, winreg.REG_DWORD, int(bool(io_high)))
            winreg.SetValueEx(st, "Fso", 0, winreg.REG_DWORD, int(bool(fso_off)))
            prev_io = _get(st, "PrevIoPriority")
            fso_had = bool(_get(st, "FsoHad"))

        perf = _create(IFEO_ROOT, exe + r"\PerfOptions")
        with perf:
            winreg.SetValueEx(perf, "CpuPriorityClass", 0, winreg.REG_DWORD, int(cpu))
            if io_high:
                winreg.SetValueEx(perf, "IoPriority", 0, winreg.REG_DWORD, IO_HIGH)
            elif prev_io is not None:
                winreg.SetValueEx(perf, "IoPriority", 0, winreg.REG_DWORD, int(prev_io))
            else:
                _delete_value(perf, "IoPriority")

        # fullscreen flag: a changed path moves it (the old path gets its own state back)
        if old_path and os.path.normcase(str(old_path)) != os.path.normcase(path):
            _drop_fso(str(old_path), fso_had)
        toks = _layer_tokens(path)
        if fso_off and FSO_FLAG not in toks:
            _set_layer_tokens(path, toks + [FSO_FLAG])
        elif not fso_off and FSO_FLAG in toks and not fso_had:
            _set_layer_tokens(path, [t for t in toks if t != FSO_FLAG])
    except PermissionError:
        raise GameProfileError(_tr("Keine Berechtigung — die App braucht Administratorrechte.",
                                   "No permission — the app needs administrator rights."))
    except OSError as e:
        raise GameProfileError(str(e))
    return GameProfile(exe=exe, path=path, cpu=cpu, io_high=bool(io_high), fso_off=bool(fso_off))


def _drop_fso(path: str, fso_had: bool):
    toks = _layer_tokens(path)
    if FSO_FLAG in toks and not fso_had:
        _set_layer_tokens(path, [t for t in toks if t != FSO_FLAG])


def remove(exe: str) -> bool:
    """Put back what was there before the profile; False when there was none."""
    if winreg is None:
        return False
    exe = exe.lower()
    st = _open(STORE_ROOT, exe)
    if st is None:
        return False
    with st:
        rec = {n: _get(st, n) for n in ("Path", "HadIfeo", "HadPerf", "FsoHad",
                                         "PrevCpuPriorityClass", "PrevIoPriority")}
    try:
        perf = _open(IFEO_ROOT, exe + r"\PerfOptions", write=True)
        if perf is not None:
            with perf:
                for name in _PERF_VALUES:
                    prev = rec.get("Prev" + name)
                    if prev is None:
                        _delete_value(perf, name)
                    else:
                        winreg.SetValueEx(perf, name, 0, winreg.REG_DWORD, int(prev))
            if not rec.get("HadPerf") and _is_empty(IFEO_ROOT, exe + r"\PerfOptions"):
                _delete_key(IFEO_ROOT, exe + r"\PerfOptions")
        if not rec.get("HadIfeo") and _is_empty(IFEO_ROOT, exe):
            _delete_key(IFEO_ROOT, exe)
        if rec.get("Path"):
            _drop_fso(str(rec["Path"]), bool(rec.get("FsoHad")))
        _delete_key(STORE_ROOT, exe)
    except PermissionError:
        raise GameProfileError(_tr("Keine Berechtigung — die App braucht Administratorrechte.",
                                   "No permission — the app needs administrator rights."))
    return True


def remove_all() -> int:
    return sum(1 for p in list_profiles() if remove(p.exe))


# ── live check ────────────────────────────────────────────────────────────────

def status(p: GameProfile) -> ProfileStatus:
    """Does the registry still hold the profile, and — if the game runs now — what
    priority did Windows really give it?"""
    s = ProfileStatus()
    perf = _open(IFEO_ROOT, p.exe + r"\PerfOptions")
    cpu = _get(perf, "CpuPriorityClass")
    io = _get(perf, "IoPriority")
    if perf is not None:
        perf.Close()
    s.perf_ok = cpu == p.cpu and ((io == IO_HIGH) if p.io_high else (io != IO_HIGH))
    s.fso_ok = (FSO_FLAG in _layer_tokens(p.path)) if p.fso_off else True
    try:
        import psutil
        procs = [pr for pr in psutil.process_iter(["name"])
                 if (pr.info.get("name") or "").lower() == p.exe]
        s.running = len(procs)
        if procs:
            try:
                s.run_cpu = int(procs[0].nice())
                s.run_io = int(procs[0].ionice())
            except Exception:
                s.note = "no access"
    except Exception:
        pass
    return s


def cpu_matches(p: GameProfile, run_cpu: int | None) -> bool | None:
    """psutil priority class vs the profile (None: not known)."""
    if run_cpu is None:
        return None
    try:
        import psutil
        want = psutil.HIGH_PRIORITY_CLASS if p.cpu == CPU_HIGH else psutil.ABOVE_NORMAL_PRIORITY_CLASS
    except Exception:
        return None
    return run_cpu == want
