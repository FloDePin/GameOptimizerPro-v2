"""
GameOptimizerPro v2.0 — BIOS Guide page
Hardware-specific BIOS recommendations with live status detection
(green = already active, red = still to set, grey = not detectable).
Cards wrap their text to the window width — nothing is cut off any more.
"""

import threading
import tkinter as tk

import customtkinter as ctk

from core.bios_detector import BiosDetector, DetectResult
from core.bios_guide    import BiosProfile, BiosSetting, get_impact_color, get_risk_color, match_profiles
from core.hardware      import HardwareInfo
from ui.components import (CheckBox, Page, ResponsiveGrid, WrapLabel, badge, button,
                           section_title)
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, DIM, ERR, F_BB, F_MONOS,
                      F_S, F_XS, GREEN, INPUT_BG, PURPLE, SLATE, TEXT, TEXT2, VIOLET, icon_image,
                      on_color, tint, tr)

# Status colors for detection result
COL_OK      = GREEN     # already active
COL_TODO    = ERR       # needs to be set
COL_UNKNOWN = "#6b7280" # can't detect

CATS = [("Memory", VIOLET), ("CPU", ACC), ("GPU", GREEN), ("Power", AMBER), ("Boot", SLATE)]
RISK_TEXT = {"safe": ("sicher", "safe"), "moderate": ("moderat", "moderate"),
             "advanced": ("riskant", "advanced")}
IMPACT_TEXT = {"high": ("hohe Wirkung", "high impact"), "medium": ("mittlere Wirkung", "medium impact"),
               "low": ("geringe Wirkung", "low impact")}


class BiosGuideTab(Page):
    def __init__(self, parent, hw: HardwareInfo, **kw):
        super().__init__(parent, tr("BIOS-Guide", "BIOS Guide"),
                         tr("Empfehlungen für dein Board und deine CPU — mit Live-Erkennung, was schon aktiv "
                            "ist. Nur Anzeige: alle Werte stellst du selbst im BIOS ein.",
                            "Recommendations for your board and CPU — with live detection of what is "
                            "already active. Read-only: you set every value in the BIOS yourself."),
                         color=AMBER, **kw)
        self.hw       = hw
        self.detector = BiosDetector()
        self._profiles: list[BiosProfile] = []
        self._active_idx = 0
        self._detect_results: dict[str, DetectResult] = {}
        self._detecting = False
        self._build()
        self.after(100, self._load_profiles)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        b = self.body
        self.btn_detect = button(self.actions, tr("System-Status prüfen", "Check system state"),
                                 self._run_detect, kind="primary", color=AMBER, height=32,
                                 image=icon_image("refresh", on_color(AMBER), 14), compound="left")
        self.btn_detect.pack(side="right")
        self.lbl_detect_status = tk.Label(self.actions, text="", font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_detect_status.pack(side="right", padx=10)

        top = ctk.CTkFrame(b, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
        top.pack(fill="x", padx=10, pady=(0, 12))
        inner = tk.Frame(top, bg=CARD_BG)
        inner.pack(fill="x", padx=16, pady=12)
        hw = self.hw
        WrapLabel(inner, text=f"CPU: {hw.cpu_name}   ·   Board: {hw.mb_manufacturer} {hw.mb_product}"
                              f"   ·   GPU: {hw.gpu_name}",
                  font=F_XS, fg=ACC, bg=CARD_BG).pack(fill="x", pady=(0, 10))

        prof = tk.Frame(inner, bg=CARD_BG)
        prof.pack(fill="x")
        tk.Label(prof, text=tr("Profil", "Profile"), font=F_BB, fg=TEXT2, bg=CARD_BG).pack(side="left")
        self.profile_var = tk.StringVar()
        self.profile_combo = ctk.CTkOptionMenu(prof, variable=self.profile_var, values=["—"],
                                               width=420, height=30, dynamic_resizing=False,
                                               command=lambda _v: self._on_profile_change())
        self.profile_combo.pack(side="left", padx=10)
        self.lbl_no_match = WrapLabel(inner, text="", font=F_S, fg=AMBER, bg=CARD_BG)
        self.lbl_no_match.pack(fill="x")

        filt = tk.Frame(inner, bg=CARD_BG)
        filt.pack(fill="x", pady=(10, 0))
        tk.Label(filt, text=tr("Anzeigen:", "Show:"), font=F_S, fg=DIM, bg=CARD_BG).pack(side="left", padx=(0, 6))
        self._filter_vars = {}
        for cat, color in CATS:
            v = tk.BooleanVar(value=True)
            self._filter_vars[cat] = v
            CheckBox(filt, v, accent=color, bg=CARD_BG, text=cat, font=F_S, size=16,
                     command=self._refresh_view).pack(side="left", padx=(0, 10))
        tk.Frame(filt, bg=BORDER, width=1, height=18).pack(side="left", padx=8)
        self._only_todo = tk.BooleanVar(value=False)
        CheckBox(filt, self._only_todo, accent=ERR, bg=CARD_BG, font=F_S, size=16,
                 text=tr("Nur noch zu erledigende", "Only what's left to do"),
                 command=self._refresh_view).pack(side="left", padx=(0, 10))
        self._show_reg = tk.BooleanVar(value=True)
        CheckBox(filt, self._show_reg, accent=PURPLE, bg=CARD_BG, font=F_S, size=16,
                 text=tr("Registry-Tipps", "Registry tips"), command=self._refresh_view).pack(side="left")

        leg = tk.Frame(inner, bg=CARD_BG)
        leg.pack(fill="x", pady=(10, 0))
        for color, de, en in [(COL_OK, "● bereits aktiv", "● already active"),
                              (COL_TODO, "● noch einstellen", "● still to set"),
                              (COL_UNKNOWN, "● nicht prüfbar", "● not detectable")]:
            tk.Label(leg, text=tr(de, en), font=F_XS, fg=color, bg=CARD_BG).pack(side="left", padx=(0, 12))

        self._inner = tk.Frame(b, bg=APP_BG)
        self._inner.pack(fill="x", padx=10)

    # ── Profile loading ────────────────────────────────────────────────────────

    def _load_profiles(self):
        self._profiles = match_profiles(
            self.hw.cpu_name, self.hw.mb_manufacturer,
            self.hw.mb_product, self.hw.gpu_name)
        if not self._profiles:
            self.lbl_no_match.config(
                text=f"Keine Profile für '{self.hw.cpu_name[:28]}' — generisch empfohlen: XMP/EXPO, "
                     f"ReBAR aktivieren.")
            return
        names = [p.name for p in self._profiles]
        self.profile_combo.configure(values=names)
        self.profile_var.set(names[0])
        self._active_idx = 0
        self._refresh_view()
        # Auto-detect on first load
        self._run_detect()

    def _on_profile_change(self, _=None):
        name = self.profile_var.get()
        for i, p in enumerate(self._profiles):
            if p.name == name:
                self._active_idx = i
                break
        self._refresh_view()

    # ── Detection ─────────────────────────────────────────────────────────────

    def _run_detect(self):
        if self._detecting:
            return
        self._detecting = True
        self.btn_detect.configure(state="disabled", text=tr("Prüfe …", "Checking …"))
        self.lbl_detect_status.config(text=tr("Lese System-Zustand …", "Reading system state …"), fg=DIM)

        def _do():
            results = self.detector.detect_all()
            self._detect_results = results
            self._detecting = False
            self.after(0, self._on_detect_done)

        threading.Thread(target=_do, daemon=True).start()

    def _on_detect_done(self):
        self.btn_detect.configure(state="normal", text=tr("System-Status prüfen", "Check system state"))
        active_count = sum(1 for r in self._detect_results.values() if r.active)
        total        = len(self._detect_results)
        self.lbl_detect_status.config(
            text=f"{active_count}/{total} " + tr("Einstellungen bereits aktiv", "settings already active"),
            fg=COL_OK if active_count == total else AMBER
        )
        self._refresh_view()

    # ── Render ─────────────────────────────────────────────────────────────────

    def _refresh_view(self):
        for w in self._inner.winfo_children():
            w.destroy()
        if not self._profiles:
            return

        profile  = self._profiles[self._active_idx]
        only_todo = self._only_todo.get()

        if profile.notes:
            nf = tk.Frame(self._inner, bg=tint(AMBER, APP_BG, 0.10), highlightthickness=1,
                          highlightbackground=tint(AMBER, APP_BG, 0.35))
            nf.pack(fill="x", pady=(0, 10))
            WrapLabel(nf, text=f"ℹ  {profile.notes}", font=F_S, fg=AMBER,
                      bg=tint(AMBER, APP_BG, 0.10)).pack(fill="x", padx=12, pady=8)

        if self._detect_results:
            detected_active = detected_total = 0
            for s in profile.settings:
                if s.detect_key and s.detect_key in self._detect_results:
                    detected_total += 1
                    if self._detect_results[s.detect_key].active:
                        detected_active += 1
            done = detected_active == detected_total
            col = COL_OK if done else AMBER
            sf = tk.Frame(self._inner, bg=tint(col, APP_BG, 0.10))
            sf.pack(fill="x", pady=(0, 10))
            tk.Label(sf, text=f"{detected_active}/{detected_total} " +
                     tr("prüfbare Einstellungen bereits aktiv", "detectable settings already active"),
                     font=F_BB, fg=col, bg=sf.cget("bg"), anchor="w").pack(fill="x", padx=12, pady=7)

        shown = 0
        for cat, color in CATS:
            if not self._filter_vars[cat].get():
                continue
            settings = [s for s in profile.settings if s.category == cat]
            if only_todo and self._detect_results:
                settings = [
                    s for s in settings
                    if not (s.detect_key and
                            self._detect_results.get(s.detect_key, DetectResult("", False)).active)
                ]
            if not settings:
                continue
            section_title(self._inner, cat, color, bg=APP_BG).pack(fill="x", pady=(8 if shown else 0, 8))
            grid = ResponsiveGrid(self._inner, min_width=420, max_cols=2, gap=12)
            grid.pack(fill="x")
            for s in settings:
                grid.add(self._build_card(grid, s, color))
                shown += 1

        if shown == 0:
            tk.Label(self._inner,
                     text=tr("✓ Alle prüfbaren Einstellungen sind bereits aktiv!",
                             "✓ All detectable settings are already active!"),
                     font=("Segoe UI Semibold", 12), fg=COL_OK, bg=APP_BG).pack(pady=30)

    def _build_card(self, parent, s: BiosSetting, color: str):
        detect = self._detect_results.get(s.detect_key) if s.detect_key else None
        if detect is None:
            status_color, status_tip = COL_UNKNOWN, tr("Nicht automatisch prüfbar", "Not detectable")
        elif detect.active:
            status_color, status_tip = COL_OK, f"{tr('Aktiv', 'Active')}: {detect.detected_val}"
        else:
            status_color, status_tip = COL_TODO, f"{tr('Noch einstellen', 'Still to set')}: {detect.note}"

        bg = CARD_BG
        card = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER)
        body = tk.Frame(card, bg=bg)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        top = tk.Frame(body, bg=bg)
        top.pack(fill="x")
        tk.Label(top, text="●", font=("Segoe UI", 13), fg=status_color, bg=bg).pack(side="left", padx=(0, 8), anchor="n")
        badge_f = tk.Frame(top, bg=bg)
        badge_f.pack(side="right", anchor="n", padx=(8, 0))
        name_f = tk.Frame(top, bg=bg)
        name_f.pack(side="left", fill="x", expand=True)
        WrapLabel(name_f, text=s.name, font=F_BB, fg=TEXT, bg=bg).pack(fill="x")
        WrapLabel(name_f, text=status_tip, font=F_XS, fg=status_color, bg=bg).pack(fill="x")
        de, en = IMPACT_TEXT.get(s.impact, (s.impact, s.impact))
        badge(badge_f, tr(de, en), get_impact_color(s.impact), bg).pack(anchor="e", pady=1)
        rde, ren = RISK_TEXT.get(s.risk, (s.risk, s.risk))
        badge(badge_f, tr(rde, ren), get_risk_color(s.risk), bg).pack(anchor="e", pady=1)

        val = tk.Frame(body, bg=CARD_BG2)
        val.pack(fill="x", pady=(10, 6))
        vin = tk.Frame(val, bg=CARD_BG2)
        vin.pack(fill="x", padx=10, pady=6)
        WrapLabel(vin, text=f"{tr('Standard', 'Default')}: {s.default}", font=F_XS, fg=DIM,
                  bg=CARD_BG2).pack(fill="x")
        WrapLabel(vin, text=f"{tr('Empfohlen', 'Recommended')}: {s.recommended}", font=F_BB, fg=color,
                  bg=CARD_BG2).pack(fill="x")

        WrapLabel(body, text=f"📍 {s.path}", font=F_XS, fg=VIOLET, bg=bg).pack(fill="x", pady=(0, 4))
        WrapLabel(body, text=s.explanation, font=F_S, fg=TEXT2, bg=bg).pack(fill="x")

        if s.registry_tweak and self._show_reg.get():
            rf = tk.Frame(body, bg=INPUT_BG)
            rf.pack(fill="x", pady=(8, 0))
            reg_str = f"{s.registry_tweak}  →  {s.registry_value} = {s.registry_data}"
            head = tk.Frame(rf, bg=INPUT_BG)
            head.pack(fill="x", padx=10, pady=(6, 0))
            tk.Label(head, text="Registry", font=("Segoe UI Semibold", 8), fg=PURPLE,
                     bg=INPUT_BG).pack(side="left")

            def _copy(t=reg_str, lbl=None):
                try:
                    self.clipboard_clear(); self.clipboard_append(t)
                    copy_lbl.config(text=tr("✓ kopiert", "✓ copied"), fg=GREEN)
                except tk.TclError:
                    pass
            copy_lbl = tk.Label(head, text=tr("Kopieren", "Copy"), font=F_XS, fg=ACC, bg=INPUT_BG,
                                cursor="hand2")
            copy_lbl.pack(side="right")
            copy_lbl.bind("<Button-1>", lambda e: _copy())
            WrapLabel(rf, text=reg_str, font=F_MONOS, fg=DIM, bg=INPUT_BG).pack(fill="x", padx=10, pady=(2, 6))
        return card
