"""GameOptimizerPro GPU Tuner page — NVTuner v2 embedded.

Auto-Tune: settings on the left (scrolls if needed), live tiles, graph,
progress and the tuner log on the right — the log is visible at every window
size. Sub-pages switch with a segmented bar (no accidental switching with the
mouse wheel like the old ttk notebook)."""

import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from core.nvtune_core import AfterburnerController, GpuMonitor, ProfileManager, TuneProfile
from core.nvtune_tuner import AutoTuner, TunerConfig, TunerState
from ui.components import (Card, CheckBox, LogView, NumberField, Page, ResponsiveGrid, Table,
                           WrapLabel, button, scroll_area, tile)
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, CYAN, DIM, ERR, F_BB,
                      F_MONO, F_S, F_XS, GREEN, INPUT_BG, MUTED, TEXT, TEXT2, VIOLET, ctk_font,
                      icon_image, mix, on_color, tr)

# Fix import path for stress worker
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

MODES = [
    ("oc_only", "Übertakten", "Overclock",
     "Maximaler stabiler Core-Offset, das Power-Limit bleibt bei 100 % — mehr FPS bei gleichen "
     "Temperaturen.",
     "Max stable core offset, power limit stays at 100 % — more FPS, same temperatures."),
    ("uv_only", "Undervolten", "Undervolt",
     "Kleinstes stabiles Power-Limit, der Core-Offset bleibt 0 — kühler und leiser bei "
     "Standard-Takt.",
     "Lowest stable power limit, core offset stays at 0 — cooler and quieter at stock speed."),
    ("oc_uv", "OC + UV", "OC + UV",
     "Bewährt und schneller (20–45 min) — beides: höherer Takt und niedrigere Temperaturen, "
     "gleiche oder bessere Leistung.",
     "Proven and quicker (20–45 min) — best of both: higher clocks, lower temperatures, same "
     "or better performance."),
    ("curve", "Rundum", "All-round",
     "Neu und am gründlichsten (40–60 min) — misst jeden Spannungspunkt der V/F-Kurve einzeln "
     "(wie HYDRA), baut daraus eine eigene Kurve, vergleicht per FurMark-Benchmark und wählt nach "
     "dem Ziel. Endtest: 5 min FurMark + Rechenprüfung, danach ein Bericht.",
     "New and most thorough (40–60 min) — measures every voltage point of the V/F curve on its "
     "own (like HYDRA), builds an own curve from it, compares with FurMark benchmarks and picks "
     "by the goal. Final test: 5 min FurMark + compute check, then a report."),
]

GOALS = [
    ("max", "Max. Leistung", "Max performance",
     "Höchste FurMark-Punktzahl: die volle gemessene Kurve. Hängt die Karte im Power-Limit, wird "
     "auch das höchste erlaubte Limit getestet. Mehr Leistung kostet mehr Strom und Wärme.",
     "Highest FurMark score: the full measured curve. If the card sits at its power limit, the "
     "highest allowed limit is tested too. More speed costs more power and heat."),
    ("balanced", "Ausgewogen", "Balanced",
     "Behält mindestens die Hälfte des Leistungsgewinns und nimmt davon die Einstellung mit den "
     "meisten Punkten pro Watt — schneller als Standard, kaum mehr Verbrauch.",
     "Keeps at least half of the performance gain and takes the setting with the most points "
     "per watt among those — faster than stock at about the same power."),
    ("efficiency", "Effizienz", "Efficiency",
     "Undervolting: Standard-Leistung (≥ 99 %) bei möglichst wenig Watt — kühler und leiser.",
     "Undervolting: stock performance (≥ 99 %) at as few watts as possible — cooler and "
     "quieter."),
]


class GpuTunerTab(Page):
    def __init__(self, parent, monitor: GpuMonitor, ab: AfterburnerController,
                 pm: ProfileManager, tuner: AutoTuner, **kw):
        super().__init__(parent, tr("GPU-Tuner", "GPU Tuner"),
                         tr("Automatisches Übertakten/Undervolten über MSI Afterburner — mit "
                            "Stabilitätstests nach jedem Schritt",
                            "Automatic overclocking/undervolting via MSI Afterburner — with a "
                            "stability test after every step"),
                         color=CYAN, scroll=False, **kw)
        self.monitor = monitor
        self.ab = ab
        self.pm = pm
        self.tuner = tuner

        self.tuner.on_state(self._on_state)
        self.tuner.on_log(self._on_log)
        self.tuner.on_progress(self._on_progress)
        self.tuner.on_tick(self._on_tick)

        self._build()

    def _build(self):
        b = self.body
        bar = tk.Frame(b, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 10))
        self._views = {}
        self._view_keys = {"Auto-Tune": "auto", tr("Profile", "Profiles"): "profiles",
                           tr("Manuell", "Manual"): "manual"}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._view_keys), height=32,
                                          font=ctk_font(12), selected_color=mix(CARD_BG2, CYAN, 0.62),
                                          selected_hover_color=mix(CARD_BG2, CYAN, 0.75),
                                          command=lambda v: self._show_view(self._view_keys[v]))
        self.seg.pack(side="left")
        self.lbl_state = tk.Label(bar, text="● Idle", font=F_BB, fg=DIM, bg=APP_BG)
        self.lbl_state.pack(side="right")

        holder = tk.Frame(b, bg=APP_BG)
        holder.pack(fill="both", expand=True)
        for key, builder in (("auto", self._build_autotune), ("profiles", self._build_profiles),
                             ("manual", self._build_manual)):
            f = tk.Frame(holder, bg=APP_BG)
            self._views[key] = f
            builder(f)
        self._show_view("auto")

    def _show_view(self, key: str):
        for k, f in self._views.items():
            if k != key:
                f.pack_forget()
        self._views[key].pack(fill="both", expand=True)
        label = next(lbl for lbl, k in self._view_keys.items() if k == key)
        self.seg.set(label)

    # ── Auto-Tune ─────────────────────────────────────────────────────────────

    def _build_autotune(self, p):
        p.grid_columnconfigure(0, weight=5, uniform="at")
        p.grid_columnconfigure(1, weight=6, uniform="at")
        p.grid_rowconfigure(0, weight=1)

        left = scroll_area(p)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = tk.Frame(p, bg=APP_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ── Mode ──────────────────────────────────────────────────────────────
        self.v_mode = tk.StringVar(value="oc_uv")
        mode = Card(left, tr("Modus", "Mode"), accent=CYAN)
        mode.pack(fill="x", padx=(0, 8), pady=(0, 12))
        self.mode_card = mode
        self._mode_short = False
        self._mode_font = ctk_font(12)
        self._mode_labels = self._mode_texts(False)
        self.seg_mode = ctk.CTkSegmentedButton(mode.body, values=list(self._mode_labels), height=32,
                                               font=self._mode_font, selected_color=mix(CARD_BG2, CYAN, 0.62),
                                               selected_hover_color=mix(CARD_BG2, CYAN, 0.75),
                                               command=lambda v: self._select_mode(self._mode_labels[v]))
        self.seg_mode.pack(fill="x")
        # (CTkSegmentedButton itself refuses bind() — its parent frame has the same width)
        mode.body.bind("<Configure>", self._fit_mode_labels, add="+")
        self.lbl_mode_desc = WrapLabel(mode.body, text="", font=F_S, fg=TEXT2, bg=CARD_BG)
        self.lbl_mode_desc.pack(fill="x", pady=(8, 0))
        self._highlight_mode_btns()

        # ── IntVars MUST be created before _show_gpu_defaults() which calls .set() ──
        self.v_core_step = tk.IntVar(value=15)
        self.v_core_max  = tk.IntVar(value=200)
        self.v_pwr_min   = tk.IntVar(value=70)
        self.v_max_temp  = tk.IntVar(value=85)
        self.v_step_dur  = tk.IntVar(value=45)
        self.v_final_dur = tk.IntVar(value=120)
        self.v_mem_max   = tk.IntVar(value=1000)
        self.v_mem_stage = tk.BooleanVar(value=True)
        self.v_ab_slot   = tk.IntVar(value=2)
        # Rundum-Tuner
        self.v_goal      = tk.StringVar(value="balanced")
        self.v_fm_final  = tk.IntVar(value=5)      # FurMark final test (min)
        self.v_safety    = tk.IntVar(value=30)     # MHz taken off every measured point

        self._build_curve_cards(left)

        params = Card(left, tr("Parameter", "Parameters"), accent=CYAN)
        params.pack(fill="x", padx=(0, 8), pady=(0, 12))
        self.params_card = params
        # GPU defaults info (uses the IntVars above — must come after)
        self.lbl_gpu_defaults = WrapLabel(params.body, text="", font=F_XS, fg=DIM, bg=CARD_BG)
        self.lbl_gpu_defaults.pack(fill="x", pady=(0, 10))
        self._show_gpu_defaults()

        grid = ResponsiveGrid(params.body, min_width=150, max_cols=2, gap=10, bg=CARD_BG)
        grid.pack(fill="x")
        for label, var, lo, hi, step in (
            (tr("Core-Schritt (MHz)", "Core step (MHz)"), self.v_core_step, 5, 50, 5),
            (tr("Core max. (MHz)", "Core max (MHz)"),     self.v_core_max, 0, 500, 15),
            (tr("Power min. (%)", "Power min (%)"),       self.v_pwr_min, 50, 100, 5),
            (tr("Max. Temperatur (°C)", "Max temp (°C)"), self.v_max_temp, 70, 95, 1),
            (tr("Stufentest (s)", "Step test (s)"),       self.v_step_dur, 15, 300, 15),
            (tr("Endtest (s)", "Final test (s)"),         self.v_final_dur, 60, 600, 30),
            (tr("Speicher max. (MHz)", "Mem max (MHz)"),  self.v_mem_max, 100, 3000, 100),
            (tr("AB-Slot (2–5)", "AB slot (2–5)"),        self.v_ab_slot, 2, 5, 1),
        ):
            cell = tk.Frame(grid, bg=CARD_BG)
            tk.Label(cell, text=label, font=F_XS, fg=DIM, bg=CARD_BG, anchor="w").pack(fill="x")
            NumberField(cell, var, lo, hi, step, width=64, bg=CARD_BG).pack(anchor="w", pady=(2, 0))
            grid.add(cell)

        # Memory stage: searched and MEASURED, not a fixed guess (the old
        # 'Mem Offset' field applied an unsearched value to every step).
        mem = tk.Frame(params.body, bg=CARD_BG)
        mem.pack(fill="x", pady=(12, 0))
        self.chk_mem_stage = CheckBox(mem, self.v_mem_stage, accent=CYAN, bg=CARD_BG,
                                      text=tr("Speicher mit übertakten", "Overclock memory too"), font=F_BB)
        self.chk_mem_stage.pack(anchor="w")
        WrapLabel(mem, text=tr(
            "Stufe 4 misst die Speicher-Bandbreite: GDDR6X korrigiert Fehler durch Wiederholen und "
            "wird über dem Limit LANGSAMER statt abzustürzen — genommen wird das Bandbreiten-Maximum "
            "(bis 'Speicher max.'). Dauert ca. 6–10 min länger.",
            "Stage 4 measures memory bandwidth: GDDR6X corrects errors by retrying and gets SLOWER "
            "above its limit instead of crashing — the bandwidth peak is taken (up to 'Mem max'). "
            "Takes about 6–10 min longer."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(4, 0))
        self._show_mode_cards()

        # ── Right: controls, live values, graph, progress, log ───────────────
        self._tuner_ok, why = self._tuner_support()
        if not self._tuner_ok:
            warn = Card(right, tr("Nicht unterstützt", "Not supported"), accent=AMBER, pady=10)
            warn.pack(fill="x", pady=(0, 10))
            self.lbl_unsupported = WrapLabel(warn.body, text=why, font=F_S, fg=AMBER, bg=CARD_BG)
            self.lbl_unsupported.pack(fill="x")
        ctrl = tk.Frame(right, bg=APP_BG)
        ctrl.pack(fill="x", pady=(0, 10))
        self.btn_start = button(ctrl, tr("Tune starten", "Start tune"), self._start_tune,
                                kind="primary", color=CYAN, image=icon_image("play", on_color(CYAN), 15),
                                compound="left", height=36,
                                state="normal" if self._tuner_ok else "disabled")
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_abort = button(ctrl, tr("Abbrechen", "Abort"), self._abort_tune, kind="danger",
                                image=icon_image("stop", "#ffffff", 14), compound="left", height=36,
                                state="disabled")
        self.btn_abort.pack(side="left")
        # Rundum-Tuner: the last report (a text file next to the tune log)
        self.btn_report = button(ctrl, tr("Bericht", "Report"), self._open_report, kind="ghost",
                                 image=icon_image("info", TEXT2, 14), compound="left", height=36,
                                 state="disabled")
        self.btn_report.pack(side="left", padx=(8, 0))

        tiles = ResponsiveGrid(right, min_width=90, max_cols=4, gap=8)
        tiles.pack(fill="x", pady=(0, 10))
        self._ttiles = {}
        for key, label, unit, color in (
            ("volt", tr("Spannung", "Voltage"), "mV",  VIOLET),
            ("temp", "Temp",                    "°C",  ERR),
            ("clk",  "Clock",                   "MHz", ACC),
            ("pwr",  tr("Leistung", "Power"),   "W",   AMBER),
        ):
            f, vl = tile(tiles, label, "--", color, unit, bg=CARD_BG)
            tiles.add(f)
            self._ttiles[key] = vl

        from ui.live_graph import LiveGraph
        gcard = Card(right, pady=12)
        gcard.pack(fill="x", pady=(0, 10))
        self.live_graph = LiveGraph(gcard.body, height=120)
        self.live_graph.pack(fill="x")

        pf = tk.Frame(right, bg=APP_BG)
        pf.pack(fill="x", pady=(0, 8))
        self.prog_var = tk.DoubleVar()
        self.prog_bar = ctk.CTkProgressBar(pf, height=8, corner_radius=4, progress_color=CYAN)
        self.prog_bar.set(0)
        self.prog_bar.pack(fill="x")
        self.prog_var.trace_add("write", lambda *_: self.prog_bar.set(
            max(0.0, min(1.0, self.prog_var.get() / 100))))
        self.lbl_prog = tk.Label(pf, text="", font=F_XS, fg=DIM, bg=APP_BG, anchor="w")
        self.lbl_prog.pack(fill="x", pady=(4, 0))

        # Log — takes the rest of the column, always visible
        lcard = ctk.CTkFrame(right, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER)
        lcard.pack(fill="both", expand=True)
        tk.Label(lcard, text="Tuner-Log", font=("Segoe UI Semibold", 8), fg=MUTED,
                 bg=INPUT_BG).pack(anchor="w", padx=12, pady=(8, 0))
        self.log = LogView(lcard, height=6)
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # ── Rundum-Tuner: goal + its own parameters ──────────────────────────────

    def _build_curve_cards(self, left):
        """Goal switch and the Rundum parameters — shown instead of the classic
        parameter card while the mode is 'curve'."""
        goal = Card(left, tr("Ziel", "Goal"), accent=CYAN)
        self.goal_card = goal
        self._goal_labels = {tr(de, en): gid for gid, de, en, _dd, _ed in GOALS}
        self.seg_goal = ctk.CTkSegmentedButton(goal.body, values=list(self._goal_labels), height=32,
                                               font=ctk_font(12), selected_color=mix(CARD_BG2, CYAN, 0.62),
                                               selected_hover_color=mix(CARD_BG2, CYAN, 0.75),
                                               command=lambda v: self._select_goal(self._goal_labels[v]))
        self.seg_goal.pack(fill="x")
        self.lbl_goal_desc = WrapLabel(goal.body, text="", font=F_S, fg=TEXT2, bg=CARD_BG)
        self.lbl_goal_desc.pack(fill="x", pady=(8, 0))
        self._select_goal(self.v_goal.get())

        cp = Card(left, tr("Rundum-Parameter", "All-round parameters"), accent=CYAN)
        self.curve_card = cp
        self.lbl_furmark = WrapLabel(cp.body, text="", font=F_XS, fg=DIM, bg=CARD_BG)
        self.lbl_furmark.pack(fill="x", pady=(0, 10))
        grid = ResponsiveGrid(cp.body, min_width=150, max_cols=2, gap=10, bg=CARD_BG)
        grid.pack(fill="x")
        for label, var, lo, hi, step in (
            (tr("Core max. (MHz)", "Core max (MHz)"),               self.v_core_max, 0, 500, 15),
            (tr("Max. Temperatur (°C)", "Max temp (°C)"),           self.v_max_temp, 70, 95, 1),
            (tr("Test je Punkt (s)", "Test per point (s)"),         self.v_step_dur, 15, 300, 15),
            (tr("Sicherheit (MHz)", "Safety margin (MHz)"),         self.v_safety, 15, 90, 15),
            (tr("FurMark-Endtest (min)", "FurMark final (min)"),    self.v_fm_final, 1, 15, 1),
            (tr("Rechenprüfung (s)", "Compute check (s)"),          self.v_final_dur, 60, 600, 30),
            (tr("Speicher max. (MHz)", "Mem max (MHz)"),            self.v_mem_max, 100, 3000, 100),
            (tr("AB-Slot (2–5)", "AB slot (2–5)"),                  self.v_ab_slot, 2, 5, 1),
        ):
            cell = tk.Frame(grid, bg=CARD_BG)
            tk.Label(cell, text=label, font=F_XS, fg=DIM, bg=CARD_BG, anchor="w").pack(fill="x")
            NumberField(cell, var, lo, hi, step, width=64, bg=CARD_BG).pack(anchor="w", pady=(2, 0))
            grid.add(cell)
        memf = tk.Frame(cp.body, bg=CARD_BG)
        memf.pack(fill="x", pady=(12, 0))
        CheckBox(memf, self.v_mem_stage, accent=CYAN, bg=CARD_BG,
                 text=tr("Speicher mit übertakten", "Overclock memory too"), font=F_BB).pack(anchor="w")
        WrapLabel(memf, text=tr(
            "Start mit einem vorsichtigen Wert je Kartengeneration (RTX 40: +500), dann "
            "100er-Schritte bis „Speicher max“ — jeder Schritt mit der ganzen Karte unter Last "
            "(FurMark + geprüfte Speicherkopien), damit Fehler sofort auffallen. Übernommen: der "
            "höchste bestandene Schritt, 100 MHz darunter, wenn ein Fehler kam.",
            "Starts at a cautious value per card generation (RTX 40: +500), then 100-MHz steps "
            "up to 'Mem max' — every step with the whole card under load (FurMark + verified "
            "memory copies), so errors show at once. Used: the highest step that passed, 100 MHz "
            "lower if a step failed."),
            font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(4, 0))
        WrapLabel(cp.body, text=tr(
            "Je Spannungspunkt: Kurve dort flach, leichte Boost-Last (die Karte sitzt genau auf dem "
            "Punkt), jedes Ergebnis wird geprüft. +15 MHz bis zum Fehler, dann halbiert bis 5 MHz. "
            "Übernommen wird der gefundene Takt minus Sicherheit (60 MHz, wo der Treiber neu "
            "starten musste).",
            "Per voltage point: curve flat there, light boost load (the card sits exactly on the "
            "point), every result checked. +15 MHz until a failure, then halved down to 5 MHz. "
            "Used: the clock found minus the safety margin (60 MHz where the driver had to "
            "restart)."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(10, 0))
        self._update_furmark_status()

    def _select_goal(self, goal_id: str):
        self.v_goal.set(goal_id)
        for gid, de, en, dd, ed in GOALS:
            if gid == goal_id:
                self.seg_goal.set(tr(de, en))
                self.lbl_goal_desc.config(text=tr(dd, ed))

    def _show_mode_cards(self):
        """Classic parameters or goal + Rundum parameters, right below the mode card."""
        curve = self.v_mode.get() == "curve"
        if curve:
            self.params_card.pack_forget()
            self.goal_card.pack(fill="x", padx=(0, 8), pady=(0, 12), after=self.mode_card)
            self.curve_card.pack(fill="x", padx=(0, 8), pady=(0, 12), after=self.goal_card)
            self._update_furmark_status()
        else:
            self.goal_card.pack_forget()
            self.curve_card.pack_forget()
            self.params_card.pack(fill="x", padx=(0, 8), pady=(0, 12), after=self.mode_card)

    @staticmethod
    def _furmark_v2() -> str:
        """FurMark 2's console exe if it is set up (the tuner needs its scored
        benchmark), else ''."""
        try:
            from core import furmark
            p = furmark.detect()
            return p if p and furmark.is_v2(p) else ""
        except Exception:
            return ""

    def _update_furmark_status(self):
        path = self._furmark_v2()
        if path:
            try:
                from core import furmark
                name = furmark.describe(path)
            except Exception:
                name = "FurMark 2"
            self.lbl_furmark.config(fg=GREEN, text=tr(
                f"✓ {name} — Benchmark 1920×1080 mit 8× MSAA (voll ausgelastet, auch mit FPS-Limit)",
                f"✓ {name} — benchmark 1920×1080 with 8× MSAA (full load, even with an FPS cap)"))
        else:
            self.lbl_furmark.config(fg=AMBER, text=tr(
                "FurMark 2 nicht gefunden — gemessen wird mit dem internen Rechen-Benchmark. Für "
                "echte Grafik-Punkte FurMark 2 im Stresstest-Tab einrichten.",
                "FurMark 2 not found — measured with the internal compute benchmark. For real "
                "graphics scores set up FurMark 2 in the Stress Test tab."))

    def _curve_prior(self) -> tuple:
        """Start offset for the first voltage point -> (MHz, from_profile): the
        core offset of the newest stable tune result for this card, else the
        cautious start value of its generation (core/gpu_defaults; 0 = coarse
        search from stock)."""
        try:
            name = self.monitor.read().name
        except Exception:
            name = ""
        best = None
        for p in self.pm.list_all():
            if not (p.is_stable and p.name.startswith("GOP_") and p.core_offset_mhz > 0):
                continue
            if name and p.gpu_name and p.gpu_name != name:
                continue
            if best is None or (p.created_at or "") > (best.created_at or ""):
                best = p
        if best:
            return int(best.core_offset_mhz), True
        try:
            from core.gpu_defaults import get_defaults
            return int(get_defaults(name).core_start_mhz), False
        except Exception:
            return 0, False

    def _mem_start(self) -> int:
        """First memory offset of the Rundum memory stage: cautious, per generation."""
        try:
            from core.gpu_defaults import get_defaults
            start = get_defaults(self.monitor.read().name).mem_start_mhz or 500
        except Exception:
            start = 500
        return max(0, min(start, self.v_mem_max.get()))

    def _tuner_support(self) -> tuple:
        """-> (supported, reason). The Auto-Tuner drives MSI Afterburner's NVIDIA
        V/F curve and reads NVML — NVIDIA cards only."""
        amd = tr("Für AMD-Karten hat die AMD Software (Adrenalin) ein eigenes Auto-Tuning: "
                 "Leistung → Tuning → automatisch undervolten / übertakten.",
                 "AMD cards have their own auto tuning in AMD Software (Adrenalin): "
                 "Performance → Tuning → auto undervolt / overclock.")
        intel = tr("Für Intel Arc: Intel Graphics Software → Leistung.",
                   "Intel Arc: Intel Graphics Software → Performance.")
        head = tr("Der Auto-Tuner arbeitet mit MSI Afterburners V/F-Kurve und NVML — beides gibt "
                  "es nur für NVIDIA-Karten. ",
                  "The Auto-Tuner works with MSI Afterburner's V/F curve and NVML — both exist "
                  "for NVIDIA cards only. ")
        try:
            from core.gpu_defaults import get_defaults
            d = get_defaults(self.monitor.read().name)
        except Exception:
            d = None
        if d is not None and not d.tuner_supported:
            return False, head + (amd if d.vendor == "AMD" else intel)
        nv = getattr(self.monitor, "nvml", None)
        if nv is not None and not getattr(nv, "available", True):
            return False, (tr("Keine NVIDIA-Grafikkarte erkannt (NVML nicht verfügbar). ",
                              "No NVIDIA graphics card found (NVML not available). ")
                           + head + amd + " " + intel)
        return True, ""

    def _open_report(self):
        path = getattr(self.tuner, "last_report_path", "") or ""
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except OSError as e:
                messagebox.showerror(tr("Bericht", "Report"), str(e))

    def _select_mode(self, mode_id: str):
        self.v_mode.set(mode_id)
        self._highlight_mode_btns()
        self._apply_mode_to_config(mode_id)
        self._show_mode_cards()

    # Short button texts when the four long ones don't fit (window at its minimum
    # size); the description below the buttons says what the mode does anyway.
    MODE_SHORT = {"oc_only": ("OC", "OC"), "uv_only": ("UV", "UV")}

    def _mode_texts(self, short: bool) -> dict:
        out = {}
        for mid, de, en, _dd, _ed in MODES:
            if short and mid in self.MODE_SHORT:
                de, en = self.MODE_SHORT[mid]
            out[tr(de, en)] = mid
        return out

    def _fit_mode_labels(self, _e=None):
        width = self.seg_mode.winfo_width()
        if width <= 1:
            return
        need = sum(self._mode_font.measure(t) + 28 for t in self._mode_texts(False))
        short = width < need
        if short != self._mode_short:
            self._mode_short = short
            self._mode_labels = self._mode_texts(short)
            self.seg_mode.configure(values=list(self._mode_labels))
            self._highlight_mode_btns()

    def _highlight_mode_btns(self):
        mid = self.v_mode.get()
        for m, de, en, dd, de_en in MODES:
            if m == mid:
                self.seg_mode.set(next(t for t, k in self._mode_labels.items() if k == mid))
                self.lbl_mode_desc.config(text=tr(dd, de_en))

    def _show_gpu_defaults(self):
        """Load GPU defaults and fill the parameter fields."""
        try:
            from core.gpu_defaults import get_defaults
            gpu_name = self.monitor.read().name
            d = get_defaults(gpu_name)

            # Fill the fields with generation-appropriate defaults
            self.v_core_step.set(d.core_step_mhz)
            self.v_core_max.set( d.core_max_mhz)
            self.v_pwr_min.set(  d.power_min_pct)
            self.v_max_temp.set( d.max_temp_c)
            self.v_mem_max.set(  d.mem_max_mhz)

            self.lbl_gpu_defaults.config(
                text=f"{gpu_name[:40]}  ·  {d.generation}  ·  "
                     f"{tr('Vorgaben', 'Defaults')}: Core max +{d.core_max_mhz} MHz, "
                     f"Mem max +{d.mem_max_mhz} MHz, Power min {d.power_min_pct} %, "
                     f"Temp-Limit {d.max_temp_c} °C"
                     + (tr(f"  ·  Rundum-Start: Core +{d.core_start_mhz}, Speicher +{d.mem_start_mhz}",
                           f"  ·  All-round start: core +{d.core_start_mhz}, memory +{d.mem_start_mhz}")
                        if d.tuner_supported else ""),
                fg=ACC if d.tuner_supported else AMBER
            )
        except Exception as e:
            self.lbl_gpu_defaults.config(
                text=f"GPU detection: {e} — using conservative defaults", fg=AMBER)

    def _apply_mode_to_config(self, mode_id: str):
        """When mode changes, adjust visible defaults."""
        try:
            from core.gpu_defaults import get_defaults
            gpu_name = self.monitor.read().name
            d = get_defaults(gpu_name)

            if mode_id == "oc_only":
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(100)
                self.v_mem_stage.set(True)
            elif mode_id == "uv_only":
                self.v_core_max.set(0)
                self.v_pwr_min.set(d.power_min_pct)
                self.v_mem_stage.set(False)    # power saving: no extra memory power
            elif mode_id in ("full", "vf_only"):
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(100)  # VF curve handles UV, not power limit
            elif mode_id == "mem_only":
                self.v_core_max.set(0)
                self.v_pwr_min.set(100)
            elif mode_id == "curve":
                self.v_core_max.set(d.core_max_mhz)
                self.v_mem_stage.set(True)
                self.v_mem_max.set(min(1000, d.mem_max_mhz))   # +500 … +1000 (whole-card test)
            else:  # oc_uv
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(d.power_min_pct)
                self.v_mem_stage.set(True)
        except Exception:
            pass

    # ── Profiles ──────────────────────────────────────────────────────────────

    def _build_profiles(self, p):
        card = Card(p, tr("GPU-Profile", "GPU profiles"),
                    subtitle=tr("Ergebnisse des Auto-Tunes und gespeicherte manuelle Werte. "
                                "„Anwenden“ schreibt das Profil über Afterburner (kurzer Neustart von AB).",
                                "Auto-Tune results and saved manual values. 'Apply' writes the profile "
                                "via Afterburner (it restarts briefly)."),
                    accent=CYAN)
        card.pack(fill="both", expand=True)
        button(card.actions, tr("Aktualisieren", "Refresh"), self._refresh_profiles, kind="ghost",
               image=icon_image("refresh", TEXT2, 14), compound="left", height=28).pack(side="right")
        tbl = Table(card.body, [
            ("name", tr("Profil", "Profile"), 170, "w"), ("core", "Core+", 70, "center"),
            ("mem", "Mem+", 70, "center"), ("pwr", "Power %", 70, "center"),
            ("volt", tr("Ø Spannung", "Avg volt"), 80, "center"), ("score", "Score", 60, "center"),
            ("stable", tr("Stabil", "Stable"), 60, "center"), ("notes", tr("Notizen", "Notes"), 240, "w"),
        ], height=12, selectmode="browse")
        tbl.pack(fill="both", expand=True)
        self.tree = tbl.tree
        act = tk.Frame(card.body, bg=CARD_BG)
        act.pack(fill="x", pady=(10, 0))
        button(act, tr("In Afterburner anwenden", "Apply to Afterburner"), self._apply_profile,
               kind="primary", color=CYAN, height=30).pack(side="left", padx=(0, 6))
        button(act, tr("Als Tray-Standard", "Set as tray default"), self._set_tray_default,
               height=30).pack(side="left", padx=(0, 6))
        button(act, tr("Löschen", "Delete"), self._delete_profile, kind="ghost", height=30,
               image=icon_image("delete", ERR, 14), compound="left").pack(side="left")
        self.lbl_detail = WrapLabel(card.body, text=tr("Profil auswählen", "Select a profile"),
                                    font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_detail.pack(fill="x", pady=(10, 0))
        self.tree.bind("<<TreeviewSelect>>", self._on_profile_select)
        self._refresh_profiles()

    # ── Manual ────────────────────────────────────────────────────────────────

    def _build_manual(self, p):
        card = Card(p, tr("Manuelle Offsets", "Manual offsets"),
                    subtitle=tr("Wird über Afterburner angewendet — Afterburner startet dafür kurz neu "
                                "(ein paar Sekunden). Den Lüfter bitte in Afterburner selbst einstellen.",
                                "Applied via Afterburner — it is restarted briefly (a few seconds). "
                                "Set the fan in Afterburner itself."),
                    accent=CYAN)
        card.pack(fill="x")
        self.v_m_core = tk.IntVar(value=0)
        self.v_m_mem  = tk.IntVar(value=0)
        self.v_m_pwr  = tk.IntVar(value=100)
        rows = tk.Frame(card.body, bg=CARD_BG)
        rows.pack(fill="x")
        rows.grid_columnconfigure(1, weight=1)
        for i, (label, var, lo, hi, step, unit) in enumerate((
            ("Core Offset", self.v_m_core, -200, 350, 5, "MHz"),
            ("Mem Offset",  self.v_m_mem,  -500, 1500, 25, "MHz"),
            ("Power Limit", self.v_m_pwr,    50, 120, 1, "%"),
        )):
            tk.Label(rows, text=label, font=F_BB, fg=TEXT, bg=CARD_BG, anchor="w", width=12
                     ).grid(row=i, column=0, sticky="w", pady=8)
            ctk.CTkSlider(rows, from_=lo, to=hi, number_of_steps=(hi - lo) // step, variable=var,
                          height=18).grid(row=i, column=1, sticky="ew", padx=12)
            NumberField(rows, var, lo, hi, step, width=64, bg=CARD_BG).grid(row=i, column=2, padx=(0, 6))
            tk.Label(rows, text=unit, font=F_S, fg=DIM, bg=CARD_BG, width=4, anchor="w"
                     ).grid(row=i, column=3, sticky="w")
        bf = tk.Frame(card.body, bg=CARD_BG)
        bf.pack(fill="x", pady=(12, 0))
        button(bf, tr("Anwenden", "Apply"), self._manual_apply, kind="primary", color=CYAN,
               height=32).pack(side="left", padx=(0, 6))
        button(bf, tr("Auf Standard zurücksetzen", "Reset to stock"), self._manual_reset,
               height=32).pack(side="left", padx=(0, 6))
        button(bf, tr("Als Profil speichern …", "Save as profile …"), self._manual_save,
               height=32, image=icon_image("save", TEXT, 14), compound="left").pack(side="left")
        self.lbl_manual_st = tk.Label(card.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG, anchor="w")
        self.lbl_manual_st.pack(fill="x", pady=(10, 0))

    # ── Tuner callbacks ───────────────────────────────────────────────────────

    def _on_state(self, state):
        colors = {
            TunerState.IDLE:       (DIM, "Idle"),
            TunerState.BASELINE:   (ACC, "Baseline..."),
            TunerState.STAGE1:     (ACC, "Stage 1: Core OC"),
            TunerState.STAGE2:     (ACC, "Stage 2: Power UV"),
            TunerState.STAGE3:     (ACC, "Stage 3: V/F"),
            TunerState.STAGE4:     (ACC, tr("Stufe 4: Speicher", "Stage 4: Memory")),
            TunerState.CURVE:      (ACC, tr("Kurve: Messpunkte", "Curve: points")),
            TunerState.BENCH:      (ACC, "Benchmark"),
            TunerState.FINAL_TEST: (AMBER, "Final verification"),
            TunerState.BACKOFF:    (AMBER, "Backoff"),
            TunerState.SAVING:     (GREEN, "Saving..."),
            TunerState.DONE:       (GREEN, "Done!"),
            TunerState.ERROR:      (ERR, "Error"),
            TunerState.ABORTED:    (ERR, "Aborted"),
        }
        col, text = colors.get(state, (DIM, state.name))
        def _do():
            self.lbl_state.config(text=f"● {text}", fg=col)
            done = {TunerState.DONE, TunerState.ERROR, TunerState.ABORTED, TunerState.IDLE}
            self.btn_start.configure(state="normal" if (state in done and self._tuner_ok)
                                     else "disabled")
            self.btn_abort.configure(state="disabled" if state in done else "normal")
            if state == TunerState.DONE:
                self._refresh_profiles()
            rep = getattr(self.tuner, "last_report_path", "") or ""
            self.btn_report.configure(state="normal" if (state in done and rep and os.path.exists(rep))
                                      else "disabled")
        self.after(0, _do)

    def _on_log(self, msg, level):
        tag = level if level in ("warning", "error", "success") else "info"
        if "═══" in msg or "Stage" in msg: tag = "header"
        self.log.append(msg, tag)          # queue-backed: safe from the tuner thread

    def _on_progress(self, pct, msg):
        def _do():
            if pct >= 0: self.prog_var.set(pct)
            self.lbl_prog.config(text=msg)
        self.after(0, _do)

    def _on_tick(self, s):
        def _do():
            self._ttiles["volt"].config(text=f"{s.voltage_mv:.0f}" if s.voltage_mv > 0 else "--")
            self._ttiles["temp"].config(text=str(s.temp))
            self._ttiles["clk"].config( text=f"{s.core_mhz:.0f}")
            self._ttiles["pwr"].config( text=f"{s.gpu_power_w:.0f}")
            self.live_graph.push(s.core_mhz, s.voltage_mv, float(s.temp))
        self.after(0, _do)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start_curve_tune(self):
        from core.nvtune_tuner import TuneMode
        slot, goal = self.v_ab_slot.get(), self.v_goal.get()
        mem_on = bool(self.v_mem_stage.get())
        fm = self._furmark_v2()
        self._update_furmark_status()
        step_s, fm_s, ver_s = self.v_step_dur.get(), self.v_fm_final.get() * 60, self.v_final_dur.get()
        # ~5 points x ~5 steps, AB restart ~10 s each; curve check; memory (+500 … max in
        # 100-MHz steps); ~4 benchmarks; final test
        mem_start = self._mem_start()
        mem_steps = max(1, (self.v_mem_max.get() - mem_start) // 100 + 1)
        est = (150 + 25 * (step_s + 10) + 45 + (mem_steps * (step_s + 15) if mem_on else 0)
               + 330 + fm_s + ver_s + 60)
        lo, hi = int(est * 0.8 / 60), int(est * 1.3 / 60 + 0.999)
        gname = next(tr(de, en) for gid, de, en, _d, _e in GOALS if gid == goal)
        prior, from_profile = self._curve_prior()
        try:
            volt_ok = self.monitor.read().voltage_mv > 0
        except Exception:
            volt_ok = False
        bench = (tr("FurMark 2 (Punkte)", "FurMark 2 (score)") if fm else
                 tr("interner Rechen-Benchmark (FurMark 2 nicht gefunden)",
                    "internal compute benchmark (FurMark 2 not found)"))
        start = (tr(f", Start bei +{prior} MHz (letztes stabiles Profil)",
                    f", starting at +{prior} MHz (last stable profile)") if prior and from_profile
                 else tr(f", Start bei +{prior} MHz (vorsichtiger Startwert dieser Kartengeneration)",
                         f", starting at +{prior} MHz (cautious start value of this card generation)")
                 if prior else tr(", grobe Suche ab Standard", ", coarse search from stock"))
        mem_line = (tr(f"Speicher: +{mem_start} bis +{self.v_mem_max.get()} MHz in 100er-Schritten, "
                       f"ganze Karte unter Last (FurMark + Datenprüfung), 100 MHz Sicherheit",
                       f"Memory: +{mem_start} to +{self.v_mem_max.get()} MHz in 100-MHz steps, whole "
                       f"card under load (FurMark + data check), 100 MHz safety") if mem_on else
                    tr("Speicher: wird nicht übertaktet", "Memory: not overclocked"))
        volt_line = ("" if volt_ok else "\n" + tr(
            "Hinweis: keine Spannungsanzeige (Afterburner-Monitoring 'GPU-Spannung') — die "
            "Spannung wird dann über den Takt geschätzt.",
            "Note: no voltage reading (Afterburner monitoring 'GPU voltage') — the voltage is "
            "then estimated from the clock."))
        msg = tr(
            f"Rundum-Tuner — Ziel: {gname}\n"
            f"AB-Slot {slot}  |  Core max +{self.v_core_max.get()} MHz  |  Max. Temp "
            f"{self.v_max_temp.get()} °C\n"
            f"Spannungspunkte: alle 50 mV ab der höchsten erreichten, je Schritt {step_s} s{start}\n"
            f"Benchmark: {bench}\n{mem_line}\n"
            f"Endtest: {fm_s // 60} min FurMark + {ver_s} s Rechenprüfung{volt_line}\n\n"
            f"Dauer ca. {lo}–{hi} Minuten. Afterburner startet bei jedem Schritt kurz neu (minimiert). "
            f"Während des Tests nicht spielen. Start?",
            f"All-round tuner — goal: {gname}\n"
            f"AB slot {slot}  |  Core max +{self.v_core_max.get()} MHz  |  Max temp "
            f"{self.v_max_temp.get()} °C\n"
            f"Voltage points: every 50 mV from the highest reached, {step_s} s per step{start}\n"
            f"Benchmark: {bench}\n{mem_line}\n"
            f"Final test: {fm_s // 60} min FurMark + {ver_s} s compute check{volt_line}\n\n"
            f"Takes about {lo}–{hi} minutes. Afterburner restarts briefly for every step "
            f"(minimised). Don't play during the test. Start?")
        if not messagebox.askyesno(tr("Rundum-Tuner starten", "Start all-round tuner"), msg):
            return
        cfg = TunerConfig(
            mode=TuneMode.CURVE, goal=goal, core_max_mhz=self.v_core_max.get(),
            max_temp_c=self.v_max_temp.get(), step_test_s=step_s, final_test_s=ver_s,
            final_bench_s=fm_s, curve_safety_mhz=self.v_safety.get(), curve_prior_mhz=prior,
            mem_offset_mhz=0, mem_stage=mem_on, mem_oc_max_mhz=max(100, self.v_mem_max.get()),
            mem_oc_step_mhz=250, mem_min_step_mhz=25, ab_slot=slot,
            furmark_path=fm, bench_msaa=8, mem_curve_start_mhz=mem_start,
        )
        self.tuner.config = cfg
        self.tuner.last_report_path = ""
        self.btn_report.configure(state="disabled")
        self.prog_var.set(0)
        self.live_graph.clear()
        self.tuner.start()

    def _start_tune(self):
        from core.nvtune_tuner import TuneMode
        ok, why = self._tuner_support()
        if not ok:
            messagebox.showinfo(tr("GPU-Tuner", "GPU tuner"), why)
            return
        if self.v_mode.get() == "curve":
            return self._start_curve_tune()
        slot = self.v_ab_slot.get()

        mode_map = {
            "oc_only":  TuneMode.OC_ONLY,
            "uv_only":  TuneMode.UV_ONLY,
            "oc_uv":    TuneMode.OC_UV,
            "full":     TuneMode.FULL,
            "vf_only":  TuneMode.VF_ONLY,
            "mem_only": TuneMode.MEM_ONLY,
        }
        mode     = mode_map.get(self.v_mode.get(), TuneMode.OC_UV)
        mode_str = {
            "oc_only":  "Overclock Only",
            "uv_only":  "Undervolt Only (Power)",
            "oc_uv":    "OC + Undervolt",
            "full":     "FULL Tune (OC + V/F Curve + Mem OC)",
            "vf_only":  "V/F Curve Undervolt",
            "mem_only": "Memory Overclock",
        }.get(self.v_mode.get(), "OC + UV")

        mem_on = bool(self.v_mem_stage.get())
        mem_line = (f"Speicher: bis +{self.v_mem_max.get()}MHz, Bandbreite gemessen"
                    if mem_on else "Speicher: wird nicht übertaktet")
        if not messagebox.askyesno("Start Tune",
            f"Mode: {mode_str}\n"
            f"AB Slot: {slot}\n"
            f"Core Max: +{self.v_core_max.get()}MHz  |  "
            f"Power Min: {self.v_pwr_min.get()}%  |  "
            f"Max Temp: {self.v_max_temp.get()}°C\n"
            f"{mem_line}\n\n"
            f"Dauer ca. {'30-45' if mem_on else '20-35'} Minuten. Start?"):
            return

        cfg = TunerConfig(
            mode=mode,
            core_step_mhz=self.v_core_step.get(),
            core_max_mhz=self.v_core_max.get(),
            power_min_pct=self.v_pwr_min.get(),
            max_temp_c=self.v_max_temp.get(),
            step_test_s=self.v_step_dur.get(),
            final_test_s=self.v_final_dur.get(),
            mem_offset_mhz=0,
            mem_stage=mem_on,
            mem_oc_max_mhz=max(100, self.v_mem_max.get()),
            mem_oc_step_mhz=250,        # coarse first, halved on the first drop ...
            mem_min_step_mhz=25,        # ... down to ±25 MHz (5 would add minutes for nothing)
            ab_slot=slot,
        )
        self.tuner.config = cfg
        self.prog_var.set(0)
        self.live_graph.clear()
        self.tuner.start()

    def _abort_tune(self):
        if messagebox.askyesno("Abort", "Abort and reset GPU to stock?"):
            # abort() waits for an in-flight Afterburner write and then resets
            # (Afterburner load ~1.5 s) — run it off the UI thread so the
            # window doesn't freeze.
            self.btn_abort.configure(state="disabled")
            threading.Thread(target=self.tuner.abort, daemon=True).start()

    def _refresh_profiles(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for p in self.pm.list_all():
            if p.name.startswith("__"): continue
            self.tree.insert("", "end", iid=p.name, values=(
                p.name, tr("Kurve", "Curve") if p.curve_points else f"+{p.core_offset_mhz}",
                f"+{p.mem_offset_mhz}",
                f"{p.power_limit_pct}%",
                f"{p.stage1_voltage:.0f}" if p.stage1_voltage else "--",
                str(p.stability_score), "✓" if p.is_stable else "⚠",
                (p.notes[:55] + "…") if len(p.notes) > 55 else p.notes,
            ))

    def _on_profile_select(self, _):
        sel = self.tree.selection()
        if not sel: return
        p = self.pm.load(sel[0])
        if p:
            curve = ""
            if p.curve_points:
                pts = " · ".join(f"{mv} mV → {f} MHz" for mv, f in sorted(p.curve_points, reverse=True))
                curve = (tr("\nKurve: ", "\nCurve: ") + pts
                         + (tr(f" · flach ab {p.curve_cap_mv} mV", f" · flat from {p.curve_cap_mv} mV")
                            if p.curve_cap_mv else ""))
            self.lbl_detail.config(text=(
                (f"Core: {tr('Kurve', 'curve')} (+{p.core_offset_mhz}MHz {tr('oben', 'at the top')})  "
                 if p.curve_points else f"Core: +{p.core_offset_mhz}MHz  ")
                + f"Mem: +{p.mem_offset_mhz}MHz  "
                f"Power: {p.power_limit_pct}%  AvgVolt: {p.stage1_voltage or '--'}mV  "
                f"Score: {p.stability_score}/100  GPU: {p.gpu_name}" + curve
            ), fg=TEXT2)

    def _run_ab(self, work, done) -> bool:
        """Run an Afterburner action off the UI thread — it closes and restarts
        Afterburner, which takes a few seconds. done(result) runs on the UI thread."""
        if getattr(self, "_ab_busy", False):
            messagebox.showinfo("Afterburner", "An Afterburner action is still running.")
            return False
        if self.tuner.is_running:
            messagebox.showwarning("Afterburner", "Auto-Tune is running — abort it first.")
            return False
        self._ab_busy = True

        def _worker():
            try:
                res = work()
            except Exception as e:
                res = (False, str(e))

            def _finish():
                self._ab_busy = False
                done(res)
            try:
                self.after(0, _finish)
            except Exception:
                self._ab_busy = False     # window already gone
        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _apply_profile(self):
        sel = self.tree.selection()
        if not sel: return messagebox.showwarning("", "Select a profile first.")
        p = self.pm.load(sel[0])
        if not p: return
        slot = self.v_ab_slot.get()

        def done(res):
            ok, err = res
            if ok:
                notes = "\n".join(self.ab.last_notes)
                messagebox.showinfo("Applied", f"'{p.name}' applied (Afterburner slot {slot})."
                                    + (f"\n\n{notes}" if notes else ""))
            else:
                messagebox.showerror("Error", err)
        if self._run_ab(lambda: self.ab.write_and_apply(slot, p), done):
            self.lbl_detail.config(text=f"Applying '{p.name}' via Afterburner …", fg=DIM)

    def _set_tray_default(self):
        sel = self.tree.selection()
        if not sel: return
        p = self.pm.load(sel[0])
        if p: self.pm.set_tray_default(p); messagebox.showinfo("OK", "Tray default set.")

    def _delete_profile(self):
        sel = self.tree.selection()
        if not sel: return
        if messagebox.askyesno("Delete", f"Delete '{sel[0]}'?"):
            self.pm.delete(sel[0]); self._refresh_profiles()

    def _manual_apply(self):
        p = TuneProfile(name="Manual", core_offset_mhz=self.v_m_core.get(),
                        mem_offset_mhz=self.v_m_mem.get(),
                        power_limit_pct=self.v_m_pwr.get())
        slot = self.v_ab_slot.get()

        def done(res):
            ok, err = res
            self.lbl_manual_st.config(
                text=(f"{'Applied' if ok else f'Error: {err}'} — Core {p.core_offset_mhz:+d} "
                      f"Mem {p.mem_offset_mhz:+d} Pwr {p.power_limit_pct}% (slot {slot})"),
                fg=GREEN if ok else ERR)
        if self._run_ab(lambda: self.ab.write_and_apply(slot, p), done):
            self.lbl_manual_st.config(text="Applying via Afterburner …", fg=DIM)

    def _manual_reset(self):
        self.v_m_core.set(0); self.v_m_mem.set(0)
        self.v_m_pwr.set(100)
        slot = self.v_ab_slot.get()

        def work():
            res = self.ab.reset_to_stock(slot)
            watts = self.monitor.power_pct_to_watts(100)   # factory limit, not the maximum
            if watts > 0:
                self.monitor.set_power_limit(watts)
            return res

        def done(res):
            ok, err = res
            self.lbl_manual_st.config(text="Reset to stock." if ok else f"Error: {err}",
                                      fg=GREEN if ok else ERR)
        if self._run_ab(work, done):
            self.lbl_manual_st.config(text="Resetting via Afterburner …", fg=DIM)

    def _manual_save(self):
        name = ctk.CTkInputDialog(title=tr("Profil speichern", "Save profile"),
                                  text=tr("Name des Profils:", "Profile name:")).get_input()
        if not name: return
        p = TuneProfile(name=name, core_offset_mhz=self.v_m_core.get(),
                        mem_offset_mhz=self.v_m_mem.get(),
                        power_limit_pct=self.v_m_pwr.get(), notes="Manual",
                        created_at=datetime.now().isoformat())
        self.pm.save(p); self._refresh_profiles()
        messagebox.showinfo("Saved", f"'{name}' saved.")
