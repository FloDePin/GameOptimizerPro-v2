"""
GameOptimizerPro v2.0 — "Tweaks nicht mehr aktiv" dialog
One decision PER tweak: ticked = apply again, unticked = mark as not applied
(no more questions). "Später" changes nothing and asks again at the next start.
(It used to be one yes/no for all of them — e.g. re-applying the power plan
also forced back a taskbar layout the user had changed on purpose.)
"""

import tkinter as tk

BG, BG2, BG3 = "#0d1117", "#161b22", "#1c2128"
TXT, DIM, ACC, WRN = "#d0d8e8", "#6b7280", "#00d9ff", "#f59e0b"


class DriftDialog(tk.Toplevel):
    def __init__(self, parent, items, on_done):
        """items: [(tweak_id, display name)]; on_done(reapply_ids, drop_ids)."""
        super().__init__(parent)
        self.title("GameOptimizerPro — Tweaks nicht mehr aktiv")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._on_done = on_done
        self.vars: dict[str, tk.BooleanVar] = {}

        tk.Label(self, text=f"{len(items)} Tweak(s), die du angewendet hast, sind nicht (mehr) "
                            "vollständig aktiv — z. B. von einem Windows-Update zurückgesetzt, von "
                            "dir selbst geändert, oder die Tweak-Version ist neuer und setzt "
                            "inzwischen mehr.",
                 font=("Segoe UI", 9), fg=TXT, bg=BG, wraplength=520, justify="left"
                 ).pack(anchor="w", padx=14, pady=(12, 6))
        tk.Label(self, text="Mit Haken: jetzt erneut anwenden (vorher Registry-Backup).\n"
                            "Ohne Haken: als „nicht angewendet“ markieren — keine erneute Nachfrage.",
                 font=("Segoe UI", 9, "bold"), fg=WRN, bg=BG, justify="left"
                 ).pack(anchor="w", padx=14, pady=(0, 8))

        box = tk.Frame(self, bg=BG2, padx=10, pady=6)
        box.pack(fill="x", padx=14)
        for tid, name in items:
            v = tk.BooleanVar(value=True)
            self.vars[tid] = v
            tk.Checkbutton(box, text=name, variable=v, anchor="w", font=("Segoe UI", 9),
                           bg=BG2, fg=TXT, activebackground=BG2, activeforeground=TXT,
                           selectcolor=BG3, highlightthickness=0, bd=0
                           ).pack(fill="x", anchor="w", pady=1)

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=14, pady=12)
        tk.Button(btns, text="Später fragen", command=self.destroy, font=("Consolas", 9),
                  bg=BG3, fg=TXT, relief="flat", padx=12, pady=5, cursor="hand2"
                  ).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="✓ Übernehmen", command=self.submit, font=("Consolas", 9, "bold"),
                  bg=ACC, fg="#04121a", relief="flat", padx=12, pady=5, cursor="hand2"
                  ).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.transient(parent)
            self.grab_set()
        except tk.TclError:
            pass

    def submit(self):
        reapply = [t for t, v in self.vars.items() if v.get()]
        drop = [t for t, v in self.vars.items() if not v.get()]
        self.destroy()
        self._on_done(reapply, drop)
