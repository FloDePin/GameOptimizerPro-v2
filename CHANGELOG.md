# Changelog

All notable changes to GameOptimizerPro are documented here.

---

## [2.6.2] — 2026-09-05

### 🐛 Bug Fixes (from two external code-review reports, each verified against the actual code first)
- **🔴 Stress-worker orphan on the numpy path (real, could peg the CPU forever)** — `cpu_stress()`'s numpy branch ran a `while True` BLAS loop with **no** parent-alive check; only the rarely-used no-numpy fallback (`_burn`) had one. Since numpy ships in `requirements.txt`, the *unprotected* path was the active one — so a hard GUI crash (not the clean Stop button) left a process at 100% CPU indefinitely. The GUI PID is now passed to the worker as `argv[1]`, and **every** burn loop (cupy, numpy, and the multiprocessing children) checks it and self-terminates when the GUI is gone. *Verified with a live test: worker exits within ~1–2 s of its parent dying.* This completes the v2.3.2 fix, which only covered the fallback
- **Update checker missed pre-release-style tags** — `_parse_version("v2.7.0-beta")` collapsed to `(0,)` (via `int("0-beta")`), so a suffixed tag was ranked *older* than the current version and never offered. Now parses the numeric core before any `-`/`+` suffix → `(2, 7, 0)`. Also split the redundant `except (URLError, Exception)` into real offline vs. other-error handling
- **`disable_hpet` revert wasn't symmetric** — the apply *deletes* `useplatformclock`, but the revert *set it to `true`* (a value that was never there, and potentially worse for timer latency than the default). Revert now deletes all three BCD values, restoring the true Windows default
- **Tweak-state file was a CWD-relative path** — `applied_tweaks.json` used `"logs/…"` (relative to the working dir) while the logs use an absolute path; launched from another dir (autostart / UAC relaunch) the two diverged and the applied-state looked lost. Anchored to the same absolute logs dir
- **`wmic` CPU fallback mapped columns wrong** — `wmic /format:csv` returns columns **alphabetically**, not in the requested order, so the positional parse put the CPU *name* into the core-count field and a *number* into the name. Now maps columns by header name (only affects the no-`wmi`-module fallback)
- **MAHM reader could drop late sensor entries** — the shared-memory buffer was sized with the nominal 260-byte stride while the real per-entry stride (from the header) can be 284, truncating the last entries when many sensors are active. Buffer now sized with the maximum entry size
- **Presets no longer mutate shared module state** — `get_preset()/get_all_presets()` assigned `tweak_ids` onto the global `BUILTIN_PRESETS` objects (a shallow copy of the list still shares the objects); the "All Safe" preset is now returned as a fresh copy via `dataclasses.replace`
- **`restore_point.py` decoded PowerShell output as `latin-1`** → switched to `utf-8`/`errors="replace"`, consistent with the rest of the project (prevents garbled umlauts in status messages)

### 🔎 Reviewed, not changed (verified NOT a bug, or overstated)
- Two reports contradicted each other on GUI threading — the "critical race condition" in the tray `_open()` is already caught by its `try/except` and cannot crash the GUI; not a real bug. Claims of "no logging at all" were false (the tweak runner writes a daily logfile). "NVML shutdown memory leak" and "Afterburner lock-check reads 1–2 MB" were overstated. The bare-`except:` prevalence and default-English language are code-style/opinion, not defects, and were left as-is

---

## [2.6.1] — 2026-09-04

### 🛡️ CPU-Pinning safety & honesty (caveats from the reference tool, verified against our impl)
- **Anti-cheat caveat** — the CPU-assignment dialog now warns that pinning reaches into a foreign game process, which kernel-level anti-cheats (EAC, BattlEye, Vanguard) *could* theoretically flag. Use at your own risk with anti-cheat titles
- **CCD-parking conflict warning** (multi-CCD machines only) — warns that AMD's 3D V-Cache optimizer / Xbox Game Bar CCD-parking can overwrite our CPU-Set assignment (last-writer-wins) or silently ignore parked cores; recommends disabling those for reliable pinning
- **Pin verification** — after assigning a CPU Set, `pin_process()` now reads it back via `GetProcessDefaultCpuSets` and only reports success if our IDs actually stuck. This catches a concurrent overwrite (e.g. by AMD's driver) and permission failures. *Honest limitation:* the readback confirms the assignment is **registered**, not that the scheduler honours it — a set of only parked cores is ignored at scheduling time, which no API call can detect (hence the separate parking warning)
- **Result surfaced in the UI** — the Per-Game tab now shows "🧩 CPU-Pinning aktiv (N Kerne)" or an amber "⚠ Pinning wurde nicht übernommen …" when a game launches, via a new thread-safe `on_cpu_pin` callback drained by the main-thread poller (no `after()` from the monitor thread — same lesson as the v2.4.2 log-box fix)

---

## [2.6] — 2026-09-03

### 🚀 New Features
- **Per-Game CPU Pinning (CPU Sets)** — the Per-Game Profiles tab can now steer a game (and its child processes) onto a chosen set of CPU cores when it launches, on top of the existing GPU-profile assignment. Targets are derived from the *actual* detected topology:
  - **AMD X3D / dual-CCD** → pin to the **cache chiplet** (the CCD carrying the extra 3D V-Cache, identified by its larger L3), or to either chiplet individually
  - **Intel Hybrid** → pin to the **P-cores** (or E-cores), keeping the other core type free for background work
  - Uses the Windows **CPU Sets** API (`SetProcessDefaultCpuSets`) — a *soft* scheduler hint, not a hard affinity mask: the game runs preferentially on the chosen cores but can still spill over under load, so it can never be accidentally starved. Falls back to `psutil` affinity if CPU Sets are unavailable
  - **Honest by design:** on a single-chiplet CPU with no P/E split (e.g. Ryzen 7 9800X3D — one CCD), the tab tells you plainly that pinning brings no benefit and offers nothing to assign, instead of faking a choice
  - New `core/cpu_topology.py` (read-only detection via `GetSystemCpuSetInformation` + `GetLogicalProcessorInformationEx`) and `core/cpu_pinning.py`. Game assignments persist in `game_profiles.json` (old files load unchanged). Child processes spawned mid-session are re-pinned automatically

---

## [2.5] — 2026-09-02

### 🚀 New Features
- **New tweak: Disable Text & Image Generation (on-device AI)** (Windows/Privacy) — turns off Windows' on-device generative AI (Settings → Privacy → Text and image generation) via `…\CapabilityAccessManager\ConsentStore\systemAIModels\Value = Deny`. The exact key was verified live on a machine where the setting was already off. Added to the Privacy and Hard presets. **71 tweaks total**
- **BIOS Guide: "Disable motherboard auto-install utilities"** — added to the AMD (Zen 3/4/5) and Intel (Raptor/Alder Lake) profiles, with the exact per-vendor paths (ASUS Auto Install ASUS Utilities, MSI Driver Utility Installer, Gigabyte Utilities Downloader, ASRock Auto Driver Installer). Stops the board from silently installing vendor bloatware (Armoury Crate, MSI Center, App Center …) at first boot

---

## [2.4.2] — 2026-08-28

### 🐛 Bug Fixes
- **Thread-safe log output (potential random Tkinter crash)** — `LogBox.append()` touched the Tk text widget directly, but it's called from worker threads (tweak apply / revert / preset). Tkinter is single-threaded, so this could randomly throw `RuntimeError: main thread is not in main loop` or corrupt the widget (verified: even `after()` from a worker thread raises on Python 3.14). `LogBox` now uses a thread-safe **queue** written by any thread and drained by a **main-thread poller** — every caller is safe automatically, no call sites had to change
- **Consistency: verifier registry paths** — three verify commands (`disable_power_throttling`, `reduce_process_count`, `disable_bing_search`) used quadruple backslashes. They *worked* (PowerShell's registry provider tolerates `\\`, unlike `reg.exe`) but were inconsistent — normalised to the single form used everywhere else
- **Hardening: `get_all_presets()` now populates "All Safe Tweaks"** so the preset has a valid tweak list even when called directly (the UI already populated it at render time, so this was not a live bug — just defence in depth)

### ✔️ Reviewed, already fixed / not a bug
- Autostart-via-Task-Scheduler and single-call BIOS detection were **already shipped in v2.4.1**. A reported "All Safe does nothing" was **not reproducible** — the UI populates that preset before use.

---

## [2.4.1] — 2026-08-22

### 🐛 Bug Fixes (from a code review)
- **Autostart no longer triggers a UAC prompt on every boot** — the "start with Windows" option used an `HKCU\…\Run` entry, which can't launch the admin-required app silently, so Windows showed the yellow UAC dialog at every logon. It now registers a **Task Scheduler** task with *run with highest privileges* (`schtasks /RL HIGHEST /SC ONLOGON`), which starts elevated without a prompt. Any old `Run` entry is removed on toggle (migration)
- **BIOS detection ~5–8× faster** — opening the BIOS Guide fired ~8 separate `powershell.exe` cold-starts (one per detector). They're now bundled into a **single** PowerShell call that returns one JSON snapshot (measured ~1.9 s instead of ~5–8 s). Detection already ran on a background thread, so the UI never froze — but the green/red state dots now appear much sooner
- **Honest PBO detection** — `MaxClockSpeed` from WMI is the *reported* max, not a live boost reading, so the old `> 4500 MHz` heuristic showed a false "inactive" on older CPUs (e.g. Ryzen 5 3600). Lowered to `≥ 4200 MHz`, marked **low-confidence**, and the note now says plainly that PBO can't be reliably read from Windows — check the BIOS
- **Ping decoding** — switched the network test from `latin-1` to `utf-8`/`errors=replace` for consistency with the rest of the codebase (note: `latin-1` never actually crashes — it maps every byte — so this is a convention change, not a crash fix)

---

## [2.4] — 2026-08-20

### 🚀 New Features
- **Graduated one-click intensity presets — Minimal → Medium → Hard** (cumulative): three new buttons in the Optimizer that apply a curated, escalating set of tweaks. **Minimal** = only rock-solid safe tweaks, no loss of function (10). **Medium** = Minimal + performance plan, gaming/network tweaks and light debloat (33). **Hard — Debloat** = Medium + aggressive debloat (Cortana/Copilot/Recall/Teams/OneDrive), full performance/network/audio + Win11-classic UI, incl. select moderate tweaks (65). Each still runs through the normal confirmation + verification flow
  - Deliberately kept out of the tiers (remain individual toggles): `disable_mpo` (situational flicker fix), `enable_dark_mode` (pure cosmetics), `power_balanced`/`power_high` (would fight the Ultimate plan), `dns_google` (Cloudflare already covers it)

---

## [2.3.1] — 2026-08-14

### 🐛 Bug Fixes (from a code review)
- **Stress-worker dead-man's-switch hardened** — the CPU-fallback checked the parent process via `psutil.pid_exists()`; if `psutil` couldn't be imported it silently disabled the check and a burner could run forever after the parent died. Now uses a `ctypes` `OpenProcess`/`GetExitCodeProcess` check first (built into Python, no dependency, reliable on Windows), with `psutil` as a fallback and "treat as dead → exit" if nothing is checkable. Note: `os.getppid()` is **not** usable here — on Windows orphans are not re-parented, so it keeps returning the dead parent's PID forever (verified empirically). *(shipped as v2.3.2)*
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
