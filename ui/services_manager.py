"""
GameOptimizerPro v2.0 — Services Manager
Eigenes Fenster (aus v1 portiert): zeigt die bekannten, meist verzichtbaren
Windows-Dienste mit echtem Status/Starttyp und kann sie deaktivieren bzw. den
ursprünglichen Starttyp wiederherstellen. Logik: core/services.py
"""

import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from core import services

DARK  = "#0d1117"
DARK2 = "#161b22"
DARK3 = "#1c2128"
BORD  = "#2d333b"
ACC   = "#00d9ff"
OK    = "#22c55e"
WRN   = "#f59e0b"
ERR   = "#ef4444"
DIM   = "#6b7280"
TXT   = "#d0d8e8"
WHT   = "#f0f4ff"
FM    = ("Consolas", 9)
FL    = ("Segoe UI", 9)


class ServicesManagerWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("GameOptimizerPro — Services Manager")
        self.geometry("1080x640")
        self.configure(bg=DARK)
        self.minsize(820, 420)
        self._items: dict[str, services.ServiceInfo] = {}
        self._busy = False
        self._admin = services.is_admin()
        self._build()
        self.after(100, self._load)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=DARK2, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙  Services Manager", font=("Segoe UI", 13, "bold"),
                 fg=ACC, bg=DARK2).pack(side="left", padx=16, pady=8)
        tk.Label(hdr, text="Meist verzichtbare Windows-Dienste — Status und Starttyp live",
                 font=FL, fg=DIM, bg=DARK2).pack(side="left")
        self.lbl_count = tk.Label(hdr, text="", font=FM, fg=DIM, bg=DARK2)
        self.lbl_count.pack(side="right", padx=16)
        tk.Button(hdr, text="⟳ Aktualisieren", command=self._load, font=FM, bg=DARK3, fg=TXT,
                  relief="flat", padx=10, pady=4, cursor="hand2").pack(side="right", padx=4)

        legend = tk.Frame(self, bg=DARK)
        legend.pack(fill="x", padx=12, pady=(6, 2))
        for color, text in ((OK, "● sicher deaktivierbar"),
                            (WRN, "● Vorsicht — schaltet eine Funktion ab (Nachfrage)"),
                            (DIM, "● bereits deaktiviert")):
            tk.Label(legend, text=text, font=FM, fg=color, bg=DARK).pack(side="left", padx=(0, 14))
        if not self._admin:
            tk.Label(legend, text="Nur Anzeige — zum Ändern GameOptimizerPro als Administrator starten",
                     font=FM, fg=WRN, bg=DARK).pack(side="right")

        style = ttk.Style()
        style.configure("SVC.Treeview", background=DARK2, foreground=TXT,
                        fieldbackground=DARK2, rowheight=26, font=FM, borderwidth=0)
        style.configure("SVC.Treeview.Heading", background=DARK3, foreground=ACC,
                        font=("Consolas", 8, "bold"), relief="flat")
        style.map("SVC.Treeview", background=[("selected", "#7c3aed")],
                  foreground=[("selected", WHT)])

        tree_f = tk.Frame(self, bg=DARK)
        tree_f.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        sb = ttk.Scrollbar(tree_f, orient="vertical")
        cols = ("display", "name", "status", "start", "cat", "safe")
        self.tree = ttk.Treeview(tree_f, columns=cols, show="headings", selectmode="extended",
                                 style="SVC.Treeview", yscrollcommand=sb.set)
        sb.config(command=self.tree.yview)
        for col, label, w, anchor in (
            ("display", "Dienst",     330, "w"),
            ("name",    "Name",       150, "w"),
            ("status",  "Status",      90, "center"),
            ("start",   "Starttyp",   170, "w"),
            ("cat",     "Kategorie",  100, "center"),
            ("safe",    "Sicher",      70, "center"),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor=anchor, minwidth=50)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("safe", foreground=OK)
        self.tree.tag_configure("caution", foreground=WRN)
        self.tree.tag_configure("disabled", foreground=DIM)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.lbl_detail = tk.Label(self, text="Dienst auswählen (Strg/Shift für mehrere).",
                                   font=FL, fg=DIM, bg=DARK, justify="left", anchor="w",
                                   wraplength=1040)
        self.lbl_detail.pack(fill="x", padx=14, pady=(2, 6))

        act = tk.Frame(self, bg=DARK2, height=46)
        act.pack(fill="x")
        act.pack_propagate(False)
        self.lbl_status = tk.Label(act, text="", font=FM, fg=DIM, bg=DARK2, anchor="w")
        self.lbl_status.pack(side="left", padx=14, fill="x", expand=True)
        tk.Button(act, text="Schließen", command=self.destroy, font=FM, bg=DARK3, fg=TXT,
                  relief="flat", padx=12, pady=6, cursor="hand2").pack(side="right", padx=4, pady=4)
        tk.Button(act, text="services.msc", command=self._open_msc, font=FM, bg=DARK3, fg=TXT,
                  relief="flat", padx=12, pady=6, cursor="hand2").pack(side="right", padx=4, pady=4)
        state = "normal" if self._admin else "disabled"
        self.btn_enable = tk.Button(act, text="✓  Aktivieren (Original)", command=self._enable,
                                    font=FM, bg=DARK3, fg=OK, relief="flat", padx=12, pady=6,
                                    cursor="hand2", state=state)
        self.btn_enable.pack(side="right", padx=4, pady=4)
        self.btn_disable = tk.Button(act, text="⊘  Deaktivieren", command=self._disable,
                                     font=FM, bg=DARK3, fg=WRN, relief="flat", padx=12, pady=6,
                                     cursor="hand2", state=state)
        self.btn_disable.pack(side="right", padx=4, pady=4)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load(self):
        self.lbl_count.config(text="Lade …")

        def work():
            try:
                items = services.list_services()
            except Exception as e:
                items, err = [], str(e)
            else:
                err = ""
            self.after(0, lambda: self._fill(items, err))
        threading.Thread(target=work, daemon=True).start()

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
            self.lbl_detail.config(text=f"{len(sel)} Dienste ausgewählt.", fg=TXT)
            return
        s = sel[0]
        start, delayed, origin = s.restore_target()
        note = (f"   ·   Aktivieren setzt: {services.start_label(start, delayed)} ({origin})"
                if s.disabled else "")
        self.lbl_detail.config(text=f"{s.display} ({s.name}) — {s.desc}{note}",
                               fg=TXT if s.safe else WRN)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run(self, fn, names, verb):
        if self._busy:
            return
        self._busy = True
        self.btn_disable.config(state="disabled")
        self.btn_enable.config(state="disabled")
        self.lbl_status.config(text=f"{verb} …", fg=DIM)

        def work():
            try:
                res = fn(names)
            except Exception as e:
                res = {n: (False, str(e)) for n in names}
            self.after(0, lambda: self._done(res, verb))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, res, verb):
        if not self.winfo_exists():
            return
        self._busy = False
        self.btn_disable.config(state="normal")
        self.btn_enable.config(state="normal")
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
