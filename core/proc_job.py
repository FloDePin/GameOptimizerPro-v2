"""
GameOptimizerPro — GPU loads that end with the app, guaranteed by Windows (23.10.)

The stress workers notice a dead app themselves (_stress_worker._parent_alive), FurMark does not:
when the app died hard in the middle of a tune (a crash, a kill, Task Manager), FurMark kept the
card under full load — on the overclock of the step that was running. A Windows job object with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ends every process in it the moment the app's last handle to
the job goes, i.e. when the app's process ends, however it ends.

Only the app's own GPU loads go in (stress workers, the encoder load, FurMark of a benchmark /
the hardness test). NEVER Afterburner, the update installer or the app's own restart: they must
outlive the app.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFO = 9
_PROCESS_SET_QUOTA, _PROCESS_TERMINATE = 0x0100, 0x0001

_job = None
_lock = threading.Lock()


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes",
                                                   "WriteBytes", "OtherBytes")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _the_job():
    """The app's job (made once, kept open for the process' lifetime), None when not possible."""
    global _job
    with _lock:
        if _job is None:
            try:
                k = _kernel32()
                h = k.CreateJobObjectW(None, None)
                if not h:
                    _job = False
                    return None
                info = _ExtendedLimits()
                info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
                if not k.SetInformationJobObject(h, _EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
                    k.CloseHandle(h)
                    _job = False
                    return None
                _job = h
            except Exception:
                _job = False
        return _job or None


def bind(proc_or_pid) -> bool:
    """Put a started process into the app's job: it ends when the app ends. -> True when bound.
    Never raises (no job here = the old behaviour)."""
    if os.name != "nt" or proc_or_pid is None:
        return False
    pid = getattr(proc_or_pid, "pid", proc_or_pid)
    job = _the_job()
    if not job or not pid:
        return False
    try:
        k = _kernel32()
        h = k.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid))
        if not h:
            return False
        try:
            return bool(k.AssignProcessToJobObject(job, h))
        finally:
            k.CloseHandle(h)
    except Exception:
        return False
