"""
GameOptimizerPro v2.1 — Entry Point
Architektur (thread-safe):
  Main-Thread  → tkinter mainloop() — einziger Thread der tkinter anfasst
  Thread 2     → pystray.run_detached() — Tray-Icon, non-blocking
  Thread 3     → GPU stats loop
  Thread 4     → Startup (crash check + profile load)
  Thread 5     → Tray menu refresh

Kein tk.Tk() vor mainloop. Kein mainloop() in Threads.
Admin-Dialog: über ctypes MessageBox (kein tkinter nötig).
"""

import os, sys, time, threading, ctypes
from tkinter import messagebox
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from core.hardware       import detect as detect_hw
from core.nvtune_core    import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner   import AutoTuner, TunerConfig
from core.tweak_runner   import TweakRunner
from core.crash_recovery import CrashRecovery
from core.startup_loader import StartupLoader
from core.game_monitor   import GameMonitor
from core.temp_monitor   import TempMonitor
from core.update_checker import UpdateChecker
from core                import i18n
from ui.main_window      import GameOptimizerWindow


# ── Restart helper (used for language switch) ─────────────────────────────────

def restart_app():
    """
    Restart the whole application in-place. Used when the language changes,
    so every label is rebuilt in the new language with no leftovers.
    """
    try:
        python = sys.executable
        script = str(BASE / "GameOptimizerPro.py")
        # Launch a fresh instance, then exit this one
        subprocess = __import__("subprocess")
        subprocess.Popen([python, script], cwd=str(BASE))
    except Exception:
        pass
    os._exit(0)


# ── Admin helpers ─────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:
        return False


def ask_admin_msgbox() -> bool:
    """Show admin prompt via Win32 MessageBox — no tkinter needed.
    Localised: main() calls i18n.init_lang() before this runs."""
    msg   = i18n.t("admin_required_msg")
    title = i18n.t("admin_required_title")
    # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST = 0x4 | 0x20 | 0x40000 = 0x40024
    result = ctypes.windll.user32.MessageBoxW(0, msg, title, 0x40024)
    return result == 6  # IDYES = 6


def relaunch_admin():
    # lpDirectory = str(BASE): ohne das setzt UAC das Arbeitsverzeichnis oft auf
    # C:\Windows\System32 — relative Pfade würden dann dort landen.
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        " ".join(f'"{a}"' for a in sys.argv), str(BASE), 1
    )
    sys.exit(0)


# ── Tray icon image ───────────────────────────────────────────────────────────

def make_icon():
    try:
        from PIL import Image, ImageDraw
        sz = 64
        img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse([1, 1, sz-1, sz-1], fill=(10, 12, 20, 230))
        d.rectangle([14, 14, 22, 50], fill=(0, 217, 255, 255))
        d.rectangle([42, 14, 50, 50], fill=(0, 217, 255, 255))
        d.polygon([(22, 14), (42, 50), (42, 38), (22, 14)],
                  fill=(0, 217, 255, 255))
        return img
    except ImportError:
        try:
            from PIL import Image
            return Image.new("RGB", (64, 64), (0, 217, 255))
        except:
            return None


# ── Main application ──────────────────────────────────────────────────────────

class GameOptimizerApp:
    """
    Thread-safe architecture:
      - All tkinter calls happen exclusively in _tk_main() → Main-Thread
      - pystray runs in its own thread via run_detached()
      - Background work (stats, startup) in daemon threads
      - Cross-thread communication via _pending_actions queue + tk.after()
    """

    def __init__(self):
        logs_dir = str(BASE / "logs")
        Path(logs_dir).mkdir(parents=True, exist_ok=True)

        # Core components (thread-safe, no tkinter)
        self.hw      = detect_hw()
        self.monitor = GpuMonitor()
        self.ab      = AfterburnerController()
        self.pm      = ProfileManager(str(BASE / "profiles"))
        self.cr      = CrashRecovery(logs_dir)
        self.tuner   = AutoTuner(
            self.monitor, self.ab, self.pm, TunerConfig(),
            log_dir=logs_dir, crash_recovery=self.cr,
        )
        self.runner  = TweakRunner(log_dir=logs_dir)
        self.sl      = StartupLoader(logs_dir, self.ab, self.pm, self.cr)

        # State (read from any thread, written carefully)
        self._running  = True
        self._tray     = None
        self._window:  Optional[GameOptimizerWindow] = None
        self._visible  = False

        # New feature components
        self.game_monitor = GameMonitor(str(BASE), self.ab, self.pm, self.cr)
        self.temp_monitor = TempMonitor(self.monitor, limit_c=90)
        self.update_checker = UpdateChecker()

        # Cached tray stats (written by stats thread, read by tray thread)
        self._temp  = 0
        self._volt  = 0.0
        self._power = 0.0
        self._clk   = 0.0
        self._gpu   = "GPU"

    # ── Window management ─────────────────────────────────────────────────────

    def _open(self, icon=None, item=None):
        """Called from tray thread → push to main thread via .after()."""
        if self._window:
            try:
                self._window.after(0, self._show_window)
            except:
                pass

    def _show_window(self):
        """Always runs in main thread."""
        if self._window:
            self._window.deiconify()
            self._window.lift()
            self._window.focus_force()

    def _hide(self):
        if self._window:
            try:
                self._window.withdraw()
            except:
                pass

    def _reset_gpu(self, icon=None, item=None):
        def _do():
            self.ab.reset_to_stock()
            _, _, mx = self.monitor.get_power_constraints()
            if mx > 0:
                self.monitor.set_power_limit(mx)
        threading.Thread(target=_do, daemon=True).start()

    def _on_update_result(self, available: bool, version: str, url: str):
        """Show update notification in title bar via after()."""
        if available and self._window:
            def _show():
                try:
                    if messagebox.askyesno(
                        "Update verfügbar",
                        f"Neue Version {version} verfügbar!\n\nJetzt herunterladen?",
                        parent=self._window
                    ):
                        import webbrowser
                        webbrowser.open(url)
                except: pass
            self._window.after(2000, _show)

    def _exit(self, icon=None, item=None):
        self._running = False
        try: self.game_monitor.stop()
        except: pass
        try: self.temp_monitor.stop()
        except: pass
        try:
            self.monitor.close()
        except:
            pass
        # Destroy tkinter safely from main thread
        if self._window:
            try:
                self._window.after(0, self._window.destroy)
            except:
                pass
        def _stop():
            if self._tray:
                try:
                    self._tray.stop()
                except:
                    pass
            time.sleep(0.3)
            os._exit(0)
        threading.Thread(target=_stop, daemon=True).start()

    def _show_crash_dialog(self, message: str):
        """Show crash dialog thread-safely via .after() or fallback to ctypes."""
        if self._window:
            try:
                self._window.after(
                    0,
                    lambda: messagebox.showwarning(
                        "GameOptimizerPro — Crash erkannt",
                        message, parent=self._window
                    )
                )
            except:
                ctypes.windll.user32.MessageBoxW(
                    0, message,
                    "GameOptimizerPro — Crash erkannt", 0x40030
                )
        else:
            # Fenster existiert noch nicht (Startup-Race) → direkt Win32 MessageBox
            ctypes.windll.user32.MessageBoxW(
                0, message,
                "GameOptimizerPro — Crash erkannt", 0x40030
            )

    # ── Tray menu ─────────────────────────────────────────────────────────────

    def _build_menu(self):
        try:
            import pystray
            from pystray import MenuItem as MI, Menu
        except:
            return None

        profiles = [p for p in self.pm.list_all()
                    if not p.name.startswith("__")]

        def apply_fn(name):
            def _do(icon=None, item=None):
                p = self.pm.load(name)
                if p and self.ab.available:
                    threading.Thread(
                        target=lambda: (
                            self.ab.write_and_apply(2, p),
                            self.cr.save_last_applied(p.to_dict())
                        ),
                        daemon=True
                    ).start()
            return _do

        p_items = [
            MI(
                f"{'✓' if p.is_stable else '⚠'} {p.name} "
                f"[+{p.core_offset_mhz}MHz | {p.power_limit_pct}%]",
                apply_fn(p.name)
            )
            for p in sorted(profiles, key=lambda x: x.name)
        ] or [MI("Keine Profile vorhanden", None, enabled=False)]

        volt_s    = f"{self._volt:.0f}mV  |  " if self._volt > 0 else ""
        stats_lbl = (
            f"{self._temp}°C  |  {self._clk:.0f}MHz  |  "
            f"{volt_s}{self._power:.0f}W"
        )

        return Menu(
            MI("⚡ GameOptimizerPro öffnen", self._open),
            Menu.SEPARATOR,
            MI("GPU Profil ▶",              Menu(*p_items)),
            MI("GPU auf Stock zurücksetzen", self._reset_gpu),
            Menu.SEPARATOR,
            MI(stats_lbl, None, enabled=False),
            Menu.SEPARATOR,
            MI("Beenden",                   self._exit),
        )

    # ── Background threads ────────────────────────────────────────────────────

    def _stats_loop(self):
        while self._running:
            try:
                s = self.monitor.read()
                self._temp  = s.temp
                self._volt  = s.voltage_mv
                self._power = s.gpu_power_w
                self._clk   = s.core_mhz
                self._gpu   = s.name[:22]
                if self._tray:
                    volt_s = f" | {s.voltage_mv:.0f}mV" if s.voltage_mv > 0 else ""
                    try:
                        # Keep the tray tooltip compact — Windows caps szTip at
                        # ~127 chars; GPU name is already trimmed to 22.
                        title = (
                            f"GameOptimizerPro | {self._gpu}\n"
                            f"{s.temp}°C | {s.core_mhz:.0f}MHz"
                            f"{volt_s} | {s.gpu_power_w:.0f}W"
                        )
                        self._tray.title = title[:120]
                    except:
                        pass
            except:
                pass
            time.sleep(4)

    def _menu_refresh_loop(self):
        # 60s statt 20s: pystray klappt ein offenes Tray-Menü ein, wenn es
        # während der Anzeige neu aufgebaut wird — seltener = kleineres Zeitfenster.
        while self._running:
            time.sleep(60)
            if self._tray:
                try:
                    self._tray.menu = self._build_menu()
                    self._tray.update_menu()
                except:
                    pass

    def _startup_bg(self):
        """Crash check + startup profile — runs in background thread."""
        try:
            crashed = self.sl.check_and_handle_crash(
                on_crash_detected=self._show_crash_dialog
            )
            if self.ab.available:
                ok, msg = self.sl.load_startup_profile()
                if ok:
                    print(f"[GameOptimizerPro] {msg}")
        except Exception as e:
            print(f"[GameOptimizerPro] Startup error: {e}")

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(self):
        # 1. Background threads
        threading.Thread(target=self._startup_bg,        daemon=True).start()
        threading.Thread(target=self._stats_loop,        daemon=True).start()
        threading.Thread(target=self._menu_refresh_loop, daemon=True).start()
        self.game_monitor.start()
        self.temp_monitor.start()
        self.update_checker.on_result(self._on_update_result)
        self.update_checker.check_async()

        # 2. Tkinter window created DIRECTLY in main thread
        self._window = GameOptimizerWindow(
            self.hw, self.monitor, self.ab, self.pm,
            self.tuner, self.runner,
            startup_loader=self.sl,
            game_monitor=self.game_monitor,
        )
        self._window.protocol("WM_DELETE_WINDOW", self._hide)

        # 3. Tray icon in its own background thread
        try:
            import pystray
            icon_img = make_icon()
            if icon_img:
                self._tray = pystray.Icon(
                    "GameOptimizerPro", icon_img,
                    "GameOptimizerPro", menu=self._build_menu()
                )
                def _tray_setup(icon):
                    icon.visible = True
                threading.Thread(
                    target=self._tray.run,
                    kwargs={"setup": _tray_setup},
                    daemon=True
                ).start()
        except ImportError:
            pass

        # 4. mainloop() blocks here in main thread — the ONLY correct place
        self._window.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Load the saved language before any UI is built
    i18n.init_lang()

    # Admin check — use Win32 MessageBox (no tkinter instance needed)
    if os.name == "nt" and not is_admin():
        if ask_admin_msgbox():
            relaunch_admin()
        # Continue without admin (some features won't work)

    GameOptimizerApp().run()


if __name__ == "__main__":
    main()
