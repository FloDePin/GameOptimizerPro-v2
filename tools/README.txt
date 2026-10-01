GameOptimizerPro — tools/ folder
================================

Helper scripts.

Afterburner self-test (ab_selftest.py)
--------------------------------------
Checks the MSI Afterburner integration: `python tools\ab_selftest.py info`
(read-only), `dryrun` (shows what would be written), `live` (small reversible
test, admin terminal) and `restore`. Step-by-step guide: TESTANLEITUNG.md.

apply_update.py
---------------
Installs an update the app downloaded from GitHub (core/updater.py starts the
copy from the NEW version, waits for the app to exit, backs up the replaced
files to logs/update_backup_<build>/, rolls back on errors, restarts the app).
Not meant to be run by hand.

Nothing here is required for the rest of the app.
