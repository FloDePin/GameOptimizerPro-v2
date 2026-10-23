"""
GameOptimizerPro — one place where unexpected errors end up (audit 2026-10-23)

The app runs without a console (pythonw): an exception in a button's handler, in a worker
thread or at start-up went to a stderr nobody sees — "the app does nothing" without a trace.
install() routes them all into logs/app_errors.log (two files of at most MAX_BYTES each), and
note() lets a "best effort" spot leave a line where it matters. The many deliberate
"except: pass" around sensors and clean-up stay as they are — they are expected, not errors.
"""

from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

MAX_BYTES = 512 * 1024
_file: Path | None = None
_wlock = threading.Lock()


def path() -> Path | None:
    return _file


def _write(text: str):
    f = _file
    if f is None:
        return
    with _wlock:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            if f.exists() and f.stat().st_size > MAX_BYTES:
                old = f.with_name(f.name + ".1")
                try:
                    old.unlink()
                except OSError:
                    pass
                f.replace(old)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(text if text.endswith("\n") else text + "\n")
        except OSError:
            pass


def note(text: str):
    """One line: something the app worked around (a broken settings file, a write that failed)."""
    _write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}")


def exception(where: str, exc_type=None, exc=None, tb=None):
    """A full traceback with where it happened."""
    if exc_type is None:
        exc_type, exc, tb = sys.exc_info()
    if exc_type is None:
        return
    body = "".join(traceback.format_exception(exc_type, exc, tb))
    _write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {where}\n{body}")


def install(logs_dir):
    """Uncaught exceptions of the main thread, of every thread and of Tk callbacks -> the log.
    Tk: call tk_hook(root) for the window too (Tk reports its callbacks' errors itself)."""
    global _file
    _file = Path(logs_dir) / "app_errors.log"
    prev = sys.excepthook

    def _main_hook(t, e, tb):
        exception("unhandled (main thread)", t, e, tb)
        try:
            prev(t, e, tb)
        except Exception:
            pass
    sys.excepthook = _main_hook

    prev_thread = getattr(threading, "excepthook", None)

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        name = getattr(args.thread, "name", "?")
        exception(f"unhandled in thread {name}", args.exc_type, args.exc_value, args.exc_traceback)
        if prev_thread is not None:
            try:
                prev_thread(args)
            except Exception:
                pass
    threading.excepthook = _thread_hook


def tk_hook(root):
    """A Tk root's callback errors -> the log (and still printed, as before)."""
    prev = getattr(root, "report_callback_exception", None)

    def _report(exc, val, tb):
        exception("Tk callback", exc, val, tb)
        if prev is not None:
            try:
                prev(exc, val, tb)
            except Exception:
                pass
    try:
        root.report_callback_exception = _report
    except Exception:
        pass
