"""
GameOptimizerPro Hardware Detection
CPU, GPU, RAM, Mainboard, OS — via wmi (Windows) with fallbacks.
"""

import os, platform, subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HardwareInfo:
    # CPU
    cpu_name:       str  = "Unknown CPU"
    cpu_cores:      int  = 0
    cpu_threads:    int  = 0
    cpu_freq_mhz:   int  = 0
    cpu_vendor:     str  = ""       # Intel / AMD
    # GPU
    gpu_name:       str  = "Unknown GPU"
    gpu_vram_mb:    int  = 0
    gpu_vendor:     str  = ""       # NVIDIA / AMD / Intel
    is_nvidia:      bool = False
    is_amd_gpu:     bool = False
    # RAM
    ram_total_gb:   float = 0.0
    ram_slots_used: int   = 0
    ram_speed_mhz:  int   = 0
    ram_type:       str   = ""      # DDR4 / DDR5
    # Mainboard
    mb_manufacturer: str = ""
    mb_product:      str = ""
    # OS
    os_name:        str  = ""
    os_build:       int  = 0
    is_win11:       bool = False
    is_win10:       bool = False
    # NVMe
    has_nvme:       bool = False
    nvme_count:     int  = 0
    # Summary string
    summary:        str  = ""


def detect() -> HardwareInfo:
    info = HardwareInfo()

    try:
        import wmi
        c = wmi.WMI()

        # CPU
        try:
            cpus = c.Win32_Processor()
            if cpus:
                cpu = cpus[0]
                info.cpu_name    = cpu.Name.strip() if cpu.Name else "Unknown CPU"
                info.cpu_cores   = int(cpu.NumberOfCores or 0)
                info.cpu_threads = int(cpu.NumberOfLogicalProcessors or 0)
                info.cpu_freq_mhz = int(cpu.MaxClockSpeed or 0)
                n = info.cpu_name.lower()
                if "intel" in n:   info.cpu_vendor = "Intel"
                elif "amd" in n:   info.cpu_vendor = "AMD"
                elif "ryzen" in n: info.cpu_vendor = "AMD"
        except: pass

        # GPU
        try:
            gpus = [g for g in c.Win32_VideoController()
                    if g.Name and "microsoft" not in g.Name.lower()]
            if gpus:
                gpu = gpus[0]
                info.gpu_name    = gpu.Name.strip()
                # AdapterRAM is a 32-bit DWORD — wraps at 4GB for > 4GB cards
                # RTX 4080 has 16GB but AdapterRAM returns ~0x100000000 which wraps to 0 or negative
                # Prefer NVML value if available, use WMI only as fallback
                raw = int(gpu.AdapterRAM or 0)
                if raw < 0:  # signed integer overflow for > 4GB GPUs
                    raw = raw + 2**32
                info.gpu_vram_mb = raw // (1024 * 1024)
                n = info.gpu_name.lower()
                if "nvidia" in n:
                    info.gpu_vendor = "NVIDIA"
                    info.is_nvidia  = True
                elif "amd" in n or "radeon" in n:
                    info.gpu_vendor = "AMD"
                    info.is_amd_gpu = True
                elif "intel" in n:
                    info.gpu_vendor = "Intel"
        except: pass

        # RAM
        try:
            sticks = c.Win32_PhysicalMemory()
            if sticks:
                total = sum(int(s.Capacity or 0) for s in sticks)
                info.ram_total_gb  = round(total / (1024**3), 1)
                info.ram_slots_used = len(sticks)
                speeds = [int(s.Speed or 0) for s in sticks if s.Speed]
                if speeds: info.ram_speed_mhz = max(speeds)
                mem_types = {20: "DDR", 21: "DDR2", 22: "DDR2 FB",
                             24: "DDR3", 26: "DDR4", 34: "DDR5"}
                mt = sticks[0].MemoryType or 0
                info.ram_type = mem_types.get(int(mt), f"Type {mt}")
        except: pass

        # Mainboard
        try:
            boards = c.Win32_BaseBoard()
            if boards:
                info.mb_manufacturer = (boards[0].Manufacturer or "").strip()
                info.mb_product      = (boards[0].Product or "").strip()
        except: pass

        # OS
        try:
            os_info = c.Win32_OperatingSystem()[0]
            info.os_name  = (os_info.Caption or "").strip()
            info.os_build = int(os_info.BuildNumber or 0)
            info.is_win11 = info.os_build >= 22000
            info.is_win10 = 10240 <= info.os_build < 22000
        except: pass

        # NVMe
        try:
            disks = c.Win32_DiskDrive()
            nvme = [d for d in disks if d.Model and
                    ("nvme" in d.Model.lower() or "nvme" in (d.InterfaceType or "").lower())]
            info.has_nvme  = len(nvme) > 0
            info.nvme_count = len(nvme)
        except: pass

    except ImportError:
        # wmi not available — fallback via platform + subprocess
        info.cpu_name  = platform.processor() or "Unknown CPU"
        info.os_name   = platform.version()
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed", "/format:csv"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
            )
            # wmic /format:csv sorts columns ALPHABETICALLY, not in the requested
            # order (Node,MaxClockSpeed,Name,NumberOfCores,NumberOfLogicalProcessors),
            # so parse the header row and map columns BY NAME instead of by position.
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) >= 2:
                header = [h.strip() for h in lines[0].split(",")]
                idx = {name: i for i, name in enumerate(header)}
                for line in lines[1:]:
                    parts = line.split(",")
                    def _col(name):
                        i = idx.get(name, -1)
                        return parts[i].strip() if 0 <= i < len(parts) else ""
                    name = _col("Name")
                    if not name:
                        continue
                    info.cpu_name     = name
                    freq              = _col("MaxClockSpeed")
                    cores             = _col("NumberOfCores")
                    threads           = _col("NumberOfLogicalProcessors")
                    info.cpu_freq_mhz = int(freq) if freq.isdigit() else 0
                    info.cpu_cores    = int(cores) if cores.isdigit() else 0
                    info.cpu_threads  = int(threads) if threads.isdigit() else info.cpu_threads
                    break
        except: pass

    except Exception as e:
        info.cpu_name = f"Detection error: {e}"

    # Build summary
    os_short = "Win11" if info.is_win11 else ("Win10" if info.is_win10 else info.os_name[:20])
    vram_str = f" ({info.gpu_vram_mb // 1024}GB)" if info.gpu_vram_mb >= 512 else ""
    info.summary = (
        f"CPU: {info.cpu_name}  |  "
        f"GPU: {info.gpu_name}{vram_str}  |  "
        f"RAM: {info.ram_total_gb:.0f}GB {info.ram_type} {info.ram_speed_mhz}MHz  |  "
        f"MB: {info.mb_manufacturer} {info.mb_product}  |  "
        f"{os_short} (Build {info.os_build})"
    )

    return info
