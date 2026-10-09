"""
GameOptimizerPro v2.0 — Profile comparison page (up to 4 GPU profiles side by side)

What tells profiles apart is how they do against stock in the same benchmark —
performance and efficiency (core/profile_score.py). The stability score is 100 for
every saved profile (a tune saves only what passed), so it is shown as "passed".
"""

import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from core.nvtune_core import ProfileManager, TuneProfile
from core.profile_score import score_of
from ui.components import Card, GaugeBar, Page, ResponsiveGrid, Table, button
from ui.theme import ACC, AMBER, CARD_BG, DIM, F_BB, F_XS, GREEN, TEXT2, VIOLET, icon_image, tr

COMPARE_COLORS = [ACC, VIOLET, GREEN, AMBER]
NONE = tr("(keins)", "(none)")
BEST = " ★"


def _pct(v: float) -> str:
    """+2.1 % (German: +2,1 %)."""
    from core.i18n import current_lang
    s = f"{v:+.1f} %"
    return s.replace(".", ",") if current_lang() == "de" else s


def describe_mode(p: TuneProfile) -> str:
    n, notes = p.name or "", p.notes or ""
    if "_sicher" in n or notes.startswith(("[Entschärft", "[Made safer")):
        return tr("Entschärfte Kopie", "Made-safer copy")
    if n.startswith("GOP_CURVE_") or notes.startswith(("[Rundum", "[All-round")):
        for tag, de, en in (("MAX", "Max", "Max"), ("BAL", "Ausgewogen", "Balanced"),
                            ("EFF", "Effizienz", "Efficiency")):
            if f"_{tag}_" in n or f" {de}]" in notes or f" {en}]" in notes:
                return tr(f"Rundum ({de})", f"All-round ({en})")
        return tr("Rundum", "All-round")
    if n.startswith("GOP_OC+UV") or notes.startswith("[OC+UV]"):
        return tr("Schnell (OC + UV)", "Quick (OC + UV)")
    if p.curve_points:
        return tr("Rundum", "All-round")
    return tr("Manuell", "Manual")


def describe_clock(p: TuneProfile) -> str:
    """'Kurve: 2879 MHz ab 1050 mV' (the top of an own curve, under its cap) or '+119 MHz'."""
    pts = [(int(mv), int(f)) for mv, f in (p.curve_points or []) if isinstance(mv, (int, float))]
    if pts:
        cap = int(p.curve_cap_mv or 0)
        under = [x for x in pts if not cap or x[0] <= cap] or pts
        mv, f = max(under)
        return tr(f"Kurve: {f} MHz ab {mv} mV", f"Curve: {f} MHz from {mv} mV")
    return f"{int(p.core_offset_mhz or 0):+d} MHz"


def _created(p: TuneProfile) -> str:
    try:
        return datetime.fromisoformat(p.created_at).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return (p.created_at or "")[:16]


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

        met = Card(b, tr("Gegenüber Standard (gleicher FurMark-Test)",
                         "Against stock (same FurMark test)"), accent=VIOLET)
        met.pack(fill="x", padx=10, pady=(0, 14))
        tk.Label(met.body, text=tr(
            "Leistung = Punkte gegenüber Standard, Effizienz = Punkte pro Watt gegenüber Standard. "
            "Profile ohne Messung: ein neuer Tune misst es (Rundum und Schnell mit FurMark 2).",
            "Performance = points vs stock, efficiency = points per watt vs stock. Profiles "
            "without a measurement: a new tune measures it (All-round and Quick with FurMark 2)."),
            font=F_XS, fg=DIM, bg=CARD_BG, anchor="w", justify="left", wraplength=900).pack(fill="x", pady=(0, 8))
        self._metric_rows: dict[str, "MetricRow"] = {}
        for label, key in [
            (tr("Leistung gegenüber Standard", "Performance vs stock"), "perf"),
            (tr("Effizienz gegenüber Standard (Punkte pro Watt)", "Efficiency vs stock (points per watt)"), "eff"),
            (tr("Leistungsaufnahme im Test (W)", "Power draw in the test (W)"), "watt"),
            (tr("Speicher-Plus (MHz)", "Memory gain (MHz)"), "mem"),
        ]:
            row = MetricRow(met.body, label)
            row.pack(fill="x", pady=(0, 8))
            self._metric_rows[key] = row

        det = Card(b, tr("Alle Details", "Full details"), accent=VIOLET)
        det.pack(fill="x", padx=10, pady=(0, 10))
        cols = [("metric", tr("Wert", "Metric"), 150, "w")] + \
               [(f"p{i + 1}", f"● {tr('Profil', 'Profile')} {i + 1}", 170, "center") for i in range(4)]
        tbl = Table(det.body, cols, height=12, selectmode="none")
        tbl.pack(fill="x")
        self.detail_tree = tbl.tree
        self._refresh_list()

    def on_show(self):
        """Every time the page is shown: profiles saved since (a tune that just
        finished, a rename, a delete) are in the lists — the page is built in
        the background at start and only read them then."""
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
        scores = {i: score_of(p) for i, p in active}
        unmeasured = tr("nicht gemessen", "not measured")

        def bars(key, fmt, higher_better=True):
            vals = [scores[i][key] for i, _p in active if scores[i]]
            lo = min(vals + [0.0]) - 1.0 if vals else 0.0
            hi = max(vals + [0.0]) if vals else 1.0
            out = []
            for i, p in active:
                s = scores[i]
                label = f"{tr('Profil', 'Profile')} {i + 1}"
                if s is None:
                    out.append((label, 0.0, 1.0, COMPARE_COLORS[i], unmeasured))
                else:
                    out.append((label, s[key] - lo, (hi - lo) or 1.0, COMPARE_COLORS[i], fmt(s[key])))
            return out

        self._metric_rows["perf"].set_values(bars("perf_pct", _pct))
        self._metric_rows["eff"].set_values(bars("eff_pct", _pct))
        watts = [(f"{tr('Profil', 'Profile')} {i + 1}",
                  float(scores[i]["power_w"]) if scores[i] else 0.0,
                  float(max((s["power_w"] for s in scores.values() if s), default=1) or 1),
                  COMPARE_COLORS[i],
                  (f"{scores[i]['power_w']} W" if scores[i] else unmeasured)) for i, _p in active]
        self._metric_rows["watt"].set_values(watts)
        mx_mem = max((p.mem_offset_mhz or 0 for _i, p in active), default=1) or 1
        self._metric_rows["mem"].set_values(
            [(f"{tr('Profil', 'Profile')} {i + 1}", float(p.mem_offset_mhz or 0), float(mx_mem), COMPARE_COLORS[i],
              f"+{int(p.mem_offset_mhz or 0)}") for i, p in active])

        def best(key):
            vals = {i: s[key] for i, s in scores.items() if s}
            return max(vals, key=vals.get) if len(vals) >= 2 else None
        b_perf, b_eff = best("perf_pct"), best("eff_pct")

        def cell_perf(i, p):
            s = scores.get(i)
            return (_pct(s["perf_pct"]) + (BEST if i == b_perf else "")) if s else unmeasured

        def cell_eff(i, p):
            s = scores.get(i)
            return (_pct(s["eff_pct"]) + (BEST if i == b_eff else "")) if s else unmeasured

        def cell_watt(i, p):
            s = scores.get(i)
            return (tr(f"{s['power_w']} W (Standard {s['stock_power_w']} W)",
                       f"{s['power_w']} W (stock {s['stock_power_w']} W)") if s else unmeasured)

        def cell_bench(i, p):
            s = scores.get(i)
            return s["label"] if s else "—"

        row_defs = [
            ("Name",                                         lambda i, p: p.name),
            (tr("Modus", "Mode"),                            lambda i, p: describe_mode(p)),
            (tr("Takt", "Clock"),                            lambda i, p: describe_clock(p)),
            (tr("Speicher", "Memory"),                       lambda i, p: f"+{int(p.mem_offset_mhz or 0)} MHz"),
            (tr("Power-Limit", "Power limit"),               lambda i, p: f"{int(p.power_limit_pct or 100)} %"),
            (tr("Leistung ggü. Standard", "Performance vs stock"), cell_perf),
            (tr("Effizienz ggü. Standard", "Efficiency vs stock"),  cell_eff),
            (tr("Leistungsaufnahme", "Power draw"),          cell_watt),
            (tr("Gemessen mit", "Measured with"),            cell_bench),
            (tr("Stabilitätstests", "Stability tests"),
             lambda i, p: tr("bestanden", "passed") if p.is_stable else tr("nicht bestanden", "not passed")),
            ("GPU",                                          lambda i, p: (p.gpu_name or "").replace("NVIDIA GeForce ", "")),
            (tr("Erstellt", "Created"),                      lambda i, p: _created(p)),
        ]
        for label, fn in row_defs:
            cells = [label] + [fn(i, self._selected[i]) if self._selected[i] else "" for i in range(4)]
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
        self.shown: list[str] = []          # the value texts (tests read them)

    def set_values(self, values: list[tuple]):
        """(label, value, max, color[, text]) per profile."""
        for w in self._bars.winfo_children():
            if w is not self._empty:
                w.destroy()
        self.shown = []
        if not values:
            self._empty.pack(fill="x")
            return
        self._empty.pack_forget()
        for item in values:
            label, val, max_val, color = item[:4]
            text = item[4] if len(item) > 4 else f"{val:.0f}"
            g = GaugeBar(self._bars, label[:16], "", color)
            g.pack(fill="x")
            g.set(val, max_val, fmt=text)
            self.shown.append(text)
