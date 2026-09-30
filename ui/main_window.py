"""
GameOptimizerPro v2.0 — Main Window (CustomTkinter)
Sidebar navigation on the left, the page on the right, status bar at the
bottom. Pages are built the first time they are opened (the optimizer and the
GPU tuner shortly after start-up in the background), so the window is up at once.
"""

import threading
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from core.hardware     import HardwareInfo
from core.nvtune_core  import GpuMonitor, AfterburnerController, ProfileManager
from core.nvtune_tuner import AutoTuner
from core.tweak_runner import TweakRunner
from ui import theme
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, DIM, ERR, F_MONO, F_S, F_XS, GREEN,
                      HEADER_BG, HOVER, MUTED, PAGE_COLORS, RED, SIDEBAR_BG, TEXT, TEXT2, WHITE,
                      ctk_font, icon_image, tint, tr)
from ui.components import WrapLabel

APP_NAME    = "GameOptimizerPro"
APP_VERSION = "v2.0"

BASE = Path(__file__).resolve().parent.parent

# Sidebar: (key, German label, English label)
TAB_DEFS = [
    ("dashboard", "Dashboard",          "Dashboard"),
    ("optimizer", "Optimizer",          "Optimizer"),
    ("gpu",       "GPU-Tuner",          "GPU Tuner"),
    ("stress",    "Stresstest",         "Stress Test"),
    ("compare",   "Profilvergleich",    "Compare"),
    ("bios",      "BIOS-Guide",         "BIOS Guide"),
    ("games",     "Spiele & Verlauf",   "Games & History"),
    ("diagnose",  "Diagnose",           "Diagnose"),
    ("startup",   "Autostart",          "Startup Apps"),
    ("services",  "Dienste",            "Services"),
    ("settings",  "Einstellungen",      "Settings"),
]
TAB_COLORS = dict(PAGE_COLORS, startup=ACC, services=AMBER)
PREBUILD = ("optimizer", "gpu")          # built in the background after start-up


def _short_gpu(name: str) -> str:
    for p in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "AMD ", "Intel(R) "):
        if name.startswith(p):
            return name[len(p):]
    return name


def _short_cpu(name: str) -> str:
    out = name.replace("(R)", "").replace("(TM)", "").replace(" CPU", "")
    for cut in (" Processor", " with Radeon"):
        i = out.find(cut)
        if i > 0:
            out = out[:i]
    for w in (" 4-Core", " 6-Core", " 8-Core", " 12-Core", " 16-Core", " 24-Core", " 32-Core"):
        out = out.replace(w, "")
    return " ".join(out.split())


class GameOptimizerWindow(ctk.CTk):
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

        self._active_tab    = ""
        self._tab_frames:   dict[str, tk.Widget] = {}
        self._tab_btns:     dict[str, ctk.CTkButton] = {}
        self._tab_bars:     dict[str, tk.Frame] = {}
        self._geo_job       = None

        self._setup_window()
        self._build_layout()
        self._build_header()
        self._build_tab_bar()
        self._build_hw_bar()
        self._build_content()
        self._build_status_bar()
        self._show_tab("dashboard")
        self._start_updater()
        # v1: did a Windows update undo tweaks applied earlier? (after start-up)
        self.after(4000, self._start_drift_check)
        for i, key in enumerate(PREBUILD):
            self.after(1500 + 1500 * i, lambda k=key: self._ensure_page(k))

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.title(f"{APP_NAME} {APP_VERSION} — by FloDePin")
        icon = theme.app_icon_path()
        if icon:
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass
        theme.setup(self)
        self.minsize(1000, 700)
        self._restore_geometry()
        # A <Configure> binding on the window fires for EVERY widget inside it (the
        # toplevel is in each widget's bindtags): CustomTkinter's own size
        # bookkeeping plus the position saver ran ~2600 times per page layout —
        # about 0.4 s for the optimizer page, and again on every resize. A private
        # bindtag delivers only the window's own events.
        self.unbind("<Configure>")
        self.bindtags(("GOPWindowOnly",) + tuple(self.bindtags()))
        self.bind_class("GOPWindowOnly", "<Configure>", self._update_dimensions_event, add="+")
        self.bind_class("GOPWindowOnly", "<Configure>", self._on_configure, add="+")
        for i, (key, *_x) in enumerate(TAB_DEFS[:9], 1):
            self.bind(f"<Control-Key-{i}>", lambda e, k=key: self._show_tab(k))

    def _restore_geometry(self):
        """Last size/position — only if that spot is still on a connected monitor."""
        w, h, x, y = 1260, 860, None, None
        try:
            from core import app_settings
            g = app_settings.get("window") or {}
            w = max(1000, int(g.get("w", w)))
            h = max(700, int(g.get("h", h)))
            if "x" in g and "y" in g and self._on_screen(int(g["x"]) + 60, int(g["y"]) + 20):
                x, y = int(g["x"]), int(g["y"])
        except Exception:
            pass
        if x is None:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h = min(w, sw - 40), min(h, sh - 80)
            x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _on_screen(x: int, y: int) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT(x, y)
            return bool(ctypes.windll.user32.MonitorFromPoint(pt, 0))   # 0 = DEFAULTTONULL
        except Exception:
            return False

    def _on_configure(self, e):
        if e.widget is not self:
            return
        if self._geo_job is not None:
            try:
                self.after_cancel(self._geo_job)
            except tk.TclError:
                pass
        self._geo_job = self.after(1200, self._save_geometry)

    def _save_geometry(self):
        self._geo_job = None
        try:
            if self.state() != "normal":
                return
            from core import app_settings
            app_settings.set("window", {"w": self.winfo_width(), "h": self.winfo_height(),
                                        "x": self.winfo_x(), "y": self.winfo_y()})
        except Exception:
            pass

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar = tk.Frame(self, bg=SIDEBAR_BG, width=224)
        self._sidebar.grid(row=0, column=0, sticky="ns")
        self._sidebar.pack_propagate(False)
        tk.Frame(self, bg=BORDER, width=1).grid(row=0, column=0, sticky="nse")
        self._content = tk.Frame(self, bg=APP_BG)
        self._content.grid(row=0, column=1, sticky="nsew")

    # ── Sidebar: brand ────────────────────────────────────────────────────────

    def _build_header(self):
        brand = tk.Frame(self._sidebar, bg=SIDEBAR_BG)
        brand.pack(fill="x", padx=16, pady=(16, 12))
        self._brand = brand
        logo = ctk.CTkFrame(brand, width=36, height=36, corner_radius=10, fg_color=tint(RED, SIDEBAR_BG, 0.22))
        logo.pack(side="left")
        logo.pack_propagate(False)
        theme.icon_label(logo, "bolt", ACC, 15, bg=tint(RED, SIDEBAR_BG, 0.22)).place(relx=0.5, rely=0.5, anchor="center")
        names = tk.Frame(brand, bg=SIDEBAR_BG)
        names.pack(side="left", padx=(9, 0))
        row = tk.Frame(names, bg=SIDEBAR_BG)
        row.pack(anchor="w")
        tk.Label(row, text="GameOptimizer", font=("Segoe UI Semibold", 11), fg=TEXT, bg=SIDEBAR_BG,
                 bd=0, padx=0).pack(side="left")
        tk.Label(row, text="Pro", font=("Segoe UI Semibold", 11), fg=RED, bg=SIDEBAR_BG,
                 bd=0, padx=0).pack(side="left")
        tk.Label(names, text=f"{APP_VERSION} · by FloDePin", font=F_XS, fg=DIM, bg=SIDEBAR_BG).pack(anchor="w")

    # ── Sidebar: navigation ───────────────────────────────────────────────────

    def _build_tab_bar(self):
        nav = tk.Frame(self._sidebar, bg=SIDEBAR_BG)
        nav.pack(fill="x", padx=(0, 12))
        self._nav = nav
        for key, de, en in TAB_DEFS:
            row = tk.Frame(nav, bg=SIDEBAR_BG)
            row.pack(fill="x", pady=1)
            bar = tk.Frame(row, bg=SIDEBAR_BG, width=3)
            bar.pack(side="left", fill="y", padx=(0, 9))
            btn = ctk.CTkButton(row, text=tr(de, en), anchor="w", height=34, corner_radius=9,
                                image=icon_image(key, DIM, 18), compound="left",
                                fg_color="transparent", hover_color=HOVER, text_color=TEXT2,
                                font=ctk_font(13), command=lambda k=key: self._show_tab(k))
            btn.pack(side="left", fill="x", expand=True)
            self._tab_btns[key] = btn
            self._tab_bars[key] = bar

    def _style_nav(self):
        for key, btn in self._tab_btns.items():
            color = TAB_COLORS.get(key, ACC)
            active = key == self._active_tab
            btn.configure(fg_color=tint(color, SIDEBAR_BG, 0.16) if active else "transparent",
                          text_color=WHITE if active else TEXT2,
                          image=icon_image(key, color if active else DIM, 18),
                          font=ctk_font(13, "bold" if active else "normal"))
            self._tab_bars[key].configure(bg=color if active else SIDEBAR_BG)

    # ── Sidebar: system + indicators ─────────────────────────────────────────

    def _build_hw_bar(self):
        foot = tk.Frame(self._sidebar, bg=SIDEBAR_BG)
        foot.pack(side="bottom", fill="x", padx=14, pady=(8, 12))
        self._foot = foot

        card = ctk.CTkFrame(foot, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=BORDER)
        card.pack(fill="x")
        self._hw_card = card
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="x", padx=12, pady=10)
        tk.Label(inner, text=tr("SYSTEM", "SYSTEM"), font=("Segoe UI Semibold", 7), fg=MUTED,
                 bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        hw = self.hw
        vram = round(hw.gpu_vram_mb / 1024) if hw.gpu_vram_mb >= 512 else 0
        lines = [
            (_short_gpu(hw.gpu_name) + (f" · {vram} GB" if vram else ""), TEXT),
            (_short_cpu(hw.cpu_name), TEXT2),
            (f"{hw.ram_total_gb:.0f} GB {hw.ram_type or 'RAM'}"
             + (" · NVMe" if hw.has_nvme else ""), TEXT2),
            (f"{'Windows 11' if hw.is_win11 else 'Windows 10' if hw.is_win10 else 'Windows'}"
             f" · Build {hw.os_build}", DIM),
        ]
        for text, col in lines:
            WrapLabel(inner, text=text, font=F_XS, fg=col, bg=CARD_BG, pad=2).pack(fill="x")

        ind = tk.Frame(foot, bg=SIDEBAR_BG)
        ind.pack(fill="x", pady=(10, 0))
        self._hw_ind = ind
        self.lbl_ab   = tk.Label(ind, text="● AB",   font=F_XS, fg=DIM, bg=SIDEBAR_BG)
        self.lbl_nvml = tk.Label(ind, text="● NVML", font=F_XS, fg=DIM, bg=SIDEBAR_BG)
        self.lbl_mahm = tk.Label(ind, text="● MAHM", font=F_XS, fg=DIM, bg=SIDEBAR_BG)
        for w in (self.lbl_ab, self.lbl_nvml, self.lbl_mahm):
            w.pack(side="left", padx=(0, 8))

        bottom = tk.Frame(foot, bg=SIDEBAR_BG)
        bottom.pack(fill="x", pady=(8, 0))
        self.lbl_time = tk.Label(bottom, text="", font=F_MONO, fg=DIM, bg=SIDEBAR_BG)
        self.lbl_time.pack(side="left")
        from core.i18n import current_lang
        # Shows the language you can switch TO, so the action is clear
        self.btn_lang = ctk.CTkButton(bottom, text="DE" if current_lang() == "en" else "EN",
                                      image=icon_image("globe", TEXT2, 14), compound="left",
                                      width=64, height=26, corner_radius=8, font=ctk_font(12, "bold"),
                                      fg_color=CARD_BG, hover_color=HOVER, text_color=TEXT2,
                                      command=self._toggle_lang)
        self.btn_lang.pack(side="right")
        self._refresh_indicators()
        self._sidebar.bind("<Configure>", self._fit_sidebar, add="+")

    def _fit_sidebar(self, _e=None):
        """Hide the system card when the sidebar is too low for everything —
        otherwise the clock / language row at the bottom is cut off."""
        card = self._hw_card
        need = (self._brand.winfo_reqheight() + self._nav.winfo_reqheight()
                + self._foot.winfo_reqheight() + 16 + 12 + 8 + 12)
        if card.winfo_manager():
            if need > self._sidebar.winfo_height():
                card.pack_forget()
        elif need + card.winfo_reqheight() <= self._sidebar.winfo_height():
            card.pack(fill="x", before=self._hw_ind)

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _build_content(self):
        """Pages are created on first use (see _ensure_page)."""
        self._page_factories = {
            "dashboard": self._make_dashboard, "optimizer": self._make_optimizer,
            "gpu": self._make_gpu, "stress": self._make_stress, "compare": self._make_compare,
            "bios": self._make_bios, "games": self._make_games, "diagnose": self._make_diagnose,
            "startup": self._make_startup, "services": self._make_services,
            "settings": self._make_settings,
        }

    def _make_dashboard(self, parent):
        from ui.tab_dashboard import DashboardTab
        return DashboardTab(parent, self.hw, self.monitor)

    def _make_optimizer(self, parent):
        from ui.tab_optimizer import OptimizerTab
        return OptimizerTab(parent, self.runner, self.hw, profiles_dir=str(BASE / "profiles"),
                            logs_dir=str(BASE / "logs"))

    def _make_gpu(self, parent):
        from ui.tab_gpu import GpuTunerTab
        return GpuTunerTab(parent, self.monitor, self.ab, self.pm, self.tuner)

    def _make_stress(self, parent):
        from ui.tab_stress import StressTab
        return StressTab(parent, self.monitor)

    def _make_compare(self, parent):
        from ui.tab_compare import CompareTab
        return CompareTab(parent, self.pm)

    def _make_bios(self, parent):
        from ui.tab_bios import BiosGuideTab
        return BiosGuideTab(parent, self.hw)

    def _make_games(self, parent):
        from ui.tab_games import GamesTab
        return GamesTab(parent, self.game_monitor, self.pm, str(BASE / "logs"))

    def _make_diagnose(self, parent):
        from ui.tab_diagnose import DiagnoseTab
        return DiagnoseTab(parent)

    def _make_startup(self, parent):
        from ui.startup_manager import StartupManagerPage
        return StartupManagerPage(parent)

    def _make_services(self, parent):
        from ui.services_manager import ServicesManagerPage
        return ServicesManagerPage(parent)

    def _make_settings(self, parent):
        from ui.tab_settings import SettingsTab
        return SettingsTab(parent, self.ab, self.monitor, self.startup_loader)

    def _ensure_page(self, key: str):
        page = self._tab_frames.get(key)
        if page is not None:
            return page
        try:
            page = self._page_factories[key](self._content)
        except Exception:
            # A broken page must not take the whole window down.
            page = tk.Frame(self._content, bg=APP_BG)
            tk.Label(page, text=tr("Diese Seite konnte nicht geladen werden:",
                                   "This page could not be loaded:"),
                     font=("Segoe UI Semibold", 12), fg=ERR, bg=APP_BG).pack(anchor="w", padx=24, pady=(24, 6))
            WrapLabel(page, text=traceback.format_exc()[-1500:], font=F_MONO, fg=TEXT2,
                      bg=APP_BG).pack(fill="x", padx=24)
        self._tab_frames[key] = page
        return page

    def _show_tab(self, key: str):
        if key not in self._page_factories:
            return
        page = self._ensure_page(key)
        old = self._tab_frames.get(self._active_tab)
        if old is not None and old is not page:
            old.pack_forget()
            if hasattr(old, "on_hide"):
                try:
                    old.on_hide()
                except Exception:
                    pass
        self._active_tab = key
        page.pack(fill="both", expand=True)
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:
                pass
        self._style_nav()

    # ── Status bar ────────────────────────────────────────────────────────────

    def set_status(self, text: str):
        try:
            self.lbl_status.config(text=text)
        except Exception:
            pass

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=HEADER_BG, height=32)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=BORDER, height=1).pack(side="top", fill="x")
        try:
            import ctypes
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            admin = False
        tk.Label(bar, text=("● Admin" if admin else tr("● Ohne Admin-Rechte", "● Not elevated")),
                 font=F_XS, fg=GREEN if admin else AMBER, bg=HEADER_BG).pack(side="left", padx=(14, 10))
        ctk.CTkButton(bar, text=tr("Log-Ordner", "Log folder"), image=icon_image("folder", TEXT2, 14),
                      compound="left", height=24, width=0, corner_radius=7, font=ctk_font(12),
                      fg_color="transparent", hover_color=HOVER, text_color=TEXT2,
                      command=self._open_log).pack(side="right", padx=(0, 10), pady=3)
        self.lbl_status = tk.Label(
            bar, text=tr("Bereit.", "Ready."), font=F_S, fg=DIM, bg=HEADER_BG, anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True)

    # ── Drift check (v1: baseline) ────────────────────────────────────────────

    def _start_drift_check(self):
        """Tweaks the app applied that are not (fully) active any more — e.g.
        reset by a Windows feature update, or a newer tweak version sets more
        than the one applied back then. Needs admin to re-apply, so it only
        runs elevated; failed checks never count as drift."""
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                return
        except Exception:
            return
        applied = list(self.runner._applied.keys())
        if not applied:
            return

        def work():
            try:
                from core import optimization_score
                drifted, switched = optimization_score.check_applied(applied, self.hw)
            except Exception:
                drifted, switched = [], []
            try:
                if switched:
                    self.after(0, lambda: self._adopt_switched(switched))
                if drifted:
                    self.after(0, lambda: self._ask_drift(drifted))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _adopt_switched(self, switched: list):
        """Another choice of an either-or group is active (e.g. DNS changed by
        hand): take it over quietly instead of offering to switch it back."""
        from core.tweaks import get_by_id
        opt = self._tab_frames.get("optimizer")
        names = []
        for old, new in switched:
            self.runner.adopt(old, new)
            vars_ = getattr(opt, "_vars", {})
            if opt is not None:
                opt._bulk = True
            try:
                if old in vars_:
                    vars_[old].set(False)
                if new in vars_:
                    vars_[new].set(True)
            finally:
                if opt is not None:
                    opt._bulk = False
            t = get_by_id(new)
            names.append(t.name if t else new)
        self.set_status("Übernommen (aktuell aktive Wahl): " + ", ".join(names))

    def _ask_drift(self, drifted: list):
        """One decision per tweak (ticked = apply again, unticked = stop asking)."""
        from core.tweaks import get_by_id
        from core.tweak_i18n import tweak_name
        from core.i18n import current_lang
        from ui.drift_dialog import DriftDialog
        items = [(t.id, tweak_name(t, current_lang()))
                 for t in (get_by_id(i) for i in drifted) if t]
        if items:
            self._drift_dialog = DriftDialog(self, items, on_done=self._handle_drift)

    def _handle_drift(self, reapply: list, drop: list):
        from core.tweaks import get_by_id
        from core.tweak_i18n import tweak_name
        from core.i18n import current_lang
        opt = self._tab_frames.get("optimizer")
        if drop:
            for tid in drop:
                self.runner._applied.pop(tid, None)
            self.runner._save_state()
            for tid in drop:
                var = getattr(opt, "_vars", {}).get(tid)
                if var is not None:
                    var.set(False)
            self.set_status(f"{len(drop)} Tweak(s) als nicht angewendet markiert.")
        tweaks = [t for t in (get_by_id(i) for i in reapply) if t]
        if not tweaks:
            return
        self.set_status(f"Wende {len(tweaks)} Tweak(s) erneut an …")

        def work():
            self.runner.backup_registry("PreDriftReapply")
            failed, failed_ids = [], []
            for t in tweaks:
                ok, out = self.runner.apply(t)
                if not ok:
                    failed.append(f"{tweak_name(t, current_lang())}: {out[:160]}")
                    failed_ids.append(t.id)
            # A tweak that could not be applied is not in effect: stop tracking
            # it, otherwise this dialog asked again at every start.
            if failed_ids:
                for tid in failed_ids:
                    self.runner._applied.pop(tid, None)
                self.runner._save_state()
            n_ok = len(tweaks) - len(failed)

            def done():
                self.set_status(f"{n_ok}/{len(tweaks)} Tweak(s) erneut angewendet.")
                msg = f"{n_ok} von {len(tweaks)} Tweak(s) erneut angewendet."
                if any(t.requires_reboot for t in tweaks):
                    msg += "\nEinige wirken erst nach einem Neustart."
                if failed:
                    msg += ("\n\nFehlgeschlagen (als nicht angewendet markiert — keine "
                            "erneute Nachfrage):\n" + "\n".join(failed))
                    opt = self._tab_frames.get("optimizer")
                    for tid in failed_ids:
                        var = getattr(opt, "_vars", {}).get(tid)
                        if var is not None:
                            var.set(False)
                (messagebox.showwarning if failed else messagebox.showinfo)(
                    "GameOptimizerPro", msg, parent=self)
            try:
                self.after(0, done)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _open_startup_mgr(self):
        """Autostart entries (was a separate window, now a page)."""
        self._show_tab("startup")

    def _open_services(self):
        """Services manager (v1 parity) — a page, links to services.msc."""
        self._show_tab("services")

    def _open_log(self):
        import subprocess as sp
        log_dir = BASE / "logs"
        try:
            sp.Popen(["explorer.exe", str(log_dir)])
        except Exception as e:
            messagebox.showerror("Fehler", f"Log-Ordner konnte nicht geöffnet werden:\n{e}")

    # ── Updater ───────────────────────────────────────────────────────────────

    def _refresh_indicators(self):
        def put(lbl, name, ok, bad_col):
            lbl.config(text=f"● {name}", fg=GREEN if ok else bad_col)
        put(self.lbl_ab, "AB", self.ab.available, ERR)
        put(self.lbl_nvml, "NVML", self.monitor.nvml.available, AMBER)
        put(self.lbl_mahm, "MAHM", self.monitor.mahm.available, AMBER)

    def _start_updater(self):
        # Runs entirely on the main thread. Tk is not thread-safe, and after()
        # from a worker thread raises "main thread is not in main loop" on
        # Python 3.14 when it fires before mainloop() has started — which is
        # exactly when a thread launched from __init__ does. A self-rescheduling
        # after() avoids threads.
        def tick():
            try:
                self.lbl_time.config(text=datetime.now().strftime("%H:%M:%S"))
                self._refresh_indicators()
            except tk.TclError:
                return   # window destroyed → stop the poller cleanly
            self._tick_id = self.after(5000, tick)
        self._tick_id = self.after(1000, tick)

    def _toggle_lang(self):
        """
        Switch language and restart the app so every label is rebuilt cleanly.
        The new language is saved to disk and loaded on the next start.
        """
        from core.i18n import current_lang, set_lang

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

        # A running Auto-Tune must not be killed mid-step by os._exit below —
        # that left the GPU on an untested overclock. Reset to stock first.
        try:
            if self.tuner.is_running:
                self.tuner.abort()
        except Exception:
            pass

        # Close cleanly, then relaunch a fresh instance
        try:
            self.monitor.close()
        except Exception:
            pass

        import os
        import subprocess
        try:
            from core.app_launch import gui_python      # pythonw: no console window
            subprocess.Popen([gui_python(), str(BASE / "GameOptimizerPro.py")], cwd=str(BASE))
        except Exception:
            pass
        os._exit(0)

    def destroy(self):
        for attr in ("_tick_id", "_geo_job"):
            try:
                if getattr(self, attr, None):
                    self.after_cancel(getattr(self, attr))
            except Exception:
                pass
            setattr(self, attr, None)
        for page in list(self._tab_frames.values()):
            if hasattr(page, "stop"):
                try:
                    page.stop()
                except Exception:
                    pass
        super().destroy()

    def on_close(self):
        self.monitor.close()
        self.destroy()


# Backward compatibility alias
GameOptimizerProWindow = GameOptimizerWindow
