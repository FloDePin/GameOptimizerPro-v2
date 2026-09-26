"""GameOptimizerPro GPU Tuner Tab — NVTuner v2 embedded."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading, time, os, sys
from datetime import datetime
from typing import Optional

from ui.widgets import *
from core.nvtune_core import GpuMonitor, AfterburnerController, TuneProfile, ProfileManager
from core.nvtune_tuner import AutoTuner, TunerConfig, TunerState

# Fix import path for stress worker
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class GpuTunerTab(tk.Frame):
    def __init__(self, parent, monitor: GpuMonitor, ab: AfterburnerController,
                 pm: ProfileManager, tuner: AutoTuner, **kw):
        super().__init__(parent, bg=BG1, **kw)
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
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # Sub-tabs
        tabs = [
            ("  Auto-Tune  ", self._build_autotune),
            ("  Profiles  ",  self._build_profiles),
            ("  Manual  ",    self._build_manual),
        ]
        for label, builder in tabs:
            f = tk.Frame(nb, bg=BG1)
            nb.add(f, text=label)
            builder(f)

    # ── Auto-Tune ─────────────────────────────────────────────────────────────

    def _build_autotune(self, p):
        # ── Mode selector ─────────────────────────────────────────────────────
        mode_f = tk.Frame(p, bg=BG1)
        mode_f.pack(fill="x", padx=12, pady=(12, 4))

        tk.Label(mode_f, text="Tune Mode", font=FH, fg=WHT, bg=BG1).pack(anchor="w")

        btn_row = tk.Frame(mode_f, bg=BG1)
        btn_row.pack(fill="x", pady=(6, 0))

        self.v_mode = tk.StringVar(value="oc_uv")

        mode_defs = [
            ("oc_only",
             "⚡ Overclock Only",
             "Max stable core offset\nPower limit stays at 100%\nMore FPS, same temps",
             ACC),
            ("uv_only",
             "❄ Undervolt Only",
             "Min stable power limit\nCore offset stays at 0\nCooler & quieter at stock speed",
             VOLT),
            ("oc_uv",
             "🚀 OC + UV  (Recommended)",
             "Best of both:\nHigher frequency, lower temps\nSame or better performance",
             OK),
        ]

        self._mode_btns = {}
        for i, (mode_id, label, desc, color) in enumerate(mode_defs):
            btn_row.columnconfigure(i, weight=1)
            f = tk.Frame(btn_row, bg=BG2, padx=10, pady=8, cursor="hand2")
            f.grid(row=0, column=i, padx=4, sticky="nsew")

            # Highlight selected
            def _select(mid=mode_id):
                self.v_mode.set(mid)
                self._highlight_mode_btns()
                self._apply_mode_to_config(mid)

            f.bind("<Button-1>", lambda e, fn=_select: fn())
            for w in f.winfo_children() if hasattr(f, 'winfo_children') else []:
                w.bind("<Button-1>", lambda e, fn=_select: fn())

            name_lbl = tk.Label(f, text=label, font=("Segoe UI", 9, "bold"),
                                fg=color, bg=BG2, anchor="w")
            name_lbl.pack(anchor="w")
            name_lbl.bind("<Button-1>", lambda e, fn=_select: fn())

            desc_lbl = tk.Label(f, text=desc, font=("Segoe UI", 8),
                                fg=DIM, bg=BG2, anchor="w", justify="left")
            desc_lbl.pack(anchor="w", pady=(2, 0))
            desc_lbl.bind("<Button-1>", lambda e, fn=_select: fn())

            self._mode_btns[mode_id] = (f, color)

        self._highlight_mode_btns()

        # ── IntVars MUST be created before _show_gpu_defaults() which calls .set() ──
        self.v_core_step = tk.IntVar(value=15)
        self.v_core_max  = tk.IntVar(value=200)
        self.v_pwr_min   = tk.IntVar(value=70)
        self.v_max_temp  = tk.IntVar(value=85)
        self.v_step_dur  = tk.IntVar(value=45)
        self.v_final_dur = tk.IntVar(value=120)
        self.v_mem_off   = tk.IntVar(value=0)
        self.v_ab_slot   = tk.IntVar(value=2)

        # ── GPU defaults info bar (uses IntVars above — must come after) ──────
        self.lbl_gpu_defaults = tk.Label(
            p, text="", font=FM, fg=DIM, bg=BG2,
            anchor="w", padx=10, pady=5
        )
        self.lbl_gpu_defaults.pack(fill="x", padx=12, pady=(4, 0))
        self._show_gpu_defaults()

        # ── Config spinboxes ──────────────────────────────────────────────────
        cfg_f = tk.Frame(p, bg=BG2)
        cfg_f.pack(fill="x", padx=12, pady=(4, 4))
        SecHdr(cfg_f, "Fine-tune Parameters (auto-filled from GPU)").pack(
            fill="x", padx=6, pady=(8, 6))

        grid = tk.Frame(cfg_f, bg=BG2)
        grid.pack(fill="x", padx=8, pady=(0, 10))
        for i in range(4): grid.columnconfigure(i, weight=1)

        def spn(parent, label, var, lo, hi, row, col):
            tk.Label(parent, text=label, font=FL, fg=DIM, bg=BG2).grid(
                row=row * 2, column=col, sticky="w", padx=6, pady=(4, 0))
            sb = tk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                            width=7, font=FM, bg=BG3, fg=TXT,
                            insertbackground=ACC, buttonbackground=BG3,
                            relief="flat", highlightthickness=1,
                            highlightcolor=BOR2, highlightbackground=BOR)
            sb.grid(row=row * 2 + 1, column=col, sticky="w", padx=6, pady=(0, 6))
            return sb

        spn(grid, "Core Step (MHz)", self.v_core_step,  5,  50, 0, 0)
        spn(grid, "Core Max (MHz)",  self.v_core_max,  30, 500, 0, 1)
        spn(grid, "Power Min (%)",   self.v_pwr_min,   50, 100, 0, 2)
        spn(grid, "Max Temp (°C)",   self.v_max_temp,  70,  95, 0, 3)
        spn(grid, "Step Test (s)",   self.v_step_dur,  15, 300, 1, 0)
        spn(grid, "Final Test (s)",  self.v_final_dur, 60, 600, 1, 1)
        spn(grid, "Mem Offset (MHz)",self.v_mem_off, -500,1000, 1, 2)
        spn(grid, "AB Slot (2-5)",   self.v_ab_slot,   2,   5, 1, 3)

        # ── Controls ──────────────────────────────────────────────────────────
        ctrl = tk.Frame(p, bg=BG1)
        ctrl.pack(fill="x", padx=12, pady=4)
        self.btn_start = mk_btn(ctrl, "▶  START TUNE", self._start_tune,
                                ACC, "#000", bold=True)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_abort = mk_btn(ctrl, "■  ABORT", self._abort_tune, ERR, WHT)
        self.btn_abort.config(state="disabled")
        self.btn_abort.pack(side="left")
        self.lbl_state = tk.Label(ctrl, text="Idle", font=FM, fg=DIM, bg=BG1)
        self.lbl_state.pack(side="right")

        # Live tiles
        live_f = tk.Frame(p, bg=BG2)
        live_f.pack(fill="x", padx=12, pady=(4, 0))
        live_f.columnconfigure((0, 1, 2, 3), weight=1)
        self._ttiles = {}
        for i, (key, label, unit, color) in enumerate([
            ("volt", "Voltage", "mV", VOLT),
            ("temp", "Temp",    "°C", ERR),
            ("clk",  "Clock",   "MHz",ACC),
            ("pwr",  "Power",   "W",  WRN),
        ]):
            f, vl = mk_tile(live_f, label, "--", color, unit)
            f.grid(row=0, column=i, padx=3, pady=4, sticky="nsew")
            self._ttiles[key] = vl

        # Live graph
        from ui.live_graph import LiveGraph
        self.live_graph = LiveGraph(p, height=130)
        self.live_graph.pack(fill="x", padx=12, pady=(4, 0))

        # Progress
        pf = tk.Frame(p, bg=BG1)
        pf.pack(fill="x", padx=12, pady=4)
        self.prog_var = tk.DoubleVar()
        ttk.Progressbar(pf, variable=self.prog_var, maximum=100).pack(fill="x")
        self.lbl_prog = tk.Label(pf, text="", font=FM, fg=DIM, bg=BG1)
        self.lbl_prog.pack(anchor="w", pady=2)

        # Log — fixed height at bottom, always visible
        sep = tk.Frame(p, bg="#2d333b", height=1)
        sep.pack(side="bottom", fill="x")
        self.log = LogBox(p)
        self.log.pack(side="bottom", fill="x", padx=12, pady=(2, 6))
        self.log.txt.configure(height=5)
        self.log.configure(height=90)
        self.log.txt.tag_config("header", foreground=ACC)
        SecHdr(p, "Tuner Log").pack(side="bottom", fill="x", padx=12)

    def _highlight_mode_btns(self):
        selected = self.v_mode.get()
        for mode_id, (frame, color) in self._mode_btns.items():
            if mode_id == selected:
                frame.config(bg=BG3, highlightthickness=2,
                             highlightbackground=color, relief="solid")
                for child in frame.winfo_children():
                    child.config(bg=BG3)
            else:
                frame.config(bg=BG2, highlightthickness=0, relief="flat")
                for child in frame.winfo_children():
                    child.config(bg=BG2)

    def _show_gpu_defaults(self):
        """Load GPU defaults and populate spinboxes."""
        try:
            from core.gpu_defaults import get_defaults
            gpu_name = self.monitor.read().name
            d = get_defaults(gpu_name)

            # Fill spinboxes with generation-appropriate defaults
            self.v_core_step.set(d.core_step_mhz)
            self.v_core_max.set( d.core_max_mhz)
            self.v_pwr_min.set(  d.power_min_pct)
            self.v_max_temp.set( d.max_temp_c)

            self.lbl_gpu_defaults.config(
                text=f"GPU: {gpu_name[:40]}  |  Gen: {d.generation}  |  "
                     f"Defaults: Core max +{d.core_max_mhz}MHz, Power min {d.power_min_pct}%, Temp limit {d.max_temp_c}°C",
                fg=ACC
            )
        except Exception as e:
            self.lbl_gpu_defaults.config(
                text=f"GPU detection: {e} — using conservative defaults", fg=WRN)

    def _apply_mode_to_config(self, mode_id: str):
        """When mode changes, adjust visible defaults."""
        try:
            from core.gpu_defaults import get_defaults
            gpu_name = self.monitor.read().name
            d = get_defaults(gpu_name)

            if mode_id == "oc_only":
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(100)
            elif mode_id == "uv_only":
                self.v_core_max.set(0)
                self.v_pwr_min.set(d.power_min_pct)
            elif mode_id in ("full", "vf_only"):
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(100)  # VF curve handles UV, not power limit
            elif mode_id == "mem_only":
                self.v_core_max.set(0)
                self.v_pwr_min.set(100)
            else:  # oc_uv
                self.v_core_max.set(d.core_max_mhz)
                self.v_pwr_min.set(d.power_min_pct)
        except:
            pass

    # ── Profiles ──────────────────────────────────────────────────────────────

    def _build_profiles(self, p):
        hdr = tk.Frame(p, bg=BG1)
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="GPU Profiles", font=FT, fg=WHT, bg=BG1).pack(side="left")
        mk_btn(hdr, "⟳ Refresh", self._refresh_profiles, BG3, TXT
               ).pack(side="right")

        cols = ("name", "core", "mem", "pwr", "volt", "score", "stable", "notes")
        tree_f = tk.Frame(p, bg=BG1)
        tree_f.pack(fill="both", expand=True, padx=12, pady=4)

        sb = ttk.Scrollbar(tree_f, orient="vertical")
        self.tree = ttk.Treeview(tree_f, columns=cols, show="headings",
                                 height=12, style="TV.Treeview",
                                 yscrollcommand=sb.set)
        sb.config(command=self.tree.yview)

        for col, label, w in [
            ("name","Profile",150),("core","Core+",80),("mem","Mem+",70),
            ("pwr","Power%",70),("volt","AvgVolt",85),("score","Score",55),
            ("stable","Stable",60),("notes","Notes",230),
        ]:
            anc = "w" if col in ("name","notes") else "center"
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor=anc)

        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        act = tk.Frame(p, bg=BG1)
        act.pack(fill="x", padx=12, pady=4)
        mk_btn(act, "▶ Apply to AB",       self._apply_profile,  ACC, "#000").pack(side="left", padx=3)
        mk_btn(act, "📌 Set Tray Default", self._set_tray_default).pack(side="left", padx=3)
        mk_btn(act, "🗑 Delete",           self._delete_profile,  ERR, WHT).pack(side="left", padx=3)

        self.lbl_detail = tk.Label(p, text="Select a profile", font=FM,
                                   fg=DIM, bg=BG2, anchor="w", padx=10, pady=6)
        self.lbl_detail.pack(fill="x", padx=12, pady=(2, 8))

        self.tree.bind("<<TreeviewSelect>>", self._on_profile_select)
        self._refresh_profiles()

    # ── Manual ────────────────────────────────────────────────────────────────

    def _build_manual(self, p):
        tk.Label(p, text="Manual Offset Control", font=FT, fg=WHT, bg=BG1
                 ).pack(padx=12, pady=(12, 2), anchor="w")
        tk.Label(p, text="Changes apply immediately via Afterburner.",
                 font=FL, fg=DIM, bg=BG1).pack(padx=12, anchor="w")

        cf = tk.Frame(p, bg=BG2)
        cf.pack(fill="x", padx=12, pady=8)

        self.v_m_core = tk.IntVar(value=0)
        self.v_m_mem  = tk.IntVar(value=0)
        self.v_m_pwr  = tk.IntVar(value=100)
        self.v_m_fan  = tk.IntVar(value=0)

        for row_i, (label, var, lo, hi, unit) in enumerate([
            ("Core Offset",  self.v_m_core,  -200, 350, "MHz"),
            ("Mem Offset",   self.v_m_mem,   -500,1500, "MHz"),
            ("Power Limit",  self.v_m_pwr,     50, 120, "%"),
            ("Fan Speed",    self.v_m_fan,      0, 100, "% (0=auto)"),
        ]):
            tk.Label(cf, text=label, font=FL, fg=DIM, bg=BG2).grid(
                row=row_i, column=0, sticky="w", padx=12, pady=6)
            tk.Scale(cf, variable=var, from_=lo, to=hi, orient="horizontal",
                     length=320, bg=BG2, fg=TXT, troughcolor=BG3,
                     activebackground=ACC, highlightthickness=0, font=FM
                     ).grid(row=row_i, column=1, padx=6)
            tk.Label(cf, textvariable=var, font=FV, fg=ACC, bg=BG2, width=5
                     ).grid(row=row_i, column=2)
            tk.Label(cf, text=unit, font=FL, fg=DIM, bg=BG2).grid(
                row=row_i, column=3, sticky="w")

        bf = tk.Frame(p, bg=BG1)
        bf.pack(fill="x", padx=12, pady=4)
        mk_btn(bf, "Apply",           self._manual_apply,  ACC, "#000", bold=True).pack(side="left", padx=(0, 8))
        mk_btn(bf, "Reset to Stock",  self._manual_reset).pack(side="left", padx=(0, 8))
        mk_btn(bf, "Save as Profile...", self._manual_save, ACC2, WHT).pack(side="left")

        self.lbl_manual_st = tk.Label(p, text="", font=FM, fg=DIM, bg=BG1)
        self.lbl_manual_st.pack(padx=12, pady=4, anchor="w")

    # ── Tuner callbacks ───────────────────────────────────────────────────────

    def _on_state(self, state):
        colors = {
            TunerState.IDLE:       (DIM, "Idle"),
            TunerState.BASELINE:   (ACC, "Baseline..."),
            TunerState.STAGE1:     (ACC, "Stage 1: Core OC"),
            TunerState.STAGE2:     (ACC, "Stage 2: Power UV"),
            TunerState.FINAL_TEST: (WRN, "Final verification"),
            TunerState.BACKOFF:    (WRN, "Backoff"),
            TunerState.SAVING:     (OK,  "Saving..."),
            TunerState.DONE:       (OK,  "Done!"),
            TunerState.ERROR:      (ERR, "Error"),
            TunerState.ABORTED:    (ERR, "Aborted"),
        }
        col, text = colors.get(state, (DIM, state.name))
        def _do():
            self.lbl_state.config(text=text, fg=col)
            done = {TunerState.DONE, TunerState.ERROR, TunerState.ABORTED, TunerState.IDLE}
            self.btn_start.config(state="normal" if state in done else "disabled")
            self.btn_abort.config(state="disabled" if state in done else "normal")
            if state == TunerState.DONE:
                self._refresh_profiles()
        self.after(0, _do)

    def _on_log(self, msg, level):
        tag = level if level in ("warning","error","success") else "info"
        if "═══" in msg or "Stage" in msg: tag = "header"
        self.after(0, lambda: self.log.append(msg, tag))

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
            # Push to live graph
            if hasattr(self, "live_graph"):
                self.live_graph.push(s.core_mhz, s.voltage_mv, float(s.temp))
        self.after(0, _do)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start_tune(self):
        from core.nvtune_tuner import TuneMode
        slot = self.v_ab_slot.get()
        if self.ab.check_profile_locked(slot):
            messagebox.showerror("Slot Locked",
                f"AB profile slot {slot} is locked (🔒). Unlock it in Afterburner first.")
            return

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

        if not messagebox.askyesno("Start Tune",
            f"Mode: {mode_str}\n"
            f"AB Slot: {slot}\n"
            f"Core Max: +{self.v_core_max.get()}MHz  |  "
            f"Power Min: {self.v_pwr_min.get()}%  |  "
            f"Max Temp: {self.v_max_temp.get()}°C\n\n"
            f"Process takes ~10-20 minutes. Start?"):
            return

        cfg = TunerConfig(
            mode=mode,
            core_step_mhz=self.v_core_step.get(),
            core_max_mhz=self.v_core_max.get(),
            power_min_pct=self.v_pwr_min.get(),
            max_temp_c=self.v_max_temp.get(),
            step_test_s=self.v_step_dur.get(),
            final_test_s=self.v_final_dur.get(),
            mem_offset_mhz=self.v_mem_off.get(),
            ab_slot=slot,
        )
        self.tuner.config = cfg
        self.prog_var.set(0)
        if hasattr(self, "live_graph"):
            self.live_graph.clear()
        self.tuner.start()

    def _abort_tune(self):
        if messagebox.askyesno("Abort", "Abort and reset GPU to stock?"):
            # abort() waits for an in-flight Afterburner write and then resets
            # (Afterburner load ~1.5 s) — run it off the UI thread so the
            # window doesn't freeze.
            self.btn_abort.config(state="disabled")
            threading.Thread(target=self.tuner.abort, daemon=True).start()

    def _refresh_profiles(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for p in self.pm.list_all():
            if p.name.startswith("__"): continue
            self.tree.insert("", "end", iid=p.name, values=(
                p.name, f"+{p.core_offset_mhz}", f"+{p.mem_offset_mhz}",
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
            self.lbl_detail.config(text=(
                f"Core: +{p.core_offset_mhz}MHz  Mem: +{p.mem_offset_mhz}MHz  "
                f"Power: {p.power_limit_pct}%  AvgVolt: {p.stage1_voltage or '--'}mV  "
                f"Score: {p.stability_score}/100  GPU: {p.gpu_name}"
            ))

    def _apply_profile(self):
        sel = self.tree.selection()
        if not sel: return messagebox.showwarning("", "Select a profile first.")
        p = self.pm.load(sel[0])
        if not p: return
        ok, err = self.ab.write_and_apply(self.v_ab_slot.get(), p)
        if ok: messagebox.showinfo("Applied", f"'{p.name}' applied.")
        else:  messagebox.showerror("Error", err)

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
        fan_v = self.v_m_fan.get()
        p = TuneProfile(name="Manual", core_offset_mhz=self.v_m_core.get(),
                        mem_offset_mhz=self.v_m_mem.get(),
                        power_limit_pct=self.v_m_pwr.get(),
                        fan_mode="manual" if fan_v > 0 else "auto",
                        fan_speed_pct=fan_v)
        ok, err = self.ab.write_and_apply(self.v_ab_slot.get(), p)
        self.lbl_manual_st.config(
            text=f"{'Applied.' if ok else f'Error: {err}'} Core+{p.core_offset_mhz} Mem+{p.mem_offset_mhz} Pwr {p.power_limit_pct}%",
            fg=OK if ok else ERR)

    def _manual_reset(self):
        self.v_m_core.set(0); self.v_m_mem.set(0)
        self.v_m_pwr.set(100); self.v_m_fan.set(0)
        self.ab.reset_to_stock()
        self.lbl_manual_st.config(text="Reset to stock.", fg=OK)

    def _manual_save(self):
        name = simpledialog.askstring("Profile Name", "Profile name:")
        if not name: return
        fan_v = self.v_m_fan.get()
        p = TuneProfile(name=name, core_offset_mhz=self.v_m_core.get(),
                        mem_offset_mhz=self.v_m_mem.get(),
                        power_limit_pct=self.v_m_pwr.get(),
                        fan_mode="manual" if fan_v > 0 else "auto",
                        fan_speed_pct=fan_v, notes="Manual",
                        created_at=datetime.now().isoformat())
        self.pm.save(p); self._refresh_profiles()
        messagebox.showinfo("Saved", f"'{name}' saved.")
