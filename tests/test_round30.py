"""Round 30 — the timer tweak says what it does; two adapter tweaks (Energy-Efficient
Ethernet, Interrupt Moderation) with the original value kept for the revert; game
profiles (CPU / disk priority per .exe, fullscreen flag per path, the previous state put
back on remove); the read-only interrupt view.

Registry work runs against a scratch key under HKCU\\Software\\GameOptimizerPro-Test
(deleted afterwards) — never the real adapter, IFEO or compatibility keys."""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


if os.name != "nt":
    print("  (not Windows: skipped)")
    sys.exit(2)

import winreg  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gop_r30_")
from pathlib import Path  # noqa: E402
from core import app_settings  # noqa: E402
app_settings.SETTINGS_FILE = Path(TMP) / "settings.json"      # never the app's own file
import core.i18n as I18N  # noqa: E402
I18N._save_lang = lambda lang: None                            # never the app's language file
I18N._current_lang = "de"

from core import game_profiles as GP, interrupts as IR  # noqa: E402
from core.tweak_i18n import TWEAK_DESC_EN, TWEAK_NAME_EN  # noqa: E402
from core.tweak_verifier import VERIFY_MAP  # noqa: E402
from core.tweaks import ALL_TWEAKS, NIC_EEE_KEYWORDS, NIC_IM_KEYWORDS, _nic_ps, get_by_id  # noqa: E402
import core.tweak_presets as TP  # noqa: E402

HKCU = winreg.HKEY_CURRENT_USER
BASE = rf"Software\GameOptimizerPro-Test\r30-{os.getpid()}"


def wipe(path):
    try:
        k = winreg.OpenKey(HKCU, path, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    with k:
        while True:
            try:
                sub = winreg.EnumKey(k, 0)
            except OSError:
                break
            wipe(path + "\\" + sub)
    winreg.DeleteKey(HKCU, path)


def put(path, **values):
    k = winreg.CreateKey(HKCU, path)
    with k:
        for name, v in values.items():
            name = name.replace("STAR_", "*")
            if isinstance(v, int):
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, v)
            else:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, v)


def get(path, name):
    try:
        with winreg.OpenKey(HKCU, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def exists(path):
    try:
        winreg.OpenKey(HKCU, path).Close()
        return True
    except OSError:
        return False


try:
    # ── 1) timer tweak ─────────────────────────────────────────────────────────
    print("timer tweak: honest name, real revert")
    t = get_by_id("timer_resolution")
    check("0.5" not in t.name and "0,5" not in t.name and "keine" in t.desc.lower()
          and "selbst keine Auflösung" in t.desc,
          f"the name promises no 0.5 ms, the text says it sets no resolution itself ({t.name})")
    check("no resolution itself" in TWEAK_DESC_EN["timer_resolution"]
          and TWEAK_NAME_EN["timer_resolution"] == "Let Timer Requests Apply System-wide",
          "English name and text")
    check("reg delete" in t.revert_cmd and "GlobalTimerResolutionRequests" in t.revert_cmd
          and t.requires_reboot, "revert removes the value (Windows default); needs a restart")
    check("GlobalTimerResolutionRequests" in VERIFY_MAP["timer_resolution"], "status check unchanged")

    # ── 2) adapter tweaks: definition ─────────────────────────────────────────
    print("adapter tweaks: definition, presets, status")
    eee, im = get_by_id("disable_eee"), get_by_id("disable_interrupt_moderation")
    check(eee and im and eee.category == im.category == "Network" and eee.group == im.group == "Adapter",
          "two new tweaks in Network → Adapter")
    check(eee.requires_reboot and im.requires_reboot and eee.risk == "safe" and im.risk == "moderate",
          "both need a restart; Interrupt Moderation is 'moderate' (more CPU load)")
    check(all(x in VERIFY_MAP and x in TWEAK_DESC_EN and x in TWEAK_NAME_EN for x in (eee.id, im.id)),
          "status check + English name and text for both")
    check("disable_eee" in TP._MEDIUM_EXTRA and "disable_interrupt_moderation" in TP._HARD_EXTRA
          and "disable_eee" in TP.get_preset("network").tweak_ids
          and "disable_interrupt_moderation" not in TP.get_preset("network").tweak_ids,
          "presets: EEE from 'Mittel' and in 'Network', Interrupt Moderation only in 'Hart'")
    for script in (eee.ps_command, eee.revert_cmd, VERIFY_MAP["disable_eee"]):
        check("Remove-ItemProperty" not in script and "Set-ItemProperty" not in script
              and "Get-ItemProperty" not in script,
              "registry access via .NET only (the cmdlets read '*EEE' as a wildcard)")
        break

    # ── 3) adapter tweaks: the real scripts against a fake class key ──────────
    print("adapter tweaks: apply / verify / revert on a fake adapter list")
    CLS = BASE + r"\Class"
    STORE = BASE + r"\NicOrig"

    def ps(script):
        for a, b in (("[Microsoft.Win32.Registry]::LocalMachine", "[Microsoft.Win32.Registry]::CurrentUser"),
                     ("SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}", CLS),
                     ("SOFTWARE\\GameOptimizerPro\\NicOrig", STORE)):
            script = script.replace(a, b)
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode, (r.stdout or "").strip()

    def adapter(sub, char, iftype, values, params):
        put(rf"{CLS}\{sub}", NetCfgInstanceId="{x}", Characteristics=char, STAR_IfType=iftype, **values)
        for kw, (default, choices) in params.items():
            put(rf"{CLS}\{sub}\Ndi\params\{kw}", default=default)
            put(rf"{CLS}\{sub}\Ndi\params\{kw}\enum", **{c: c for c in choices})

    # 0000 physical Ethernet: *EEE on, Green Ethernet only as the driver default (no value),
    #      a vendor value 'MyEEE' that is not one of our keywords
    adapter("0000", 4, 6, {"STAR_EEE": "1", "STAR_InterruptModeration": "1", "MyEEE": "1"},
            {"*EEE": ("1", ["0", "1"]), "EnableGreenEthernet": ("1", ["0", "1"]),
             "*InterruptModeration": ("1", ["0", "1"]), "MyEEE": ("1", ["0", "1"])})
    adapter("0001", 1, 6, {"STAR_EEE": "1"}, {"*EEE": ("1", ["0", "1"])})              # virtual
    adapter("0002", 4, 71, {"STAR_InterruptModeration": "1"},
            {"*InterruptModeration": ("1", ["0", "1"])})                             # Wi-Fi
    adapter("0003", 4, 6, {"EEELinkAdvertisement": "2"},
            {"EEELinkAdvertisement": ("2", ["1", "2"])})                             # no "0" choice
    put(rf"{CLS}\Properties")                                                        # not an adapter

    E_APPLY, E_REV, E_VER = (_nic_ps(m, "EEE", NIC_EEE_KEYWORDS) for m in ("apply", "revert", "verify"))
    I_APPLY, I_REV, I_VER = (_nic_ps(m, "IM", NIC_IM_KEYWORDS) for m in ("apply", "revert", "verify"))
    check(ps(E_VER) == (0, "0") and ps(I_VER) == (0, "0"), "before: both inactive")
    rc, out = ps(E_APPLY)
    check(rc == 0 and "2 adapter setting" in out, f"EEE apply: two settings of the Ethernet adapter ({out})")
    c0 = CLS + r"\0000"
    check(get(c0, "*EEE") == "0" and get(c0, "EnableGreenEthernet") == "0",
          "*EEE and Green Ethernet (only a driver default before) are 0")
    check(get(c0, "MyEEE") == "1" and get(CLS + r"\0001", "*EEE") == "1"
          and get(CLS + r"\0003", "EEELinkAdvertisement") == "2",
          "untouched: a vendor value outside the list, the virtual adapter, a setting without '0'")
    check(get(STORE, "EEE|0000|*EEE") == "1" and get(STORE, "EEE|0000|EnableGreenEthernet") == "*none*",
          "the values before are kept (incl. 'no value')")
    check(ps(E_VER) == (0, "1"), "verify: active")
    check(ps(E_APPLY)[0] == 0 and get(STORE, "EEE|0000|*EEE") == "1",
          "a second apply keeps the ORIGINAL value, not the 0")
    rc, _o = ps(E_REV)
    check(rc == 0 and get(c0, "*EEE") == "1" and get(c0, "EnableGreenEthernet") is None
          and get(c0, "MyEEE") == "1", "revert: *EEE back to 1, Green Ethernet back to 'no value'")
    check(get(STORE, "EEE|0000|*EEE") is None and ps(E_VER) == (0, "0"), "revert: record gone, inactive")
    rc, out = ps(I_APPLY)
    check(rc == 0 and get(c0, "*InterruptModeration") == "0"
          and get(CLS + r"\0002", "*InterruptModeration") == "1",
          "Interrupt Moderation: the Ethernet adapter only, not Wi-Fi")
    check(ps(I_VER) == (0, "1") and ps(I_REV)[0] == 0 and get(c0, "*InterruptModeration") == "1",
          "Interrupt Moderation: active, then reverted to 1")
    # no record (e.g. the GameOptimizerPro key was removed): back to the driver default
    put(c0, STAR_EEE="0")
    check(ps(E_REV)[0] == 0 and get(c0, "*EEE") == "1", "revert without a record: the driver default")
    wipe(c0)
    rc, out = ps(E_APPLY)
    check(rc == 1 and "no wired adapter" in out, f"no adapter offers it: apply fails (not recorded) ({out})")

    # ── 4) game profiles ───────────────────────────────────────────────────────
    print("game profiles: registry")
    GP.IFEO_ROOT = (HKCU, BASE + r"\IFEO")
    GP.STORE_ROOT = (HKCU, BASE + r"\GameProfiles")
    GP.LAYERS_ROOT = (HKCU, BASE + r"\Layers")
    IFEO, LAY = BASE + r"\IFEO", BASE + r"\Layers"

    def err(path):
        try:
            GP.check_path(path)
        except GP.GameProfileError as e:
            return str(e)
        return ""
    check(err(r"C:\Windows\explorer.exe") and err(r"C:\x\python.exe") and err(r"C:\x\game.txt")
          and not err(r"D:\Games\Shooter\shooter.exe"),
          "system programs / interpreters / non-.exe refused, a game accepted")
    check(GP.is_generic("Launcher.exe") and not GP.is_generic("shooter.exe"), "common names are flagged")
    gpath = r"D:\Games\Shooter\Shooter.exe"
    p = GP.save(gpath)
    check(p.exe == "shooter.exe" and get(IFEO + r"\shooter.exe\PerfOptions", "CpuPriorityClass") == 3
          and get(IFEO + r"\shooter.exe\PerfOptions", "IoPriority") == 3,
          "new profile: CPU priority High (3), I/O priority High (3)")
    check([x.exe for x in GP.list_profiles()] == ["shooter.exe"] and GP.status(p).perf_ok,
          "listed; status: entry ok")
    check(get(LAY, os.path.normpath(gpath)) is None, "fullscreen flag not set unless chosen")
    put(LAY, **{os.path.normpath(gpath): "~ RUNASADMIN"})                  # the user's own flag
    GP.save(gpath, cpu=GP.CPU_ABOVE, io_high=False, fso_off=True)
    check(get(IFEO + r"\shooter.exe\PerfOptions", "CpuPriorityClass") == 6
          and get(IFEO + r"\shooter.exe\PerfOptions", "IoPriority") is None,
          "changed: Above normal (6), I/O priority value removed")
    check(get(LAY, os.path.normpath(gpath)) == "~ RUNASADMIN DISABLEDXMAXIMIZEDWINDOWEDMODE",
          "fullscreen flag added next to the user's own flag")
    check(GP.status(GP.get_profile("shooter.exe")).fso_ok, "status: flag ok")
    newpath = r"E:\Shooter\shooter.exe"
    GP.save(newpath, cpu=GP.CPU_ABOVE, io_high=False, fso_off=True)
    check(get(LAY, os.path.normpath(gpath)) == "~ RUNASADMIN" and get(LAY, newpath) == "~ DISABLEDXMAXIMIZEDWINDOWEDMODE",
          "a new path moves the flag (the old path keeps only the user's flag)")
    check(GP.remove("shooter.exe") and not exists(IFEO + r"\shooter.exe") and get(LAY, newpath) is None
          and GP.list_profiles() == [], "remove: IFEO key and flag gone (were not there before)")
    check(not GP.remove("shooter.exe"), "removing twice: nothing to do")
    # an entry that existed before: other values and the old priority come back
    put(IFEO + r"\tool.exe", MitigationOptions="x")
    put(IFEO + r"\tool.exe\PerfOptions", CpuPriorityClass=2)
    put(LAY, **{r"C:\Tools\tool.exe": "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"})
    GP.save(r"C:\Tools\tool.exe", fso_off=True)
    check(get(IFEO + r"\tool.exe\PerfOptions", "CpuPriorityClass") == 3, "existing entry: set to High")
    GP.save(r"C:\Tools\tool.exe", fso_off=False)
    check(get(LAY, r"C:\Tools\tool.exe") == "~ DISABLEDXMAXIMIZEDWINDOWEDMODE",
          "a flag the user had before stays when the option is turned off")
    GP.remove("tool.exe")
    check(get(IFEO + r"\tool.exe\PerfOptions", "CpuPriorityClass") == 2
          and get(IFEO + r"\tool.exe\PerfOptions", "IoPriority") is None
          and get(IFEO + r"\tool.exe", "MitigationOptions") == "x"
          and get(LAY, r"C:\Tools\tool.exe") == "~ DISABLEDXMAXIMIZEDWINDOWEDMODE",
          "remove: the old priority and the other values are back, nothing else deleted")
    GP.save(r"D:\A\a1.exe"); GP.save(r"D:\B\b1.exe")
    check(GP.remove_all() == 2 and GP.list_profiles() == [], "remove all")
    import psutil
    me = GP.GameProfile(exe=psutil.Process().name().lower(), path=sys.executable)
    s = GP.status(me)
    check(s.running >= 1 and s.run_cpu == psutil.Process().nice() and s.run_io is not None,
          f"live check: a running process' real priority is read ({s.run_cpu}, I/O {s.run_io})")
    check(GP.cpu_matches(me, psutil.HIGH_PRIORITY_CLASS) and not GP.cpu_matches(me, psutil.NORMAL_PRIORITY_CLASS)
          and GP.cpu_matches(me, None) is None, "priority class compared with the profile")

    # ── 5) interrupts ──────────────────────────────────────────────────────────
    print("interrupt view")
    rows = [
        {"id": "PCI\\VEN_10DE&DEV_1", "name": "GPU", "cls": "Display", "cc": "0300", "irqs": [4294967252],
         "msi": 1, "limit": None, "prio": None, "policy": None, "mask": None},
        {"id": "PCI\\VEN_1022&DEV_2", "name": "HD Audio", "cls": "System", "cc": "0403", "irqs": [40],
         "msi": 0, "limit": None, "prio": None, "policy": None, "mask": None},
        {"id": "PCI\\VEN_8086&DEV_3", "name": "NIC", "cls": "Net", "cc": "0200", "irqs": [16],
         "msi": None, "limit": None, "prio": 3, "policy": 4, "mask": "05-00-00-00-00-00-00-00"},
        {"id": "PCI\\VEN_8086&DEV_4", "name": "Old card", "cls": "Display", "cc": "0300", "irqs": [16],
         "msi": None, "limit": None, "prio": None, "policy": None, "mask": None},
        {"id": "PCI\\VEN_144D&DEV_5", "name": "NVMe", "cls": "SCSIAdapter", "cc": "0108",
         "irqs": [4294967287, 4294967286, -12], "msi": 1, "limit": 2048, "prio": 3, "policy": 5, "mask": None},
    ]
    devs = IR.parse(rows)
    by = {d.name: d for d in devs}
    check([d.kind for d in devs] == ["gpu", "gpu", "network", "storage", "audio"],
          f"sorted by type, line interrupts first ({[d.name for d in devs]})")
    check(by["GPU"].mode == "msi" and by["NVMe"].mode == "msi" and by["NVMe"].messages == 3
          and by["HD Audio"].mode == "line", "MSI = an allocated IRQ >= 2^31 (also as a negative number)")
    check(by["NIC"].cores == [0, 2] and by["NIC"].shared_with == ["Old card"]
          and by["Old card"].shared_with == ["NIC"], "core mask decoded; a shared line IRQ found")
    check(IR.mode_text(by["HD Audio"]) == "Leitung (IRQ 40)" and IR.cores_text(by["NIC"]) == "fest: Kern 0, 2"
          and IR.cores_text(by["NVMe"]) == "verteilt auf alle Kerne" and IR.priority_text(3) == "hoch",
          "texts (German)")
    n_audio = IR.notes(by["HD Audio"])
    n_old = IR.notes(by["Old card"])
    check(any("MSISupported = 0" in t for _l, t in n_audio) and not any(lv == "warning" for lv, _t in n_audio),
          "a driver that turns MSI off: an info to leave it, no warning")
    check(any("Enable MSI Mode" in t for _l, t in n_old) and any("Teilt sich" in t for _l, t in n_old),
          "a GPU on a line interrupt: points to the MSI tweak; the shared IRQ is named")
    check(IR.notes(by["GPU"]) == [] and any("Eigene" in t for _l, t in IR.notes(by["NIC"])),
          "nothing to say about a GPU with MSI; a custom core assignment is mentioned")
    check(len(IR.parse(rows[0])) == 1, "a single device (JSON object instead of a list) works")
    I18N._current_lang = "en"
    check(IR.mode_text(by["HD Audio"]) == "Line (IRQ 40)" and IR.summary(devs).startswith("5 devices: 2 with MSI, 3 with"),
          "texts (English)")
    I18N._current_lang = "de"
    t0 = time.time()
    live = IR.scan()
    check(live.ok and live.devices and all(d.mode in ("msi", "line") for d in live.devices),
          f"read-only scan on this PC: {len(live.devices)} devices in {time.time() - t0:.1f} s")

    # ── 6) UI: the games section and the interrupt view ──────────────────────
    print("UI")
    import tkinter as tk
    from tkinter import filedialog, messagebox
    ASKED = []
    messagebox.askyesno = lambda *a, **k: (ASKED.append(a), True)[1]
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: ASKED.append(("error",) + a)
    from core.tweak_runner import TweakRunner
    from core.tweak_verifier import TweakVerifier
    TweakVerifier.verify_all = lambda self, ids, exp: {}
    from core.hardware import HardwareInfo
    runner = TweakRunner(log_dir=TMP)
    runner.backup_registry = lambda label: None
    runner._run_ps = lambda cmd, timeout=60: (True, "ok")
    I18N._current_lang = "en"
    root = tk.Tk()
    root.geometry("1100x800")
    root.attributes("-alpha", 0.0)
    from ui.tab_optimizer import OptimizerTab
    opt = OptimizerTab(root, runner, HardwareInfo(), profiles_dir=os.path.join(TMP, "p"), logs_dir=TMP)
    opt.pack(fill="both", expand=True)

    def pump(cond=lambda: False, secs=3.0):
        end = time.time() + secs
        while time.time() < end:
            root.update()
            if cond():
                return True
            time.sleep(0.02)
        return cond()

    pump(secs=0.5)
    check("Games" in opt._seg_keys and opt._seg_keys["Games"] == "games", "Optimizer: a 'Games' section")
    opt._show_section("games")
    pump(secs=0.3)
    kids = opt._games_list.winfo_children()
    check(len(kids) == 1 and "No games yet" in kids[0].cget("text"), "empty: a hint")
    filedialog.askopenfilename = lambda **k: r"D:\Games\Racer\racer.exe"
    opt._add_game()
    pump(secs=0.3)
    rows_ = opt._games_list.winfo_children()
    check(len(rows_) == 1 and get(IFEO + r"\racer.exe\PerfOptions", "CpuPriorityClass") == 3,
          "'Add game': one row, entry written")
    from ui.components import CheckBox

    def boxes():
        out = []
        stack = list(opt._games_list.winfo_children())
        while stack:
            w = stack.pop(0)
            if isinstance(w, CheckBox):
                out.append(w)
            stack.extend(w.winfo_children())
        return out
    cbs = boxes()
    check(len(cbs) == 2, "two options per game (disk priority, fullscreen optimizations)")
    cbs[1].invoke()                                     # fullscreen optimizations off
    pump(secs=0.3)
    check(get(LAY, r"D:\Games\Racer\racer.exe") == "~ DISABLEDXMAXIMIZEDWINDOWEDMODE",
          "ticking 'fullscreen optimizations off' writes the flag right away")
    boxes()[0].invoke()                                 # disk priority off
    pump(secs=0.3)
    check(get(IFEO + r"\racer.exe\PerfOptions", "IoPriority") is None, "unticking disk priority removes it")
    texts = []
    stack = list(opt._games_list.winfo_children())
    while stack:
        w = stack.pop(0)
        try:
            texts.append(str(w.cget("text")))
        except Exception:
            pass
        stack.extend(w.winfo_children())
    check(any("takes effect the next time the game starts" in x for x in texts),
          "status: set, effective from the next start (the game is not running)")
    filedialog.askopenfilename = lambda **k: r"C:\Windows\explorer.exe"
    n_err = len([a for a in ASKED if a and a[0] == "error"])
    opt._add_game()
    check(len([a for a in ASKED if a and a[0] == "error"]) == n_err + 1 and len(GP.list_profiles()) == 1,
          "a system program is refused with a message")
    # "Revert all" also removes the game profiles
    ASKED.clear()
    opt._revert_all()
    check(ASKED and "game profile" in ASKED[-1][1], f"'Revert all' names the game profiles ({ASKED[-1:]})")
    check(pump(lambda: not GP.list_profiles(), secs=5) and not exists(IFEO + r"\racer.exe")
          and get(LAY, r"D:\Games\Racer\racer.exe") is None, "... and removes them")
    opt.destroy()

    from ui.tab_diagnose import DiagnoseTab
    IR.scan = lambda: IR.InterruptScan(ok=True, devices=devs)
    diag = DiagnoseTab(root)
    diag.pack(fill="both", expand=True)
    pump(secs=0.3)
    check("Interrupts" in diag._view_keys, "Diagnose: an 'Interrupts' view")
    diag._show_view("irq")
    diag._run_irq()
    check(pump(lambda: len(diag.irq_tree.get_children()) == 5, secs=5), "five devices in the table")
    first = diag.irq_tree.item(diag.irq_tree.get_children()[0])
    check(first["values"][2] == "Line (IRQ 16)" and "line" in first["tags"], f"row texts + colour tag ({first})")
    def log_has(*words):
        txt = diag.irq_log.txt.get("1.0", "end")
        return all(w in txt for w in words)
    check(pump(lambda: log_has("Enable MSI Mode", "Leave it"), secs=3), "notes below the table")
    check("2 with MSI" in diag.lbl_irq.cget("text"), f"summary line ({diag.lbl_irq.cget('text')})")
    diag.destroy()
    root.destroy()
finally:
    wipe(BASE)
    try:
        winreg.DeleteKey(HKCU, r"Software\GameOptimizerPro-Test")
    except OSError:
        pass

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
