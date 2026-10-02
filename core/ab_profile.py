"""
MSI Afterburner per-GPU profile file — parser/writer (pure logic, no process
control; see AfterburnerController in nvtune_core for that).

Afterburner keeps ALL settings of one graphics card in ONE file next to its exe,
named after the card's PnP identity:

    <Afterburner>\\Profiles\\VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg

It is an INI file: [Startup] (applied at boot), [Profile1] … [Profile5] (the
five slots), [Defaults], [Settings], [PreSuspendedMode]. A slot, from a real
file (VFCurve shortened):

    [Profile2]
    Format=2
    PowerLimit=80            % of the card's STOCK power limit
    ThermalLimit=75
    CoreClkBoost=-350000     core offset in kHz (-350 MHz); 1000000 = custom curve
    VFCurve=0000020080000000000000000000E1430080B6430000AFC3...
    MemClkBoost=600000       memory offset in kHz (+600 MHz)
    FanMode=0
    FanSpeed=80

VFCurve is a hex-encoded little-endian blob:
    header  <uint32 version = 0x00020000><uint32 point count><4 bytes reserved>
    points  count x <float voltage mV><float base MHz><float offset MHz>
    then zero padding and further data (lock parameters) that is kept verbatim.
A point whose base frequency is 225.0 MHz is unused by the GPU (stock
behaviour, offset ignored). The effective clock of a point is base + offset;
a plain core offset is the same offset on every point.

Cross-checked sources: a real RTX 3090 profile (qdm12/reinstall), the hekmon/aiup
"msiaf" Go package, KingAi_MSi_afterburner_overclocker_tools, Annihil's VF-curve
gist. Afterburner reads this file only when it STARTS and keeps the slots in
memory ("MSIAfterburner.exe -ProfileN" applies the in-memory copy) — a writer
must close Afterburner, write, and start it again.

The FanMode encoding differs between those sources (0 = auto vs. 1 = auto; a
live 4.6.6 install with the fan untouched shows FanMode=1), so this module never
sets fan values itself — a newly created slot copies them from [Defaults] or
[Startup], i.e. from what Afterburner itself wrote.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import Optional


# ── VFCurve blob ──────────────────────────────────────────────────────────────

VF_VERSION        = 0x00020000
VF_HEADER_SIZE    = 12
VF_POINT_SIZE     = 12
VF_INACTIVE_BASE  = 225.0      # base MHz of points the GPU does not use
CORE_CURVE_MARKER = 1000000    # CoreClkBoost value Afterburner writes for a custom curve
MAX_CURVE_SHIFT   = 1000       # MHz — sanity bound for any per-point offset we write
# Points ABOVE a flat start (lock point / cap) are written this far below it.
# The GPU adds our offsets to its LIVE curve, which shifts with temperature —
# and not evenly: on an RTX 4080 the live clock was 30 MHz below the stored
# curve at 1075 mV but 60 MHz above it at 920 mV. A curve that was flat in the
# file was then not flat on the card, and the GPU boosted past the point under
# test (to 920 mV instead of 875 mV). Clearly lower points above make the flat
# start the fastest point no matter how the live curve is shifted.
ABOVE_FLAT_DROP_MHZ = 100


class ProfileError(ValueError):
    """The profile file can't be read or changed safely."""


@dataclass
class VFPoint:
    index:      int
    voltage_mv: float
    base_mhz:   float
    offset_mhz: float

    @property
    def active(self) -> bool:
        return self.voltage_mv > 0 and abs(self.base_mhz - VF_INACTIVE_BASE) > 0.5

    @property
    def effective_mhz(self) -> float:
        return self.base_mhz + self.offset_mhz


class VFCurve:
    """One VFCurve blob. Only the offset floats of the declared points are ever
    changed; every other byte (header, padding, trailing data) is kept."""

    def __init__(self, raw: bytes):
        if len(raw) < VF_HEADER_SIZE + VF_POINT_SIZE:
            raise ProfileError("VFCurve zu kurz")
        version, count = struct.unpack_from("<II", raw, 0)
        if version != VF_VERSION:
            raise ProfileError(f"unbekannte VFCurve-Version {version:#010x}")
        n = min(count, (len(raw) - VF_HEADER_SIZE) // VF_POINT_SIZE)
        if n <= 0:
            raise ProfileError("VFCurve enthält keine Punkte")
        self._raw  = bytearray(raw)
        self.count = n

    @classmethod
    def from_hex(cls, text: str) -> "VFCurve":
        s = (text or "").strip()
        if not s:
            raise ProfileError("VFCurve ist leer")
        try:
            return cls(bytes.fromhex(s))
        except ValueError as e:
            raise ProfileError(f"VFCurve ist kein gültiger Hex-Wert ({e})") from None

    def to_hex(self) -> str:
        return self._raw.hex().upper()

    def copy(self) -> "VFCurve":
        return VFCurve(bytes(self._raw))

    def points(self) -> list[VFPoint]:
        out = []
        for i in range(self.count):
            v, f, o = struct.unpack_from("<fff", self._raw, VF_HEADER_SIZE + i * VF_POINT_SIZE)
            out.append(VFPoint(i, v, f, o))
        return out

    def active_points(self) -> list[VFPoint]:
        return [p for p in self.points() if p.active]

    def _set_offset(self, index: int, mhz: float):
        struct.pack_into("<f", self._raw,
                         VF_HEADER_SIZE + index * VF_POINT_SIZE + 8, float(mhz))

    def with_uniform_offset(self, mhz: int) -> "VFCurve":
        """Plain core offset: the same offset on every point (what Afterburner
        itself writes when only the core-clock slider was moved)."""
        if abs(mhz) > MAX_CURVE_SHIFT:
            raise ProfileError(f"Core-Offset {mhz:+d} MHz außerhalb ±{MAX_CURVE_SHIFT} MHz")
        c = self.copy()
        for p in c.points():
            if p.voltage_mv > 0:
                c._set_offset(p.index, mhz)
        return c

    def lock_point(self, lock_mv: float) -> VFPoint:
        """The active point closest to lock_mv (ties -> the lower voltage)."""
        act = self.active_points()
        if not act:
            raise ProfileError("VFCurve hat keine aktiven Punkte")
        p = min(act, key=lambda q: (abs(q.voltage_mv - lock_mv), q.voltage_mv))
        if abs(p.voltage_mv - lock_mv) > 25:
            raise ProfileError(
                f"{lock_mv:.0f} mV liegt außerhalb der Kurve "
                f"({act[0].voltage_mv:.0f}–{act[-1].voltage_mv:.0f} mV)")
        return p

    def with_flatline(self, lock_mv: float, target_mhz: float) -> "VFCurve":
        """Classic curve undervolt: the point at lock_mv runs target_mhz and every
        higher point is set ABOVE_FLAT_DROP_MHZ below it, so the GPU never boosts
        past that voltage (the usual "drag the points right of it down" — the
        lock point is the fastest one even on a shifted live curve). Points below
        are shifted by the same amount (capped at target)."""
        # floor(), not round(): with fractional base values a rounded offset
        # could put a point up to 0.5 MHz ABOVE the frequency that was tested.
        lock  = self.lock_point(lock_mv)
        delta = math.floor(target_mhz - lock.base_mhz)
        if abs(delta) > MAX_CURVE_SHIFT:
            raise ProfileError(
                f"Kurven-Offset {delta:+d} MHz bei {lock.voltage_mv:.0f} mV "
                f"außerhalb ±{MAX_CURVE_SHIFT} MHz (Ziel {target_mhz:.0f} MHz)")
        c = self.copy()
        for p in c.points():
            if p.voltage_mv <= 0:
                continue
            if not p.active:                       # ignored by the GPU — keep it tame
                off = delta
            elif p.voltage_mv < lock.voltage_mv:
                off = min(delta, math.floor(target_mhz - p.base_mhz))
            elif p.index == lock.index:
                off = delta
            else:
                off = math.floor(target_mhz - ABOVE_FLAT_DROP_MHZ - p.base_mhz)
            if abs(off) > MAX_CURVE_SHIFT:
                raise ProfileError(
                    f"Kurven-Offset {off:+d} MHz bei {p.voltage_mv:.0f} mV außerhalb "
                    f"±{MAX_CURVE_SHIFT} MHz")
            c._set_offset(p.index, off)
        return c

    def with_anchor_curve(self, anchors, cap_mv: float = 0) -> "VFCurve":
        """Own V/F curve from measured points: anchors = [(voltage_mv, mhz)],
        each the highest frequency found stable at that voltage (margins already
        taken off). Between two anchors the OFFSET is interpolated linearly;
        below the lowest anchor the smallest measured offset is used (untested
        territory — the safe side); the highest anchor — or cap_mv, if given and
        lower — is the top of the curve: every point above it is written
        ABOVE_FLAT_DROP_MHZ lower, so the GPU never boosts past it, however its
        live curve is shifted. Below the top no point may run faster than any
        point above it: going down the curve every frequency is clamped to the
        one above (only ever lowered, never raised past a measurement)."""
        act = self.active_points()
        if not act:
            raise ProfileError("VFCurve hat keine aktiven Punkte")
        pts = sorted((float(mv), float(mhz)) for mv, mhz in anchors)
        if not pts:
            raise ProfileError("keine Messpunkte für die Kurve")
        aoff = []                                  # (point voltage, offset, target)
        for mv, mhz in pts:
            p = self.lock_point(mv)
            aoff.append((p.voltage_mv, mhz - p.base_mhz, mhz))
        low_off = min(o for _v, o, _t in aoff)
        top_v, _o, top_t = aoff[-1]

        def target(p):                               # before the cap / monotony
            v = p.voltage_mv
            if v >= top_v:
                return top_t                         # flat above the highest anchor
            if v < aoff[0][0]:
                return p.base_mhz + low_off
            for (v1, o1, _t1), (v2, o2, _t2) in zip(aoff, aoff[1:]):
                if v1 <= v <= v2:
                    return p.base_mhz + o1 + (o2 - o1) * (v - v1) / (v2 - v1)
            return p.base_mhz + low_off              # pragma: no cover (sorted anchors)

        c = self.copy()
        pts_all = [p for p in c.points() if p.voltage_mv > 0]
        eff = {p.index: target(p) for p in pts_all}
        flat = self.lock_point(top_v)                # the curve is flat from here up
        if cap_mv:
            cap = self.lock_point(cap_mv)
            if cap.voltage_mv < top_v:
                cap_t = eff[cap.index]
                for p in pts_all:
                    if p.voltage_mv >= cap.voltage_mv:
                        eff[p.index] = cap_t
                flat = cap
        # monotonic from the top (only lowering)
        ordered = sorted(pts_all, key=lambda q: (q.voltage_mv, q.index))
        for hi, lo in zip(reversed(ordered), list(reversed(ordered))[1:]):
            if eff[lo.index] > eff[hi.index]:
                eff[lo.index] = eff[hi.index]
        offs = {}
        for p in pts_all:
            off = math.floor(eff[p.index] - p.base_mhz)
            if not p.active:                         # ignored by the GPU — keep it tame
                off = math.floor(low_off)
            offs[p.index] = off
        # Every point above the top of the curve clearly below it (see
        # ABOVE_FLAT_DROP_MHZ) — also covers rounding with fractional bases.
        flat_eff = flat.base_mhz + offs[flat.index]
        for p in pts_all:
            if p.active and p.voltage_mv > flat.voltage_mv:
                offs[p.index] = min(offs[p.index],
                                    math.floor(flat_eff - ABOVE_FLAT_DROP_MHZ - p.base_mhz))
        for p in pts_all:
            off = offs[p.index]
            if abs(off) > MAX_CURVE_SHIFT:
                raise ProfileError(
                    f"Kurven-Offset {off:+d} MHz bei {p.voltage_mv:.0f} mV außerhalb "
                    f"±{MAX_CURVE_SHIFT} MHz")
            c._set_offset(p.index, off)
        return c

    def summary(self) -> str:
        act = self.active_points()
        if not act:
            return f"{self.count} Punkte, keiner aktiv"
        offs = sorted({round(p.offset_mhz) for p in act})
        if len(offs) == 1:
            kind = f"einheitlicher Offset {offs[0]:+d} MHz"
        else:
            top = max(p.effective_mhz for p in act)
            kind = f"eigene Kurve (Offsets {offs[0]:+d}…{offs[-1]:+d} MHz, max {top:.0f} MHz)"
        return (f"{self.count} Punkte ({len(act)} aktiv, "
                f"{act[0].voltage_mv:.0f}–{act[-1].voltage_mv:.0f} mV), {kind}")


# ── INI file (line-preserving) ───────────────────────────────────────────────

def decode_cfg(raw: bytes) -> tuple[str, str]:
    """-> (text, encoding). Afterburner writes plain ANSI; latin-1 round-trips
    every byte. A BOM (never seen, but legal for INI files) is honoured."""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="surrogateescape"), "utf-8-sig"
    return raw.decode("latin-1"), "latin-1"


def encode_cfg(text: str, encoding: str) -> bytes:
    if encoding == "utf-16":
        return text.encode("utf-16")
    if encoding == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8", errors="surrogateescape")
    return text.encode("latin-1", errors="replace")


class ProfileFile:
    """Minimal INI editor that keeps the file as it is — order, comments, unknown
    sections/keys and line endings — and only replaces the values it is told to."""

    def __init__(self, text: str):
        self.eol = "\n" if ("\n" in text and "\r\n" not in text) else "\r\n"
        self.lines = text.splitlines()
        self.final_eol = text == "" or text.endswith(("\n", "\r"))

    @staticmethod
    def _header(line: str) -> Optional[str]:
        s = line.strip()
        if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
            return s[1:-1].strip()
        return None

    @staticmethod
    def _kv(line: str) -> Optional[tuple[str, str]]:
        s = line.strip()
        if not s or s[0] in ";#[" or "=" not in s:
            return None
        k, _, v = s.partition("=")
        return k.strip(), v.strip()

    def sections(self) -> list[str]:
        return [h for h in (self._header(l) for l in self.lines) if h is not None]

    def _bounds(self, section: str) -> Optional[tuple[int, int]]:
        want, start = section.lower(), None
        for i, line in enumerate(self.lines):
            h = self._header(line)
            if h is None:
                continue
            if start is not None:
                return start, i
            if h.lower() == want:
                start = i
        return (start, len(self.lines)) if start is not None else None

    def has_section(self, section: str) -> bool:
        return self._bounds(section) is not None

    def items(self, section: str) -> dict[str, str]:
        """Key (lower case) -> value; the FIRST occurrence wins, like the Win32
        profile API."""
        b = self._bounds(section)
        out: dict[str, str] = {}
        if b:
            for i in range(b[0] + 1, b[1]):
                kv = self._kv(self.lines[i])
                if kv and kv[0].lower() not in out:
                    out[kv[0].lower()] = kv[1]
        return out

    def get(self, section: str, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.items(section).get(key.lower(), default)

    def _append_section(self, section: str, body: list[str]):
        while self.lines and not self.lines[-1].strip():
            self.lines.pop()
        if self.lines:
            self.lines.append("")
        self.lines.append(f"[{section}]")
        self.lines.extend(body)
        self.final_eol = True

    def set_values(self, section: str, updates: dict[str, str],
                   template_body: Optional[list[str]] = None):
        """Replace the given keys in `section` (every occurrence), append missing
        keys at the end of the section, create the section (from template_body)
        if it doesn't exist."""
        if not self.has_section(section):
            self._append_section(section, list(template_body or []))
        start, end = self._bounds(section)
        pending = {k.lower(): (k, str(v)) for k, v in updates.items()}
        seen: set[str] = set()
        for i in range(start + 1, end):
            kv = self._kv(self.lines[i])
            if kv and kv[0].lower() in pending:
                self.lines[i] = f"{kv[0]}={pending[kv[0].lower()][1]}"
                seen.add(kv[0].lower())
        missing = [pending[k] for k in pending if k not in seen]
        if missing:
            ins = end
            while ins > start + 1 and not self.lines[ins - 1].strip():
                ins -= 1
            for j, (k, v) in enumerate(missing):
                self.lines.insert(ins + j, f"{k}={v}")

    def section_body(self, section: str) -> list[str]:
        b = self._bounds(section)
        if not b:
            return []
        return [self.lines[i].strip() for i in range(b[0] + 1, b[1]) if self._kv(self.lines[i])]

    def text(self) -> str:
        out = self.eol.join(self.lines)
        if self.final_eol and self.lines:
            out += self.eol
        return out


# ── GPU profile file name ────────────────────────────────────────────────────

_GPU_FILE_RE = re.compile(
    r"^VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})&SUBSYS_([0-9A-F]{8})&REV_([0-9A-F]{2})"
    r"&BUS_(\d+)&DEV_(\d+)&FN_(\d+)\.cfg$", re.IGNORECASE)


@dataclass
class GpuFileId:
    vendor: int
    device: int
    subsys: int
    rev:    int
    bus:    int
    name:   str


def parse_gpu_filename(name: str) -> Optional[GpuFileId]:
    m = _GPU_FILE_RE.match(name)
    if not m:
        return None
    return GpuFileId(int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16),
                     int(m.group(4), 16), int(m.group(5)), name)


def pick_gpu_file(names: list[str], device: Optional[int] = None,
                  subsys: Optional[int] = None, bus: Optional[int] = None
                  ) -> tuple[Optional[str], str]:
    """Choose the profile file of the NVIDIA card we tune. With the card's PCI
    identity (from NVML) the match is exact; a leftover file of an OLD card is
    never picked. -> (file name or None, explanation)."""
    ids = [g for g in (parse_gpu_filename(n) for n in names) if g and g.vendor == 0x10DE]
    if not ids:
        return None, ("Afterburner hat noch kein Profil für die NVIDIA-Karte angelegt — "
                      "Afterburner einmal starten und unten 'Speichern' → Slot 1 klicken.")
    if device is not None and subsys is not None:
        same = [g for g in ids if g.device == device and g.subsys == subsys]
        if len(same) > 1 and bus is not None:
            same = [g for g in same if g.bus == bus] or same
        if len(same) == 1:
            return same[0].name, "per PCI-ID zugeordnet"
        if not same:
            return None, (f"Kein Afterburner-Profil passt zur Karte (DEV_{device:04X} "
                          f"SUBSYS_{subsys:08X}) — gefunden: " + ", ".join(g.name for g in ids))
        return None, "Mehrere gleiche Karten gefunden — Zuordnung nicht eindeutig."
    if len(ids) == 1:
        return ids[0].name, "einzige NVIDIA-Profildatei"
    return None, ("Mehrere NVIDIA-Profildateien und keine PCI-ID (NVML) zum Zuordnen: "
                  + ", ".join(g.name for g in ids))


# ── Writing a slot ────────────────────────────────────────────────────────────

@dataclass
class SlotSettings:
    core_mhz:  int = 0
    mem_mhz:   int = 0
    power_pct: int = 100
    lock_mv:   int = 0       # > 0 together with lock_mhz -> flat V/F curve
    lock_mhz:  int = 0
    curve:     tuple = ()    # own curve: ((voltage_mv, mhz), ...) measured points
    cap_mv:    int = 0       # own curve: flat from this voltage up (0 = top point)

    @property
    def uses_curve(self) -> bool:
        return bool(self.curve) or (self.lock_mv > 0 and self.lock_mhz > 0)


# Where a usable V/F curve (the card's base frequencies) is taken from. [Defaults]
# first: it is the untouched stock state, so no lock parameters of a user curve
# are carried over into our slot.
def _curve_sources(section: str) -> list[str]:
    order = ["Defaults", section, "Profile1", "Profile2", "Profile3",
             "Profile4", "Profile5", "Startup"]
    seen, out = set(), []
    for s in order:
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def pick_curve(pf: ProfileFile, section: str) -> tuple[Optional[VFCurve], str]:
    for src in _curve_sources(section):
        raw = pf.get(src, "VFCurve")
        if not raw:
            continue
        try:
            c = VFCurve.from_hex(raw)
        except ProfileError:
            continue
        if c.active_points():
            return c, src
    return None, ""


def _template_body(pf: ProfileFile) -> list[str]:
    """Body for a slot that doesn't exist yet — every key Afterburner itself
    writes, so nothing we don't set (fan mode, thermal limit, voltage boost) is
    left to how it treats a MISSING key: [Defaults] if present, else [Startup]
    (Afterburner 4.6.6 writes no [Defaults]; [Startup] holds what it applies at
    boot — on a fresh install the stock values, fan on auto). Never another
    slot: that could be a user's own fan/thermal tuning."""
    for src in ("Defaults", "Startup"):
        body = pf.section_body(src)
        if body:
            return body
    return ["Format=2"]


def apply_slot(text: str, slot: int, s: SlotSettings) -> tuple[str, list[str]]:
    """Write `s` into [Profile<slot>] of a GPU profile file.
    -> (new file text, human-readable notes). Raises ProfileError."""
    if not 1 <= int(slot) <= 5:
        raise ProfileError(f"Profil-Slot {slot} ungültig (1–5)")
    if not -1000 < int(s.core_mhz) < 1000:      # 1000000 kHz = custom-curve marker
        raise ProfileError(f"Core-Offset {s.core_mhz:+d} MHz außerhalb ±999 MHz")
    pf      = ProfileFile(text)
    section = f"Profile{int(slot)}"
    notes: list[str] = []

    updates: dict[str, str] = {
        "PowerLimit":  str(int(s.power_pct)),
        "MemClkBoost": str(int(s.mem_mhz) * 1000),
    }
    curve, src = pick_curve(pf, section)
    if s.uses_curve:
        if curve is None:
            raise ProfileError(
                "Das Afterburner-Profil enthält noch keine V/F-Kurve — in Afterburner "
                "einmal unten auf 'Speichern' und dann auf einen Slot klicken.")
        if s.curve:
            own = curve.with_anchor_curve(s.curve, s.cap_mv)
            updates["CoreClkBoost"] = str(CORE_CURVE_MARKER)
            updates["VFCurve"]      = own.to_hex()
            act = own.active_points()
            top = max(act, key=lambda q: (q.effective_mhz, -q.voltage_mv))
            vs = sorted(int(mv) for mv, _f in s.curve)
            notes.append(f"Eigene V/F-Kurve aus {len(vs)} Messpunkten ({vs[0]}–{vs[-1]} mV), "
                         f"max {top.effective_mhz:.0f} MHz ab {top.voltage_mv:.0f} mV"
                         + (f", flach ab {s.cap_mv} mV" if s.cap_mv else "")
                         + f" (Basis-Kurve aus [{src}])")
        else:
            flat = curve.with_flatline(s.lock_mv, s.lock_mhz)
            lock = curve.lock_point(s.lock_mv)
            updates["CoreClkBoost"] = str(CORE_CURVE_MARKER)
            updates["VFCurve"]      = flat.to_hex()
            notes.append(f"V/F-Kurve flach ab {lock.voltage_mv:.0f} mV auf {s.lock_mhz} MHz "
                         f"(Basis-Kurve aus [{src}])")
    else:
        updates["CoreClkBoost"] = str(int(s.core_mhz) * 1000)
        if curve is not None:
            updates["VFCurve"] = curve.with_uniform_offset(int(s.core_mhz)).to_hex()
            notes.append(f"Core {s.core_mhz:+d} MHz auf allen Kurvenpunkten "
                         f"(Basis-Kurve aus [{src}])")
        else:
            notes.append(f"Core {s.core_mhz:+d} MHz (Profil ohne V/F-Kurve)")

    created = not pf.has_section(section)
    pf.set_values(section, updates, _template_body(pf) if created else None)
    if not pf.get(section, "Format"):
        pf.set_values(section, {"Format": "2"})
    notes.append(f"Mem {s.mem_mhz:+d} MHz, Power-Limit {s.power_pct} %")
    if created:
        notes.append(f"[{section}] neu angelegt")
    return pf.text(), notes


def slot_equivalent(old_text: str, new_text: str, slot: int) -> bool:
    """True if [Profile<slot>] holds the same settings in both texts. The V/F
    curve is compared by its per-point offsets, not by the base frequencies
    stored next to them (they differ between saves, e.g. with temperature) —
    so re-applying identical values never restarts Afterburner needlessly."""
    sec = f"Profile{int(slot)}"
    a, b = ProfileFile(old_text), ProfileFile(new_text)
    if not a.has_section(sec) or not b.has_section(sec):
        return False
    ia, ib = a.items(sec), b.items(sec)
    ca, cb = ia.pop("vfcurve", ""), ib.pop("vfcurve", "")
    if ia != ib:
        return False
    if not ca or not cb:
        return ca == cb
    try:
        pa, pb = VFCurve.from_hex(ca).points(), VFCurve.from_hex(cb).points()
    except ProfileError:
        return False
    return len(pa) == len(pb) and all(
        abs(x.voltage_mv - y.voltage_mv) < 0.01 and abs(x.offset_mhz - y.offset_mhz) < 0.5
        for x, y in zip(pa, pb))


def slot_summary(pf: ProfileFile, slot: int, de: bool = True) -> str:
    """What slot `slot` holds, short — for the "save to slot" menu:
    "leer", "Kurve · Speicher +1000 · Power 100 %", "Core +135 · Speicher +0 · Power 96 %"."""
    it = pf.items(f"Profile{int(slot)}")
    if not it:
        return "leer" if de else "empty"

    def num(key):                       # None = not in the slot (nothing to show)
        try:
            return int(it[key]) if it.get(key, "").strip() else None
        except ValueError:
            return None
    core = num("coreclkboost")
    parts = []
    if core == CORE_CURVE_MARKER:
        parts.append("Kurve" if de else "curve")
    elif core is not None:
        parts.append(f"Core {round(core / 1000):+d}")
    mem = num("memclkboost")
    if mem is not None:
        parts.append(f"{'Speicher' if de else 'memory'} {round(mem / 1000):+d}")
    if it.get("powerlimit"):
        parts.append(f"Power {it['powerlimit']} %")
    return " · ".join(parts) or ("belegt" if de else "used")


def describe_slot(pf: ProfileFile, section: str) -> str:
    """One line per slot for diagnostics."""
    it = pf.items(section)
    if not it:
        return "leer"

    def khz(key):
        v = it.get(key, "")
        try:
            n = int(v)
        except ValueError:
            return v or "—"
        if key == "coreclkboost" and n == CORE_CURVE_MARKER:
            return "Kurve"
        return f"{n // 1000:+d} MHz"

    parts = [f"Power {it.get('powerlimit') or '—'} %",
             f"Core {khz('coreclkboost')}",
             f"Mem {khz('memclkboost')}"]
    if it.get("thermallimit"):
        parts.append(f"Temp-Limit {it['thermallimit']} °C")
    if it.get("fanmode") or it.get("fanspeed"):
        parts.append(f"FanMode={it.get('fanmode', '')} FanSpeed={it.get('fanspeed', '')}")
    raw = it.get("vfcurve", "")
    if raw:
        try:
            parts.append("Kurve: " + VFCurve.from_hex(raw).summary())
        except ProfileError as e:
            parts.append(f"Kurve unlesbar ({e})")
    return ", ".join(parts)
