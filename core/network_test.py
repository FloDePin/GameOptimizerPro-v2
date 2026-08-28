"""
GameOptimizerPro v2.1.1 — Network Latency Test
Pingt Gateway + öffentliche DNS-Server und misst Latenz, Paketverlust und Jitter.
Rein lesend, keine Systemänderung. Läuft über den Windows `ping`-Befehl.
"""

import subprocess, re, statistics, socket, os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PingResult:
    label:      str                 # z.B. "Gateway", "Cloudflare"
    host:       str                 # IP/Hostname
    reachable:  bool  = False
    min_ms:     float = 0.0
    avg_ms:     float = 0.0
    max_ms:     float = 0.0
    jitter_ms:  float = 0.0         # Standardabweichung der Antwortzeiten
    loss_pct:   float = 100.0
    rtts:       list  = field(default_factory=list)
    error:      str   = ""


# Feste Ziele (Gateway wird dynamisch ermittelt)
PUBLIC_TARGETS = [
    ("Cloudflare", "1.1.1.1"),
    ("Google DNS", "8.8.8.8"),
]


def get_default_gateway() -> Optional[str]:
    """Ermittelt die Standard-Gateway-IP (IPv4) ohne externe Abhängigkeiten."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -EA SilentlyContinue | "
             "Sort-Object RouteMetric | Select-Object -First 1).NextHop"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        gw = (out.stdout or "").strip().splitlines()
        for line in gw:
            line = line.strip()
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", line) and line != "0.0.0.0":
                return line
    except Exception:
        pass
    # Fallback: route print parsen
    try:
        out = subprocess.run(["route", "print", "0.0.0.0"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for line in (out.stdout or "").splitlines():
            m = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def ping(label: str, host: str, count: int = 10, timeout_ms: int = 1000) -> PingResult:
    """Pingt einen Host `count` mal und wertet Latenz/Loss/Jitter aus."""
    res = PingResult(label=label, host=host)
    if not host:
        res.error = "kein Host"
        return res
    try:
        if os.name == "nt":
            cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(max(1, timeout_ms // 1000)), host]
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=count * (timeout_ms / 1000) + 8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = (out.stdout or "") + (out.stderr or "")
        # Einzelne RTTs: "Zeit=12ms" (DE), "time=12ms" / "time<1ms" (EN), "Zeit<1ms"
        rtts = []
        for m in re.finditer(r"(?:time|Zeit)[=<]\s*(\d+)\s*ms", text, re.IGNORECASE):
            rtts.append(float(m.group(1)))
        res.rtts = rtts
        if rtts:
            res.reachable = True
            res.min_ms = min(rtts)
            res.max_ms = max(rtts)
            res.avg_ms = round(statistics.mean(rtts), 1)
            res.jitter_ms = round(statistics.pstdev(rtts), 1) if len(rtts) > 1 else 0.0
        # Paketverlust: "(0% Verlust)" / "(0% loss)" / "0% packet loss"
        m = re.search(r"(\d+)%\s*(?:Verlust|loss|packet loss)", text, re.IGNORECASE)
        if m:
            res.loss_pct = float(m.group(1))
        elif rtts:
            res.loss_pct = round((count - len(rtts)) / count * 100.0, 0)
        if not rtts and res.loss_pct >= 100.0:
            res.error = "keine Antwort"
    except subprocess.TimeoutExpired:
        res.error = "Timeout"
    except Exception as e:
        res.error = str(e)
    return res


def run_all(count: int = 10) -> list[PingResult]:
    """Testet Gateway + öffentliche DNS-Server. Gibt eine Liste von PingResults zurück."""
    results = []
    gw = get_default_gateway()
    if gw:
        results.append(ping("Gateway (Router)", gw, count=count))
    else:
        r = PingResult(label="Gateway (Router)", host="?")
        r.error = "Gateway nicht gefunden"
        results.append(r)
    for label, host in PUBLIC_TARGETS:
        results.append(ping(label, host, count=count))
    return results


def rate_latency(avg_ms: float) -> str:
    """Grobe Einordnung für die UI-Farbe."""
    if avg_ms <= 0:      return "unknown"
    if avg_ms < 20:      return "excellent"
    if avg_ms < 50:      return "good"
    if avg_ms < 100:     return "ok"
    return "poor"
