"""
GameOptimizerPro v2.1 — Per-Game Profile Monitor
Überwacht laufende Prozesse via psutil.
Wenn ein bekanntes Spiel startet → lädt das zugewiesene GPU-Profil.
Wenn das Spiel schließt → lädt das "default" Profil zurück.
Ressourcenschonend: prüft nur alle 3s, nur wenn Prozessliste sich geändert hat.
"""

import json, threading, time, os
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Callable


@dataclass
class GameEntry:
    exe:          str    # z.B. "Cyberpunk2077.exe" (case-insensitive)
    display_name: str    # z.B. "Cyberpunk 2077"
    profile_name: str    # Name des GOP GPU-Profils
    restore_profile: str = "__tray_default__"  # Profil nach Spielende
    enabled:      bool = True
    cpu_target:   str = ""   # CPU-Pinning-Ziel (Key aus cpu_topology.pin_targets), "" = kein Pinning


class GameMonitor:
    GAMES_FILE = "profiles/game_profiles.json"
    CHECK_INTERVAL = 3  # Sekunden zwischen Checks

    # Bekannte Spiele — vorgefüllt für komfort
    DEFAULT_GAMES = [
        GameEntry("Cyberpunk2077.exe",    "Cyberpunk 2077",          ""),
        GameEntry("cs2.exe",              "Counter-Strike 2",        ""),
        GameEntry("r5apex.exe",           "Apex Legends",            ""),
        GameEntry("RainbowSix.exe",       "Rainbow Six Siege",       ""),
        GameEntry("Overwatch.exe",        "Overwatch 2",             ""),
        GameEntry("Valorant-Win64-Shipping.exe", "Valorant",         ""),
        GameEntry("EscapeFromTarkov.exe", "Escape From Tarkov",      ""),
        GameEntry("RocketLeague.exe",     "Rocket League",           ""),
        GameEntry("FortniteClient-Win64-Shipping.exe", "Fortnite",   ""),
        GameEntry("GTA5.exe",             "GTA V",                   ""),
        GameEntry("eldenring.exe",        "Elden Ring",              ""),
        GameEntry("Witcher3.exe",         "The Witcher 3",           ""),
        GameEntry("DOOM.exe",             "DOOM Eternal",            ""),
        GameEntry("bf2042.exe",           "Battlefield 2042",        ""),
        GameEntry("HogwartsLegacy.exe",   "Hogwarts Legacy",         ""),
    ]

    def __init__(self, base_dir: str, ab, pm, cr=None):
        self.base    = Path(base_dir)
        self.ab      = ab
        self.pm      = pm
        self.cr      = cr
        self._games: list[GameEntry] = []
        self._active_game: Optional[str] = None  # currently running exe
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._last_procs: set[str] = set()
        self._apply_lock = threading.Lock()
        self._pinned_pids: set[int] = set()  # PIDs already pinned for the active game

        # CPU topology — detected once, read-only
        try:
            from core import cpu_topology
            self._topo = cpu_topology.detect()
        except Exception:
            self._topo = None

        # Callbacks
        self._on_game_start: Optional[Callable] = None
        self._on_game_stop:  Optional[Callable] = None
        self._on_cpu_pin:    Optional[Callable] = None
        self._pin_reported = False  # report the main-process pin result only once

        self._load_games()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _games_path(self) -> Path:
        return self.base / self.GAMES_FILE

    def _load_games(self):
        path = self._games_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # Tolerate unknown/legacy keys so old files still load
                fields = set(GameEntry.__dataclass_fields__.keys())
                self._games = [GameEntry(**{k: v for k, v in g.items() if k in fields})
                               for g in data]
                return
            except:
                pass
        # First run: use defaults (no profile assigned yet)
        self._games = [GameEntry(g.exe, g.display_name, g.profile_name)
                       for g in self.DEFAULT_GAMES]
        self._save_games()

    def _save_games(self):
        self._games_path().parent.mkdir(parents=True, exist_ok=True)
        self._games_path().write_text(
            json.dumps([asdict(g) for g in self._games], indent=2),
            encoding="utf-8"
        )

    # ── Game list management ──────────────────────────────────────────────────

    def get_games(self) -> list[GameEntry]:
        return list(self._games)

    def add_game(self, exe: str, display_name: str, profile_name: str):
        # Avoid duplicates
        exe_lower = exe.lower()
        for g in self._games:
            if g.exe.lower() == exe_lower:
                g.display_name  = display_name
                g.profile_name  = profile_name
                self._save_games()
                return
        self._games.append(GameEntry(exe, display_name, profile_name))
        self._save_games()

    def update_game(self, exe: str, profile_name: str,
                    enabled: bool = True, restore: str = "__tray_default__",
                    cpu_target: Optional[str] = None):
        for g in self._games:
            if g.exe.lower() == exe.lower():
                g.profile_name  = profile_name
                g.enabled       = enabled
                g.restore_profile = restore
                if cpu_target is not None:
                    g.cpu_target = cpu_target
                self._save_games()
                return

    def set_cpu_target(self, exe: str, cpu_target: str):
        """Set only the CPU-pinning target for a game (keeps other fields)."""
        for g in self._games:
            if g.exe.lower() == exe.lower():
                g.cpu_target = cpu_target
                self._save_games()
                return

    # ── CPU topology accessors (for UI) ───────────────────────────────────────

    @property
    def topology(self):
        return self._topo

    def cpu_pin_targets(self):
        """Available pin targets for this machine, or [] if unsupported."""
        if self._topo and self._topo.ok:
            return self._topo.pin_targets()
        return []

    def remove_game(self, exe: str):
        self._games = [g for g in self._games if g.exe.lower() != exe.lower()]
        self._save_games()

    # ── Monitor loop ──────────────────────────────────────────────────────────

    def on_game_start(self, cb: Callable): self._on_game_start = cb
    def on_game_stop(self,  cb: Callable): self._on_game_stop  = cb
    def on_cpu_pin(self,    cb: Callable): self._on_cpu_pin    = cb

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _get_process_names(self) -> set[str]:
        """Get current process names (lowercase). Lightweight psutil call."""
        try:
            import psutil
            return {p.name().lower() for p in psutil.process_iter(['name'])
                    if p.info['name']}
        except:
            return set()

    def _loop(self):
        while self._running:
            try:
                procs = self._get_process_names()

                # Only act if process list changed
                if procs == self._last_procs:
                    time.sleep(self.CHECK_INTERVAL)
                    continue
                self._last_procs = procs

                # Check each enabled game — qualifies if it has a GPU profile
                # OR a CPU-pinning target assigned
                found_game = None
                for game in self._games:
                    if not game.enabled:
                        continue
                    if not game.profile_name and not game.cpu_target:
                        continue
                    if game.exe.lower() in procs:
                        found_game = game
                        break

                if found_game and self._active_game != found_game.exe.lower():
                    # New game started
                    self._active_game = found_game.exe.lower()
                    self._pinned_pids.clear()
                    self._pin_reported = False
                    self._apply_profile(found_game.profile_name)
                    self._apply_cpu_pin(found_game)
                    if self._on_game_start:
                        self._on_game_start(found_game)

                elif found_game and self._active_game == found_game.exe.lower():
                    # Still running — re-pin any newly spawned child processes
                    self._apply_cpu_pin(found_game)

                elif not found_game and self._active_game:
                    # Active game stopped
                    stopped_exe = self._active_game
                    self._active_game = None
                    self._pinned_pids.clear()
                    # Find restore profile
                    for game in self._games:
                        if game.exe.lower() == stopped_exe:
                            self._apply_profile(game.restore_profile)
                            break
                    if self._on_game_stop:
                        self._on_game_stop(stopped_exe)

            except Exception as e:
                pass  # Never crash the monitor thread

            time.sleep(self.CHECK_INTERVAL)

    def _apply_profile(self, profile_name: str):
        """Apply a GPU profile by name."""
        if not profile_name or not self.ab.available:
            return
        try:
            p = self.pm.load(profile_name)
            if p:
                def _do(p=p):
                    with self._apply_lock:
                        self.ab.write_and_apply(2, p)
                        if self.cr:
                            self.cr.save_last_applied(p.to_dict())
                threading.Thread(target=_do, daemon=True).start()
        except:
            pass

    def _apply_cpu_pin(self, game: GameEntry):
        """Pin the game process + its children onto the chosen cores.
        Runs on the monitor thread; best-effort, never raises. Only pins PIDs
        not seen yet this session so repeated calls are cheap."""
        if not game.cpu_target or not self._topo or not self._topo.ok:
            return
        logicals = self._topo.target_logicals(game.cpu_target)
        if not logicals:
            return
        try:
            import psutil
            from core import cpu_pinning
            exe_low = game.exe.lower()
            procs = []
            for p in psutil.process_iter(["name", "pid"]):
                try:
                    if (p.info["name"] or "").lower() == exe_low:
                        procs.append(p)
                except Exception:
                    continue
            main_ok = None  # pin result of the game's own process (for reporting)
            for proc in procs:
                # The exe-matching process itself is the "main" one; children follow
                for is_main, pr in ([(True, proc)] +
                                    [(False, c) for c in cpu_pinning._safe_children(proc)]):
                    if pr.pid in self._pinned_pids:
                        continue
                    self._pinned_pids.add(pr.pid)
                    ok = cpu_pinning.pin_process(pr.pid, self._topo, logicals)
                    if is_main and main_ok is None:
                        main_ok = ok

            # Report the main-process result once (UI surfaces overwrite/failure)
            if main_ok is not None and not self._pin_reported:
                self._pin_reported = True
                if self._on_cpu_pin:
                    label = self._topo.target_logicals(game.cpu_target) or []
                    detail = (f"{len(label)} Kerne" if main_ok else
                              "Pinning wurde nicht übernommen (evtl. überschrieben "
                              "oder Kerne geparkt)")
                    try:
                        self._on_cpu_pin(game, main_ok, detail)
                    except Exception:
                        pass
        except Exception:
            pass

    @property
    def active_game(self) -> Optional[str]:
        return self._active_game

    @property
    def is_running(self) -> bool:
        return self._running
