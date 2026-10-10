# Changelog

All notable changes to GameOptimizerPro are documented here.

---

## [2.0] — Final — 2026-09-05

The finalized GameOptimizerPro **2.0** — an all-in-one Windows & gaming
optimizer, built and hardened over many internal iterations and two full
external code-review rounds. Every feature below ships in 2.0, and every
verified bug from those reviews is fixed.

### ✨ Features

- **Diagnose tab — measure, don't guess.** Three read-only diagnostics:
  - **FPS / Frametime capture** — average FPS, **1% and 0.1% lows**, stutter
    count, and a measured **CPU-vs-GPU bottleneck** (from per-frame GPU-busy
    time). Live via Intel's open-source **PresentMon** (optional, dropped in
    `tools/`) or by analyzing any existing PresentMon / CapFrameX / OCAT CSV —
    the CSV path needs no external binary.
  - **Health Report** — a 30-day summary of what Windows already logged: WHEA
    hardware errors, bluescreens, unexpected shutdowns, GPU driver timeouts
    (TDR), disk errors and app crashes, each with severity + last occurrence.
  - **Remnant Scan** — finds leftovers of *other* tweak tools (WinRing0 / inpout
    drivers, ISLC, TimerResolution autostarts, third-party/duplicate power
    plans, Razer Cortex). Reports only — never removes anything, and never
    flags GameOptimizerPro's own tweaks.
  - Also fixed a **latent UI bug**: the tab bar only rendered its first two rows,
    so the **Games and Settings tab buttons were unreachable** — it now renders
    every tab.
- **GPU Auto-Tuner** — Overclock-only / Undervolt-only / OC+UV modes with an
  automated, step-by-step stability test, live voltage/clock/temp graph, TDR
  (driver-timeout) detection via the Windows Event Log, and crash recovery that
  restores the last stable profile on the next boot. Integrates with **MSI
  Afterburner** (MAHM shared memory for real mV readings); GPU-generation
  auto-detection (Pascal→Ada, RDNA 1–3).
- **Windows Optimizer — 106 tweaks** across Windows, Gaming, Network and Audio
  (incl. the Windows 11 24H2/26H2 AI features and storage/RAM tweaks), each
  with **live status verification** (except the one-time Disk Cleanup) that
  reads the real registry/service state (not just a saved flag), shown as
  ● green (verified) / ◑ amber (applied, unverified) / ○ grey (inactive). A
  **drift check** at start offers to re-apply tweaks a Windows update has reset.
- **Graduated one-click presets** — 🟢 Minimal → 🟡 Medium → 🔴 Hard (Debloat),
  cumulative intensity tiers, plus curated Gaming, Privacy & Anti-Telemetry,
  Debloat, Network, Performance, Windows 11 Classic and All-Safe presets.
- **Per-Game Profiles** — a lightweight background monitor auto-applies a GPU
  profile when a game launches and restores the default on exit.
- **Per-Game CPU Pinning (CPU Sets)** — optionally steer a game (and its child
  processes) onto specific cores: the **X3D cache chiplet** on dual-CCD AMD
  (detected by its larger L3) or the **P-cores / E-cores** on Intel Hybrid.
  Uses the Windows CPU Sets API (`SetProcessDefaultCpuSets`) — a *soft* hint
  that never starves the game — with a `psutil` affinity fallback and readback
  verification. Honest by design: on a single-chiplet CPU (e.g. Ryzen 7
  9800X3D) it says plainly that pinning brings no benefit. Includes anti-cheat
  and CCD-parking (AMD 3D V-Cache optimizer / Game Bar) caveat warnings.
- **BIOS Guide** — hardware-aware recommendations (auto-detects CPU/GPU/board),
  live state detection, exact BIOS menu paths + registry equivalents; covers
  AMD Zen 3/4/5 and Intel 12/13/14th Gen, including a motherboard vendor
  auto-install (bloatware) warning.
- **Live Dashboard** — real-time GPU telemetry + CPU/RAM/Disk tiles, an
  **Optimization Score**, a **monitor refresh-rate advisor** and a one-click
  network latency test (gateway + Cloudflare/Google, jitter & loss).
- **System Cleaner + opt-in Deep Clean & Restore Point**, **Services Manager**,
  **Tune History**, **Temperature Warning** (toast at 90 °C), **Startup
  Manager**, **background Update Checker**, and full **DE/EN** language switching.

### 🔁 v1 parity (ported from GameOptimizerPro v1)

v2 is a Python rewrite of the PowerShell/WPF v1, and a handful of v1 features had
never made it across. The first batch is below; a line-by-line audit later
showed that this was **not** complete yet — the rest followed in round 9 (see
the fixes list). Ported with v1's original commands as the reference:

- **Registry Backup** — exports all **36** registry branches the tweaks can touch
  as `.reg` files to `%LOCALAPPDATA%\GameOptimizerPro\RegistryBackups\`, so any
  change can be undone with a double-click. Runs automatically before every
  Apply Selected / preset (`PreApply`), Revert All (`PreRevert`) and
  "Abweichungen beheben" (`PreFix`), plus on demand from Settings *(as first
  shipped it only hooked methods the UI never called — fixed in round 6)*. **Improvement over v1:** a full export is tens of MB, so only the
  **10 newest** backups are kept — v1 grew without bound.
- **AMD GPU tweaks (3)** — `amd_disable_ulps`, `amd_shader_cache`, `amd_antilag`.
  v2 previously had a `requires_amd` flag that no tweak used; AMD users now get
  the same coverage NVIDIA users had.
- **CTT Essentials (4)** — `prevent_device_companion`,
  `start_menu_previous_layout`, `explorer_folder_discovery`,
  `store_no_recommended`.
- **Network adapter (1)** — `nic_power_saving` (disables "allow the computer to
  turn off this device", a classic source of latency spikes and dropouts).
- **Power Plan (4)** — `power_display_sleep_15`, `power_sleep_off`,
  `power_cpu_min_100`, `power_cpu_max_100`. Like v1 these write to **every** power
  scheme (GUIDs parsed from `powercfg /L`, never the localized plan name), because
  Windows may activate a different plan after a reboot and the setting would look
  reverted. `power_cpu_max_100` ships **without** a revert command on purpose —
  100 % is the Windows default, so a "revert" would write the identical value.

Tweak count: **71 → 83** in this batch (→ **106** after round 9), all with live
verifiers (VERIFY_MAP stays 1:1) and full English descriptions.

### 🛡️ Safety & honesty

- Marginal, risky, or security-lowering tweaks are deliberately **not** shipped.
- Registry keys are verified against the live system before being recommended.
- CPU-pinning honestly reports when it brings no benefit and warns about
  anti-cheat / CCD-parking interference.
- No shell/registry injection anywhere — all commands are hardcoded, no
  unfiltered user input reaches a shell.

### 🐛 Notable fixes folded into 2.0 (from two external review rounds)

- **Stress-worker dead-man switch** on *all* burn paths (cupy, numpy, and the
  no-numpy multiprocessing fallback): the GUI PID is passed to the worker and
  every loop self-terminates when the GUI is gone — no more orphaned 100 %-CPU
  process after a hard GUI crash. *Verified live.*
- **Thread-safe log box & monitor callbacks** — worker threads never touch Tk;
  a queue is drained by a main-thread poller (avoids `RuntimeError: main thread
  is not in main loop` on Python 3.14).
- **Autostart via Task Scheduler** (`/RL HIGHEST`) instead of an `HKCU\Run`
  entry, so the admin app starts without a UAC prompt each boot.
- **Honest per-tweak reverts** — `disable_hpet` now restores the true Windows
  default; and 12 previously one-way tweaks (mmcss_gaming, disable_fullscreen_opt,
  disable_bg_throttle, enable_msi_mode, dx12/TdrDelay, disable_nagle, disable_lso,
  dns_cloudflare, dns_google, enable_rss, disable_sticky_keys, disable_usb_suspend)
  now have proper revert commands, so "Revert All" truly reverts.
- **Honest DX12 tweak** — the old value wrote a D3D12 *debug env var* into the
  registry that the runtime never reads (placebo). It's now a truthful
  **"Raise GPU Timeout (TDR Delay)"** tweak — real `TdrDelay`/`TdrDdiDelay`
  values, described as timeout protection, not an FPS boost.
- **Nahimic verifier** no longer shows a permanent amber "mismatch" on the
  majority of PCs that never had Nahimic (absence = goal satisfied).
- **Update checker** parses pre-release-style tags correctly; **stress score**
  uses the configured max-temp instead of a hardcoded 85 °C; **tweak-state file**
  is anchored to an absolute path; **CPU-topology / MAHM / wmic / presets /
  restore-point** edge cases fixed; consistent `utf-8` decoding throughout.
- **Round-3 hardening:** CPU-pin reset (empty set) now reports success
  correctly; GPU-profile offsets get sanity guard-rails so a hand-edited/corrupt
  profile can't push an absurd overclock to Afterburner; `.nextune` import
  rejects implausibly large files (>10 MB); the admin-elevation prompt is now
  localized (DE/EN) instead of German-only; tray tooltip trimmed and
  de-versioned; friendly errors when launching services.msc / the log folder.
- **Round-4 bug hunt (verified fixes):**
  - **Auto-Tuner final verification now tests the exact profile it saves.** In
    FULL / VF_ONLY / MEM_ONLY modes the 2-minute final run previously applied
    only core-offset + power (`_apply(best_core, cfg.mem_offset_mhz, best_pwr)`)
    — so the Stage-3 **V/F-curve undervolt** and Stage-4 **memory OC** that get
    written into the saved profile were never verified together, and the
    stability score was measured on a milder (stock-voltage) setup. The final
    test now applies the V/F undervolt + `best_mem_offset` (the values actually
    saved). Default OC+UV mode was unaffected.
  - **Header clock & AB/NVML/MAHM indicators no longer freeze.** The status
    updater ran in a worker thread and called Tk `after()` from it; that thread
    is started in `__init__`, so its first `after()` fires *before* `mainloop()`
    and raises `RuntimeError: main thread is not in main loop` on Python 3.14 —
    and the old `except: break` then killed the updater permanently. It now runs
    as a self-rescheduling **main-thread** poller (no worker, no dead thread).
  - **Per-game process scan** reads the pre-filled `p.info['name']` instead of
    re-calling `p.name()`, which could raise `NoSuchProcess` for a process that
    died mid-scan and blank the whole cycle (briefly mis-reading a running game
    as stopped).
  - **FPS-CSV parsing** keeps the GPU-busy column index-aligned with frametimes
    even when a row is short, so the CPU-vs-GPU bottleneck verdict can't drift.
- **Round-5 bug hunt (verified fixes):**
  - **`set_mmcss_audio` no longer deletes a Windows-shipped registry key.** Its
    revert ran `Remove-Item … 'Pro Audio' -Recurse`, but that MMCSS task ships
    **with Windows**. A live read confirmed the key holds values the tweak never
    sets (`Background Only`) and stock values it does change (`Priority` 1→6,
    `SFIO Priority` Normal→High). Reverting therefore *removed* the Pro-Audio
    scheduling profile instead of restoring it. The revert now writes the real
    Windows defaults back.
  - **Afterburner profile writes no longer destroy the file's INI structure.**
    `write_and_apply` parsed only `key=value` lines, so every `[Section]` header
    was dropped and the profile was rewritten as a flat key list — the opposite
    of the "preserve unknown keys" intent. It now keeps the original lines
    verbatim (sections, comments, unknown keys) and replaces only its own keys
    in place, appending any that weren't present. *Honest caveat:* the
    section-stripping is provable from the code and is covered by a test with a
    sectioned `.cfg`, but MSI Afterburner was not installed on the machine this
    was fixed on, so the exact key naming it expects could not be confirmed
    against a real profile.
  - **`.nextune` import no longer crashes on non-object JSON.** A valid JSON
    array/number/string has no `.get()`, which raised an uncaught
    `AttributeError` straight out of the button handler — no error message, the
    button just did nothing. Import now type-checks the payload and coerces
    `tweaks`/`gpu_profiles`/`user_presets` to the expected types.
  - **System Cleaner safety guard compares path *segments*.** The old substring
    check would also have accepted `…\Templates` or `…\temp_backup`. Unreachable
    from the UI (only three fixed targets are passed), but a guard should hold
    regardless.

- **Round-6 bug hunt (verified fixes):**
  - **"Check status" silently claimed ownership of settings made outside the app.**
    `_live_verify` compared every tweak against `expected=False` and then added
    each one found active to `runner._applied`. One click on "⟳ Status prüfen"
    therefore recorded pre-existing settings (dark mode, file extensions, NIC
    power saving, …) as "applied by GameOptimizerPro", and **Revert All then
    switched them off**. Reproduced with the values this machine really reports.
    The verifier now only feeds the status dots; `_applied` lists exactly what
    this app applied.
  - **"Abweichungen beheben" applied tweaks that were never chosen.** A mismatch
    is `expected != actual`, which includes "active on the system but not
    applied by us". The verify tab now separates *reset behind our back*
    (re-applied by the button) from *active, but not ours* (shown in blue,
    untouched).
  - **Dead "sync state" block removed** from the verify tab — it sat behind
    `not mismatch` while describing mismatch cases, so neither branch could
    ever run (proven over all four expected/actual combinations).
  - **`.nextune` import marked tweaks as applied without applying them.**
    Nothing changed on the PC, the tweaks still showed as active, and Revert All
    would have reverted them here. Imports now *pre-select* the tweaks (known +
    fitting this hardware) for review and "Apply Selected".
  - **GPU-vendor tweaks were applied on the wrong hardware.** Presets ("Mittel",
    "Hart", "All Safe") ignored `requires_nvidia` / `requires_amd`, which only the
    tweak list honored. Worse, the AMD tweaks ported in round 5 looped over
    **every** subkey of the display-adapter class — which also holds NVIDIA and
    Intel adapters — because v1's `if ($IsAMD)` guard was dropped in the port,
    and "All Safe" now included them. Fixed twice: a single `_is_applicable`
    filter for list, presets and import; and each command guards itself (AMD
    tweaks touch only subkeys whose `ProviderName` is AMD — on hybrid systems
    just the AMD adapter — and `exit 1` without one; `nvidia_low_latency`
    refuses unless the `nvlddmkm` driver service exists, instead of creating a
    bogus `Services\nvlddmkm` tree via `reg add /f`). A read-only check confirmed
    no stray values had reached this machine.
  - **The MAHM reader created and squatted Afterburner's shared memory.**
    `mmap.mmap(-1, 1 MB, tagname="MAHMSharedMemory")` *creates* the section when
    it doesn't exist, and on the resulting signature mismatch the handle was never
    closed — so on any PC without a running Afterburner, GameOptimizerPro held a
    1 MB section under Afterburner's name for the whole session (verified live).
    It also failed with "access denied" against any real section smaller than
    1 MB, and `reopen()` was never called, so starting Afterburner after the app
    never connected. Now: `OpenFileMappingW` (never creates), `MapViewOfFile`
    with length 0 (any section size), release on signature mismatch or
    Afterburner shutdown (`0xDEAD`), and an automatic reconnect every 5 s.
    Tested end-to-end against a stand-in section.
  - **Correction to round 5: the automatic registry backup never ran from the
    UI.** It was wired into `TweakRunner.apply_batch()` / `revert_all()`, which
    have no callers — the UI applies and reverts tweak by tweak. The backup is
    now taken in the actual UI paths: Apply Selected, presets, Revert All and
    "Abweichungen beheben". (Round 5 tested `create()` and the manual button, not
    whether the automatic hook was reached.)
- **Startup Manager — v1 parity.** v2's Startup Manager could only *list* the
  three Run keys and open Task Manager. It now also lists **both Startup folders**
  (per-user and all-users; `.lnk` targets resolved), shows each entry's **real
  on/off state**, and can **enable / disable** entries (multi-select) exactly
  like Task Manager: only the `StartupApproved` flag is written (`0x02` enabled,
  `0x03` + FILETIME disabled — encoding verified against this machine's live
  values), nothing is deleted, and the state is read back after each change.
  Confirmation before disabling, with an extra warning for system /
  not-recommended entries; "disabled" filter; sorting by the "Pfad" column now
  actually sorts (it keyed on a field that didn't exist). Tested on a temporary
  HKCU test entry that is always removed afterwards — never on real entries.

- **Round-7 bug hunt (verified fixes):**
  - **MAHM (Afterburner telemetry) parser rewritten to the real layout.** Cross-
    checked against two independent readers (LCDHost's C++ header, CleanMeter's
    Kotlin reader): entries are **1324** bytes (five 260-byte strings, value at
    @1300, source id at @1320) after a header whose @8 is `dwHeaderSize`. The old
    parser assumed 284-byte entries with the value at @268 and read
    `dwHeaderSize` as the entry count — fed a spec-conformant image it returned
    **0 for every sensor** while reporting "available", so real mV readings and
    the V/F stage could never work. The old `src_id & 0xFF` also mapped
    **CPU power (0x100) onto GPU temperature**; the GPU index is taken from
    `dwGpu` instead (other GPUs no longer overwrite GPU 0). v1.x entries without
    ids fall back to name matching; implausible headers are rejected. *Caveat:*
    no Afterburner on the dev machine — verified against spec-built images.
    (Round 6's MAHM test used the parser's own layout and only proved
    open/reconnect, not parsing.)
  - **MAHM no longer overwrites good NVML values with zeros.** Afterburner only
    exports sources whose graphs are enabled; the unconditional copy turned fan
    45 % → 0 % and power limit 320 W → 0 W. Afterburner's "Power/Temp limit"
    sources are 0/1 limiter flags and are no longer written into W/°C fields —
    the temperature gauge used the flag as its scale (1 °C) whenever the thermal
    limiter was active. The gauge scale now comes from NVML's slowdown threshold.
  - **"Abort" could be overridden.** The running stress step (up to 60 s) kept
    loading the GPU after Abort, and its result was then acted on — reproduced:
    reset to stock, then **+30 MHz re-applied**; the crash flag was set again
    (false "GPU crash" dialog next start) and the state ended on `BACKOFF`, which
    left the Start button disabled. Now: one lock around every Afterburner/NVML
    write, `abort()` sets the stop flag first and resets under the lock, writes
    after abort are no-ops, the stress step checks the stop flag every second,
    every stage returns right after a stopped step, and `ABORTED` can't be
    overwritten. Abort runs off the UI thread.
  - **Exiting (tray) or switching language mid-tune** killed the tuner thread
    via `os._exit` and left the GPU on the last, untested OC — both now abort
    (reset to stock) first.
  - **"Reset to stock" set the MAXIMUM power limit.** It used the upper
    constraint, which on many partner cards is above stock (e.g. 450 W stock /
    600 W max) — i.e. it *raised* the limit. Now the factory limit from
    `nvmlDeviceGetPowerManagementDefaultLimit`; "power %" means % of stock
    (Afterburner's meaning), clamped to the allowed range, and 100 % is actually
    applied (a later 100 % step used to leave a reduced limit in place).
  - **No tuning without GPU load.** The stress worker loads the GPU only via
    `cupy`, which is optional and was undocumented; without it, it silently
    burned the CPU and every OC/UV step "passed" on an idle GPU. The tuner now
    measures GPU load during the baseline and aborts below 70 % with a clear
    explanation (install `cupy-cuda12x` or run FurMark in parallel).
  - **Autostart task hardened.** `schtasks /Create` defaults (verified on a
    throwaway task): `ExecutionTimeLimit=PT72H` (Windows kills the tray app
    after 3 days), no start on battery, stop when unplugged. The task is now set
    to no time limit and battery-friendly — existing tasks are repaired on start —
    and always launches `pythonw.exe` (no console).
  - **Stress Test tab**: a stopped run was reported "✓ PASSED" (the thread ran on
    and judged `peak < max`); Stop→Start could let the old thread kill the new
    worker; a crashed worker or a TDR was ignored; "PASSED" only meant "temp
    below the limit". Now run generations, own-worker cleanup, fail on worker
    crash / TDR, and "no GPU stress" instead of "passed" when GPU load < 70 %.
  - **Tune History**: the mode regex matched the logger's `[INFO]` tag, so every
    run showed mode "INFO"; the log file was opened once per app START (24 empty
    `tune_*.log` on the dev machine, all runs of a session merged); the GPU name
    was never parsed. Now one log per run, correct mode/GPU, empty leftovers pruned.
  - **Primary GPU detection**: only the first WMI adapter was used, so on
    iGPU + dGPU systems the iGPU could win — wrong name and wrong NVIDIA/AMD flags
    (which gate vendor tweaks). Discrete GPUs are now ranked first.
  - Cosmetic: periodic `after()` pollers are cancelled when their widget is
    destroyed (no more "invalid command name" noise on exit); the Startup Manager
    tolerates being closed while it is still loading.

- **Round 8 — Afterburner profile writer:**
  - Profiles reach Afterburner: the card's own profile file (`Profiles\VEN_…cfg`) is
    written and Afterburner is restarted with `-ProfileN` (it reads the file only at
    start). "Reset to stock" writes stock values into the app's slot instead of
    loading slot 1. The setup check reads the real `MSIAfterburner.cfg`.
  - The MAHM reader is thread-safe and recovers after Afterburner restarts.
  - The tuner stops on a failed apply, no longer counts normal power limiting as a
    failure, detects instability by verified results (gpu-burn / OCCT method), lowers
    the power limit only while it costs at most 3 % performance, and measures memory
    bandwidth (GDDR6X retries bad transfers — EDC).
  - `tools/ab_selftest.py`: `info` (read-only), `dryrun`, `live`, `restore`.
  - The OC search uses a game-like mixed load (full load alternating with boost load).
- **Round 9 — v1 parity audit and Windows 11 26H2** (corrected parity list, 26H2
  changes, features deliberately not ported).
- **Round 10 — first real use:** no console window; a failed final test steps back
  and tests again instead of saving an untested profile; either-or tweak groups
  (power plans, DNS); power-plan fixes; mouse wheel over the tweak list; several
  status checks fixed; one drift decision per tweak; the temp cleaner only deletes
  files older than 24 hours; the tests live in the repository (CI).
- **Round 11 — memory overclock in the Auto-Tune.**
- **Round 12 — new interface:** CustomTkinter UI with sidebar; GPU tuner with live
  tiles and graph; optimizer search; FurMark 1 / 2 and 3DMark detection and recording
  during external tests; audio tweaks fixed for Windows 11 26H2; remnant scan; the
  tray-default GPU profile can load at start; new dependency `customtkinter`.
- **Round 13 — the All-round tuner ("Rundum"):** a boost-load probe per voltage
  point, an own V/F curve from the measured points, a curve check, memory tested with
  the whole card under load (FurMark + verified copies), the goal chosen by a FurMark
  benchmark (Max / Balanced / Efficiency), a final test (5 min FurMark + 2 min
  compute-checked load) and a report. Follow-ups: live values throughout the tune,
  points every 25 mV, the same memory stage in every mode, the test battery runs on a
  hidden desktop.
- **Round 14 — leaner, every BIOS platform, updates from GitHub:** per-game profiles,
  CPU pinning and FPS capture removed; page switches 2–3× faster; the BIOS guide
  covers 16 platforms with honest detection; updates from GitHub (`build.json`, zip
  or `git pull`); "keep running in the tray"; Afterburner setup checks; clearer tuner
  settings; one update check at a time; the tune history shows every value and the
  reason, runs can be deleted.
- **Round 15 — two modes:** All-round (default) and Quick (OC + UV); a memory check
  that cannot starve (FurMark never takes the foreground); any result into any
  Afterburner slot (history / profiles, right click); status dots explain
  themselves; a driver-reset check without gaps; profiles can be renamed.
- **Round 16 — tests closer to what games do:**
  - Game test after the final test (both modes): cool-down, load changes at the top
    clock, steady boost point. Hang detection: a load without results for 8 s fails.
  - Margins: 45 MHz, 60 MHz at the top points (within 75 mV of the highest), 30 MHz
    more where a driver reset or hang happened; Quick mode 60 MHz; memory 200 MHz below
    the highest passed step, a bandwidth drop marks the edge.
  - GPU watchdog at app start: GPU hang / reset events since the applied profile →
    make safer / stock / keep. "Make safer" (curve −30 MHz, memory −200 MHz).
  - The applied profile is recorded wherever the app applies one; applying a profile
    that has a safer copy asks first; one app instance at a time.
  - Fixes from live tests: the mixed load now reports during its boost phase (false
    hang alarms); the power-limit stage cross-checks against a fresh 100 % reference;
    a memory bandwidth drop must show twice; the tuner log follows the app's language.
- **Round 17 — what the PC boots with, and polish:**
  - Afterburner's boot entry (`[Startup]`, applied at every Windows start) follows
    the profile you apply; while a tune tests steps it holds the profile you had
    before (never a step under test), at the end the saved profile. The GPU tab says
    after applying whether Afterburner also loads the profile at Windows start.
  - GPU errors logged together with a compute error now count as a driver-level
    failure (the point gets the extra 30 MHz margin).
  - After a successful tune the app offers to name the profile (e.g. "All-round
    Balanced 09.10."); the history, the start-up profile and the watchdog follow a
    rename.
  - Number fields are clamped before a tune starts (a typed value outside the range
    was only corrected when the field lost the focus).
  - The app-start test no longer writes into the app's logs folder; texts in the
    app, the code and the docs are neutral.

- **Round 18 — profiles compared against stock** (build 25):
  - The profile comparison shows what tells profiles apart: **performance** (points vs
    stock) and **efficiency** (points per watt vs stock) from the same benchmark, the
    best marked; unmeasured profiles say so instead of showing a made-up number. The
    stability score (100 for every saved profile) became "passed". Also clock (an own
    curve's top point under its cap, or the offset), memory, power limit, power draw in
    the test, mode and date; full names; German labels.
  - Both modes store the benchmark with the profile (`TuneProfile.bench`,
    `core/profile_score.py`): the All-round mode its stock and after runs, the Quick mode
    now 60 s of FurMark 2 at stock and with the result (needs FurMark 2; about 3 min
    more). Older All-round profiles are read from their notes; runs of different length
    are compared per second.
  - 1031 checks in 27 suites, all green.

- **Round 19 — smoother window, tidier lists, remembered tuner settings** (build 26):
  - Maximize / restore: only the visible page is mapped and laid out (hidden pages are
    unmapped and keep their layout). Measured with every page built: the optimizer page
    blocked 1.0–1.3 s per resize, now 0.2–0.4 s; GPU tuner 0.9–1.1 s → 0.2–0.3 s;
    dashboard 0.7–1.0 s → 0.15–0.2 s.
  - Optimizer: every category folds open / closed (header with the number of tweaks
    and how many are active, "Open all" / "Close all"; closed by default, the open ones
    are remembered; a search shows matches in closed categories too).
  - GPU tuner: the values set in the fields are remembered — a mode switch or an app
    start no longer puts the card's defaults back (e.g. "max memory gain"); the clock
    gain is kept per mode; "Restore the card's defaults" forgets them.
  - Tray: a click on the icon opens the window. Profile comparison: no GPU row.
  - Tests: every suite of the battery gets its own settings file (`GOP_SETTINGS_FILE`),
    six UI suites patched too — no test can write the app's own settings.
  - 1041 checks in 27 suites, all green.

- **Round 20 — tweak review against Windows 11 26H2** (build 27):
  - Live status check of all tweaks on a current 26H2 system: every applied tweak still
    in effect (no update reset one). Windows' AI policies checked against Microsoft's
    WindowsAI policy reference: Recall, Click to Do, Paint AI, text and image generation
    and Copilot are covered; the Settings agent, agent connectors and the Copilot-app
    removal policies apply to Enterprise / Education only (not added); the new Low
    Latency Profile has no setting or policy (not added).
  - New: **Optimizations for windowed games** (Gaming, safe, in "Medium" and the gaming
    preset) — DirectX 10/11 games in a window or borderless window use the flip model
    (less latency, VRR and Auto HDR in a window). Apply and revert change only this flag
    in `DirectXUserGlobalSettings` and keep the others.
  - Fixed: "Disable Store recommended search results" was shown as not active although it
    was — its deny rule also blocks reading the file's permissions; "access denied" now
    counts as applied.
  - Fixed: "Clear shader cache" is a one-time action — no status any more (a cache that
    fills up again while playing was shown as "not active", and the drift dialog offered
    to clear it again: every game then rebuilds its shaders), and not part of "Hard".
  - 1052 checks in 28 suites, all green.

- **Round 21 — remembered tuner settings, one fix** (build 28):
  - Fixed: starting a tune (or applying / resetting by hand) recorded every field of the
    GPU tuner as a value the user had set, so the card's defaults shown at that moment
    stayed fixed afterwards. Number fields now write only a value they actually correct
    (out of range or half-typed); only real changes are remembered.
  - 1056 checks in 28 suites, all green.

- **Round 22 — stock as point 0 in the profile comparison** (build 29):
  - Profile comparison: stock is a column and a bar of its own (0 %), with its FurMark
    points, power draw and points per watt — the mean of the stock runs the chosen profiles
    were measured against (every tune measures stock right before, in the same test).
  - New rows: FurMark points (per 60 s, so runs of another length read the same) and points
    per watt, each next to the profile's own stock run.
  - Better or worse than stock at a glance: ▲ better, ▼ worse, ≈ the same (within the
    run-to-run noise of ±0.5 %); ★ still marks the best profile.
  - Curve report: a GPU error in the event log during the search is named as such (it was
    called a driver reset), and the recommendation states the margin actually used at that
    point instead of a fixed "60 MHz".
  - 1060 checks in 28 suites, all green.

- **Round 23 — All-round goals refined from a full test series** (build 30):
  - **Balanced, new rule:** performance **and** efficiency above stock, as evenly as
    possible — the setting whose smaller gain is the largest. A test series on an RTX 4080
    showed the old rule (half the gain, most points per watt) picking flat from 1050 mV:
    +2.4 % performance, −0.5 % efficiency — hardly different from Max (+3.9 % / +1.7 %),
    while one cap lower already gave +0.9 % / +6.2 %. The old rule remains the fallback
    when no setting beats stock in both; log and report name the rule that applied.
  - **Fine search (Balanced, Efficiency):** after the caps every 25 mV, one more cap
    halfway to the neighbour where the goal's optimum lies (balanced: towards the higher
    cap while performance is the smaller gain, else lower; efficiency: lower), snapped to a
    real curve point — about 75 s more. A crash there is handled like any candidate's.
  - **The card's minimum voltage under load is remembered** per GPU (next to the tune
    logs): the next tune plans its measuring points only down to it — no test at a point
    the card never reaches — and puts the lowest point right at it when the grid ends a
    distinct point above.
  - Texts: the goal descriptions and the step-by-step tune explanation say so.
  - 1090 checks in 29 suites, all green.

- **Round 24 — curve chart, fair benchmarks, Quick mode refined** (build 31):
  - **Profile comparison: V/F curves** like Afterburner's curve editor — voltage to the
    right, clock up; stock dashed, every chosen profile in its colour (All-round profiles
    flat from their cap with the measured points as dots, Quick profiles as the shifted
    curve), the range the card runs in under load shaded; pointing at the chart shows every
    curve's clock at that voltage. The stock curve is read from Afterburner's profile file.
  - **Every comparison benchmark starts at the stock run's temperature:** the card idles
    until it is back there (at most 90 s) before each All-round candidate, the fine search
    and the Quick mode's "after" run. A test series showed the Quick "after" run starting at
    ~67 °C right after the game test (stock: ~55 °C) and All-round candidates 2–5 °C warmer
    than stock — a warm card clocks a bin lower and draws a few watts more, so profiles
    looked slightly worse than they are.
  - **Quick mode: the curve is flat from the game test's highest voltage.** The offset
    shifted the whole curve, also the points above the highest voltage any test reached
    (RTX 4080: 1075 → 1100 mV at +134 MHz, never tested; a light load can boost there).
    Now: below that voltage exactly what was tested, above it lower. The description says
    honestly that the lowered power limit only saves power under full load (FurMark and
    most games stay below it).
  - "≈ stock" now within ±0.7 % — the spread of four stock runs of the same card.
  - 1111 checks in 30 suites, all green.

- **Round 25 — start-up profile in its own slot, stall watchdog** (build 32):
  - Fixed: at an app start the last applied profile was always written into Afterburner
    slot 2 — whatever was there was replaced, and Afterburner restarted for nothing. It is
    now applied from the slot that already holds it (2–5; slot 1 stays the user's own);
    only when no slot does, slot 2 as before.
  - Stall watchdog for the tuner: no log line or progress for 2 minutes means a call is
    stuck (every step reports at least every few seconds, an Afterburner restart takes
    5–30 s). The log then says so and every thread's position goes into
    `logs/stall_<time>.txt`; when the tune goes on, the log says after how long. (Seen once:
    a tune stood still ~19 minutes between two steps while the PC was idle and Windows ran
    its automatic maintenance — afterwards nothing told where it had waited. The results
    were not affected: the next step measured its reference again.)
  - 1116 checks in 30 suites, all green.

- **Round 26 — clearer profile comparison** (build 33):
  - Curve chart: every profile has its own line style (solid, dashed, dotted, dash-dot) and
    the chart a legend — curves lying on each other no longer hide the one below (two Quick
    profiles with the same offset are identical up to the highest tested voltage).
  - New bar row "FurMark points": the profiles against each other in points. The
    percentages compare each profile with its OWN stock run (measured right before, same
    conditions); stock runs of the same card differ by ~1 %, so a profile can read a higher
    percentage with fewer points.
  - 1118 checks in 30 suites.

- **Round 27 — All-round tuner checked live end to end** (build 34):
  - The saved minimum voltage under load is used: on a card's second tune the voltage
    points stop there — on the test card 7 instead of 10 points, the three it never
    reaches under load are no longer tested.
  - The fine search for Efficiency goes down: halfway between the last cap that kept
    ≥ 99 % of stock and the first one below; the goal rule then picks the cap with the
    least power. Result on the test card: −0.7 % points at −16 % power (+18.6 % points
    per watt).
  - Log line for the saved minimum voltage corrected: the points stop there (the lowest
    one can lie a few mV below it, within the reach tolerance) — it said "right at it".
  - For clarity: All-round has no extra comparison run after the final test — the
    "after" value in the report is the chosen variant's benchmark, measured with exactly
    the settings that get saved. Only Quick measures once more after the final test,
    because it caps its curve at the game test's voltage.
  - 1118 checks in 30 suites, all green.

### 🔎 Reviewed, verified NOT a bug

Some reported items were checked against the actual code and left unchanged
because they were overstated or false: the tray `_open()` "race" is already
caught by its try/except; file logging does exist (a daily tweak logfile is
written); the NVML-shutdown "leak" and Afterburner lock-check cost were
overstated. Known low-impact edge cases (CPU topology on >64-thread CPUs,
graph rendering across data gaps, `apply()` trusting a PowerShell exit code
that `-EA SilentlyContinue` can leave at 0) are documented and mitigated by the
live verifier rather than papered over.
