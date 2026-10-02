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

- **Round 8 — Afterburner profile writer (the former "known open issue"):**
  - **Profiles now reach Afterburner.** `write_and_apply` wrote
    `Profiles\MSIAfterburner{slot}.cfg` with invented keys (`CoreClockOffset` in
    MHz, `VoltagePoints`, …) that Afterburner never reads — applying a profile had
    no effect. It now writes Afterburner's **real per-GPU profile**
    `Profiles\VEN_10DE&DEV_…&SUBSYS_…&REV_…&BUS_…&DEV_0&FN_0.cfg`, chosen by the
    card's PCI identity from NVML (a leftover file of an old card is never
    touched): `[ProfileN]` with `CoreClkBoost` / `MemClkBoost` in **kHz**,
    `PowerLimit` in % of stock and the binary `VFCurve` (header + per point
    voltage / base / offset floats — only the offset floats are changed, every
    other byte is kept). A plain offset goes onto every curve point, as
    Afterburner does; the V/F undervolt writes a real flat curve from the card's
    own curve points (`CoreClkBoost=1000000` marks a custom curve) and never puts
    a point above the tested frequency. Format cross-checked against a real
    RTX 3090 profile, the hekmon/aiup `msiaf` parser, KingAi's Afterburner tools
    and Annihil's VF-curve parser (new module `core/ab_profile.py`).
  - Afterburner reads that file only when it starts, so new values mean: close it
    (WM_CLOSE, terminate only if it hangs, never within 8 s of its own start),
    write atomically, start it again with `-ProfileN` (minimized, no focus
    steal). Identical values are just re-sent with `-ProfileN` — no restart. The
    original file is backed up once per session to
    `%LOCALAPPDATA%\GameOptimizerPro\AfterburnerBackups\`.
  - **"Reset to stock" loaded the user's slot 1** (whatever was saved there). It
    now writes stock values (0 / 0 / 100 %, stock curve) into the app's slot.
  - **Setup checker** read the installer's *template* `MSIAfterburner.cfg` and
    looked for a key that doesn't exist (`EnableVoltageControlInterface`). It now
    reads `Profiles\MSIAfterburner.cfg` (`UnlockVoltageControl`,
    `UnlockVoltageMonitoring`, the "GPU voltage" graph) and shows whether the
    card's profile file exists. The per-slot "🔒 locked" check (it read a file
    Afterburner never had) is gone.
  - **Fan:** sources disagree on Afterburner's `FanMode` encoding (0 = auto vs.
    1 = auto), so the writer never touches fan keys; the manual fan slider was
    removed rather than pretending.
  - **MAHM reader is thread-safe.** With Afterburner restarting on every tuning
    step, one thread could unmap the shared-memory view while another was still
    copying from it (access violation). Stress-tested: ~300 000 reads while a
    fake section was destroyed and recreated 59 times — no error. Afterburner's
    "Power" source in **%** is no longer shown as watts.
  - **The tuner ignored failed applies.** `_apply()`'s result was never checked,
    so a step that could not be applied ran its stress test on the previous
    settings and was saved as "stable"; and "Undervolt only" without Afterburner
    never set the power limit at all (NVML was only called after a successful
    Afterburner write). Now a failed apply ends the tune with a clear error and
    resets to stock; power-only undervolting works via NVML without Afterburner,
    while core/memory offsets and the V/F curve say plainly that Afterburner is
    required.
  - GPU-tab Apply / Reset / profile apply and Settings → "load startup profile"
    run off the UI thread (they take seconds now); applying is blocked while an
    Auto-Tune runs.
  - **The tuner counted normal power limiting as a failure.** Its NVML
    throttle table was shifted by one bit (0x04, the software power cap, was
    labelled "Thermal"; 0x02, application clocks, "Power"), and *any* active
    reason failed a step. Under full load a GeForce practically always runs
    into its power limit, so OC steps failed for no reason — and the power-limit
    stage, whose very lever *is* the power limit, could never lower anything.
    Bits now come from `nvml.h`; only thermal / hardware slowdowns
    (0x08 / 0x20 / 0x40 / 0x80) count, and the dashboard shows "Power-Limit" as
    normal instead of a warning.
  - **Instability is detected by wrong results (gpu-burn / OCCT method).** The
    stress worker repeats the same SGEMM and compares every result with the
    first (cuBLAS is deterministic; tolerance a few ULPs) — one wrong value ends
    the step with "computation error". A CUDA error *after* the load started is
    now an instability signal instead of a silent fall-back to CPU load. It also
    reports its work rate (TFLOPS).
  - **Power-limit stage has a real criterion:** the lowest limit that costs at
    most **3 %** performance (work rate, else clock) against the 100 % run at the
    chosen core offset (`power_max_loss_pct`). Published RTX 40 measurements put
    70–80 % power limits at a few percent loss in games; a full-load stress test
    loses more than a game, so 3 % is conservative.
  - **Memory stage measures bandwidth.** GDDR6X retries failed transfers (EDC),
    so a memory overclock past its limit gets *slower* instead of crashing — the
    old crash-only test would have kept "passing" it. Memory steps now run a
    bandwidth load (copies verified against a reference) and stop when bandwidth
    drops more than 2 % below the best seen (measured run-to-run noise: 0.8 %);
    the result is the offset with the **highest measured bandwidth** — the
    stepping itself creeps a little past the peak, where the memory already
    corrects errors. Without cupy it says so and falls back to crash detection.
    (Note: the Full / V/F-curve / Memory modes exist in the tuner but are not
    selectable in the GPU tab — it offers OC, UV and OC+UV.)
  - `install.bat` offers `pip install "cupy-cuda12x[ctk]"` (no CUDA Toolkit
    needed) and shows the current Afterburner setup (the old "unlock the
    padlock" step was wrong); all cupy hints now include `[ctk]`.
  - **`tools/ab_selftest.py`**: `info` (read-only), `dryrun` (the exact diff,
    verifies that no other section changes, writes nothing), `live` (+15 MHz /
    90 % via Afterburner, measured with NVML, optional flat curve, then stock
    values and the original file are restored — also on Ctrl+C; refuses while
    the GPU is busy), `restore` (put a backup back).
  - *Verification status at that point:* offline only (199 checks) — format tests against
    spec-built files in the real layout, the controller flow on a fake install,
    real process control against a dummy `MSIAfterburner.exe`, the MAHM stress
    test, the GPU/Settings/Stress/Dashboard tabs under a real Tk mainloop, the
    stress worker against a numpy-backed cupy stand-in with injected errors, and
    every tuner stage against a scripted GPU.
  - **First read-only checks on a real system** (RTX 4080, Afterburner
    4.6.6.16757): the card's profile file was found by PCI ID, its `VFCurve`
    parsed as 127 points from 450 to 1240 mV (6448 hex chars = 12-byte header +
    256 slots + 140 trailing bytes — exactly the documented layout), and the
    MAHM reader read all 55 live sources with values matching NVML (temperature,
    clocks). Two things the real data corrected: Afterburner's **"Power" in W is
    source 0x61** (0x60 is the percentage) — it was ignored and the NVML value
    used instead; and 4.6.6 keeps **no graph list** (`Sources=`) in
    `MSIAfterburner.cfg`, so "is the GPU-voltage graph on?" is now answered from
    the live monitoring data. (Also seen: `FanMode=1` with the fan in auto — one
    more reason not to trust the "0 = auto" reading and to leave fans alone.)

- **Round 8 — live on the real system** (RTX 4080, Afterburner 4.6.6, driver 617,
  Windows 11 26H2):
  - **The Afterburner writer works on real hardware.** `tools/ab_selftest.py live`
    wrote +15 MHz / 90 % into slot 2, Afterburner restarted with `-Profile2`, and
    NVML read the new power limit back (**288 W** = 90 % of 320 W); identical
    values were then applied *without* a restart, "reset to stock" wrote
    0 / 0 / 100 %, and the original profile file came back **byte-exact**.
    (`nvmlDeviceGetClockOffsets` is readable but does *not* report Afterburner's
    offset, so the core offset can't be confirmed via NVML — the power limit is.)
  - **Real bug found live: frozen monitoring after an Afterburner restart.**
    In the tray Afterburner ignores WM_CLOSE, so the restart ends in a kill; a
    killed Afterburner doesn't mark its shared memory as closed, every reader
    that still holds a handle keeps the old section alive, and the *new*
    Afterburner then doesn't publish into it. Result seen: the dashboard showed
    8 % load / 210 MHz for 14 minutes of full load. Fix: the reader lets go of
    the section *before* the kill (`on_ab_closing` → `suspend()`), the
    controller waits until the section is really gone, reconnects when the new
    Afterburner is ready (`on_ab_started` → `resume()`), and a section whose
    time stamp stops moving for 8 s is treated as dead and never re-attached.
    GPU values now come from NVML first; Afterburner only supplies what NVML
    can't (voltage, memory voltage, fan rpm).
  - **Game-like load for the OC search.** A constant full-load SGEMM keeps the
    card at its power limit (~2510 MHz here) — but games crash at the *boost*
    point (high clock, high voltage, lower power). The stress worker's `mixed`
    mode alternates 10 s heavy load with 10 s half-duty load that reaches
    **2790 MHz @ 1075 mV** — the exact operating point measured in Hunt:
    Showdown. Stage 1, the V/F stage and the final test use it; the power-limit
    stage keeps the steady load (it needs a reproducible reference, measured
    warm), the memory stage its bandwidth load.
  - Calibration on the card: 0 computation errors at stock,
    step-to-step work-rate noise **0.06 %**, bandwidth noise **0.8 %** (hence the
    2 % memory criterion), 74 °C max. A Hunt: Showdown capture: ~69 % GPU load,
    ~232 W, never power-limited — so in this game an OC gains little, an
    undervolt costs nothing.
  - Hardware detection: VRAM showed 4 GB on a 16 GB card (WMI's `AdapterRAM` is
    32-bit) — now read from the driver's `HardwareInformation.qwMemorySize`; RAM
    type DDR5 from `SMBIOSMemoryType` (34) instead of "Unknown"; NVMe drives via
    `MSFT_PhysicalDisk.BusType` (17).
  - Dashboard: the network test at the bottom was cut off — the tab scrolls now.
  - Still to do *on real hardware*: a complete end-to-end Auto-Tune run (all
    parts are tested individually and against a scripted GPU) —
    [TESTANLEITUNG.md](TESTANLEITUNG.md), step 8.

- **Round 9 — v1 parity audit + Windows 11 26H2:**
  - **Honest correction:** the earlier "full v1 parity" claim was wrong. A
    line-by-line audit of v1 (`GameOptimizerPro.ps1`) found 24 tweaks and 5
    features that never made it into v2. 18 tweaks and all 5 features are ported
    now with v1's commands as the reference — checked, not copied blindly — and
    6 tweaks deliberately not (see below):
    - **Storage & RAM:** long paths, free the reserved storage (~7 GB), system-
      managed pagefile, clear pagefile at shutdown, memory compression off, SSD
      TRIM on, scheduled defrag off, **NVMe queue depth** (only offered with an
      NVMe drive), **write-cache buffer flushing off** (advanced; v1 wrote
      `UserWriteCacheSetting`, which is the *other* checkbox — v2 sets
      `CacheIsPowerProtected`, the value Device Manager's "turn off buffer
      flushing" really uses).
    - **Comfort / Windows 11:** NumLock at start-up, skip the lock screen, remove
      the Chat icon, hide "Recommended" in Start.
    - **Network / audio:** TCP (ECN and timestamps off, SACK on), QoS reserve
      0 % (described honestly: Windows does *not* permanently reserve 20 %),
      MMCSS "Audio" task profile, `SystemResponsiveness` 0 (shared with the
      network-throttling tweak — reverting one keeps the value while the other
      still needs it).
    - **Disk Cleanup (one-time):** safe categories only, then
      `DISM /StartComponentCleanup` **without** `/ResetBase`. Deliberately not:
      Downloads, Recycle Bin, Windows.old, shader cache, old drivers — v1's
      `/sagerun` profile included several of those.
    - **Deep Clean** (Settings, every target opt-in): browser *caches* of
      Chrome/Edge/Firefox (never passwords, history, bookmarks, cookies),
      Windows Update download cache (the service is stopped and restarted
      around it), thumbnails, prefetch, CBS logs / minidumps / error reports,
      and the Recycle Bin (extra confirmation). Only really deleted files count
      as freed; files in use are skipped.
    - **Services Manager** (own window instead of opening services.msc): v1's
      list of 29 rarely needed services with category, a safe/caution rating and
      live status / start type. Disabling remembers the **original start type**
      (incl. "Automatic (delayed)"); "Enable" restores it, or the Windows
      default — v1 always set "Manual", so e.g. the print spooler no longer
      started on its own. Changed from v1: the Xbox services are "caution"
      (Game Pass PC games need them), the touch-keyboard service is gone (it
      doesn't exist since 24H2, and its successor must never be disabled —
      typing in Search and apps breaks), the 24H2/26H2 AI host was added.
    - **Dashboard:** an **Optimization Score** — the share of *safe*, applicable
      tweaks the verifier finds active on the system right now (moderate /
      advanced tweaks don't count, so a high score never pushes towards risky
      ones; one-time actions and either-or choices like the DNS provider are
      left out) — and a **monitor advisor** that compares each display's refresh
      rate with the highest one the driver offers *at the current resolution*
      (v1 used the adapter's maximum over all resolutions). On the test PC it
      immediately found two monitors running at 50 Hz instead of 60 Hz.
    - **Drift check at start:** tweaks the app applied that are no longer (fully)
      active — typically reset by a feature update — are listed with the choice
      *re-apply* (after a registry backup), *mark as not applied*, or *ask
      again next time*. Failed checks never count as drift.
    - **Registry backup** covers what the new tweaks touch, plus v1's later
      additions (Explorer folder views, per-device keys of the GPU and every
      disk): 43 fixed branches + the device keys (45 on the test PC).
  - **Windows 11 26H2** (installed on the test PC the day before): the update
    re-provisioned the Microsoft 365 Copilot app (Office Hub) and the
    discontinued Dev Home, and runs a new auto-start AI host (`WSAIFabricSvc`).
    New tweaks, each using Microsoft's documented policies where one exists
    (Policy CSP *WindowsAI*): **Click to Do** off (computer + user),
    **Paint AI** off (Cocreator, Image Creator, generative fill / erase, remove
    background), **Notepad AI** off, the **AI host service** off, and removal of
    the **Copilot app + Dev Home** including their provisioned packages (so the
    next feature update doesn't bring them back). Updated: **Recall** now also
    sets `AllowRecallEnablement=0`, which removes the component and its
    snapshots on the next restart; **on-device text/image generation** also
    sets the AppPrivacy *Force Deny* policy apps can't override; **Remove
    Bloatware** also removes the provisioned packages, Mixed Reality and the
    remaining ad apps. Enterprise-only policies (e.g. removing the Copilot app
    via policy) were deliberately not used — they do nothing on Home/Pro.
  - **Not ported, on purpose** (checked against v1's code): the four NVIDIA
    registry tweaks (threaded optimization, max pre-rendered frames, shader
    cache size, PowerMizer) — current drivers keep these settings in their own
    profile database (NVIDIA Control Panel / App), so the registry values do
    nothing; *Spatial Sound off* — it writes a value Windows doesn't use for
    that setting (and spatial sound is off by default); *Audio device power
    save* — undocumented values, and USB selective suspend is already covered.
  - **Memory stage** result is now the bandwidth peak (see the memory bullet
    above) — found while re-running the scripted-GPU tests.
  - Totals: **106 tweaks** (105 with a live check — Disk Cleanup is a one-time
    action), 90 of them "safe". Tests: **313 checks in 15 suites**, including a
    PowerShell *parse* check of all 303 command snippets (apply, revert,
    verify) and of the Services Manager scripts. The tests that need Afterburner's
    process or shared memory now use test names, so they run safely next to a
    running Afterburner.

- **Round 10 — first real use** (findings from a full day of real use on the
  test PC: select-all apply of 97 tweaks, two complete Auto-Tunes, the cleaner):
  - **No console window.** Started any other way than `GameOptimizerPro.bat`
    (double-click on the `.py` → Python install manager → `python.exe`), the
    admin relaunch and the language restart re-used that `python.exe`, and a
    black console stayed open. They now start `pythonw.exe`; a console that
    exists only for the app (double-click) is left by relaunching windowless.
  - **Auto-Tune: a failed final test is no longer the end.** It used to save an
    *untested* "conservative" profile (core −1 step, power +5 %, memory 0),
    marked it stable and stop. Now it takes one step back and runs the final
    test again — core −1 step, then the memory offset halved (a user-set
    memory offset, e.g. +1000 MHz, was in play in the real run), V/F undervolt
    +25 mV first, power limit −5 % first for thermal failures — up to 4 times.
    Only a configuration that PASSED is saved; if none does, nothing is saved
    and the card goes back to stock with a clear message. The PC is kept awake
    (no sleep / screen-off) while a tune or the stress test runs.
  - **Either-or tweaks.** "Select all" ticked all three power plans and both DNS
    providers — applied one after another, the last one silently won (the log
    shows Cloudflare *and* Google applied). Power plan and DNS are now
    either-or groups: select all / "All Safe" take one (the presets' choice or
    the one already applied), ticking one unticks the others (badge
    "⇄ entweder-oder"), applying one replaces the other in the app's state,
    and old states with both are cleaned up. A choice changed outside the app
    (e.g. DNS switched by hand) is taken over instead of being "re-applied".
  - **Power plans.** "Ultimate Performance" ran `powercfg -duplicatescheme` on
    every apply — **15 copies** of the plan were found on the test PC. It now
    reuses an existing one and removes the extra copies. The high-performance
    plans keep the screen on and never go to sleep / hibernate on mains power
    (battery values untouched); "Display sleep = 15 min" no longer writes into
    them (the active Ultimate plan turned the screen off after 15 minutes).
    The plan checks include this, so an older installation shows the plan once
    as "not fully active" and offers to re-apply it.
  - **Optimizer list:** the mouse wheel works over the tweak rows (it only worked
    in the empty strip next to them — moving onto a row fired `<Leave>` on the
    canvas, which removed the binding); **one batch at a time** — a second click
    while the Disk Cleanup ran (minutes) started a parallel batch that applied
    every tweak twice; long tweaks show "läuft …"; the "⟳ einmalig" badge sat on
    every safe tweak — it now marks only one-way actions.
  - **Tweaks that reported wrongly:** *network adapter power saving* worked on
    all 14 adapters but reported ✗ (the class key has a locked `Properties`
    subkey; its access error set PowerShell's exit code); *RSS* now only touches
    adapters that offer it and logs why otherwise; *memory compression* failed
    when SysMain was disabled (by the Prefetch/Superfetch tweak) — SysMain is
    started briefly and disabled again; *audio enhancements* wrote
    `PKEY_AudioEndpoint_Disable_SysFx = 0`, which means **enabled** (documented:
    1 = disabled; inherited from v1) — and on the test PC none of the values
    had arrived on any of the 19 endpoints, so this tweak and *exclusive mode*
    now check after writing and say so honestly instead of a false ✓ (how to
    make Windows' audio service keep them is left for the next live test);
    PowerShell output is decoded in the OEM code page (umlauts in the log).
  - **Status checks:** a check that throws (e.g. `Get-AppxPackage -AllUsers` or
    `bcdedit` without admin rights) now counts as *unknown*, not *inactive*;
    the TCP auto-tuning check only understood English Windows (German:
    "Autom. Abstimmungsgrad Empfangsfenster") and always said "inactive".
  - **Drift dialog:** one decision per tweak (ticked = apply again, unticked =
    stop asking) instead of one yes/no for all — re-applying the power plan
    must not force back a taskbar layout changed on purpose.
  - **Temp cleaner:** only files older than 24 hours (like CCleaner). It deleted
    every unlocked file in `%TEMP%` — including the working files of a running
    program: found when a clean-up during the live test wiped the whole
    scratchpad of the test session.
  - **Tests are in the repository now** (`tests/`, 389 checks in 16 suites; CI
    byte-compiles them). They lived in that scratchpad and were rebuilt from the
    session transcript — the loss is exactly the case the 24-h rule prevents.

- **Round 11 — memory overclock in the Auto-Tune:** the user wants memory OC in
  the tune. The tuner's memory stage (bandwidth-measured, result = bandwidth
  peak) is now a checkbox in the GPU tab ("Speicher mit übertakten", on for OC
  and OC + UV, off for "Nur UV"); the fixed "Mem Offset" field — a value that was
  never searched and applied to every step — is replaced by "Mem Max" (from the
  generation table: +1500 MHz on an RTX 4080). Steps start at 250 MHz and are
  halved after the first drop down to ±25 MHz (±5 would add minutes for nothing);
  "Mem Max" itself is tested once and nothing right next to a failed offset is
  tested again. The final test runs with core + memory + power limit, and its
  back-off alternates core and memory. Tests: `tests/test_memstage.py`.

- **Round 12 — new interface, audio API, FurMark 2 / 3DMark** (from the user's
  screenshots: columns that didn't follow the window width, the tuner log only
  visible after enlarging the window, the mouse wheel over the Auto-Tune tab
  jumping to "Profiles", a FurMark location lost after a restart, BIOS cards cut
  off, the audio errors back after every restart):
  - **The whole UI is rebuilt with CustomTkinter**: sidebar navigation with
    icons (Segoe Fluent Icons), dark title bar, rounded cards, an app icon. Every
    page follows the window width — texts wrap (the preset list and the BIOS
    guide used fixed wrap widths), card grids reflow between 1 and 4 columns.
    Window size and position are remembered (only restored when that spot is
    still on a connected monitor); Ctrl+1 … Ctrl+9 open the pages. Pages are
    built on first use (optimizer and GPU tuner in the background right after
    start-up); a page that fails to build shows its error instead of taking the
    window down; hidden pages stop reading sensors. Long lists stay plain tk
    with drawn check boxes — measured: 70 rows of CustomTkinter check boxes took
    4.5 s to build and 0.4 s per window resize.
  - **GPU tuner:** settings on the left (scrolling), live tiles, graph,
    progress and the **tuner log on the right — visible at every window size**.
    Auto-Tune / Profiles / Manual switch with a segmented bar (the ttk notebook
    flipped tabs with the mouse wheel). Manual offsets: slider + exact field.
  - **Optimizer:** search box, the whole row toggles, rows highlight under the
    pointer, the "✓ aktiv" badge follows the live status check, sections in a
    segmented bar; the log stays visible.
  - **Autostart and Services manager are pages** of the main window (they were
    separate windows).
  - **FurMark 1 and 2:** found next to the app (FurMark 2 preferred when both are
    there), in install folders or where the user pointed it — **remembered
    after a restart** (it was lost); shown with version (FurMark 2's
    `furmark.exe` carries no version, the GUI exe's is shown). FurMark 2 gets its
    own command line with a demo choice (OpenGL / Vulkan, Knot); resolution
    (incl. the native one), duration and demo are remembered.
  - **3DMark:** found in every Steam library (`libraryfolders.vdf`) or a
    standalone install, started through Steam (`steam://rungameid/223850` — the
    Steam version refuses a direct start). Command-line stress tests exist only in
    the Professional Edition (`3DMarkCmd.exe` is detected); otherwise the test
    is picked in 3DMark.
  - **Recording during external tests:** while FurMark or 3DMark runs, the app
    records peak temperature, average and minimum clock under load (samples
    below 50 % GPU load are left out), maximum power and driver resets (TDR from
    the event log) and ends with a summary — "no driver reset" or "not stable!".
  - **Audio tweaks fixed for real:** Windows 11 26H2 locks
    `MMDevices\Audio\Render\{id}\Properties|FxProperties` even for
    administrators (a probe write failed despite the ACL). Both audio tweaks now
    go through the Windows audio policy API (IPolicyConfig COM — what the Sound
    control panel uses), set every active/unplugged render endpoint and read the
    value back; verified live on 3 endpoints, the values also appear in the
    registry. The status checks read the active endpoints.
  - **Drift dialog:** a re-apply that fails is marked "not applied" — the dialog
    asked again at every start.
  - **Remnant scan:** one "Ultimate Performance" plan (activating it creates a
    copy) is normal and no longer reported — only duplicates.
  - **"Load the tray-default GPU profile at start"** was a checkbox without any
    function; it is saved now and honoured at start-up.
  - **Found while testing the new UI on the real PC:**
    - *Crash:* a CustomTkinter dialog that calls `resizable()` re-colours its
      title bar 10 ms later — a transient dialog closed before that took the
      whole process down (access violation, reproduced in isolation). The
      dialogs don't call it any more.
    - *Speed:* CustomTkinter's scrollbar runs `update_idletasks()` on every
      redraw (also while being created), and a `<Configure>` binding on the
      window fired for every widget inside it (~2600 Python callbacks per page
      layout, and again on every resize); a font given as a tuple is loaded per
      label (17 ms for each emoji icon). Own slim scrollbar, a window-only
      bindtag and shared fonts: the optimizer page builds in ~0.17 s instead of
      ~1.4 s (measured unmapped); first visits of the pages 30–550 ms with real
      hardware, afterwards instant.
    - *Looks:* active tweaks were shown in the category colour — red for
      Windows, which read like an error next to the green legend. Status dots
      are green / amber / grey now, names stay white, Windows is blue; the
      preset icons are drawn as colour emoji (Tk renders emoji flat); disabled
      coloured buttons fade; grids balance their rows (3 + 3, not 5 + 1); the
      sidebar drops the system card when the window is too low; the Autostart
      "Status" column showed the long description instead of "✓ Safe" (old bug).
    - *Stress test, live:* FurMark ran at exactly 162 FPS with 41–45 % GPU
      load (189 W) — the NVIDIA App's frame limit; with the limit off, at
      165 FPS: the driver's forced VSync + G-SYNC, which FurMark's own
      `--vsync 0` can't override. A normal gaming setup, so the app adapts:
      FurMark 2 now runs with 8x MSAA by default (GPU-bound under the cap:
      100 % load, 274 W, 126 FPS at 1080p), reads FurMark's own stats (FPS,
      max GPU load — `furmark.exe` is a console program, which also opened a
      console window before) and explains a low load (FPS limit / VSync)
      instead of only saying "no load". The internal test was unaffected
      (compute load, no frames): 100 % load, passed.
    - *Test:* `test_real_profile.py` read the base V/F curve from `[Startup]`,
      which Afterburner empties when "apply overclocking at system startup" is
      off (seen on the test PC); the app itself already took it from the
      profile slots — the test does the same now.
  - **New dependency `customtkinter`** (`requirements.txt` / `install.bat`). An
    update via `git pull` without `install.bat` no longer ends in a silent
    non-start (pythonw has no console): the app asks once and installs it.
  - Tests: `tests/test_round12.py` (logic: settings, FurMark/3DMark detection
    and command lines, audio API scripts, remnant scan, the install guard) and
    `tests/test_ui_round12.py` (the whole new UI with fakes under a real main
    loop), `tests/live_stress_check.py` (live: internal test + FurMark with
    the real app); the older UI suites follow the new structure — 527 checks
    in 19 suites, all green.

- **Round 13 — the All-round tuner ("Rundum")** (the user: "one tune that does
  everything, ends with a 5-minute test, reads the scores, compares and keeps
  searching until it has the best result" — with Yuri "1usmus" Bubliy's HYDRA as
  the model; the user chose a goal switch, per-point curve tuning and FurMark as
  the final test):
  - **Per voltage point** (`core/curve_tune.py`): a boost-load probe at stock
    finds the highest voltage the card reaches (RTX 4080: 1075 mV); from there
    every 50 mV down to 850 mV each point is searched on its own — curve flat at
    the point, the stress worker's new **`boost` mode** (light enough to stay
    under the power limit, so the card sits exactly on the point), every result
    checked; +15 MHz until a failure, halved to 5 MHz, never re-testing above a
    failure. Start: the last stable profile, else a cautious value for the card's
    generation. 30 MHz safety, 60 MHz where the driver had to restart. A pass
    only counts when the card really ran at the point (median voltage within
    10 mV — both ways); "Core max" itself is tested and reported.
  - **Own V/F curve** (`VFCurve.with_anchor_curve`): offsets interpolated
    between the points, below the lowest one the smallest measured offset;
    every point above the top (or the chosen cap) is written **100 MHz lower** —
    the card adds offsets to its *live* curve, which shifts with temperature and
    not evenly (−30 MHz at 1075 mV, +60 MHz at 920 mV on the RTX 4080), so a
    curve flat in the file was not flat on the card (875 mV under test, the card
    ran 920 mV). The same for the classic V/F flatline.
  - **Curve check:** 30 s FurMark on the new curve with memory at +0, before the
    memory is touched; a crash lowers only the point where the card ran.
  - **Memory with the whole card under load** (the user's plan after run 1):
    +500 (RTX 40; per generation) → +1000 in 100-MHz steps, each step FurMark and
    the worker's verified memory copies at the same time; 100 MHz safety when a
    step failed. RTX 40 "Mem max" is +1000 now.
  - **Goal by benchmark:** FurMark 2 (`furmark.run_benchmark`, 1080p, 8x MSAA —
    GPU-bound even under an FPS cap) on curve caps every 25 mV. Max = highest
    score (within 1 % the frugal one; a higher power limit only when stock ran
    into it); Balanced = at least half of the measured gain, the most points per
    watt of those; Efficiency = stock performance (≥ 99 %) at the lowest power.
    A crashed candidate: memory −100 first, then the curve, all candidates again.
  - **Final test:** 5 min FurMark + 2 min compute-checked mixed load; on a
    failure one targeted step back (the points around the voltage where the card
    failed / memory −100 / too hot: power limit, then a lower cap) and again —
    only what passed is saved; then the same 60-s benchmark again for a fair
    before/after. A benchmark that ran far too short or far below stock stops
    the tune ("driver not clean after a crash — restart the PC"), and after
    every crash the driver gets 20 s.
  - **Report** (log, `logs/curve_report_*.txt`, "Report" button): every point
    found → used, every candidate with points/W, before → after, final test,
    recommendations ("Core max" reached, a point below the card's minimum load
    voltage, clock stretching, temperature). Profiles keep the curve
    (`curve_points`, `curve_cap_mv`); the profile list shows "Curve" and the
    points; Tune History lists the run as "Rundum".
  - **Live on the RTX 4080, three runs:**
    1. The point search worked and repeats within a few MHz between runs, but
       the memory stage of the time took +1500 straight from the bandwidth peak
       (no margin; GDDR6X hides errors from a bandwidth test by retrying) — the
       first FurMark candidate showed **green speckles, all screens went black**
       (nvlddmkm 13/14, FurMark died), and the tune went on measuring on a
       broken driver (FurMark ended after 10 of 60 s with 398 instead of ~7200
       points) until the user aborted. Led to: memory with the whole card under
       load, the curve check, candidate step-back, the plausibility stop, the
       crash pause and nvlddmkm 13/14 counting as a crash.
    2. Stopped at stock clocks: nvlddmkm **153** had been counted as a crash —
       the driver logs it at the end of *every* stress step (17x in run 1
       without any problem). Only Display 4101 and nvlddmkm 13/14 count now.
    3. **Passed:** curve 1075 mV → 2940, 1025 → 2847, 975 → 2741, 925 → 2560
       MHz (Core max reached there); memory +500 … +1000 all passed under
       whole-card load; Balanced chose "flat from 1050 mV"; FurMark 7269 → 7538
       points (+3.7 %), 257 → 265 W, average clock 2790 → 2880 MHz; 5-min final
       test and compute check passed without a step back. 3DMark Speed Way
       afterwards: 7622 (RTX 4080 average: 7424).
    - Also found live: NVIDIA sets "SW thermal" for about a second whenever a
      load ends or Afterburner applies a profile (seen at 46–53 °C) — a good
      step failed as "throttling". A slowdown counts only after the ramp-up and
      when it lasts 3 s; the log names the reason.
  - **GPU table** (`core/gpu_defaults.py`): RTX 50 (Blackwell) added — it fell
    back to the "unknown" values (sources: TheFPSReview, RTX 5080 FE +350 MHz /
    memory +500, RTX 5090 FE +270 / +1500); cautious **start values per
    generation** (core and memory) for the All-round tuner; RTX 4080 core max
    +250 (the live run hit +220); hot GDDR6X on RTX 3080/3090 memory max +800;
    "RTX 5000 Ada" (workstation) isn't taken for an RTX 50. AMD (RX 5000–9000)
    and Intel Arc are marked not supported: the GPU tab says so and points to
    AMD Adrenalin / Intel Graphics Software instead of failing (the tuner needs
    Afterburner's NVIDIA curve and NVML).
  - **NumLock tweak:** Windows rewrites `InitialKeyboardIndicators` at sign-out
    from the live keyboard state ("2147483650" → "2", both mean NumLock on); the
    status check compared the exact string, so the drift dialog asked after
    every restart. It checks the NumLock bit now.
  - **GPU tab:** at the minimum window size the four mode buttons use short
    texts (OC / UV) instead of clipping; an abort is written into the run's log
    file (it only reached the UI).
  - Tests: `tests/test_round13.py` (search, margins, goals, report, the own
    curve in an Afterburner profile, the FurMark benchmark with a fake process,
    the worker's boost mode, the driver-event filter, the GPU table, and the
    whole tune against a simulated card that reads its curve from the profile
    file the real code wrote — memory edge, crashed candidate, implausible
    benchmark, failing curve check, driver reset, no FurMark, no voltage
    readings, power-limited card, abort, English) and `tests/test_ui_round13.py`
    (GPU tab: modes, goal switch, start configuration, AMD / no NVML) — 711
    checks in 21 suites, all green.
- **Round 13 follow-up — live values through the whole tune** (the user, about
  the memory stage of the live run: "while FurMark runs the values are not read,
  and MAHM at the bottom left turns orange now and then"):
  - Measured first: a read-only logger (Afterburner's shared memory and NVML
    every 0.5 s) while the user ran FurMark 2 for 79 s at full load (2880 MHz,
    266 W, 65 °C) — Afterburner stamped fresh values every second, the voltage
    never dropped out, NVML never took longer than 18 ms. FurMark itself was
    not the cause.
  - The cause was the tuner's own timing: the GPU page's tiles and graph only
    got values from inside a measured step. Every memory step restarts
    Afterburner, waits 2 s, starts FurMark, waits 4 s and after the step waits
    for FurMark to end — about 18 s of every 63-s step without new values (run-3
    log), part of it with FurMark already or still running. A tune now keeps the
    page live: when no step value came for 1.5 s, a light loop reads the monitor
    and sends one (`AutoTuner._live_loop`; the NVML reads keep no state, so the
    measurements are not affected).
  - The orange dot was Afterburner being restarted on purpose (the reader lets
    go of its section for every step). `MAHMReader.restarting` tells that apart
    from a real outage: the status dot is **blue** while the tuner restarts
    Afterburner (and up to 10 s after, until the new section delivers) and
    orange only when it is really gone; the dashboard says "Afterburner
    restarting …" instead of "enable voltage monitoring in AB"; the GPU page
    says "Afterburner applies the settings (restart) …" and "FurMark starting
    …". The status dots refresh every second (was 5 s).
  - Tests: the live loop (quiet during a step, fills a 3.2-s gap, stops with
    the run), the restart announcement, `restarting` (suspended / right after
    resume without a section / a real outage after the grace time), the status
    dot colours and the dashboard hint — 724 checks in 21 suites, all green.
- **Round 13 follow-up 2 — a finer curve, the whole-card memory test in every
  mode, more room per point** (the user: "finish the open points — build it,
  simulate it, done"; built and tested in the simulation only, while the user
  was gaming):
  - **Points every 25 mV** (was 50; `TunerConfig.curve_anchor_step_mv`, GPU tab
    "Punktabstand" 25 / 50): between two measured points the curve was only
    interpolated, and the stable offset is not linear in the voltage (RTX 4080
    live: +165 at 1075 mV, +177 at 1025, +206 at 975, +220 at 925). Each point
    starts at its neighbour's result, so the closer points need fewer steps. A
    point the card stays *above* under load (875 mV, the card ran at 920) is
    below its minimum voltage — `AnchorResult.below_floor` — and every lower
    point is skipped instead of tested one by one. The start dialog's estimate
    counts the points (25 mV ≈ 50–80 min, 50 mV ≈ 40–60).
  - **"Core max" per point +100 MHz for the All-round mode**
    (`GpuDefaults.curve_core_max_mhz`; RTX 4080 +350 instead of +250): every
    point is searched up to its first failure, so the limit is only a sanity
    bound — in run 3 the old limit, not a failure, ended the search at 925 mV.
    The classic modes keep their limit.
  - **OC / UV / OC + UV / memory-only use the All-round tuner's memory stage**
    (`_mem_stage_full` takes the apply function of the mode): +500 (per
    generation) → "Mem max" in 100-MHz steps, every step with FurMark 2 and the
    verified memory copies at once, 100 MHz safety after a failure, no profile
    when even +0 fails. The old stage took the bandwidth peak of a memory-only
    load — the method that gave +1500 and green speckles in the first live run;
    it is removed together with its settings (`mem_oc_step_mhz`,
    `mem_min_step_mhz`, `mem_bw_drop_pct`). A failed final test takes memory
    back by 100 MHz (was: halved), like the All-round tuner. The GPU tab passes
    FurMark 2 and the generation's start value to these modes too; a step
    without bandwidth numbers no longer logs "0 GB/s".
  - Tests: anchors every 25 mV and the floor (`test_round13` A), the curve
    "Core max" for every generation, two new simulated runs (E19: nine points,
    each found to ±5 MHz, at most 6 steps per point; E20: a card that never goes
    below 920 mV — one test at 900 mV, 875 / 850 skipped, the report explains
    it), the classic memory stage rewritten (`test_memstage`: +500 → failure →
    −100, FurMark during every step, start value failing, +0 failing → no
    profile, "Mem max", memory-only, final test −100), the stage tests and the
    GPU tab (point spacing, estimate, Core max per mode, classic config) — 746
    checks in 21 suites, all green.
  - **The test battery while a game runs:** the three suites that map real
    (invisible, alpha-0) windows for real geometry could take the focus from a
    fullscreen game. `tests/run_hidden_desktop.py` runs a test on its own Windows
    desktop that is never switched to (CreateDesktop + SetThreadDesktop before
    tkinter is imported — windows belong to their thread's desktop; checked: the
    Tk window has its real size and is not among the user's desktop windows);
    `run_all_tests.py` uses it for those suites.

- **Round 14 — leaner, every BIOS platform, updates from GitHub** (the user:
  "the games thing is unnecessary, remove it, the FPS thing too; the BIOS guide
  should list MANY boards and show the matching one; a tick box in the settings
  to check for updates that downloads them from GitHub; switching tabs feels a
  bit laggy — remove the stuff, look at the code to make it more robust, then
  test everything"):
  - **Removed:** the per-game profiles with the background process watcher
    (`core/game_monitor.py`), CPU pinning (`cpu_pinning.py`, `cpu_topology.py`),
    the FPS/frametime capture (`fps_capture.py`, Diagnose tab) and the old
    release checker (`update_checker.py` — the version stays "2.0", so it could
    never find anything). The **tune history** moved into the GPU tuner (view
    "History", now with the memory offset; logs are read when the view opens;
    odd file names sort by their time).
  - **Page switches 2–3× faster** (measured on the visible desktop: revisits
    37–129 ms → 12–47 ms): pages stay placed and stacked in the content area and
    a switch only raises one (packing a page in and out re-mapped every widget);
    only the two sidebar buttons that change are redrawn (all 11 were, ~8 ms);
    the pages are built in the background after the start — only while there was
    no click / key for 1.5 s (a first visit cost up to 465 ms).
  - **BIOS guide for every platform** (`core/bios_guide.py` rewritten): 16
    platforms from Intel 8th gen / Ryzen 1000 to Ryzen 9000X3D / Core Ultra 200S
    plus the basics for anything else (158 settings); the hardware detection only
    pre-selects the platform (CPU name → platform, laptops → basics) and the board
    maker; every setting has the **menu path for ASUS / MSI / Gigabyte / ASRock**
    (generic otherwise, with the BIOS search hint). Content fixed where the old
    guide was wrong or vague: C-states stay on (the "Gaming: Disabled" advice
    lowers single-core boost on Ryzen), 7000X3D only via the Curve Optimizer,
    the 13th/14th-gen microcode 0x12F (Vmin shift) first, Intel Default Settings,
    200S Boost, X3D core parking, Secure Boot for anti-cheats; the "G-Sync in
    the BIOS" setting and the unrelated registry "tips" (HAGS as ReBAR, timer
    resolution as Thread Director) are gone.
  - **Honest BIOS detection** (`core/bios_detector.py` rewritten, 0.3 s instead
    of several seconds): RAM profile from the configured speed vs. the JEDEC
    ceiling of its DDR type (the old "> 3200 MHz" called every DDR5 at stock
    "active"), **Resizable BAR from NVIDIA's BAR1 aperture** (16 GB = on, 256 MB =
    off; the old check combined HAGS with a WMI value that never exceeds 4 GB),
    Secure Boot from the UEFI state (no admin needed), CSM only where certain
    (Legacy boot = on, Secure Boot on = off). PBO, C-states, fast boot: no
    reliable signal from Windows — grey instead of a guess. The status is shown
    for the detected platform only.
  - **Updates from GitHub** (`core/updater.py`, `tools/apply_update.py`,
    `ui/update_flow.py`, `build.json`): Settings → "Check for updates at
    start-up" (default on, 8 s after the start) and "Check for updates now".
    A release is identified by the build number in `build.json` (raised with
    every release). Zip install: download, safe unpack (no zip-slip), check
    (build and files), then "restart now?" — "no" installs it at the next start
    (before anything else runs), never during a tune; the installer (from the
    NEW version) waits for the app's process, backs up every file it replaces
    or removes (`logs/update_backup_<build>/`), copies, removes app code the new
    version no longer has, puts the old state back if a copy fails, runs pip
    when `requirements.txt` changed, logs to `logs/update.log` and restarts the
    app. `logs/` and `profiles/` are never touched. A git checkout is updated
    with `git pull --ff-only` (clean tree only); "no" is remembered per build
    for the automatic check.
  - **Checked against the real GitHub repository** after the push: a zip
    install claiming build 13 (temp folder) found build 14, downloaded it
    (0.4 s), and the real installer replaced the files, removed a stale module,
    kept logs/ and profiles/ — the files then matched GitHub main. That run
    showed one waste: `requirements.txt` differing only in line endings (CRLF in
    a git checkout, LF in the zip) started `pip install`; line endings don't
    count any more.
  - **Close behaviour:** Settings → "Keep running in the tray when closed"
    (default on); off = the X quits. Without a tray icon (pystray missing) the X
    used to hide the window with no way back — it quits now.
  - **Afterburner setup checks** "starts with Windows" and "applies the
    overclock at system startup" (the `[Startup]` section of the card's profile):
    without them a reboot starts the card at stock unless GameOptimizerPro runs —
    on the user's PC both were off.
  - **Robustness:** 52 bare `except:` → `except Exception:` (Ctrl+C / exit pass
    through), timeouts for every `schtasks` call (30 s) and the pip install
    (600 s), 20 unused imports removed, the setup check survives a failing row.
  - Tests: `tests/test_round14.py` (CPU → platform for 30 CPU names, every
    profile complete, vendor paths, the detector's rules, the updater against a
    fake GitHub incl. zip-slip / wrong build / broken download, the installer on
    temp folders incl. rollback and the whole script, pip only for a real
    requirements change, every update dialog path,
    tune history, close behaviour); `test_ui_round12` (history view, BIOS page,
    page stack, two-button redraw, settings switches, Afterburner rows);
    `tests/run_hidden_desktop.py` runs the suites that map real windows on a
    never-shown desktop — the whole battery can run while the user plays —
    828 checks in 22 suites, all green; screenshots of every page at 1400×900
    and 1000×700 checked.

- **Round 14 hotfix — the app didn't start** (the user: "Afterburner starts but
  the optimizer doesn't come"): the tray menu's "Beenden" action got a third
  parameter (`relaunch`, for restarting after an update). pystray accepts menu
  actions with at most two (icon, item) and raised `ValueError` while building
  the menu — after the start-up profile had already restarted Afterburner, before
  the window, and pythonw shows no error. `_exit(icon, item)` is the tray action
  again; the restart lives in `_shutdown(relaunch)`. The unit tests built the
  app object by hand and never the real tray menu — new `tests/test_app_start.py`
  runs the real start path (`main()` → tray menu → main window) in a child
  process on the hidden desktop, with nothing applied (verified: with the bug put
  back it fails with exactly this ValueError). 834 checks in 23 suites.

- **Round 14 — clear tuner settings** (the user: "the names aren't clear — in
  which steps do we go now? Name them more precisely, if need be with a '?' that
  opens a small window with the explanation, both languages"; build 15):
  - Every field of both parameter cards renamed after what it does, the same
    names in the start dialogs and the report: Takt-Schritt / Clock step,
    Takt-Plus max. (je Punkt) / Max clock gain (per point), Power-Limit min.,
    Temperatur-Grenze, Testdauer je Schritt, Abstand der Messpunkte, Sicherheits-
    abzug, Endtest: FurMark / Rechenprüfung, Speicher-Plus max., Afterburner-
    Profilplatz.
  - A **"?"** next to every field and the memory tick box (`HelpTip`, new in
    `ui/components.py`): pointing at it or a click opens a small window with the
    explanation — what the value does, the step sizes (+15 MHz, halved to 5;
    memory +500 then 100-MHz steps; power limit in 5 % steps), the preset.
  - The All-round card shows **"How the tune runs"**: the six steps with the
    values set right now (point spacing, test time, safety margin, memory range,
    final test), updated as soon as a value changes; the classic start dialog
    lists every value and is bilingual.
  - The classic dialog shows step and test time now; the report says "max clock
    gain per point" where it said "Core max".
  - Tests: names, a "?" for every setting (10 in the All-round card, 9 in the
    classic card), the help window opens and closes (hidden desktop), the
    procedure box follows the values; the build check reads build.json — 841
    checks in 23 suites, all green.

- **Round 14 — one update check at a time** (build 16; the user tried the update
  live on a build-14 copy: it worked, but two "update ready" windows came up —
  "Check for updates now" clicked right after the start, and the automatic check
  8 s later ran next to it): the lock was released when the download finished,
  before the question; the automatic timer then fired inside the open dialog's
  event loop. The lock now holds until the question is answered; a second start
  says "the update check is already running". Test: a check started from inside
  the open question asks nothing — 842 checks in 23 suites, all green.

- **Round 14 — tune history: every value, the reason, deleting** (build 17; the
  user: "some values from yesterday are missing — if those are stock values,
  show them; and the history should be deletable, single runs or all"):
  - Finished runs: stock values are shown as such (+0 MHz memory, 100 % power)
    instead of "--" (the view hid 0 and 100).
  - Runs without a profile no longer show only "--": their values come from the
    steps — the configuration tested last ("Final test: +179MHz | 96% pwr |
    Mem+500MHz"), the stage results, the All-round tuner's own curve (top point
    against its stock clock), the baseline voltage, the highest temperature seen.
    A new column "Note" says why: final test failed (with the error), stopped,
    driver reset at the boost probe, interrupted (app closed / crash). On the
    user's six real runs every value is filled in now.
  - Unknown values stay `None` ("--") instead of a made-up 0; log lines are read
    by their level tag; the selected run's reason heads its log.
  - **Delete selected** (Ctrl/Shift click for several, or the Delete key) and
    **Delete all**, each after a question: the tune log and — for the All-round
    tuner — its report (`TuneHistory.delete` / `delete_all`; only tune_*.log in
    logs/ is touched, saved GPU profiles stay; a log a running tune still writes
    is skipped and the view says so).
  - Tests: the real log lines of the live runs (failed final test, TDR at the
    boost probe, cut-off All-round run, finished run without memory / power
    lines, stopped run), deleting one / all / nothing outside logs, the view's
    question and buttons — 853 checks in 23 suites, all green.

- **Round 15 — two modes, a memory check that can't starve, results into any
  Afterburner slot, renaming profiles, gap-free driver-reset check** (build 18; the user during the live All-round test: "we have 4 modes and
  'balanced' is basically OC + UV — do we need all of them?", "why is MAHM blue now?",
  "with 5 results from trying things and no free Afterburner slot — right click in the
  history, 'export to slot 3'?", and: fix whatever the test shows, look at everything
  critically, then a synthetic test and push):
  - **Two modes:** Rundum (now the default) and Schnell (OC + UV). "Übertakten" and
    "Undervolten" are gone — the Rundum goals *Max. Leistung* / *Effizienz* cover them per
    voltage point (the old "undervolt" only lowered the power limit). The never-shown
    FULL / V/F-only / memory-only modes went with them: Stage 3 (V/F undervolt),
    `core/vf_curve.py`, the `vf_*` / `mem_oc_enabled` settings; the memory stage is
    `mem_stage` in both modes; `_final_backoff` lost its V/F voltage. The point lock the
    Rundum search uses (`_apply_vf`) stays.
  - **Results into any Afterburner slot:** right click a run in the tune history (it now
    knows its saved profile, `TuneRun.profile_name`) or a profile → slot 1–5. The menu
    shows what each slot holds (`AfterburnerController.slot_summaries` /
    `ab_profile.slot_summary`, read-only), asks before overwriting, marks slot 1 as the
    user's; a run without a profile shows its reason instead. The profiles' button opens
    the same menu (it used to write into the tuner's slot setting from another view).
  - **Status dots explain themselves** (`HoverTip`, also behind every "?"): blue MAHM =
    Afterburner restarts on purpose for a tuner step, orange = really gone (what to
    check), AB / NVML likewise.
  - **Driver-reset check without gaps:** the event log was read at "elapsed % 10 == 0"
    — a look takes 1–2 s itself, so later looks were skipped now and then, and a reset
    in a step's last seconds was never looked for in that step (the next step got the
    blame). Now each look starts where the last one ended, and a last look closes every
    step.
  - **Memory check that can't starve** (found in the live test): every memory step
    logged "13 GB/s, FurMark 123 FPS" instead of round 13's "231 GB/s, 67 FPS" — 123 FPS
    is FurMark alone. The FurMark window was in front; Windows gives the window in front
    priority on the GPU, and the verified copies (the only thing that SEES a memory
    error) got one compare every ~8 s. Measured live with the user clicking: copies
    alone ~640 GB/s, next to a FurMark in the background ~244, FurMark clicked to the
    front 12.6, back ~244. Now: the tuner starts FurMark without the focus
    (SW_SHOWNOACTIVATE + LockSetForegroundWindow while it starts; `furmark.run_benchmark
    (focus=False)`), the worker compares at least twice a second (a starved copy with an
    error: found in 0.7 s, was > 6 s), and a step whose copies stay below 50 GB/s
    counts as "check too weak" — repeated once, then the memory is not raised any further
    (+0 if nothing was checked properly; never "even +0 fails"). The start dialogs say
    not to click the FurMark windows. (Today's +1000 had passed the full check the day
    before, and the 5-min final test passed.)
  - FurMark is killed **and waited for** on a stop / hang (the next benchmark starts
    seconds later). The remaining English-only texts of the GPU tuner (abort question,
    Afterburner busy, manual offsets, profiles) speak German too.
  - **Profiles** (the user: "renaming the profiles would be nice", "Delete should have a
    frame too", and: today's profile was missing in the comparison, a "Default" was in
    it): "Umbenennen …" (button + right click, `ProfileManager.rename`; a pre-filled
    `TextDialog` that refuses taken / reserved names; the old name keeps finding the
    profile through `renamed.map`, so the tune history's link survives; a case-only
    rename is not "already exists" on Windows); "Löschen" is a framed button; the
    comparison page refreshes its lists every time it is shown (`on_show` — it is built
    in the background at start and only read them then); `list_all` / `load` accept only
    real profiles — `profiles/language.json` and the old `game_profiles.json` were read
    as a profile without a name, i.e. "Default" (the files stay, they're just not
    profiles).
  - Nagle tweak: only connected adapters count — Windows had created the interface key
    of an unused Bluetooth PAN adapter without the values, and the tweak was reported
    "no longer active" at every start.
  - Live All-round run with the round-14 changes (25-mV points, floor skip, Core max
    +350 per point, whole-card memory stage): Round 15 (points every 25 mV, max clock gain +350 per point): 7415 → 7542 points (+1.7 % — the stock run was 2 % higher than the day before; the tuned result is the same, 7542 vs 7538), 2790 → 2880 MHz, 925 mV now 2576 MHz (was capped at 2560), 900–850 mV skipped (the card runs ≥ 925 mV under this load), memory +1000, final test passed.
  - Tests: test_round15 (driver-reset looks with a fake clock and event log, both modes,
    slot summaries against a real-format profile file, history → profile), the slot menu
    in the UI test (right click → slot 3 → asked → written), the dots' explanations, the
    stage tests on the Quick mode, a starved memory copy with an error (found in 0.7 s,
    the old worker: not within 6 s), the weak-check rule, FurMark without focus,
    renaming (old names, case-only, refused names, the dialog) and the comparison
    refresh — 918 checks in 24 suites, all green.

### 🔎 Reviewed, verified NOT a bug

Some reported items were checked against the actual code and left unchanged
because they were overstated or false: the tray `_open()` "race" is already
caught by its try/except; file logging does exist (a daily tweak logfile is
written); the NVML-shutdown "leak" and Afterburner lock-check cost were
overstated. Known low-impact edge cases (CPU topology on >64-thread CPUs,
graph rendering across data gaps, `apply()` trusting a PowerShell exit code
that `-EA SilentlyContinue` can leave at 0) are documented and mitigated by the
live verifier rather than papered over.
