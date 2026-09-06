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

### 🛠 Windows Optimizer
- **71 Tweaks** across Windows, Gaming, Network, Audio categories
- Live status verification — reads actual Registry/Service state (not just JSON)
- 3-state indicators: ● Green (verified active) / ◑ Amber (applied, unverified) / ○ Grey (inactive)
- **Graduated one-click presets — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat)** — cumulative intensity tiers that apply a curated, escalating set of tweaks
- **10 built-in Presets:** the 3 intensity tiers + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, All Safe Tweaks
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

### v2.0 — Final — 2026-09-05
GameOptimizerPro **2.0** is the finalized release: the complete feature set below, hardened over many internal iterations and **two full external code-review rounds** — every verified bug fixed, honestly.

**Highlights**
- 🩺 **Diagnose tab (measure, don't guess):** FPS/frametime capture with **1% & 0.1% lows**, stutters and a measured **CPU-vs-GPU bottleneck** (PresentMon live or CSV); a 30-day **Health Report** from Windows' own logs; and a **Remnant Scan** for other tweak tools' leftovers. All read-only. *(Also fixed a latent bug that hid the Games/Settings tab buttons.)*
- 🎮 **GPU Auto-Tuner** (OC / UV / OC+UV) with automated stability testing, live graph, TDR detection and crash recovery — plus MSI Afterburner (MAHM) integration
- 🛠 **71 verified tweaks** with live status (green/amber/grey), graduated Minimal→Medium→Hard presets and curated Gaming/Privacy/Debloat/Network/Performance/Win11 presets
- 🎮 **Per-Game Profiles + CPU Pinning (CPU Sets)** — steer games to the X3D cache chiplet (AMD) or P-cores (Intel), with anti-cheat & CCD-parking warnings and an honest "no benefit" note on single-chiplet CPUs
- 🖥 **BIOS Guide**, 📊 **Live Dashboard** (GPU + CPU/RAM/Disk + latency test), 🧹 **System Cleaner & Restore Point**, 📋 **Tune History**, 🚀 **Startup Manager**, 🌐 **DE/EN**

**Reliability & honesty (fixes folded into 2.0)**
- Stress-worker dead-man switch on all paths (no orphaned 100% CPU process); thread-safe log/UI; UAC-free autostart via Task Scheduler
- Honest per-tweak reverts (incl. 12 tweaks that were previously one-way) so "Revert All" truly reverts
- DX12 tweak rewritten honestly as "Raise GPU Timeout (TDR Delay)" (the old value was a no-op placebo); Nahimic verifier no longer false-ambers on PCs without Nahimic
- Robust update-checker version parsing, config-driven stability score, absolute state-file path, and assorted topology / MAHM / wmic / encoding edge-case fixes
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
