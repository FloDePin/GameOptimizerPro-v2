"""
GameOptimizerPro — the app's own JSON state, safe against locks, crashes and broken files

Audit 2026-10-23: every store read its file with "can't read it → {}" and wrote the next
change on top of that {} — a virus scanner holding settings.json for a moment at boot, or a
broken file after a power cut, silently wiped the settings, which tweaks the app had applied
(so it could no longer revert them) or which services it changed.

  read(path, default)          missing -> default; locked -> a few tries (a scanner or a backup
                               lets go within moments); broken -> the last good copy (.bak),
                               the broken file kept aside as .broken-<time>
  read(path, default, strict=True)
                               the same, but raises Unreadable instead of returning the default
                               when the file is there and can't be read: a caller that writes it
                               back must never write {} over it
  write(path, data)            temp file + flush + fsync, the last good file kept as .bak, then
                               an atomic replace (retried while another process holds the file)

One lock per file inside the app: a reader never meets a replace half way.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

RETRY_WAITS = (0.05, 0.15, 0.3, 0.6)      # ~1.1 s in all
KEEP_BROKEN = 3                            # broken copies kept per file

_locks: dict = {}
_guard = threading.Lock()


class Unreadable(Exception):
    """The file is there but could not be read (locked / broken without a good copy)."""


def _lock(p: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(str(p)))
    with _guard:
        lk = _locks.get(key)
        if lk is None:
            lk = _locks[key] = threading.RLock()
        return lk


def _bak(p: Path) -> Path:
    return p.with_name(p.name + ".bak")


def _note(text: str):
    try:
        from core import errlog
        errlog.note(text)
    except Exception:
        pass


def _load(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _keep_broken(p: Path):
    """The broken file aside (never deleted: it may still be worth a look), the oldest beyond
    KEEP_BROKEN removed."""
    try:
        os.replace(p, p.with_name(f"{p.name}.broken-{datetime.now():%Y%m%d_%H%M%S}"))
        old = sorted(p.parent.glob(p.name + ".broken-*"))
        for q in old[:-KEEP_BROKEN]:
            try:
                q.unlink()
            except OSError:
                pass
    except OSError:
        pass


def read(path, default=None, *, strict: bool = False):
    p = Path(path)
    with _lock(p):
        if not p.exists():
            return default
        err = None
        for wait in (0.0,) + RETRY_WAITS:
            if wait:
                time.sleep(wait)
            try:
                return _load(p)
            except ValueError as e:            # broken: no point in reading it again
                err = e
                break
            except OSError as e:               # locked by another process — try again
                err = e
        if isinstance(err, ValueError):
            try:
                data = _load(_bak(p))
            except (OSError, ValueError):
                data = None
            _keep_broken(p)
            if data is not None:
                _note(f"{p.name}: broken ({err}) — restored from its last good copy")
                write(p, data, backup=False)
                return data
            _note(f"{p.name}: broken ({err}), no good copy — kept aside, starting empty")
            if strict:
                raise Unreadable(f"{p.name}: {err}")
            return default
        _note(f"{p.name}: not readable ({err})")
        if strict:
            raise Unreadable(f"{p.name}: {err}")
        return default


def write(path, data, *, indent=2, ensure_ascii: bool = False, backup: bool = True) -> bool:
    """-> True when the new content is on disk."""
    p = Path(path)
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    with _lock(p):
        tmp = p.with_name(p.name + ".tmp")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            _note(f"{p.name}: not written ({e})")
            return False
        if backup and p.exists():
            try:                                # only a GOOD file becomes the backup
                good = p.read_bytes()
                json.loads(good.decode("utf-8"))
                with open(_bak(p), "wb") as f:
                    f.write(good)
            except (OSError, ValueError, UnicodeDecodeError):
                pass
        err = None
        for wait in (0.0,) + RETRY_WAITS:
            if wait:
                time.sleep(wait)
            try:
                os.replace(tmp, p)
                return True
            except OSError as e:               # another process holds the file — try again
                err = e
        try:
            tmp.unlink()
        except OSError:
            pass
        _note(f"{p.name}: not written ({err})")
        return False
