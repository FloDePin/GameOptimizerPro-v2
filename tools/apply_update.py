"""
GameOptimizerPro — install a downloaded update (started by core/updater.py from
the NEW version's folder, standard library only).

    pythonw apply_update.py --src <new version> --dst <app folder> --pid <app pid>
                            [--build N] [--relaunch]

1. waits until the app (pid) has exited — no file is replaced while it runs
2. backs up every file it will replace or remove to logs/update_backup_<build>/
3. copies the new files; app code (.py in core/ ui/ tools/ tests/) that the new
   version no longer has is removed (stale modules could be imported otherwise)
4. requirements.txt changed: pip install -r requirements.txt
5. a failed copy puts the backed-up files back; everything goes to logs/update.log
6. --relaunch: starts the app again

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
    SYNCHRONIZE = 0x00100000
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        return True                      # already gone
    try:
        return k.WaitForSingleObject(h, int(timeout * 1000)) == 0
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
    old_req = (dst / "requirements.txt").read_bytes() if (dst / "requirements.txt").exists() else b""
    ok, msg = apply(src, dst, a.build)
    log(dst, f"Update auf Build {a.build}: {'OK' if ok else 'FEHLER'} — {msg}")
    if ok and (dst / "requirements.txt").exists() and (dst / "requirements.txt").read_bytes() != old_req:
        py = Path(sys.executable).with_name("python.exe")
        try:
            r = subprocess.run([str(py if py.exists() else sys.executable), "-m", "pip", "install", "-r",
                                str(dst / "requirements.txt")], capture_output=True, text=True,
                               timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            log(dst, f"pip install -r requirements.txt: Exit {r.returncode}")
        except (OSError, subprocess.SubprocessError) as e:
            log(dst, f"pip install fehlgeschlagen: {e}")
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
            subprocess.Popen([str(w if w.exists() else exe), str(dst / "GameOptimizerPro.py")], cwd=str(dst),
                             close_fds=True)
        except OSError as e:
            log(dst, f"Neustart fehlgeschlagen: {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
