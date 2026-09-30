"""
GameOptimizerPro v2.0 — Games page: per-game profiles (GPU profile and CPU
cores while a game runs) and the Auto-Tune history.
"""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core.game_monitor import GameEntry, GameMonitor
from core.nvtune_core  import ProfileManager
from core.tune_history import TuneHistory
from ui.components import ChoiceDialog, LogView, Page, Table, WrapLabel, button
from ui.theme import (AMBER, APP_BG, BLUE, BORDER, CARD_BG, CARD_BG2, DIM, ERR, F_MONO, F_S,
                      F_XS, GREEN, MUTED, TEXT2, VIOLET, ctk_font, icon_image, mix, on_color, tr)

GAME_COLOR = GREEN
HIST_COLOR = VIOLET


class GamesTab(Page):
    def __init__(self, parent, game_monitor: GameMonitor,
                 pm: ProfileManager, logs_dir: str, **kw):
        super().__init__(parent, tr("Spiele & Verlauf", "Games & history"),
                         tr("Pro Spiel automatisch ein GPU-Profil und/oder CPU-Kerne — und der Verlauf "
                            "aller Auto-Tune-Läufe",
                            "A GPU profile and/or CPU cores per game, applied automatically — and the "
                            "history of all Auto-Tune runs"),
                         color=GREEN, scroll=False, **kw)
        self.gm      = game_monitor
        self.pm      = pm
        self.history = TuneHistory(logs_dir)
        self._build()

    def _build(self):
        bar = tk.Frame(self.body, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 10))
        self._view_keys = {tr("Spiele-Profile", "Per-game profiles"): "games",
                           tr("Tune-Verlauf", "Tune history"): "history"}
        self.seg = ctk.CTkSegmentedButton(bar, values=list(self._view_keys), height=32,
                                          font=ctk_font(12), selected_color=mix(CARD_BG2, GREEN, 0.55),
                                          selected_hover_color=mix(CARD_BG2, GREEN, 0.7),
                                          command=lambda v: self._show_view(self._view_keys[v]))
        self.seg.pack(side="left")
        self.lbl_monitor_status = tk.Label(bar, text="", font=F_S, fg=DIM, bg=APP_BG)
        self.lbl_monitor_status.pack(side="right")
        holder = tk.Frame(self.body, bg=APP_BG)
        holder.pack(fill="both", expand=True)
        self._views = {"games": tk.Frame(holder, bg=APP_BG), "history": tk.Frame(holder, bg=APP_BG)}
        self._build_games(self._views["games"])
        self._build_history(self._views["history"])
        self._show_view("games")

    def _show_view(self, key):
        for k, f in self._views.items():
            if k != key:
                f.pack_forget()
        self._views[key].pack(fill="both", expand=True)
        self.seg.set(next(lbl for lbl, k in self._view_keys.items() if k == key))

    # ── Per-Game Profiles ─────────────────────────────────────────────────────

    def _build_games(self, p):
        card = ctk.CTkFrame(p, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        WrapLabel(inner, text=tr("Weist jedem Spiel automatisch ein GPU-Profil und/oder CPU-Kerne zu. "
                                 "GameOptimizerPro überwacht im Hintergrund, welche Prozesse laufen.",
                                 "Assigns a GPU profile and/or CPU cores to each game automatically. "
                                 "GameOptimizerPro watches the running processes in the background."),
                  font=F_S, fg=TEXT2, bg=CARD_BG).pack(fill="x")

        # CPU topology note (honest guidance — e.g. single-CCD = pinning useless)
        topo = self.gm.topology
        if topo is not None and topo.note:
            icon = "🧩" if (topo.ok and len(self.gm.cpu_pin_targets()) > 1) else "ℹ"
            WrapLabel(inner, text=f"{icon}  {topo.note}", font=F_XS, fg=DIM,
                      bg=CARD_BG).pack(fill="x", pady=(4, 0))

        act = tk.Frame(inner, bg=CARD_BG)
        act.pack(fill="x", pady=(12, 10))
        button(act, tr("Spiel hinzufügen", "Add game"), self._add_game, kind="primary", color=GAME_COLOR,
               image=icon_image("add", on_color(GAME_COLOR), 14), compound="left", height=30
               ).pack(side="left", padx=(0, 6))
        button(act, tr("Profil zuweisen", "Assign profile"), self._assign_profile, height=30
               ).pack(side="left", padx=(0, 6))
        button(act, tr("CPU-Kerne zuweisen", "Assign CPU cores"), self._assign_cpu, height=30
               ).pack(side="left", padx=(0, 6))
        button(act, tr("An/Aus", "On/Off"), self._toggle_game, height=30).pack(side="left", padx=(0, 6))
        button(act, tr("Entfernen", "Remove"), self._remove_game, kind="ghost", height=30,
               image=icon_image("delete", ERR, 14), compound="left").pack(side="left")

        tbl = Table(inner, [
            ("status",  "Status",                               70, "center"),
            ("game",    tr("Spiel", "Game"),                   160, "w"),
            ("exe",     tr("Prozess (.exe)", "Process (.exe)"), 180, "w"),
            ("profile", tr("Profil bei Start", "Profile at start"), 150, "w"),
            ("restore", tr("Profil danach", "Profile after"),  130, "w"),
            ("cpu",     tr("CPU-Kerne", "CPU cores"),          150, "w"),
        ], height=12, selectmode="browse")
        tbl.pack(fill="both", expand=True)
        self.game_tree = tbl.tree
        self.game_tree.tag_configure("active",   foreground=GAME_COLOR)
        self.game_tree.tag_configure("disabled", foreground=MUTED)
        self.game_tree.tag_configure("no_profile", foreground=AMBER)

        self.lbl_active_game = tk.Label(inner, text=tr("Kein Spiel erkannt", "No game detected"),
                                        font=F_MONO, fg=DIM, bg=CARD_BG, anchor="w")
        self.lbl_active_game.pack(fill="x", pady=(10, 0))

        # Wire game monitor callbacks
        self._pending_pin = None  # (name, ok, detail) set from monitor thread
        self.gm.on_game_start(self._on_game_start)
        self.gm.on_game_stop(self._on_game_stop)
        self.gm.on_cpu_pin(self._on_cpu_pin_result)

        self._update_monitor_status()
        self._refresh_games()
        self._periodic_id = self.after(3000, self._periodic_update)

    def destroy(self):
        try:
            if getattr(self, "_periodic_id", None):
                self.after_cancel(self._periodic_id)
        except Exception:
            pass
        self._periodic_id = None
        super().destroy()

    def _update_monitor_status(self):
        if self.gm.is_running:
            active = self.gm.active_game
            if active:
                self.lbl_monitor_status.config(
                    text=f"● {tr('Überwachung aktiv', 'Watching')}  ·  {tr('Spiel', 'Game')}: {active}",
                    fg=GAME_COLOR)
            else:
                self.lbl_monitor_status.config(
                    text=f"● {tr('Überwachung aktiv', 'Watching')}  ·  "
                         f"{tr('kein Spiel erkannt', 'no game detected')}", fg=DIM)
        else:
            self.lbl_monitor_status.config(text=tr("○ Überwachung inaktiv", "○ Not watching"), fg=MUTED)

    def _refresh_games(self):
        for row in self.game_tree.get_children():
            self.game_tree.delete(row)

        active = (self.gm.active_game or "").lower()
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
            self.game_tree.insert("", "end", iid=game.exe, values=(
                status, game.display_name, game.exe,
                game.profile_name or "(nicht gesetzt)",
                game.restore_profile.replace("__tray_default__", "← Standard"),
                cpu_disp,
            ), tags=(tag,))

    def _selected_exe(self):
        sel = self.game_tree.selection()
        if not sel:
            messagebox.showwarning("", "Kein Spiel ausgewählt.")
            return None
        return sel[0]

    def _add_game(self):
        exe = ctk.CTkInputDialog(title=tr("Spiel hinzufügen", "Add game"),
                                 text=tr("Prozessname der .exe-Datei (z. B. Cyberpunk2077.exe):",
                                         "Process name of the .exe (e.g. Cyberpunk2077.exe):")).get_input()
        if not exe or not exe.strip():
            return
        exe = exe.strip()
        if not exe.lower().endswith(".exe"):
            exe += ".exe"
        name = ctk.CTkInputDialog(title=tr("Anzeigename", "Display name"),
                                  text=tr(f"Anzeigename für '{exe}' (leer = Dateiname):",
                                          f"Display name for '{exe}' (empty = file name):")).get_input()
        name = (name or "").strip() or exe[:-4]
        self.gm.add_game(exe, name, "")
        self._refresh_games()

    def _assign_profile(self):
        exe = self._selected_exe()
        if not exe:
            return
        profiles = [p.name for p in self.pm.list_all() if not p.name.startswith("__")]
        if not profiles:
            messagebox.showinfo("",
                "Noch keine GPU-Profile vorhanden.\n"
                "Führe zuerst einen Auto-Tune durch.")
            return
        cur = next((g.profile_name for g in self.gm.get_games() if g.exe == exe), None)
        chosen = ChoiceDialog(self, tr("Profil zuweisen", "Assign profile"),
                              tr(f"GPU-Profil für {exe}", f"GPU profile for {exe}"),
                              [(p, p) for p in profiles], current=cur,
                              ok_text=tr("Zuweisen", "Assign"), accent=GAME_COLOR).show()
        if chosen:
            self.gm.update_game(exe, chosen)
            self._refresh_games()

    def _assign_cpu(self):
        exe = self._selected_exe()
        if not exe:
            return
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
        cur = next((g.cpu_target or "all" for g in self.gm.get_games() if g.exe == exe), "all")
        notes = []
        if topo and topo.note:
            notes.append((topo.note, DIM))
        notes.append(("ℹ CPU Sets sind ein weicher Hinweis: Das Spiel läuft bevorzugt auf den gewählten "
                      "Kernen, kann bei Bedarf aber ausweichen — es kann also nie ausgebremst werden.", DIM))
        # Anti-cheat caveat (always) — we modify a foreign game process
        notes.append(("⚠ Anti-Cheat: Das Pinnen greift von außen in den Spielprozess ein. "
                      "Kernel-Anti-Cheats (EAC, BattlEye, Vanguard) könnten das theoretisch als "
                      "Manipulation werten — mit Anti-Cheat-Spielen auf eigenes Risiko nutzen.", "#d08770"))
        # CCD-parking conflict — only relevant on multi-CCD machines
        if topo and len(topo.ccds) > 1:
            notes.append(("⚠ CCD-Parking: Ist AMDs 3D-V-Cache-Optimizer bzw. das Game-Bar-CCD-Parking "
                          "aktiv, kann es unser Pinning überschreiben oder geparkte Kerne stillschweigend "
                          "ignorieren. Für zuverlässiges Pinning diese in Windows/BIOS deaktivieren.",
                          "#d08770"))
        chosen = ChoiceDialog(self, tr("CPU-Kerne zuweisen", "Assign CPU cores"),
                              tr(f"CPU-Kerne für {exe}", f"CPU cores for {exe}"),
                              [(t.key, t.label) for t in targets], current=cur, notes=notes,
                              ok_text=tr("Zuweisen", "Assign"), accent=BLUE).show()
        if chosen:
            # store "" for the no-op "all" so the column shows a clean "—"
            self.gm.set_cpu_target(exe, "" if chosen == "all" else chosen)
            self._refresh_games()

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
                    text=f"🧩 {name}: CPU-Pinning aktiv ({detail})", fg=BLUE)
            else:
                self.lbl_active_game.config(
                    text=f"⚠ {name}: {detail}", fg=AMBER)
        self._periodic_id = self.after(3000, self._periodic_update)

    # ── Tune History ──────────────────────────────────────────────────────────

    def _build_history(self, p):
        card = ctk.CTkFrame(p, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        head = tk.Frame(inner, bg=CARD_BG)
        head.pack(fill="x", pady=(0, 10))
        button(head, tr("Aktualisieren", "Refresh"), self._refresh_history, kind="ghost", height=28,
               image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right")
        WrapLabel(head, text=tr("Alle Auto-Tune-Läufe — Zeile auswählen, um das Protokoll zu sehen.",
                                "All Auto-Tune runs — select a row to see its log."),
                  font=F_S, fg=TEXT2, bg=CARD_BG).pack(side="left", fill="x", expand=True)

        tbl = Table(inner, [
            ("date",   tr("Datum", "Date"),        150, "w"),
            ("mode",   tr("Modus", "Mode"),         80, "center"),
            ("core",   "Core +MHz",                 85, "center"),
            ("power",  "Power %",                   75, "center"),
            ("volt",   "Avg Volt",                  85, "center"),
            ("temp",   "Max Temp",                  80, "center"),
            ("score",  "Score",                     65, "center"),
            ("result", tr("Ergebnis", "Result"),    80, "center"),
        ], height=9, selectmode="browse")
        tbl.pack(fill="x")
        self.hist_tree = tbl.tree
        self.hist_tree.tag_configure("pass", foreground=GREEN)
        self.hist_tree.tag_configure("fail", foreground=ERR)

        tk.Label(inner, text=tr("PROTOKOLL", "LOG"), font=("Segoe UI Semibold", 8), fg=MUTED,
                 bg=CARD_BG).pack(anchor="w", pady=(12, 4))
        self.hist_log = LogView(inner, height=8)
        self.hist_log.pack(fill="both", expand=True)

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
