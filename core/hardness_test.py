"""
GameOptimizerPro v2.0 — hardness test (round 33)

The tuner tests one load at a time: compute (CUDA), memory copies, FurMark. A game
that is streamed or recorded puts several engines to work AT ONCE — the game's 3D
frames, the encoder (NVENC) for every frame, CUDA for scaling, a browser beside it —
and the card switches between their contexts all the time. A profile can pass every
single test and still compute wrong that way — measured: compute + encoder at once
gave wrong results in about one of four 25-s runs, never at stock.

The hardness test runs those loads together on the profile that is applied now, in
phases that change every PHASE_S seconds with a short idle gap (IDLE_S) between them:
the card drops its clocks and every load starts at once — like leaving a menu or a
loading screen.

  game + recording           FurMark (3D; without FurMark the "mixed" CUDA load)
                             + the encoder worker (scene, scaling, NVENC at 60 fps)
  load changes + recording   verified bursts at the top of the curve + encoder
  game + recording + compute 3D + encoder + verified bursts: three contexts
  game + recording + memory  3D + encoder + verified memory copies

FurMark's OpenGL and Vulkan demos take turns, light and heavy. Every compute result and every
converted frame is checked; a load that stops answering is a hung GPU; the System
log is read every POLL_S seconds (nvlddmkm 13 / 14 / 153, Display 4101). A failure
stops everything at once and names the phase, the loads and the state just before
it (gpu_watchdog.fault_point) — with the curve points involved, for a targeted
make-safer. The fault goes into the field list like a game's (the next tune keeps
more margin there). It never changes a clock itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core import furmark
from core import gpu_watchdog as WD
from core.i18n import tr

APP_DIR = Path(__file__).resolve().parent.parent
WORKER = APP_DIR / "_stress_worker.py"

PHASE_S = 150          # one load combination
IDLE_S = 8             # all loads off between phases: clocks drop, then everything starts at once
START_S = 45           # first answer of a load (cupy import, CUDA context, kernels)
HANG_S = 10            # a running load silent this long = hung GPU
POLL_S = 2.0           # System log
SETTLE_S = 3.0         # after a failure: the driver's entries come within seconds
EXIT_ERROR, EXIT_NO_ENCODER = 3, 4
STOP_GRACE_S = 8.0     # a load asked to end gets this long before it is killed
KILL_SLACK_S = 3.0     # GPU events this close to a kill are the kill's, not the profile's

PHASES = (
    ("game_rec", ("Spiel + Aufnahme", "game + recording"), ("game", "encode")),
    ("changes_rec", ("Lastwechsel + Aufnahme", "load changes + recording"), ("transient", "encode")),
    ("game_rec_compute", ("Spiel + Aufnahme + Rechnen", "game + recording + compute"),
     ("game", "encode", "transient")),
    ("game_rec_mem", ("Spiel + Aufnahme + Speicher", "game + recording + memory"), ("game", "encode", "mem")),
)
LOAD_NAMES = {"game": ("3D-Last", "3D load"), "encode": ("Aufnahme (NVENC)", "recording (NVENC)"),
              "transient": ("Lastwechsel", "load changes"), "mem": ("Speicher", "memory")}
# FurMark in turn: OpenGL / Vulkan, light (a game under an FPS cap: partly loaded at the top of the
# curve — live 43 % at 2880 MHz / 1050 mV) and heavy (8x MSAA: full load, mid-curve)
FURMARK_VARIANTS = (("furmark-gl", 0), ("furmark-vk", 8), ("furmark-vk", 0), ("furmark-gl", 8))


def plan(minutes: float, phase_s: float = PHASE_S) -> list:
    """[(key, (de, en), loads, seconds)] — the four combinations in turn, equal phases of about
    phase_s seconds that fill the time."""
    total = max(float(phase_s), float(minutes) * 60)
    n = max(1, round(total / phase_s))
    return [PHASES[i % len(PHASES)] + (total / n,) for i in range(n)]


@dataclass
class HardResult:
    passed: bool = False
    aborted: bool = False
    kind: str = ""              # compute | frame | stall | hang | crash | driver | temp | stopped | ""
    reason: str = ""
    phase: str = ""
    load: str = ""
    at_s: float = 0.0           # seconds into the test
    t_fail: float = 0.0         # epoch of the failure
    seconds: float = 0.0
    point: dict = field(default_factory=dict)
    anchors: list = field(default_factory=list)
    events: list = field(default_factory=list)       # [(epoch, source, id)]
    encoder: bool = True        # the encoder ran (False: none here)
    game: str = ""              # "FurMark" | "CUDA"
    peak_temp: int = 0
    max_w: float = 0.0
    max_mhz: float = 0.0
    max_mv: float = 0.0
    profile: str = ""
    log_path: str = ""

    @property
    def unstable(self) -> bool:
        return self.kind in ("compute", "frame", "stall", "hang", "crash", "driver")


class _Load:
    """One load process; its output read in a thread (the pipe never blocks it)."""

    def __init__(self, kind: str, cmd: list, talks: bool = True, env: Optional[dict] = None,
                 cwd: Optional[str] = None, startupinfo=None):
        self.kind, self.cmd, self.talks = kind, cmd, talks
        self.env, self.cwd, self.startupinfo = env, cwd, startupinfo
        self.stop_file = (env or {}).get("GOP_STRESS_STOP_FILE", "")
        self.proc: Optional[subprocess.Popen] = None
        self.t0 = self.last = 0.0
        self.err: list = []
        self.noenc = ""
        self.vals: dict = {}

    def start(self):
        self.t0 = time.time()
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                     env=self.env, cwd=self.cwd, startupinfo=self.startupinfo,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                if not self.talks:
                    continue
                self.last = time.time()
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "ERR":
                    self.err.append(" ".join(parts[1:]))
                elif parts[0] == "NOENC":
                    self.noenc = " ".join(parts[1:]) or "no encoder"
                elif parts[0] in ("RATE", "BW", "ENC") and len(parts) > 1:
                    try:
                        self.vals[parts[0]] = float(parts[1])
                    except ValueError:
                        pass
        except Exception:
            pass

    def check(self, now: float) -> Optional[tuple]:
        """None = fine, else (kind, detail)."""
        rc = self.proc.poll() if self.proc else None
        if rc is not None:
            if rc == EXIT_NO_ENCODER or self.noenc:
                return ("noenc", self.noenc)
            if self.err:
                e = self.err[-1]
                return ("stall" if e.startswith("stall") else "frame" if e.startswith("frame") else "compute", e)
            if rc == EXIT_ERROR:
                return ("compute", "exit 3")
            if not self.talks and rc == 0:
                return ("stopped", "")           # FurMark closed (by hand)
            return ("crash", f"exit {rc}")
        if self.talks:
            if self.last and now - self.last >= HANG_S:
                return ("hang", f"{now - self.last:.0f}")
            if not self.last and now - self.t0 >= START_S:
                return ("hang", f"{now - self.t0:.0f}")
        return None

    def ended_badly(self) -> Optional[tuple]:
        """After the end: a result check failed on the way out (ERR / exit 3) -> (kind, detail)."""
        if self.err:
            e = self.err[-1]
            return ("stall" if e.startswith("stall") else "frame" if e.startswith("frame") else "compute", e)
        if self.proc is not None and self.proc.poll() == EXIT_ERROR:
            return ("compute", "exit 3")
        return None

    def ask_stop(self):
        """End without a kill: a worker finds its stop file (its product finishes, the encoder
        closes its session), FurMark gets a WM_CLOSE to its window. A kill in the middle of GPU
        work while another program encodes makes the driver log nvlddmkm 153 — live 6 of 6."""
        p = self.proc
        if p is None or p.poll() is not None:
            return
        if self.stop_file:
            try:
                Path(self.stop_file).touch()
            except OSError:
                pass
        else:
            _close_windows(p.pid)

    def stop(self, grace_s: float = STOP_GRACE_S) -> bool:
        """-> True when the process had to be killed (its GPU events are ours)."""
        p = self.proc
        if p is None:
            return False
        self.ask_stop()
        killed = False
        try:
            p.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            killed = True
            try:
                p.kill()
                p.wait(timeout=10)
            except Exception:
                pass
        except Exception:
            pass
        if self.stop_file:
            try:
                os.remove(self.stop_file)          # our own marker file
            except OSError:
                pass
        return killed


def _close_windows(pid: int):
    """WM_CLOSE to the top-level windows of a process (FurMark: a normal exit)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _lp):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid:
                found.append(hwnd)
            return True
        user32.EnumWindows(each, 0)
        for hwnd in found:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
    except Exception:
        pass


class HardnessTest:
    def __init__(self, read_stats: Callable, logs_dir, minutes: float = 20, furmark_path: Optional[str] = None,
                 max_temp: int = 85, profile: Optional[dict] = None, stop_event: Optional[threading.Event] = None,
                 on_progress: Optional[Callable[[int, str], None]] = None,
                 on_log: Optional[Callable[[str, str], None]] = None, phase_s: float = PHASE_S,
                 idle_s: float = IDLE_S, tail_factory: Optional[Callable] = None,
                 load_factory: Optional[Callable] = None, record_field: bool = True,
                 gpu_name: str = ""):
        self._read = read_stats
        self.logs_dir = Path(logs_dir)
        self.minutes = minutes
        self.furmark = furmark_path if furmark_path and os.path.exists(furmark_path) and furmark.is_v2(
            furmark_path) else None
        self.max_temp = int(max_temp)
        self.profile = profile or {}
        self.stop_event = stop_event or threading.Event()
        self._progress = on_progress
        self._on_log = on_log
        self.phase_s, self.idle_s = phase_s, idle_s
        self._tail_factory = tail_factory
        self._load_factory = load_factory or self._make_load
        self.record_field = record_field
        self.gpu = gpu_name
        self.samples: list = []
        self._loads: list = []
        self._log_f = None
        self._tail = None
        self._encoder_ok = True
        self._delivered = False
        self._kills: list = []
        self._n_loads = 0
        self._gl_vk = 0

    # ── output ────────────────────────────────────────────────────────────────
    def _log(self, text: str, tag: str = "info"):
        if self._log_f:
            try:
                self._log_f.write(f"[{datetime.now():%H:%M:%S}] {text}\n")
                self._log_f.flush()
            except OSError:
                pass
        if self._on_log:
            try:
                self._on_log(text, tag)
            except Exception:
                pass

    def _prog(self, pct: float, text: str):
        if self._progress:
            try:
                self._progress(int(max(0, min(100, pct))), text)
            except Exception:
                pass

    # ── loads ─────────────────────────────────────────────────────────────────
    def _make_load(self, kind: str, seconds: float) -> _Load:
        py = sys.executable
        if kind == "game" and self.furmark:
            demo, msaa = FURMARK_VARIANTS[self._gl_vk % len(FURMARK_VARIANTS)]
            self._gl_vk += 1
            self._log(f"  FurMark: {furmark.DEMOS.get(demo, demo)}" + (f", {msaa}× MSAA" if msaa else ""), "dim")
            args = furmark.build_args(self.furmark, 1920, 1080, int(seconds) + 30, demo, msaa)
            return _Load(kind, args, talks=False, cwd=os.path.dirname(self.furmark),
                         startupinfo=furmark._no_focus_startupinfo())
        mode = {"game": "mixed", "encode": "encode", "transient": "transient", "mem": "mem"}[kind]
        self._n_loads += 1
        stop = os.path.join(tempfile.gettempdir(), f"gop_stop_{os.getpid()}_{self._n_loads}")
        try:
            os.remove(stop)                        # a leftover of an earlier run
        except OSError:
            pass
        env = dict(os.environ, GOP_STRESS_STOP_FILE=stop)
        if self._delivered:              # a load answered before: CUDA works, a start-up error is instability
            env["GOP_STRESS_GPU_OK"] = "1"
        return _Load(kind, [py, str(WORKER), str(os.getpid()), mode], env=env, cwd=str(APP_DIR))

    def _start_loads(self, loads: tuple, seconds: float):
        self._loads = []
        for kind in loads:
            if kind == "encode" and not self._encoder_ok:
                continue
            ld = self._load_factory(kind, seconds)
            try:
                ld.start()
            except OSError as e:
                self._log(tr(f"  {self._load_name(kind)} ließ sich nicht starten: {e}",
                             f"  {self._load_name(kind)} could not be started: {e}"), "warning")
                continue
            self._loads.append(ld)

    def _stop_loads(self) -> list:
        """All asked at once (as they started), then each waited for; a kill is remembered.
        -> [(load, (kind, detail))] of the loads whose last result was wrong — a load step
        down (everything ends at once) is a moment where an edge profile fails, too."""
        loads, self._loads = self._loads, []
        for ld in loads:
            ld.ask_stop()
        bad = []
        for ld in loads:
            killed = ld.stop()
            st = ld.ended_badly()
            if st:
                bad.append((ld, st))
            if killed:
                self._kills.append(time.time())
                self._log(tr(f"  {self._load_name(ld.kind)} endete nicht von selbst — beendet; GPU-Ereignisse "
                             f"in diesen Sekunden zählen nicht", f"  {self._load_name(ld.kind)} did not end by "
                             f"itself — killed; GPU events in these seconds don't count"), "warning")
        return bad

    @staticmethod
    def _load_name(kind: str) -> str:
        de, en = LOAD_NAMES.get(kind, (kind, kind))
        return tr(de, en)

    # ── watching ──────────────────────────────────────────────────────────────
    def _sample(self) -> Optional[dict]:
        try:
            from core.gpu_flight import sample_of
            s = sample_of(self._read())
        except Exception:
            return None
        self.samples.append(s)
        if len(self.samples) > 4000:
            del self.samples[:1000]
        return s

    def _gpu_events(self) -> list:
        if self._tail is None:
            return []
        try:
            from core.gpu_flight import GPU_SOURCES
            evs = [(t, src, eid) for t, src, eid in self._tail.poll() if eid in GPU_SOURCES.get(src, ())]
        except Exception:
            return []
        # the log has whole seconds: an event up to a second "before" a kill can be the kill's
        return [e for e in evs if not any(k - 1 - KILL_SLACK_S <= e[0] <= k + KILL_SLACK_S for k in self._kills)]

    # ── the run ───────────────────────────────────────────────────────────────
    def run(self) -> HardResult:
        res = HardResult(game="FurMark" if self.furmark else "CUDA", profile=self.profile.get("name", ""))
        steps = plan(self.minutes, self.phase_s)
        total = sum(s[3] for s in steps) + self.idle_s * len(steps)
        t0 = time.time()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            res.log_path = str(self.logs_dir / f"hard_{stamp}.log")
            self._log_f = open(res.log_path, "w", encoding="utf-8")
        except OSError:
            self._log_f = None
        try:
            self._tail = (self._tail_factory or __import__("core.gpu_flight", fromlist=["EventTail"]).EventTail)()
        except Exception:
            self._tail = None
        WD.own_load_started(t0)
        try:
            from core.power_state import keep_awake
            keep_awake(True)
        except Exception:
            keep_awake = None
        self._describe_start(res, steps, total)
        done_s = 0.0
        try:
            for i, (key, names, loads, secs) in enumerate(steps):
                name = tr(*names)
                if self._watch(res, None, self.idle_s, t0, done_s, total,
                               tr(f"Pause vor Phase {i + 1}", f"pause before phase {i + 1}")):
                    break
                done_s += self.idle_s
                used = [k for k in loads if k != "encode" or self._encoder_ok]
                self._log(tr(f"Phase {i + 1}/{len(steps)}: {name} ({int(secs)} s) — "
                             f"{', '.join(self._load_name(k) for k in used)}",
                             f"Phase {i + 1}/{len(steps)}: {name} ({int(secs)} s) — "
                             f"{', '.join(self._load_name(k) for k in used)}"), "header")
                self._start_loads(loads, secs)
                stopped = self._watch(res, name, secs, t0, done_s, total,
                                      f"{tr('Phase', 'Phase')} {i + 1}/{len(steps)} · {name}")
                self._delivered = self._delivered or any(ld.last for ld in self._loads)
                late = self._stop_loads()
                done_s += secs
                if late and not stopped:
                    ld, (kind, detail) = late[0]
                    stopped = self._fail(res, kind, name, ld.kind, time.time() - t0, [], detail, late=True)
                if stopped:
                    break
                self._log(tr(f"  ✓ {name}: bestanden", f"  ✓ {name}: passed"), "success")
            else:
                # the driver logs a few seconds late: a fault at the very end belongs to the test
                if not self._watch(res, None, max(self.idle_s, SETTLE_S + POLL_S), t0, done_s, total,
                                   tr("Abschluss", "finishing")):
                    res.passed = True
        finally:
            self._stop_loads()
            res.seconds = round(time.time() - t0, 1)
            if res.unstable:
                self._fault(res)
            WD.record_own_load(t0, time.time())
            if keep_awake:
                keep_awake(False)
            if self._tail is not None:
                try:
                    self._tail.close()
                except Exception:
                    pass
            self._summary(res)
            if self._log_f:
                try:
                    self._log_f.close()
                except OSError:
                    pass
                self._log_f = None
        return res

    def _describe_start(self, res: HardResult, steps: list, total: float):
        p = self.profile
        curve = p.get("curve_points") or []
        what = (tr(f"Kurve {curve[0][0]}–{curve[-1][0]} mV", f"curve {curve[0][0]}–{curve[-1][0]} mV")
                + (tr(f", flach ab {p['curve_cap_mv']} mV", f", flat from {p['curve_cap_mv']} mV")
                   if p.get("curve_cap_mv") else "")) if curve else f"+{p.get('core_offset_mhz', 0)} MHz"
        self._log(tr(f"Härtetest: {total / 60:.0f} min, {len(steps)} Phasen", f"Hardness test: {total / 60:.0f} min, "
                     f"{len(steps)} phases"), "header")
        if p:
            self._log(tr(f"Profil: „{p.get('name', '?')}“ — {what}, Speicher +{p.get('mem_offset_mhz', 0)} MHz, "
                         f"Power-Limit {p.get('power_limit_pct', 100)} %",
                         f"Profile: '{p.get('name', '?')}' — {what}, memory +{p.get('mem_offset_mhz', 0)} MHz, "
                         f"power limit {p.get('power_limit_pct', 100)} %"))
        self._log(tr(f"3D-Last: {'FurMark (OpenGL/Vulkan, leicht/schwer im Wechsel)' if self.furmark else 'CUDA (FurMark nicht gefunden)'}"
                     f" · Aufnahme: NVENC H.264 60 fps · Temperaturgrenze {self.max_temp} °C",
                     f"3D load: {'FurMark (OpenGL/Vulkan, light/heavy in turn)' if self.furmark else 'CUDA (FurMark not found)'}"
                     f" · recording: NVENC H.264 60 fps · temperature limit {self.max_temp} °C"))
        if self._tail is None:
            self._log(tr("  Ereignisprotokoll nicht lesbar — Treiber-Resets werden nur über die Lasten erkannt",
                         "  event log not readable — driver resets are only seen through the loads"), "warning")

    def _watch(self, res: HardResult, phase: Optional[str], secs: float, t0: float, done_s: float,
               total: float, label: str) -> bool:
        """Run one phase (or the idle gap: phase None) -> True when the test ends here."""
        end = time.time() + secs
        last_poll = last_line = 0.0
        while True:
            now = time.time()
            if self.stop_event.is_set():
                res.aborted, res.kind = True, "stopped"
                res.reason = tr("Abgebrochen", "Aborted")
                return True
            s = self._sample()
            if s:
                res.peak_temp = max(res.peak_temp, s["temp"])
                if phase is not None and s.get("util", 0) >= 50:
                    res.max_w = max(res.max_w, s["w"])
                    res.max_mhz = max(res.max_mhz, s["mhz"])
                    res.max_mv = max(res.max_mv, s["mv"])
                if s["temp"] >= self.max_temp:
                    res.kind, res.phase = "temp", phase or ""
                    res.reason = tr(f"Temperaturgrenze erreicht ({s['temp']} °C ≥ {self.max_temp} °C)",
                                    f"temperature limit reached ({s['temp']} °C >= {self.max_temp} °C)")
                    res.at_s = now - t0
                    return True
            if now - last_poll >= POLL_S:
                last_poll = now
                evs = self._gpu_events()
                if evs:
                    return self._fail(res, "driver", phase or tr("Pause", "pause"), "", now - t0, evs)
            for ld in self._loads:
                st = ld.check(now)
                if st is None:
                    continue
                kind, detail = st
                if kind == "noenc":
                    self._encoder_ok = False
                    res.encoder = False
                    self._log(tr(f"  Aufnahme-Last nicht möglich ({detail}) — weiter ohne Encoder",
                                 f"  recording load not possible ({detail}) — going on without the encoder"),
                              "warning")
                    self._loads.remove(ld)
                    break
                if kind == "stopped":
                    res.aborted, res.kind = True, "stopped"
                    res.reason = tr("FurMark wurde geschlossen — Test abgebrochen",
                                    "FurMark was closed — test aborted")
                    return True
                return self._fail(res, kind, phase or "", ld.kind, now - t0, [], detail)
            if s and now - last_line >= 10 and phase is not None:
                last_line = now
                enc = next((ld.vals.get("ENC") for ld in self._loads if ld.kind == "encode"), None)
                self._log(f"  {int(now - t0):>4}s  {s['temp']} °C  {s['mhz']} MHz  {s['mv']} mV  {s['w']:.0f} W  "
                          f"{s['util']} %" + (f"  enc {enc:.0f} fps" if enc is not None else ""), "dim")
            pct = (done_s + (secs - max(0.0, end - now))) / max(total, 1) * 100
            if s:
                self._prog(pct, f"{label} · {s['temp']} °C · {s['mhz']} MHz · {s['mv']} mV · {s['w']:.0f} W")
            if now >= end:
                return False
            self.stop_event.wait(min(1.0, max(0.05, end - time.time())))

    def _fail(self, res: HardResult, kind: str, phase: str, load: str, at_s: float, events: list,
              detail: str = "", late: bool = False) -> bool:
        res.kind, res.phase, res.load, res.at_s = kind, phase, load, round(at_s, 1)
        res.t_fail = time.time()
        self._stop_loads()
        self.stop_event.wait(SETTLE_S)
        res.events = list(events) + self._gpu_events()
        ln = self._load_name(load) if load else ""
        texts = {
            "compute": lambda: tr(f"Rechenfehler unter Last ({ln})", f"computation error under load ({ln})"),
            "frame": lambda: tr("Fehlerhaftes Bild im Aufnahme-Teil (CUDA-Skalierung)",
                                "corrupt frame in the recording part (CUDA scaling)"),
            "stall": lambda: tr(f"Video-Encoder steht ({detail})", f"video encoder stalled ({detail})"),
            "hang": lambda: tr(f"GPU reagiert nicht — {ln} seit {detail} s ohne Ergebnis",
                               f"GPU not responding — {ln} without a result for {detail} s"),
            "crash": lambda: tr(f"{ln} abgestürzt ({detail})", f"{ln} crashed ({detail})"),
            "driver": lambda: tr("Treiber meldet einen GPU-Fehler", "the driver reported a GPU error"),
        }
        reason = texts[kind]() if kind in texts else kind
        if late:
            reason += tr(" — beim Lastende", " — as the loads ended")
        ids = sorted({f"{src} {eid}" for _t, src, eid in res.events})
        if ids:
            reason += tr(" — Ereignisprotokoll: ", " — event log: ") + ", ".join(ids)
        res.reason = reason
        return True

    def _fault(self, res: HardResult):
        """The state just before the failure, the curve points involved, the field list."""
        t_fail = res.t_fail or time.time()
        if res.events:
            t_fail = min(t_fail, min(t for t, _s, _i in res.events))
        pt = WD.fault_point(self.samples, t_fail, self.profile) or {}
        res.point = pt
        res.anchors = WD.affected_anchors(self.profile, pt.get("mv", 0)) if pt else []
        if self.record_field and pt.get("mv"):
            fault = {"t": t_fail, "ids": sorted({i for _t, _s, i in res.events}), "gpu": self.gpu,
                     "profile": self.profile.get("name", ""), "mv": pt.get("mv", 0), "mhz": pt.get("mhz", 0),
                     "point": pt, "anchors": res.anchors, "source": "hardness", "phase": res.phase,
                     "kind": res.kind}
            WD.record_fault(self.logs_dir, fault, [s for s in self.samples if t_fail - 120 <= s["t"] <= t_fail + 10])

    def _summary(self, res: HardResult):
        mins = res.seconds / 60
        if res.passed:
            self._log(tr(f"✓ Härtetest bestanden ({mins:.0f} min) — max. {res.max_mhz:.0f} MHz, {res.max_mv:.0f} mV, "
                         f"{res.max_w:.0f} W, {res.peak_temp} °C",
                         f"✓ Hardness test passed ({mins:.0f} min) — max {res.max_mhz:.0f} MHz, {res.max_mv:.0f} mV, "
                         f"{res.max_w:.0f} W, {res.peak_temp} °C"), "success")
            return
        if res.aborted:
            self._log(tr(f"■ {res.reason} nach {mins:.1f} min — kein Ergebnis", f"■ {res.reason} after "
                         f"{mins:.1f} min — no result"), "warning")
            return
        if res.kind == "temp":
            self._log(tr(f"■ {res.reason} — Test beendet, das ist kein Stabilitätsfehler",
                         f"■ {res.reason} — test ended, that is no stability fault"), "warning")
            return
        pt = res.point
        where = (tr(f" — kurz davor {pt['mv']:.0f} mV / {pt['mhz']:.0f} MHz, {pt.get('w', 0):.0f} W, "
                    f"{pt.get('temp', 0)} °C", f" — just before {pt['mv']:.0f} mV / {pt['mhz']:.0f} MHz, "
                    f"{pt.get('w', 0):.0f} W, {pt.get('temp', 0)} °C") if pt.get("mv") else "")
        self._log(tr(f"✗ Härtetest NICHT bestanden nach {res.at_s / 60:.1f} min in „{res.phase}“: {res.reason}{where}",
                     f"✗ Hardness test FAILED after {res.at_s / 60:.1f} min in '{res.phase}': {res.reason}{where}"),
                  "error")
        if res.anchors:
            pts = ", ".join(str(a) for a in res.anchors)
            self._log(tr(f"  Betroffene Kurvenpunkte: {pts} mV — „Gezielt entschärfen“ senkt nur diese um 30 MHz",
                         f"  Curve points involved: {pts} mV — 'make safer at these points' lowers only them "
                         f"by 30 MHz"), "warning")


# ── command line: python -m core.hardness_test [minutes] [--no-furmark] ─────────────
def _main(argv: list) -> int:
    from core import app_settings
    from core.crash_recovery import CrashRecovery
    from core.nvtune_core import GpuMonitor
    nums = [float(a) for a in argv if a.replace(".", "", 1).isdigit()]
    minutes = nums[0] if nums else 20.0
    phase_s = nums[1] if len(nums) > 1 else PHASE_S
    logs = APP_DIR / "logs"
    WD.SESSIONS_FILE = logs / "gpu_sessions.json"          # the app's own-load list (same as the app)
    mon = GpuMonitor()
    profile = CrashRecovery(str(logs)).load_last_applied() or {}
    fm = None if "--no-furmark" in argv else furmark.detect()
    try:
        gpu = mon.read().name or ""
    except Exception:
        gpu = ""
    max_temp = int((app_settings.get("tuner_settings", {}) or {}).get("max_temp", 85) or 85)
    t = HardnessTest(mon.read, logs, minutes=minutes, furmark_path=fm, max_temp=max_temp, profile=profile,
                     on_log=lambda s, tag: print(s, flush=True), gpu_name=gpu, phase_s=phase_s)
    try:
        r = t.run()
    except KeyboardInterrupt:
        t.stop_event.set()
        return 130
    print("RESULT", "passed" if r.passed else ("aborted" if r.aborted else r.kind), r.log_path, flush=True)
    return 0 if r.passed else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
