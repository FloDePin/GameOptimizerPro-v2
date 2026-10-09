"""
GameOptimizerPro v2.0 — "Tweaks nicht mehr aktiv" dialog
One decision PER tweak: ticked = apply again, unticked = mark as not applied
(no more questions). "Später" changes nothing and asks again at the next start.
(It used to be one yes/no for all of them — e.g. re-applying the power plan
also forced back a taskbar layout the user had changed on purpose.)
"""

import tkinter as tk

import customtkinter as ctk

from ui import theme
from ui.components import CheckBox, button
from ui.theme import ACC, AMBER, APP_BG, CARD_BG, F_B, F_S, F_SB, TEXT, TEXT2


class DriftDialog(ctk.CTkToplevel):
    def __init__(self, parent, items, on_done):
        """items: [(tweak_id, display name)]; on_done(reapply_ids, drop_ids)."""
        super().__init__(parent)
        self.title("GameOptimizerPro — Tweaks nicht mehr aktiv")
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

        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(body, text=f"{len(items)} Tweak(s) nicht mehr vollständig aktiv",
                 font=("Segoe UI Semibold", 13), fg=TEXT, bg=APP_BG).pack(anchor="w")
        msg = tk.Label(body, text="Du hast sie angewendet, aber sie sind nicht (mehr) vollständig "
                                  "aktiv — z. B. von einem Windows-Update zurückgesetzt, von dir "
                                  "selbst geändert, oder die Tweak-Version ist neuer und setzt "
                                  "inzwischen mehr.",
                       font=F_S, fg=TEXT2, bg=APP_BG, justify="left", wraplength=500)
        msg.pack(anchor="w", pady=(4, 10))
        tk.Label(body, text="Mit Haken: jetzt erneut anwenden (vorher Registry-Backup).\n"
                            "Ohne Haken: als „nicht angewendet“ markieren — keine erneute Nachfrage.",
                 font=F_SB, fg=AMBER, bg=APP_BG, justify="left").pack(anchor="w", pady=(0, 10))

        card = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10)
        card.pack(fill="x")
        box = tk.Frame(card, bg=CARD_BG)
        box.pack(fill="x", padx=12, pady=10)
        for tid, name in items:
            v = tk.BooleanVar(value=True)
            self.vars[tid] = v
            CheckBox(box, v, accent=ACC, bg=CARD_BG, text=name, font=F_B).pack(fill="x", anchor="w", pady=2)

        btns = tk.Frame(body, bg=APP_BG)
        btns.pack(fill="x", pady=(16, 0))
        button(btns, "Später fragen", self.destroy).pack(side="right", padx=(8, 0))
        button(btns, "Übernehmen", self.submit, kind="primary").pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.transient(parent)
            self.after(60, self._focus)
        except tk.TclError:
            pass

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
        self.destroy()
        self._on_done(reapply, drop)
