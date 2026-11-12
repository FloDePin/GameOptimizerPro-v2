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

Windows update check (windows_watch.py)
---------------------------------------
After a Windows update: `python tools\windows_watch.py` shows the state of every
tweak and what changed since the last run (tweaks an update reset, services /
tasks / power settings that are gone); `--scan` also searches Windows' own files
for every registry value name the tweaks set (a name no file contains any more
is probably not read: a tweak without effect); `--winget` checks the program
installer's ids. Read-only, low priority; the report and the state go to
privat\ (or `--out <folder>`).

find_python.cmd
---------------
Finds the python.org Python for GameOptimizerPro.bat and install.bat (never the
Store one) and offers to install Python 3.12 when there is none.

Nothing here is required for the rest of the app.
