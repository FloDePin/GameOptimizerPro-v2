import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_ab_profile.py", "test_real_profile.py", "test_ab_controller.py", "test_ab_process.py",
         "test_mahm_threads.py", "test_tuner_apply.py", "test_tuner_stages.py", "test_worker.py",
         "test_ui_ab.py", "test_selftest_tool.py", "test_services.py", "test_score_clean_display.py",
         "test_ui_new.py", "test_round10.py", "test_memstage.py", "ps_parse_all.py", "ci_backslash_check.py"]
SKIPPED = 2          # exit code of a test that can't run here (e.g. no Afterburner)
env = dict(os.environ, PYTHONIOENCODING="utf-8")
total_ok = total_fail = 0
bad = []
for t in TESTS:
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, t)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=900, cwd=HERE)
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
