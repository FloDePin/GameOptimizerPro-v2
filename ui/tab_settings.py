"""
GameOptimizerPro Settings Tab
- Windows Autostart toggle
- Startup profile loader toggle
- Afterburner setup checker
- About
"""

import tkinter as tk
from tkinter import messagebox
import threading
from ui.widgets import *
from core import system_cleaner
from core import restore_point


class SettingsTab(tk.Frame):
    def __init__(self, parent, ab, monitor, startup_loader, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self.ab             = ab
        self.monitor        = monitor
        self.startup_loader = startup_loader
        self._build()

    def _build(self):
        tk.Label(self, text="Settings", font=FT, fg=WHT, bg=BG1
                 ).pack(padx=14, pady=(12, 8), anchor="w")

        # ── Startup ───────────────────────────────────────────────────────────
        SecHdr(self, "Startup").pack(fill="x", padx=14, pady=(4, 4))

        stt_f = tk.Frame(self, bg=BG2, padx=12, pady=10)
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
        SecHdr(self, "Afterburner Setup Checker").pack(fill="x", padx=14, pady=(8, 4))

        self.setup_frame = tk.Frame(self, bg=BG1)
        self.setup_frame.pack(fill="x", padx=14, pady=(0, 8))

        mk_btn(self, "⟳ Setup prüfen", self._run_setup_check, BG3, TXT
               ).pack(padx=14, anchor="w", pady=(0, 4))

        # ── System Restore Point ──────────────────────────────────────────────
        SecHdr(self, "Wiederherstellungspunkt").pack(fill="x", padx=14, pady=(8, 4))
        rp_f = tk.Frame(self, bg=BG2, padx=12, pady=10)
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

        # ── System Cleaner ────────────────────────────────────────────────────
        SecHdr(self, "System Cleaner (Temp-Dateien)").pack(fill="x", padx=14, pady=(8, 4))
        cln_f = tk.Frame(self, bg=BG2, padx=12, pady=10)
        cln_f.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(cln_f,
                 text="Löscht nur dedizierte Temp-/Dump-Ordner (Benutzer-Temp, Windows-Temp, "
                      "CrashDumps). Niemals Dokumente, Browserprofile oder Papierkorb. "
                      "Dateien in Benutzung werden übersprungen.",
                 font=FM, fg=DIM, bg=BG2, justify="left", wraplength=560).pack(anchor="w")
        cln_btns = tk.Frame(cln_f, bg=BG2)
        cln_btns.pack(anchor="w", pady=(8, 2))
        mk_btn(cln_btns, "🔍 Scannen", self._cleaner_scan, BG3, TXT).pack(side="left", padx=(0, 6))
        self.btn_clean = mk_btn(cln_btns, "🧹 Bereinigen", self._cleaner_clean, BG3, TXT)
        self.btn_clean.pack(side="left")
        self.lbl_cleaner = tk.Label(cln_f, text="Noch nicht gescannt.", font=FM,
                                    fg=DIM, bg=BG2, justify="left", anchor="w")
        self.lbl_cleaner.pack(anchor="w", pady=(6, 0))

        # ── About ─────────────────────────────────────────────────────────────
        SecHdr(self, "About").pack(fill="x", padx=14, pady=(8, 4))
        about_f = tk.Frame(self, bg=BG2, padx=12, pady=10)
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
        ok, msg = self.startup_loader.load_startup_profile()
        self.lbl_startup_result.config(
            text=msg, fg=OK if ok else WRN)

    def _create_restore_point(self):
        self.btn_restore.config(state="disabled")
        self.lbl_restore.config(text="Erstelle Wiederherstellungspunkt … (kann bis zu 1 Min dauern)", fg=DIM)
        def work():
            ok, msg = restore_point.create("GameOptimizerPro Tweaks")
            self.after(0, lambda: (
                self.lbl_restore.config(text=msg, fg=OK if ok else WRN),
                self.btn_restore.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    def _cleaner_scan(self):
        self.lbl_cleaner.config(text="Scanne…", fg=DIM)
        def work():
            targets = system_cleaner.scan()
            tf = sum(t.file_count for t in targets)
            tb = sum(t.bytes for t in targets)
            lines = [f"Gefunden: {tf} Dateien, {system_cleaner.human_size(tb)}"]
            for t in targets:
                if t.exists:
                    lines.append(f"   • {t.label}: {t.file_count} Dateien, "
                                 f"{system_cleaner.human_size(t.bytes)}")
            self.after(0, lambda: self.lbl_cleaner.config(
                text="\n".join(lines), fg=OK if tf else DIM))
        threading.Thread(target=work, daemon=True).start()

    def _cleaner_clean(self):
        if not messagebox.askyesno(
            "Bereinigen",
            "Temp-Dateien jetzt löschen?\n\nBetrifft nur Temp-/Dump-Ordner. "
            "Dateien, die gerade in Benutzung sind, werden übersprungen."):
            return
        self.lbl_cleaner.config(text="Bereinige…", fg=DIM)
        self.btn_clean.config(state="disabled")
        def work():
            res = system_cleaner.clean()
            msg = (f"✓ {res.files_deleted} Dateien gelöscht, "
                   f"{system_cleaner.human_size(res.bytes_freed)} freigegeben")
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
            "MAHM Shared Memory (Spannung verfügbar)",
            mahm,
            "Spannungswerte aktiv ✓ — Volt wird im Dashboard angezeigt" if mahm else
            "Für grünes MAHM: 1) AB starten & im Tray lassen  "
            "2) AB → Einstellungen → Überwachung → 'GPU Spannung' Haken setzen  "
            "3) AB → Allgemein → 'Spannungsüberwachung entsperren' aktivieren"
        ))

        ab_cfg = self.ab.check_ab_setup() if self.ab.available else {}
        checks.append((
            "AB: Unlock Voltage Control",
            ab_cfg.get("voltage_control", False),
            "✓" if ab_cfg.get("voltage_control") else
            "AB → Settings → General → Unlock voltage control → Standard MSI"
        ))
        checks.append((
            "AB: Unlock Voltage Monitoring",
            ab_cfg.get("voltage_monitoring", False),
            "✓" if ab_cfg.get("voltage_monitoring") else
            "AB → Settings → General → Unlock voltage monitoring aktivieren"
        ))

        locked = self.ab.check_profile_locked(2) if self.ab.available else False
        checks.append((
            "AB Profil-Slot 2 entsperrt",
            not locked,
            "✓ Slot 2 ist beschreibbar" if not locked else
            "Schloss-Symbol neben Slot 2 in Afterburner öffnen"
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
