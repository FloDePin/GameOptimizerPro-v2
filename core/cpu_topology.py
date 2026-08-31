"""
GameOptimizerPro v2.1 — CPU Topology Detection
Detects physical cores, SMT pairing, Intel P/E cores and AMD CCDs (via L3 cache
groupings) so games can be pinned to the "good" cores:

  • AMD X3D  → the chiplet (CCD) that carries the extra 3D V-Cache
  • Intel    → the performance (P) cores, keeping E-cores for background work
  • Dual-CCD → either chiplet individually

Everything is read-only via two Win32 APIs (ctypes, no external deps):
  GetSystemCpuSetInformation      → per-logical-CPU: CpuSet-Id, core, L3-index, eff-class
  GetLogicalProcessorInformationEx → L3 cache sizes (to find the X3D cache die)

Non-Windows or on any failure → returns an "unknown" topology with a single
"all cores" target, so callers can degrade gracefully.
"""

from __future__ import annotations
import ctypes
import platform
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

# ── Win32 constants ───────────────────────────────────────────────────────────
_RelationCache = 2
_RelationAll = 0xFFFF
_CpuSetInformation = 0  # SYSTEM_CPU_SET_INFORMATION_TYPE.CpuSetInformation


@dataclass
class LogicalCpu:
    cpuset_id: int          # Id passed to SetProcessDefaultCpuSets
    logical_index: int      # 0-based logical processor index
    core_index: int         # physical core (SMT siblings share this)
    llc_index: int          # last-level (L3) cache index → identifies a CCD
    efficiency_class: int   # higher = more performant (Intel: P > E)
    group: int = 0


@dataclass
class Ccd:
    """A group of cores sharing one L3 cache (an AMD chiplet, or a cache domain)."""
    llc_index: int
    logicals: list[int]       # logical processor indices
    l3_bytes: int = 0         # L3 size in bytes (0 = unknown)


@dataclass
class PinTarget:
    """A selectable set of cores a game can be pinned to."""
    key: str                  # stable id stored per-game (e.g. "cache_ccd")
    label: str                # human label (DE)
    logicals: list[int]       # logical indices this target covers


@dataclass
class CpuTopology:
    ok: bool = False
    vendor: str = ""                       # "AMD" / "Intel" / ""
    physical_cores: int = 0
    logical_cpus: int = 0
    is_hybrid: bool = False                # Intel P/E
    cpus: list[LogicalCpu] = field(default_factory=list)
    ccds: list[Ccd] = field(default_factory=list)
    p_cores: list[int] = field(default_factory=list)
    e_cores: list[int] = field(default_factory=list)
    cache_ccd_index: int = -1              # index into .ccds of the X3D cache die (-1 = none/unknown)
    note: str = ""

    def all_logicals(self) -> list[int]:
        return [c.logical_index for c in self.cpus]

    def pin_targets(self) -> list[PinTarget]:
        """The set of pinning options that make sense for THIS machine."""
        targets: list[PinTarget] = [
            PinTarget("all", "Alle Kerne (kein Pinning)", self.all_logicals())
        ]
        # Intel hybrid: P-cores / E-cores
        if self.is_hybrid and self.p_cores:
            targets.append(PinTarget(
                "p_cores", f"Nur P-Cores ({len(self.p_cores)} Threads)", list(self.p_cores)))
            if self.e_cores:
                targets.append(PinTarget(
                    "e_cores", f"Nur E-Cores ({len(self.e_cores)} Threads)", list(self.e_cores)))
        # AMD (or any) multi-CCD: cache die + individual chiplets
        if len(self.ccds) > 1:
            if self.cache_ccd_index >= 0:
                ccd = self.ccds[self.cache_ccd_index]
                mb = ccd.l3_bytes // (1024 * 1024)
                targets.append(PinTarget(
                    "cache_ccd",
                    f"X3D-Cache-Chiplet (CCD{self.cache_ccd_index}, {mb}MB L3)",
                    list(ccd.logicals)))
            for i, ccd in enumerate(self.ccds):
                mb = ccd.l3_bytes // (1024 * 1024)
                targets.append(PinTarget(
                    f"ccd{i}", f"Chiplet CCD{i} ({len(ccd.logicals)} Threads, {mb}MB L3)",
                    list(ccd.logicals)))
        return targets

    def target_logicals(self, key: str) -> Optional[list[int]]:
        """Resolve a stored target key to logical indices (None = unknown key)."""
        if not key or key == "all":
            return None  # no pinning
        for t in self.pin_targets():
            if t.key == key:
                return t.logicals
        return None


# ── Win32 access ──────────────────────────────────────────────────────────────

def _get_cpu_set_info() -> list[LogicalCpu]:
    """GetSystemCpuSetInformation → per-logical-CPU records."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = k32.GetSystemCpuSetInformation
    fn.restype = wintypes.BOOL
    fn.argtypes = [ctypes.c_void_p, wintypes.ULONG,
                   ctypes.POINTER(wintypes.ULONG), wintypes.HANDLE, wintypes.ULONG]

    needed = wintypes.ULONG(0)
    fn(None, 0, ctypes.byref(needed), None, 0)
    size = needed.value
    if size == 0:
        return []
    buf = (ctypes.c_byte * size)()
    if not fn(buf, size, ctypes.byref(needed), None, 0):
        return []

    raw = bytes(buf)
    out: list[LogicalCpu] = []
    off = 0
    while off + 8 <= len(raw):
        rec_size = int.from_bytes(raw[off:off + 4], "little")
        rec_type = int.from_bytes(raw[off + 4:off + 8], "little")
        if rec_size == 0:
            break
        if rec_type == _CpuSetInformation and off + 20 <= len(raw):
            # struct CpuSet layout after the 8-byte header:
            #  Id(DWORD)@8  Group(WORD)@12  LogicalProcessorIndex(BYTE)@14
            #  CoreIndex(BYTE)@15  LastLevelCacheIndex(BYTE)@16
            #  NumaNodeIndex(BYTE)@17  EfficiencyClass(BYTE)@18
            cid = int.from_bytes(raw[off + 8:off + 12], "little")
            group = int.from_bytes(raw[off + 12:off + 14], "little")
            lp = raw[off + 14]
            core = raw[off + 15]
            llc = raw[off + 16]
            eff = raw[off + 18]
            out.append(LogicalCpu(cid, lp, core, llc, eff, group))
        off += rec_size
    return out


def _get_l3_masks() -> list[tuple[int, int, int]]:
    """GetLogicalProcessorInformationEx(RelationCache) → L3 cache entries.
    Returns list of (size_bytes, group, affinity_mask) for level-3 caches."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = k32.GetLogicalProcessorInformationEx
    fn.restype = wintypes.BOOL
    fn.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]

    length = wintypes.DWORD(0)
    fn(_RelationAll, None, ctypes.byref(length))
    size = length.value
    if size == 0:
        return []
    buf = (ctypes.c_byte * size)()
    if not fn(_RelationAll, buf, ctypes.byref(length)):
        return []

    raw = bytes(buf)
    out: list[tuple[int, int, int]] = []
    off = 0
    while off + 8 <= len(raw):
        relationship = int.from_bytes(raw[off:off + 4], "little")
        rec_size = int.from_bytes(raw[off + 4:off + 8], "little")
        if rec_size == 0:
            break
        if relationship == _RelationCache:
            # CACHE_RELATIONSHIP after 8-byte header (Win10+ layout):
            #  Level(BYTE)@8  Assoc(BYTE)@9  LineSize(WORD)@10  CacheSize(DWORD)@12
            #  Type(DWORD)@16  Reserved[18]@20  GroupCount(WORD)@38  GroupMask@40
            level = raw[off + 8]
            cache_size = int.from_bytes(raw[off + 12:off + 16], "little")
            if level == 3 and off + 50 <= len(raw):
                mask = int.from_bytes(raw[off + 40:off + 48], "little")
                grp = int.from_bytes(raw[off + 48:off + 50], "little")
                out.append((cache_size, grp, mask))
        off += rec_size
    return out


def detect() -> CpuTopology:
    """Detect CPU topology. Safe on any platform — returns ok=False on failure."""
    topo = CpuTopology()
    if platform.system() != "Windows":
        topo.note = "CPU-Pinning nur unter Windows verfügbar."
        return topo

    try:
        cpus = _get_cpu_set_info()
        if not cpus:
            topo.note = "CPU-Topologie konnte nicht gelesen werden."
            return topo

        topo.cpus = cpus
        topo.logical_cpus = len(cpus)
        topo.physical_cores = len({c.core_index for c in cpus})
        try:
            topo.vendor = platform.processor()
            name = (topo.vendor or "").lower()
            topo.vendor = "AMD" if ("amd" in name or "ryzen" in name) else (
                "Intel" if "intel" in name else "")
        except Exception:
            topo.vendor = ""

        # Hybrid (Intel P/E): efficiency classes differ
        eff_classes = {c.efficiency_class for c in cpus}
        topo.is_hybrid = len(eff_classes) > 1
        if topo.is_hybrid:
            max_eff = max(eff_classes)
            topo.p_cores = sorted(c.logical_index for c in cpus if c.efficiency_class == max_eff)
            topo.e_cores = sorted(c.logical_index for c in cpus if c.efficiency_class != max_eff)

        # CCDs = groups of logicals sharing an L3 (LastLevelCacheIndex)
        by_llc: dict[int, list[int]] = {}
        for c in cpus:
            by_llc.setdefault(c.llc_index, []).append(c.logical_index)
        ccds = [Ccd(llc, sorted(logs)) for llc, logs in sorted(by_llc.items())]

        # Attach L3 sizes (to identify the X3D cache die)
        l3 = _get_l3_masks()
        for ccd in ccds:
            # Match a CCD to an L3 entry: the L3 whose affinity mask covers this CCD's cores
            for size, grp, mask in l3:
                covered = [i for i in ccd.logicals if mask & (1 << i)]
                if covered and len(covered) >= len(ccd.logicals) // 2 + 1:
                    ccd.l3_bytes = max(ccd.l3_bytes, size)
        topo.ccds = ccds

        # The X3D cache die = the CCD with the largest L3 (only if sizes actually differ)
        if len(ccds) > 1:
            sizes = [c.l3_bytes for c in ccds]
            if any(sizes) and len(set(sizes)) > 1:
                topo.cache_ccd_index = max(range(len(ccds)), key=lambda i: ccds[i].l3_bytes)

        topo.ok = True

        # Honest guidance note
        if topo.is_hybrid:
            topo.note = (f"Intel Hybrid erkannt: {len(topo.p_cores)} P-Threads / "
                         f"{len(topo.e_cores)} E-Threads.")
        elif len(ccds) <= 1:
            topo.note = ("Single-Chiplet-CPU: Alle Kerne teilen sich denselben Cache — "
                         "Pinning bringt hier keinen Vorteil.")
        elif topo.cache_ccd_index >= 0:
            mb = ccds[topo.cache_ccd_index].l3_bytes // (1024 * 1024)
            topo.note = (f"Dual-Chiplet mit X3D-Cache erkannt: CCD{topo.cache_ccd_index} "
                         f"trägt {mb}MB L3 (Cache-Die).")
        else:
            topo.note = f"{len(ccds)} Chiplets erkannt (gleicher Cache — kein X3D-Vorteil)."

    except Exception as e:
        topo.ok = False
        topo.note = f"Topologie-Erkennung fehlgeschlagen: {e}"
    return topo


# Manual smoke test
if __name__ == "__main__":
    t = detect()
    print(f"ok={t.ok} vendor={t.vendor} cores={t.physical_cores} logical={t.logical_cpus}")
    print(f"hybrid={t.is_hybrid} p={t.p_cores} e={t.e_cores}")
    print(f"note: {t.note}")
    for i, ccd in enumerate(t.ccds):
        print(f"  CCD{i}: L3={ccd.l3_bytes//(1024*1024)}MB logicals={ccd.logicals}"
              f"{'  <-- cache die' if i == t.cache_ccd_index else ''}")
    print("Pin targets:")
    for pt in t.pin_targets():
        print(f"  [{pt.key}] {pt.label} -> {pt.logicals}")
