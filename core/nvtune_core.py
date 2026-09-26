"""
NVTuner v2 Core
Combined NVML + MAHM telemetry, Afterburner profile controller,
setup validator (checks AB unlock settings + profile locks).
"""

import subprocess, os, time, json, struct
try:
    import winreg
except ImportError:
    winreg = None
from dataclasses import dataclass, asdict, field
from typing import Optional
from pathlib import Path
from datetime import datetime


# ── Combined GPU stats ────────────────────────────────────────────────────────

@dataclass
class GpuStats:
    # Identity
    name:           str   = "Unknown"
    driver_version: str   = "Unknown"
    # Thermal
    temp:           int   = 0       # °C
    fan_pct:        float = 0.0     # %
    fan_rpm:        float = 0.0
    # Clocks
    core_mhz:       float = 0.0
    shader_mhz:     float = 0.0
    mem_mhz:        float = 0.0
    # Voltage (only from MAHM)
    voltage_mv:     float = 0.0     # mV  ← the KEY value
    mem_voltage_mv: float = 0.0
    # Power
    power_w:        float = 0.0
    gpu_power_w:    float = 0.0     # alias kept in sync with power_w
    power_limit_w:  float = 0.0
    power_min_w:    float = 0.0
    power_max_w:    float = 0.0
    # Utilisation
    gpu_usage:      float = 0.0     # %
    mem_usage:      float = 0.0
    vram_used_mb:   int   = 0
    vram_total_mb:  int   = 0
    # Limits/throttle
    temp_limit_c:   float = 0.0
    throttle:       str   = "None"
    # Source flags
    nvml_ok:        bool  = False
    mahm_ok:        bool  = False


# ── Tune Profile ──────────────────────────────────────────────────────────────

@dataclass
class TuneProfile:
    name:               str   = "Default"
    # Offsets applied via Afterburner
    core_offset_mhz:    int   = 0
    mem_offset_mhz:     int   = 0
    # Power / voltage
    power_limit_pct:    int   = 100
    # Fan
    fan_mode:           str   = "auto"    # "auto" | "manual"
    fan_speed_pct:      int   = 0
    # V/F curve locking (Afterburner curve editor values)
    lock_voltage_mv:    int   = 0         # 0 = no lock
    lock_freq_mhz:      int   = 0
    # Stability metadata
    is_stable:          bool  = False
    stability_score:    int   = 0
    # Stage 1/2 results
    stage1_freq:        int   = 0         # Highest stable freq found
    stage1_voltage:     int   = 0         # At this voltage
    stage2_freq:        int   = 0         # Same freq, lower voltage
    stage2_voltage:     int   = 0
    # Misc
    notes:              str   = ""
    created_at:         str   = ""
    gpu_name:           str   = ""

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TuneProfile":
        p = TuneProfile()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p


# ── Profile manager ──────────────────────────────────────────────────────────

class ProfileManager:
    def __init__(self, profiles_dir: str):
        self.dir = Path(profiles_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        """Sanitize a profile name to a safe filename stem.
        Used by both save() and load() so they always agree on the on-disk
        name, and so a crafted name can't escape the profiles directory
        (e.g. '../../evil')."""
        return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)

    def save(self, profile: TuneProfile) -> str:
        safe = self._safe_name(profile.name)
        path = self.dir / f"{safe}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)
        return str(path)

    def load(self, name: str) -> Optional[TuneProfile]:
        path = self.dir / f"{self._safe_name(name)}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return TuneProfile.from_dict(json.load(f))

    def list_all(self) -> list[TuneProfile]:
        result = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    result.append(TuneProfile.from_dict(json.load(fp)))
            except:
                pass
        return result

    def delete(self, name: str) -> bool:
        path = self.dir / f"{self._safe_name(name)}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def get_tray_default(self) -> Optional[TuneProfile]:
        return self.load("__tray_default__")

    def set_tray_default(self, profile: TuneProfile):
        p = TuneProfile.from_dict(profile.to_dict())
        p.name = "__tray_default__"
        self.save(p)


# ── NVML wrapper ─────────────────────────────────────────────────────────────

class NvmlMonitor:
    def __init__(self):
        self._handle = None
        self._ok = False
        self._init()

    def _init(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nv = pynvml
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._ok = True
        except Exception as e:
            self._ok = False
            self._err = str(e)

    @property
    def available(self):
        return self._ok

    def enrich(self, stats: GpuStats):
        """Fill stats with NVML data."""
        if not self._ok:
            return
        nv, h = self._nv, self._handle
        try:
            n = nv.nvmlDeviceGetName(h)
            stats.name = n.decode() if isinstance(n, bytes) else n
        except: pass
        try:
            d = nv.nvmlSystemGetDriverVersion()
            stats.driver_version = d.decode() if isinstance(d, bytes) else d
        except: pass
        try:
            stats.temp = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
        except: pass
        try:
            # Real thermal slowdown point (e.g. 94 °C on an RTX 4080) — used as
            # the temperature gauge's scale. It used to come from Afterburner's
            # "Temp limit" source, which is only a 0/1 limiter flag.
            stats.temp_limit_c = float(nv.nvmlDeviceGetTemperatureThreshold(
                h, nv.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN))
        except: pass
        try:
            stats.core_mhz = float(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_GRAPHICS))
        except: pass
        try:
            stats.mem_mhz = float(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
        except: pass
        try:
            u = nv.nvmlDeviceGetUtilizationRates(h)
            stats.gpu_usage = float(u.gpu)
            stats.mem_usage = float(u.memory)
        except: pass
        try:
            m = nv.nvmlDeviceGetMemoryInfo(h)
            stats.vram_used_mb  = m.used  // (1024**2)
            stats.vram_total_mb = m.total // (1024**2)
        except: pass
        try:
            stats.power_w       = nv.nvmlDeviceGetPowerUsage(h)  / 1000.0
            stats.power_limit_w = nv.nvmlDeviceGetPowerManagementLimit(h) / 1000.0
        except: pass
        try:
            mn, mx = nv.nvmlDeviceGetPowerManagementLimitConstraints(h)
            stats.power_min_w = mn / 1000.0
            stats.power_max_w = mx / 1000.0
        except: pass
        try:
            reasons = nv.nvmlDeviceGetCurrentClocksThrottleReasons(h)
            TR = {
                0x0000000000000002: "Power",
                0x0000000000000004: "Thermal",
                0x0000000000000008: "Reliability",
                0x0000000000000010: "LimitSetting",
                0x0000000000000020: "HW-Thermal",
                0x0000000000000040: "HW-Power",
            }
            active = [v for k, v in TR.items() if reasons & k]
            stats.throttle = ", ".join(active) if active else "None"
        except: pass
        try:
            stats.fan_pct = float(nv.nvmlDeviceGetFanSpeed(h))
        except: pass
        stats.nvml_ok = True

    def set_power_limit(self, watts: float) -> bool:
        if not self._ok:
            return False
        try:
            self._nv.nvmlDeviceSetPowerManagementLimit(self._handle, int(watts * 1000))
            return True
        except:
            return False

    def get_default_power_limit(self) -> float:
        """Factory (stock) power limit in W — what "reset to stock" must restore.
        NOT the maximum constraint: on many partner cards the maximum is above
        stock (e.g. 450 W stock / 600 W max), so resetting to the maximum used to
        RAISE the limit. 0.0 if unavailable."""
        if not self._ok:
            return 0.0
        try:
            return round(self._nv.nvmlDeviceGetPowerManagementDefaultLimit(self._handle) / 1000.0, 1)
        except Exception:
            return 0.0

    def get_power_constraints(self) -> tuple[float, float, float]:
        if not self._ok:
            return (0, 0, 0)
        try:
            cur = self._nv.nvmlDeviceGetPowerManagementLimit(self._handle) / 1000.0
            mn, mx = self._nv.nvmlDeviceGetPowerManagementLimitConstraints(self._handle)
            return (round(cur, 1), round(mn / 1000.0, 1), round(mx / 1000.0, 1))
        except:
            return (0, 0, 0)

    def close(self):
        if self._ok:
            try: self._nv.nvmlShutdown()
            except: pass


# ── Afterburner Controller ────────────────────────────────────────────────────

class AfterburnerController:
    DEFAULT_PATHS = [
        r"C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe",
        r"C:\Program Files\MSI Afterburner\MSIAfterburner.exe",
    ]
    PROFILE_DIR_CANDIDATES = [
        os.path.expandvars(r"%APPDATA%\MSI Afterburner\Profiles"),
        os.path.expandvars(r"%LOCALAPPDATA%\MSI Afterburner\Profiles"),
    ]

    def __init__(self):
        self.exe: Optional[str] = None
        self.profile_dir: Optional[str] = None
        self._detect()

    def _detect(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\MSI\Afterburner", 0, winreg.KEY_READ)
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            exe = os.path.join(path, "MSIAfterburner.exe")
            if os.path.exists(exe):
                self.exe = exe
        except: pass

        if not self.exe:
            for p in self.DEFAULT_PATHS:
                if os.path.exists(p):
                    self.exe = p
                    break

        for c in self.PROFILE_DIR_CANDIDATES:
            if os.path.isdir(c):
                self.profile_dir = c
                break

        if self.exe and not self.profile_dir:
            nearby = os.path.join(os.path.dirname(self.exe), "Profiles")
            if os.path.isdir(nearby):
                self.profile_dir = nearby

    @property
    def available(self):
        return self.exe is not None

    def check_profile_locked(self, slot: int) -> bool:
        """Return True if profile slot is locked (we can't write to it)."""
        if not self.profile_dir:
            return False
        path = os.path.join(self.profile_dir, f"MSIAfterburner{slot}.cfg")
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("Locked=1"):
                        return True
        except:
            pass
        return False

    def check_ab_setup(self) -> dict:
        """
        Check Afterburner general.cfg for required unlock settings.
        Returns dict with keys: voltage_control, voltage_monitoring, any missing.
        """
        result = {"voltage_control": False, "voltage_monitoring": False, "cfg_found": False}
        if not self.exe:
            return result

        # AB general config is next to the exe
        ab_dir = os.path.dirname(self.exe)
        cfg_path = os.path.join(ab_dir, "MSIAfterburner.cfg")
        if not os.path.exists(cfg_path):
            # Try appdata
            cfg_path = os.path.expandvars(r"%APPDATA%\MSI Afterburner\MSIAfterburner.cfg")

        if not os.path.exists(cfg_path):
            return result

        result["cfg_found"] = True
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "EnableVoltageControlInterface=1" in content:
                result["voltage_control"] = True
            if "EnableVoltageMonitoring=1" in content:
                result["voltage_monitoring"] = True
        except:
            pass

        return result

    def load_profile_slot(self, slot: int) -> bool:
        if not self.available or not (1 <= slot <= 5):
            return False
        try:
            subprocess.Popen(
                [self.exe, f"/Profile{slot}"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(1.5)
            return True
        except:
            return False

    def write_and_apply(self, slot: int, profile: TuneProfile) -> tuple[bool, str]:
        """Write profile .cfg and load it. Returns (success, error_msg)."""
        if not self.available:
            return False, "Afterburner not found"
        if self.check_profile_locked(slot):
            return False, f"Profile slot {slot} is locked (🔒) — unlock it in Afterburner first"
        if not self.profile_dir:
            return False, "Profile directory not found"

        path = os.path.join(self.profile_dir, f"MSIAfterburner{slot}.cfg")

        # Read the existing profile. We keep the RAW lines (not just a key->value
        # dict) because an Afterburner .cfg is an INI file: it has [Section]
        # headers, comments and blank lines. The old version parsed only
        # "key=value" lines and rewrote a flat list, which silently DELETED every
        # section header — corrupting the very file it meant to preserve. Now the
        # original structure is kept verbatim and only our own keys are replaced
        # in place (unknown keys/sections are never touched).
        orig_lines: list[str] = []
        existing = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    orig_lines = f.read().splitlines()
                for l in orig_lines:
                    ls = l.strip()
                    if "=" in ls and not ls.startswith(";") and not ls.startswith("["):
                        k, _, v = ls.partition("=")
                        existing[k.strip()] = v.strip()
            except: pass

        # Keys THIS call sets (merged into the original structure further down).
        updates: dict[str, str] = {}

        # Sanity guard-rails against absurd offsets — protects against a
        # hand-edited/corrupt profile JSON (e.g. core=9999) that Afterburner
        # would apply verbatim and crash the GPU. Bounds are far beyond any
        # real overclock, so legitimate (even aggressive) profiles are never
        # touched; only garbage is clamped.
        def _clamp(v, lo, hi):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return 0
        core_off = _clamp(profile.core_offset_mhz, -1500, 1500)
        mem_off  = _clamp(profile.mem_offset_mhz,  -6000, 6000)

        # Apply our values
        updates["CoreClockOffset"]   = str(core_off)
        updates["MemoryClockOffset"] = str(mem_off)

        if profile.fan_mode == "manual" and profile.fan_speed_pct > 0:
            updates["FanSpeed"] = str(profile.fan_speed_pct)
            updates["FanMode"]  = "1"
        else:
            updates["FanMode"] = "0"

        # V/F curve (if set) — writes precise flatline undervolt curve
        if profile.lock_voltage_mv > 0 and profile.lock_freq_mhz > 0:
            try:
                from core.vf_curve import get_builder_for_gpu
                # Try to get GPU name from existing profile or use Ada as default
                gpu_hint = existing.get("GPUName", "RTX 40")
                builder  = get_builder_for_gpu(gpu_hint)
                curve    = builder.build_flatline_curve(
                    target_freq_mhz=profile.lock_freq_mhz,
                    lock_voltage_mv=profile.lock_voltage_mv,
                    base_core_offset=core_off,
                )
                if curve.curve_offsets:
                    updates["VFCurveEnabled"]      = "1"
                    updates["CoreClockOffset"]     = str(core_off)
                    updates["VoltagePoints"]       = curve.to_afterburner_string()
                    updates["VFLockVoltage"]       = str(profile.lock_voltage_mv)
                    updates["VFLockFrequency"]     = str(profile.lock_freq_mhz)
            except Exception as vf_err:
                # Non-fatal: fall back to simple offset without curve
                updates["CoreClockOffset"] = str(core_off)

        def _sanitize(v) -> str:
            # Strip CR/LF so a crafted name/notes (e.g. from an imported
            # .nextune) can't inject extra key=value lines into the .cfg
            return str(v).replace("\r", " ").replace("\n", " ")

        try:
            os.makedirs(self.profile_dir, exist_ok=True)
            safe_pname = _sanitize(profile.name)
            safe_notes = _sanitize(profile.notes)

            out_lines: list[str] = []
            written: set[str] = set()

            if orig_lines:
                # Merge into the existing file: replace our keys where they already
                # stand, and copy EVERYTHING else (sections, comments, blank lines,
                # unknown keys) through untouched.
                for l in orig_lines:
                    ls = l.strip()
                    if "=" in ls and not ls.startswith(";") and not ls.startswith("["):
                        key = ls.partition("=")[0].strip()
                        if key in updates and key not in written:
                            out_lines.append(f"{key}={_sanitize(updates[key])}")
                            written.add(key)
                            continue
                    out_lines.append(l)
            else:
                # Brand-new profile file — write our own header.
                out_lines.append(f"; GameOptimizerPro v2.0 profile: {safe_pname}")
                out_lines.append(f"; {safe_notes}")

            # Any of our keys that weren't already in the file get appended.
            for k, v in updates.items():
                if k not in written:
                    out_lines.append(f"{k}={_sanitize(v)}")

            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines) + "\n")
        except Exception as e:
            return False, f"Write failed: {e}"

        success = self.load_profile_slot(slot)
        if not success:
            return False, "Profile written but Afterburner load failed"
        return True, ""

    def reset_to_stock(self, slot: int = 1) -> bool:
        return self.load_profile_slot(slot)


# ── Combined monitor (NVML + MAHM) ───────────────────────────────────────────

class GpuMonitor:
    def __init__(self):
        from core.mahm_reader import MAHMReader
        self.nvml  = NvmlMonitor()
        self.mahm  = MAHMReader()

    def read(self) -> GpuStats:
        stats = GpuStats()
        self.nvml.enrich(stats)

        mahm_data = self.mahm.read()
        if mahm_data.available:
            stats.mahm_ok = True
            # Take a MAHM value only when Afterburner actually exports it (> 0).
            # Afterburner only publishes the sources whose graphs are enabled; the
            # old unconditional copy replaced good NVML readings with 0 (fan 45 %
            # -> 0 %, power limit 320 W -> 0 W). Afterburner's "Power/Temp limit"
            # sources are limiter FLAGS (0/1) and are no longer written into the
            # watt / °C fields at all — the temp gauge used the flag as its scale
            # maximum (1 °C) whenever the thermal limiter was active.
            if mahm_data.gpu_voltage_mv > 0:
                stats.voltage_mv     = mahm_data.gpu_voltage_mv
            if mahm_data.mem_voltage_mv > 0:
                stats.mem_voltage_mv = mahm_data.mem_voltage_mv
            if mahm_data.fan_speed_pct > 0:
                stats.fan_pct        = mahm_data.fan_speed_pct
            if mahm_data.fan_rpm > 0:
                stats.fan_rpm        = mahm_data.fan_rpm
            if mahm_data.gpu_power_w > 0:
                stats.gpu_power_w    = mahm_data.gpu_power_w  # prefer MAHM power
            if mahm_data.gpu_temp > 0 and not stats.nvml_ok:
                stats.temp           = int(round(mahm_data.gpu_temp))
            # Prefer MAHM clocks (more accurate, direct driver read)
            if mahm_data.core_clock > 0:
                stats.core_mhz   = mahm_data.core_clock
            if mahm_data.shader_clock > 0:
                stats.shader_mhz = mahm_data.shader_clock
            if mahm_data.mem_clock > 0:
                stats.mem_mhz    = mahm_data.mem_clock
            if mahm_data.gpu_usage > 0:
                stats.gpu_usage  = mahm_data.gpu_usage
            if mahm_data.vram_usage > 0:
                stats.mem_usage  = mahm_data.vram_usage

        # Use NVML power if MAHM didn't provide it
        if stats.gpu_power_w == 0 and stats.power_w > 0:
            stats.gpu_power_w = stats.power_w

        return stats

    def set_power_limit(self, watts: float) -> bool:
        return self.nvml.set_power_limit(watts)

    def get_power_constraints(self):
        return self.nvml.get_power_constraints()

    def get_default_power_limit(self) -> float:
        return self.nvml.get_default_power_limit()

    def power_pct_to_watts(self, pct: float) -> float:
        """Power limit % -> W, where 100 % = the STOCK limit (Afterburner's
        meaning of "power limit %"), clamped to the card's allowed range.
        Previously 100 % meant the card's MAXIMUM limit. 0.0 if unknown."""
        _cur, mn, mx = self.get_power_constraints()
        base = self.get_default_power_limit() or mx
        if base <= 0:
            return 0.0
        w = base * float(pct) / 100.0
        if mn > 0:
            w = max(mn, w)
        if mx > 0:
            w = min(mx, w)
        return round(w, 1)

    def close(self):
        self.nvml.close()
        self.mahm.close()
