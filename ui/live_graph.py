"""
GameOptimizerPro Live Graph
Rolling canvas-based line chart for core clock, voltage and temperature
during tuning. No external deps — pure tkinter Canvas.
"""

import tkinter as tk
from collections import deque

from ui.theme import ACC, BORDER, CARD_BG, DIM, ERR, F_XS, INPUT_BG, MUTED, VIOLET, mix

VOLT = VIOLET
GRID = mix(INPUT_BG, "#ffffff", 0.06)


class LiveGraph(tk.Frame):
    """
    Rolling line graph.
    Series A = Core Clock (MHz, cyan)
    Series B = Voltage (mV, violet)
    Series C = Temperature (°C, red)
    """

    MAX_POINTS = 120   # 2 minutes at 1s resolution

    def __init__(self, parent, height=160, bg: str = CARD_BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._bg = bg

        # Data
        self._clocks   = deque(maxlen=self.MAX_POINTS)
        self._voltages = deque(maxlen=self.MAX_POINTS)
        self._temps    = deque(maxlen=self.MAX_POINTS)

        # Ranges (auto-scaled)
        self._clk_min  = 0
        self._clk_max  = 3000
        self._volt_min = 700
        self._volt_max = 1100
        self._temp_max = 100

        self._height = height
        self._build()

    def _build(self):
        bg = self._bg
        # Legend with the last values
        leg = tk.Frame(self, bg=bg)
        leg.pack(fill="x", pady=(0, 6))
        self.lbl_clk  = tk.Label(leg, text="● Clock -- MHz", font=F_XS, fg=ACC,  bg=bg)
        self.lbl_volt = tk.Label(leg, text="● Volt -- mV",   font=F_XS, fg=VOLT, bg=bg)
        self.lbl_temp = tk.Label(leg, text="● Temp -- °C",   font=F_XS, fg=ERR,  bg=bg)
        for w in (self.lbl_clk, self.lbl_volt, self.lbl_temp):
            w.pack(side="left", padx=(0, 14))

        self.cv = tk.Canvas(self, bg=INPUT_BG, height=self._height, width=100,
                            highlightthickness=1, highlightbackground=BORDER)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda e: self._redraw())

    def push(self, core_mhz: float, voltage_mv: float, temp: float):
        self._clocks.append(core_mhz)
        self._voltages.append(voltage_mv)
        self._temps.append(temp)

        # Auto-scale
        if self._clocks:
            self._clk_min  = max(0,   min(self._clocks)   - 50)
            self._clk_max  = max(100, max(self._clocks)   + 50)
        if self._voltages and max(self._voltages) > 0:
            self._volt_min = max(0,   min(v for v in self._voltages if v > 0) - 50)
            self._volt_max = max(100, max(self._voltages) + 50)

        self.lbl_clk.config( text=f"● Clock {core_mhz:.0f} MHz")
        self.lbl_volt.config(text=f"● Volt {voltage_mv:.0f} mV" if voltage_mv > 0 else "● Volt -- mV")
        self.lbl_temp.config(text=f"● Temp {temp:.0f} °C")
        self._redraw()

    def clear(self):
        self._clocks.clear()
        self._voltages.clear()
        self._temps.clear()
        self.cv.delete("all")
        self._redraw()

    def _redraw(self, *_):
        self.cv.delete("all")
        w = self.cv.winfo_width()
        h = self.cv.winfo_height()
        if w < 10 or h < 10:
            return

        pad_l, pad_r, pad_t, pad_b = 44, 10, 10, 10
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        for i in range(0, 5):
            y = pad_t + plot_h * i // 4
            self.cv.create_line(pad_l, y, w - pad_r, y, fill=GRID)

        n = len(self._clocks)
        if n < 2:
            self.cv.create_text(pad_l + plot_w / 2, pad_t + plot_h / 2,
                                text="Live-Werte erscheinen, sobald der Tune läuft",
                                font=F_XS, fill=MUTED)
            return

        def x_pos(i):
            return pad_l + plot_w * i / (self.MAX_POINTS - 1)

        def y_norm(val, lo, hi):
            if hi == lo:
                return pad_t + plot_h // 2
            frac = (val - lo) / (hi - lo)
            return h - pad_b - int(frac * plot_h)

        def draw_series(data, lo, hi, color):
            pts = list(data)
            if len(pts) < 2:
                return
            offset = self.MAX_POINTS - len(pts)
            coords = []
            for i, v in enumerate(pts):
                if v > 0:
                    coords.append(x_pos(i + offset))
                    coords.append(y_norm(v, lo, hi))
            if len(coords) >= 4:
                self.cv.create_line(*coords, fill=color, width=2, smooth=True)

        draw_series(self._temps,    0,              self._temp_max, ERR)
        draw_series(self._voltages, self._volt_min, self._volt_max, VOLT)
        draw_series(self._clocks,   self._clk_min,  self._clk_max,  ACC)

        # Y axis labels (clock)
        for val in (self._clk_max, self._clk_min):
            y = y_norm(val, self._clk_min, self._clk_max)
            self.cv.create_text(pad_l - 6, y, text=f"{val:.0f}", anchor="e",
                                font=("Consolas", 7), fill=DIM)
