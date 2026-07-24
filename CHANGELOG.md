# Changelog

All notable changes to GameOptimizerPro are documented here.

---

## [2.1.1] — 2026-07-05

### 🐛 Bug Fixes
- **Launcher window silently starting hidden** — `GameOptimizerPro.bat` passed an extra `-WindowStyle Hidden` to the inner `Start-Process` call launching `pythonw.exe`. Since `pythonw.exe` has no console to hide, that flag instead hid the first window the process created (the Tkinter main window) with no way to bring it back except killing the process
- **"Disable Power Throttling" / "Process Count Reduction" tweaks always failing** — a double-escaped backslash in the registry path made `reg.exe` reject both commands with "invalid key name" every time
- **Audio tweaks incomplete** — `Disable Audio Enhancements` and `Disable Exclusive Audio Lock` had no registry verification (always showed "applied, unverified") and no revert command; both added and validated against a synthetic test registry structure
- **"Block Telemetry Hosts" not revertible** — added a revert command that removes exactly the appended hosts-file entries
- Minor: `core/game_monitor.py` now serializes profile-apply + last-applied-profile writes with a lock to avoid overlapping file writes on rapid game switches
- Docs: corrected stale references to the old repo name/URL and to a VBScript-based launcher description (the launcher has used PowerShell `Start-Process` since v2.0)

---

## [2.1] — 2026-07-02

### New Tweaks
- **Disable Power Throttling** (Gaming) — sets PowerThrottlingOff so Windows does not throttle game side-processes for power saving
- **Process Count Reduction** (Gaming, moderate) — raises the Svchost split threshold to RAM size, bundling services into fewer processes. Requires reboot
- **Disable Bing in Windows Search** (Privacy) — turns off Bing web integration so Start menu search stays local and loads faster

### Notes
- Reviewed several tweaks from third-party utilities and deliberately excluded the risky ones (AMD Crash Defender off, C-States off, ULPS off, modded drivers) because they reduce stability or security without meaningful gains, especially on systems that undervolt with the built-in GPU tuner
- All three new tweaks include revert commands and registry verification checks

---

## [2.0] — 2026-05-25

### 🆕 New Features
- **Per-Game Profiles** — background process monitor (psutil) auto-loads GPU profiles when games start
- **Tune History Viewer** — log viewer for all past Auto-Tune runs
- **GPU Temperature Toast** — Windows notification at ≥90°C with 5-min cooldown
- **GitHub Update Checker** — non-blocking background check on startup
- **DE/EN Language Toggle** — instant switch, English default
- **BIOS Guide Tab** — hardware-aware BIOS recommendations with live state detection
- **? Tooltips** on every tweak (hover to see description)
- **Startup Manager Window** — lists all autostart entries with Safe/Caution/System classification
- **Profile Comparison Tab** — compare up to 4 GPU profiles side-by-side
- **Export / Import** — save tweaks, profiles and presets as `.nextune` files
- **Tweak Status Verification** — reads actual Registry/Service state (100% coverage, 50/50 tweaks)
- **7 built-in Presets** — Gaming, Privacy, Debloat, Network, Performance, Win11 Classic, All Safe
- **Live Voltage/Clock/Temp Graph** — rolling canvas graph during Auto-Tune
- **Crash Recovery** — TDR detection + auto-restore of last stable profile

### ⚡ GPU Tuner
- 3 Tune Modes: OC Only / UV Only / OC+UV (Recommended)
- GPU generation auto-detection fills safe defaults (Pascal → Ada, RDNA 1–3)
- TDR detection via Windows Event Log (Event ID 4101)
- Crash flag system — clears on clean exit, triggers recovery on crash

### 🛠 Optimizer
- 3-state status circles: ● verified / ◑ applied / ○ inactive
- Auto-verify on tab open (800ms) and after every Apply
- Fast batch (20s) + slow batch (30s) verification — AppxPackage checks don't block Registry checks

### 🏗 Architecture (thread-safe rewrite)
- `tkinter mainloop()` exclusively in Main Thread
- `pystray.run()` in daemon Thread
- Cross-thread via `widget.after(0, callback)` — no more freezes or crashes
- Admin check via `ctypes.windll.user32.MessageBoxW` — no orphan `tk.Tk()` before mainloop
- `os._exit(0)` for guaranteed clean process termination

### 🐛 Bug Fixes
- Fixed `v_core_step` AttributeError — IntVars now initialized before `_show_gpu_defaults()`
- Fixed `gpu_power_w` AttributeError — field added to `GpuStats` dataclass
- Fixed Treeview/Combobox white background — global `option_add` dark overrides
- Fixed BIOS Guide scroll — recursive `bind("<MouseWheel>")` on all child widgets
- Fixed tray "Exit" not killing process — `os._exit(0)` in background thread
- Removed duplicate `nextune.py` and `NexTune.bat`

---

## [1.0] — 2026-05-23 *(Initial Release — GameOptimizerPro)*

### Core Features
- **GPU Auto-Tuner** — automated OC + UV via MSI Afterburner
- **Windows Optimizer** — 50 tweaks (Windows, Gaming, Network)
- **Dashboard** — live GPU telemetry (temp, clock, voltage, power, load)
- **Stress Test** — internal GPU stress worker + FurMark launcher
- **System Tray** — icon with live stats tooltip and profile quick-switch
- **Hardware Detection** — CPU, GPU, RAM, Motherboard via WMI
- **MSI Afterburner Integration** — MAHM Shared Memory for real voltage readings
- **Profile Manager** — save, load, apply GPU profiles
- **Crash Recovery** — basic TDR detection and profile reset
- Dark themed UI with colored tab buttons

### Known Issues in v1.0 (fixed in v2.0)
- `tkinter mainloop()` ran in sub-thread — caused freezes on some systems
- GPU status dots were always grey (verify ran only once on startup)
- Treeview and Combobox dropdowns showed white background
- `v_core_step` AttributeError when GPU detection ran before IntVar init
- No language support (German only)
- No per-game profile monitoring
- No BIOS recommendations
- No export/import
- No update checking

---

*Dates reflect development/release dates. For full commit history see [GitHub](https://github.com/FloDePin/GameOptimizerPro-v2.1.1/commits).*
