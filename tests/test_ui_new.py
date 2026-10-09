"""UI test under a REAL Tk mainloop: Settings (scroll + Deep Clean), Services
Manager window (fake data, nothing changed), Dashboard score + monitor advisor
(fake score), main window drift dialog (fake runner, fake answers)."""
import os, sys, time, tempfile, threading, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import tempfile as _tf                     # never the app's own settings (run on their own too)
from pathlib import Path as _P
from core import app_settings as _AS
_AS.SETTINGS_FILE = _P(_tf.mkdtemp(prefix="gop_set_")) / "settings.json"
import tkinter as tk
from tkinter import messagebox

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

ANSWERS = []          # queued answers for ask* dialogs
ASKED = []
def fake_ask(kind):
    def f(title, msg, **k):
        ASKED.append((kind, title, msg))
        return ANSWERS.pop(0) if ANSWERS else False
    return f
messagebox.askyesno = fake_ask("yesno")
messagebox.askyesnocancel = fake_ask("yesnocancel")
BOXES = []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, (lambda n: lambda *a, **k: BOXES.append((n,) + a))(n))

# ── fakes ─────────────────────────────────────────────────────────────────────
import core.system_cleaner as sc
CLEANED = []
class T:  # target stand-in
    def __init__(self, label, key="", n=3, b=3000):
        self.label, self.key, self.file_count, self.bytes, self.exists, self.path = label, key, n, b, True, "x"
sc.get_targets = lambda: [T("Benutzer-Temp")]
sc.get_deep_targets = lambda keys: [T("Chrome-Cache (Default)", "browser")] if "browser" in keys else []
sc.scan = lambda ts: ts
def fake_clean(ts):
    CLEANED.append([t.label for t in ts])
    r = sc.CleanResult(); r.files_deleted, r.bytes_freed, r.errors = 6, 6000, 1
    return r
sc.clean = fake_clean
BIN = []
sc.recycle_bin_info = lambda: (4, 4 * 1024 * 1024)
sc.empty_recycle_bin = lambda: (BIN.append(1), (True, 4 * 1024 * 1024))[1]

class FakeMAHM:
    available = False
    def read(self):
        class D: gpu_voltage_mv = 0
        return D()
class FakeNVML:
    available = True
class FakeMon:
    mahm, nvml = FakeMAHM(), FakeNVML()
class FakeAB:
    available, exe = False, None
    def check_ab_setup(self): return {}
class FakeSL:
    def is_autostart_enabled(self): return False

import core.services as svc
svc.is_admin = lambda: False
S = svc.ServiceInfo
svc.list_services = lambda: [
    S("SysMain", "SysMain", "Leistung", True, "d", "Beendet", False, 4, False, {"start": 2, "delayed": False}),
    S("Spooler", "Druckwarteschlange", "System", False, "Druck", "Läuft", True, 2, False, None),
    S("WSearch", "Windows Search", "Leistung", True, "Suche", "Läuft", True, 2, True, None)]

import core.optimization_score as osc
class R:
    active, checkable, unknown, score = 65, 83, 0, 78
osc.compute_score = lambda hw, verifier=None: (time.sleep(0.3), R())[1]

root = tk.Tk()
root.geometry("1000x700")
root.attributes("-alpha", 0.0)       # mapped (geometry works) but invisible on the desktop

from ui.tab_settings import SettingsTab
st = SettingsTab(root, FakeAB(), FakeMon(), FakeSL())
st.pack(fill="both", expand=True)

STEPS = []
def step(delay):
    def deco(fn):
        STEPS.append((delay, fn)); return fn
    return deco

@step(300)
def s_settings():
    print("settings: scrollable + Deep Clean")
    root.update_idletasks()
    check(st._canvas.yview() != (0.0, 1.0), f"page taller than the window -> scrollable {st._canvas.yview()}")
    check(set(st._deep_vars) == set(sc.DEEP_GROUPS) and not any(v.get() for v in st._deep_vars.values()),
          "one checkbox per Deep-Clean group, all OFF by default")
    y0 = st._canvas.yview()[0]
    ev = type("E", (), {"delta": -120})()
    st._on_wheel(ev)
    check(st._canvas.yview()[0] > y0, "mouse wheel scrolls")
    st._deep_vars["browser"].set(True)
    st._deep_vars["recyclebin"].set(True)
    targets, with_bin = st._cleaner_targets()
    check([t.label for t in targets] == ["Benutzer-Temp", "Chrome-Cache (Default)"] and with_bin,
          "targets = standard + chosen deep groups; recycle bin flagged separately")
    st._cleaner_scan()

@step(600)
def s_scan():
    txt = st.lbl_cleaner.cget("text")
    check("Gefunden: 10 Dateien" in txt and "Papierkorb: 4 Dateien" in txt and "Browser-Caches" in txt,
          f"scan summary per group incl. recycle bin: {txt!r}")
    print("clean: user declines the Recycle Bin")
    ANSWERS[:] = [True, False]         # clean yes, recycle bin no
    st._cleaner_clean()
    check(len(ASKED) == 2 and "Papierkorb" in ASKED[1][1] and "Deep Clean: Browser-Caches" in ASKED[0][2],
          "two questions: clean (lists deep groups) + extra Recycle-Bin confirmation")

@step(600)
def s_clean():
    check(CLEANED[-1] == ["Benutzer-Temp", "Chrome-Cache (Default)"] and not BIN, "cleaned, Recycle Bin NOT emptied")
    txt = st.lbl_cleaner.cget("text")
    check("6 Dateien gelöscht" in txt and "1 in Benutzung übersprungen" in txt and "Papierkorb" not in txt,
          f"result: {txt!r}")
    ANSWERS[:] = [True, True]
    st._cleaner_clean()

@step(600)
def s_clean2():
    check(BIN == [1] and "Papierkorb geleert" in st.lbl_cleaner.cget("text"), "second run: Recycle Bin emptied")
    check("9.9 KB" in st.lbl_cleaner.cget("text") or "4.0 MB" in st.lbl_cleaner.cget("text"),
          f"freed bytes include the bin: {st.lbl_cleaner.cget('text')!r}")
    ANSWERS[:] = [False]
    n = len(CLEANED)
    st._cleaner_clean()
    check(len(CLEANED) == n, "answer 'No' -> nothing cleaned")

    print("services manager window")
    from ui.services_manager import ServicesManagerPage
    global sw
    sw = ServicesManagerPage(root)            # a page in the main window now
    st.pack_forget(); sw.pack(fill="both", expand=True)

@step(800)
def s_svc():
    rows = sw.tree.get_children()
    check(list(rows) == ["Spooler", "WSearch", "SysMain"] or set(rows) == {"Spooler", "WSearch", "SysMain"},
          f"rows: {rows}")
    check(sw.tree.item("SysMain", "tags") == ("disabled",) and sw.tree.item("Spooler", "tags") == ("caution",),
          "tags: disabled grey, unsafe amber")
    check(str(sw.btn_disable.cget("state")) == "disabled", "not admin -> action buttons disabled")
    check("3 Dienste gefunden · 1 deaktiviert" in sw.lbl_count.cget("text"), sw.lbl_count.cget("text"))
    sw.tree.selection_set(["SysMain"]); sw._on_select()
    check("Aktivieren setzt: Automatisch (gemerkt)" in sw.lbl_detail.cget("text"), sw.lbl_detail.cget("text"))
    # risky disable asks first (admin simulated by calling the handler directly)
    global called
    called = []
    svc.disable = lambda names: (called.append(names), {n: (True, "") for n in names})[1]
    sw.tree.selection_set(["Spooler", "WSearch"])
    ANSWERS[:] = [False]
    sw._disable()
    check(not called and "Vorsicht" in ASKED[-1][1], "unsafe service -> warning; 'No' -> nothing done")
    ANSWERS[:] = [True]
    sw._disable()

@step(800)
def s_svc2():
    check(called and sorted(called[-1]) == ["Spooler", "WSearch"], f"'Yes' -> disable({called[-1] if called else None})")
    check("Deaktivieren: 2 von 2 erfolgreich" in sw.lbl_status.cget("text"), sw.lbl_status.cget("text"))
    sw.destroy()

    print("dashboard: score + monitor advisor")
    from core.hardware import HardwareInfo
    from ui.tab_dashboard import DashboardTab
    class Mon2:
        def read(self):
            raise RuntimeError("no gpu in test")
    global dash
    hw = HardwareInfo()
    import core.display_info as di
    global DISP_CALLS
    DISP_CALLS = []
    _real_displays = di.displays
    di.displays = lambda: (DISP_CALLS.append(1), _real_displays())[1]
    dash = DashboardTab(root, hw, Mon2())
    st.pack_forget(); dash.pack(fill="both", expand=True)
    check(len(dash._mon_rows.winfo_children()) >= 1 and len(DISP_CALLS) == 1,
          "monitor rows shown IMMEDIATELY (not only after the score check)")

@step(2500)
def s_dash():
    txt = dash.lbl_score.cget("text")
    check(txt.startswith("78 %") and "65/83" in txt, f"score shown: {txt!r}")
    mons = [w for w in dash._mon_rows.winfo_children()]
    check(len(mons) >= 1, f"{len(mons)} monitor row(s)")
    check(len(DISP_CALLS) == 1, f"the automatic score check does not re-read monitors ({len(DISP_CALLS)})")
    dash._refresh_score()
    check(len(DISP_CALLS) == 2 and len(dash._mon_rows.winfo_children()) == len(mons),
          "'⟳ Neu prüfen' re-reads the refresh rates (rows rebuilt, not duplicated)")
    dash._running = False

    print("main window: drift dialog")
    import ui.main_window as mw
    class Runner:
        def __init__(self):
            self._applied = {"disable_telemetry": "x", "disable_bing_search": "y"}
            self.saved = 0; self.applied = []; self.backups = []
        def _save_state(self): self.saved += 1
        def backup_registry(self, label): self.backups.append(label)
        def apply(self, t):
            self.applied.append(t.id); return (t.id != "disable_bing_search", "Zugriff verweigert")
    class Opt:
        _vars = {"disable_telemetry": tk.BooleanVar(value=True)}
    global fake, R1
    R1 = Runner()
    status = []
    fake = tk.Frame(root)          # a real widget: the dialog needs a Tk parent
    fake.runner, fake._tab_frames = R1, {"optimizer": Opt()}
    fake.set_status = status.append
    fake._handle_drift = lambda re, dr: mw.GameOptimizerWindow._handle_drift(fake, re, dr)
    mw.GameOptimizerWindow._ask_drift(fake, ["disable_telemetry", "disable_bing_search", "w11_taskbar_left"])
    dlg = fake._drift_dialog
    dlg.attributes("-alpha", 0.0)
    check(list(dlg.vars) == ["disable_telemetry", "disable_bing_search", "w11_taskbar_left"]
          and all(v.get() for v in dlg.vars.values()), "one tick box per tweak, all ticked")
    dlg.destroy()
    check(R1._applied.keys() == {"disable_telemetry", "disable_bing_search"} and not R1.applied,
          "'Später' -> nothing changed (asks again next start)")
    global dlg2
    R1._applied["w11_taskbar_left"] = "z"
    mw.GameOptimizerWindow._ask_drift(fake, ["disable_telemetry", "disable_bing_search", "w11_taskbar_left"])
    dlg2 = fake._drift_dialog
    dlg2.attributes("-alpha", 0.0)
    dlg2.vars["w11_taskbar_left"].set(False)            # the user keeps the centred taskbar
    Opt._vars["w11_taskbar_left"] = tk.BooleanVar(value=True)
    dlg2.submit()
    # saved >= 1: the re-apply thread saves again (failed re-apply = not applied)
    check("w11_taskbar_left" not in R1._applied and not Opt._vars["w11_taskbar_left"].get() and R1.saved >= 1,
          "unticked -> marked as not applied, state saved, optimizer box cleared")

@step(1500)
def s_drift2():
    check(R1.backups == ["PreDriftReapply"], "ticked -> registry backup first")
    check(R1.applied == ["disable_telemetry", "disable_bing_search"], "then exactly the ticked ones re-applied")
    check(BOXES and BOXES[-1][0] == "showwarning" and "1 von 2" in BOXES[-1][2] and "Zugriff verweigert" in BOXES[-1][2],
          f"summary lists the failure: {BOXES[-1][2][:80] if BOXES else None!r}")
    check("disable_bing_search" not in R1._applied and "disable_telemetry" in R1._applied and R1.saved >= 2,
          "a failed re-apply is marked 'not applied' (no question at every start)")
    check("keine erneute Nachfrage" in BOXES[-1][2], "the summary says so")

def run(i=0):
    if i >= len(STEPS):
        root.after(200, root.quit)
        return
    delay, fn = STEPS[i]
    def go():
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(False, f"step {fn.__name__} raised {e!r}")
        run(i + 1)
    root.after(delay, go)

run()
root.after(30000, root.quit)
root.mainloop()
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
