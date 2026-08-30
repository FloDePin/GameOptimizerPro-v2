"""
GameOptimizerPro v2.1 — BIOS Guide Database
Erkennt CPU/MB/GPU-Generation und gibt spezifische BIOS-Empfehlungen
plus passende Windows Registry-Tweaks aus.

Struktur:
  BiosSetting  — eine einzelne Empfehlung mit Menüpfad, Wert, Erklärung
  BiosProfile  — alle Settings für eine Hardware-Kombination
  match()      — findet das beste Profil für erkannte Hardware
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Risk levels ───────────────────────────────────────────────────────────────
SAFE     = "safe"       # Immer empfohlen, kein Risiko
MODERATE = "moderate"   # Empfohlen, kleines Risiko
ADVANCED = "advanced"   # Nur für Erfahrene


@dataclass
class BiosSetting:
    category:    str          # z.B. "Memory", "CPU", "GPU", "Power"
    name:        str          # Einstellungsname
    recommended: str          # Empfohlener Wert
    default:     str          # BIOS-Standard
    path:        str          # Menüpfad im BIOS
    explanation: str          # Warum diese Einstellung wichtig ist
    risk:        str = SAFE
    registry_tweak: Optional[str] = None   # Passender Windows Registry Key
    registry_value: Optional[str] = None
    registry_data:  Optional[str] = None
    impact:      str = "medium"   # "low" | "medium" | "high"
    detect_key:  Optional[str] = None  # Key for BiosDetector (e.g. "expo_xmp", "rebar")


@dataclass
class BiosProfile:
    id:           str
    name:         str          # z.B. "AMD Ryzen 9000 + X670 + NVIDIA RTX 40xx"
    cpu_match:    list[str]    # Substrings die in CPU-Name matchen
    mb_match:     list[str]    # Substrings die in MB-Name matchen (leer = alle)
    gpu_match:    list[str]    # Substrings die in GPU-Name matchen (leer = alle)
    settings:     list[BiosSetting] = field(default_factory=list)
    notes:        str = ""


# ── Gemeinsame AMD-Zusatz-Einstellungen (AM4 + AM5) ──────────────────────────
# Frische Objekte pro Aufruf, damit sie nicht profilübergreifend geteilt werden.
def _amd_extra_latency() -> list:
    return [
        BiosSetting(
            category="Boot",
            name="Launch CSM (Legacy-Modus)",
            recommended="Disabled",
            default="Auto / Enabled",
            path="Boot → CSM Configuration → Launch CSM = Disabled",
            explanation="CSM ist der alte Legacy-BIOS-Kompatibilitätsmodus. Für Resizable BAR und "
                        "sauberes UEFI-Booten muss er aus sein. WICHTIG: nur deaktivieren, wenn Windows "
                        "bereits im UEFI-Modus (GPT-Datenträger) installiert ist — sonst startet das "
                        "System nicht mehr. Prüfen mit msinfo32 → 'BIOS-Modus: UEFI'.",
            risk=MODERATE,
            impact="medium",
        ),
        BiosSetting(
            category="CPU",
            name="Local APIC Mode = x2APIC",
            recommended="x2APIC",
            default="Auto",
            path="Advanced → AMD CBS → CPU Common Options → Local APIC Mode = x2APIC",
            explanation="x2APIC ist die moderne, effizientere Interrupt-Verwaltung — besonders bei "
                        "CPUs mit vielen Threads. Auf 'Auto' wählt das BIOS es meist ohnehin; explizit "
                        "'x2APIC' ist die saubere Einstellung. Kein Risiko auf aktuellem Windows.",
            risk=SAFE,
            impact="low",
        ),
        BiosSetting(
            category="CPU",
            name="Data Fabric (DF) C-States",
            recommended="Disabled",
            default="Auto / Enabled",
            path="Advanced → AMD Overclocking / CBS → DF C-States = Disabled",
            explanation="Verhindert, dass der Infinity-Fabric-Interconnect (zwischen CPU-Chiplets und "
                        "RAM) in Schlafzustände geht. Reduziert Latenz-Spikes — spürbar bei "
                        "latenzkritischem Gaming. Kostet minimal mehr Idle-Strom. Gilt für AM4 und AM5.",
            risk=MODERATE,
            impact="medium",
        ),
        _vendor_autoinstall(),
    ]


def _vendor_autoinstall():
    """Herstellerübergreifend (ASUS/MSI/Gigabyte/ASRock) — verhindert Mainboard-Bloatware."""
    return BiosSetting(
        category="Boot",
        name="Auto-Install von Mainboard-Utilities deaktivieren",
        recommended="Disabled",
        default="Enabled",
        path="ASUS: Tool → Auto Install ASUS Utilities = Disabled  |  "
             "MSI: Settings → Advanced → MSI Driver Utility Installer = Disabled  |  "
             "Gigabyte: Settings → Gigabyte Utilities Downloader Configuration = Disabled  |  "
             "ASRock: Tool → Auto Driver Installer = Disabled",
        explanation="Verhindert, dass das Mainboard beim ersten Windows-Start automatisch "
                    "Hersteller-Software, Hintergrunddienste und Treiber-Downloader installiert "
                    "(Armoury Crate, MSI Center, App Center …) — ungefragte Bloatware auf UEFI-Ebene. "
                    "Treiber bei Bedarf sauber direkt von der Hersteller-Website ziehen.",
        risk=SAFE,
        impact="medium",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BIOS PROFILES DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

PROFILES: list[BiosProfile] = [

    # ── AMD Ryzen 9000 Series (Zen 5) — X670 / B650 ──────────────────────────
    BiosProfile(
        id="amd_zen5_x670",
        name="AMD Ryzen 9000 (Zen 5) + X670/B650",
        cpu_match=["9900X", "9800X3D", "9700X", "9600X", "9500X"],
        mb_match=[],  # Alle AM5-Boards
        gpu_match=[],
        notes="Ryzen 9000 Zen 5 — AM5 Plattform. EXPO für RAM dringend empfohlen.",
        settings=[
            BiosSetting(
                category="Memory",
                name="EXPO / XMP Profil",
                recommended="Profil 1 (EXPO)",
                default="Disabled",
                path="MIT → Advanced Memory Settings → EXPO/XMP",
                explanation="Ohne EXPO läuft dein RAM auf 4800 MHz statt dem Nennwert. "
                            "Bei 6000 MHz RAM bringt EXPO massiven Performance-Unterschied "
                            "vor allem bei Ryzen durch den Infinity Fabric Link.",
                risk=SAFE,
                impact="high",
                detect_key="expo_xmp"
            ),
            BiosSetting(
                category="Memory",
                name="FCLK Frequency",
                recommended="2000 MHz (bei 6000MT/s RAM)",
                default="Auto",
                path="MIT → Advanced Memory Settings → FCLK Frequency",
                explanation="FCLK sollte halb so hoch wie die effektive RAM-Frequenz sein "
                            "(6000 MT/s = 3000 MHz DDR = 1500 MHz FCLK... aber 2:1 Ratio "
                            "bei 6000 MT/s = FCLK 2000). Falsche Einstellung = Stabilitätsprobleme.",
                risk=MODERATE,
                impact="high",
            ),
            BiosSetting(
                category="CPU",
                name="Precision Boost Overdrive (PBO)",
                recommended="Advanced → Scalar 10x",
                default="Disabled",
                path="MIT → Advanced CPU Core Settings → AMD Overclocking → PBO",
                explanation="PBO erlaubt der CPU kurzfristig über das TDP-Limit zu boosten. "
                            "Bei guter Kühlung bringt PBO 5-15% mehr Single-Core Leistung "
                            "ohne manuelle Eingriffe. Scalar 10x = maximale Flexibilität.",
                risk=MODERATE,
                impact="high",
                registry_tweak=r"HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings\54533251-82be-4824-96c1-47b60b740d00\be337238-0d82-4146-a960-4f3749d470c7",
                registry_value="Attributes",
                registry_data="0",
                detect_key="pbo"
            ),
            BiosSetting(
                category="CPU",
                name="CPU Core Performance Boost",
                recommended="Enabled",
                default="Enabled",
                path="MIT → Advanced CPU Core Settings → Core Performance Boost",
                explanation="Muss aktiviert sein damit Precision Boost und PBO funktionieren. "
                            "Ohne das läuft die CPU immer auf Basistakt.",
                risk=SAFE,
                impact="high",
                detect_key="pbo"
            ),
            BiosSetting(
                category="CPU",
                name="Global C-State Control",
                recommended="Enabled (Gaming: Disabled)",
                default="Enabled",
                path="MIT → Advanced CPU Core Settings → Global C-state Control",
                explanation="C-States sparen Strom wenn die CPU idle ist. Für Gaming kann "
                            "Disabled latenzärmer sein da kein Aufwachen aus Schlafzuständen. "
                            "Für normalen Betrieb: Enabled.",
                risk=MODERATE,
                impact="medium",
                detect_key="c_states"
            ),
            BiosSetting(
                category="Power",
                name="CPU PPT Limit",
                recommended="142W (Standard) oder Unlimited für PBO",
                default="142W",
                path="MIT → Advanced CPU Core Settings → AMD Overclocking → PBO → PPT Limit",
                explanation="Package Power Tracking — maximale Gesamtleistungsaufnahme. "
                            "Unlimited = CPU kann so viel nehmen wie nötig. Nur mit guter Kühlung.",
                risk=MODERATE,
                impact="high",
            ),
            BiosSetting(
                category="GPU",
                name="Resizable BAR (ReBAR)",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding → Enabled, "
                     "dann Settings → IO Ports → Re-Size BAR Support → Enabled",
                explanation="Erlaubt der CPU direkten Zugriff auf den gesamten GPU-VRAM. "
                            "Pflicht für NVIDIA RTX 30/40xx Smart Access Memory. "
                            "Bringt bis zu 15% mehr FPS in manchen Spielen.",
                risk=SAFE,
                impact="high",
                registry_tweak=r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                registry_value="HwSchMode",
                registry_data="2",
                detect_key="rebar"
            ),
            BiosSetting(
                category="GPU",
                name="Above 4G Decoding",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding",
                explanation="Voraussetzung für ReBAR. Ermöglicht Speichermapping über 4GB. "
                            "Ohne das funktioniert ReBAR nicht.",
                risk=SAFE,
                impact="medium",
                detect_key="above_4g"
            ),
            BiosSetting(
                category="Power",
                name="ErP Ready",
                recommended="Disabled",
                default="Disabled",
                path="Settings → Power → ErP Ready",
                explanation="ErP drosselt USB und Netzwerk im Standby stark. "
                            "Für Gaming-PCs deaktivieren — verhindert langsames Aufwachen "
                            "und Probleme mit USB-Headsets nach Standby.",
                risk=SAFE,
                impact="low",
            ),
            BiosSetting(
                category="Boot",
                name="Fast Boot",
                recommended="Enabled",
                default="Enabled",
                path="Settings → Boot → Fast Boot",
                explanation="Überspringt POST-Tests für schnelleren Start. "
                            "Kein Nachteil im normalen Betrieb.",
                risk=SAFE,
                impact="low",
                detect_key="fast_boot"
            ),
            BiosSetting(
                category="GPU",
                name="Integrierte Grafik (iGPU) deaktivieren",
                recommended="Disabled (nur mit dedizierter GPU)",
                default="Auto / Enabled",
                path="ASUS: Advanced → NB Configuration → Primary Video Device = PCIE, "
                     "Integrated Graphics = Disabled. Gigabyte: Settings → Miscellaneous → "
                     "iGPU Configuration = Disabled.",
                explanation="Alle AM5-Ryzen-Desktop-CPUs haben eine kleine integrierte Grafik "
                            "(RDNA2). Sie reserviert etwas System-RAM (UMA Frame Buffer, ~0,5–2 GB) "
                            "und bleibt als Gerät aktiv. Wenn du eine dedizierte Grafikkarte nutzt, "
                            "kannst du sie abschalten: gibt den reservierten RAM frei und entfernt "
                            "ein Hintergrundgerät. WICHTIG: danach funktionieren die Bildausgänge "
                            "des Mainboards nicht mehr (nur noch die der Grafikkarte), und du "
                            "verlierst die iGPU als Notfall-/Zweitausgabe sowie deren Video-Encoder. "
                            "Der FPS-Gewinn ist minimal — es ist eher Aufräumen als echter Boost.",
                risk=MODERATE,
                impact="low",
            ),
            *_amd_extra_latency(),
        ],
    ),

    # ── AMD Ryzen 7000 Series (Zen 4) — X670 / B650 ──────────────────────────
    BiosProfile(
        id="amd_zen4_x670",
        name="AMD Ryzen 7000 (Zen 4) + X670/B650",
        cpu_match=["7900X", "7800X3D", "7700X", "7700", "7600X", "7600", "7950X"],
        mb_match=[],
        gpu_match=[],
        notes="Ryzen 7000 Zen 4 — AM5. Ähnlich wie Zen 5 aber ältere BIOS-Versionen.",
        settings=[
            BiosSetting(
                category="Memory",
                name="EXPO / XMP Profil",
                recommended="Profil 1 (EXPO)",
                default="Disabled",
                path="MIT → Advanced Memory Settings → EXPO/XMP",
                explanation="Kritisch für AM5. Ohne EXPO läuft DDR5 auf 4800 MHz statt "
                            "dem Nennwert. Infinity Fabric profitiert massiv von höherem Takt.",
                risk=SAFE,
                impact="high",
                detect_key="expo_xmp"
            ),
            BiosSetting(
                category="CPU",
                name="Precision Boost Overdrive (PBO)",
                recommended="Enabled → Auto",
                default="Disabled",
                path="MIT → Advanced CPU Core Settings → AMD Overclocking → PBO",
                explanation="PBO2 auf Zen 4 sehr ausgereift. Auto-Modus ist für die meisten "
                            "Nutzer optimal — CPU regelt selbst je nach Temp und Last.",
                risk=MODERATE,
                impact="high",
                detect_key="pbo"
            ),
            BiosSetting(
                category="GPU",
                name="Resizable BAR",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding + Re-Size BAR Support",
                explanation="Wichtig für NVIDIA und AMD GPUs der aktuellen Generation.",
                risk=SAFE,
                impact="high",
                detect_key="rebar_intel"
            ),
            BiosSetting(
                category="GPU",
                name="Integrierte Grafik (iGPU) deaktivieren",
                recommended="Disabled (nur mit dedizierter GPU)",
                default="Auto / Enabled",
                path="ASUS: Advanced → NB Configuration → Primary Video Device = PCIE, "
                     "Integrated Graphics = Disabled. Gigabyte: Settings → Miscellaneous → "
                     "iGPU Configuration = Disabled.",
                explanation="Ryzen 7000 Desktop-CPUs haben eine kleine integrierte RDNA2-Grafik, "
                            "die etwas System-RAM reserviert (UMA Frame Buffer, ~0,5–2 GB) und als "
                            "Gerät aktiv bleibt. Mit dedizierter Grafikkarte abschaltbar — gibt den "
                            "RAM frei und entfernt ein Hintergrundgerät. WICHTIG: danach sind die "
                            "Mainboard-Bildausgänge tot (nur noch die der Grafikkarte), und die iGPU "
                            "als Notfall-Ausgabe/Video-Encoder entfällt. FPS-Gewinn ist minimal.",
                risk=MODERATE,
                impact="low",
            ),
            *_amd_extra_latency(),
        ],
    ),

    # ── AMD Ryzen 5000 Series (Zen 3) — X570 / B550 ──────────────────────────
    BiosProfile(
        id="amd_zen3_x570",
        name="AMD Ryzen 5000 (Zen 3) + X570/B550",
        cpu_match=["5900X", "5800X3D", "5800X", "5700X", "5600X", "5600", "5950X"],
        mb_match=[],
        gpu_match=[],
        notes="Ryzen 5000 Zen 3 — AM4. Sehr mature Plattform, gute BIOS-Unterstützung.",
        settings=[
            BiosSetting(
                category="Memory",
                name="XMP / DOCP Profil",
                recommended="Profil 1 (XMP/DOCP)",
                default="Disabled",
                path="MIT → Advanced Memory Settings → Extreme Memory Profile (X.M.P.)",
                explanation="AM4 nutzt DDR4. DOCP ist AMDs Bezeichnung für XMP. "
                            "Für beste Leistung: DDR4-3600 CL16 mit 1:1 Infinity Fabric Ratio.",
                risk=SAFE,
                impact="high",
                detect_key="expo_xmp"
            ),
            BiosSetting(
                category="Memory",
                name="FCLK Frequency",
                recommended="1800 MHz (bei DDR4-3600)",
                default="Auto",
                path="MIT → Advanced Memory Settings → FCLK Frequency",
                explanation="1:1 Ratio FCLK=MCLK bei DDR4-3600 = maximale Bandbreite. "
                            "Bei DDR4-3800+ kann 2:1 Ratio nötig sein.",
                risk=MODERATE,
                impact="high",
            ),
            BiosSetting(
                category="CPU",
                name="Precision Boost Overdrive (PBO)",
                recommended="Enabled",
                default="Disabled",
                path="MIT → Advanced CPU Core Settings → AMD Overclocking → Precision Boost Overdrive",
                explanation="Auf Zen 3 sehr empfohlen. Bringt messbar mehr Boost-Frequenz "
                            "bei guter Kühlung. Curve Optimizer für einzelne Kerne optional.",
                risk=MODERATE,
                impact="high",
                detect_key="pbo"
            ),
            BiosSetting(
                category="GPU",
                name="Above 4G Decoding + ReBAR",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding",
                explanation="X570/B550 unterstützt ReBAR. Wichtig für RTX 30xx+.",
                risk=SAFE,
                impact="medium",
                detect_key="rebar"
            ),
            *_amd_extra_latency(),
        ],
    ),

    # ── Intel Core 13th/14th Gen (Raptor Lake) — Z790 / Z690 ────────────────
    BiosProfile(
        id="intel_rapterlake_z790",
        name="Intel Core 13th/14th Gen (Raptor Lake) + Z790/Z690",
        cpu_match=["13900", "13700", "13600", "14900", "14700", "14600",
                   "i9-13", "i7-13", "i5-13", "i9-14", "i7-14", "i5-14"],
        mb_match=["Z790", "Z690", "B760", "B660"],
        gpu_match=[],
        notes="Intel Raptor Lake. Wichtig: Intel-typische BIOS-Inflation der Power Limits beachten.",
        settings=[
            BiosSetting(
                category="Memory",
                name="XMP Profil",
                recommended="Profil 1 (XMP 3.0)",
                default="Disabled",
                path="Tweaker → Extreme Memory Profile (X.M.P.)",
                explanation="DDR5 läuft ohne XMP auf 4800 MHz. Mit XMP 3.0 "
                            "auf dem Nennwert (5600-7200 MHz). Großer Gaming-Unterschied.",
                risk=SAFE,
                impact="high",
                detect_key="xmp_intel"
            ),
            BiosSetting(
                category="CPU",
                name="Power Limits (PL1 / PL2)",
                recommended="PL1=125W PL2=253W (Intel Spec)",
                default="Unlimited (Board-Hersteller inflationär)",
                path="Tweaker → Advanced CPU Settings → CPU Power Limit",
                explanation="Viele Boards setzen PL1/PL2 auf Unlimited. Das verursacht "
                            "thermisches Throttling und instabile Boost-Frequenzen. "
                            "Intel-Spec-Werte = stabileres, vorhersagbares Verhalten.",
                risk=MODERATE,
                impact="high",
            ),
            BiosSetting(
                category="CPU",
                name="Intel Turbo Boost Max Technology 3.0",
                recommended="Enabled",
                default="Enabled",
                path="Tweaker → Advanced CPU Settings → Intel Turbo Boost Max Technology",
                explanation="Lenkt Last auf die leistungsfähigsten Kerne. "
                            "Messbar besser für Single-Threaded Gaming.",
                risk=SAFE,
                impact="medium",
            ),
            BiosSetting(
                category="CPU",
                name="Hyper-Threading",
                recommended="Enabled (Gaming: testen)",
                default="Enabled",
                path="Tweaker → Advanced CPU Settings → Hyper-Threading Technology",
                explanation="Für die meisten Spiele empfohlen. Wenige ältere Titel "
                            "profitieren von deaktiviertem HT — selten nötig.",
                risk=SAFE,
                impact="low",
            ),
            BiosSetting(
                category="GPU",
                name="Resizable BAR",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding → On, "
                     "dann Peripherals → Re-Size BAR Support → Enabled",
                explanation="Intel Z790 unterstützt ReBAR vollständig. "
                            "Pflicht für RTX 40xx maximale Performance.",
                risk=SAFE,
                impact="high",
                detect_key="rebar_intel"
            ),
            BiosSetting(
                category="Power",
                name="CPU SVID Support",
                recommended="Enabled",
                default="Enabled",
                path="Tweaker → Advanced CPU Settings → CPU SVID Support",
                explanation="Erlaubt dem VRM die Spannung dynamisch anzupassen. "
                            "Disabled = feste hohe Spannung = mehr Wärme.",
                risk=SAFE,
                impact="medium",
            ),
            _vendor_autoinstall(),
        ],
    ),

    # ── Intel Core 12th Gen (Alder Lake) — Z690 / B660 ──────────────────────
    BiosProfile(
        id="intel_alderlake_z690",
        name="Intel Core 12th Gen (Alder Lake) + Z690/B660",
        cpu_match=["12900", "12700", "12600", "12400",
                   "i9-12", "i7-12", "i5-12"],
        mb_match=["Z690", "B660", "H670"],
        gpu_match=[],
        notes="Erste Generation mit P/E-Core Mix. Windows 11 Scheduler empfohlen.",
        settings=[
            BiosSetting(
                category="Memory",
                name="XMP Profil",
                recommended="Profil 1",
                default="Disabled",
                path="Tweaker → Extreme Memory Profile",
                explanation="Alder Lake unterstützt DDR4 und DDR5. "
                            "XMP aktivieren für RAM-Nennwert.",
                risk=SAFE,
                impact="high",
                detect_key="xmp_intel"
            ),
            BiosSetting(
                category="CPU",
                name="Intel Thread Director",
                recommended="Enabled",
                default="Enabled",
                path="Tweaker → Advanced CPU Settings → Intel Thread Director",
                explanation="Notwendig damit Windows 11 P-Cores für Gaming-Threads "
                            "und E-Cores für Hintergrundprozesse nutzt.",
                risk=SAFE,
                impact="high",
                registry_tweak=r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel",
                registry_value="GlobalTimerResolutionRequests",
                registry_data="1",
            ),
            BiosSetting(
                category="GPU",
                name="Resizable BAR",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding + Re-Size BAR",
                explanation="Z690 mit aktuellem BIOS unterstützt ReBAR vollständig.",
                risk=SAFE,
                impact="high",
                detect_key="rebar_intel"
            ),
            _vendor_autoinstall(),
        ],
    ),

    # ── AMD Ryzen 7000/9000 + NVIDIA RTX 40xx spezifisch ────────────────────
    BiosProfile(
        id="amd_am5_nvidia_rtx40",
        name="AMD AM5 + NVIDIA RTX 40xx (Zusatz-Einstellungen)",
        cpu_match=["9800X3D", "9900X", "7800X3D", "7900X", "9700X", "7700X"],
        mb_match=[],
        gpu_match=["RTX 40", "RTX 4080", "RTX 4090", "RTX 4070", "RTX 4060"],
        notes="Kombinations-spezifische Empfehlungen für AM5 + Ada Lovelace.",
        settings=[
            BiosSetting(
                category="GPU",
                name="PCIe Gen 5 x16",
                recommended="Gen 5 (Auto)",
                default="Auto",
                path="Settings → IO Ports → PCIEX16 Slot Configuration → PCIe 5.0",
                explanation="RTX 40xx nutzt PCIe 4.0 x16 oder PCIe 5.0 x16. "
                            "In der Praxis kein messbarer Unterschied zwischen Gen4 und Gen5 "
                            "bei aktuellen GPUs — Auto ist optimal.",
                risk=SAFE,
                impact="low",
            ),
            BiosSetting(
                category="GPU",
                name="NVIDIA G-Sync / VRR Support",
                recommended="Enabled (wenn Monitor unterstützt)",
                default="Depends",
                path="Display → G-Sync oder VRR im Monitor-OSD",
                explanation="Kein BIOS-Setting direkt, aber ReBAR muss für G-Sync Pulsar "
                            "(auf RTX 40xx) aktiviert sein. In NVIDIA-Treiber: "
                            "G-Sync kompatibel aktivieren.",
                risk=SAFE,
                impact="medium",
                detect_key="hags"
            ),
            BiosSetting(
                category="Memory",
                name="EXPO + RCOMP Optimierung",
                recommended="EXPO Profil + RCOMP Auto",
                default="Jedec",
                path="MIT → Advanced Memory Settings → Memory Subtimings → RCOMP",
                explanation="Bei Gigabyte X670: RCOMP auf Auto lassen wenn EXPO aktiv. "
                            "Manuelles RCOMP nur bei Stabilitätsproblemen mit hohem RAM-Takt.",
                risk=MODERATE,
                impact="medium",
            ),
        ],
    ),

    # ── Generisch AMD AM4 ────────────────────────────────────────────────────
    BiosProfile(
        id="amd_am4_generic",
        name="AMD AM4 (generisch — X370/X470/X570/B450/B550)",
        cpu_match=["Ryzen 3", "Ryzen 5", "Ryzen 7", "Ryzen 9"],
        mb_match=["X370", "X470", "X570", "B450", "B550", "A520"],
        gpu_match=[],
        notes="Generische AM4-Empfehlungen. Gilt für Ryzen 1000-5000.",
        settings=[
            BiosSetting(
                category="Memory",
                name="XMP / DOCP",
                recommended="Profil 1",
                default="Disabled",
                path="MIT / AI Tweaker → Extreme Memory Profile",
                explanation="DDR4 XMP/DOCP für korrekten RAM-Takt aktivieren.",
                risk=SAFE,
                impact="high",
            ),
            BiosSetting(
                category="CPU",
                name="Core Performance Boost",
                recommended="Enabled",
                default="Enabled",
                path="MIT → Advanced CPU Settings → Core Performance Boost",
                explanation="Ermöglicht automatisches Boosten über Basistakt.",
                risk=SAFE,
                impact="high",
            ),
        ],
    ),

    # ── Generisch Intel LGA1700 ───────────────────────────────────────────────
    BiosProfile(
        id="intel_lga1700_generic",
        name="Intel LGA1700 (generisch — Z690/Z790/B660/B760)",
        cpu_match=["Core i9", "Core i7", "Core i5", "Core i3"],
        mb_match=["Z790", "Z690", "B760", "B660", "H770", "H670"],
        gpu_match=[],
        notes="Generische LGA1700 Intel-Empfehlungen.",
        settings=[
            BiosSetting(
                category="Memory",
                name="XMP Profil",
                recommended="Profil 1",
                default="Disabled",
                path="Tweaker → Extreme Memory Profile (X.M.P.)",
                explanation="XMP für korrekten DDR4/DDR5-Takt aktivieren.",
                risk=SAFE,
                impact="high",
                detect_key="xmp_intel"
            ),
            BiosSetting(
                category="GPU",
                name="Resizable BAR",
                recommended="Enabled",
                default="Disabled",
                path="Settings → IO Ports → Above 4G Decoding",
                explanation="ReBAR für aktuelle NVIDIA/AMD GPUs aktivieren.",
                risk=SAFE,
                impact="high",
                detect_key="rebar_intel"
            ),
        ],
    ),
]


# ── Matcher ────────────────────────────────────────────────────────────────────

def match_profiles(cpu_name: str, mb_manufacturer: str, mb_product: str,
                   gpu_name: str) -> list[BiosProfile]:
    """
    Returns all matching profiles sorted by specificity.
    Most specific first (kombinations-Profile vor generischen).
    """
    cpu_str = cpu_name.upper()
    mb_str  = f"{mb_manufacturer} {mb_product}".upper()
    gpu_str = gpu_name.upper()

    matched = []
    for profile in PROFILES:
        cpu_match = any(s.upper() in cpu_str for s in profile.cpu_match)
        mb_match  = (not profile.mb_match or
                     any(s.upper() in mb_str for s in profile.mb_match))
        gpu_match = (not profile.gpu_match or
                     any(s.upper() in gpu_str for s in profile.gpu_match))

        if cpu_match and mb_match and gpu_match:
            # Score: more specific = higher score
            score = (len(profile.cpu_match) * 2
                     + len(profile.mb_match) * 3
                     + len(profile.gpu_match) * 3)
            matched.append((score, profile))

    matched.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in matched]


def get_impact_color(impact: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(impact, "#6b7280")

def get_risk_color(risk: str) -> str:
    return {"safe": "#22c55e", "moderate": "#f59e0b", "advanced": "#ef4444"}.get(risk, "#6b7280")
