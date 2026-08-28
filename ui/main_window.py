"""
GameOptimizerPro v2.1 — Main Window
Layout inspired by v1.0: dark bg, colored tab buttons, hardware info bar,
compact header, status bar at bottom.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading, time
from datetime import datetime
from pathlib import Path

from ui.widgets       import *
from ui.tab_dashboard  import DashboardTab
from ui.tab_optimizer  import OptimizerTab
from ui.tab_gpu        import GpuTunerTab
from ui.tab_stress     import StressTab
from ui.tab_compare    import CompareTab
from ui.tab_bios       import BiosGuideTab
from ui.tab_games      import GamesTab
from ui.startup_manager import StartupManagerWindow
from ui.tab_settings   import SettingsTab
from core.hardware     import HardwareInfo
from core.nvtune_core  import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner
from core.tweak_runner import TweakRunner

APP_NAME    = "GameOptimizerPro"
APP_VERSION = "v2.4.1"

# Tab definitions: (key, label, color_active, color_bg)
TAB_DEFS = [
    ("dashboard", "[SYS]  Dashboard",  "#e53935", "#1a0a0a"),
    ("optimizer", "[WIN]  Optimizer",   "#e53935", "#1a0a0a"),
    ("gpu",       "[GPU]  GPU Tuner",   "#00b4d8", "#001a20"),
    ("stress",    "[TEST] Stress Test", "#f59e0b", "#1a1200"),
    ("compare",   "[CMP]  Compare",     "#7c3aed", "#100a1a"),
    ("bios",      "[BIOS] BIOS Guide",  "#f59e0b", "#1a1200"),
    ("games",     "[GME]  Games & History", "#22c55e", "#001a0a"),
    ("settings",  "[SET]  Settings",    "#6b7280", "#0f0f0f"),
]


class GameOptimizerWindow(tk.Tk):
    def __init__(
        self,
        hw:      HardwareInfo,
        monitor: GpuMonitor,
        ab:      AfterburnerController,
        pm:      ProfileManager,
        tuner:   AutoTuner,
        runner:  TweakRunner,
        startup_loader=None,
        game_monitor=None,
    ):
        super().__init__()
        self.hw             = hw
        self.monitor        = monitor
        self.ab             = ab
        self.pm             = pm
        self.tuner          = tuner
        self.runner         = runner
        self.startup_loader = startup_loader
        self.game_monitor   = game_monitor

        self._active_tab    = "dashboard"
        self._tab_frames:   dict[str, tk.Frame] = {}
        self._tab_btns:     dict[str, tk.Button] = {}

        self._setup_window()
        self._build_header()
        self._build_hw_bar()
        self._build_tab_bar()
        self._build_content()
        self._build_status_bar()
        self._show_tab("dashboard")
        self._start_updater()

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.title(f"{APP_NAME} {APP_VERSION} -- by FloDePin")
        self.geometry("1000x920")
        self.minsize(900, 720)
        self.configure(bg="#0d1117")
        apply_ttk_style(self)   # global dark theme + option_add overrides

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg="#0d1117")
        hdr.pack(fill="x", padx=14, pady=(12, 0))

        tk.Label(
            hdr, text=APP_NAME,
            font=("Segoe UI", 22, "bold"),
            fg="#e53935", bg="#0d1117"
        ).pack(side="left")

        ver_f = tk.Frame(hdr, bg="#0d1117")
        ver_f.pack(side="left", padx=10)
        tk.Label(
            ver_f, text=f"Windows & Gaming Optimizer {APP_VERSION} -- by FloDePin",
            font=("Segoe UI", 9), fg="#6b7280", bg="#0d1117"
        ).pack(anchor="w")

        # Right side: AB / NVML / MAHM indicators
        ind = tk.Frame(hdr, bg="#0d1117")
        ind.pack(side="right")
        self.lbl_mahm = tk.Label(ind, text="MAHM: ?", font=("Consolas", 9), bg="#0d1117")
        self.lbl_nvml = tk.Label(ind, text="NVML: ?", font=("Consolas", 9), bg="#0d1117")
        self.lbl_ab   = tk.Label(ind, text="AB: ?",   font=("Consolas", 9), bg="#0d1117")
        self.lbl_time = tk.Label(ind, text="",        font=("Consolas", 9), fg="#4b5563", bg="#0d1117")
        # DE/EN language toggle button — always visible
        # Shows the language you can switch TO, so the action is clear
        from core.i18n import current_lang
        _next_lang_label = "DE" if current_lang() == "en" else "EN"
        self.btn_lang = tk.Button(
            ind, text=_next_lang_label,
            command=self._toggle_lang,
            font=("Consolas", 8, "bold"),
            bg="#1c2128", fg="#00d9ff",
            relief="flat", padx=8, pady=2, cursor="hand2",
            activebackground="#2d333b"
        )
        for w in (self.lbl_time, self.btn_lang, self.lbl_mahm, self.lbl_nvml, self.lbl_ab):
            w.pack(side="right", padx=6)
        self._refresh_indicators()

    # ── HW info bar (like v1.0) ───────────────────────────────────────────────

    def _build_hw_bar(self):
        bar = tk.Frame(self, bg="#0d1117")
        bar.pack(fill="x", padx=14, pady=(4, 6))

        # Line 1: GPU | RAM | NVMe
        line1 = (
            f"GPU: {self.hw.gpu_name[:34]}    |    "
            f"RAM: {self.hw.ram_total_gb:.0f} GB    |    "
            f"NVMe: {'yes' if self.hw.has_nvme else 'none'}"
        )
        # Line 2: CPU | OS
        line2 = (
            f"CPU: {self.hw.cpu_name[:44]}    |    "
            f"{'Win11' if self.hw.is_win11 else 'Win10'} (Build {self.hw.os_build})"
        )
        tk.Label(bar, text=line1, font=("Consolas", 8),
                 fg="#00b4d8", bg="#0d1117", anchor="w").pack(fill="x")
        tk.Label(bar, text=line2, font=("Consolas", 8),
                 fg="#00b4d8", bg="#0d1117", anchor="w").pack(fill="x")

        # Separator line
        tk.Frame(self, bg="#2d333b", height=1).pack(fill="x", padx=0)

    # ── Tab bar (colored buttons like v1.0) ───────────────────────────────────

    def _build_tab_bar(self):
        # Two rows of 4 buttons each (like v1.0 layout)
        tab_bar = tk.Frame(self, bg="#161b22")
        tab_bar.pack(fill="x")

        row1 = tk.Frame(tab_bar, bg="#161b22")
        row1.pack(fill="x")
        row2 = tk.Frame(tab_bar, bg="#161b22")
        row2.pack(fill="x")

        rows = [
            [TAB_DEFS[0], TAB_DEFS[2], TAB_DEFS[4]],   # Dashboard, GPU, Compare
            [TAB_DEFS[1], TAB_DEFS[3], TAB_DEFS[5]],   # Optimizer, Stress, BIOS
            [TAB_DEFS[6], TAB_DEFS[7]],                 # Games, Settings
        ]

        for row_frame, tab_list in [(row1, rows[0]), (row2, rows[1])]:
            for key, label, color, _ in tab_list:
                btn = tk.Button(
                    row_frame,
                    text=label,
                    font=("Consolas", 9, "bold"),
                    bg="#1c2128", fg="#6b7280",
                    activebackground=color,
                    activeforeground="#ffffff",
                    relief="flat", bd=0,
                    padx=16, pady=8,
                    cursor="hand2",
                    command=lambda k=key: self._show_tab(k)
                )
                btn.pack(side="left", fill="x", expand=True)
                self._tab_btns[key] = btn

        tk.Frame(self, bg="#2d333b", height=1).pack(fill="x")

    # ── Content area ──────────────────────────────────────────────────────────

    def _build_content(self):
        self._content = tk.Frame(self, bg="#0d1117")
        self._content.pack(fill="both", expand=True)

        base = Path(__file__).resolve().parent.parent

        self._tab_frames["dashboard"] = DashboardTab(
            self._content, self.hw, self.monitor)
        self._tab_frames["optimizer"] = OptimizerTab(
            self._content, self.runner, self.hw,
            profiles_dir=str(base / "profiles"),
            logs_dir=str(base / "logs"))
        self._tab_frames["gpu"]       = GpuTunerTab(
            self._content, self.monitor, self.ab, self.pm, self.tuner)
        self._tab_frames["stress"]    = StressTab(
            self._content, self.monitor)
        self._tab_frames["compare"]   = CompareTab(
            self._content, self.pm)
        self._tab_frames["bios"]      = BiosGuideTab(
            self._content, self.hw)
        self._tab_frames["games"]     = GamesTab(
            self._content, self.game_monitor, self.pm,
            str(Path(__file__).resolve().parent.parent / "logs"))
        self._tab_frames["settings"]  = SettingsTab(
            self._content, self.ab, self.monitor, self.startup_loader)

    def _show_tab(self, key: str):
        self._active_tab = key

        # Hide all, show selected
        for k, frame in self._tab_frames.items():
            frame.pack_forget()
        self._tab_frames[key].pack(fill="both", expand=True)

        # Update button colors
        for k, btn in self._tab_btns.items():
            tab_color = next(c for tk_key, _, c, _ in TAB_DEFS if tk_key == k)
            if k == key:
                btn.config(bg=tab_color, fg="#ffffff",
                           font=("Consolas", 9, "bold"))
            else:
                btn.config(bg="#1c2128", fg="#6b7280",
                           font=("Consolas", 9))

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        tk.Frame(self, bg="#2d333b", height=1).pack(fill="x")
        status = tk.Frame(self, bg="#161b22", height=28)
        status.pack(fill="x")
        status.pack_propagate(False)

        self.lbl_status = tk.Label(
            status,
            text="Ready -- select tweaks and click Apply Selected.",
            font=("Consolas", 8), fg="#6b7280", bg="#161b22",
            anchor="w"
        )
        self.lbl_status.pack(side="left", padx=10)

        # Quick action buttons (like v1.0 bottom bar)
        for text, cmd in [
            ("🚀 Startup Mgr", self._open_startup_mgr),
            ("⚙ Services Mgr", self._open_services),
            ("[Log] Open Log",  self._open_log),
        ]:
            tk.Button(
                status, text=text,
                font=("Consolas", 8),
                bg="#1c2128", fg="#9ca3af",
                relief="flat", padx=10, pady=4,
                cursor="hand2",
                command=cmd
            ).pack(side="right", padx=2, pady=2)

    def _open_startup_mgr(self):
        """Open our custom Startup Manager window."""
        StartupManagerWindow(self)

    def _open_services(self):
        import subprocess as sp
        sp.Popen(["services.msc"],
                 shell=True,
                 creationflags=sp.CREATE_NO_WINDOW if hasattr(sp, 'CREATE_NO_WINDOW') else 0)

    def _open_log(self):
        import subprocess as sp
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        sp.Popen(["explorer.exe", str(log_dir)])

    # ── Updater ───────────────────────────────────────────────────────────────

    def _refresh_indicators(self):
        self.lbl_ab.config(
            text=f"AB: {'✓' if self.ab.available else '✗'}",
            fg="#22c55e" if self.ab.available else "#ef4444"
        )
        self.lbl_nvml.config(
            text=f"NVML: {'✓' if self.monitor.nvml.available else '✗'}",
            fg="#22c55e" if self.monitor.nvml.available else "#f59e0b"
        )
        mahm_ok = self.monitor.mahm.available
        self.lbl_mahm.config(
            text=f"MAHM: {'✓' if mahm_ok else '✗'}",
            fg="#22c55e" if mahm_ok else "#f59e0b"
        )

    def _start_updater(self):
        def tick():
            while True:
                ts = datetime.now().strftime("%H:%M:%S")
                try:
                    self.after(0, lambda t=ts: self.lbl_time.config(text=t))
                    self.after(0, self._refresh_indicators)
                except:
                    break
                time.sleep(5)
        threading.Thread(target=tick, daemon=True).start()

    def _toggle_lang(self):
        """
        Switch language and restart the app so every label is rebuilt cleanly.
        The new language is saved to disk and loaded on the next start.
        """
        from core.i18n import current_lang, set_lang
        from tkinter import messagebox

        new = "de" if current_lang() == "en" else "en"

        lang_name = "Deutsch" if new == "de" else "English"
        proceed = messagebox.askyesno(
            "Sprache wechseln / Change language",
            f"Sprache auf {lang_name} umstellen?\n"
            f"Die App wird dafuer kurz neu gestartet.\n\n"
            f"Switch language to {lang_name}?\n"
            f"The app will restart briefly.",
            parent=self
        )
        if not proceed:
            return

        set_lang(new)   # persists to disk

        # Close cleanly, then relaunch a fresh instance
        try:
            self.monitor.close()
        except Exception:
            pass

        import sys, os, subprocess
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent
        try:
            subprocess.Popen([sys.executable, str(base / "GameOptimizerPro.py")],
                             cwd=str(base))
        except Exception:
            pass
        os._exit(0)

    def on_close(self):
        self.monitor.close()
        self.destroy()

# Keep backward-compat alias
# Backward compatibility alias
GameOptimizerProWindow = GameOptimizerWindow
