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
from ui.components import (Card, CheckBox, HelpTip, LogView, NumberField, Page, ResponsiveGrid, Table,
                           WrapLabel, button, param_cell, scroll_area, tile)
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
     "Neu und am gründlichsten (50–80 min) — misst die V/F-Kurve alle 25 mV Punkt für Punkt "
     "(wie HYDRA), baut daraus eine eigene Kurve, vergleicht per FurMark-Benchmark und wählt nach "
     "dem Ziel. Endtest: 5 min FurMark + Rechenprüfung, danach ein Bericht.",
     "New and most thorough (50–80 min) — measures the V/F curve point by point every 25 mV "
     "(like HYDRA), builds an own curve from it, compares with FurMark benchmarks and picks "
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


# Parameter names and their "?" explanations (German, English). The same names
# are used in the start dialogs and the report.
H_TEMP = ("Temperatur-Grenze (°C)", "Temperature limit (°C)",
          "Erreicht die Grafikkarte diese Temperatur, wird der laufende Testschritt sofort beendet und "
          "als „zu heiß“ gewertet — der Tuner geht danach vorsichtiger weiter.",
          "If the graphics card reaches this temperature, the running test step ends at once and counts "
          "as 'too hot' — the tuner continues more carefully.")
H_STEP_TIME = ("Testdauer je Schritt (s)", "Test time per step (s)",
               "So lange läuft jeder einzelne Testschritt (jede Taktstufe, jede Speicherstufe). Länger "
               "findet seltene Fehler eher, der Tune dauert aber länger.",
               "How long every single test step runs (each clock step, each memory step). Longer finds "
               "rare errors more often, but the tune takes longer.")
H_MEM_MAX = ("Speicher-Plus max. (MHz)", "Max memory gain (MHz)",
             "Höchster Speicher-Offset, der getestet wird. Ablauf: Start mit einem vorsichtigen Wert "
             "(RTX 40: +500), dann in 100er-Schritten bis zu diesem Wert — jeder Schritt mit FurMark und "
             "geprüften Speicherkopien gleichzeitig. Übernommen wird der höchste bestandene Schritt, "
             "100 MHz darunter, wenn ein Schritt scheiterte.",
             "Highest memory offset that is tested. It starts at a cautious value (RTX 40: +500) and goes "
             "up in 100-MHz steps to this value — every step with FurMark and verified memory copies at "
             "once. Used: the highest step that passed, 100 MHz lower if a step failed.")
H_SLOT = ("Afterburner-Profilplatz (2–5)", "Afterburner profile slot (2–5)",
          "In welchen der fünf Profilplätze von MSI Afterburner das Ergebnis geschrieben wird. Platz 1 "
          "bleibt für deine eigenen Einstellungen.",
          "Which of MSI Afterburner's five profile slots the result is written to. Slot 1 stays yours.")
H_MEM_STAGE = ("Wird der Haken entfernt, bleibt der Grafikspeicher auf Standard und nur der Kern-Takt "
               "wird eingestellt (spart ca. 6–10 Minuten).",
               "Unticked, the video memory stays at stock and only the core clock is set (saves about "
               "6–10 minutes).")


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
                           tr("Manuell", "Manual"): "manual", tr("Verlauf", "History"): "history"}
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
                             ("manual", self._build_manual), ("history", self._build_history)):
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
        if key == "history":
            self.history.ensure_loaded()

    def _build_history(self, p):
        """All Auto-Tune runs (was a part of the removed "Games & history" page)."""
        from ui.tune_history_view import TuneHistoryView
        self.history = TuneHistoryView(p, getattr(self.tuner, "_log_dir", "logs"))
        self.history.pack(fill="both", expand=True)

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
        self.v_point_mv  = tk.IntVar(value=25)     # voltage point spacing: 25 = finer, 50 = faster

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
        for (de, en, hde, hen), var, lo, hi, step in (
            (("Takt-Schritt (MHz)", "Clock step (MHz)",
              "Um so viele MHz wird der Kern-Takt (Core-Offset) je Testschritt erhöht. Nach einem Fehler "
              "geht es zurück zum letzten stabilen Wert und der Schritt wird halbiert, bis 5 MHz.",
              "The core clock offset goes up by this many MHz per test step. After a failure it goes "
              "back to the last stable value and the step is halved, down to 5 MHz."),
             self.v_core_step, 5, 50, 5),
            (("Takt-Plus max. (MHz)", "Max clock gain (MHz)",
              "Höchster Core-Offset (MHz über dem Werkstakt), der getestet wird — die Obergrenze der "
              "Suche. Vorgabe je Kartengeneration.",
              "Highest core offset (MHz above the factory clock) that is tested — the upper bound of "
              "the search. Preset per card generation."),
             self.v_core_max, 0, 500, 15),
            (("Power-Limit min. (%)", "Min power limit (%)",
              "So weit darf das Power-Limit beim Undervolten höchstens sinken (in 5-%-Schritten). "
              "Gesucht wird das niedrigste Limit, das höchstens 3 % Leistung kostet.",
              "The power limit may go down this far at most when undervolting (in 5 % steps). The "
              "search looks for the lowest limit that costs at most 3 % performance."),
             self.v_pwr_min, 50, 100, 5),
            (H_TEMP, self.v_max_temp, 70, 95, 1),
            (H_STEP_TIME, self.v_step_dur, 15, 300, 15),
            (("Endtest (s)", "Final test (s)",
              "Abschlusstest mit genau der Einstellung, die gespeichert wird (spielähnliche Wechsellast, "
              "jedes Ergebnis geprüft). Fällt er durch, nimmt der Tuner einen Schritt zurück und testet "
              "erneut — gespeichert wird nur, was bestanden hat.",
              "Final test with exactly the setting that is saved (game-like alternating load, every "
              "result checked). If it fails, the tuner takes one step back and tests again — only what "
              "passed is saved."),
             self.v_final_dur, 60, 600, 30),
            (H_MEM_MAX, self.v_mem_max, 100, 3000, 100),
            (H_SLOT, self.v_ab_slot, 2, 5, 1),
        ):
            grid.add(param_cell(grid, tr(de, en), var, lo, hi, step, tr(hde, hen)))

        # Memory stage: searched with the whole card under load (as in the Rundum
        # mode) — not a fixed guess, and not the bandwidth peak of a memory-only load.
        mem = tk.Frame(params.body, bg=CARD_BG)
        mem.pack(fill="x", pady=(12, 0))
        mrow = tk.Frame(mem, bg=CARD_BG)
        mrow.pack(fill="x")
        self.chk_mem_stage = CheckBox(mrow, self.v_mem_stage, accent=CYAN, bg=CARD_BG,
                                      text=tr("Speicher mit übertakten", "Overclock memory too"), font=F_BB)
        self.chk_mem_stage.pack(side="left")
        HelpTip(mrow, tr(H_MEM_MAX[2] + " " + H_MEM_STAGE[0], H_MEM_MAX[3] + " " + H_MEM_STAGE[1]),
                bg=CARD_BG).pack(side="left", padx=(6, 0))
        WrapLabel(mem, text=tr(
            "Wie im Rundum-Modus: +500, dann 100er-Schritte bis „Speicher-Plus max.“, jeder Schritt mit "
            "der ganzen Karte unter Last. Dauert ca. 6–10 min länger.",
            "As in the All-round mode: +500, then 100-MHz steps up to 'Max memory gain', every step "
            "with the whole card under load. Takes about 6–10 min longer."),
            font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(4, 0))
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
        for (de, en, hde, hen), var, lo, hi, step in (
            (("Takt-Plus max. je Punkt (MHz)", "Max clock gain per point (MHz)",
              "Obergrenze der Suche: So viele MHz über dem Werkstakt darf ein Spannungspunkt höchstens "
              "bekommen. Gesucht wird in +15-MHz-Schritten bis zum ersten Fehler, dann halbiert "
              "(+7, +5 MHz) — diese Grenze fängt nur unsinnige Werte ab. Vorgabe je Kartengeneration "
              "(RTX 4080: +350).",
              "Upper bound of the search: at most this many MHz above the factory clock per voltage "
              "point. The search goes up in +15 MHz steps to the first failure, then halved (+7, "
              "+5 MHz) — this bound only catches absurd values. Preset per card generation "
              "(RTX 4080: +350)."),
             self.v_core_max, 0, 600, 15),
            (H_TEMP, self.v_max_temp, 70, 95, 1),
            (H_STEP_TIME, self.v_step_dur, 15, 300, 15),
            (("Abstand der Messpunkte (mV)", "Spacing of measured points (mV)",
              "Alle wie viel Millivolt ein Punkt der Spannungs-/Takt-Kurve einzeln gemessen wird — von "
              "der höchsten erreichten Spannung bis 850 mV; dazwischen wird die Kurve verbunden. "
              "25 = genauer (RTX 4080: ca. 8 Punkte), 50 = schneller (ca. 5 Punkte). Punkte unter der "
              "Mindestspannung der Karte werden übersprungen.",
              "Every how many millivolts a point of the voltage/clock curve is measured on its own — "
              "from the highest voltage reached down to 850 mV; in between the curve is joined. "
              "25 = finer (RTX 4080: about 8 points), 50 = faster (about 5 points). Points below the "
              "card's minimum voltage are skipped."),
             self.v_point_mv, 25, 50, 25),
            (("Sicherheitsabzug (MHz)", "Safety margin (MHz)",
              "Wird vom höchsten stabil gefundenen Takt jedes Punkts abgezogen — Reserve für Spiele, die "
              "anders belasten, und für kalte Starts. Wo der Treiber während der Suche neu starten "
              "musste, doppelt so viel.",
              "Taken off the highest stable clock found at every point — headroom for games that load "
              "the card differently and for cold starts. Doubled where the driver had to restart "
              "during the search."),
             self.v_safety, 15, 90, 15),
            (("Endtest: FurMark (min)", "Final test: FurMark (min)",
              "Zum Schluss läuft die gewählte Einstellung so lange unter FurMark (volle Grafiklast, mit "
              "Speicher-Übertaktung). Fällt sie durch, nimmt der Tuner gezielt einen Schritt zurück und "
              "testet erneut — gespeichert wird nur, was bestanden hat.",
              "At the end the chosen setting runs this long under FurMark (full graphics load, with the "
              "memory overclock). If it fails, the tuner takes one targeted step back and tests again "
              "— only what passed is saved."),
             self.v_fm_final, 1, 15, 1),
            (("Endtest: Rechenprüfung (s)", "Final test: compute check (s)",
              "Danach so lange eine Rechenlast, deren Ergebnisse verglichen werden — schon ein einziger "
              "falscher Wert lässt den Test durchfallen. Findet Instabilität, bevor ein Spiel abstürzt.",
              "Then a compute load this long whose results are compared — a single wrong value fails "
              "the test. Finds instability before a game crashes."),
             self.v_final_dur, 60, 600, 30),
            (H_MEM_MAX, self.v_mem_max, 100, 3000, 100),
            (H_SLOT, self.v_ab_slot, 2, 5, 1),
        ):
            grid.add(param_cell(grid, tr(de, en), var, lo, hi, step, tr(hde, hen)))
        memf = tk.Frame(cp.body, bg=CARD_BG)
        memf.pack(fill="x", pady=(12, 0))
        CheckBox(memf, self.v_mem_stage, accent=CYAN, bg=CARD_BG,
                 text=tr("Speicher mit übertakten", "Overclock memory too"), font=F_BB).pack(side="left")
        HelpTip(memf, tr(H_MEM_MAX[2] + " " + H_MEM_STAGE[0], H_MEM_MAX[3] + " " + H_MEM_STAGE[1]),
                bg=CARD_BG).pack(side="left", padx=(6, 0))

        # the whole procedure with the current values (updates while they change)
        steps = tk.Frame(cp.body, bg=CARD_BG2)
        steps.pack(fill="x", pady=(12, 0))
        tk.Label(steps, text=tr("SO LÄUFT DER TUNE", "HOW THE TUNE RUNS"), font=("Segoe UI Semibold", 8),
                 fg=MUTED, bg=CARD_BG2, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_curve_steps = WrapLabel(steps, text="", font=F_XS, fg=TEXT2, bg=CARD_BG2)
        self.lbl_curve_steps.pack(fill="x", padx=10, pady=(0, 8))
        for v in (self.v_point_mv, self.v_step_dur, self.v_safety, self.v_mem_max, self.v_fm_final,
                  self.v_final_dur, self.v_core_max, self.v_mem_stage):
            v.trace_add("write", lambda *_a: self._update_curve_steps())
        self._update_curve_steps()
        self._update_furmark_status()

    def _update_curve_steps(self):
        """The Rundum procedure, step by step, with the values set right now."""
        def val(var, default):
            try:
                return int(var.get())
            except (tk.TclError, ValueError):
                return default
        pmv, step_s = val(self.v_point_mv, 25), val(self.v_step_dur, 45)
        safety, mem_max = val(self.v_safety, 30), val(self.v_mem_max, 1000)
        fm, ver, cmax = val(self.v_fm_final, 5), val(self.v_final_dur, 120), val(self.v_core_max, 350)
        try:
            mem_on = bool(self.v_mem_stage.get())
        except tk.TclError:
            mem_on = True
        try:
            mem_start = self._mem_start()
        except Exception:
            mem_start = 500
        mem_de = (f"4. Speicher: +{mem_start} MHz, dann +100er-Schritte bis +{mem_max} MHz — je Schritt "
                  f"{step_s} s FurMark + geprüfte Speicherkopien; übernommen: höchster bestandener Schritt"
                  if mem_on else "4. Speicher: bleibt auf Standard (Haken aus)")
        mem_en = (f"4. Memory: +{mem_start} MHz, then +100 MHz steps up to +{mem_max} MHz — {step_s} s "
                  f"of FurMark + verified memory copies per step; used: the highest step that passed"
                  if mem_on else "4. Memory: stays at stock (unticked)")
        self.lbl_curve_steps.config(text=tr(
            f"1. Standard messen: Boost-Last + 60 s FurMark-Benchmark (der Vergleichswert)\n"
            f"2. Kurve: alle {pmv} mV ein Punkt, von der höchsten erreichten Spannung bis 850 mV. "
            f"Je Punkt +15 MHz, bis ein Fehler kommt, dann +7 / +5 MHz (höchstens +{cmax} MHz), "
            f"{step_s} s je Schritt. Übernommen: gefundener Takt − {safety} MHz\n"
            f"3. Kurven-Check: 30 s FurMark mit der neuen Kurve\n"
            f"{mem_de}\n"
            f"5. Vergleich: 60 s FurMark je Kurven-Variante — Auswahl nach dem Ziel\n"
            f"6. Endtest: {fm} min FurMark + {ver} s Rechenprüfung → Profil + Bericht",
            f"1. Measure stock: boost load + 60 s FurMark benchmark (the reference)\n"
            f"2. Curve: a point every {pmv} mV, from the highest voltage reached down to 850 mV. "
            f"Per point +15 MHz until a failure, then +7 / +5 MHz (at most +{cmax} MHz), "
            f"{step_s} s per step. Used: the clock found − {safety} MHz\n"
            f"3. Curve check: 30 s FurMark on the new curve\n"
            f"{mem_en}\n"
            f"5. Compare: 60 s FurMark per curve variant — picked by the goal\n"
            f"6. Final test: {fm} min FurMark + {ver} s compute check → profile + report"))

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
                     + tr(f"Vorgaben: Takt-Plus max. +{d.core_max_mhz} MHz, Speicher-Plus max. "
                          f"+{d.mem_max_mhz} MHz, Power-Limit min. {d.power_min_pct} %, Temperatur-Grenze "
                          f"{d.max_temp_c} °C",
                          f"Defaults: max clock gain +{d.core_max_mhz} MHz, max memory gain "
                          f"+{d.mem_max_mhz} MHz, min power limit {d.power_min_pct} %, temperature limit "
                          f"{d.max_temp_c} °C")
                     + (tr(f"  ·  Rundum: Start Takt +{d.core_start_mhz}, Speicher +{d.mem_start_mhz}, "
                           f"Takt-Plus max. je Punkt +{d.curve_core_max_mhz}",
                           f"  ·  All-round: start clock +{d.core_start_mhz}, memory +{d.mem_start_mhz}, "
                           f"max clock gain per point +{d.curve_core_max_mhz}")
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
                self.v_core_max.set(d.curve_core_max_mhz)   # per point, searched to a failure
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
            if state in done and state != TunerState.IDLE and self.history._loaded:
                self.history.refresh()
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
        # Points (RTX 40: 1075 … 850 mV) x steps each, AB restart ~10 s per step: ~5 steps at
        # 50 mV, ~4 at 25 mV (a point starts at its neighbour's result); curve check; memory
        # (+500 … max in 100-MHz steps); ~4 benchmarks; final test
        pmv = max(25, min(100, self.v_point_mv.get()))
        n_pts = (1075 - 850) // pmv + 1
        per_pt = 5 if pmv >= 50 else 4
        mem_start = self._mem_start()
        mem_steps = max(1, (self.v_mem_max.get() - mem_start) // 100 + 1)
        est = (150 + n_pts * per_pt * (step_s + 10) + 45
               + (mem_steps * (step_s + 15) if mem_on else 0) + 330 + fm_s + ver_s + 60)
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
            f"Afterburner-Profilplatz {slot}  |  Takt-Plus max. je Punkt +{self.v_core_max.get()} MHz  |  "
            f"Temperatur-Grenze {self.v_max_temp.get()} °C\n"
            f"Messpunkte: alle {pmv} mV ab der höchsten erreichten Spannung, Testdauer je Schritt "
            f"{step_s} s, Sicherheitsabzug {self.v_safety.get()} MHz{start}\n"
            f"Benchmark: {bench}\n{mem_line}\n"
            f"Endtest: {fm_s // 60} min FurMark + {ver_s} s Rechenprüfung{volt_line}\n\n"
            f"Dauer ca. {lo}–{hi} Minuten. Afterburner startet bei jedem Schritt kurz neu (minimiert). "
            f"Während des Tests nicht spielen. Start?",
            f"All-round tuner — goal: {gname}\n"
            f"Afterburner profile slot {slot}  |  Max clock gain per point +{self.v_core_max.get()} MHz  |  "
            f"Temperature limit {self.v_max_temp.get()} °C\n"
            f"Measured points: every {pmv} mV from the highest voltage reached, test time per step "
            f"{step_s} s, safety margin {self.v_safety.get()} MHz{start}\n"
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
            ab_slot=slot, furmark_path=fm, bench_msaa=8, mem_curve_start_mhz=mem_start,
            curve_anchor_step_mv=pmv,
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
        fm = self._furmark_v2() if mem_on else ""
        mem_start = self._mem_start()
        load = (tr("FurMark + Datenprüfung", "FurMark + data check") if fm else
                tr("Datenprüfung — FurMark 2 nicht gefunden", "data check — FurMark 2 not found"))
        mem_line = (tr(f"Speicher: +{mem_start} bis +{self.v_mem_max.get()} MHz in 100er-Schritten, "
                       f"ganze Karte unter Last ({load}), 100 MHz Sicherheit",
                       f"Memory: +{mem_start} to +{self.v_mem_max.get()} MHz in 100-MHz steps, whole "
                       f"card under load ({load}), 100 MHz safety")
                    if mem_on else tr("Speicher: wird nicht übertaktet", "Memory: not overclocked"))
        if not messagebox.askyesno(tr("Tune starten", "Start tune"),
            tr(f"Modus: {mode_str}\n"
               f"Afterburner-Profilplatz: {slot}\n"
               f"Takt-Schritt {self.v_core_step.get()} MHz  |  Takt-Plus max. +{self.v_core_max.get()} MHz  |  "
               f"Power-Limit min. {self.v_pwr_min.get()} %  |  Temperatur-Grenze {self.v_max_temp.get()} °C\n"
               f"Testdauer je Schritt {self.v_step_dur.get()} s  |  Endtest {self.v_final_dur.get()} s\n",
               f"Mode: {mode_str}\n"
               f"Afterburner profile slot: {slot}\n"
               f"Clock step {self.v_core_step.get()} MHz  |  Max clock gain +{self.v_core_max.get()} MHz  |  "
               f"Min power limit {self.v_pwr_min.get()} %  |  Temperature limit {self.v_max_temp.get()} °C\n"
               f"Test time per step {self.v_step_dur.get()} s  |  Final test {self.v_final_dur.get()} s\n")
            + f"{mem_line}\n"
            + (tr("FurMark-Fenster gehen bei den Speicher-Schritten auf — nicht schließen.\n",
                  "FurMark windows open during the memory steps — don't close them.\n") if fm else "")
            + tr(f"\nDauer ca. {'30-45' if mem_on else '20-35'} Minuten. Start?",
                 f"\nTakes about {'30-45' if mem_on else '20-35'} minutes. Start?")):
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
            mem_curve_start_mhz=mem_start,   # whole-card stage: cautious start, 100-MHz steps
            furmark_path=fm, bench_msaa=8,   # FurMark during every memory step
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
