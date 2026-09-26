"""
GameOptimizerPro v2.1 — Tune History
Liest alle .log Dateien aus dem logs/ Ordner und parst die Tune-Runs.
"""

import os, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TuneRun:
    filename:    str
    date:        str
    mode:        str   # OC / UV / OC+UV
    core_offset: int   = 0
    power_pct:   int   = 100
    avg_volt_mv: int   = 0
    max_temp:    float = 0.0
    score:       int   = 0
    gpu_name:    str   = ""
    passed:      bool  = False
    log_lines:   list  = field(default_factory=list)


class TuneHistory:
    def __init__(self, logs_dir: str):
        self.logs_dir = Path(logs_dir)

    # Header written by the tuner:  "... Auto-Tune [OC UV]"  (mode.value upper-cased,
    # "_" -> " "). The old regex also matched the logger's "[INFO]" level tag in
    # front of it, so every run showed mode "INFO".
    _MODE_RE = re.compile(r"Auto-Tune\s+\[([A-Z0-9 _+]+)\]")
    _MODE_LABEL = {
        "OC ONLY": "OC", "UV ONLY": "UV", "OC UV": "OC+UV", "FULL": "FULL",
        "VF ONLY": "VF", "MEM ONLY": "MEM",
    }

    def _prune_empty(self):
        """Older versions created an EMPTY tune_*.log at every app start (the log
        file was opened when the tuner object was built, not when a tune ran).
        Remove those 0-byte leftovers; the age check avoids a log that is being
        created right now."""
        import time as _t
        for f in self.logs_dir.glob("tune_*.log"):
            try:
                st = f.stat()
                if st.st_size == 0 and _t.time() - st.st_mtime > 120:
                    f.unlink()
            except OSError:
                pass

    def get_runs(self) -> list[TuneRun]:
        """Parse all tune_*.log files and return TuneRun list sorted newest first."""
        runs = []
        if not self.logs_dir.exists():
            return runs
        self._prune_empty()

        for log_file in sorted(self.logs_dir.glob("tune_*.log"), reverse=True):
            run = self._parse_log(log_file)
            if run:
                runs.append(run)
        return runs

    def _parse_log(self, path: Path) -> Optional[TuneRun]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except:
            return None

        if not lines:
            return None

        run = TuneRun(
            filename=path.name,
            date=path.name.replace("tune_", "").replace(".log", ""),
            log_lines=lines,
            mode="Unknown",
        )

        # Format date nicely: 20260524_193045 → 24.05.2026 19:30:45
        try:
            d = run.date
            run.date = f"{d[6:8]}.{d[4:6]}.{d[0:4]} {d[9:11]}:{d[11:13]}:{d[13:15]}"
        except:
            pass

        for line in lines:
            # Extract mode
            m = self._MODE_RE.search(line)
            if m:
                raw_mode = m.group(1).strip().replace("_", " ")
                run.mode = self._MODE_LABEL.get(raw_mode, raw_mode)

            # Extract results
            if "Core offset:" in line or "Core offset" in line:
                m2 = re.search(r'\+(\d+)MHz', line)
                if m2: run.core_offset = int(m2.group(1))

            if "Power limit:" in line:
                m2 = re.search(r'(\d+)%', line)
                if m2: run.power_pct = int(m2.group(1))

            if "Avg voltage:" in line:
                m2 = re.search(r'(\d+)mV', line)
                if m2: run.avg_volt_mv = int(m2.group(1))

            if "Max temp:" in line:
                m2 = re.search(r'([\d.]+)°C', line)
                if m2: run.max_temp = float(m2.group(1))

            if "Score:" in line:
                m2 = re.search(r'(\d+)/100', line)
                if m2: run.score = int(m2.group(1))

            if "Profile saved:" in line:
                run.passed = True

            # GPU name from the tuner's "GPU: <name>" line. Log lines carry a
            # "<timestamp> [INFO]" prefix, so the old startswith("GPU:") never
            # matched; the old character class also cut names at "(" or "-".
            if not run.gpu_name:
                m2 = re.search(r'(?:^|\]\s+)GPU:\s*(.+?)\s*$', line)
                if m2:
                    run.gpu_name = m2.group(1).strip()

        return run if run.mode != "Unknown" or run.passed else None
