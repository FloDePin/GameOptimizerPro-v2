"""Round 12 — the new CustomTkinter UI under a real (invisible) main loop.
Main window with fakes (no hardware, registry or PowerShell access): lazy
pages, sidebar, shortcuts, window position, error page; the building blocks
(wrapping labels, responsive grid, check boxes, log, async hand-over, number
fields); every page with fake data — optimizer search + status badges + row
highlight, GPU tuner views, stress test with FurMark/3DMark and the recording
of an external test, settings, games (choice dialog), BIOS cards, compare,
startup apps, diagnose. Nothing is launched or changed on the system; settings
go to a TEMP file."""
import os, sys, tempfile, threading, time, traceback, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

import tkinter as tk
from tkinter import messagebox
BOXES, ANSWERS = [], []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, (lambda n: lambda *a, **k: BOXES.append((n,) + a))(n))
messagebox.askyesno = lambda *a, **k: ANSWERS.pop(0) if ANSWERS else False
ERRORS = []
tk.Tk.report_callback_exception = lambda self, e, v, tb: ERRORS.append(
    "".join(traceback.format_exception(e, v, tb))[-900:])

tmp = tempfile.mkdtemp(prefix="gop_ui12_")
from pathlib import Path
from core import app_settings
app_settings.SETTINGS_FILE = Path(tmp) / "settings.json"

# ── fakes: nothing below touches the real system ──────────────────────────────
from core.nvtune_core import GpuStats, ProfileManager, TuneProfile
class FakeMAHM:
    available = True
    def read(self):                     # like MahmReader.read(): a MAHM snapshot
        return type("MahmData", (), {"gpu_voltage_mv": 1050.0})()
class FakeNVML:
    available = True
class FakeMon:
    mahm, nvml = FakeMAHM(), FakeNVML()
    temp = 64
    def read(self):
        return GpuStats(name="NVIDIA GeForce RTX 4080", temp=self.temp, core_mhz=2745.0, mem_mhz=11200.0,
                        voltage_mv=1050.0, gpu_power_w=280.0, power_w=280.0, gpu_usage=98.0, fan_pct=55.0,
                        temp_limit_c=90.0, power_max_w=320.0, vram_total_mb=16376, vram_used_mb=4200)
    def close(self): pass
    def power_pct_to_watts(self, pct): return 320.0
    def set_power_limit(self, w): pass
class FakeAB:
    available, exe, last_notes = True, r"C:\fake\MSIAfterburner.exe", []
    def check_ab_setup(self):
        return {"cfg_found": True, "voltage_control": True, "voltage_monitoring": True}
    writes = []
    def find_gpu_profile(self): return r"C:\fake\VEN_10DE.cfg", ""
    def write_and_apply(self, slot, p):
        FakeAB.writes.append((slot, p.name)); return True, ""
    def slot_summaries(self, de=True):
        return {1: "Core +0 · Speicher +0 · Power 100 %", 2: "Kurve · Speicher +1000 · Power 100 %",
                3: "leer", 4: "leer", 5: "leer"}
    def reset_to_stock(self, slot=2): return True, ""
    def startup_apply_enabled(self): return False
    def base_curve(self, slot=2):                     # round 24: the card's stock V/F curve
        import struct
        from core import ab_profile as _AP
        pts = [(450.0, 225.0, 0.0)] + [(float(v), 1955 + (v - 700) * 2.4, 0.0) for v in range(700, 1101, 5)]
        raw = struct.pack("<II", _AP.VF_VERSION, len(pts)) + bytes(4)
        for p in pts:
            raw += struct.pack("<fff", *p)
        return _AP.VFCurve.from_hex((raw + bytes(24)).hex().upper()), "Defaults"
class FakeSL:
    auto, calls, fail = False, [], False
    def is_autostart_enabled(self): return self.auto
    def set_autostart(self, on):
        self.calls.append(on)
        return not self.fail
    def load_startup_profile(self): return True, "Profil 'Test' geladen"
from core.hardware import HardwareInfo
hw = HardwareInfo(cpu_name="AMD Ryzen 7 7800X3D 8-Core Processor", cpu_cores=8, cpu_threads=16,
                  gpu_name="NVIDIA GeForce RTX 4080", gpu_vram_mb=16376, gpu_vendor="NVIDIA", is_nvidia=True,
                  ram_total_gb=32, ram_type="DDR5", ram_speed_mhz=6000, ram_slots_used=2,
                  mb_manufacturer="ASUSTeK COMPUTER INC.", mb_product="ROG STRIX B650E-F GAMING WIFI",
                  os_name="Windows 11 Pro", os_build=26300, is_win11=True, has_nvme=True, nvme_count=2)

import core.optimization_score as osc
class R: active, checkable, unknown, score = 70, 80, 2, 88
osc.compute_score = lambda hw, verifier=None: R()
import core.display_info as di
di.displays = lambda: []
from core.tweak_verifier import TweakVerifier
TweakVerifier.verify_all = lambda self, ids, exp: {}
import core.services as svc
svc.is_admin = lambda: False
svc.list_services = lambda: []
import core.startup_control as sc
from core.startup_control import StartupEntry
sc.list_entries = lambda: [StartupEntry("Discord", r"C:\Users\x\Discord\Update.exe --processStart", "HKCU\\Run"),
                           StartupEntry("SecurityHealthSystray", r"C:\Windows\System32\SecurityHealthSystray.exe",
                                        "HKLM\\Run"),
                           StartupEntry("OldTool", r"C:\Tools\old.exe", "HKCU\\Run", enabled=False)]
from core.bios_detector import BiosDetector, DetectResult
BiosDetector.detect_all = lambda self: {"expo_xmp": DetectResult("expo_xmp", True, "DDR5-6000"),
                                        "rebar": DetectResult("rebar", False, "BAR1 256 MB", note="aus"),
                                        "secure_boot": DetectResult("secure_boot", True, "an")}
from core import furmark, threedmark
fmdir = Path(tmp) / "FurMark_win64"; fmdir.mkdir()
(fmdir / "furmark.exe").write_bytes(b"MZ"); (fmdir / "FurMark_GUI.exe").write_bytes(b"MZ")
furmark.detect = lambda: str(fmdir / "furmark.exe")
threedmark.detect = lambda: None
import core.crash_recovery as crm
crm.CrashRecovery.check_tdr_since = lambda self, seconds_back=15: False

from core.tweak_runner import TweakRunner
runner = TweakRunner(log_dir=tmp)
runner.backup_registry = lambda label: None
runner._run_ps = lambda cmd, timeout=60: (True, "ok")
from core.nvtune_tuner import AutoTuner, TunerConfig
with open(os.path.join(tmp, "tune_20261001_114809.log"), "w", encoding="utf-8") as _f:
    _f.write("2026-10-01 11:48:09,636 [INFO]   GameOptimizerPro Auto-Tune [CURVE]\n"
             "2026-10-01 12:25:49,248 [INFO] Profile saved: GOP_CURVE_BAL_1001_1225\n"
             "2026-10-01 12:25:49,248 [INFO]   Core offset:  +135MHz (Kurve, oberster Punkt)\n"
             "2026-10-01 12:25:49,248 [INFO]   Memory offset:+1000MHz\n"
             "2026-10-01 12:25:49,248 [INFO]   Max temp:     65°C\n")
pm = ProfileManager(os.path.join(tmp, "profiles"))
pm.save(TuneProfile(name="P1", core_offset_mhz=120, mem_offset_mhz=800, power_limit_pct=90, stability_score=95))
pm.save(TuneProfile(name="P2", core_offset_mhz=90, mem_offset_mhz=500, power_limit_pct=80, stability_score=88))
mon, ab, sl = FakeMon(), FakeAB(), FakeSL()
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=tmp)

import customtkinter as ctk
import ui.main_window as mw
t0 = time.perf_counter()
w = mw.GameOptimizerWindow(hw, mon, ab, pm, tuner, runner, startup_loader=sl)
build_ms = (time.perf_counter() - t0) * 1000
w.attributes("-alpha", 0.0)

STEPS = []
def step(ms):
    def deco(fn): STEPS.append((ms, fn)); return fn
    return deco

# ── main window ───────────────────────────────────────────────────────────────
@step(300)
def s_window():
    print("main window")
    check(list(w._tab_frames) == ["dashboard"], f"only the dashboard is built at start ({build_ms:.0f} ms)")
    check(w._active_tab == "dashboard" and w._tab_btns["dashboard"].cget("fg_color") != "transparent"
          and w._tab_btns["gpu"].cget("fg_color") == "transparent", "sidebar marks the active page")
    check(w.lbl_ab.cget("text") == "● AB" and w.lbl_ab.cget("fg") == "#22c55e", "status chips (AB/NVML/MAHM)")
    check(w.btn_lang.cget("text") in ("DE", "EN"), "language button")
    w.event_generate("<Control-Key-3>")
    check(w._active_tab == "gpu", "Ctrl+3 opens the GPU tuner")
    dash = w._tab_frames["dashboard"]
    check(dash._visible is False, "hidden dashboard stops reading sensors")
    w._open_startup_mgr()
    check(w._active_tab == "startup" and "startup" in w._tab_frames, "Autostart is a page now")
    w._open_services()
    check(w._active_tab == "services", "Services is a page now")
    w._page_factories["broken"] = lambda parent: 1 / 0
    page = w._ensure_page("broken")
    texts = [c.cget("text") for c in page.winfo_children()]
    check(any("ZeroDivisionError" in t for t in texts), "a failing page shows its error instead of killing the window")
    del w._page_factories["broken"]; w._tab_frames.pop("broken").destroy()
    w.geometry("1111x777+120+90")

@step(3500)
def s_prebuild():
    check("optimizer" in w._tab_frames and "gpu" in w._tab_frames, "optimizer + GPU tuner built in the background")
    g = app_settings.get("window") or {}
    check(g.get("w") == 1111 and g.get("h") == 777, f"window size remembered: {g}")
    for key, *_x in mw.TAB_DEFS:
        w._show_tab(key)
    w.update()
    check(len(w._tab_frames) == len(mw.TAB_DEFS) == 10 and not ERRORS,
          f"all 10 pages open without errors ({len(ERRORS)})")

# ── building blocks ───────────────────────────────────────────────────────────
@step(200)
def s_components():
    print("building blocks")
    from ui import components as C
    w._show_tab("settings")
    host = tk.Frame(w._content, bg="#000000", width=600, height=400)
    host.place(x=0, y=0, width=600, height=400)
    global HOST
    HOST = host
    lbl = C.WrapLabel(host, text="lorem ipsum " * 60)
    lbl.pack(fill="x")
    grid = C.ResponsiveGrid(host, min_width=200, max_cols=4, gap=10)
    grid.pack(fill="x")
    for i in range(4):
        grid.add(tk.Frame(grid, width=50, height=20, bg="#123456"))
    v = tk.BooleanVar(value=False)
    cb = C.CheckBox(host, v, text="x")
    cb.pack()
    cb.invoke()
    check(v.get() is True, "check box toggles its variable")
    iv = tk.IntVar(value=5)
    nf = C.NumberField(host, iv, 0, 10, 3)
    nf.pack()
    nf.bump(+3); nf.bump(+3)
    check(iv.get() == 10, "number field clamps at the upper limit")
    iv.set(-4); nf.clamp()
    check(iv.get() == 0, "typed value below the limit clamped")
    writes = []
    iv.trace_add("write", lambda *_a: writes.append(1))
    iv.set(7); writes.clear(); nf.clamp()
    check(iv.get() == 7 and not writes, "a value in range: clamp writes nothing (no 'change' for a trace)")
    n_err = len(ERRORS)
    nf.entry.delete(0, "end"); writes.clear(); nf.clamp()
    del ERRORS[n_err:]      # CustomTkinter's own entry callback reads the IntVar: "" raises there
    check(iv.get() == 0 and len(writes) == 1, "an emptied field: clamp writes the lower limit")
    log = C.LogView(host, height=4)
    log.pack(fill="x")
    def writer():
        for i in range(40):
            log.append(f"line {i}", "info")
    th = threading.Thread(target=writer); th.start(); th.join()
    global LOG, BOX, GRID, LBL
    LOG, GRID, LBL = log, grid, lbl
    BOX = {}
    C.run_async(w, lambda: threading.current_thread().name,
                lambda r: BOX.update(worker=r, main=threading.current_thread() is threading.main_thread()))
    g = C.GaugeBar(host, "Temp", "°C", "#ef4444")
    g.pack(fill="x")
    g.set(45, 90)
    check(g.lbl.cget("text") == "45°C" and abs(g._pct - 0.5) < 1e-9, "gauge bar value + fill")

@step(600)
def s_components2():
    w.update()
    check(0 < LBL.cget("wraplength") <= 600, f"label wraps to its width ({LBL.cget('wraplength')})")
    cols = {int(c.grid_info()["column"]) for c in GRID._items}
    check(cols == {0, 1}, f"600 px / min 200 px -> 2 columns ({sorted(cols)})")
    HOST.place_configure(width=950)
    w.update()
    cols = {int(c.grid_info()["column"]) for c in GRID._items}
    check(cols == {0, 1, 2, 3}, f"950 px -> 4 columns ({sorted(cols)})")
    from ui import components as C
    box6 = tk.Frame(HOST, width=900, height=120)      # 900 px: (900+10) // (150+10) = 5 fit
    box6.pack(anchor="w")
    box6.pack_propagate(False)
    g6 = C.ResponsiveGrid(box6, min_width=150, max_cols=6, gap=10)
    g6.pack(fill="x")
    for i in range(6):
        g6.add(tk.Frame(g6, width=40, height=10))
    w.update()
    rows6 = sorted({int(c.grid_info()["row"]) for c in g6._items})
    cols6 = sorted({int(c.grid_info()["column"]) for c in g6._items})
    check(g6._fit == 5 and cols6 == [0, 1, 2] and rows6 == [0, 1],
          f"6 tiles where 5 fit -> balanced 3 + 3 (fit {g6._fit}, cols {cols6})")
    lines = LOG.txt.get("1.0", "end").strip().splitlines()
    check(len(lines) == 40 and lines[-1].endswith("line 39"), "log written from a worker thread shows up in order")
    check(BOX.get("main") is True and BOX.get("worker") != "MainThread", "run_async: work off, result on the main thread")
    HOST.destroy()

# ── optimizer ─────────────────────────────────────────────────────────────────
@step(100)
def s_optimizer():
    print("optimizer")
    opt = w._tab_frames["optimizer"]
    w._show_tab("optimizer")
    opt._show_section("windows")
    w.update()
    rows = [x for x in opt._rows["windows"] if x[0] == "row"]
    opt.ent_search.insert(0, "telemetr")
    opt._apply_filter()
    shown = [t.id for k, wdg, t in rows if wdg.winfo_manager()]
    check("disable_telemetry" in shown and 0 < len(shown) < len(rows),
          f"search filters the list ({len(shown)} of {len(rows)})")
    opt.ent_search.delete(0, "end"); opt.ent_search.insert(0, "xyzzy-nothing")
    opt._apply_filter()
    check(not any(wdg.winfo_manager() for k, wdg, t in rows) and opt._empty_lbl["windows"].winfo_manager(),
          "no match -> 'Kein Tweak passt zur Suche'")
    opt.ent_search.delete(0, "end")
    opt._apply_filter()
    heads = [wdg for k, wdg, t in opt._rows["windows"] if k == "group"]
    check(not any(wdg.winfo_manager() for k, wdg, t in rows) and all(h.winfo_manager() for h in heads),
          "round 19: the categories start closed — only their headers show")
    first = next(t for k, wdg, t in opt._rows["windows"] if k == "group")
    opt._toggle_group("windows", first)
    in_first = [wdg for k, wdg, t in rows if t.group == first]
    check(all(wdg.winfo_manager() for wdg in in_first)
          and not any(wdg.winfo_manager() for k, wdg, t in rows if t.group != first)
          and first in app_settings.get("optimizer_open_groups", []),
          f"a click on '{first}' opens it (the others stay closed), remembered")
    cnt = opt._group_heads[("windows", first)]["count"].cget("text")
    check(str(len(in_first)) in cnt, f"the header counts its tweaks: {cnt!r}")
    opt.set_all_groups("windows", True)
    check(all(wdg.winfo_manager() for k, wdg, t in rows), "'Alle auf' -> all rows back")
    w.update()                          # the rows are viewable again (pointer events)
    runner._applied["disable_telemetry"] = "2026-09-30T12:00:00"
    opt._update_dots()
    check(opt._active_badges["disable_telemetry"].winfo_manager() == "pack"
          and opt._dot_labels["disable_telemetry"].cget("text") == "◑", "applied -> ◑ + 'aktiv' badge")
    runner._applied.pop("disable_telemetry")
    opt._update_dots()
    check(not opt._active_badges["disable_telemetry"].winfo_manager(), "not applied -> badge hidden again")
    row = opt._name_labels["disable_telemetry"].master.master
    badge_bg = [b for b in row.winfo_children()[-1].winfo_children()][0].cget("bg")
    row.event_generate("<Enter>")
    check(opt._name_labels["disable_telemetry"].cget("bg") != "#151a22", "row highlighted under the pointer")
    check([b for b in row.winfo_children()[-1].winfo_children()][0].cget("bg") == badge_bg, "badges keep their tint")
    row.winfo_containing = lambda x, y: None
    row.event_generate("<Leave>")
    check(opt._name_labels["disable_telemetry"].cget("bg") == "#151a22", "highlight removed on leave")
    opt._show_section("presets")
    check(opt.seg.get() == "Presets" and opt._section_frames["presets"].winfo_manager(), "segmented section bar")

# ── GPU tuner ─────────────────────────────────────────────────────────────────
@step(100)
def s_gpu():
    print("GPU tuner")
    g = w._tab_frames["gpu"]
    w._show_tab("gpu")
    g._show_view("profiles")
    check(g._views["profiles"].winfo_manager() and not g._views["auto"].winfo_manager(), "sub-pages switch")
    check(set(g.tree.get_children()) == {"P1", "P2"}, "profiles listed")
    g._show_view("auto")
    check(g.v_mode.get() == "curve" and list(g._mode_labels.values()) == ["curve", "oc_uv"],
          "two modes, Rundum first and selected")
    g._select_mode("oc_uv")
    desc = g.lbl_mode_desc.cget("text")
    check(g.v_mode.get() == "oc_uv" and g.v_mem_stage.get() and g.params_card.winfo_manager() == "pack"
          and ("Power-Limit" in desc or "power limit" in desc),
          "mode 'Schnell (OC + UV)' sets the parameters and explains itself")
    g.prog_var.set(50)
    check(abs(g.prog_bar.get() - 0.5) < 1e-6, "progress bar follows the tuner progress")
    w.update()
    lg = g.log.winfo_height()
    check(lg > 60, f"the tuner log is visible without enlarging the window ({lg} px high)")

# ── stress test ───────────────────────────────────────────────────────────────
PROCS = []
class FakeProc:
    def __init__(self, n, out=None):
        self.n = n; self.returncode = None
        if out is not None:
            import io
            self.stdout = io.StringIO(out)
    def poll(self):
        self.n -= 1
        if self.n <= 0:
            self.returncode = 0
            return 0
        return None
@step(100)
def s_stress():
    print("stress test")
    st = w._tab_frames["stress"]
    w._show_tab("stress")
    check("FurMark 2" in st.lbl_furmark_path.cget("text") and str(st.opt_demo.cget("state")) == "normal",
          "FurMark 2 recognised, demo choice enabled")
    check(str(st.btn_3dm_start.cget("state")) == "disabled" and st.btn_3dm_store.winfo_manager(),
          "3DMark missing -> start disabled, store link shown")
    import ui.tab_stress as ts
    ts.subprocess.Popen, st._real_popen = (lambda args, **kw: (PROCS.append(args), FakeProc(4))[1]), ts.subprocess.Popen
    st.v_fur_demo.set(furmark.DEMOS["furmark-vk"])
    st.v_fur_res.set("2560x1440")
    st.v_fur_dur.set(90)
    st._launch_furmark()
    check(PROCS and PROCS[-1][1:] == ["--demo", "furmark-vk", "--width", "2560", "--height", "1440",
                                      "--max-time", "90", "--vsync", "0", "--msaa", "8"],
          f"FurMark 2 started with its own switches, 8x MSAA by default: {PROCS[-1][1:] if PROCS else None}")
    check(app_settings.get("furmark_res") == "2560x1440" and app_settings.get("furmark_demo") == "furmark-vk",
          "FurMark choices remembered")
    check(st._ext is not None and st.btn_rec_stop.winfo_manager(), "recording of the external test started")

@step(6500)
def s_stress2():
    st = w._tab_frames["stress"]
    import ui.tab_stress as ts
    ts.subprocess.Popen = st._real_popen
    txt = st.lbl_session.cget("text")
    check(st._ext is None and "Peak 64 °C" in txt and "max. 280 W" in txt and "Ø Takt 2745 MHz" in txt
          and "kein Treiber-Reset" in txt, f"summary after FurMark ended: {txt!r}")
    check(not st.btn_rec_stop.winfo_manager(), "stop-recording button hidden again")
    check("nicht voll ausgelastet" not in txt, "full load -> no load warning")
    # an FPS cap / forced VSync: FurMark ran, but the GPU idled half the time
    FakeMon.read_orig = FakeMon.read
    FakeMon.read = lambda self: GpuStats(name="NVIDIA GeForce RTX 4080", temp=57, core_mhz=2800.0,
                                         gpu_power_w=187.0, power_w=187.0, gpu_usage=44.0)
    st._start_session("FurMark", proc=FakeProc(3, '[ Demo Quick Stats ]\n- frames               : 9707\n- duration             : 60005 ms\n- FPS (min/avg/max)    : 157 / 162 / 163\n- GPU 0: NVIDIA GeForce RTX 4080 [10DE-2704]\n  .max temperature: 58°C\n  .max usage: 45%\n  .max core clock: 2956 MHz\n  .min core clock: 2610 MHz\n'), status=st.lbl_fur_status)

@step(6500)
def s_stress3():
    st = w._tab_frames["stress"]
    FakeMon.read = FakeMon.read_orig
    txt = st.lbl_session.cget("text")
    check("FurMark: Ø 162 FPS (min 157), max. GPU-Last 45 %" in txt, f"FurMark's own FPS / load shown: {txt[:160]!r}")
    check("nicht voll ausgelastet" in txt and "Max. Bildfrequenz" in txt and "8×" in txt,
          "capped run explained (FPS limit / VSync) with the fix, not just 'no load'")

# ── settings ──────────────────────────────────────────────────────────────────
@step(100)
def s_settings():
    print("settings")
    st = w._tab_frames["settings"]
    check(str(st.sw_autostart.cget("state")) == "normal" and st.v_autostart.get() is False,
          "autostart state read in the background")
    st.sw_load_startup.toggle()
    check(app_settings.get("load_startup_profile") is False, "'load startup profile' is saved (was a dead checkbox)")
    check(st.v_check_updates.get() is True and st.v_close_to_tray.get() is True,
          "update check and close-to-tray on by default")
    st.sw_check_updates.toggle(); st.sw_close_to_tray.toggle()
    check(app_settings.get("check_updates") is False and app_settings.get("close_to_tray") is False,
          "both switches are saved")
    from core import updater as _up
    check(f"build {_up.local_build().build}" in st.lbl_update.cget("text").lower(),
          f"installed build shown: {st.lbl_update.cget('text')!r}")
    class FakeFlow:
        def start(self, manual=False, on_status=None):
            self.manual = manual
            on_status("Aktuell — Build 14.", "success")
    w.update_flow = FakeFlow()
    st._check_updates_now()
    check(w.update_flow.manual and st.lbl_update.cget("text") == "Aktuell — Build 14." and
          st.lbl_update.cget("fg") == "#22c55e", "'check now' runs the update flow and shows its result")
    del w.update_flow
    st.sw_autostart.toggle()

@step(400)
def s_settings2():
    st = w._tab_frames["settings"]
    check(FakeSL.calls == [True] and st.v_autostart.get() is True, "autostart switch -> set_autostart(True)")
    FakeSL.fail = True
    st.sw_autostart.toggle()

@step(400)
def s_settings3():
    st = w._tab_frames["settings"]
    check(FakeSL.calls[-1] is False and st.v_autostart.get() is True and BOXES and BOXES[-1][0] == "showerror",
          "failed change -> error + switch back")
    texts = []
    def walk(x):
        for c in x.winfo_children():
            try: texts.append(str(c.cget("text")))
            except tk.TclError: pass
            walk(c)
    walk(st.setup_frame)
    check(any("AB: Unlock Voltage Control" in t for t in texts), "Afterburner setup rows")
    check(any("AB: startet mit Windows" in t for t in texts)
          and any("Übertaktung beim Systemstart" in t for t in texts),
          "setup rows: Afterburner starts with Windows / applies the overclock at start-up")

# ── tune history (moved from the removed games page into the GPU tuner) ──────
@step(100)
def s_history():
    print("tune history in the GPU tuner")
    g = w._tab_frames["gpu"]
    check(list(g._view_keys.values()) == ["auto", "profiles", "manual", "history"], "GPU tuner views")
    check(not g.history._loaded, "the logs are read only when the view is opened")
    g._show_view("history")
    rows = g.history.tree.get_children()
    check(g._views["history"].winfo_manager() and rows == ("tune_20261001_114809.log",), f"one run listed: {rows}")
    vals = g.history.tree.item(rows[0], "values")
    check(vals[1] in ("Rundum", "All-round") and vals[2] == "+135" and vals[3] == "+1000" and vals[4] == "100%"
          and "OK" in vals[7] and vals[8] == "",
          f"mode, core, memory, result: {vals}")
    g.history.tree.selection_set(rows[0]); g.history._on_select(); g.history.log._drain()
    check("Profile saved" in g.history.log.txt.get("1.0", "end"), "selecting a run shows its log")

    # right click: the run's saved profile into an Afterburner slot
    import ui.tab_gpu as TG
    pm.save(TuneProfile(name="GOP_CURVE_BAL_1001_1225", curve_points=[[1075, 2940], [925, 2560]],
                        mem_offset_mhz=1000))
    posted, asked_ab, shown = [], [], []
    real_post, real_ask_ab, real_info = g._post, TG.messagebox.askyesno, TG.messagebox.showinfo
    g._post = lambda menu, x, y: posted.append(menu)
    run = g.history._runs[rows[0]]
    check(run.profile_name == "GOP_CURVE_BAL_1001_1225", "the run knows its saved profile")
    bbox = g.history.tree.bbox(rows[0])
    if bbox:                                                          # the real binding
        g.history.tree.event_generate("<Button-3>", x=bbox[0] + 5, y=bbox[1] + 3)
    check(bbox and posted, "right click on the row opens the menu")
    g._on_history_menu(run, 10, 10)
    m = posted[-1]
    entries = [(m.type(i), m.entrycget(i, "label") if m.type(i) == "command" else "")
               for i in range(m.index("end") + 1)]
    slots = [lbl for typ, lbl in entries if typ == "command"][1:]
    check(len(slots) == 5 and "Kurve · Speicher +1000" in slots[1] and "leer" in slots[2]
          and ("eigenen" in slots[0] or "own" in slots[0]),
          f"menu: five slots with what they hold now, slot 1 marked as the user's: {slots}")
    TG.messagebox.askyesno = lambda title, msg, **k: (asked_ab.append(msg), True)[1]
    TG.messagebox.showinfo = lambda title, msg, **k: shown.append(msg)
    FakeAB.writes.clear()
    m.invoke(4)                                                       # slot 3
    t_end = time.time() + 5
    while not shown and time.time() < t_end:
        w.update(); time.sleep(0.02)
    check(FakeAB.writes == [(3, "GOP_CURVE_BAL_1001_1225")] and asked_ab and "leer" in asked_ab[-1]
          and shown and "3" in shown[-1],
          f"slot 3: asked first (with what is there now), written + applied: {FakeAB.writes}")
    TG.messagebox.askyesno = lambda title, msg, **k: (asked_ab.append(msg), False)[1]
    FakeAB.writes.clear()
    g._export_to_slot(pm.load("P1"), 4, "leer")
    check(FakeAB.writes == [], "'no' writes nothing")
    from core.tune_history import TuneRun
    g._on_history_menu(TuneRun("x.log", "", "Rundum", reason="Endtest fehlgeschlagen (TDR)"), 0, 0)
    m2 = posted[-1]
    check(m2.index("end") == 0 and "TDR" in m2.entrycget(0, "label")
          and str(m2.entrycget(0, "state")) == "disabled",
          "a run without a profile: no slots, the reason instead")
    gone = g._slot_menu("GOP_DELETED")
    check(gone.index("end") == 0 and str(gone.entrycget(0, "state")) == "disabled",
          "a deleted profile: says so, no slots")
    g._post, TG.messagebox.askyesno, TG.messagebox.showinfo = real_post, real_ask_ab, real_info

    # renaming a profile
    g._show_view("profiles")
    g._refresh_profiles()
    g.tree.selection_set("GOP_CURVE_BAL_1001_1225")
    asked_names = []

    def answer(old, check_fn):
        asked_names.append((old, check_fn("P1"), check_fn("__x"), check_fn("Rundum gestern")))
        return "Rundum gestern"
    g._ask_name = answer
    g._rename_profile()
    check(asked_names and asked_names[0][0] == "GOP_CURVE_BAL_1001_1225" and asked_names[0][1]
          and asked_names[0][2] and asked_names[0][3] == "",
          "rename dialog starts from the old name; an existing / reserved name is refused in the dialog")
    check(g.tree.exists("Rundum gestern") and not g.tree.exists("GOP_CURVE_BAL_1001_1225")
          and g.tree.selection() == ("Rundum gestern",), "renamed in the list, still selected")
    check(g.history._runs[rows[0]].profile_name == "GOP_CURVE_BAL_1001_1225"
          and pm.load("GOP_CURVE_BAL_1001_1225").name == "Rundum gestern",
          "the history's run still finds its (renamed) profile")
    btns = []

    def find(wd):
        for c in wd.winfo_children():
            if isinstance(c, TG.ctk.CTkButton):
                btns.append(c)
            find(c)
    find(g._views["profiles"])
    dele = [b for b in btns if b.cget("text") in ("Löschen", "Delete")]
    tray = [b for b in btns if b.cget("text") in ("Als Tray-Standard", "Set as tray default")]
    check(dele and tray and dele[0].cget("fg_color") == tray[0].cget("fg_color") != "transparent"
          and any(b.cget("text") in ("Umbenennen …", "Rename …") for b in btns),
          "'Löschen' has a frame like 'Als Tray-Standard' (was a borderless ghost button); 'Umbenennen …' is there")
    # round 17: after a tune, name its profile ("so you don't forget which is which")
    from datetime import datetime as _dt
    fresh = TuneProfile(name="GOP_CURVE_BAL_1009_0905", core_offset_mhz=119, curve_points=[[1050, 2879]],
                        created_at=_dt(2026, 10, 9, 9, 5).isoformat())
    pm.save(fresh)
    g.tuner.best_profile = fresh
    offered = []

    class _CR2:
        renamed = []
        def rename_last_applied(self, o, n): _CR2.renamed.append((o, n)); return True
    real_cr2, g.tuner.cr = g.tuner.cr, _CR2()
    g._ask_tune_name = lambda old, sug, chk: (offered.append((old, sug, chk(sug), chk("P1"))), sug)[1]
    g._offer_tune_name()
    check(offered and offered[0][:3] == ("GOP_CURVE_BAL_1009_0905", TG.tr("Rundum Ausgewogen", "All-round Balanced") + " 09.10.", "")
          and offered[0][3] and pm.load(offered[0][1]) is not None
          and pm.load("GOP_CURVE_BAL_1009_0905").name == offered[0][1]
          and _CR2.renamed == [("GOP_CURVE_BAL_1009_0905", offered[0][1])],
          f"after a tune: 'how should it be called?' with a readable suggestion; renamed, the history and "
          f"the start-up record follow: {offered[:1]}")
    g._offer_tune_name()
    check(len(offered) == 1, "asked once per profile")
    fresh2 = TuneProfile(name="GOP_CURVE_BAL_1009_1200", core_offset_mhz=100, created_at=_dt(2026, 10, 9, 12).isoformat())
    pm.save(fresh2)
    g.tuner.best_profile = fresh2
    g._ask_tune_name = lambda old, sug, chk: (offered.append((old, sug)), None)[1]      # Cancel
    g._offer_tune_name()
    check(offered[-1] == ("GOP_CURVE_BAL_1009_1200", offered[0][1] + " (2)")
          and pm.load("GOP_CURVE_BAL_1009_1200").name == "GOP_CURVE_BAL_1009_1200",
          "a taken suggestion gets '(2)'; Cancel keeps the automatic name")
    q = TuneProfile(name="GOP_OC+UV_1009_1300", created_at=_dt(2026, 10, 9, 13).isoformat())
    check(g._suggest_tune_name(q) == TG.tr("Schnell", "Quick") + " 09.10.", "Quick mode: 'Schnell 09.10.'")
    g.tuner.best_profile = None
    g._offer_tune_name()
    check(len(offered) == 2, "no saved profile (failed / aborted tune): no question")
    g.tuner.cr = real_cr2
    # a typed value outside the range is used only clamped (slot 1 = the own Afterburner slot)
    g.v_ab_slot.set(1)
    g.v_step_dur.set(5)
    g._clamp_fields()
    check(g.v_ab_slot.get() == 2 and g.v_step_dur.get() >= 10,
          f"typed slot 1 -> 2 before a tune starts (the field said 2–5): {g.v_ab_slot.get()}")
    # round 16: "make safer" + what the app applied is recorded (start-up profile, GPU watchdog)
    class _CR:
        saved = []
        def save_last_applied(self, d): _CR.saved.append(d["name"])
    real_cr, g.tuner.cr = g.tuner.cr, _CR()
    posted2 = []
    g._post = lambda menu, x, y: posted2.append(menu)
    g.tree.selection_set("Rundum gestern")
    g._derate_profile()
    sp = pm.load("Rundum gestern_sicher")
    check(sp is not None and g.tree.selection() == ("Rundum gestern_sicher",) and posted2
          and sp.mem_offset_mhz == pm.load("Rundum gestern").mem_offset_mhz - 200,
          "'Entschärfen': a safer copy, selected, the slot menu opens to apply it")
    TG.messagebox.askyesno = lambda *a, **k: True
    TG.messagebox.showinfo = lambda *a, **k: None
    asked3 = []
    real_ync = TG.messagebox.askyesnocancel
    TG.messagebox.askyesnocancel = lambda title, msg, **k: (asked3.append(msg), None)[1]
    FakeAB.writes.clear()
    g._export_to_slot(pm.load("Rundum gestern"), 4, "leer")
    check(asked3 and "Rundum gestern_sicher" in asked3[-1] and FakeAB.writes == [],
          "the original that has a safer copy: asked first (Cancel = nothing written)")
    TG.messagebox.askyesnocancel = lambda title, msg, **k: True
    g._export_to_slot(pm.load("Rundum gestern"), 4, "leer")
    t_end = time.time() + 5
    while not FakeAB.writes and time.time() < t_end:
        w.update(); time.sleep(0.02)
    check(FakeAB.writes == [(4, "Rundum gestern_sicher")], f"'Yes': the safer copy goes into the slot: {FakeAB.writes}")
    TG.messagebox.askyesnocancel = real_ync
    _CR.saved.clear()
    g._export_to_slot(sp, 4, "leer")
    t_end = time.time() + 5
    while not _CR.saved and time.time() < t_end:
        w.update(); time.sleep(0.02)
    check(_CR.saved == ["Rundum gestern_sicher"],
          "applied via the slot menu -> recorded (the app put the OLD profile back at its next start)")
    g.tuner.cr, g._post = real_cr, real_post
    TG.messagebox.askyesno, TG.messagebox.showinfo = real_ask_ab, real_info
    from ui.components import TextDialog
    dlg = TextDialog(w, "Profil umbenennen", "Neuer Name:", initial="Alt",
                     check=lambda t: "gibt es schon" if t == "P1" else "")
    t_end = time.time() + 0.3
    while time.time() < t_end:
        w.update(); time.sleep(0.02)
    check(dlg._var.get() == "Alt", "text dialog: pre-filled with the old name")
    dlg._var.set("P1"); dlg._ok()
    check(dlg.winfo_exists() and "gibt es schon" in dlg.lbl_err.cget("text") and dlg.result is None,
          "a taken name: the dialog stays open and says why")
    dlg._var.set("  Neu  "); dlg._ok()
    w.update()
    check(dlg.result == "Neu" and not dlg.winfo_exists(), "a good name: trimmed, dialog closed")
    g._show_view("history")
    import ui.tune_history_view as THV
    asked = []
    real_ask = THV.messagebox.askyesno
    THV.messagebox.askyesno = lambda title, msg, **k: (asked.append(msg), False)[1]
    g.history.tree.selection_set(rows[0]); g.history._on_select()
    check(str(g.history.btn_delete.cget("state")) == "normal", "a selected run can be deleted")
    g.history.delete_selected()
    check(asked and "01.10.2026" in asked[-1] and os.path.exists(os.path.join(tmp, "tune_20261001_114809.log")),
          "delete asks first ('no' keeps the run)")
    THV.messagebox.askyesno = lambda title, msg, **k: (asked.append(msg), True)[1]
    g.history.delete_all()
    check(not os.path.exists(os.path.join(tmp, "tune_20261001_114809.log"))
          and g.history.tree.get_children() and "1 " in g.history.lbl_status.cget("text"),
          f"delete all: gone, the view says so ({g.history.lbl_status.cget('text')!r})")
    THV.messagebox.askyesno = real_ask
    g._show_view("auto")
    from ui.components import HelpTip
    def tips(x):
        out = []
        for c in x.winfo_children():
            if isinstance(c, HelpTip): out.append(c)
            out += tips(c)
        return out
    tip = tips(g.params_card)[0]
    tip.show()
    w.update()
    pop = tip._tip
    texts = [c.cget("text") for c in pop.winfo_children()[0].winfo_children()] if pop else []
    check(pop is not None and pop.winfo_ismapped() and texts == [tip.text] and pop.overrideredirect(),
          "'?': a small window with the explanation opens")
    tip.hide()
    w.update()
    check(tip._tip is None and not pop.winfo_exists(), "... and closes again")
    check("games" not in w._page_factories and not any(k == "games" for k, *_x in mw.TAB_DEFS),
          "the games page is gone")

# ── BIOS, compare, startup, diagnose ──────────────────────────────────────────
@step(1500)
def s_bios():
    print("BIOS / compare / startup / diagnose")
    b = w._tab_frames["bios"]
    names = list(b.profile_combo.cget("values"))
    check(len(names) == 16 and "7000X3D" in names[0] and ("erkannt" in names[0] or "detected" in names[0])
          and b._profile.id == "am5_zen4_x3d", f"every platform listed, the detected one first: {names[0]!r}")
    check(b.vendor_var.get().startswith("ASUS") and b._vendor == "asus", "board maker detected: ASUS")
    w.update()
    def texts():
        out = []
        def walk(x):
            for c in x.winfo_children():
                try: out.append(str(c.cget("text")))
                except tk.TclError: pass
                walk(c)
        walk(b._inner)
        return out
    cards = lambda: sum(len(g._items) for g in b._inner.winfo_children() if hasattr(g, "_items"))
    check(any(x.startswith("📍 ASUS: Ai Tweaker") for x in texts()), "menu paths for ASUS boards")
    n_all = cards()
    b._only_todo.set(True); b._refresh_view()
    n_todo = cards()
    check(n_all > 0 and n_todo == n_all - 2, f"'only what is left' hides EXPO + Secure Boot ({n_all} -> {n_todo})")
    b._only_todo.set(False)
    b.vendor_var.set(next(v for v in b._vendor_labels if b._vendor_labels[v] == "msi")); b._on_vendor_change()
    check(any(x.startswith("📍 MSI: OC") for x in texts()), "board maker switch: MSI paths")
    check("bereits gesetzt" in b.lbl_detect_status.cget("text") or "already set" in b.lbl_detect_status.cget("text"),
          f"detection summary: {b.lbl_detect_status.cget('text')!r}")
    other = next(v for v in b._profile_labels if b._profile_labels[v] == "lga1700_rpl")
    b.profile_var.set(other); b._on_profile_change()
    check("Nicht deine" in b.lbl_profile_info.cget("text") or "Not your" in b.lbl_profile_info.cget("text"),
          "another platform can be opened (marked as not detected)")
    check(any("Microcode 0x12F" in x for x in texts()) and not b.lbl_detect_status.cget("text"),
          "Raptor Lake: microcode warning; no status for a platform that isn't this PC")
    b.profile_var.set(names[0]); b._on_profile_change()

    c = w._tab_frames["compare"]
    # a profile saved after the page was built (it was missing in the comparison)
    # and a non-profile JSON in the folder (it showed up as "Default")
    with open(os.path.join(str(pm.dir), "language.json"), "w", encoding="utf-8") as _f:
        _f.write('{"lang": "de"}')
    pm.save(TuneProfile(name="Neu nach dem Bau", core_offset_mhz=50))
    w._show_tab("compare")
    vals = list(c._combos[0].cget("values"))
    check("Neu nach dem Bau" in vals and "Rundum gestern" in vals and "Default" not in vals,
          f"comparison: refreshed every time it is shown, only real profiles: {vals}")
    c._sel_vars[0].set("P1"); c._on_select(0)
    c._sel_vars[1].set("P2"); c._on_select(1)
    check(len(c.detail_tree.get_children()) == 13,
          "detail table (no GPU row: one PC's own profiles; points and points per watt)")
    check(len(c._metric_rows["perf"]._bars.winfo_children()) == 4,
          "one bar per chosen profile + stock (+ hidden hint)")
    # round 18: performance / efficiency against stock instead of "100/100" for every profile
    import ui.tab_compare as TC
    import ui.tab_gpu as TG
    from core import profile_score as PS
    pm.save(TuneProfile(name="Rundum alt", curve_points=[[925, 2564], [1050, 2879], [1075, 2924]],
                        curve_cap_mv=1050, mem_offset_mhz=500, is_stable=True,
                        notes="[Rundum Ausgewogen] Kurve 7 Punkte | Mem+500MHz | Pwr 100% | FurMark 7295→7446 "
                              "(+2.1 %) | 252→257 W | MaxTemp 65°C | Score 100/100"))
    pm.save(TuneProfile(name="Schnell neu", core_offset_mhz=119, mem_offset_mhz=700, power_limit_pct=96,
                        is_stable=True, bench=PS.bench_record("FurMark", 300, 37522, 266.1, 7295, 252,
                                                               stock_seconds=60)))
    c._refresh_list()
    for k, n in enumerate(("Rundum alt", "Schnell neu", "P1")):
        c._sel_vars[k].set(n); c._on_select(k)
    rows = {str(c.detail_tree.item(r)["values"][0]): [str(v) for v in c.detail_tree.item(r)["values"][1:]]
            for r in c.detail_tree.get_children()}
    perf = rows[TG.tr("Leistung ggü. Standard", "Performance vs stock")]
    eff = rows[TG.tr("Effizienz ggü. Standard", "Efficiency vs stock")]
    clock = rows[TG.tr("Takt", "Clock")]
    nm = TG.tr("nicht gemessen", "not measured")
    # column 0 = stock (point 0), then the profiles
    check(perf[1:4] == [TC._pct(2.1) + " ▲", TC._pct(2.9) + " ▲" + TC.BEST, nm]
          and eff[1:4] == [TC._pct(0.1) + " ≈" + TC.BEST, TC._pct(-2.6) + " ▼", nm],
          f"performance / efficiency vs stock: ▲ better, ▼ worse, ≈ within the noise, the best marked, "
          f"an unmeasured profile says so: {perf[1:4]} {eff[1:4]}")
    check(clock[1:3] == [TG.tr("Kurve: 2879 MHz ab 1050 mV", "Curve: 2879 MHz from 1050 mV"), "+119 MHz"]
          and rows["Name"][1:3] == ["Rundum alt", "Schnell neu"],
          f"clock: a curve's top under its cap, an offset as offset; full names: {clock[1:3]}")
    pts = rows[TG.tr("FurMark-Punkte (je 60 s)", "FurMark points (per 60 s)")]
    ppw = rows[TG.tr("Punkte pro Watt", "Points per watt")]
    watt = rows[TG.tr("Leistungsaufnahme", "Power draw")]
    std = TG.tr("Standard", "stock")
    check(rows["Name"][0] == TG.tr("Standard (ab Werk)", "Stock (as it comes)") and perf[0] == TC.BASE
          and eff[0] == TC.BASE and pts[0] == "7295" and watt[0] == "252 W"
          and rows[TG.tr("Speicher", "Memory")][0] == "+0 MHz",
          f"stock is a column of its own: 0 %, its points and watts (mean of the stock runs): "
          f"{rows['Name'][0]}, {pts[0]}, {watt[0]}")
    check(pts[1:3] == [f"7446 ({std} 7295)", f"7504 ({std} 7295)"] and ppw[1] == f"{TC._dec(28.97)} ({std} {TC._dec(28.95)})",
          f"points per 60 s (a 5-min run reads the same) and points per watt, each with its own stock run: "
          f"{pts[1:3]} {ppw[1]}")
    check(c._metric_rows["points"].shown == ["7295", "7446", "7504", nm],
          f"round 26: the FurMark points themselves — the profiles against each other: "
          f"{c._metric_rows['points'].shown}")
    check(c._metric_rows["perf"].shown == [TC.BASE, TC._pct(2.1) + " ▲", TC._pct(2.9) + " ▲", nm]
          and c._metric_rows["watt"].shown[:3] == ["252 W", "257 W", "266 W"]
          and c._metric_rows["mem"].shown[0] == "+0",
          f"bars: stock first: {c._metric_rows['perf'].shown}, {c._metric_rows['watt'].shown}")
    # round 24: the V/F curves (stock as the arc, every chosen profile in its colour)
    cc = c.curve_chart
    c.update()
    cc._draw()
    lines = cc.find_withtag("line")
    check(cc.find_withtag("stock") and len(lines) == 3 and len(cc.find_withtag("dot")) == 3
          and cc.itemcget(cc.find_withtag("line0")[0], "fill") == TC.COMPARE_COLORS[0]
          and cc.find_withtag("band") and not cc.find_withtag("empty"),
          f"curve chart: stock, 3 profile lines in their colours, the measured points of the curve "
          f"profile, the range under load shaded ({len(lines)} lines)")
    check([cc.itemcget(cc.find_withtag(f"line{k}")[0], "dash") for k in range(3)][0] == ""
          and all(cc.itemcget(cc.find_withtag(f"line{k}")[0], "dash") for k in (1, 2))
          and c.legend_items == [TG.tr("Standard", "Stock")] + [f"{TG.tr('Profil', 'Profile')} {k}" for k in (1, 2, 3)],
          f"every profile its own line style (lines on each other stay visible), a legend: {c.legend_items}")
    cc.show_at(1060)
    ht = cc.hover_text
    check(ht.startswith("1060 mV") and TG.tr("Standard 2819", "Stock 2819") in ht
          and f"{TG.tr('Profil', 'Profile')} 1 2879" in ht and f"{TG.tr('Profil', 'Profile')} 2 2938" in ht,
          f"pointing at 1060 mV: stock, the curve profile flat from 1050 (2879), Quick +119 (2938): {ht}")
    qcap = TuneProfile(name="Schnell gedeckelt", core_offset_mhz=134, curve_points=[[1075, 2909]],
                       curve_cap_mv=1075, notes="[OC+UV] Core+134MHz | Pwr 96% | flach ab 1075 mV")
    check(TC.describe_clock(qcap) == TG.tr("+134 MHz, flach ab 1075 mV", "+134 MHz, flat from 1075 mV"),
          f"a Quick profile with its flat top reads as its offset: {TC.describe_clock(qcap)}")
    real_bc = FakeAB.base_curve
    FakeAB.base_curve = lambda self, slot=2: (None, "kein Profil")
    c._refresh_list()
    c.update()
    cc._draw()
    check(cc.find_withtag("empty") and not cc.find_withtag("line")
          and "kein Profil" in cc.itemcget(cc.find_withtag("empty")[0], "text"),
          "no Afterburner curve: the chart says why instead of drawing")
    FakeAB.base_curve = real_bc
    c._refresh_list()

    s = w._tab_frames["startup"]
    check(len(s.tree.get_children()) == 3, "startup entries listed")
    s._filter_var.set("disabled"); s._apply_filter()
    check([s.tree.set(i, "name") for i in s.tree.get_children()] == ["OldTool"], "filter 'Deaktiviert'")
    s._filter_var.set("all"); s.ent_search.insert(0, "disc"); s._apply_filter()
    check([s.tree.set(i, "name") for i in s.tree.get_children()] == ["Discord"], "search")

    d = w._tab_frames["diagnose"]
    d._show_view("health")
    check(set(d._views) == {"health", "remn"} and d._views["health"].winfo_manager(),
          "diagnose sub-pages (the FPS capture is gone)")

@step(300)
def s_pages():
    print("page stack")
    keys = [k for k, *_x in mw.TAB_DEFS]
    check(all(k in w._tab_frames for k in keys), f"every page built in the background: {sorted(w._tab_frames)}")
    check([k for k in keys if w._tab_frames[k].winfo_manager() == "place"] == [w._active_tab],
          "round 19: only the visible page is mapped (a maximize re-laid out all of them)")
    for k in ("bios", "settings", "dashboard"):
        w._show_tab(k)
        w.update()
        top = [c for c in w._content.winfo_children() if c.winfo_manager() == "place"][-1]
        check(top is w._tab_frames[k], f"{k}: raised on top of the stack")
    drawn = []
    real = w._tab_btns["gpu"].configure
    for kk, btn in w._tab_btns.items():
        btn.configure = (lambda kk=kk, f=btn.configure: lambda **kw: (drawn.append(kk), f(**kw)))()
    w._show_tab("gpu")
    for kk, btn in w._tab_btns.items():
        del btn.configure
    check(sorted(drawn) == ["dashboard", "gpu"], f"a switch redraws only the two changed buttons: {drawn}")

@step(300)
def s_close():
    check(not ERRORS, f"no Tk callback errors ({len(ERRORS)})")
    for e in ERRORS[:5]:
        print(e)
    w.destroy()

def run(i=0):
    if i >= len(STEPS):
        return
    ms, fn = STEPS[i]
    def go():
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            check(False, f"{fn.__name__} raised {e!r}")
        if fn is s_close:
            return
        run(i + 1)
    w.after(ms, go)

run()
w.after(90000, w.destroy)
w.mainloop()
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
