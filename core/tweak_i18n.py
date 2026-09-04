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
    "remove_recall":
        "Disables Windows Recall so it no longer takes screenshots of your activity. Privacy critical.",
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
        "Enables the Ultimate Performance power plan. CPU cores are no longer throttled. Increases power draw.",
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
        "Enables Message Signaled Interrupts for GPU and NVMe. Significantly reduces interrupt latency. Reboot required.",
    "enable_hags":
        "Hands GPU scheduling directly to the hardware. Less CPU overhead and lower input lag. Needs RTX 2000+ or RX 5000+.",
    "clear_shader_cache":
        "Clears the NVIDIA/AMD shader cache. Useful after driver updates or on graphics glitches.",
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
        "Enables Receive-Side Scaling on all adapters. Spreads network processing across CPU cores. Better on fast connections.",
    "w11_classic_context_menu":
        "Restores the classic right-click context menu in Windows 11. No more Show more options.",
    "w11_taskbar_left":
        "Moves taskbar icons to the left (classic Windows 10 layout).",
    "w11_disable_widgets":
        "Disables the Windows 11 widgets panel. Saves RAM and reduces background activity.",
    "w11_disable_snap_suggest":
        "Disables the automatic snap layout popup when hovering the maximise button.",
    "power_balanced":
        "Sets the power plan to Balanced (Windows default).",
    "power_high":
        "Enables High Performance. A good balance between performance and power draw.",
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
    "disable_ai_text_image_gen":
        "Disables Windows' on-device generative AI (Settings → Privacy → Text and image generation). Stops Windows and apps from using local AI models. Does not affect cloud AI services. Reversible.",
}

# English names, only where the German name differs. Most names are already English.
TWEAK_NAME_EN: dict[str, str] = {
    "end_task_right_click": "End Task via Right-Click (Taskbar)",
    "show_file_extensions": "Show File Extensions",
    "show_hidden_files":    "Show Hidden Files",
    "disable_mpo":          "Disable Multiplane Overlay (MPO)",
    "disable_wpbt":         "Disable Windows Platform Binary Table (WPBT)",
    "disable_storage_sense": "Disable Storage Sense",
    "disable_ai_text_image_gen": "Disable Text & Image Generation (on-device AI)",
    "dx12_optimization":    "Raise GPU Timeout (TDR Delay)",
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
