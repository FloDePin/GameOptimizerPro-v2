"""
GameOptimizerPro v2.1 — Internationalization (i18n)
DE/EN language switching. All UI strings go through t().
Selected language is persisted to disk so it survives a restart.
"""

import json
from pathlib import Path
from typing import Callable

# Language preference is stored next to the app so it survives restarts
_LANG_FILE = Path(__file__).resolve().parent.parent / "profiles" / "language.json"

_current_lang = "en"
_listeners: list[Callable] = []


def _load_saved_lang() -> str:
    """Load the saved language from disk, default to English."""
    try:
        if _LANG_FILE.exists():
            data = json.loads(_LANG_FILE.read_text(encoding="utf-8"))
            lang = data.get("lang", "en")
            if lang in ("de", "en"):
                return lang
    except Exception:
        pass
    return "en"


def _save_lang(lang: str):
    """Persist the chosen language to disk."""
    try:
        _LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LANG_FILE.write_text(json.dumps({"lang": lang}), encoding="utf-8")
    except Exception:
        pass

STRINGS = {
    # ── App general ───────────────────────────────────────────────────────────
    "app_subtitle":       {"de": "Windows & Gaming Optimizer v2.0 -- by FloDePin",
                           "en": "Windows & Gaming Optimizer v2.0 -- by FloDePin"},
    "btn_status_check":   {"de": "⟳ Status prüfen",        "en": "⟳ Check Status"},
    "btn_apply_selected": {"de": ">> Apply Selected",       "en": ">> Apply Selected"},
    "btn_revert_all":     {"de": "↩ Revert All",            "en": "↩ Revert All"},
    "btn_select_all":     {"de": "[x] Select All",          "en": "[x] Select All"},
    "btn_deselect_all":   {"de": "[ ] Deselect All",        "en": "[ ] Deselect All"},
    "btn_refresh":        {"de": "⟳ Aktualisieren",         "en": "⟳ Refresh"},
    "btn_apply":          {"de": "▶ Apply",                 "en": "▶ Apply"},
    "btn_delete":         {"de": "🗑 Löschen",              "en": "🗑 Delete"},
    "lbl_ready":          {"de": "Bereit — Tweaks auswählen und Apply Selected klicken.",
                           "en": "Ready — select tweaks and click Apply Selected."},
    # ── Tabs ──────────────────────────────────────────────────────────────────
    "tab_dashboard":      {"de": "[SYS]  Dashboard",        "en": "[SYS]  Dashboard"},
    "tab_optimizer":      {"de": "[WIN]  Optimizer",        "en": "[WIN]  Optimizer"},
    "tab_gpu":            {"de": "[GPU]  GPU Tuner",        "en": "[GPU]  GPU Tuner"},
    "tab_stress":         {"de": "[TEST] Stress Test",      "en": "[TEST] Stress Test"},
    "tab_compare":        {"de": "[CMP]  Compare",          "en": "[CMP]  Compare"},
    "tab_bios":           {"de": "[BIOS] BIOS Guide",       "en": "[BIOS] BIOS Guide"},
    "tab_settings":       {"de": "[SET]  Settings",         "en": "[SET]  Settings"},
    # ── Optimizer ─────────────────────────────────────────────────────────────
    "sec_presets":        {"de": "⭐  Presets",             "en": "⭐  Presets"},
    "sec_windows":        {"de": "[WIN]  Windows",          "en": "[WIN]  Windows"},
    "sec_gaming":         {"de": "[GAME] Gaming",           "en": "[GAME] Gaming"},
    "sec_network":        {"de": "[NET]  Network",          "en": "[NET]  Network"},
    "sec_verify":         {"de": "[✓]   Verify",            "en": "[✓]   Verify"},
    "sec_exim":           {"de": "[↕]   Export/Import",     "en": "[↕]   Export/Import"},
    "lbl_optimizer":      {"de": "Optimizer",               "en": "Optimizer"},
    "lbl_sections":       {"de": "SECTIONS",                "en": "SECTIONS"},
    "hint_applied":       {"de": "✓ aktiv",                 "en": "✓ active"},
    "hint_einmalig":      {"de": "⟳ einmalig",              "en": "⟳ one-time"},
    # ── GPU Tuner ─────────────────────────────────────────────────────────────
    "tune_mode_oc":       {"de": "⚡ Overclock Only",       "en": "⚡ Overclock Only"},
    "tune_mode_uv":       {"de": "❄ Undervolt Only",        "en": "❄ Undervolt Only"},
    "tune_mode_ocuv":     {"de": "🚀 OC + UV  (Empfohlen)", "en": "🚀 OC + UV  (Recommended)"},
    "btn_start_tune":     {"de": "▶  START TUNE",           "en": "▶  START TUNE"},
    "btn_abort":          {"de": "■  ABORT",                "en": "■  ABORT"},
    "lbl_idle":           {"de": "Idle",                    "en": "Idle"},
    # ── Dashboard ─────────────────────────────────────────────────────────────
    "lbl_sys_overview":   {"de": "System Overview",         "en": "System Overview"},
    "lbl_live_telem":     {"de": "LIVE GPU TELEMETRY",      "en": "LIVE GPU TELEMETRY"},
    "lbl_throttle":       {"de": "Throttle:",               "en": "Throttle:"},
    "lbl_none":           {"de": "None",                    "en": "None"},
    # ── Stress Test ───────────────────────────────────────────────────────────
    "lbl_internal_stress":{"de": "Internal Stress Test",    "en": "Internal Stress Test"},
    "btn_start_test":     {"de": "▶ Start Internal Test",   "en": "▶ Start Internal Test"},
    "btn_stop_test":      {"de": "■ Stop",                  "en": "■ Stop"},
    "lbl_duration":       {"de": "Duration:",               "en": "Duration:"},
    "lbl_seconds":        {"de": "seconds",                 "en": "seconds"},
    "lbl_max_temp":       {"de": "Max Temp:",               "en": "Max Temp:"},
    # ── Settings ──────────────────────────────────────────────────────────────
    "lbl_settings":       {"de": "Settings",                "en": "Settings"},
    "lbl_startup":        {"de": "Startup",                 "en": "Startup"},
    "lbl_autostart":      {"de": "Mit Windows starten",     "en": "Start with Windows"},
    "lbl_load_profile":   {"de": "Tray-Default GPU-Profil beim Start laden",
                           "en": "Load tray default GPU profile on startup"},
    "btn_load_now":       {"de": "⟳ Jetzt Startup-Profil laden",
                           "en": "⟳ Load Startup Profile Now"},
    "lbl_ab_setup":       {"de": "Afterburner Setup Checker","en": "Afterburner Setup Checker"},
    "lbl_about":          {"de": "About",                   "en": "About"},
    # ── Tray ──────────────────────────────────────────────────────────────────
    "tray_open":          {"de": "⚡ GameOptimizerPro öffnen","en": "⚡ Open GameOptimizerPro"},
    "tray_gpu_profile":   {"de": "GPU Profil ▶",            "en": "GPU Profile ▶"},
    "tray_reset_gpu":     {"de": "GPU auf Stock zurücksetzen","en": "Reset GPU to Stock"},
    "tray_exit":          {"de": "Beenden",                 "en": "Exit"},
    "tray_no_profiles":   {"de": "Keine Profile vorhanden", "en": "No profiles saved"},
    # ── Game Profiles ─────────────────────────────────────────────────────────
    "lbl_game_profiles":  {"de": "Per-Game Profile",        "en": "Per-Game Profiles"},
    "lbl_game_add":       {"de": "+ Spiel hinzufügen",      "en": "+ Add Game"},
    "lbl_game_exe":       {"de": "Prozessname (.exe)",      "en": "Process name (.exe)"},
    "lbl_game_profile":   {"de": "GPU-Profil beim Start",   "en": "GPU profile on launch"},
    "lbl_monitoring":     {"de": "Überwachung aktiv",       "en": "Monitoring active"},
    # ── History ───────────────────────────────────────────────────────────────
    "lbl_tune_history":   {"de": "Tune History",            "en": "Tune History"},
    "lbl_no_history":     {"de": "Noch keine Tune-Runs vorhanden.",
                           "en": "No tune runs recorded yet."},
    # ── Toast warnings ────────────────────────────────────────────────────────
    "toast_temp_title":   {"de": "GPU Temperatur-Warnung",  "en": "GPU Temperature Warning"},
    "toast_temp_msg":     {"de": "GPU-Temperatur: {temp}°C — über dem Limit von {limit}°C!",
                           "en": "GPU temperature: {temp}°C — above limit of {limit}°C!"},
    # ── Update check ─────────────────────────────────────────────────────────
    "lbl_update_avail":   {"de": "Update verfügbar: v{ver}",
                           "en": "Update available: v{ver}"},
    "lbl_up_to_date":     {"de": "Aktuell (v{ver})",        "en": "Up to date (v{ver})"},
    "btn_download":       {"de": "⬇ Herunterladen",         "en": "⬇ Download"},
    # ── Common ───────────────────────────────────────────────────────────────
    "lbl_error":          {"de": "Fehler",                  "en": "Error"},
    "lbl_ok":             {"de": "OK",                      "en": "OK"},
    "lbl_cancel":         {"de": "Abbrechen",               "en": "Cancel"},
    "lbl_yes":            {"de": "Ja",                      "en": "Yes"},
    "lbl_no":             {"de": "Nein",                    "en": "No"},
    "lbl_save":           {"de": "Speichern",               "en": "Save"},
    "lbl_loading":        {"de": "Lade...",                 "en": "Loading..."},
    "lbl_done":           {"de": "Fertig.",                 "en": "Done."},
}


def t(key: str, **kwargs) -> str:
    """Translate a key to current language. Supports {placeholder} formatting."""
    entry = STRINGS.get(key)
    if not entry:
        return key  # fallback: return key itself
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def current_lang() -> str:
    return _current_lang


def init_lang():
    """Load the saved language at startup. Call before building the UI."""
    global _current_lang
    _current_lang = _load_saved_lang()
    return _current_lang


def set_lang(lang: str):
    global _current_lang
    if lang in ("de", "en"):
        _current_lang = lang
        _save_lang(lang)
        for cb in _listeners:
            try:
                cb(lang)
            except Exception:
                pass


def on_lang_change(cb: Callable):
    """Register a callback that fires when language changes."""
    if cb not in _listeners:
        _listeners.append(cb)


def toggle() -> str:
    """Toggle between DE and EN, return new lang."""
    new = "en" if _current_lang == "de" else "de"
    set_lang(new)
    return new
