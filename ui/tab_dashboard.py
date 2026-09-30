"""GameOptimizerPro Dashboard — hardware overview, optimisation score, live GPU
and system values, network latency test."""

import os
import threading
import time
import tkinter as tk

import customtkinter as ctk

from core import network_test
from core.hardware import HardwareInfo
from ui.components import Card, GaugeBar, Page, ResponsiveGrid, WrapLabel, button, tile
from ui.theme import (ACC, AMBER, BLUE, CARD_BG, CARD_BG2, CYAN, DIM, ERR, F_BB, F_MONO, F_S,
                      F_XS, GREEN, PURPLE, RED, TEXT, TEXT2, VIOLET, icon_label, tr)

VOLT = VIOLET


class DashboardTab(Page):
    def __init__(self, parent, hw: HardwareInfo, monitor, **kw):
        super().__init__(parent, "Dashboard",
                         tr("Systemübersicht, Optimierungs-Score und Live-Werte",
                            "System overview, optimisation score and live values"),
                         color=RED, **kw)
        self.hw = hw
        self.monitor = monitor
        self._running = True
        self._visible = True
        self._build()
        self._start_live()

    def on_show(self):
        self._visible = True

    def on_hide(self):
        self._visible = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        b = self.body
        pad = dict(fill="x", padx=10, pady=(0, 14))

        # Hardware cards
        hw = self.hw
        vram = (f"{round(hw.gpu_vram_mb / 1024)} GB" if hw.gpu_vram_mb >= 512 else f"{hw.gpu_vram_mb} MB")
        grid = ResponsiveGrid(b, min_width=250, max_cols=4, gap=12)
        grid.pack(**pad)
        for icon, color, title, main, sub in (
            ("chip", CYAN, "CPU", hw.cpu_name,
             f"{hw.cpu_cores} Kerne / {hw.cpu_threads} Threads · {hw.cpu_freq_mhz} MHz"),
            ("gpu", GREEN, "GPU", hw.gpu_name, f"{hw.gpu_vendor} · {vram} VRAM"),
            ("bios", VIOLET, "RAM", f"{hw.ram_total_gb:.0f} GB {hw.ram_type}",
             f"{hw.ram_slots_used} Module · {hw.ram_speed_mhz} MHz"),
            ("monitor", AMBER, "Board / OS", f"{hw.mb_manufacturer} {hw.mb_product}".strip() or "—",
             f"{'Windows 11' if hw.is_win11 else 'Windows 10' if hw.is_win10 else 'Windows'} · "
             f"Build {hw.os_build} · NVMe: {str(hw.nvme_count) + 'x' if hw.has_nvme else tr('nein', 'no')}"),
        ):
            card = ctk.CTkFrame(grid, fg_color=CARD_BG, corner_radius=12, border_width=1,
                                border_color="#242b36")
            inner = tk.Frame(card, bg=CARD_BG)
            inner.pack(fill="both", expand=True, padx=14, pady=12)
            head = tk.Frame(inner, bg=CARD_BG)
            head.pack(fill="x")
            icon_label(head, icon, color, 12, bg=CARD_BG).pack(side="left", padx=(0, 6))
            tk.Label(head, text=title, font=("Segoe UI Semibold", 8), fg=DIM, bg=CARD_BG).pack(side="left")
            WrapLabel(inner, text=main, font=F_BB, fg=TEXT, bg=CARD_BG).pack(fill="x", pady=(6, 2))
            WrapLabel(inner, text=sub, font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")
            grid.add(card)

        # Optimisation score + monitors (v1)
        sc = Card(b, tr("Optimierung & Monitor", "Optimisation & monitor"), accent=RED)
        sc.pack(**pad)
        self.btn_score = button(sc.actions, tr("Neu prüfen", "Check again"), self._refresh_score,
                                height=28)
        self.btn_score.pack(side="right")
        row = tk.Frame(sc.body, bg=CARD_BG)
        row.pack(fill="x")
        self.lbl_score = tk.Label(row, text=tr("wird geprüft …", "checking …"), font=F_BB, fg=DIM,
                                  bg=CARD_BG, anchor="w")
        self.lbl_score.pack(side="left", fill="x", expand=True)
        self.score_bar = ctk.CTkProgressBar(sc.body, height=8, corner_radius=4, progress_color=GREEN)
        self.score_bar.set(0)
        self.score_bar.pack(fill="x", pady=(8, 6))
        WrapLabel(sc.body, text=tr("Anteil der sicheren, auf diesem PC anwendbaren Tweaks, die laut "
                                   "Systemprüfung gerade aktiv sind (moderate/riskante zählen nicht).",
                                   "Share of the safe tweaks that fit this PC and are active right now "
                                   "according to the system check (moderate/risky ones don't count)."),
                  font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(0, 8))
        self._mon_rows = tk.Frame(sc.body, bg=CARD_BG)
        self._mon_rows.pack(fill="x")

        # Live GPU telemetry
        gpu = Card(b, tr("Live-GPU-Werte", "Live GPU telemetry"), accent=CYAN)
        gpu.pack(**pad)
        tiles = ResponsiveGrid(gpu.body, min_width=112, max_cols=6, gap=8, bg=CARD_BG)
        tiles.pack(fill="x")
        vf = ctk.CTkFrame(tiles, fg_color=CARD_BG2, corner_radius=10)
        vin = tk.Frame(vf, bg=CARD_BG2)
        vin.pack(fill="both", expand=True, padx=10, pady=8)
        tk.Label(vin, text=tr("Kernspannung", "Core voltage"), font=F_XS, fg=DIM, bg=CARD_BG2).pack()
        self.lbl_volt = tk.Label(vin, text="-- mV", font=("Consolas", 18, "bold"), fg=VOLT, bg=CARD_BG2)
        self.lbl_volt.pack()
        self.lbl_volt_src = tk.Label(vin, text="via MAHM", font=("Consolas", 8), fg=DIM, bg=CARD_BG2)
        self.lbl_volt_src.pack()
        tiles.add(vf)
        self._tiles = {}
        for key, label, unit, color in (
            ("temp",    tr("Temperatur", "Temp"), "°C",  ERR),
            ("core",    "Core",                   "MHz", ACC),
            ("mem_clk", tr("Speicher", "Memory"), "MHz", CYAN),
            ("power",   tr("Leistung", "Power"),  "W",   AMBER),
            ("usage",   tr("GPU-Last", "GPU load"), "%", GREEN),
        ):
            f, vl = tile(tiles, label, "--", color, unit)
            tiles.add(f)
            self._tiles[key] = vl

        bars = tk.Frame(gpu.body, bg=CARD_BG)
        bars.pack(fill="x", pady=(10, 0))
        self.bar_temp  = GaugeBar(bars, tr("Temperatur", "Temperature"), "°C", ERR)
        self.bar_fan   = GaugeBar(bars, tr("Lüfter", "Fan speed"), "%", CYAN)
        self.bar_power = GaugeBar(bars, tr("Leistung", "Power draw"), "W", AMBER)
        self.bar_core  = GaugeBar(bars, "Core Clock", "MHz", ACC)
        self.bar_vram  = GaugeBar(bars, tr("VRAM belegt", "VRAM used"), "MB", PURPLE)
        for bar in (self.bar_temp, self.bar_fan, self.bar_power, self.bar_core, self.bar_vram):
            bar.pack(fill="x", pady=1)
        thr = tk.Frame(gpu.body, bg=CARD_BG)
        thr.pack(fill="x", pady=(8, 0))
        tk.Label(thr, text="Throttle:", font=F_S, fg=DIM, bg=CARD_BG).pack(side="left")
        self.lbl_throttle = tk.Label(thr, text="None", font=F_MONO, fg=GREEN, bg=CARD_BG)
        self.lbl_throttle.pack(side="left", padx=8)

        # System + network side by side (stacked when narrow)
        duo = ResponsiveGrid(b, min_width=380, max_cols=2, gap=14)
        duo.pack(**pad)
        sysc = Card(duo, "System", accent=VIOLET)
        duo.add(sysc)
        st = ResponsiveGrid(sysc.body, min_width=90, max_cols=3, gap=8, bg=CARD_BG)
        st.pack(fill="x")
        self._sys_tiles = {}
        for key, label, color in (("cpu", "CPU", ACC), ("ram", "RAM", VIOLET), ("disk", tr("Laufwerk C:", "Disk C:"), AMBER)):
            f, vl = tile(st, label, "--", color, "%")
            st.add(f)
            self._sys_tiles[key] = vl

        net = Card(duo, tr("Netzwerk-Latenz", "Network latency"), accent=BLUE)
        duo.add(net)
        self.btn_nettest = button(net.actions, tr("Test starten", "Run test"), self._run_nettest,
                                  kind="primary", color=ACC, height=28)
        self.btn_nettest.pack(side="right")
        self.lbl_nettest_hint = WrapLabel(net.body, text=tr(
            "Ping zu Gateway, Cloudflare (1.1.1.1) und Google (8.8.8.8)",
            "Ping to the gateway, Cloudflare (1.1.1.1) and Google (8.8.8.8)"),
            font=F_XS, fg=DIM, bg=CARD_BG)
        self.lbl_nettest_hint.pack(fill="x", pady=(0, 6))
        self._net_rows = tk.Frame(net.body, bg=CARD_BG)
        self._net_rows.pack(fill="x")
        self._net_labels = {}
        for key in ("Gateway (Router)", "Cloudflare", "Google DNS"):
            r = ctk.CTkFrame(self._net_rows, fg_color=CARD_BG2, corner_radius=8)
            r.pack(fill="x", pady=2)
            inner = tk.Frame(r, bg=CARD_BG2)
            inner.pack(fill="x", padx=10, pady=5)
            tk.Label(inner, text=key, font=F_BB, fg=TEXT, bg=CARD_BG2, anchor="w").pack(fill="x")
            val = WrapLabel(inner, text="—", font=F_MONO, fg=DIM, bg=CARD_BG2)
            val.pack(fill="x")
            self._net_labels[key] = val

        self._refresh_monitors()          # instant (~40 ms)
        # The score runs ~5 s of PowerShell checks: start it after the UI is up.
        self.after(1500, lambda: self._refresh_score(monitors=False))

    # ── Score / monitor ───────────────────────────────────────────────────────

    def _refresh_score(self, monitors: bool = True):
        self.btn_score.configure(state="disabled")
        self.lbl_score.config(text=tr("wird geprüft …", "checking …"), fg=DIM)
        if monitors:                      # button: also re-read the refresh rates
            self._refresh_monitors()

        def work():
            pct = 0.0
            try:
                from core import optimization_score
                r = optimization_score.compute_score(self.hw)
                txt = f"{r.score} %   ·   {r.active}/{r.checkable} sichere Tweaks aktiv"
                txt += f", {r.unknown} nicht prüfbar" if r.unknown else ""
                col = GREEN if r.score >= 80 else (AMBER if r.score >= 50 else ERR)
                pct = r.score / 100
            except Exception as e:
                txt, col = f"Prüfung fehlgeschlagen: {e}", AMBER
            try:
                self.after(0, lambda: self._show_score(txt, col, pct))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _show_score(self, txt, col, pct):
        self.lbl_score.config(text=txt, fg=col)
        self.score_bar.configure(progress_color=col)
        self.score_bar.set(pct)
        self.btn_score.configure(state="normal")

    def _refresh_monitors(self):
        from core import display_info
        for w in self._mon_rows.winfo_children():
            w.destroy()
        try:
            shown = display_info.displays()
        except Exception:
            shown = []
        if not shown:
            tk.Label(self._mon_rows, text=tr("Monitor: Bildwiederholrate nicht ermittelbar",
                                             "Monitor: refresh rate unknown"),
                     font=F_S, fg=DIM, bg=CARD_BG, anchor="w").pack(fill="x")
        for n, d in enumerate(shown, 1):
            row = tk.Frame(self._mon_rows, bg=CARD_BG)
            row.pack(fill="x", pady=2)
            icon_label(row, "monitor", AMBER if d.below_max else ACC, 11, bg=CARD_BG).pack(side="left", padx=(0, 8), anchor="n")
            tk.Label(row, text=f"Monitor {n}{' (primär)' if d.primary else ''}", font=F_BB,
                     fg=TEXT, bg=CARD_BG, width=17, anchor="nw").pack(side="left", anchor="n")
            WrapLabel(row, text=d.advice(), font=F_S, fg=AMBER if d.below_max else TEXT2,
                      bg=CARD_BG).pack(side="left", fill="x", expand=True)

    # ── Network ───────────────────────────────────────────────────────────────

    def _run_nettest(self):
        self.btn_nettest.configure(state="disabled", text=tr("Läuft …", "Running …"))
        for lbl in self._net_labels.values():
            lbl.config(text="…", fg=DIM)

        def work():
            try:
                results = network_test.run_all(count=10)
            except Exception:
                results = []
            self.after(0, lambda: self._show_nettest(results))

        threading.Thread(target=work, daemon=True).start()

    def _show_nettest(self, results):
        colmap = {"excellent": GREEN, "good": GREEN, "ok": AMBER, "poor": ERR, "unknown": DIM}
        for r in results:
            lbl = self._net_labels.get(r.label)
            if not lbl:
                continue
            if r.reachable:
                rating = network_test.rate_latency(r.avg_ms)
                lbl.config(
                    text=(f"{r.avg_ms:.0f} ms Ø  (min {r.min_ms:.0f} / max {r.max_ms:.0f})  ·  "
                          f"Jitter {r.jitter_ms:.0f} ms  ·  Verlust {r.loss_pct:.0f}%  ·  {r.host}"),
                    fg=colmap.get(rating, DIM))
            else:
                lbl.config(text=f"nicht erreichbar — {r.error}  ·  {r.host}", fg=ERR)
        self.btn_nettest.configure(state="normal", text=tr("Test starten", "Run test"))

    # ── Live values ───────────────────────────────────────────────────────────

    def _start_live(self):
        try:
            import psutil
            psutil.cpu_percent()   # prime (first call returns 0.0)
            self._psutil = psutil
            self._sysdrive = (os.environ.get("SystemDrive", "C:") + "\\")
        except Exception:
            self._psutil = None

        def loop():
            while self._running:
                if not self._visible:            # hidden page: no sensor reads
                    time.sleep(0.5)
                    continue
                try:
                    s = self.monitor.read()
                    self.after(0, self._update, s)
                    if self._psutil:
                        cpu = self._psutil.cpu_percent()
                        ram = self._psutil.virtual_memory().percent
                        try:
                            disk = self._psutil.disk_usage(self._sysdrive).percent
                        except Exception:
                            disk = 0.0
                        self.after(0, self._update_sys, cpu, ram, disk)
                except Exception:
                    pass
                time.sleep(1.0)
        threading.Thread(target=loop, daemon=True).start()

    def _update_sys(self, cpu, ram, disk):
        if "cpu" not in self._sys_tiles:
            return
        self._sys_tiles["cpu"].config(text=f"{cpu:.0f}", fg=ERR if cpu >= 90 else AMBER if cpu >= 70 else ACC)
        self._sys_tiles["ram"].config(text=f"{ram:.0f}", fg=ERR if ram >= 90 else AMBER if ram >= 80 else VIOLET)
        self._sys_tiles["disk"].config(text=f"{disk:.0f}", fg=ERR if disk >= 95 else AMBER if disk >= 85 else GREEN)

    def _update(self, s):
        if s.voltage_mv > 0:
            self.lbl_volt.config(text=f"{s.voltage_mv:.0f} mV", fg=VOLT)
            self.lbl_volt_src.config(text="via MAHM", fg=DIM)
        else:
            self.lbl_volt.config(text="-- mV", fg=DIM)
            self.lbl_volt_src.config(text=tr("In AB 'Spannungsüberwachung' freischalten",
                                             "Enable 'Unlock voltage monitoring' in AB"), fg=AMBER)

        self._tiles["temp"].config(text=str(s.temp), fg=ERR if s.temp >= 80 else AMBER if s.temp >= 70 else ACC)
        self._tiles["core"].config(text=f"{s.core_mhz:.0f}")
        self._tiles["mem_clk"].config(text=f"{s.mem_mhz:.0f}")
        self._tiles["power"].config(text=f"{s.gpu_power_w:.0f}")
        self._tiles["usage"].config(text=f"{s.gpu_usage:.0f}")

        self.bar_temp.set(s.temp, s.temp_limit_c or 100)
        self.bar_fan.set(s.fan_pct, 100)
        self.bar_power.set(s.gpu_power_w, s.power_max_w or 400)
        self.bar_core.set(s.core_mhz, 3000)
        # Use NVML vram_total if WMI returned a wrong value
        vram_max = s.vram_total_mb if s.vram_total_mb > 100 else max(self.hw.gpu_vram_mb, 1)
        self.bar_vram.set(s.vram_used_mb, max(vram_max, 1))

        # Throttle — only thermal/hardware slowdowns are a warning; running into
        # the power limit under load is normal GPU Boost behaviour.
        if s.throttle and s.throttle != "None":
            self.lbl_throttle.config(text=s.throttle,
                                     fg=AMBER if getattr(s, "throttle_protective", True) else TEXT)
        else:
            self.lbl_throttle.config(text="None", fg=GREEN)

    def stop(self):
        self._running = False
