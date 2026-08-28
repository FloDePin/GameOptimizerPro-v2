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


# ── Abgestufte Intensitäts-Stufen (kumulativ: Mittel = Minimal + X, Hart = Mittel + Y) ──
# Bewusst NICHT in den Stufen: disable_mpo (situativer Flacker-Fix), enable_dark_mode
# (reine Optik), power_balanced/power_high (widersprechen dem Ultimate-Plan),
# dns_google (Cloudflare reicht) — die bleiben Einzel-Tweaks.

_TIER_MINIMAL = [
    # sicher, universell, kein Funktionsverlust — "das sollte jeder machen"
    "disable_telemetry", "disable_activity_history", "disable_advertising_id",
    "disable_consumer_features",
    "enable_game_mode", "disable_game_bar", "disable_mouse_accel", "disable_fullscreen_opt",
    "disable_sticky_keys", "show_file_extensions",
]

_MEDIUM_EXTRA = [
    # + ausgewogene Performance/Privacy/Debloat + Gaming-Basics
    "disable_bing_search", "disable_location", "disable_telemetry_tasks",
    "ultimate_performance", "visual_effects_perf", "timer_resolution", "disable_transparency",
    "cpu_priority_games", "mmcss_gaming", "disable_bg_throttle", "enable_hags",
    "dx12_optimization", "nvidia_low_latency", "enable_msi_mode",
    "remove_bloatware", "remove_xbox",
    "disable_nagle", "disable_network_throttle", "enable_rss", "disable_delivery_optimization",
    "disable_hibernation", "disable_storage_sense", "end_task_right_click",
]

_HARD_EXTRA = [
    # + aggressiver Debloat + volle Performance/Netzwerk/Audio + W11-Classic + moderate Tweaks
    "remove_cortana", "remove_copilot", "remove_recall", "remove_teams", "remove_onedrive",
    "block_telemetry_hosts", "disable_wpbt",
    "disable_prefetch", "disable_search_indexing", "disable_usb_suspend", "disable_hpet",
    "disable_power_throttling", "disable_wu_gaming", "reduce_process_count", "clear_shader_cache",
    "dns_cloudflare", "flush_dns", "disable_tcp_autotuning", "disable_lso",
    "disable_audio_enhancements", "disable_audio_exclusive_lock", "disable_nahimic",
    "set_mmcss_audio", "disable_audio_ducking", "disable_sound_scheme",
    "w11_classic_context_menu", "w11_taskbar_left", "w11_disable_widgets", "w11_disable_snap_suggest",
    "power_pcie_aspm_off", "power_disk_never_sleep", "show_hidden_files",
]

_TIER_MEDIUM = _TIER_MINIMAL + _MEDIUM_EXTRA
_TIER_HARD   = _TIER_MINIMAL + _MEDIUM_EXTRA + _HARD_EXTRA


# ── Builtin Presets ───────────────────────────────────────────────────────────

BUILTIN_PRESETS: list[TweakPreset] = [

    TweakPreset(
        id="tier_minimal",
        name="Minimal",
        icon="🟢",
        desc="Sanfte Basis: nur absolut sichere Tweaks ohne Funktionsverlust — "
             "Grund-Privacy, Gaming-Basics und ein paar Komfort-Fixes. Ideal als Einstieg.",
        color="#22c55e",
        tweak_ids=list(_TIER_MINIMAL),
    ),
    TweakPreset(
        id="tier_medium",
        name="Mittel",
        icon="🟡",
        desc="Ausgewogen: Minimal + Performance-Plan, Gaming-/Netzwerk-Tweaks, "
             "leichter Debloat (Candy Crush & Xbox-Apps). Guter Allround-Kompromiss.",
        color="#f59e0b",
        tweak_ids=list(_TIER_MEDIUM),
    ),
    TweakPreset(
        id="tier_hard",
        name="Hart — Debloat",
        icon="🔴",
        desc="Maximal: Mittel + aggressiver Debloat (Cortana, Copilot, Recall, Teams, OneDrive), "
             "volle Performance/Netzwerk/Audio-Tweaks, W11-Classic-UI. Für erfahrene Nutzer — "
             "vorher am besten einen Wiederherstellungspunkt erstellen (Settings).",
        color="#ef4444",
        tweak_ids=list(_TIER_HARD),
    ),

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
            "disable_wpbt",
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
            "disable_storage_sense",
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
    # "All Safe" wird dynamisch befüllt, damit es auch bei direktem Aufruf
    # (nicht nur beim UI-Rendern) eine gültige Tweak-Liste hat.
    for p in result:
        if p.id == "all_safe":
            p.tweak_ids = get_all_safe_ids()
    if user_presets:
        result.extend(user_presets)
    return result
