"""
GameOptimizerPro v2.0 — updates from GitHub (stdlib only)

The version stays "2.0" across releases, so a release is identified by the
integer in build.json (raised with every release). At start-up — when the user
leaves "check for updates" on — the app compares it with build.json on GitHub:

  * zip install: download the repository zip, unpack it to logs/update/ and
    check it; the user is asked to restart. tools/apply_update.py (from the new
    version) then waits until the app has exited, backs up every file it
    replaces (logs/update_backup_<build>/), copies the new files, removes app
    code that no longer exists and starts the app again. Answering "later"
    leaves it pending: the next start applies it before anything else runs.
  * git checkout (a .git folder): `git pull --ff-only`, only on a clean tree.

logs/ and profiles/ (the user's data) are never touched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO = "FloDePin/GameOptimizerPro-v2"
BRANCH = "main"
BASE = Path(__file__).resolve().parent.parent
BUILD_FILE = BASE / "build.json"
RAW_BUILD_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/build.json"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
STAGING = BASE / "logs" / "update"
PENDING = STAGING / "pending.json"
MAX_ZIP_BYTES = 60 * 1024 * 1024
USER_AGENT = "GameOptimizerPro-Updater"


@dataclass
class BuildInfo:
    build: int
    date: str = ""
    notes: str = ""


def parse_build(text: str) -> Optional[BuildInfo]:
    try:
        d = json.loads(text)
        b = int(d["build"])
    except (ValueError, KeyError, TypeError):
        return None
    if b <= 0:
        return None
    return BuildInfo(b, str(d.get("date") or ""), str(d.get("notes") or ""))


def local_build(base: Path = BASE) -> BuildInfo:
    try:
        return parse_build((base / "build.json").read_text(encoding="utf-8")) or BuildInfo(0)
    except OSError:
        return BuildInfo(0)


def _get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — fixed https URLs
        return r.read(MAX_ZIP_BYTES + 1)


def fetch_remote(timeout: float = 6.0) -> Optional[BuildInfo]:
    """build.json of the newest release on GitHub, None when offline / unreadable."""
    try:
        return parse_build(_get(f"{RAW_BUILD_URL}?t={int(time.time())}", timeout).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def is_git_checkout(base: Path = BASE) -> bool:
    return (base / ".git").exists()


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git_clean(base: Path = BASE) -> Optional[bool]:
    """True = no local changes, False = changes, None = git not usable."""
    try:
        r = subprocess.run(["git", "-C", str(base), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, timeout=20, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return not r.stdout.strip()


def git_pull(base: Path = BASE) -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", "-C", str(base), "pull", "--ff-only"], capture_output=True, text=True,
                           timeout=120, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out.strip()[-600:]


# ── zip install ──────────────────────────────────────────────────────────────

def _safe_extract(zf: zipfile.ZipFile, dest: Path):
    """Extract without leaving dest (no '..' / absolute paths)."""
    root = dest.resolve()
    for info in zf.infolist():
        target = (dest / info.filename).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"unsafe path in the update zip: {info.filename}")
    zf.extractall(dest)


def download_and_stage(remote: BuildInfo, progress: Optional[Callable[[str], None]] = None,
                       base: Path = BASE, fetch: Callable[[str, float], bytes] = _get) -> tuple[bool, str]:
    """Download the release, unpack it to logs/update/new and check it.
    -> (ok, message); ok writes logs/update/pending.json."""
    staging = base / "logs" / "update"
    try:
        if progress:
            progress("download")
        data = fetch(ZIP_URL, 60.0)
        if len(data) > MAX_ZIP_BYTES:
            return False, "Update-Download zu groß"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        zpath = staging / "download.zip"
        zpath.write_bytes(data)
        with zipfile.ZipFile(zpath) as zf:
            if zf.testzip() is not None:
                return False, "Update-Download beschädigt"
            _safe_extract(zf, staging / "new")
        zpath.unlink(missing_ok=True)
        roots = [p for p in (staging / "new").iterdir() if p.is_dir()]
        root = roots[0] if len(roots) == 1 else staging / "new"
        got = local_build(root)
        if not (root / "GameOptimizerPro.py").exists() or not (root / "tools" / "apply_update.py").exists():
            return False, "Update unvollständig (Programmdateien fehlen)"
        if got.build != remote.build:
            return False, f"Update passt nicht (Build {got.build} statt {remote.build})"
        (staging / "pending.json").write_text(json.dumps({"build": got.build, "date": got.date,
                                                          "notes": got.notes, "dir": str(root)}),
                                              encoding="utf-8")
        return True, f"Build {got.build} bereit"
    except (urllib.error.URLError, OSError, zipfile.BadZipFile, ValueError) as e:
        return False, f"Update-Download fehlgeschlagen: {e}"


def pending(base: Path = BASE) -> Optional[dict]:
    """The downloaded, not yet installed update — only if it is newer and complete."""
    marker = base / "logs" / "update" / "pending.json"
    try:
        d = json.loads(marker.read_text(encoding="utf-8"))
        build, root = int(d["build"]), Path(d["dir"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if build <= local_build(base).build or not (root / "tools" / "apply_update.py").exists():
        clear_pending(base)
        return None
    return d


def clear_pending(base: Path = BASE):
    shutil.rmtree(base / "logs" / "update", ignore_errors=True)


def gui_python() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def launch_apply(info: dict, relaunch: bool = True, base: Path = BASE) -> bool:
    """Start the new version's apply script; it waits for this process to end.
    The caller must exit right after (the files are replaced then)."""
    script = Path(info["dir"]) / "tools" / "apply_update.py"
    args = [gui_python(), str(script), "--src", str(info["dir"]), "--dst", str(base),
            "--pid", str(os.getpid()), "--build", str(info.get("build", 0))]
    if relaunch:
        args.append("--relaunch")
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
             | _no_window())
    try:
        subprocess.Popen(args, cwd=str(base), close_fds=True, creationflags=flags)
        return True
    except OSError:
        return False
