"""
GameOptimizerPro v2.1 — Optimizer Tab
Layout: Left sidebar with section buttons (like v1.0 tabs but as sidebar),
Right = content area. Everything visible, no hidden sub-tabs.
Sections: Presets | [WIN] Windows | [GAME] Gaming | [NET] Network | Verify | Export/Import
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
from datetime import datetime
from typing import Optional

from ui.widgets import *
from core.tweaks         import ALL_TWEAKS, get_groups, Tweak, get_by_id
from core.tweak_i18n     import tweak_desc, tweak_name


def _make_tooltip(widget, text: str):
    """Simple hover tooltip."""
    tip = None
    def _enter(e):
        nonlocal tip
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(tip, text=text, font=("Segoe UI", 8),
                 bg="#1c2128", fg="#d0d8e8",
                 relief="flat", padx=8, pady=5,
                 wraplength=420, justify="left"
                 ).pack()
    def _leave(e):
        nonlocal tip
        if tip:
            try: tip.destroy()
            except: pass
            tip = None
    widget.bind("<Enter>", _enter)
    widget.bind("<Leave>", _leave)
from core.tweak_runner   import TweakRunner
from core.tweak_verifier import TweakVerifier, VERIFY_MAP
from core.tweak_presets  import TweakPreset, BUILTIN_PRESETS, get_all_presets
from core.export_import  import ExportImport
from core.hardware       import HardwareInfo


# Section definitions: (key, label, color)
SECTIONS = [
    ("presets",  "⭐  Presets",        "#e53935"),
    ("windows",  "[WIN]  Windows",     "#e53935"),
    ("gaming",   "[GAME] Gaming",      "#f59e0b"),
    ("network",  "[NET]  Network",     "#00b4d8"),
    ("audio",    "[AUDIO] Audio",      "#a78bfa"),
    ("verify",   "[✓]   Verify",       "#22c55e"),
    ("exim",     "[↕]   Export/Import","#7c3aed"),
]


class OptimizerTab(tk.Frame):
    def __init__(self, parent, runner: TweakRunner, hw: HardwareInfo,
                 profiles_dir: str = "profiles", logs_dir: str = "logs", **kw):
        super().__init__(parent, bg="#0d1117", **kw)
        self.runner       = runner
        self.hw           = hw
        self.verifier     = TweakVerifier()
        self.exim         = ExportImport(profiles_dir, logs_dir)
        self._vars:         dict[str, tk.BooleanVar] = {}
        self._user_presets: list[TweakPreset]         = []
        self._section_btns: dict[str, tk.Button]      = {}
        self._section_frames: dict[str, tk.Frame]     = {}
        self._active_section = "presets"
        self._import_data: Optional[dict] = None
        self._verify_states: dict[str, bool] = {}   # tweak_id -> True/False/None
        self._dot_labels:    dict[str, tk.Label] = {} # tweak_id -> dot Label widget
        self._name_labels:   dict[str, tk.Label] = {} # tweak_id -> name Label widget
        self._verifying = False
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Top: action bar (Select All / Apply / Revert / DE/EN)
        self._build_action_bar()

        # Body: left sidebar + right content
        body = tk.Frame(self, bg="#0d1117")
        body.pack(fill="both", expand=True)

        self._sidebar = tk.Frame(body, bg="#161b22", width=155)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        self._content_area = tk.Frame(body, bg="#0d1117")
        self._content_area.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_all_sections()

        # Auto-run verify after 800ms so dots get colored on first view
        self.after(800, self._live_verify)

        # Bottom: log — fixed height, always visible even at small window sizes
        sep = tk.Frame(self, bg="#2d333b", height=1)
        sep.pack(side="bottom", fill="x")
        self.log = LogBox(self)
        self.log.pack(side="bottom", fill="x", padx=0, pady=0)
        self.log.txt.configure(height=5)   # ~5 lines always visible
        self.log.configure(height=90)

        self._show_section("presets")

    def _build_action_bar(self):
        bar = tk.Frame(self, bg="#161b22")
        bar.pack(fill="x")

        # Left: title
        tk.Label(bar, text="Optimizer", font=("Segoe UI", 11, "bold"),
                 fg="#e53935", bg="#161b22").pack(side="left", padx=12, pady=6)

        # Right: action buttons matching v1.0 style
        for text, cmd, bg, fg in [
            ("[x] Select All",   self._select_all,     "#1c2128", "#9ca3af"),
            ("[ ] Deselect All", self._deselect_all,   "#1c2128", "#9ca3af"),
            (">> Apply Selected",self._apply_selected, "#e53935", "#ffffff"),
            ("↩ Revert All",     self._revert_all,     "#f59e0b", "#000000"),
        ]:
            tk.Button(
                bar, text=text, command=cmd,
                font=("Consolas", 8, "bold"),
                bg=bg, fg=fg, relief="flat",
                padx=10, pady=6, cursor="hand2",
                activebackground=bg
            ).pack(side="right", padx=2, pady=4)

        # Live verify button
        self.btn_live_verify = tk.Button(
            bar, text="⟳ Status prüfen",
            command=self._live_verify,
            font=("Consolas", 8, "bold"),
            bg="#22c55e", fg="#000",
            relief="flat", padx=10, pady=6, cursor="hand2",
            activebackground="#22c55e"
        )
        self.btn_live_verify.pack(side="left", padx=(8, 2), pady=4)
        self.lbl_verify_hint = tk.Label(
            bar, text="● grün=aktiv  ○ grau=inaktiv  ◑ gelb=ungeprüft",
            font=("Consolas", 7), fg="#4b5563", bg="#161b22"
        )
        self.lbl_verify_hint.pack(side="left", padx=4)

    def _build_sidebar(self):
        tk.Label(self._sidebar, text="SECTIONS",
                 font=("Consolas", 7, "bold"),
                 fg="#4b5563", bg="#161b22"
                 ).pack(pady=(10, 4))

        for key, label, color in SECTIONS:
            btn = tk.Button(
                self._sidebar, text=label,
                font=("Consolas", 8, "bold"),
                bg="#1c2128", fg="#6b7280",
                relief="flat", bd=0,
                padx=10, pady=9,
                cursor="hand2", anchor="w",
                command=lambda k=key: self._show_section(k)
            )
            btn.pack(fill="x", padx=4, pady=1)
            self._section_btns[key] = btn

    def _build_all_sections(self):
        for key, _, _ in SECTIONS:
            f = tk.Frame(self._content_area, bg="#0d1117")
            self._section_frames[key] = f

        self._build_presets(self._section_frames["presets"])
        self._build_tweaks_section(self._section_frames["windows"], "Windows")
        self._build_tweaks_section(self._section_frames["gaming"], "Gaming")
        self._build_tweaks_section(self._section_frames["network"], "Network")
        self._build_tweaks_section(self._section_frames["audio"],   "Audio")
        self._build_verify(self._section_frames["verify"])
        self._build_exim(self._section_frames["exim"])

    def _show_section(self, key: str):
        self._active_section = key
        for k, frame in self._section_frames.items():
            frame.pack_forget()
        self._section_frames[key].pack(fill="both", expand=True)

        # Update sidebar button colors
        for k, btn in self._section_btns.items():
            color = next(c for sk, _, c in SECTIONS if sk == k)
            if k == key:
                btn.config(bg=color, fg="#ffffff")
            else:
                btn.config(bg="#1c2128", fg="#6b7280")

    # ── Presets Section ───────────────────────────────────────────────────────

    def _build_presets(self, p):
        from core.i18n import current_lang
        _lang = current_lang()
        _hdr_txt = ("Tweak Presets — 1-Klick Optimierung" if _lang == "de"
                    else "Tweak Presets — 1-Click Optimisation")
        _btn_txt = "+ Eigenes Preset" if _lang == "de" else "+ Custom Preset"
        hdr = tk.Frame(p, bg="#0d1117")
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text=_hdr_txt,
                 font=("Segoe UI", 10, "bold"),
                 fg="#e53935", bg="#0d1117").pack(side="left")
        tk.Button(hdr, text=_btn_txt,
                  command=self._create_user_preset,
                  font=("Consolas", 8), bg="#7c3aed", fg="white",
                  relief="flat", padx=8, pady=4, cursor="hand2"
                  ).pack(side="right")

        canvas = tk.Canvas(p, bg="#0d1117", highlightthickness=0)
        sb     = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        inner  = tk.Frame(canvas, bg="#0d1117")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=4, pady=2)
        sb.pack(side="right", fill="y")
        canvas.bind("<Enter>", lambda e, c=canvas:
                    c.bind_all("<MouseWheel>",
                    lambda ev, cv=c: cv.yview_scroll(int(-1*(ev.delta/120)), "units")))
        canvas.bind("<Leave>", lambda e, c=canvas: c.unbind_all("<MouseWheel>"))
        self._preset_inner = inner
        self._refresh_presets()

    def _refresh_presets(self):
        for w in self._preset_inner.winfo_children():
            w.destroy()
        for preset in get_all_presets(self._user_presets):
            if preset.id == "all_safe":
                from core.tweak_presets import get_all_safe_ids
                preset.tweak_ids = get_all_safe_ids()
            self._build_preset_card(self._preset_inner, preset)

    def _build_preset_card(self, parent, preset: TweakPreset):
        card = tk.Frame(parent, bg="#161b22", pady=8, padx=12)
        card.pack(fill="x", padx=8, pady=3)

        hdr = tk.Frame(card, bg="#161b22")
        hdr.pack(fill="x")

        tk.Label(hdr, text=preset.icon, font=("Segoe UI", 14),
                 fg=preset.color, bg="#161b22").pack(side="left", padx=(0, 8))

        from core.i18n import current_lang
        from core.tweak_i18n import preset_name, preset_desc
        _lang = current_lang()

        txt = tk.Frame(hdr, bg="#161b22")
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=preset_name(preset, _lang), font=("Segoe UI", 9, "bold"),
                 fg=preset.color, bg="#161b22", anchor="w").pack(anchor="w")

        # Count only tweaks this hardware can take — otherwise e.g. "Mittel" on
        # an AMD system could never reach n/n because of the NVIDIA-only tweak.
        usable  = [tid for tid in preset.tweak_ids
                   if get_by_id(tid) and self._is_applicable(get_by_id(tid))]
        n       = len(usable)
        already = sum(1 for tid in usable if self.runner.is_applied(tid))
        s_col   = OK if already == n else WRN if already > 0 else DIM
        _active_word = "aktiv" if _lang == "de" else "active"
        tk.Label(txt, text=f"{already}/{n} {_active_word}", font=FM,
                 fg=s_col, bg="#161b22", anchor="w").pack(anchor="w")

        btn_f = tk.Frame(hdr, bg="#161b22")
        btn_f.pack(side="right")
        tk.Button(btn_f, text="▶ Apply",
                  command=lambda p=preset: self._apply_preset(p),
                  font=("Consolas", 8, "bold"),
                  bg=preset.color, fg="#000000" if preset.color in ("#e53935","#f59e0b","#00b4d8") else "#ffffff",
                  relief="flat", padx=8, pady=4, cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(btn_f, text="👁",
                  command=lambda p=preset: self._preview_preset(p),
                  font=("Consolas", 8), bg="#1c2128", fg="#9ca3af",
                  relief="flat", padx=6, pady=4, cursor="hand2"
                  ).pack(side="left", padx=2)
        if not preset.builtin:
            tk.Button(btn_f, text="🗑",
                      command=lambda p=preset: self._delete_user_preset(p),
                      font=("Consolas", 8), bg=ERR, fg=WHT,
                      relief="flat", padx=6, pady=4, cursor="hand2"
                      ).pack(side="left", padx=2)

        tk.Label(card, text=preset_desc(preset, _lang), font=("Segoe UI", 8),
                 fg="#6b7280", bg="#161b22", anchor="w",
                 justify="left", wraplength=680).pack(anchor="w", pady=(4, 0))

    def _apply_preset(self, preset):
        tweaks   = [t for t in (get_by_id(tid) for tid in preset.tweak_ids) if t]
        skipped  = [t for t in tweaks if not self._is_applicable(t)]
        to_apply = [t for t in tweaks
                    if self._is_applicable(t) and not self.runner.is_applied(t.id)]
        if not to_apply:
            messagebox.showinfo("Preset", f"'{preset.name}' ist bereits vollständig aktiv.")
            return
        needs_rb = any(t.requires_reboot for t in to_apply)
        msg = f"Preset '{preset.name}' anwenden?\n{len(to_apply)} Tweak(s) werden aktiviert."
        if skipped:
            msg += (f"\n\n{len(skipped)} Tweak(s) passen nicht zu deiner Hardware und "
                    f"werden übersprungen ({', '.join(t.name for t in skipped)}).")
        if needs_rb: msg += "\n\n⚠ Einige benötigen einen Neustart."
        if not messagebox.askyesno("Preset anwenden", msg): return

        def _run():
            self.log.append(f"Preset: {preset.icon} {preset.name}", "header")
            self._backup_before("PreApply")
            for i, t in enumerate(to_apply):
                ok, out = self.runner.apply(t)
                self.log.append(f"  {t.name}: {'✓' if ok else '✗ '+out[:60]}",
                                "success" if ok else "error")
            self.log.append("Fertig.", "success")
            self.after(0, self._refresh_presets)
            self.after(600, self._live_verify)
        threading.Thread(target=_run, daemon=True).start()

    def _preview_preset(self, preset):
        lines = [f"{preset.icon} {preset.name}\n"]
        for tid in preset.tweak_ids:
            t = get_by_id(tid)
            if t and not self._is_applicable(t):
                state = "— n/a  "          # passt nicht zu dieser Hardware
            else:
                state = "✓ aktiv" if self.runner.is_applied(tid) else "○ inaktiv"
            lines.append(f"  {state}  {t.name if t else tid}")
        messagebox.showinfo(f"Preset: {preset.name}", "\n".join(lines))

    def _backup_before(self, label: str):
        """Registry backup before a batch of changes (runs in the worker thread).
        TweakRunner.apply_batch()/revert_all() already did this — but the UI
        never calls those; it applies/reverts tweak by tweak. So the automatic
        backup has to be triggered here, where the batches actually happen."""
        self.log.append("Sichere Registry (Backup vor der Änderung) …", "dim")
        res = self.runner.backup_registry(label)
        if res is None:
            self.log.append("  ⚠ Registry-Backup nicht möglich — fahre trotzdem fort.", "warning")
        else:
            self.log.append("  " + res.summary(), "success" if res.ok else "warning")

    def _create_user_preset(self):
        name = simpledialog.askstring("Eigenes Preset", "Name:")
        if not name: return
        applied_ids = list(self.runner._applied.keys())
        if not applied_ids:
            messagebox.showinfo("Preset", "Keine aktiven Tweaks — wende zuerst welche an.")
            return
        self._user_presets.append(TweakPreset(
            id=f"user_{name.lower().replace(' ','_')}",
            name=name, icon="⭐",
            desc=f"Eigenes Preset: {len(applied_ids)} aktive Tweaks",
            tweak_ids=applied_ids, color=ACC3, builtin=False))
        self._refresh_presets()

    def _delete_user_preset(self, preset):
        if messagebox.askyesno("Löschen", f"Preset '{preset.name}' löschen?"):
            self._user_presets = [p for p in self._user_presets if p.id != preset.id]
            self._refresh_presets()

    # ── Tweaks Section (Windows / Gaming / Network) ───────────────────────────

    def _build_tweaks_section(self, p, category: str):
        # Header with category name
        hdr = tk.Frame(p, bg="#0d1117")
        hdr.pack(fill="x", padx=12, pady=(10, 2))

        cat_colors = {"Windows": "#e53935", "Gaming": "#f59e0b", "Network": "#00b4d8", "Audio": "#a78bfa"}
        color = cat_colors.get(category, ACC)
        tk.Label(hdr, text=f"[{category[:3].upper()}]  {category}",
                 font=("Segoe UI", 10, "bold"),
                 fg=color, bg="#0d1117").pack(side="left")

        # Scrollable tweak list
        canvas = tk.Canvas(p, bg="#0d1117", highlightthickness=0)
        sb     = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        sf     = tk.Frame(canvas, bg="#0d1117")
        sf.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=4, pady=2)
        sb.pack(side="right", fill="y")
        canvas.bind("<Enter>", lambda e, c=canvas:
                    c.bind_all("<MouseWheel>",
                    lambda ev, cv=c: cv.yview_scroll(int(-1*(ev.delta/120)), "units")))
        canvas.bind("<Leave>", lambda e, c=canvas: c.unbind_all("<MouseWheel>"))

        for group in get_groups(category):
            tweaks = [t for t in ALL_TWEAKS
                      if t.category == category and t.group == group]

            # Group header line
            g_f = tk.Frame(sf, bg="#0d1117")
            g_f.pack(fill="x", padx=8, pady=(10, 2))
            tk.Label(g_f, text=f"-- {group}",
                     font=("Consolas", 8, "bold"),
                     fg=color, bg="#0d1117").pack(side="left")
            tk.Frame(g_f, bg="#2d333b", height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0))

            for tweak in tweaks:
                if not self._is_applicable(tweak):
                    continue
                self._build_tweak_row(sf, tweak, color)

    def _is_applicable(self, tweak: Tweak) -> bool:
        """Hardware filter used EVERYWHERE a tweak can be applied (list, presets,
        import). The list used to filter inline while presets didn't — so the
        'Mittel' / 'Hart' / 'All Safe' presets applied NVIDIA- and AMD-only
        tweaks on the wrong hardware."""
        if tweak.requires_nvidia and not self.hw.is_nvidia:
            return False
        if tweak.requires_amd and not self.hw.is_amd_gpu:
            return False
        return True

    def _build_tweak_row(self, parent, tweak: Tweak, color: str = ACC):
        is_applied = self.runner.is_applied(tweak.id)
        var = tk.BooleanVar(value=is_applied)
        self._vars[tweak.id] = var

        bg = "#161b22" if len(self._vars) % 2 == 0 else "#0d1117"
        row = tk.Frame(parent, bg=bg, pady=3)
        row.pack(fill="x", padx=4, pady=1)

        # ── Status circle ─────────────────────────────────────────────────────
        # 3 states:
        #   ● color  = verified aktiv (aus Registry gelesen)
        #   ● amber  = laut JSON aktiv, aber noch nicht live geprüft
        #   ○ #374151 = nicht aktiv / unbekannt
        verified_state = self._verify_states.get(tweak.id)  # True/False/None
        has_verify     = tweak.id in VERIFY_MAP
        if verified_state is True:
            dot_color = color          # kategoriefarbe = definitiv aktiv ✓
            dot_txt   = "●"
        elif verified_state is False:
            dot_color = "#374151"      # dunkelgrau = definitiv nicht aktiv
            dot_txt   = "○"
        elif is_applied:
            dot_color = "#f59e0b"      # amber = JSON sagt aktiv, noch nicht geprüft
            dot_txt   = "◑"
        elif has_verify and not self._verify_states:
            # Verify hat noch nicht gelaufen — zeige amber für prüfbare Tweaks
            dot_color = "#4b5563"      # mittelgrau = prüfbar aber unbekannt
            dot_txt   = "○"
        else:
            dot_color = "#374151"      # dunkelgrau = nicht aktiv
            dot_txt   = "○"

        dot_lbl = tk.Label(row, text=dot_txt, font=("Consolas", 13),
                           fg=dot_color, bg=bg, cursor="hand2")
        dot_lbl.pack(side="left", padx=(6, 0))
        dot_lbl.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))
        # Store for live update
        self._dot_labels[tweak.id] = dot_lbl

        tk.Checkbutton(row, variable=var, bg=bg,
                       activebackground=bg, selectcolor="#1c2128",
                       fg=TXT, highlightthickness=0, bd=0
                       ).pack(side="left", padx=(0, 0))

        # ? tooltip button
        from core.i18n import current_lang
        _lang = current_lang()
        _t_name = tweak_name(tweak, _lang)
        _t_desc = tweak_desc(tweak, _lang)

        q_btn = tk.Label(row, text="?",
                         font=("Consolas", 8), fg="#4b5563", bg=bg,
                         cursor="hand2", padx=3)
        q_btn.pack(side="left", padx=(0, 4))
        _make_tooltip(q_btn, _t_desc)

        # Name + desc
        txt_f = tk.Frame(row, bg=bg)
        txt_f.pack(side="left", fill="x", expand=True)
        name_lbl = tk.Label(txt_f, text=_t_name,
                 font=("Segoe UI", 9, "bold"),
                 fg=color if (verified_state is True or (verified_state is None and is_applied))
                    else "#d1d5db",
                 bg=bg, anchor="w")
        name_lbl.pack(anchor="w")
        self._name_labels[tweak.id] = name_lbl
        tk.Label(txt_f, text=_t_desc,
                 font=("Segoe UI", 8), fg="#6b7280", bg=bg,
                 anchor="w", wraplength=580, justify="left"
                 ).pack(anchor="w")

        # Right badges
        badge_f = tk.Frame(row, bg=bg)
        badge_f.pack(side="right", padx=8)
        if tweak.requires_reboot:
            tk.Label(badge_f, text="⚠ reboot",
                     font=("Consolas", 7), fg=WRN, bg=bg).pack()
        risk_col = {"safe": "#374151", "moderate": WRN, "advanced": ERR}
        tk.Label(badge_f, text=f"[{tweak.risk}]",
                 font=("Consolas", 7),
                 fg=risk_col.get(tweak.risk, DIM), bg=bg).pack()
        if tweak.risk == "safe" and not tweak.requires_reboot:
            tk.Label(badge_f, text="⟳ einmalig",
                     font=("Consolas", 7), fg="#4b5563", bg=bg).pack()
        if is_applied or verified_state is True:
            tk.Label(badge_f, text="✓ aktiv",
                     font=("Consolas", 7), fg=color, bg=bg).pack()

    # ── Live Verify (dot update) ─────────────────────────────────────────────

    def _live_verify(self):
        """Run registry checks for ALL verifiable tweaks, update dots live."""
        if self._verifying:
            return
        self._verifying = True
        self.btn_live_verify.config(state="disabled", text="Prüfe...")
        self.lbl_verify_hint.config(text="Prüfe System-Zustand...", fg="#f59e0b")
        # Immediate first pass: show JSON state (amber) before registry check finishes
        self.after(10, self._update_dots)

        def _do():
            # Verify ALL tweaks in VERIFY_MAP regardless of applied state
            all_ids  = list(VERIFY_MAP.keys())
            # expected doesn't matter for status display — we just want actual state
            expected = {tid: False for tid in all_ids}
            results  = self.verifier.verify_all(all_ids, expected)

            # Store actual state only when we got a real answer
            for tid, res in results.items():
                if res.error:
                    # No usable output → leave state unknown (None)
                    self._verify_states[tid] = None
                else:
                    self._verify_states[tid] = res.actual

            # NOTE: the verified state is for DISPLAY only and must never change
            # ownership. This used to add every setting that was already active
            # on the system (dark mode, file extensions, …) to runner._applied —
            # so a later "Revert All" switched off things the user had set up
            # themselves before ever using GameOptimizerPro. _applied only ever
            # lists tweaks this app actually applied.

            self._verifying = False
            self.after(0, self._update_dots)

        import threading as _t
        _t.Thread(target=_do, daemon=True).start()

    def _update_dots(self):
        """
        Update dot labels. Priority order:
        1. v_state True  → ● green   (registry confirmed active)
        2. v_state False AND is_applied → ◑ amber (we applied it, registry disagrees — trust JSON)
        3. v_state False AND NOT applied → ○ grey  (confirmed inactive)
        4. is_applied (no verify) → ◑ amber (JSON says done, unverifiable)
        5. neither → ○ grey (not applied, not verified)
        """
        cat_colors = {
            "Windows": "#e53935",
            "Gaming":  "#f59e0b",
            "Network": "#00b4d8",
            "Audio":   "#a78bfa",
        }

        ok_count      = 0  # verified active
        applied_count = 0  # applied (JSON or verify conflict)
        inactive_count = 0  # confirmed NOT active
        open_count    = 0  # unknown / not applied

        for tweak in ALL_TWEAKS:
            dot  = self._dot_labels.get(tweak.id)
            nlbl = self._name_labels.get(tweak.id)
            if not dot:
                continue

            color      = cat_colors.get(tweak.category, ACC)
            v_state    = self._verify_states.get(tweak.id)  # True / False / None
            is_applied = self.runner.is_applied(tweak.id)

            if v_state is True:
                # Registry confirms active → solid green dot
                dot.config(text="●", fg=color)
                if nlbl: nlbl.config(fg=color)
                ok_count += 1

            elif v_state is False and is_applied:
                # Registry says not active BUT we applied it
                # Most likely: tweak needs reboot, or registry path slightly different
                # Trust JSON — show amber, don't penalise user
                dot.config(text="◑", fg="#f59e0b")
                if nlbl: nlbl.config(fg="#f59e0b")
                applied_count += 1

            elif v_state is False and not is_applied:
                # Registry confirms NOT active and we haven't applied it
                dot.config(text="○", fg="#374151")
                if nlbl: nlbl.config(fg="#6b7280")
                inactive_count += 1

            elif is_applied:
                # No verify data yet but JSON says applied → amber
                dot.config(text="◑", fg="#f59e0b")
                if nlbl: nlbl.config(fg="#f59e0b")
                applied_count += 1

            else:
                # Not applied, no verify → grey
                dot.config(text="○", fg="#374151")
                if nlbl: nlbl.config(fg="#6b7280")
                open_count += 1

        self.btn_live_verify.config(state="normal", text="⟳ Status prüfen")

        # Summary — only count things the user hasn't done yet
        active_total = ok_count + applied_count
        parts = []
        if ok_count:       parts.append(f"● {ok_count} verifiziert")
        if applied_count:  parts.append(f"◑ {applied_count} applied")
        if inactive_count: parts.append(f"○ {inactive_count} inaktiv")
        if open_count:     parts.append(f"○ {open_count} offen")

        self.lbl_verify_hint.config(
            text="  ".join(parts) if parts else "Keine Daten",
            fg="#22c55e" if inactive_count == 0 and open_count == 0 else "#9ca3af"
        )

    # ── Verify Section ────────────────────────────────────────────────────────

    def _build_verify(self, p):
        # Force dark background on ALL treeviews in this widget tree
        try:
            p.option_add("*Treeview.background",      "#161b22")
            p.option_add("*Treeview.foreground",      "#d0d8e8")
            p.option_add("*Treeview.fieldBackground", "#161b22")
            p.option_add("*Treeview.selectBackground","#7c3aed")
            p.option_add("*Treeview.selectForeground","#ffffff")
        except: pass
        hdr = tk.Frame(p, bg="#0d1117")
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="[✓]  Status Verification",
                 font=("Segoe UI", 10, "bold"),
                 fg="#22c55e", bg="#0d1117").pack(side="left")
        tk.Button(hdr, text="⟳ Jetzt prüfen",
                  command=self._run_verify,
                  font=("Consolas", 8, "bold"),
                  bg="#22c55e", fg="#000000",
                  relief="flat", padx=10, pady=5, cursor="hand2"
                  ).pack(side="right")

        tk.Label(p,
                 text="Liest den tatsächlichen Registry-Zustand und vergleicht mit GameOptimizerPro's Status. "
                      "Findet Tweaks die Windows-Update oder andere Tools rückgängig gemacht haben.",
                 font=("Segoe UI", 8), fg="#6b7280", bg="#0d1117",
                 wraplength=700, justify="left"
                 ).pack(padx=12, anchor="w")

        self.lbl_verify_summary = tk.Label(
            p, text="Noch nicht geprüft — klick auf 'Jetzt prüfen'",
            font=("Consolas", 8), fg="#6b7280", bg="#161b22",
            anchor="w", padx=10, pady=5)
        self.lbl_verify_summary.pack(fill="x", padx=12, pady=4)

        # Results tree
        cols = ("name", "expected", "actual", "status")
        tf = tk.Frame(p, bg="#0d1117")
        tf.pack(fill="both", expand=True, padx=12, pady=2)
        sb2 = ttk.Scrollbar(tf, orient="vertical")
        # Force dark style for verify tree
        _vs = ttk.Style()
        _vs.configure("VRF.Treeview",
            background="#161b22", foreground="#d0d8e8",
            fieldbackground="#161b22", rowheight=26, font=("Segoe UI", 9),
            borderwidth=0)
        _vs.configure("VRF.Treeview.Heading",
            background="#1c2128", foreground="#00d9ff",
            font=("Segoe UI", 9, "bold"), relief="flat")
        _vs.map("VRF.Treeview",
            background=[("selected", "#7c3aed")],
            foreground=[("selected", "#ffffff")])
        self.verify_tree = ttk.Treeview(
            tf, columns=cols, show="headings",
            height=14, style="VRF.Treeview",
            yscrollcommand=sb2.set)
        sb2.config(command=self.verify_tree.yview)
        for col, label, w in [
            ("name",     "Tweak",       250),
            ("expected", "Erwartet",     90),
            ("actual",   "Tatsächlich",  90),
            ("status",   "Status",      110),
        ]:
            self.verify_tree.heading(col, text=label)
            self.verify_tree.column(col, width=w,
                anchor="w" if col == "name" else "center")
        self.verify_tree.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.verify_tree.tag_configure("ok",       foreground=OK)
        self.verify_tree.tag_configure("mismatch", foreground=ERR)
        self.verify_tree.tag_configure("unknown",  foreground=DIM)
        self.verify_tree.tag_configure("external", foreground="#60a5fa")  # aktiv, aber nicht von uns

        fix_f = tk.Frame(p, bg="#0d1117")
        fix_f.pack(fill="x", padx=12, pady=4)
        tk.Button(fix_f, text="🔧 Abweichungen beheben",
                  command=self._fix_mismatches,
                  font=("Consolas", 8, "bold"),
                  bg=WRN, fg="#000", relief="flat",
                  padx=10, pady=5, cursor="hand2"
                  ).pack(side="left")
        self.lbl_fix_result = tk.Label(fix_f, text="", font=FM, fg=DIM, bg="#0d1117")
        self.lbl_fix_result.pack(side="left", padx=12)

    def _run_verify(self):
        self.lbl_verify_summary.config(text="Prüfe System-Zustand...", fg=DIM)
        for row in self.verify_tree.get_children():
            self.verify_tree.delete(row)

        def _do():
            expected = {tid: True for tid in self.runner._applied.keys()}
            for tid in VERIFY_MAP:
                if tid not in expected: expected[tid] = False
            results = self.verifier.verify_all(list(expected.keys()), expected)

            # A "mismatch" (expected != actual) covers two very different cases:
            #   regressed — we applied it, but it is no longer active (Windows
            #               Update / another tool reverted it) → worth re-applying
            #   external  — active on the system, but NOT applied by us (the user
            #               or Windows set it) → nothing to fix, not ours to touch
            # Treating both as "Abweichung" made "Abweichungen beheben" apply
            # tweaks the user never selected.
            def _kind(r):
                if r.error:
                    return "unknown"
                if r.expected and not r.actual:
                    return "regressed"
                if r.actual and not r.expected:
                    return "external"
                return "ok"

            kinds = {tid: _kind(r) for tid, r in results.items()}
            ok_c  = sum(1 for k in kinds.values() if k == "ok")
            mis_c = sum(1 for k in kinds.values() if k == "regressed")
            ext_c = sum(1 for k in kinds.values() if k == "external")
            err_c = sum(1 for k in kinds.values() if k == "unknown")
            order = {"regressed": 0, "external": 1, "unknown": 2, "ok": 3}

            def _update():
                self._last_verify = results
                for row in self.verify_tree.get_children():
                    self.verify_tree.delete(row)
                for tid, res in sorted(results.items(), key=lambda x: order[kinds[x[0]]]):
                    t = get_by_id(tid)
                    name = t.name if t else tid
                    kind = kinds[tid]
                    if kind == "unknown":     tag, status = "unknown",  f"? {res.error[:30]}"
                    elif kind == "regressed": tag, status = "mismatch", "⚠ zurückgesetzt"
                    elif kind == "external":  tag, status = "external", "ℹ extern aktiv"
                    else:                     tag, status = "ok",       "✓ OK"
                    self.verify_tree.insert("", "end", iid=tid,
                        values=(name,
                                "aktiv" if res.expected else "inaktiv",
                                "aktiv" if res.actual   else "inaktiv",
                                status),
                        tags=(tag,))
                col = OK if mis_c == 0 else WRN
                self.lbl_verify_summary.config(
                    text=(f"✓ {ok_c} OK   ⚠ {mis_c} zurückgesetzt   "
                          f"ℹ {ext_c} extern aktiv   ? {err_c} Fehler   "
                          f"({len(results)} geprüft)"),
                    fg=col)
                # No state "sync" here: the old block sat behind `not mismatch`
                # but described mismatch cases, so it could never run — and the
                # verifier must not change ownership anyway (see _live_verify).
            self.after(0, _update)
        threading.Thread(target=_do, daemon=True).start()

    def _fix_mismatches(self):
        # Only tweaks WE applied that were reverted behind our back. Checked
        # against the stored results as well as the row tag, so a setting that
        # is merely active on the system is never applied by this button.
        last = getattr(self, "_last_verify", {}) or {}
        mis = []
        for item in self.verify_tree.get_children():
            if "mismatch" not in self.verify_tree.item(item, "tags"):
                continue
            res = last.get(item)
            if res is not None and not (res.expected and not res.actual):
                continue
            mis.append(get_by_id(item))
        mis = [t for t in mis if t]
        if not mis:
            self.lbl_fix_result.config(text="Keine Abweichungen.", fg=DIM)
            return
        if not messagebox.askyesno("Beheben", f"{len(mis)} Tweak(s) erneut anwenden?"):
            return
        def _do():
            self._backup_before("PreFix")
            ok_c = sum(1 for t in mis if self.runner.apply(t)[0])
            self.after(0, lambda: self.lbl_fix_result.config(
                text=f"{ok_c}/{len(mis)} behoben.", fg=OK))
            self.after(500, self._run_verify)
        threading.Thread(target=_do, daemon=True).start()

    # ── Export / Import Section ───────────────────────────────────────────────

    def _build_exim(self, p):
        tk.Label(p, text="[↕]  Export / Import",
                 font=("Segoe UI", 10, "bold"),
                 fg="#7c3aed", bg="#0d1117"
                 ).pack(padx=12, pady=(10, 6), anchor="w")

        # Export
        exp_f = tk.Frame(p, bg="#161b22", padx=12, pady=10)
        exp_f.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(exp_f, text="EXPORT", font=("Consolas", 8, "bold"),
                 fg="#7c3aed", bg="#161b22").pack(anchor="w")
        tk.Label(exp_f,
                 text="Speichert aktive Tweaks, GPU-Profile und eigene Presets in eine .nextune Datei.",
                 font=("Segoe UI", 8), fg="#6b7280", bg="#161b22",
                 wraplength=680).pack(anchor="w", pady=(2, 6))

        chk_row = tk.Frame(exp_f, bg="#161b22")
        chk_row.pack(anchor="w")
        self.v_exp_tweaks   = tk.BooleanVar(value=True)
        self.v_exp_profiles = tk.BooleanVar(value=True)
        self.v_exp_presets  = tk.BooleanVar(value=True)
        for var, label in [(self.v_exp_tweaks, "Tweaks"),
                           (self.v_exp_profiles, "GPU-Profile"),
                           (self.v_exp_presets, "Presets")]:
            tk.Checkbutton(chk_row, variable=var, text=label,
                           bg="#161b22", activebackground="#161b22",
                           selectcolor="#1c2128", fg=TXT,
                           highlightthickness=0, bd=0
                           ).pack(side="left", padx=8)

        exp_btn_f = tk.Frame(exp_f, bg="#161b22")
        exp_btn_f.pack(anchor="w", pady=(8, 0))
        tk.Button(exp_btn_f, text="💾 Exportieren...",
                  command=self._do_export,
                  font=("Consolas", 8, "bold"),
                  bg="#7c3aed", fg="white",
                  relief="flat", padx=10, pady=5, cursor="hand2"
                  ).pack(side="left")
        self.lbl_exp_result = tk.Label(exp_btn_f, text="", font=FM, fg=DIM, bg="#161b22")
        self.lbl_exp_result.pack(side="left", padx=10)

        # Import
        imp_f = tk.Frame(p, bg="#161b22", padx=12, pady=10)
        imp_f.pack(fill="x", padx=12)
        tk.Label(imp_f, text="IMPORT", font=("Consolas", 8, "bold"),
                 fg="#7c3aed", bg="#161b22").pack(anchor="w")
        tk.Label(imp_f,
                 text="Importiert Einstellungen aus einer .nextune Datei. Vorschau vor dem Apply.",
                 font=("Segoe UI", 8), fg="#6b7280", bg="#161b22",
                 wraplength=680).pack(anchor="w", pady=(2, 6))

        chk_imp = tk.Frame(imp_f, bg="#161b22")
        chk_imp.pack(anchor="w")
        self.v_imp_tweaks   = tk.BooleanVar(value=True)
        self.v_imp_profiles = tk.BooleanVar(value=True)
        self.v_imp_presets  = tk.BooleanVar(value=True)
        for var, label in [(self.v_imp_tweaks, "Tweaks"),
                           (self.v_imp_profiles, "GPU-Profile"),
                           (self.v_imp_presets, "Presets")]:
            tk.Checkbutton(chk_imp, variable=var, text=label,
                           bg="#161b22", activebackground="#161b22",
                           selectcolor="#1c2128", fg=TXT,
                           highlightthickness=0, bd=0
                           ).pack(side="left", padx=8)

        self.lbl_imp_preview = tk.Label(imp_f, text="", font=FM,
                                        fg=DIM, bg="#161b22", anchor="w", justify="left")
        self.lbl_imp_preview.pack(anchor="w", pady=4)

        imp_btn_f = tk.Frame(imp_f, bg="#161b22")
        imp_btn_f.pack(anchor="w", pady=(6, 0))
        tk.Button(imp_btn_f, text="📂 Datei öffnen & Vorschau",
                  command=self._preview_import,
                  font=("Consolas", 8), bg="#1c2128", fg="#9ca3af",
                  relief="flat", padx=10, pady=5, cursor="hand2"
                  ).pack(side="left", padx=(0, 8))
        self.btn_do_import = tk.Button(
            imp_btn_f, text="✓ Import bestätigen",
            command=self._do_import,
            font=("Consolas", 8, "bold"),
            bg=OK, fg="#000", relief="flat",
            padx=10, pady=5, cursor="hand2", state="disabled")
        self.btn_do_import.pack(side="left")
        self.lbl_imp_result = tk.Label(imp_btn_f, text="", font=FM,
                                       fg=DIM, bg="#161b22")
        self.lbl_imp_result.pack(side="left", padx=10)

    def _do_export(self):
        path = filedialog.asksaveasfilename(
            title="Export speichern", defaultextension=".nextune",
            filetypes=[("GameOptimizerPro Export", "*.nextune"), ("JSON", "*.json")])
        if not path: return
        user_pd = [{"id": p.id, "name": p.name, "icon": p.icon,
                    "desc": p.desc, "tweak_ids": p.tweak_ids, "color": p.color}
                   for p in self._user_presets] if self.v_exp_presets.get() else None
        ok, msg = self.exim.export(
            path,
            include_tweaks=self.v_exp_tweaks.get(),
            include_profiles=self.v_exp_profiles.get(),
            include_presets=self.v_exp_presets.get(),
            applied_tweaks=dict(self.runner._applied) if self.v_exp_tweaks.get() else None,
            user_presets=user_pd)
        self.lbl_exp_result.config(text="✓ OK" if ok else "✗ Fehler", fg=OK if ok else ERR)
        if ok: messagebox.showinfo("Export", msg)

    def _preview_import(self):
        path = filedialog.askopenfilename(
            title="Export öffnen",
            filetypes=[("GameOptimizerPro Export", "*.nextune"), ("JSON", "*.json"), ("Alle", "*.*")])
        if not path: return
        ok, data, msg = self.exim.import_file(path)
        if not ok: messagebox.showerror("Import Fehler", msg); return
        self._import_data = data
        self.lbl_imp_preview.config(text=msg, fg=ACC)
        self.btn_do_import.config(state="normal")

    def _do_import(self):
        if not self._import_data: return
        data = self._import_data
        msgs = []
        if self.v_imp_tweaks.get() and data.get("tweaks"):
            # Imported tweaks are SELECTED for review, not recorded as applied.
            # This used to do runner._applied.update(...): nothing was changed on
            # this PC, yet the tweaks showed as active — and "Revert All" would
            # then have reverted settings this app never applied here. Now the
            # user sees the selection and applies it with ">> Apply Selected"
            # (which also takes a registry backup first).
            wanted = [tid for tid in data["tweaks"] if isinstance(tid, str)]
            usable = [tid for tid in wanted if tid in self._vars]   # known + fits this hardware
            n_skip = len(wanted) - len(usable)
            for v in self._vars.values():
                v.set(False)
            for tid in usable:
                self._vars[tid].set(True)
            n_new = sum(1 for tid in usable if not self.runner.is_applied(tid))
            m = (f"{len(usable)} Tweaks ausgewählt ({n_new} davon neu) — "
                 f"mit '>> Apply Selected' anwenden")
            if n_skip:
                m += f"; {n_skip} unbekannt/passen nicht zu dieser Hardware"
            msgs.append(m)
        if self.v_imp_profiles.get() and data.get("gpu_profiles"):
            n_ok, _ = self.exim.apply_imported_profiles(data["gpu_profiles"])
            msgs.append(f"{n_ok} Profile")
        if self.v_imp_presets.get() and data.get("user_presets"):
            for pd in data["user_presets"]:
                self._user_presets.append(TweakPreset(
                    id=pd.get("id",""), name=pd.get("name",""),
                    icon=pd.get("icon","⭐"), desc=pd.get("desc",""),
                    tweak_ids=pd.get("tweak_ids",[]),
                    color=pd.get("color", ACC3), builtin=False))
            msgs.append(f"{len(data['user_presets'])} Presets")
            self._refresh_presets()
        self.lbl_imp_result.config(text="✓ " + ", ".join(msgs), fg=OK)
        messagebox.showinfo("Import", "Import erfolgreich:\n" + "\n".join(f"  • {m}" for m in msgs))
        self._import_data = None
        self.btn_do_import.config(state="disabled")
        self.lbl_imp_preview.config(text="")

    # ── Global actions ────────────────────────────────────────────────────────

    def _select_all(self):
        for v in self._vars.values(): v.set(True)

    def _deselect_all(self):
        for v in self._vars.values(): v.set(False)

    def _apply_selected(self):
        selected = [t for t in ALL_TWEAKS
                    if t.id in self._vars and self._vars[t.id].get()
                    and not self.runner.is_applied(t.id)]
        if not selected:
            messagebox.showinfo("Nichts", "Keine neuen Tweaks ausgewählt.")
            return
        needs_rb = any(t.requires_reboot for t in selected)
        msg = f"{len(selected)} Tweak(s) anwenden?"
        if needs_rb: msg += "\n\n⚠ Einige benötigen einen Neustart."
        if not messagebox.askyesno("Anwenden", msg): return
        def _run():
            self.log.append(f"Wende {len(selected)} Tweak(s) an...", "header")
            self._backup_before("PreApply")
            for i, t in enumerate(selected):
                ok, out = self.runner.apply(t)
                self.log.append(
                    f"  [{i+1}/{len(selected)}] {t.name}: {'✓' if ok else '✗ '+out[:80]}",
                    "success" if ok else "error")
            self.log.append("Fertig.", "success")
            # Re-verify dots after apply
            self.after(500, self._live_verify)
        threading.Thread(target=_run, daemon=True).start()

    def _revert_all(self):
        applied = [t for t in ALL_TWEAKS if self.runner.is_applied(t.id) and t.revert_cmd]
        if not applied:
            messagebox.showinfo("Nichts", "Keine aktiven Tweaks mit Revert-Befehl.")
            return
        if not messagebox.askyesno("Zurücksetzen", f"{len(applied)} Tweak(s) zurücksetzen?"):
            return
        def _run():
            self.log.append(f"Setze {len(applied)} zurück...", "warning")
            self._backup_before("PreRevert")
            for t in applied:
                ok, out = self.runner.revert(t)
                self.log.append(f"  ↩ {t.name}: {'OK' if ok else out[:80]}",
                                "success" if ok else "error")
            self.log.append("Revert abgeschlossen.", "success")
        threading.Thread(target=_run, daemon=True).start()
