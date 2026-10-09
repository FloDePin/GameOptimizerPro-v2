"""The writer against a COPY of this PC's real Afterburner 4.6.6 profile."""
import os, sys, struct
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.ab_profile import (ProfileFile, VFCurve, SlotSettings, apply_slot, slot_equivalent,
                             pick_curve, decode_cfg, encode_cfg, CORE_CURVE_MARKER)

FAILS = []
def check(c, label):
    print(("  ok   " if c else "  FAIL ") + label, flush=True)
    if not c:
        FAILS.append(label)

# This PC's REAL Afterburner profile of this card — only READ; every write
# below goes into strings. Skipped (exit 2) without Afterburner / NVIDIA card.
from core.nvtune_core import AfterburnerController, GpuMonitor
_mon = GpuMonitor()
_path, _why = AfterburnerController(_mon.nvml.get_pci_identity()).find_gpu_profile()
if not _path:
    print(f"no Afterburner profile for this card ({_why}) — skipped")
    sys.exit(2)
print("   reading", os.path.basename(_path))
raw = open(_path, "rb").read()
text, enc = decode_cfg(raw)
check(encode_cfg(ProfileFile(text).text(), enc) == raw, "real file: parse -> write is byte-identical")
pf = ProfileFile(text)
# The curve the writer would start from — [Startup] is EMPTY when Afterburner's
# "apply overclocking at system startup" is off (seen on the test PC), so the
# app takes it from a profile slot (pick_curve); the test used to read [Startup].
_c0, src_sec = pick_curve(pf, "Profile2")
check(_c0 is not None, f"a real V/F curve is found (from [{src_sec}])")
blob = bytes.fromhex(pf.get(src_sec, "VFCurve")) if _c0 is not None else b""
check(len(blob) == 3224 and struct.unpack_from("<II", blob, 0) == (0x20000, 127),
      f"real VFCurve: {len(blob)} bytes, version 0x20000, 127 points")
c = VFCurve(blob)
pts = c.points()
check(abs(pts[0].voltage_mv - 450) < 0.01 and abs(pts[-1].voltage_mv - 1240) < 0.01 and
      all(b.voltage_mv > a.voltage_mv for a, b in zip(pts, pts[1:])), "450 -> 1240 mV, strictly rising")
check(all(b.base_mhz >= a.base_mhz for a, b in zip(pts, pts[1:])), "base clocks never fall (monotonic real curve)")
check(blob[12 + 256 * 12:] == bytes.fromhex(c.with_uniform_offset(15).to_hex())[12 + 256 * 12:],
      "140 trailing bytes kept verbatim")

new, notes = apply_slot(text, 2, SlotSettings(core_mhz=15, power_pct=90))
b = ProfileFile(new)
it = b.items("Profile2")
print("   new [Profile2]:", {k: (v if len(v) < 20 else v[:16] + "…") for k, v in it.items()})
src = pf.items("Profile2") if pf.has_section("Profile2") else pf.items("Startup")
keep = ("fanmode", "fanspeed", "corevoltageboost", "thermalprioritize", "thermallimit")
check(all(it.get(k) == src.get(k) for k in keep if k in src) and "thermallimit" in it,
      "fan / voltage-boost / thermal keys taken over unchanged (the writer never touches them)")
check(it["powerlimit"] == "90" and it["coreclkboost"] == "15000" and it["memclkboost"] == "0", "our values")
check(b.items("Startup") == pf.items("Startup"), "[Startup] untouched")
nc = VFCurve.from_hex(it["vfcurve"])
check(all(p.offset_mhz == 15 for p in nc.points()), "curve +15 on all 127 points")
check(slot_equivalent(new, apply_slot(new, 2, SlotSettings(core_mhz=15, power_pct=90))[0], 2),
      "re-applying the same values -> no restart")

flat, notes = apply_slot(text, 2, SlotSettings(lock_mv=950, lock_mhz=2535))
fc = VFCurve.from_hex(ProfileFile(flat).get("Profile2", "VFCurve"))
eff = [(p.voltage_mv, p.effective_mhz) for p in fc.points()]
at = [f for v, f in eff if abs(v - 950) < 0.01]
check(all(f <= 2535 for v, f in eff) and at and abs(at[0] - 2535) < 1
      and all(f <= 2535 - 99 for v, f in eff if v > 950),
      "real points: 950 mV runs 2535 MHz, every point above it 100 MHz lower, never above")
low = [(v, f) for v, f in eff if v <= 950]
check(all(b2 >= a2 - 0.01 for (_, a2), (_, b2) in zip(low, low[1:])), "effective curve monotonic up to 950 mV")
check(ProfileFile(flat).get("Profile2", "CoreClkBoost") == str(CORE_CURVE_MARKER), "curve marker")
print("   notes:", notes)
print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
