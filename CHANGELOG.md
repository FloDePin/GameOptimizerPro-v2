# Changelog

All notable changes to GameOptimizerPro are documented here.

---

## [2.0] — Final — 2026-09-05

The finalized GameOptimizerPro **2.0** — an all-in-one Windows & gaming
optimizer, built and hardened over many internal iterations and two full
external code-review rounds. Every feature below ships in 2.0, and every
verified bug from those reviews is fixed.

### ✨ Features

- **GPU Auto-Tuner** — Overclock-only / Undervolt-only / OC+UV modes with an
  automated, step-by-step stability test, live voltage/clock/temp graph, TDR
  (driver-timeout) detection via the Windows Event Log, and crash recovery that
  restores the last stable profile on the next boot. Integrates with **MSI
  Afterburner** (MAHM shared memory for real mV readings); GPU-generation
  auto-detection (Pascal→Ada, RDNA 1–3).
- **Windows Optimizer — 71 tweaks** across Windows, Gaming, Network and Audio,
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

### 🔎 Reviewed, verified NOT a bug

Some reported items were checked against the actual code and left unchanged
because they were overstated or false: the tray `_open()` "race" is already
caught by its try/except; file logging does exist (a daily tweak logfile is
written); the NVML-shutdown "leak" and Afterburner lock-check cost were
overstated. Known low-impact edge cases (CPU topology on >64-thread CPUs,
graph rendering across data gaps, `apply()` trusting a PowerShell exit code
that `-EA SilentlyContinue` can leave at 0) are documented and mitigated by the
live verifier rather than papered over.
