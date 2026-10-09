"""
GameOptimizerPro v2.0 — BIOS Guide database

Every desktop platform since Intel's 8th gen / AMD's first Ryzen, each with the
settings that matter for games, and the menu path on ASUS, MSI, Gigabyte and
ASRock boards. The hardware detection only PRE-SELECTS the platform and the board
maker — every profile can be opened.

  BiosSetting  — one recommendation: value, menu path (per board maker), why
  BiosProfile  — one platform (CPU generation + socket / chipsets)
  PROFILES     — all platforms, newest first per vendor
  detect_profile() / vendor_of() — what the hardware detection picks

Menu names differ between BIOS versions — every path is the usual one; the
BIOS's own search (ASUS F9, MSI Ctrl+F) finds an option by its name.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Risk levels ───────────────────────────────────────────────────────────────
SAFE     = "safe"       # always recommended, no risk
MODERATE = "moderate"   # recommended, test stability afterwards
ADVANCED = "advanced"   # for experienced users only

# board makers: key, label
VENDORS = [("asus", "ASUS"), ("msi", "MSI"), ("gigabyte", "Gigabyte"), ("asrock", "ASRock"),
           ("other", "Andere / unbekannt")]


def vendor_of(manufacturer: str) -> str:
    """Board maker key from the WMI baseboard manufacturer."""
    m = (manufacturer or "").upper()
    if "ASUS" in m:
        return "asus"
    if "MICRO-STAR" in m or m.startswith("MSI"):
        return "msi"
    if "GIGABYTE" in m:
        return "gigabyte"
    if "ASROCK" in m:
        return "asrock"
    return "other"


@dataclass
class BiosSetting:
    category:    str          # "Memory" | "CPU" | "GPU" | "Power" | "Boot"
    name:        str
    recommended: str
    default:     str
    path:        str          # generic menu path (any board)
    explanation: str
    risk:        str = SAFE
    impact:      str = "medium"   # "low" | "medium" | "high"
    detect_key:  Optional[str] = None   # BiosDetector result that shows whether it is set
    paths:       dict = field(default_factory=dict)   # vendor key -> menu path
    key:         str = ""     # stable id (tests, de-duplication)

    def path_for(self, vendor: str) -> str:
        return self.paths.get(vendor) or self.path


@dataclass
class BiosProfile:
    id:        str
    name:      str
    cpus:      str            # which CPUs, as shown to the user
    platform:  str            # socket + chipsets
    brand:     str            # "amd" | "intel" | "any"
    settings:  list = field(default_factory=list)
    notes:     str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Setting builders — fresh objects per profile
# ═══════════════════════════════════════════════════════════════════════════════

def _memory_profile(brand: str, ddr: str, target: str, note: str = "") -> BiosSetting:
    amd = brand == "amd"
    name = ("EXPO-Profil" if ddr == "DDR5" else "D.O.C.P. / A-XMP-Profil") if amd else "XMP-Profil"
    paths = ({
        "asus": "Ai Tweaker → Ai Overclock Tuner → " + ("EXPO I" if ddr == "DDR5" else "D.O.C.P."),
        "msi": "OC → A-XMP / EXPO → Profile 1 (oder der EXPO-/A-XMP-Schalter im EZ-Mode)",
        "gigabyte": "Tweaker → Extreme Memory Profile (X.M.P.) / EXPO → Profile1 (auch im Easy Mode)",
        "asrock": "OC Tweaker → DRAM Profile Configuration → DRAM Profile Setting → EXPO/XMP-Profil 1",
    } if amd else {
        "asus": "Ai Tweaker → Ai Overclock Tuner → XMP I",
        "msi": "OC → Extreme Memory Profile (XMP) → Profile 1 (oder der XMP-Schalter im EZ-Mode)",
        "gigabyte": "Tweaker → Extreme Memory Profile (X.M.P.) → Profile1 (auch im Easy Mode)",
        "asrock": "OC Tweaker → DRAM Profile Configuration → XMP-Profil 1",
    })
    return BiosSetting(
        key="memory_profile", category="Memory", name=name,
        recommended=f"Profil 1 ({target})", default=f"Aus — JEDEC-Standardtakt",
        path="OC-/Tweaker-Menü → Speicherprofil (EXPO bzw. XMP/DOCP) → Profil 1",
        explanation=(f"Ohne Profil läuft der RAM nur mit dem langsamen {ddr}-Standardtakt — der größte "
                     f"kostenlose Gewinn im BIOS, vor allem für die 1-%-Lows in CPU-lastigen Spielen. "
                     + note + (" " if note else "")
                     + "Startet der PC danach nicht oder gibt es Abstürze: Profil 2 oder ein Takt-Schritt "
                       "niedriger; viele Boards setzen nach 3 Fehlstarts selbst zurück."),
        risk=SAFE, impact="high", detect_key="expo_xmp", paths=paths)


def _rebar(brand: str, note: str = "") -> BiosSetting:
    return BiosSetting(
        key="rebar", category="GPU", name="Resizable BAR (+ Above 4G Decoding)",
        recommended="Above 4G Decoding = Enabled, Re-Size BAR Support = Enabled", default="Disabled",
        path="PCI-/IO-Einstellungen → Above 4G Decoding = Enabled → Re-Size BAR Support = Enabled",
        explanation=("Die CPU darf den ganzen Grafikspeicher auf einmal ansprechen statt in 256-MB-Häppchen. "
                     "NVIDIA nutzt es für die Spiele, für die es im Treiber freigegeben ist; bei AMD-Karten "
                     "heißt es „Smart Access Memory“ und wirkt fast überall. Voraussetzung: CSM aus "
                     "(UEFI-Start). " + note).strip(),
        risk=SAFE, impact="high", detect_key="rebar", paths={
            "asus": "Advanced → PCI Subsystem Settings → Above 4G Decoding = Enabled → Re-Size BAR Support = Enabled",
            "msi": "Settings → Advanced → PCIe/PCI Sub-system Settings → Above 4G memory/Crypto Currency mining = "
                   "Enabled → Re-Size BAR Support = Enabled",
            "gigabyte": "Settings → IO Ports → Above 4G Decoding = Enabled → Re-Size BAR Support = Auto/Enabled",
            "asrock": "Advanced → PCI Configuration → Above 4G Decoding = Enabled → Re-Size BAR Support"
                      + (" (bei AMD-Boards auch „C.A.M.“)" if brand == "amd" else "") + " = Enabled",
        })


def _csm() -> BiosSetting:
    return BiosSetting(
        key="csm", category="Boot", name="CSM (Legacy-Start) aus", recommended="Disabled (reiner UEFI-Start)",
        default="je nach Board Auto / Enabled",
        path="Boot → CSM (Compatibility Support Module) → Disabled",
        explanation="Der alte Legacy-BIOS-Modus. Aus = Voraussetzung für Resizable BAR und Secure Boot. "
                    "WICHTIG: nur ausschalten, wenn Windows im UEFI-Modus installiert ist — prüfen mit "
                    "msinfo32 → „BIOS-Modus: UEFI“. Steht dort „Legacy“, startet Windows ohne CSM nicht.",
        risk=MODERATE, impact="medium", detect_key="csm", paths={
            "asus": "Boot → CSM (Compatibility Support Module) → Launch CSM = Disabled",
            "msi": "Settings → Advanced → Windows OS Configuration → BIOS UEFI/CSM Mode = UEFI",
            "gigabyte": "Boot → CSM Support = Disabled",
            "asrock": "Boot → CSM (Compatibility Support Module) → CSM = Disabled",
        })


def _secure_boot() -> BiosSetting:
    return BiosSetting(
        key="secure_boot", category="Boot", name="Secure Boot", recommended="Enabled",
        default="oft Disabled (bzw. „Other OS“)",
        path="Boot/Security → Secure Boot = Enabled",
        explanation="Bringt keine FPS, ist aber für immer mehr Spiele Pflicht: Valorant/Vanguard unter "
                    "Windows 11, Battlefield 6, Call of Duty und weitere Anti-Cheats starten ohne Secure "
                    "Boot nicht. Braucht CSM aus. Meldet das BIOS fehlende Schlüssel: „Restore Factory "
                    "Keys“ bzw. „Install default Secure Boot keys“.",
        risk=SAFE, impact="medium", detect_key="secure_boot", paths={
            "asus": "Boot → Secure Boot → OS Type = Windows UEFI mode",
            "msi": "Settings → Security → Secure Boot → Secure Boot = Enabled",
            "gigabyte": "Boot → Secure Boot → Secure Boot = Enabled",
            "asrock": "Security → Secure Boot → Secure Boot = Enabled",
        })


def _bios_update(what: str, risk: str = SAFE, impact: str = "medium") -> BiosSetting:
    return BiosSetting(
        key="bios_update", category="Boot", name="BIOS aktuell halten", recommended="neueste Version des Herstellers",
        default="Auslieferungsstand",
        path="Flash-Tool im BIOS — Datei von der Support-Seite des Boards auf einen FAT32-USB-Stick",
        explanation=what + " Vor dem Flashen das EXPO/XMP-Profil notieren (danach ist alles auf Standard) "
                           "und den PC währenddessen nicht ausschalten.",
        risk=risk, impact=impact, paths={
            "asus": "Tool → ASUS EZ Flash 3 Utility (Datei auf USB-Stick)",
            "msi": "M-FLASH (Startbildschirm, links unten) — Datei auf USB-Stick",
            "gigabyte": "Q-Flash (Taste F8) — Datei auf USB-Stick",
            "asrock": "Tool → Instant Flash — Datei auf USB-Stick",
        })


def _autoinstall() -> BiosSetting:
    return BiosSetting(
        key="autoinstall", category="Boot", name="Automatische Hersteller-Software aus", recommended="Disabled",
        default="Enabled",
        path="Hersteller-Menü → Auto-Installation der Board-Software = Disabled",
        explanation="Sonst installiert das Board beim ersten Windows-Start ungefragt Hersteller-Software, "
                    "Hintergrunddienste und Treiber-Downloader (Armoury Crate, MSI Center, GIGABYTE "
                    "Control Center …). Treiber bei Bedarf direkt von der Hersteller-Seite laden.",
        risk=SAFE, impact="low", paths={
            "asus": "Tool → ASUS Armoury Crate → Download & Install ARMOURY CRATE app = Disabled",
            "msi": "Settings → Advanced → MSI Driver Utility Installer = Disabled",
            "gigabyte": "Settings → GIGABYTE Utilities Downloader Configuration → Disabled",
            "asrock": "Tool → Auto Driver Installer = Disabled",
        })


def _pcie_gpu() -> BiosSetting:
    return BiosSetting(
        key="pcie_gpu", category="GPU", name="PCIe-Geschwindigkeit des Grafikkarten-Slots", recommended="Auto",
        default="Auto",
        path="PCIe-Einstellungen des GPU-Slots (z. B. „PCIEX16_1 Link Speed“ / „PCI_E1 Gen Switch“) = Auto",
        explanation="Auf Auto nimmt die Karte die schnellste Stufe, die Slot und Karte können. Nur bei "
                    "Schwarzbild, Bildaussetzern oder „kein Signal“ nach dem Einbau (vor allem RTX 50 / "
                    "PCIe 5.0 mit Riser-Kabel) eine Stufe fest einstellen (Gen 4) — kostet in Spielen "
                    "praktisch nichts.",
        risk=SAFE, impact="low")


# ── AMD ──────────────────────────────────────────────────────────────────────

_AMD_PBO_PATHS = {
    "asus": "Ai Tweaker → Precision Boost Overdrive (AM4: Advanced → AMD Overclocking → Precision Boost Overdrive)",
    "msi": "OC → Advanced CPU Configuration → AMD Overclocking → Precision Boost Overdrive",
    "gigabyte": "Tweaker → Advanced CPU Settings → Precision Boost Overdrive (alternativ Settings → AMD Overclocking)",
    "asrock": "Advanced → AMD Overclocking → Precision Boost Overdrive",
}
_AMD_CO_PATHS = {
    "asus": "Ai Tweaker → Precision Boost Overdrive → Curve Optimizer → All Cores → Negative",
    "msi": "OC → Advanced CPU Configuration → AMD Overclocking → Precision Boost Overdrive → Advanced → Curve Optimizer",
    "gigabyte": "Tweaker → Advanced CPU Settings → Precision Boost Overdrive → Curve Optimizer",
    "asrock": "Advanced → AMD Overclocking → Precision Boost Overdrive → Curve Optimizer",
}


def _pbo(kind: str) -> BiosSetting:
    texts = {
        "zen5": ("Enabled (PBO-Limits: Motherboard)", MODERATE, "medium",
                 "Lässt die CPU mehr Strom ziehen und länger hoch boosten. In Spielen meist 1–3 %, in "
                 "Mehrkern-Last mehr — dafür wärmer. Mit einem guten Kühler sinnvoll; zusammen mit dem "
                 "Curve Optimizer bringt es am meisten."),
        "zen5_x3d": ("Enabled (+ bis +200 MHz Boost Override)", MODERATE, "medium",
                     "Die 9000X3D sind — anders als die 7000X3D — offen: PBO mit Curve Optimizer und bis zu "
                     "+200 MHz Boost Override ist erlaubt. Temperaturen im Blick behalten (der Cache sitzt "
                     "jetzt unter den Kernen, die Kühlung ist dadurch besser als bei Zen 4)."),
        "zen4_x3d": ("Advanced → nur Curve Optimizer (Limits: Auto)", MODERATE, "medium",
                     "Bei den 7000X3D sind Takt und Leistungsgrenzen gesperrt — PBO wirkt nur über den "
                     "Curve Optimizer (negativ = weniger Spannung → mehr Boost bei gleicher Temperatur)."),
        "zen4": ("Enabled", MODERATE, "medium",
                 "Mehr Boost unter Last; in Spielen wenig, in Mehrkern-Last deutlich. Ryzen 7000 wird "
                 "schnell 95 °C heiß — das ist bei ihnen gewollt, aber mit Curve Optimizer bleibt die "
                 "CPU kühler."),
        "zen3": ("Enabled", MODERATE, "medium",
                 "Mehr Boost unter Last. Zusammen mit einem negativen Curve Optimizer der beste "
                 "Hebel bei Ryzen 5000."),
        "zen2": ("Auto / Enabled", MODERATE, "low",
                 "Bei Ryzen 3000 bringt PBO nur wenig (meist < 2 %) — kann an bleiben, wenn der "
                 "Kühler reicht."),
    }
    rec, risk, impact, expl = texts[kind]
    return BiosSetting(
        key="pbo", category="CPU", name="Precision Boost Overdrive (PBO)", recommended=rec, default="Auto (= aus)",
        path="Advanced → AMD Overclocking → Precision Boost Overdrive", explanation=expl,
        risk=risk, impact=impact, paths=_AMD_PBO_PATHS)


def _curve_optimizer(rec: str, expl: str, risk: str = MODERATE) -> BiosSetting:
    return BiosSetting(
        key="curve_optimizer", category="CPU", name="Curve Optimizer (Undervolting)", recommended=rec,
        default="0 (aus)", path="AMD Overclocking → Precision Boost Overdrive → Curve Optimizer",
        explanation=expl + " Danach stabil testen (z. B. OCCT oder CoreCycler, auch im Leerlauf — "
                           "Instabilität zeigt sich oft beim Surfen, nicht unter Last).",
        risk=risk, impact="medium", paths=_AMD_CO_PATHS)


def _fclk(value: str, expl: str) -> BiosSetting:
    return BiosSetting(
        key="fclk", category="Memory", name="Infinity Fabric (FCLK)", recommended=value, default="Auto",
        path="AMD Overclocking → DDR and Infinity Fabric Frequency/Timings → Infinity Fabric Frequency and "
             "Dividers → FCLK",
        explanation=expl + " Gibt es danach Abstürze oder USB-Aussetzer: zurück auf Auto.",
        risk=MODERATE, impact="medium", paths={
            "asus": "Ai Tweaker → FCLK Frequency",
            "msi": "OC → FCLK Frequency",
        })


def _mcr() -> BiosSetting:
    return BiosSetting(
        key="mcr", category="Memory", name="Memory Context Restore", recommended="Enabled",
        default="Auto (meist aus)",
        path="Advanced → AMD CBS → UMC Common Options → DDR Options → DDR Memory Features → Memory Context Restore",
        explanation="Spart das lange Speichertraining bei jedem Start (DDR5 auf AM5 sonst 20–60 s "
                    "schwarzer Bildschirm). Neuere BIOS-Versionen machen das stabil; gibt es danach "
                    "Startprobleme oder Abstürze nach dem Aufwachen: wieder Auto.",
        risk=MODERATE, impact="low", paths={
            "asus": "Ai Tweaker → DRAM Timing Control → Memory Context Restore",
            "msi": "OC → Advanced DRAM Configuration → Memory Context Restore",
            "gigabyte": "Tweaker → Advanced Memory Settings → Memory Context Restore",
        })


def _cstates_amd() -> BiosSetting:
    return BiosSetting(
        key="cstates", category="Power", name="Global C-State Control", recommended="Auto / Enabled lassen",
        default="Auto",
        path="Advanced → AMD CBS → CPU Common Options → Global C-state Control",
        explanation="Oft wird „aus für weniger Latenz“ empfohlen — bei Ryzen bringt das in Spielen "
                    "praktisch nichts, kostet aber Strom im Leerlauf und kann den Einkern-Boost senken "
                    "(der höchste Boost braucht schlafende Nachbarkerne). Also an lassen.",
        risk=SAFE, impact="low", paths={
            "msi": "OC → Advanced CPU Configuration → Global C-state Control",
            "gigabyte": "Tweaker → Advanced CPU Settings → Global C-state Control",
        })


def _igpu_off(apu: bool = False) -> BiosSetting:
    if apu:
        return BiosSetting(
            key="igpu", category="GPU", name="Grafikspeicher der iGPU (UMA Frame Buffer)",
            recommended="ohne Grafikkarte: 2–4 GB  ·  mit Grafikkarte: iGPU aus", default="Auto (oft 512 MB)",
            path="Advanced → AMD CBS → NBIO Common Options → GFX Configuration → UMA Frame buffer Size",
            explanation="Spielst du über die integrierte Grafik, gibt ein größerer fester Grafikspeicher "
                        "vielen Spielen mehr Luft (genug RAM vorausgesetzt — 32 GB empfohlen). Mit "
                        "dedizierter Grafikkarte die iGPU ausschalten.",
            risk=SAFE, impact="medium")
    return BiosSetting(
        key="igpu", category="GPU", name="Integrierte Grafik (iGPU) aus", recommended="Disabled (nur mit Grafikkarte)",
        default="Auto / Enabled",
        path="Advanced → AMD CBS → NBIO Common Options → GFX Configuration → iGPU Configuration = iGPU Disabled",
        explanation="Ryzen 7000/9000 haben eine kleine iGPU. Mit dedizierter Grafikkarte braucht man sie "
                    "nicht; aus spart etwas Strom und Arbeitsspeicher und verhindert, dass Programme die "
                    "falsche GPU wählen. Monitor dann unbedingt an der Grafikkarte anschließen.",
        risk=MODERATE, impact="low", paths={
            "asus": "Advanced → NB Configuration → Integrated Graphics = Disabled",
            "msi": "Settings → Advanced → Integrated Graphics Configuration → Integrated Graphics = Disabled",
            "gigabyte": "Settings → IO Ports → Integrated Graphics = Disabled",
        })


def _cppc_x3d() -> BiosSetting:
    return BiosSetting(
        key="x3d_cppc", category="CPU", name="Kern-Zuteilung bei X3D mit zwei CCDs",
        recommended="CPPC Dynamic Preferred Cores = Auto (Driver)", default="Auto",
        path="Advanced → AMD CBS → SMU Common Options → CPPC Dynamic Preferred Cores",
        explanation="Nur 7900X3D/7950X3D/9900X3D/9950X3D: Spiele sollen auf dem CCD mit dem 3D-Cache "
                    "laufen. Das übernimmt AMDs Chipsatz-Treiber zusammen mit dem Windows-Spielmodus und "
                    "der Xbox Game Bar — im BIOS auf Auto lassen, aktuellen Chipsatz-Treiber installieren. "
                    "Bei 7800X3D/9800X3D (ein CCD) gibt es nichts zu tun.",
        risk=SAFE, impact="medium")


# ── Intel ────────────────────────────────────────────────────────────────────

def _intel_default(gen: str) -> BiosSetting:
    rec, expl = {
        "rpl": ("Intel Default Settings = Performance (i9-K: PL1 = PL2 = 253 W, ICCMax 307 A)",
                "Viele Boards ließen 13./14. Gen ohne Leistungsgrenze laufen — zusammen mit dem "
                "Vmin-Shift-Fehler führte das zu Abstürzen und dauerhaft geschädigten CPUs. Intels "
                "Vorgabe „Performance“ (bzw. „Extreme“ nur für i9-K mit sehr gutem Kühler) ist der sichere "
                "Stand; in Spielen kostet sie praktisch nichts."),
        "adl": ("PL1 / PL2 nach Intel (z. B. i9-12900K: 125 W / 241 W)",
                "Board-Standard ist oft „unbegrenzt“ — das bringt in Spielen kaum etwas, macht die CPU "
                "aber sehr heiß. Intels Werte stehen auf ark.intel.com."),
        "arl": ("Intel Default Settings = Performance",
                "Der von Intel empfohlene Stand für Core Ultra 200S; manche Boards starten mit "
                "„unbegrenzt“."),
    }[gen]
    return BiosSetting(
        key="intel_power", category="Power", name="Leistungsgrenzen (Intel Default Settings)", recommended=rec,
        default="je nach Board „unbegrenzt“", path="CPU-/OC-Menü → Intel Default Settings bzw. Long/Short "
                                                 "Duration Power Limit (PL1/PL2)",
        explanation=expl, risk=SAFE if gen == "rpl" else MODERATE, impact="medium", paths={
            "asus": "Ai Tweaker → Intel Default Settings (ältere BIOS: Internal CPU Power Management → PL1/PL2)",
            "msi": "OC → Intel Default Settings (ältere BIOS: Advanced CPU Configuration → Long/Short Duration "
                   "Power Limit)",
            "gigabyte": "Tweaker → Intel Default Settings (ältere BIOS: Advanced CPU Settings → Turbo Power Limits)",
            "asrock": "OC Tweaker → CPU Configuration → Intel Default Settings bzw. Long/Short Duration Power Limit",
        })


def _mce() -> BiosSetting:
    return BiosSetting(
        key="mce", category="CPU", name="Multi-Core Enhancement", recommended="Auto (Leistung) — bei Hitze: Disabled",
        default="Auto / Enabled",
        path="OC-Menü → Multi-Core Enhancement",
        explanation="Lässt alle Kerne mit dem Einkern-Turbo laufen (außerhalb von Intels Vorgabe). Ein "
                    "paar Prozent mehr Leistung, dafür deutlich mehr Wärme — mit schwachem Kühler "
                    "Disabled wählen.",
        risk=MODERATE, impact="low", paths={
            "asus": "Ai Tweaker → ASUS MultiCore Enhancement",
            "msi": "OC → Enhanced Turbo",
            "gigabyte": "Tweaker → Advanced CPU Settings → Enhanced Multi-Core Performance",
            "asrock": "OC Tweaker → CPU Configuration → Multi Core Enhancement",
        })


def _200s_boost() -> BiosSetting:
    return BiosSetting(
        key="200s_boost", category="Memory", name="Intel 200S Boost", recommended="Enabled (mit passendem RAM)",
        default="Disabled",
        path="OC-Menü → Intel 200S Boost (ab BIOS mit Microcode 0x114)",
        explanation="Intels offizielle, von der Garantie gedeckte Übertaktung für Core Ultra 200S: "
                    "schnellere Verbindung zwischen den Kacheln (D2D/NGU) und RAM bis DDR5-8000. Bringt "
                    "in Spielen einige Prozent — die größte Schwäche von Arrow Lake ist die Speicher-Latenz.",
        risk=SAFE, impact="medium", paths={
            "asus": "Ai Tweaker → Intel(R) 200S Boost",
            "msi": "OC → Intel 200S Boost",
            "gigabyte": "Tweaker → Intel 200S Boost",
            "asrock": "OC Tweaker → Intel 200S Boost",
        })


def _ecores() -> BiosSetting:
    return BiosSetting(
        key="ecores", category="CPU", name="E-Cores", recommended="Enabled lassen", default="Enabled",
        path="CPU-Konfiguration → Active Efficient Cores = All",
        explanation="Früher half das Abschalten der E-Cores manchen Spielen. Mit Windows 11 und dem Thread "
                    "Director landen Spiele heute auf den P-Cores; abschalten kostet Leistung bei allem "
                    "anderen. Nur bei einem einzelnen Spiel mit Problemen (alte Anti-Cheats) testen.",
        risk=SAFE, impact="low")


# ═══════════════════════════════════════════════════════════════════════════════
# Profiles
# ═══════════════════════════════════════════════════════════════════════════════

def _am5_base(x3d: str = "", zen: str = "zen5") -> list:
    """Shared AM5 settings."""
    s = [
        _memory_profile("amd", "DDR5", "DDR5-6000 CL30 ist der Sweet Spot",
                        "AM5 läuft am besten mit DDR5-6000 bis -6400 im 1:1-Modus (UCLK = MCLK)."),
        _fclk("2000 MHz (Zen 5 oft auch 2100)" if zen == "zen5" else "2000 MHz",
              "Die Verbindung zwischen Kernen und Speicher-Controller. Bei DDR5-6000 sind 2000 MHz "
              "üblich und stabil; Auto lässt oft 1733–1800 MHz liegen."),
        _mcr(),
        _cstates_amd(),
        _rebar("amd"),
        _pcie_gpu(),
        _igpu_off(),
        _csm(),
        _secure_boot(),
        _bios_update("Neue AGESA-Versionen bringen bei AM5 spürbar kürzere Startzeiten, besseren "
                     "RAM-Support und Leistungs-Fixes (Zen 5: „2-Kern-Latenz“-Update)."),
        _autoinstall(),
    ]
    return s


PROFILES: list[BiosProfile] = [
    # ── AMD AM5 ──────────────────────────────────────────────────────────────
    BiosProfile(
        id="am5_zen5_x3d", name="AMD Ryzen 9000X3D (Zen 5 + 3D V-Cache) — AM5",
        cpus="Ryzen 7 9800X3D, Ryzen 9 9900X3D, 9950X3D",
        platform="AM5 — X870E / X870 / B850 / B840 / X670E / X670 / B650 / A620", brand="amd",
        settings=[_pbo("zen5_x3d"),
                  _curve_optimizer("All Cores, Negative 15–25",
                                   "Die meisten 9800X3D vertragen −15 bis −25; weniger Spannung = mehr Boost "
                                   "bei gleicher Temperatur."),
                  _cppc_x3d()] + _am5_base(zen="zen5"),
        notes="Die beste Gaming-CPU-Familie — der 3D-Cache macht den größten Teil der Arbeit. EXPO "
              "aktivieren ist Pflicht, PBO/Curve Optimizer sind Feinschliff."),
    BiosProfile(
        id="am5_zen5", name="AMD Ryzen 9000 (Zen 5) — AM5",
        cpus="Ryzen 5 9600(X), Ryzen 7 9700X, Ryzen 9 9900X, 9950X",
        platform="AM5 — X870E / X870 / B850 / B840 / X670E / X670 / B650 / A620", brand="amd",
        settings=[_pbo("zen5"),
                  _curve_optimizer("All Cores, Negative 10–20",
                                   "Zen 5 verträgt meist −10 bis −20."),
                  ] + _am5_base(zen="zen5"),
        notes="9600X/9700X kommen ab Werk mit 65-W-Grenze; PBO (oder der 105-W-Modus mancher BIOS) hebt "
              "sie an — in Spielen bringt das nur wenig."),
    BiosProfile(
        id="am5_zen4_x3d", name="AMD Ryzen 7000X3D (Zen 4 + 3D V-Cache) — AM5",
        cpus="Ryzen 7 7800X3D, Ryzen 9 7900X3D, 7950X3D",
        platform="AM5 — X870E / X870 / B850 / X670E / X670 / B650 / A620", brand="amd",
        settings=[_pbo("zen4_x3d"),
                  _curve_optimizer("All Cores, Negative 15–30",
                                   "Der einzige Hebel bei den 7000X3D: weniger Spannung lässt sie höher "
                                   "boosten."),
                  _cppc_x3d()] + _am5_base(zen="zen4"),
        notes="Wichtig: BIOS aktuell halten — frühe Versionen ließen zu hohe SoC-Spannungen zu (2023 "
              "durchgebrannte 7800X3D). Aktuelle BIOS begrenzen die SoC-Spannung auf ≤ 1,3 V."),
    BiosProfile(
        id="am5_zen4", name="AMD Ryzen 7000 (Zen 4) — AM5",
        cpus="Ryzen 5 7600(X), Ryzen 7 7700(X), Ryzen 9 7900(X), 7950X",
        platform="AM5 — X870E / X870 / B850 / X670E / X670 / B650 / A620", brand="amd",
        settings=[_pbo("zen4"),
                  _curve_optimizer("All Cores, Negative 10–20",
                                   "Senkt Temperatur und hebt den Boost — bei Ryzen 7000 der beste Hebel.")
                  ] + _am5_base(zen="zen4")),
    BiosProfile(
        id="am5_apu", name="AMD Ryzen 8000G / 8000F (Zen 4 APU) — AM5",
        cpus="Ryzen 5 8500G / 8600G, Ryzen 7 8700G, Ryzen 5 8400F, Ryzen 7 8700F",
        platform="AM5 — B650 / A620 / X670 / B850", brand="amd",
        settings=[
            _memory_profile("amd", "DDR5", "DDR5-6000 oder schneller",
                            "Spielst du über die integrierte Grafik, ist schneller RAM besonders wichtig — "
                            "die iGPU hat keinen eigenen Speicher."),
            _igpu_off(apu=True), _pbo("zen4"),
            _curve_optimizer("All Cores, Negative 10–20", "Senkt Temperatur und hebt den Boost."),
            _mcr(), _cstates_amd(), _rebar("amd"), _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Neue AGESA-Versionen verbessern RAM-Support und Startzeiten."), _autoinstall()],
        notes="Die 8000G/8000F haben PCIe 4.0 und — bei 8500G/8400F — weniger Lanes; für eine schnelle "
              "Grafikkarte ist ein Ryzen 7000/9000 die bessere Wahl."),

    # ── AMD AM4 ──────────────────────────────────────────────────────────────
    BiosProfile(
        id="am4_zen3_x3d", name="AMD Ryzen 5000X3D (Zen 3 + 3D V-Cache) — AM4",
        cpus="Ryzen 5 5600X3D, Ryzen 7 5700X3D, 5800X3D",
        platform="AM4 — X570 / B550 / X470 / B450 / A520", brand="amd",
        settings=[
            _memory_profile("amd", "DDR4", "DDR4-3600 CL16 ist der Sweet Spot"),
            _fclk("1800 MHz (bei DDR4-3600)", "1:1 mit dem RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900."),
            _curve_optimizer("nur wenn angeboten: All Cores, Negative 15–30",
                             "Die 5000X3D sind gesperrt; neuere BIOS (AGESA 1.2.0.8+) bieten den Curve "
                             "Optimizer teils an, MSI nennt es „Kombo Strike“ (OC-Menü, Stufe 1–3)."),
            _rebar("amd", "AM4 braucht dafür ein BIOS von 2021 oder neuer."), _pcie_gpu(), _csm(),
            _secure_boot(), _bios_update("Für 5000X3D auf älteren Boards ist ein BIOS-Update Pflicht "
                                         "(AGESA 1.2.0.x)."), _autoinstall()],
        notes="PBO und Takt-Übertaktung sind bei den 5000X3D gesperrt — EXPO/XMP und FCLK 1:1 sind die "
              "wichtigsten Punkte."),
    BiosProfile(
        id="am4_zen3", name="AMD Ryzen 5000 (Zen 3) — AM4",
        cpus="Ryzen 5 5500 / 5600(X), Ryzen 7 5700X / 5800X, Ryzen 9 5900X / 5950X",
        platform="AM4 — X570 / B550 / X470 / B450 / A520", brand="amd",
        settings=[
            _memory_profile("amd", "DDR4", "DDR4-3600 CL16 ist der Sweet Spot"),
            _fclk("1800 MHz (bei DDR4-3600)", "1:1 mit dem RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900 "
                                              "(nicht jede CPU schafft 1900)."),
            _pbo("zen3"),
            _curve_optimizer("All Cores, Negative 10–20 (besser: pro Kern)",
                             "Zen 3 reagiert stark auf den Curve Optimizer; die besten zwei Kerne "
                             "vertragen meist weniger."),
            _rebar("amd", "AM4 braucht dafür ein BIOS von 2021 oder neuer."), _pcie_gpu(), _csm(),
            _secure_boot(), _bios_update("Auf 400er-Boards ist ein BIOS-Update für Ryzen 5000 Pflicht; "
                                         "neuere AGESA-Versionen beheben USB-Aussetzer."), _autoinstall()]),
    BiosProfile(
        id="am4_apu", name="AMD Ryzen 5000G / 4000G / 3000G / 2000G (APU) — AM4",
        cpus="Ryzen 3 5300G, Ryzen 5 5600G / 4600G / 3400G / 2400G, Ryzen 7 5700G",
        platform="AM4 — B550 / A520 / X570 / B450 / A320", brand="amd",
        settings=[
            _memory_profile("amd", "DDR4", "DDR4-3600 oder schneller",
                            "Die iGPU nutzt den Arbeitsspeicher als Grafikspeicher — schneller RAM bringt "
                            "ihr am meisten."),
            _igpu_off(apu=True),
            _fclk("1800–2000 MHz", "Die APUs schaffen oft FCLK 2000 (DDR4-4000 1:1)."),
            _rebar("amd", "Bei den APUs nur mit 5000G und aktuellem BIOS."), _pcie_gpu(), _csm(),
            _secure_boot(), _bios_update("Neue AGESA-Versionen verbessern den APU-Support."), _autoinstall()],
        notes="5600G/5700G haben nur PCIe 3.0 — für eine schnelle Grafikkarte nicht ideal."),
    BiosProfile(
        id="am4_zen2", name="AMD Ryzen 3000 (Zen 2) — AM4",
        cpus="Ryzen 5 3600(X), Ryzen 7 3700X / 3800X, Ryzen 9 3900X / 3950X",
        platform="AM4 — X570 / B550 / X470 / B450", brand="amd",
        settings=[
            _memory_profile("amd", "DDR4", "DDR4-3600 CL16"),
            _fclk("1800 MHz (bei DDR4-3600)", "Zen 2 schafft fast immer 1800 MHz 1:1, 1866–1900 nur selten."),
            _pbo("zen2"),
            _rebar("amd", "Ryzen 3000 unterstützt es seit 2021 auf 400er/500er-Boards — BIOS-Update nötig."),
            _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Für Resizable BAR und Windows-11-TPM ist ein BIOS ab 2021 nötig."), _autoinstall()]),
    BiosProfile(
        id="am4_zen1", name="AMD Ryzen 1000 / 2000 (Zen / Zen+) — AM4",
        cpus="Ryzen 5 1600 / 2600, Ryzen 7 1700 / 2700X",
        platform="AM4 — X470 / B450 / X370 / B350", brand="amd",
        settings=[
            _memory_profile("amd", "DDR4", "DDR4-3200 (Zen+: oft 3466)",
                            "Zen/Zen+ sind beim RAM wählerisch — klappt das Profil nicht, den Takt eine "
                            "Stufe senken."),
            _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Neuere BIOS-Versionen verbessern die RAM-Kompatibilität deutlich."), _autoinstall()],
        notes="Resizable BAR gibt es für Ryzen 1000/2000 nicht. Ein Ryzen 5000(X3D) passt meist mit "
              "BIOS-Update in dasselbe Board — der größte Sprung für wenig Geld."),

    # ── Intel ────────────────────────────────────────────────────────────────
    BiosProfile(
        id="lga1851_arl", name="Intel Core Ultra 200S (Arrow Lake) — LGA1851",
        cpus="Core Ultra 5 245K / 225, Core Ultra 7 265K, Core Ultra 9 285K",
        platform="LGA1851 — Z890 / B860 / H810", brand="intel",
        settings=[
            _memory_profile("intel", "DDR5", "DDR5-6400 bis -8000 (CUDIMM)",
                            "Arrow Lake profitiert stark von schnellem RAM; ab DDR5-8000 lohnen CUDIMM-Module."),
            _200s_boost(), _intel_default("arl"), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Pflicht bei Arrow Lake: das BIOS mit Microcode 0x114 (oder neuer) behebt die "
                         "schwache Spieleleistung zum Start und bringt „200S Boost“.", impact="high"),
            _autoinstall()],
        notes="Core Ultra 200S haben kein Hyper-Threading. Windows aktuell halten — die Leistungs-Fixes "
              "kamen zusammen mit Windows-Updates."),
    BiosProfile(
        id="lga1700_rpl", name="Intel Core 13./14. Gen (Raptor Lake) — LGA1700",
        cpus="Core i5-13400–14600K, Core i7-13700K / 14700K, Core i9-13900K / 14900K",
        platform="LGA1700 — Z790 / B760 / H770 / Z690 / B660", brand="intel",
        settings=[
            _bios_update("SEHR WICHTIG: BIOS mit Microcode 0x12F (oder neuer) — behebt den „Vmin Shift“, "
                         "der 13./14.-Gen-CPUs (vor allem i7/i9) dauerhaft instabil machen kann. Ältere "
                         "BIOS-Versionen nicht weiter verwenden.", impact="high"),
            _intel_default("rpl"),
            _memory_profile("intel", "DDR5", "DDR5-6000 bis -7200 (DDR4-Boards: DDR4-3600)"),
            _ecores(), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(), _autoinstall()],
        notes="Abstürze in Spielen („Out of video memory“, Shader-Fehler) sind bei 13./14. Gen ein "
              "typisches Zeichen für den Vmin-Shift — erst BIOS-Update + Intel Default Settings, dann weiter "
              "optimieren. Intel hat die Garantie dieser CPUs verlängert."),
    BiosProfile(
        id="lga1700_adl", name="Intel Core 12. Gen (Alder Lake) — LGA1700",
        cpus="Core i3-12100, Core i5-12400 / 12600K, Core i7-12700K, Core i9-12900K",
        platform="LGA1700 — Z690 / B660 / H670 / H610 (auch Z790/B760)", brand="intel",
        settings=[
            _memory_profile("intel", "DDR5", "DDR5-6000 (DDR4-Boards: DDR4-3600 im Gear 1)"),
            _intel_default("adl"), _ecores(), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Neuere BIOS-Versionen verbessern den DDR5-Support deutlich."), _autoinstall()],
        notes="Unter Windows 10 verteilt der Thread Director die Kerne schlechter — Windows 11 holt bei "
              "12. Gen spürbar mehr heraus."),
    BiosProfile(
        id="lga1200", name="Intel Core 10./11. Gen (Comet / Rocket Lake) — LGA1200",
        cpus="Core i5-10400–11600K, Core i7-10700K / 11700K, Core i9-10900K / 11900K",
        platform="LGA1200 — Z590 / B560 / H570 / Z490 / B460 / H410", brand="intel",
        settings=[
            _memory_profile("intel", "DDR4", "DDR4-3200 bis -3600 (11. Gen: Gear 1)",
                            "Bei 11. Gen den Speicher-Controller im „Gear 1“ lassen — Gear 2 kostet Latenz."),
            _mce(),
            _rebar("intel", "Offiziell ab 11. Gen auf 500er-Boards; viele Z490-Boards haben es per "
                            "BIOS-Update für 10. Gen nachgereicht."),
            _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Für Resizable BAR und Windows-11-TPM ist ein BIOS ab 2021 nötig."), _autoinstall()]),
    BiosProfile(
        id="lga1151", name="Intel Core 8./9. Gen (Coffee Lake) — LGA1151",
        cpus="Core i5-8400–9600K, Core i7-8700K / 9700K, Core i9-9900K",
        platform="LGA1151 v2 — Z390 / Z370 / B365 / B360 / H370", brand="intel",
        settings=[
            _memory_profile("intel", "DDR4", "DDR4-3200"),
            _mce(), _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Neuere BIOS-Versionen enthalten Sicherheits-Microcode und teils Resizable BAR "
                         "(nur manche Z390-Boards, inoffiziell)."), _autoinstall()],
        notes="Resizable BAR gibt es offiziell erst ab Intel 10./11. Gen."),

    # ── everything else ──────────────────────────────────────────────────────
    BiosProfile(
        id="generic", name="Andere / unbekannte Plattform — Grundlagen",
        cpus="jede Desktop-CPU", platform="jedes Board", brand="any",
        settings=[
            BiosSetting(key="memory_profile", category="Memory", name="XMP / EXPO / DOCP-Profil",
                        recommended="Profil 1", default="Aus — JEDEC-Standardtakt",
                        path="OC-/Tweaker-Menü → Speicherprofil → Profil 1",
                        explanation="Ohne Profil läuft der RAM nur mit dem Standardtakt — der größte "
                                    "kostenlose Gewinn im BIOS.", risk=SAFE, impact="high", detect_key="expo_xmp"),
            _rebar("any"), _pcie_gpu(), _csm(), _secure_boot(),
            _bios_update("Neuere BIOS-Versionen verbessern RAM-Kompatibilität und Sicherheit."), _autoinstall()],
        notes="Laptops: Die meisten Laptop-BIOS bieten diese Optionen nicht — dort lohnt vor allem der "
              "Hersteller-Leistungsmodus (z. B. „Turbo“/„Performance“) im Hersteller-Tool."),
]

_BY_ID = {p.id: p for p in PROFILES}


def get_profile(pid: str) -> Optional[BiosProfile]:
    return _BY_ID.get(pid)


# ── Matching ─────────────────────────────────────────────────────────────────

_RYZEN_RE = re.compile(r"RYZEN\s+(?:THREADRIPPER\s+)?(?:\d\s+)?(?:PRO\s+)?(\d{4})(X3D|XT|X|GE|G|F|E)?\b")
_INTEL_CORE_RE = re.compile(r"\bI[3579]-(\d{4,5})([A-Z]{0,2})\b")
_INTEL_ULTRA_RE = re.compile(r"ULTRA\s+[3579]\s+(\d{3})([A-Z]{0,2})\b")
_MOBILE = ("H", "HS", "HX", "U", "P", "Y", "HK", "G7", "V")


def detect_profile(cpu_name: str) -> str:
    """Profile id for a CPU name (Win32_Processor.Name); "generic" when unknown
    (laptops, Threadripper, server CPUs)."""
    c = " ".join((cpu_name or "").upper().replace("(TM)", " ").replace("(R)", " ").split())
    m = _RYZEN_RE.search(c)
    if m and "THREADRIPPER" not in c:
        # mobile Ryzen ("7840HS", "5600H") never matches: no word boundary after the digits
        num, suf = int(m.group(1)), (m.group(2) or "")
        series = num // 1000
        if series == 9:
            return "am5_zen5_x3d" if suf == "X3D" else "am5_zen5"
        if series == 8:
            return "am5_apu"
        if series == 7:
            return "am5_zen4_x3d" if suf == "X3D" else "am5_zen4"
        if series == 5:
            if suf == "X3D":
                return "am4_zen3_x3d"
            return "am4_apu" if suf in ("G", "GE") else "am4_zen3"
        if series == 4:
            return "am4_apu" if suf in ("G", "GE") else "generic"
        if series == 3:
            return "am4_apu" if suf in ("G", "GE") else "am4_zen2"
        if series in (1, 2):
            return "am4_apu" if suf in ("G", "GE") else "am4_zen1"
        return "generic"
    m = _INTEL_ULTRA_RE.search(c)
    if m:
        num, suf = int(m.group(1)), m.group(2)
        if 200 <= num < 300 and suf in ("", "K", "KF", "F", "T"):
            return "lga1851_arl"
        return "generic"                              # Core Ultra mobile (1xxH/U, 2xxV/H)
    m = _INTEL_CORE_RE.search(c)
    if m:
        digits, suf = m.group(1), m.group(2)
        if suf in _MOBILE or suf.startswith("H"):
            return "generic"
        gen = int(digits[:2]) if len(digits) == 5 else int(digits[0])
        if gen in (13, 14):
            return "lga1700_rpl"
        if gen == 12:
            return "lga1700_adl"
        if gen in (10, 11):
            return "lga1200"
        if gen in (8, 9):
            return "lga1151"
    return "generic"


def match_profiles(cpu_name: str, mb_manufacturer: str = "", mb_product: str = "",
                   gpu_name: str = "") -> list[BiosProfile]:
    """All profiles, the one for this CPU first (the BIOS guide lists every
    platform; the hardware detection only pre-selects)."""
    pid = detect_profile(cpu_name)
    first = _BY_ID[pid]
    return [first] + [p for p in PROFILES if p is not first]


def get_impact_color(impact: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(impact, "#6b7280")


def get_risk_color(risk: str) -> str:
    return {"safe": "#22c55e", "moderate": "#f59e0b", "advanced": "#ef4444"}.get(risk, "#6b7280")
