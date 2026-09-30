"""Optimization score + drift (fake verifier), monitor advisor (real, read-only),
Deep Clean (temp trees only — the real system is never cleaned; the Update
service is never stopped; the Recycle Bin is only QUERIED)."""
import ctypes, os, sys, tempfile, shutil, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []
def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)

# ── score / drift ─────────────────────────────────────────────────────────────
from core import optimization_score as osc
from core.tweak_verifier import VerifyResult, VERIFY_MAP
from core.tweaks import ALL_TWEAKS

class HW:
    is_nvidia, is_amd_gpu, has_nvme = True, False, False

class FakeVerifier:
    def __init__(self, active=(), errors=()):
        self.active, self.errors, self.asked = set(active), set(errors), []
    def verify_all(self, ids, expected):
        self.asked.append(list(ids))
        return {i: VerifyResult(i, True, i in self.active, False, "no output" if i in self.errors else "")
                for i in ids}

print("score")
ids = osc.score_ids(HW())
by = {t.id: t for t in ALL_TWEAKS}
check(all(by[i].risk == "safe" for i in ids), "only SAFE tweaks count")
check(not set(ids) & osc.SCORE_EXCLUDE, "one-time actions / either-or choices excluded")
check(not any(by[i].requires_amd for i in ids), "AMD-only tweaks excluded on NVIDIA")
check(not any(by[i].requires_nvme for i in ids), "NVMe-only tweaks excluded without NVMe")
check(all(i in VERIFY_MAP for i in ids), "every counted tweak is checkable")
fv = FakeVerifier(active=ids[:10], errors=ids[10:12])
r = osc.compute_score(HW(), fv)
check(r.active == 10 and r.unknown == 2 and r.checkable == len(ids) - 2,
      f"counts: {r.active}/{r.checkable}, unknown {r.unknown}")
check(r.score == round(10 / (len(ids) - 2) * 100), f"score {r.score} %")
check(osc.ScoreResult().score == 0, "no checkable tweaks -> 0 %, no division error")

print("drift")
amd = next(t.id for t in ALL_TWEAKS if t.requires_amd and t.id in VERIFY_MAP)
applied = ["disable_telemetry", "flush_dns", "run_disk_cleanup", "not_a_tweak", amd,
           "disable_advertising_id", "disable_bing_search"]
fv = FakeVerifier(active={"disable_bing_search"}, errors={"disable_advertising_id"})
d = osc.find_drift(applied, HW(), fv)
asked = fv.asked[0]
check("flush_dns" not in asked and "run_disk_cleanup" not in asked, "one-time actions never checked for drift")
check("not_a_tweak" not in asked and amd not in asked, f"unknown ids and not-applicable ({amd}) ignored")
check(d == ["disable_telemetry"],
      f"inactive -> drift, failed check -> NOT drift, active -> not drift: {d}")
check(osc.find_drift([], HW(), FakeVerifier()) == [], "nothing applied -> no check at all")

# ── monitor advisor ──────────────────────────────────────────────────────────
print("monitor advisor")
from core import display_info as di
check(ctypes.sizeof(di.DEVMODEW) == 220, "DEVMODEW is 220 bytes (Win32 layout)")
check(ctypes.sizeof(di.DISPLAY_DEVICEW) == 840, "DISPLAY_DEVICEW is 840 bytes")
ds = di.displays()
check(len(ds) >= 1 and ds[0].primary, f"{len(ds)} active display(s), primary first")
check(all(d.max_hz >= d.current_hz > 0 for d in ds), "max >= current for every display")
for d in ds:
    print(f"      {d.device}: {d.advice()}")
S = di.DisplayState
check(S("x", "", True, 2560, 1440, 144, 144).below_max is False, "at max -> no hint")
check(S("x", "", True, 2560, 1440, 143, 144).below_max is False, "143 vs 144 (rounding) -> no hint")
check(S("x", "", True, 1920, 1080, 60, 144).below_max is True, "60 of 144 -> hint")
check("UNTER" in S("x", "", True, 1920, 1080, 60, 144).advice(), "hint text")
check("unbekannt" in S("x", "", True, 1920, 1080, 0, 0).advice(), "unknown rate handled")

# ── Deep Clean on a fake tree ────────────────────────────────────────────────
print("deep clean (temp tree)")
import core.system_cleaner as sc
tmp = tempfile.mkdtemp(prefix="gop_clean_")
la, win, pd = (os.path.join(tmp, x) for x in ("Local", "Windows", "ProgramData"))
def mk(path, size=100):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    return path
keep = [
    mk(os.path.join(la, "Google", "Chrome", "User Data", "Default", "Login Data")),
    mk(os.path.join(la, "Google", "Chrome", "User Data", "Default", "History")),
    mk(os.path.join(la, "Google", "Chrome", "User Data", "Default", "Bookmarks")),
    mk(os.path.join(la, "Microsoft", "Edge", "User Data", "Profile 1", "Cookies")),
    mk(os.path.join(la, "Mozilla", "Firefox", "Profiles", "ab.default", "places.sqlite")),
    mk(os.path.join(la, "Microsoft", "Windows", "Explorer", "iconcache_32.db")),
    mk(os.path.join(win, "Prefetch", "Layout.ini")),
    mk(os.path.join(win, "Logs", "CBS", "CbsPersist_1.cab")),
    mk(os.path.join(win, "SoftwareDistribution", "DataStore", "DataStore.edb")),
]
gone = [
    mk(os.path.join(la, "Google", "Chrome", "User Data", "Default", "Cache", "Cache_Data", "f_000001"), 1000),
    mk(os.path.join(la, "Google", "Chrome", "User Data", "Default", "Code Cache", "js", "index"), 1000),
    mk(os.path.join(la, "Microsoft", "Edge", "User Data", "Profile 1", "Cache", "data_0"), 1000),
    mk(os.path.join(la, "Mozilla", "Firefox", "Profiles", "ab.default", "cache2", "entries", "A1"), 1000),
    mk(os.path.join(la, "Microsoft", "Windows", "Explorer", "thumbcache_256.db"), 1000),
    mk(os.path.join(win, "Prefetch", "GAME.EXE-12345678.pf"), 1000),
    mk(os.path.join(win, "Logs", "CBS", "CBS.log"), 1000),
    mk(os.path.join(win, "Minidump", "093026-1-01.dmp"), 1000),
    mk(os.path.join(win, "SoftwareDistribution", "Download", "abc", "update.cab"), 1000),
    mk(os.path.join(pd, "Microsoft", "Windows", "WER", "ReportQueue", "r1", "Report.wer"), 1000),
]
old_env = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "SystemRoot", "ProgramData")}
os.environ.update(LOCALAPPDATA=la, SystemRoot=win, ProgramData=pd)
svc_calls = []
sc._service = lambda action, name: svc_calls.append((action, name))
try:
    check(sc.get_deep_targets([]) == [], "no group chosen -> no deep targets")
    ts = sc.get_deep_targets(list(sc.DEEP_GROUPS))
    labels = sorted(t.label for t in ts)
    check(all(sc._is_safe(t.path, t.key) for t in ts), f"all {len(ts)} targets pass the guard")
    check(not any("Login Data" in t.path or t.path.endswith("Default") for t in ts),
          "browser profile folders themselves are never targets")
    sc.scan(ts)
    n_found = sum(t.file_count for t in ts)
    check(n_found == len(gone), f"scan finds exactly the {len(gone)} junk files ({n_found})")
    res = sc.clean(ts)
    check(res.files_deleted == len(gone) and res.bytes_freed == 1000 * len(gone),
          f"deleted {res.files_deleted}, freed {res.bytes_freed} B")
    check(all(not os.path.exists(p) for p in gone), "junk gone")
    check(all(os.path.exists(p) for p in keep), "passwords/history/bookmarks/cookies/places, iconcache, "
                                                "Layout.ini, .cab in CBS, DataStore untouched")
    check(os.path.isdir(os.path.join(win, "Prefetch")) and os.path.isdir(
        os.path.join(la, "Google", "Chrome", "User Data", "Default", "Cache")), "target roots kept")
    check(svc_calls == [("stop", "wuauserv"), ("start", "wuauserv")],
          f"Update service stopped + started around its cache (faked): {svc_calls}")
    # locked file -> skipped, not counted
    lock_p = mk(os.path.join(win, "Minidump", "locked.dmp"), 500)
    # open without any sharing (like a running program holding its dump)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    hl = k32.CreateFileW(lock_p, 0x80000000, 0, None, 3, 0x80, None)
    check(hl not in (None, ctypes.c_void_p(-1).value), "test file locked (no sharing)")
    try:
        res = sc.clean(sc.get_deep_targets(["logs"]))
        check(res.errors >= 1 and res.bytes_freed == 0 and os.path.exists(lock_p),
              f"file in use: skipped, counted as error, NOT as freed ({res.errors} err, {res.bytes_freed} B)")
    finally:
        k32.CloseHandle(ctypes.c_void_p(hl))
    # guard: a deep target whose last segment is wrong is refused
    bad = sc.CleanTarget("x", os.path.join(la, "Google"), exists=True, key="browser")
    check(not sc._is_safe(bad.path, "browser"), "guard refuses a browser root that isn't a cache folder")
    check(not sc._is_safe(r"C:\Users\Test\AppData\Roaming\Microsoft\Windows\Templates", ""),
          "'Templates' is not 'Temp'")
    check(not sc._is_safe(r"C:\Users\Test\temp_backup", ""), "'temp_backup' is not 'Temp'")
    check(sc._is_safe(r"C:\Users\Test\AppData\Local\Temp", ""), "'Temp' segment accepted")
    check(not sc._is_safe(r"C:\Temp"[:6], ""), "too-short paths refused")
finally:
    for k, v in old_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
shutil.rmtree(tmp, ignore_errors=True)

print("standard targets + recycle bin (read-only)")
std = sc.get_targets()
check([t.label for t in std] == ["Benutzer-Temp", "Windows-Temp", "Absturz-Dumps"] or len(std) >= 2,
      f"standard targets: {[t.label for t in std]}")
n, size = sc.recycle_bin_info()
check(isinstance(n, int) and isinstance(size, int) and n >= 0, f"recycle bin query: {n} items, {sc.human_size(size)}")
check(sc.DEEP_GROUPS["recyclebin"][2] is True and not any(v[2] for k, v in sc.DEEP_GROUPS.items() if k != "recyclebin"),
      "only the Recycle Bin needs the extra confirmation")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
