"""
GameOptimizerPro Tweak Presets
Vordefinierte Tweak-Kombinationen für häufige Anwendungsfälle.
Jedes Preset hat eine Liste von Tweak-IDs + Metadaten.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TweakPreset:
    id:          str
    name:        str
    icon:        str
    desc:        str
    tweak_ids:   list[str]
    color:       str = "#00d9ff"
    builtin:     bool = True    # False = user-created


# ── Builtin Presets ───────────────────────────────────────────────────────────

BUILTIN_PRESETS: list[TweakPreset] = [

    TweakPreset(
        id="gaming",
        name="Gaming",
        icon="🎮",
        desc="Optimiert für maximale FPS und minimalen Input-Lag. Deaktiviert Xbox Game Bar, aktiviert Ultimate Performance Plan, HAGS, CPU Priority, Mouse Accel off.",
        color="#00d9ff",
        tweak_ids=[
            "ultimate_performance",
            "enable_game_mode",
            "disable_game_bar",
            "cpu_priority_games",
            "mmcss_gaming",
            "disable_fullscreen_opt",
            "disable_mouse_accel",
            "disable_sticky_keys",
            "disable_hpet",
            "timer_resolution",
            "enable_hags",
            "disable_bg_throttle",
            "dx12_optimization",
            "end_task_right_click",
        ],
    ),

    TweakPreset(
        id="privacy",
        name="Privacy & Anti-Telemetry",
        icon="🔒",
        desc="Deaktiviert alle Microsoft Telemetrie-Dienste, Tracking, Werbe-ID, Activity History, Copilot und Recall. Blockiert Telemetrie-Server in der hosts-Datei.",
        color="#a78bfa",
        tweak_ids=[
            "disable_telemetry",
            "disable_telemetry_tasks",
            "block_telemetry_hosts",
            "disable_activity_history",
            "disable_advertising_id",
            "disable_location",
            "remove_copilot",
            "remove_recall",
        ],
    ),

    TweakPreset(
        id="debloat",
        name="Debloat Windows",
        icon="🧹",
        desc="Entfernt alle vorinstallierten Apps (Candy Crush, TikTok, Xbox Apps, Teams Consumer, OneDrive). Kein Datenverlust, Apps können neu installiert werden.",
        color="#22c55e",
        tweak_ids=[
            "remove_bloatware",
            "remove_xbox",
            "remove_cortana",
            "remove_teams",
            "remove_copilot",
            "remove_onedrive",
            "w11_disable_widgets",
            "disable_consumer_features",
        ],
    ),

    TweakPreset(
        id="network",
        name="Network Optimization",
        icon="🌐",
        desc="Optimiert Netzwerk-Latenz: Nagle deaktivieren, DNS auf Cloudflare, Network Throttling aus, RSS aktivieren. Spürbarer Unterschied bei Online-Spielen.",
        color="#f59e0b",
        tweak_ids=[
            "disable_nagle",
            "disable_network_throttle",
            "enable_rss",
            "dns_cloudflare",
            "flush_dns",
            "disable_delivery_optimization",
        ],
    ),

    TweakPreset(
        id="performance",
        name="Performance",
        icon="⚡",
        desc="Allgemeine Windows Performance: Ultimate Performance Plan, Prefetch/Superfetch aus (SSD), Animationen aus, Such-Index aus, USB Suspend aus.",
        color="#ef4444",
        tweak_ids=[
            "ultimate_performance",
            "disable_prefetch",
            "visual_effects_perf",
            "disable_search_indexing",
            "disable_usb_suspend",
            "timer_resolution",
            "disable_transparency",
            "disable_hibernation",
            "power_pcie_aspm_off",
            "power_disk_never_sleep",
        ],
    ),

    TweakPreset(
        id="win11_classic",
        name="Windows 11 Classic UI",
        icon="🪟",
        desc="Stellt klassisches Windows 10 Feeling in Windows 11 wieder her: Rechtsklick-Menü, Taskbar-Icons links, Widgets aus, Snap-Suggestions aus.",
        color="#7c3aed",
        tweak_ids=[
            "w11_classic_context_menu",
            "w11_taskbar_left",
            "w11_disable_widgets",
            "w11_disable_snap_suggest",
            "enable_dark_mode",
            "disable_transparency",
        ],
    ),

    TweakPreset(
        id="all_safe",
        name="All Safe Tweaks",
        icon="✅",
        desc="Wendet alle als 'safe' markierten Tweaks an. Geeignet für eine schnelle Komplettoptimierung ohne riskante Eingriffe.",
        color="#22c55e",
        tweak_ids=[],   # populated dynamically
    ),
]


def get_all_safe_ids() -> list[str]:
    from core.tweaks import ALL_TWEAKS
    return [t.id for t in ALL_TWEAKS if t.risk == "safe"]


def get_preset(preset_id: str) -> Optional[TweakPreset]:
    for p in BUILTIN_PRESETS:
        if p.id == preset_id:
            if preset_id == "all_safe":
                p.tweak_ids = get_all_safe_ids()
            return p
    return None


def get_all_presets(user_presets: list[TweakPreset] = None) -> list[TweakPreset]:
    result = list(BUILTIN_PRESETS)
    if user_presets:
        result.extend(user_presets)
    return result
