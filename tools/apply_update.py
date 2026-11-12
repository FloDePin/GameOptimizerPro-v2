"""
GameOptimizerPro — install a downloaded update (started by core/updater.py from
the NEW version's folder, standard library only).

    pythonw apply_update.py --src <new version> --dst <app folder> --pid <app pid>
                            [--build N] [--relaunch]

1. waits until the app (pid) has exited — no file is replaced while it runs
2. backs up every file it will replace or remove to logs/update_backup_<build>/
3. copies the new files; app code (.py in core/ ui/ tools/ tests/) that the new
   version no longer has is removed (stale modules could be imported otherwise)
4. a failed copy puts the backed-up files back; everything goes to logs/update.log
5. --relaunch: starts the app again

New Python packages (requirements.txt changed) are NOT installed here: the app's start checks
every package (core/deps.py) and installs what is missing with a progress window and a clear
message when it fails — here pip ran without any window, up to 10 minutes between the app
closing and starting again, and a failure only went to the log.

logs/, profiles/, .git/ and third-party folders next to the app are never touched.
"""

import argparse
import ctypes
import filecmp
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKIP_TOP = {"logs", "profiles", ".git", "__pycache__", ".claude", "venv", ".venv"}
APP_CODE_DIRS = ("core", "ui", "tools", "tests")


def log(dst: Path, msg: str):
    try:
        (dst / "logs").mkdir(parents=True, exist_ok=True)
        with open(dst / "logs" / "update.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def wait_for_exit(pid: int, timeout: float = 90.0) -> bool:
    if pid <= 0:
        return True
    if os.name != "nt":
        end = time.time() + timeout
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                return True
            time.sleep(0.3)
        return False
    from ctypes import wintypes
    SYNCHRONIZE, WAIT_OBJECT_0, ERROR_INVALID_PARAMETER = 0x00100000, 0, 87
    # a handle is pointer-sized: without these types ctypes takes a 32-bit int
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        # only "no such process" means it has ended — a process that can't be watched
        # (access denied) must not get its files replaced under it
        return ctypes.get_last_error() == ERROR_INVALID_PARAMETER
    try:
        return k.WaitForSingleObject(h, int(timeout * 1000)) == WAIT_OBJECT_0    # not WAIT_FAILED / timeout
    finally:
        k.CloseHandle(h)


def files_of(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel.parts[0] in SKIP_TOP or "__pycache__" in rel.parts or p.suffix == ".pyc":
            continue
        yield rel


def apply(src: Path, dst: Path, build: int) -> tuple[bool, str]:
    backup = dst / "logs" / f"update_backup_{build or int(time.time())}"
    new_files = set(files_of(src))
    replaced, created = [], []
    stale = []
    for d in APP_CODE_DIRS:
        if (dst / d).is_dir():
            for p in (dst / d).rglob("*.py"):
                rel = p.relative_to(dst)
                if "__pycache__" not in rel.parts and rel not in new_files:
                    stale.append(rel)
    try:
        for rel in sorted(new_files):
            target = dst / rel
            if target.exists():
                if filecmp.cmp(src / rel, target, shallow=False):
                    continue
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / rel)
                replaced.append(rel)
            else:
                created.append(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, target)
        for rel in stale:
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst / rel), str(backup / rel))
    except OSError as e:
        # put back what was already replaced / removed / added
        for rel in replaced + stale:
            try:
                shutil.copy2(backup / rel, dst / rel)
            except OSError:
                pass
        for rel in created:
            try:
                (dst / rel).unlink()
            except OSError:
                pass
        return False, f"Kopieren fehlgeschlagen ({e}) — alter Stand wiederhergestellt"
    return True, (f"{len(replaced)} Dateien ersetzt, {len(created)} neu, {len(stale)} entfernt — "
                  f"Sicherung: {backup}")


def _req(path: Path) -> bytes:
    """requirements.txt for comparing: line endings / trailing space don't count
    (a git checkout has CRLF, the GitHub zip LF — that started pip for nothing)."""
    try:
        return b"\n".join(line.rstrip() for line in path.read_bytes().splitlines()).strip()
    except OSError:
        return b""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--build", type=int, default=0)
    ap.add_argument("--relaunch", action="store_true")
    a = ap.parse_args(argv)
    src, dst = Path(a.src).resolve(), Path(a.dst).resolve()
    if not (src / "GameOptimizerPro.py").exists() or not (dst / "GameOptimizerPro.py").exists():
        log(dst, f"Update abgebrochen: {src} oder {dst} ist kein GameOptimizerPro-Ordner")
        return 2
    if not wait_for_exit(a.pid):
        log(dst, "Update abgebrochen: GameOptimizerPro hat sich nicht beendet")
        return 3
    time.sleep(0.5)
    old_req = _req(dst / "requirements.txt")
    ok, msg = apply(src, dst, a.build)
    log(dst, f"Update auf Build {a.build}: {'OK' if ok else 'FEHLER'} — {msg}")
    if ok and (dst / "requirements.txt").exists() and _req(dst / "requirements.txt") != old_req:
        log(dst, "requirements.txt geändert — fehlende Pakete installiert der nächste Start (core/deps.py, "
                 "mit Fortschrittsfenster)")
    if ok:
        shutil.rmtree(dst / "logs" / "update", ignore_errors=True)   # staging + pending marker
    else:
        try:                            # no retry at every start: the next check downloads it again
            (dst / "logs" / "update" / "pending.json").unlink()
        except OSError:
            pass
    if a.relaunch:
        exe = Path(sys.executable)
        w = exe.with_name("pythonw.exe")
        try:
            subprocess.Popen([str(w if w.exists() else exe), str(dst / "GameOptimizerPro.py"), "--after-restart"], cwd=str(dst),
                             close_fds=True)
        except OSError as e:
            log(dst, f"Neustart fehlgeschlagen: {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
