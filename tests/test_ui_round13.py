"""Round 13 — GPU tab: 'Rundum' mode with the goal switch, its own parameters,
the FurMark status, the start configuration, curve profiles in the list and the
report button. Withdrawn window, fake monitor / Afterburner — nothing is applied."""
import os, sys, tempfile, shutil, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import tempfile as _tf                     # never the app's own settings (run on their own too)
from pathlib import Path as _P
from core import app_settings as _AS
_AS.SETTINGS_FILE = _P(_tf.mkdtemp(prefix="gop_set_")) / "settings.json"
import atexit as _ax, shutil as _sh  # noqa: E401,E402
_ax.register(_sh.rmtree, str(_AS.SETTINGS_FILE.parent), True)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

import core.i18n as I18N
I18N._current_lang = "de"                  # in memory only

import tkinter as tk
from tkinter import messagebox
ASKED = []
messagebox.askyesno = lambda title, msg, **k: (ASKED.append((title, msg)), True)[1]

from core.nvtune_core import AfterburnerController, ProfileManager, TuneProfile
from core.nvtune_tuner import AutoTuner, TunerConfig, TuneMode, TunerState
import ui.tab_gpu as TG


class Mon:
    def read(self):
        return types.SimpleNamespace(name="NVIDIA GeForce RTX 4080", temp=45, voltage_mv=880.0,
                                     core_mhz=210.0, gpu_power_w=25.0, gpu_usage=2.0, mem_mhz=405.0)
    def power_pct_to_watts(self, pct): return round(320 * pct / 100, 1)
    def set_power_limit(self, w): return True


class FakeAB(AfterburnerController):
    def _detect(self):
        self.exe, self.profile_dir = r"C:\fake\MSIAfterburner.exe", None


tmp = tempfile.mkdtemp(prefix="gop_ui13_")
FM = os.path.join(tmp, "FurMark_win64", "furmark.exe")
os.makedirs(os.path.dirname(FM))
for n in ("furmark.exe", "FurMark_GUI.exe"):
    open(os.path.join(os.path.dirname(FM), n), "wb").close()
TG.GpuTunerTab._furmark_v2 = staticmethod(lambda: FM)     # pretend FurMark 2 is set up


def build(lang):
    I18N._current_lang = lang
    _AS.set("tuner_settings", {})    # remembered fields: each build starts from the card's defaults
    import ui.theme as TH
    TH._ICON_CACHE.clear()          # icons belong to a Tk root; this test makes a second one
    root = tk.Tk()
    root.withdraw()
    pm = ProfileManager(os.path.join(tmp, f"profiles_{lang}"))
    tuner = AutoTuner(Mon(), FakeAB(), pm, TunerConfig(), log_dir=os.path.join(tmp, "logs"))
    started = []
    tuner.start = lambda: started.append(tuner.config)
    tab = TG.GpuTunerTab(root, Mon(), tuner.ab, pm, tuner)
    tab.pack(fill="both", expand=True)
    root.update_idletasks()
    return root, tab, tuner, pm, started


print("GPU tab — German")
root, tab, tuner, pm, started = build("de")
labels = list(tab._mode_labels)
check(labels == ["Rundum", "Schnell (OC + UV)"] and tab.seg_mode.get() == "Rundum",
      f"two modes, Rundum first and selected: {labels}")
tab.seg_mode.winfo_width = lambda: 120          # very narrow (large font scaling)
tab._fit_mode_labels()
check(list(tab._mode_labels) == ["Rundum", "Schnell"] and tab.seg_mode.get() == "Rundum",
      f"narrow: short button text, selection kept: {list(tab._mode_labels)}")
tab.seg_mode.winfo_width = lambda: 600
tab._fit_mode_labels()
check(list(tab._mode_labels) == labels and tab.seg_mode.get() == "Rundum", "wide again: long texts")
check(tab.params_card.winfo_manager() == "" and tab.goal_card.winfo_manager() == "pack"
      and tab.curve_card.winfo_manager() == "pack", "start: goal + Rundum parameters")
tab._select_mode("oc_uv")
root.update_idletasks()
check(tab.params_card.winfo_manager() == "pack" and tab.goal_card.winfo_manager() == ""
      and tab.curve_card.winfo_manager() == "", "Schnell: classic parameters, no goal card")
tab._select_mode("curve")
root.update_idletasks()
check(tab.v_mode.get() == "curve" and tab.params_card.winfo_manager() == ""
      and tab.goal_card.winfo_manager() == "pack" and tab.curve_card.winfo_manager() == "pack",
      "'Rundum': goal + Rundum parameters instead of the classic card")
order = [w for w in tab.mode_card.master.pack_slaves() if w.winfo_manager() == "pack"]
check(order[:3] == [tab.mode_card, tab.goal_card, tab.curve_card], "order: mode, goal, parameters")
check("HYDRA" in tab.lbl_mode_desc.cget("text") and "70–105 min" in tab.lbl_mode_desc.cget("text")
      and "25 mV" in tab.lbl_mode_desc.cget("text"), "mode description")
from core.gpu_defaults import get_defaults as _gd
check(tab.v_core_max.get() == _gd("NVIDIA GeForce RTX 4080").curve_core_max_mhz == 350,
      f"Rundum: 'Core max' +350 per point (classic +250): {tab.v_core_max.get()}")


def _texts(w):
    out = []
    for c in w.winfo_children():
        try:
            out.append(str(c.cget("text")))
        except Exception:
            pass
        out += _texts(c)
    return out


ctexts = _texts(tab.curve_card)
check("Abstand der Messpunkte (mV)" in ctexts and tab.v_point_mv.get() == 25,
      "Rundum parameters: 'Abstand der Messpunkte' 25 mV by default")
names = ["Takt-Plus max. je Punkt (MHz)", "Temperatur-Grenze (°C)", "Testdauer je Schritt (s)",
         "Abstand der Messpunkte (mV)", "Sicherheitsabzug (MHz)", "Endtest: FurMark (min)",
         "Endtest: Rechenprüfung (s)", "Speicher-Plus max. (MHz)", "Afterburner-Profilplatz (2–5)"]
check(all(n in ctexts for n in names), f"clear names: {[n for n in names if n not in ctexts]}")
from ui.components import HelpTip


def _tips(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, HelpTip):
            out.append(c)
        out += _tips(c)
    return out


tips = _tips(tab.curve_card)
check(len(tips) == 12 and all(len(x.text) > 60 for x in tips),
      f"a '?' with an explanation for every Rundum setting + the memory, encoder and hardness test tick boxes ({len(tips)})")
ptips = _tips(tab.params_card)
check(len(ptips) == 11, f"... and for the classic parameters ({len(ptips)})")
steps = tab.curve_steps.text()
check(steps.startswith("1. Start und Standard-Messung: Abkühlen auf höchstens 45 °C") and "Dann Standard messen" in steps
      and "Alle 25 mV" in steps and "6. Endtests: Zuerst ein Lastwechsel-Check: 150 s Härtetest-Phase" in steps and "die empfindlichsten zuerst: 120 s Rechenprüfung, Härtetest" in steps and "5 min FurMark." in steps and "die letzten 15 s mit Lastwechseln" in steps and "7. Nachher-Messung: 60 s FurMark" in steps,
      "procedure box: the steps with the current values")
check("− 200 MHz Sicherheit" in steps and "noch einmal mit Speicher auf Standard" in steps
      and "beginnt mit dem gescheiterten Test" in steps and "höchstens 12 Versuche" in steps,
      "procedure box: the memory margin, the cross-check and the fail-fast retry as the tuner does them")
check(len(steps.splitlines()) == 7 and tab.curve_steps._rows[5][2].winfo_manager() == "pack"
      and tab.curve_steps._rows[5][2].cget("text").startswith("↻ Fällt ein Test durch"),
      "seven numbered steps; the step back is a note of its own under the final tests")
tab.v_point_mv.set(50); tab.v_mem_stage.set(False); tab.v_fm_final.set(7)
steps = tab.curve_steps.text()
check("Alle 50 mV" in steps and "Bleibt auf Standard" in steps and "7 min FurMark" in steps
      and "Speicher auf Standard" not in steps,
      "... updated as soon as a value changes (memory off: no memory cross-check in the note)")
tab.v_point_mv.set(25); tab.v_mem_stage.set(True); tab.v_fm_final.set(5)
check(any("übersprungen" in x.text and "25 = genauer" in x.text for x in tips),
      "the point spacing is explained in its '?'")
check(list(tab._goal_labels) == ["Max. Leistung", "Ausgewogen", "Effizienz"] and tab.v_goal.get() == "balanced",
      "goal switch, 'Ausgewogen' preselected")
tab._select_goal("efficiency")
check(tab.v_goal.get() == "efficiency" and "Undervolting" in tab.lbl_goal_desc.cget("text")
      and tab.seg_goal.get() == "Effizienz", "goal switch updates value and description")
check("FurMark 2" in tab.lbl_furmark.cget("text") and "8× MSAA" in tab.lbl_furmark.cget("text"),
      f"FurMark status: {tab.lbl_furmark.cget('text')[:70]}")
check(tab.v_mem_stage.get() is True, "memory stage on by default in Rundum")
check(tab.v_mem_max.get() == 1000, f"Rundum: 'Mem max' +1000 (+500 … +1000 in 100-MHz steps): {tab.v_mem_max.get()}")

check(tab._curve_prior() == (90, False) and tab._mem_start() == 500,
      "no profile yet: the RTX 4080's cautious start values (+90 core, +500 memory)")
check(tab._tuner_ok and str(tab.btn_start.cget("state")) == "normal" and not hasattr(tab, "lbl_unsupported"),
      "NVIDIA card: tuner available, no warning")
pm.save(TuneProfile(name="GOP_OC+UV_0928_2100", core_offset_mhz=179, is_stable=True,
                    gpu_name="NVIDIA GeForce RTX 4080", created_at="2026-09-28T21:00:00"))
pm.save(TuneProfile(name="GOP_OC_0901_1000", core_offset_mhz=150, is_stable=True,
                    gpu_name="NVIDIA GeForce RTX 4080", created_at="2026-09-01T10:00:00"))
pm.save(TuneProfile(name="Manual", core_offset_mhz=250, is_stable=False))
check(tab._curve_prior() == (179, True), "start value = newest stable tune result of this card (+179)")

tab.v_fm_final.set(5)
tab.v_safety.set(45)
tab._start_tune()
cfg = started[-1] if started else None
title, msg = ASKED[-1] if ASKED else ("", "")
check(cfg is not None and cfg.mode == TuneMode.CURVE and cfg.goal == "efficiency",
      "start: Rundum mode with the chosen goal")
check(cfg and cfg.final_bench_s == 300 and cfg.final_test_s == tab.v_final_dur.get()
      and cfg.curve_safety_mhz == 45 and cfg.curve_prior_mhz == 179 and cfg.furmark_path == FM
      and cfg.bench_msaa == 8 and cfg.step_test_s == tab.v_step_dur.get(),
      "config: 5-min FurMark, compute check, safety 45, start +179, FurMark 2, 8x MSAA")
check(cfg and cfg.mem_stage and cfg.curve_anchor_step_mv == 25 and "alle 25 mV" in msg,
      "points every 25 mV (config and dialog), memory stage on")
check(title == "Rundum-Tuner starten" and "Ziel: Effizienz" in msg and "+179 MHz" in msg
      and "5 min FurMark" in msg and "Minuten" in msg and "nicht spielen" in msg,
      "start dialog explains goal, start value, final test, duration")
check("FurMark-Fenster nicht anklicken" in msg and "Vorrang" in msg,
      "... and not to click the FurMark windows (live: FurMark in front left the memory check 13 GB/s)")
check("Speicher: +500 bis +1000 MHz in 100er-Schritten, ganze Karte unter Last" in msg
      and cfg.mem_oc_max_mhz == 1000 and cfg.mem_curve_start_mhz == 500 and cfg.mem_curve_step_mhz == 100,
      "memory plan in the dialog and the config: +500 … +1000, 100-MHz steps, whole card")

import re as _re
est25 = int(_re.search(r"Dauer ca\. (\d+)–", msg).group(1))
tab.v_point_mv.set(50)
tab._start_tune()
cfg50, msg50 = started[-1], ASKED[-1][1]
est50 = int(_re.search(r"Dauer ca\. (\d+)–", msg50).group(1))
check(cfg50.curve_anchor_step_mv == 50 and "alle 50 mV" in msg50 and est50 < est25,
      f"50 mV: faster ({est50} vs {est25} min at the low end)")
tab.v_point_mv.set(25)

tab._select_mode("oc_uv")
root.update_idletasks()
check(tab.params_card.winfo_manager() == "pack" and tab.curve_card.winfo_manager() == ""
      and tab.goal_card.winfo_manager() == "", "back to Schnell: classic parameters again")
check(tab.v_core_max.get() == 250, "Schnell keeps its 'Core max' (+250)")
tab._start_tune()
check(started[-1].mode == TuneMode.OC_UV and "Modus: Schnell (OC + Undervolt)" in ASKED[-1][1]
      and "Takt-Schritt" in ASKED[-1][1] and "Testdauer je Schritt" in ASKED[-1][1],
      "classic start unchanged")
c2 = started[-1]
check(c2.mem_stage and c2.mem_curve_start_mhz == 500 and c2.furmark_path == FM and c2.bench_msaa == 8
      and "ganze Karte unter Last (FurMark + Datenprüfung)" in ASKED[-1][1]
      and "FurMark-Fenster gehen auf" in ASKED[-1][1] and "Vergleich mit Standard" in ASKED[-1][1],
      "classic memory stage: the whole card under load as in Rundum (+500, FurMark 2)")

pm.save(TuneProfile(name="GOP_CURVE_BAL_1001_2130", core_offset_mhz=142, is_stable=True,
                    curve_points=[[850, 2531], [1050, 2937]], curve_cap_mv=1025,
                    stability_score=100, gpu_name="NVIDIA GeForce RTX 4080"))
tab._refresh_profiles()
check(tab.tree.set("GOP_CURVE_BAL_1001_2130", "core") == "Kurve", "profile list: 'Kurve' instead of an offset")
tab.tree.selection_set("GOP_CURVE_BAL_1001_2130")
tab._on_profile_select(None)
det = tab.lbl_detail.cget("text")
check("1050 mV → 2937 MHz · 850 mV → 2531 MHz" in det and "flach ab 1025 mV" in det,
      f"profile details list the curve: {det.splitlines()[-1]!r}")

check(tab.btn_report.winfo_manager() == "" and tab._latest_report() == "", "no report yet: no report button")
check(tab.btn_start.winfo_manager() == "pack" and tab.btn_abort.winfo_manager() == "",
      "idle: only 'Start tune' — no greyed abort button next to it")
os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
rep = os.path.join(tmp, "logs", "curve_report_x.txt")
open(rep, "w", encoding="utf-8").write("Rundum-Tuner\n")
tuner.last_report_path = rep
tab._on_state(TunerState.DONE)
root.update()
check(tab.btn_report.winfo_manager() == "pack" and str(tab.btn_report.cget("state")) == "normal",
      "report button shown after a Rundum run")
tuner.last_report_path = ""
tab._on_state(TunerState.BASELINE)
root.update()
check(tab.btn_report.winfo_manager() == "", "hidden while a tune runs (its report comes at the end)")
check(tab.btn_abort.winfo_manager() == "pack" and tab.btn_start.winfo_manager() == ""
      and str(tab.btn_abort.cget("state")) == "normal" and "abbrechen" in tab.btn_abort.cget("text"),
      "running: the one button is 'Tune abbrechen'")
tab._on_state(TunerState.ABORTED)
root.update()
check(tab.btn_start.winfo_manager() == "pack" and tab.btn_abort.winfo_manager() == ""
      and str(tab.btn_start.cget("state")) == "normal", "aborted: back to 'Tune starten'")
check(tab.btn_report.winfo_manager() == "pack" and tab._latest_report() == rep,
      "idle again: the newest report in the logs folder is offered")

# 23.10.: the remaining time, the pre-start check, what the final tests learned
import time as _time


class _Alive:
    def is_alive(self):
        return True


tuner._thread = _Alive()
tuner.eta_end = _time.time() + 25 * 60 + 10
check(tab._eta_text() == "Rest ca. 25 min", f"remaining time while a tune runs: {tab._eta_text()!r}")
tuner.eta_end = _time.time() + 125 * 60 + 10
check(tab._eta_text() == "Rest ca. 2:05 h", f"... in hours from 90 min on: {tab._eta_text()!r}")
tuner.eta_end = _time.time() + 20
check(tab._eta_text() == "Rest < 1 min", "... under a minute")
tuner.eta_end = _time.time() + 600
tab._on_progress(50, "Punkt 3/7")
root.update()
check(tab.lbl_eta.cget("text") == "Rest ca. 10 min" and tab.lbl_prog.cget("text") == "Punkt 3/7",
      "shown next to the progress text")
tuner._thread = None
check(tab._eta_text() == "", "no tune running: no remaining time")
tuner.eta_end = 0.0

check(tab._preflight() == [] and tab._preflight_text() == "", "idle card, no driver error: nothing to warn")
_mon = tab.monitor
tab.monitor = types.SimpleNamespace(read=lambda: types.SimpleNamespace(
    name="NVIDIA GeForce RTX 4080", temp=60, voltage_mv=1000.0, core_mhz=2700.0, gpu_power_w=200.0,
    gpu_usage=80.0, mem_mhz=11200.0))
tuner.cr = types.SimpleNamespace(check_tdr_since=lambda s: s == 3600)
pre = tab._preflight_text()
check(pre.startswith("⚠ Vorab-Check:") and "zu 80 % ausgelastet" in pre and "Treiber-Reset" in pre
      and "Trotzdem starten geht" in pre,
      "pre-start check: a busy GPU and a driver error in the last hour are said before a 1.5-h tune")
tab._select_mode("curve")
tab._start_tune()
check(ASKED[-1][1].startswith("⚠ Vorab-Check:") and "Rundum-Tuner — Ziel" in ASKED[-1][1],
      "... at the top of the start dialog (starting anyway stays possible)")
tab.monitor = _mon
tuner.cr = None

from core import learned_limits as _LL
_LL.record(tuner._log_dir, "NVIDIA GeForce RTX 4080", 1000, 2742, "Härtetest")
tab._refresh_learned()
root.update()
rows = getattr(tab, "_learned_rows", [])
check(len(rows) == 2 and all(r.winfo_manager() == "pack" for r, _l in rows)
      and "1000 mV ≤ 2727 MHz" in rows[0][1].cget("text") and "Gelernt aus Endtests" in rows[0][1].cget("text"),
      f"what the final tests learned is shown in both modes' cards: {rows and rows[0][1].cget('text')!r}")
tab._forget_learned()
root.update()
check(_LL.load(tuner._log_dir, "NVIDIA GeForce RTX 4080") == {} and all(r.winfo_manager() == "" for r, _l in rows)
      and "Wärmeleitpaste" in ASKED[-1][1],
      "'Vergessen' (asked first: e.g. after a cleaning or new thermal paste) clears it and hides the row")
tab._on_state(TunerState.BASELINE)
root.update()
tab._on_state(TunerState.CURVE)
root.update()
check("Kurve" in tab.lbl_state.cget("text"), f"state label for the point search: {tab.lbl_state.cget('text')}")
root.destroy()

print("GPU tab — AMD / no NVML")
class AmdMon(Mon):
    def read(self):
        st = super().read()
        st.name = "AMD Radeon RX 7900 XTX"
        return st
I18N._current_lang = "de"
import ui.theme as TH
TH._ICON_CACHE.clear()
root2 = tk.Tk(); root2.withdraw()
pm2 = ProfileManager(os.path.join(tmp, "profiles_amd"))
tuner2 = AutoTuner(AmdMon(), FakeAB(), pm2, TunerConfig(), log_dir=os.path.join(tmp, "logs"))
started2 = []
tuner2.start = lambda: started2.append(1)
INFOS = []
messagebox.showinfo = lambda title, msg, **k: INFOS.append(msg)
tab2 = TG.GpuTunerTab(root2, AmdMon(), tuner2.ab, pm2, tuner2)
check(not tab2._tuner_ok and "AMD Software (Adrenalin)" in tab2.lbl_unsupported.cget("text")
      and str(tab2.btn_start.cget("state")) == "disabled", "AMD card: clear hint, Start disabled")
tab2._start_tune()
check(not started2 and INFOS and "nur für NVIDIA" in INFOS[-1], "and a start attempt only explains why")
root2.destroy()


class NoNvmlMon(Mon):
    nvml = types.SimpleNamespace(available=False)
    def read(self):
        st = super().read()
        st.name = "Unknown"
        return st
TH._ICON_CACHE.clear()
root3 = tk.Tk(); root3.withdraw()
tuner3 = AutoTuner(NoNvmlMon(), FakeAB(), ProfileManager(os.path.join(tmp, "p3")), TunerConfig(),
                   log_dir=os.path.join(tmp, "logs"))
tab3 = TG.GpuTunerTab(root3, NoNvmlMon(), tuner3.ab, tuner3.pm, tuner3)
check(not tab3._tuner_ok and "NVML nicht verfügbar" in tab3.lbl_unsupported.cget("text"),
      "no NVML at all: 'no NVIDIA card found'")
root3.destroy()

print("GPU tab — English")
root, tab, tuner, pm, started = build("en")
check(list(tab._mode_labels) == ["All-round", "Quick (OC + UV)"] and
      list(tab._goal_labels) == ["Max performance", "Balanced", "Efficiency"], "English labels")
tab._select_mode("curve")
tab._start_tune()
title, msg = ASKED[-1]
check(title == "Start all-round tuner" and "goal: Balanced" in msg and "Ziel" not in msg
      and "Minuten" not in msg, "English start dialog")
root.destroy()

I18N._current_lang = "de"

print("Status dot / voltage hint while the tuner restarts Afterburner")
from unittest import mock
import ui.main_window as MW
import ui.tab_dashboard as TD
from ui.theme import ACC, AMBER, DIM, GREEN
from core.nvtune_core import GpuStats


class _Lbl:
    def __init__(self):
        self.kw = {}

    def config(self, **kw):
        self.kw.update(kw)


mahm = types.SimpleNamespace(available=False, restarting=True)
win = types.SimpleNamespace(lbl_ab=_Lbl(), lbl_nvml=_Lbl(), lbl_mahm=_Lbl(), _ind_state={},
                            INDICATOR_TEXT=MW.GameOptimizerWindow.INDICATOR_TEXT,
                            ab=types.SimpleNamespace(available=True),
                            monitor=types.SimpleNamespace(nvml=types.SimpleNamespace(available=True),
                                                          mahm=mahm))
MW.GameOptimizerWindow._refresh_indicators(win)
tip = MW.GameOptimizerWindow._indicator_text(win, "mahm")
check(win.lbl_mahm.kw.get("fg") == ACC and "absichtlich" in tip and "grün" in tip,
      f"MAHM dot blue while Afterburner is restarted on purpose — pointing at it says why: {tip[:60]}…")
mahm.restarting = False
MW.GameOptimizerWindow._refresh_indicators(win)
check(win.lbl_mahm.kw.get("fg") == AMBER and "Spannung" in MW.GameOptimizerWindow._indicator_text(win, "mahm"),
      "orange when it is really gone (and what to check)")
mahm.available = True
MW.GameOptimizerWindow._refresh_indicators(win)
check(win.lbl_mahm.kw.get("fg") == GREEN and all(MW.GameOptimizerWindow._indicator_text(win, k)
                                                 for k in ("ab", "nvml", "mahm")),
      "green when it delivers; every dot explains itself")

dash = mock.MagicMock()
dash.hw.gpu_vram_mb = 16376
st = GpuStats()
st.mahm_restarting = True
TD.DashboardTab._update(dash, st)
kw = dash.lbl_volt_src.config.call_args.kwargs
check("Afterburner startet neu" in kw.get("text", "") and kw.get("fg") == DIM,
      f"dashboard voltage: 'Afterburner startet neu' instead of 'freischalten': {kw}")
st.mahm_restarting = False
TD.DashboardTab._update(dash, st)
check("freischalten" in dash.lbl_volt_src.config.call_args.kwargs.get("text", ""),
      "without a restart the hint to enable voltage monitoring stays")

print("GPU tab — remembered settings (round 19)")
root, tab, tuner, pm, started = build("de")
tab._select_mode("curve")
d_core_curve = tab.v_core_max.get()
tab.v_mem_max.set(700)                  # the user's series: memory up to +700 in every run
tab.v_ab_slot.set(3)
tab._select_mode("oc_uv")
check(tab.v_mem_max.get() == 700 and tab.v_ab_slot.get() == 3,
      f"a mode switch keeps what the user set (memory max was reset to +1000): {tab.v_mem_max.get()}")
tab.v_core_max.set(180)                 # Quick: own clock gain
tab._select_mode("curve")
check(tab.v_core_max.get() == d_core_curve, "the clock gain is per mode (per point vs one offset)")
root.destroy()
import ui.theme as TH
TH._ICON_CACHE.clear()
root = tk.Tk()
root.withdraw()
tuner = AutoTuner(Mon(), FakeAB(), pm, TunerConfig(), log_dir=os.path.join(tmp, "logs"))
tab = TG.GpuTunerTab(root, Mon(), tuner.ab, pm, tuner)       # the next start: the saved values
check(tab.v_mode.get() == "curve" and tab.v_mem_max.get() == 700 and tab.v_ab_slot.get() == 3,
      f"after a restart: mode, memory max, slot as left: {tab.v_mode.get()}, {tab.v_mem_max.get()}, "
      f"{tab.v_ab_slot.get()}")
tab._select_mode("oc_uv")
check(tab.v_core_max.get() == 180, "the Quick mode's own clock gain too")
tab._reset_user_settings()
check(tab.v_mem_max.get() != 700 and tab.v_ab_slot.get() == 2 and _AS.get("tuner_settings") == {"mode": "oc_uv"},
      "'Vorgaben der Karte wiederherstellen': the card's defaults, nothing remembered")
tab._clamp_fields()                     # what Start does first
check(_AS.get("tuner_settings") == {"mode": "oc_uv"},
      f"Start (fields clamped) records no field as the user's: {_AS.get('tuner_settings')}")
tab.v_ab_slot.set(1)
tab._user_settings.pop("ab_slot", None)
tab._clamp_fields()
check(tab.v_ab_slot.get() == 2 and _AS.get("tuner_settings").get("ab_slot") == 2,
      "a typed value outside the range is corrected — and that correction is kept")
# a test on the stress page still loads the GPU: no tune next to it (two loads skew every measurement)
import time as _time
from core import gpu_watchdog as _WD
_WD.SESSIONS_FILE = None              # never the app's own session list
_INF, _si = [], messagebox.showinfo
messagebox.showinfo = lambda title, msg, **k: _INF.append(msg)
started = []
tuner.start = lambda: started.append(tuner.config)    # never a real run here
n0, t_own = len(started), _time.time()
_WD.own_load_started(t_own)
tab._start_tune()
check(len(started) == n0 and _INF and "Stresstest-Seite" in _INF[-1] and "verfälschen" in _INF[-1],
      "a stress-page test still running: the tune does not start, a box says why")
_WD.record_own_load(t_own, _time.time())
tab._start_tune()
check(len(started) == n0 + 1, "... once it has ended, the tune starts")
messagebox.showinfo = _si
root.destroy()

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
