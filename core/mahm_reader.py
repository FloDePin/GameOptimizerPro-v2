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
 114 = Voltage Limit   116 = Util Limit
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
MAHM_MAX_SOURCES           = 256
MAHM_GPU_ENTRY_SIZE        = 688   # sizeof(MAHM_SHARED_MEMORY_GPU_ENTRY)
MAHM_ENTRY_SIZE            = 260   # nominal sizeof(MAHM_SHARED_MEMORY_ENTRY)
MAHM_MAX_ENTRY_SIZE        = 512   # upper bound used to size the read buffer, so
                                   # a larger real stride (e.g. 284) never truncates
                                   # the last sensor entries

# Header: dwSignature(4) + dwVersion(4) + dwNumEntries(4) + dwNumGpuEntries(4)
#       + time(8) + dwEntrySize(4) + dwGpuEntrySize(4)  = 32 bytes
MAHM_HEADER_SIZE = 32

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
    power_limit_w:  float = 0.0     # W
    temp_limit_c:   float = 0.0     # °C
    voltage_limit:  float = 0.0
    util_limit:     float = 0.0
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
            if sig != 0x4D41484D:  # 'MAHM' (0xDEAD while Afterburner shuts down)
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
            # Size the buffer with the MAX possible entry size — the real stride
            # (read from the header below) can be larger than the nominal 260, and
            # a too-small buffer would silently drop the last entries.
            raw = self._bytes(MAHM_HEADER_SIZE + MAHM_MAX_SOURCES * MAHM_MAX_ENTRY_SIZE)

            # Parse header
            sig, ver, n_entries, n_gpu_entries = struct.unpack_from("<IIII", raw, 0)
            if sig != 0x4D41484D:
                # Afterburner is shutting down (0xDEAD) or gone — let go of the
                # section so it can be destroyed; read() will reconnect later.
                self._available = False
                self._release()
                return data

            data.available   = True
            data.num_entries = n_entries

            # Parse each entry
            # Entry layout (260 bytes):
            # szSrcName[260-36 = 224... actually the layout is:
            # szSrcName[MAX_PATH=260] not quite. Real layout from SDK:
            #   char  szSrcName[MAX_PATH]  = 260 bytes
            #   char  szSrcUnits[8]        = 8 bytes
            #   float data                 = 4 bytes
            #   float minLimit             = 4 bytes
            #   float maxLimit             = 4 bytes
            #   DWORD dwSrcId             = 4 bytes
            #   Total = 260+8+4+4+4+4 = 284... but SDK says entry_size can vary.
            # We read dwEntrySize from header if available (byte 24).

            # Read actual entry size from header (offset 24)
            try:
                entry_size = struct.unpack_from("<I", raw, 24)[0]
                if entry_size < 64 or entry_size > 512:
                    entry_size = 284   # Fallback
            except:
                entry_size = 284

            entries_offset = MAHM_HEADER_SIZE

            for i in range(min(n_entries, MAHM_MAX_SOURCES)):
                offset = entries_offset + i * entry_size
                if offset + entry_size > len(raw):
                    break

                # szSrcName: first 260 bytes, null-terminated
                name_raw = raw[offset:offset + 260]
                name = name_raw.split(b'\x00')[0].decode('utf-8', errors='replace')

                # data float at offset 260+8 = 268
                # units at offset 260
                units_raw = raw[offset + 260:offset + 268]
                units = units_raw.split(b'\x00')[0].decode('utf-8', errors='replace')

                val   = struct.unpack_from("<f", raw, offset + 268)[0]
                # dwSrcId at offset 268+4+4+4 = 280
                src_id = struct.unpack_from("<I", raw, offset + 280)[0]

                self._apply_entry(data, src_id, name, val, units)

        except Exception as e:
            self._error = str(e)
            # Don't mark unavailable for transient errors

        return data

    def _apply_entry(self, data: MAHMData, src_id: int, name: str, val: float, units: str):
        """Map source IDs to MAHMData fields."""
        # Voltage: AB reports in V, we want mV
        def v_to_mv(v):
            return v * 1000.0 if v < 10.0 else v   # AB usually reports in V

        sid = src_id & 0xFF  # Strip GPU index bits (upper bytes = GPU index)

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
        elif sid == SRC_POWER_LIMIT:   data.power_limit_w  = val
        elif sid == SRC_TEMP_LIMIT:    data.temp_limit_c   = val
        elif sid == SRC_VOLTAGE_LIMIT: data.voltage_limit  = val
        elif sid == SRC_UTIL_LIMIT:    data.util_limit     = val

    def close(self):
        self._release()
        self._available = False
