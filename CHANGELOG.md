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
- **Windows Optimizer — 83 tweaks** across Windows, Gaming, Network and Audio,
  each with **live status verification** that reads the real registry/service
  state (not just a saved flag), shown as ● green (verified) / ◑ amber
  (applied, unverified) / ○ grey (inactive).
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
- **Live Dashboard** — real-time GPU telemetry + CPU/RAM/Disk tiles and a
  one-click network latency test (gateway + Cloudflare/Google, jitter & loss).
- **System Cleaner & Restore Point**, **Tune History**, **Temperature Warning**
  (toast at 90 °C), **Startup Manager**, **background Update Checker**, and full
  **DE/EN** language switching.

### 🔁 Full v1 parity (ported from GameOptimizerPro v1)

v2 is a Python rewrite of the PowerShell/WPF v1, and a handful of v1 features had
never made it across. They are now ported, with v1's original commands as the
reference:

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

Tweak count: **71 → 83**, all with live verifiers (VERIFY_MAP stays 1:1) and full
English descriptions.

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
  - **"Check status" silently claimed ownership of the user's own settings.**
    `_live_verify` compared every tweak against `expected=False` and then added
    each one found active to `runner._applied`. One click on "⟳ Status prüfen"
    therefore recorded pre-existing settings (dark mode, file extensions, NIC
    power saving, …) as "applied by GameOptimizerPro", and **Revert All then
    switched them off**. Reproduced with the values this machine really reports.
    The verifier now only feeds the status dots; `_applied` lists exactly what
    this app applied.
  - **"Abweichungen beheben" applied tweaks the user never chose.** A mismatch
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

### ⚠️ Known open issue

- **Applying OC profiles to MSI Afterburner has no effect.** `write_and_apply`
  writes `Profiles\MSIAfterburner{slot}.cfg` with `CoreClockOffset` in MHz, but
  Afterburner keeps profiles **per GPU** in
  `Profiles\VEN_10DE&DEV_…&BUS_…&DEV_0&FN_0.cfg`, in `[Profile1]`…`[Profile5]`
  sections with `CoreClkBoost` / `MemClkBoost` in **kHz**, `PowerLimit` in % and
  a binary `VFCurve` (verified against three independent real-world files and
  tools). `/Profile2` therefore loads Afterburner's own, unchanged profile 2. A
  correct fix has to close Afterburner, write its real profile file and restart
  it; it can't be tested without Afterburner and NVML can't read back the offset
  on GeForce, so it is pending a decision rather than shipped blind.

### 🔎 Reviewed, verified NOT a bug

Some reported items were checked against the actual code and left unchanged
because they were overstated or false: the tray `_open()` "race" is already
caught by its try/except; file logging does exist (a daily tweak logfile is
written); the NVML-shutdown "leak" and Afterburner lock-check cost were
overstated. Known low-impact edge cases (CPU topology on >64-thread CPUs,
graph rendering across data gaps, `apply()` trusting a PowerShell exit code
that `-EA SilentlyContinue` can leave at 0) are documented and mitigated by the
live verifier rather than papered over.
