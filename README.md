<div align="center">

# ⚡ GameOptimizerPro

**Windows & Gaming Optimizer v2.0 by FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

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
- **System-wide audio enhancements** for gaming and productivity
- Low-latency audio configuration
- Automatic driver optimization
- Audio device prioritization for gaming scenarios
- Quality vs. performance presets
- Real-time audio latency monitoring

### 🛠 Windows Optimizer
- **50 Tweaks** across Windows, Gaming, Network categories
- Live status verification — reads actual Registry/Service state (not just JSON)
- 3-state indicators: ● Green (verified active) / ◑ Amber (applied, unverified) / ○ Grey (inactive)
- **7 built-in Presets:** Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, All Safe Tweaks
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

> The launcher uses VBScript to start Python invisibly and requests Administrator rights via UAC. No CMD window will appear.

---

## 🚀 First Steps

1. Open **[WIN] Optimizer** → click **"⟳ Check Status"** to see which tweaks are already active
2. Apply the **🎮 Gaming Preset** for a quick all-in-one optimization
3. Check **[AUDIO] Audio Optimizer** — configure audio settings for your use case
4. Check **[BIOS] BIOS Guide** — it detects your hardware and shows what to change
5. If you have Afterburner running, try the **[GPU] GPU Tuner** → Start Tune (OC+UV recommended)

---

## 🗂 Project Structure

```
GameOptimizerPro/
├── GameOptimizerPro.py       ← Main entry point
├── GameOptimizerPro.bat      ← Launcher (VBScript, hidden, UAC)
├── install.bat               ← Dependency installer
├── _stress_worker.py         ← GPU stress test subprocess
├── core/
│   ├── nvtune_core.py        ← GPU monitor (NVML + MAHM), Afterburner controller
│   ├── nvtune_tuner.py       ← Auto-tuner (Stage 1 OC, Stage 2 UV, TDR detection)
│   ├── audio_optimizer.py    ← Audio system optimization
│   ├── hardware.py           ← WMI hardware detection
│   ├── tweaks.py             ← 50 tweaks database
│   ├── tweak_runner.py       ← PowerShell executor (hidden)
│   ├── tweak_verifier.py     ← Registry verification (100% coverage)
│   ├── tweak_presets.py      ← 7 built-in presets
│   ├── bios_guide.py         ← BIOS recommendations database
│   ├── bios_detector.py      ← Live BIOS state detection
│   ├── game_monitor.py       ← Per-game profile monitor (psutil)
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
    ├── tab_optimizer.py      ← Windows optimizer with sidebar
    ├── tab_audio.py          ← Audio optimizer UI
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
Thread 6      → Game process monitor (3s interval, psutil)
Thread 7      → Temperature monitor (10s interval)
Thread 8      → Audio optimization monitor
Thread 9+     → Auto-tune stages, stress worker subprocess
```

Cross-thread communication uses `widget.after(0, callback)` — the only safe way to update tkinter from background threads.

---

## 🛡 Safety

- **No BIOS writes** — BIOS Guide is read-only recommendations only
- **No driver modifications** — works through MSI Afterburner and official NVML
- **Registry tweaks are reversible** — "Revert All" restores defaults
- **Crash recovery** — TDR detection automatically resets GPU to safe settings
- **Admin rights** are requested via UAC, not baked in
- **Audio optimizations are reversible** — all changes can be undone

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
