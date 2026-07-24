"""GameOptimizerPro Dashboard Tab — Hardware overview + live GPU stats."""

import tkinter as tk
from tkinter import ttk
import threading, time
from typing import Optional

from ui.widgets import *
from core.hardware import HardwareInfo
from core import network_test


class DashboardTab(tk.Frame):
    def __init__(self, parent, hw: HardwareInfo, monitor, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self.hw = hw
        self.monitor = monitor
        self._running = True
        self._build()
        self._start_live()

    def _build(self):
        # Title
        hdr = tk.Frame(self, bg=BG1)
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(hdr, text="System Overview", font=FT, fg=WHT, bg=BG1).pack(side="left")

        # Hardware cards
        cards = tk.Frame(self, bg=BG1)
        cards.pack(fill="x", padx=14, pady=(0, 8))
        cards.columnconfigure((0, 1, 2, 3), weight=1)

        hw_items = [
            ("🖥  CPU",   self.hw.cpu_name,
             f"{self.hw.cpu_cores}c/{self.hw.cpu_threads}t  {self.hw.cpu_freq_mhz}MHz  {self.hw.cpu_vendor}"),
            ("🎮  GPU",   self.hw.gpu_name,
             f"{self.hw.gpu_vendor}  {self.hw.gpu_vram_mb // 1024 if self.hw.gpu_vram_mb >= 512 else self.hw.gpu_vram_mb}{'GB' if self.hw.gpu_vram_mb >= 512 else 'MB'} VRAM"),
            ("🔵  RAM",   f"{self.hw.ram_total_gb:.0f} GB {self.hw.ram_type}",
             f"{self.hw.ram_slots_used} slots  {self.hw.ram_speed_mhz} MHz"),
            ("🔧  Board", f"{self.hw.mb_manufacturer}",
             f"{self.hw.mb_product}"),
        ]
        for i, (icon_label, main, sub) in enumerate(hw_items):
            f = tk.Frame(cards, bg=BG2, padx=10, pady=10)
            f.grid(row=0, column=i, padx=4, sticky="nsew")
            tk.Label(f, text=icon_label, font=("Segoe UI", 8, "bold"),
                     fg=ACC, bg=BG2).pack(anchor="w")
            tk.Label(f, text=main[:32], font=("Segoe UI", 9, "bold"),
                     fg=WHT, bg=BG2, wraplength=160, justify="left"
                     ).pack(anchor="w", pady=(2, 0))
            tk.Label(f, text=sub, font=FM, fg=DIM, bg=BG2, wraplength=160,
                     justify="left").pack(anchor="w")

        # OS + summary
        os_f = tk.Frame(self, bg=BG2)
        os_f.pack(fill="x", padx=14, pady=(0, 10))
        os_label = (
            f"OS: {self.hw.os_name}  (Build {self.hw.os_build})"
            f"  |  NVMe: {'Yes (' + str(self.hw.nvme_count) + 'x)' if self.hw.has_nvme else 'No'}"
            f"  |  {'Windows 11' if self.hw.is_win11 else 'Windows 10' if self.hw.is_win10 else 'Windows'}"
        )
        tk.Label(os_f, text=os_label, font=FM, fg=DIM, bg=BG2,
                 anchor="w", padx=10, pady=6).pack(fill="x")

        # Live GPU stats section
        SecHdr(self, "Live GPU Telemetry").pack(fill="x", padx=14, pady=(6, 4))

        # Voltage hero
        volt_row = tk.Frame(self, bg=BG1)
        volt_row.pack(fill="x", padx=14, pady=(0, 6))

        vbox = tk.Frame(volt_row, bg=BG2, padx=20, pady=12)
        vbox.pack(side="left", padx=(0, 8))
        tk.Label(vbox, text="CORE VOLTAGE", font=("Segoe UI", 8, "bold"),
                 fg=DIM, bg=BG2).pack()
        self.lbl_volt = tk.Label(vbox, text="-- mV", font=("Consolas", 22, "bold"),
                                 fg=VOLT, bg=BG2)
        self.lbl_volt.pack()
        self.lbl_volt_src = tk.Label(vbox, text="via MAHM", font=FM, fg=DIM, bg=BG2)
        self.lbl_volt_src.pack()

        # Live tiles
        tiles_f = tk.Frame(volt_row, bg=BG1)
        tiles_f.pack(side="left", fill="x", expand=True)
        tiles_f.columnconfigure((0, 1, 2, 3, 5), weight=1)

        self._tiles = {}
        tile_defs = [
            ("temp",    "Temp",     "°C",  ERR),
            ("core",    "Core",     "MHz", ACC),
            ("mem_clk", "Memory",   "MHz", ACC),
            ("power",   "Power",    "W",   WRN),
            ("usage",   "GPU Load", "%",   OK),
        ]
        for i, (key, label, unit, color) in enumerate(tile_defs):
            f, vl = mk_tile(tiles_f, label, "--", color, unit)
            f.grid(row=0, column=i, padx=3, sticky="nsew")
            self._tiles[key] = vl

        # Gauge bars
        bar_f = tk.Frame(self, bg=BG1)
        bar_f.pack(fill="x", padx=14, pady=4)

        self.bar_temp  = HBar(bar_f, "Temperature", "°C", ERR)
        self.bar_fan   = HBar(bar_f, "Fan Speed",   "%",  ACC2)
        self.bar_power = HBar(bar_f, "Power Draw",  "W",  WRN)
        self.bar_core  = HBar(bar_f, "Core Clock",  "MHz",ACC)
        self.bar_vram  = HBar(bar_f, "VRAM Used",   "MB", ACC2)
        for b in (self.bar_temp, self.bar_fan, self.bar_power,
                  self.bar_core, self.bar_vram):
            b.pack(fill="x", padx=4, pady=2)

        # Throttle
        thr = tk.Frame(bar_f, bg=BG1)
        thr.pack(fill="x", padx=8, pady=(4, 2))
        tk.Label(thr, text="Throttle:", font=FL, fg=DIM, bg=BG1).pack(side="left")
        self.lbl_throttle = tk.Label(thr, text="None", font=FM, fg=OK, bg=BG1)
        self.lbl_throttle.pack(side="left", padx=8)

        # ── Network latency test ────────────────────────────────────────────
        SecHdr(self, "Network Latency Test").pack(fill="x", padx=14, pady=(10, 4))
        net_f = tk.Frame(self, bg=BG1)
        net_f.pack(fill="x", padx=14, pady=(0, 10))

        top = tk.Frame(net_f, bg=BG1)
        top.pack(fill="x")
        self.btn_nettest = tk.Button(
            top, text="▶  Test starten", font=("Segoe UI", 9, "bold"),
            bg=ACC, fg="#04121a", activebackground="#33e0ff", relief="flat",
            padx=14, pady=4, cursor="hand2", command=self._run_nettest)
        self.btn_nettest.pack(side="left")
        self.lbl_nettest_hint = tk.Label(
            top, text="Ping zu Gateway, Cloudflare (1.1.1.1) und Google (8.8.8.8)",
            font=FM, fg=DIM, bg=BG1)
        self.lbl_nettest_hint.pack(side="left", padx=10)

        self._net_rows = tk.Frame(net_f, bg=BG1)
        self._net_rows.pack(fill="x", pady=(6, 0))
        self._net_labels = {}
        for key in ("Gateway (Router)", "Cloudflare", "Google DNS"):
            row = tk.Frame(self._net_rows, bg=BG2)
            row.pack(fill="x", pady=2)
            name = tk.Label(row, text=key, font=FL, fg=WHT, bg=BG2,
                            width=18, anchor="w", padx=10, pady=4)
            name.pack(side="left")
            val = tk.Label(row, text="—", font=FM, fg=DIM, bg=BG2, anchor="w")
            val.pack(side="left", fill="x", expand=True)
            self._net_labels[key] = val

    def _run_nettest(self):
        self.btn_nettest.config(state="disabled", text="⏳  Läuft…")
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
        colmap = {"excellent": OK, "good": OK, "ok": WRN, "poor": ERR, "unknown": DIM}
        for r in results:
            lbl = self._net_labels.get(r.label)
            if not lbl:
                continue
            if r.reachable:
                rating = network_test.rate_latency(r.avg_ms)
                lbl.config(
                    text=(f"{r.avg_ms:.0f} ms  Ø   "
                          f"(min {r.min_ms:.0f} / max {r.max_ms:.0f})   "
                          f"Jitter {r.jitter_ms:.0f} ms   "
                          f"Verlust {r.loss_pct:.0f}%   [{r.host}]"),
                    fg=colmap.get(rating, DIM))
            else:
                lbl.config(text=f"nicht erreichbar — {r.error}   [{r.host}]", fg=ERR)
        self.btn_nettest.config(state="normal", text="▶  Test starten")

    def _start_live(self):
        def loop():
            while self._running:
                try:
                    s = self.monitor.read()
                    self.after(0, self._update, s)
                except: pass
                time.sleep(1.0)
        threading.Thread(target=loop, daemon=True).start()

    def _update(self, s):
        # Voltage
        if s.voltage_mv > 0:
            self.lbl_volt.config(text=f"{s.voltage_mv:.0f} mV", fg=VOLT)
            self.lbl_volt_src.config(text="via MAHM", fg=DIM)
        else:
            self.lbl_volt.config(text="-- mV", fg=DIM)
            self.lbl_volt_src.config(
                text="Enable 'Unlock voltage monitoring' in AB", fg=WRN)

        # Tiles
        tc = ERR if s.temp >= 80 else WRN if s.temp >= 70 else ACC
        self._tiles["temp"].config(text=str(s.temp), fg=tc)
        self._tiles["core"].config(   text=f"{s.core_mhz:.0f}")
        self._tiles["mem_clk"].config( text=f"{s.mem_mhz:.0f}")
        self._tiles["power"].config(  text=f"{s.gpu_power_w:.0f}")
        self._tiles["usage"].config(  text=f"{s.gpu_usage:.0f}")

        # Bars
        self.bar_temp.set( s.temp,        s.temp_limit_c or 100)
        self.bar_fan.set(  s.fan_pct,     100)
        self.bar_power.set(s.gpu_power_w, s.power_max_w or 400)
        self.bar_core.set( s.core_mhz,    3000)
        # Use NVML vram_total if WMI returned wrong value
        vram_max = s.vram_total_mb if s.vram_total_mb > 100 else max(self.hw.gpu_vram_mb, 1)
        self.bar_vram.set(s.vram_used_mb, max(vram_max, 1))

        # Throttle
        if s.throttle and s.throttle != "None":
            self.lbl_throttle.config(text=s.throttle, fg=WRN)
        else:
            self.lbl_throttle.config(text="None", fg=OK)

    def stop(self):
        self._running = False
