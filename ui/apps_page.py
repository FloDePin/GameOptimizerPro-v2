"""
GameOptimizerPro — Apps page
Two views:
  * Store apps: the installed Store apps with a plain name and a rating (core/app_removal.py) —
    select and remove (all users + the provisioned copy), a System Restore point first.
  * Install programs: a short, hand-picked list of gaming programs installed through winget
    (core/winget_installer.py) — tick and install, one after the other.
Nothing is read before the page is shown for the first time (both lists take a few seconds).
"""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import app_removal, services, winget_installer
from ui.components import LogView, Page, Table, WrapLabel, button, run_async
from ui.theme import (AMBER, APP_BG, BORDER, CARD_BG, CARD_BG2, DIM, ERR, F_S, F_XS, GREEN, INPUT_BG,
                      MUTED, TEXT, TEXT2, ctk_font, icon_image, mix, on_color, tr)

CAT_LABEL = {
    app_removal.BLOAT:    ("kann weg", "can go"),
    app_removal.OPTIONAL: ("wird evtl. genutzt", "may be in use"),
    app_removal.OTHER:    ("selbst entscheiden", "your call"),
}
CAT_COLOR = {app_removal.BLOAT: GREEN, app_removal.OPTIONAL: AMBER, app_removal.OTHER: TEXT2}


class AppsPage(Page):
    def __init__(self, parent, **kw):
        super().__init__(parent, tr("Apps", "Apps"),
                         tr("Store-Apps gezielt entfernen und die üblichen Programme eines Gaming-PCs "
                            "installieren — nichts passiert ohne deine Auswahl",
                            "Remove Store apps one by one and install the usual programs of a gaming PC — "
                            "nothing happens without your choice"),
                         color=GREEN, scroll=False, **kw)
        self._admin = services.is_admin()
        self._busy = False
        self._apps: dict[str, app_removal.AppInfo] = {}
        self._installed: set[str] = set()
        self._loaded = {"apps": False, "install": False}
        # a list being read: no second read (a double click on Refresh started two, and winget runs
        # side by side can fail), no removing / installing on a list that is about to change
        self._loading = {"apps": False, "install": False}
        self._winget = True                 # checked again whenever the install view is read
        self._view = "apps"
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.btn_refresh = button(self.actions, tr("Aktualisieren", "Refresh"), self._refresh, kind="ghost",
                                  height=30, image=icon_image("refresh", TEXT2, 14), compound="left")
        self.btn_refresh.pack(side="right")
        self.lbl_count = tk.Label(self.actions, text="", font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_count.pack(side="right", padx=10)

        bar = tk.Frame(self.body, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 10))
        self._view_keys = {tr("Store-Apps entfernen", "Remove Store apps"): "apps",
                           tr("Programme installieren", "Install programs"): "install"}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._view_keys), height=32, font=ctk_font(12),
                                          selected_color=mix(CARD_BG2, GREEN, 0.45),
                                          selected_hover_color=mix(CARD_BG2, GREEN, 0.6),
                                          command=lambda v: self._show_view(self._view_keys[v]))
        self.seg.pack(side="left")
        if not self._admin:
            tk.Label(bar, text=tr("Nur Anzeige — zum Ändern GameOptimizerPro als Administrator starten",
                                  "View only — run GameOptimizerPro as administrator to change"),
                     font=F_XS, fg=AMBER, bg=APP_BG).pack(side="right")

        holder = tk.Frame(self.body, bg=APP_BG)
        holder.pack(fill="both", expand=True)
        self._views = {}
        for key, builder in (("apps", self._build_apps), ("install", self._build_install)):
            card = ctk.CTkFrame(holder, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
            inner = tk.Frame(card, bg=CARD_BG)
            inner.pack(fill="both", expand=True, padx=16, pady=14)
            builder(inner)
            self._views[key] = card
        self._show_view("apps", load=False)

    def _logbox(self, p, height=6):
        box = ctk.CTkFrame(p, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER)
        box.pack(side="bottom", fill="x", pady=(10, 0))
        log = LogView(box, height=height)
        log.pack(fill="both", expand=True, padx=6, pady=6)
        return log

    def _build_apps(self, p):
        WrapLabel(p, text=tr(
            "Grün = vorinstallierte Extras, die weg können · Gelb = Apps, die manche nutzen (es wird vorher "
            "gefragt) · Rest = selbst installiert oder unbekannt. Windows-Bestandteile, der Store, App-Installer, "
            "Treiber-Apps, Codecs und Sprachpakete werden gar nicht erst angezeigt. Entfernt wird für alle "
            "Benutzer samt bereitgestelltem Paket (Funktionsupdates bringen die App sonst zurück) — vorher ein "
            "Wiederherstellungspunkt: nur er holt eine entfernte App zurück (oder der Microsoft Store).",
            "Green = preinstalled extras that can go · yellow = apps some people use (you are asked first) · "
            "the rest = installed by you or unknown. Windows parts, the Store, App Installer, driver apps, codecs "
            "and language packs are not even listed. Removal is for every user including the provisioned package "
            "(feature updates bring the app back otherwise) — a restore point first: only it brings a removed "
            "app back (or the Microsoft Store)."), font=F_S, fg=TEXT2, bg=CARD_BG).pack(fill="x", pady=(0, 8))
        act = tk.Frame(p, bg=CARD_BG)
        act.pack(side="bottom", fill="x", pady=(8, 0))
        self.btn_remove = button(act, tr("Ausgewählte entfernen", "Remove selected"), self._remove, kind="primary",
                                 color=ERR, height=32, state="normal" if self._admin else "disabled",
                                 image=icon_image("delete", on_color(ERR), 14), compound="left")
        self.btn_remove.pack(side="right")
        button(act, tr("Alle grünen auswählen", "Select all green"), self._select_bloat, kind="ghost",
               height=32).pack(side="right", padx=(0, 8))
        self.lbl_apps = WrapLabel(act, text="", font=F_S, fg=DIM, bg=CARD_BG)
        self.lbl_apps.pack(side="left", fill="x", expand=True)
        self.log_apps = self._logbox(p)
        tbl = Table(p, [
            ("display", tr("App", "App"),            260, "w"),
            ("cat",     tr("Einstufung", "Rating"),  130, "w"),
            ("note",    tr("Hinweis", "Note"),       330, "w"),
            ("name",    tr("Paket", "Package"),      230, "w"),
        ], height=12)
        tbl.pack(fill="both", expand=True)
        self.tree_apps = tbl.tree
        for cat, color in CAT_COLOR.items():
            self.tree_apps.tag_configure(cat, foreground=color)
        self.tree_apps.bind("<<TreeviewSelect>>", lambda _e: self._apps_selected())

    def _build_install(self, p):
        WrapLabel(p, text=tr(
            "Über winget, den Paketmanager von Windows, aus seiner offiziellen Quelle — leise und nacheinander. "
            "Nur was du auswählst (Strg/Shift für mehrere). Grafiktreiber und die NVIDIA-App gibt es dort nicht: "
            "die beim Hersteller holen.",
            "Through winget, Windows' package manager, from its official source — silently, one after the other. "
            "Only what you select (Ctrl/Shift for several). Graphics drivers and the NVIDIA app are not in it: get "
            "those from the manufacturer."), font=F_S, fg=TEXT2, bg=CARD_BG).pack(fill="x", pady=(0, 8))
        act = tk.Frame(p, bg=CARD_BG)
        act.pack(side="bottom", fill="x", pady=(8, 0))
        self.btn_install = button(act, tr("Ausgewählte installieren", "Install selected"), self._install,
                                  kind="primary", color=GREEN, height=32,
                                  state="normal" if self._admin else "disabled",
                                  image=icon_image("download", on_color(GREEN), 14), compound="left")
        self.btn_install.pack(side="right")
        self.lbl_install = WrapLabel(act, text="", font=F_S, fg=DIM, bg=CARD_BG)
        self.lbl_install.pack(side="left", fill="x", expand=True)
        self.log_install = self._logbox(p)
        tbl = Table(p, [
            ("name",   tr("Programm", "Program"),  240, "w"),
            ("group",  tr("Bereich", "Area"),      170, "w"),
            ("state",  "Status",                   110, "center"),
            ("note",   tr("Hinweis", "Note"),      420, "w"),
        ], height=12)
        tbl.pack(fill="both", expand=True)
        self.tree_inst = tbl.tree
        self.tree_inst.tag_configure("installed", foreground=MUTED)
        self.tree_inst.tag_configure("missing", foreground=TEXT)

    # ── Views ─────────────────────────────────────────────────────────────────

    def on_show(self):
        if not self._loaded[self._view]:
            self._refresh()

    def _show_view(self, key, load=True):
        self._view = key
        for k, f in self._views.items():
            if k != key:
                f.pack_forget()
        self._views[key].pack(fill="both", expand=True)
        self.seg.set(next(lbl for lbl, k in self._view_keys.items() if k == key))
        self._update_count()
        self._update_buttons()
        if load and not self._loaded[key]:
            self._refresh()

    def _refresh(self):
        if self._busy or self._loading[self._view]:
            return
        if self._view == "apps":
            self._load_apps()
        else:
            self._load_installed()

    def _update_buttons(self):
        """Remove / install: admin rights, nothing else running, the list read; install also needs
        winget — installed later, 'Refresh' finds it and frees the button again."""
        def state(ok):
            return "normal" if ok else "disabled"
        free = self._admin and not self._busy
        self.btn_remove.configure(state=state(free and not self._loading["apps"]))
        self.btn_install.configure(state=state(free and not self._loading["install"] and self._winget))
        self.btn_refresh.configure(state=state(not self._busy and not self._loading[self._view]))

    def _update_count(self):
        if self._loading[self._view]:
            self.lbl_count.config(text=tr("Lese installierte Apps …", "Reading installed apps …")
                                  if self._view == "apps" else
                                  tr("Prüfe installierte Programme …", "Checking installed programs …"))
            return
        if self._view == "apps":
            n = len(self._apps)
            green = sum(1 for a in self._apps.values() if a.category == app_removal.BLOAT)
            text = tr(f"{n} Apps · {green} können weg", f"{n} apps · {green} can go") if self._loaded["apps"] else ""
        else:
            n = len(winget_installer.CATALOG)
            have = len(self._installed)
            text = (tr(f"{n} Programme · {have} installiert", f"{n} programs · {have} installed")
                    if self._loaded["install"] else "")
        self.lbl_count.config(text=text)

    # ── Store apps ───────────────────────────────────────────────────────────

    def _load_apps(self):
        self._loading["apps"] = True
        self._update_count()
        self._update_buttons()

        def done(res):
            self._loading["apps"] = False
            if not self.winfo_exists():
                return
            if isinstance(res, Exception):
                self.log_apps.append(tr(f"Fehler beim Lesen: {res}", f"Error reading: {res}"), "error")
                res = []
            self._fill_apps(res)
            self._update_buttons()
        run_async(self, app_removal.list_apps, done)

    def _fill_apps(self, apps):
        sel = set(self.tree_apps.selection())
        self.tree_apps.delete(*self.tree_apps.get_children())
        self._apps = {a.name: a for a in apps}
        for a in apps:
            de, en = CAT_LABEL[a.category]
            self.tree_apps.insert("", "end", iid=a.name, tags=(a.category,),
                                  values=(a.display, tr(de, en), a.note, a.name))
        keep = [i for i in sel if i in self._apps]
        if keep:
            self.tree_apps.selection_set(keep)
        self._loaded["apps"] = True
        self._update_count()
        self._apps_selected()

    def _select_bloat(self):
        ids = [n for n, a in self._apps.items() if a.category == app_removal.BLOAT]
        self.tree_apps.selection_set(ids)
        if not ids:
            self.lbl_apps.config(text=tr("Keine vorinstallierten Extras mehr da.", "No preinstalled extras left."),
                                 fg=GREEN)

    def _apps_selected(self):
        sel = [self._apps[i] for i in self.tree_apps.selection() if i in self._apps]
        if not sel:
            self.lbl_apps.config(text=tr("App(s) auswählen (Strg/Shift für mehrere).",
                                         "Select app(s) (Ctrl/Shift for several)."), fg=DIM)
        else:
            self.lbl_apps.config(text=tr(f"{len(sel)} ausgewählt.", f"{len(sel)} selected."), fg=TEXT)

    def _remove(self):
        if self._busy or self._loading["apps"]:
            return
        sel = [self._apps[i] for i in self.tree_apps.selection() if i in self._apps]
        if not sel:
            self._apps_selected()
            return
        names = "\n".join(f"  • {a.display}" + (f" — {a.note}" if a.note else "") for a in sel[:25])
        more = "" if len(sel) <= 25 else tr(f"\n  … und {len(sel) - 25} weitere", f"\n  … and {len(sel) - 25} more")
        risky = [a for a in sel if a.category != app_removal.BLOAT]
        head = (tr(f"{len(risky)} davon werden evtl. genutzt.\n\n", f"{len(risky)} of them may be in use.\n\n")
                if risky else "")
        if not messagebox.askyesno(
                tr("Apps entfernen", "Remove apps"),
                head + tr(f"{len(sel)} App(s) für alle Benutzer entfernen?\n\n", f"Remove {len(sel)} app(s) for every user?\n\n")
                + names + more + tr("\n\nVorher wird ein Wiederherstellungspunkt erstellt. Zurück holt eine App nur er "
                                    "— oder der Microsoft Store.",
                                    "\n\nA restore point is made first. Only it brings an app back — or the "
                                    "Microsoft Store."),
                icon="warning" if risky else "question", parent=self):
            return
        self._set_busy(True)
        self.log_apps.clear()
        from core import restore_point
        self.log_apps.append(tr("Wiederherstellungspunkt …", "Restore point …"), "dim")

        def work():
            res = {}
            for i, a in enumerate(sel, 1):
                self.log_apps.append(f"[{i}/{len(sel)}] {a.display} …", "info")
                good, why = app_removal.remove(a.name)
                res[a.name] = (good, why)
                self.log_apps.append("  " + (tr("✓ entfernt", "✓ removed") if good
                                             else tr(f"✗ nicht entfernt: {why}", f"✗ not removed: {why}")),
                                     "success" if good else "warning")
            return res

        def done(res):
            if not self.winfo_exists():
                return
            self._set_busy(False)
            if isinstance(res, Exception):
                self.log_apps.append(str(res), "error")
                res = {}
            ok = sum(1 for g, _w in res.values() if g)
            self.lbl_apps.config(text=tr(f"Entfernt: {ok} von {len(res)}.", f"Removed: {ok} of {len(res)}."),
                                 fg=GREEN if ok == len(res) else AMBER)
            self._load_apps()

        def rp_done(rp):
            # round 47 (found in v1): without a restore point the apps were removed anyway — now asked first
            if not self.winfo_exists():
                return
            ok, msg, _why = rp if not isinstance(rp, Exception) else (False, str(rp), "error")
            self.log_apps.append("  " + msg, "success" if ok else "warning")
            if not ok and not messagebox.askyesno(tr("Kein Wiederherstellungspunkt", "No restore point"),
                                                  restore_point.ask_text(msg), icon="warning", default="no",
                                                  parent=self):
                self.log_apps.append(tr("Abgebrochen — nichts entfernt.", "Cancelled — nothing removed."), "warning")
                self.lbl_apps.config(text=tr("Nichts entfernt.", "Nothing removed."), fg=AMBER)
                self._set_busy(False)
                return
            run_async(self, work, done)
        run_async(self, lambda: restore_point.create_ex("GameOptimizerPro before app removal"), rp_done)

    # ── Install programs ────────────────────────────────────────────────────

    def _load_installed(self):
        self._loading["install"] = True
        self._winget = winget_installer.winget_exe() is not None
        if not self._winget:
            self.log_install.append(tr("winget wurde nicht gefunden — installiere 'App-Installer' aus dem Microsoft "
                                       "Store, dann 'Aktualisieren'.",
                                       "winget was not found — install 'App Installer' from the Microsoft Store, then "
                                       "'Refresh'."), "warning")
        self._update_count()
        self._update_buttons()

        def done(res):
            self._loading["install"] = False
            if not self.winfo_exists():
                return
            if isinstance(res, Exception):
                self.log_install.append(str(res), "error")
                res = set()
            self._installed = set(res)
            self._fill_install()
            self._update_buttons()
        run_async(self, winget_installer.installed_ids, done)

    def _fill_install(self):
        sel = set(self.tree_inst.selection())
        self.tree_inst.delete(*self.tree_inst.get_children())
        groups = {k: tr(de, en) for k, de, en in winget_installer.GROUPS}
        order = {k: i for i, (k, _d, _e) in enumerate(winget_installer.GROUPS)}
        for p in sorted(winget_installer.CATALOG, key=lambda x: (order.get(x.group, 9), x.name.lower())):
            have = p.id in self._installed
            self.tree_inst.insert("", "end", iid=p.id, tags=("installed" if have else "missing",),
                                  values=(p.name, groups.get(p.group, p.group),
                                          tr("installiert", "installed") if have else "—", p.note))
        keep = [i for i in sel if i in {p.id for p in winget_installer.CATALOG}]
        if keep:
            self.tree_inst.selection_set(keep)
        self._loaded["install"] = True
        self._update_count()

    def _install(self):
        if self._busy or self._loading["install"] or not self._winget:
            return
        ids = list(self.tree_inst.selection())
        names = {p.id: p.name for p in winget_installer.CATALOG}
        todo = [i for i in ids if i in names and i not in self._installed]
        skipped = [names[i] for i in ids if i in self._installed]
        if not todo:
            self.lbl_install.config(text=tr("Nichts Neues ausgewählt (schon installiert oder keine Auswahl).",
                                            "Nothing new selected (already installed or no selection)."), fg=DIM)
            return
        if not messagebox.askyesno(
                tr("Programme installieren", "Install programs"),
                tr(f"{len(todo)} Programm(e) über winget installieren?\n\n", f"Install {len(todo)} program(s) through winget?\n\n")
                + "\n".join(f"  • {names[i]}" for i in todo)
                + (tr("\n\nSchon installiert, wird übersprungen: ", "\n\nAlready installed, skipped: ") + ", ".join(skipped)
                   if skipped else ""), parent=self):
            return
        self._set_busy(True)
        self.log_install.clear()

        def work():
            res = {}
            for n, pid in enumerate(todo, 1):
                self.log_install.append(f"[{n}/{len(todo)}] {names[pid]} …", "info")
                last = {"t": ""}

                def line(s, last=last):
                    if s != last["t"]:
                        last["t"] = s
                        self.log_install.append("    " + s[:160], "dim")
                good, why = winget_installer.install(pid, on_line=line)
                res[pid] = (good, why)
                self.log_install.append("  " + (tr("✓ installiert", "✓ installed") + (f" ({why})" if why else "")
                                                if good else tr(f"✗ fehlgeschlagen: {why}", f"✗ failed: {why}")),
                                        "success" if good else "warning")
            return res

        def done(res):
            if not self.winfo_exists():
                return
            self._set_busy(False)
            if isinstance(res, Exception):
                self.log_install.append(str(res), "error")
                res = {}
            ok = sum(1 for g, _w in res.values() if g)
            self.lbl_install.config(text=tr(f"Installiert: {ok} von {len(res)}.", f"Installed: {ok} of {len(res)}."),
                                    fg=GREEN if ok == len(res) else AMBER)
            self._load_installed()
        run_async(self, work, done)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._update_buttons()
