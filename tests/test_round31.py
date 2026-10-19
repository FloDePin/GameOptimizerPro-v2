"""Round 31 — the precise GPU watchdog: a flight recorder of clock / voltage / power while
the app runs, GPU events seen within seconds (classic event log, read from where it was),
the state just before a fault and the curve points it involves, a targeted "make safer"
(only those points), escalation when the same points fail again, an unexpected restart
that counts only when the card was under load until the end, and the next tune keeping
extra margin where games hung. Everything on temp folders; the real event log only read."""
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


TMP = tempfile.mkdtemp(prefix="gop_r31_")
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None
I18N._current_lang = "de"
from core import curve_tune as CT, gpu_flight as GF, gpu_watchdog as W  # noqa: E402
from core.nvtune_core import ProfileManager, TuneProfile  # noqa: E402

LOGS = os.path.join(TMP, "logs")
os.makedirs(LOGS)
CURVE = [[925, 2560], [950, 2620], [975, 2680], [1000, 2740], [1025, 2800], [1050, 2880], [1075, 2880]]
PROF = {"name": "Rundum Test", "curve_points": CURVE, "curve_cap_mv": 1050, "mem_offset_mhz": 500}

# ── 1) the classic event log: records parsed, the real log read ──────────────
print("event log")


def rec(recno, t, source, eid):
    strings = (source + "\0" + "PC\0").encode("utf-16-le")
    body = strings + b"\0" * ((4 - len(strings) % 4) % 4)
    length = 56 + len(body) + 4
    head = struct.pack("<IIIIIIHHHHIIIIII", length, 0x654C664C, recno, int(t), int(t), eid | 0xC0000000,
                       1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    return head + body + struct.pack("<I", length)


buf = rec(7, 1760000000, "nvlddmkm", 153) + rec(8, 1760000010, "Display", 4101)
check(GF.parse_records(buf) == [(7, 1760000000.0, "nvlddmkm", 153), (8, 1760000010.0, "Display", 4101)],
      "EVENTLOGRECORDs: record number, time, source, event id (the high bits dropped)")
check(GF.parse_records(buf[:70]) == [], "a cut record is not read")
if os.name == "nt":
    tail = GF.EventTail("System")
    start = tail.next
    check(tail.poll() == [] or tail.next >= start, "a new tail starts at the end of the log")
    oldest, newest = tail._range()
    tail.next = max(oldest, newest - 40)
    got = tail.poll()
    check(got and all(isinstance(s, str) and t > 1.5e9 for t, s, _i in got) and tail.next == newest + 1,
          f"the last records read back ({len(got)}), the tail at the end again")
    tail.next = oldest
    nv = [(t, i) for t, s, i in tail.poll() if s == "nvlddmkm" and i == 153]
    tail.close()
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "@(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='nvlddmkm'; Id=153} "
                        "-EA SilentlyContinue).Count"], capture_output=True, text=True, timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    ps_n = int((r.stdout or "0").strip() or 0)
    check(len(nv) == ps_n, f"the same nvlddmkm 153 events as Get-WinEvent ({len(nv)} / {ps_n})")

# ── 2) the state before a fault, the points it involves ──────────────────────
print("fault point")
T0 = 1_760_000_000.0
idle = [{"t": T0 + i, "mhz": 210, "mem": 405, "mv": 0, "w": 25, "temp": 40, "util": 2} for i in range(30)]
load = [{"t": T0 + 30 + i, "mhz": 2880 if i % 3 else 2800, "mem": 11500, "mv": 1050 if i % 3 else 1025,
         "w": 290, "temp": 66, "util": 98} for i in range(40)]
fp = W.fault_point(idle + load, T0 + 66, PROF)
check(fp and fp["mv"] == 1050 and fp["mhz"] == 2880 and fp["w"] == 290,
      f"the loaded sample with the highest voltage just before ({fp})")
check(W.fault_point(idle, T0 + 20, PROF) is None, "the card was idle: no point (nothing to blame on the curve)")
check(W.fault_point(load, T0 + 500, PROF) is None, "nothing recorded at that time: no point")
nomv = [dict(s, mv=0) for s in load]
check(W.fault_point(nomv, T0 + 66, PROF)["mv"] == 1050,
      "no voltage reading (Afterburner off): the voltage from the curve at that clock")
check(W.affected_anchors(PROF, 1050) == [1025, 1050, 1075], "in the flat part: the cap point, its neighbour, above")
check(W.affected_anchors(PROF, 980) == [975, 1000], "between points: the two around it")
check(W.affected_anchors({"curve_points": [], "core_offset_mhz": 120}, 1050) == [], "offset profile: none")

# ── 3) targeted "make safer" ──────────────────────────────────────────────────
print("targeted make-safer")
pm = ProfileManager(os.path.join(TMP, "profiles"))
pm.save(TuneProfile.from_dict(dict(PROF, core_offset_mhz=0)))
p = pm.derate_points("Rundum Test", [1050, 1075])
check(p and p.name == "Rundum Test_sicher" and p.mem_offset_mhz == 500
      and dict(map(tuple, p.curve_points)) == {925: 2560, 950: 2620, 975: 2680, 1000: 2740, 1025: 2800,
                                               1050: 2850, 1075: 2850},
      f"only 1050 / 1075 −30 MHz, memory kept ({p.curve_points if p else None})")
p2 = pm.derate_points("Rundum Test", [1075])
check(dict(map(tuple, p2.curve_points))[1075] == 2850 and dict(map(tuple, p2.curve_points))[1050] == 2850
      and p2.name == "Rundum Test_sicher2", "a lower point is never faster than the one above (monotonic)")
check(pm.derate_points("Rundum Test", [800]) is None and pm.derate_points("nope", [1050]) is None,
      "points not on the curve / unknown profile: None (the caller falls back to the whole profile)")
check("Gezielt entschärft" in p.notes and "1050, 1075 mV" in p.notes, "the note says what was lowered")

# ── 4) field faults: stored, found again, escalation ─────────────────────────
print("field faults")
fault = {"t": T0 + 66, "gpu": "GPU X", "profile": "Rundum Test", "mv": 1050, "mhz": 2880, "ids": [153],
         "anchors": [1025, 1050, 1075], "point": fp}
W.record_fault(LOGS, fault, load)
check(W.field_voltages(LOGS, "GPU X") == [1050] and W.field_voltages(LOGS, "Other GPU") == [],
      "the fault voltage per GPU (the next tune reads it)")
saved = list(Path(LOGS, W.FAULTS_DIR).glob("fault_*.json"))
check(len(saved) == 1 and len(json.loads(saved[0].read_text())["samples"]) == 40, "the recording around it is kept")
check(W.fault_near(LOGS, T0, T0 + 100)["mv"] == 1050 and W.fault_near(LOGS, T0 + 200, T0 + 300) is None,
      "found again by its time")
check(not W.repeated(LOGS, "Rundum Test_sicher", [1050], T0)
      and W.repeated(LOGS, "Rundum Test_sicher", [1050], T0 + 500)
      and not W.repeated(LOGS, "Anderes", [1050], T0 + 500),
      "the same points of the same profile family failed before -> escalate")

# ── 5) the start check: point, anchors, escalation, unexpected restart ───────
print("start check")


class CR:
    def __init__(self, d, applied):
        self._last_applied = Path(TMP) / "last_applied.json"
        self._last_applied.write_text(json.dumps(d))
        os.utime(self._last_applied, (applied, applied))

    def load_last_applied(self):
        return json.loads(self._last_applied.read_text())


cr = CR(PROF, T0 - 3600)
found = W.check(cr, LOGS, 0, lambda since: [(T0 + 66, 153), (T0 + 76, 153)])
check(found and found["point"]["mv"] == 1050 and found["anchors"] == [1025, 1050, 1075] and not found["escalate"],
      "a game event with a live recording: point + curve points, no escalation yet")
txt = W.describe(found, True)
check("1050 mV / 2880 MHz" in txt and "Gezielt entschärfen" in txt and "1025, 1050, 1075 mV" in txt,
      "the dialog text names the state and the points")
W.record_fault(LOGS, dict(fault, t=T0 + 4000, profile="Rundum Test_sicher"), load)
cr2 = CR(dict(PROF, name="Rundum Test_sicher2"), T0 + 7000)
found2 = W.check(cr2, LOGS, 0, lambda since: [(T0 + 9000, 153)])
check(found2 is not None and "point" not in found2, "no recording for this event: the old way (whole profile)")
W.record_fault(LOGS, dict(fault, t=T0 + 9001, profile="Rundum Test_sicher2"), load)
found3 = W.check(cr2, LOGS, 0, lambda since: [(T0 + 9000, 153)])
check(found3["escalate"] and "ganze Profil" in W.describe(found3, True),
      "the same points failed again after the targeted fix: the whole profile this time")
I18N._current_lang = "en"
check("Make safer at these points" in W.describe(found, False) and "1050 mV / 2880 MHz" in W.describe(found, False),
      "English text")
I18N._current_lang = "de"
# unexpected restart: counts only with load until the recording ended
LOGS2 = os.path.join(TMP, "logs2")
os.makedirs(LOGS2)
W.save_flight(LOGS2, "GPU X", load)
W.keep_previous_flight(LOGS2)
check(Path(LOGS2, W.FLIGHT_PREV).exists() and not Path(LOGS2, W.FLIGHT_FILE).exists(),
      "at start the last session's recording moves aside")
W.save_flight(LOGS2, "GPU X", idle)                         # the new session already writes
boot = T0 + 69 + 90
cr3 = CR(PROF, T0 - 3600)
f4 = W.check(cr3, LOGS2, 0, lambda since: [(boot, 41)])
check(f4 and f4["events"] == [(load[-1]["t"], 41)] and f4["point"]["mv"] == 1050,
      "restart after a recording that ends under load: a GPU crash at the recording's end")
check("unerwarteter Neustart" in W.describe(f4, True), "named in the dialog")
W.save_flight(LOGS2, "GPU X", idle)
os.replace(Path(LOGS2, W.FLIGHT_FILE), Path(LOGS2, W.FLIGHT_PREV))
check(W.check(cr3, LOGS2, 0, lambda since: [(T0 + 200, 41)]) is None,
      "restart while the card was idle (power cut, reset button): not a GPU fault")

# ── 6) the live watch ────────────────────────────────────────────────────────
print("live watch")
CLOCK = [T0]
STATS = {"v": None}


class FakeTail:
    def __init__(self): self.q = []
    def poll(self): out, self.q = self.q, []; return out
    def close(self): pass


tail = FakeTail()
BUSY = [False]
GOT = []
LW = GF.LiveWatch(lambda: STATS["v"], LOGS, is_busy=lambda: BUSY[0], on_fault=GOT.append,
                  profile_fn=lambda: PROF, gpu_name="GPU X", tail_factory=lambda: tail, clock=lambda: CLOCK[0])


def run(seconds, mhz=2880, mv=1050, w=290, util=98):
    for _ in range(int(seconds)):
        STATS["v"] = types.SimpleNamespace(core_mhz=mhz, mem_mhz=11500, voltage_mv=mv, gpu_power_w=w, power_w=w,
                                           temp=66, gpu_usage=util)
        LW.sample()
        LW.check_events()
        CLOCK[0] += 1


run(20, 210, 0, 25, 2)
run(30)
tail.q = [(CLOCK[0] - 1, "nvlddmkm", 153), (CLOCK[0], "Application Error", 1000), (CLOCK[0], "Display", 4101)]
run(1)
check(GOT == [], "not before the samples after the event are in (settle)")
run(4)
check(len(GOT) == 1 and GOT[0]["mv"] == 1050 and GOT[0]["ids"] == [153, 4101]
      and GOT[0]["anchors"] == [1025, 1050, 1075] and GOT[0]["profile"] == "Rundum Test",
      "a GPU fault: point, ids (other sources ignored), the curve points")
tail.q = [(CLOCK[0], "nvlddmkm", 153)]
run(5)
check(len(GOT) == 1, "the same fault again 10 s later: grouped (153 often comes twice)")
CLOCK[0] += 300
BUSY[0] = True
tail.q = [(CLOCK[0], "nvlddmkm", 153)]
run(5)
check(len(GOT) == 1, "during an own load (tune / stress / Afterburner restart): ignored")
BUSY[0] = False
tune_log = Path(LOGS, time.strftime("tune_%Y%m%d_%H%M%S.log", time.localtime(CLOCK[0] - 100)))
tune_log.write_text("x")
os.utime(tune_log, (CLOCK[0] + 2, CLOCK[0] + 2))
tail.q = [(CLOCK[0], "nvlddmkm", 153)]
run(5)
check(len(GOT) == 1, "inside a tune log's window: ignored")
tune_log.unlink()
CLOCK[0] += 300
tail.q = [(CLOCK[0], "nvlddmkm", 13)]
run(5)
check(len(GOT) == 2 and GOT[1]["ids"] == [13], "a later fault is a new one")
LW.flush()
on_disk = W.load_flight(LOGS)
check(on_disk["gpu"] == "GPU X" and on_disk["samples"]
      and min(s["t"] for s in on_disk["samples"]) >= CLOCK[0] - LW.FILE_KEEP_S - 1,
      "the recording on disk: the last minute")
check(LW.loaded_recently(), "loaded: written every few seconds")
run(70, 210, 0, 25, 2)
check(not LW.loaded_recently(), "idle for a minute: written only once a minute")
# the real thread with the real event log: starts, records, stops
if os.name == "nt":
    LOGS3 = os.path.join(TMP, "logs3")
    os.makedirs(LOGS3)
    live = GF.LiveWatch(lambda: types.SimpleNamespace(core_mhz=1500, mem_mhz=405, voltage_mv=800, gpu_power_w=40,
                                                      power_w=40, temp=40, gpu_usage=5),
                        LOGS3, is_busy=lambda: False, on_fault=GOT.append, interval=0.1, poll_s=0.2, flush_s=0.3)
    live.start()
    time.sleep(1.2)
    live.stop()
    time.sleep(0.3)
    check(len(live.snapshot()) >= 5 and W.load_flight(LOGS3).get("samples") and live._tail is not None,
          f"the thread records ({len(live.snapshot())} samples), reads the real log, writes the file")

# ── 7) the next tune: extra margin where games hung ──────────────────────────
print("tuner margins")
rs = [CT.AnchorResult(mv, 2800, best_mhz=2950) for mv in (1075, 1050, 1000, 950)]
rs[0].tdr = True
CT.apply_margins(rs, 45, 60, 30, field_mv=[1050])
m = {r.mv: r.margin_mhz for r in rs}
check(m == {1075: 90, 1050: 90, 1000: 60, 950: 45},
      f"+30 at the point near the game hang, not stacked with a reset (1075: tdr) ({m})")
src = open(os.path.join(ROOT, "core", "nvtune_tuner.py"), encoding="utf-8").read()
check("WD.field_voltages(self._log_dir, gpu_key)" in src and "field_mv=field_mv" in src,
      "the curve tune passes the recorded fault voltages of this GPU")

# ── 8) the app: busy, toast, dialog with the targeted option ─────────────────
print("app")
import GameOptimizerPro as G  # noqa: E402
import ui.components as UC  # noqa: E402

fake = object.__new__(G.GameOptimizerApp)
fake.tuner = types.SimpleNamespace(is_running=False)
fake.monitor = types.SimpleNamespace(mahm=types.SimpleNamespace(restarting=False))
check(not fake._gpu_busy(), "nothing running: not busy")
fake.monitor.mahm.restarting = True
check(fake._gpu_busy(), "Afterburner restarting for a profile: busy")
fake.monitor.mahm.restarting = False
W.own_load_started(time.time())
check(fake._gpu_busy(), "a stress test running (started, not ended yet): busy")
W._ACTIVE.clear()
TOASTS = []
GF.toast = lambda title, msg: TOASTS.append((title, msg))
fake._on_live_fault(GOT[0])
check(fake._watchdog_pending and TOASTS and "1050 mV / 2880 MHz" in TOASTS[0][1],
      "a live fault: a notification (no window over the game), the dialog waits")


class FakeWin:
    def __init__(self): self.q = []
    def after(self, ms, fn): self.q.append(fn)
    def pump(self, limit=5.0):
        end = time.time() + limit
        while self.q and time.time() < end:
            self.q.pop(0)()
            time.sleep(0.01)


class AppAB:
    def __init__(self): self.writes = []
    def write_and_apply(self, slot, p, startup="same"):
        self.writes.append((slot, p)); return True, ""


class AppCR:
    def __init__(self): self.saved = []
    def save_last_applied(self, d): self.saved.append(d["name"])


G.messagebox = types.SimpleNamespace(showinfo=lambda *a, **k: None, showerror=lambda *a, **k: None)
SEEN = {}


def dialog(choice, f):
    app = object.__new__(G.GameOptimizerApp)
    app._window, app.pm, app.ab, app.cr = FakeWin(), pm, AppAB(), AppCR()
    app.monitor = types.SimpleNamespace(power_pct_to_watts=lambda p: 320.0, set_power_limit=lambda w: True)

    def cd(*a, **k):
        SEEN["opts"], SEEN["current"] = a[3], k.get("current")
        return types.SimpleNamespace(show=lambda: choice)
    UC.ChoiceDialog = cd
    app._watchdog_dialog(f)
    app._window.pump()
    return app


a = dialog("point", found)
check(SEEN["current"] == "point" and [o[0] for o in SEEN["opts"]] == ["point", "safer", "stock", "keep"]
      and "1025, 1050, 1075 mV" in SEEN["opts"][0][1], "targeted first and recommended")
wp = a.ab.writes[0][1] if a.ab.writes else None
check(wp and dict(map(tuple, wp.curve_points))[975] == 2680 and dict(map(tuple, wp.curve_points))[1050] == 2850
      and wp.mem_offset_mhz == 500 and a.cr.saved == [wp.name],
      "'targeted': only those points lower, memory kept, applied to slot 2 and recorded")
a = dialog("safer", found3)
check(SEEN["current"] == "safer" and "point" not in [o[0] for o in SEEN["opts"]],
      "escalation: no targeted option, the whole profile recommended")
w2 = a.ab.writes[0][1]
check(dict(map(tuple, w2.curve_points))[925] == CURVE[0][1] - 30 and w2.mem_offset_mhz == 300,
      "whole profile: every point −30, memory −200")
app_src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check("self._live_watch_start()" in app_src and "live.stop()" in app_src
      and app_src.index("live.stop()") < app_src.index("self.monitor.close()"),
      "started with the window; stopped before NVML closes")
stress_src = open(os.path.join(ROOT, "ui", "tab_stress.py"), encoding="utf-8").read()
check(stress_src.count("gpu_watchdog.own_load_started(") == 2, "stress test + FurMark/3DMark runs say they started")
rat = open(os.path.join(ROOT, "tests", "run_all_tests.py"), encoding="utf-8").read()
check('"OMP_NUM_THREADS"' in rat and "IDLE_PRIORITY_CLASS" in rat,
      "the battery: one numpy thread, lowest priority (it often runs next to a game)")

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
