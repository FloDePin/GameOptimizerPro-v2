"""
GameOptimizerPro v2.0 — BIOS Guide page
Every platform from core/bios_guide.py can be opened; the hardware detection
pre-selects the user's platform and board maker (the menu paths follow the board
maker). Live status: green = already set, red = still to set, grey = Windows
can't tell. Read-only — the user sets everything in the BIOS.
"""

import threading
import tkinter as tk

import customtkinter as ctk

from core.bios_detector import BiosDetector
from core.bios_guide    import (PROFILES, VENDORS, BiosSetting, detect_profile, get_impact_color,
                                get_profile, get_risk_color, vendor_of)
from core.hardware      import HardwareInfo
from ui.components import CheckBox, Page, ResponsiveGrid, WrapLabel, badge, button, section_title
from ui.theme import (ACC, AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, DIM, ERR, F_BB, F_S, F_XS,
                      GREEN, SLATE, TEXT, TEXT2, VIOLET, icon_image, on_color, tint, tr)

COL_OK      = GREEN       # already set
COL_TODO    = ERR         # still to set
COL_UNKNOWN = "#6b7280"   # Windows can't tell

CATS = [("Memory", tr("Speicher", "Memory"), VIOLET), ("CPU", "CPU", ACC), ("GPU", "GPU", GREEN),
        ("Power", tr("Energie", "Power"), AMBER), ("Boot", tr("Start & Sicherheit", "Boot & security"), SLATE)]
RISK_TEXT = {"safe": ("sicher", "safe"), "moderate": ("moderat", "moderate"),
             "advanced": ("riskant", "advanced")}
IMPACT_TEXT = {"high": ("hohe Wirkung", "high impact"), "medium": ("mittlere Wirkung", "medium impact"),
               "low": ("geringe Wirkung", "low impact")}
DETECTED = "  ✓ " + tr("erkannt", "detected")


class BiosGuideTab(Page):
    def __init__(self, parent, hw: HardwareInfo, **kw):
        super().__init__(parent, tr("BIOS-Guide", "BIOS Guide"),
                         tr("Alle Plattformen mit den wichtigen BIOS-Einstellungen und den Menüpfaden je "
                            "Board-Hersteller — deine wird erkannt und ist vorgewählt. Nur Anzeige: du stellst "
                            "alles selbst im BIOS ein.",
                            "Every platform with the BIOS settings that matter and the menu paths per board "
                            "maker — yours is detected and pre-selected. Read-only: you set everything in "
                            "the BIOS yourself."),
                         color=AMBER, **kw)
        self.hw = hw
        self.detector = BiosDetector()
        self._detected_id = detect_profile(hw.cpu_name)
        self._detected_vendor = vendor_of(hw.mb_manufacturer)
        self._profile = get_profile(self._detected_id)
        self._vendor = self._detected_vendor
        self._detect_results: dict = {}
        self._detecting = False
        self._build()
        self._refresh_view()
        self.after(150, self._run_detect)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _profile_label(self, p) -> str:
        return p.name + (DETECTED if p.id == self._detected_id else "")

    def _vendor_label(self, key: str) -> str:
        name = dict(VENDORS)[key]
        return name + (DETECTED if key == self._detected_vendor and key != "other" else "")

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

        sel = ResponsiveGrid(inner, min_width=420, max_cols=2, gap=12, bg=CARD_BG)   # one column when narrow
        sel.pack(fill="x")
        self._profile_labels = {self._profile_label(p): p.id
                                for p in [get_profile(self._detected_id)]
                                + [p for p in PROFILES if p.id != self._detected_id]}
        self._vendor_labels = {self._vendor_label(k): k for k, _n in VENDORS}
        cell = tk.Frame(sel, bg=CARD_BG)
        tk.Label(cell, text=tr("Plattform", "Platform"), font=F_BB, fg=TEXT2, bg=CARD_BG,
                 anchor="w").pack(fill="x")
        self.profile_var = tk.StringVar(value=self._profile_label(self._profile))
        self.profile_combo = ctk.CTkOptionMenu(cell, variable=self.profile_var,
                                               values=list(self._profile_labels), height=30,
                                               dynamic_resizing=False,
                                               command=lambda _v: self._on_profile_change())
        self.profile_combo.pack(fill="x", pady=(4, 0))
        sel.add(cell)
        cell = tk.Frame(sel, bg=CARD_BG)
        tk.Label(cell, text=tr("Board-Hersteller (für die Menüpfade)", "Board maker (for the menu paths)"),
                 font=F_BB, fg=TEXT2, bg=CARD_BG, anchor="w").pack(fill="x")
        self.vendor_var = tk.StringVar(value=self._vendor_label(self._vendor))
        self.vendor_combo = ctk.CTkOptionMenu(cell, variable=self.vendor_var, values=list(self._vendor_labels),
                                              height=30, dynamic_resizing=False,
                                              command=lambda _v: self._on_vendor_change())
        self.vendor_combo.pack(fill="x", pady=(4, 0))
        sel.add(cell)

        self.lbl_profile_info = WrapLabel(inner, text="", font=F_S, fg=TEXT2, bg=CARD_BG)
        self.lbl_profile_info.pack(fill="x", pady=(10, 0))

        filt = tk.Frame(inner, bg=CARD_BG)
        filt.pack(fill="x", pady=(10, 0))
        tk.Label(filt, text=tr("Anzeigen:", "Show:"), font=F_S, fg=DIM, bg=CARD_BG).pack(side="left", padx=(0, 6))
        self._filter_vars = {}
        for cat, label, color in CATS:
            v = tk.BooleanVar(value=True)
            self._filter_vars[cat] = v
            CheckBox(filt, v, accent=color, bg=CARD_BG, text=label, font=F_S, size=16,
                     command=self._refresh_view).pack(side="left", padx=(0, 10))
        tk.Frame(filt, bg=BORDER, width=1, height=18).pack(side="left", padx=8)
        self._only_todo = tk.BooleanVar(value=False)
        CheckBox(filt, self._only_todo, accent=ERR, bg=CARD_BG, font=F_S, size=16,
                 text=tr("Nur noch zu erledigende", "Only what's left to do"),
                 command=self._refresh_view).pack(side="left")

        leg = tk.Frame(inner, bg=CARD_BG)
        leg.pack(fill="x", pady=(10, 0))
        for color, de, en in [(COL_OK, "● bereits eingestellt", "● already set"),
                              (COL_TODO, "● noch einstellen", "● still to set"),
                              (COL_UNKNOWN, "● von Windows aus nicht prüfbar", "● not detectable from Windows")]:
            tk.Label(leg, text=tr(de, en), font=F_XS, fg=color, bg=CARD_BG).pack(side="left", padx=(0, 12))
        WrapLabel(inner, text=tr("Menünamen unterscheiden sich je nach BIOS-Version — die Suche im BIOS "
                                 "(ASUS: F9, MSI: Strg+F, Gigabyte: Strg+F im Advanced Mode) findet eine "
                                 "Einstellung über ihren Namen.",
                                 "Menu names differ between BIOS versions — the BIOS's search (ASUS: F9, "
                                 "MSI: Ctrl+F, Gigabyte: Ctrl+F in Advanced Mode) finds a setting by its name."),
                  font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(8, 0))

        self._inner = tk.Frame(b, bg=APP_BG)
        self._inner.pack(fill="x", padx=10)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_profile_change(self, _=None):
        pid = self._profile_labels.get(self.profile_var.get())
        if pid:
            self._profile = get_profile(pid)
            self._refresh_view()

    def _on_vendor_change(self, _=None):
        key = self._vendor_labels.get(self.vendor_var.get())
        if key:
            self._vendor = key
            self._refresh_view()

    # ── Detection ─────────────────────────────────────────────────────────────

    def _run_detect(self):
        if self._detecting:
            return
        self._detecting = True
        self.btn_detect.configure(state="disabled", text=tr("Prüfe …", "Checking …"))
        self.lbl_detect_status.config(text=tr("Lese System-Zustand …", "Reading system state …"), fg=DIM)
        box: dict = {}

        def work():
            try:
                box["r"] = self.detector.detect_all()
            except Exception:
                box["r"] = {}

        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():                     # main thread only: after() from a worker raises on 3.14
            if th.is_alive():
                self.after(100, poll)
                return
            self._detect_results = box.get("r") or {}
            self._detecting = False
            self._on_detect_done()
        self.after(100, poll)

    def _on_detect_done(self):
        self.btn_detect.configure(state="normal", text=tr("System-Status prüfen", "Check system state"))
        self._refresh_view()

    def _detect_summary(self):
        keys = {s.detect_key for s in self._profile.settings if s.detect_key}
        found = [self._detect_results[k] for k in keys if k in self._detect_results]
        active = sum(1 for r in found if r.active)
        if not found:
            self.lbl_detect_status.config(text="", fg=DIM)
            return
        self.lbl_detect_status.config(
            text=f"{active}/{len(found)} " + tr("prüfbare Einstellungen bereits gesetzt",
                                               "detectable settings already set"),
            fg=COL_OK if active == len(found) else AMBER)

    # ── Render ────────────────────────────────────────────────────────────────

    def _refresh_view(self):
        for w in self._inner.winfo_children():
            w.destroy()
        p = self._profile
        is_mine = p.id == self._detected_id
        info = (f"{p.cpus}   ·   {p.platform}"
                + ("" if is_mine else "\n" + tr("Nicht deine erkannte Plattform — zum Nachlesen.",
                                                "Not your detected platform — for reference.")))
        self.lbl_profile_info.config(text=info, fg=TEXT2 if is_mine else AMBER)
        if not self._detecting:
            if is_mine:
                self._detect_summary()
            else:
                self.lbl_detect_status.config(text="", fg=DIM)

        if p.notes:
            nf = tk.Frame(self._inner, bg=tint(AMBER, APP_BG, 0.10), highlightthickness=1,
                          highlightbackground=tint(AMBER, APP_BG, 0.35))
            nf.pack(fill="x", pady=(0, 10))
            WrapLabel(nf, text=f"ℹ  {p.notes}", font=F_S, fg=AMBER,
                      bg=tint(AMBER, APP_BG, 0.10)).pack(fill="x", padx=12, pady=8)

        only_todo = self._only_todo.get()
        shown = 0
        for cat, label, color in CATS:
            if not self._filter_vars[cat].get():
                continue
            settings = [s for s in p.settings if s.category == cat]
            if only_todo:
                settings = [s for s in settings if not self._is_done(s)]
            if not settings:
                continue
            section_title(self._inner, label, color, bg=APP_BG).pack(fill="x", pady=(8 if shown else 0, 8))
            grid = ResponsiveGrid(self._inner, min_width=420, max_cols=2, gap=12)
            grid.pack(fill="x")
            for s in settings:
                grid.add(self._build_card(grid, s, color))
                shown += 1

        if shown == 0:
            tk.Label(self._inner,
                     text=tr("✓ Alle prüfbaren Einstellungen sind bereits gesetzt!",
                             "✓ All detectable settings are already set!") if only_todo else
                     tr("Keine Einstellungen in den gewählten Bereichen.", "No settings in the chosen areas."),
                     font=("Segoe UI Semibold", 12), fg=COL_OK if only_todo else DIM, bg=APP_BG).pack(pady=30)

    def _is_done(self, s: BiosSetting) -> bool:
        if self._profile.id != self._detected_id:
            return False                       # the status is about this PC's platform only
        r = self._detect_results.get(s.detect_key) if s.detect_key else None
        return bool(r and r.active)

    def _build_card(self, parent, s: BiosSetting, color: str):
        detect = (self._detect_results.get(s.detect_key)
                  if s.detect_key and self._profile.id == self._detected_id else None)
        if detect is None:
            status_color = COL_UNKNOWN
            status_tip = (tr("Von Windows aus nicht prüfbar — im BIOS nachsehen",
                             "Not detectable from Windows — check in the BIOS")
                          if self._profile.id == self._detected_id or not s.detect_key else
                          tr("Status nur für deine erkannte Plattform", "Status only for your detected platform"))
        elif detect.active:
            status_color, status_tip = COL_OK, detect.note or tr("Bereits gesetzt", "Already set")
        else:
            status_color, status_tip = COL_TODO, detect.note or tr("Noch einstellen", "Still to set")

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

        vendor = self._vendor
        path = s.path_for(vendor)
        who = dict(VENDORS).get(vendor, "") if vendor in s.paths else tr("allgemein", "generic")
        WrapLabel(body, text=f"📍 {who}: {path}", font=F_XS, fg=VIOLET, bg=bg).pack(fill="x", pady=(0, 4))
        WrapLabel(body, text=s.explanation, font=F_S, fg=TEXT2, bg=bg).pack(fill="x")
        return card
