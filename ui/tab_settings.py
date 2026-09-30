"""
GameOptimizerPro Settings page
- Start with Windows, startup GPU profile
- Afterburner setup checker
- Restore point, registry backup
- System cleaner + Deep Clean
- About
"""

import os
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import registry_backup, restore_point, system_cleaner
from ui.components import (Card, CheckBox, Page, ResponsiveGrid, WrapLabel, button, run_async)
from ui.theme import (ACC, AMBER, CARD_BG, CARD_BG2, DIM, ERR, F_BB, F_MONO, F_S, F_XS, GREEN,
                      SLATE, TEXT, TEXT2, VIOLET, ctk_font, icon_image, on_color, tr)


class SettingsTab(Page):
    def __init__(self, parent, ab, monitor, startup_loader, **kw):
        super().__init__(parent, tr("Einstellungen", "Settings"),
                         tr("Start, Afterburner-Einrichtung, Sicherungen und Aufräumen",
                            "Start-up, Afterburner setup, backups and clean-up"),
                         color=SLATE, **kw)
        self.ab             = ab
        self.monitor        = monitor
        self.startup_loader = startup_loader
        self._canvas = self.body._parent_canvas        # the scrolling canvas of the page
        self._build()

    def _build(self):
        from core import app_settings
        b = self.body
        pad = dict(fill="x", padx=10, pady=(0, 14))

        # ── Start ─────────────────────────────────────────────────────────────
        st = Card(b, tr("Start", "Start-up"), accent=SLATE)
        st.pack(**pad)
        self.v_autostart = tk.BooleanVar(value=False)
        self.sw_autostart = ctk.CTkSwitch(
            st.body, text=tr("Mit Windows starten (geplante Aufgabe — ohne UAC-Abfrage beim Booten)",
                             "Start with Windows (scheduled task — no UAC prompt at boot)"),
            variable=self.v_autostart, command=self._toggle_autostart, font=ctk_font(13),
            progress_color=ACC, state="disabled")
        self.sw_autostart.pack(anchor="w", pady=4)
        if self.startup_loader:
            run_async(self, self.startup_loader.is_autostart_enabled, self._show_autostart)

        self.v_load_startup = tk.BooleanVar(value=bool(app_settings.get("load_startup_profile", True)))
        self.sw_load_startup = ctk.CTkSwitch(
            st.body, text=tr("Tray-Standard-GPU-Profil beim Start automatisch laden",
                             "Load the tray-default GPU profile at start-up"),
            variable=self.v_load_startup, font=ctk_font(13), progress_color=ACC,
            command=lambda: app_settings.set("load_startup_profile", bool(self.v_load_startup.get())))
        self.sw_load_startup.pack(anchor="w", pady=4)
        row = tk.Frame(st.body, bg=CARD_BG)
        row.pack(fill="x", pady=(8, 0))
        button(row, tr("Startup-Profil jetzt laden", "Load startup profile now"), self._load_startup_now,
               height=30, image=icon_image("refresh", TEXT, 14), compound="left").pack(side="left")
        self.lbl_startup_result = WrapLabel(st.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_startup_result.pack(fill="x", pady=(6, 0))

        # ── Afterburner setup ─────────────────────────────────────────────────
        abc = Card(b, tr("Afterburner-Einrichtung", "Afterburner setup"),
                   subtitle=tr("Was der GPU-Tuner braucht — ✗-Zeilen sagen, wo du es einschaltest.",
                               "What the GPU tuner needs — ✗ rows tell you where to switch it on."),
                   accent=ACC)
        abc.pack(**pad)
        button(abc.actions, tr("Setup prüfen", "Check setup"), self._run_setup_check, kind="ghost",
               height=28, image=icon_image("refresh", TEXT2, 14), compound="left").pack(side="right")
        self.setup_frame = tk.Frame(abc.body, bg=CARD_BG)
        self.setup_frame.pack(fill="x")

        # ── Safety: restore point + registry backup ───────────────────────────
        duo = ResponsiveGrid(b, min_width=360, max_cols=2, gap=14)
        duo.pack(**pad)
        rp = Card(duo, tr("Wiederherstellungspunkt", "Restore point"), accent=GREEN)
        duo.add(rp)
        WrapLabel(rp.body, text=tr(
            "Erstellt einen Windows-Wiederherstellungspunkt als Sicherheitsnetz — am besten VOR dem "
            "Anwenden von Tweaks. Braucht Admin-Rechte und aktivierten Computerschutz; Windows erlaubt "
            "standardmäßig höchstens einen Punkt pro 24 h.",
            "Creates a Windows restore point as a safety net — best BEFORE applying tweaks. Needs admin "
            "rights and System Protection; by default Windows allows one point per 24 h."),
            font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")
        self.btn_restore = button(rp.body, tr("Wiederherstellungspunkt erstellen", "Create restore point"),
                                  self._create_restore_point, kind="primary", color=GREEN, height=30,
                                  image=icon_image("shield", on_color(GREEN), 14), compound="left")
        self.btn_restore.pack(anchor="w", pady=(10, 0))
        self.lbl_restore = WrapLabel(rp.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_restore.pack(fill="x", pady=(6, 0))

        rb = Card(duo, "Registry-Backup", accent=VIOLET)
        duo.add(rb)
        WrapLabel(rb.body, text=tr(
            "Exportiert alle Registry-Zweige, die die Tweaks anfassen können, als .reg-Dateien — zum "
            "Zurückspielen genügt ein Doppelklick. Vor jedem Stapel-Apply und jedem Revert-All passiert "
            "das automatisch; hier kannst du zusätzlich jederzeit von Hand sichern.",
            "Exports every registry branch the tweaks can touch as .reg files — double-click to restore. "
            "This happens automatically before every batch apply and revert-all; here you can back up "
            "by hand at any time."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")
        rbb = tk.Frame(rb.body, bg=CARD_BG)
        rbb.pack(fill="x", pady=(10, 0))
        self.btn_regbackup = button(rbb, tr("Registry sichern", "Back up registry"),
                                    self._create_registry_backup, kind="primary", color=VIOLET, height=30,
                                    image=icon_image("save", on_color(VIOLET), 14), compound="left")
        self.btn_regbackup.pack(side="left", padx=(0, 6))
        button(rbb, tr("Ordner öffnen", "Open folder"), self._open_backup_folder, height=30,
               image=icon_image("folder", TEXT, 14), compound="left").pack(side="left")
        self.lbl_regbackup = WrapLabel(rb.body, text="", font=F_MONO, fg=DIM, bg=CARD_BG)
        self.lbl_regbackup.pack(fill="x", pady=(6, 0))

        # ── System cleaner ────────────────────────────────────────────────────
        cl = Card(b, "System Cleaner & Deep Clean", accent=AMBER)
        cl.pack(**pad)
        WrapLabel(cl.body, text=tr(
            "Immer: Benutzer-Temp, Windows-Temp, CrashDumps — nur Dateien, die älter als 24 Stunden sind "
            "(frische Temp-Dateien laufender Programme bleiben). Optional (Deep Clean): die angehakten "
            "Ziele unten. Niemals Dokumente oder Browserprofile (Passwörter, Verlauf, Lesezeichen). "
            "Dateien in Benutzung werden übersprungen und zählen nicht als freigegeben.",
            "Always: user temp, Windows temp, crash dumps — only files older than 24 hours (fresh temp "
            "files of running programs stay). Optional (Deep Clean): the ticked targets below. Never "
            "documents or browser profiles (passwords, history, bookmarks). Files in use are skipped "
            "and not counted as freed."), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x", pady=(0, 8))
        self._deep_vars: dict[str, tk.BooleanVar] = {}
        for key, (label, desc, confirm) in system_cleaner.DEEP_GROUPS.items():
            row = tk.Frame(cl.body, bg=CARD_BG)
            row.pack(fill="x", pady=3)
            v = tk.BooleanVar(value=False)
            self._deep_vars[key] = v
            CheckBox(row, v, accent=AMBER, bg=CARD_BG).pack(side="left", anchor="n", padx=(0, 8))
            txt = tk.Frame(row, bg=CARD_BG)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=label, font=F_BB, fg=AMBER if confirm else TEXT, bg=CARD_BG,
                     anchor="w").pack(fill="x")
            WrapLabel(txt, text=desc, font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")
        cb = tk.Frame(cl.body, bg=CARD_BG)
        cb.pack(fill="x", pady=(10, 0))
        button(cb, tr("Scannen", "Scan"), self._cleaner_scan, height=30,
               image=icon_image("search", TEXT, 14), compound="left").pack(side="left", padx=(0, 6))
        self.btn_clean = button(cb, tr("Bereinigen", "Clean"), self._cleaner_clean, kind="primary",
                                color=AMBER, height=30)
        self.btn_clean.pack(side="left")
        self.lbl_cleaner = tk.Label(cl.body, text="Noch nicht gescannt.", font=F_MONO, fg=DIM,
                                    bg=CARD_BG, justify="left", anchor="w")
        self.lbl_cleaner.pack(fill="x", pady=(8, 0))

        # ── About ─────────────────────────────────────────────────────────────
        about = Card(b, tr("Über", "About"), accent=SLATE)
        about.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(about.body, text="GameOptimizerPro v2.0 — by FloDePin", font=F_BB, fg=TEXT,
                 bg=CARD_BG, anchor="w").pack(fill="x")
        WrapLabel(about.body, text=tr(
            "All-in-one Windows- & GPU-Optimizer · GPU-Tuner (NVML + MAHM + Afterburner) · "
            "Oberfläche: CustomTkinter",
            "All-in-one Windows & GPU optimizer · GPU tuner (NVML + MAHM + Afterburner) · "
            "UI: CustomTkinter"), font=F_XS, fg=DIM, bg=CARD_BG).pack(fill="x")

        # Run setup check on init
        self.after(200, self._run_setup_check)

    def _on_wheel(self, e):
        if self._canvas.yview() != (0.0, 1.0):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)) * 20, "units")

    # ── Start ─────────────────────────────────────────────────────────────────

    def _show_autostart(self, enabled):
        self.v_autostart.set(enabled is True)
        self.sw_autostart.configure(state="normal")

    def _toggle_autostart(self):
        if not self.startup_loader:
            return
        want = bool(self.v_autostart.get())
        self.sw_autostart.configure(state="disabled")

        def done(ok):
            self.sw_autostart.configure(state="normal")
            if ok is not True:
                messagebox.showerror(
                    "Autostart",
                    "Konnte den Autostart nicht einrichten.\n"
                    "Stelle sicher, dass GameOptimizerPro als Administrator läuft.")
                self.v_autostart.set(not want)
        run_async(self, lambda: self.startup_loader.set_autostart(want), done)

    def _load_startup_now(self):
        if not self.startup_loader:
            return
        self.lbl_startup_result.config(text="Lade Profil über Afterburner …", fg=DIM)

        def done(res):
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.lbl_startup_result.config(text=msg, fg=GREEN if ok else AMBER)
        run_async(self, self.startup_loader.load_startup_profile, done)

    # ── Safety ────────────────────────────────────────────────────────────────

    def _create_restore_point(self):
        self.btn_restore.configure(state="disabled")
        self.lbl_restore.config(text="Erstelle Wiederherstellungspunkt … (kann bis zu 1 Min dauern)", fg=DIM)

        def done(res):
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.lbl_restore.config(text=msg, fg=GREEN if ok else AMBER)
            self.btn_restore.configure(state="normal")
        run_async(self, lambda: restore_point.create("GameOptimizerPro Tweaks"), done)

    def _create_registry_backup(self):
        self.btn_regbackup.configure(state="disabled")
        self.lbl_regbackup.config(text="Sichere Registry-Zweige … (kann einen Moment dauern)", fg=DIM)

        def done(res):
            if isinstance(res, Exception):
                self.lbl_regbackup.config(text=str(res), fg=AMBER)
            else:
                self.lbl_regbackup.config(text=res.summary(), fg=GREEN if res.ok else AMBER)
            self.btn_regbackup.configure(state="normal")
        run_async(self, lambda: registry_backup.create("Manual"), done)

    def _open_backup_folder(self):
        import subprocess as sp
        root = registry_backup.backup_root()
        try:
            os.makedirs(root, exist_ok=True)
            sp.Popen(["explorer.exe", root])
        except Exception as e:
            messagebox.showerror("Fehler", f"Backup-Ordner konnte nicht geöffnet werden:\n{e}")

    # ── Cleaner ───────────────────────────────────────────────────────────────

    def _cleaner_targets(self):
        keys = [k for k, v in self._deep_vars.items() if v.get()]
        return (system_cleaner.get_targets()
                + system_cleaner.get_deep_targets([k for k in keys if k != "recyclebin"]),
                "recyclebin" in keys)

    def _cleaner_scan(self):
        self.lbl_cleaner.config(text="Scanne…", fg=DIM)
        targets, with_bin = self._cleaner_targets()

        def work():
            system_cleaner.scan(targets)
            tf = sum(t.file_count for t in targets)
            tb = sum(t.bytes for t in targets)
            groups: dict[str, list] = {}
            for t in targets:
                if t.exists and t.file_count:
                    g = system_cleaner.DEEP_GROUPS.get(t.key, (t.label,))[0] if t.key else t.label
                    acc = groups.setdefault(g, [0, 0])
                    acc[0] += t.file_count
                    acc[1] += t.bytes
            if with_bin:
                n, size = system_cleaner.recycle_bin_info()
                if n:
                    groups["Papierkorb"] = [n, size]
                    tf += n
                    tb += size
            lines = [f"Gefunden: {tf} Dateien, {system_cleaner.human_size(tb)}"]
            for g, (n, size) in groups.items():
                lines.append(f"   • {g}: {n} Dateien, {system_cleaner.human_size(size)}")
            return "\n".join(lines), (GREEN if tf else DIM)

        def done(res):
            if isinstance(res, Exception):
                self.lbl_cleaner.config(text=f"Scan fehlgeschlagen: {res}", fg=AMBER)
            else:
                self.lbl_cleaner.config(text=res[0], fg=res[1])
        run_async(self, work, done)

    def _cleaner_clean(self):
        targets, with_bin = self._cleaner_targets()
        deep = sorted({system_cleaner.DEEP_GROUPS[t.key][0] for t in targets if t.key})
        extra = ("\n\nDeep Clean: " + ", ".join(deep)) if deep else ""
        if not messagebox.askyesno(
            "Bereinigen",
            "Jetzt bereinigen?\n\nImmer: Temp-/Dump-Ordner. Dateien, die gerade in Benutzung "
            "sind, werden übersprungen." + extra):
            return
        if with_bin and not messagebox.askyesno(
            "Papierkorb leeren",
            "Der Papierkorb ALLER Laufwerke wird endgültig geleert.\n\n"
            "Gelöschte Dateien sind danach nicht mehr wiederherstellbar. Fortfahren?",
            icon="warning"):
            with_bin = False
        self.lbl_cleaner.config(text="Bereinige…", fg=DIM)
        self.btn_clean.configure(state="disabled")

        def work():
            res = system_cleaner.clean(targets)
            freed = res.bytes_freed
            bin_note = ""
            if with_bin:
                ok, size = system_cleaner.empty_recycle_bin()
                freed += size
                bin_note = ("   + Papierkorb geleert" if ok else "   (Papierkorb: nicht möglich)")
            msg = (f"✓ {res.files_deleted} Dateien gelöscht, "
                   f"{system_cleaner.human_size(freed)} freigegeben{bin_note}")
            if res.errors:
                msg += f"   ({res.errors} in Benutzung übersprungen)"
            return msg

        def done(msg):
            self.lbl_cleaner.config(text=str(msg), fg=AMBER if isinstance(msg, Exception) else GREEN)
            self.btn_clean.configure(state="normal")
        run_async(self, work, done)

    # ── Afterburner setup check ───────────────────────────────────────────────

    def _run_setup_check(self):
        for w in self.setup_frame.winfo_children():
            w.destroy()

        checks = []

        checks.append((
            "MSI Afterburner installiert",
            self.ab.available,
            self.ab.exe or "Nicht gefunden — https://www.msi.com/Landing/afterburner"
        ))

        checks.append((
            "NVML (nvidia-ml-py)",
            self.monitor.nvml.available,
            "OK" if self.monitor.nvml.available else "pip install nvidia-ml-py"
        ))

        mahm = self.monitor.mahm.available
        checks.append((
            "MAHM Shared Memory (Afterburner-Monitoring)",
            mahm,
            "✓ Afterburner-Monitoring wird gelesen" if mahm else
            "Afterburner starten und im Tray lassen"
        ))

        ab_cfg = self.ab.check_ab_setup() if self.ab.available else {}
        no_cfg = "Afterburner einmal starten (legt Profiles\\MSIAfterburner.cfg an)"
        checks.append((
            "AB: Unlock Voltage Control",
            ab_cfg.get("voltage_control", False),
            "✓" if ab_cfg.get("voltage_control") else
            (no_cfg if not ab_cfg.get("cfg_found") else
             "AB → Einstellungen → Allgemein → Spannungssteuerung freischalten")
        ))
        checks.append((
            "AB: Unlock Voltage Monitoring",
            ab_cfg.get("voltage_monitoring", False),
            "✓" if ab_cfg.get("voltage_monitoring") else
            (no_cfg if not ab_cfg.get("cfg_found") else
             "AB → Einstellungen → Allgemein → Spannungsüberwachung freischalten")
        ))
        # Ground truth: does Afterburner's monitoring export a voltage right now?
        # (4.6.6 keeps no graph list in its cfg until the page is changed.)
        volt = mahm and self.monitor.mahm.read().gpu_voltage_mv > 0
        if not mahm and ab_cfg.get("voltage_graph") is not None:
            volt = bool(ab_cfg.get("voltage_graph"))
        checks.append((
            "AB: Graph 'GPU-Spannung' aktiv",
            volt,
            "✓ Spannung wird geliefert" if volt else
            "AB → Einstellungen → Überwachung → Haken bei 'GPU-Spannung' (für V/F-Tuning)"
        ))

        if self.ab.available:
            gpu_cfg, why = self.ab.find_gpu_profile()
        else:
            gpu_cfg, why = None, "Afterburner nicht installiert"
        checks.append((
            "AB: Profildatei der Grafikkarte",
            bool(gpu_cfg),
            os.path.basename(gpu_cfg) if gpu_cfg else why
        ))

        try:
            import ctypes
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            admin = False
        checks.append((
            "Administrator-Rechte",
            admin,
            "✓ Admin-Rechte vorhanden" if admin else
            "GameOptimizerPro.bat verwenden — fragt automatisch per UAC nach Admin"
        ))

        try:
            import pystray, PIL      # noqa: F401
            tray_ok = True
        except ImportError:
            tray_ok = False
        checks.append((
            "Systemtray (pystray + Pillow)",
            tray_ok,
            "✓" if tray_ok else "pip install pystray Pillow"
        ))

        for i, (label, ok, detail) in enumerate(checks):
            bg = CARD_BG2 if i % 2 == 0 else CARD_BG
            row = tk.Frame(self.setup_frame, bg=bg)
            row.pack(fill="x")
            tk.Label(row, text="✓" if ok else "✗", font=("Segoe UI Semibold", 11),
                     fg=GREEN if ok else ERR, bg=bg, width=3).pack(side="left", padx=(6, 4), pady=5)
            tk.Label(row, text=label, font=F_S, fg=TEXT, bg=bg, width=44, anchor="w"
                     ).pack(side="left", pady=5)
            WrapLabel(row, text=detail, font=F_XS, fg=DIM if ok else AMBER, bg=bg
                      ).pack(side="left", fill="x", expand=True, padx=8, pady=5)
