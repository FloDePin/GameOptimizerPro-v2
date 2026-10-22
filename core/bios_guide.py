"""
GameOptimizerPro — BIOS Guide database

Every desktop platform since Intel's 8th gen / AMD's first Ryzen, each with the
settings that matter for games, and the menu path on ASUS, MSI, Gigabyte and
ASRock boards. The hardware detection only PRE-SELECTS the platform and the board
maker — every profile can be opened.

  BiosSetting  — one recommendation: value, menu path (per board maker), why
  BiosProfile  — one platform (CPU generation + socket / chipsets)
  profiles()   — all platforms in the app's language, newest first per vendor
  detect_profile() / vendor_of() — what the hardware detection picks

Menu names differ between BIOS versions — every path is the usual one; the
BIOS's own search (ASUS F9, MSI Ctrl+F) finds an option by its name.
Every text is German + English (_tr); the profiles are built per language.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from core.i18n import current_lang, tr as _tr


# ── Risk levels ───────────────────────────────────────────────────────────────
SAFE     = "safe"       # always recommended, no risk
MODERATE = "moderate"   # recommended, test stability afterwards
ADVANCED = "advanced"   # for experienced users only

# board makers: key, label
VENDORS = [("asus", "ASUS"), ("msi", "MSI"), ("gigabyte", "Gigabyte"), ("asrock", "ASRock"),
           ("other", "Andere / unbekannt")]


def vendors() -> list:
    """VENDORS in the app's language."""
    return [(k, _tr(n, "Other / unknown") if k == "other" else n) for k, n in VENDORS]


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
    name = (_tr("EXPO-Profil", "EXPO profile") if ddr == "DDR5" else _tr("D.O.C.P. / A-XMP-Profil", "D.O.C.P. / A-XMP profile")) \
        if amd else _tr("XMP-Profil", "XMP profile")
    paths = ({
        "asus": "Ai Tweaker → Ai Overclock Tuner → " + ("EXPO I" if ddr == "DDR5" else "D.O.C.P."),
        "msi": _tr("OC → A-XMP / EXPO → Profile 1 (oder der EXPO-/A-XMP-Schalter im EZ-Mode)",
                   "OC → A-XMP / EXPO → Profile 1 (or the EXPO / A-XMP switch in EZ Mode)"),
        "gigabyte": _tr("Tweaker → Extreme Memory Profile (X.M.P.) / EXPO → Profile1 (auch im Easy Mode)",
                        "Tweaker → Extreme Memory Profile (X.M.P.) / EXPO → Profile1 (also in Easy Mode)"),
        "asrock": _tr("OC Tweaker → DRAM Profile Configuration → DRAM Profile Setting → EXPO/XMP-Profil 1",
                      "OC Tweaker → DRAM Profile Configuration → DRAM Profile Setting → EXPO/XMP profile 1"),
    } if amd else {
        "asus": "Ai Tweaker → Ai Overclock Tuner → XMP I",
        "msi": _tr("OC → Extreme Memory Profile (XMP) → Profile 1 (oder der XMP-Schalter im EZ-Mode)",
                   "OC → Extreme Memory Profile (XMP) → Profile 1 (or the XMP switch in EZ Mode)"),
        "gigabyte": _tr("Tweaker → Extreme Memory Profile (X.M.P.) → Profile1 (auch im Easy Mode)",
                        "Tweaker → Extreme Memory Profile (X.M.P.) → Profile1 (also in Easy Mode)"),
        "asrock": _tr("OC Tweaker → DRAM Profile Configuration → XMP-Profil 1",
                      "OC Tweaker → DRAM Profile Configuration → XMP profile 1"),
    })
    return BiosSetting(
        key="memory_profile", category="Memory", name=name,
        recommended=_tr(f"Profil 1 ({target})", f"Profile 1 ({target})"),
        default=_tr("Aus — JEDEC-Standardtakt", "Off — JEDEC stock speed"),
        path=_tr("OC-/Tweaker-Menü → Speicherprofil (EXPO bzw. XMP/DOCP) → Profil 1",
                 "OC / Tweaker menu → memory profile (EXPO or XMP/DOCP) → Profile 1"),
        explanation=(_tr(f"Ohne Profil läuft der RAM nur mit dem langsamen {ddr}-Standardtakt — der größte "
                         f"kostenlose Gewinn im BIOS, vor allem für die 1-%-Lows in CPU-lastigen Spielen. ",
                         f"Without a profile the RAM runs at the slow {ddr} stock speed only — the biggest "
                         f"free gain in the BIOS, above all for the 1 % lows in CPU-heavy games. ")
                     + note + (" " if note else "")
                     + _tr("Startet der PC danach nicht oder gibt es Abstürze: Profil 2 oder ein Takt-Schritt "
                           "niedriger; viele Boards setzen nach 3 Fehlstarts selbst zurück.",
                           "If the PC doesn't start afterwards or crashes: profile 2 or one speed step lower; "
                           "many boards reset themselves after 3 failed starts.")),
        risk=SAFE, impact="high", detect_key="expo_xmp", paths=paths)


def _rebar(brand: str, note: str = "") -> BiosSetting:
    return BiosSetting(
        key="rebar", category="GPU", name="Resizable BAR (+ Above 4G Decoding)",
        recommended="Above 4G Decoding = Enabled, Re-Size BAR Support = Enabled", default="Disabled",
        path=_tr("PCI-/IO-Einstellungen → Above 4G Decoding = Enabled → Re-Size BAR Support = Enabled",
                 "PCI / IO settings → Above 4G Decoding = Enabled → Re-Size BAR Support = Enabled"),
        explanation=(_tr("Die CPU darf den ganzen Grafikspeicher auf einmal ansprechen statt in 256-MB-Häppchen. "
                         "NVIDIA nutzt es für die Spiele, für die es im Treiber freigegeben ist; bei AMD-Karten "
                         "heißt es „Smart Access Memory“ und wirkt fast überall. Voraussetzung: CSM aus "
                         "(UEFI-Start). ",
                         "The CPU may address the whole graphics memory at once instead of in 256-MB chunks. "
                         "NVIDIA uses it for the games it is enabled for in the driver; on AMD cards it is "
                         "called “Smart Access Memory” and works almost everywhere. Needs CSM off "
                         "(UEFI boot). ") + note).strip(),
        risk=SAFE, impact="high", detect_key="rebar", paths={
            "asus": "Advanced → PCI Subsystem Settings → Above 4G Decoding = Enabled → Re-Size BAR Support = Enabled",
            "msi": "Settings → Advanced → PCIe/PCI Sub-system Settings → Above 4G memory/Crypto Currency mining = "
                   "Enabled → Re-Size BAR Support = Enabled",
            "gigabyte": "Settings → IO Ports → Above 4G Decoding = Enabled → Re-Size BAR Support = Auto/Enabled",
            "asrock": "Advanced → PCI Configuration → Above 4G Decoding = Enabled → Re-Size BAR Support"
                      + (_tr(" (bei AMD-Boards auch „C.A.M.“)", " (on AMD boards also “C.A.M.”)")
                         if brand == "amd" else "") + " = Enabled",
        })


def _csm() -> BiosSetting:
    return BiosSetting(
        key="csm", category="Boot", name=_tr("CSM (Legacy-Start) aus", "CSM (legacy boot) off"),
        recommended=_tr("Disabled (reiner UEFI-Start)", "Disabled (pure UEFI boot)"),
        default=_tr("je nach Board Auto / Enabled", "Auto / Enabled, depending on the board"),
        path="Boot → CSM (Compatibility Support Module) → Disabled",
        explanation=_tr("Der alte Legacy-BIOS-Modus. Aus = Voraussetzung für Resizable BAR und Secure Boot. "
                        "WICHTIG: nur ausschalten, wenn Windows im UEFI-Modus installiert ist — prüfen mit "
                        "msinfo32 → „BIOS-Modus: UEFI“. Steht dort „Legacy“, startet Windows ohne CSM nicht.",
                        "The old legacy BIOS mode. Off = needed for Resizable BAR and Secure Boot. "
                        "IMPORTANT: only turn it off when Windows is installed in UEFI mode — check with "
                        "msinfo32 → “BIOS Mode: UEFI”. If it says “Legacy”, Windows does "
                        "not start without CSM."),
        risk=MODERATE, impact="medium", detect_key="csm", paths={
            "asus": "Boot → CSM (Compatibility Support Module) → Launch CSM = Disabled",
            "msi": "Settings → Advanced → Windows OS Configuration → BIOS UEFI/CSM Mode = UEFI",
            "gigabyte": "Boot → CSM Support = Disabled",
            "asrock": "Boot → CSM (Compatibility Support Module) → CSM = Disabled",
        })


def _secure_boot() -> BiosSetting:
    return BiosSetting(
        key="secure_boot", category="Boot", name="Secure Boot", recommended="Enabled",
        default=_tr("oft Disabled (bzw. „Other OS“)", "often Disabled (or “Other OS”)"),
        path="Boot/Security → Secure Boot = Enabled",
        explanation=_tr("Bringt keine FPS, ist aber für immer mehr Spiele Pflicht: Valorant/Vanguard unter "
                        "Windows 11, Battlefield 6, Call of Duty und weitere Anti-Cheats starten ohne Secure "
                        "Boot nicht. Braucht CSM aus. Meldet das BIOS fehlende Schlüssel: „Restore Factory "
                        "Keys“ bzw. „Install default Secure Boot keys“.",
                        "No FPS, but a must for more and more games: Valorant/Vanguard on Windows 11, "
                        "Battlefield 6, Call of Duty and other anti-cheats don't start without Secure Boot. "
                        "Needs CSM off. If the BIOS reports missing keys: “Restore Factory Keys” or "
                        "“Install default Secure Boot keys”."),
        risk=SAFE, impact="medium", detect_key="secure_boot", paths={
            "asus": "Boot → Secure Boot → OS Type = Windows UEFI mode",
            "msi": "Settings → Security → Secure Boot → Secure Boot = Enabled",
            "gigabyte": "Boot → Secure Boot → Secure Boot = Enabled",
            "asrock": "Security → Secure Boot → Secure Boot = Enabled",
        })


def _bios_update(what: str, risk: str = SAFE, impact: str = "medium") -> BiosSetting:
    return BiosSetting(
        key="bios_update", category="Boot", name=_tr("BIOS aktuell halten", "Keep the BIOS up to date"),
        recommended=_tr("neueste Version des Herstellers", "the maker's newest version"),
        default=_tr("Auslieferungsstand", "as shipped"),
        path=_tr("Flash-Tool im BIOS — Datei von der Support-Seite des Boards auf einen FAT32-USB-Stick",
                 "Flash tool in the BIOS — the file from the board's support page on a FAT32 USB stick"),
        explanation=what + _tr(" Vor dem Flashen das EXPO/XMP-Profil notieren (danach ist alles auf Standard) "
                               "und den PC währenddessen nicht ausschalten.",
                               " Note the EXPO/XMP profile before flashing (everything is at default afterwards) "
                               "and don't switch the PC off meanwhile."),
        risk=risk, impact=impact, paths={
            "asus": _tr("Tool → ASUS EZ Flash 3 Utility (Datei auf USB-Stick)",
                        "Tool → ASUS EZ Flash 3 Utility (file on a USB stick)"),
            "msi": _tr("M-FLASH (Startbildschirm, links unten) — Datei auf USB-Stick",
                       "M-FLASH (start screen, bottom left) — file on a USB stick"),
            "gigabyte": _tr("Q-Flash (Taste F8) — Datei auf USB-Stick", "Q-Flash (key F8) — file on a USB stick"),
            "asrock": _tr("Tool → Instant Flash — Datei auf USB-Stick", "Tool → Instant Flash — file on a USB stick"),
        })


def _autoinstall() -> BiosSetting:
    return BiosSetting(
        key="autoinstall", category="Boot",
        name=_tr("Automatische Hersteller-Software aus", "Automatic vendor software off"), recommended="Disabled",
        default="Enabled",
        path=_tr("Hersteller-Menü → Auto-Installation der Board-Software = Disabled",
                 "Vendor menu → automatic installation of the board software = Disabled"),
        explanation=_tr("Sonst installiert das Board beim ersten Windows-Start ungefragt Hersteller-Software, "
                        "Hintergrunddienste und Treiber-Downloader (Armoury Crate, MSI Center, GIGABYTE "
                        "Control Center …). Treiber bei Bedarf direkt von der Hersteller-Seite laden.",
                        "Otherwise the board installs vendor software, background services and driver "
                        "downloaders (Armoury Crate, MSI Center, GIGABYTE Control Center …) at the first "
                        "Windows start without asking. Get drivers from the maker's website when needed."),
        risk=SAFE, impact="low", paths={
            "asus": "Tool → ASUS Armoury Crate → Download & Install ARMOURY CRATE app = Disabled",
            "msi": "Settings → Advanced → MSI Driver Utility Installer = Disabled",
            "gigabyte": "Settings → GIGABYTE Utilities Downloader Configuration → Disabled",
            "asrock": "Tool → Auto Driver Installer = Disabled",
        })


def _pcie_gpu() -> BiosSetting:
    return BiosSetting(
        key="pcie_gpu", category="GPU",
        name=_tr("PCIe-Geschwindigkeit des Grafikkarten-Slots", "PCIe speed of the graphics card slot"),
        recommended="Auto", default="Auto",
        path=_tr("PCIe-Einstellungen des GPU-Slots (z. B. „PCIEX16_1 Link Speed“ / „PCI_E1 Gen Switch“) = Auto",
                 "PCIe settings of the GPU slot (e.g. “PCIEX16_1 Link Speed” / “PCI_E1 Gen Switch”) = Auto"),
        explanation=_tr("Auf Auto nimmt die Karte die schnellste Stufe, die Slot und Karte können. Nur bei "
                        "Schwarzbild, Bildaussetzern oder „kein Signal“ nach dem Einbau (vor allem RTX 50 / "
                        "PCIe 5.0 mit Riser-Kabel) eine Stufe fest einstellen (Gen 4) — kostet in Spielen "
                        "praktisch nichts.",
                        "On Auto the card takes the fastest level slot and card can do. Only with a black "
                        "screen, dropouts or “no signal” after fitting it (above all RTX 50 / PCIe "
                        "5.0 with a riser cable) set one level fixed (Gen 4) — it costs practically nothing "
                        "in games."),
        risk=SAFE, impact="low")


# ── AMD ──────────────────────────────────────────────────────────────────────

def _amd_pbo_paths():
    return {
        "asus": _tr("Ai Tweaker → Precision Boost Overdrive (AM4: Advanced → AMD Overclocking → Precision Boost Overdrive)",
                    "Ai Tweaker → Precision Boost Overdrive (AM4: Advanced → AMD Overclocking → Precision Boost Overdrive)"),
        "msi": "OC → Advanced CPU Configuration → AMD Overclocking → Precision Boost Overdrive",
        "gigabyte": _tr("Tweaker → Advanced CPU Settings → Precision Boost Overdrive (alternativ Settings → AMD Overclocking)",
                        "Tweaker → Advanced CPU Settings → Precision Boost Overdrive (or Settings → AMD Overclocking)"),
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
        "zen5": (_tr("Enabled (PBO-Limits: Motherboard)", "Enabled (PBO limits: Motherboard)"), MODERATE, "medium",
                 _tr("Lässt die CPU mehr Strom ziehen und länger hoch boosten. In Spielen meist 1–3 %, in "
                     "Mehrkern-Last mehr — dafür wärmer. Mit einem guten Kühler sinnvoll; zusammen mit dem "
                     "Curve Optimizer bringt es am meisten.",
                     "Lets the CPU draw more power and boost high for longer. In games usually 1–3 %, more "
                     "under multi-core load — and warmer. Worth it with a good cooler; together with the "
                     "Curve Optimizer it brings the most.")),
        "zen5_x3d": (_tr("Enabled (+ bis +200 MHz Boost Override)", "Enabled (+ up to +200 MHz boost override)"),
                     MODERATE, "medium",
                     _tr("Die 9000X3D sind — anders als die 7000X3D — offen: PBO mit Curve Optimizer und bis zu "
                         "+200 MHz Boost Override ist erlaubt. Temperaturen im Blick behalten (der Cache sitzt "
                         "jetzt unter den Kernen, die Kühlung ist dadurch besser als bei Zen 4).",
                         "Unlike the 7000X3D, the 9000X3D are unlocked: PBO with Curve Optimizer and up to "
                         "+200 MHz boost override are allowed. Keep an eye on temperatures (the cache now sits "
                         "under the cores, so cooling is better than on Zen 4).")),
        "zen4_x3d": (_tr("Advanced → nur Curve Optimizer (Limits: Auto)", "Advanced → Curve Optimizer only (limits: Auto)"),
                     MODERATE, "medium",
                     _tr("Bei den 7000X3D sind Takt und Leistungsgrenzen gesperrt — PBO wirkt nur über den "
                         "Curve Optimizer (negativ = weniger Spannung → mehr Boost bei gleicher Temperatur).",
                         "On the 7000X3D clocks and power limits are locked — PBO works only through the "
                         "Curve Optimizer (negative = less voltage → more boost at the same temperature).")),
        "zen4": ("Enabled", MODERATE, "medium",
                 _tr("Mehr Boost unter Last; in Spielen wenig, in Mehrkern-Last deutlich. Ryzen 7000 wird "
                     "schnell 95 °C heiß — das ist bei ihnen gewollt, aber mit Curve Optimizer bleibt die "
                     "CPU kühler.",
                     "More boost under load; little in games, clearly more under multi-core load. Ryzen 7000 "
                     "reaches 95 °C quickly — that is intended for them, but with the Curve Optimizer the "
                     "CPU stays cooler.")),
        "zen3": ("Enabled", MODERATE, "medium",
                 _tr("Mehr Boost unter Last. Zusammen mit einem negativen Curve Optimizer der beste "
                     "Hebel bei Ryzen 5000.",
                     "More boost under load. Together with a negative Curve Optimizer the best lever on "
                     "Ryzen 5000.")),
        "zen2": ("Auto / Enabled", MODERATE, "low",
                 _tr("Bei Ryzen 3000 bringt PBO nur wenig (meist < 2 %) — kann an bleiben, wenn der "
                     "Kühler reicht.",
                     "On Ryzen 3000 PBO brings little (usually < 2 %) — it can stay on if the cooler is "
                     "good enough.")),
    }
    rec, risk, impact, expl = texts[kind]
    return BiosSetting(
        key="pbo", category="CPU", name="Precision Boost Overdrive (PBO)", recommended=rec,
        default=_tr("Auto (= aus)", "Auto (= off)"),
        path="Advanced → AMD Overclocking → Precision Boost Overdrive", explanation=expl,
        risk=risk, impact=impact, paths=_amd_pbo_paths())


def _curve_optimizer(rec: str, expl: str, risk: str = MODERATE) -> BiosSetting:
    return BiosSetting(
        key="curve_optimizer", category="CPU", name="Curve Optimizer (Undervolting)", recommended=rec,
        default=_tr("0 (aus)", "0 (off)"), path="AMD Overclocking → Precision Boost Overdrive → Curve Optimizer",
        explanation=expl + _tr(" Danach stabil testen (z. B. OCCT oder CoreCycler, auch im Leerlauf — "
                               "Instabilität zeigt sich oft beim Surfen, nicht unter Last).",
                               " Then test stability (e.g. OCCT or CoreCycler, at idle too — instability "
                               "often shows while browsing, not under load)."),
        risk=risk, impact="medium", paths=_AMD_CO_PATHS)


def _fclk(value: str, expl: str) -> BiosSetting:
    return BiosSetting(
        key="fclk", category="Memory", name="Infinity Fabric (FCLK)", recommended=value, default="Auto",
        path="AMD Overclocking → DDR and Infinity Fabric Frequency/Timings → Infinity Fabric Frequency and "
             "Dividers → FCLK",
        explanation=expl + _tr(" Gibt es danach Abstürze oder USB-Aussetzer: zurück auf Auto.",
                               " If crashes or USB dropouts follow: back to Auto."),
        risk=MODERATE, impact="medium", paths={
            "asus": "Ai Tweaker → FCLK Frequency",
            "msi": "OC → FCLK Frequency",
        })


def _mcr() -> BiosSetting:
    return BiosSetting(
        key="mcr", category="Memory", name="Memory Context Restore", recommended="Enabled",
        default=_tr("Auto (meist aus)", "Auto (usually off)"),
        path="Advanced → AMD CBS → UMC Common Options → DDR Options → DDR Memory Features → Memory Context Restore",
        explanation=_tr("Spart das lange Speichertraining bei jedem Start (DDR5 auf AM5 sonst 20–60 s "
                        "schwarzer Bildschirm). Neuere BIOS-Versionen machen das stabil; gibt es danach "
                        "Startprobleme oder Abstürze nach dem Aufwachen: wieder Auto.",
                        "Saves the long memory training at every start (DDR5 on AM5 otherwise 20–60 s of black "
                        "screen). Newer BIOS versions make it stable; if start problems or crashes after "
                        "waking up follow: back to Auto."),
        risk=MODERATE, impact="low", paths={
            "asus": "Ai Tweaker → DRAM Timing Control → Memory Context Restore",
            "msi": "OC → Advanced DRAM Configuration → Memory Context Restore",
            "gigabyte": "Tweaker → Advanced Memory Settings → Memory Context Restore",
        })


def _cstates_amd() -> BiosSetting:
    return BiosSetting(
        key="cstates", category="Power", name="Global C-State Control",
        recommended=_tr("Auto / Enabled lassen", "Leave Auto / Enabled"),
        default="Auto",
        path="Advanced → AMD CBS → CPU Common Options → Global C-state Control",
        explanation=_tr("Oft wird „aus für weniger Latenz“ empfohlen — bei Ryzen bringt das in Spielen "
                        "praktisch nichts, kostet aber Strom im Leerlauf und kann den Einkern-Boost senken "
                        "(der höchste Boost braucht schlafende Nachbarkerne). Also an lassen.",
                        "“Off for less latency” is often recommended — on Ryzen it brings practically "
                        "nothing in games, but costs power at idle and can lower the single-core boost (the "
                        "highest boost needs sleeping neighbour cores). So leave it on."),
        risk=SAFE, impact="low", paths={
            "msi": "OC → Advanced CPU Configuration → Global C-state Control",
            "gigabyte": "Tweaker → Advanced CPU Settings → Global C-state Control",
        })


def _igpu_off(apu: bool = False) -> BiosSetting:
    if apu:
        return BiosSetting(
            key="igpu", category="GPU",
            name=_tr("Grafikspeicher der iGPU (UMA Frame Buffer)", "iGPU graphics memory (UMA frame buffer)"),
            recommended=_tr("ohne Grafikkarte: 2–4 GB  ·  mit Grafikkarte: iGPU aus",
                            "without a graphics card: 2–4 GB  ·  with a graphics card: iGPU off"),
            default=_tr("Auto (oft 512 MB)", "Auto (often 512 MB)"),
            path="Advanced → AMD CBS → NBIO Common Options → GFX Configuration → UMA Frame buffer Size",
            explanation=_tr("Spielst du über die integrierte Grafik, gibt ein größerer fester Grafikspeicher "
                            "vielen Spielen mehr Luft (genug RAM vorausgesetzt — 32 GB empfohlen). Mit "
                            "dedizierter Grafikkarte die iGPU ausschalten.",
                            "If you game on the integrated graphics, a larger fixed graphics memory gives many "
                            "games more room (enough RAM provided — 32 GB recommended). With a dedicated "
                            "graphics card turn the iGPU off."),
            risk=SAFE, impact="medium")
    return BiosSetting(
        key="igpu", category="GPU", name=_tr("Integrierte Grafik (iGPU) aus", "Integrated graphics (iGPU) off"),
        recommended=_tr("Disabled (nur mit Grafikkarte)", "Disabled (only with a graphics card)"),
        default="Auto / Enabled",
        path="Advanced → AMD CBS → NBIO Common Options → GFX Configuration → iGPU Configuration = iGPU Disabled",
        explanation=_tr("Ryzen 7000/9000 haben eine kleine iGPU. Mit dedizierter Grafikkarte braucht man sie "
                        "nicht; aus spart etwas Strom und Arbeitsspeicher und verhindert, dass Programme die "
                        "falsche GPU wählen. Monitor dann unbedingt an der Grafikkarte anschließen.",
                        "Ryzen 7000/9000 have a small iGPU. With a dedicated graphics card you don't need it; "
                        "off saves a little power and memory and keeps programs from picking the wrong GPU. "
                        "Then the monitor must be connected to the graphics card."),
        risk=MODERATE, impact="low", paths={
            "asus": "Advanced → NB Configuration → Integrated Graphics = Disabled",
            "msi": "Settings → Advanced → Integrated Graphics Configuration → Integrated Graphics = Disabled",
            "gigabyte": "Settings → IO Ports → Integrated Graphics = Disabled",
        })


def _cppc_x3d() -> BiosSetting:
    return BiosSetting(
        key="x3d_cppc", category="CPU", name=_tr("Kern-Zuteilung bei X3D mit zwei CCDs",
                                                 "Core assignment on X3D with two CCDs"),
        recommended="CPPC Dynamic Preferred Cores = Auto (Driver)", default="Auto",
        path="Advanced → AMD CBS → SMU Common Options → CPPC Dynamic Preferred Cores",
        explanation=_tr("Nur 7900X3D/7950X3D/9900X3D/9950X3D: Spiele sollen auf dem CCD mit dem 3D-Cache "
                        "laufen. Das übernimmt AMDs Chipsatz-Treiber zusammen mit dem Windows-Spielmodus und "
                        "der Xbox Game Bar — im BIOS auf Auto lassen, aktuellen Chipsatz-Treiber installieren. "
                        "Bei 7800X3D/9800X3D (ein CCD) gibt es nichts zu tun.",
                        "Only 7900X3D/7950X3D/9900X3D/9950X3D: games should run on the CCD with the 3D cache. "
                        "AMD's chipset driver does that together with Windows Game Mode and the Xbox Game Bar "
                        "— leave it on Auto in the BIOS, install the current chipset driver. On 7800X3D/9800X3D "
                        "(one CCD) there is nothing to do."),
        risk=SAFE, impact="medium")


# ── Intel ────────────────────────────────────────────────────────────────────

def _intel_default(gen: str) -> BiosSetting:
    rec, expl = {
        "rpl": ("Intel Default Settings = Performance (i9-K: PL1 = PL2 = 253 W, ICCMax 307 A)",
                _tr("Viele Boards ließen 13./14. Gen ohne Leistungsgrenze laufen — zusammen mit dem "
                    "Vmin-Shift-Fehler führte das zu Abstürzen und dauerhaft geschädigten CPUs. Intels "
                    "Vorgabe „Performance“ (bzw. „Extreme“ nur für i9-K mit sehr gutem Kühler) ist der sichere "
                    "Stand; in Spielen kostet sie praktisch nichts.",
                    "Many boards ran the 13th/14th gen without a power limit — together with the Vmin shift "
                    "bug this led to crashes and permanently damaged CPUs. Intel's “Performance” "
                    "profile (“Extreme” only for i9-K with a very good cooler) is the safe state; "
                    "it costs practically nothing in games.")),
        "adl": (_tr("PL1 / PL2 nach Intel (z. B. i9-12900K: 125 W / 241 W)",
                    "PL1 / PL2 as Intel specifies (e.g. i9-12900K: 125 W / 241 W)"),
                _tr("Board-Standard ist oft „unbegrenzt“ — das bringt in Spielen kaum etwas, macht die CPU "
                    "aber sehr heiß. Intels Werte stehen auf ark.intel.com.",
                    "The board default is often “unlimited” — that hardly helps in games but makes "
                    "the CPU very hot. Intel's values are on ark.intel.com.")),
        "arl": ("Intel Default Settings = Performance",
                _tr("Der von Intel empfohlene Stand für Core Ultra 200S; manche Boards starten mit "
                    "„unbegrenzt“.",
                    "The state Intel recommends for Core Ultra 200S; some boards start with "
                    "“unlimited”.")),
    }[gen]
    return BiosSetting(
        key="intel_power", category="Power",
        name=_tr("Leistungsgrenzen (Intel Default Settings)", "Power limits (Intel Default Settings)"),
        recommended=rec,
        default=_tr("je nach Board „unbegrenzt“", "“unlimited” on some boards"),
        path=_tr("CPU-/OC-Menü → Intel Default Settings bzw. Long/Short Duration Power Limit (PL1/PL2)",
                 "CPU / OC menu → Intel Default Settings or Long/Short Duration Power Limit (PL1/PL2)"),
        explanation=expl, risk=SAFE if gen == "rpl" else MODERATE, impact="medium", paths={
            "asus": _tr("Ai Tweaker → Intel Default Settings (ältere BIOS: Internal CPU Power Management → PL1/PL2)",
                        "Ai Tweaker → Intel Default Settings (older BIOS: Internal CPU Power Management → PL1/PL2)"),
            "msi": _tr("OC → Intel Default Settings (ältere BIOS: Advanced CPU Configuration → Long/Short Duration "
                       "Power Limit)",
                       "OC → Intel Default Settings (older BIOS: Advanced CPU Configuration → Long/Short Duration "
                       "Power Limit)"),
            "gigabyte": _tr("Tweaker → Intel Default Settings (ältere BIOS: Advanced CPU Settings → Turbo Power Limits)",
                            "Tweaker → Intel Default Settings (older BIOS: Advanced CPU Settings → Turbo Power Limits)"),
            "asrock": _tr("OC Tweaker → CPU Configuration → Intel Default Settings bzw. Long/Short Duration Power Limit",
                          "OC Tweaker → CPU Configuration → Intel Default Settings or Long/Short Duration Power Limit"),
        })


def _mce() -> BiosSetting:
    return BiosSetting(
        key="mce", category="CPU", name="Multi-Core Enhancement",
        recommended=_tr("Auto (Leistung) — bei Hitze: Disabled", "Auto (performance) — when too hot: Disabled"),
        default="Auto / Enabled",
        path=_tr("OC-Menü → Multi-Core Enhancement", "OC menu → Multi-Core Enhancement"),
        explanation=_tr("Lässt alle Kerne mit dem Einkern-Turbo laufen (außerhalb von Intels Vorgabe). Ein "
                        "paar Prozent mehr Leistung, dafür deutlich mehr Wärme — mit schwachem Kühler "
                        "Disabled wählen.",
                        "Runs all cores at the single-core turbo (outside Intel's spec). A few percent more "
                        "performance for clearly more heat — with a weak cooler choose Disabled."),
        risk=MODERATE, impact="low", paths={
            "asus": "Ai Tweaker → ASUS MultiCore Enhancement",
            "msi": "OC → Enhanced Turbo",
            "gigabyte": "Tweaker → Advanced CPU Settings → Enhanced Multi-Core Performance",
            "asrock": "OC Tweaker → CPU Configuration → Multi Core Enhancement",
        })


def _200s_boost() -> BiosSetting:
    return BiosSetting(
        key="200s_boost", category="Memory", name="Intel 200S Boost",
        recommended=_tr("Enabled (mit passendem RAM)", "Enabled (with fitting RAM)"),
        default="Disabled",
        path=_tr("OC-Menü → Intel 200S Boost (ab BIOS mit Microcode 0x114)",
                 "OC menu → Intel 200S Boost (from the BIOS with microcode 0x114)"),
        explanation=_tr("Intels offizielle, von der Garantie gedeckte Übertaktung für Core Ultra 200S: "
                        "schnellere Verbindung zwischen den Kacheln (D2D/NGU) und RAM bis DDR5-8000. Bringt "
                        "in Spielen einige Prozent — die größte Schwäche von Arrow Lake ist die Speicher-Latenz.",
                        "Intel's official overclock for Core Ultra 200S, covered by the warranty: a faster link "
                        "between the tiles (D2D/NGU) and RAM up to DDR5-8000. A few percent in games — Arrow "
                        "Lake's biggest weakness is memory latency."),
        risk=SAFE, impact="medium", paths={
            "asus": "Ai Tweaker → Intel(R) 200S Boost",
            "msi": "OC → Intel 200S Boost",
            "gigabyte": "Tweaker → Intel 200S Boost",
            "asrock": "OC Tweaker → Intel 200S Boost",
        })


def _ecores() -> BiosSetting:
    return BiosSetting(
        key="ecores", category="CPU", name="E-Cores", recommended=_tr("Enabled lassen", "Leave Enabled"),
        default="Enabled",
        path=_tr("CPU-Konfiguration → Active Efficient Cores = All", "CPU configuration → Active Efficient Cores = All"),
        explanation=_tr("Früher half das Abschalten der E-Cores manchen Spielen. Mit Windows 11 und dem Thread "
                        "Director landen Spiele heute auf den P-Cores; abschalten kostet Leistung bei allem "
                        "anderen. Nur bei einem einzelnen Spiel mit Problemen (alte Anti-Cheats) testen.",
                        "Turning the E-cores off used to help some games. With Windows 11 and the Thread "
                        "Director games land on the P-cores today; turning them off costs performance in "
                        "everything else. Only test it for a single game with problems (old anti-cheats)."),
        risk=SAFE, impact="low")


# ═══════════════════════════════════════════════════════════════════════════════
# Profiles
# ═══════════════════════════════════════════════════════════════════════════════

def _am5_base(x3d: str = "", zen: str = "zen5") -> list:
    """Shared AM5 settings."""
    s = [
        _memory_profile("amd", "DDR5", _tr("DDR5-6000 CL30 ist der Sweet Spot", "DDR5-6000 CL30 is the sweet spot"),
                        _tr("AM5 läuft am besten mit DDR5-6000 bis -6400 im 1:1-Modus (UCLK = MCLK).",
                            "AM5 runs best with DDR5-6000 to -6400 in 1:1 mode (UCLK = MCLK).")),
        _fclk(_tr("2000 MHz (Zen 5 oft auch 2100)", "2000 MHz (Zen 5 often 2100 too)") if zen == "zen5" else "2000 MHz",
              _tr("Die Verbindung zwischen Kernen und Speicher-Controller. Bei DDR5-6000 sind 2000 MHz "
                  "üblich und stabil; Auto lässt oft 1733–1800 MHz liegen.",
                  "The link between the cores and the memory controller. With DDR5-6000, 2000 MHz is usual "
                  "and stable; Auto often leaves it at 1733–1800 MHz.")),
        _mcr(),
        _cstates_amd(),
        _rebar("amd"),
        _pcie_gpu(),
        _igpu_off(),
        _csm(),
        _secure_boot(),
        _bios_update(_tr("Neue AGESA-Versionen bringen bei AM5 spürbar kürzere Startzeiten, besseren "
                         "RAM-Support und Leistungs-Fixes (Zen 5: „2-Kern-Latenz“-Update).",
                         "New AGESA versions bring noticeably shorter start times on AM5, better RAM support "
                         "and performance fixes (Zen 5: the “core-to-core latency” update).")),
        _autoinstall(),
    ]
    return s


def _build_profiles() -> list:
    """All platforms in the app's language (newest first per vendor)."""
    rebar_am4 = _tr("AM4 braucht dafür ein BIOS von 2021 oder neuer.", "AM4 needs a BIOS from 2021 or newer for it.")
    return [
        # ── AMD AM5 ──────────────────────────────────────────────────────────
        BiosProfile(
            id="am5_zen5_x3d", name="AMD Ryzen 9000X3D (Zen 5 + 3D V-Cache) — AM5",
            cpus="Ryzen 7 9800X3D, Ryzen 9 9900X3D, 9950X3D",
            platform="AM5 — X870E / X870 / B850 / B840 / X670E / X670 / B650 / A620", brand="amd",
            settings=[_pbo("zen5_x3d"),
                      _curve_optimizer("All Cores, Negative 15–25",
                                       _tr("Die meisten 9800X3D vertragen −15 bis −25; weniger Spannung = mehr Boost "
                                           "bei gleicher Temperatur.",
                                           "Most 9800X3D take −15 to −25; less voltage = more boost at the same "
                                           "temperature.")),
                      _cppc_x3d()] + _am5_base(zen="zen5"),
            notes=_tr("Die beste Gaming-CPU-Familie — der 3D-Cache macht den größten Teil der Arbeit. EXPO "
                      "aktivieren ist Pflicht, PBO/Curve Optimizer sind Feinschliff.",
                      "The best gaming CPU family — the 3D cache does most of the work. Enabling EXPO is a "
                      "must, PBO / Curve Optimizer are fine-tuning.")),
        BiosProfile(
            id="am5_zen5", name="AMD Ryzen 9000 (Zen 5) — AM5",
            cpus="Ryzen 5 9600(X), Ryzen 7 9700X, Ryzen 9 9900X, 9950X",
            platform="AM5 — X870E / X870 / B850 / B840 / X670E / X670 / B650 / A620", brand="amd",
            settings=[_pbo("zen5"),
                      _curve_optimizer("All Cores, Negative 10–20",
                                       _tr("Zen 5 verträgt meist −10 bis −20.", "Zen 5 usually takes −10 to −20.")),
                      ] + _am5_base(zen="zen5"),
            notes=_tr("9600X/9700X kommen ab Werk mit 65-W-Grenze; PBO (oder der 105-W-Modus mancher BIOS) hebt "
                      "sie an — in Spielen bringt das nur wenig.",
                      "9600X/9700X come with a 65-W limit; PBO (or the 105-W mode of some BIOS versions) raises "
                      "it — in games that brings little.")),
        BiosProfile(
            id="am5_zen4_x3d", name="AMD Ryzen 7000X3D (Zen 4 + 3D V-Cache) — AM5",
            cpus="Ryzen 7 7800X3D, Ryzen 9 7900X3D, 7950X3D",
            platform="AM5 — X870E / X870 / B850 / X670E / X670 / B650 / A620", brand="amd",
            settings=[_pbo("zen4_x3d"),
                      _curve_optimizer("All Cores, Negative 15–30",
                                       _tr("Der einzige Hebel bei den 7000X3D: weniger Spannung lässt sie höher "
                                           "boosten.",
                                           "The only lever on the 7000X3D: less voltage lets them boost higher.")),
                      _cppc_x3d()] + _am5_base(zen="zen4"),
            notes=_tr("Wichtig: BIOS aktuell halten — frühe Versionen ließen zu hohe SoC-Spannungen zu (2023 "
                      "durchgebrannte 7800X3D). Aktuelle BIOS begrenzen die SoC-Spannung auf ≤ 1,3 V.",
                      "Important: keep the BIOS up to date — early versions allowed too high SoC voltages "
                      "(burnt 7800X3D in 2023). Current BIOS versions limit the SoC voltage to ≤ 1.3 V.")),
        BiosProfile(
            id="am5_zen4", name="AMD Ryzen 7000 (Zen 4) — AM5",
            cpus="Ryzen 5 7600(X), Ryzen 7 7700(X), Ryzen 9 7900(X), 7950X",
            platform="AM5 — X870E / X870 / B850 / X670E / X670 / B650 / A620", brand="amd",
            settings=[_pbo("zen4"),
                      _curve_optimizer("All Cores, Negative 10–20",
                                       _tr("Senkt Temperatur und hebt den Boost — bei Ryzen 7000 der beste Hebel.",
                                           "Lowers the temperature and raises the boost — the best lever on "
                                           "Ryzen 7000."))
                      ] + _am5_base(zen="zen4")),
        BiosProfile(
            id="am5_apu", name="AMD Ryzen 8000G / 8000F (Zen 4 APU) — AM5",
            cpus="Ryzen 5 8500G / 8600G, Ryzen 7 8700G, Ryzen 5 8400F, Ryzen 7 8700F",
            platform="AM5 — B650 / A620 / X670 / B850", brand="amd",
            settings=[
                _memory_profile("amd", "DDR5", _tr("DDR5-6000 oder schneller", "DDR5-6000 or faster"),
                                _tr("Spielst du über die integrierte Grafik, ist schneller RAM besonders wichtig — "
                                    "die iGPU hat keinen eigenen Speicher.",
                                    "If you game on the integrated graphics, fast RAM matters most — the iGPU "
                                    "has no memory of its own.")),
                _igpu_off(apu=True), _pbo("zen4"),
                _curve_optimizer("All Cores, Negative 10–20",
                                 _tr("Senkt Temperatur und hebt den Boost.", "Lowers the temperature and raises the boost.")),
                _mcr(), _cstates_amd(), _rebar("amd"), _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Neue AGESA-Versionen verbessern RAM-Support und Startzeiten.",
                                 "New AGESA versions improve RAM support and start times.")), _autoinstall()],
            notes=_tr("Die 8000G/8000F haben PCIe 4.0 und — bei 8500G/8400F — weniger Lanes; für eine schnelle "
                      "Grafikkarte ist ein Ryzen 7000/9000 die bessere Wahl.",
                      "The 8000G/8000F have PCIe 4.0 and — on 8500G/8400F — fewer lanes; for a fast graphics "
                      "card a Ryzen 7000/9000 is the better choice.")),

        # ── AMD AM4 ──────────────────────────────────────────────────────────
        BiosProfile(
            id="am4_zen3_x3d", name="AMD Ryzen 5000X3D (Zen 3 + 3D V-Cache) — AM4",
            cpus="Ryzen 5 5600X3D, Ryzen 7 5700X3D, 5800X3D",
            platform="AM4 — X570 / B550 / X470 / B450 / A520", brand="amd",
            settings=[
                _memory_profile("amd", "DDR4", _tr("DDR4-3600 CL16 ist der Sweet Spot", "DDR4-3600 CL16 is the sweet spot")),
                _fclk(_tr("1800 MHz (bei DDR4-3600)", "1800 MHz (with DDR4-3600)"),
                      _tr("1:1 mit dem RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900.",
                          "1:1 with the RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900.")),
                _curve_optimizer(_tr("nur wenn angeboten: All Cores, Negative 15–30",
                                     "only when offered: All Cores, Negative 15–30"),
                                 _tr("Die 5000X3D sind gesperrt; neuere BIOS (AGESA 1.2.0.8+) bieten den Curve "
                                     "Optimizer teils an, MSI nennt es „Kombo Strike“ (OC-Menü, Stufe 1–3).",
                                     "The 5000X3D are locked; newer BIOS versions (AGESA 1.2.0.8+) partly offer the "
                                     "Curve Optimizer, MSI calls it “Kombo Strike” (OC menu, level 1–3).")),
                _rebar("amd", rebar_am4), _pcie_gpu(), _csm(),
                _secure_boot(), _bios_update(_tr("Für 5000X3D auf älteren Boards ist ein BIOS-Update Pflicht "
                                                 "(AGESA 1.2.0.x).",
                                                 "For a 5000X3D on older boards a BIOS update is a must "
                                                 "(AGESA 1.2.0.x).")), _autoinstall()],
            notes=_tr("PBO und Takt-Übertaktung sind bei den 5000X3D gesperrt — EXPO/XMP und FCLK 1:1 sind die "
                      "wichtigsten Punkte.",
                      "PBO and clock overclocking are locked on the 5000X3D — EXPO/XMP and FCLK 1:1 are the most "
                      "important points.")),
        BiosProfile(
            id="am4_zen3", name="AMD Ryzen 5000 (Zen 3) — AM4",
            cpus="Ryzen 5 5500 / 5600(X), Ryzen 7 5700X / 5800X, Ryzen 9 5900X / 5950X",
            platform="AM4 — X570 / B550 / X470 / B450 / A520", brand="amd",
            settings=[
                _memory_profile("amd", "DDR4", _tr("DDR4-3600 CL16 ist der Sweet Spot", "DDR4-3600 CL16 is the sweet spot")),
                _fclk(_tr("1800 MHz (bei DDR4-3600)", "1800 MHz (with DDR4-3600)"),
                      _tr("1:1 mit dem RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900 (nicht jede CPU schafft 1900).",
                          "1:1 with the RAM: DDR4-3600 → FCLK 1800, DDR4-3800 → 1900 (not every CPU makes 1900).")),
                _pbo("zen3"),
                _curve_optimizer(_tr("All Cores, Negative 10–20 (besser: pro Kern)", "All Cores, Negative 10–20 (better: per core)"),
                                 _tr("Zen 3 reagiert stark auf den Curve Optimizer; die besten zwei Kerne "
                                     "vertragen meist weniger.",
                                     "Zen 3 responds strongly to the Curve Optimizer; the best two cores usually "
                                     "take less.")),
                _rebar("amd", rebar_am4), _pcie_gpu(), _csm(),
                _secure_boot(), _bios_update(_tr("Auf 400er-Boards ist ein BIOS-Update für Ryzen 5000 Pflicht; "
                                                 "neuere AGESA-Versionen beheben USB-Aussetzer.",
                                                 "On 400-series boards a BIOS update is a must for Ryzen 5000; "
                                                 "newer AGESA versions fix USB dropouts.")), _autoinstall()]),
        BiosProfile(
            id="am4_apu", name="AMD Ryzen 5000G / 4000G / 3000G / 2000G (APU) — AM4",
            cpus="Ryzen 3 5300G, Ryzen 5 5600G / 4600G / 3400G / 2400G, Ryzen 7 5700G",
            platform="AM4 — B550 / A520 / X570 / B450 / A320", brand="amd",
            settings=[
                _memory_profile("amd", "DDR4", _tr("DDR4-3600 oder schneller", "DDR4-3600 or faster"),
                                _tr("Die iGPU nutzt den Arbeitsspeicher als Grafikspeicher — schneller RAM bringt "
                                    "ihr am meisten.",
                                    "The iGPU uses the system memory as graphics memory — fast RAM helps it most.")),
                _igpu_off(apu=True),
                _fclk("1800–2000 MHz", _tr("Die APUs schaffen oft FCLK 2000 (DDR4-4000 1:1).",
                                           "The APUs often make FCLK 2000 (DDR4-4000 1:1).")),
                _rebar("amd", _tr("Bei den APUs nur mit 5000G und aktuellem BIOS.",
                                  "On the APUs only with a 5000G and a current BIOS.")), _pcie_gpu(), _csm(),
                _secure_boot(), _bios_update(_tr("Neue AGESA-Versionen verbessern den APU-Support.",
                                                 "New AGESA versions improve APU support.")), _autoinstall()],
            notes=_tr("5600G/5700G haben nur PCIe 3.0 — für eine schnelle Grafikkarte nicht ideal.",
                      "5600G/5700G have PCIe 3.0 only — not ideal for a fast graphics card.")),
        BiosProfile(
            id="am4_zen2", name="AMD Ryzen 3000 (Zen 2) — AM4",
            cpus="Ryzen 5 3600(X), Ryzen 7 3700X / 3800X, Ryzen 9 3900X / 3950X",
            platform="AM4 — X570 / B550 / X470 / B450", brand="amd",
            settings=[
                _memory_profile("amd", "DDR4", "DDR4-3600 CL16"),
                _fclk(_tr("1800 MHz (bei DDR4-3600)", "1800 MHz (with DDR4-3600)"),
                      _tr("Zen 2 schafft fast immer 1800 MHz 1:1, 1866–1900 nur selten.",
                          "Zen 2 almost always makes 1800 MHz 1:1, 1866–1900 only rarely.")),
                _pbo("zen2"),
                _rebar("amd", _tr("Ryzen 3000 unterstützt es seit 2021 auf 400er/500er-Boards — BIOS-Update nötig.",
                                  "Ryzen 3000 supports it on 400/500-series boards since 2021 — BIOS update needed.")),
                _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Für Resizable BAR und Windows-11-TPM ist ein BIOS ab 2021 nötig.",
                                 "Resizable BAR and the Windows 11 TPM need a BIOS from 2021 on.")), _autoinstall()]),
        BiosProfile(
            id="am4_zen1", name="AMD Ryzen 1000 / 2000 (Zen / Zen+) — AM4",
            cpus="Ryzen 5 1600 / 2600, Ryzen 7 1700 / 2700X",
            platform="AM4 — X470 / B450 / X370 / B350", brand="amd",
            settings=[
                _memory_profile("amd", "DDR4", _tr("DDR4-3200 (Zen+: oft 3466)", "DDR4-3200 (Zen+: often 3466)"),
                                _tr("Zen/Zen+ sind beim RAM wählerisch — klappt das Profil nicht, den Takt eine "
                                    "Stufe senken.",
                                    "Zen/Zen+ are picky about RAM — if the profile doesn't work, lower the speed "
                                    "one step.")),
                _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Neuere BIOS-Versionen verbessern die RAM-Kompatibilität deutlich.",
                                 "Newer BIOS versions improve RAM compatibility clearly.")), _autoinstall()],
            notes=_tr("Resizable BAR gibt es für Ryzen 1000/2000 nicht. Ein Ryzen 5000(X3D) passt meist mit "
                      "BIOS-Update in dasselbe Board — der größte Sprung für wenig Geld.",
                      "Ryzen 1000/2000 have no Resizable BAR. A Ryzen 5000(X3D) usually fits the same board "
                      "after a BIOS update — the biggest step for little money.")),

        # ── Intel ────────────────────────────────────────────────────────────
        BiosProfile(
            id="lga1851_arl", name="Intel Core Ultra 200S (Arrow Lake) — LGA1851",
            cpus="Core Ultra 5 245K / 225, Core Ultra 7 265K, Core Ultra 9 285K",
            platform="LGA1851 — Z890 / B860 / H810", brand="intel",
            settings=[
                _memory_profile("intel", "DDR5", _tr("DDR5-6400 bis -8000 (CUDIMM)", "DDR5-6400 to -8000 (CUDIMM)"),
                                _tr("Arrow Lake profitiert stark von schnellem RAM; ab DDR5-8000 lohnen CUDIMM-Module.",
                                    "Arrow Lake gains a lot from fast RAM; from DDR5-8000 on, CUDIMM modules pay off.")),
                _200s_boost(), _intel_default("arl"), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Pflicht bei Arrow Lake: das BIOS mit Microcode 0x114 (oder neuer) behebt die "
                                 "schwache Spieleleistung zum Start und bringt „200S Boost“.",
                                 "A must on Arrow Lake: the BIOS with microcode 0x114 (or newer) fixes the weak "
                                 "launch gaming performance and brings “200S Boost”."), impact="high"),
                _autoinstall()],
            notes=_tr("Core Ultra 200S haben kein Hyper-Threading. Windows aktuell halten — die Leistungs-Fixes "
                      "kamen zusammen mit Windows-Updates.",
                      "Core Ultra 200S have no Hyper-Threading. Keep Windows up to date — the performance fixes "
                      "came together with Windows updates.")),
        BiosProfile(
            id="lga1700_rpl", name=_tr("Intel Core 13./14. Gen (Raptor Lake) — LGA1700",
                                       "Intel Core 13th/14th gen (Raptor Lake) — LGA1700"),
            cpus="Core i5-13400–14600K, Core i7-13700K / 14700K, Core i9-13900K / 14900K",
            platform="LGA1700 — Z790 / B760 / H770 / Z690 / B660", brand="intel",
            settings=[
                _bios_update(_tr("SEHR WICHTIG: BIOS mit Microcode 0x12F (oder neuer) — behebt den „Vmin Shift“, "
                                 "der 13./14.-Gen-CPUs (vor allem i7/i9) dauerhaft instabil machen kann. Ältere "
                                 "BIOS-Versionen nicht weiter verwenden.",
                                 "VERY IMPORTANT: the BIOS with microcode 0x12F (or newer) — fixes the “Vmin "
                                 "shift” that can make 13th/14th gen CPUs (above all i7/i9) permanently "
                                 "unstable. Don't keep using older BIOS versions."), impact="high"),
                _intel_default("rpl"),
                _memory_profile("intel", "DDR5", _tr("DDR5-6000 bis -7200 (DDR4-Boards: DDR4-3600)",
                                                     "DDR5-6000 to -7200 (DDR4 boards: DDR4-3600)")),
                _ecores(), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(), _autoinstall()],
            notes=_tr("Abstürze in Spielen („Out of video memory“, Shader-Fehler) sind bei 13./14. Gen ein "
                      "typisches Zeichen für den Vmin-Shift — erst BIOS-Update + Intel Default Settings, dann weiter "
                      "optimieren. Intel hat die Garantie dieser CPUs verlängert.",
                      "Crashes in games (“Out of video memory”, shader errors) are a typical sign of the "
                      "Vmin shift on 13th/14th gen — first the BIOS update + Intel Default Settings, then tune "
                      "further. Intel extended the warranty of these CPUs.")),
        BiosProfile(
            id="lga1700_adl", name=_tr("Intel Core 12. Gen (Alder Lake) — LGA1700",
                                       "Intel Core 12th gen (Alder Lake) — LGA1700"),
            cpus="Core i3-12100, Core i5-12400 / 12600K, Core i7-12700K, Core i9-12900K",
            platform=_tr("LGA1700 — Z690 / B660 / H670 / H610 (auch Z790/B760)",
                         "LGA1700 — Z690 / B660 / H670 / H610 (also Z790/B760)"), brand="intel",
            settings=[
                _memory_profile("intel", "DDR5", _tr("DDR5-6000 (DDR4-Boards: DDR4-3600 im Gear 1)",
                                                     "DDR5-6000 (DDR4 boards: DDR4-3600 in Gear 1)")),
                _intel_default("adl"), _ecores(), _rebar("intel"), _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Neuere BIOS-Versionen verbessern den DDR5-Support deutlich.",
                                 "Newer BIOS versions improve DDR5 support clearly.")), _autoinstall()],
            notes=_tr("Unter Windows 10 verteilt der Thread Director die Kerne schlechter — Windows 11 holt bei "
                      "12. Gen spürbar mehr heraus.",
                      "On Windows 10 the Thread Director assigns cores worse — Windows 11 gets noticeably more "
                      "out of the 12th gen.")),
        BiosProfile(
            id="lga1200", name=_tr("Intel Core 10./11. Gen (Comet / Rocket Lake) — LGA1200",
                                   "Intel Core 10th/11th gen (Comet / Rocket Lake) — LGA1200"),
            cpus="Core i5-10400–11600K, Core i7-10700K / 11700K, Core i9-10900K / 11900K",
            platform="LGA1200 — Z590 / B560 / H570 / Z490 / B460 / H410", brand="intel",
            settings=[
                _memory_profile("intel", "DDR4", _tr("DDR4-3200 bis -3600 (11. Gen: Gear 1)",
                                                     "DDR4-3200 to -3600 (11th gen: Gear 1)"),
                                _tr("Bei 11. Gen den Speicher-Controller im „Gear 1“ lassen — Gear 2 kostet Latenz.",
                                    "On the 11th gen keep the memory controller in “Gear 1” — Gear 2 "
                                    "costs latency.")),
                _mce(),
                _rebar("intel", _tr("Offiziell ab 11. Gen auf 500er-Boards; viele Z490-Boards haben es per "
                                    "BIOS-Update für 10. Gen nachgereicht.",
                                    "Officially from the 11th gen on 500-series boards; many Z490 boards added it "
                                    "for the 10th gen with a BIOS update.")),
                _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Für Resizable BAR und Windows-11-TPM ist ein BIOS ab 2021 nötig.",
                                 "Resizable BAR and the Windows 11 TPM need a BIOS from 2021 on.")), _autoinstall()]),
        BiosProfile(
            id="lga1151", name=_tr("Intel Core 8./9. Gen (Coffee Lake) — LGA1151",
                                   "Intel Core 8th/9th gen (Coffee Lake) — LGA1151"),
            cpus="Core i5-8400–9600K, Core i7-8700K / 9700K, Core i9-9900K",
            platform="LGA1151 v2 — Z390 / Z370 / B365 / B360 / H370", brand="intel",
            settings=[
                _memory_profile("intel", "DDR4", "DDR4-3200"),
                _mce(), _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Neuere BIOS-Versionen enthalten Sicherheits-Microcode und teils Resizable BAR "
                                 "(nur manche Z390-Boards, inoffiziell).",
                                 "Newer BIOS versions contain security microcode and partly Resizable BAR (only "
                                 "some Z390 boards, unofficially).")), _autoinstall()],
            notes=_tr("Resizable BAR gibt es offiziell erst ab Intel 10./11. Gen.",
                      "Resizable BAR officially exists from Intel's 10th/11th gen on.")),

        # ── everything else ──────────────────────────────────────────────────
        BiosProfile(
            id="generic", name=_tr("Andere / unbekannte Plattform — Grundlagen", "Other / unknown platform — basics"),
            cpus=_tr("jede Desktop-CPU", "any desktop CPU"), platform=_tr("jedes Board", "any board"), brand="any",
            settings=[
                BiosSetting(key="memory_profile", category="Memory",
                            name=_tr("XMP / EXPO / DOCP-Profil", "XMP / EXPO / DOCP profile"),
                            recommended=_tr("Profil 1", "Profile 1"),
                            default=_tr("Aus — JEDEC-Standardtakt", "Off — JEDEC stock speed"),
                            path=_tr("OC-/Tweaker-Menü → Speicherprofil → Profil 1",
                                     "OC / Tweaker menu → memory profile → Profile 1"),
                            explanation=_tr("Ohne Profil läuft der RAM nur mit dem Standardtakt — der größte "
                                            "kostenlose Gewinn im BIOS.",
                                            "Without a profile the RAM runs at stock speed only — the biggest free "
                                            "gain in the BIOS."),
                            risk=SAFE, impact="high", detect_key="expo_xmp"),
                _rebar("any"), _pcie_gpu(), _csm(), _secure_boot(),
                _bios_update(_tr("Neuere BIOS-Versionen verbessern RAM-Kompatibilität und Sicherheit.",
                                 "Newer BIOS versions improve RAM compatibility and security.")), _autoinstall()],
            notes=_tr("Laptops: Die meisten Laptop-BIOS bieten diese Optionen nicht — dort lohnt vor allem der "
                      "Hersteller-Leistungsmodus (z. B. „Turbo“/„Performance“) im Hersteller-Tool.",
                      "Laptops: most laptop BIOS versions don't offer these options — there the maker's "
                      "performance mode (e.g. “Turbo” / “Performance”) in the maker's tool is "
                      "what pays off.")),
    ]


_CACHE: dict = {}


def profiles() -> list:
    """All platforms in the app's language (built once per language)."""
    lang = current_lang()
    if lang not in _CACHE:
        _CACHE[lang] = _build_profiles()
    return _CACHE[lang]


PROFILES: list[BiosProfile] = profiles()        # in the language at import (the app imports it late)


def get_profile(pid: str) -> Optional[BiosProfile]:
    return next((p for p in profiles() if p.id == pid), None)


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
    first = get_profile(pid)
    return [first] + [p for p in profiles() if p is not first]


def get_impact_color(impact: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(impact, "#6b7280")


def get_risk_color(risk: str) -> str:
    return {"safe": "#22c55e", "moderate": "#f59e0b", "advanced": "#ef4444"}.get(risk, "#6b7280")
