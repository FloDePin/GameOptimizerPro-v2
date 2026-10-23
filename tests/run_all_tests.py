import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_ab_profile.py", "test_real_profile.py", "test_ab_controller.py", "test_ab_process.py",
         "test_mahm_threads.py", "test_tuner_apply.py", "test_tuner_stages.py", "test_worker.py",
         "test_ui_ab.py", "test_selftest_tool.py", "test_services.py", "test_score_clean_display.py",
         "test_ui_new.py", "test_round10.py", "test_memstage.py", "test_round12.py",
         "test_ui_round12.py", "test_round13.py", "test_ui_round13.py", "test_round14.py", "test_round15.py", "test_round16.py", "test_round17.py", "test_round18.py", "test_round20.py", "test_round23.py", "test_round24.py", "test_round28.py", "test_round29.py", "test_round30.py", "test_round31.py", "test_round32.py", "test_round33.py", "test_round34.py", "test_round35.py", "test_round36.py", "test_round37.py", "test_round38.py", "test_app_start.py", "ps_parse_all.py",
         "ci_backslash_check.py"]
SKIPPED = 2          # exit code of a test that can't run here (e.g. no Afterburner)
# These map real (alpha-0) windows for real geometry. They run on their own,
# never-shown desktop (run_hidden_desktop.py), so the battery can't take the
# focus from a fullscreen game while it runs.
WINDOWED = {"test_ui_new.py", "test_round10.py", "test_ui_round12.py", "test_round30.py", "test_round33.py", "test_round34.py", "test_round35.py"}
env = dict(os.environ, PYTHONIOENCODING="utf-8")
# The battery often runs next to a game: numpy (the fake GPU load of the stress-worker
# tests) gets one thread instead of every core, and the battery — with every suite it
# starts — runs at the lowest CPU priority without `start /low`.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    env.setdefault(_var, "1")
try:
    import psutil
    if os.name == "nt":
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
except Exception:
    pass
total_ok = total_fail = 0
bad = []
import shutil
import tempfile
for t in TESTS:
    t0 = time.time()
    # every suite its own settings file: no suite writes the app's settings, and no
    # remembered value (tuner fields, open groups) leaks from one suite into the next
    set_dir = tempfile.mkdtemp(prefix="gop_set_")
    env["GOP_SETTINGS_FILE"] = os.path.join(set_dir, "settings.json")
    cmd = [sys.executable, os.path.join(HERE, t)]
    if t in WINDOWED and os.name == "nt":
        cmd.insert(1, os.path.join(HERE, "run_hidden_desktop.py"))
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=900, cwd=HERE)
    shutil.rmtree(set_dir, ignore_errors=True)        # the suite's own settings, nothing else
    out = r.stdout + r.stderr
    ok = out.count("  ok   ")
    fail = out.count("  FAIL ")
    total_ok += ok; total_fail += fail
    note = "  (skipped)" if r.returncode == SKIPPED and not fail else ""
    print(f"{t:32s} exit={r.returncode}  {ok:3d} ok  {fail} FAIL  ({time.time() - t0:.0f}s){note}", flush=True)
    if (r.returncode not in (0, SKIPPED)) or fail:
        bad.append(t)
        for line in out.splitlines():
            if "FAIL" in line or "Traceback" in line or "Error" in line:
                print("     ", line[:160])
print(f"\nTOTAL: {total_ok} checks ok, {total_fail} failed; suites with problems: {bad or 'none'}")
sys.exit(1 if bad else 0)
