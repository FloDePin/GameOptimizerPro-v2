"""
GameOptimizerPro v2.0 — GPU flight recorder (round 31)

While the app runs (window or tray): once a second clock, voltage, power,
temperature and load into a ring buffer of the last minutes — written to
logs/gpu_flight.json every few seconds, so a crash that restarts the PC leaves
the seconds before it on disk. Every few seconds the System event log is read
from where it was last time (classic event log API, no PowerShell): a GPU hang /
reset (nvlddmkm 13 / 14 / 153, Display 4101) that is not one of the app's own
loads becomes a fault — the recording around it is saved, the state just before
it (gpu_watchdog.fault_point) recorded for the next tune, and `on_fault` called.
Reading telemetry and the log changes nothing.
"""

from __future__ import annotations

import ctypes
import os
import struct
import threading
import time
from collections import deque
from ctypes import wintypes
from typing import Callable, Optional

from core import gpu_watchdog as WD

GPU_SOURCES = {"nvlddmkm": set(WD.NV_IDS), "Display": {4101}}
SETTLE_S = 3.0          # samples after the event are part of the picture
GROUP_S = 60.0          # events this close belong to one fault (153 often comes twice)

_REC_HEAD = struct.Struct("<IIIIIIHHHHIIIIII")     # EVENTLOGRECORD up to the strings


def parse_records(data: bytes) -> list:
    """EVENTLOGRECORDs -> [(record number, epoch, source, event id)]."""
    out, off = [], 0
    while off + _REC_HEAD.size <= len(data):
        (length, _res, recno, t_gen, _t_wr, event_id, _typ, _nstr, _cat, _rf, _closing,
         _stroff, _sidlen, _sidoff, _dlen, _doff) = _REC_HEAD.unpack_from(data, off)
        if length < _REC_HEAD.size or off + length > len(data):
            break
        raw = data[off + _REC_HEAD.size: off + length]
        end = 0
        while end + 1 < len(raw) and raw[end:end + 2] != b"\x00\x00":
            end += 2
        source = raw[:end].decode("utf-16-le", errors="replace")
        out.append((recno, float(t_gen), source, event_id & 0xFFFF))
        off += length
    return out


class EventTail:
    """New records of a classic event log since the last poll."""
    SEEK, FORWARDS = 0x2, 0x4
    ERROR_INSUFFICIENT_BUFFER, ERROR_HANDLE_EOF = 122, 38

    def __init__(self, log: str = "System"):
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.OpenEventLogW.restype = wintypes.HANDLE
        api.OpenEventLogW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        api.ReadEventLogW.restype = wintypes.BOOL
        api.ReadEventLogW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                      ctypes.POINTER(wintypes.DWORD)]
        for fn in (api.GetOldestEventLogRecord, api.GetNumberOfEventLogRecords):
            fn.restype = wintypes.BOOL
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.CloseEventLog.argtypes = [wintypes.HANDLE]
        self._api = api
        self._h = api.OpenEventLogW(None, log)
        if not self._h:
            raise OSError(ctypes.get_last_error(), f"OpenEventLog({log})")
        oldest, newest = self._range()
        self.next = newest + 1

    def _range(self) -> tuple[int, int]:
        o, n = wintypes.DWORD(), wintypes.DWORD()
        self._api.GetOldestEventLogRecord(self._h, ctypes.byref(o))
        self._api.GetNumberOfEventLogRecords(self._h, ctypes.byref(n))
        return o.value, o.value + n.value - 1

    def poll(self) -> list:
        """[(epoch, source, event id)] written since the last poll."""
        oldest, newest = self._range()
        if self.next < oldest or self.next > newest + 1:      # wrapped or cleared
            self.next = oldest if self.next < oldest else newest + 1
        out, size = [], 64 * 1024
        while self.next <= newest:
            buf = ctypes.create_string_buffer(size)
            got, need = wintypes.DWORD(), wintypes.DWORD()
            if not self._api.ReadEventLogW(self._h, self.SEEK | self.FORWARDS, self.next, buf, size,
                                           ctypes.byref(got), ctypes.byref(need)):
                if ctypes.get_last_error() == self.ERROR_INSUFFICIENT_BUFFER and need.value > size:
                    size = need.value
                    continue
                break
            recs = parse_records(buf.raw[:got.value])
            if not recs:
                break
            for recno, t, src, eid in recs:
                out.append((t, src, eid))
                self.next = max(self.next, recno + 1)
        return out

    def close(self):
        if self._h:
            self._api.CloseEventLog(self._h)
            self._h = None


def sample_of(stats) -> dict:
    """One recording sample. The clock comes from the same Afterburner poll as the voltage when
    there is one — NVML's instant clock next to Afterburner's 1-s voltage gave pairs like
    "2805 MHz at 970 mV" under bursty load, above any point of the curve."""
    mv = float(stats.voltage_mv or 0)
    ab = float(getattr(stats, "ab_core_mhz", 0) or 0)
    return {"t": round(time.time(), 1), "mhz": round(ab if (mv and ab) else float(stats.core_mhz or 0)),
            "mem": round(float(stats.mem_mhz or 0)), "mv": round(float(stats.voltage_mv or 0)),
            "w": round(float(stats.gpu_power_w or stats.power_w or 0), 1), "temp": int(stats.temp or 0),
            "util": round(float(stats.gpu_usage or 0))}


class LiveWatch:
    """The flight recorder + live event watch (see the module text)."""

    def __init__(self, read_stats: Callable, logs_dir: str, is_busy: Callable[[], bool],
                 on_fault: Callable[[dict], None], profile_fn: Callable[[], Optional[dict]] = lambda: None,
                 gpu_name: str = "", interval: float = 1.0, keep_s: float = 180, flush_s: float = 5,
                 poll_s: float = 4, tail_factory: Callable = EventTail, clock: Callable[[], float] = time.time):
        self._read, self._logs, self._busy, self._on_fault = read_stats, logs_dir, is_busy, on_fault
        self._profile_fn, self.gpu = profile_fn, gpu_name
        self.interval, self.flush_s, self.poll_s = interval, flush_s, poll_s
        self._clock = clock
        self.samples: deque = deque(maxlen=max(10, int(keep_s / max(interval, 0.1))))
        self._lock = threading.Lock()
        self._tail_factory = tail_factory
        self._tail = None
        self._pending: list = []          # GPU events waiting for the samples after them
        self._last_fault_t = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.faults: list = []

    # ── recording ─────────────────────────────────────────────────────────────
    def sample(self):
        try:
            s = sample_of(self._read())
        except Exception:
            return
        s["t"] = round(self._clock(), 1)
        if not s["mhz"] and not s["w"]:
            return                         # no reading (NVML not ready)
        with self._lock:
            self.samples.append(s)

    def snapshot(self) -> list:
        with self._lock:
            return list(self.samples)

    FILE_KEEP_S = 60        # what goes to disk: the last minute is enough to see a crash
    IDLE_FLUSH_S = 60       # an idle card: no need to write every few seconds

    def flush(self):
        now = self._clock()
        WD.save_flight(self._logs, self.gpu, [s for s in self.snapshot() if s["t"] >= now - self.FILE_KEEP_S])

    def loaded_recently(self, secs: float = 60) -> bool:
        now = self._clock()
        snap = [s for s in self.snapshot() if s["t"] >= now - secs]
        peak = max((s.get("w", 0) for s in self.snapshot()), default=0)
        return any(WD.is_loaded(s, peak) for s in snap)

    # ── events ────────────────────────────────────────────────────────────────
    def _gpu_events(self) -> list:
        if self._tail is None:
            try:
                self._tail = self._tail_factory()
            except Exception:
                return []
        try:
            evs = self._tail.poll()
        except Exception:
            return []
        return [(t, eid) for t, src, eid in evs if eid in GPU_SOURCES.get(src, ())]

    def _ours(self, t: float) -> bool:
        try:
            if self._busy():
                return True
        except Exception:
            pass
        return any(a - WD.SLACK_S <= t <= b + WD.SLACK_S for a, b in WD.own_windows(self._logs))

    def check_events(self):
        now = self._clock()
        for t, eid in self._gpu_events():
            if not self._ours(t):
                self._pending.append((t, eid))
        settled = [e for e in self._pending if now >= e[0] + SETTLE_S]
        if not settled:
            return
        first = min(t for t, _i in settled)
        # everything close to the first settled event is the same fault (e.g. 153 + 4101)
        ready = sorted(e for e in self._pending if e[0] - first <= GROUP_S)
        self._pending = [e for e in self._pending if e not in ready]
        if ready[0][0] - self._last_fault_t <= GROUP_S:      # the same fault, again
            self._last_fault_t = ready[-1][0]
            return
        self._handle(ready)

    def _handle(self, events: list):
        t = events[0][0]
        self._last_fault_t = events[-1][0]
        profile = None
        try:
            profile = self._profile_fn()
        except Exception:
            pass
        samples = self.snapshot()
        pt = WD.fault_point(samples, t, profile) or {}
        fault = {"t": t, "ids": sorted({i for _t, i in events}), "gpu": self.gpu,
                 "profile": (profile or {}).get("name", ""), "mv": pt.get("mv", 0), "mhz": pt.get("mhz", 0),
                 "point": pt, "anchors": WD.affected_anchors(profile or {}, pt.get("mv", 0))}
        WD.record_fault(self._logs, fault, [s for s in samples if t - 120 <= s["t"] <= t + 10])
        self.faults.append(fault)
        try:
            self._on_fault(fault)
        except Exception:
            pass

    # ── thread ────────────────────────────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        WD.keep_previous_flight(self._logs)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gpu-flight", daemon=True)
        self._thread.start()

    def stop(self):
        """The loop ends within a second, writes its recording once more and closes the
        log handle itself (never closed under a running read)."""
        self._stop.set()

    def _loop(self):
        last_flush = last_poll = 0.0
        while not self._stop.is_set():
            t0 = time.monotonic()
            self.sample()
            if t0 - last_poll >= self.poll_s:
                last_poll = t0
                self.check_events()
            every = self.flush_s if self.loaded_recently() else self.IDLE_FLUSH_S
            if t0 - last_flush >= every:
                last_flush = t0
                self.flush()
            self._stop.wait(max(0.05, self.interval - (time.monotonic() - t0)))
        try:
            self.flush()
        except Exception:
            pass
        if self._tail is not None:
            try:
                self._tail.close()
            except Exception:
                pass


def toast(title: str, msg: str):
    """A Windows notification (no window, nothing to click away)."""
    if os.name != "nt":
        return
    import subprocess
    esc = lambda s: s.replace('"', "'").replace("`", "'").replace("$", "")   # noqa: E731
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        f"$t.SelectSingleNode('//text[@id=1]').InnerText=\"{esc(title)}\"; "
        f"$t.SelectSingleNode('//text[@id=2]').InnerText=\"{esc(msg)}\"; "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('GameOptimizerPro')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, timeout=8,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass
