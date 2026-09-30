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
    def find_gpu_profile(self): return r"C:\fake\VEN_10DE.cfg", ""
    def write_and_apply(self, slot, p): return True, ""
    def reset_to_stock(self, slot=2): return True, ""
class FakeSL:
    auto, calls, fail = False, [], False
    def is_autostart_enabled(self): return self.auto
    def set_autostart(self, on):
        self.calls.append(on)
        return not self.fail
    def load_startup_profile(self): return True, "Profil 'Test' geladen"
from core.game_monitor import GameEntry
class FakeGM:
    topology, is_running, active_game = None, False, None
    def __init__(self):
        self.games = [GameEntry("Game1.exe", "Game One", ""), GameEntry("Game2.exe", "Game Two", "P1")]
    def on_game_start(self, cb): pass
    def on_game_stop(self, cb): pass
    def on_cpu_pin(self, cb): pass
    def get_games(self): return list(self.games)
    def cpu_pin_targets(self): return []
    def add_game(self, exe, name, prof): self.games.append(GameEntry(exe, name, prof))
    def update_game(self, exe, prof, enabled=True, restore="__tray_default__", cpu_target=None):
        for g in self.games:
            if g.exe == exe:
                g.profile_name, g.enabled = prof, enabled
    def remove_game(self, exe): self.games = [g for g in self.games if g.exe != exe]
    def set_cpu_target(self, exe, t): pass

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
BiosDetector.detect_all = lambda self: {"expo_xmp": DetectResult("expo_xmp", True, "6000 MT/s"),
                                        "hags": DetectResult("hags", False, "", note="aus"),
                                        "pbo": DetectResult("pbo", False, "", note="unbekannt")}
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
pm = ProfileManager(os.path.join(tmp, "profiles"))
pm.save(TuneProfile(name="P1", core_offset_mhz=120, mem_offset_mhz=800, power_limit_pct=90, stability_score=95))
pm.save(TuneProfile(name="P2", core_offset_mhz=90, mem_offset_mhz=500, power_limit_pct=80, stability_score=88))
mon, ab, sl, gm = FakeMon(), FakeAB(), FakeSL(), FakeGM()
tuner = AutoTuner(mon, ab, pm, TunerConfig(), log_dir=tmp)

import customtkinter as ctk
import ui.main_window as mw
t0 = time.perf_counter()
w = mw.GameOptimizerWindow(hw, mon, ab, pm, tuner, runner, startup_loader=sl, game_monitor=gm)
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
    check(len(w._tab_frames) == 11 and not ERRORS, f"all 11 pages open without errors ({len(ERRORS)})")

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
    check(all(wdg.winfo_manager() for k, wdg, t in rows), "empty search -> all rows back")
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
    g._select_mode("uv_only")
    desc = g.lbl_mode_desc.cget("text")
    check(g.v_mode.get() == "uv_only" and g.v_core_max.get() == 0 and not g.v_mem_stage.get()
          and ("Power-Limit" in desc or "power limit" in desc),
          "mode 'Undervolt' sets the parameters and explains itself")
    g._select_mode("oc_uv")
    g.prog_var.set(50)
    check(abs(g.prog_bar.get() - 0.5) < 1e-6, "progress bar follows the tuner progress")
    w.update()
    lg = g.log.winfo_height()
    check(lg > 60, f"the tuner log is visible without enlarging the window ({lg} px high)")

# ── stress test ───────────────────────────────────────────────────────────────
PROCS = []
class FakeProc:
    def __init__(self, n): self.n = n; self.returncode = None
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
                                      "--max-time", "90"], f"FurMark 2 started with its own switches: {PROCS[-1][1:] if PROCS else None}")
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

# ── settings ──────────────────────────────────────────────────────────────────
@step(100)
def s_settings():
    print("settings")
    st = w._tab_frames["settings"]
    check(str(st.sw_autostart.cget("state")) == "normal" and st.v_autostart.get() is False,
          "autostart state read in the background")
    st.sw_load_startup.toggle()
    check(app_settings.get("load_startup_profile") is False, "'load startup profile' is saved (was a dead checkbox)")
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

# ── games ─────────────────────────────────────────────────────────────────────
@step(100)
def s_games():
    print("games")
    import ui.tab_games as tg
    gt = w._tab_frames["games"]
    check(set(gt.game_tree.get_children()) == {"Game1.exe", "Game2.exe"}, "games listed")
    class AutoChoice(tg.ChoiceDialog):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.attributes("-alpha", 0.0)            # never visible on the desktop
            self.after(250, lambda: (self._var.set("P2"), self._ok()))
    tg.ChoiceDialog, real = AutoChoice, tg.ChoiceDialog
    gt.game_tree.selection_set("Game1.exe")
    gt._assign_profile()                      # blocks in wait_window until AutoChoice answers
    tg.ChoiceDialog = real
    check(gm.games[0].profile_name == "P2" and gt.game_tree.set("Game1.exe", "profile") == "P2",
          "profile picked in the dialog is assigned")
    class Inputs:
        answers = ["NewGame", ""]
        def __init__(self, **k): pass
        def get_input(self): return Inputs.answers.pop(0)
    real_in = ctk.CTkInputDialog
    ctk.CTkInputDialog = Inputs
    gt._add_game()
    ctk.CTkInputDialog = real_in
    check(gm.games[-1].exe == "NewGame.exe" and gm.games[-1].display_name == "NewGame",
          "add game: '.exe' appended, empty name -> file name")
    gt._show_view("history")
    check(gt._views["history"].winfo_manager() and gt.hist_tree.get_children(), "tune history view")

# ── BIOS, compare, startup, diagnose ──────────────────────────────────────────
@step(1500)
def s_bios():
    print("BIOS / compare / startup / diagnose")
    b = w._tab_frames["bios"]
    names = b.profile_combo.cget("values")
    check(len(names) >= 1 and b.profile_var.get() == names[0], f"BIOS profiles for the board: {names}")
    pick = next(p.name for p in b._profiles if any(s.detect_key == "expo_xmp" for s in p.settings))
    b.profile_var.set(pick); b._on_profile_change()
    cards = lambda: sum(len(g._items) for g in b._inner.winfo_children() if hasattr(g, "_items"))
    n_all = cards()
    b._only_todo.set(True); b._refresh_view()
    n_todo = cards()
    check(n_all > 0 and n_todo < n_all, f"'only what is left' hides active settings ({n_all} -> {n_todo})")
    b._only_todo.set(False); b._refresh_view()
    check("bereits aktiv" in b.lbl_detect_status.cget("text") or "already active" in b.lbl_detect_status.cget("text"),
          "detection summary")

    c = w._tab_frames["compare"]
    c._sel_vars[0].set("P1"); c._on_select(0)
    c._sel_vars[1].set("P2"); c._on_select(1)
    check(len(c.detail_tree.get_children()) == 9, "detail table")
    check(len(c._metric_rows["core"]._bars.winfo_children()) == 3, "one bar per chosen profile (+ hidden hint)")

    s = w._tab_frames["startup"]
    check(len(s.tree.get_children()) == 3, "startup entries listed")
    s._filter_var.set("disabled"); s._apply_filter()
    check([s.tree.set(i, "name") for i in s.tree.get_children()] == ["OldTool"], "filter 'Deaktiviert'")
    s._filter_var.set("all"); s.ent_search.insert(0, "disc"); s._apply_filter()
    check([s.tree.set(i, "name") for i in s.tree.get_children()] == ["Discord"], "search")

    d = w._tab_frames["diagnose"]
    d._show_view("health")
    check(d._views["health"].winfo_manager() and not d._views["fps"].winfo_manager(), "diagnose sub-pages")

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
