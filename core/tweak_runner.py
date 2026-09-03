"""
GameOptimizerPro Tweak Runner
Executes PowerShell tweaks as subprocess, tracks state, provides revert.
"""

import subprocess, os, json, logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from core.tweaks import Tweak, get_by_id


class TweakRunner:
    def __init__(self, log_dir: str = "logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        # Keep the state file next to the logs (absolute) — NOT a CWD-relative
        # path, which would land elsewhere when the app is started from another
        # working dir (autostart / UAC relaunch) and lose the applied-state.
        self._state_file = self._log_dir / "applied_tweaks.json"
        self._applied: dict[str, str] = self._load_state()

        logfile = self._log_dir / f"tweaks_{datetime.now().strftime('%Y%m%d')}.log"
        logging.basicConfig(
            filename=str(logfile), level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
        self.logger = logging.getLogger("gop.tweaks")

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def _save_state(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(self._applied, f, indent=2)

    def is_applied(self, tweak_id: str) -> bool:
        return tweak_id in self._applied

    def apply(
        self,
        tweak: Tweak,
        on_result: Optional[Callable[[str, bool, str], None]] = None
    ) -> tuple[bool, str]:
        """Apply a tweak. Returns (success, output)."""
        cmd = tweak.ps_command.strip()
        ok, out = self._run_ps(cmd)
        self.logger.info(f"APPLY {tweak.id}: {'OK' if ok else 'FAIL'} | {out[:200]}")
        if ok:
            self._applied[tweak.id] = datetime.now().isoformat()
            self._save_state()
        if on_result:
            on_result(tweak.id, ok, out)
        return ok, out

    def revert(
        self,
        tweak: Tweak,
        on_result: Optional[Callable[[str, bool, str], None]] = None
    ) -> tuple[bool, str]:
        """Revert a tweak if revert_cmd is defined."""
        if not tweak.revert_cmd:
            msg = f"No revert command for '{tweak.name}'"
            if on_result: on_result(tweak.id, False, msg)
            return False, msg
        ok, out = self._run_ps(tweak.revert_cmd.strip())
        self.logger.info(f"REVERT {tweak.id}: {'OK' if ok else 'FAIL'} | {out[:200]}")
        if ok and tweak.id in self._applied:
            del self._applied[tweak.id]
            self._save_state()
        if on_result: on_result(tweak.id, ok, out)
        return ok, out

    def apply_batch(
        self,
        tweaks: list[Tweak],
        on_each: Optional[Callable[[Tweak, bool, str], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> dict[str, tuple[bool, str]]:
        results = {}
        for i, tweak in enumerate(tweaks):
            ok, out = self.apply(tweak)
            results[tweak.id] = (ok, out)
            if on_each: on_each(tweak, ok, out)
            if on_progress: on_progress(i + 1, len(tweaks))
        return results

    def revert_all(
        self,
        on_each: Optional[Callable[[Tweak, bool, str], None]] = None
    ) -> dict[str, tuple[bool, str]]:
        results = {}
        applied_ids = list(self._applied.keys())
        for tid in applied_ids:
            tweak = get_by_id(tid)
            if tweak:
                ok, out = self.revert(tweak)
                results[tid] = (ok, out)
                if on_each: on_each(tweak, ok, out)
        return results

    @staticmethod
    def _run_ps(command: str) -> tuple[bool, str]:
        """Run a PowerShell command block silently (no window), return (success, output)."""
        try:
            # CREATE_NO_WINDOW + WindowStyle Hidden = completely invisible on Windows
            flags = 0
            startupinfo = None
            if os.name == "nt":
                flags = subprocess.CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden",
                 "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace",
                creationflags=flags,
                startupinfo=startupinfo,
            )
            out = ((result.stdout or "") + (result.stderr or "")).strip()
            return result.returncode == 0, out
        except subprocess.TimeoutExpired:
            return False, "Timeout after 60s"
        except Exception as e:
            return False, str(e)
