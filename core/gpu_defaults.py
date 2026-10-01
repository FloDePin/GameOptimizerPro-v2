"""
GameOptimizerPro GPU Defaults
Erkennt die GPU-Generation am Namen und liefert konservative Tuning-Vorgaben:
Startwerte (damit beginnt der Rundum-Tuner, wenn es noch kein eigenes Profil
gibt) und Obergrenzen (bis dorthin wird höchstens gesucht). Jeder Schritt wird
ohnehin getestet — die Werte sparen nur Zeit und schlagen nichts Riskantes vor.

Grundlage (Stand 2025/26):
  * eigene Live-Messung RTX 4080 (Runde 13): Kurvenspitze +165 MHz, +220 bei
    925 mV (Grenze erreicht), Speicher +1000 unter Last auf der ganzen Karte
    stabil — +1500 aus dem reinen Bandbreiten-Test gab Bildfehler + Treiber-Reset;
  * TheFPSReview: RTX 5080 FE +350 MHz / Speicher +500 (30 → 31 Gbps, „nah am
    Limit“), RTX 5090 FE +270 MHz / Speicher +1500 (28 → 31 Gbps);
  * übliche Spannen älterer Generationen: Turing/Ampere +100…150 MHz,
    GDDR6X (RTX 3080/3090) wird heiß, Pascal +80…120 MHz.
Startwerte liegen deutlich unter diesen Ergebnissen, Speicher-Startwerte am
unteren Rand. AMD und Intel: der Auto-Tuner arbeitet mit MSI Afterburners
V/F-Kurve und NVML — beides gibt es nur für NVIDIA.
"""

from dataclasses import dataclass


@dataclass
class GpuDefaults:
    gpu_name:       str
    generation:     str
    # OC defaults
    core_step_mhz:  int
    core_max_mhz:   int
    mem_max_mhz:    int
    # UV defaults
    power_min_pct:  int
    power_step_pct: int
    # Safety
    max_temp_c:     int
    # Info
    notes:          str
    # Rundum-Tuner: where the search starts when there is no own profile yet
    core_start_mhz: int  = 0
    mem_start_mhz:  int  = 0
    vendor:         str  = "NVIDIA"
    tuner_supported: bool = True      # MSI Afterburner curve + NVML: NVIDIA only


def _nv(prefix, gen, step, core_max, core_start, mem_max, mem_start, power_min, notes,
        temp_max=85):
    return prefix, dict(generation=gen, core_step_mhz=step, core_max_mhz=core_max,
                        core_start_mhz=core_start, mem_max_mhz=mem_max,
                        mem_start_mhz=mem_start, power_min_pct=power_min, power_step_pct=5,
                        max_temp_c=temp_max, notes=notes)


_AMD_HINT = ("Auto-Tuner nicht unterstützt (braucht NVIDIA) — AMD Software: Adrenalin Edition "
             "→ Leistung → Tuning → automatisch undervolten / übertakten")
_INTEL_HINT = ("Auto-Tuner nicht unterstützt (braucht NVIDIA) — Intel Graphics Software → "
               "Leistung")


def _other(prefix, gen, vendor, notes):
    return prefix, dict(generation=gen, core_step_mhz=10, core_max_mhz=0, core_start_mhz=0,
                        mem_max_mhz=0, mem_start_mhz=0, power_min_pct=100, power_step_pct=5,
                        max_temp_c=85, notes=notes, vendor=vendor, tuner_supported=False)


# ── Generation table ──────────────────────────────────────────────────────────
# Matched top-down on the upper-cased name: most specific first. No bare
# "RTX 50" / "RTX 20": workstation cards are called "RTX 5000 Ada", "RTX 2000 Ada".

_TABLE = [
    # NVIDIA Blackwell (RTX 50) — large core headroom, GDDR7 varies a lot per card
    _nv("RTX 509", "Blackwell", 15, 300, 120, 1000, 250, 70,
        "RTX 5090 — ab Werk nah am Limit (FE: +270 MHz), GDDR7"),
    _nv("RTX 508", "Blackwell", 15, 400, 150, 1000, 250, 70,
        "RTX 5080 — viel Kern-Luft (FE: +350 MHz), GDDR7 teils schon bei +500 am Limit"),
    _nv("RTX 507", "Blackwell", 15, 400, 150, 1000, 250, 70,
        "RTX 5070 / 5070 Ti — viel Kern-Luft, GDDR7"),
    _nv("RTX 506", "Blackwell", 15, 350, 120, 1000, 250, 72,
        "RTX 5060 / 5060 Ti — GDDR7"),
    _nv("RTX 505", "Blackwell", 15, 300, 100, 800, 250, 75,
        "RTX 5050"),

    # NVIDIA Ada Lovelace (RTX 40) — memory max +1000: +1500 gave visible artifacts
    # (green speckles) and a driver reset in FurMark on a live RTX 4080.
    _nv("RTX 409", "Ada Lovelace", 15, 250, 90, 1000, 500, 65,
        "RTX 4090 — high TDP, good OC potential"),
    _nv("RTX 408", "Ada Lovelace", 15, 250, 90, 1000, 500, 65,
        "RTX 4080 — good OC and UV headroom (live: +165 at the top, +220 at 925 mV)"),
    _nv("RTX 407", "Ada Lovelace", 15, 220, 90, 1000, 500, 68,
        "RTX 4070 family — solid UV gains"),
    _nv("RTX 406", "Ada Lovelace", 12, 200, 75, 1000, 400, 70,
        "RTX 4060 family — moderate OC headroom"),
    _nv("RTX 40",  "Ada Lovelace", 15, 200, 75, 1000, 400, 68,
        "RTX 40-series — Ada Lovelace"),

    # NVIDIA Ampere (RTX 30) — GDDR6X on 3080/3090 runs hot: memory kept low
    _nv("RTX 309", "Ampere", 12, 180, 60, 800, 300, 70,
        "RTX 3090/Ti — high TDP, great UV gains, hot GDDR6X"),
    _nv("RTX 308", "Ampere", 12, 160, 60, 800, 300, 70,
        "RTX 3080 family — hot GDDR6X"),
    _nv("RTX 307", "Ampere", 10, 150, 60, 1000, 300, 72,
        "RTX 3070 family"),
    _nv("RTX 306", "Ampere", 10, 130, 45, 900, 300, 75,
        "RTX 3060 family"),
    _nv("RTX 305", "Ampere", 10, 120, 45, 800, 300, 75,
        "RTX 3050"),
    _nv("RTX 30",  "Ampere", 10, 150, 45, 800, 300, 72,
        "RTX 30-series — Ampere"),

    # NVIDIA Turing (RTX 20 / GTX 16)
    _nv("RTX 208", "Turing", 10, 120, 45, 800, 300, 75, "RTX 2080 family", temp_max=83),
    _nv("RTX 207", "Turing", 10, 110, 45, 800, 300, 75, "RTX 2070 family", temp_max=83),
    _nv("RTX 206", "Turing",  8, 100, 30, 700, 300, 78, "RTX 2060 family", temp_max=83),
    _nv("GTX 16",  "Turing",  8,  80, 30, 600, 200, 80, "GTX 16-series", temp_max=83),

    # NVIDIA Pascal (GTX 10)
    _nv("GTX 108", "Pascal",  8,  80, 30, 500, 200, 82, "GTX 1080 family", temp_max=83),
    _nv("GTX 107", "Pascal",  8,  80, 30, 500, 200, 82, "GTX 1070 family", temp_max=83),
    _nv("GTX 106", "Pascal",  6,  60, 20, 400, 150, 85, "GTX 1060 family", temp_max=83),
    _nv("GTX 10",  "Pascal",  6,  60, 20, 400, 150, 85, "GTX 10-series — Pascal", temp_max=83),

    # AMD / Intel — the Auto-Tuner needs MSI Afterburner's NVIDIA curve and NVML
    _other("RX 90",  "AMD RDNA 4", "AMD", _AMD_HINT),
    _other("RX 7",   "AMD RDNA 3", "AMD", _AMD_HINT),
    _other("RX 6",   "AMD RDNA 2", "AMD", _AMD_HINT),
    _other("RADEON", "AMD Radeon", "AMD", _AMD_HINT),
    _other("RX ",    "AMD Radeon", "AMD", _AMD_HINT),
    _other("ARC",    "Intel Arc",  "Intel", _INTEL_HINT),
]

_FALLBACK = GpuDefaults(
    gpu_name="Unknown",
    generation="Unknown",
    core_step_mhz=10,
    core_max_mhz=100,
    mem_max_mhz=500,
    power_min_pct=80,
    power_step_pct=5,
    max_temp_c=85,
    notes="Conservative generic defaults — GPU generation not recognized",
    core_start_mhz=0,
    mem_start_mhz=200,
)


def get_defaults(gpu_name: str) -> GpuDefaults:
    """Match GPU name to generation table and return safe defaults."""
    name_upper = (gpu_name or "").upper()
    for prefix, fields in _TABLE:
        if prefix.upper() in name_upper:
            return GpuDefaults(gpu_name=gpu_name, **fields)
    return GpuDefaults(
        gpu_name=gpu_name,
        generation="Unknown",
        core_step_mhz=_FALLBACK.core_step_mhz,
        core_max_mhz=_FALLBACK.core_max_mhz,
        mem_max_mhz=_FALLBACK.mem_max_mhz,
        power_min_pct=_FALLBACK.power_min_pct,
        power_step_pct=_FALLBACK.power_step_pct,
        max_temp_c=_FALLBACK.max_temp_c,
        notes=f"Unknown GPU: {gpu_name} — using conservative defaults",
        core_start_mhz=_FALLBACK.core_start_mhz,
        mem_start_mhz=_FALLBACK.mem_start_mhz,
    )
