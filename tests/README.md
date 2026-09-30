# Tests

Windows-only test battery (Python 3.10+, run from anywhere):

```
python tests\run_all_tests.py
```

Every suite prints `ok` / `FAIL` lines and exits with 0 (passed), 1 (failed) or
2 (skipped — e.g. `test_real_profile.py` without MSI Afterburner).

What they do — and don't:

- **Nothing on the system is changed.** Tweaks run against a faked PowerShell,
  the services manager against fake `sc.exe` calls, the cleaner against temp
  trees, the Afterburner controller against a fake install and a dummy process
  under a *test* name (safe next to a running Afterburner), the MAHM reader
  against a *test* shared-memory section.
- **Read-only real checks:** `test_real_profile.py` reads the real Afterburner
  profile of the card (writes go to strings only), `ps_parse_all.py` *parses*
  every PowerShell snippet of every tweak and check (never executes them),
  `test_services.py` / `test_score_clean_display.py` read services, displays and
  the Recycle Bin state.
- `test_worker.py` runs the stress worker for ~30 s against a numpy-backed
  stand-in for cupy (`fakecupy/`, with injected computation errors) — CPU only,
  the GPU is not touched.
- The UI suites run under a real Tk mainloop with invisible windows.

CI (GitHub Actions, Linux) only byte-compiles them.
