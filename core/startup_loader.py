"""
GameOptimizerPro Startup Loader
- Lädt beim Start das "Tray Default" Profil automatisch in Afterburner
- Prüft ob letzter Run gecrasht ist und warnt den User
- Registriert / entfernt GameOptimizerPro aus Windows Autostart (HKCU Run)
"""

import os, sys, json, subprocess
try:
    import winreg
except ImportError:
    winreg = None
from pathlib import Path
from typing import Optional, Callable


AUTOSTART_KEY  = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "GameOptimizerPro"
TASK_NAME      = "GameOptimizerPro_Autostart"


def _nw_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class StartupLoader:
    def __init__(self, base_dir: str, ab, pm, crash_recovery):
        self.base    = Path(base_dir)
        self.ab      = ab      # AfterburnerController
        self.pm      = pm      # ProfileManager
        self.cr      = crash_recovery

    # ── Crash recovery check ──────────────────────────────────────────────────

    def check_and_handle_crash(self, on_crash_detected: Optional[Callable] = None) -> bool:
        """
        Call on startup. Returns True if a crash was detected.
        Loads last_stable profile if crash detected.
        """
        crashed_profile = self.cr.crashed_last_run()
        if not crashed_profile:
            return False

        # Crash detected — load last stable profile
        last_stable = self.cr.load_last_stable()
        self.cr.clear_tuning_flag()

        if last_stable and self.ab.available:
            from core.nvtune_core import TuneProfile
            try:
                p = TuneProfile.from_dict(last_stable)
                p.name = "__crash_recovery__"
                self.ab.write_and_apply(2, p)
            except: pass

        if on_crash_detected:
            name = crashed_profile.get("name", "Unknown")
            core = crashed_profile.get("core_offset_mhz", 0)
            pwr  = crashed_profile.get("power_limit_pct", 100)
            on_crash_detected(
                f"Letzter Run hat einen GPU-Crash verursacht!\n\n"
                f"Aktives Profil beim Crash: {name} "
                f"(Core+{core}MHz, Power {pwr}%)\n\n"
                f"GameOptimizerPro hat das letzte stabile Profil geladen.\n"
                f"Empfehlung: Tuning mit konservativeren Werten wiederholen."
            )
        return True

    # ── Startup profile load ──────────────────────────────────────────────────

    def load_startup_profile(self) -> tuple[bool, str]:
        """
        Loads tray_default profile into Afterburner on startup.
        Returns (success, message).
        """
        if not self.ab.available:
            return False, "Afterburner not available"

        # Try tray default first
        profile = self.pm.get_tray_default()

        # Fallback: last applied profile
        if not profile:
            last = self.cr.load_last_applied()
            if last:
                from core.nvtune_core import TuneProfile
                try:
                    profile = TuneProfile.from_dict(last)
                except: pass

        if not profile:
            return False, "No startup profile configured"

        # Don't load placeholder names
        if profile.name.startswith("__"):
            return False, "No startup profile configured"

        ok, err = self.ab.write_and_apply(2, profile)
        if ok:
            return True, f"Startup profile loaded: {profile.name}"
        return False, f"Failed to load startup profile: {err}"

    # ── Windows Autostart (per Task Scheduler) ────────────────────────────────
    # WICHTIG: NICHT über HKCU\Run. Da die App Admin-Rechte braucht, würde ein
    # Run-Eintrag bei JEDEM Boot einen UAC-Prompt auslösen. Der Task Scheduler
    # mit "/RL HIGHEST" startet die App still mit höchsten Rechten — kein UAC.

    def is_autostart_enabled(self) -> bool:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                               capture_output=True, text=True, creationflags=_nw_flags())
            if r.returncode == 0:
                return True
        except Exception:
            pass
        # Migration: alter (UAC-verursachender) Run-Eintrag noch vorhanden?
        return self._legacy_run_present()

    def set_autostart(self, enabled: bool) -> bool:
        exe    = sys.executable   # pythonw.exe
        script = str(Path(__file__).resolve().parent.parent / "GameOptimizerPro.py")
        try:
            if enabled:
                # /TR als EIN Argument — subprocess quoted es korrekt (Pfade mit Leerzeichen)
                r = subprocess.run(
                    ["schtasks", "/Create", "/TN", TASK_NAME,
                     "/TR", f'"{exe}" "{script}"',
                     "/SC", "ONLOGON", "/RL", "HIGHEST", "/F"],
                    capture_output=True, text=True, creationflags=_nw_flags())
                self._remove_legacy_run()   # alten Run-Eintrag entfernen
                return r.returncode == 0
            else:
                subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                               capture_output=True, text=True, creationflags=_nw_flags())
                self._remove_legacy_run()
                return True
        except Exception:
            return False

    # ── Legacy HKCU\Run Migration/Cleanup ─────────────────────────────────────

    def _legacy_run_present(self) -> bool:
        if not winreg:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _remove_legacy_run(self):
        if not winreg:
            return
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass
