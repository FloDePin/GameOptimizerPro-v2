"""
GameOptimizerPro v2.0 — Startup Manager page
Lists every autostart entry (Run keys + Startup folders) and enables/disables
it like Task Manager does. For each entry:
  - on/off state (the real Windows state, not guessed)
  - name, publisher, path, source
  - status: Safe / Caution / Critical / Unknown
  - recommendation: whether it can be disabled
"""

import subprocess
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import startup_control
from ui.components import Page, Table, button, run_async
from ui.theme import (ACC, AMBER, APP_BG, CARD_BG2, DIM, ERR, F_S, F_XS, GREEN, MUTED, TEXT,
                      TEXT2, ctk_font, icon_image, mix, tr)

OK, WRN, TXT = GREEN, AMBER, TEXT


# ── Known process database ────────────────────────────────────────────────────
# status: "safe" | "caution" | "critical" | "system"
# can_disable: True = problemlos deaktivierbar

KNOWN_PROCESSES = {
    # ── System / Windows ──────────────────────────────────────────────────────
    "SecurityHealthSystray":    ("system",  False, "Windows Security",         "Windows Defender Tray — nicht deaktivieren"),
    "SecurityHealthService":    ("system",  False, "Windows Security",         "Windows Defender Service — kritisch"),
    "WindowsDefender":          ("system",  False, "Microsoft",                "Windows Defender — Systemschutz"),
    "OneDrive":                 ("safe",    True,  "Microsoft",                "Cloud-Sync. Deaktivierbar wenn nicht genutzt"),
    "Teams":                    ("safe",    True,  "Microsoft",                "Microsoft Teams — startet mit Windows. Sicher zu deaktivieren"),
    "MicrosoftTeams":           ("safe",    True,  "Microsoft",                "Microsoft Teams — sicher deaktivierbar"),
    "Slack":                    ("safe",    True,  "Slack Technologies",       "Slack — sicher deaktivierbar wenn nicht täglich genutzt"),
    "Discord":                  ("safe",    True,  "Discord Inc.",             "Discord — sicher deaktivierbar. Manuell starten"),
    "Spotify":                  ("safe",    True,  "Spotify AB",               "Spotify — sicher deaktivierbar"),
    "Steam":                    ("safe",    True,  "Valve Corporation",        "Steam — sicher. Manuell starten beim Gaming"),
    "EpicGamesLauncher":        ("safe",    True,  "Epic Games",               "Epic Launcher — sicher deaktivierbar"),
    "EABackgroundService":      ("caution", True,  "Electronic Arts",          "EA App Hintergrunddienst — deaktivierbar aber EA-Spiele brauchen ihn"),
    "RiotClientServices":       ("safe",    True,  "Riot Games",               "Riot Client — deaktivierbar, startet bei Bedarf"),
    "BattleNet":                ("safe",    True,  "Blizzard Entertainment",   "Battle.net Launcher — sicher deaktivierbar"),
    "upc":                      ("safe",    True,  "Ubisoft",                  "Ubisoft Connect — sicher deaktivierbar"),
    "GalaxyClient":             ("safe",    True,  "CD Projekt",               "GOG Galaxy — sicher deaktivierbar"),
    # ── NVIDIA ────────────────────────────────────────────────────────────────
    "NVDisplay.Container":      ("caution", False, "NVIDIA Corporation",       "NVIDIA Display Container — für OSD/Overlay nötig"),
    "nvcontainer":              ("caution", False, "NVIDIA Corporation",       "NVIDIA Container — Treiber-Komponente"),
    "NvBackend":                ("safe",    True,  "NVIDIA Corporation",       "NVIDIA GeForce Experience Backend — deaktivierbar wenn GFE nicht genutzt"),
    "NvTelemetryContainer":     ("safe",    True,  "NVIDIA Corporation",       "NVIDIA Telemetrie — sicher zu deaktivieren"),
    "NVIDIAGeForceExperience":  ("safe",    True,  "NVIDIA Corporation",       "GeForce Experience — sicher wenn manuell gestartet"),
    # ── AMD ───────────────────────────────────────────────────────────────────
    "RadeonSoftware":           ("safe",    True,  "AMD",                      "AMD Radeon Software — sicher deaktivierbar"),
    "AMDRSServ":                ("caution", False, "AMD",                      "AMD Radeon Service — für Treiberfunktionen nötig"),
    # ── Audio ─────────────────────────────────────────────────────────────────
    "RtkAudUService64":         ("caution", False, "Realtek",                  "Realtek Audio Manager — für Audio-Einstellungen nötig"),
    "RTHDVCPL":                 ("caution", False, "Realtek",                  "Realtek HD Audio — nötig für Audio-Konfiguration"),
    "nahimic":                  ("safe",    True,  "Nahimic / A-Volute",       "Nahimic Audio — deaktivierbar wenn nicht genutzt"),
    "SteelSeriesEngine":        ("safe",    True,  "SteelSeries",              "SteelSeries GG / Engine — deaktivierbar"),
    # ── Peripherals / RGB ─────────────────────────────────────────────────────
    "iCUE":                     ("safe",    True,  "Corsair",                  "Corsair iCUE — deaktivierbar wenn RGB nicht wichtig"),
    "CORSAIR":                  ("safe",    True,  "Corsair",                  "Corsair Software — sicher deaktivierbar"),
    "LGHUBUpdater":             ("safe",    True,  "Logitech",                 "Logitech G Hub — sicher deaktivierbar"),
    "LGHUB":                    ("safe",    True,  "Logitech",                 "Logitech G Hub — deaktivierbar"),
    "RazerCentral":             ("safe",    True,  "Razer Inc.",               "Razer Central — deaktivierbar wenn keine Razer-Geräte im Einsatz"),
    "RazerSynapse":             ("safe",    True,  "Razer Inc.",               "Razer Synapse — deaktivierbar, Makros/DPI-Profile gehen verloren"),
    "SteelSeriesGG":            ("safe",    True,  "SteelSeries",              "SteelSeries GG — sicher deaktivierbar"),
    "ASUS":                     ("safe",    True,  "ASUS",                     "ASUS Software — meist sicher deaktivierbar"),
    "ArmouryCrate":             ("safe",    True,  "ASUS",                     "ASUS Armoury Crate — sicher deaktivierbar"),
    # ── System Tools ──────────────────────────────────────────────────────────
    "ctfmon":                   ("system",  False, "Microsoft",                "Text Input / Spracherkennung — Systemkomponente"),
    "sihost":                   ("system",  False, "Microsoft",                "Shell Infrastructure Host — kritische Systemkomponente"),
    "taskhostw":                ("system",  False, "Microsoft",                "Task Host — Windows-Systemdienst"),
    "MSIAfterburner":           ("safe",    True,  "MSI / RivaTuner",          "MSI Afterburner — sicher deaktivierbar, OC-Profile müssen dann manuell geladen werden"),
    "RTSS":                     ("safe",    True,  "RivaTuner",                "RivaTuner Statistics Server — für FPS-Counter nötig"),
    "HWiNFO64":                 ("safe",    True,  "REALiX",                   "HWiNFO — sicher deaktivierbar"),
    "MSICenter":                ("safe",    True,  "MSI",                      "MSI Center — sicher deaktivierbar"),
    "GigabyteControlCenter":    ("safe",    True,  "Gigabyte",                 "Gigabyte Control Center — sicher deaktivierbar"),
    "EasyTune":                 ("safe",    True,  "Gigabyte",                 "Gigabyte EasyTune — sicher deaktivierbar"),
    # ── Security / Antivirus ──────────────────────────────────────────────────
    "MsMpEng":                  ("system",  False, "Microsoft",                "Windows Defender Antivirus — nicht deaktivieren"),
    "avgnt":                    ("caution", True,  "Avira",                    "Avira Antivirus — nur wenn anderer AV vorhanden"),
    "avastui":                  ("caution", True,  "Avast",                    "Avast Antivirus — nur wenn anderer AV vorhanden"),
    "mcshield":                 ("caution", True,  "McAfee",                   "McAfee — deaktivierbar wenn Windows Defender genutzt wird"),
}


STATUS_CONFIG = {
    "safe":     (OK,  "✓ Safe",     "Problemlos deaktivierbar"),
    "caution":  (WRN, "⚠ Caution",  "Deaktivierbar aber mit Einschränkungen"),
    "critical": (ERR, "✗ Critical", "NICHT deaktivieren — Systemfunktion"),
    "system":   (ERR, "⚙ System",   "Windows-Systemkomponente — nicht deaktivieren"),
    "unknown":  (DIM, "? Unknown",  "Unbekannt — recherchieren vor Deaktivierung"),
}

FILTERS = [("all", "Alle", "All"), ("safe", "Safe", "Safe"), ("caution", "Caution", "Caution"),
           ("system", "System", "System"), ("unknown", "Unbekannt", "Unknown"),
           ("disabled", "Deaktiviert", "Disabled")]


class StartupManagerPage(Page):
    def __init__(self, parent, **kw):
        super().__init__(parent, tr("Autostart", "Startup apps"),
                         tr("Run-Schlüssel und Autostart-Ordner — an/aus wie im Task-Manager, es wird "
                            "nichts gelöscht",
                            "Run keys and Startup folders — on/off like in Task Manager, nothing is "
                            "deleted"),
                         color=ACC, scroll=False, **kw)
        self._entries: list[dict] = []
        self._filtered: list[dict] = []
        self._filter_var = tk.StringVar(value="all")
        self._sort_col = "name"
        self._sort_rev = False
        self._build()
        self.after(200, self._load_entries)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        button(self.actions, tr("Aktualisieren", "Refresh"), self._load_entries, kind="ghost",
               height=30, image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right")
        b = self.body

        filt = tk.Frame(b, bg=APP_BG)
        filt.pack(fill="x", pady=(0, 8))
        self._filter_keys = {tr(de, en): key for key, de, en in FILTERS}
        self.seg_filter = ctk.CTkSegmentedButton(
            filt, values=list(self._filter_keys), height=30, font=ctk_font(12),
            selected_color=mix(CARD_BG2, ACC, 0.45), selected_hover_color=mix(CARD_BG2, ACC, 0.6),
            command=lambda v: (self._filter_var.set(self._filter_keys[v]), self._apply_filter()))
        self.seg_filter.set(tr("Alle", "All"))
        self.seg_filter.pack(side="left")
        self.ent_search = ctk.CTkEntry(filt, width=200, height=30,
                                       placeholder_text=tr("Suchen …", "Search …"))
        self.ent_search.pack(side="right")
        self.ent_search.bind("<KeyRelease>", lambda e: self._apply_filter())

        self.lbl_count = tk.Label(b, text="", font=F_XS, fg=DIM, bg=APP_BG, anchor="w")
        self.lbl_count.pack(fill="x", pady=(0, 6))

        act = tk.Frame(b, bg=APP_BG)
        act.pack(side="bottom", fill="x", pady=(10, 0))
        button(act, "Details", self._show_details, kind="ghost", height=32,
               image=icon_image("info", TEXT2, 14), compound="left").pack(side="right", padx=(6, 0))
        button(act, "Task-Manager", self._open_task_manager, kind="ghost", height=32
               ).pack(side="right", padx=(6, 0))
        button(act, tr("Aktivieren", "Enable"), lambda: self._toggle(True), height=32,
               image=icon_image("check", GREEN, 14), compound="left").pack(side="right", padx=(6, 0))
        button(act, tr("Deaktivieren", "Disable"), lambda: self._toggle(False), kind="primary",
               color=AMBER, height=32).pack(side="right")
        self.lbl_selected = tk.Label(act, text=tr("Kein Eintrag ausgewählt", "Nothing selected"),
                                     font=F_S, fg=DIM, bg=APP_BG, anchor="w")
        self.lbl_selected.pack(side="left", fill="x", expand=True)

        tbl = Table(b, [
            ("state",          tr("An/Aus", "On/Off"),       80, "center"),
            ("status",         "Status",                     95, "center"),
            ("name",           "Name",                      170, "w"),
            ("publisher",      "Publisher",                 140, "w"),
            ("recommendation", tr("Empfehlung", "Advice"),  260, "w"),
            ("path",           tr("Pfad", "Path"),          240, "w"),
        ], height=14)
        tbl.pack(fill="both", expand=True)
        self.tree = tbl.tree
        for col in ("state", "status", "name", "publisher", "recommendation", "path"):
            self.tree.heading(col, command=lambda c=col: self._sort_by(c))
        self.tree.tag_configure("safe",    foreground=OK)
        self.tree.tag_configure("caution", foreground=WRN)
        self.tree.tag_configure("system",  foreground=ERR)
        self.tree.tag_configure("critical", foreground=ERR)
        self.tree.tag_configure("unknown", foreground=DIM)
        self.tree.tag_configure("disabled", foreground=MUTED)   # deaktiviert = grau
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_entries(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._entries = []
        self.lbl_count.config(text="Lade …")
        run_async(self, self._fetch_entries, lambda _r: self._apply_filter())

    def _fetch_entries(self):
        """Read autostart entries (Run keys + Autostart folders) with their REAL
        enabled/disabled state — the same StartupApproved flags Task Manager
        uses. (The old PowerShell reader only saw the three Run keys and showed
        entries disabled in Task Manager as if they were active.)"""
        entries = []
        try:
            for se in startup_control.list_entries():
                info = self._lookup(se.name, se.command)
                entries.append({
                    "name":           se.name,
                    "command":        se.command,
                    "source":         se.source,
                    "enabled":        se.enabled,
                    "entry":          se,
                    "status":         info[0],
                    "can_disable":    info[1],
                    "publisher":      info[2],
                    "recommendation": info[3],
                })
        except Exception as e:
            entries.append({
                "name": f"Fehler: {e}", "command": "", "source": "", "enabled": True,
                "entry": None, "status": "unknown", "can_disable": False,
                "publisher": "", "recommendation": "Autostart-Einträge konnten nicht gelesen werden"
            })

        self._entries = entries

    def _lookup(self, name: str, command: str) -> tuple:
        """Match name/command against known process database."""
        name_upper = name.upper()
        cmd_upper  = command.upper()

        for key, info in KNOWN_PROCESSES.items():
            if key.upper() in name_upper or key.upper() in cmd_upper:
                status, can_dis, publisher, rec = info
                return status, can_dis, publisher, rec

        # Heuristics for unknowns
        if any(s in cmd_upper for s in ["WINDOWS\\SYSTEM32", "WINDOWS\\SYSWOW64"]):
            return "system", False, "Microsoft / System", "Systemdatei — nicht deaktivieren ohne zu recherchieren"
        if "UPDATE" in name_upper or "UPDATER" in name_upper:
            return "safe", True, "Unbekannt", "Updater-Prozess — sicher deaktivierbar, Updates dann manuell"
        if any(s in name_upper for s in ["TRAY", "HELPER", "AGENT", "LAUNCHER"]):
            return "safe", True, "Unbekannt", "Hintergrundprozess — meist sicher deaktivierbar"

        return "unknown", None, "Unbekannt", "Unbekannt — vor Deaktivierung recherchieren"

    # ── Filter & display ──────────────────────────────────────────────────────

    def _apply_filter(self, *_):
        if not self.winfo_exists():
            return
        filt   = self._filter_var.get()
        search = self.ent_search.get().strip().lower()

        def _match_filter(e):
            if filt == "all":
                return True
            if filt == "disabled":
                return not e.get("enabled", True)
            return e["status"] == filt

        self._filtered = [
            e for e in self._entries
            if _match_filter(e)
            and (not search or search in e["name"].lower()
                 or search in e.get("publisher", "").lower()
                 or search in e["command"].lower())
        ]

        for row in self.tree.get_children():
            self.tree.delete(row)

        # iid = index into self._filtered, so a (multi-)selection maps back to
        # its entries reliably.
        for i, e in enumerate(self._filtered):
            _col, label, _desc = STATUS_CONFIG.get(e["status"], (DIM, "?", "?"))
            cmd = e["command"]
            if len(cmd) > 55:
                cmd = "..." + cmd[-52:]
            enabled = e.get("enabled", True)
            self.tree.insert("", "end", iid=str(i),
                values=(
                    "✓ An" if enabled else "⊘ Aus",
                    label,
                    e["name"],
                    e.get("publisher", ""),
                    e["recommendation"],
                    cmd,
                ),
                tags=(e["status"] if enabled else "disabled",)
            )

        total = len(self._entries)
        shown = len(self._filtered)
        n_off = sum(1 for e in self._entries if not e.get("enabled", True))
        self.lbl_count.config(
            text=f"{shown} von {total} Einträgen  ·  "
                 f"{sum(1 for e in self._entries if e['status']=='safe')} Safe  ·  "
                 f"{sum(1 for e in self._entries if e['status']=='caution')} Caution  ·  "
                 f"{sum(1 for e in self._entries if e['status'] in ('system','critical'))} System  ·  "
                 f"{n_off} deaktiviert"
        )

    # Tree column -> entry key. "path" used to sort on a key that doesn't exist
    # (entries store the command under "command"), so that header did nothing.
    _SORT_KEYS = {"path": "command", "state": "enabled"}

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        key = self._SORT_KEYS.get(col, col)
        self._entries.sort(key=lambda e: str(e.get(key, "")).lower(),
                           reverse=self._sort_rev)
        self._apply_filter()

    def _selected_entries(self) -> list:
        out = []
        for iid in self.tree.selection():
            try:
                e = self._filtered[int(iid)]
            except (ValueError, IndexError):
                continue
            out.append(e)
        return out

    def _on_select(self, _):
        sel = self._selected_entries()
        if not sel:
            return
        if len(sel) > 1:
            self.lbl_selected.config(text=f"{len(sel)} Einträge ausgewählt", fg=TXT)
            return
        e = sel[0]
        status_cfg = STATUS_CONFIG.get(e["status"], (DIM, "?", "?"))
        state = "an" if e.get("enabled", True) else "AUS"
        self.lbl_selected.config(
            text=f"{e['name']}  ·  {state}  ·  {status_cfg[1]}  ·  {e.get('publisher','?')}",
            fg=status_cfg[0]
        )

    def _show_details(self):
        sel = self._selected_entries()
        if not sel:
            messagebox.showinfo("Details", "Keinen Eintrag ausgewählt.", parent=self)
            return
        e = sel[0]
        status_cfg = STATUS_CONFIG.get(e["status"], (DIM, "?", "Unbekannt"))

        detail = (
            f"Name:          {e['name']}\n"
            f"Zustand:       {'✓ aktiviert' if e.get('enabled', True) else '⊘ deaktiviert'}\n"
            f"Publisher:     {e.get('publisher', 'Unbekannt')}\n"
            f"Status:        {status_cfg[1]}\n"
            f"Deaktivierbar: {'✓ Ja' if e['can_disable'] else ('✗ Nein' if e['can_disable'] is False else '? Unbekannt')}\n"
            f"Quelle:        {e.get('source', '?')}\n\n"
            f"Empfehlung:\n  {e['recommendation']}\n\n"
            f"Pfad:\n  {e['command']}"
        )
        messagebox.showinfo(f"Details: {e['name']}", detail, parent=self)

    def _toggle(self, enable: bool):
        """Enable/disable the selected entries — flag only, exactly like Task
        Manager. Nothing is deleted, so every change can be undone here or there."""
        sel = [e for e in self._selected_entries() if e.get("entry") is not None]
        if not sel:
            messagebox.showinfo("Autostart", "Keinen Eintrag ausgewählt.", parent=self)
            return
        todo = [e for e in sel if e.get("enabled", True) != enable]
        if not todo:
            messagebox.showinfo(
                "Autostart",
                f"Bereits {'aktiviert' if enable else 'deaktiviert'}.", parent=self)
            return

        if not enable:
            names = "\n".join(f"  • {e['name']}" for e in todo[:12])
            if len(todo) > 12:
                names += f"\n  … und {len(todo) - 12} weitere"
            msg = (f"{len(todo)} Autostart-Eintrag/Einträge deaktivieren?\n\n{names}\n\n"
                   "Es wird nichts gelöscht — wie im Task-Manager lässt sich das "
                   "jederzeit wieder aktivieren.")
            risky = [e for e in todo
                     if e["status"] in ("system", "critical") or e["can_disable"] is False]
            if risky:
                msg += ("\n\n⚠ ACHTUNG: " + ", ".join(e["name"] for e in risky) +
                        " ist als System-/nicht empfohlen markiert. Deaktivieren kann "
                        "Funktionen beeinträchtigen (z.B. Windows-Sicherheit, Audio-, "
                        "Treiber- oder Geräte-Software).")
            if not messagebox.askyesno("Autostart deaktivieren", msg,
                                       icon="warning" if risky else "question",
                                       parent=self):
                return

        results = []
        for e in todo:
            ok, m = startup_control.set_enabled(e["entry"], enable)
            e["enabled"] = e["entry"].enabled        # re-read state, not assumed
            results.append((e["name"], ok, m))
        self._apply_filter()

        bad = [r for r in results if not r[1]]
        done = len(results) - len(bad)
        self.lbl_selected.config(
            text=f"{done} Eintrag/Einträge {'aktiviert' if enable else 'deaktiviert'}"
                 + (f", {len(bad)} fehlgeschlagen" if bad else ""),
            fg=OK if not bad else WRN)
        if bad:
            messagebox.showwarning(
                "Autostart",
                "Nicht alle Änderungen waren möglich:\n\n" +
                "\n".join(f"  • {n}: {m}" for n, _, m in bad), parent=self)

    def _open_task_manager(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1
            subprocess.Popen(
                ["taskmgr.exe"],
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
