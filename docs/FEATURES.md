# GameOptimizerPro v2.1 — all features

🇬🇧 **English** | 🇩🇪 [Deutsch](FEATURES.de.md) · [← back to the README](../README.md)

Everything the app does, in detail. Results quoted from live runs are from one test card; every card differs.

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
- **All-round mode (new, the most thorough — 50–80 min)** — inspired by Yuri "1usmus" Bubliy's HYDRA: instead of one offset for the whole curve, **every voltage point is measured on its own** (every 25 mV — 50 mV is selectable and faster — from the highest voltage the card reaches down to 850 mV; points below the card's minimum voltage under load are skipped after one test, and that minimum is remembered per card — the next tune plans its points only down to it; the curve is flattened at the point, a light boost load keeps the card exactly on it, every result is checked; +15 MHz until a failure, then halved down to 5 MHz; "Core max" is only an upper bound per point here, 100 MHz above the classic modes' limit). From the points the tuner builds **its own V/F curve** (**45 MHz safety, 60 MHz at the top points** where games boost, +30 where the driver had to restart or the GPU hung), checks it under FurMark, overclocks the memory with **the whole card under load** (FurMark and verified memory copies at the same time: +500 → +1000 in 100-MHz steps on an RTX 40; used: the highest step that passed minus 200 MHz), then **benchmarks curve caps every 25 mV with FurMark 2** (Balanced and Efficiency: plus a fine search halfway to the neighbouring cap) and picks by your **goal**:
  - **Max performance** — the highest score (equal within the noise: the more frugal setting; a higher power limit only if the card ran into it at stock)
  - **Balanced** — performance **and** efficiency above stock, as evenly as possible (the smaller of the two gains counts); if no setting beats stock in both: at least half of the measured gain, of those the most points per watt
  - **Efficiency (undervolt)** — stock performance (≥ 99 %) at the lowest power draw

  Final test: **5 minutes of FurMark plus 2 minutes of compute-checked load, then the game test**; on any failure a targeted step back (the points around the voltage where the card failed; memory −100 MHz only when its own test failed or 3 curve step-backs did not help) and then every final test again — saved is only what passed all of them in one go (up to 12 tries). A crashed benchmark candidate steps back and re-measures all candidates; a benchmark that ends far too early or far below stock (a driver that isn't clean after a crash) stops the tune and says "restart the PC". At the end a **report** (log, text file, "Report" button): every point found → used, every candidate with points/W, a fair **before → after** with the same benchmark, recommendations. Without a saved profile the search starts at a **cautious value for the card's generation**. *Live on a test card (RTX 40 series, round 13, 50-mV points): FurMark 7269 → 7538 points (+3.7 %), average clock 2790 → 2880 MHz, curve 1075 mV → 2940 MHz … 925 mV → 2560 MHz, memory +1000, final test passed. Round 15 (points every 25 mV, max clock gain +350 per point): 7415 → 7542 points (+1.7 % — the stock run was 2 % higher than the day before; the tuned result is the same, 7542 vs 7538), 2790 → 2880 MHz, 925 mV now 2576 MHz (was capped at 2560), 900–850 mV skipped (the card runs ≥ 925 mV under this load), memory +1000, final test passed.*
- **Memory overclock ("Speicher mit übertakten", on by default in both modes):** the same stage as in the All-round mode — after core and power limit the memory offset starts at a cautious value per card generation (+500 on an RTX 40) and goes up in 100-MHz steps to "Mem Max" (+1000 on an RTX 40), every step with **the whole card under load** (FurMark 2 and the stress worker's verified memory copies at the same time, so errors show at once). Used: **the highest step that passed minus 200 MHz**; if the bandwidth drops although the clock rises, the memory is already retrying bad transfers (EDC) — that counts as the edge; a failed final test takes memory back by 100 MHz. **The check can't starve:** Windows gives the window in front priority on the GPU — measured live: with FurMark in front the verified copies fell from 244 to 13 GB/s, i.e. one compare every ~8 s. So the tuner starts FurMark without the focus, the copies are compared at least twice a second, and a step whose check got too little GPU time is repeated once and never raises the memory. Adds about 6–10 minutes. (Until round 13 this stage took the bandwidth peak of a memory-only load — in the live run that was +1500 MHz and gave green speckles in FurMark.)
- **Game-like load for the OC search:** a constant full load keeps the card at its power limit (~2500 MHz), but games crash at the *boost* point. The OC steps and the final test alternate heavy load with half-duty load that reaches the high-clock / high-voltage point games use (measured on the test card: 2790 MHz @ 1075 mV, the point where games boost)
- **Instability is detected by wrong results, not only by crashes** — the stress worker repeats the same matrix product and compares every result with the first one (the gpu-burn / OCCT method); a single wrong value fails the step. Running into the power limit is treated as normal; only thermal / hardware slowdowns count as a limit
- Automated step-by-step stability testing with stress worker — **refuses to tune without real GPU load** (measured during the baseline; ≥ 70 %), because an OC/UV test on an idle GPU would store unstable values as "stable". GPU load comes from the stress worker via `cupy` (`pip install "cupy-cuda12x[ctk]"` — `install.bat` offers it) or from FurMark running in parallel
- **A failed final test is not the end:** the tuner takes one step back (core, then a memory offset, or the power limit for heat) and tests again — only a configuration that passed the final test is ever saved. The PC is kept awake while a tune or stress test runs
- **Abort really stops**: the running stress step ends immediately, the GPU goes back to stock (offsets 0, factory power limit) and nothing is applied afterwards; exiting the app or switching the language during a tune does the same
- **Game test after the final test (both modes)** — what a game does that steady tests don't: 1 min cool-down with the settings applied (a cold card runs its curve higher), 5 min of **load changes at the top clock** (bursts of random length with short pauses — where the supply voltage dips), 4 min at the boost point. Every result checked; a failure steps back and runs the final test again. *(A game can hang — D3D12 "device hung" — on a profile that passed every steady test; this catches more of that.)*
- **Test with the video encoder running (both modes, on by default, no extra time):** every stability step — each curve point, the OC steps, the final and the game test — runs with the encoder load (NVENC, 60 frames/s) next to it; a wrong frame, a stalled encoder or a wrong result fails the step. *Why: a curve found with single loads computed wrong within minutes with the encoder running — from the core curve, not the memory overclock, and never at stock.* The baseline, the power-limit steps and the benchmarks run without it, so the performance numbers stay comparable. Without NVENC the steps run as before
- **Hardness test at the end (both modes, +10 min, on by default):** after the game test, several loads at once — 3D (FurMark), the video encoder (NVENC), compute and memory — like a game that is recorded or streamed (see *Stress Test*). A failure lowers the points around the voltage of the fault by one step (unknown voltage: the whole curve; Quick: the core offset) and runs every final test again, like any other failure. Then, in the All-round mode, the after benchmark — always at the very end, on exactly the profile that is saved
- **Hang detection:** a test load that stops delivering results for 8 s fails as "GPU hangs" (it used to count as passed until a driver reset killed it)
- **GPU watchdog:** at every app start, GPU hang / driver reset events since the applied profile was set (own tunes and stress tests left out) → "make safer", "stock" or "keep"
- **Flight recorder + live watch:** while the app runs (window or tray) clock, voltage, power, temperature and load are recorded once a second (the last minute also on disk, so a crash that restarts the PC leaves it behind), and the event log is read every few seconds. A game's GPU hang gives a Windows notification — no window over the game; the dialog comes when you are back in the app. It names the state just before the hang (e.g. "1050 mV / 2880 MHz") and offers to lower **only the curve points involved** by 30 MHz; if the same points fail again, the whole profile is made safer. An unexpected restart counts only when the card was under load until the recording ended. Where games hung, the next tune adds 30 MHz margin
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
- **Applies profiles through MSI Afterburner's real per-GPU profile** (`Profiles\VEN_…cfg`, picked by the card's PCI ID): core/memory offset, power limit and a real flat V/F curve for the undervolt. Afterburner only reads that file at start-up, so it is **restarted briefly** (minimized) when new values are applied; identical values are just re-sent. The original file is backed up once per session. *Status: verified live on an RTX 40 card with Afterburner 4.6.6 — a profile written by the app was applied by Afterburner (power limit read back via NVML), identical values were re-applied without a restart, reset to stock worked and the original file came back byte-exact. Complete end-to-end tunes on real hardware: OC + UV (round 10) and the All-round tuner (round 13, see above).* Fan settings stay in Afterburner.

### ⚡ Stress Test
- **Hardness test — like gaming while recording / streaming** (10 / 20 / 45 min): several loads at once in combinations that change every 2.5 min — 3D (FurMark: OpenGL / Vulkan, light like a game under an FPS cap and heavy with 8x MSAA), the **video encoder** (NVENC, H.264 at 60 frames/s, every frame drawn and scaled by CUDA first, as OBS does with "GPU scaling"), verified load changes at the top of the curve and verified memory copies. A short idle gap between the phases makes the card clock up from idle with everything starting at once. Every compute result and every converted frame is checked; a load that stops answering is a hung GPU; the System log is read every 2 s. It tests the profile applied now and changes nothing — after a failure it names the phase and the state just before it and offers to lower **only the curve points involved**. *Why: a profile can pass every single-load test and still compute wrong with the encoder running next to it — measured in about one of four 25-s runs, never at stock.* The encoder load uses the driver's own `nvEncodeAPI64.dll` (no extra package); without NVENC the test runs without it. The loads end on request, not by a kill: ending GPU work by force while another program encodes makes the driver log nvlddmkm 153 by itself
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
- **109 Tweaks** across Windows, Gaming, Network, Audio categories (incl. AMD GPU tweaks)
- **Network adapter settings:** Energy-Efficient Ethernet off and Interrupt Moderation off — only on physical wired adapters and only with the keywords the driver itself offers (vendors name them differently); the value found before is kept and put back on revert. No connection drop when applied, effective after a restart
- **Honest timer tweak:** *Let timer requests apply system-wide* (`GlobalTimerResolutionRequests`) brings back the system-wide effect of a program's timer request on Windows 11 — it sets no resolution itself (that needs a running program), and it says so
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
- **Game profiles** (Optimizer → Games): choose a game's `.exe` — Windows then starts it with a *High* or *Above normal* CPU priority and a high disk priority (Image File Execution Options), optionally without fullscreen optimizations for that game only. No background process; Windows applies it at every start. While the game runs, the status shows the priority it really got (some anti-cheat systems reset it). Never *Realtime*; Windows and system programs are refused; removing a profile — or *Revert all* — puts back what was there before

### 🖥 BIOS Guide
- **Every desktop platform since Intel 8th gen / Ryzen 1000** — 16 platforms: Ryzen 9000X3D / 9000 / 7000X3D / 7000 / 8000G (AM5), Ryzen 5000X3D / 5000 / APUs / 3000 / 1000–2000 (AM4), Core Ultra 200S, Core 12th / 13th–14th gen, 10th–11th gen, 8th–9th gen, plus the basics for anything else (laptops, workstations)
- The hardware detection only **pre-selects** your platform and your board maker (ASUS / MSI / Gigabyte / ASRock) — every platform can be opened
- Each setting with the **menu path for your board maker**, the default, the recommended value, risk and impact — and the things that matter on that platform (EXPO 6000 + FCLK 2000 on AM5, Curve Optimizer, the 13th/14th-gen microcode 0x12F fix, Intel Default Settings, 200S Boost, X3D core parking, Secure Boot for anti-cheats …)
- **Live status only where Windows really knows it** (green = set, red = still to do, grey = can't tell): RAM profile (configured speed vs. the JEDEC ceiling of its DDR type), Resizable BAR (NVIDIA's BAR1 aperture from the driver), Secure Boot and CSM (UEFI state). The old guesses (ReBAR from HAGS, XMP from "> 3200 MHz", PBO from the max clock) are gone

### 🩺 Diagnose
- **Health Report** — read-only summary of what Windows already recorded in the last 30 days: WHEA hardware errors, bluescreens, unexpected shutdowns, GPU driver timeouts (TDR), disk errors, app crashes — with severity and last occurrence
- **Remnant Scan** — read-only detection of leftovers from *other* tweak tools (WinRing0 / inpout drivers, ISLC, TimerResolution autostarts, third-party power plans, Razer Cortex). Reports only — removes nothing
- **Interrupts** — per PCI device: MSI or the old line interrupt (read from what Windows really allocated, not just the registry flag), number of messages, interrupt priority and core assignment, shared line interrupts — with a note where it matters (a GPU without MSI points to the MSI tweak; a driver that turns MSI off on purpose is left alone). Read-only

### 📊 Profile Compare
- Compare up to **4 saved GPU profiles side-by-side** by what they do **against stock in the same benchmark**: a **stock column** as point 0, performance (points vs stock) and efficiency (points per watt vs stock) with ▲ / ▼ / ≈ (within the ±0.7 % run-to-run noise), the FurMark points themselves, power draw, memory and mode
- A **V/F curve chart** like Afterburner's curve editor: stock dashed, every profile in its own colour and line style, the measured points as dots, the range the card runs in under load shaded; point at it for the clocks at that voltage
- Both tune modes measure it (60 s of FurMark 2 at stock and with the result; before each comparison run the card cools down to the stock run's starting temperature)

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
- **English** (default) and **German** — toggle with the `EN/DE` button in the sidebar
- The app restarts briefly to rebuild every page in the new language (a running tune is reset to stock first)

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
│   ├── tweaks.py             ← 109 tweaks database (Windows, Gaming, Network, Audio)
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
│   ├── interrupts.py         ← Interrupt view: MSI / line per PCI device (read-only)
│   ├── game_profiles.py      ← Game profiles: CPU / disk priority per .exe, fullscreen flag
│   ├── remnant_detector.py   ← leftover tweak-tool detection
│   ├── crash_recovery.py     ← TDR detection, crash flag system
│   ├── temp_monitor.py       ← GPU temp toast notifications
│   ├── updater.py            ← Updates from GitHub (build.json, download, git pull)
│   ├── export_import.py      ← .nextune export/import
│   ├── tune_history.py       ← Tune log parser
│   ├── profile_score.py      ← Profile scores vs stock (comparison)
│   ├── profile_curves.py     ← V/F curves of the profiles (comparison chart)
│   ├── gpu_watchdog.py       ← GPU hang / reset events since the applied profile, fault point
│   ├── hardness_test.py      ← Hardness test: 3D + encoder + compute / memory at once, in phases
│   ├── nvenc.py              ← NVIDIA video encoder through the driver's nvEncodeAPI64.dll (ctypes)
│   ├── gpu_flight.py         ← Flight recorder + live event watch (while the app runs)
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
    ├── tab_compare.py        ← Profile comparison (vs stock, V/F curve chart)
    ├── tab_bios.py           ← BIOS guide with live detection
    ├── tune_history_view.py  ← Tune history (a view of the GPU tuner)
    ├── update_flow.py        ← Update check / question (start-up + settings)
    ├── tab_diagnose.py       ← Health report + remnant scan + interrupts
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
Thread 5      → Tray menu refresh (60s interval)
Thread 6      → Temperature monitor (10s interval)
Thread 7+     → Auto-tune stages, stress worker subprocess
```

Cross-thread communication uses `widget.after(0, callback)` or a queue the main thread polls (the log views, `ui.components.run_async`) — Tk must only be touched from the main thread.

---
