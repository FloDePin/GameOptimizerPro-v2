"""
GameOptimizerPro v2.0 — Profile comparison page (up to 4 GPU profiles side by side)

What tells profiles apart is how they do against stock in the same benchmark —
performance and efficiency (core/profile_score.py). Stock is a column of its own (point 0:
the mean of the stock runs the chosen profiles were measured against — every tune measures
stock right before); ▲ / ▼ = better / worse than stock, ≈ within the run-to-run noise.
The stability score is 100 for every saved profile (a tune saves only what passed), so it
is shown as "passed". The curve chart shows the profiles' V/F curves against stock
(core/profile_curves.py; the stock curve is read from Afterburner's profile file).
"""

import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from core.nvtune_core import ProfileManager, TuneProfile
from core.profile_curves import flat_from, measured_points, profile_line, stock_line
from core.profile_score import score_of, stock_of
from ui.components import Card, GaugeBar, Page, ResponsiveGrid, Table, button
from ui.theme import (ACC, AMBER, CARD_BG, DIM, F_BB, F_S, F_SB, F_XS, GREEN, SLATE, TEXT2, VIOLET,
                      icon_image, mix, tr)

COMPARE_COLORS = [ACC, VIOLET, GREEN, AMBER]
NONE = tr("(keins)", "(none)")
BEST = " ★"
STOCK_COLOR = SLATE
# Two stock runs of the same card differ by about this much (FurMark 2, 60 s): closer to
# stock than that is "the same", not better or worse
NOISE_PCT = 0.7


def _pct(v: float) -> str:
    """+2.1 % (German: +2,1 %)."""
    from core.i18n import current_lang
    s = f"{v:+.1f} %"
    return s.replace(".", ",") if current_lang() == "de" else s


def _mark(v: float) -> str:
    """▲ better than stock, ▼ worse, ≈ within the noise."""
    return "▲" if v >= NOISE_PCT else "▼" if v <= -NOISE_PCT else "≈"


def _pct_mark(v: float) -> str:
    return f"{_pct(v)} {_mark(v)}"


def _dec(v: float) -> str:
    """28.76 (German: 28,76)."""
    from core.i18n import current_lang
    s = f"{v:.2f}"
    return s.replace(".", ",") if current_lang() == "de" else s


BASE = tr("0 % (Basis)", "0 % (base)")


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
    """'Kurve: 2879 MHz ab 1050 mV' (the top of an own curve, under its cap), '+134 MHz, flach
    ab 1075 mV' (a Quick profile, round 24) or '+119 MHz'."""
    pts = [(int(mv), int(f)) for mv, f in (p.curve_points or []) if isinstance(mv, (int, float))]
    if pts and (p.notes or "").startswith("[OC+UV]"):
        cap = int(p.curve_cap_mv or max(pts)[0])
        return tr(f"{int(p.core_offset_mhz or 0):+d} MHz, flach ab {cap} mV",
                  f"{int(p.core_offset_mhz or 0):+d} MHz, flat from {cap} mV")
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
    def __init__(self, parent, pm: ProfileManager, ab=None, **kw):
        super().__init__(parent, tr("Profilvergleich", "Profile comparison"),
                         tr("Bis zu 4 GPU-Profile nebeneinander vergleichen",
                            "Compare up to 4 GPU profiles side by side"),
                         color=VIOLET, **kw)
        self.pm = pm
        self.ab = ab
        self._base_curve = None             # the card's stock curve (read on every show)
        self._curve_note = ""
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
            "Standard = die Karte ab Werk (0 %). Jeder Tune misst sie direkt vorher im gleichen Test, "
            "jedes Profil wird mit seiner eigenen Messung verglichen; die Spalte Standard zeigt deren "
            "Durchschnitt. Leistung = Punkte, Effizienz = Punkte pro Watt. ▲ besser als Standard, "
            "▼ schlechter, ≈ gleich (innerhalb der Messschwankung von ±0,7 %). Profile ohne Messung: "
            "ein neuer Tune misst es (Rundum und Schnell mit FurMark 2).",
            "Stock = the card as it comes (0 %). Every tune measures it right before in the same test, "
            "every profile is compared with its own measurement; the stock column shows their mean. "
            "Performance = points, efficiency = points per watt. ▲ better than stock, ▼ worse, "
            "≈ the same (within the run-to-run noise of ±0.7 %). Profiles without a measurement: "
            "a new tune measures it (All-round and Quick with FurMark 2)."),
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

        cur = Card(b, tr("Kurven (wie im Kurven-Editor von Afterburner)",
                         "Curves (as in Afterburner's curve editor)"), accent=VIOLET)
        cur.pack(fill="x", padx=10, pady=(0, 14))
        tk.Label(cur.body, text=tr(
            "Takt je Spannung: Standard gestrichelt, jedes Profil in seiner Farbe — Rundum-Profile flach ab "
            "ihrer Obergrenze, die Punkte sind die gemessenen Spannungen; Schnell-Profile verschieben die "
            "ganze Kurve. Hell hinterlegt: wo die Karte unter Last läuft. Mit der Maus zeigen: die Takte bei "
            "dieser Spannung.",
            "Clock per voltage: stock dashed, every profile in its colour — All-round profiles flat from "
            "their cap, the dots are the measured voltages; Quick profiles shift the whole curve. Shaded: "
            "where the card runs under load. Point at it: the clocks at that voltage."),
            font=F_XS, fg=DIM, bg=CARD_BG, anchor="w", justify="left", wraplength=900).pack(fill="x", pady=(0, 6))
        self.curve_chart = CurveChart(cur.body, height=300)
        self.curve_chart.pack(fill="x")

        det = Card(b, tr("Alle Details", "Full details"), accent=VIOLET)
        det.pack(fill="x", padx=10, pady=(0, 10))
        cols = [("metric", tr("Wert", "Metric"), 150, "w"), ("stock", tr("Standard", "Stock"), 130, "center")] + \
               [(f"p{i + 1}", f"● {tr('Profil', 'Profile')} {i + 1}", 160, "center") for i in range(4)]
        tbl = Table(det.body, cols, height=13, selectmode="none")
        tbl.pack(fill="x")
        self.detail_tree = tbl.tree
        self._refresh_list()

    def on_show(self):
        """Every time the page is shown: profiles saved since (a tune that just
        finished, a rename, a delete) are in the lists — the page is built in
        the background at start and only read them then."""
        self._refresh_list()

    def _load_base_curve(self):
        """The card's stock V/F curve from Afterburner's profile file (read-only)."""
        self._base_curve, self._curve_note = None, ""
        getter = getattr(self.ab, "base_curve", None)
        if getter is None:
            self._curve_note = tr("Afterburner nicht gefunden — keine Kurve", "Afterburner not found — no curve")
            return
        try:
            curve, why = getter(2)
        except Exception as e:
            curve, why = None, str(e)
        if curve is None:
            self._curve_note = tr(f"Kurve nicht lesbar: {why}", f"Curve not readable: {why}")
        self._base_curve = curve

    def _refresh_list(self):
        self._load_base_curve()
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
        self._update_curves(active)
        if not active:
            for r in self._metric_rows.values():
                r.set_values([])
            return
        scores = {i: score_of(p) for i, p in active}
        stock = stock_of(scores.values())
        unmeasured = tr("nicht gemessen", "not measured")

        def bars(key, fmt, higher_better=True):
            vals = [scores[i][key] for i, _p in active if scores[i]]
            lo = min(vals + [0.0]) - 1.0 if vals else 0.0
            hi = max(vals + [0.0]) if vals else 1.0
            out = [(tr("Standard", "Stock"), 0.0 - lo, (hi - lo) or 1.0, STOCK_COLOR, BASE)]
            for i, p in active:
                s = scores[i]
                label = f"{tr('Profil', 'Profile')} {i + 1}"
                if s is None:
                    out.append((label, 0.0, 1.0, COMPARE_COLORS[i], unmeasured))
                else:
                    out.append((label, s[key] - lo, (hi - lo) or 1.0, COMPARE_COLORS[i], fmt(s[key])))
            return out

        self._metric_rows["perf"].set_values(bars("perf_pct", _pct_mark))
        self._metric_rows["eff"].set_values(bars("eff_pct", _pct_mark))
        mx_w = float(max([s["power_w"] for s in scores.values() if s] + ([stock["power_w"]] if stock else []),
                         default=1) or 1)
        watts = [(tr("Standard", "Stock"), float(stock["power_w"]) if stock else 0.0, mx_w, STOCK_COLOR,
                  f"{stock['power_w']} W" if stock else "—")]
        watts += [(f"{tr('Profil', 'Profile')} {i + 1}",
                   float(scores[i]["power_w"]) if scores[i] else 0.0, mx_w, COMPARE_COLORS[i],
                   (f"{scores[i]['power_w']} W" if scores[i] else unmeasured)) for i, _p in active]
        self._metric_rows["watt"].set_values(watts)
        mx_mem = max((p.mem_offset_mhz or 0 for _i, p in active), default=1) or 1
        self._metric_rows["mem"].set_values(
            [(tr("Standard", "Stock"), 0.0, float(mx_mem), STOCK_COLOR, "+0")] +
            [(f"{tr('Profil', 'Profile')} {i + 1}", float(p.mem_offset_mhz or 0), float(mx_mem), COMPARE_COLORS[i],
              f"+{int(p.mem_offset_mhz or 0)}") for i, p in active])

        def best(key):
            vals = {i: s[key] for i, s in scores.items() if s}
            return max(vals, key=vals.get) if len(vals) >= 2 else None
        b_perf, b_eff = best("perf_pct"), best("eff_pct")

        def cell_perf(i, p):
            s = scores.get(i)
            return (_pct_mark(s["perf_pct"]) + (BEST if i == b_perf else "")) if s else unmeasured

        def cell_eff(i, p):
            s = scores.get(i)
            return (_pct_mark(s["eff_pct"]) + (BEST if i == b_eff else "")) if s else unmeasured

        def cell_points(i, p):
            s = scores.get(i)
            return (tr(f"{s['points']} (Standard {s['stock_points']})", f"{s['points']} (stock {s['stock_points']})")
                    if s else unmeasured)

        def cell_ppw(i, p):
            s = scores.get(i)
            return (tr(f"{_dec(s['ppw'])} (Standard {_dec(s['stock_ppw'])})",
                       f"{_dec(s['ppw'])} (stock {_dec(s['stock_ppw'])})") if s else unmeasured)

        def cell_watt(i, p):
            s = scores.get(i)
            return (tr(f"{s['power_w']} W (Standard {s['stock_power_w']} W)",
                       f"{s['power_w']} W (stock {s['stock_power_w']} W)") if s else unmeasured)

        def cell_bench(i, p):
            s = scores.get(i)
            return s["label"] if s else "—"

        if stock:
            measured = (tr("vor jedem Tune", "before every tune") +
                        (tr(f" (Ø aus {stock['n']})", f" (mean of {stock['n']})") if stock["n"] > 1 else ""))
        # (label, stock column, per profile)
        row_defs = [
            ("Name", tr("Standard (ab Werk)", "Stock (as it comes)"), lambda i, p: p.name),
            (tr("Modus", "Mode"), tr("ohne Tuning", "no tuning"), lambda i, p: describe_mode(p)),
            (tr("Takt", "Clock"), tr("ab Werk", "as it comes"), lambda i, p: describe_clock(p)),
            (tr("Speicher", "Memory"), "+0 MHz", lambda i, p: f"+{int(p.mem_offset_mhz or 0)} MHz"),
            (tr("Power-Limit", "Power limit"), "100 %", lambda i, p: f"{int(p.power_limit_pct or 100)} %"),
            (tr("FurMark-Punkte (je 60 s)", "FurMark points (per 60 s)"),
             str(stock["points"]) if stock else "—", cell_points),
            (tr("Punkte pro Watt", "Points per watt"), _dec(stock["ppw"]) if stock else "—", cell_ppw),
            (tr("Leistung ggü. Standard", "Performance vs stock"), BASE, cell_perf),
            (tr("Effizienz ggü. Standard", "Efficiency vs stock"), BASE, cell_eff),
            (tr("Leistungsaufnahme", "Power draw"), f"{stock['power_w']} W" if stock else "—", cell_watt),
            (tr("Gemessen mit", "Measured with"), measured if stock else "—", cell_bench),
            (tr("Stabilitätstests", "Stability tests"), "—",
             lambda i, p: tr("bestanden", "passed") if p.is_stable else tr("nicht bestanden", "not passed")),
            (tr("Erstellt", "Created"), "—", lambda i, p: _created(p)),
        ]
        for label, base, fn in row_defs:
            cells = [label, base] + [fn(i, self._selected[i]) if self._selected[i] else "" for i in range(4)]
            self.detail_tree.insert("", "end", values=cells)

    def _update_curves(self, active):
        c = self._base_curve
        if c is None:
            self.curve_chart.set_data([], [], self._curve_note)
            return
        lines = [(f"{tr('Profil', 'Profile')} {i + 1}", COMPARE_COLORS[i], profile_line(c, p),
                  measured_points(p), flat_from(p)) for i, p in active]
        self.curve_chart.set_data(stock_line(c), lines)


class CurveChart(tk.Canvas):
    """The V/F curves like Afterburner's curve editor: voltage to the right, clock up.
    set_data(stock, [(label, colour, line, measured, flat_mv)]) — lines as [(mV, MHz)].
    Pointing at the chart shows every line's clock at that voltage."""

    PAD_L, PAD_R, PAD_T, PAD_B = 54, 16, 26, 30

    def __init__(self, parent, height: int = 300, **kw):
        super().__init__(parent, height=height, bg=CARD_BG, highlightthickness=0, bd=0, **kw)
        self._stock: list = []
        self._lines: list = []
        self._note = ""
        self.hover_text = ""              # what the pointer shows (tests read it)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._clear_hover())

    def set_data(self, stock: list, lines: list, note: str = ""):
        self._stock, self._lines, self._note = list(stock or []), list(lines or []), note
        self._draw()

    def _ranges(self):
        xs = [mv for mv, _f in self._stock] + [mv for _l, _c, ln, _m, _fl in self._lines for mv, _f in ln]
        ys = [f for _mv, f in self._stock] + [f for _l, _c, ln, _m, _fl in self._lines for _mv, f in ln]
        if not xs:
            return None
        x0, x1 = min(xs), max(xs)
        y0 = int(min(ys) // 100) * 100
        y1 = int(-(-max(ys) // 100)) * 100
        return x0, x1, y0, max(y1, y0 + 100)

    def _xy(self, mv, mhz, r):
        x0, x1, y0, y1 = r
        w, h = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        x = self.PAD_L + (mv - x0) / ((x1 - x0) or 1) * (w - self.PAD_L - self.PAD_R)
        y = h - self.PAD_B - (mhz - y0) / ((y1 - y0) or 1) * (h - self.PAD_T - self.PAD_B)
        return x, y

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        r = self._ranges()
        if r is None or w < 60 or h < 60:
            self.create_text(w / 2 if w > 1 else 200, h / 2 if h > 1 else 100, fill=DIM, font=F_S,
                             text=self._note or tr("— kein Profil gewählt", "— no profile selected"),
                             tags=("empty",))
            return
        x0, x1, y0, y1 = r
        grid = mix(CARD_BG, "#ffffff", 0.07)
        # where the card runs under load: from the lowest to the highest measured point
        meas = [mv for _l, _c, _ln, m, _fl in self._lines for mv, _f in m]
        if meas:
            a, _ = self._xy(min(meas), y0, r)
            b, _ = self._xy(max(meas), y0, r)
            self.create_rectangle(a, self.PAD_T, b, h - self.PAD_B, fill=mix(CARD_BG, "#ffffff", 0.035),
                                  outline="", tags=("band",))
            self.create_text((a + b) / 2, self.PAD_T - 8, fill=DIM, font=F_XS, tags=("band",),
                             text=tr(f"Lastbereich {min(meas):.0f}–{max(meas):.0f} mV",
                                     f"under load {min(meas):.0f}–{max(meas):.0f} mV"))
        step_y = 100 if (y1 - y0) <= 1200 else 200
        for f in range(y0, y1 + 1, step_y):
            _x, y = self._xy(x0, f, r)
            self.create_line(self.PAD_L, y, w - self.PAD_R, y, fill=grid, tags=("grid",))
            self.create_text(self.PAD_L - 6, y, text=str(f), anchor="e", fill=DIM, font=F_XS, tags=("grid",))
        for mv in range(int(-(-x0 // 50)) * 50, int(x1) + 1, 50):
            x, _y = self._xy(mv, y0, r)
            self.create_line(x, self.PAD_T, x, h - self.PAD_B, fill=grid, tags=("grid",))
            self.create_text(x, h - self.PAD_B + 12, text=str(mv), fill=DIM, font=F_XS, tags=("grid",))
        self.create_text(self.PAD_L - 6, self.PAD_T - 8, text="MHz", anchor="e", fill=DIM, font=F_XS)
        self.create_text(w - self.PAD_R, h - 4, text="mV", anchor="se", fill=DIM, font=F_XS)
        if len(self._stock) > 1:
            self.create_line(*[c for mv, f in self._stock for c in self._xy(mv, f, r)], fill=STOCK_COLOR,
                             width=2, dash=(5, 3), tags=("stock",))
        for i, (_label, color, line, measured, _flat) in enumerate(self._lines):
            if len(line) > 1:
                self.create_line(*[c for mv, f in line for c in self._xy(mv, f, r)], fill=color, width=2,
                                 tags=("line", f"line{i}"))
            for mv, f in measured:
                x, y = self._xy(mv, f, r)
                self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=CARD_BG, tags=("dot", f"dot{i}"))

    def _clear_hover(self):
        self.delete("hover")
        self.hover_text = ""

    def _on_motion(self, e):
        r = self._ranges()
        if r is None:
            return
        x0, x1, _y0, _y1 = r
        w, h = self.winfo_width(), self.winfo_height()
        if not (self.PAD_L <= e.x <= w - self.PAD_R):
            return self._clear_hover()
        mv = x0 + (e.x - self.PAD_L) / max(w - self.PAD_L - self.PAD_R, 1) * (x1 - x0)
        self.show_at(mv)

    def show_at(self, mv: float):
        """The clocks of every line at mv: a vertical line and their values (pointer)."""
        from core.profile_curves import value_at
        r = self._ranges()
        if r is None:
            return
        self.delete("hover")
        h = self.winfo_height()
        x, _y = self._xy(mv, r[2], r)
        self.create_line(x, self.PAD_T, x, h - self.PAD_B, fill=TEXT2, dash=(2, 3), tags=("hover",))
        parts = [(f"{mv:.0f} mV", TEXT2)]
        s = value_at(self._stock, mv)
        if s is not None:
            parts.append((tr(f"Standard {s:.0f}", f"Stock {s:.0f}"), STOCK_COLOR))
        for label, color, line, _m, _fl in self._lines:
            v = value_at(line, mv)
            if v is not None:
                parts.append((f"{label} {v:.0f}", color))
        self.hover_text = "  ·  ".join(t for t, _c in parts)
        tx, items = self.PAD_L + 6, []
        for text, color in parts:
            item = self.create_text(tx, self.PAD_T + 8, text=text, anchor="w", fill=color, font=F_SB,
                                    tags=("hover",))
            items.append(item)
            bx = self.bbox(item)
            tx = (bx[2] if bx else tx + 60) + 12
        bb = self.bbox(*items)
        if bb:
            bg = self.create_rectangle(self.PAD_L + 2, bb[1] - 3, bb[2] + 6, bb[3] + 3,
                                       fill=mix(CARD_BG, "#000000", 0.25), outline="", tags=("hover",))
            self.tag_lower(bg, items[0])


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
