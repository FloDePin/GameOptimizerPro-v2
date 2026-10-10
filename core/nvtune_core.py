"""
NVTuner v2 Core
Combined NVML + MAHM telemetry, Afterburner profile controller,
setup validator (checks AB unlock settings + profile locks).
"""

import subprocess, os, time, json, threading
try:
    import winreg
except ImportError:
    winreg = None
from dataclasses import dataclass, asdict, field
from typing import Callable, Optional
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
    throttle:       str   = "None"   # human-readable active reasons
    throttle_bits:  int   = 0        # raw NVML clock-event reasons
    throttle_protective: bool = False  # thermal / hardware slowdown active
    power_capped:   bool  = False    # running into the power limit (normal under load)
    # Source flags
    nvml_ok:        bool  = False
    mahm_ok:        bool  = False
    mahm_restarting: bool = False    # Afterburner is being restarted on purpose (tune step)


# NVML clock-event ("throttle") reasons — values from nvml.h. Running into the
# power limit (SW power cap) is NORMAL under full load and not a fault; only the
# thermal / hardware slowdowns mean the card is protecting itself.
THR_POWER_CAP      = 0x0004   # nvmlClocksEventReasonSwPowerCap
THR_HW_SLOWDOWN    = 0x0008   # nvmlClocksEventReasonHwSlowdown
THR_SW_THERMAL     = 0x0020   # nvmlClocksEventReasonSwThermalSlowdown
THR_HW_THERMAL     = 0x0040   # nvmlClocksEventReasonHwThermalSlowdown
THR_HW_POWER_BRAKE = 0x0080   # nvmlClocksEventReasonHwPowerBrakeSlowdown
THR_PROTECTIVE     = THR_HW_SLOWDOWN | THR_SW_THERMAL | THR_HW_THERMAL | THR_HW_POWER_BRAKE
_THR_LABELS = {
    0x0002: "App-Clocks", THR_POWER_CAP: "Power-Limit", THR_HW_SLOWDOWN: "HW-Slowdown",
    0x0010: "SyncBoost", THR_SW_THERMAL: "Thermal", THR_HW_THERMAL: "HW-Thermal",
    THR_HW_POWER_BRAKE: "HW-PowerBrake",
}


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
    # Own curve (Rundum-Tuner): measured points [[voltage_mv, mhz], ...] and the
    # voltage from which it is flat (0 = from the highest point)
    curve_points:       list  = field(default_factory=list)
    curve_cap_mv:       int   = 0
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
    # The same benchmark at stock and with this profile (core/profile_score.py):
    # {name, seconds, score, power_w, stock_score, stock_seconds, stock_power_w, at}
    bench:              dict  = field(default_factory=dict)

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

def _t(de: str, en: str) -> str:
    try:
        from core.i18n import current_lang
        return de if current_lang() == "de" else en
    except Exception:
        return de


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

    @staticmethod
    def _is_profile(d) -> bool:
        """Only real GPU profiles. The folder also holds other JSON files
        (language.json, the old game_profiles.json) — read as profiles they
        showed up as a profile called "Default" in every list."""
        return (isinstance(d, dict) and isinstance(d.get("name"), str) and d["name"].strip() != ""
                and ("core_offset_mhz" in d or "power_limit_pct" in d))

    # Renamed profiles: old name -> new name (the tune history knows a run's
    # profile by the name it was saved under). Not *.json: never read as a profile.
    ALIASES = "renamed.map"

    def _aliases(self) -> dict:
        try:
            d = json.loads((self.dir / self.ALIASES).read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_aliases(self, d: dict):
        try:
            (self.dir / self.ALIASES).write_text(json.dumps(d, indent=1, ensure_ascii=False),
                                                 encoding="utf-8")
        except OSError:
            pass

    def _read(self, name: str) -> Optional[TuneProfile]:
        path = self.dir / f"{self._safe_name(name)}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        return TuneProfile.from_dict(d) if self._is_profile(d) else None

    def load(self, name: str) -> Optional[TuneProfile]:
        """The profile `name` — or, if it was renamed, under its new name."""
        p = self._read(name)
        if p is None:
            aliases, seen = self._aliases(), {name}
            while p is None and name in aliases and aliases[name] not in seen:
                name = aliases[name]
                seen.add(name)
                p = self._read(name)
        return p

    def list_all(self) -> list[TuneProfile]:
        result = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    d = json.load(fp)
            except Exception:
                continue
            if self._is_profile(d):
                result.append(TuneProfile.from_dict(d))
        return result

    def rename(self, old: str, new: str) -> tuple[bool, str]:
        """-> (ok, message). The file is saved under the new name; the old name
        keeps pointing to it (tune history)."""
        new = (new or "").strip()
        p = self._read(old)
        if p is None:
            return False, _t("Profil nicht gefunden", "Profile not found")
        if not new or new.startswith("__"):
            return False, _t("Ungültiger Name", "Invalid name")
        if new == old:
            return True, ""
        # case-only rename ("Alt" -> "ALT"): the same file on Windows
        same_file = self._safe_name(new).lower() == self._safe_name(old).lower()
        if not same_file and (self.dir / f"{self._safe_name(new)}.json").exists():
            return False, _t(f"„{new}“ gibt es schon", f"'{new}' already exists")
        p.name = new
        try:
            self.save(p)
            if not same_file:
                (self.dir / f"{self._safe_name(old)}.json").unlink()
        except OSError as e:
            return False, str(e)
        aliases = {k: (new if v == old else v) for k, v in self._aliases().items() if k != new}
        if not same_file:
            aliases[old] = new
        self._write_aliases(aliases)
        return True, ""

    DERATE_CORE_MHZ = 30
    DERATE_MEM_MHZ = 200

    def derate(self, name: str, core_mhz: int = DERATE_CORE_MHZ,
               mem_mhz: int = DERATE_MEM_MHZ) -> Optional[TuneProfile]:
        """A safer copy (round 16 — a tuned profile can hang a game after hours):
        every curve point (or the core offset) −core_mhz, memory −mem_mhz, never
        below 0. Saved as '<name>_sicher' ('…_sicher2', … when that exists; a copy
        of a copy counts on from its base). -> the copy, None if `name` is unknown."""
        import re
        src = self.load(name)
        if src is None:
            return None
        base = re.sub(r"_sicher\d*$", "", src.name)
        new_name, i = f"{base}_sicher", 2
        while self._read(new_name) is not None:
            new_name, i = f"{base}_sicher{i}", i + 1
        p = TuneProfile.from_dict(src.to_dict())
        p.name = new_name
        if p.curve_points:
            p.curve_points = [[int(mv), int(f) - int(core_mhz)] for mv, f in p.curve_points]
        p.core_offset_mhz = int(p.core_offset_mhz) - int(core_mhz)
        if p.lock_freq_mhz:
            p.lock_freq_mhz = max(0, int(p.lock_freq_mhz) - int(core_mhz))
        p.mem_offset_mhz = max(0, int(p.mem_offset_mhz) - int(mem_mhz))
        p.created_at = datetime.now().isoformat()
        p.notes = (_t(f"[Entschärft aus {src.name}: Kurve/Takt −{core_mhz} MHz, Speicher "
                      f"+{src.mem_offset_mhz}→+{p.mem_offset_mhz}] ",
                      f"[Made safer from {src.name}: curve/clock −{core_mhz} MHz, memory "
                      f"+{src.mem_offset_mhz}→+{p.mem_offset_mhz}] ") + (src.notes or ""))[:400]
        self.save(p)
        return p

    @staticmethod
    def _safer_level(name: str, base: str) -> int:
        """0 = the original, 1 = '<base>_sicher', n = '<base>_sicher<n>'."""
        rest = name[len(base):]
        if not rest:
            return 0
        return int(rest[len("_sicher"):] or 1)

    def safer_version(self, name: str) -> Optional[str]:
        """The safest made-safer copy of `name` that is safer than `name` itself
        ('X' -> 'X_sicher2' if it exists), else None. Round 16: the tune history
        offered the original profile that had hung a game — and it was applied."""
        import re
        base = re.sub(r"_sicher\d*$", "", name)
        pat = re.compile(re.escape(base) + r"(_sicher\d*)?$")
        mine = self._safer_level(name, base) if pat.match(name) else 0
        best, level = None, mine
        for p in self.list_all():
            if pat.match(p.name) and p.name != base:
                lv = self._safer_level(p.name, base)
                if lv > level:
                    best, level = p.name, lv
        return best

    def delete(self, name: str) -> bool:
        path = self.dir / f"{self._safe_name(name)}.json"
        if path.exists():
            path.unlink()
            aliases = self._aliases()
            if name in aliases.values():
                self._write_aliases({k: v for k, v in aliases.items() if v != name})
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
        except Exception: pass
        try:
            d = nv.nvmlSystemGetDriverVersion()
            stats.driver_version = d.decode() if isinstance(d, bytes) else d
        except Exception: pass
        try:
            stats.temp = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
        except Exception: pass
        try:
            # Real thermal slowdown point (e.g. 94 °C on an RTX 4080) — used as
            # the temperature gauge's scale. It used to come from Afterburner's
            # "Temp limit" source, which is only a 0/1 limiter flag.
            stats.temp_limit_c = float(nv.nvmlDeviceGetTemperatureThreshold(
                h, nv.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN))
        except Exception: pass
        try:
            stats.core_mhz = float(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_GRAPHICS))
        except Exception: pass
        try:
            stats.mem_mhz = float(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
        except Exception: pass
        try:
            u = nv.nvmlDeviceGetUtilizationRates(h)
            stats.gpu_usage = float(u.gpu)
            stats.mem_usage = float(u.memory)
        except Exception: pass
        try:
            m = nv.nvmlDeviceGetMemoryInfo(h)
            stats.vram_used_mb  = m.used  // (1024**2)
            stats.vram_total_mb = m.total // (1024**2)
        except Exception: pass
        try:
            stats.power_w       = nv.nvmlDeviceGetPowerUsage(h)  / 1000.0
            stats.power_limit_w = nv.nvmlDeviceGetPowerManagementLimit(h) / 1000.0
        except Exception: pass
        try:
            mn, mx = nv.nvmlDeviceGetPowerManagementLimitConstraints(h)
            stats.power_min_w = mn / 1000.0
            stats.power_max_w = mx / 1000.0
        except Exception: pass
        try:
            # The old table was shifted by one bit: 0x04 (the normal power limit)
            # was labelled "Thermal", 0x02 (application clocks) "Power", … — and
            # the tuner treated ANY of them as a failed step.
            reasons = int(nv.nvmlDeviceGetCurrentClocksThrottleReasons(h))
            stats.throttle_bits = reasons
            stats.power_capped = bool(reasons & THR_POWER_CAP)
            stats.throttle_protective = bool(reasons & THR_PROTECTIVE)
            active = [v for k, v in _THR_LABELS.items() if reasons & k]
            stats.throttle = ", ".join(active) if active else "None"
        except Exception: pass
        try:
            stats.fan_pct = float(nv.nvmlDeviceGetFanSpeed(h))
        except Exception: pass
        stats.nvml_ok = True

    def set_power_limit(self, watts: float) -> bool:
        if not self._ok:
            return False
        try:
            self._nv.nvmlDeviceSetPowerManagementLimit(self._handle, int(watts * 1000))
            return True
        except Exception:
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

    def get_pci_identity(self) -> Optional[tuple[int, int, int]]:
        """(PCI device id, subsystem id, bus) of the tuned card — the same
        identity Afterburner uses to name its per-GPU profile file."""
        if not self._ok:
            return None
        try:
            pci = self._nv.nvmlDeviceGetPciInfo(self._handle)
            return ((int(pci.pciDeviceId) >> 16) & 0xFFFF,
                    int(pci.pciSubSystemId) & 0xFFFFFFFF,
                    int(pci.bus))
        except Exception:
            return None

    def get_power_constraints(self) -> tuple[float, float, float]:
        if not self._ok:
            return (0, 0, 0)
        try:
            cur = self._nv.nvmlDeviceGetPowerManagementLimit(self._handle) / 1000.0
            mn, mx = self._nv.nvmlDeviceGetPowerManagementLimitConstraints(self._handle)
            return (round(cur, 1), round(mn / 1000.0, 1), round(mx / 1000.0, 1))
        except Exception:
            return (0, 0, 0)

    def close(self):
        if self._ok:
            try: self._nv.nvmlShutdown()
            except Exception: pass


# ── Afterburner Controller ────────────────────────────────────────────────────

def _no_window() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class AfterburnerController:
    """Writes tuning values into MSI Afterburner's REAL per-GPU profile file and
    makes Afterburner apply them.

    Afterburner reads Profiles\\VEN_….cfg only when it starts and keeps the five
    slots in memory; "MSIAfterburner.exe -ProfileN" applies the in-memory copy.
    So applying NEW values means: close Afterburner, write the slot, start it
    again with -ProfileN. When the slot already holds exactly these values,
    -ProfileN is simply sent to the running instance (no restart).

    (Up to v2.0 round 7 this class wrote a made-up MSIAfterburner<slot>.cfg with
    invented keys that Afterburner never reads — applying profiles had no effect.
    See core/ab_profile.py for the verified file format.)"""

    EXE_NAME = "MSIAfterburner.exe"
    DEFAULT_PATHS = [
        r"C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe",
        r"C:\Program Files\MSI Afterburner\MSIAfterburner.exe",
    ]
    CLOSE_TIMEOUT_S = 2.0     # graceful close before it is terminated (a tray-minimised
                              # Afterburner ignored WM_CLOSE in the live test)
    READY_TIMEOUT_S = 20.0    # start-up until the monitoring section exists
    MIN_READY_S     = 3.0     # never return earlier than this after the launch
    MIN_AGE_S       = 8.0     # never close an Afterburner that is still starting up
    MAX_BACKUPS     = 30

    # Bounds for values from (possibly hand-edited) profile JSONs. Core stops at
    # ±999: +1000 MHz would be CoreClkBoost=1000000, Afterburner's custom-curve marker.
    CORE_RANGE  = (-999, 999)
    MEM_RANGE   = (-3000, 6000)
    POWER_RANGE = (30, 150)

    def __init__(self, gpu_pci: Optional[tuple[int, int, int]] = None):
        self.exe: Optional[str] = None
        self.profile_dir: Optional[str] = None      # <Afterburner>\Profiles
        self._pci = gpu_pci                         # (device id, subsystem id, bus)
        self._io_lock = threading.RLock()           # one close/write/start at a time
        self._backed_up: set[str] = set()
        self.last_backup: str = ""
        self.last_notes: list[str] = []
        # The app hooks its MAHM reader in here: drop the shared memory BEFORE
        # Afterburner is closed (a held handle keeps the old section alive and the
        # restarted Afterburner doesn't publish into it), reconnect once it's up.
        self.on_ab_closing: Optional[Callable[[], None]] = None
        self.on_ab_started: Optional[Callable[[], None]] = None
        self._detect()

    # ── discovery ─────────────────────────────────────────────────────────────

    def _detect(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\MSI\Afterburner", 0, winreg.KEY_READ)
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            exe = os.path.join(path, self.EXE_NAME)
            if os.path.exists(exe):
                self.exe = exe
        except Exception:
            pass
        if not self.exe:
            for p in self.DEFAULT_PATHS:
                if os.path.exists(p):
                    self.exe = p
                    break
        # Afterburner keeps its settings and GPU profiles in <install>\Profiles.
        # (The %APPDATA% paths used before don't exist for Afterburner.)
        if self.exe:
            d = os.path.join(os.path.dirname(self.exe), "Profiles")
            if os.path.isdir(d):
                self.profile_dir = d

    @property
    def available(self):
        return self.exe is not None

    def set_gpu_identity(self, pci: Optional[tuple[int, int, int]]):
        self._pci = pci

    def settings_path(self) -> Optional[str]:
        """Afterburner's global settings. The MSIAfterburner.cfg next to the exe
        is only the installer's template — the live one is in Profiles."""
        if not self.profile_dir:
            return None
        p = os.path.join(self.profile_dir, "MSIAfterburner.cfg")
        return p if os.path.exists(p) else None

    def find_gpu_profile(self) -> tuple[Optional[str], str]:
        """-> (path of the tuned card's VEN_….cfg or None, explanation)."""
        from core.ab_profile import pick_gpu_file
        if not self.available:
            return None, "MSI Afterburner nicht gefunden"
        if not self.profile_dir:
            self._detect()
            if not self.profile_dir:
                return None, "Afterburner-Profilordner fehlt — Afterburner einmal starten."
        try:
            names = os.listdir(self.profile_dir)
        except OSError as e:
            return None, f"Profilordner nicht lesbar: {e}"
        dev = sub = bus = None
        if self._pci:
            dev, sub, bus = self._pci
        name, why = pick_gpu_file(names, dev, sub, bus)
        if not name:
            return None, why
        return os.path.join(self.profile_dir, name), why

    def check_ab_setup(self) -> dict:
        """Read Profiles\\MSIAfterburner.cfg [Settings]."""
        from core.ab_profile import ProfileFile, decode_cfg
        result = {"cfg_found": False, "voltage_control": False,
                  "voltage_monitoring": False, "profiles_locked": False,
                  "start_minimized": False, "voltage_graph": None,
                  "start_with_windows": False}
        path = self.settings_path()
        if not path:
            return result
        try:
            with open(path, "rb") as f:
                text, _enc = decode_cfg(f.read())
        except OSError:
            return result
        st = ProfileFile(text).items("Settings")
        result["cfg_found"] = True

        def on(key):
            try:
                return int(st.get(key.lower(), "0") or "0") != 0
            except ValueError:
                return False
        result["voltage_control"]    = on("UnlockVoltageControl")
        result["voltage_monitoring"] = on("UnlockVoltageMonitoring")
        result["profiles_locked"]    = on("LockProfiles")
        result["start_minimized"]    = on("StartMinimized")
        result["start_with_windows"] = on("StartWithWindows")
        # Older versions list the graphs as "Sources=+GPU temperature,-Core clock,…"
        # (+ = enabled). Afterburner 4.6.6 doesn't write that list until the
        # monitoring page is changed -> None = unknown; the live monitoring data
        # (is a "GPU voltage" source exported?) is the reliable check.
        if "sources" in st:
            sources = [s.strip().lower() for s in st.get("sources", "").split(",")]
            result["voltage_graph"] = any(s.startswith("+") and "voltage" in s
                                          for s in sources)
        return result

    def startup_apply_enabled(self) -> Optional[bool]:
        """Afterburner's "Apply overclocking at system startup": it keeps the
        settings to apply in the [Startup] section of the card's profile file
        (empty values = off). None = no profile file found."""
        from core.ab_profile import ProfileFile, decode_cfg
        path, _why = self.find_gpu_profile()
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                text, _enc = decode_cfg(f.read())
        except OSError:
            return None
        st = ProfileFile(text).items("Startup")
        return any((st.get(k) or "").strip() for k in ("coreclkboost", "vfcurve", "memclkboost", "powerlimit"))

    # ── process control ───────────────────────────────────────────────────────

    def _procs(self):
        try:
            import psutil
        except ImportError:
            return None
        out = []
        for p in psutil.process_iter(["name", "create_time"]):
            try:
                if (p.info.get("name") or "").lower() == self.EXE_NAME.lower():
                    out.append(p)
            except Exception:
                continue
        return out

    def is_running(self) -> bool:
        procs = self._procs()
        if procs is not None:
            return bool(procs)
        try:
            r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {self.EXE_NAME}", "/NH"],
                               capture_output=True, text=True, timeout=10,
                               creationflags=_no_window())
            return self.EXE_NAME.lower() in (r.stdout or "").lower()
        except Exception:
            return False

    def _wait_gone(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.is_running():
                return True
            time.sleep(0.25)
        return not self.is_running()

    @staticmethod
    def _call(cb):
        if cb:
            try:
                cb()
            except Exception:
                pass

    def _wait_section_gone(self, timeout: float = 10.0) -> bool:
        """After the kill: wait until nobody holds the old monitoring section any
        more (other readers drop a frozen one within MAHMReader.STALE_S), so the
        new Afterburner creates a fresh one."""
        from core.mahm_reader import section_exists
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not section_exists():
                return True
            time.sleep(0.25)
        return False

    def close(self) -> tuple[bool, str]:
        """Close Afterburner: WM_CLOSE first (it then marks its shared memory
        0xDEAD and exits cleanly), terminate only if it doesn't react."""
        procs = self._procs() or []
        ages = [time.time() - (p.info.get("create_time") or 0) for p in procs]
        young = [a for a in ages if 0 <= a < self.MIN_AGE_S]
        if young:                       # e.g. just launched by its own autostart
            time.sleep(self.MIN_AGE_S - min(young))
        if not self.is_running():
            return True, ""
        self._call(self.on_ab_closing)
        try:
            subprocess.run(["taskkill", "/IM", self.EXE_NAME], capture_output=True,
                           timeout=15, creationflags=_no_window())
        except Exception:
            pass
        if not self._wait_gone(self.CLOSE_TIMEOUT_S):
            try:
                subprocess.run(["taskkill", "/F", "/IM", self.EXE_NAME], capture_output=True,
                               timeout=15, creationflags=_no_window())
            except Exception:
                pass
            if not self._wait_gone(5.0):
                return False, ("Afterburner ließ sich nicht beenden (läuft er mit Admin-"
                               "Rechten und GameOptimizerPro ohne?)")
        time.sleep(0.5)                 # let it release its files
        self._wait_section_gone()
        return True, ""

    def _wait_ready(self) -> tuple[bool, str]:
        """Wait until the new Afterburner has applied the profile. Measured on a
        live 4.6.6: the power limit changed ~1.1 s after the process appeared.
        The monitoring section alone is no proof — other readers (e.g. this app)
        keep the OLD section alive across the restart — so a fixed minimum time
        since the launch is enforced as well."""
        from core.mahm_reader import section_ready
        start = time.monotonic()
        end = start + self.READY_TIMEOUT_S
        while time.monotonic() < end:
            if self.is_running() and section_ready():
                rest = self.MIN_READY_S - (time.monotonic() - start)
                time.sleep(max(1.0, rest))   # it applies the profile during start-up
                self._call(self.on_ab_started)
                return True, ""
            time.sleep(0.3)
        if self.is_running():
            self._call(self.on_ab_started)
            return True, ("Afterburner läuft, aber sein Monitoring (MAHM) meldet sich "
                          "nicht — Profil vermutlich trotzdem angewendet.")
        return False, "Afterburner wurde gestartet, läuft aber nicht."

    def _launch(self, args: list[str]):
        si = None
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7          # SW_SHOWMINNOACTIVE: don't steal the focus
        return subprocess.Popen([self.exe] + args, cwd=os.path.dirname(self.exe),
                                close_fds=True, startupinfo=si)

    def start(self, slot: Optional[int] = None) -> tuple[bool, str]:
        """Start Afterburner (optionally applying profile slot `slot`)."""
        if not self.available:
            return False, "MSI Afterburner nicht gefunden"
        try:
            self._launch([f"-Profile{slot}"] if slot else [])
        except OSError as e:
            if getattr(e, "winerror", None) == 740:
                return False, ("Afterburner braucht Administratorrechte — "
                               "GameOptimizerPro als Administrator starten.")
            return False, f"Afterburner-Start fehlgeschlagen: {e}"
        return self._wait_ready()

    def load_profile_slot(self, slot: int) -> tuple[bool, str]:
        """Apply slot `slot` as Afterburner currently has it in memory."""
        if not self.available or not (1 <= slot <= 5):
            return False, "Afterburner nicht verfügbar / Slot ungültig"
        if not self.is_running():
            return self.start(slot)
        try:
            p = self._launch([f"-Profile{slot}"])   # hands over to the running instance
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        except OSError as e:
            if getattr(e, "winerror", None) == 740:
                return False, ("Afterburner braucht Administratorrechte — "
                               "GameOptimizerPro als Administrator starten.")
            return False, f"Afterburner-Aufruf fehlgeschlagen: {e}"
        time.sleep(1.0)
        return True, ""

    # ── writing ───────────────────────────────────────────────────────────────

    @staticmethod
    def backup_dir() -> str:
        la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(la, "GameOptimizerPro", "AfterburnerBackups")

    def _backup(self, path: str):
        """Copy the profile file before the FIRST change in this session."""
        if path in self._backed_up:
            return
        import shutil
        d = self.backup_dir()
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, f"{datetime.now():%Y%m%d_%H%M%S}_{os.path.basename(path)}")
        shutil.copy2(path, dst)
        self._backed_up.add(path)
        self.last_backup = dst
        try:
            olds = sorted(Path(d).glob("*.cfg"), key=lambda p: p.stat().st_mtime)
            for p in olds[:-self.MAX_BACKUPS]:
                p.unlink()
        except OSError:
            pass

    @staticmethod
    def _read(path: str) -> tuple[str, str]:
        from core.ab_profile import decode_cfg
        with open(path, "rb") as f:
            return decode_cfg(f.read())

    @staticmethod
    def _write_bytes(path: str, data: bytes):
        """Atomic replace; never leaves the temp file behind."""
        tmp = path + ".gop.tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @classmethod
    def _write(cls, path: str, text: str, enc: str):
        from core.ab_profile import encode_cfg
        cls._write_bytes(path, encode_cfg(text, enc))

    def _settings_for(self, profile: TuneProfile):
        from core.ab_profile import SlotSettings

        def _clamp(v, lo, hi, default=0):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return default
        return SlotSettings(
            core_mhz=_clamp(profile.core_offset_mhz, *self.CORE_RANGE),
            mem_mhz=_clamp(profile.mem_offset_mhz, *self.MEM_RANGE),
            power_pct=_clamp(profile.power_limit_pct, *self.POWER_RANGE, default=100),
            lock_mv=_clamp(profile.lock_voltage_mv, 0, 1300),
            lock_mhz=_clamp(profile.lock_freq_mhz, 0, 4000),
            curve=tuple((_clamp(mv, 300, 1300), _clamp(mhz, 100, 4000))
                        for mv, mhz in (profile.curve_points or [])
                        if isinstance(mv, (int, float)) and isinstance(mhz, (int, float))),
            cap_mv=_clamp(getattr(profile, "curve_cap_mv", 0), 0, 1300),
        )

    def write_and_apply(self, slot: int, profile: TuneProfile,
                        startup="same") -> tuple[bool, str]:
        """Write `profile` into Afterburner slot `slot` and apply it.
        `startup` = what Afterburner applies at BOOT ([Startup]; only while its
        "Apply overclocking at system startup" is on): "same" = this profile —
        what the user applies is what the PC boots with; a TuneProfile = that one
        (a tune keeps the known-good profile there while it tests steps); None =
        leave it. Returns (success, error message). Blocks for a few seconds when
        Afterburner has to be restarted — call it off the UI thread."""
        from core.ab_profile import (apply_slot, apply_startup, copy_slot_to_startup,
                                     section_equivalent, slot_equivalent, ProfileError, STARTUP)
        if not self.available:
            return False, "MSI Afterburner nicht gefunden"
        if not 1 <= int(slot) <= 5:
            return False, f"Profil-Slot {slot} ungültig (1–5)"
        spec = self._settings_for(profile)
        boot = (None if startup is None or isinstance(startup, str)
                else self._settings_for(startup))

        def build(text):
            new_text, notes_ = apply_slot(text, slot, spec)
            try:                        # the boot entry never blocks the slot itself
                if isinstance(startup, str):
                    new_text = copy_slot_to_startup(new_text, slot)
                elif boot is not None:
                    new_text = apply_startup(new_text, boot)
            except ProfileError as e:
                notes_ = notes_ + [f"Boot-Eintrag ([Startup]) nicht gesetzt: {e}"]
            return new_text, notes_

        with self._io_lock:
            path, why = self.find_gpu_profile()
            if not path:
                return False, why
            try:
                old, enc = self._read(path)
                new, notes = build(old)
            except ProfileError as e:
                return False, f"Afterburner-Profil: {e}"
            except OSError as e:
                return False, f"Afterburner-Profil nicht lesbar: {e}"
            self.last_notes = notes
            if profile.fan_mode == "manual" and profile.fan_speed_pct > 0:
                self.last_notes.append("Lüfter nicht gesetzt — bitte in Afterburner einstellen")

            if new == old or (slot_equivalent(old, new, slot)
                              and section_equivalent(old, new, STARTUP)):
                return self.load_profile_slot(slot)   # slot (and boot entry) already hold these values

            if self.is_running():
                ok, err = self.close()
                if not ok:
                    return False, err
                try:                    # it may have saved something on exit (also [Startup])
                    old, enc = self._read(path)
                    new, notes = build(old)
                    self.last_notes = notes
                except (ProfileError, OSError) as e:
                    self.start()
                    return False, f"Afterburner-Profil: {e}"
            try:
                self._backup(path)
                self._write(path, new, enc)
            except PermissionError:
                self.start()
                return False, ("Keine Schreibrechte im Afterburner-Ordner — "
                               "GameOptimizerPro als Administrator starten.")
            except OSError as e:
                self.start()
                return False, f"Schreiben fehlgeschlagen: {e}"
            return self.start(slot)

    def slot_holding(self, profile: TuneProfile, slots=(2, 3, 4, 5)) -> Optional[int]:
        """The first of `slots` that already holds exactly what writing `profile` would
        write there (read-only) — None when no slot does or the file can't be read.
        Slot 1 is the user's own and is never looked at."""
        from core.ab_profile import apply_slot, slot_equivalent, ProfileError
        path, _why = self.find_gpu_profile()
        if not path:
            return None
        try:
            spec = self._settings_for(profile)
            text, _enc = self._read(path)
        except (ProfileError, OSError, ValueError):
            return None
        for s in slots:
            try:
                new, _notes = apply_slot(text, int(s), spec)
            except ProfileError:
                continue
            if new == text or slot_equivalent(text, new, int(s)):
                return int(s)
        return None

    def base_curve(self, slot: int = 2):
        """The V/F curve apply_slot() takes the base frequencies from for this
        slot — voltage points and their stock clocks. Read-only.
        -> (VFCurve, source section) or (None, reason)."""
        from core.ab_profile import ProfileFile, pick_curve
        path, why = self.find_gpu_profile()
        if not path:
            return None, why
        try:
            text, _enc = self._read(path)
        except OSError as e:
            return None, f"Afterburner-Profil nicht lesbar: {e}"
        curve, src = pick_curve(ProfileFile(text), f"Profile{int(slot)}")
        if curve is None:
            return None, ("Das Afterburner-Profil enthält noch keine V/F-Kurve — in Afterburner "
                          "einmal unten auf 'Speichern' und dann auf einen Slot klicken.")
        return curve, src

    def slot_summaries(self, de: bool = True) -> dict:
        """{1: "Kurve · Speicher +1000 · Power 100 %", 2: "leer", …} — what the
        five slots hold right now (read-only; {} when the file can't be read)."""
        from core.ab_profile import ProfileFile, slot_summary
        path, _why = self.find_gpu_profile()
        if not path:
            return {}
        try:
            text, _enc = self._read(path)
        except OSError:
            return {}
        pf = ProfileFile(text)
        return {s: slot_summary(pf, s, de) for s in range(1, 6)}

    def reset_to_stock(self, slot: int = 2, startup="same") -> tuple[bool, str]:
        """Stock clocks, stock power limit, flat stock curve — written into OUR
        slot and applied (and, by default, what the PC boots with). (It used to
        just load the user's slot 1.)"""
        return self.write_and_apply(slot, TuneProfile(name="__stock__"), startup=startup)

    def startup_state(self, slot: int) -> Optional[bool]:
        """Does Afterburner boot with what slot `slot` holds? None = unknown /
        "apply at startup" off / slot empty. Read-only."""
        from core.ab_profile import startup_matches_slot
        path, _why = self.find_gpu_profile()
        if not path:
            return None
        try:
            text, _enc = self._read(path)
        except OSError:
            return None
        return startup_matches_slot(text, slot)

    def restore_file(self, backup_path: str) -> tuple[bool, str]:
        """Put a backed-up profile file back (Afterburner closed meanwhile) and
        start Afterburner normally."""
        with self._io_lock:
            path, why = self.find_gpu_profile()
            if not path:
                return False, why
            if self.is_running():
                ok, err = self.close()
                if not ok:
                    return False, err
            try:
                with open(backup_path, "rb") as f:
                    self._write_bytes(path, f.read())
            except OSError as e:
                self.start()
                return False, f"Wiederherstellen fehlgeschlagen: {e}"
            return self.start()


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
        if not mahm_data.available:
            stats.mahm_restarting = bool(getattr(self.mahm, "restarting", False))
        if mahm_data.available:
            stats.mahm_ok = True
            # Take a MAHM value only when Afterburner actually exports it (> 0).
            # Afterburner only publishes the sources whose graphs are enabled; the
            # old unconditional copy replaced good NVML readings with 0 (fan 45 %
            # -> 0 %, power limit 320 W -> 0 W). Afterburner's "Power/Temp limit"
            # sources are limiter FLAGS (0/1) and are no longer written into the
            # watt / °C fields at all — the temp gauge used the flag as its scale
            # maximum (1 °C) whenever the thermal limiter was active.
            # MAHM supplies what NVML can't (voltage, fan RPM). Clocks, load,
            # power and temperature come from NVML whenever it has them: MAHM is
            # a 1 s poll by another program and can freeze — after an Afterburner
            # restart the tuner saw "8 % load, 210 MHz" during full load, which
            # would have aborted a tune with "no GPU load".
            nv = stats.nvml_ok
            if mahm_data.gpu_voltage_mv > 0:
                stats.voltage_mv     = mahm_data.gpu_voltage_mv
            if mahm_data.mem_voltage_mv > 0:
                stats.mem_voltage_mv = mahm_data.mem_voltage_mv
            if mahm_data.fan_rpm > 0:
                stats.fan_rpm        = mahm_data.fan_rpm
            if mahm_data.fan_speed_pct > 0 and not nv:
                stats.fan_pct        = mahm_data.fan_speed_pct
            if mahm_data.gpu_power_w > 0 and not (nv and stats.power_w > 0):
                stats.gpu_power_w    = mahm_data.gpu_power_w
            if mahm_data.gpu_temp > 0 and not nv:
                stats.temp           = int(round(mahm_data.gpu_temp))
            if mahm_data.core_clock > 0 and not (nv and stats.core_mhz > 0):
                stats.core_mhz   = mahm_data.core_clock
            if mahm_data.shader_clock > 0:
                stats.shader_mhz = mahm_data.shader_clock
            if mahm_data.mem_clock > 0 and not (nv and stats.mem_mhz > 0):
                stats.mem_mhz    = mahm_data.mem_clock
            if mahm_data.gpu_usage > 0 and not nv:
                stats.gpu_usage  = mahm_data.gpu_usage
            if mahm_data.vram_usage > 0 and not nv:
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
