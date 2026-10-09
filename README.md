<div align="center">

# ⚡ GameOptimizerPro v2.0

**Windows & Gaming Optimizer v2.0 by FloDePin**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.0-red?style=flat-square)](https://github.com/FloDePin/GameOptimizerPro-v2/releases)

🇬🇧 **English** | 🇩🇪 [Deutsch](README.de.md)

*All-in-one PC optimization tool — GPU Auto-Tuner, Audio Optimization, Windows Tweaks, BIOS Guide and more.*

</div>

---

## ✨ Features

### 🖥 Interface
- **Modern dark UI built with CustomTkinter** — sidebar navigation with icons, rounded cards, dark title bar
- **Adapts to the window width** — texts wrap, card grids reflow between 1 and 4 columns (preset list, BIOS guide, dashboard); nothing is cut off at fixed widths any more
- The GPU tuner's **log is visible at every window size**; sub-pages switch with segmented bars (the mouse wheel no longer flips tabs by accident)
- Remembers window size and position; **Ctrl+1 … Ctrl+9** jump to the pages; pages are built on first use and hidden pages don't poll sensors
- The optimizer list has a **search box**; rows highlight under the pointer and the whole row toggles

### 🎮 GPU Auto-Tuner
- **2 Tune Modes:** **All-round** (the default, below) and **Quick (OC + UV)**. The former "Overclock" / "Undervolt" modes are covered by the All-round goals *Max performance* / *Efficiency* — per voltage point instead of one offset for the whole curve, and as a real undervolt instead of a lower power limit
- **Any result into any Afterburner slot:** right click a run in the tune history (or a profile, or its "To Afterburner slot … ▾" button) → slot 1–5. The menu shows what each slot holds now ("curve · memory +1000 · power 100 %", "empty"), asks before overwriting it, slot 1 is marked as your own; Afterburner restarts briefly and applies it. Profiles can be **renamed** (button or right click — the tune history still finds them under their old name)
- **Quick (OC + UV, 20–45 min) — how it searches:** raises the core offset step by step (e.g. +15 MHz); on a failure it returns to the **last stable value and halves the step** (15 → 7 → 5 MHz), so it converges on the edge of stability with ±5 MHz precision. The power limit goes down to the **lowest value that costs at most 3 % performance** under full load. Then **60 MHz come off the offset found** (a uniform offset also moves the top of the curve, where games boost). A 2-minute final test plus the **game test** (below) verify the exact profile that is saved.
- **All-round mode (new, the most thorough — 50–80 min)** — inspired by Yuri "1usmus" Bubliy's HYDRA: instead of one offset for the whole curve, **every voltage point is measured on its own** (every 25 mV — 50 mV is selectable and faster — from the highest voltage the card reaches down to 850 mV; points below the card's minimum voltage under load are skipped after one test; the curve is flattened at the point, a light boost load keeps the card exactly on it, every result is checked; +15 MHz until a failure, then halved down to 5 MHz; "Core max" is only an upper bound per point here, 100 MHz above the classic modes' limit). From the points the tuner builds **its own V/F curve** (**45 MHz safety, 60 MHz at the top points** where games boost, +30 where the driver had to restart or the GPU hung), checks it under FurMark, overclocks the memory with **the whole card under load** (FurMark and verified memory copies at the same time: +500 → +1000 in 100-MHz steps on an RTX 40, 100 MHz safety if a step failed), then **benchmarks curve caps every 25 mV with FurMark 2** and picks by your **goal**:
  - **Max performance** — the highest score (equal within the noise: the more frugal setting; a higher power limit only if the card ran into it at stock)
  - **Balanced** — at least half of the measured gain, of those the most points per watt
  - **Efficiency (undervolt)** — stock performance (≥ 99 %) at the lowest power draw

  Final test: **5 minutes of FurMark plus 2 minutes of compute-checked load, then the game test**; on a failure one targeted step back (only the points around the voltage where the card failed, or memory −100 MHz) and again. A crashed benchmark candidate steps back and re-measures all candidates; a benchmark that ends far too early or far below stock (a driver that isn't clean after a crash) stops the tune and says "restart the PC". At the end a **report** (log, text file, "Report" button): every point found → used, every candidate with points/W, a fair **before → after** with the same benchmark, recommendations. Without a saved profile the search starts at a **cautious value for the card's generation**. *Live on an RTX 4080 (round 13, 50-mV points): FurMark 7269 → 7538 points (+3.7 %), average clock 2790 → 2880 MHz, curve 1075 mV → 2940 MHz … 925 mV → 2560 MHz, memory +1000, final test passed. Round 15 (points every 25 mV, max clock gain +350 per point): 7415 → 7542 points (+1.7 % — the stock run was 2 % higher than the day before; the tuned result is the same, 7542 vs 7538), 2790 → 2880 MHz, 925 mV now 2576 MHz (was capped at 2560), 900–850 mV skipped (the card runs ≥ 925 mV under this load), memory +1000, final test passed.*
- **Memory overclock ("Speicher mit übertakten", on by default in both modes):** the same stage as in the All-round mode — after core and power limit the memory offset starts at a cautious value per card generation (+500 on an RTX 40) and goes up in 100-MHz steps to "Mem Max" (+1000 on an RTX 40), every step with **the whole card under load** (FurMark 2 and the stress worker's verified memory copies at the same time, so errors show at once). Used: **the highest step that passed minus 200 MHz**; if the bandwidth drops although the clock rises, the memory is already retrying bad transfers (EDC) — that counts as the edge; a failed final test takes memory back by 100 MHz. **The check can't starve:** Windows gives the window in front priority on the GPU — measured live: with FurMark in front the verified copies fell from 244 to 13 GB/s, i.e. one compare every ~8 s. So the tuner starts FurMark without the focus, the copies are compared at least twice a second, and a step whose check got too little GPU time is repeated once and never raises the memory. Adds about 6–10 minutes. (Until round 13 this stage took the bandwidth peak of a memory-only load — in the live run that was +1500 MHz and gave green speckles in FurMark.)
- **Game-like load for the OC search:** a constant full load keeps the card at its power limit (~2500 MHz), but games crash at the *boost* point. The OC steps and the final test alternate heavy load with half-duty load that reaches the high-clock / high-voltage point games use (measured on an RTX 4080: 2790 MHz @ 1075 mV, the point where games boost)
- **Instability is detected by wrong results, not only by crashes** — the stress worker repeats the same matrix product and compares every result with the first one (the gpu-burn / OCCT method); a single wrong value fails the step. Running into the power limit is treated as normal; only thermal / hardware slowdowns count as a limit
- Automated step-by-step stability testing with stress worker — **refuses to tune without real GPU load** (measured during the baseline; ≥ 70 %), because an OC/UV test on an idle GPU would store unstable values as "stable". GPU load comes from the stress worker via `cupy` (`pip install "cupy-cuda12x[ctk]"` — `install.bat` offers it) or from FurMark running in parallel
- **A failed final test is not the end:** the tuner takes one step back (core, then a memory offset, or the power limit for heat) and tests again — only a configuration that passed the final test is ever saved. The PC is kept awake while a tune or stress test runs
- **Abort really stops**: the running stress step ends immediately, the GPU goes back to stock (offsets 0, factory power limit) and nothing is applied afterwards; exiting the app or switching the language during a tune does the same
- **Game test after the final test (both modes)** — what a game does that steady tests don't: 1 min cool-down with the settings applied (a cold card runs its curve higher), 5 min of **load changes at the top clock** (bursts of random length with short pauses — where the supply voltage dips), 4 min at the boost point. Every result checked; a failure steps back and runs the final test again. *(A game can hang — D3D12 "device hung" — on a profile that passed every steady test; this catches more of that.)*
- **Hang detection:** a test load that stops delivering results for 8 s fails as "GPU hangs" (it used to count as passed until a driver reset killed it)
- **GPU watchdog:** at every app start, GPU hang / driver reset events since the applied profile was set (own tunes and stress tests left out) → "make safer", "stock" or "keep"
- **Make safer** (profiles: button or right click): a copy with the curve / core −30 MHz and memory −200 MHz, then the slot menu to apply it. Applying a profile that has such a safer copy asks first ("use the safer one?")
- **One instance at a time:** "close to tray" only hides the window — a second start now brings the running app to the front instead of starting a second copy next to it
- **What the PC boots with:** Afterburner applies its own boot entry at every Windows start (with "Apply
  overclocking at system startup" on). The app now sets it to the profile you apply; while a tune tests
  steps it holds the profile you had before (never a step under test), at the end the saved profile.
  After applying, the GPU tab says whether Afterburner also loads the profile at Windows start
- TDR (GPU driver timeout) detection via Windows Event Log — every second of a test step is looked at, up to its last one (a reset in a step's last seconds used to be blamed on the next step)
- Crash Recovery — automatically restores last stable profile on next boot
- Live Voltage/Clock/Temp graph during tuning
- Integrates with **MSI Afterburner** (MAHM Shared Memory for real mV readings — parser follows Afterburner's documented layout; reconnects automatically when Afterburner is started later; a monitoring section that stops updating — e.g. after Afterburner was killed — is detected within 8 s and dropped instead of showing frozen values; GPU values come from NVML first)
- GPU generation auto-detection (Pascal → Blackwell / RTX 50) with **cautious start values and limits per generation**. AMD (RX 5000–9000) and Intel Arc are recognised but **not supported** by the tuner (it needs Afterburner's NVIDIA V/F curve and NVML) — the GPU tab says so and points to AMD Adrenalin's / Intel Graphics Software's own auto tuning instead of failing
- **Applies profiles through MSI Afterburner's real per-GPU profile** (`Profiles\VEN_…cfg`, picked by the card's PCI ID): core/memory offset, power limit and a real flat V/F curve for the undervolt. Afterburner only reads that file at start-up, so it is **restarted briefly** (minimized) when new values are applied; identical values are just re-sent. The original file is backed up once per session. *Status: verified live on an RTX 4080 with Afterburner 4.6.6 — a profile written by the app was applied by Afterburner (power limit read back via NVML), identical values were re-applied without a restart, reset to stock worked and the original file came back byte-exact. Complete end-to-end tunes on real hardware: OC + UV (round 10) and the All-round tuner (round 13, see above).* Fan settings stay in Afterburner.

### ⚡ Stress Test
- **Internal stability test** — built-in GPU/CPU stress worker with configurable duration and a **max-temp auto-abort**; includes a dead-man switch so it never leaves an orphaned 100%-CPU process behind. Fails on **wrong results (computation errors)**, a **worker crash or a TDR**, reports the **average GPU load**, and says plainly "no GPU stress" instead of "passed" when the GPU wasn't loaded (no `cupy`); a stopped test reports no result
- **FurMark 1 and FurMark 2** — detected next to the app, in the usual install folders or where you point it (remembered after a restart), shown with version; FurMark 2 gets its own command line (`--demo … --max-time …`) with a **demo choice** (OpenGL / Vulkan, Knot), resolution incl. your native one and duration. **8x MSAA by default**: with an FPS limit or the driver's forced VSync/G-SYNC (a normal gaming setup) FurMark otherwise renders at the cap and loads the GPU only ~45 % — the app reads FurMark's own FPS/load and says so
- **3DMark** — found in every Steam library (or a standalone install), started through Steam; you pick the test in 3DMark (command-line stress tests exist only in the Professional Edition)
- **Recording while FurMark / 3DMark runs** — peak temperature, average and minimum clock under load, maximum power and **driver resets (TDR)**, with a summary at the end ("no driver reset" / "not stable!")

### 🔊 Audio Optimization
- **Low-latency audio tweaks** for gaming — disable audio enhancements, exclusive audio lock. Windows 11 (26H2) locks these endpoint settings in the registry even for administrators, so both tweaks go through the **Windows audio API** (IPolicyConfig, like the Sound control panel) and read the value back
- **System sound optimization** — disable Nahimic service, disable Windows sound scheme
- **Audio CPU Priority** — MMCSS Pro Audio priority maximization for distortion-free audio under load
- **Audio Ducking Control** — prevent Discord/music from being muted by games
- **Windows Audio Enhancement Removal** — reduces audio latency and CPU overhead
- All audio tweaks integrated into **Windows Optimizer** for easy on/off control
- Full verification & revert support for all audio tweaks

### 📊 Live Dashboard
- Real-time **GPU telemetry** (voltage, temp, clocks, power, load) + gauge bars
- **CPU / RAM / Disk usage** tiles alongside the GPU stats (via psutil)
- **Optimization Score** — the share of *safe*, applicable tweaks that the verifier finds really active right now (moderate/advanced tweaks don't count, so the score never pushes you towards risky ones)
- **Monitor advisor** — warns when a display runs below the highest refresh rate its driver offers at the current resolution (e.g. 50 Hz instead of 60 Hz, 60 instead of 144/165 Hz)
- **Network Latency Test** — one-click ping to your gateway + Cloudflare (1.1.1.1) & Google (8.8.8.8) with average/min/max latency, jitter and packet loss

### 🧹 System Cleaner & Safety
- Always: temp/dump folders (user `%TEMP%`, `Windows\Temp`, `CrashDumps`) — only files older than 24 hours, so running programs keep their fresh temp files
- **Deep Clean (opt-in, each target separately):** browser *caches* (Chrome, Edge, Firefox), Windows Update download cache, thumbnails, prefetch, system logs & error reports, and the Recycle Bin (extra confirmation)
- **Never** touches documents or browser profiles (passwords, history, bookmarks, cookies); skips files in use and only counts what was really deleted
- Scan first to see how much can be freed per group, then clean with one click
- **Create Restore Point** — one-click Windows System Restore Point as a safety net before applying tweaks
- **Registry Backup** — exports every registry branch the tweaks can touch as `.reg` files (double-click to restore). Runs **automatically before every Apply Selected, preset, Revert All and "fix deviations"**, plus on demand; keeps the 10 newest backups and prunes older ones so it can't fill your disk

### 🛠 Windows Optimizer
- **107 Tweaks** across Windows, Gaming, Network, Audio categories (incl. AMD GPU tweaks)
- **Windows 11 24H2/26H2 AI & bloat:** Recall (policy + component removal), Click to Do, Paint AI (Cocreator, Image Creator, generative fill/erase), Notepad AI, on-device text/image generation, the AI host service (`WSAIFabricSvc`), and removal of the Microsoft 365 Copilot app / Dev Home that feature updates re-install — using Microsoft's documented policies where they exist
- **Storage & RAM:** long paths, reserved storage, pagefile, memory compression, SSD TRIM, scheduled defrag, NVMe queue depth (only offered with an NVMe drive), write-cache buffer flushing (advanced), plus a one-time **safe Disk Cleanup** (no Downloads, no Recycle Bin, no Windows.old)
- **Drift check at start:** tweaks you applied that a Windows update has reset are listed with one tick box each — ticked ones are re-applied (after a registry backup), unticked ones are no longer tracked; "later" asks again next time
- **Either-or choices:** only one power plan and one DNS provider can be selected ("⇄ entweder-oder"); ticking one unticks the other, and the high-performance plans never turn the screen off or go to sleep on mains power
- **One batch at a time** with visible progress for long tweaks (Disk Cleanup takes minutes); mouse wheel works over the whole list
- Live status verification — reads actual Registry/Service state (not just JSON)
- 3-state indicators: ● Green (verified active) / ◑ Amber (applied, unverified) / ○ Grey (inactive)
- **Graduated one-click presets — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat)** — cumulative intensity tiers that apply a curated, escalating set of tweaks
- **10 built-in Presets:** the 3 intensity tiers + Gaming, Privacy & Anti-Telemetry, Debloat, Network, Performance, Windows 11 Classic, All Safe Tweaks
- **AMD GPU tweaks** — disable ULPS, unlimited shader cache, Anti-Lag (low-latency mode); shown for AMD systems and honestly reported as inactive on NVIDIA. GPU-vendor tweaks (AMD and NVIDIA) are **hardware-guarded twice**: presets skip them on the wrong GPU, and the command itself refuses to run without a matching adapter — AMD values only ever go into the AMD adapter's driver key
- **Power Plan tweaks write to *every* power scheme** — Windows can activate a different plan after a reboot, which would otherwise make a setting look reverted. Plan GUIDs are read from `powercfg /L`, never the localized plan name, so it works in any language
- Export / Import settings as `.nextune` files
- Tooltips (hover `?`) on every single tweak

### 🖥 BIOS Guide
- **Every desktop platform since Intel 8th gen / Ryzen 1000** — 16 platforms: Ryzen 9000X3D / 9000 / 7000X3D / 7000 / 8000G (AM5), Ryzen 5000X3D / 5000 / APUs / 3000 / 1000–2000 (AM4), Core Ultra 200S, Core 12th / 13th–14th gen, 10th–11th gen, 8th–9th gen, plus the basics for anything else (laptops, workstations)
- The hardware detection only **pre-selects** your platform and your board maker (ASUS / MSI / Gigabyte / ASRock) — every platform can be opened
- Each setting with the **menu path for your board maker**, the default, the recommended value, risk and impact — and the things that matter on that platform (EXPO 6000 + FCLK 2000 on AM5, Curve Optimizer, the 13th/14th-gen microcode 0x12F fix, Intel Default Settings, 200S Boost, X3D core parking, Secure Boot for anti-cheats …)
- **Live status only where Windows really knows it** (green = set, red = still to do, grey = can't tell): RAM profile (configured speed vs. the JEDEC ceiling of its DDR type), Resizable BAR (NVIDIA's BAR1 aperture from the driver), Secure Boot and CSM (UEFI state). The old guesses (ReBAR from HAGS, XMP from "> 3200 MHz", PBO from the max clock) are gone

### 🩺 Diagnose
- **Health Report** — read-only summary of what Windows already recorded in the last 30 days: WHEA hardware errors, bluescreens, unexpected shutdowns, GPU driver timeouts (TDR), disk errors, app crashes — with severity and last occurrence
- **Remnant Scan** — read-only detection of leftovers from *other* tweak tools (WinRing0 / inpout drivers, ISLC, TimerResolution autostarts, third-party power plans, Razer Cortex). Reports only — removes nothing

### 📊 Profile Compare
- Compare up to **4 saved GPU profiles side-by-side** by what they do **against stock in the same benchmark**: performance (points vs stock) and efficiency (points per watt vs stock), the best marked — plus clock (an own curve's top point or the offset), memory, power limit, power draw in the test, mode and date. Both tune modes measure it (60 s of FurMark 2 at stock and with the result)

### 📋 Tune History (GPU Tuner → History)
- Every Auto-Tune run (date, mode, core and memory offset, power, voltage, temperature, result); stock values are shown as such (+0 MHz, 100 %)
- Runs without a profile show the values tested last and **why** (final test failed, stopped, driver reset …)
- Click a run to view its log; **right click: its profile into an Afterburner slot** (1–5, with what each slot holds now); **delete** selected runs or the whole history (log + All-round report; saved GPU profiles stay)

### 🌡 Temperature Warning
- Windows Toast Notification when GPU hits 90°C
- 5-minute cooldown between warnings, configurable limit

### 🔄 Updates from GitHub
- **Settings → "Check for updates at start-up"** (on by default) and **"Check for updates now"**
- A release is identified by the build number in `build.json`. A newer one is downloaded in the background, checked and installed after a short question ("restart now?" — "no" installs it at the next start; never during a tune): `tools/apply_update.py` waits until the app has exited, **backs up every replaced file** (`logs/update_backup_<build>/`), copies the new files, puts the old state back if anything fails, and starts the app again. `logs/` and `profiles/` are never touched
- A git checkout is updated with `git pull --ff-only` (only without local changes)

### 🌐 Language Support
- **English** (default) and **German** — toggle with `EN/DE` button in the title bar
- Instant switch, no restart required

### 🔽 System Tray
- Closing the window keeps the app in the tray (Settings → "Keep running in the tray when closed" — off: the X quits); the tray tooltip shows **live GPU temp / clock / voltage / power**
- **The app doesn't have to run after tweaking / tuning:** the tweaks are Windows settings, the GPU profile is in Afterburner — enable Afterburner's "Start with Windows" and "Apply overclocking at system startup" (Settings → Afterburner setup checks both). While the app is closed there is no 90 °C warning and no tray menu
- Quick-apply any saved GPU profile, reset the GPU to stock, or open/exit — all from the tray menu

### ⚙ Services Manager
- Page in the sidebar with 29 rarely needed Windows services (telemetry, Xbox, fax, maps, Hyper-V, the 24H2/26H2 AI host, …) — live status, start type, category and a safe/caution rating
- **Disable remembers the original start type** (incl. "Automatic (delayed)"), **Enable restores it** (or the Windows default) — not just "Manual"
- Extra confirmation for services that switch off a function (print spooler, Windows Update, BITS, the Xbox services Game Pass games need); view-only without admin rights; links to `services.msc`

### 🚀 Startup Manager
- Page in the sidebar listing all autostart entries — the **Run keys (HKCU, HKLM, HKLM 32-bit) and both Startup folders** (per-user and all-users `.lnk` shortcuts, targets resolved)
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
| **customtkinter** | Installed by `install.bat` (`requirements.txt`); if it is missing after an update, the app offers to install it at start |
| **GPU** | NVIDIA (full support) or AMD (tweaks + BIOS guide) |
| **MSI Afterburner** | Optional — required for voltage readings (mV) and OC profiles (applying a profile restarts it briefly) |
| **cupy** | Optional — `pip install "cupy-cuda12x[ctk]"` (no CUDA Toolkit needed; `install.bat` asks) gives the stress worker real **GPU** load plus error and bandwidth checks (NVIDIA). Without it (or FurMark in parallel) the Auto-Tuner refuses to run |
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
Double-click `install.bat` — it installs everything automatically and then offers `cupy` (GPU load for the Auto-Tuner, answer **J**):
```
pystray, Pillow, nvidia-ml-py, numpy, wmi, psutil
```

### 4. (Optional) Set up MSI Afterburner
For voltage readings and GPU overclocking:
1. Download and install [MSI Afterburner](https://www.msi.com/Landing/afterburner/graphics-cards)
2. Open Afterburner → Settings → **General** → check **"Unlock voltage control"**
3. Settings → **General** → check **"Unlock voltage monitoring"** (and, recommended, **"Start minimized"**)
4. Settings → **Monitoring** → enable the **GPU voltage** and **Power** graphs
5. Without changing anything, click **Save** and then **slot 1** — this creates the card's profile file (`Profiles\VEN_…cfg`) with its V/F curve, and slot 1 keeps your stock settings. GameOptimizerPro writes into **slot 2** (changeable in the GPU tab)
6. Leave Afterburner running in the system tray
7. Check it: `python tools\ab_selftest.py info` (read-only)

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
- 🛠 **83 verified tweaks** (106 today — see below) with live status (green/amber/grey), graduated Minimal→Medium→Hard presets and curated Gaming/Privacy/Debloat/Network/Performance/Win11 presets
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

**Since the release (still 2.0)**
- 🧠 **Memory overclock in the Auto-Tune** — searched step by step with the whole card under load (replaces the fixed "Mem Offset" field)
- 🎮 **Afterburner profiles verified live** on real hardware; a real bug found that way — frozen monitoring after an Afterburner restart — is fixed; OC steps now run a **game-like mixed load**
- 🔁 **v1 parity completed honestly** — an audit showed the earlier "full parity" claim was wrong: 18 more tweaks, **Deep Clean**, **Services Manager**, **Optimization Score**, **monitor advisor** and the **drift check** are ported; 6 v1 tweaks are deliberately left out (no effect on current drivers/Windows)
- 🪟 **Windows 11 26H2:** new tweaks against the re-installed Copilot app / Dev Home, Click to Do, Paint/Notepad AI and the new AI host service; Recall and on-device AI now use the official policies
- 🧪 After the first real use: no console window, final-test back-off in the tuner, either-or power plans / DNS, per-tweak drift dialog, several tweaks that reported wrongly fixed — see CHANGELOG, round 10
- 🖥 **New interface (CustomTkinter)** — sidebar, cards that adapt to the window width, tuner log always visible, search in the optimizer; Autostart and Services manager are pages now
- 🔥 **FurMark 1/2 + 3DMark** with recording of temperature, clocks, power and driver resets during the test; FurMark location remembered
- 🔊 **Audio tweaks work on Windows 11 26H2** — through the Windows audio API instead of locked registry keys
- 🎯 **All-round tuner** — own V/F curve measured point by point every 25 mV (HYDRA-style), memory tested with the whole card under load (now in every mode), goal switch Max / Balanced / Efficiency, 5-min FurMark final test and a before/after report, live values through the whole tune; GPU table with RTX 50 and cautious start values; AMD/Intel get a clear "not supported"
- ❓ **Clear tuner settings:** every field of the GPU tuner has a self-explaining name (e.g. "Max clock gain per point", "Test time per step", "Spacing of measured points", "Safety margin") and a **"?"** that explains it (German / English); the All-round mode shows **how the tune runs, step by step, with the current values**
- 🧹 **Round 14 — leaner:** per-game profiles, CPU pinning and the FPS capture removed (the background process watcher with them); the tune history moved into the GPU tuner; page switches **2–3× faster** (pages stay stacked and are built in the background); a **BIOS guide for every platform** with menu paths per board maker and honest live status; **updates from GitHub**; "close to tray" switch; Afterburner setup checks "start with Windows" / "apply at start-up"
- 🎛 **Round 15 — two modes:** All-round (default) and Quick (OC + UV) instead of four; the never-shown FULL / V/F-only / memory-only modes and their code are gone. **Any result into any Afterburner slot** from the history or the profiles (with what each slot holds now). The **AB / NVML / MAHM dots explain themselves** when you point at them (blue MAHM = Afterburner restarts on purpose). **The memory check can't starve any more** — found in the live test: the FurMark window in front got the GPU's priority and the verified copies fell from 244 to 13 GB/s; FurMark now starts without the focus, the copies are compared twice a second, a too-weak check never raises the memory. Driver resets are looked for up to the last second of every step; FurMark is waited for after a stop; the remaining English-only messages of the GPU tuner speak German too; the Nagle tweak no longer reports "not active" because of an unused Bluetooth adapter. **Profiles can be renamed**, "Delete" has a frame like the other buttons, the **profile comparison is current every time it opens** (a tune finished after the start was missing), and the lists show **only real profiles** (language.json and the old game_profiles.json in the profiles folder showed up as a profile called "Default")
- 🛡 **Round 16 — tests that find what a game finds:** because a game can hang (D3D12 "device hung") on a profile that passed every steady test — a game test after every final test (cool-down, load changes at the top clock, boost point), hang detection, bigger margins (45 / 60 at the top; Quick −60), memory −200 with an EDC check, a GPU watchdog at app start, "make safer" in one click, and every applied profile is recorded (the app used to put an older one back at its next start)
- 🧪 1056 automated checks in 28 test suites (in `tests/`), incl. a PowerShell parse check of every command, the whole UI under a real main loop (on a hidden desktop, so it can run while you game), the All-round tuner against a simulated card and the updater against temporary folders

See [CHANGELOG.md](CHANGELOG.md) for the full detail.

## 🚀 First Steps

1. Open **Optimizer** in the sidebar → **"Check status"** shows which tweaks are already active (● verified, ◑ applied but not confirmed, ○ inactive)
2. Apply the **🎮 Gaming Preset** for a quick all-in-one optimization
3. Find the **Audio tweaks** in **Optimizer → Audio** — enable low-latency audio tweaks for gaming
4. Try the **Performance Preset** if you want maximum system performance
5. Check the **BIOS Guide** — it detects your hardware and shows what to change
6. If you have Afterburner running, try the **GPU Tuner** → **All-round**, goal *Balanced* (50–80 min) — or **Quick (OC + UV)** for a 20–45-minute run

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
│   ├── nvtune_tuner.py       ← Auto-tuner: All-round (own V/F curve) + Quick (OC + UV), memory; TDR + error detection
│   ├── curve_tune.py         ← All-round tuner logic: point search, margins, goals, report
│   ├── hardware.py           ← WMI hardware detection
│   ├── tweaks.py             ← 107 tweaks database (Windows, Gaming, Network, Audio)
│   ├── network_test.py       ← Gateway/DNS ping latency test
│   ├── system_cleaner.py     ← Safe temp/junk cleaner + opt-in Deep Clean
│   ├── services.py           ← Services Manager logic (remembers original start types)
│   ├── optimization_score.py ← Optimization Score + drift check
│   ├── display_info.py       ← Monitor refresh-rate advisor
│   ├── app_launch.py         ← Start without a console window (pythonw)
│   ├── power_state.py        ← Keep the PC awake during tune / stress test
│   ├── registry_backup.py    ← Exports affected registry branches as .reg
│   ├── startup_control.py    ← Autostart list + enable/disable (StartupApproved flags)
│   ├── restore_point.py      ← System Restore Point creator
│   ├── tweak_runner.py       ← PowerShell executor (hidden)
│   ├── tweak_verifier.py     ← Registry verification (100% coverage)
│   ├── tweak_presets.py      ← 10 built-in presets
│   ├── tweak_i18n.py         ← Multilingual tweak descriptions (EN/DE)
│   ├── bios_guide.py         ← BIOS guide: 16 platforms, menu paths per board maker
│   ├── bios_detector.py      ← What Windows can tell (RAM profile, ReBAR, Secure Boot, CSM)
│   ├── health_report.py      ← 30-day Windows event/health report
│   ├── remnant_detector.py   ← leftover tweak-tool detection
│   ├── crash_recovery.py     ← TDR detection, crash flag system
│   ├── temp_monitor.py       ← GPU temp toast notifications
│   ├── updater.py            ← Updates from GitHub (build.json, download, git pull)
│   ├── export_import.py      ← .nextune export/import
│   ├── tune_history.py       ← Tune log parser
│   ├── startup_loader.py     ← Autostart + startup profile loader
│   ├── gpu_defaults.py       ← GPU generation defaults table
│   ├── app_settings.py       ← Small persistent settings (logs/settings.json)
│   ├── audio_policy.py       ← Audio endpoint settings via the Windows audio API
│   ├── furmark.py            ← FurMark 1/2 detection + command line
│   ├── threedmark.py         ← 3DMark detection (Steam libraries) + launch
│   ├── mahm_reader.py        ← MSI Afterburner shared memory reader
│   ├── ab_profile.py         ← Afterburner per-GPU profile + V/F curve editor
│   └── i18n.py               ← EN/DE language module
└── ui/
    ├── main_window.py        ← Main window: sidebar, lazy pages, status bar
    ├── theme.py              ← Colours, fonts, icons, CustomTkinter defaults
    ├── components.py         ← Building blocks (cards, wrapping labels, responsive grid, log, tables …)
    ├── tab_dashboard.py      ← System overview + live GPU telemetry
    ├── tab_optimizer.py      ← Windows optimizer with sidebar (includes Audio tweaks)
    ├── tab_gpu.py            ← GPU tuner UI
    ├── tab_stress.py         ← Stress test, FurMark 1/2 + 3DMark, recording during external tests
    ├── tab_compare.py        ← Profile comparison
    ├── tab_bios.py           ← BIOS guide with live detection
    ├── tune_history_view.py  ← Tune history (a view of the GPU tuner)
    ├── update_flow.py        ← Update check / question (start-up + settings)
    ├── tab_diagnose.py       ← Health report + remnant scan
    ├── tab_settings.py       ← Autostart, setup checker, about
    ├── live_graph.py         ← Rolling voltage/clock/temp graph
    ├── startup_manager.py    ← Startup manager page
    ├── services_manager.py   ← Services manager page
    └── drift_dialog.py       ← "Tweaks no longer active" dialog (one tick box per tweak)
tests/                        ← Windows test battery: python tests\run_all_tests.py
tools/
    ├── ab_selftest.py        ← Afterburner self-test (info / dryrun / live / restore)
    └── apply_update.py       ← Installs a downloaded update (backup, rollback, restart)
build.json                    ← Build number of this release (the updater compares it)
```

---

## ⚙️ Architecture

```
Main Thread   → CustomTkinter/tkinter mainloop() — only thread touching the UI
Thread 2      → pystray.run() — system tray icon
Thread 3      → GPU stats loop (4s interval)
Thread 4      → Startup (crash check + profile load)
Thread 5      → Menu refresh (20s interval)
Thread 6      → Game process monitor (3s interval, psutil) — thread-safe with locks
Thread 7      → Temperature monitor (10s interval)
Thread 8+     → Auto-tune stages, stress worker subprocess
```

Cross-thread communication uses `widget.after(0, callback)` or a queue the main thread polls (the log views, `ui.components.run_async`) — Tk must only be touched from the main thread.

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
- **Services keep their history** — the original start type is remembered before a service is disabled

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
