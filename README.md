<div align="center">

# ⚡ GameOptimizerPro v2.0

**Windows & Gaming Optimizer v2.0 by FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 **English** | 🇩🇪 [Deutsch](README.de.md)

*All-in-one PC optimization tool — GPU Auto-Tuner, Audio Optimization, Windows Tweaks, BIOS Guide, Per-Game Profiles and more.*

</div>

---

## ✨ Features

### 🎮 GPU Auto-Tuner
- **3 Tune Modes:** Overclock Only, Undervolt Only, OC + UV (Recommended)
- Automated step-by-step stability testing with stress worker — **refuses to tune without real GPU load** (measured during the baseline; ≥ 70 %), because an OC/UV test on an idle GPU would store unstable values as "stable". GPU load comes from the stress worker via `cupy` (`pip install cupy-cuda12x`) or from FurMark running in parallel
- **Abort really stops**: the running stress step ends immediately, the GPU goes back to stock (offsets 0, factory power limit) and nothing is applied afterwards; exiting the app or switching the language during a tune does the same
- TDR (GPU driver timeout) detection via Windows Event Log
- Crash Recovery — automatically restores last stable profile on next boot
- Live Voltage/Clock/Temp graph during tuning
- Integrates with **MSI Afterburner** (MAHM Shared Memory for real mV readings — parser follows Afterburner's documented layout; reconnects automatically when Afterburner is started later)
- GPU generation auto-detection (Pascal → Ada Lovelace, RDNA 1–3)
- ⚠️ **Known open issue:** applying OC profiles *to Afterburner* writes a file Afterburner doesn't read (it keeps profiles per GPU in `Profiles\VEN_…cfg`). The fix requires closing/restarting Afterburner and is being worked on — see [CHANGELOG.md](CHANGELOG.md)

### ⚡ Stress Test
- **Internal stability test** — built-in GPU/CPU stress worker with configurable duration and a **max-temp auto-abort**; includes a dead-man switch so it never leaves an orphaned 100%-CPU process behind. Fails on a **worker crash or a TDR**, reports the **average GPU load**, and says plainly "no GPU stress" instead of "passed" when the GPU wasn't loaded (no `cupy`); a stopped test reports no result
- **FurMark launcher** — auto-detects a FurMark install, pick the resolution, one-click launch for a heavier GPU burn-in

### 🔊 Audio Optimization
- **Low-latency audio tweaks** for gaming — disable audio enhancements, exclusive audio lock
- **System sound optimization** — disable Nahimic service, disable Windows sound scheme
- **Audio CPU Priority** — MMCSS Pro Audio priority maximization for distortion-free audio under load
- **Audio Ducking Control** — prevent Discord/music from being muted by games
- **Windows Audio Enhancement Removal** — reduces audio latency and CPU overhead
- All audio tweaks integrated into **Windows Optimizer** for easy on/off control
- Full verification & revert support for all audio tweaks

### 📊 Live Dashboard
- Real-time **GPU telemetry** (voltage, temp, clocks, power, load) + gauge bars
- **CPU / RAM / Disk usage** tiles alongside the GPU stats (via psutil)
- **Network Latency Test** — one-click ping to your gateway + Cloudflare (1.1.1.1) & Google (8.8.8.8) with average/min/max latency, jitter and packet loss

### 🧹 System Cleaner & Safety
- Safely clears temp/dump folders (user `%TEMP%`, `Windows\Temp`, `CrashDumps`)
- **Never** touches documents, browser profiles or the recycle bin; skips files in use
- Scan first to see how much can be freed, then clean with one click
- **Create Restore Point** — one-click Windows System Restore Point as a safety net before applying tweaks
- **Registry Backup** — exports every registry branch the tweaks can touch as `.reg` files (double-click to restore). Runs **automatically before every Apply Selected, preset, Revert All and "fix deviations"**, plus on demand; keeps the 10 newest backups and prunes older ones so it can't fill your disk

### 🛠 Windows Optimizer
- **83 Tweaks** across Windows, Gaming, Network, Audio categories (incl. AMD GPU tweaks)
- Live status verification — reads actual Registry/Service state (not just JSON)
- 3-state indicators: ● Green (verified active) / ◑ Amber (applied, unverified) / ○ Grey (inactive)
- **Graduated one-click presets — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat)** — cumulative intensity tiers that apply a curated, escalating set of tweaks
- **10 built-in Presets:** the 3 intensity tiers + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, All Safe Tweaks
- **AMD GPU tweaks** — disable ULPS, unlimited shader cache, Anti-Lag (low-latency mode); shown for AMD systems and honestly reported as inactive on NVIDIA. GPU-vendor tweaks (AMD and NVIDIA) are **hardware-guarded twice**: presets skip them on the wrong GPU, and the command itself refuses to run without a matching adapter — AMD values only ever go into the AMD adapter's driver key
- **Power Plan tweaks write to *every* power scheme** — Windows can activate a different plan after a reboot, which would otherwise make a setting look reverted. Plan GUIDs are read from `powercfg /L`, never the localized plan name, so it works in any language
- Export / Import settings as `.nextune` files
- Tooltips (hover `?`) on every single tweak

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

### 🩺 Diagnose & Measure
- **FPS / Frametime capture** — measure the *real* effect of your tweaks: **average FPS, 1% and 0.1% lows, stutters**, and a measured **CPU-vs-GPU bottleneck** verdict. Live via [PresentMon](https://github.com/GameTechDev/PresentMon) (optional, drop it in `tools/`) or analyze any existing PresentMon / CapFrameX / OCAT CSV — no binary needed for CSV analysis
- **Health Report** — read-only summary of what Windows already recorded in the last 30 days: WHEA hardware errors, bluescreens, unexpected shutdowns, GPU driver timeouts (TDR), disk errors, app crashes — with severity and last occurrence
- **Remnant Scan** — read-only detection of leftovers from *other* tweak tools (WinRing0 / inpout drivers, ISLC, TimerResolution autostarts, third-party power plans, Razer Cortex). Reports only — removes nothing

### 📊 Profile Compare
- Compare up to **4 saved GPU profiles side-by-side** (core/memory offset, power limit, voltage lock, stability score) to pick the best one at a glance

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

### 🔽 System Tray
- Minimizes to the tray instead of closing; the tray tooltip shows **live GPU temp / clock / voltage / power**
- Quick-apply any saved GPU profile, reset the GPU to stock, or open/exit — all from the tray menu

### 🚀 Startup Manager
- Separate window listing all autostart entries — the **Run keys (HKCU, HKLM, HKLM 32-bit) and both Startup folders** (per-user and all-users `.lnk` shortcuts, targets resolved)
- Shows the **real on/off state** and can **enable / disable** entries (multi-select) — exactly like Task Manager: only Windows' `StartupApproved` flag is set, nothing is deleted, so every change is reversible here or in Task Manager
- Confirmation before disabling, with an extra warning for system / not-recommended entries; filter for disabled entries
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
| **cupy** | Optional — `pip install cupy-cuda12x` gives the stress worker real **GPU** load (NVIDIA). Without it (or FurMark in parallel) the Auto-Tuner refuses to run |
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

### v2.0 — Final — 2026-09-05
GameOptimizerPro **2.0** is the finalized release: the complete feature set below, hardened over many internal iterations and **two full external code-review rounds** — every verified bug fixed, honestly.

**Highlights**
- 🩺 **Diagnose tab (measure, don't guess):** FPS/frametime capture with **1% & 0.1% lows**, stutters and a measured **CPU-vs-GPU bottleneck** (PresentMon live or CSV); a 30-day **Health Report** from Windows' own logs; and a **Remnant Scan** for other tweak tools' leftovers. All read-only. *(Also fixed a latent bug that hid the Games/Settings tab buttons.)*
- 🎮 **GPU Auto-Tuner** (OC / UV / OC+UV) with automated stability testing, live graph, TDR detection and crash recovery — plus MSI Afterburner (MAHM) integration
- 🛠 **83 verified tweaks** with live status (green/amber/grey), graduated Minimal→Medium→Hard presets and curated Gaming/Privacy/Debloat/Network/Performance/Win11 presets
- 🎮 **Per-Game Profiles + CPU Pinning (CPU Sets)** — steer games to the X3D cache chiplet (AMD) or P-cores (Intel), with anti-cheat & CCD-parking warnings and an honest "no benefit" note on single-chiplet CPUs
- 🖥 **BIOS Guide**, 📊 **Live Dashboard** (GPU + CPU/RAM/Disk + latency test), 🧹 **System Cleaner & Restore Point**, 📋 **Tune History**, 🚀 **Startup Manager**, 🌐 **DE/EN**

**Reliability & honesty (fixes folded into 2.0)**
- Stress-worker dead-man switch on all paths (no orphaned 100% CPU process); thread-safe log/UI; UAC-free autostart via Task Scheduler
- Honest per-tweak reverts (incl. 12 tweaks that were previously one-way) so "Revert All" truly reverts
- DX12 tweak rewritten honestly as "Raise GPU Timeout (TDR Delay)" (the old value was a no-op placebo); Nahimic verifier no longer false-ambers on PCs without Nahimic
- Robust update-checker version parsing, config-driven stability score, absolute state-file path, and assorted topology / MAHM / wmic / encoding edge-case fixes
- Auto-Tuner **final verification now tests the exact profile it saves** — including the V/F-curve undervolt and memory OC (previously the final run used stock voltage, so the saved undervolt was never verified as a whole)
- Header **clock and the AB / NVML / MAHM indicators now refresh reliably** — the old background updater could die on its first tick (Tk `after()` from a worker thread before mainloop on Python 3.14); it now runs on the main thread
- Per-game process scan reads the cached process name (no whole-scan blackout if a process dies mid-scan); FPS-CSV GPU column stays index-aligned on short rows
- **"Revert All" only ever touches what GameOptimizerPro applied** — "Check status" used to adopt every setting that was already active on the PC (dark mode, file extensions, …), so Revert All could switch off things you had set yourself; importing a `.nextune` marked tweaks as applied without applying them; "fix deviations" re-applied settings you never chose. The verifier now only *displays* state, the verify tab separates "reset behind our back" from "active, but not ours", and imports pre-select tweaks for review instead
- **GPU tweaks can't land on the wrong GPU** — presets applied NVIDIA/AMD-only tweaks on any hardware, and the AMD tweaks looped over *all* display adapters (incl. NVIDIA/Intel). Now filtered in the UI **and** guarded in each command
- **No more squatting of Afterburner's shared memory** — the MAHM reader *created* a 1 MB `MAHMSharedMemory` section whenever Afterburner wasn't running and kept it open; it now only opens an existing one, maps it at any size, and reconnects automatically when Afterburner is started later
- **Registry backup really runs automatically** — it was wired into batch methods the UI never called
- **Afterburner telemetry works** — the MAHM parser used a wrong layout (284-byte entries; real ones are 1324) and returned 0 for every sensor; empty MAHM values no longer overwrite good NVML readings (fan %, power limit), and CPU power is no longer shown as GPU temperature
- **Auto-Tune safety** — "Abort" could be overridden by the still-running step (an OC was re-applied after the reset to stock); exiting mid-tune left an untested OC; "reset to stock" set the card's *maximum* power limit; without GPU load (no `cupy`) the tuner "verified" OCs on an idle GPU — all fixed
- **Autostart survives** — Windows' task defaults killed the tray app after 3 days and blocked it on battery; the Stress Test no longer reports a stopped run as "PASSED"; Tune History shows the real mode; the primary GPU is detected on iGPU + dGPU systems
- Reviewed-and-verified-not-a-bug items were left unchanged rather than papered over

See [CHANGELOG.md](CHANGELOG.md) for the full detail.

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
│   ├── tweaks.py             ← 83 tweaks database (Windows, Gaming, Network, Audio)
│   ├── network_test.py       ← Gateway/DNS ping latency test
│   ├── system_cleaner.py     ← Safe temp/junk file cleaner
│   ├── registry_backup.py    ← Exports affected registry branches as .reg
│   ├── startup_control.py    ← Autostart list + enable/disable (StartupApproved flags)
│   ├── restore_point.py      ← System Restore Point creator
│   ├── tweak_runner.py       ← PowerShell executor (hidden)
│   ├── tweak_verifier.py     ← Registry verification (100% coverage)
│   ├── tweak_presets.py      ← 10 built-in presets
│   ├── tweak_i18n.py         ← Multilingual tweak descriptions (EN/DE)
│   ├── bios_guide.py         ← BIOS recommendations database
│   ├── bios_detector.py      ← Live BIOS state detection
│   ├── game_monitor.py       ← Per-game profile monitor (psutil, thread-safe)
│   ├── cpu_topology.py       ← CPU topology (CCDs, P/E cores, X3D cache die)
│   ├── cpu_pinning.py        ← Per-game CPU pinning via CPU Sets API
│   ├── fps_capture.py        ← FPS/frametime metrics (PresentMon + CSV)
│   ├── health_report.py      ← 30-day Windows event/health report
│   ├── remnant_detector.py   ← leftover tweak-tool detection
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
    ├── tab_diagnose.py       ← FPS capture + health report + remnant scan
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
