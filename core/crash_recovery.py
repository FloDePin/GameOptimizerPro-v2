"""
GameOptimizerPro Crash Recovery
Erkennt GPU TDR (Timeout Detection & Recovery) Events via Windows Event Log.
Schreibt "last_stable" Profil vor jedem Tuning-Schritt.
Beim nächsten Start: prüft ob letzter Run gecrasht ist → lädt letztes stabiles Profil.
"""

import os, json, subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional


CRASH_FLAG_FILE = "logs/.crash_flag"
LAST_STABLE_FILE = "logs/.last_stable_profile.json"
LAST_APPLIED_FILE = "logs/.last_applied_profile.json"


class CrashRecovery:
    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._crash_flag  = self.base / ".crash_flag"
        self._last_stable = self.base / ".last_stable_profile.json"
        self._last_applied = self.base / ".last_applied_profile.json"

    # ── Flag management ───────────────────────────────────────────────────────

    def set_tuning_active(self, profile_data: dict):
        """Call before each tuning step. Marks tuning in progress."""
        self._crash_flag.write_text(json.dumps({
            "ts": datetime.now().isoformat(),
            "profile": profile_data
        }), encoding="utf-8")

    def clear_tuning_flag(self):
        """Call after successful step or on clean exit."""
        if self._crash_flag.exists():
            self._crash_flag.unlink()

    def crashed_last_run(self) -> Optional[dict]:
        """
        Returns the profile that was active when last crash happened,
        or None if last run was clean.
        """
        if not self._crash_flag.exists():
            return None
        try:
            data = json.loads(self._crash_flag.read_text(encoding="utf-8"))
            return data.get("profile")
        except Exception:
            return None

    # ── Stable profile tracking ───────────────────────────────────────────────

    def save_last_stable(self, profile_dict: dict):
        """Save the last known-good profile."""
        self._last_stable.write_text(
            json.dumps(profile_dict, indent=2), encoding="utf-8")

    def load_last_stable(self) -> Optional[dict]:
        if not self._last_stable.exists():
            return None
        try:
            return json.loads(self._last_stable.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_last_applied(self, profile_dict: dict):
        """Track the most recently applied profile (for startup loader)."""
        self._last_applied.write_text(
            json.dumps(profile_dict, indent=2), encoding="utf-8")

    def rename_last_applied(self, old: str, new: str) -> bool:
        """A profile was renamed: the last-applied record follows. Its time stays
        — the GPU watchdog counts events since the profile was APPLIED."""
        try:
            d = self.load_last_applied()
            if not d or d.get("name") != old:
                return False
            st = self._last_applied.stat()
            d["name"] = new
            self.save_last_applied(d)
            os.utime(self._last_applied, (st.st_atime, st.st_mtime))
            return True
        except OSError:
            return False

    def load_last_applied(self) -> Optional[dict]:
        if not self._last_applied.exists():
            return None
        try:
            return json.loads(self._last_applied.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ── TDR detection via Windows Event Log ──────────────────────────────────

    # Display driver reset (Display 4101) and the NVIDIA driver's error reports
    # nvlddmkm 13 (graphics exception) / 14. The live Rundum run on an RTX 4080
    # (memory +1500) logged a burst of nvlddmkm 13 + 14 when FurMark's picture
    # got green speckles, the screens went black and FurMark died — no 4101, so
    # a 4101-only check missed that crash. NOT nvlddmkm 153: the driver logs it
    # at the end of EVERY stress step (the worker is stopped mid-kernel) — 17x
    # in a run without any problem; counting it stopped a tune at stock clocks.
    GPU_ERROR_EVENTS = "4101,13,14"

    def check_tdr_since(self, seconds_back: int = 120) -> bool:
        """
        Check Windows Event Log for a driver reset / NVIDIA GPU error in the
        last N seconds. Returns True if one was found.
        """
        if os.name != "nt":
            return False
        try:
            ps_cmd = (
                f"$cutoff = (Get-Date).AddSeconds(-{int(seconds_back)}); "
                f"$events = Get-WinEvent -FilterHashtable "
                f"@{{LogName='System'; Id={self.GPU_ERROR_EVENTS}; StartTime=$cutoff}} "
                f"-ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.Id -eq 4101 -or $_.ProviderName -eq 'nvlddmkm' }}; "
                f"if ($events) {{ 'TDR_FOUND' }} else {{ 'NO_TDR' }}"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return "TDR_FOUND" in result.stdout
        except Exception:
            return False

    def get_tdr_count_since(self, seconds_back: int = 300) -> int:
        """Returns number of TDR events in last N seconds."""
        if os.name != "nt":
            return 0
        try:
            ps_cmd = (
                f"$cutoff = (Get-Date).AddSeconds(-{seconds_back}); "
                f"$events = Get-WinEvent -FilterHashtable "
                f"@{{LogName='System'; Id=4101; StartTime=$cutoff}} "
                f"-ErrorAction SilentlyContinue; "
                f"if ($events) {{ $events.Count }} else {{ 0 }}"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            txt = result.stdout.strip()
            return int(txt) if txt.isdigit() else 0
        except Exception:
            return 0
