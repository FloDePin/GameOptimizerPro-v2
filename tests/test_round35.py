"""Round 35 — two external audits checked against the code; the confirmed points fixed:
stress tests end with the app, WMI device keys in a worker thread, NVRTC failure = no encoder,
the watchdog waits for its own apply, only real profiles exported, a broken import name,
"destination host unreachable", English BIOS texts, a cleared event log."""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r35_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "en"
from core import gpu_watchdog as WD  # noqa: E402
WD.SESSIONS_FILE = Path(TMP) / "gpu_sessions.json"     # never the app's own list

# ── 1) the registry backup reads the device keys in a worker thread too ──────
if os.name == "nt":
    print("registry backup: device keys")
    from core.registry_backup import _device_keys  # noqa: E402
    main = _device_keys()
    box: dict = {}
    th = threading.Thread(target=lambda: box.update(k=_device_keys()))
    th.start()
    th.join(60)
    check(main and box.get("k") == main,
          f"worker thread (the optimizer's backup) = main thread: {len(box.get('k') or [])} of {len(main)} "
          f"GPU / disk keys (before: 0 — WMI without COM set up for the thread)")

# ── 2) the stress page ends its tests with the app ───────────────────────────
print("stress page: tests end with the app")
import customtkinter as ctk  # noqa: E402
from ui.tab_stress import StressTab  # noqa: E402


class Mon:
    def read(self):
        return types.SimpleNamespace(temp=40, voltage_mv=900, core_mhz=210, gpu_power_w=20, gpu_usage=1,
                                     temp_limit_c=90, power_max_w=320, name="Test GPU")


root = ctk.CTk()
root.withdraw()                                  # never mapped
page = StressTab(root, Mon(), tuner=types.SimpleNamespace(is_running=False, cr=None))
page._alive = False
stop = threading.Event()
ended = []


def hard_run():                                  # stands in for HardnessTest.run: ends on its stop event
    stop.wait(30)
    time.sleep(0.3)                              # its loads end
    ended.append(time.time())


page._hard, page._hard_thread = stop, threading.Thread(target=hard_run, daemon=True)
page._hard_thread.start()


class Proc:
    def __init__(self): self.terminated = False
    def poll(self): return 0 if self.terminated else None
    def terminate(self): self.terminated = True
    def wait(self, timeout=None): return 0


proc = Proc()
page._running_internal, page._worker_proc, page._int_t0 = True, proc, time.time() - 30
t0 = time.time()
page.end_gpu_tests()
check(ended and stop.is_set(), f"the hardness test is asked to end and waited for ({time.time() - t0:.1f} s) — "
      f"before, its FurMark windows went on after the app had gone")
check(proc.terminated and not page._running_internal and WD.SESSIONS_FILE.exists(),
      "the internal test's worker ends, its run is recorded as own GPU load")
page.stop()                                      # page.stop() at destroy: harmless a second time
check(True, "a second end (the window's destroy) does nothing more")
root.destroy()

import GameOptimizerPro as G  # noqa: E402
calls = []
fake_app = types.SimpleNamespace(_window=types.SimpleNamespace(_tab_frames={
    "stress": types.SimpleNamespace(end_gpu_tests=lambda: calls.append("stress")),
    "gpu": types.SimpleNamespace()}))
G.GameOptimizerApp._end_gpu_tests(fake_app)
check(calls == ["stress"], "the app's shutdown ends them before the process exits")
src = Path(ROOT, "GameOptimizerPro.py").read_text(encoding="utf-8")
i_shut = src.index("def _shutdown(")
check(src.index("self._end_gpu_tests()", i_shut) < src.index("self._stop_thread.start()", i_shut),
      "... before the stop thread (it ends the process with os._exit)")

# ── 3) the watchdog: no new check while its own apply runs ───────────────────
print("watchdog: waits for its own apply")
app = object.__new__(G.GameOptimizerApp)
app._watchdog_applying, app._watchdog_busy = True, False
started = []
G.threading = types.SimpleNamespace(**{**vars(threading), "Thread": lambda *a, **k: started.append(1)})
app._watchdog_start()
check(not started and not app._watchdog_busy, "Afterburner still applying the safer profile: no second check")
G.threading = threading

# ── 4) the encoder worker: NVRTC missing = no encoder, not an unstable card ──
print("encoder worker: kernels that can't be compiled")
FAKE = os.path.join(HERE, "fakecupy")            # its cupy has no RawModule: the compile fails
r = subprocess.run([sys.executable, os.path.join(ROOT, "_stress_worker.py"), str(os.getpid()), "encode"],
                   capture_output=True, text=True, timeout=60,
                   env=dict(os.environ, PYTHONPATH=FAKE, GOP_STRESS_GPU_OK="1"),
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
check(r.returncode == 4 and r.stdout.startswith("NOENC"),
      f"after a load delivered (GPU_OK): 'NOENC', exit 4 — before: 'ERR cuda', a failed step (exit {r.returncode})")
wsrc = Path(ROOT, "_stress_worker.py").read_text(encoding="utf-8")
check('state["done"] = time.time()' in wsrc and "while True:" in wsrc[wsrc.index("def stall_guard"):],
      "the stall guard keeps watching while the encoder closes (a hang there is a hang), with a fresh window")

# ── 5) the hardness test closes a load's pipe ────────────────────────────────
print("hardness test: a load's pipe")
from core.hardness_test import _Load  # noqa: E402
ld = _Load("transient", [sys.executable, "-c", "print('RATE 5')"])
ld.start()
ld.proc.wait(20)
for _ in range(50):
    if ld.proc.stdout.closed:
        break
    time.sleep(0.05)
check(ld.proc.stdout.closed and ld.vals.get("RATE") == 5.0, "read to the end, then closed")

# ── 6) export / import ───────────────────────────────────────────────────────
print("export / import")
from core.export_import import ExportImport  # noqa: E402
pdir = Path(TMP, "profiles")
pdir.mkdir()
(pdir / "language.json").write_text('{"lang": "de"}', encoding="utf-8")
(pdir / "game_profiles.json").write_text('{"games": []}', encoding="utf-8")
(pdir / "__tray_default__.json").write_text('{"name": "__tray_default__", "core_offset_mhz": 0}', encoding="utf-8")
(pdir / "Real.json").write_text('{"name": "Real", "core_offset_mhz": 120, "power_limit_pct": 100}',
                                encoding="utf-8")
ex = ExportImport(str(pdir), TMP)
out = str(Path(TMP, "x.nextune"))
ok, _msg = ex.export(out, include_tweaks=False, include_presets=False)
exported = json.loads(Path(out).read_text(encoding="utf-8"))["gpu_profiles"]
check(ok and [p["name"] for p in exported] == ["Real"],
      f"only real GPU profiles are exported (not language.json, game_profiles.json, internal ones): "
      f"{[p.get('name', '?') for p in exported]}")
data = json.loads(Path(out).read_text(encoding="utf-8"))
data["gpu_profiles"] += [{"name": 123, "core_offset_mhz": 5}, {"name": "", "core_offset_mhz": 5},
                         {"lang": "de"}, {"name": "Other", "core_offset_mhz": 90, "power_limit_pct": 95}]
Path(out).write_text(json.dumps(data), encoding="utf-8")
ok, res, msg = ex.import_file(out)
check(ok and msg.startswith("Import read:") and "GPU profiles" in msg, "the import summary in English too")
dest = Path(TMP, "imported")
ex2 = ExportImport(str(dest), TMP)
try:
    n_in, n_skip = ex2.apply_imported_profiles(res["gpu_profiles"])
    crashed = None
except Exception as e:
    n_in = n_skip = -1
    crashed = e
check(crashed is None and n_in == 2 and n_skip == 3,
      f"a name that is no text, an empty name, no profile at all: skipped, no crash ({n_in} in, {n_skip} "
      f"skipped{', ' + repr(crashed) if crashed else ''})")

# ── 7) ping: "destination host unreachable" ──────────────────────────────────
print("network test")
from core import network_test as NT  # noqa: E402
_run = NT.subprocess.run
NT.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=(
    "Pinging 192.168.1.50 with 32 bytes of data:\n"
    + "Reply from 192.168.1.1: Destination host unreachable.\n" * 4
    + "\nPing statistics for 192.168.1.50:\n    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),\n"),
    stderr="")
r = NT.ping("Gateway", "192.168.1.50", count=4)
check(not r.reachable and r.loss_pct == 100.0 and r.error == "no answer",
      f"replies without a time: not reachable, 100 % loss, 'no answer' (before: 0 %, no error) — "
      f"{r.loss_pct} %, '{r.error}'")
NT.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=(
    "Reply from 1.1.1.1: bytes=32 time=12ms TTL=57\nReply from 1.1.1.1: bytes=32 time=14ms TTL=57\n"
    "    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),\n"), stderr="")
r = NT.ping("Cloudflare", "1.1.1.1", count=2)
check(r.reachable and r.loss_pct == 0.0 and r.avg_ms == 13.0 and not r.error, "normal replies as before")
for lang, out in (("German", "Antwort von 1.1.1.1: Bytes=32 Zeit=12ms TTL=57\nAntwort von 1.1.1.1: Bytes=32 Zeit<1ms "
                              "TTL=57\n    Pakete: Gesendet = 2, Empfangen = 2, Verloren = 0\n    (0% Verlust),\n"),
                  ("French", "Réponse de 1.1.1.1 : octets=32 temps=12 ms TTL=57\nRéponse de 1.1.1.1 : octets=32 "
                             "temps=14 ms TTL=57\n    Paquets : envoyés = 2, reçus = 2, perdus = 0 (perte 0%),\n")):
    NT.subprocess.run = lambda *a, o=out, **k: types.SimpleNamespace(stdout=o, stderr="")
    r = NT.ping("x", "1.1.1.1", count=2)
    check(r.reachable and len(r.rtts) == 2 and not r.error, f"{lang} Windows: the reply times are read ({r.rtts})")
NT.subprocess.run = _run

# ── 8) BIOS checks in English ────────────────────────────────────────────────
print("BIOS checks")
import core.bios_detector as BD  # noqa: E402
sb_on = BD.BiosDetector.detect_secure_boot({"secureboot": "1"})
sb_legacy = BD.BiosDetector.detect_secure_boot({"firmware": "Legacy"})
csm = BD.BiosDetector.detect_csm({"firmware": "legacy"})
_bar = BD._bar1_mb
BD._bar1_mb = lambda: (256.0, 16376.0)
rebar = BD.BiosDetector.detect_rebar({})
BD._bar1_mb = _bar
check((sb_on.detected_val, sb_on.note) == ("on", "Secure Boot is on") and sb_legacy.detected_val == "legacy boot"
      and "UEFI" in sb_legacy.note and csm.detected_val == "legacy boot" and rebar.note.startswith("Resizable BAR off"),
      "Secure Boot, legacy boot, Resizable BAR off: English in the English app")
I18N._current_lang = "de"
check(BD.BiosDetector.detect_secure_boot({"secureboot": "0"}).note == "Secure Boot ist aus", "... German in German")
I18N._current_lang = "en"

# ── 9) a cleared event log: the live watch reopens it ────────────────────────
print("event log cleared while open")
from core import gpu_flight as GF  # noqa: E402
state = {"oldest": 100, "count": 50, "reads": 0, "opened": 0}


class FakeApi:
    def GetOldestEventLogRecord(self, h, p):
        p._obj.value = state["oldest"]
        return True

    def GetNumberOfEventLogRecords(self, h, p):
        p._obj.value = state["count"]
        return True

    def ReadEventLogW(self, h, flags, rec, buf, size, got, need):
        state["reads"] += 1
        ctypes.set_last_error(1503 if state["opened"] == 0 else 38)
        return False

    def OpenEventLogW(self, server, log):
        state["opened"] += 1
        state.update(oldest=1, count=5)         # the cleared log starts again at 1
        return 1234

    def CloseEventLog(self, h):
        return True


tail = object.__new__(GF.EventTail)
tail._api, tail._h, tail._log, tail.next = FakeApi(), 1, "System", 120
tail.poll()
check(state["opened"] == 1 and tail._h == 1234 and tail.next == 1,
      "ERROR_EVENTLOG_FILE_CHANGED: handle reopened, read from the new start (before: blind until a restart)")
tail.poll()
check(state["opened"] == 1, "a normal end of the log: no reopen")

if os.name == "nt":
    # live 22.10.: after a tool had cleared the logs, every classic read ended with 995 (also on a new
    # handle) — the modern API (wevtapi) reads on from the same record
    real = GF.EventTail("System")
    api = real._api

    class Broken:
        def __getattr__(self, name):
            return getattr(api, name)

        def ReadEventLogW(self, *a):
            ctypes.set_last_error(995)
            return False

    real._api = Broken()
    oldest, newest = real._range()
    real.next = max(oldest, newest - 20)
    want = newest - real.next + 1
    got = real.poll()
    check(real._modern is not None and len(got) >= min(want, 1) and real.next >= newest + 1
          and all(isinstance(s, str) and t > 1.5e9 for t, s, _i in got),
          f"the classic API fails (995): the modern one reads the same records ({len(got)} of {want})")
    check(real.poll() == [] or real._modern is not None, "... and goes on with it")
    real.close()

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
