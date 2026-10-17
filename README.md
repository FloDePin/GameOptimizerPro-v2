<div align="center">

# ⚡ GameOptimizerPro v2.0

**A Windows gaming optimizer with a GPU auto-tuner that measures your card's V/F curve point by point — plus 109 reversible Windows tweaks, game profiles, a BIOS guide and stress tests.**

[![Version](https://img.shields.io/badge/version-2.0%20%C2%B7%20build%2039-d9480f?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)
[![CI](https://github.com/FloDePin/GameOptimizerPro-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/FloDePin/GameOptimizerPro-v2/actions/workflows/ci.yml)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=flat-square&logo=windows)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-2da44e?style=flat-square)](LICENSE)

🇬🇧 **English** | 🇩🇪 [Deutsch](README.de.md)

<img src="docs/img/compare.png" alt="Profile comparison: four tuned profiles against stock, performance and efficiency bars" width="860">

</div>

## What it does

| | |
|---|---|
| 🎮 **GPU auto-tuner** | Measures every voltage point on its own and builds its own V/F curve — goals *Max performance*, *Balanced*, *Efficiency*. Plus a quick mode (offset + power limit). |
| ✅ **Tested, not guessed** | Only what passed FurMark, a compute check and a game test with load changes is saved. A watchdog records clock and voltage while the app runs, sees an in-game GPU hang within seconds and makes only the curve points involved safer — the next tune keeps extra margin there. |
| 📊 **Profile comparison** | Every profile against stock in the same benchmark: points, watts, points per watt — and the V/F curves in a chart. |
| 🛠 **109 Windows tweaks** | Live-verified (● active · ◑ applied · ○ inactive), presets from *Minimal* to *Hard*, a registry backup before every change, *Revert all*. |
| 🎯 **Game profiles** | Per game `.exe`: a higher CPU and disk priority, optionally no fullscreen optimizations — Windows applies it at every start, no background process. While the game runs, the status shows the priority it really got. |
| 🖥 **BIOS guide** | 16 platforms (Intel 8th gen / Ryzen 1000 and newer) with menu paths for ASUS, MSI, Gigabyte and ASRock; live status only where Windows really knows it. |
| 🩺 **Stress test & diagnosis** | Internal stress test, FurMark 1/2 and 3DMark with recording, a 30-day health report, an interrupt view (MSI or line interrupt per device), services and startup managers, cleaner, dashboard. |

<p align="center"><img src="docs/img/gpu-tuner.png" alt="GPU tuner: All-round mode with goal and parameters" width="49%"> <img src="docs/img/optimizer.png" alt="Optimizer presets from Minimal to Hard" width="49%"></p>

## Install in 5 steps

1. Install **Python 3.10+** from [python.org](https://python.org/downloads) and tick **"Add Python to PATH"**.
2. Click **Code → Download ZIP** above and extract it to a folder of its own, e.g. `C:\Tools\GameOptimizerPro`.
3. Double-click **`install.bat`** and answer **J** (yes) to the GPU load question (`cupy`, about 1–2 GB, no CUDA toolkit needed).
4. For the GPU tuner: install [MSI Afterburner](https://www.msi.com/Landing/afterburner/graphics-cards) and set it up (below). Recommended: put [FurMark 2](https://geeks3d.com/furmark/) into a folder `FurMark_win64` next to the app — the tuner compares with its benchmark.
5. Start **`GameOptimizerPro.bat`** and allow the Windows prompt. From then on the app updates itself (*Settings → Check for updates*).

<details>
<summary><b>Setting up MSI Afterburner</b> (once, about 2 minutes)</summary>

1. Afterburner → Settings → **General**: tick **"Unlock voltage control"** and **"Unlock voltage monitoring"** (recommended: **"Start with Windows"**, **"Start minimized"**)
2. Settings → **Monitoring**: enable the **GPU voltage** and **Power** graphs
3. Without changing anything click **Save**, then **slot 1** — that creates the card's profile file, and slot 1 keeps your stock settings. GameOptimizerPro writes into slots 2–5.
4. Leave Afterburner running in the tray. *Settings → Afterburner setup* in the app checks all of it.
</details>

## GPU tuner: which mode?

| Mode | Time | For |
|---|---|---|
| **All-round · Balanced** | 60–95 min | performance **and** efficiency above stock — the recommendation |
| **All-round · Max performance** | 60–95 min | the highest score |
| **All-round · Efficiency** | 60–95 min | stock performance (≥ 99 %) at the least power — cooler, quieter |
| **Quick (OC + UV)** | 20–45 min | one clock offset and a power limit, no own curve |

**What it did on a test card** (FurMark 2, 60 s each; stock = the mean of ten stock runs):

| Profile | Points | Watts | Performance | Efficiency |
|---|---:|---:|---:|---:|
| Stock (mean) | 7278 | 256 | — | — |
| All-round · Efficiency | 7207 | 215 | ▼ −1.0 % | ▲ +17.9 % |
| All-round · Balanced | 7491 | 257 | ▲ +2.9 % | ▲ +2.5 % |
| All-round · Max performance | 7551 | 260 | ▲ +3.7 % | ▲ +2.1 % |
| Quick (OC + UV) | 7524 | 265 | ▲ +3.4 % | ≈ −0.2 % |

Every card differs — the profile comparison in the app shows yours.

## Safety

- No BIOS or driver changes — the GPU goes through MSI Afterburner and NVML; the BIOS guide only shows what to set.
- Every tweak can be reverted on its own or all at once; a registry backup runs before every change, a restore point is one click.
- *Abort* puts the GPU back to stock at once; the GPU watchdog reports in-game crashes (also a crash that restarts the PC) and makes the profile safer where it failed.

## FAQ

<details><summary>Does the app have to keep running?</summary>

No. The tweaks and game profiles are Windows settings, and Afterburner loads the GPU profile at start-up ("Apply overclocking at system startup").
</details>
<details><summary>AMD or Intel graphics?</summary>

Tweaks, BIOS guide, stress tests and diagnosis work everywhere; the GPU tuner needs an NVIDIA card (Afterburner's V/F curve + NVML).
</details>
<details><summary>Trouble with anti-cheat?</summary>

The app never touches a game's files or memory; it changes Windows and Afterburner settings only. A game profile just tells Windows which priority to start the game with — some anti-cheat systems reset it, and the status in the app shows that.
</details>

## Requirements

Windows 10 / 11 · Python 3.10+ · admin rights (the launcher asks through UAC) · for the GPU tuner: an NVIDIA card, MSI Afterburner and `cupy` (`install.bat` offers it); FurMark 2 recommended.

## More

- 📖 [All features in detail](docs/FEATURES.md) — including the project structure
- 📜 [Changelog](CHANGELOG.md)
- 🧪 1278 automated checks in 35 test suites (`python tests\run_all_tests.py`), run on every push
- 🤝 Pull requests are welcome — for bigger changes please open an issue first.

<div align="center">

MIT License · made by FloDePin

</div>
