"""
MAHM Shared Memory Reader
Reads live GPU telemetry directly from MSI Afterburner's shared memory segment.
Gives us real voltage in mV, all clocks, temps, power - much richer than NVML alone.

Source IDs from MAHMSharedMemory.h (official AB SDK):
  0  = GPU Temp         16 = Fan Speed       17 = Fan RPM
  32 = Core Clock       33 = Shader Clock    34 = Memory Clock
  48 = GPU Usage        49 = Memory Usage    50 = Framebuffer Usage
  52 = Bus Usage        64 = GPU Voltage     65 = Aux Voltage
  66 = Memory Voltage   80 = Framerate       81 = Frametime
  96 = GPU Power       112 = Temp Limit     113 = Power Limit
 114 = Voltage Limit   116 = Util Limit     256 = CPU Power
The *Limit sources are limiter FLAGS (0/1 = "this limiter is active"), not
values in °C / W.

Shared-memory layout (MAHMSharedMemory.h v2.0 — cross-checked against two
independent readers: LCDHost's C++ header and CleanMeter's Kotlin reader):

  MAHM_SHARED_MEMORY_HEADER (32 bytes)
    @0  dwSignature  'MAHM' (0xDEAD while Afterburner shuts down)
    @4  dwVersion    @8  dwHeaderSize   @12 dwNumEntries   @16 dwEntrySize
    @20 time (32-bit)                   @24 dwNumGpuEntries @28 dwGpuEntrySize

  MAHM_SHARED_MEMORY_ENTRY (1324 bytes in v2.0), starting at dwHeaderSize,
  stride dwEntrySize:
    @0    szSrcName[260]         @260  szSrcUnits[260]
    @520  szLocalizedSrcName     @780  szLocalizedSrcUnits
    @1040 szRecommendedFormat    @1300 float data
    @1304 float minLimit         @1308 float maxLimit    @1312 dwFlags
    @1316 dwGpu (0-based, 0xFFFFFFFF = global)           @1320 dwSrcId

The previous parser assumed a 284-byte entry with the value at @268 and read
dwHeaderSize as the entry count — against a real Afterburner image it
returned 0 for every sensor while reporting "available".
"""

import ctypes
import os
import struct
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

# ── Win32: open an EXISTING named section read-only (never create one) ───────
# The old code used mmap.mmap(-1, 1 MB, tagname="MAHMSharedMemory"). On Windows
# that CREATES a 1 MB pagefile-backed section under Afterburner's name whenever
# Afterburner isn't running — and on a signature mismatch the handle was never
# closed, so GameOptimizerPro squatted Afterburner's shared-memory name for the
# whole session. OpenFileMappingW only ever opens what Afterburner created.
_FILE_MAP_READ = 0x0004


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_void_p),
        ("AllocationBase",    ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId",       wintypes.WORD),
        ("RegionSize",        ctypes.c_size_t),
        ("State",             wintypes.DWORD),
        ("Protect",           wintypes.DWORD),
        ("Type",              wintypes.DWORD),
    ]


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenFileMappingW.restype  = wintypes.HANDLE
    k.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.MapViewOfFile.restype     = ctypes.c_void_p
    k.MapViewOfFile.argtypes    = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_size_t]
    k.UnmapViewOfFile.restype   = wintypes.BOOL
    k.UnmapViewOfFile.argtypes  = [ctypes.c_void_p]
    k.VirtualQuery.restype      = ctypes.c_size_t
    k.VirtualQuery.argtypes     = [ctypes.c_void_p,
                                   ctypes.POINTER(_MEMORY_BASIC_INFORMATION),
                                   ctypes.c_size_t]
    k.CloseHandle.restype       = wintypes.BOOL
    k.CloseHandle.argtypes      = [wintypes.HANDLE]
    return k

# ── MAHM memory layout constants ─────────────────────────────────────────────
MAHM_SHARED_MEMORY_NAME    = "MAHMSharedMemory"
MAHM_SIGNATURE             = 0x4D41484D   # 'MAHM'
MAHM_MAX_SOURCES           = 1024         # sanity cap (plugins can add many sources)
MAHM_HEADER_SIZE           = 32           # v2.0 header (v1.x header = 24 bytes)
MAHM_MIN_HEADER_SIZE       = 24

# Entry field offsets (see module docstring)
_OFF_NAME   = 0
_OFF_UNITS  = 260
_OFF_DATA   = 1300
_OFF_GPU    = 1316
_OFF_SRCID  = 1320
MAHM_ENTRY_V1_SIZE = 1316   # up to and incl. dwFlags (no dwGpu / dwSrcId)
MAHM_ENTRY_V2_SIZE = 1324   # + dwGpu + dwSrcId
MAHM_MAX_ENTRY_SIZE = 8192  # sanity cap for dwEntrySize
_GLOBAL_GPU = 0xFFFFFFFF

# Source IDs
SRC_GPU_TEMP       = 0
SRC_FAN_SPEED      = 16
SRC_FAN_RPM        = 17
SRC_CORE_CLOCK     = 32
SRC_SHADER_CLOCK   = 33
SRC_MEM_CLOCK      = 34
SRC_GPU_USAGE      = 48
SRC_MEM_USAGE      = 49
SRC_VRAM_USAGE     = 50
SRC_BUS_USAGE      = 52
SRC_GPU_VOLTAGE    = 64
SRC_AUX_VOLTAGE    = 65
SRC_MEM_VOLTAGE    = 66
SRC_FRAMERATE      = 80
SRC_FRAMETIME      = 81
SRC_GPU_POWER      = 96
SRC_TEMP_LIMIT     = 112
SRC_POWER_LIMIT    = 113
SRC_VOLTAGE_LIMIT  = 114
SRC_UTIL_LIMIT     = 116
SRC_CPU_POWER      = 256   # 0x100 — the old `src_id & 0xFF` turned this into GPU temp

# Fallback for v1.x entries that carry no dwSrcId: match on the source name.
_NAME_TO_SRC = {
    "gpu temperature": SRC_GPU_TEMP, "fan speed": SRC_FAN_SPEED,
    "fan tachometer": SRC_FAN_RPM, "core clock": SRC_CORE_CLOCK,
    "shader clock": SRC_SHADER_CLOCK, "memory clock": SRC_MEM_CLOCK,
    "gpu usage": SRC_GPU_USAGE, "fb usage": SRC_VRAM_USAGE,
    "bus usage": SRC_BUS_USAGE, "gpu voltage": SRC_GPU_VOLTAGE,
    "memory voltage": SRC_MEM_VOLTAGE, "framerate": SRC_FRAMERATE,
    "frametime": SRC_FRAMETIME, "power": SRC_GPU_POWER,
}


@dataclass
class MAHMData:
    """All telemetry from MAHM shared memory."""
    available:      bool  = False
    gpu_temp:       float = 0.0     # °C
    fan_speed_pct:  float = 0.0     # %
    fan_rpm:        float = 0.0     # RPM
    core_clock:     float = 0.0     # MHz
    shader_clock:   float = 0.0     # MHz
    mem_clock:      float = 0.0     # MHz
    gpu_usage:      float = 0.0     # %
    mem_usage:      float = 0.0     # %
    vram_usage:     float = 0.0     # %
    bus_usage:      float = 0.0     # %
    gpu_voltage_mv: float = 0.0     # mV  ← the important one
    aux_voltage_mv: float = 0.0     # mV
    mem_voltage_mv: float = 0.0     # mV
    framerate:      float = 0.0     # fps
    frametime:      float = 0.0     # ms
    gpu_power_w:    float = 0.0     # W
    # Limiter FLAGS (Afterburner's "Temp/Power/Voltage/Util limit" graphs are
    # 0/1 "limiter active" indicators — NOT a temperature or wattage).
    temp_limit_active:    bool = False
    power_limit_active:   bool = False
    voltage_limit_active: bool = False
    util_limit_active:    bool = False
    num_entries:    int   = 0


class MAHMReader:
    """
    Reads MSI Afterburner Hardware Monitor shared memory.
    Falls back gracefully when AB is not running.
    """

    # Afterburner may be started AFTER GameOptimizerPro. read() retries opening
    # the section at most this often (OpenFileMappingW is cheap).
    RETRY_INTERVAL_S = 5.0

    def __init__(self):
        self._handle = None           # section handle (from OpenFileMappingW)
        self._view   = None           # base address of the mapped view
        self._view_size = 0           # size of the mapped view in bytes
        self._available = False
        self._error = ""
        self._last_try = 0.0
        self._try_open()

    def _release(self):
        """Unmap the view and close the section handle (idempotent)."""
        if os.name != "nt":
            self._handle = self._view = None
            self._view_size = 0
            return
        try:
            k = _k32()
            if self._view:
                k.UnmapViewOfFile(self._view)
            if self._handle:
                k.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None
        self._view = None
        self._view_size = 0

    def _try_open(self):
        self._last_try = time.monotonic()
        self._release()
        self._available = False
        if os.name != "nt":
            self._error = "MAHM nur unter Windows verfügbar."
            return
        try:
            k = _k32()
            h = k.OpenFileMappingW(_FILE_MAP_READ, False, MAHM_SHARED_MEMORY_NAME)
            if not h:
                # Normal case when Afterburner isn't running — nothing is created.
                self._error = "Afterburner-Shared-Memory nicht vorhanden (Afterburner läuft nicht)."
                return
            # Length 0 maps the WHOLE section, whatever size Afterburner chose.
            view = k.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
            if not view:
                k.CloseHandle(h)
                self._error = f"MapViewOfFile fehlgeschlagen (Win32 {ctypes.get_last_error()})"
                return
            mbi = _MEMORY_BASIC_INFORMATION()
            size = 0
            if k.VirtualQuery(view, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                size = int(mbi.RegionSize)
            self._handle, self._view, self._view_size = h, view, size
            if size < MAHM_HEADER_SIZE:
                self._error = f"MAHM-Section zu klein ({size} Bytes)"
                self._release()
                return
            sig = struct.unpack_from("<I", self._bytes(4))[0]
            if sig != MAHM_SIGNATURE:  # 0xDEAD while Afterburner shuts down
                self._error = f"MAHM signature mismatch: {sig:#010x}"
                self._release()    # never keep a handle to a section we can't use
                return
            self._error = ""
            self._available = True
        except Exception as e:
            self._error = str(e)
            self._release()

    def _bytes(self, n: int) -> bytes:
        """Copy up to n bytes from the start of the mapped view."""
        if not self._view:
            return b""
        return ctypes.string_at(self._view, min(n, self._view_size))

    def reopen(self):
        """Force a reconnect attempt (e.g. right after Afterburner was started)."""
        self._try_open()

    @property
    def available(self):
        return self._available

    @property
    def error(self):
        return self._error

    def read(self) -> MAHMData:
        data = MAHMData()
        if not self._available or not self._view:
            # Lazy reconnect: Afterburner may have been started after us.
            if time.monotonic() - self._last_try >= self.RETRY_INTERVAL_S:
                self._try_open()
            if not self._available or not self._view:
                return data

        try:
            head = self._bytes(MAHM_HEADER_SIZE)
            if len(head) < MAHM_MIN_HEADER_SIZE:
                return data
            sig, _ver, hdr_size, n_entries, entry_size = struct.unpack_from("<IIIII", head, 0)
            if sig != MAHM_SIGNATURE:
                # Afterburner is shutting down (0xDEAD) or gone — let go of the
                # section so it can be destroyed; read() will reconnect later.
                self._available = False
                self._release()
                return data

            # Plausibility — never trust a header blindly.
            if (not MAHM_MIN_HEADER_SIZE <= hdr_size <= 4096
                    or not MAHM_ENTRY_V1_SIZE <= entry_size <= MAHM_MAX_ENTRY_SIZE
                    or n_entries > MAHM_MAX_SOURCES):
                self._error = (f"MAHM-Header unplausibel (header={hdr_size}, "
                               f"entry={entry_size}, entries={n_entries})")
                return data

            raw = self._bytes(hdr_size + n_entries * entry_size)
            n_entries = min(n_entries, max(0, (len(raw) - hdr_size) // entry_size))
            has_ids = entry_size >= MAHM_ENTRY_V2_SIZE

            data.available   = True
            data.num_entries = n_entries

            for i in range(n_entries):
                off = hdr_size + i * entry_size
                name  = raw[off + _OFF_NAME:off + _OFF_NAME + 260].split(b"\x00")[0] \
                            .decode("utf-8", errors="replace")
                units = raw[off + _OFF_UNITS:off + _OFF_UNITS + 260].split(b"\x00")[0] \
                            .decode("utf-8", errors="replace")
                val = struct.unpack_from("<f", raw, off + _OFF_DATA)[0]
                if has_ids:
                    gpu, src_id = struct.unpack_from("<II", raw, off + _OFF_GPU)
                else:                           # v1.x entries: no dwGpu / dwSrcId
                    gpu, src_id = 0, _NAME_TO_SRC.get(name.strip().lower())
                    if src_id is None:
                        continue
                # Only the first GPU (index 0) and global sources. Multi-GPU
                # systems used to let GPU 2's values overwrite GPU 1's.
                if gpu not in (0, _GLOBAL_GPU):
                    continue
                if val != val:                  # NaN guard
                    continue
                self._apply_entry(data, src_id, name, val, units)

        except Exception as e:
            self._error = str(e)
            # Don't mark unavailable for transient errors

        return data

    def _apply_entry(self, data: MAHMData, src_id: int, name: str, val: float, units: str):
        """Map source IDs to MAHMData fields. src_id is used as-is: the GPU index
        lives in dwGpu. (The old `src_id & 0xFF` mapped CPU power, 0x100, onto
        GPU temperature.)"""
        def v_to_mv(v):
            # Afterburner reports voltages in V ("V" units); accept mV as well.
            if units.strip().lower() == "mv":
                return v
            return v * 1000.0 if v < 10.0 else v

        sid = src_id
        if   sid == SRC_GPU_TEMP:      data.gpu_temp       = val
        elif sid == SRC_FAN_SPEED:     data.fan_speed_pct  = val
        elif sid == SRC_FAN_RPM:       data.fan_rpm        = val
        elif sid == SRC_CORE_CLOCK:    data.core_clock     = val
        elif sid == SRC_SHADER_CLOCK:  data.shader_clock   = val
        elif sid == SRC_MEM_CLOCK:     data.mem_clock      = val
        elif sid == SRC_GPU_USAGE:     data.gpu_usage      = val
        elif sid == SRC_MEM_USAGE:     data.mem_usage      = val
        elif sid == SRC_VRAM_USAGE:    data.vram_usage     = val
        elif sid == SRC_BUS_USAGE:     data.bus_usage      = val
        elif sid == SRC_GPU_VOLTAGE:   data.gpu_voltage_mv = v_to_mv(val)
        elif sid == SRC_AUX_VOLTAGE:   data.aux_voltage_mv = v_to_mv(val)
        elif sid == SRC_MEM_VOLTAGE:   data.mem_voltage_mv = v_to_mv(val)
        elif sid == SRC_FRAMERATE:     data.framerate      = val
        elif sid == SRC_FRAMETIME:     data.frametime      = val
        elif sid == SRC_GPU_POWER:     data.gpu_power_w    = val
        elif sid == SRC_TEMP_LIMIT:    data.temp_limit_active    = val >= 0.5
        elif sid == SRC_POWER_LIMIT:   data.power_limit_active   = val >= 0.5
        elif sid == SRC_VOLTAGE_LIMIT: data.voltage_limit_active = val >= 0.5
        elif sid == SRC_UTIL_LIMIT:    data.util_limit_active    = val >= 0.5

    def close(self):
        self._release()
        self._available = False
