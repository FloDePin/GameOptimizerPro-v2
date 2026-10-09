"""
GameOptimizerPro v2.1 — Tweak translations
English descriptions for all tweaks. German lives in tweaks.py as the default.
Lookup by tweak id. If an id is missing here, the German default is used.
"""

# English descriptions, keyed by tweak id.
TWEAK_DESC_EN: dict[str, str] = {
    "remove_cortana":
        "Uninstalls Cortana. Cortana sends data to Microsoft and is unused by most people.",
    "remove_xbox":
        "Removes Xbox Game Bar, Xbox Identity Provider and Xbox TCUI. They run in the background even without Xbox.",
    "remove_teams":
        "Removes Teams Consumer and blocks automatic reinstallation via the registry.",
    "remove_copilot":
        "Disables Windows Copilot and stops it from sending data in the background.",
    "remove_onedrive":
        "Fully uninstalls OneDrive including autostart. Local files are kept.",
    'remove_recall':
        'Turns off Windows Recall via the official policies (no more screenshots of your activity) and REMOVES its components and saved snapshots on the next restart. Privacy critical.',
    "remove_bloatware":
        "Removes preinstalled apps: Candy Crush, TikTok, Disney+, Facebook, Spotify, News, Solitaire, Clipchamp, ToDo, Paint3D and more.",
    "disable_telemetry":
        "Disables all Windows telemetry services (DiagTrack, dmwappushservice). Recommended for everyone.",
    "disable_activity_history":
        "Disables Windows Timeline. Windows no longer records which apps and files you opened.",
    "disable_advertising_id":
        "Disables the Windows advertising ID. Apps can no longer track you across devices.",
    "disable_location":
        "Disables the Windows location service system-wide.",
    "block_telemetry_hosts":
        "Blocks Microsoft telemetry servers in the hosts file. Works even if services are still running.",
    "disable_telemetry_tasks":
        "Disables all scheduled Windows tasks that collect telemetry data.",
    "ultimate_performance":
        "Enables the Ultimate Performance power plan. CPU cores are no longer throttled, and on mains power the screen never turns off and the PC never goes to sleep. Increases power draw. (Creates the plan only once — each apply used to add another copy; extra copies are removed.)",
    "disable_hpet":
        "Disables the High Precision Event Timer. Reduces system latency and improves frame times in games.",
    "timer_resolution":
        "Sets the Windows timer resolution to 0.5ms (default 15.6ms). Better frame timing and less input lag.",
    "disable_prefetch":
        "Disables SysMain. Useful on SSDs, not recommended on HDDs.",
    "visual_effects_perf":
        "Turns off all Windows animations. Windows feels noticeably faster.",
    "disable_search_indexing":
        "Disables WSearch. Reduces background disk access. Search still works but slower.",
    "disable_mouse_accel":
        "Disables Enhance Pointer Precision. Important for FPS: 1:1 mouse movement with no dynamic gain.",
    "disable_sticky_keys":
        "Disables the Sticky Keys dialog (5x Shift). Prevents interruptions mid-game.",
    "enable_dark_mode":
        "Enables dark mode for Windows and apps system-wide.",
    "disable_transparency":
        "Disables transparency in the taskbar and Start menu. Saves GPU resources.",
    "enable_game_mode":
        "Enables Windows Game Mode. Prioritises CPU/GPU for the active game and blocks Windows Update restarts.",
    "disable_game_bar":
        "Disables Xbox Game Bar (Win+G). Prevents background load. Game Mode stays active.",
    "cpu_priority_games":
        "Sets Win32PrioritySeparation to 26. Windows gives active games significantly more CPU time.",
    "mmcss_gaming":
        "Sets MMCSS to High Priority for games. Windows prioritises audio and timer interrupts.",
    "disable_fullscreen_opt":
        "Disables Windows Fullscreen Optimizations globally. Forces true fullscreen for lower input lag.",
    "disable_wu_gaming":
        "Prevents automatic Windows Update downloads and installs. Avoids reboots and performance drops while gaming.",
    "disable_bg_throttle":
        "Disables CPU throttling for background processes. Important for CPU-heavy games.",
    "nvidia_low_latency":
        "Enables NVIDIA Ultra Low Latency Mode. Reduces the render queue to 1 frame. NVIDIA GPUs only.",
    "enable_msi_mode":
        "Enables Message Signaled Interrupts for the GPU. Reduces interrupt latency. Reboot required.",
    "enable_hags":
        "Hands GPU scheduling directly to the hardware. Less CPU overhead and lower input lag. Needs RTX 2000+ or RX 5000+.",
    "clear_shader_cache":
        "Clears the NVIDIA/AMD shader cache (one-time action). Only after driver updates or on graphics "
        "glitches — every game then rebuilds its shaders (the first minutes stutter).",
    "windowed_game_optimizations":
        "Turns on Windows' 'Optimizations for windowed games' (Settings → System → Display → Graphics): "
        "DirectX 10/11 games in a window or borderless window use the modern flip model instead of the old "
        "presentation — less latency, VRR (G-Sync/FreeSync) and Auto HDR in a window too. DX12 games "
        "already use it. Reversible.",
    "dx12_optimization":
        "Raises the GPU watchdog timeout (TdrDelay/TdrDdiDelay to 10s) so demanding DX12 scenes "
        "don't trigger a false driver reset (TDR) under load. NOT an FPS boost — only prevents "
        "needless timeouts/freezes. Reversible.",
    "disable_nagle":
        "Disables Nagle's algorithm on all network adapters. Less latency in online games, a noticeable ping difference.",
    "disable_lso":
        "Disables Large Send Offload on active adapters. Helps with unstable ping in online games.",
    "disable_network_throttle":
        "Disables network throttling under high CPU load. Gives the network stack top priority.",
    "dns_cloudflare":
        "Sets DNS to Cloudflare 1.1.1.1/1.0.0.1. One of the fastest and most privacy-friendly DNS services.",
    "dns_google":
        "Sets DNS to Google 8.8.8.8/8.8.4.4. Globally distributed, fast and reliable.",
    "flush_dns":
        "Flushes the local DNS cache. Fast, with no side effects.",
    "disable_tcp_autotuning":
        "Disables the automatic TCP receive window. Can reduce latency spikes. Slightly lower throughput at 1Gbit+.",
    "enable_rss":
        "Enables Receive-Side Scaling on every adapter that offers it. Spreads network processing across CPU cores. Better on fast connections. (Says so honestly when the driver doesn't expose RSS to Windows.)",
    "w11_classic_context_menu":
        "Restores the classic right-click context menu in Windows 11. No more Show more options.",
    "w11_taskbar_left":
        "Moves taskbar icons to the left (classic Windows 10 layout).",
    "w11_disable_widgets":
        "Disables the Windows 11 widgets panel. Saves RAM and reduces background activity.",
    "w11_disable_snap_suggest":
        "Disables the automatic snap layout popup when hovering the maximise button.",
    "power_balanced":
        "Sets the power plan to Balanced (Windows default). Alternative to High Performance and Ultimate Performance — only one plan can be active. AMD's recommendation for X3D CPUs.",
    "power_high":
        "Enables High Performance. A good balance between performance and power draw; on mains power the screen never turns off and the PC never goes to sleep. (Alternative to Ultimate Performance and Balanced — only one plan can be active.)",
    "disable_usb_suspend":
        "Prevents USB devices (mouse, headset) from entering power saving mode. No more sudden disconnects.",
    "disable_audio_enhancements":
        "Disables Windows audio enhancements (bass boost, EQ etc.). Reduces audio latency and CPU load. Recommended for gaming.",
    "disable_audio_exclusive_lock":
        "Prevents games from locking the audio device exclusively and muting Discord/Spotify.",
    "disable_sound_scheme":
        "Turns off all Windows system sounds (startup, error, notifications). Prevents audio interruptions while gaming.",
    "disable_nahimic":
        "Disables Nahimic audio (preinstalled on MSI boards and gaming laptops). Causes CPU spikes and audio artefacts. Safe if unused.",
    "set_mmcss_audio":
        "Sets MMCSS audio priority to maximum. Windows gives audio threads higher CPU priority, less stutter and crackle under high load.",
    "disable_audio_ducking":
        "Prevents Windows from lowering other sounds during calls/communication. Often annoying when gaming with Discord.",
    # v2.1 additions
    "disable_power_throttling":
        "Prevents Windows from throttling processes to save power. Useful for games whose side-processes would otherwise be throttled.",
    "reduce_process_count":
        "Sets the Svchost split threshold to your RAM size so Windows bundles services into fewer processes. Lowers the total background process count. Safe with 16GB+ RAM.",
    "disable_bing_search":
        "Disables Bing web integration in Windows Search. Start menu search stays local and loads faster.",
    "disable_consumer_features":
        "Stops Windows from auto-installing suggested apps and bloatware (Candy Crush & co. reappear after updates otherwise). Policy only, no uninstall.",
    "disable_hibernation":
        "Disables hibernation and deletes hiberfil.sys (otherwise uses RAM-size on the SSD, e.g. 32 GB). Also turns off the often flaky Fast Startup. Safe on desktop gaming PCs.",
    "end_task_right_click":
        "Adds 'End Task' to the taskbar right-click menu — kill a frozen game instantly without opening Task Manager. Windows 11 22H2+.",
    "disable_delivery_optimization":
        "Turns off peer-to-peer sharing of Windows updates, which otherwise eats upload/download bandwidth in the background — noticeably steadier pings for online gaming. Policy only.",
    "power_pcie_aspm_off":
        "Disables PCIe link power saving (ASPM). The PCIe bus to the graphics card stays at full power instead of dropping into low-power states — marginally more consistent latency at the cost of a little more idle power. Fully reversible.",
    "power_disk_never_sleep":
        "Stops Windows from spinning down drives after inactivity. On systems with HDD(s) this prevents micro-stutter when a background process has to wake a sleeping drive. Fully reversible.",
    "show_file_extensions":
        "Shows file extensions (.exe, .txt, .cfg …) in Explorer. Helps spot disguised files like 'setup.exe.scr' — a small security & convenience win.",
    "show_hidden_files":
        "Shows hidden files and folders in Explorer. Handy for cleaning up and editing app configs stored in hidden folders.",
    "disable_mpo":
        "Disables Multiplane Overlay (registry OverlayTestMode=5). A well-known fix for screen flickering and micro-stutter, especially on NVIDIA + multi-monitor. NOTE: recent drivers have largely fixed MPO bugs — only enable this if you actually have flicker/stutter problems. Needs a reboot.",
    "disable_wpbt":
        "Prevents firmware/motherboard from injecting programs into Windows at boot (WPBT). Blocks vendor-preinstalled background software at the UEFI level. Safe, reversible.",
    "disable_storage_sense":
        "Turns off Windows' automatic Storage Sense, which can delete files in the background. Not needed if you clean up yourself (e.g. via the System Cleaner).",
    'disable_ai_text_image_gen':
        "Blocks Windows' on-device generative AI (Settings → Privacy → Text and image generation) for all apps — the switch AND the policy (Force Deny) that apps and users can't turn back on. Doesn't affect cloud AI services. Reversible.",

    # ── Ported from GameOptimizerPro v1 ──────────────────────────────────────
    "prevent_device_companion":
        "Stops Windows from pulling device metadata off the network and auto-installing or suggesting companion apps for connected devices. Saves background traffic and unwanted app installs.",
    "start_menu_previous_layout":
        "Enables the previous Start menu layout on supported Windows 11 builds via a feature override. Only has an effect on builds that know this flag — otherwise it does nothing.",
    "explorer_folder_discovery":
        "Sets every folder to 'General items'. File Explorer then stops wasting time auto-detecting folder types, so large folders open noticeably faster. Requires sign-out/restart.",
    "store_no_recommended":
        "Locks the Microsoft Store's store.db via file permissions, so the Store no longer shows recommended/sponsored search results. Fully reversible.",
    "nic_power_saving":
        "Turns off 'Allow the computer to turn off this device to save power' for every network adapter. Prevents dropouts and latency spikes caused by adapter power saving.",
    "power_display_sleep_15":
        "Sets the monitor sleep timer to 15 minutes (AC) and 5 minutes (battery) in every plan EXCEPT High Performance and Ultimate Performance — those keep the screen on while on mains power.",
    "power_sleep_off":
        "Disables system sleep entirely — the PC no longer suspends after being idle. Recommended for desktops that should keep running in the background (downloads, servers).",
    "power_cpu_min_100":
        "Sets the minimum CPU state to 100%, so the CPU never clocks down. Removes the brief ramp-up delay coming out of idle — good for consistent FPS, but raises idle power draw and temperature.",
    "power_cpu_max_100":
        "Makes sure Windows never artificially caps the CPU. Relevant on laptops and systems with an aggressive thermal policy. 100% is also the Windows default — so there is honestly nothing to revert here.",
    "amd_disable_ulps":
        "AMD only: disables Ultra Low Power State. ULPS puts idle GPUs into an extreme power-saving mode and can cause stutter on wake-up. Worth disabling even on a single GPU.",
    "amd_shader_cache":
        "AMD only: sets the AMD shader cache to its maximum size. Prevents cache eviction and repeated shader recompilation — reduces stutter especially in OpenGL/Vulkan titles.",
    "amd_antilag":
        "AMD only: enables AMD Anti-Lag via the registry. Shortens the gap between CPU input and GPU output — similar to NVIDIA Reflex. Most effective in CPU-limited games (RX 5000+).",
    'enable_long_paths':
        "Allows file paths longer than 260 characters. Prevents 'path too long' errors with deep folder structures, game mods, Node projects etc.",
    'numlock_on_startup':
        'Turns NumLock on automatically at startup and on the sign-in screen.',
    'disable_lock_screen':
        'Goes straight to the sign-in field on start/wake instead of showing the lock screen first. Honest note: Microsoft only guarantees this policy on Enterprise/Education — on Home/Pro it depends on the build.',
    'run_disk_cleanup':
        'Runs Windows Disk Cleanup on SAFE categories only (temp files, update leftovers, error reports, memory dumps, delivery optimization, thumbnails …) and then removes old update components with DISM. Deliberately NOT: the Downloads folder, the Recycle Bin, Windows.old (the way back to the previous Windows), the shader cache (games would stutter again), old drivers. One-time action, takes a few minutes.',
    'disable_reserved_storage':
        'Frees the storage Windows reserves for updates (typically ~7 GB). Windows then manages update space dynamically. Only works while no update is pending.',
    'pagefile_system_managed':
        "Sets the pagefile to 'system managed'. Windows sizes it to demand — prevents too-small (crashes on RAM spikes) and needlessly large files. This is the Windows default.",
    'clear_pagefile_shutdown':
        'Overwrites the pagefile at every shutdown so no memory remnants stay on disk (privacy). Makes shutdown slower — noticeably with a large pagefile.',
    'disable_memory_compression':
        'Turns off RAM compression and saves CPU time while gaming. Only sensible with enough RAM (16 GB+) — otherwise Windows pages to disk earlier. (If SysMain is disabled it is started briefly for the change and disabled again.)',
    'enable_ssd_trim':
        'Makes sure Windows tells SSDs about deleted blocks (TRIM), keeping SSD performance high long-term. Usually already on — this tweak checks and enforces it.',
    'disable_scheduled_defrag':
        "Disables the weekly drive optimization. Honest note: on SSDs Windows doesn't defragment, it only sends another TRIM — that stops (TRIM on delete stays). Only useful if you want to control optimization yourself.",
    'nvme_queue_depth':
        "Sets a StorPort queue depth of 32 and a higher interrupt priority for NVMe SSDs and turns off the NVMe driver's idle power saving (lower latency, slightly more power). Honest note: the effect depends on the driver and is usually only measurable in benchmarks. Greyed out without an NVMe drive.",
    'disable_write_cache_flush':
        "Same as 'Turn off Windows write-cache buffer flushing' in Device Manager: faster writes, but a power loss or crash can cause data loss and file-system errors. Desktop PCs with a stable power supply only (ideally a UPS). (v1 set the wrong registry value here.)",
    'w11_remove_chat_icon':
        'Removes the Teams Chat icon from the taskbar (prevents an unwanted Teams install). Current builds usually no longer have the icon — then this changes nothing.',
    'w11_hide_recommended':
        "Hides the 'Recommended' section (recent files/apps) in the Start menu via policy. Honest note: not guaranteed on every edition/build.",
    'disable_click_to_do':
        "Turns off 'Click to Do', which takes a screenshot on a key press and has an AI analyze it to suggest actions. Official Windows AI policy (documented for Pro too), for computer and user.",
    'disable_paint_ai':
        'Turns off the AI features in Paint via the official policies: Cocreator, Image Creator, generative fill — plus generative erase and remove background.',
    'disable_notepad_ai':
        'Turns off the Copilot features in Notepad (rewrite, summarize, write) via the official policy.',
    'disable_ai_fabric_service':
        "Disables the 'Host for Windows AI components'. Since 24H2/26H2 it starts automatically and serves local AI models (AI search in Settings, Click to Do, AI actions). Saves RAM and CPU in the background; those AI features are off afterwards. Reversible.",
    'remove_m365_copilot_devhome':
        "Removes the 'Microsoft 365 Copilot' app (Office Hub) and the discontinued Dev Home — feature updates like 26H2 re-install both. Also removes the provisioned packages so they don't come back for new users. Office in the browser keeps working.",
    'tcp_optimize':
        'Turns ECN and TCP timestamps off and SACK on — slightly less overhead per packet. Honest note: the effect on ping is small; turning ECN off mainly helps behind routers that mishandle ECN packets.',
    'disable_qos_limit':
        "Sets the QoS policy 'limit reservable bandwidth' to 0 %. Honest note: contrary to popular belief Windows does NOT permanently reserve 20 % — the reserve only applies when a QoS application requests bandwidth. Usually no measurable effect, but harmless.",
    'mmcss_audio_profile':
        "Sets the MMCSS task 'Audio' to latency-sensitive with high scheduling priority — fewer crackles and dropouts under CPU load. (Complements 'MMCSS Audio Priority', which covers the 'Pro Audio' task.)",
    'audio_service_priority':
        "Sets SystemResponsiveness to 0 — MMCSS no longer reserves CPU time for background tasks, so audio and games get more. Against dropouts while gaming + streaming. ('Network Throttling Index' uses the same value — it's only reset once neither tweak needs it.)",
}

# English names, only where the German name differs. Most names are already English.
TWEAK_NAME_EN: dict[str, str] = {
    "windowed_game_optimizations": "Optimizations for windowed games",
    "end_task_right_click": "End Task via Right-Click (Taskbar)",
    "show_file_extensions": "Show File Extensions",
    "show_hidden_files":    "Show Hidden Files",
    "disable_mpo":          "Disable Multiplane Overlay (MPO)",
    "disable_wpbt":         "Disable Windows Platform Binary Table (WPBT)",
    "disable_storage_sense": "Disable Storage Sense",
    "disable_ai_text_image_gen": "Disable Text & Image Generation (on-device AI)",
    "dx12_optimization":    "Raise GPU Timeout (TDR Delay)",
    'enable_long_paths':
        'Enable Long Paths (> 260 characters)',
    'numlock_on_startup':
        'NumLock on at Startup',
    'disable_lock_screen':
        'Skip the Lock Screen',
    'run_disk_cleanup':
        'Run Disk Cleanup (one-time)',
    'disable_reserved_storage':
        'Free Reserved Storage (~7 GB)',
    'pagefile_system_managed':
        'Let Windows Manage the Pagefile',
    'clear_pagefile_shutdown':
        'Clear Pagefile at Shutdown',
    'disable_memory_compression':
        'Disable Memory Compression',
    'enable_ssd_trim':
        'Ensure SSD TRIM',
    'disable_scheduled_defrag':
        'Disable Scheduled Drive Optimization',
    'nvme_queue_depth':
        'NVMe: Queue Depth & Idle Power Saving',
    'disable_write_cache_flush':
        'Disable Write-Cache Buffer Flushing (desktop + UPS only)',
    'w11_remove_chat_icon':
        'Win11: Remove Chat Icon from Taskbar',
    'w11_hide_recommended':
        "Win11: Hide 'Recommended' in Start",
    'disable_click_to_do':
        'Disable Click to Do (AI screen analysis)',
    'disable_paint_ai':
        'Disable Paint AI',
    'disable_notepad_ai':
        'Disable Notepad AI',
    'disable_ai_fabric_service':
        'Turn off the Windows AI Service (WSAIFabricSvc)',
    'remove_m365_copilot_devhome':
        'Remove Microsoft 365 Copilot App & Dev Home',
    'tcp_optimize':
        'Optimize TCP (ECN & Timestamps off, SACK on)',
    'disable_qos_limit':
        'QoS Bandwidth Reserve to 0 %',
    'mmcss_audio_profile':
        'Optimize MMCSS Audio Profile',
    'audio_service_priority':
        'Raise Audio Priority System-wide',
}


# Preset descriptions in English, keyed by preset id.
PRESET_DESC_EN: dict[str, str] = {
    "tier_minimal":
        "Gentle baseline: only rock-solid safe tweaks with no loss of function — basic privacy, gaming basics and a few comfort fixes. A good starting point.",
    "tier_medium":
        "Balanced: Minimal + performance plan, gaming/network tweaks, light debloat (Candy Crush & Xbox apps). A solid all-round compromise.",
    "tier_hard":
        "Maximum: Medium + aggressive debloat (Cortana, Copilot, Recall, Teams, OneDrive), full performance/network/audio tweaks, Win11 classic UI. For advanced users — best to create a restore point first (Settings).",
    "gaming":
        "Optimises for maximum FPS and minimal input lag. Disables Xbox Game Bar, enables Ultimate Performance plan, HAGS, CPU priority, mouse accel off.",
    "privacy":
        "Disables all Microsoft telemetry services, tracking, advertising ID, activity history, Copilot and Recall. Blocks telemetry servers in the hosts file.",
    "debloat":
        "Removes all preinstalled apps (Candy Crush, TikTok, Xbox apps, Teams Consumer, OneDrive). No data loss, apps can be reinstalled.",
    "network":
        "Optimises network latency: disable Nagle, DNS to Cloudflare, network throttling off, enable RSS. A noticeable difference in online games.",
    "performance":
        "General Windows performance: Ultimate Performance plan, Prefetch/Superfetch off (SSD), animations off, search index off, USB suspend off.",
    "win11_classic":
        "Restores the classic Windows 10 feel on Windows 11: right-click menu, taskbar icons left, widgets off, snap suggestions off.",
    "all_safe":
        "Applies every tweak marked as safe. Good for a quick full optimisation without risky changes.",
}

PRESET_NAME_EN: dict[str, str] = {
    "tier_minimal": "Minimal",
    "tier_medium":  "Medium",
    "tier_hard":    "Hard — Debloat",
}


def preset_desc(preset, lang: str) -> str:
    """Return the preset description in the requested language."""
    if lang == "en":
        return PRESET_DESC_EN.get(preset.id, preset.desc)
    return preset.desc


def preset_name(preset, lang: str) -> str:
    """Return the preset name in the requested language."""
    if lang == "en":
        return PRESET_NAME_EN.get(preset.id, preset.name)
    return preset.name


def tweak_desc(tweak, lang: str) -> str:
    """Return the tweak description in the requested language."""
    if lang == "en":
        return TWEAK_DESC_EN.get(tweak.id, tweak.desc)
    return tweak.desc


def tweak_name(tweak, lang: str) -> str:
    """Return the tweak name in the requested language."""
    if lang == "en":
        return TWEAK_NAME_EN.get(tweak.id, tweak.name)
    return tweak.name
