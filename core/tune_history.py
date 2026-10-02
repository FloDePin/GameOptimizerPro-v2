"""
GameOptimizerPro v2.0 — Tune history
Reads every tune_*.log in logs/ and turns it into one TuneRun.

A finished run has a summary ("Profile saved: …", "Core offset: …"). A run that
failed or was stopped has none — its values then come from the steps: the last
configuration it tested ("Final test: …" / "Endtest: …"), the stage results
("Stage 1 done: best core = …"), the own curve of the All-round tuner, the
baseline. Stock values are shown as such (+0 MHz, 100 %), unknown ones as None.
`reason` says why a run has no profile. delete() removes runs (log + report).
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TuneRun:
    filename:    str
    date:        str
    mode:        str                      # OC / UV / OC+UV / Rundum …
    core_offset: Optional[int] = None     # None = unknown
    mem_offset:  Optional[int] = None
    power_pct:   Optional[int] = None
    avg_volt_mv: Optional[int] = None
    max_temp:    Optional[float] = None
    score:       int   = 0
    gpu_name:    str   = ""
    passed:      bool  = False
    reason:      str   = ""               # why there is no profile (failed / stopped runs)
    log_lines:   list  = field(default_factory=list)
    path:        str   = ""
    profile_name: str  = ""               # "Profile saved: <name>" (GPU profiles)


def _de() -> bool:
    try:
        from core.i18n import current_lang
        return current_lang() == "de"
    except Exception:
        return True


class TuneHistory:
    def __init__(self, logs_dir: str):
        self.logs_dir = Path(logs_dir)

    # Header written by the tuner: "... Auto-Tune [OC UV]" (mode.value upper-cased).
    _MODE_RE = re.compile(r"Auto-Tune\s+\[([A-Z0-9 _+]+)\]")
    _MODE_LABEL = {
        "OC ONLY": "OC", "UV ONLY": "UV", "OC UV": "OC+UV", "FULL": "FULL",
        "VF ONLY": "VF", "MEM ONLY": "MEM",
    }
    _MSG_RE = re.compile(r"^[^\[]*\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s?(.*)$")   # "<time> [LEVEL] msg"
    _TEMP_RE = re.compile(r"(?:avg=|temp=|max\.?\s|Temp\s)([\d.]+)\s?°C")

    def _prune_empty(self):
        """Older versions created an EMPTY tune_*.log at every app start. Remove
        those 0-byte leftovers; the age check spares a log being written now."""
        for f in self.logs_dir.glob("tune_*.log"):
            try:
                st = f.stat()
                if st.st_size == 0 and time.time() - st.st_mtime > 120:
                    f.unlink()
            except OSError:
                pass

    @staticmethod
    def _when(f: Path) -> str:
        """tune_YYYYMMDD_HHMMSS.log sorts by its name; anything else by its time stamp."""
        stem = f.name[5:-4]
        if len(stem) == 15 and stem[8] == "_" and (stem[:8] + stem[9:]).isdigit():
            return stem
        try:
            return time.strftime("%Y%m%d_%H%M%S", time.localtime(f.stat().st_mtime))
        except OSError:
            return ""

    def get_runs(self) -> list[TuneRun]:
        """All runs, newest first."""
        runs = []
        if not self.logs_dir.exists():
            return runs
        self._prune_empty()
        for log_file in sorted(self.logs_dir.glob("tune_*.log"), key=self._when, reverse=True):
            run = self._parse_log(log_file)
            if run:
                runs.append(run)
        return runs

    # ── deleting ──────────────────────────────────────────────────────────────

    def _report_of(self, log_file: Path) -> list[Path]:
        """The All-round report written at the end of this run (its time lies
        between the run's start and the log's last write)."""
        start = self._when(log_file)
        try:
            end = time.strftime("%Y%m%d_%H%M%S", time.localtime(log_file.stat().st_mtime + 60))
        except OSError:
            return []
        out = []
        for rep in self.logs_dir.glob("curve_report_*.txt"):
            stamp = rep.name[len("curve_report_"):-4]
            if start <= stamp <= end:
                out.append(rep)
        return out

    def delete(self, filenames) -> int:
        """Delete these runs (tune log + its report). -> number of runs deleted.
        Only tune_*.log files inside logs/ are touched."""
        n = 0
        for name in filenames:
            f = self.logs_dir / Path(str(name)).name
            if not (f.name.startswith("tune_") and f.suffix == ".log" and f.is_file()):
                continue
            for rep in self._report_of(f):
                try:
                    rep.unlink()
                except OSError:
                    pass
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n

    def delete_all(self) -> int:
        return self.delete([f.name for f in self.logs_dir.glob("tune_*.log")])

    # ── parsing ───────────────────────────────────────────────────────────────

    def _parse_log(self, path: Path) -> Optional[TuneRun]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return None
        if not lines:
            return None

        run = TuneRun(filename=path.name, date=path.name.replace("tune_", "").replace(".log", ""),
                      log_lines=lines, mode="Unknown", path=str(path))
        d = run.date
        if len(d) == 15 and d[8] == "_" and (d[:8] + d[9:]).isdigit():
            run.date = f"{d[6:8]}.{d[4:6]}.{d[0:4]} {d[9:11]}:{d[11:13]}:{d[13:15]}"

        summary: dict = {}             # values of the closing summary (finished runs)
        found: dict = {}               # values seen along the way
        stock: dict = {}               # All-round: voltage point -> stock clock
        temps: list = []
        errors: list = []
        aborted = complete = False
        final_failed = ""
        curve = False

        for raw in lines:
            m = self._MSG_RE.match(raw)
            level, msg = (m.group(1), m.group(2).strip()) if m else ("INFO", raw.strip())

            mm = self._MODE_RE.search(msg)
            if mm:
                raw_mode = mm.group(1).strip().replace("_", " ")
                run.mode = self._MODE_LABEL.get(raw_mode, raw_mode)
                if raw_mode == "CURVE":
                    curve = True
                    run.mode = "Rundum" if _de() else "All-round"
                continue
            if not run.gpu_name:
                g = re.match(r"GPU:\s*(.+?)\s*$", msg)
                if g:
                    run.gpu_name = g.group(1)
            for t in self._TEMP_RE.findall(msg):
                try:
                    temps.append(float(t))
                except ValueError:
                    pass

            # closing summary
            if msg.startswith("Profile saved:"):
                run.passed = True
                run.profile_name = msg[len("Profile saved:"):].strip()
            elif msg.startswith("Core offset:"):
                v = re.search(r"([+-]?\d+)\s*MHz", msg)
                if v:
                    summary["core"] = int(v.group(1))
            elif msg.startswith("Memory offset:"):
                v = re.search(r"([+-]?\d+)\s*MHz", msg)
                if v:
                    summary["mem"] = int(v.group(1))
            elif msg.startswith("Power limit:"):
                v = re.search(r"(\d+)\s*%", msg)
                if v:
                    summary["pwr"] = int(v.group(1))
            elif msg.startswith("Avg voltage:"):
                v = re.search(r"(\d+)\s*mV", msg)
                if v:
                    summary["volt"] = int(v.group(1))
            elif msg.startswith("Max temp:"):
                v = re.search(r"([\d.]+)\s*°C", msg)
                if v:
                    summary["temp"] = float(v.group(1))
            elif msg.startswith("Score:"):
                v = re.search(r"(\d+)/100", msg)
                if v:
                    run.score = int(v.group(1))

            # along the way
            elif msg.startswith("Baseline OK"):
                v = re.search(r"volt=(\d+)mV", msg)
                if v:
                    found.setdefault("volt", int(v.group(1)))
            elif msg.startswith("Stage 1 done"):
                v = re.search(r"\+(\d+)MHz", msg)
                if v:
                    found["core"] = int(v.group(1))
            elif msg.startswith("Stage 2 done"):
                v = re.search(r"(\d+)%", msg)
                if v:
                    found["pwr"] = int(v.group(1))
            elif msg.startswith("Stage 4 done"):
                v = re.search(r"\+(\d+)MHz", msg)
                if v:
                    found["mem"] = int(v.group(1))
            elif msg.startswith("Final test:"):
                # "Final test: +179MHz | 96% pwr | Mem+500MHz | 120s" — what was tested last
                c = re.search(r"Final test:\s*\+(\d+)MHz", msg)
                if c:
                    found["core"] = int(c.group(1))
                p = re.search(r"(\d+)% pwr", msg)
                if p:
                    found["pwr"] = int(p.group(1))
                mem = re.search(r"Mem\+(\d+)MHz", msg)
                found["mem"] = int(mem.group(1)) if mem else 0
            elif msg.startswith("Endtest:"):
                mem = re.search(r"Mem\+(\d+)MHz", msg)
                if mem:
                    found["mem"] = int(mem.group(1))
            elif re.match(r"(?:Speicher|Memory): .*→ \+(\d+) MHz", msg):
                found["mem"] = int(re.search(r"→ \+(\d+) MHz", msg).group(1))
            elif re.match(r"(?:Punkt|Point) \d+/\d+: \d+ mV \((?:Stock|stock) \d+ MHz\)", msg):
                v = re.match(r"(?:Punkt|Point) \d+/\d+: (\d+) mV \((?:Stock|stock) (\d+) MHz\)", msg)
                stock[int(v.group(1))] = int(v.group(2))
            elif msg.startswith("Eigene Kurve") or msg.startswith("Own curve"):
                pts = [(int(a), int(b)) for a, b in re.findall(r"(\d+) mV → (\d+) MHz", msg)]
                if pts:
                    top_mv, top_mhz = max(pts)
                    if top_mv in stock:
                        found["core"] = top_mhz - stock[top_mv]

            if level == "ERROR":
                errors.append(msg)
            if "Abbruch angefordert" in msg or "Aborted by user" in msg:
                aborted = True
            if "Auto-Tune Complete" in msg:
                complete = True
            if msg.startswith("Final failed") or msg.startswith("Final test ✗") or msg.startswith("Endtest ✗"):
                final_failed = msg

        run.core_offset = summary.get("core", found.get("core"))
        run.mem_offset = summary.get("mem", found.get("mem"))
        run.power_pct = summary.get("pwr", found.get("pwr"))
        run.avg_volt_mv = summary.get("volt", found.get("volt"))
        run.max_temp = summary.get("temp", max(temps) if temps else None)
        if run.passed:
            # a finished run without these lines left them at stock
            if run.power_pct is None:
                run.power_pct = 100
            if run.mem_offset is None:
                run.mem_offset = 0
            if run.core_offset is None:
                run.core_offset = 0
        else:
            de = _de()
            if aborted:
                run.reason = "abgebrochen" if de else "aborted"
            elif errors:
                run.reason = errors[-1]
            elif final_failed:
                why = re.search(r"\((.+)\)", final_failed)
                run.reason = (("Endtest fehlgeschlagen" if de else "final test failed")
                              + (f" ({why.group(1)})" if why else ""))
            elif complete:
                run.reason = "kein Profil gespeichert" if de else "no profile saved"
            else:
                run.reason = ("unterbrochen (App beendet / Absturz)" if de
                              else "interrupted (app closed / crash)")
        if curve and run.power_pct is None and run.core_offset is not None:
            run.power_pct = 100       # the All-round tuner only raises it for "max" (logged then)
        return run if run.mode != "Unknown" or run.passed else None
