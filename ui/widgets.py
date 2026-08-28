"""
GameOptimizerPro shared UI widgets and theme.
"""

import tkinter as tk
from tkinter import ttk
import queue

# ── Palette ───────────────────────────────────────────────────────────────────
BG0  = "#080b0f"
BG1  = "#0f1217"
BG2  = "#161b24"
BG3  = "#1e2530"
BOR  = "#252d3a"
BOR2 = "#2e3a4a"
ACC  = "#00d9ff"
ACC2 = "#7c3aed"
ACC3 = "#f59e0b"
OK   = "#22c55e"
WRN  = "#f59e0b"
ERR  = "#ef4444"
TXT  = "#d0d8e8"
DIM  = "#5a6880"
WHT  = "#f0f4ff"
VOLT = "#a78bfa"

FM   = ("Consolas", 9)
FL   = ("Segoe UI", 9)
FV   = ("Consolas", 12, "bold")
FH   = ("Segoe UI", 10, "bold")
FT   = ("Segoe UI", 14, "bold")


def apply_ttk_style(root=None):
    style = ttk.Style()
    style.theme_use("clam")

    # Global dark overrides for ALL ttk widgets
    # This fixes the white flash on Treeview/Combobox dropdowns
    if root:
        try:
            # Treeview rows
            root.option_add("*Treeview.background",       "#161b22")
            root.option_add("*Treeview.foreground",       "#d0d8e8")
            root.option_add("*Treeview.fieldBackground",  "#161b22")
            root.option_add("*Treeview.selectBackground", "#7c3aed")
            root.option_add("*Treeview.selectForeground", "#ffffff")
            # Combobox dropdown list
            root.option_add("*TCombobox*Listbox.background",       "#1c2128")
            root.option_add("*TCombobox*Listbox.foreground",       "#d0d8e8")
            root.option_add("*TCombobox*Listbox.selectBackground", "#7c3aed")
            root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        except: pass
    style.configure("TNotebook",     background=BG0, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG2, foreground=DIM,
                    padding=[16, 7], font=FL)
    style.map("TNotebook.Tab",
              background=[("selected", BG1)],
              foreground=[("selected", ACC)])
    style.configure("TFrame", background=BG0)
    style.configure("TV.Treeview",
                    background=BG2, foreground=TXT,
                    fieldbackground=BG2, rowheight=26, font=FL)
    style.configure("TV.Treeview.Heading",
                    background=BG3, foreground=ACC,
                    font=("Segoe UI", 9, "bold"), relief="flat")
    style.map("TV.Treeview",
              background=[("selected", ACC2)],
              foreground=[("selected", WHT)])
    style.configure("Vertical.TScrollbar",
                    background=BG3, troughcolor=BG1,
                    arrowcolor=DIM, relief="flat")


class HBar(tk.Frame):
    """Horizontal gauge bar with label and value."""
    def __init__(self, parent, label, unit="", color=ACC, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self.unit = unit
        self.color = color
        self._pct = 0.0
        tk.Label(self, text=label, font=FL, fg=DIM, bg=BG2,
                 width=13, anchor="w").pack(side="left", padx=(8, 4))
        self.cv = tk.Canvas(self, height=16, bg=BG3,
                            highlightthickness=1, highlightbackground=BOR)
        self.cv.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cv.bind("<Configure>", self._draw)
        self.lbl = tk.Label(self, text="--", font=FM, fg=color,
                            bg=BG2, width=9, anchor="e")
        self.lbl.pack(side="right", padx=(0, 8))

    def set(self, val, max_val, fmt=None):
        self._pct = min(1.0, max(0.0, val / max_val)) if max_val else 0
        self.lbl.config(text=fmt or f"{val:.0f}{self.unit}")
        self._draw()

    def _draw(self, *_):
        w = self.cv.winfo_width()
        h = self.cv.winfo_height()
        self.cv.delete("all")
        fw = int(w * self._pct)
        if fw > 2:
            self.cv.create_rectangle(0, 1, fw, h - 1, fill=self.color, outline="")
            tip = min(4, fw)
            r = min(255, int(self.color[1:3], 16) + 70)
            g = min(255, int(self.color[3:5], 16) + 70)
            b = min(255, int(self.color[5:7], 16) + 70)
            self.cv.create_rectangle(fw - tip, 1, fw, h - 1,
                                     fill=f"#{r:02x}{g:02x}{b:02x}", outline="")


class SecHdr(tk.Frame):
    def __init__(self, parent, title, **kw):
        super().__init__(parent, bg=BG1, **kw)
        tk.Label(self, text=title.upper(), font=("Segoe UI", 8, "bold"),
                 fg=ACC, bg=BG1).pack(side="left", padx=(8, 10))
        tk.Frame(self, bg=BOR, height=1).pack(side="left", fill="x", expand=True)


class LogBox(tk.Frame):
    """Scrollable log text box."""
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG1, **kw)
        sb = ttk.Scrollbar(self)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(self, font=FM, bg=BG2, fg=TXT,
                           insertbackground=ACC, relief="flat",
                           state="disabled", yscrollcommand=sb.set,
                           wrap="word", highlightthickness=1,
                           highlightbackground=BOR)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)
        self.txt.tag_config("info",    foreground=TXT)
        self.txt.tag_config("warning", foreground=WRN)
        self.txt.tag_config("error",   foreground=ERR)
        self.txt.tag_config("success", foreground=OK)
        self.txt.tag_config("header",  foreground=ACC)
        self.txt.tag_config("dim",     foreground=DIM)

        # Thread-Safety: Worker-Threads (Tweak-Apply/Revert/Preset) dürfen Tkinter
        # NICHT direkt anfassen — selbst self.after() aus einem Fremd-Thread wirft
        # "RuntimeError: main thread is not in main loop". Daher: append()/clear()
        # schreiben nur in eine thread-sichere Queue; ein Poller im Main-Thread
        # (per after() gestartet, was hier sicher ist) leert sie und aktualisiert
        # das Widget. So ist JEDER Aufrufer aus JEDEM Thread sicher.
        self._q = queue.Queue()
        self._alive = True
        self.after(120, self._drain)

    def append(self, msg: str, tag: str = "info"):
        from datetime import datetime
        self._q.put(("append", datetime.now().strftime("%H:%M:%S"), msg, tag))

    def clear(self):
        self._q.put(("clear",))

    def _drain(self):
        try:
            self.txt.config(state="normal")
            wrote = False
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "append":
                    _, ts, msg, tag = item
                    self.txt.insert("end", f"[{ts}] {msg}\n", tag)
                    wrote = True
                elif item[0] == "clear":
                    self.txt.delete("1.0", "end")
            if wrote:
                self.txt.see("end")
            self.txt.config(state="disabled")
        except tk.TclError:
            self._alive = False
            return   # Widget zerstört -> Poller stoppen
        if self._alive:
            try:
                self.after(120, self._drain)
            except (tk.TclError, RuntimeError):
                self._alive = False


def mk_btn(parent, text, cmd, bg=BG3, fg=TXT, bold=False, **kw):
    font = ("Segoe UI", 10, "bold") if bold else FL
    return tk.Button(parent, text=text, command=cmd, font=font,
                     bg=bg, fg=fg, relief="flat", cursor="hand2",
                     activebackground=bg, padx=12, pady=7, **kw)


def mk_tile(parent, label, value_text="--", color=ACC, unit=""):
    f = tk.Frame(parent, bg=BG3, padx=8, pady=6)
    tk.Label(f, text=label, font=("Segoe UI", 8), fg=DIM, bg=BG3).pack()
    vl = tk.Label(f, text=value_text, font=("Consolas", 18, "bold"),
                  fg=color, bg=BG3)
    vl.pack()
    if unit:
        tk.Label(f, text=unit, font=FM, fg=DIM, bg=BG3).pack()
    return f, vl
