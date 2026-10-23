"""
GameOptimizerPro — a Windows notification without starting PowerShell (23.10.)

The temperature warning and the GPU watchdog started a powershell.exe for every notification
(WinRT toast) — mid-game, the moment something went wrong; on stripped-down Windows installs
without the app's ID registered Windows also dropped it silently. The app's own tray icon can
show it directly (pystray -> Shell_NotifyIcon, a balloon Windows shows as a notification); the
PowerShell toast stays the fallback when there is no tray icon.
"""

from __future__ import annotations

from typing import Callable, Optional

_tray = None


def set_tray(icon):
    """The app's pystray icon (None when it ends)."""
    global _tray
    _tray = icon


def show(title: str, message: str, fallback: Optional[Callable[[], None]] = None) -> bool:
    """-> True when the tray icon showed it; else the fallback runs (if given)."""
    ic = _tray
    if ic is not None and getattr(ic, "visible", False) and hasattr(ic, "notify"):
        try:
            ic.notify(message, title)
            return True
        except Exception:
            pass
    if fallback is not None:
        try:
            fallback()
        except Exception:
            pass
    return False
