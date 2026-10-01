"""
GameOptimizerPro v2.0 — update check and offer (app start + settings page).
The network / download part runs in a worker thread; every dialog and widget
update happens on the main thread (a poll via after(), never after() from the
worker — that raises on Python 3.14).
"""

import threading
from tkinter import messagebox

from core import app_settings, updater
from ui.theme import tr


class UpdateFlow:
    def __init__(self, window):
        self.w = window
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, manual: bool = False, on_status=None):
        """Check (and download) in the background, then ask. manual = started by
        the user: says "up to date" / "offline" too, and asks again even if the
        user declined this build before."""
        if self._busy:
            return
        self._busy = True
        box: dict = {}

        def work():
            try:
                box["res"] = self._work()
            except Exception as e:                  # never crash the app over an update
                box["res"] = {"state": "error", "msg": str(e)}

        th = threading.Thread(target=work, daemon=True)
        th.start()
        if on_status:
            on_status(tr("Suche nach Updates …", "Checking for updates …"), "info")

        def poll():
            if th.is_alive():
                self.w.after(300, poll)
                return
            self._busy = False
            self._finish(box.get("res") or {"state": "error", "msg": "?"}, manual, on_status)
        self.w.after(300, poll)

    @staticmethod
    def _work() -> dict:
        local = updater.local_build()
        remote = updater.fetch_remote()
        if remote is None:
            return {"state": "offline", "local": local}
        if remote.build <= local.build:
            return {"state": "current", "local": local, "remote": remote}
        if updater.is_git_checkout():
            return {"state": "git", "local": local, "remote": remote, "clean": updater.git_clean()}
        ok, msg = updater.download_and_stage(remote)
        return {"state": "staged" if ok else "error", "local": local, "remote": remote, "msg": msg}

    # ── main thread ───────────────────────────────────────────────────────────

    def _status(self, on_status, text, kind="info"):
        if on_status:
            try:
                on_status(text, kind)
            except Exception:
                pass

    def _tuning(self) -> bool:
        try:
            return bool(self.w.tuner.is_running)
        except Exception:
            return False

    def _exit(self, relaunch: bool):
        fn = getattr(self.w, "request_exit", None)
        if fn:
            fn(relaunch=relaunch)
        else:                                   # tests / no app object
            self.w.quit()

    def _finish(self, res: dict, manual: bool, on_status):
        st = res.get("state")
        remote = res.get("remote")
        if st == "offline":
            self._status(on_status, tr("GitHub nicht erreichbar — später erneut versuchen.",
                                       "GitHub not reachable — try again later."), "warning")
            return
        if st == "current":
            self._status(on_status, tr(f"Aktuell — Build {res['local'].build}.",
                                       f"Up to date — build {res['local'].build}."), "success")
            return
        if st == "error":
            self._status(on_status, res.get("msg") or tr("Update fehlgeschlagen.", "Update failed."), "error")
            if manual:
                messagebox.showwarning("GameOptimizerPro", res.get("msg") or "Update", parent=self.w)
            return
        if not manual and app_settings.get("update_declined") == remote.build:
            self._status(on_status, tr(f"Build {remote.build} verfügbar.", f"Build {remote.build} available."))
            return
        notes = f"\n\n{remote.notes}" if remote.notes else ""
        when = f" ({remote.date})" if remote.date else ""
        if st == "git":
            if res.get("clean") is not True:
                self._status(on_status, tr(f"Build {remote.build} verfügbar — Git-Ordner mit Änderungen: "
                                           f"bitte selbst „git pull“.",
                                           f"Build {remote.build} available — git folder with changes: "
                                           f"run 'git pull' yourself."), "warning")
                if manual:
                    messagebox.showinfo("GameOptimizerPro", tr(
                        f"Neue Version: Build {remote.build}{when}.{notes}\n\nDein App-Ordner ist ein "
                        f"Git-Checkout mit lokalen Änderungen — bitte selbst „git pull“ ausführen.",
                        f"New version: build {remote.build}{when}.{notes}\n\nYour app folder is a git "
                        f"checkout with local changes — please run 'git pull' yourself."), parent=self.w)
                return
            if self._tuning():
                self._status(on_status, tr("Update verfügbar — nach dem Tune erneut prüfen.",
                                           "Update available — check again after the tune."))
                return
            if not messagebox.askyesno(tr("Update verfügbar", "Update available"), tr(
                    f"Neue Version: Build {remote.build}{when}.{notes}\n\nJetzt mit „git pull“ holen und "
                    f"GameOptimizerPro neu starten?",
                    f"New version: build {remote.build}{when}.{notes}\n\nGet it with 'git pull' now and "
                    f"restart GameOptimizerPro?"), parent=self.w):
                app_settings.set("update_declined", remote.build)
                return
            box: dict = {}
            th = threading.Thread(target=lambda: box.update(r=updater.git_pull()), daemon=True)
            th.start()
            self._status(on_status, "git pull …")

            def wait():
                if th.is_alive():
                    self.w.after(300, wait)
                    return
                ok, out = box.get("r", (False, "?"))
                if not ok:
                    messagebox.showwarning("GameOptimizerPro", tr("„git pull“ hat nicht geklappt:\n\n",
                                                                  "'git pull' failed:\n\n") + out, parent=self.w)
                    return
                self._exit(relaunch=True)
            self.w.after(300, wait)
            return
        # st == "staged": downloaded and checked, waiting in logs/update
        if self._tuning():
            self._status(on_status, tr("Update geladen — wird beim nächsten Start installiert.",
                                       "Update downloaded — it is installed at the next start."))
            return
        if not messagebox.askyesno(tr("Update bereit", "Update ready"), tr(
                f"Neue Version geladen: Build {remote.build}{when}.{notes}\n\nJetzt installieren? "
                f"GameOptimizerPro startet dafür kurz neu (deine Profile und Einstellungen bleiben).\n"
                f"Nein = beim nächsten Start.",
                f"New version downloaded: build {remote.build}{when}.{notes}\n\nInstall it now? "
                f"GameOptimizerPro restarts for it (your profiles and settings stay).\n"
                f"No = at the next start."), parent=self.w):
            self._status(on_status, tr("Update wird beim nächsten Start installiert.",
                                       "The update is installed at the next start."))
            return
        info = updater.pending()
        if info and updater.launch_apply(info, relaunch=True):
            self._exit(relaunch=False)
        else:
            messagebox.showwarning("GameOptimizerPro", tr("Das Update ließ sich nicht starten — es wird "
                                                          "beim nächsten Start erneut versucht.",
                                                          "The update could not be started — it is tried "
                                                          "again at the next start."), parent=self.w)
