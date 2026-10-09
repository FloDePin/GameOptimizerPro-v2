"""
GameOptimizerPro v2.0 — Optimizer page
Sections (segmented bar): Presets | Windows | Gaming | Netzwerk | Audio |
Prüfen | Export/Import. Tweak lists are light tk rows (see ui/components) with
a live status dot; the log stays visible at the bottom.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from core.export_import  import ExportImport
from core.hardware       import HardwareInfo
from core.tweak_i18n     import tweak_desc, tweak_name
from core.tweak_presets  import TweakPreset, get_all_presets
from core.tweak_runner   import TweakRunner
from core.tweak_verifier import TweakVerifier, VERIFY_MAP
from core.tweaks         import ALL_TWEAKS, Tweak, get_by_id, get_groups
from ui.components import (Card, CheckBox, LogView, Page, ProgressLine, ResponsiveGrid, Table, WrapLabel,
                           badge, button, scroll_area, section_title)
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, CYAN, DIM, ERR, F_BB,
                      F_MONO, F_S, F_XS, GREEN, INPUT_BG, MUTED, PURPLE, RED, TEXT, TEXT2,
                      VIOLET, ctk_font, emoji_image, icon_image, mix, named_font, on_color, tr)

ACC3 = AMBER

# Section definitions: (key, German label, English label, color)
SECTIONS = [
    ("presets", "Presets",       "Presets",       RED),
    ("windows", "Windows",       "Windows",       "#4f9cf9"),
    ("gaming",  "Gaming",        "Gaming",        AMBER),
    ("network", "Netzwerk",      "Network",       CYAN),
    ("audio",   "Audio",         "Audio",         VIOLET),
    ("verify",  "Prüfen",        "Verify",        GREEN),
    ("exim",    "Export/Import", "Export/Import", PURPLE),
]
CATEGORY_OF = {"windows": "Windows", "gaming": "Gaming", "network": "Network", "audio": "Audio"}
CAT_COLORS = {"Windows": "#4f9cf9", "Gaming": AMBER, "Network": CYAN, "Audio": VIOLET}
RISK_TEXT = {"safe": ("sicher", "safe"), "moderate": ("moderat", "moderate"),
             "advanced": ("riskant", "advanced")}
DOT_OFF = "#3a4452"
ROW_HOVER = mix(CARD_BG, "#ffffff", 0.035)


class OptimizerTab(Page):
    def __init__(self, parent, runner: TweakRunner, hw: HardwareInfo,
                 profiles_dir: str = "profiles", logs_dir: str = "logs", **kw):
        super().__init__(parent, "Optimizer",
                         tr("Windows-, Gaming-, Netzwerk- und Audio-Tweaks — mit Live-Statusprüfung",
                            "Windows, gaming, network and audio tweaks — with a live status check"),
                         color=RED, scroll=False, **kw)
        self.runner       = runner
        self.hw           = hw
        self.verifier     = TweakVerifier()
        self.exim         = ExportImport(profiles_dir, logs_dir)
        self._vars:         dict[str, tk.BooleanVar] = {}
        self._user_presets: list[TweakPreset]         = []
        self._section_frames: dict[str, tk.Widget]    = {}
        self._lists:        dict[str, ctk.CTkScrollableFrame] = {}
        self._rows:         dict[str, list] = {}       # section -> [(kind, widget, tweak|None)]
        self._active_section = ""
        self._import_data: Optional[dict] = None
        self._verify_states: dict[str, bool] = {}   # tweak_id -> True/False/None
        self._dot_labels:    dict[str, tk.Label] = {} # tweak_id -> dot Label widget
        self._name_labels:   dict[str, tk.Label] = {} # tweak_id -> name Label widget
        self._active_badges: dict[str, tk.Label] = {}
        self._verifying = False
        self._bulk = False                 # "select all": no either-or reactions
        self._batch_running = False        # one apply/revert batch at a time
        self._action_btns: list = []
        self._filter_job = None
        self._empty_lbl:    dict[str, tk.Label] = {}
        # Categories (groups) fold open / closed; the open ones are remembered.
        # Default: all closed — a list of 100+ tweaks at once was too much.
        from core import app_settings
        try:
            self._open_groups: set[str] = set(app_settings.get("optimizer_open_groups", []) or [])
        except Exception:
            self._open_groups = set()
        self._group_heads: dict[tuple, dict] = {}   # (section, group) -> {"arrow", "count"}
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self._build_action_bar()
        b = self.body

        bar = tk.Frame(b, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 8))
        self._seg_keys = {tr(de, en): key for key, de, en, _c in SECTIONS}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._seg_keys), height=32,
                                          font=ctk_font(12), selected_color=RED,
                                          selected_hover_color=mix(RED, "#000000", 0.18),
                                          command=lambda v: self._show_section(self._seg_keys[v]))
        self.seg.pack(side="left")
        # no textvariable: CTkEntry only shows its placeholder without one
        self.ent_search = ctk.CTkEntry(bar, width=170, height=32,
                                       placeholder_text=tr("Tweaks suchen …", "Search tweaks …"))
        self.ent_search.pack(side="right")
        self.ent_search.bind("<KeyRelease>", lambda e: self._schedule_filter())
        self._fold_btns = []
        for txt_de, txt_en, open_ in (("Alle zu", "Close all", False), ("Alle auf", "Open all", True)):
            bt = button(bar, tr(txt_de, txt_en), lambda o=open_: self.set_all_groups(self._active_section, o),
                        kind="ghost", height=30)
            bt.pack(side="right", padx=(0, 6))
            self._fold_btns.append(bt)

        legend = tk.Frame(b, bg=APP_BG)
        legend.pack(fill="x", pady=(0, 8))
        for sym, col, de, en in (("●", GREEN, "aktiv (geprüft)", "active (verified)"),
                                 ("◑", AMBER, "angewendet, nicht bestätigt", "applied, not confirmed"),
                                 ("○", MUTED, "inaktiv", "inactive")):
            tk.Label(legend, text=f"{sym} {tr(de, en)}", font=F_XS, fg=col, bg=APP_BG).pack(side="left", padx=(0, 12))
        self.btn_live_verify = button(legend, tr("Status prüfen", "Check status"), self._live_verify,
                                      kind="ghost", height=26, image=icon_image("refresh", TEXT2, 14),
                                      compound="left")
        self.btn_live_verify.pack(side="right")
        self.lbl_verify_hint = tk.Label(legend, text="", font=F_XS, fg=DIM, bg=APP_BG)
        self.lbl_verify_hint.pack(side="right", padx=8)

        # Bottom: log — fixed height, always visible even at small window sizes
        log_card = ctk.CTkFrame(b, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER)
        log_card.pack(side="bottom", fill="x", pady=(10, 0))
        self.log = LogView(log_card, height=5)
        self.log.pack(fill="x", padx=6, pady=6)

        self._content_area = tk.Frame(b, bg=APP_BG)
        self._content_area.pack(fill="both", expand=True)

        self._build_all_sections()
        self._show_section("presets")
        # Auto-run verify so the dots get colored on first view
        self.after(800, self._live_verify)

    def _build_action_bar(self):
        a = self.actions
        rv = button(a, tr("Alle zurücksetzen", "Revert all"), self._revert_all, kind="primary",
                    color=AMBER, image=icon_image("undo", on_color(AMBER), 15), compound="left")
        rv.pack(side="right", padx=(6, 0))
        ap = button(a, tr("Ausgewählte anwenden", "Apply selected"), self._apply_selected,
                    kind="primary", color=RED, image=icon_image("play", on_color(RED), 15),
                    compound="left")
        ap.pack(side="right", padx=(6, 0))
        self._action_btns += [ap, rv]
        button(a, tr("Keine", "None"), self._deselect_all).pack(side="right", padx=(6, 0))
        button(a, tr("Alle", "All"), self._select_all).pack(side="right")

    def _build_all_sections(self):
        for key, *_x in SECTIONS:
            self._section_frames[key] = tk.Frame(self._content_area, bg=APP_BG)
        self._build_presets(self._section_frames["presets"])
        for key, cat in CATEGORY_OF.items():
            self._build_tweaks_section(self._section_frames[key], key, cat)
        self._build_verify(self._section_frames["verify"])
        self._build_exim(self._section_frames["exim"])

    def _show_section(self, key: str):
        if key == self._active_section:
            return
        self._active_section = key
        for k, frame in self._section_frames.items():
            if k != key:
                frame.pack_forget()
        self._section_frames[key].pack(fill="both", expand=True)
        label = next(tr(de, en) for k, de, en, _c in SECTIONS if k == key)
        color = next(c for k, _d, _e, c in SECTIONS if k == key)
        self.seg.configure(selected_color=mix(CARD_BG2, color, 0.62),
                           selected_hover_color=mix(CARD_BG2, color, 0.75))
        self.seg.set(label)
        if key in CATEGORY_OF:
            self._apply_filter()

    # ── Presets Section ───────────────────────────────────────────────────────

    def _build_presets(self, p):
        head = tk.Frame(p, bg=APP_BG)
        head.pack(fill="x", pady=(0, 8))
        button(head, tr("Eigenes Preset", "Custom preset"), self._create_user_preset,
               image=icon_image("add", TEXT, 14), compound="left", height=30).pack(side="right", padx=(10, 0))
        WrapLabel(head, text=tr("1-Klick-Optimierung: ein Preset wendet alle passenden Tweaks an, "
                                "die noch nicht aktiv sind (vorher Registry-Backup).",
                                "1-click optimisation: a preset applies every fitting tweak that is "
                                "not active yet (registry backup first)."),
                  font=F_S, fg=DIM, bg=APP_BG).pack(side="left", fill="x", expand=True)
        area = scroll_area(p)
        area.pack(fill="both", expand=True)
        self._preset_area = area
        self._preset_inner = None
        self._refresh_presets()

    def _refresh_presets(self):
        if self._preset_inner is not None:
            self._preset_inner.destroy()
        self._preset_inner = ResponsiveGrid(self._preset_area, min_width=330, max_cols=3, gap=12)
        self._preset_inner.pack(fill="x", padx=(0, 8))
        for preset in get_all_presets(self._user_presets):
            if preset.id == "all_safe":
                from core.tweak_presets import get_all_safe_ids
                preset.tweak_ids = get_all_safe_ids()
            self._preset_inner.add(self._build_preset_card(self._preset_inner, preset))

    def _build_preset_card(self, parent, preset: TweakPreset):
        from core.i18n import current_lang
        from core.tweak_i18n import preset_desc, preset_name
        _lang = current_lang()
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=14, pady=12)
        hdr = tk.Frame(inner, bg=CARD_BG)
        hdr.pack(fill="x")
        img = emoji_image(hdr, preset.icon, 24)        # colour emoji (Tk draws them flat)
        if img is not None:
            tk.Label(hdr, image=img, bg=CARD_BG).pack(side="left", padx=(0, 10))
        else:
            tk.Label(hdr, text=preset.icon, font=named_font(hdr, "Segoe UI Emoji", 15),
                     fg=preset.color, bg=CARD_BG).pack(side="left", padx=(0, 10))
        txt = tk.Frame(hdr, bg=CARD_BG)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=preset_name(preset, _lang), font=F_BB, fg=TEXT, bg=CARD_BG,
                 anchor="w").pack(fill="x")
        # Count only tweaks this hardware can take — otherwise e.g. "Mittel" on
        # an AMD system could never reach n/n because of the NVIDIA-only tweak.
        usable  = [tid for tid in preset.tweak_ids
                   if get_by_id(tid) and self._is_applicable(get_by_id(tid))]
        n       = len(usable)
        already = sum(1 for tid in usable if self.runner.is_applied(tid))
        s_col   = GREEN if n and already == n else AMBER if already > 0 else DIM
        tk.Label(txt, text=f"{already}/{n} {'aktiv' if _lang == 'de' else 'active'}", font=F_XS,
                 fg=s_col, bg=CARD_BG, anchor="w").pack(fill="x")
        bar = ProgressLine(inner, preset.color)
        bar.set(already / n if n else 0)
        bar.pack(fill="x", pady=(10, 8))
        WrapLabel(inner, text=preset_desc(preset, _lang), font=F_S, fg=DIM, bg=CARD_BG).pack(fill="x")
        btn_f = tk.Frame(inner, bg=CARD_BG)
        btn_f.pack(fill="x", pady=(10, 0))
        button(btn_f, tr("Anwenden", "Apply"), lambda p=preset: self._apply_preset(p),
               kind="primary", color=preset.color, height=30).pack(side="left")
        button(btn_f, tr("Vorschau", "Preview"), lambda p=preset: self._preview_preset(p),
               height=30).pack(side="left", padx=6)
        if not preset.builtin:
            button(btn_f, "", lambda p=preset: self._delete_user_preset(p), kind="ghost", width=34,
                   height=30, image=icon_image("delete", ERR, 15)).pack(side="right")
        return card

    def _apply_preset(self, preset):
        if self._batch_busy():
            return
        from core.tweaks import resolve_selection
        tweaks   = [get_by_id(tid) for tid in resolve_selection(
                        [tid for tid in preset.tweak_ids if get_by_id(tid)], self.runner._applied)]
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
                self._apply_one(t, prefix=f"  [{i+1}/{len(to_apply)}] ")
            self.log.append("Fertig.", "success")
            self.after(0, self._refresh_presets)
            self.after(600, self._live_verify)
        self._run_batch(_run)

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
        name = ctk.CTkInputDialog(title=tr("Eigenes Preset", "Custom preset"),
                                  text=tr("Name des Presets (enthält alle gerade aktiven Tweaks):",
                                          "Preset name (holds all currently active tweaks):")).get_input()
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

    # ── Tweak lists (Windows / Gaming / Network / Audio) ─────────────────────

    def _build_tweaks_section(self, p, key: str, category: str):
        color = CAT_COLORS.get(category, ACC)
        area = scroll_area(p)
        area.pack(fill="both", expand=True)
        self._lists[key] = area
        items = self._rows.setdefault(key, [])
        for group in get_groups(category):
            tweaks = [t for t in ALL_TWEAKS
                      if t.category == category and t.group == group and self._is_applicable(t)]
            if not tweaks:
                continue
            hdr = self._group_header(area, key, group, color, len(tweaks))
            items.append(("group", hdr, group))
            for tweak in tweaks:
                items.append(("row", self._build_tweak_row(area, tweak, color), tweak))
        self._empty_lbl[key] = tk.Label(area, text=tr("Kein Tweak passt zur Suche.",
                                                      "No tweak matches the search."),
                                        font=F_S, fg=DIM, bg=APP_BG)
        self._pack_rows(key, None)

    def _group_header(self, parent, key: str, group: str, color: str, n: int) -> tk.Frame:
        """'▸ BLOATWARE   9 Tweaks · 7 aktiv ────' — a click folds the group open / closed."""
        f = tk.Frame(parent, bg=APP_BG, cursor="hand2")
        arrow = tk.Label(f, text="▾" if group in self._open_groups else "▸", font=("Segoe UI", 10),
                         fg=color, bg=APP_BG, width=2, cursor="hand2")
        arrow.pack(side="left")
        title = tk.Label(f, text=group.upper(), font=("Segoe UI Semibold", 9), fg=color, bg=APP_BG,
                         cursor="hand2")
        title.pack(side="left")
        count = tk.Label(f, text="", font=F_XS, fg=DIM, bg=APP_BG, cursor="hand2")
        count.pack(side="left", padx=(10, 0))
        line = tk.Frame(f, bg=BORDER, height=1)
        line.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
        for wdg in (f, arrow, title, count, line):
            wdg.bind("<Button-1>", lambda e, k=key, g=group: self._toggle_group(k, g))
        self._group_heads[(key, group)] = {"arrow": arrow, "count": count, "n": n}
        return f

    def _toggle_group(self, key: str, group: str):
        if group in self._open_groups:
            self._open_groups.discard(group)
        else:
            self._open_groups.add(group)
        try:
            from core import app_settings
            app_settings.set("optimizer_open_groups", sorted(self._open_groups))
        except Exception:
            pass
        if self.ent_search.get().strip():
            self._apply_filter()
        else:
            self._pack_rows(key, None)

    def set_all_groups(self, key: str, open_: bool):
        """Open / close every group of a section (the buttons next to the search)."""
        groups = [obj for kind, _w, obj in self._rows.get(key, []) if kind == "group"]
        if open_:
            self._open_groups.update(groups)
        else:
            self._open_groups.difference_update(groups)
        try:
            from core import app_settings
            app_settings.set("optimizer_open_groups", sorted(self._open_groups))
        except Exception:
            pass
        self._pack_rows(key, None)

    def _refresh_group_counts(self):
        for (key, group), h in self._group_heads.items():
            active = sum(1 for k2, _w, t in self._rows.get(key, [])
                         if k2 == "row" and t.group == group and self.runner.is_applied(t.id))
            try:
                h["count"].config(text=tr(f"{h['n']} Tweaks · {active} aktiv", f"{h['n']} tweaks · {active} active"))
            except tk.TclError:
                pass

    def _pack_rows(self, key: str, visible: Optional[set]):
        """Groups always show their header; their rows only when the group is open —
        or, during a search, every match (closed groups too)."""
        for kind, w, _t in self._rows.get(key, []):
            w.pack_forget()
        empty = self._empty_lbl.get(key)
        if empty is not None:
            empty.pack_forget()
        shown = groups = 0
        open_now = None
        for kind, w, obj in self._rows.get(key, []):
            if kind == "group":
                group_rows = [t for k2, _w2, t in self._rows[key]
                              if k2 == "row" and t.group == obj and (visible is None or t.id in visible)]
                open_now = visible is not None or obj in self._open_groups
                h = self._group_heads.get((key, obj))
                if h is not None:
                    try:
                        h["arrow"].config(text="▾" if open_now else "▸")
                    except tk.TclError:
                        pass
                if group_rows:
                    w.pack(fill="x", padx=(0, 8), pady=(10 if groups else 2, 4))
                    groups += 1
            elif (visible is None or obj.id in visible) and open_now:
                w.pack(fill="x", padx=(0, 8), pady=2)
                shown += 1
        self._refresh_group_counts()
        if not groups and empty is not None:
            empty.pack(pady=30)

    def _schedule_filter(self):
        if self._filter_job is not None:
            try:
                self.after_cancel(self._filter_job)
            except tk.TclError:
                pass
        self._filter_job = self.after(180, self._apply_filter)

    def _apply_filter(self):
        self._filter_job = None
        key = self._active_section
        if key not in CATEGORY_OF:
            return
        q = self.ent_search.get().strip().lower()
        if not q:
            self._pack_rows(key, None)
            return
        from core.i18n import current_lang
        lang = current_lang()
        visible = {t.id for kind, _w, t in self._rows.get(key, []) if kind == "row"
                   and (q in tweak_name(t, lang).lower() or q in tweak_desc(t, lang).lower()
                        or q in t.id.lower() or q in t.group.lower())}
        self._pack_rows(key, visible)

    def _is_applicable(self, tweak: Tweak) -> bool:
        """Hardware filter used EVERYWHERE a tweak can be applied (list, presets,
        import). The list used to filter inline while presets didn't — so the
        'Mittel' / 'Hart' / 'All Safe' presets applied NVIDIA- and AMD-only
        tweaks on the wrong hardware."""
        if tweak.requires_nvidia and not self.hw.is_nvidia:
            return False
        if tweak.requires_amd and not self.hw.is_amd_gpu:
            return False
        if getattr(tweak, "requires_nvme", False) and not self.hw.has_nvme:
            return False
        return True

    def _build_tweak_row(self, parent, tweak: Tweak, color: str = ACC):
        is_applied = self.runner.is_applied(tweak.id)
        var = tk.BooleanVar(value=is_applied)
        self._vars[tweak.id] = var
        var.trace_add("write", lambda *_a, tid=tweak.id: self._on_toggle(tid))
        bg = CARD_BG

        row = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER,
                       highlightcolor=BORDER)
        toggle = lambda e, v=var: v.set(not v.get())

        # Status dot: ● category colour = verified active, ◑ amber = applied but
        # not confirmed, ○ grey = not active (live-updated by _update_dots)
        dot_lbl = tk.Label(row, text="◑" if is_applied else "○", font=("Segoe UI", 12), width=2,
                           fg=AMBER if is_applied else DOT_OFF, bg=bg, cursor="hand2")
        dot_lbl.pack(side="left", padx=(12, 4))
        dot_lbl.bind("<Button-1>", toggle)
        self._dot_labels[tweak.id] = dot_lbl

        CheckBox(row, var, accent=color, bg=bg).pack(side="left", padx=(2, 10))

        from core.i18n import current_lang
        _lang = current_lang()
        txt_f = tk.Frame(row, bg=bg, cursor="hand2")      # packed after the badges (below)
        name_lbl = tk.Label(txt_f, text=tweak_name(tweak, _lang), font=F_BB,
                            fg=TEXT, bg=bg, anchor="w", cursor="hand2")
        name_lbl.pack(fill="x")
        self._name_labels[tweak.id] = name_lbl
        desc = WrapLabel(txt_f, text=tweak_desc(tweak, _lang), font=F_S, fg=DIM, bg=bg, cursor="hand2")
        desc.pack(fill="x")
        for w in (txt_f, name_lbl, desc):
            w.bind("<Button-1>", toggle)

        # Right badges — packed BEFORE the text so a long description can't squeeze them out
        badge_f = tk.Frame(row, bg=bg)
        badge_f.pack(side="right", padx=12, pady=8, anchor="n")
        txt_f.pack(side="left", fill="x", expand=True, pady=8)
        de, en = RISK_TEXT.get(tweak.risk, (tweak.risk, tweak.risk))
        risk_col = {"safe": MUTED, "moderate": AMBER, "advanced": ERR}.get(tweak.risk, DIM)
        badge(badge_f, tr(de, en), risk_col if tweak.risk != "safe" else TEXT2, bg).pack(anchor="e", pady=1)
        if tweak.requires_reboot:
            badge(badge_f, tr("⚠ Neustart", "⚠ reboot"), AMBER, bg).pack(anchor="e", pady=1)
        # "einmalig" = a one-way action without a revert (removals, clean-ups) —
        # it used to hang on EVERY safe tweak that needs no restart. Power plans
        # and DNS providers are a choice: only one of them can be active.
        from core.tweaks import alternatives_of
        if alternatives_of(tweak.id):
            badge(badge_f, "⇄ entweder-oder", CYAN, bg).pack(anchor="e", pady=1)
        elif not (tweak.revert_cmd or "").strip():
            badge(badge_f, "⟳ einmalig", TEXT2, bg).pack(anchor="e", pady=1)
        act = badge(badge_f, "✓ " + tr("aktiv", "active"), GREEN, bg)
        if is_applied:
            act.pack(anchor="e", pady=1)
        self._active_badges[tweak.id] = act

        self._hover(row)
        return row

    @staticmethod
    def _hover(row):
        """Subtle highlight of the row under the pointer (badges keep their tint)."""
        def recolor(w, color):
            if getattr(w, "_keep_bg", False):
                return
            try:
                if isinstance(w, tk.Checkbutton):
                    w.configure(bg=color, activebackground=color, selectcolor=color)
                else:
                    w.configure(bg=color)
            except tk.TclError:
                return
            for c in w.winfo_children():
                recolor(c, color)

        def inside() -> bool:
            try:
                w = row.winfo_containing(*row.winfo_pointerxy())
            except Exception:
                return False
            path = str(w) if w is not None else ""
            return path == str(row) or path.startswith(str(row) + ".")

        def enter(_e):
            if not getattr(row, "_hot", False):
                row._hot = True
                recolor(row, ROW_HOVER)

        def leave(_e):
            if getattr(row, "_hot", False) and not inside():
                row._hot = False
                recolor(row, CARD_BG)
        row.bind("<Enter>", enter)
        row.bind("<Leave>", leave)

    # ── Live Verify (dot update) ─────────────────────────────────────────────

    def _live_verify(self):
        """Run registry checks for ALL verifiable tweaks, update dots live."""
        if self._verifying:
            return
        self._verifying = True
        self.btn_live_verify.configure(state="disabled", text=tr("Prüfe …", "Checking …"))
        self.lbl_verify_hint.config(text=tr("Prüfe System-Zustand …", "Reading system state …"), fg=AMBER)
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

        threading.Thread(target=_do, daemon=True).start()

    def _update_dots(self):
        """
        Update dot labels. Priority order:
        1. v_state True  → ● category colour (registry confirmed active)
        2. v_state False AND is_applied → ◑ amber (we applied it, registry disagrees — trust JSON)
        3. v_state False AND NOT applied → ○ grey  (confirmed inactive)
        4. is_applied (no verify) → ◑ amber (JSON says done, unverifiable)
        5. neither → ○ grey (not applied, not verified)
        """
        ok_count = applied_count = inactive_count = open_count = 0

        for tweak in ALL_TWEAKS:
            dot  = self._dot_labels.get(tweak.id)
            nlbl = self._name_labels.get(tweak.id)
            if not dot:
                continue
            color      = CAT_COLORS.get(tweak.category, ACC)
            v_state    = self._verify_states.get(tweak.id)  # True / False / None
            is_applied = self.runner.is_applied(tweak.id)
            active = False

            if v_state is True:
                dot.config(text="●", fg=GREEN)
                ok_count += 1
                active = True
            elif v_state is False and is_applied:
                # Most likely: tweak needs a reboot, or the check reads a
                # slightly different path. Trust JSON — amber, don't penalise.
                dot.config(text="◑", fg=AMBER)
                applied_count += 1
                active = True
            elif v_state is False and not is_applied:
                dot.config(text="○", fg=DOT_OFF)
                inactive_count += 1
            elif is_applied:
                dot.config(text="◑", fg=AMBER)
                applied_count += 1
                active = True
            else:
                dot.config(text="○", fg=DOT_OFF)
                open_count += 1
            ab = self._active_badges.get(tweak.id)
            if ab is not None:
                if active and not ab.winfo_manager():
                    ab.pack(anchor="e", pady=1)
                elif not active and ab.winfo_manager():
                    ab.pack_forget()

        self.btn_live_verify.configure(state="normal", text=tr("Status prüfen", "Check status"))
        self._refresh_group_counts()
        parts = []
        if ok_count:       parts.append(f"● {ok_count} " + tr("verifiziert", "verified"))
        if applied_count:  parts.append(f"◑ {applied_count} " + tr("angewendet", "applied"))
        if inactive_count: parts.append(f"○ {inactive_count} " + tr("inaktiv", "inactive"))
        if open_count:     parts.append(f"○ {open_count} " + tr("offen", "open"))
        self.lbl_verify_hint.config(
            text="   ".join(parts) if parts else tr("Keine Daten", "No data"),
            fg=GREEN if inactive_count == 0 and open_count == 0 else TEXT2)

    # ── Verify Section ────────────────────────────────────────────────────────

    def _build_verify(self, p):
        card = Card(p, tr("Status-Prüfung", "Status verification"),
                    subtitle=tr("Liest den tatsächlichen Registry-Zustand und vergleicht ihn mit dem, "
                                "was GameOptimizerPro angewendet hat. Findet Tweaks, die ein "
                                "Windows-Update oder andere Tools rückgängig gemacht haben.",
                                "Reads the real registry state and compares it with what "
                                "GameOptimizerPro applied. Finds tweaks a Windows update or another "
                                "tool has undone."),
                    accent=GREEN)
        card.pack(fill="both", expand=True)
        button(card.actions, tr("Jetzt prüfen", "Check now"), self._run_verify, kind="primary",
               color=GREEN, height=30).pack(side="right")
        self.lbl_verify_summary = tk.Label(
            card.body, text=tr("Noch nicht geprüft — „Jetzt prüfen“ klicken.",
                               "Not checked yet — click 'Check now'."),
            font=F_MONO, fg=DIM, bg=CARD_BG, anchor="w")
        self.lbl_verify_summary.pack(fill="x", pady=(0, 8))
        tbl = Table(card.body, [("name", "Tweak", 280, "w"), ("expected", tr("Erwartet", "Expected"), 90, "center"),
                                ("actual", tr("Tatsächlich", "Actual"), 90, "center"),
                                ("status", "Status", 130, "center")], height=12)
        tbl.pack(fill="both", expand=True)
        self.verify_tree = tbl.tree
        self.verify_tree.tag_configure("ok",       foreground=GREEN)
        self.verify_tree.tag_configure("mismatch", foreground=ERR)
        self.verify_tree.tag_configure("unknown",  foreground=DIM)
        self.verify_tree.tag_configure("external", foreground="#60a5fa")  # aktiv, aber nicht von uns
        fix_f = tk.Frame(card.body, bg=CARD_BG)
        fix_f.pack(fill="x", pady=(10, 0))
        button(fix_f, tr("Abweichungen beheben", "Fix deviations"), self._fix_mismatches,
               kind="primary", color=AMBER, height=30).pack(side="left")
        self.lbl_fix_result = tk.Label(fix_f, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
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
                col = GREEN if mis_c == 0 else AMBER
                self.lbl_verify_summary.config(
                    text=(f"✓ {ok_c} OK   ⚠ {mis_c} zurückgesetzt   "
                          f"ℹ {ext_c} extern aktiv   ? {err_c} Fehler   "
                          f"({len(results)} geprüft)"),
                    fg=col)
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
        if self._batch_busy():
            return
        if not messagebox.askyesno("Beheben", f"{len(mis)} Tweak(s) erneut anwenden?"):
            return
        def _do():
            self._backup_before("PreFix")
            ok_c = sum(1 for t in mis if self._apply_one(t)[0])
            self.after(0, lambda: self.lbl_fix_result.config(
                text=f"{ok_c}/{len(mis)} behoben.", fg=GREEN))
            self.after(500, self._run_verify)
        self._run_batch(_do)

    # ── Export / Import Section ───────────────────────────────────────────────

    def _build_exim(self, p):
        grid = ResponsiveGrid(p, min_width=340, max_cols=2, gap=14)
        grid.pack(fill="x")

        exp = Card(grid, "Export", subtitle=tr(
            "Speichert aktive Tweaks, GPU-Profile und eigene Presets in eine .nextune-Datei.",
            "Saves active tweaks, GPU profiles and custom presets to a .nextune file."), accent=PURPLE)
        grid.add(exp)
        self.v_exp_tweaks   = tk.BooleanVar(value=True)
        self.v_exp_profiles = tk.BooleanVar(value=True)
        self.v_exp_presets  = tk.BooleanVar(value=True)
        chk = tk.Frame(exp.body, bg=CARD_BG)
        chk.pack(fill="x")
        for var, label in [(self.v_exp_tweaks, "Tweaks"), (self.v_exp_profiles, tr("GPU-Profile", "GPU profiles")),
                           (self.v_exp_presets, "Presets")]:
            CheckBox(chk, var, accent=PURPLE, bg=CARD_BG, text=label, font=F_S).pack(side="left", padx=(0, 14))
        row = tk.Frame(exp.body, bg=CARD_BG)
        row.pack(fill="x", pady=(12, 0))
        button(row, tr("Exportieren …", "Export …"), self._do_export, kind="primary", color=PURPLE,
               image=icon_image("save", on_color(PURPLE), 14), compound="left", height=30).pack(side="left")
        self.lbl_exp_result = tk.Label(row, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_exp_result.pack(side="left", padx=10)

        imp = Card(grid, "Import", subtitle=tr(
            "Importiert Einstellungen aus einer .nextune-Datei — mit Vorschau vor dem Übernehmen.",
            "Imports settings from a .nextune file — with a preview first."), accent=PURPLE)
        grid.add(imp)
        self.v_imp_tweaks   = tk.BooleanVar(value=True)
        self.v_imp_profiles = tk.BooleanVar(value=True)
        self.v_imp_presets  = tk.BooleanVar(value=True)
        chk2 = tk.Frame(imp.body, bg=CARD_BG)
        chk2.pack(fill="x")
        for var, label in [(self.v_imp_tweaks, "Tweaks"), (self.v_imp_profiles, tr("GPU-Profile", "GPU profiles")),
                           (self.v_imp_presets, "Presets")]:
            CheckBox(chk2, var, accent=PURPLE, bg=CARD_BG, text=label, font=F_S).pack(side="left", padx=(0, 14))
        self.lbl_imp_preview = WrapLabel(imp.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_imp_preview.pack(fill="x", pady=(8, 0))
        row2 = tk.Frame(imp.body, bg=CARD_BG)
        row2.pack(fill="x", pady=(10, 0))
        button(row2, tr("Datei öffnen & Vorschau", "Open file & preview"), self._preview_import,
               image=icon_image("folder", TEXT, 14), compound="left", height=30).pack(side="left", padx=(0, 8))
        self.btn_do_import = button(row2, tr("Import bestätigen", "Confirm import"), self._do_import,
                                    kind="primary", color=GREEN, height=30, state="disabled")
        self.btn_do_import.pack(side="left")
        self.lbl_imp_result = tk.Label(imp.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG, anchor="w")
        self.lbl_imp_result.pack(fill="x", pady=(8, 0))

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
        self.lbl_exp_result.config(text="✓ OK" if ok else "✗ Fehler", fg=GREEN if ok else ERR)
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
        self.btn_do_import.configure(state="normal")

    def _do_import(self):
        if not self._import_data: return
        data = self._import_data
        msgs = []
        if self.v_imp_tweaks.get() and data.get("tweaks"):
            # Imported tweaks are SELECTED for review, not recorded as applied:
            # nothing was changed on this PC yet. The user applies the selection
            # with 'Ausgewählte anwenden' (which takes a registry backup first).
            wanted = [tid for tid in data["tweaks"] if isinstance(tid, str)]
            usable = [tid for tid in wanted if tid in self._vars]   # known + fits this hardware
            n_skip = len(wanted) - len(usable)
            for v in self._vars.values():
                v.set(False)
            for tid in usable:
                self._vars[tid].set(True)
            n_new = sum(1 for tid in usable if not self.runner.is_applied(tid))
            m = (f"{len(usable)} Tweaks ausgewählt ({n_new} davon neu) — "
                 f"mit 'Ausgewählte anwenden' übernehmen")
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
        self.lbl_imp_result.config(text="✓ " + ", ".join(msgs), fg=GREEN)
        messagebox.showinfo("Import", "Import erfolgreich:\n" + "\n".join(f"  • {m}" for m in msgs))
        self._import_data = None
        self.btn_do_import.configure(state="disabled")
        self.lbl_imp_preview.config(text="")

    # ── Global actions ────────────────────────────────────────────────────────

    def _on_toggle(self, tid: str):
        """Either-or choices (power plan, DNS): ticking one unticks the others."""
        if self._bulk:
            return
        v = self._vars.get(tid)
        if v is None or not v.get():
            return
        from core.tweaks import alternatives_of
        for other in alternatives_of(tid):
            ov = self._vars.get(other)
            if ov is not None and ov.get():
                ov.set(False)

    def _select_all(self):
        # Everything — but only ONE power plan and ONE DNS provider (it used to
        # tick all of them; applied in a row, the last one silently won).
        from core.tweaks import resolve_selection
        keep = set(resolve_selection(list(self._vars), self.runner._applied))
        self._bulk = True
        try:
            for tid, v in self._vars.items():
                v.set(tid in keep)
        finally:
            self._bulk = False
        left = [get_by_id(t) for t in self._vars if t not in keep]
        if left:
            from core.i18n import current_lang
            self.log.append("Alle ausgewählt — außer den Alternativen (nur ein Energieplan / ein "
                            "DNS-Anbieter möglich): " + ", ".join(
                                tweak_name(t, current_lang()) for t in left if t), "dim")

    def _batch_busy(self) -> bool:
        if self._batch_running:
            messagebox.showinfo(
                "Bitte warten",
                "Es läuft noch ein Vorgang — z. B. die Datenträgerbereinigung dauert einige "
                "Minuten. Bitte warten, bis im Protokoll „Fertig.“ steht.")
            return True
        return False

    def _set_batch(self, running: bool):
        self._batch_running = running
        for b in self._action_btns:
            try:
                b.configure(state="disabled" if running else "normal")
            except Exception:
                pass

    def _run_batch(self, work):
        """Run `work` (a list of apply/revert steps) in a thread — never two at
        once: a second click during a long tweak used to start a second batch
        that applied the same tweaks in parallel."""
        self._set_batch(True)

        def _go():
            try:
                work()
            finally:
                self.after(0, lambda: self._set_batch(False))
        threading.Thread(target=_go, daemon=True).start()

    def _apply_one(self, t, prefix: str = "  "):
        """Apply one tweak with visible progress; untick replaced alternatives."""
        if getattr(t, "timeout_s", 60) > 60:
            self.log.append(f"{prefix}{t.name} … läuft (kann einige Minuten dauern)", "dim")
        ok, out = self.runner.apply(t)
        self.log.append(f"{prefix}{t.name}: {'✓' if ok else '✗ ' + out[:100]}",
                        "success" if ok else "error")
        sup = list(self.runner.last_superseded)
        if ok and sup:
            names = ", ".join((get_by_id(x).name if get_by_id(x) else x) for x in sup)
            self.log.append(f"{prefix}  ↳ ersetzt: {names}", "dim")

            def _untick(ids=sup):
                self._bulk = True
                try:
                    for x in ids:
                        if x in self._vars:
                            self._vars[x].set(False)
                finally:
                    self._bulk = False
            self.after(0, _untick)
        return ok, out

    def _deselect_all(self):
        for v in self._vars.values(): v.set(False)

    def _apply_selected(self):
        if self._batch_busy():
            return
        from core.tweaks import resolve_selection, alternatives_of
        ids = resolve_selection([t.id for t in ALL_TWEAKS
                                 if t.id in self._vars and self._vars[t.id].get()
                                 and not self.runner.is_applied(t.id)],
                                self.runner._applied)
        selected = [get_by_id(i) for i in ids]
        if not selected:
            messagebox.showinfo("Nichts", "Keine neuen Tweaks ausgewählt.")
            return
        needs_rb = any(t.requires_reboot for t in selected)
        msg = f"{len(selected)} Tweak(s) anwenden?"
        replaced = [get_by_id(a) for t in selected for a in alternatives_of(t.id)
                    if self.runner.is_applied(a)]
        if replaced:
            msg += "\n\nErsetzt (Entweder-oder): " + ", ".join(t.name for t in replaced if t)
        if needs_rb: msg += "\n\n⚠ Einige benötigen einen Neustart."
        if not messagebox.askyesno("Anwenden", msg): return

        def _run():
            self.log.append(f"Wende {len(selected)} Tweak(s) an...", "header")
            self._backup_before("PreApply")
            for i, t in enumerate(selected):
                self._apply_one(t, prefix=f"  [{i+1}/{len(selected)}] ")
            self.log.append("Fertig.", "success")
            # Re-verify dots after apply
            self.after(500, self._live_verify)
        self._run_batch(_run)

    def _revert_all(self):
        if self._batch_busy():
            return
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
            self.after(500, self._live_verify)
        self._run_batch(_run)
