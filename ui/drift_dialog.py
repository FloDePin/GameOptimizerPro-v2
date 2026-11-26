"""
GameOptimizerPro — "Tweaks nicht mehr aktiv" dialog
One decision PER tweak: ticked = apply again, unticked = mark as not applied
(no more questions). "Später" changes nothing and asks again at the next start.
(It used to be one yes/no for all of them — e.g. re-applying the power plan
also forced back a taskbar layout the user had changed on purpose.)
Round 49: also the tweaks a newer version took out that are still applied ("leftovers"): ticked =
remove what they set (only their own values), unticked = keep it and stop asking. Before, only
"Revert all" cleaned them up — and that reverted every other tweak too.
"""

import tkinter as tk

import customtkinter as ctk

from ui import theme
from ui.components import CheckBox, button
from ui.theme import ACC, AMBER, APP_BG, CARD_BG, F_B, F_S, F_SB, TEXT, TEXT2
from ui.theme import tr


class DriftDialog(ctk.CTkToplevel):
    def __init__(self, parent, items, on_done, build_change=None, leftovers=()):
        """items: [(tweak_id, display name)]; on_done(reapply_ids, drop_ids, clean_ids, keep_ids);
        build_change: (old, new) Windows build when Windows was updated since the last start;
        leftovers: [(retired tweak id, display name)] still applied."""
        super().__init__(parent)
        self.title(tr("GameOptimizerPro — Tweaks nicht mehr aktiv", "GameOptimizerPro — tweaks no longer active"))
        icon = theme.app_icon_path()
        if icon:
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass
        # no resizable(): CustomTkinter re-colours the title bar 10 ms later, and a
        # transient dialog closed before that crashes Tk (access violation)
        self._on_done = on_done
        self.vars: dict[str, tk.BooleanVar] = {}
        self.left_vars: dict[str, tk.BooleanVar] = {}

        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        if items:
            self._build_drift(body, items, build_change)
        if leftovers:
            self._build_leftovers(body, leftovers, top=bool(items))

        btns = tk.Frame(body, bg=APP_BG)
        btns.pack(fill="x", pady=(16, 0))
        button(btns, tr("Später fragen", "Ask later"), self.destroy).pack(side="right", padx=(8, 0))
        button(btns, tr("Übernehmen", "Apply"), self.submit, kind="primary").pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.transient(parent)
            self.after(60, self._focus)
        except tk.TclError:
            pass

    def _build_leftovers(self, body, leftovers, top: bool):
        tk.Label(body, text=tr(f"{len(leftovers)} ausgemusterte(r) Tweak(s) noch angewendet",
                               f"{len(leftovers)} retired tweak(s) still applied"),
                 font=("Segoe UI Semibold", 13), fg=TEXT, bg=APP_BG).pack(anchor="w", pady=((18, 0) if top else 0))
        tk.Label(body, text=tr("Diese Version hat sie herausgenommen: sie wirken nicht wie beschrieben (Windows liest "
                               "den Wert nicht mehr oder nichts belegt eine Wirkung) oder sie schaden mehr als sie "
                               "nützen. Das Aufräumen entfernt nur die Werte, die sie selbst gesetzt haben.",
                               "This version took them out: they don't work as described (Windows no longer reads "
                               "the value, or nothing documents an effect) or they do more harm than good. The "
                               "clean-up removes only the values they set themselves."),
                 font=F_S, fg=TEXT2, bg=APP_BG, justify="left", wraplength=500).pack(anchor="w", pady=(4, 10))
        tk.Label(body, text=tr("Mit Haken: jetzt aufräumen (vorher Registry-Backup).\n"
                               "Ohne Haken: so lassen — keine erneute Nachfrage.",
                               "Ticked: clean up now (registry backup first).\nUnticked: leave it — not asked again."),
                 font=F_SB, fg=AMBER, bg=APP_BG, justify="left").pack(anchor="w", pady=(0, 10))
        card = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10)
        card.pack(fill="x")
        box = tk.Frame(card, bg=CARD_BG)
        box.pack(fill="x", padx=12, pady=10)
        for tid, name in leftovers:
            v = tk.BooleanVar(value=True)
            self.left_vars[tid] = v
            CheckBox(box, v, accent=ACC, bg=CARD_BG, text=name, font=F_B).pack(fill="x", anchor="w", pady=2)

    def _build_drift(self, body, items, build_change):
        tk.Label(body, text=tr(f"{len(items)} Tweak(s) nicht mehr vollständig aktiv", f"{len(items)} tweak(s) no longer fully active"),
                 font=("Segoe UI Semibold", 13), fg=TEXT, bg=APP_BG).pack(anchor="w")
        msg = tk.Label(body, text=tr("Du hast sie angewendet, aber sie sind nicht (mehr) vollständig "
                                  "aktiv — z. B. von einem Windows-Update zurückgesetzt, von dir "
                                  "selbst geändert, oder die Tweak-Version ist neuer und setzt "
                                  "inzwischen mehr.", "You applied them, but they are not (fully) active any more — e.g. reset by a Windows update, changed by you, or the tweak is newer and sets more by now."),
                       font=F_S, fg=TEXT2, bg=APP_BG, justify="left", wraplength=500)
        msg.pack(anchor="w", pady=(4, 10))
        if build_change:
            old, new = build_change
            tk.Label(body, text=tr(f"Windows wurde seit dem letzten Start aktualisiert (Build {old} → {new}) — "
                                   "Updates setzen Einstellungen oft zurück.",
                                   f"Windows was updated since the last start (build {old} → {new}) — "
                                   "updates often reset settings."),
                     font=F_S, fg=ACC, bg=APP_BG, justify="left", wraplength=500).pack(anchor="w", pady=(0, 10))
        tk.Label(body, text=tr("Mit Haken: jetzt erneut anwenden (vorher Registry-Backup).\n"
                            "Ohne Haken: als „nicht angewendet“ markieren — keine erneute Nachfrage.", "Ticked: apply again now (registry backup first).\nUnticked: mark as 'not applied' — not asked again."),
                 font=F_SB, fg=AMBER, bg=APP_BG, justify="left").pack(anchor="w", pady=(0, 10))

        card = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10)
        card.pack(fill="x")
        box = tk.Frame(card, bg=CARD_BG)
        box.pack(fill="x", padx=12, pady=10)
        for tid, name in items:
            v = tk.BooleanVar(value=True)
            self.vars[tid] = v
            CheckBox(box, v, accent=ACC, bg=CARD_BG, text=name, font=F_B).pack(fill="x", anchor="w", pady=2)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def submit(self):
        reapply = [t for t, v in self.vars.items() if v.get()]
        drop = [t for t, v in self.vars.items() if not v.get()]
        clean = [t for t, v in self.left_vars.items() if v.get()]
        keep = [t for t, v in self.left_vars.items() if not v.get()]
        self.destroy()
        self._on_done(reapply, drop, clean, keep)
