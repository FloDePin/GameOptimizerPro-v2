"""
GameOptimizerPro v2.1 — BIOS State Detector
Liest den tatsächlichen System-Zustand aus um zu erkennen ob eine
BIOS-Einstellung bereits aktiv ist.
Gibt für jede BiosSetting-ID einen DetectResult zurück.
"""

import subprocess, os, struct
from dataclasses import dataclass
from typing import Optional


@dataclass
class DetectResult:
    setting_id:  str
    active:      bool           # True = Einstellung ist bereits aktiv/korrekt
    detected_val: str = ""      # Was wir tatsächlich gemessen haben
    confidence:  str = "high"   # "high" | "medium" | "low"
    note:        str = ""


def _run_ps(cmd: str) -> str:
    """Run PowerShell silently, return stdout."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        si = None
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
             "-Command", cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            creationflags=flags, startupinfo=si
        )
        return r.stdout.strip()
    except:
        return ""


# Ein einziger PowerShell-Aufruf sammelt ALLE Rohwerte in eine JSON-Hashtable.
# Früher: ~8 separate powershell.exe-Kaltstarts (je ~0,5-1s) beim Öffnen des
# BIOS-Tabs. Jetzt: 1 Aufruf -> Detection ist ~5-8x schneller.
_BUNDLE_PS = r"""
$d=@{}
$d.ram_speed=(Get-CimInstance Win32_PhysicalMemory -EA SilentlyContinue | Sort-Object Speed -Descending | Select-Object -First 1).Speed
$d.hwsch=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name HwSchMode -EA SilentlyContinue).HwSchMode
$d.vram=(Get-CimInstance Win32_VideoController -EA SilentlyContinue | Where-Object { $_.Name -notmatch 'Microsoft' } | Select-Object -First 1).AdapterRAM
try { $d.secureboot=[bool](Confirm-SecureBootUEFI) } catch { $d.secureboot=$null }
$d.hiberboot=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -EA SilentlyContinue).HiberbootEnabled
$d.cpumax=(Get-CimInstance Win32_Processor -EA SilentlyContinue | Select-Object -First 1).MaxClockSpeed
$c=powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 2>$null | Out-String
$mm=[regex]::Matches($c,'0x[0-9a-fA-F]{8}')
$d.procmin=if($mm.Count -ge 2){[Convert]::ToInt32($mm[$mm.Count-2].Value.Substring(2),16)}else{-1}
$d | ConvertTo-Json -Compress
"""


class BiosDetector:
    """
    Detects current BIOS-related state via Windows APIs / Registry / WMI.
    detect_all() gathers everything in ONE PowerShell call; the individual
    detect_* methods build a DetectResult from that shared data (and still
    work standalone by gathering on demand).
    """

    # ── Shared gather (one PowerShell call) ───────────────────────────────────

    def _gather(self) -> dict:
        out = _run_ps(_BUNDLE_PS)
        try:
            import json
            d = json.loads(out) if out.strip() else {}
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _vram_mb(data: dict) -> float:
        try:
            return int(data.get("vram")) / (1024 * 1024)
        except Exception:
            return 0.0

    # ── Public: run all detections at once ────────────────────────────────────

    def detect_all(self) -> dict[str, DetectResult]:
        """Run all detectors from a single gathered snapshot."""
        data = self._gather()
        results = {}
        detectors = [
            ("expo_xmp",        self.detect_expo_xmp),
            ("rebar",           self.detect_rebar),
            ("above_4g",        self.detect_above_4g),
            ("hags",            self.detect_hags),
            ("secure_boot",     self.detect_secure_boot),
            ("fast_boot",       self.detect_fast_boot),
            ("pbo",             self.detect_pbo),
            ("c_states",        self.detect_c_states),
            ("xmp_intel",       self.detect_expo_xmp),     # same check
            ("rebar_rtx40",     self.detect_rebar),
            ("rebar_intel",     self.detect_rebar),
        ]
        for sid, fn in detectors:
            try:
                results[sid] = fn(data)
                results[sid].setting_id = sid
            except Exception as e:
                results[sid] = DetectResult(sid, False, "",
                                            "low", f"Detect error: {e}")
        return results

    # ── Individual detectors (data-driven) ────────────────────────────────────

    def detect_expo_xmp(self, data: dict = None) -> DetectResult:
        """XMP/EXPO active = RAM running above JEDEC baseline."""
        if data is None:
            data = self._gather()
        try:
            speed = int(data.get("ram_speed"))
            active = speed > 3200  # Above JEDEC baseline = profile active
            return DetectResult(
                "expo_xmp", active, f"{speed} MHz", "high",
                f"RAM läuft auf {speed} MHz"
                + (" — XMP/EXPO aktiv ✓" if active else " — möglicherweise JEDEC-Standard"))
        except Exception:
            return DetectResult("expo_xmp", False, str(data.get("ram_speed")), "low",
                                "RAM-Geschwindigkeit konnte nicht ermittelt werden")

    def detect_rebar(self, data: dict = None) -> DetectResult:
        """ReBAR = HwSchMode=2 AND full GPU VRAM visible."""
        if data is None:
            data = self._gather()
        hw_mode = str(data.get("hwsch") or "").strip()
        vram_mb = self._vram_mb(data)
        active = vram_mb > 1024 and hw_mode == "2"
        return DetectResult(
            "rebar", active,
            f"VRAM sichtbar: {vram_mb:.0f}MB, HwSchMode={hw_mode}", "medium",
            "ReBAR aktiv (VRAM voll zugänglich + HAGS)" if active
            else "ReBAR möglicherweise inaktiv — im BIOS prüfen")

    def detect_above_4g(self, data: dict = None) -> DetectResult:
        """Above 4G Decoding: GPU VRAM visible > 1GB."""
        if data is None:
            data = self._gather()
        vram_mb = self._vram_mb(data)
        if vram_mb <= 0:
            return DetectResult("above_4g", False, "", "low", "Konnte VRAM nicht lesen")
        active = vram_mb >= 1024
        return DetectResult(
            "above_4g", active, f"{vram_mb:.0f} MB VRAM sichtbar", "high",
            f"VRAM: {vram_mb:.0f}MB sichtbar — "
            + ("Above 4G wahrscheinlich aktiv ✓" if active
               else "könnte auf fehlendes Above 4G hinweisen"))

    def detect_hags(self, data: dict = None) -> DetectResult:
        """HAGS = HwSchMode registry = 2."""
        if data is None:
            data = self._gather()
        hw = str(data.get("hwsch") or "").strip()
        active = hw == "2"
        return DetectResult("hags", active, f"HwSchMode={hw}", "high",
                            "HAGS aktiv ✓" if active else "HAGS nicht aktiv")

    def detect_secure_boot(self, data: dict = None) -> DetectResult:
        """Secure Boot state."""
        if data is None:
            data = self._gather()
        val = data.get("secureboot")
        active = val is True
        return DetectResult("secure_boot", active, str(val), "high",
                            "Secure Boot: aktiv" if active else "Secure Boot: inaktiv")

    def detect_fast_boot(self, data: dict = None) -> DetectResult:
        """Fast Startup (HiberbootEnabled)."""
        if data is None:
            data = self._gather()
        hb = str(data.get("hiberboot") or "").strip()
        active = hb == "1"
        return DetectResult("fast_boot", active, f"HiberbootEnabled={hb}", "medium",
                            "Fast Startup (Windows) aktiv" if active else "Fast Startup inaktiv")

    def detect_pbo(self, data: dict = None) -> DetectResult:
        """PBO — nur grobe Heuristik (siehe Hinweis unten)."""
        if data is None:
            data = self._gather()
        try:
            max_clk = int(data.get("cpumax") or 0)
        except Exception:
            max_clk = 0
        # WMI MaxClockSpeed ist der GEMELDETE Maximaltakt, kein Live-Boost-Wert.
        # Bei älteren CPUs (z.B. Ryzen 5 3600, max ~4200) schlägt eine hohe Schwelle
        # trotz aktivem PBO fehl -> niedrigere Schwelle + LOW confidence + ehrlicher
        # Hinweis, dass PBO aus Windows nicht zuverlässig auslesbar ist.
        active = max_clk >= 4200
        return DetectResult(
            "pbo", active, f"Max Clock: {max_clk} MHz", "low",
            f"CPU meldet max {max_clk}MHz. Hinweis: PBO lässt sich aus Windows nicht "
            "zuverlässig auslesen — im Zweifel im BIOS prüfen. "
            + ("Boost-Takt sieht hoch aus ✓" if active
               else "bei älteren CPUs trotz aktivem PBO evtl. niedriger"))

    def detect_c_states(self, data: dict = None) -> DetectResult:
        """C-States via CPU minimum processor state (AC)."""
        if data is None:
            data = self._gather()
        try:
            val = int(data.get("procmin"))
            if val < 0:
                raise ValueError
            active = val == 0   # 0% min = C-states fully allowed
            return DetectResult(
                "c_states", active, f"Min CPU State: {val}%", "medium",
                f"CPU Minimalzustand: {val}% — "
                + ("C-States aktiv (Stromspar-Modi erlaubt)" if active
                   else f"Minimalzustand auf {val}% gesetzt"))
        except Exception:
            return DetectResult("c_states", True, "", "low",
                                "C-State-Status konnte nicht geprüft werden")
