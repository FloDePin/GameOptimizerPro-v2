"""
GameOptimizerPro v2.0 — BIOS state detector
Reads what Windows can really tell about BIOS settings, read-only. Only
settings with a reliable signal get a result; everything else stays "not
detectable" (grey) instead of a guess:

  expo_xmp     RAM's configured clock vs. the JEDEC ceiling of its DDR type
  rebar        NVIDIA: the BAR1 aperture from the driver (256 MB = off, the
               whole VRAM = on); other GPUs: not detectable
  secure_boot  the UEFI Secure Boot state Windows records (no admin needed)
  csm          Legacy boot = CSM is on; Secure Boot on = CSM is off

The old checks guessed: ReBAR from HAGS plus Win32_VideoController.AdapterRAM
(a 32-bit value that never shows more than 4 GB), XMP from "> 3200 MHz" (true
for any DDR5 at stock), PBO from the reported maximum clock (it is the base
clock on most CPUs) — green dots that meant nothing.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class DetectResult:
    setting_id:  str
    active:      bool           # True = the recommendation is already in place
    detected_val: str = ""      # what was measured
    confidence:  str = "high"   # "high" | "medium" | "low"
    note:        str = ""


def _run_ps(cmd: str) -> str:
    """Run PowerShell silently, return stdout ('' on any failure)."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            creationflags=flags)
        return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# One PowerShell start gathers every raw value (each start costs ~0.5-1 s).
_BUNDLE_PS = r"""
$d=@{}
$m=Get-CimInstance Win32_PhysicalMemory -EA SilentlyContinue | Sort-Object ConfiguredClockSpeed -Descending | Select-Object -First 1
$d.ram_speed=$m.ConfiguredClockSpeed
$d.ram_type=$m.SMBIOSMemoryType
$d.secureboot=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled -EA SilentlyContinue).UEFISecureBootEnabled
$d.firmware=$env:firmware_type
$d | ConvertTo-Json -Compress
"""

# Highest JEDEC (non-profile) speed per SMBIOS memory type
_JEDEC_MAX = {24: (1600, "DDR3"), 26: (3200, "DDR4"), 34: (5600, "DDR5")}


def _bar1_mb() -> Optional[tuple]:
    """(BAR1 aperture MB, VRAM MB) of NVIDIA GPU 0 via NVML, or None."""
    try:
        import pynvml
        pynvml.nvmlInit()
    except Exception:
        return None
    try:
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        bar1 = pynvml.nvmlDeviceGetBAR1MemoryInfo(h).bar1Total / 2 ** 20
        vram = pynvml.nvmlDeviceGetMemoryInfo(h).total / 2 ** 20
        return bar1, vram
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()       # NVML counts inits: the app's own session stays
        except Exception:
            pass


class BiosDetector:
    def _gather(self) -> dict:
        out = _run_ps(_BUNDLE_PS)
        try:
            d = json.loads(out) if out else {}
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}

    def detect_all(self) -> dict:
        """setting key -> DetectResult, only for what could be measured."""
        data = self._gather()
        results = {}
        for key, fn in (("expo_xmp", self.detect_memory_profile), ("rebar", self.detect_rebar),
                        ("secure_boot", self.detect_secure_boot), ("csm", self.detect_csm)):
            try:
                r = fn(data)
            except Exception:
                r = None
            if r is not None:
                r.setting_id = key
                results[key] = r
        return results

    # ── individual checks ─────────────────────────────────────────────────────

    @staticmethod
    def detect_memory_profile(data: dict) -> Optional[DetectResult]:
        try:
            speed = int(data.get("ram_speed") or 0)
        except (TypeError, ValueError):
            return None
        if speed <= 0:
            return None
        try:
            mtype = int(data.get("ram_type") or 0)
        except (TypeError, ValueError):
            mtype = 0
        jedec, ddr = _JEDEC_MAX.get(mtype, (5600 if speed > 4000 else 3200,
                                            "DDR5" if speed > 4000 else "DDR4"))
        if speed > jedec:
            return DetectResult("expo_xmp", True, f"{ddr}-{speed}", "high",
                                f"RAM läuft mit {ddr}-{speed} — über dem Standardtakt, das Profil ist aktiv")
        if speed == jedec:
            return None          # top JEDEC speed or a kit whose profile has that speed: can't tell
        return DetectResult("expo_xmp", False, f"{ddr}-{speed}", "high",
                            f"RAM läuft nur mit {ddr}-{speed} (Standardtakt) — Profil im BIOS aktivieren")

    @staticmethod
    def detect_rebar(data: dict = None) -> Optional[DetectResult]:
        got = _bar1_mb()
        if not got:
            return None
        bar1, vram = got
        if bar1 > 512:
            return DetectResult("rebar", True, f"BAR1 {bar1:.0f} MB", "high",
                                f"Resizable BAR aktiv — die CPU sieht {bar1 / 1024:.0f} GB Grafikspeicher am Stück")
        return DetectResult("rebar", False, f"BAR1 {bar1:.0f} MB", "high",
                            f"Resizable BAR aus — nur {bar1:.0f} MB Fenster (Grafikspeicher {vram / 1024:.0f} GB)")

    @staticmethod
    def detect_secure_boot(data: dict) -> Optional[DetectResult]:
        val = data.get("secureboot")
        if val is None:
            if str(data.get("firmware") or "").lower() == "legacy":
                return DetectResult("secure_boot", False, "Legacy-Start", "high",
                                    "Windows startet im Legacy-Modus — Secure Boot braucht UEFI")
            return None
        on = str(val).strip() == "1"
        return DetectResult("secure_boot", on, "an" if on else "aus", "high",
                            "Secure Boot ist aktiv" if on else "Secure Boot ist aus")

    @staticmethod
    def detect_csm(data: dict) -> Optional[DetectResult]:
        fw = str(data.get("firmware") or "").lower()
        if fw == "legacy":
            return DetectResult("csm", False, "Legacy-Start", "high",
                                "Windows ist im Legacy-Modus installiert — CSM erst abschalten, wenn "
                                "Windows auf UEFI umgestellt ist (MBR2GPT)")
        if fw == "uefi" and str(data.get("secureboot") or "").strip() == "1":
            return DetectResult("csm", True, "UEFI + Secure Boot", "high",
                                "UEFI-Start mit Secure Boot — CSM ist damit sicher aus")
        return None              # UEFI without Secure Boot: CSM may be on or off
