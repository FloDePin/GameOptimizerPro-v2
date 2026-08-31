"""
GameOptimizerPro v2.1 — Per-Game Profiles + Tune History Tab
Two sub-sections: Game Profile Manager + Tune History
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
from datetime import datetime

from ui.widgets import *
from core.game_monitor import GameMonitor, GameEntry
from core.tune_history  import TuneHistory
from core.nvtune_core   import ProfileManager

DARK  = "#0d1117"
DARK2 = "#161b22"
DARK3 = "#1c2128"
BORD  = "#2d333b"
GAME_COLOR = "#22c55e"
HIST_COLOR = "#a78bfa"


class GamesTab(tk.Frame):
    def __init__(self, parent, game_monitor: GameMonitor,
                 pm: ProfileManager, logs_dir: str, **kw):
        super().__init__(parent, bg=DARK, **kw)
        self.gm      = game_monitor
        self.pm      = pm
        self.history = TuneHistory(logs_dir)
        self._build()

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        g_frame = tk.Frame(nb, bg=DARK)
        h_frame = tk.Frame(nb, bg=DARK)
        nb.add(g_frame, text="  🎮 Per-Game Profile  ")
        nb.add(h_frame, text="  📋 Tune History  ")

        self._build_games(g_frame)
        self._build_history(h_frame)

    # ── Per-Game Profiles ─────────────────────────────────────────────────────

    def _build_games(self, p):
        # Header
        hdr = tk.Frame(p, bg=DARK)
        hdr.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(hdr, text="🎮  Per-Game Profile",
                 font=("Segoe UI", 10, "bold"),
                 fg=GAME_COLOR, bg=DARK).pack(side="left")

        # Status indicator
        self.lbl_monitor_status = tk.Label(
            hdr, text="", font=("Consolas", 8), fg=DIM, bg=DARK)
        self.lbl_monitor_status.pack(side="right", padx=8)
        self._update_monitor_status()

        tk.Label(p,
                 text="Weist jedem Spiel automatisch ein GPU-Profil und/oder CPU-Kerne zu. "
                      "GameOptimizerPro überwacht im Hintergrund welche Prozesse laufen.",
                 font=("Segoe UI", 8), fg=DIM, bg=DARK,
                 wraplength=800).pack(padx=14, anchor="w")

        # CPU topology note (honest guidance — e.g. single-CCD = pinning useless)
        topo = self.gm.topology
        if topo is not None and topo.note:
            icon = "🧩" if (topo.ok and len(self.gm.cpu_pin_targets()) > 1) else "ℹ"
            tk.Label(p, text=f"{icon}  {topo.note}",
                     font=("Segoe UI", 8), fg="#7c8794", bg=DARK,
                     wraplength=800).pack(padx=14, anchor="w", pady=(2, 0))

        # Game list
        style = ttk.Style()
        style.configure("GM.Treeview",
            background=DARK2, foreground=TXT,
            fieldbackground=DARK2, rowheight=26, font=FM)
        style.configure("GM.Treeview.Heading",
            background=DARK3, foreground=GAME_COLOR,
            font=("Consolas", 8, "bold"), relief="flat")
        style.map("GM.Treeview",
            background=[("selected", "#7c3aed")],
            foreground=[("selected", WHT)])

        tree_f = tk.Frame(p, bg=DARK)
        tree_f.pack(fill="both", expand=True, padx=14, pady=6)

        sb = ttk.Scrollbar(tree_f, orient="vertical")
        cols = ("status", "game", "exe", "profile", "restore", "cpu")
        self.game_tree = ttk.Treeview(
            tree_f, columns=cols, show="headings",
            style="GM.Treeview", height=14, yscrollcommand=sb.set)
        sb.config(command=self.game_tree.yview)

        for col, label, w in [
            ("status",  "Status",          55),
            ("game",    "Spiel",           150),
            ("exe",     "Prozess (.exe)",  180),
            ("profile", "Profil bei Start",140),
            ("restore", "Profil danach",   130),
            ("cpu",     "CPU-Kerne",       150),
        ]:
            self.game_tree.heading(col, text=label)
            self.game_tree.column(col, width=w,
                anchor="center" if col == "status" else "w")

        self.game_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.game_tree.tag_configure("active",   foreground=GAME_COLOR)
        self.game_tree.tag_configure("disabled", foreground=DIM)
        self.game_tree.tag_configure("no_profile", foreground="#f59e0b")

        # Actions
        act = tk.Frame(p, bg=DARK)
        act.pack(fill="x", padx=14, pady=4)

        for text, cmd, bg, fg in [
            ("+ Spiel hinzufügen",     self._add_game,    GAME_COLOR, "#000"),
            ("✏ Profil zuweisen",      self._assign_profile, DARK3,   TXT),
            ("🧩 CPU-Kerne zuweisen",  self._assign_cpu,  "#3b82f6", WHT),
            ("⊘ Deaktivieren/Aktivieren", self._toggle_game, "#f59e0b", "#000"),
            ("🗑 Entfernen",            self._remove_game,  ERR,      WHT),
        ]:
            tk.Button(act, text=text, command=cmd,
                      font=("Consolas", 8), bg=bg, fg=fg,
                      relief="flat", padx=10, pady=6, cursor="hand2"
                      ).pack(side="left", padx=3)

        # Active game display
        self.lbl_active_game = tk.Label(
            p, text="Kein Spiel erkannt",
            font=("Consolas", 8), fg=DIM, bg=DARK2,
            anchor="w", padx=10, pady=5)
        self.lbl_active_game.pack(fill="x", padx=14, pady=(2, 8))

        # Wire game monitor callbacks
        self._pending_pin = None  # (name, ok, detail) set from monitor thread
        self.gm.on_game_start(self._on_game_start)
        self.gm.on_game_stop(self._on_game_stop)
        self.gm.on_cpu_pin(self._on_cpu_pin_result)

        self._refresh_games()

        # Periodic status update
        self.after(3000, self._periodic_update)

    def _update_monitor_status(self):
        if self.gm.is_running:
            active = self.gm.active_game
            if active:
                self.lbl_monitor_status.config(
                    text=f"● Überwachung aktiv | Spiel: {active}",
                    fg=GAME_COLOR)
            else:
                self.lbl_monitor_status.config(
                    text="● Überwachung aktiv | Kein Spiel erkannt", fg=DIM)
        else:
            self.lbl_monitor_status.config(text="○ Überwachung inaktiv", fg="#374151")

    def _refresh_games(self):
        for row in self.game_tree.get_children():
            self.game_tree.delete(row)

        active = (self.gm.active_game or "").lower()
        profiles = [p.name for p in self.pm.list_all()
                    if not p.name.startswith("__")]

        # Map cpu_target keys → short labels for display
        cpu_labels = {t.key: t.label for t in self.gm.cpu_pin_targets()}

        for game in self.gm.get_games():
            is_active  = game.exe.lower() == active
            has_profile = bool(game.profile_name)
            status = "▶ AKTIV" if is_active else ("✓" if (has_profile or game.cpu_target) else "○")

            tag = "active" if is_active else ("disabled" if not game.enabled else
                  ("no_profile" if not (has_profile or game.cpu_target) else ""))

            if game.cpu_target and game.cpu_target != "all":
                cpu_disp = cpu_labels.get(game.cpu_target, game.cpu_target)
            else:
                cpu_disp = "—"

            self.game_tree.insert("", "end",
                iid=game.exe,
                values=(
                    status,
                    game.display_name,
                    game.exe,
                    game.profile_name or "(nicht gesetzt)",
                    game.restore_profile.replace("__tray_default__", "← Standard"),
                    cpu_disp,
                ),
                tags=(tag,)
            )

    def _add_game(self):
        exe = simpledialog.askstring(
            "Spiel hinzufügen",
            "Prozessname der .exe Datei:\n(z.B. Cyberpunk2077.exe)"
        )
        if not exe:
            return
        exe = exe.strip()
        if not exe.lower().endswith(".exe"):
            exe += ".exe"
        name = simpledialog.askstring(
            "Anzeigename", f"Anzeigename für '{exe}':", initialvalue=exe.replace(".exe","")
        ) or exe
        self.gm.add_game(exe, name, "")
        self._refresh_games()

    def _assign_profile(self):
        sel = self.game_tree.selection()
        if not sel:
            messagebox.showwarning("", "Kein Spiel ausgewählt.")
            return
        exe = sel[0]
        profiles = [p.name for p in self.pm.list_all()
                    if not p.name.startswith("__")]
        if not profiles:
            messagebox.showinfo("",
                "Noch keine GPU-Profile vorhanden.\n"
                "Führe zuerst einen Auto-Tune durch.")
            return

        # Simple selection dialog
        win = tk.Toplevel(self)
        win.title("Profil zuweisen")
        win.configure(bg=DARK)
        win.geometry("350x280")
        win.resizable(False, False)

        tk.Label(win, text=f"Profil für: {exe}",
                 font=FL, fg=TXT, bg=DARK).pack(padx=14, pady=(12, 4), anchor="w")

        lb_var = tk.StringVar()
        lb = tk.Listbox(win, listvariable=tk.StringVar(value=profiles),
                        font=FM, bg=DARK2, fg=TXT,
                        selectbackground="#7c3aed", selectforeground=WHT,
                        highlightthickness=0, relief="flat", height=10)
        lb.pack(fill="both", expand=True, padx=14, pady=4)

        def _confirm():
            sel_idx = lb.curselection()
            if sel_idx:
                chosen = profiles[sel_idx[0]]
                self.gm.update_game(exe, chosen)
                self._refresh_games()
            win.destroy()

        tk.Button(win, text="Zuweisen", command=_confirm,
                  font=FM, bg=GAME_COLOR, fg="#000",
                  relief="flat", padx=12, pady=6, cursor="hand2"
                  ).pack(pady=8)

    def _assign_cpu(self):
        sel = self.game_tree.selection()
        if not sel:
            messagebox.showwarning("", "Kein Spiel ausgewählt.")
            return
        exe = sel[0]

        targets = self.gm.cpu_pin_targets()
        topo = self.gm.topology
        if not targets or (topo and not topo.ok):
            messagebox.showinfo("CPU-Pinning nicht verfügbar",
                (topo.note if topo and topo.note else
                 "CPU-Topologie konnte nicht gelesen werden."))
            return
        if len(targets) <= 1:
            # Only "all" available → nothing meaningful to pin
            messagebox.showinfo("Kein CPU-Pinning nötig",
                (topo.note if topo and topo.note else "") +
                "\n\nDeine CPU bietet keine sinnvolle Kern-Aufteilung "
                "(z.B. nur ein Chiplet). Das Zuweisen einzelner Kerne würde "
                "hier keinen Vorteil bringen.")
            return

        # Current target for this game
        cur = ""
        for g in self.gm.get_games():
            if g.exe == exe:
                cur = g.cpu_target or "all"
                break

        win = tk.Toplevel(self)
        win.title("CPU-Kerne zuweisen")
        win.configure(bg=DARK)
        win.geometry("470x470")
        win.resizable(False, False)

        tk.Label(win, text=f"🧩  CPU-Kerne für: {exe}",
                 font=FL, fg="#3b82f6", bg=DARK).pack(padx=14, pady=(12, 2), anchor="w")
        if topo and topo.note:
            tk.Label(win, text=topo.note, font=("Segoe UI", 8), fg=DIM, bg=DARK,
                     wraplength=430, justify="left").pack(padx=14, anchor="w", pady=(0, 6))

        sel_var = tk.StringVar(value=cur)
        opt_frame = tk.Frame(win, bg=DARK)
        opt_frame.pack(fill="both", expand=True, padx=14)
        for t in targets:
            tk.Radiobutton(
                opt_frame, text=t.label, value=t.key, variable=sel_var,
                font=FM, fg=TXT, bg=DARK, selectcolor=DARK3,
                activebackground=DARK, activeforeground=WHT,
                anchor="w", highlightthickness=0
            ).pack(fill="x", anchor="w", pady=1)

        tk.Label(win,
                 text="ℹ CPU Sets sind ein weicher Hinweis: Das Spiel läuft "
                      "bevorzugt auf den gewählten Kernen, kann bei Bedarf aber "
                      "ausweichen — es kann also nie ausgebremst werden.",
                 font=("Segoe UI", 7), fg="#6b7280", bg=DARK,
                 wraplength=440, justify="left").pack(padx=14, pady=(6, 0), anchor="w")

        # Anti-cheat caveat (always) — we modify a foreign game process
        tk.Label(win,
                 text="⚠ Anti-Cheat: Das Pinnen greift von außen in den Spielprozess "
                      "ein. Kernel-Anti-Cheats (EAC, BattlEye, Vanguard) könnten das "
                      "theoretisch als Manipulation werten — mit Anti-Cheat-Spielen "
                      "auf eigenes Risiko nutzen.",
                 font=("Segoe UI", 7), fg="#d08770", bg=DARK,
                 wraplength=440, justify="left").pack(padx=14, pady=(4, 0), anchor="w")

        # CCD-parking conflict — only relevant on multi-CCD machines
        if topo and len(topo.ccds) > 1:
            tk.Label(win,
                     text="⚠ CCD-Parking: Ist AMDs 3D-V-Cache-Optimizer bzw. das "
                          "Game-Bar-CCD-Parking aktiv, kann es unser Pinning "
                          "überschreiben oder geparkte Kerne stillschweigend ignorieren. "
                          "Für zuverlässiges Pinning diese in Windows/BIOS deaktivieren.",
                     font=("Segoe UI", 7), fg="#d08770", bg=DARK,
                     wraplength=440, justify="left").pack(padx=14, pady=(4, 0), anchor="w")

        def _confirm():
            chosen = sel_var.get()
            # store "" for the no-op "all" so the column shows a clean "—"
            self.gm.set_cpu_target(exe, "" if chosen == "all" else chosen)
            self._refresh_games()
            win.destroy()

        tk.Button(win, text="Zuweisen", command=_confirm,
                  font=FM, bg="#3b82f6", fg=WHT,
                  relief="flat", padx=12, pady=6, cursor="hand2").pack(pady=10)

    def _toggle_game(self):
        sel = self.game_tree.selection()
        if not sel: return
        exe = sel[0]
        for g in self.gm.get_games():
            if g.exe == exe:
                self.gm.update_game(exe, g.profile_name, not g.enabled)
                break
        self._refresh_games()

    def _remove_game(self):
        sel = self.game_tree.selection()
        if not sel: return
        if messagebox.askyesno("Entfernen", f"'{sel[0]}' aus der Liste entfernen?"):
            self.gm.remove_game(sel[0])
            self._refresh_games()

    def _on_game_start(self, game: GameEntry):
        self.after(0, lambda: (
            self.lbl_active_game.config(
                text=f"▶ {game.display_name} erkannt → Profil '{game.profile_name}' geladen",
                fg=GAME_COLOR),
            self._refresh_games(),
            self._update_monitor_status()
        ))

    def _on_game_stop(self, exe: str):
        self.after(0, lambda: (
            self.lbl_active_game.config(
                text=f"■ Spiel beendet ({exe}) → Standard-Profil wiederhergestellt",
                fg=DIM),
            self._refresh_games(),
            self._update_monitor_status()
        ))

    def _on_cpu_pin_result(self, game, ok, detail):
        """Called from the monitor thread — only store; the main-thread poller
        (_periodic_update) renders it. Never touch Tk from here."""
        try:
            self._pending_pin = (game.display_name, bool(ok), detail)
        except Exception:
            pass

    def _periodic_update(self):
        self._update_monitor_status()
        # Surface a pending CPU-pin result (set from the monitor thread)
        pending = self._pending_pin
        if pending:
            self._pending_pin = None
            name, ok, detail = pending
            if ok:
                self.lbl_active_game.config(
                    text=f"🧩 {name}: CPU-Pinning aktiv ({detail})", fg="#3b82f6")
            else:
                self.lbl_active_game.config(
                    text=f"⚠ {name}: {detail}", fg="#f59e0b")
        self.after(3000, self._periodic_update)

    # ── Tune History ──────────────────────────────────────────────────────────

    def _build_history(self, p):
        hdr = tk.Frame(p, bg=DARK)
        hdr.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(hdr, text="📋  Tune History",
                 font=("Segoe UI", 10, "bold"),
                 fg=HIST_COLOR, bg=DARK).pack(side="left")
        tk.Button(hdr, text="⟳ Aktualisieren",
                  command=self._refresh_history,
                  font=FM, bg=DARK3, fg=TXT,
                  relief="flat", padx=8, cursor="hand2"
                  ).pack(side="right")

        # History tree
        style = ttk.Style()
        style.configure("HT.Treeview",
            background=DARK2, foreground=TXT,
            fieldbackground=DARK2, rowheight=26, font=FM)
        style.configure("HT.Treeview.Heading",
            background=DARK3, foreground=HIST_COLOR,
            font=("Consolas", 8, "bold"), relief="flat")
        style.map("HT.Treeview",
            background=[("selected", "#7c3aed")],
            foreground=[("selected", WHT)])

        tree_f = tk.Frame(p, bg=DARK)
        tree_f.pack(fill="x", padx=14, pady=4)

        sb = ttk.Scrollbar(tree_f, orient="vertical")
        cols = ("date", "mode", "core", "power", "volt", "temp", "score", "result")
        self.hist_tree = ttk.Treeview(
            tree_f, columns=cols, show="headings",
            style="HT.Treeview", height=10, yscrollcommand=sb.set)
        sb.config(command=self.hist_tree.yview)

        for col, label, w in [
            ("date",   "Datum",       140),
            ("mode",   "Modus",        65),
            ("core",   "Core +MHz",    80),
            ("power",  "Power %",      70),
            ("volt",   "Avg Volt",     80),
            ("temp",   "Max Temp",     75),
            ("score",  "Score",        55),
            ("result", "Ergebnis",     80),
        ]:
            self.hist_tree.heading(col, text=label)
            self.hist_tree.column(col, width=w, anchor="center" if col != "date" else "w")

        self.hist_tree.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.hist_tree.tag_configure("pass", foreground=OK)
        self.hist_tree.tag_configure("fail", foreground=ERR)

        # Log viewer
        SecHdr(p, "Log Details").pack(fill="x", padx=14, pady=(8, 0))
        self.hist_log = LogBox(p)
        self.hist_log.pack(fill="both", expand=True, padx=14, pady=(2, 8))

        self.hist_tree.bind("<<TreeviewSelect>>", self._on_history_select)
        self._refresh_history()

    def _refresh_history(self):
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)
        runs = self.history.get_runs()
        if not runs:
            self.hist_tree.insert("", "end",
                values=("Keine Runs", "", "", "", "", "", "", ""),
                tags=("fail",))
            return
        for run in runs:
            tag = "pass" if run.passed else "fail"
            self.hist_tree.insert("", "end", iid=run.filename, values=(
                run.date,
                run.mode,
                f"+{run.core_offset}" if run.core_offset else "--",
                f"{run.power_pct}%" if run.power_pct < 100 else "--",
                f"{run.avg_volt_mv}mV" if run.avg_volt_mv else "--",
                f"{run.max_temp:.0f}°C" if run.max_temp else "--",
                f"{run.score}/100" if run.score else "--",
                "✓ OK" if run.passed else "✗",
            ), tags=(tag,))

    def _on_history_select(self, _):
        sel = self.hist_tree.selection()
        if not sel: return
        runs = {r.filename: r for r in self.history.get_runs()}
        run = runs.get(sel[0])
        if run:
            self.hist_log.clear()
            for line in run.log_lines[-50:]:  # last 50 lines
                lvl = "success" if "✓" in line or "OK" in line else \
                      "error"   if "✗" in line or "FAIL" in line else "info"
                self.hist_log.append(line, lvl)
