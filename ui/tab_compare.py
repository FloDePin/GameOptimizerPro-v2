"""
GameOptimizerPro v2.0 — Profile comparison page (up to 4 GPU profiles side by side)
"""

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from core.nvtune_core import ProfileManager, TuneProfile
from ui.components import Card, GaugeBar, Page, ResponsiveGrid, Table, button
from ui.theme import ACC, AMBER, CARD_BG, DIM, F_BB, F_XS, GREEN, TEXT2, VIOLET, icon_image, tr

COMPARE_COLORS = [ACC, VIOLET, GREEN, AMBER]
NONE = tr("(keins)", "(none)")


class CompareTab(Page):
    def __init__(self, parent, pm: ProfileManager, **kw):
        super().__init__(parent, tr("Profilvergleich", "Profile comparison"),
                         tr("Bis zu 4 GPU-Profile nebeneinander vergleichen",
                            "Compare up to 4 GPU profiles side by side"),
                         color=VIOLET, **kw)
        self.pm = pm
        self._selected: list[Optional[TuneProfile]] = [None, None, None, None]
        self._build()

    def _build(self):
        b = self.body
        button(self.actions, tr("Aktualisieren", "Refresh"), self._refresh_list, kind="ghost",
               image=icon_image("refresh", TEXT2, 14), compound="left", height=30).pack(side="right")

        sel = Card(b, tr("Auswahl", "Selection"), accent=VIOLET)
        sel.pack(fill="x", padx=10, pady=(0, 14))
        grid = ResponsiveGrid(sel.body, min_width=170, max_cols=4, gap=10, bg=CARD_BG)
        grid.pack(fill="x")
        self._sel_vars: list[tk.StringVar] = []
        self._combos: list[ctk.CTkOptionMenu] = []
        for i in range(4):
            cell = tk.Frame(grid, bg=CARD_BG)
            tk.Label(cell, text=f"● {tr('Profil', 'Profile')} {i + 1}", font=F_BB,
                     fg=COMPARE_COLORS[i], bg=CARD_BG).pack(anchor="w", pady=(0, 4))
            v = tk.StringVar(value=NONE)
            om = ctk.CTkOptionMenu(cell, variable=v, values=[NONE], height=30, dynamic_resizing=False,
                                   command=lambda _v, idx=i: self._on_select(idx))
            om.pack(fill="x")
            self._sel_vars.append(v)
            self._combos.append(om)
            grid.add(cell)

        met = Card(b, tr("Kennzahlen", "Metrics"), accent=VIOLET)
        met.pack(fill="x", padx=10, pady=(0, 14))
        self._metric_rows: dict[str, "MetricRow"] = {}
        for label, key in [
            ("Core +MHz",   "core"),
            ("Mem +MHz",    "mem"),
            (tr("Power-Ersparnis %", "Power saved %"), "pwr"),
            (tr("Ø Spannung mV", "Avg volt mV"), "volt"),
            ("Score /100",  "score"),
        ]:
            row = MetricRow(met.body, label)
            row.pack(fill="x", pady=(0, 8))
            self._metric_rows[key] = row

        det = Card(b, tr("Alle Details", "Full details"), accent=VIOLET)
        det.pack(fill="x", padx=10, pady=(0, 10))
        cols = [("metric", tr("Wert", "Metric"), 130, "w")] + \
               [(f"p{i + 1}", f"● {tr('Profil', 'Profile')} {i + 1}", 150, "center") for i in range(4)]
        tbl = Table(det.body, cols, height=9, selectmode="none")
        tbl.pack(fill="x")
        self.detail_tree = tbl.tree
        self._refresh_list()

    def _refresh_list(self):
        profiles = [p for p in self.pm.list_all() if not p.name.startswith("__")]
        names    = [NONE] + [p.name for p in profiles]
        for i, (om, v) in enumerate(zip(self._combos, self._sel_vars)):
            current = v.get()
            om.configure(values=names)
            v.set(current if current in names else NONE)
            self._selected[i] = self.pm.load(v.get()) if v.get() != NONE else None
        self._update_comparison()

    def _on_select(self, idx: int):
        name = self._sel_vars[idx].get()
        self._selected[idx] = self.pm.load(name) if name != NONE else None
        self._update_comparison()

    def _update_comparison(self):
        active = [(i, p) for i, p in enumerate(self._selected) if p is not None]
        for row in self.detail_tree.get_children():
            self.detail_tree.delete(row)
        if not active:
            for r in self._metric_rows.values():
                r.set_values([])
            return

        def mx(attr): return max((getattr(p, attr, 0) or 0 for _, p in active), default=1) or 1

        def bar_vals(attr, max_val):
            return [(p.name, getattr(p, attr, 0) or 0, max_val, COMPARE_COLORS[i]) for i, p in active]

        self._metric_rows["core"].set_values(bar_vals("core_offset_mhz", mx("core_offset_mhz")))
        self._metric_rows["mem"].set_values(bar_vals("mem_offset_mhz", mx("mem_offset_mhz")))
        self._metric_rows["volt"].set_values(bar_vals("stage1_voltage", mx("stage1_voltage")))
        self._metric_rows["score"].set_values(bar_vals("stability_score", 100))
        # Power: lower limit = more saved
        self._metric_rows["pwr"].set_values(
            [(p.name, 100 - (p.power_limit_pct or 100), 50, COMPARE_COLORS[i]) for i, p in active])

        def fmt(p, attr, suf=""):
            v = getattr(p, attr, None)
            return f"{v}{suf}" if v else "--"

        row_defs = [
            ("Name",        lambda p: p.name[:22]),
            ("Core Offset", lambda p: fmt(p, "core_offset_mhz", " MHz")),
            ("Mem Offset",  lambda p: fmt(p, "mem_offset_mhz",  " MHz")),
            ("Power Limit", lambda p: fmt(p, "power_limit_pct", "%")),
            ("Avg Voltage", lambda p: fmt(p, "stage1_voltage",  " mV")),
            ("Score",       lambda p: fmt(p, "stability_score", "/100")),
            ("Stable",      lambda p: "✓" if p.is_stable else "⚠"),
            ("GPU",         lambda p: (p.gpu_name or "")[:24]),
            ("Created",     lambda p: (p.created_at or "")[:16]),
        ]
        for label, fn in row_defs:
            cells = [label] + [fn(self._selected[i]) if self._selected[i] else "" for i in range(4)]
            self.detail_tree.insert("", "end", values=cells)


class MetricRow(tk.Frame):
    """One metric: a coloured bar per selected profile."""

    def __init__(self, parent, label, **kw):
        super().__init__(parent, bg=CARD_BG, **kw)
        tk.Label(self, text=label, font=F_BB, fg=TEXT2, bg=CARD_BG, anchor="w").pack(fill="x")
        self._bars = tk.Frame(self, bg=CARD_BG)
        self._bars.pack(fill="x")
        self._empty = tk.Label(self._bars, text=tr("— kein Profil gewählt", "— no profile selected"),
                               font=F_XS, fg=DIM, bg=CARD_BG, anchor="w")
        self._empty.pack(fill="x")

    def set_values(self, values: list[tuple[str, float, float, str]]):
        for w in self._bars.winfo_children():
            if w is not self._empty:
                w.destroy()
        if not values:
            self._empty.pack(fill="x")
            return
        self._empty.pack_forget()
        for label, val, max_val, color in values:
            g = GaugeBar(self._bars, label[:16], "", color)
            g.pack(fill="x")
            g.set(val, max_val, fmt=f"{val:.0f}")
