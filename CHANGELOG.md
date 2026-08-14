# Changelog

All notable changes to GameOptimizerPro are documented here.

---

## [2.3.2] — 2026-08-14

### 🐛 Bug Fixes
- **Stress-worker dead-man's-switch hardened** — the v2.3.1 CPU-fallback checked the parent process via `psutil.pid_exists()`; if `psutil` couldn't be imported it silently disabled the check and a burner could run forever after the parent died. Now uses a `ctypes` `OpenProcess`/`GetExitCodeProcess` check first (built into Python, no dependency, reliable on Windows), with `psutil` as a fallback and "treat as dead → exit" if nothing is checkable. Note: `os.getppid()` is **not** usable here — on Windows orphans are not re-parented, so it keeps returning the dead parent's PID forever (verified empirically)

---

## [2.3.1] — 2026-08-14

### 🐛 Bug Fixes (from a code review)
- **Installer / launcher Python mismatch (could crash the app on first run)** — `install.bat` used a plain `python`/`pip`, which can install the dependencies into the Microsoft-Store Python while the launcher starts the classic `C:\PythonXX\pythonw.exe` → `ModuleNotFoundError`. `install.bat` now uses the **same** classic-Python search as the launcher and installs via `"%PY%" -m pip install -r requirements.txt`
- **Elevation lost the working directory** — `relaunch_admin()` passed `lpDirectory=None` to `ShellExecuteW`, so after the UAC prompt Windows set the working dir to `System32`. Now passes `str(BASE)` (app already used absolute paths internally, so this is hardening)
- **CPU stress fallback only loaded one core** — the no-numpy fallback ran a single GIL-bound loop. It now spawns one process per core via `multiprocessing`; each child self-terminates when the worker is stopped (checks the parent PID), so no orphaned CPU-burning processes remain after a stress test
- **Launcher missed all-users Python installs** — added `C:\Program Files\PythonXX\` (and 312/313/314) to both the launcher and installer search paths
- **Tray menu could collapse** — the tray menu is now rebuilt every 60 s instead of 20 s, shrinking the window in which an open menu gets redrawn (a known pystray quirk)

### 🧹 Housekeeping
- `requirements.txt`: relaxed lower bounds (e.g. `numpy>=1.26` instead of `>=2.0`) so the app coexists with environments that have older, already-installed packages
- `.gitignore`: added `venv/ .venv/ env/ .env/ ENV/`

---

## [2.3] — 2026-08-10

### 🚀 New Features
- **Create Restore Point** (`core/restore_point.py` + Settings panel) — one-click Windows System Restore Point as a safety net before applying tweaks. Uses `Checkpoint-Computer`; reports clear messages for the common cases (protection disabled, 24 h frequency limit, not admin). The description is sanitized against injection
- **5 new tweaks (from the Chris-Titus WinUtil set, only the safe/fitting ones)** — **70 tweaks total**:
  - **Disable Multiplane Overlay (MPO)** (Gaming, moderate) — `OverlayTestMode=5`, a known fix for screen flicker / micro-stutter (esp. NVIDIA + multi-monitor). Flagged honestly: recent drivers largely fixed MPO, so only for people actually seeing flicker
  - **Disable WPBT** (Privacy) — blocks firmware/motherboard from injecting programs into Windows at boot (`DisableWpbtExecution=1`)
  - **Show File Extensions** / **Show Hidden Files** (Mouse & UI) — Explorer QoL, also helps spot disguised files
  - **Disable Storage Sense** (Performance) — stops Windows auto-deleting files in the background

### 📝 Notes
- Deliberately skipped WinUtil items that don't fit a gaming optimizer or aren't safe: BitLocker-off (weakens disk encryption), Services→Manual (risky batch), IPv6/Teredo off (can break networking), Edge removal (Windows depends on it), Date-to-UTC (dual-boot only), and pure cosmetic toggles. "Background Apps" was already covered by *Disable Background App Throttling*

---

## [2.2] — 2026-08-05

### 🚀 New Features
- **Network Latency Test** (`core/network_test.py` + Dashboard panel) — one-click ping to the default gateway + Cloudflare (1.1.1.1) and Google (8.8.8.8), reporting average/min/max latency, jitter and packet loss. Read-only, runs in a background thread. Parses the Windows `ping` output as latin-1 so non-English locales (e.g. German "Zeit=12ms") don't crash the reader thread
- **Live System Monitoring** — CPU, RAM and Disk-C: usage tiles added to the Dashboard next to the GPU telemetry (via `psutil`, already a dependency), colour-coded by load
- **System Cleaner** (`core/system_cleaner.py` + Settings panel) — scans and clears only dedicated temp/dump folders (user `%TEMP%`, `%SystemRoot%\Temp`, `%LOCALAPPDATA%\CrashDumps`). A safety guard refuses any path that isn't clearly a temp/dump dir, so it never touches documents, browser profiles or the recycle bin; files in use are skipped, target root dirs are kept
- **iGPU-disable BIOS recommendation** for AM5 (Zen 4/5) — added to the BIOS Guide with the exact ASUS/Gigabyte menu paths and an honest write-up of the trade-offs (frees ~0.5–2 GB reserved RAM, but disables the motherboard's display outputs and the iGPU video encoder; minimal FPS impact)
- **2 new power tweaks** — PCIe Link State Power Management off (steadier GPU-bus latency) and Hard disk never sleep (avoids micro-stutter when a background process wakes a sleeping HDD), both with apply/revert and a locale-independent powercfg verifier
- Larger default window (1000×920) so the full dashboard is visible at startup

### 🐛 Bug Fixes
- **Verifier engine parse bug** — `TweakVerifier` wrapped each check as `$__r=(cmd)`, but a PowerShell `(...)` grouping only accepts a single pipeline, so every verify command written as two statements (`$v=…; if(…){}`) — most of the registry checks — failed to parse and silently showed the amber "unverified" dot. Changed to `$__r=$(cmd)` (subexpression); the green/amber/grey indicators now reflect real state for all 65 tweaks

### 🎯 New Tweaks (since v2.1.1)
- 4 gaming tweaks from v2.1.1 (Disable Consumer Features, Disable Hibernation, End Task via Right-Click, Disable Delivery Optimization) plus the 2 power tweaks above — **65 tweaks total**, all with verification & revert

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

*Dates reflect development/release dates. For full commit history see [GitHub](https://github.com/FloDePin/GameOptimizerPro-v2/commits).*
