"""
GameOptimizerPro — Tweak translations
English descriptions for all tweaks. German lives in tweaks.py as the default.
Lookup by tweak id. If an id is missing here, the German default is used.
"""

# English descriptions, keyed by tweak id.
TWEAK_DESC_EN: dict[str, str] = {
    "remove_xbox":
        "Removes Xbox Game Bar, Xbox Identity Provider and Xbox TCUI. They run in the background even without Xbox. "
        "Don't apply it if you play games with an Xbox sign-in (Game Pass, Microsoft Store), use Xbox mode or "
        "Game Bar recordings — those are gone until the apps are reinstalled from the Store.",
    "remove_copilot":
        "Disables Windows Copilot and stops it from sending data in the background.",
    "remove_onedrive":
        "Fully uninstalls OneDrive including autostart. Local files are kept.",
    'remove_recall':
        'Turns off Windows Recall via the official policies (no more screenshots of your activity) and REMOVES its components and saved snapshots on the next restart. Privacy critical.',
    "remove_bloatware":
        "Removes Microsoft's preinstalled extras and the bundled games: Candy Crush & co., Solitaire, News, Weather, Clipchamp, To Do, Feedback Hub, Paint 3D, Mixed Reality and more — the provisioned packages too, so feature updates don't reinstall them. Deliberately not: apps many people install themselves (Spotify, Netflix, Disney+, TikTok, Instagram, Facebook, X), Media Player (Windows 11's default player) and Get Help (the troubleshooters run through it) — remove those one by one on the Apps page if you like.",
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
        "Disables the scheduled Windows tasks that collect or send telemetry and diagnostic data: compatibility "
        "appraisal, Customer Experience Improvement Program, feedback data, the error report queue, disk and "
        "energy diagnostics. Tasks this Windows doesn't have are skipped; revert switches them back on.",
    "ultimate_performance":
        "Enables the Ultimate Performance power plan. CPU cores are no longer throttled, and on mains power the screen never turns off and the PC never goes to sleep. Increases power draw. (Creates the plan only once — each apply used to add another copy; extra copies are removed.)",
    "disable_hpet":
        "Disables the High Precision Event Timer. Reduces system latency and improves frame times in games.",
    "timer_resolution":
        "Since Windows 10 2004 a finer timer resolution (e.g. 0.5 ms instead of 15.6 ms) only applies to the "
        "program that requests it, and Windows 11 ignores it for minimized windows. This value brings back "
        "the former system-wide behaviour. Honest note: it sets no resolution itself — games and tools "
        "request it when they start. Takes effect after a restart.",
    "disable_prefetch":
        "Disables SysMain. Useful on SSDs, not recommended on HDDs.",
    "visual_effects_perf":
        "Turns off the Windows animations — minimize/maximize, menus, tooltips, lists, controls, taskbar — at "
        "once, without signing out. Deliberately kept ON: smooth screen fonts, window contents while dragging, "
        "thumbnails and the shadows under icon labels: they cost practically nothing, without them Windows only "
        "gets harder to read. Windows feels noticeably more direct.",
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
        "Sets the MMCSS category of the 'Games' task to High: threads that register with Windows as a game task "
        "run at priority 23–26 instead of 16–22. Honest note: only some games and programs do that; the values "
        "'GPU Priority' and 'Priority' often set along with it are not read by Windows for this, per Microsoft "
        "(GPU Priority is not used, Priority always counts as 2 with High).",
    "disable_fullscreen_opt":
        "Disables Windows Fullscreen Optimizations globally. Forces true fullscreen for lower input lag.",
    "disable_wu_gaming":
        "Windows no longer downloads and installs updates by itself, it only tells you that there are some — for good, not just while gaming. No restarts or downloads mid-game, but security updates only come when you start them yourself under Settings → Windows Update. Only if you do that regularly. (Windows already avoids restarts during active hours.)",
    "disable_bg_throttle":
        "Store apps no longer keep running in the background (Windows' 'Let apps run in the background' switch for your user, Home included). Saves a little memory and CPU time. Consequence: closed Store apps such as WhatsApp, Phone Link or Mail don't report new messages. Windows throttling processes is a different tweak ('Disable Power Throttling').",
    "enable_msi_mode":
        "Enables Message Signaled Interrupts for the GPU. Reduces interrupt latency. Reboot required.",
    "enable_hags":
        "Hands GPU scheduling directly to the hardware. Less CPU overhead and lower input lag. Needs RTX 2000+ or RX 5000+; DLSS Frame Generation requires it. Revert puts back the state from before (not set before: Windows decides again).",
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
        "Disables network throttling under high CPU load. Gives the network stack top priority. Also sets "
        "SystemResponsiveness to 10 (the lowest value Windows accepts).",
    "dns_cloudflare":
        "Sets DNS to Cloudflare — IPv4 (1.1.1.1 / 1.0.0.1) and IPv6 (2606:4700:4700::1111 / ::1001), on the physical network adapters only (VPN and virtual adapters stay as they are). One of the fastest and most privacy-friendly DNS services.",
    "dns_google":
        "Sets DNS to Google — IPv4 (8.8.8.8 / 8.8.4.4) and IPv6 (2001:4860:4860::8888 / ::8844), on the physical network adapters only (VPN and virtual adapters stay as they are). Globally distributed, fast and reliable.",
    "flush_dns":
        "Flushes the local DNS cache. Fast, with no side effects.",
    "disable_tcp_autotuning":
        "Turns the automatic TCP receive window off — it stays at 64 KB. Honest note: downloads get much slower (at a 20 ms ping at most about 25 Mbit/s per connection), and there is no documented gain for the ping in games. Only for troubleshooting very old routers.",
    "enable_rss":
        "Enables Receive-Side Scaling on every adapter that offers it. Spreads network processing across CPU cores. Better on fast connections. (Says so honestly when the driver doesn't expose RSS to Windows.)",
    "w11_classic_context_menu":
        "Restores the classic right-click context menu in Windows 11. No more Show more options. "
        "Note: with the Windows update KB5127936 (Oct 2026) the new menu gradually becomes customizable "
        "itself (right-click → 'Customize menu'). If the tweak stops working after it, just revert it.",
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
        "Prevents USB devices (mouse, headset) from entering power saving mode — in every power plan, on mains power. No more sudden disconnects. Revert puts back each plan's value from before.",
    "disable_audio_enhancements":
        "Disables Windows audio enhancements (bass boost, EQ etc.). Reduces audio latency and CPU load. Recommended for gaming.",
    "disable_audio_exclusive_lock":
        "Prevents games from locking the audio device exclusively and muting Discord/Spotify.",
    "disable_sound_scheme":
        "Turns off all Windows system sounds (startup, error, notifications). Prevents audio interruptions while gaming.",
    "disable_nahimic":
        "Disables Nahimic audio (preinstalled on MSI boards and gaming laptops). Causes CPU spikes and audio artefacts. Safe if unused.",
    "disable_audio_ducking":
        "Prevents Windows from lowering other sounds during calls/communication. Often annoying when gaming with Discord.",
    # v2.1 additions
    "disable_power_throttling":
        "Prevents Windows from throttling processes to save power. Useful for games whose side-processes would otherwise be throttled.",
    "reduce_process_count":
        "Sets the Svchost split threshold to your RAM size so Windows bundles services into fewer processes. Lowers the total background process count. Safe with 16GB+ RAM. Revert puts back the value from before (Windows' own is 3.5 GB).",
    "disable_bing_search":
        "Disables Bing web integration in Windows Search. Start menu search stays local and loads faster. Also "
        "off: search highlights (pictures and topics of the day in the search box) and the cloud content search "
        "(OneDrive/Outlook results of the Microsoft or work account).",
    "disable_consumer_features":
        "Stops Windows from silently installing suggested apps and games (Candy Crush, TikTok & co.) — also the ones the PC maker and Microsoft line up. Works on every edition incl. Home and Pro (Content Delivery Manager); plus the 'Turn off Microsoft consumer experiences' policy, which Windows honours on Enterprise / Education only. Apps already installed stay — 'Remove Bloatware' is for those.",
    "disable_hibernation":
        "Disables hibernation and deletes hiberfil.sys (otherwise uses RAM-size on the SSD, e.g. 32 GB). Also turns off the often flaky Fast Startup. Safe on desktop gaming PCs.",
    "end_task_right_click":
        "Adds 'End Task' to the taskbar right-click menu — kill a frozen game instantly without opening Task Manager. Windows 11 22H2+.",
    "disable_delivery_optimization":
        "Turns off peer-to-peer sharing of Windows updates, which otherwise eats upload/download bandwidth in the background — noticeably steadier pings for online gaming. Policy only.",
    "power_pcie_aspm_off":
        "Disables PCIe link power saving (ASPM) in every power plan, on mains power. The PCIe bus to the graphics card stays at full power instead of dropping into low-power states — marginally more consistent latency at the cost of a little more idle power. Revert puts back each plan's value from before.",
    "power_disk_never_sleep":
        "Stops Windows from spinning down drives after inactivity — in every power plan, on mains power. On systems with HDD(s) this prevents micro-stutter when a background process has to wake a sleeping drive. Revert puts back each plan's value from before.",
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
    "explorer_folder_discovery":
        "Sets every folder to 'General items'. File Explorer then stops wasting time auto-detecting folder types, so large folders open noticeably faster. Caution: applying it loses the saved views of all folders (sorting, columns, view). Revert only takes the default back — the views from before don't return. Requires sign-out/restart.",
    "store_no_recommended":
        "Locks the Microsoft Store's store.db via file permissions, so the Store no longer shows recommended/sponsored search results. Fully reversible.",
    "nic_power_saving":
        "Turns off 'Allow the computer to turn off this device to save power' for every network adapter. Prevents dropouts and latency spikes caused by adapter power saving.",
    "power_display_sleep_15":
        "Sets the monitor sleep timer to 15 minutes (AC) and 5 minutes (battery) in every plan EXCEPT High Performance and Ultimate Performance — those keep the screen on while on mains power. Revert puts back each plan's values from before.",
    "power_sleep_off":
        "Disables system sleep entirely (every power plan, mains and battery) — the PC no longer suspends after being idle. Recommended for desktops that should keep running in the background (downloads, servers). Revert puts back each plan's values from before.",
    "power_cpu_min_100":
        "Sets the minimum CPU state to 100% (every power plan), so the CPU never clocks down. Removes the brief ramp-up delay coming out of idle — good for consistent FPS, but raises idle power draw and temperature. Revert puts back each plan's values from before.",
    "power_cpu_max_100":
        "Makes sure Windows never artificially caps the CPU. Relevant on laptops and systems with an aggressive thermal policy. 100% is also the Windows default — so there is honestly nothing to revert here.",
    "amd_disable_ulps":
        "AMD only: disables Ultra Low Power State. ULPS puts idle GPUs into an extreme power-saving mode and can cause stutter on wake-up. Worth disabling even on a single GPU.",
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
    'disable_write_cache_flush':
        "Same as 'Turn off Windows write-cache buffer flushing' in Device Manager: faster writes, but a power loss or crash can cause data loss and file-system errors. Desktop PCs with a stable power supply only (ideally a UPS). (v1 set the wrong registry value here.)",
    'w11_hide_recommended':
        "Hides the 'Recommended' section in Start via policy — which Microsoft only documents for Education/SE. "
        "So that it stays empty on Home and Pro too, also off: recently opened files (in Explorer's Home and the "
        "taskbar jump lists as well) and tips/app recommendations in Start. Revert puts your previous settings back.",
    'disable_click_to_do':
        "Turns off 'Click to Do', which takes a screenshot on a key press and has an AI analyze it to suggest actions. Official Windows AI policy (documented for Pro too), for computer and user.",
    'disable_paint_ai':
        'Turns off the AI features in Paint via the official policies: Cocreator, Image Creator and generative fill. Generative erase and remove background have no policy.',
    'disable_notepad_ai':
        'Turns off the Copilot features in Notepad (rewrite, summarize, write) via the official policy.',
    'disable_ai_fabric_service':
        "Disables the 'Host for Windows AI components'. Since 24H2/26H2 it starts automatically and serves local AI models (AI search in Settings, Click to Do, AI actions). Saves RAM and CPU in the background; those AI features are off afterwards. Reversible.",
    'remove_m365_copilot_devhome':
        "Removes the 'Microsoft 365 Copilot' app (Office Hub) and the discontinued Dev Home — feature updates like 26H2 re-install both. Also removes the provisioned packages so they don't come back for new users. Office in the browser keeps working.",
    "disable_eee":
        "Turns off Energy-Efficient Ethernet (EEE, 'Green Ethernet') on every wired adapter that offers it. "
        "With EEE the link drops into a power-saving state during pauses and has to wake up for the next "
        "packet, which can cause small latency spikes. On a desktop turning it off costs practically "
        "nothing. Only settings the driver itself offers are changed; revert puts the previous value back. "
        "No connection drop now, takes effect after a restart.",
    "disable_interrupt_moderation":
        "The wired adapter reports every packet right away instead of collecting several and reporting "
        "them together. Lowers network latency by a fraction of a millisecond, but causes noticeably more "
        "CPU load at high download rates. Meant for online games — if you often download big files or "
        "stream, better leave it on. Only settings the driver itself offers are changed; revert puts the "
        "previous value back. Takes effect after a restart.",
    'mmcss_audio_profile':
        "Sets the MMCSS task 'Audio' to latency-sensitive with high scheduling priority — fewer crackles and dropouts under CPU load.",
    'audio_service_priority':
        "Sets SystemResponsiveness to 10 — MMCSS only keeps 10 % instead of 20 % of CPU time free for background tasks, so audio and games get more. Against dropouts while gaming + streaming. Honest note: 10 is the minimum — lower values (often recommended: 0) are treated like the default 20, per Microsoft. ('Network Throttling Index' uses the same value — it's only reset once neither tweak needs it.)",
    # ── Round 45 ──────────────────────────────────────────────────────────────
    "disable_tips_suggestions":
        "Turns off Windows' built-in advertising: 'tips and suggestions', the welcome page after updates, 'finish "
        "setting up your device' hints, suggested content in Settings, tips and fun facts on the lock screen (the "
        "Spotlight pictures stay), account hints in Start and Settings and the OneDrive ads in Explorer. All of "
        "them switches Windows offers itself (Home and Pro); revert puts your previous values back.",
    "disable_input_speech_data":
        "Turns off the privacy switches around typing and speech: the personal inking and typing dictionary "
        "(Windows collects what you type and write for it), 'improve inking and typing', online speech "
        "recognition, 'tailored experiences' with diagnostic data, feedback requests, the language list for "
        "websites and tracking app launches (Start then shows no 'most used' list). Revert puts your previous "
        "values back.",
    "onedrive_block_kfm":
        "Stops OneDrive from moving Desktop, Documents and Pictures to the cloud ('back up folders') — and from "
        "asking about it. The official OneDrive policy, for every account incl. a personal Microsoft account. If "
        "the folders are in OneDrive already, the tweak stops and says how to move them back first (otherwise "
        "exactly that button would be locked). No effect without OneDrive.",
    "disable_remote_assistance":
        "Turns off the old Windows Remote Assistance (System properties → Remote): nobody can start a help "
        "session on this PC through it. Practically only used in company networks any more; Quick Assist, "
        "TeamViewer & co. are not affected. Less attack surface. Revert puts the previous values back.",
    "exclude_wu_drivers":
        "Windows Update no longer installs drivers with the monthly updates (official policy). Protects the "
        "graphics driver you installed from being replaced by an older or generic version. In return chipset, "
        "Wi-Fi, Bluetooth & co. get no drivers through Windows Update either — get those from the manufacturer. "
        "Pro, Enterprise and Education only (Windows Home ignores the policy, hidden there).",
    "wu_pin_feature_version":
        "Keeps Windows on the installed version (e.g. 26H2): feature updates, which can reinstall apps and reset "
        "settings, only come once you lift this again. Security and quality updates keep coming. Official policy, "
        "Pro, Enterprise and Education only (Home: hidden). Revert it before the version's end of support — after "
        "that there would be no more security updates.",
    "disable_background_apps":
        "Official policy 'Let Windows apps run in the background: force deny': Store apps (Phone Link, Mail and "
        "Calendar, Weather …) only run while they are open — saves RAM and background CPU. Afterwards such apps "
        "no longer notify you while closed, e.g. WhatsApp from the Store. Regular programs (Steam, Discord, "
        "Afterburner) are not affected. Pro, Enterprise and Education only (Home: hidden).",
    "usb3_link_power_off":
        "Turns off the power saving of the USB 3 link on mains power (hidden power option 'USB 3 Link Power "
        "Management', Windows default: moderate savings). The link stays awake — against short dropouts and slow "
        "wake-ups of USB 3 devices such as headsets, DACs, capture cards or external SSDs. Slightly more power "
        "draw. Applies to every power plan; revert puts the previous values back. Complements 'USB Selective "
        "Suspend' (that one is about the devices, not the link).",
    "disable_wake_timers":
        "Scheduled tasks (update restarts, maintenance) no longer wake the PC from sleep (power option 'Allow "
        "wake timers' on mains power; Windows default: on). A sleeping PC stays off at night; updates install "
        "while it is on. Applies to every power plan; revert puts the previous values back.",
    "startup_delay_off":
        "Windows starts autostart programs (Run entries and the Startup folder) only a few seconds after you "
        "sign in. Without the delay Discord & co. are there at once; with very many autostarts signing in feels "
        "a bit heavier for a moment. Programs with their own task (e.g. Afterburner) are not affected.",
    "explorer_open_this_pc":
        "Explorer opens 'This PC' (drives and folders) instead of 'Home' with the recently used files. A matter "
        "of taste; doesn't count towards the score.",
    "alt_tab_windows_only":
        "Alt+Tab and snapping show windows only, no single Edge tabs (Settings → System → Multitasking). Out of a "
        "game you get to the right window faster. Takes effect after signing out. A matter of taste; doesn't "
        "count towards the score.",
    "disable_dynamic_lighting":
        "Turns off 'Dynamic Lighting' (Settings → Personalization): Windows no longer controls the RGB lighting "
        "of keyboard, mouse & co. — against conflicts with the vendor software (iCUE, G HUB, Armoury Crate, "
        "SignalRGB …), which can otherwise flicker or lose its effects. If you control the lighting through "
        "Windows, leave it on. Takes effect after signing out at the latest; doesn't count towards the score.",
    "controller_no_game_bar":
        "The Xbox/guide button on the controller no longer opens the Game Bar — so it no longer pulls you out of "
        "the game or out of Steam Big Picture (Settings → Gaming → Game Bar). Revert puts the previous value back.",
}

# English names, only where the German name differs. Most names are already English.
TWEAK_NAME_EN: dict[str, str] = {
    # round 47: renamed honestly (German names in core/tweaks.py)
    "disable_wu_gaming":
        "Turn off automatic Windows updates",
    "disable_bg_throttle":
        "Stop background apps (all editions)",
    "disable_consumer_features": "Stop Auto-Installed Suggested Apps",
    "timer_resolution":     "Let Timer Requests Apply System-wide",
    "disable_eee":          "Disable Energy-Efficient Ethernet",
    "disable_interrupt_moderation": "Disable Interrupt Moderation",
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
    'disable_write_cache_flush':
        'Disable Write-Cache Buffer Flushing (desktop + UPS only)',
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
    'mmcss_audio_profile':
        'Optimize MMCSS Audio Profile',
    'audio_service_priority':
        'Raise Audio Priority System-wide',
    # round 45
    "disable_tips_suggestions":  "Turn Off Tips, Suggestions & Ads in Windows",
    "disable_input_speech_data": "Don't Send Typing, Inking & Speech Data",
    "onedrive_block_kfm":        "OneDrive: Don't Move Folders to the Cloud",
    "disable_remote_assistance": "Disable Remote Assistance",
    "exclude_wu_drivers":        "No Drivers through Windows Update",
    "wu_pin_feature_version":    "Stay on This Windows Version",
    "disable_background_apps":   "Don't Let Store Apps Run in the Background",
    "usb3_link_power_off":       "USB 3: Link Power Saving Off",
    "disable_wake_timers":       "Disable Wake Timers",
    "startup_delay_off":         "Autostart Programs Without Delay",
    "explorer_open_this_pc":     "Explorer Opens 'This PC'",
    "alt_tab_windows_only":      "Alt+Tab Without Browser Tabs",
    "disable_dynamic_lighting":  "Turn Off Dynamic Lighting (RGB control by Windows)",
    "controller_no_game_bar":    "Xbox Button Doesn't Open the Game Bar",
}


# Preset descriptions in English, keyed by preset id.
PRESET_DESC_EN: dict[str, str] = {
    "tier_minimal":
        "Gentle baseline: only rock-solid safe tweaks with no loss of function — basic privacy, gaming basics and a few comfort fixes. A good starting point.",
    "tier_medium":
        "Balanced: Minimal + performance plan, gaming/network tweaks, light debloat (Candy Crush & co.). A solid all-round compromise.",
    "tier_hard":
        "Maximum: Medium + aggressive debloat (Xbox apps, Copilot, Recall, OneDrive), full performance/network/audio tweaks, Win11 classic UI. For advanced users — best to create a restore point first (Settings).",
    "gaming":
        "Optimises for maximum FPS and minimal input lag. Disables Xbox Game Bar, enables Ultimate Performance plan, HAGS, CPU priority, mouse accel off.",
    "privacy":
        "Disables all Microsoft telemetry services, tracking, advertising ID, activity history, Copilot and Recall. Blocks telemetry servers in the hosts file.",
    "debloat":
        "Removes all preinstalled apps (Candy Crush, TikTok, Xbox apps, Microsoft 365 Copilot, OneDrive). No data loss, apps can be reinstalled.",
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
    if not getattr(preset, "builtin", True):     # the user's own: its saved text is German only
        n = len(preset.tweak_ids)
        return f"Custom preset: {n} tweaks" if lang == "en" else f"Eigenes Preset: {n} Tweaks"
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
