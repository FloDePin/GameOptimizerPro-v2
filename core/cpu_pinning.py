"""
GameOptimizerPro v2.1 — CPU Pinning
Steers a game process (and its children) onto a chosen set of cores.

Primary mechanism: the Windows **CPU Sets** API (SetProcessDefaultCpuSets) — a
*soft* scheduler hint, exactly like the reference tool. Unlike a hard affinity
mask, the scheduler may still spill the process onto other cores if the chosen
set is saturated, so a game can never be accidentally starved. This is the safer
default for unattended per-game pinning.

Fallback: psutil's cpu_affinity() (a hard mask) if the CPU Sets calls are
unavailable. Callers pass logical processor indices; we translate to the
CpuSet-Ids reported by the topology layer.

All functions are best-effort and never raise — pinning is a nice-to-have, it
must never crash the monitor or the app.
"""

from __future__ import annotations
import ctypes
import platform
from ctypes import wintypes
from typing import Optional

from core.cpu_topology import CpuTopology

# OpenProcess access rights
_PROCESS_SET_LIMITED_INFORMATION = 0x2000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _k32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _logicals_to_cpuset_ids(topo: CpuTopology, logicals: list[int]) -> list[int]:
    """Map logical processor indices → CpuSet-Ids from the topology."""
    by_logical = {c.logical_index: c.cpuset_id for c in topo.cpus}
    return [by_logical[i] for i in logicals if i in by_logical]


def _set_default_cpu_sets(hproc, ids: list[int]) -> bool:
    """SetProcessDefaultCpuSets on an already-open handle. Empty ids = clear."""
    try:
        k = _k32()
        fn = k.SetProcessDefaultCpuSets
        fn.restype = wintypes.BOOL
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG), wintypes.ULONG]
        if ids:
            arr = (wintypes.ULONG * len(ids))(*ids)
            return bool(fn(hproc, arr, len(ids)))
        return bool(fn(hproc, None, 0))
    except Exception:
        return False


def _open(pid: int, write: bool = True):
    k = _k32()
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    access = _PROCESS_QUERY_LIMITED_INFORMATION
    if write:
        access |= _PROCESS_SET_LIMITED_INFORMATION
    h = k.OpenProcess(access, False, pid)
    return h or None


def _close(h):
    try:
        _k32().CloseHandle(h)
    except Exception:
        pass


def is_supported() -> bool:
    """CPU Sets API present (Windows 10+)."""
    if platform.system() != "Windows":
        return False
    try:
        return hasattr(_k32(), "SetProcessDefaultCpuSets")
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def pin_process(pid: int, topo: CpuTopology, logicals: list[int]) -> bool:
    """Steer one process onto `logicals`. Empty list = reset to system default.
    Tries CPU Sets first, then psutil affinity. Returns True on success."""
    if platform.system() != "Windows":
        return False
    ids = _logicals_to_cpuset_ids(topo, logicals)

    # 1) CPU Sets (soft hint)
    if is_supported():
        h = _open(pid, write=True)
        if h:
            try:
                if _set_default_cpu_sets(h, ids):
                    return True
            finally:
                _close(h)

    # 2) Fallback: hard affinity via psutil (only when actually restricting)
    if logicals:
        try:
            import psutil
            psutil.Process(pid).cpu_affinity(list(logicals))
            return True
        except Exception:
            return False
    return False


def unpin_process(pid: int, topo: CpuTopology) -> bool:
    """Clear any CPU-Set steering (and reset affinity to all cores)."""
    ok = False
    if is_supported():
        h = _open(pid, write=True)
        if h:
            try:
                ok = _set_default_cpu_sets(h, [])
            finally:
                _close(h)
    # Also lift a hard affinity mask if one was set as fallback
    try:
        import psutil
        psutil.Process(pid).cpu_affinity(topo.all_logicals())
    except Exception:
        pass
    return ok


def pin_by_name(exe_name: str, topo: CpuTopology, logicals: list[int]) -> int:
    """Pin every running process matching exe_name (case-insensitive) + children.
    Returns the number of processes successfully pinned."""
    if not logicals or platform.system() != "Windows":
        return 0
    try:
        import psutil
    except Exception:
        return 0

    exe_low = exe_name.lower()
    count = 0
    targets = []
    for p in psutil.process_iter(["name", "pid"]):
        try:
            if (p.info["name"] or "").lower() == exe_low:
                targets.append(p)
        except Exception:
            continue

    seen: set[int] = set()
    for proc in targets:
        for pr in [proc] + _safe_children(proc):
            if pr.pid in seen:
                continue
            seen.add(pr.pid)
            if pin_process(pr.pid, topo, logicals):
                count += 1
    return count


def verify_process(pid: int) -> Optional[list[int]]:
    """Read back the CpuSet-Ids currently steering a process (for self-test).
    Returns the id list, or None if unavailable."""
    if not is_supported():
        return None
    h = _open(pid, write=False)
    if not h:
        return None
    try:
        k = _k32()
        fn = k.GetProcessDefaultCpuSets
        fn.restype = wintypes.BOOL
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG),
                       wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
        required = wintypes.ULONG(0)
        fn(h, None, 0, ctypes.byref(required))
        n = required.value
        if n == 0:
            return []
        arr = (wintypes.ULONG * n)()
        if fn(h, arr, n, ctypes.byref(required)):
            return list(arr[:required.value])
        return None
    except Exception:
        return None
    finally:
        _close(h)


def _safe_children(proc):
    try:
        return proc.children(recursive=True)
    except Exception:
        return []


# Manual self-test: pin our own process to core 0, verify, then clear.
if __name__ == "__main__":
    import os
    from core import cpu_topology
    topo = cpu_topology.detect()
    print(f"supported={is_supported()} topo_ok={topo.ok}")
    pid = os.getpid()
    print("before:", verify_process(pid))
    ok = pin_process(pid, topo, [0])
    print(f"pin core0 -> {ok}; now:", verify_process(pid))
    ids0 = _logicals_to_cpuset_ids(topo, [0])
    print(f"expected cpuset id for logical 0: {ids0}")
    unpin_process(pid, topo)
    print("after unpin:", verify_process(pid))
