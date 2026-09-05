"""
GameOptimizerPro Export / Import
Exportiert und importiert:
  - Tweak-Auswahl (welche Tweaks applied sind)
  - GPU-Profile
  - Tweak-Presets (user-defined)

Format: JSON mit Versionierung und Metadaten.
"""

import json, os, shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


EXPORT_VERSION = "1.0"
EXPORT_MAGIC   = "gop_export"


class ExportImport:
    def __init__(self, profiles_dir: str, logs_dir: str):
        self.profiles_dir = Path(profiles_dir)
        self.logs_dir     = Path(logs_dir)

    # ── Export ────────────────────────────────────────────────────────────────

    def export(
        self,
        path:             str,
        include_tweaks:   bool = True,
        include_profiles: bool = True,
        include_presets:  bool = True,
        applied_tweaks:   dict = None,     # {tweak_id: timestamp}
        user_presets:     list = None,     # list of TweakPreset.to_dict()
    ) -> tuple[bool, str]:
        """
        Export to a .nextune JSON file.
        Returns (success, message).
        """
        data = {
            "_magic":   EXPORT_MAGIC,
            "_version": EXPORT_VERSION,
            "_created": datetime.now().isoformat(),
            "_host":    os.environ.get("COMPUTERNAME", "unknown"),
        }

        if include_tweaks and applied_tweaks is not None:
            data["tweaks"] = applied_tweaks

        if include_profiles:
            profiles = []
            for f in sorted(self.profiles_dir.glob("*.json")):
                try:
                    with open(f, encoding="utf-8") as fh:
                        profiles.append(json.load(fh))
                except:
                    pass
            data["gpu_profiles"] = profiles

        if include_presets and user_presets:
            data["user_presets"] = user_presets

        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            n_tweaks   = len(data.get("tweaks", {}))
            n_profiles = len(data.get("gpu_profiles", []))
            n_presets  = len(data.get("user_presets", []))
            return True, (
                f"Export erfolgreich:\n"
                f"  {n_tweaks} Tweaks\n"
                f"  {n_profiles} GPU-Profile\n"
                f"  {n_presets} User-Presets\n"
                f"→ {path}"
            )
        except Exception as e:
            return False, f"Export fehlgeschlagen: {e}"

    # ── Import ────────────────────────────────────────────────────────────────

    def import_file(self, path: str) -> tuple[bool, dict, str]:
        """
        Import from a .nextune file.
        Returns (success, data_dict, message).
        data_dict contains:
          tweaks:       {tweak_id: timestamp}
          gpu_profiles: [list of profile dicts]
          user_presets: [list of preset dicts]
          meta:         {version, created, host}
        """
        # Reject implausibly large files before parsing — a .nextune is a small
        # JSON (tweaks + a handful of GPU profiles); anything above 10 MB is
        # corrupt or hostile and shouldn't be handed to json.load.
        MAX_IMPORT_SIZE = 10 * 1024 * 1024
        try:
            if os.path.getsize(path) > MAX_IMPORT_SIZE:
                return False, {}, "Datei zu groß (>10 MB) — vermutlich beschädigt."
        except OSError as e:
            return False, {}, f"Datei nicht gefunden: {e}"

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            return False, {}, f"Datei konnte nicht gelesen werden: {e}"

        if raw.get("_magic") != EXPORT_MAGIC:
            return False, {}, "Ungültige Datei — kein GameOptimizerPro Export"

        result = {
            "meta": {
                "version": raw.get("_version", "?"),
                "created": raw.get("_created", "?"),
                "host":    raw.get("_host", "?"),
            },
            "tweaks":       raw.get("tweaks", {}),
            "gpu_profiles": raw.get("gpu_profiles", []),
            "user_presets": raw.get("user_presets", []),
        }

        n_tweaks   = len(result["tweaks"])
        n_profiles = len(result["gpu_profiles"])
        n_presets  = len(result["user_presets"])

        msg = (
            f"Import gelesen:\n"
            f"  Version: {result['meta']['version']}\n"
            f"  Erstellt: {result['meta']['created'][:16]}\n"
            f"  Von PC: {result['meta']['host']}\n"
            f"  {n_tweaks} Tweaks, {n_profiles} GPU-Profile, {n_presets} Presets"
        )
        return True, result, msg

    def apply_imported_profiles(
        self, profiles: list[dict]
    ) -> tuple[int, int]:
        """
        Write imported GPU profiles to profiles directory.
        Returns (imported_count, skipped_count).
        """
        imported = skipped = 0
        for pd in profiles:
            name = pd.get("name", "")
            if not name or name.startswith("__"):
                skipped += 1
                continue
            safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
            dest = self.profiles_dir / f"{safe}.json"
            try:
                self.profiles_dir.mkdir(parents=True, exist_ok=True)
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(pd, f, indent=2)
                imported += 1
            except:
                skipped += 1
        return imported, skipped
