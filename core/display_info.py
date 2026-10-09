"""
GameOptimizerPro v2.0 — Monitor-Berater (aus v1)
Prüft je aktivem Bildschirm, ob er mit der höchsten Bildwiederholrate läuft, die
der Treiber bei der AKTUELLEN Auflösung anbietet. (v1 nahm die Maximalrate des
Grafikadapters über alle Auflösungen — die kann der Monitor oft gar nicht.)
Rein lesend: EnumDisplayDevicesW / EnumDisplaySettingsW.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

ENUM_CURRENT_SETTINGS = -1
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x4
# Refresh rates are reported as whole numbers (143.9 Hz -> 143 or 144), and some
# drivers list "TV" rates (59/60, 119/120) next to each other: only a gap of
# more than this is worth a hint.
MIN_GAP_HZ = 2


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD), ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD), ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmUnion1", ctypes.c_byte * 16),   # printer fields / position+orientation
        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


@dataclass
class DisplayState:
    device:  str        # \\.\DISPLAY1
    name:    str        # monitor name (if the driver reports one)
    primary: bool
    width:   int
    height:  int
    current_hz: int
    max_hz:  int        # highest rate the driver offers at this resolution

    @property
    def below_max(self) -> bool:
        return self.current_hz > 0 and self.max_hz - self.current_hz >= MIN_GAP_HZ

    def advice(self) -> str:
        res = f"{self.width}×{self.height}"
        if self.current_hz <= 0:
            return f"{res} — Bildwiederholrate unbekannt"
        if self.below_max:
            return (f"{res} @ {self.current_hz} Hz — läuft UNTER dem Maximum! Möglich sind "
                    f"{self.max_hz} Hz: Einstellungen → System → Bildschirm → Erweiterte "
                    f"Anzeige → Bildwiederholrate.")
        return f"{res} @ {self.current_hz} Hz (Maximum bei dieser Auflösung)"


def _monitor_name(user32, adapter: str) -> str:
    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(dd)
    if user32.EnumDisplayDevicesW(adapter, 0, ctypes.byref(dd), 0):
        return dd.DeviceString.strip()
    return ""


def displays() -> list[DisplayState]:
    if os.name != "nt":
        return []
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return []
    out = []
    i = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        i += 1
        if not dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue
        cur = DEVMODEW()
        cur.dmSize = ctypes.sizeof(cur)
        if not user32.EnumDisplaySettingsW(dd.DeviceName, ENUM_CURRENT_SETTINGS, ctypes.byref(cur)):
            continue
        w, h, hz = cur.dmPelsWidth, cur.dmPelsHeight, cur.dmDisplayFrequency
        best = hz if hz > 1 else 0
        m, mode = 0, DEVMODEW()
        mode.dmSize = ctypes.sizeof(mode)
        while user32.EnumDisplaySettingsW(dd.DeviceName, m, ctypes.byref(mode)):
            m += 1
            if (mode.dmPelsWidth, mode.dmPelsHeight) == (w, h) and mode.dmDisplayFrequency > best:
                best = mode.dmDisplayFrequency
            if m > 5000:                 # safety net against odd drivers
                break
        out.append(DisplayState(
            device=dd.DeviceName, name=_monitor_name(user32, dd.DeviceName),
            primary=bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
            width=w, height=h, current_hz=hz if hz > 1 else 0, max_hz=best))
    out.sort(key=lambda d: not d.primary)
    return out
