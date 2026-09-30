"""
GameOptimizerPro v2.0 — Services Manager page (ported from v1)
Shows the known, mostly dispensable Windows services with their real status
and start type; disables them or restores the original start type.
Logic: core/services.py
"""

import subprocess
import tkinter as tk
from tkinter import messagebox

from core import services
from ui.components import Page, Table, WrapLabel, button, run_async
from ui.theme import AMBER, APP_BG, DIM, ERR, F_S, F_XS, GREEN, MUTED, TEXT, TEXT2, icon_image, tr

OK, WRN = GREEN, AMBER


class ServicesManagerPage(Page):
    def __init__(self, parent, **kw):
        super().__init__(parent, tr("Dienste", "Services"),
                         tr("Meist verzichtbare Windows-Dienste — Status und Starttyp live; "
                            "„Aktivieren“ stellt den ursprünglichen Starttyp wieder her",
                            "Mostly dispensable Windows services — live status and start type; "
                            "'Enable' restores the original start type"),
                         color=AMBER, scroll=False, **kw)
        self._items: dict[str, services.ServiceInfo] = {}
        self._busy = False
        self._admin = services.is_admin()
        self._build()
        self.after(100, self._load)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        button(self.actions, tr("Aktualisieren", "Refresh"), self._load, kind="ghost", height=30,
               image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right")
        self.lbl_count = tk.Label(self.actions, text="", font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_count.pack(side="right", padx=10)

        b = self.body
        legend = tk.Frame(b, bg=APP_BG)
        legend.pack(fill="x", pady=(0, 8))
        for color, text in ((OK, tr("● sicher deaktivierbar", "● safe to disable")),
                            (WRN, tr("● Vorsicht — schaltet eine Funktion ab (Nachfrage)",
                                     "● caution — switches a feature off (asks first)")),
                            (MUTED, tr("● bereits deaktiviert", "● already disabled"))):
            tk.Label(legend, text=text, font=F_XS, fg=color, bg=APP_BG).pack(side="left", padx=(0, 14))
        if not self._admin:
            tk.Label(legend, text=tr("Nur Anzeige — zum Ändern GameOptimizerPro als Administrator starten",
                                     "View only — run GameOptimizerPro as administrator to change"),
                     font=F_XS, fg=WRN, bg=APP_BG).pack(side="right")

        act = tk.Frame(b, bg=APP_BG)
        act.pack(side="bottom", fill="x", pady=(10, 0))
        state = "normal" if self._admin else "disabled"
        button(act, "services.msc", self._open_msc, kind="ghost", height=32).pack(side="right", padx=(6, 0))
        self.btn_enable = button(act, tr("Aktivieren (Original)", "Enable (original)"), self._enable,
                                 height=32, state=state, image=icon_image("check", GREEN, 14),
                                 compound="left")
        self.btn_enable.pack(side="right", padx=(6, 0))
        self.btn_disable = button(act, tr("Deaktivieren", "Disable"), self._disable, kind="primary",
                                  color=AMBER, height=32, state=state)
        self.btn_disable.pack(side="right")
        self.lbl_status = WrapLabel(act, text="", font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.lbl_detail = WrapLabel(b, text=tr("Dienst auswählen (Strg/Shift für mehrere).",
                                               "Select a service (Ctrl/Shift for several)."),
                                    font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_detail.pack(side="bottom", fill="x", pady=(8, 0))

        tbl = Table(b, [
            ("display", tr("Dienst", "Service"),      320, "w"),
            ("name",    "Name",                       150, "w"),
            ("status",  "Status",                      90, "center"),
            ("start",   tr("Starttyp", "Start type"), 170, "w"),
            ("cat",     tr("Kategorie", "Category"),  100, "center"),
            ("safe",    tr("Sicher", "Safe"),          70, "center"),
        ], height=14)
        tbl.pack(fill="both", expand=True)
        self.tree = tbl.tree
        self.tree.tag_configure("safe", foreground=OK)
        self.tree.tag_configure("caution", foreground=WRN)
        self.tree.tag_configure("disabled", foreground=MUTED)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load(self):
        self.lbl_count.config(text="Lade …")

        def work():
            try:
                return services.list_services(), ""
            except Exception as e:
                return [], str(e)
        run_async(self, work, lambda res: self._fill(*res))

    def _fill(self, items, err=""):
        if not self.winfo_exists():
            return
        sel = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        self._items = {s.name: s for s in items}
        order = sorted(items, key=lambda s: (s.disabled, not s.safe, s.category, s.display.lower()))
        for s in order:
            tag = "disabled" if s.disabled else ("safe" if s.safe else "caution")
            self.tree.insert("", "end", iid=s.name, tags=(tag,), values=(
                s.display, s.name, s.status, s.start_text, s.category, "Ja" if s.safe else "Nein"))
        keep = [i for i in sel if i in self._items]
        if keep:
            self.tree.selection_set(keep)
        n_off = sum(1 for s in items if s.disabled)
        self.lbl_count.config(text=f"{len(items)} Dienste gefunden · {n_off} deaktiviert")
        if err:
            self.lbl_status.config(text=f"Fehler beim Lesen: {err}", fg=ERR)

    def _selected(self) -> list:
        return [self._items[i] for i in self.tree.selection() if i in self._items]

    def _on_select(self, _e=None):
        sel = self._selected()
        if not sel:
            self.lbl_detail.config(text="Dienst auswählen (Strg/Shift für mehrere).", fg=DIM)
            return
        if len(sel) > 1:
            self.lbl_detail.config(text=f"{len(sel)} Dienste ausgewählt.", fg=TEXT)
            return
        s = sel[0]
        start, delayed, origin = s.restore_target()
        note = (f"   ·   Aktivieren setzt: {services.start_label(start, delayed)} ({origin})"
                if s.disabled else "")
        self.lbl_detail.config(text=f"{s.display} ({s.name}) — {s.desc}{note}",
                               fg=TEXT if s.safe else WRN)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run(self, fn, names, verb):
        if self._busy:
            return
        self._busy = True
        self.btn_disable.configure(state="disabled")
        self.btn_enable.configure(state="disabled")
        self.lbl_status.config(text=f"{verb} …", fg=DIM)

        def work():
            try:
                return fn(names)
            except Exception as e:
                return {n: (False, str(e)) for n in names}
        run_async(self, work, lambda res: self._done(res, verb))

    def _done(self, res, verb):
        if not self.winfo_exists():
            return
        self._busy = False
        state = "normal" if self._admin else "disabled"
        self.btn_disable.configure(state=state)
        self.btn_enable.configure(state=state)
        ok = [n for n, (good, _) in res.items() if good]
        bad = [f"{n}: {msg}" for n, (good, msg) in res.items() if not good]
        notes = [f"{n}: {msg}" for n, (good, msg) in res.items() if good and msg]
        text = f"{verb}: {len(ok)} von {len(res)} erfolgreich."
        if notes:
            text += "   " + " · ".join(notes)
        self.lbl_status.config(text=text, fg=OK if not bad else WRN)
        if bad:
            messagebox.showwarning("Services Manager",
                                   "Nicht geändert:\n\n" + "\n".join(bad), parent=self)
        self._load()

    def _disable(self):
        sel = [s for s in self._selected() if not s.disabled]
        if not sel:
            self.lbl_status.config(text="Nichts ausgewählt (oder schon deaktiviert).", fg=DIM)
            return
        risky = [s for s in sel if not s.safe]
        if risky:
            lines = "\n".join(f"  • {s.display} — {s.desc}" for s in risky)
            if not messagebox.askyesno(
                    "Services Manager — Vorsicht",
                    f"{len(risky)} ausgewählte(r) Dienst(e) schalten eine Funktion ab:\n\n{lines}\n\n"
                    "Trotzdem deaktivieren?  (Rückgängig: 'Aktivieren' stellt den "
                    "ursprünglichen Starttyp wieder her.)", icon="warning", parent=self):
                return
        self._run(services.disable, [s.name for s in sel], "Deaktivieren")

    def _enable(self):
        sel = [s for s in self._selected() if s.disabled]
        if not sel:
            self.lbl_status.config(text="Nichts Deaktiviertes ausgewählt.", fg=DIM)
            return
        self._run(services.enable, [s.name for s in sel], "Aktivieren")

    def _open_msc(self):
        try:
            subprocess.Popen(["mmc.exe", "services.msc"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            messagebox.showerror("Fehler", f"services.msc konnte nicht geöffnet werden:\n{e}",
                                 parent=self)
