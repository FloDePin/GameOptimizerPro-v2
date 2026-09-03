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
import mmap
import struct
from dataclasses import dataclass, field
from typing import Optional

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

    def __init__(self):
        self._mm: Optional[mmap.mmap] = None
        self._available = False
        self._error = ""
        self._try_open()

    def _try_open(self):
        try:
            self._mm = mmap.mmap(
                -1,
                1 << 20,   # 1 MB should cover any AB version
                tagname=MAHM_SHARED_MEMORY_NAME,
                access=mmap.ACCESS_READ
            )
            # Quick sanity check: read signature
            self._mm.seek(0)
            sig = struct.unpack_from("<I", self._mm.read(4))[0]
            if sig != 0x4D41484D:  # 'MAHM' in little-endian
                self._available = False
                self._error = f"MAHM signature mismatch: {sig:#010x}"
                return
            self._available = True
        except Exception as e:
            self._available = False
            self._error = str(e)
            self._mm = None

    def reopen(self):
        """Try to reconnect (call when AB is started)."""
        if self._mm:
            try:
                self._mm.close()
            except:
                pass
            self._mm = None
        self._try_open()

    @property
    def available(self):
        return self._available

    @property
    def error(self):
        return self._error

    def read(self) -> MAHMData:
        data = MAHMData()
        if not self._available or not self._mm:
            return data

        try:
            self._mm.seek(0)
            # Size the buffer with the MAX possible entry size — the real stride
            # (read from the header below) can be larger than the nominal 260, and
            # a too-small buffer would silently drop the last entries.
            raw = self._mm.read(MAHM_HEADER_SIZE + MAHM_MAX_SOURCES * MAHM_MAX_ENTRY_SIZE)

            # Parse header
            sig, ver, n_entries, n_gpu_entries = struct.unpack_from("<IIII", raw, 0)
            if sig != 0x4D41484D:
                self._available = False
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
        if self._mm:
            try:
                self._mm.close()
            except:
                pass
            self._mm = None
