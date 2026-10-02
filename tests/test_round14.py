"""Round 14 — clean-up (games page, CPU pinning, FPS capture removed; tune history
in the GPU tuner), the BIOS guide for every platform, honest BIOS detection, updates
from GitHub (download, install with backup / rollback), close-to-tray setting.
Nothing is downloaded or installed for real: the network is a fake and the
installer works on temporary folders. One read-only PowerShell call reads this
PC's RAM / Secure Boot state."""
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import zipfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)


import core.i18n as I18N
I18N._current_lang = "de"                  # in memory only
TMP = tempfile.mkdtemp(prefix="gop_r14_")
from core import app_settings
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the user's file

# ── A: BIOS guide ─────────────────────────────────────────────────────────────
print("A  BIOS guide: every platform, the detection only pre-selects")
from core import bios_guide as BG
CPUS = {
    "AMD Ryzen 7 9800X3D 8-Core Processor": "am5_zen5_x3d", "AMD Ryzen 9 9950X3D 16-Core Processor": "am5_zen5_x3d",
    "AMD Ryzen 9 9950X 16-Core Processor": "am5_zen5", "AMD Ryzen 5 9600X 6-Core Processor": "am5_zen5",
    "AMD Ryzen 7 7800X3D 8-Core Processor": "am5_zen4_x3d", "AMD Ryzen 5 7600 6-Core Processor": "am5_zen4",
    "AMD Ryzen 7 8700G w/ Radeon 780M Graphics": "am5_apu", "AMD Ryzen 5 8400F 6-Core Processor": "am5_apu",
    "AMD Ryzen 7 5800X3D 8-Core Processor": "am4_zen3_x3d", "AMD Ryzen 5 5600X 6-Core Processor": "am4_zen3",
    "AMD Ryzen 7 5700G with Radeon Graphics": "am4_apu", "AMD Ryzen 5 PRO 4650G with Radeon Graphics": "am4_apu",
    "AMD Ryzen 5 3600 6-Core Processor": "am4_zen2", "AMD Ryzen 7 2700X Eight-Core Processor": "am4_zen1",
    "AMD Ryzen 5 2400G with Radeon Vega Graphics": "am4_apu",
    "Intel(R) Core(TM) Ultra 9 285K": "lga1851_arl", "13th Gen Intel(R) Core(TM) i9-13900K": "lga1700_rpl",
    "Intel(R) Core(TM) i7-14700KF": "lga1700_rpl", "12th Gen Intel(R) Core(TM) i5-12400F": "lga1700_adl",
    "Intel(R) Core(TM) i9-10900K CPU @ 3.70GHz": "lga1200", "11th Gen Intel(R) Core(TM) i7-11700K @ 3.60GHz": "lga1200",
    "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz": "lga1151", "Intel(R) Core(TM) i9-9900K CPU @ 3.60GHz": "lga1151",
    # laptops, workstation, unknown -> the basics
    "AMD Ryzen 7 7840HS w/ Radeon 780M Graphics": "generic", "AMD Ryzen 9 7945HX": "generic",
    "Intel(R) Core(TM) Ultra 7 155H": "generic", "12th Gen Intel(R) Core(TM) i7-12700H": "generic",
    "Intel(R) Core(TM) i7-1165G7 @ 2.80GHz": "generic",
    "AMD Ryzen Threadripper 3970X 32-Core Processor": "generic", "": "generic",
}
bad = {c: (BG.detect_profile(c), e) for c, e in CPUS.items() if BG.detect_profile(c) != e}
check(not bad, f"{len(CPUS)} CPU names -> the right platform{'' if not bad else ': ' + str(bad)}")
ids = [p.id for p in BG.PROFILES]
check(len(ids) == 16 and len(set(ids)) == 16, f"16 platforms, unique ids: {ids}")
check({BG.detect_profile(c) for c in CPUS} == set(ids), "every platform is reachable by detection")
lst = BG.match_profiles("AMD Ryzen 7 7800X3D 8-Core Processor")
check(len(lst) == 16 and lst[0].id == "am5_zen4_x3d", "match_profiles: all platforms, the detected one first")
problems = []
for p in BG.PROFILES:
    keys = [s.key for s in p.settings]
    if len(keys) != len(set(keys)):
        problems.append(f"{p.id}: duplicate {keys}")
    if "memory_profile" not in keys or "bios_update" not in keys or "csm" not in keys or "secure_boot" not in keys:
        problems.append(f"{p.id}: basics missing")
    for s in p.settings:
        if s.risk not in (BG.SAFE, BG.MODERATE, BG.ADVANCED) or s.impact not in ("low", "medium", "high") \
                or s.category not in ("Memory", "CPU", "GPU", "Power", "Boot") or not s.path or not s.explanation:
            problems.append(f"{p.id}/{s.key}: bad fields")
        if s.detect_key not in (None, "expo_xmp", "rebar", "secure_boot", "csm"):
            problems.append(f"{p.id}/{s.key}: detect key {s.detect_key}")
        if set(s.paths) - {"asus", "msi", "gigabyte", "asrock"}:
            problems.append(f"{p.id}/{s.key}: unknown vendor in paths")
check(not problems, f"every profile complete and consistent {problems[:3]}")
no_rebar = {p.id for p in BG.PROFILES if not any(s.key == "rebar" for s in p.settings)}
check(no_rebar == {"am4_zen1", "lga1151"}, f"Resizable BAR everywhere it exists (not Ryzen 1000/2000, Intel 8/9): {no_rebar}")
check(sum(len(p.settings) for p in BG.PROFILES) >= 150, "plenty of settings")
rpl = BG.get_profile("lga1700_rpl")
check(rpl.settings[0].key == "bios_update" and "0x12F" in rpl.settings[0].explanation and rpl.settings[0].impact == "high",
      "Raptor Lake: the microcode update comes first")
x3d = BG.get_profile("am5_zen4_x3d")
pbo = next(s for s in x3d.settings if s.key == "pbo")
check("Curve Optimizer" in pbo.recommended, "7000X3D: PBO only through the Curve Optimizer (locked clocks)")
cst = next(s for s in BG.get_profile("am5_zen5").settings if s.key == "cstates")
check("Auto" in cst.recommended and "Enabled" in cst.recommended,
      "C-states stay on (the old 'Gaming: Disabled' advice is gone)")
check([BG.vendor_of(m) for m in ("ASUSTeK COMPUTER INC.", "Micro-Star International Co., Ltd.",
                                 "Gigabyte Technology Co., Ltd.", "ASRock", "Dell Inc.", "")]
      == ["asus", "msi", "gigabyte", "asrock", "other", "other"], "board maker from the WMI manufacturer")
rb = next(s for s in x3d.settings if s.key == "rebar")
check(rb.path_for("gigabyte").startswith("Settings → IO Ports") and rb.path_for("other") == rb.path
      and "C.A.M." in rb.path_for("asrock"), "menu path per board maker, generic otherwise")

# ── B: BIOS detector ─────────────────────────────────────────────────────────
print("B  BIOS detector: only what Windows can really tell")
from core import bios_detector as BD
D = BD.BiosDetector
m = D.detect_memory_profile
check(m({"ram_speed": 6000, "ram_type": 34}).active, "DDR5-6000: profile active")
check(m({"ram_speed": 4800, "ram_type": 34}).active is False, "DDR5-4800: still at stock (the old '> 3200' said active)")
check(m({"ram_speed": 5600, "ram_type": 34}) is None, "DDR5-5600 (JEDEC top / 5600 kit): can't tell -> grey")
check(m({"ram_speed": 3600, "ram_type": 26}).active and m({"ram_speed": 2133, "ram_type": 26}).active is False,
      "DDR4: 3600 active, 2133 stock")
check(m({}) is None and m({"ram_speed": "x"}) is None, "no reading -> no result")
real_bar1 = BD._bar1_mb
BD._bar1_mb = lambda: (16384.0, 16376.0)
check(D.detect_rebar({}).active, "NVIDIA BAR1 16 GB -> Resizable BAR on")
BD._bar1_mb = lambda: (256.0, 16376.0)
r = D.detect_rebar({})
check(r.active is False and "256 MB" in r.note, "BAR1 256 MB -> off")
BD._bar1_mb = lambda: None
check(D.detect_rebar({}) is None, "no NVIDIA card -> not detectable")
check(D.detect_secure_boot({"secureboot": 1}).active and D.detect_secure_boot({"secureboot": 0}).active is False,
      "Secure Boot from the UEFI state")
check(D.detect_secure_boot({"firmware": "Legacy"}).active is False and D.detect_secure_boot({"firmware": "UEFI"}) is None,
      "Secure Boot: legacy boot = off, no value = unknown")
check(D.detect_csm({"firmware": "Legacy"}).active is False and D.detect_csm({"firmware": "UEFI", "secureboot": 1}).active
      and D.detect_csm({"firmware": "UEFI", "secureboot": 0}) is None, "CSM inferred only where it's certain")
BD._bar1_mb = lambda: (16384.0, 16376.0)
det = D()
det._gather = lambda: {"ram_speed": 6000, "ram_type": 34, "secureboot": 1, "firmware": "UEFI"}
res = det.detect_all()
check(set(res) == {"expo_xmp", "rebar", "secure_boot", "csm"} and all(r.active for r in res.values()),
      f"detect_all: {sorted(res)}")
det._gather = lambda: {}
BD._bar1_mb = lambda: None
check(D().detect_all.__func__(det) == {}, "nothing readable -> nothing claimed")
BD._bar1_mb = real_bar1
if os.name == "nt":
    t0 = time.time()
    raw = D()._gather()
    check(int(raw.get("ram_speed") or 0) > 0 and time.time() - t0 < 15, f"real read on this PC: {raw}")

# ── C: updater ───────────────────────────────────────────────────────────────
print("C  updater (fake network)")
from core import updater as UP
check(UP.parse_build('{"build": 15, "date": "2026-10-02", "notes": "x"}').build == 15
      and UP.parse_build("{}") is None and UP.parse_build("nonsense") is None
      and UP.parse_build('{"build": 0}') is None, "build.json parsing")
lb = UP.local_build()
check(lb.build >= 14 and lb.date, f"this version: build {lb.build} ({lb.date})")
check(UP.is_git_checkout(Path(ROOT)) and UP.git_clean(Path(ROOT)) in (True, False), "git checkout recognised")


def make_zip(build, extra=None, top="GameOptimizerPro-v2-main/"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(top + "GameOptimizerPro.py", "# new app\n")
        z.writestr(top + "build.json", json.dumps({"build": build, "date": "2026-10-03", "notes": "neu"}))
        z.writestr(top + "tools/apply_update.py", open(os.path.join(ROOT, "tools", "apply_update.py"),
                                                       encoding="utf-8").read())
        z.writestr(top + "core/new_module.py", "X = 1\n")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


app = Path(TMP) / "app"
(app / "logs").mkdir(parents=True)
(app / "GameOptimizerPro.py").write_text("# old app\n", encoding="utf-8")
(app / "build.json").write_text(json.dumps({"build": 14}), encoding="utf-8")
fetched = []
ok, msg = UP.download_and_stage(UP.BuildInfo(15), base=app,
                                fetch=lambda url, t: (fetched.append(url), make_zip(15))[1])
info = UP.pending(app)
check(ok and fetched == [UP.ZIP_URL] and info and info["build"] == 15
      and Path(info["dir"], "core", "new_module.py").exists(), f"download + unpack + check: {msg}")
ok2, msg2 = UP.download_and_stage(UP.BuildInfo(16), base=app, fetch=lambda u, t: make_zip(15))
check(not ok2 and "passt nicht" in msg2, "a zip with another build than announced is refused")
ok3, msg3 = UP.download_and_stage(UP.BuildInfo(15), base=app,
                                  fetch=lambda u, t: make_zip(15, {"../../evil.py": "x"}))
check(not ok3 and "unsafe" in msg3 and not (Path(TMP) / "evil.py").exists(), "zip-slip paths are refused")
ok4, msg4 = UP.download_and_stage(UP.BuildInfo(15), base=app, fetch=lambda u, t: b"not a zip")
check(not ok4 and UP.pending(app) is None, "a broken download leaves nothing pending")
UP.download_and_stage(UP.BuildInfo(15), base=app, fetch=lambda u, t: make_zip(15))
(app / "build.json").write_text(json.dumps({"build": 15}), encoding="utf-8")
check(UP.pending(app) is None and not (app / "logs" / "update").exists(),
      "an update that is already installed is no longer pending (marker removed)")
(app / "build.json").write_text(json.dumps({"build": 14}), encoding="utf-8")
real_get = UP._get
UP._get = lambda url, t: b'{"build": 99, "date": "2030-01-01"}'
check(UP.fetch_remote().build == 99, "remote build.json read")
UP._get = lambda url, t: (_ for _ in ()).throw(OSError("offline"))
check(UP.fetch_remote() is None, "offline -> None, no exception")
UP._get = real_get
launched = []
real_popen = UP.subprocess.Popen
UP.subprocess.Popen = lambda args, **kw: launched.append((args, kw))
UP.download_and_stage(UP.BuildInfo(15), base=app, fetch=lambda u, t: make_zip(15))
check(UP.launch_apply(UP.pending(app), base=app) and "--relaunch" in launched[-1][0]
      and launched[-1][0][1].endswith(os.path.join("tools", "apply_update.py"))
      and str(os.getpid()) in launched[-1][0], "the NEW version's installer is started with this pid")
UP.subprocess.Popen = real_popen

# ── D: installer ─────────────────────────────────────────────────────────────
print("D  installer (tools/apply_update.py on temp folders)")
spec = importlib.util.spec_from_file_location("apply_update", os.path.join(ROOT, "tools", "apply_update.py"))
AU = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AU)


def tree(base, files):
    for rel, data in files.items():
        p = Path(base, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")


src, dst = Path(TMP) / "src", Path(TMP) / "dst"
tree(src, {"GameOptimizerPro.py": "new", "core/a.py": "A2", "core/b.py": "B", "logs/x.txt": "never copied",
           "tools/apply_update.py": "#", "requirements.txt": "same\n", "README.md": "neu"})
tree(dst, {"GameOptimizerPro.py": "old", "core/a.py": "A1", "core/gone.py": "stale", "logs/keep.txt": "mine",
           "profiles/p.json": "{}", "requirements.txt": "same\n", "README.md": "neu", "FurMark_win64/f.exe": "3rd"})
ok, msg = AU.apply(src, dst, 15)
backup = dst / "logs" / "update_backup_15"
check(ok and (dst / "core" / "a.py").read_text() == "A2" and (dst / "core" / "b.py").exists()
      and (dst / "GameOptimizerPro.py").read_text() == "new", f"new files in place: {msg}")
check(not (dst / "core" / "gone.py").exists() and (backup / "core" / "gone.py").exists()
      and (backup / "core" / "a.py").read_text() == "A1" and not (backup / "README.md").exists(),
      "replaced + removed files backed up (unchanged ones not)")
check((dst / "logs" / "keep.txt").read_text() == "mine" and not (dst / "logs" / "x.txt").exists()
      and (dst / "profiles" / "p.json").exists() and (dst / "FurMark_win64" / "f.exe").exists(),
      "logs / profiles / third-party folders untouched")
# rollback: a file that can't be replaced
src2, dst2 = Path(TMP) / "src2", Path(TMP) / "dst2"
tree(src2, {"GameOptimizerPro.py": "new", "core/a.py": "A2", "core/z.py": "Z2", "core/new.py": "N"})
tree(dst2, {"GameOptimizerPro.py": "old", "core/a.py": "A1", "core/z.py": "Z1"})
os.chmod(dst2 / "core" / "z.py", stat.S_IREAD)
ok, msg = AU.apply(src2, dst2, 16)
os.chmod(dst2 / "core" / "z.py", stat.S_IREAD | stat.S_IWRITE)
check(not ok and (dst2 / "core" / "a.py").read_text() == "A1" and (dst2 / "GameOptimizerPro.py").read_text() == "old"
      and not (dst2 / "core" / "new.py").exists() and "wiederhergestellt" in msg,
      f"a failed copy restores the old state: {msg}")
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.4)"])
t0 = time.time()
check(AU.wait_for_exit(p.pid, 10) and time.time() - t0 < 5, "waits for the app process to end")
check(AU.wait_for_exit(0) and AU.wait_for_exit(999999), "no / unknown pid: nothing to wait for")
# the whole script: install + log + staging removed
src3 = dst / "logs" / "update" / "new" / "pkg"
tree(src3, {"GameOptimizerPro.py": "newer", "core/a.py": "A3", "tools/apply_update.py": "#",
            "requirements.txt": "same\n"})
(dst / "logs" / "update" / "pending.json").write_text("{}", encoding="utf-8")
rc = AU.main(["--src", str(src3), "--dst", str(dst), "--pid", "0", "--build", "17"])
log = (dst / "logs" / "update.log").read_text(encoding="utf-8")
check(rc == 0 and (dst / "core" / "a.py").read_text() == "A3" and "Build 17: OK" in log
      and not (dst / "logs" / "update").exists(), "apply_update.py: installed, logged, staging removed")
check(AU.main(["--src", str(Path(TMP) / "nothing"), "--dst", str(dst), "--pid", "0"]) == 2,
      "refuses a folder that isn't GameOptimizerPro")
pips = []
real_run = AU.subprocess.run
AU.subprocess.run = lambda *a, **k: (pips.append(a[0]), subprocess.CompletedProcess(a[0], 0))[1]
src4 = dst / "logs" / "update" / "new" / "pkg4"
tree(src4, {"GameOptimizerPro.py": "newest", "tools/apply_update.py": "#", "requirements.txt": "same\n"})
(dst / "requirements.txt").write_bytes(b"same  \r\n")
AU.main(["--src", str(src4), "--dst", str(dst), "--pid", "0", "--build", "18"])
check(not pips, "requirements.txt differing only in line endings: no pip run")
src5 = dst / "logs" / "update" / "new" / "pkg5"
tree(src5, {"GameOptimizerPro.py": "newest2", "tools/apply_update.py": "#", "requirements.txt": "same\nnewpkg\n"})
AU.main(["--src", str(src5), "--dst", str(dst), "--pid", "0", "--build", "19"])
check(len(pips) == 1 and "-r" in pips[0], "a new requirement: pip install -r requirements.txt")
AU.subprocess.run = real_run

# ── E: update flow (dialogs) ─────────────────────────────────────────────────
print("E  update flow: what the user is asked")
import ui.update_flow as UF


class Win:
    def __init__(self, tuning=False):
        self.tuner = types.SimpleNamespace(is_running=tuning)
        self.q, self.exits = [], []

    def after(self, ms, fn, *a):
        self.q.append((fn, a))

    def request_exit(self, relaunch=False):
        self.exits.append(relaunch)

    def pump(self):
        end = time.time() + 10
        while self.q and time.time() < end:
            fn, a = self.q.pop(0)
            fn(*a)
            time.sleep(0.01)


ASK, INFO, WARN, CALLS = [], [], [], []
UF.messagebox.askyesno = lambda title, msg, **k: (ASK.append(msg), ANSWER[0])[1]
UF.messagebox.showinfo = lambda title, msg, **k: INFO.append(msg)
UF.messagebox.showwarning = lambda title, msg, **k: WARN.append(msg)
ANSWER = [True]
FAKE = {"remote": UP.BuildInfo(15, "2026-10-03", "Neu: X"), "git": False, "clean": True, "stage": (True, "ok")}
U = UF.updater
U.local_build = lambda base=None: UP.BuildInfo(14, "2026-10-02")
U.fetch_remote = lambda timeout=6.0: FAKE["remote"]
U.is_git_checkout = lambda base=None: FAKE["git"]
U.git_clean = lambda base=None: FAKE["clean"]
U.download_and_stage = lambda remote, **k: (CALLS.append("stage"), FAKE["stage"])[1]
U.pending = lambda base=None: {"build": 15, "dir": "x"}
U.launch_apply = lambda info, relaunch=True, base=None: (CALLS.append("apply"), True)[1]
U.git_pull = lambda base=None: (CALLS.append("pull"), (True, "Updating"))[1]


def run(manual=False, tuning=False):
    w, status = Win(tuning), []
    UF.UpdateFlow(w).start(manual=manual, on_status=lambda t, k="info": status.append((t, k)))
    w.pump()
    return w, status


FAKE["remote"] = None
w, st = run(manual=True)
check("nicht erreichbar" in st[-1][0] and not ASK, "offline: says so, no dialog")
FAKE["remote"] = UP.BuildInfo(14)
w, st = run(manual=True)
check("Aktuell — Build 14" in st[-1][0] and not ASK, "up to date")
FAKE["remote"] = UP.BuildInfo(15, "2026-10-03", "Neu: X")
w, st = run()
check(ASK and "Build 15" in ASK[-1] and "Neu: X" in ASK[-1] and CALLS[-2:] == ["stage", "apply"]
      and w.exits == [False], "zip install: download, ask, install = restart via the installer")
ANSWER[0] = False
n = len(ASK)
w, st = run()
check(len(ASK) == n + 1 and CALLS[-1] == "stage" and not w.exits and "nächsten Start" in st[-1][0],
      "'no' = installed at the next start")
n = len(ASK)
w, st = run(tuning=True)
check(len(ASK) == n and not w.exits and "nächsten Start" in st[-1][0], "never asks / restarts during a tune")
FAKE["git"], ANSWER[0] = True, True
w, st = run()
check(CALLS[-1] == "pull" and w.exits == [True], "git checkout: 'git pull' and restart")
ANSWER[0] = False
w, st = run()
check(app_settings.get("update_declined") == 15, "git: 'no' is remembered for this build")
n = len(ASK)
w, st = run()
check(len(ASK) == n and "verfügbar" in st[-1][0], "... the automatic check doesn't ask again")
w, st = run(manual=True)
check(len(ASK) == n + 1, "... a manual check does")
FAKE["clean"] = False
n, c = len(ASK), len(CALLS)
w, st = run(manual=True)
check(len(ASK) == n and INFO and "lokalen Änderungen" in INFO[-1] and "pull" not in CALLS[c:],
      "git with local changes: no pull, the user is told")
# a second check while the first one's question is open (the user clicked "check now"
# right after the start; the automatic check came 8 s later): no second window
FAKE["git"], FAKE["clean"], ANSWER[0] = False, True, False
w2, st2 = Win(), []
flow = UF.UpdateFlow(w2)
n = len(ASK)
real_ask = UF.messagebox.askyesno


def ask_and_retrigger(title, msg, **k):
    ASK.append(msg)
    flow.start(on_status=lambda t, kk="info": st2.append(t))     # the 8-s timer fires meanwhile
    return False


UF.messagebox.askyesno = ask_and_retrigger
flow.start(manual=True, on_status=lambda t, kk="info": st2.append(t))
w2.pump()
UF.messagebox.askyesno = real_ask
check(len(ASK) == n + 1 and any("läuft schon" in s for s in st2) and not flow.busy,
      "a second check while the question is open: no second window, it says so")
FAKE["git"], FAKE["stage"] = False, (False, "Update-Download fehlgeschlagen: x")
w, st = run(manual=True)
check(WARN and "fehlgeschlagen" in WARN[-1] and st[-1][1] == "error", "a failed download is reported")

# ── F: tune history ──────────────────────────────────────────────────────────
print("F  tune history (now in the GPU tuner)")
from core.tune_history import TuneHistory
hd = Path(TMP) / "hist"
hd.mkdir()
(hd / "tune_20261001_114809.log").write_text(
    "x [INFO]   GameOptimizerPro Auto-Tune [CURVE]\nx [INFO] Profile saved: GOP\n"
    "x [INFO]   Core offset:  +135MHz (Kurve)\nx [INFO]   Memory offset:+1000MHz\n", encoding="utf-8")
(hd / "tune_20260930_101817.log").write_text(
    "x [INFO]   GameOptimizerPro Auto-Tune [OC UV]\nx [INFO]   Core offset:  +165MHz\n", encoding="utf-8")
(hd / "tune_broken-name.log").write_text("x [INFO]   GameOptimizerPro Auto-Tune [OC ONLY]\n", encoding="utf-8")
runs = TuneHistory(str(hd)).get_runs()
by = {r.filename: r for r in runs}
order = [r.filename for r in runs]
check(by["tune_20261001_114809.log"].mode == "Rundum" and by["tune_20261001_114809.log"].mem_offset == 1000
      and by["tune_20261001_114809.log"].passed and by["tune_20260930_101817.log"].mode == "OC+UV"
      and by["tune_20260930_101817.log"].mem_offset is None and not by["tune_20260930_101817.log"].passed,
      "runs, memory offset, result (unknown = None, not 0)")
# real log lines of runs from the live tests (shortened)
L1 = """2026-09-30 10:41:40,793 [INFO]   GameOptimizerPro Auto-Tune [OC UV]
2026-09-30 10:42:17,167 [INFO] Baseline OK | temp=68.1°C | GPU-Last=100% | volt=934mV | clk=2474MHz
2026-09-30 10:52:00,284 [INFO]   +165MHz ✓  step=15MHz  avg=67.1°C  volt=989mV  clk=2730/2940MHz
2026-09-30 10:55:41,087 [INFO] Stage 1 done: best core = +175MHz (precision ±5MHz)
2026-09-30 11:01:25,082 [INFO] Stage 2 done: best power = 97% (precision ±1%)
2026-09-30 11:01:25,082 [INFO] Final test: +175MHz | 97% pwr | Mem+1000MHz | 120s
2026-09-30 11:03:03,735 [WARNING] Final failed (Rechenfehler unter Last (GPU instabil)) — saving conservative profile
2026-09-30 11:03:07,663 [INFO]         Auto-Tune Complete
"""
L2 = """2026-10-01 11:43:38,448 [INFO]   GameOptimizerPro Auto-Tune [CURVE]
2026-10-01 11:44:14,833 [INFO] Baseline OK | temp=64.7°C | GPU-Last=96% | volt=940mV | clk=2456MHz
2026-10-01 11:44:25,103 [ERROR] Boost-Probe bei Standard fehlgeschlagen (TDR (GPU driver timeout) detected) — Kühlung/Treiber prüfen
"""
L3 = """2026-10-01 09:33:51,892 [INFO]   GameOptimizerPro Auto-Tune [CURVE]
2026-10-01 09:35:55,343 [INFO]   Punkt 1/5: 1075 mV (Stock 2805 MHz) — Start bei 2805 MHz (+0)
2026-10-01 09:53:29,966 [INFO] Eigene Kurve (−30 MHz Sicherheit, −60 nach Treiber-Reset): 1075 mV → 2939 MHz, 1025 mV → 2839 MHz
2026-10-01 09:59:16,461 [INFO] Stage 4 done: best memory = +1500MHz (precision ±25MHz)
2026-10-01 10:00:07,402 [INFO]   flach ab 1050 mV: 398 Punkte, Ø 246 W, max. 63 °C, 1.62 Punkte/W
"""
L4 = """2026-09-30 10:18:17,000 [INFO]   GameOptimizerPro Auto-Tune [OC UV]
2026-09-30 10:39:32,066 [INFO] Profile saved: GOP_OC+UV_0930_1039
2026-09-30 10:39:32,067 [INFO]   Core offset:  +179MHz
2026-09-30 10:39:32,067 [INFO]   Avg voltage:  995mV
"""
L5 = """2026-10-02 09:00:00,000 [INFO]   GameOptimizerPro Auto-Tune [CURVE]
2026-10-02 09:01:00,000 [WARNING] Abbruch angefordert — GPU wird auf Standard zurückgesetzt …
"""
hd2 = Path(TMP) / "hist2"
hd2.mkdir()
for name, txt in (("tune_20260930_104140.log", L1), ("tune_20261001_114338.log", L2),
                  ("tune_20261001_093351.log", L3), ("tune_20260930_101817.log", L4),
                  ("tune_20261002_090000.log", L5)):
    (hd2 / name).write_text(txt, encoding="utf-8")
(hd2 / "curve_report_20261002_090030.txt").write_text("report", encoding="utf-8")
(hd2 / "curve_report_20251201_000000.txt").write_text("other run", encoding="utf-8")
(hd2 / "settings.json").write_text("{}", encoding="utf-8")
th = TuneHistory(str(hd2))
r = {x.filename: x for x in th.get_runs()}
a = r["tune_20260930_104140.log"]
check((a.core_offset, a.power_pct, a.mem_offset, a.avg_volt_mv, a.max_temp) == (175, 97, 1000, 934, 68.1)
      and not a.passed and a.reason.startswith("Endtest fehlgeschlagen (Rechenfehler"),
      f"failed final test: the values tested last + the reason: {(a.core_offset, a.power_pct, a.mem_offset, a.reason)}")
b = r["tune_20261001_114338.log"]
check(b.core_offset is None and b.avg_volt_mv == 940 and b.reason.startswith("Boost-Probe bei Standard"),
      "stopped before any value: unknown stays '--', the error is the reason")
c = r["tune_20261001_093351.log"]
check(c.core_offset == 134 and c.mem_offset == 1500 and c.power_pct == 100 and "unterbrochen" in c.reason,
      f"All-round run cut off: offset of the own curve's top point, memory, stock power: {(c.core_offset, c.mem_offset)}")
d = r["tune_20260930_101817.log"]
check(d.passed and (d.core_offset, d.mem_offset, d.power_pct) == (179, 0, 100) and not d.reason,
      "finished run without memory / power lines: stock values (+0, 100 %), not '--'")
check(r["tune_20261002_090000.log"].reason == "abgebrochen", "stopped by the user: 'abgebrochen'")
check(th.delete(["tune_20261002_090000.log"]) == 1 and not (hd2 / "tune_20261002_090000.log").exists()
      and not (hd2 / "curve_report_20261002_090030.txt").exists()
      and (hd2 / "curve_report_20251201_000000.txt").exists(),
      "delete one run: its log and its report, nothing else")
check(th.delete(["../settings.json", "settings.json", "nope.log"]) == 0 and (hd2 / "settings.json").exists(),
      "delete never touches anything but tune logs in logs/")
check(th.delete_all() == 4 and not list(hd2.glob("tune_*.log")) and (hd2 / "settings.json").exists(),
      "delete all: every tune log, other files stay")
check(order.index("tune_20261001_114809.log") < order.index("tune_20260930_101817.log")
      and order[0] == "tune_broken-name.log" and by["tune_broken-name.log"].date == "broken-name",
      f"newest first; an odd file name sorts by its time and keeps its name as the date: {order}")

# ── G: removed features, close behaviour ─────────────────────────────────────
print("G  removed features, close behaviour")
gone = [m for m in ("core.game_monitor", "core.cpu_pinning", "core.cpu_topology", "core.fps_capture",
                    "ui.tab_games", "core.update_checker") if importlib.util.find_spec(m) is not None]
check(not gone, f"modules removed: {gone or 'all'}")
src_diag = open(os.path.join(ROOT, "ui", "tab_diagnose.py"), encoding="utf-8").read()
check("PresentMon" not in src_diag and "fps" not in src_diag.lower(), "Diagnose: no FPS capture any more")
import GameOptimizerPro as GOP
app_obj = object.__new__(GOP.GameOptimizerApp)
acts = []
app_obj._hide = lambda: acts.append("hide")
app_obj._exit = lambda *a, **k: acts.append("exit")
app_obj._tray = object()
app_settings.set("close_to_tray", True)
app_obj._on_close()
app_settings.set("close_to_tray", False)
app_obj._on_close()
app_obj._tray = None
app_settings.set("close_to_tray", True)
app_obj._on_close()
check(acts == ["hide", "exit", "exit"], f"X: tray (setting on), quit (off), quit without a tray icon: {acts}")
check(GOP.BASE.joinpath("build.json").exists(), "build.json ships with the app")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
