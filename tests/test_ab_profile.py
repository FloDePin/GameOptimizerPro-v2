"""Offline tests for core/ab_profile.py + AfterburnerController (no Afterburner needed)."""
import os, sys, struct, tempfile, shutil, time, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core import ab_profile as P
from core.ab_profile import (VFCurve, ProfileFile, ProfileError, SlotSettings, apply_slot,
                             slot_equivalent, pick_gpu_file, pick_curve, describe_slot,
                             decode_cfg, encode_cfg, CORE_CURVE_MARKER)

FAILS = []
def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        FAILS.append(label)

# ── fixtures in the verified format ──────────────────────────────────────────
def make_curve(n_active=121, slots=256, start_mv=450.0, step=6.25, inactive_first=6,
               base_shift=0.0, offset=0.0, trailing=True, quantize=True):
    """Ada-like curve: first points inactive (base 225), base rising to ~2900 MHz."""
    raw = bytearray(struct.pack("<IIf", 0x00020000, n_active, 0.0))
    for i in range(slots):
        if i < n_active:
            v = start_mv + i * step
            if i < inactive_first:
                f = 225.0
            else:
                f = min(2925.0, 210.0 + (v - 450.0) * 4.2)
                if quantize:          # real GPUs: base clocks in 15 MHz bins
                    f = round(f / 15.0) * 15.0
                f += base_shift
            raw += struct.pack("<fff", v, f, offset)
        else:
            raw += b"\x00" * 12
    if trailing:   # "lock parameters" as seen after the points in a real profile
        raw += struct.pack("<I", 3) + struct.pack("<6f", 1800.0, 83.0, 1800.0, 86.0, 1395.0, 90.0)
    return bytes(raw)

REAL_PREFIX = ("0000020080000000000000000000E14300005243000000000020E44300005243"
               "000000000040E7430000524300000000")   # from the real RTX 3090 profile

def make_profile(defaults_curve=True, eol="\r\n", with_p2=False):
    c = make_curve().hex().upper()
    lines = ["[Startup]", "Format=2", "PowerLimit=", "ThermalLimit=", "CoreClkBoost=",
             "VFCurve=", "MemClkBoost=", "FanMode=", "FanSpeed=", "FanMode2=", "FanSpeed2=", "",
             "[Profile1]", "Format=2", "PowerLimit=100", "ThermalLimit=83", "CoreClkBoost=0",
             f"VFCurve={c}", "MemClkBoost=0", "FanMode=1", "FanSpeed=30", "FanMode2=", "FanSpeed2=", ""]
    if with_p2:
        lines += ["[Profile2]", "Format=2", "PowerLimit=80", "ThermalLimit=75",
                  "CoreClkBoost=-350000", f"VFCurve={make_curve(offset=-350).hex().upper()}",
                  "MemClkBoost=600000", "FanMode=0", "FanSpeed=80", "UnknownKey=keepme", ""]
    lines += ["[Defaults]", "Format=2", "PowerLimit=100", "ThermalLimit=83", "CoreClkBoost=0",
              ("VFCurve=" + c) if defaults_curve else "VFCurve=", "MemClkBoost=0",
              "FanMode=1", "FanSpeed=30", "", "[Settings]", "VDDC_Generic_Detection=0",
              "; a comment", "CaptureDefaults=1"]
    return eol.join(lines) + eol

print("VFCurve")
raw = make_curve()
c = VFCurve(raw)
check(c.count == 121 and c.to_hex() == raw.hex().upper(), "parse + round-trip")
real = VFCurve.from_hex(REAL_PREFIX)
p0 = real.points()[0]
check(abs(p0.voltage_mv - 450) < 1e-6 and abs(p0.base_mhz - 210) < 1e-6 and p0.offset_mhz == 0,
      "real RTX 3090 bytes decode to 450 mV / 210 MHz / +0")
check(len(real.points()) == (len(bytes.fromhex(REAL_PREFIX)) - 12) // 12, "short real blob: count capped by length")
u = c.with_uniform_offset(15)
ub = bytes.fromhex(u.to_hex())
diff = [i for i in range(len(raw)) if raw[i] != ub[i]]
off_bytes = set()
for i in range(c.count):
    off_bytes.update(range(12 + 12 * i + 8, 12 + 12 * i + 12))
check(len(ub) == len(raw) and set(diff) <= off_bytes, "uniform offset changes ONLY offset floats")
check(all(p.offset_mhz == 15 for p in u.points() if p.voltage_mv > 0), "uniform +15 on every point")
check(u.to_hex()[-120:] == raw.hex().upper()[-120:], "trailing lock data kept verbatim")
try:
    c.with_uniform_offset(1500); check(False, "uniform > 1000 MHz rejected")
except ProfileError:
    check(True, "uniform > 1000 MHz rejected")

f = c.with_flatline(950, 2400)
lock = c.lock_point(950)
act = [p for p in f.points() if p.active]
check(abs(lock.voltage_mv - 950) < 3.2, f"lock point nearest to 950 mV ({lock.voltage_mv})")
check(all(abs(p.effective_mhz - 2400) < 0.51 for p in act if p.voltage_mv >= lock.voltage_mv),
      "flat at target from lock voltage up")
check(all(p.effective_mhz <= 2400.0 for p in act), "never above target")
eff = [p.effective_mhz for p in act]
check(all(b >= a - 0.51 for a, b in zip(eff, eff[1:])), "effective curve monotonic")
delta = round(2400 - lock.base_mhz)
check(all(p.offset_mhz == delta for p in act if p.voltage_mv < lock.voltage_mv
          and p.base_mhz + delta <= 2400), "points below lock shifted by the same delta")
check(all(p.offset_mhz == delta for p in f.points() if p.voltage_mv > 0 and not p.active),
      "inactive (225 MHz) points get the tame delta, not target-225")
fr = VFCurve(make_curve(quantize=False)).with_flatline(950, 2400)
fa = [p for p in fr.active_points()]
check(all(p.effective_mhz <= 2400.0 for p in fa), "fractional bases: never above target (floor)")
check(all(p.effective_mhz > 2399.0 for p in fa if p.voltage_mv >= 950), "fractional bases: within 1 MHz of target")
for bad in ((300, 2400), (950, 5000)):
    try:
        c.with_flatline(*bad); check(False, f"flatline {bad} rejected")
    except ProfileError:
        check(True, f"flatline {bad} rejected")
for badhex in ("", "zz", "01000000" * 8):
    try:
        VFCurve.from_hex(badhex); check(False, f"bad blob {badhex[:10]!r} rejected")
    except ProfileError:
        check(True, f"bad blob {badhex[:10]!r} rejected")

print("ProfileFile")
for eol in ("\r\n", "\n"):
    t = make_profile(eol=eol, with_p2=True)
    check(ProfileFile(t).text() == t, f"round-trip identical ({'CRLF' if eol == chr(13)+chr(10) else 'LF'})")
t = make_profile()
check(ProfileFile(t.rstrip("\r\n")).text() == t.rstrip("\r\n"), "no final newline preserved")
for tag, rawb in (("ansi", t.encode("latin-1")), ("utf8bom", b"\xef\xbb\xbf" + t.encode()),
                  ("utf16", t.encode("utf-16"))):
    txt, enc = decode_cfg(rawb)
    check(encode_cfg(txt, enc) == rawb and "[Profile1]" in txt, f"encoding round-trip {tag}")
pf = ProfileFile(make_profile(with_p2=True))
check(pf.sections() == ["Startup", "Profile1", "Profile2", "Defaults", "Settings"], "sections")
check(pf.get("profile2", "unknownkey") == "keepme" and pf.get("PROFILE1", "fanmode") == "1",
      "case-insensitive get")

print("apply_slot")
old = make_profile(with_p2=True)
new, notes = apply_slot(old, 2, SlotSettings(core_mhz=15, mem_mhz=500, power_pct=90))
a, b = ProfileFile(old), ProfileFile(new)
it = b.items("Profile2")
check(it["coreclkboost"] == "15000" and it["memclkboost"] == "500000" and it["powerlimit"] == "90",
      "kHz / % values written")
check(it["thermallimit"] == "75" and it["fanmode"] == "0" and it["unknownkey"] == "keepme",
      "untouched keys (thermal, fan, unknown) kept")
nc = VFCurve.from_hex(it["vfcurve"])
check(all(p.offset_mhz == 15 for p in nc.points() if p.voltage_mv > 0), "slot curve: +15 everywhere")
check(pick_curve(a, "Profile2")[1] == "Defaults", "base curve taken from [Defaults]")
others_same = all(a.items(s) == b.items(s) for s in ("Startup", "Profile1", "Defaults", "Settings"))
check(others_same, "all other sections byte-identical in content")
check([l for l in old.splitlines() if not l.startswith(("CoreClkBoost=-350000", "PowerLimit=80",
       "MemClkBoost=600000", "VFCurve="))] ==
      [l for l in new.splitlines() if not l.startswith(("CoreClkBoost=15000", "PowerLimit=90",
       "MemClkBoost=500000", "VFCurve="))], "line order/comments unchanged")
check(new.count("\r\n") == old.count("\r\n"), "CRLF kept, no lines added")

new3, notes3 = apply_slot(old, 3, SlotSettings(core_mhz=-30, power_pct=100))
b3 = ProfileFile(new3)
check(b3.has_section("Profile3") and b3.get("Profile3", "Format") == "2", "missing slot created")
check(b3.get("Profile3", "FanMode") == "1" and b3.get("Profile3", "ThermalLimit") == "83",
      "new slot body = [Defaults] stock values")
check(b3.get("Profile3", "CoreClkBoost") == "-30000", "negative offset in kHz")
check(any("neu angelegt" in n for n in notes3), "note: slot created")

newc, notesc = apply_slot(old, 2, SlotSettings(lock_mv=950, lock_mhz=2400))
ic = ProfileFile(newc).items("Profile2")
check(ic["coreclkboost"] == str(CORE_CURVE_MARKER) and ic["powerlimit"] == "100",
      "curve mode: CoreClkBoost=1000000 marker, power 100")
fc = VFCurve.from_hex(ic["vfcurve"])
check(all(abs(p.effective_mhz - 2400) < 0.51 for p in fc.active_points() if p.voltage_mv >= 949),
      "curve mode: flat line written")
try:
    apply_slot(make_profile(defaults_curve=False).replace(
        "VFCurve=" + make_curve().hex().upper(), "VFCurve="), 2, SlotSettings(lock_mv=950, lock_mhz=2400))
    check(False, "curve mode without any curve -> error")
except ProfileError:
    check(True, "curve mode without any curve -> error")
nd, _ = apply_slot(make_profile(defaults_curve=False), 2, SlotSettings(core_mhz=10))
check(pick_curve(ProfileFile(make_profile(defaults_curve=False)), "Profile2")[1] == "Profile1",
      "fallback curve source: Profile1 (the user's stock save)")
emp = "[Settings]\r\nX=1\r\n"
ne, _ = apply_slot(emp, 2, SlotSettings(core_mhz=10))
check(ProfileFile(ne).get("Profile2", "CoreClkBoost") == "10000" and
      ProfileFile(ne).get("Profile2", "Format") == "2" and "VFCurve" not in ne,
      "file without curves: offset only, Format=2")
try:
    apply_slot(old, 2, SlotSettings(core_mhz=1000)); check(False, "core +1000 (marker collision) rejected")
except ProfileError:
    check(True, "core +1000 (marker collision) rejected")
try:
    apply_slot(old, 6, SlotSettings()); check(False, "slot 6 rejected")
except ProfileError:
    check(True, "slot 6 rejected")

print("slot_equivalent")
check(slot_equivalent(new, apply_slot(new, 2, SlotSettings(15, 500, 90))[0], 2), "same values -> equivalent")
check(apply_slot(new, 2, SlotSettings(15, 500, 90))[0] == new, "same values -> byte-identical")
shifted = new.replace(make_curve().hex().upper(), make_curve(base_shift=-15).hex().upper())
re_new, _ = apply_slot(shifted, 2, SlotSettings(15, 500, 90))
check(re_new != shifted and slot_equivalent(shifted, re_new, 2),
      "Defaults base freqs refreshed -> not identical but equivalent (no restart)")
check(not slot_equivalent(new, apply_slot(new, 2, SlotSettings(30, 500, 90))[0], 2), "changed offset -> not equivalent")
check(not slot_equivalent(old, apply_slot(old, 3, SlotSettings())[0], 3), "missing slot -> not equivalent")

print("pick_gpu_file")
mine = "VEN_10DE&DEV_2704&SUBSYS_F2981569&REV_A1&BUS_1&DEV_0&FN_0.cfg"
oldcard = "VEN_10DE&DEV_2204&SUBSYS_39873842&REV_A1&BUS_10&DEV_0&FN_0.cfg"
amd = "VEN_1002&DEV_73BF&SUBSYS_0E3A1002&REV_C1&BUS_3&DEV_0&FN_0.cfg"
names = ["MSIAfterburner.cfg", oldcard, mine, amd]
check(pick_gpu_file(names, 0x2704, 0xF2981569, 1)[0] == mine, "exact PCI match, old card ignored")
check(pick_gpu_file([oldcard, "MSIAfterburner.cfg"], 0x2704, 0xF2981569, 1)[0] is None,
      "only an OLD card's file -> refused")
check(pick_gpu_file([mine.lower()], 0x2704, 0xF2981569, 1)[0] == mine.lower(), "case-insensitive")
twin = mine.replace("BUS_1&", "BUS_2&")
check(pick_gpu_file([mine, twin], 0x2704, 0xF2981569, 2)[0] == twin, "two identical cards -> bus decides")
check(pick_gpu_file([mine, amd], None, None, None)[0] == mine, "no PCI info + single NVIDIA file")
check(pick_gpu_file([mine, oldcard], None, None, None)[0] is None, "no PCI info + two NVIDIA files -> refused")
check(pick_gpu_file(["MSIAfterburner.cfg", amd])[0] is None, "no NVIDIA profile -> explanation")
check(P.parse_gpu_filename(mine).bus == 1 and P.parse_gpu_filename(mine).device == 0x2704, "filename parse")

print("describe_slot")
d = describe_slot(ProfileFile(newc), "Profile2")
check("Core Kurve" in d and "Power 100 %" in d, f"describe: {d[:80]}…")

print("\n%d failure(s)" % len(FAILS))
for f_ in FAILS:
    print("  -", f_)
sys.exit(1 if FAILS else 0)
