"""
GameOptimizerPro Settings Tab
- Windows Autostart toggle
- Startup profile loader toggle
- Afterburner setup checker
- About
"""

import tkinter as tk
from tkinter import messagebox, ttk
import os
import threading
from ui.widgets import *
from core import system_cleaner
from core import restore_point
from core import registry_backup


class SettingsTab(tk.Frame):
    def __init__(self, parent, ab, monitor, startup_loader, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self.ab             = ab
        self.monitor        = monitor
        self.startup_loader = startup_loader
        self._build()

    def _build(self):
        # Scrollable — with Deep Clean the page is taller than a normal window.
        self._canvas = tk.Canvas(self, bg=BG1, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        body = tk.Frame(self._canvas, bg=BG1)
        win = self._canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(
            win, width=e.width))
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        tk.Label(body, text="Settings", font=FT, fg=WHT, bg=BG1
                 ).pack(padx=14, pady=(12, 8), anchor="w")

        # ── Startup ───────────────────────────────────────────────────────────
        SecHdr(body, "Startup").pack(fill="x", padx=14, pady=(4, 4))

        stt_f = tk.Frame(body, bg=BG2, padx=12, pady=10)
        stt_f.pack(fill="x", padx=14, pady=(0, 8))

        # Autostart toggle
        self.v_autostart = tk.BooleanVar(
            value=self.startup_loader.is_autostart_enabled()
            if self.startup_loader else False
        )
        as_row = tk.Frame(stt_f, bg=BG2)
        as_row.pack(fill="x", pady=4)
        tk.Checkbutton(
            as_row, variable=self.v_autostart,
            bg=BG2, activebackground=BG2, selectcolor=BG3,
            fg=TXT, highlightthickness=0, bd=0,
            command=self._toggle_autostart
        ).pack(side="left")
        tk.Label(as_row, text="Mit Windows starten (HKCU Autostart)",
                 font=FL, fg=TXT, bg=BG2).pack(side="left", padx=4)

        # Load startup profile toggle
        self.v_load_startup = tk.BooleanVar(value=True)
        ls_row = tk.Frame(stt_f, bg=BG2)
        ls_row.pack(fill="x", pady=4)
        tk.Checkbutton(
            ls_row, variable=self.v_load_startup,
            bg=BG2, activebackground=BG2, selectcolor=BG3,
            fg=TXT, highlightthickness=0, bd=0,
        ).pack(side="left")
        tk.Label(ls_row,
                 text="Tray-Default GPU-Profil beim Start automatisch laden",
                 font=FL, fg=TXT, bg=BG2).pack(side="left", padx=4)

        mk_btn(stt_f, "⟳ Jetzt Startup-Profil laden",
               self._load_startup_now, BG3, TXT
               ).pack(anchor="w", pady=(8, 0))

        self.lbl_startup_result = tk.Label(stt_f, text="", font=FM,
                                           fg=DIM, bg=BG2)
        self.lbl_startup_result.pack(anchor="w", pady=2)

        # ── Afterburner Setup ─────────────────────────────────────────────────
        SecHdr(body, "Afterburner Setup Checker").pack(fill="x", padx=14, pady=(8, 4))

        self.setup_frame = tk.Frame(body, bg=BG1)
        self.setup_frame.pack(fill="x", padx=14, pady=(0, 8))

        mk_btn(body, "⟳ Setup prüfen", self._run_setup_check, BG3, TXT
               ).pack(padx=14, anchor="w", pady=(0, 4))

        # ── System Restore Point ──────────────────────────────────────────────
        SecHdr(body, "Wiederherstellungspunkt").pack(fill="x", padx=14, pady=(8, 4))
        rp_f = tk.Frame(body, bg=BG2, padx=12, pady=10)
        rp_f.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(rp_f,
                 text="Erstellt einen Windows-Wiederherstellungspunkt als Sicherheitsnetz — "
                      "am besten VOR dem Anwenden von Tweaks. Erfordert Admin-Rechte und aktivierten "
                      "Computerschutz. Windows erlaubt standardmäßig max. einen Punkt pro 24 h.",
                 font=FM, fg=DIM, bg=BG2, justify="left", wraplength=560).pack(anchor="w")
        self.btn_restore = mk_btn(rp_f, "🛟 Wiederherstellungspunkt erstellen",
                                  self._create_restore_point, BG3, TXT)
        self.btn_restore.pack(anchor="w", pady=(8, 2))
        self.lbl_restore = tk.Label(rp_f, text="", font=FM, fg=DIM, bg=BG2,
                                    justify="left", anchor="w", wraplength=560)
        self.lbl_restore.pack(anchor="w", pady=(4, 0))

        # ── Registry-Backup ───────────────────────────────────────────────────
        SecHdr(body, "Registry-Backup").pack(fill="x", padx=14, pady=(8, 4))
        rb_f = tk.Frame(body, bg=BG2, padx=12, pady=10)
        rb_f.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(rb_f,
                 text="Exportiert alle Registry-Zweige, die die Tweaks anfassen können, als "
                      ".reg-Dateien — zum Zurückspielen genügt ein Doppelklick. Vor jedem "
                      "Stapel-Apply und jedem Revert-All passiert das automatisch; hier kannst "
                      "du zusätzlich jederzeit von Hand sichern.",
                 font=FM, fg=DIM, bg=BG2, justify="left", wraplength=560).pack(anchor="w")
        rb_btns = tk.Frame(rb_f, bg=BG2)
        rb_btns.pack(anchor="w", pady=(8, 2))
        self.btn_regbackup = mk_btn(rb_btns, "💾 Registry sichern",
                                    self._create_registry_backup, BG3, TXT)
        self.btn_regbackup.pack(side="left", padx=(0, 6))
        mk_btn(rb_btns, "📂 Backup-Ordner öffnen",
               self._open_backup_folder, BG3, TXT).pack(side="left")
        self.lbl_regbackup = tk.Label(rb_f, text="", font=FM, fg=DIM, bg=BG2,
                                      justify="left", anchor="w", wraplength=560)
        self.lbl_regbackup.pack(anchor="w", pady=(4, 0))

        # ── System Cleaner ────────────────────────────────────────────────────
        SecHdr(body, "System Cleaner & Deep Clean").pack(fill="x", padx=14, pady=(8, 4))
        cln_f = tk.Frame(body, bg=BG2, padx=12, pady=10)
        cln_f.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(cln_f,
                 text="Immer: Benutzer-Temp, Windows-Temp, CrashDumps. Optional (Deep Clean, "
                      "aus v1): die angehakten Ziele unten. Niemals Dokumente oder Browserprofile "
                      "(Passwörter, Verlauf, Lesezeichen). Dateien in Benutzung werden übersprungen "
                      "und zählen nicht als freigegeben.",
                 font=FM, fg=DIM, bg=BG2, justify="left", wraplength=560).pack(anchor="w")
        deep_f = tk.Frame(cln_f, bg=BG2)
        deep_f.pack(anchor="w", fill="x", pady=(6, 0))
        self._deep_vars: dict[str, tk.BooleanVar] = {}
        for key, (label, desc, confirm) in system_cleaner.DEEP_GROUPS.items():
            row = tk.Frame(deep_f, bg=BG2)
            row.pack(anchor="w", fill="x")
            v = tk.BooleanVar(value=False)
            self._deep_vars[key] = v
            tk.Checkbutton(row, variable=v, bg=BG2, activebackground=BG2, selectcolor=BG3,
                           fg=TXT, highlightthickness=0, bd=0).pack(side="left")
            tk.Label(row, text=label, font=FL, fg=WRN if confirm else TXT, bg=BG2
                     ).pack(side="left", padx=(2, 6))
            tk.Label(row, text=desc, font=FM, fg=DIM, bg=BG2, justify="left",
                     wraplength=420, anchor="w").pack(side="left", fill="x")
        cln_btns = tk.Frame(cln_f, bg=BG2)
        cln_btns.pack(anchor="w", pady=(8, 2))
        mk_btn(cln_btns, "🔍 Scannen", self._cleaner_scan, BG3, TXT).pack(side="left", padx=(0, 6))
        self.btn_clean = mk_btn(cln_btns, "🧹 Bereinigen", self._cleaner_clean, BG3, TXT)
        self.btn_clean.pack(side="left")
        self.lbl_cleaner = tk.Label(cln_f, text="Noch nicht gescannt.", font=FM,
                                    fg=DIM, bg=BG2, justify="left", anchor="w")
        self.lbl_cleaner.pack(anchor="w", pady=(6, 0))

        # ── About ─────────────────────────────────────────────────────────────
        SecHdr(body, "About").pack(fill="x", padx=14, pady=(8, 4))
        about_f = tk.Frame(body, bg=BG2, padx=12, pady=10)
        about_f.pack(fill="x", padx=14)
        tk.Label(about_f,
                 text="GameOptimizerPro v2.0\n"
                      "All-in-one Windows & GPU Optimizer\n"
                      "GPU Tuner (NVML + MAHM + Afterburner)\n"
                      "by FloDePin",
                 font=FM, fg=DIM, bg=BG2, justify="left"
                 ).pack(anchor="w")

        # Run setup check on init
        self.after(200, self._run_setup_check)
        self._bind_wheel(self._canvas)

    def _on_wheel(self, e):
        if self._canvas.yview() != (0.0, 1.0):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _toggle_autostart(self):
        if not self.startup_loader:
            return
        ok = self.startup_loader.set_autostart(self.v_autostart.get())
        if not ok:
            messagebox.showerror(
                "Autostart",
                "Konnte Autostart-Eintrag nicht schreiben.\n"
                "Stelle sicher dass GameOptimizerPro als Administrator läuft."
            )
            self.v_autostart.set(not self.v_autostart.get())

    def _load_startup_now(self):
        if not self.startup_loader:
            return
        self.lbl_startup_result.config(text="Lade Profil über Afterburner …", fg=DIM)

        def work():
            ok, msg = self.startup_loader.load_startup_profile()
            try:
                self.after(0, lambda: self.lbl_startup_result.config(
                    text=msg, fg=OK if ok else WRN))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _create_restore_point(self):
        self.btn_restore.config(state="disabled")
        self.lbl_restore.config(text="Erstelle Wiederherstellungspunkt … (kann bis zu 1 Min dauern)", fg=DIM)
        def work():
            ok, msg = restore_point.create("GameOptimizerPro Tweaks")
            self.after(0, lambda: (
                self.lbl_restore.config(text=msg, fg=OK if ok else WRN),
                self.btn_restore.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    def _create_registry_backup(self):
        self.btn_regbackup.config(state="disabled")
        self.lbl_regbackup.config(text="Sichere Registry-Zweige … (kann einen Moment dauern)", fg=DIM)

        def work():
            res = registry_backup.create("Manual")
            self.after(0, lambda: (
                self.lbl_regbackup.config(text=res.summary(), fg=OK if res.ok else WRN),
                self.btn_regbackup.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    def _open_backup_folder(self):
        import subprocess as sp
        import os
        root = registry_backup.backup_root()
        try:
            os.makedirs(root, exist_ok=True)
            sp.Popen(["explorer.exe", root])
        except Exception as e:
            messagebox.showerror("Fehler", f"Backup-Ordner konnte nicht geöffnet werden:\n{e}")

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
            self.after(0, lambda: self.lbl_cleaner.config(
                text="\n".join(lines), fg=OK if tf else DIM))
        threading.Thread(target=work, daemon=True).start()

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
        self.btn_clean.config(state="disabled")

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
            self.after(0, lambda: (
                self.lbl_cleaner.config(text=msg, fg=OK),
                self.btn_clean.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

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
        except:
            admin = False
        checks.append((
            "Administrator-Rechte",
            admin,
            "✓ Admin-Rechte vorhanden" if admin else
            "GameOptimizerPro.bat verwenden — fragt automatisch per UAC nach Admin"
        ))

        try:
            import pystray, PIL
            tray_ok = True
        except ImportError:
            tray_ok = False
        checks.append((
            "Systemtray (pystray + Pillow)",
            tray_ok,
            "✓" if tray_ok else "pip install pystray Pillow"
        ))

        self.after(50, lambda: self._bind_wheel(self.setup_frame))
        for i, (label, ok, detail) in enumerate(checks):
            row = tk.Frame(
                self.setup_frame,
                bg=BG2 if i % 2 == 0 else BG1,
                pady=5
            )
            row.pack(fill="x", pady=1)
            tk.Label(row, text="✓" if ok else "✗",
                     font=("Segoe UI", 11, "bold"),
                     fg=OK if ok else ERR,
                     bg=row.cget("bg"), width=3
                     ).pack(side="left", padx=(8, 4))
            tk.Label(row, text=label, font=FL,
                     fg=TXT, bg=row.cget("bg"),
                     width=38, anchor="w"
                     ).pack(side="left")
            tk.Label(row, text=detail, font=FM,
                     fg=DIM if ok else WRN,
                     bg=row.cget("bg"), anchor="w",
                     wraplength=380, justify="left"
                     ).pack(side="left", padx=8, fill="x", expand=True)
