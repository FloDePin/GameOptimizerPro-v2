<div align="center">

# ⚡ GameOptimizerPro v2.6

**Windows & Gaming Optimizer v2.6 by FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.6-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 **English** | 🇩🇪 [Deutsch](README.de.md)

*All-in-one PC optimization tool — GPU Auto-Tuner, Audio Optimization, Windows Tweaks, BIOS Guide, Per-Game Profiles and more.*

</div>

---

## ✨ Features

### 🎮 GPU Auto-Tuner
- **3 Tune Modes:** Overclock Only, Undervolt Only, OC + UV (Recommended)
- Automated step-by-step stability testing with stress worker
- TDR (GPU driver timeout) detection via Windows Event Log
- Crash Recovery — automatically restores last stable profile on next boot
- Live Voltage/Clock/Temp graph during tuning
- Integrates with **MSI Afterburner** (MAHM Shared Memory for real mV readings)
- GPU generation auto-detection (Pascal → Ada Lovelace, RDNA 1–3)

### 🔊 Audio Optimization
- **Low-latency audio tweaks** for gaming — disable audio enhancements, exclusive audio lock
- **System sound optimization** — disable Nahimic service, disable Windows sound scheme
- **Audio CPU Priority** — MMCSS Pro Audio priority maximization for distortion-free audio under load
- **Audio Ducking Control** — prevent Discord/music from being muted by games
- **Windows Audio Enhancement Removal** — reduces audio latency and CPU overhead
- All audio tweaks integrated into **Windows Optimizer** for easy on/off control
- ✨ **NEW in v2.1.1:** Full verification & revert support for all audio tweaks

### 📊 Live Dashboard
- Real-time **GPU telemetry** (voltage, temp, clocks, power, load) + gauge bars
- **CPU / RAM / Disk usage** tiles alongside the GPU stats (via psutil)
- **Network Latency Test** — one-click ping to your gateway + Cloudflare (1.1.1.1) & Google (8.8.8.8) with average/min/max latency, jitter and packet loss

### 🧹 System Cleaner & Safety
- Safely clears temp/dump folders (user `%TEMP%`, `Windows\Temp`, `CrashDumps`)
- **Never** touches documents, browser profiles or the recycle bin; skips files in use
- Scan first to see how much can be freed, then clean with one click
- **Create Restore Point** — one-click Windows System Restore Point as a safety net before applying tweaks

### 🛠 Windows Optimizer
- **71 Tweaks** across Windows, Gaming, Network, Audio categories
- Live status verification — reads actual Registry/Service state (not just JSON)
- 3-state indicators: ● Green (verified active) / ◑ Amber (applied, unverified) / ○ Grey (inactive)
- **Graduated one-click presets — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat)** — cumulative intensity tiers that apply a curated, escalating set of tweaks
- **10 built-in Presets:** the 3 intensity tiers + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, All Safe Tweaks
- Export / Import settings as `.nextune` files
- Tooltips (hover `?`) on every single tweak
- ✨ **NEW in v2.1.1:** 4 powerful new tweaks for gaming & system optimization

### 🖥 BIOS Guide
- Hardware-aware recommendations (auto-detects CPU, GPU, Motherboard)
- Live system state detection — shows what's already active (green ●) vs still needed (red ●)
- Covers: AMD Zen 3/4/5, Intel 12th/13th/14th Gen, X670/B650/Z790/Z690
- Settings include exact BIOS menu paths + Windows Registry equivalents

### 🎮 Per-Game Profiles
- Background process monitor (psutil, ~3s interval, resource-light)
- Auto-loads GPU profile when a game starts, restores default when it closes
- **Per-Game CPU Pinning (CPU Sets)** — optionally steer a game onto specific cores: the **X3D cache chiplet** on dual-CCD AMD, or the **P-cores** on Intel Hybrid. Soft scheduler hint (never starves the game); honestly disabled on single-chiplet CPUs where it wouldn't help
- 15 pre-configured games (CS2, Cyberpunk 2077, Apex Legends, Valorant, Fortnite...)
- Add any `.exe` process manually

### 📋 Tune History
- Logs every Auto-Tune run (date, mode, core offset, power, voltage, score)
- Click any run to view the full log

### 🌡 Temperature Warning
- Windows Toast Notification when GPU hits 90°C
- 5-minute cooldown between warnings, configurable limit

### 🔄 Update Checker
- Checks GitHub Releases on startup (non-blocking background thread)
- Shows download link when a new version is available

### 🌐 Language Support
- **English** (default) and **German** — toggle with `EN/DE` button in the title bar
- Instant switch, no restart required

### 🚀 Startup Manager
- Separate window listing all autostart entries from Registry
- Status for each entry: Safe ✓ / Caution ⚠ / System ⚙ / Unknown ?
- 40+ pre-classified known processes (Discord, Steam, Corsair, NVIDIA, etc.)

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10 / Windows 11 |
| **Python** | 3.10 or newer |
| **GPU** | NVIDIA (full support) or AMD (tweaks + BIOS guide) |
| **MSI Afterburner** | Optional — required for voltage readings (mV) and OC profiles |
| **Admin rights** | Required for Registry tweaks and GPU power control |

---

## 📦 Installation

### 1. Install Python
Download Python 3.10+ from [python.org/downloads](https://python.org/downloads).

> ⚠️ **Important:** Check **"Add Python to PATH"** during installation.

### 2. Download GameOptimizerPro
Click **Code → Download ZIP** on this page, or clone the repo:
```bash
git clone https://github.com/FloDePin/GameOptimizerPro-v2.git
```
Extract to a permanent folder, e.g. `C:\Tools\GameOptimizerPro\`

### 3. Install Dependencies
Double-click `install.bat` — it installs everything automatically:
```
pystray, Pillow, nvidia-ml-py, numpy, wmi, psutil
```

### 4. (Optional) Set up MSI Afterburner
For voltage readings and GPU overclocking:
1. Download and install [MSI Afterburner](https://www.msi.com/Landing/afterburner/graphics-cards)
2. Open Afterburner → Settings → **General** → check **"Unlock voltage control"**
3. Settings → **General** → check **"Unlock voltage monitoring"**
4. Settings → **Monitoring** → enable **GPU Core Voltage**
5. Click the 🔒 lock icon on Profile Slot 2 to unlock it
6. Leave Afterburner running in the system tray

### 5. Launch
Double-click **`GameOptimizerPro.bat`**

> The launcher uses a hidden PowerShell `Start-Process -Verb RunAs` call to start `pythonw.exe` invisibly and requests Administrator rights via UAC. No CMD window will appear.

---

## 📜 Changelog

### v2.6 ⭐ **CURRENT** — 2026-09-03
- 🧩 **New: Per-Game CPU Pinning (CPU Sets)** — the Per-Game Profiles tab can now steer a game and its child processes onto specific CPU cores at launch: the **X3D cache chiplet** on dual-CCD AMD (detected by its larger L3), or the **P-cores / E-cores** on Intel Hybrid. Uses the Windows CPU Sets API (`SetProcessDefaultCpuSets`) — a *soft* hint that never starves the game — with `psutil` affinity as fallback. On a single-chiplet CPU with no P/E split (e.g. Ryzen 7 9800X3D) it honestly tells you pinning brings no benefit instead of faking a choice

### v2.5 — 2026-09-02
- 🤖 **New tweak: Disable Text & Image Generation (on-device AI)** (Privacy) — turns off Windows' on-device generative AI (Settings → Privacy → Text and image generation). Added to the Privacy & Hard presets. **71 tweaks total**
- 🖥 **BIOS Guide: "Disable motherboard auto-install utilities"** — added to the AMD (Zen 3/4/5) and Intel (Raptor/Alder Lake) profiles with exact per-vendor paths (ASUS / MSI / Gigabyte / ASRock). Stops the board silently installing vendor bloatware (Armoury Crate, MSI Center, App Center …) at first boot

### v2.4.2 — 2026-08-28 *(bug-fix release)*
- 🐛 **Fix: thread-safe log (potential random crash)** — the log box was written directly from worker threads (tweak apply/revert/preset), which can throw `RuntimeError: main thread is not in main loop` in Tkinter. It now uses a thread-safe queue drained by a main-thread poller — safe from any thread
- 🧹 normalised 3 verifier registry paths that used quadruple backslashes (they worked — PowerShell tolerates it — but were inconsistent); `get_all_presets()` now self-populates "All Safe Tweaks"
- ✔️ reviewed: autostart-via-Task-Scheduler and single-call BIOS detection were already fixed in v2.4.1; "All Safe does nothing" was not reproducible (the UI populates it before use)

### v2.4.1 — 2026-08-22 *(bug-fix release)*
- 🐛 **Fix: autostart no longer prompts UAC every boot** — "start with Windows" now uses a Task Scheduler task with *highest privileges* (`schtasks /RL HIGHEST`) instead of an `HKCU\Run` entry, so the admin app starts elevated silently. Old Run entry auto-removed
- ⚡ **BIOS detection ~5–8× faster** — the ~8 separate PowerShell cold-starts on opening the BIOS Guide are now one bundled JSON call (~1.9 s vs ~5–8 s). State dots appear much sooner (detection already ran off the UI thread, so it never froze)
- 🐛 **Fix: honest PBO detection** — WMI `MaxClockSpeed` is the reported max, not a live boost, so older CPUs (e.g. Ryzen 5 3600) showed a false "inactive". Threshold lowered, marked low-confidence, note now says PBO can't be reliably read from Windows
- 🧹 network test uses `utf-8`/replace instead of `latin-1` (convention; `latin-1` never actually crashed)

### v2.4 — 2026-08-20
- 🎚 **New: graduated one-click presets — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat)** — cumulative intensity tiers in the Optimizer that apply a curated, escalating set of tweaks (10 → 33 → 65), each through the normal confirm + verify flow. Minimal = only rock-solid safe tweaks; Medium adds performance/gaming/network + light debloat; Hard adds aggressive debloat (Cortana/Copilot/Recall/Teams/OneDrive), full performance/network/audio and the Win11-classic UI
- Situational/preference tweaks stay separate on purpose (Disable MPO, Dark Mode, the other power plans, Google DNS)

### v2.3.1 — 2026-08-14 *(bug-fix release)*
- 🐛 **Fix: stress-worker dead-man's-switch** *(shipped as v2.3.2)* — the CPU-fallback's parent-alive check relied on `psutil`; if that couldn't import, the switch silently disabled and a burner could run forever. Now uses a dependency-free `ctypes` `OpenProcess` check (reliable on Windows), with `psutil` fallback and "exit if unverifiable". (`os.getppid()` doesn't work here — Windows never re-parents orphans, verified by test)
- 🐛 **Fix: installer/launcher Python mismatch** — `install.bat` could install dependencies into the Microsoft-Store Python while the launcher runs classic `C:\PythonXX\pythonw.exe` → `ModuleNotFoundError`. The installer now uses the **same** classic-Python search as the launcher (`"%PY%" -m pip …`)
- 🐛 **Fix: elevation working directory** — `relaunch_admin()` now passes `str(BASE)` to `ShellExecuteW`, so UAC no longer drops the app into `System32`
- 🐛 **Fix: CPU stress fallback used one core** — the no-numpy fallback now spawns one process per core (`multiprocessing`) and each child self-terminates when the test is stopped (no orphaned CPU-burners)
- 🐛 **Fix: launcher missed all-users installs** — added `C:\Program Files\PythonXX\` paths to launcher + installer
- 🐛 **Fix: tray menu could collapse** — menu now rebuilt every 60 s instead of 20 s (known pystray quirk)
- 🧹 `requirements.txt` relaxed lower bounds (`numpy>=1.26` etc.); `.gitignore` now covers virtual-env folders

### v2.3 — 2026-08-10
- 🛟 **New: Create Restore Point** (Settings) — one-click Windows System Restore Point as a safety net before applying tweaks (clear messages for protection-disabled / 24 h-limit / not-admin)
- 🖥 **New tweak: Disable Multiplane Overlay (MPO)** — known fix for screen flicker / micro-stutter (NVIDIA + multi-monitor); flagged honestly as "only if you have flicker problems", recent drivers largely fixed it
- 🛡 **New tweak: Disable WPBT** — blocks firmware/motherboard from injecting programs into Windows at boot
- 🗂 **New tweaks: Show File Extensions + Show Hidden Files** — Explorer QoL, also helps spot disguised files
- 🧹 **New tweak: Disable Storage Sense** — stops Windows auto-deleting files in the background
- ➡️ **70 tweaks total.** Picked from the Chris-Titus WinUtil set — deliberately skipped the unsafe/unfitting ones (BitLocker-off, Services→Manual, IPv6/Teredo off, Edge removal, cosmetic toggles)

### v2.2 — 2026-08-05
- 🌐 **New: Network Latency Test** (Dashboard) — one-click ping to your gateway + Cloudflare (1.1.1.1) & Google (8.8.8.8) with average/min/max latency, jitter and packet loss (read-only, runs in the background)
- 📊 **New: Live System Monitoring** — CPU, RAM and Disk-C: usage tiles added to the Dashboard next to the GPU telemetry (via psutil), colour-coded by load
- 🧹 **New: System Cleaner** (Settings) — scans & clears only dedicated temp/dump folders (`%TEMP%`, `Windows\Temp`, `CrashDumps`); a safety guard means it never touches documents, browser profiles or the recycle bin, and files in use are skipped
- 🖥 **New: iGPU-disable BIOS tip** for AM5 (Zen 4/5) — added to the BIOS Guide with exact ASUS/Gigabyte menu paths and an honest write-up of the trade-offs (frees reserved RAM, but disables the board's display outputs + iGPU encoder)
- ⚡ **New tweaks (2):** PCIe Link State Power Management off, Hard disk never sleep → **65 tweaks total**
- 🐛 **Fix: verifier engine** — a PowerShell grouping bug (`$__r=(cmd)` vs `$__r=$(cmd)`) meant most registry status checks silently showed the amber "unverified" dot; the green/amber/grey indicators now reflect real state for **all** tweaks
- 🐛 **Fix:** non-English Windows `ping` output no longer crashes the network test (latin-1 decoding)
- 🪟 **UI:** larger default window (1000×920) so the full dashboard fits at startup

### v2.1.1 — 2026-07-05
- 🐛 **Fix: launcher window** — removed a `-WindowStyle Hidden` flag on the inner `Start-Process` that started the whole app window invisibly (only fix was killing the process)
- 🐛 **Fix: registry tweaks** — corrected a double-backslash escaping bug that made "Disable Power Throttling" & "Process Count Reduction" fail with "invalid key name" every time
- 🔊 **Fix: audio tweaks** — "Disable Audio Enhancements" & "Disable Exclusive Audio Lock" now have full status verification **and** revert commands
- 🛡 **Fix:** "Block Telemetry Hosts" now reverts precisely (removes only the appended hosts-file entries)
- 🔒 **Hardening:** profile names/notes sanitized (no `.cfg` injection); game-profile file writes are now thread-safe (lock)
- 🎯 **New tweaks (4):** Disable Consumer Features, Disable Hibernation, End Task via Right-Click, Disable Delivery Optimization
- 📚 **Docs/CI:** added German README (`README.de.md`) + GitHub Actions CI (syntax & registry-path validation)

### v2.1 — 2026-07-02
- ✨ **3 new tweaks:** Disable Power Throttling (Gaming), Process Count Reduction / Svchost (Gaming), Disable Bing in Windows Search (Privacy) — all with revert + verification
- 🛡 **Safety review:** deliberately excluded risky third-party tweaks (AMD Crash Defender off, C-States off, ULPS off, modded drivers) that reduce stability/security without meaningful gains

### v2.0 — 2026-05-25
- 🎮 **New: Per-Game Profiles** — background process monitor auto-loads a GPU profile when a game starts, restores default on exit
- 📋 **New: Tune History Viewer**, 🌡 **GPU Temperature Toast** (≥90 °C, 5-min cooldown), 🔄 **GitHub Update Checker**
- 🖥 **New: BIOS Guide Tab** — hardware-aware recommendations with live state detection
- 🚀 **New: Startup Manager**, 🔀 **Profile Comparison Tab**, 💾 **Export/Import** as `.nextune`
- ✅ **New: Tweak Status Verification** — reads real Registry/Service state (3-state dots), **7 built-in presets**
- 🌐 **New: DE/EN language toggle**, ℹ️ tooltips on every tweak, 📈 live Voltage/Clock/Temp graph
- ⚡ **GPU Tuner:** 3 modes (OC / UV / OC+UV), generation auto-detection, TDR detection (Event ID 4101), crash recovery
- 🏗 **Rewrite:** thread-safe architecture — `tkinter mainloop()` on the main thread, tray in a daemon thread (fixes freezes/crashes)

### v1.0 — 2026-05-23 *(Initial Release)*
- 🎮 **GPU Auto-Tuner** (automated OC + UV via MSI Afterburner)
- 🛠 **Windows Optimizer** (50 tweaks: Windows, Gaming, Network)
- 📊 **Dashboard** (live GPU telemetry), 🔥 **Stress Test** + FurMark launcher
- 🖥 **Hardware Detection** (WMI), 💾 **Profile Manager**, 🖲 **System Tray** with live stats

> Full technical detail for every release: [CHANGELOG.md](CHANGELOG.md)

---

## 🚀 First Steps

1. Open **[WIN] Optimizer** → click **"⟳ Check Status"** to see which tweaks are already active (green ● = active, amber ◑ = needs verification)
2. Apply the **🎮 Gaming Preset** for a quick all-in-one optimization
3. Find **Audio tweaks** in **[WIN] Optimizer** (category: Audio) — enable low-latency audio tweaks for gaming
4. Try **[WIN] Optimizer** → **Performance Preset** if you want maximum system performance
5. Check **[BIOS] BIOS Guide** — it detects your hardware and shows what to change
6. If you have Afterburner running, try the **[GPU] GPU Tuner** → Start Tune (OC+UV recommended)

---

## 🗂 Project Structure

```
GameOptimizerPro/
├── GameOptimizerPro.py       ← Main entry point
├── GameOptimizerPro.bat      ← Launcher (PowerShell Start-Process, hidden, UAC)
├── install.bat               ← Dependency installer
├── _stress_worker.py         ← GPU stress test subprocess
├── requirements.txt          ← Python dependencies
├── .github/
│   └── workflows/
│       └── ci.yml            ← GitHub Actions CI (syntax & registry checks)
├── core/
│   ├── nvtune_core.py        ← GPU monitor (NVML + MAHM), Afterburner controller
│   ├── nvtune_tuner.py       ← Auto-tuner (Stage 1 OC, Stage 2 UV, TDR detection)
│   ├── vf_curve.py           ← Voltage-frequency curve optimization
│   ├── hardware.py           ← WMI hardware detection
│   ├── tweaks.py             ← 70 tweaks database (Windows, Gaming, Network, Audio)
│   ├── network_test.py       ← Gateway/DNS ping latency test
│   ├── system_cleaner.py     ← Safe temp/junk file cleaner
│   ├── restore_point.py      ← System Restore Point creator
│   ├── tweak_runner.py       ← PowerShell executor (hidden)
│   ├── tweak_verifier.py     ← Registry verification (100% coverage)
│   ├── tweak_presets.py      ← 7 built-in presets
│   ├── tweak_i18n.py         ← Multilingual tweak descriptions (EN/DE)
│   ├── bios_guide.py         ← BIOS recommendations database
│   ├── bios_detector.py      ← Live BIOS state detection
│   ├── game_monitor.py       ← Per-game profile monitor (psutil, thread-safe)
│   ├── cpu_topology.py       ← CPU topology (CCDs, P/E cores, X3D cache die)
│   ├── cpu_pinning.py        ← Per-game CPU pinning via CPU Sets API
│   ├── crash_recovery.py     ← TDR detection, crash flag system
│   ├── temp_monitor.py       ← GPU temp toast notifications
│   ├── update_checker.py     ← GitHub releases API
│   ├── export_import.py      ← .nextune export/import
│   ├── tune_history.py       ← Tune log parser
│   ├── startup_loader.py     ← Autostart + startup profile loader
│   ├── gpu_defaults.py       ← GPU generation defaults table
│   ├── mahm_reader.py        ← MSI Afterburner shared memory reader
│   └── i18n.py               ← EN/DE language module
└── ui/
    ├── main_window.py        ← Main window, tab router
    ├── widgets.py            ← Shared widgets, colors, styles
    ├── tab_dashboard.py      ← System overview + live GPU telemetry
    ├── tab_optimizer.py      ← Windows optimizer with sidebar (includes Audio tweaks)
    ├── tab_gpu.py            ← GPU tuner UI
    ├── tab_stress.py         ← Stress test + FurMark launcher
    ├── tab_compare.py        ← Profile comparison
    ├── tab_bios.py           ← BIOS guide with live detection
    ├── tab_games.py          ← Per-game profiles + tune history
    ├── tab_settings.py       ← Autostart, setup checker, about
    ├── live_graph.py         ← Rolling voltage/clock/temp graph
    └── startup_manager.py    ← Startup manager window
```

---

## ⚙️ Architecture

```
Main Thread   → tkinter mainloop() — only thread touching the UI
Thread 2      → pystray.run() — system tray icon
Thread 3      → GPU stats loop (4s interval)
Thread 4      → Startup (crash check + profile load)
Thread 5      → Menu refresh (20s interval)
Thread 6      → Game process monitor (3s interval, psutil) — thread-safe with locks
Thread 7      → Temperature monitor (10s interval)
Thread 8+     → Auto-tune stages, stress worker subprocess
```

Cross-thread communication uses `widget.after(0, callback)` — the only safe way to update tkinter from background threads.

---

## 🛡 Safety

- **No BIOS writes** — BIOS Guide is read-only recommendations only
- **No driver modifications** — works through MSI Afterburner and official NVML
- **Registry tweaks are reversible** — "Revert All" restores defaults
- **Crash recovery** — TDR detection automatically resets GPU to safe settings
- **Admin rights** are requested via UAC, not baked in
- **Audio tweaks are reversible** — all changes can be undone with "Revert"
- **Profile injection protection** — names & notes sanitized to prevent registry injection
- **Hosts file safe revert** — telemetry entries removed precisely, no data loss

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
Made with ❤️ by FloDePin
</div>
