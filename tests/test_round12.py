"""Round 12 — logic without windows: persistent app settings, FurMark 1/2 +
3DMark detection and launch arguments, audio tweaks through the Windows audio
API, remnant scan (one Ultimate plan is normal), missing-customtkinter guard,
main-window helpers. Nothing is launched, installed or changed on the system."""
import json, os, subprocess, sys, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

tmp = tempfile.mkdtemp(prefix="gop_r12_")

# ── 1) app settings ──────────────────────────────────────────────────────────
print("app settings")
from core import app_settings
from pathlib import Path
real_file = app_settings.SETTINGS_FILE
app_settings.SETTINGS_FILE = Path(tmp) / "settings.json"
check(app_settings.get("x", 5) == 5, "missing key -> default")
check(app_settings.set("x", {"a": 1}) and app_settings.get("x") == {"a": 1}, "set + get round trip")
check(json.load(open(app_settings.SETTINGS_FILE, encoding="utf-8"))["x"] == {"a": 1}, "stored as JSON")
open(app_settings.SETTINGS_FILE, "w").write("{broken")
check(app_settings.load() == {} and app_settings.get("x", 7) == 7, "corrupt file -> empty, no crash")
check(app_settings.set("y", 1) and app_settings.load() == {"y": 1}, "rewritten cleanly after corruption")

# ── 2) FurMark 1 / 2 ─────────────────────────────────────────────────────────
print("FurMark")
from core import furmark
fm2 = Path(tmp) / "FurMark_win64"; fm2.mkdir()
(fm2 / "furmark.exe").write_bytes(b"MZ"); (fm2 / "FurMark_GUI.exe").write_bytes(b"MZ")
fm1 = Path(tmp) / "FurMark1"; fm1.mkdir()
(fm1 / "FurMark.exe").write_bytes(b"MZ")
check(furmark.normalize(str(fm2 / "FurMark_GUI.exe")) == str(fm2 / "furmark.exe"), "GUI exe -> CLI runner")
check(furmark.is_v2(str(fm2 / "furmark.exe")) and not furmark.is_v2(str(fm1 / "FurMark.exe")), "v1/v2 told apart")
a2 = furmark.build_args(str(fm2 / "furmark.exe"), 2560, 1440, 90, "furmark-knot-vk")
check(a2[1:] == ["--demo", "furmark-knot-vk", "--width", "2560", "--height", "1440", "--max-time", "90",
                 "--vsync", "0"], f"FurMark 2 command line: {a2[1:]}")
a8 = furmark.build_args(str(fm2 / "furmark.exe"), 2560, 1440, 90, "furmark-gl", 8)
check(a8[-2:] == ["--msaa", "8"] and "--vsync" in a8, "8x MSAA (GPU-bound even under an FPS cap / VSync)")
check("--msaa" not in furmark.build_args(str(fm2 / "furmark.exe"), 1920, 1080, 60, "furmark-gl", 3),
      "invalid MSAA value ignored")
st = furmark.parse_stats('[ Demo Quick Stats ]\n- frames               : 9707\n- duration             : 60005 ms\n- FPS (min/avg/max)    : 157 / 162 / 163\n- GPU 0: NVIDIA GeForce RTX 4080 [10DE-2704]\n  .max temperature: 58°C\n  .max usage: 45%\n  .max core clock: 2956 MHz\n  .min core clock: 2610 MHz\n')
check(st == {"fps_min": 157, "fps_avg": 162, "fps_max": 163, "frames": 9707, "max_temp": 58,
             "max_usage": 45, "clock_max": 2956, "clock_min": 2610, "duration_ms": 60005},
      f"FurMark's own stats parsed: {st}")
check(furmark.parse_stats("") == {} and furmark.parse_stats(None) == {}, "no output -> no stats")
check(furmark.build_args(str(fm2 / "furmark.exe"), 1920, 1080, 60, "bogus")[2] == "furmark-gl",
      "unknown demo -> furmark-gl")
a1 = furmark.build_args(str(fm1 / "FurMark.exe"), 1920, 1080, 60)
check(a1[1:] == ["/width=1920", "/height=1080", "/max_time=60000", "/nogui", "/run_mode=1"],
      f"FurMark 1 command line: {a1[1:]}")
check(furmark.describe(str(fm2 / "furmark.exe")) == "FurMark 2" and
      furmark.describe(str(fm1 / "FurMark.exe")) == "FurMark 1", "describe() without version info")
real_fm = os.path.join(ROOT, "FurMark_win64", "furmark.exe")
if os.path.exists(real_fm):
    d = furmark.describe(real_fm)
    check(d.startswith("FurMark 2 (v") and "0.0.0" not in d, f"real FurMark 2 shows its version: {d}")
furmark.APP_DIR, _real_app = Path(tmp), furmark.APP_DIR
furmark._INSTALL_PATHS, _real_paths = [], furmark._INSTALL_PATHS
check(furmark.detect() == str(fm2 / "furmark.exe"), "FurMark folders next to the app: FurMark 2 preferred")
shutil.rmtree(fm2)
check(furmark.detect() == str(fm1 / "FurMark.exe"), "... FurMark 1 found with its real file name")
fm2.mkdir(); (fm2 / "furmark.exe").write_bytes(b"MZ"); (fm2 / "FurMark_GUI.exe").write_bytes(b"MZ")
furmark.remember(str(fm1 / "FurMark.exe"))
check(furmark.detect() == str(fm1 / "FurMark.exe"), "a remembered choice wins after a restart")
furmark.remember(str(fm2 / "FurMark_GUI.exe"))
check(app_settings.get("furmark_path") == str(fm2 / "furmark.exe"), "remembering FurMark_GUI.exe stores the runner")
furmark.APP_DIR, furmark._INSTALL_PATHS = _real_app, _real_paths

# ── 3) 3DMark ────────────────────────────────────────────────────────────────
print("3DMark")
from core import threedmark
steam = Path(tmp) / "Steam"; (steam / "steamapps").mkdir(parents=True)
lib2 = Path(tmp) / "SteamLibrary"
exe = lib2 / "steamapps" / "common" / "3DMark" / "bin" / "x64" / "3DMark.exe"
exe.parent.mkdir(parents=True); exe.write_bytes(b"MZ")
vdf = ('"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n'
       '\t\t"apps"\n\t\t{\n\t\t\t"223850"\t\t"123"\n\t\t}\n\t}\n}\n'
       % (str(steam).replace("\\", "\\\\"), str(lib2).replace("\\", "\\\\")))
(steam / "steamapps" / "libraryfolders.vdf").write_text(vdf, encoding="utf-8")
libs = threedmark.steam_libraries(str(steam))
check([os.path.normcase(x) for x in libs] == [os.path.normcase(str(steam)), os.path.normcase(str(lib2))],
      f"all Steam libraries from libraryfolders.vdf: {libs}")
threedmark.steam_path, _real_sp = (lambda: str(steam)), threedmark.steam_path
threedmark._STANDALONE, _real_sa = [], threedmark._STANDALONE
check(threedmark.detect() == str(exe), "3DMark found in a second Steam library")
check(threedmark.is_steam(str(exe)) and not threedmark.is_steam(r"C:\Program Files\UL\3DMark\3DMark.exe"),
      "Steam version recognised")
check(threedmark.cmd_exe(str(exe)) is None, "no 3DMarkCmd.exe -> not the Professional Edition")
(exe.parent / "3DMarkCmd.exe").write_bytes(b"MZ")
check(threedmark.cmd_exe(str(exe)) == str(exe.parent / "3DMarkCmd.exe"), "Professional Edition CLI found")
STARTED = []
_real_startfile = os.startfile
os.startfile = lambda target: STARTED.append(("startfile", target))
_real_popen = subprocess.Popen
subprocess.Popen = lambda args, **kw: STARTED.append(("popen", args, kw.get("cwd")))
ok, msg = threedmark.launch(str(exe))
check(ok and STARTED[-1] == ("startfile", "steam://rungameid/223850"), f"Steam version started via Steam: {msg}")
sa = Path(tmp) / "UL" / "3DMark.exe"; sa.parent.mkdir(); sa.write_bytes(b"MZ")
ok, msg = threedmark.launch(str(sa))
check(ok and STARTED[-1] == ("popen", [str(sa)], str(sa.parent)), "standalone version started directly")
os.startfile, subprocess.Popen = _real_startfile, _real_popen
threedmark.remember(str(sa))
check(threedmark.detect() == os.path.normpath(str(sa)), "picked 3DMark.exe is remembered")
threedmark.steam_path, threedmark._STANDALONE = _real_sp, _real_sa
import psutil
class P:
    def __init__(self, n): self.info = {"name": n}
_real_iter = psutil.process_iter
psutil.process_iter = lambda attrs=None: [P("explorer.exe"), P("3DMark.exe"), P("3DMarkSpeedWay.exe")]
check(threedmark.running_processes() == ["3DMark.exe", "3DMarkSpeedWay.exe"], "launcher + workload processes seen")
psutil.process_iter = _real_iter

# ── 4) audio tweaks through the audio API ────────────────────────────────────
print("audio API tweaks")
from core import audio_policy
from core.tweaks import get_by_id
from core.tweak_verifier import VERIFY_MAP
s_off, s_on = audio_policy.ps_sysfx(True), audio_policy.ps_sysfx(False)
check("Add-Type -TypeDefinition @'" in s_off and "\n'@ -Language CSharp" in s_off, "C# compiled via here-string")
check("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9".lower() in audio_policy.CSHARP.lower() and
      "F8679F50-850A-41CF-9C72-430F290290C8".lower() in audio_policy.CSHARP.lower(),
      "IPolicyConfig CLSID + IID")
check("SetUInt($id,$true,'{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}',5,1)" in s_off and
      "SetUInt($id,$true,'{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}',5,0)" in s_on,
      "enhancements: Disable_SysFx 1 = off / 0 = on (FX store)")
e_off = audio_policy.ps_exclusive(False)
check(e_off.count("SetUInt($id,$false,'{b3f8fa53-0004-438e-9003-51a46e139bfc}'") == 2 and ",3,0)" in e_off
      and ",4,0)" in e_off, "exclusive mode: both switches off in the endpoint store")
check("value=1$" in s_off and "readback" in s_off, "the value is read back after writing")
t = get_by_id("disable_audio_enhancements")
check(t.ps_command == s_off and t.revert_cmd == s_on, "tweak 'audio enhancements' uses the API (+ revert)")
t = get_by_id("disable_audio_exclusive_lock")
check(t.ps_command == e_off and t.revert_cmd == audio_policy.ps_exclusive(True), "tweak 'exclusive mode' uses the API")
check("disable_audio_enhancements" in VERIFY_MAP and "disable_audio_exclusive_lock" in VERIFY_MAP,
      "both audio tweaks are verified")
check("HKLM" not in t.ps_command.split("Add-Type")[0], "no direct registry write any more (locked on 26H2)")

# ── 5) remnant scan: one Ultimate plan is normal ─────────────────────────────
print("remnant scan")
from core import remnant_detector as rd
_real_gather = rd._gather
def gather(plans):
    return lambda: {"powerplans": {"list": ";;".join(plans)}}
rd._gather = gather(["11111111-aaaa|Ultimative Leistung", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c|Höchstleistung"])
r = rd.scan()
pp = next(i for i in r.items if i.key == "powerplans")
check(r.ok and not pp.present, "one copy of Ultimate Performance is not reported")
rd._gather = gather(["1|Ultimate Performance", "2|Ultimate Performance", "3|Ultimate Performance",
                     "4|Driver Booster Power Plan"])
pp = next(i for i in rd.scan().items if i.key == "powerplans")
check(pp.present and "Ultimate Performance ×3 (Duplikate" in pp.detail and "Driver Booster Power Plan" in pp.detail,
      f"duplicates + foreign plans reported: {pp.detail!r}")
rd._gather = _real_gather

# ── 6) main window helpers + customtkinter guard ─────────────────────────────
print("main window helpers")
import ui.main_window as mw
check(mw._short_gpu("NVIDIA GeForce RTX 4080") == "RTX 4080", "GPU name shortened")
check(mw._short_cpu("AMD Ryzen 7 7800X3D 8-Core Processor") == "AMD Ryzen 7 7800X3D", "CPU name shortened")
check(mw._short_cpu("Intel(R) Core(TM) i7-14700K") == "Intel Core i7-14700K", "Intel CPU name shortened")
keys = [k for k, *_x in mw.TAB_DEFS]
check(len(keys) == len(set(keys)) == 10 and "startup" in keys and "services" in keys and "games" not in keys,
      "10 pages incl. Autostart + Dienste (the games page is gone)")
src = open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8").read()
check(all(f'"{k}": self._make_' in src for k in keys), "every page has a factory")
check(all(mw.TAB_COLORS.get(k) for k in keys), "every page has a colour")

print("missing customtkinter -> offer to install, no silent non-start")
code = ("import sys, ctypes; sys.modules['customtkinter'] = None\n"
        "ctypes.windll.user32.MessageBoxW = lambda *a: (print('ASKED', a[2]), 7)[1]\n"
        "import GameOptimizerPro as g\n"
        "print('WINDOW', g.GameOptimizerWindow)\n"
        "print('RESULT', g.ensure_ui_package())\n")
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                   encoding="utf-8", errors="replace", timeout=120)
out = r.stdout + r.stderr
check("WINDOW None" in out and "ASKED GameOptimizerPro" in out and "RESULT False" in out,
      f"import guard + question, 'No' -> no start: {out.strip()[-200:]!r}")
import GameOptimizerPro as gop
check(gop.GameOptimizerWindow is mw.GameOptimizerWindow and gop.ensure_ui_package() is True,
      "installed -> no question")
src = open(os.path.join(ROOT, "GameOptimizerPro.py"), encoding="utf-8").read()
check('app_settings.get("load_startup_profile", True)' in src,
      "start-up profile only loaded when the setting is on (the checkbox used to do nothing)")
req = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read()
check("customtkinter" in req, "customtkinter in requirements.txt (install.bat)")

app_settings.SETTINGS_FILE = real_file
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
