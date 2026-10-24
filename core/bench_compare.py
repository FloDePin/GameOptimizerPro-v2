"""
GameOptimizerPro — the 3DMark comparison of the GPU profiles (24.10.)

The way it was done by hand live: each chosen profile is applied in turn, the card cools down, the
user starts the 3DMark test, every new result file is read and booked on the profile that was active,
and the board power is sampled while the card is under load. Stock runs last (it borrows a profile's
Afterburner slot, which is restored afterwards), then the profile that was active before comes back.
3DMark's Steam edition can't be started from outside (only the Professional edition has a command
line) — so the user presses "Run", the app does the rest.

UI-agnostic: the stress page calls poll() about once a second and shows what it returns.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

STOCK = "__stock__"


@dataclass
class Booked:
    key: str            # profile name or STOCK
    test: str           # "Speed Way", "Time Spy", …
    score: int
    power_w: float      # mean board power while the GPU was loaded (0 = not measured)
    file: str = ""


@dataclass
class State:
    phase: str          # applying | cooling | ready | restoring | done | aborted | error
    key: str = ""
    step: int = 0       # 1-based profile in the order
    steps: int = 0
    run: int = 0        # 1-based run of this profile
    runs: int = 0
    temp: float = 0.0
    error: str = ""
    last: Optional[Booked] = None
    note: str = ""      # "early": a run started before the cool-down ended (not counted)


class CompareSession:
    COOL_C = 45.0           # every run starts at most this warm (like the tuner's start)
    COOL_MAX_S = 180        # … or after this long (a warm room)
    LOAD_PCT = 90.0         # power samples count while the GPU is this busy

    def __init__(self, keys: list, runs: int, apply: Callable[[str], tuple], restore: Callable[[], tuple],
                 read: Callable[[], object], results_since: Callable[[float], list],
                 now: Callable[[], float] = time.time, names: Optional[Callable[[], list]] = None):
        """keys: profile names in order (STOCK is moved to the end); apply(key) -> (ok, err), blocking
        (Afterburner); restore() -> (ok, err): the borrowed slot back + the profile active before;
        read() -> stats with .temp, .gpu_usage, .gpu_power_w; results_since(t) -> parsed 3DMark results."""
        ks = [k for k in keys if k != STOCK] + ([STOCK] if STOCK in keys else [])
        self.keys, self.runs = ks, max(1, int(runs))
        self._apply, self._restore, self._read, self._since, self._now = apply, restore, read, results_since, now
        self._names = names or (lambda: [r["file"] for r in results_since(0.0)])
        self.booked: list[Booked] = []
        self._seen: set = set()
        self._i, self._run = 0, 0
        self._phase = "idle"
        self._job: Optional[threading.Thread] = None
        self._job_res: tuple = (True, "")
        self._t0 = 0.0
        self._samples: list = []
        self._error = ""
        self._temp = 0.0
        self._abort = False
        self._note = ""
        self._t_step = 0.0        # when the current profile's apply began

    # ── driving ──────────────────────────────────────────────────────────────
    def start(self):
        if not self.keys:
            self._phase = "done"
            return
        self._seen = set(self._names())           # results from before never count
        self._begin_apply()

    def abort(self):
        if self._phase in ("done", "aborted", "error", "restoring"):
            return
        self._abort = True
        if self._job is None or not self._job.is_alive():
            self._begin_restore()

    def _run_job(self, fn: Callable[[], tuple]):
        self._job_res = (False, "")

        def work():
            try:
                self._job_res = fn() or (True, "")
            except Exception as e:                # Afterburner trouble must not kill the page
                self._job_res = (False, str(e))
        self._job = threading.Thread(target=work, daemon=True)
        self._job.start()

    def _begin_apply(self):
        self._phase, self._run, self._t_step = "applying", 0, self._now()
        key = self.keys[self._i]
        self._run_job(lambda: self._apply(key))

    def _begin_restore(self):
        self._phase = "restoring"
        self._run_job(self._restore)

    def _begin_cool(self):
        self._phase, self._t0 = "cooling", self._now()

    def _early(self):
        """A result while applying or cooling: started too early (a warm card) — not counted, said so."""
        for r in self._since(self._t_step - 2):
            if r["file"] not in self._seen:
                self._seen.add(r["file"])
                self._note = "early"

    def poll(self) -> State:
        try:
            st = self._read()
            self._temp = float(getattr(st, "temp", 0) or 0)
            busy = float(getattr(st, "gpu_usage", 0) or 0)
            watt = float(getattr(st, "gpu_power_w", 0) or 0)
        except Exception:
            busy, watt = 0.0, 0.0
        if self._phase in ("applying", "cooling"):
            self._early()
        if self._phase == "applying" and self._job is not None and not self._job.is_alive():
            ok, err = self._job_res
            if self._abort:
                self._begin_restore()
            elif not ok:
                self._error = err or "Afterburner"
                self._begin_restore()
            else:
                self._begin_cool()
        elif self._phase == "cooling":
            if self._temp <= self.COOL_C or self._now() - self._t0 >= self.COOL_MAX_S:
                self._phase, self._t0, self._samples = "ready", self._now(), []
        elif self._phase == "ready":
            if busy >= self.LOAD_PCT and watt > 0:
                self._samples.append(watt)
            new = [r for r in self._since(self._t0 - 2) if r["file"] not in self._seen]
            if new:
                r = new[0]
                self._seen.add(r["file"])
                self._note = ""
                w = round(sum(self._samples) / len(self._samples), 1) if self._samples else 0.0
                self.booked.append(Booked(self.keys[self._i], r["test"], int(r["score"]), w, r["file"]))
                self._run += 1
                if self._run >= self.runs:
                    self._i += 1
                    if self._i >= len(self.keys):
                        self._begin_restore()
                    else:
                        self._begin_apply()
                else:
                    self._begin_cool()
        elif self._phase == "restoring" and self._job is not None and not self._job.is_alive():
            ok, err = self._job_res
            if not ok and not self._error:
                self._error = err or "Afterburner"
            self._phase = "error" if self._error else ("aborted" if self._abort else "done")
        i = min(self._i, len(self.keys) - 1) if self.keys else 0
        return State(self._phase, self.keys[i] if self.keys else "", i + 1, len(self.keys), self._run + 1,
                     self.runs, self._temp, self._error, self.booked[-1] if self.booked else None, self._note)

    # ── results ──────────────────────────────────────────────────────────────
    def summary(self) -> dict:
        """{key: {test: {"score": mean, "power_w": mean or 0, "runs": n, "perf_pct": vs stock or None,
        "power_pct": vs stock or None}}} — means over the runs of that profile and test."""
        acc: dict = {}
        for b in self.booked:
            d = acc.setdefault(b.key, {}).setdefault(b.test, {"scores": [], "powers": []})
            d["scores"].append(b.score)
            if b.power_w > 0:
                d["powers"].append(b.power_w)
        out: dict = {}
        for key, tests in acc.items():
            for test, d in tests.items():
                sc = sum(d["scores"]) / len(d["scores"])
                pw = sum(d["powers"]) / len(d["powers"]) if d["powers"] else 0.0
                out.setdefault(key, {})[test] = {"score": round(sc), "power_w": round(pw, 1), "runs": len(d["scores"]),
                                                 "perf_pct": None, "power_pct": None}
        base = out.get(STOCK, {})
        for key, tests in out.items():
            for test, d in tests.items():
                b = base.get(test)
                if key != STOCK and b and b["score"]:
                    d["perf_pct"] = round((d["score"] / b["score"] - 1) * 100, 1)
                    if d["power_w"] and b["power_w"]:
                        d["power_pct"] = round((d["power_w"] / b["power_w"] - 1) * 100, 1)
        return out

    def bench_entries(self) -> dict:
        """{profile name: {"3dmark:<test>": record}} for TuneProfile.bench — only tests stock ran too."""
        summ = self.summary()
        base = summ.get(STOCK, {})
        at = time.strftime("%Y-%m-%dT%H:%M:%S")
        out: dict = {}
        for key, tests in summ.items():
            if key == STOCK:
                continue
            for test, d in tests.items():
                b = base.get(test)
                if not b:
                    continue
                out.setdefault(key, {})[f"3dmark:{test}"] = {
                    "name": f"3DMark {test}", "score": d["score"], "power_w": d["power_w"],
                    "stock_score": b["score"], "stock_power_w": b["power_w"], "runs": d["runs"], "at": at}
        return out
