"""
GameOptimizerPro — Afterburner integration self-test.

  python tools\\ab_selftest.py info
      Read-only: what the app sees (Afterburner, settings, the card's profile
      file, V/F curve, monitoring sources, NVML power limit/offsets).
  python tools\\ab_selftest.py dryrun [--slot 2] [--core 15] [--mem 0] [--power 90]
                                     [--lock-mv 950 --lock-mhz 2600]
      Shows exactly what WOULD be written into the slot. Writes nothing.
  python tools\\ab_selftest.py live [--slot 2] [--hold 20] [--curve] [--pause]
      The live test (admin terminal, GPU idle): +15 MHz core / 90 % power limit
      via Afterburner, measured with NVML; optionally a flat V/F curve; then
      stock values, then the ORIGINAL profile file is put back.
  python tools\\ab_selftest.py restore [BACKUP.cfg]
      Puts a backup back (default: the newest one of this card).

Everything is also written to logs\\ab_selftest_<time>.txt.
"""

import argparse
import ctypes
import difflib
import glob
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.ab_profile import (ProfileFile, VFCurve, ProfileError, apply_slot,  # noqa: E402
                             describe_slot, pick_curve, decode_cfg)
from core.nvtune_core import AfterburnerController, GpuMonitor, TuneProfile  # noqa: E402


# ── output: console + log file ───────────────────────────────────────────────

class Out:
    def __init__(self, mode: str):
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        self.path = os.path.join(ROOT, "logs",
                                 f"ab_selftest_{mode}_{datetime.now():%Y%m%d_%H%M%S}.txt")
        self._f = open(self.path, "w", encoding="utf-8")
        self.fails = 0

    def __call__(self, msg: str = ""):
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode(), flush=True)
        self._f.write(msg + "\n")
        self._f.flush()

    def head(self, title: str):
        self("")
        self(f"== {title} " + "=" * max(3, 66 - len(title)))

    def check(self, ok: bool, label: str, detail: str = ""):
        if not ok:
            self.fails += 1
        self(f"  [{'OK ' if ok else 'FEHLER'}] {label}" + (f" — {detail}" if detail else ""))

    def close(self):
        self._f.close()


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def file_version(exe: str) -> str:
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"(Get-Item -LiteralPath '{exe}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout or "").strip() or "?"
    except Exception:
        return "?"


# ── NVML helpers ──────────────────────────────────────────────────────────────

def nvml_power(mon: GpuMonitor):
    cur, mn, mx = mon.get_power_constraints()
    return cur, mn, mx, mon.get_default_power_limit()


def nvml_offsets(mon: GpuMonitor):
    """(core, mem) offset in MHz as the driver reports it, or None."""
    nv = getattr(mon.nvml, "_nv", None)
    h = getattr(mon.nvml, "_handle", None)
    if nv is None or h is None or not hasattr(nv, "c_nvmlClockOffset_t"):
        return None
    out = []
    try:
        for clk in (nv.NVML_CLOCK_GRAPHICS, nv.NVML_CLOCK_MEM):
            o = nv.c_nvmlClockOffset_t()
            o.version = nv.nvmlClockOffset_v1
            o.type = clk
            o.pstate = nv.NVML_PSTATE_0
            nv.nvmlDeviceGetClockOffsets(h, o)
            out.append(int(o.clockOffsetMHz))
        return tuple(out)
    except Exception:
        return None


def gpu_busy(mon: GpuMonitor, seconds: float = 3.0) -> float:
    peak, end = 0.0, time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            peak = max(peak, float(mon.read().gpu_usage))
        except Exception:
            pass
        time.sleep(0.5)
    return peak


# ── info ──────────────────────────────────────────────────────────────────────

def cmd_info(out: Out, ab: AfterburnerController, mon: GpuMonitor):
    out.head("System")
    out(f"  Python {sys.version.split()[0]}   Admin: {'ja' if is_admin() else 'nein'}")

    out.head("NVIDIA (NVML)")
    s = mon.read()
    out.check(mon.nvml.available, "NVML verfügbar", s.name if mon.nvml.available else "")
    if mon.nvml.available:
        pci = mon.nvml.get_pci_identity()
        out(f"  Treiber {s.driver_version}   PCI: "
            + (f"DEV_{pci[0]:04X} SUBSYS_{pci[1]:08X} BUS_{pci[2]}" if pci else "?"))
        cur, mn, mx, dflt = nvml_power(mon)
        out(f"  Power-Limit: aktuell {cur} W, Standard {dflt} W, erlaubt {mn}–{mx} W")
        offs = nvml_offsets(mon)
        out(f"  Takt-Offsets laut Treiber: "
            + (f"Core {offs[0]:+d} MHz, Mem {offs[1]:+d} MHz" if offs else "nicht auslesbar"))
        out(f"  Jetzt: {s.core_mhz:.0f} MHz, {s.temp} °C, GPU-Last {s.gpu_usage:.0f} %, "
            f"{s.power_w:.0f} W")

    out.head("MSI Afterburner")
    out.check(ab.available, "installiert", ab.exe or "nicht gefunden")
    if not ab.available:
        return
    out(f"  Version {file_version(ab.exe)}   läuft: {'ja' if ab.is_running() else 'nein'}")
    out(f"  Profilordner: {ab.profile_dir or '— fehlt (Afterburner einmal starten)'}")
    if ab.profile_dir:
        for f in sorted(os.listdir(ab.profile_dir)):
            fp = os.path.join(ab.profile_dir, f)
            note = ""
            if f.lower().startswith("msiafterburner") and f.lower() != "msiafterburner.cfg":
                note = "   <- Datei einer alten GameOptimizerPro-Version, kann gelöscht werden"
            out(f"    {f}  ({os.path.getsize(fp)} Bytes){note}")

    out.head("Afterburner-Einstellungen (Profiles\\MSIAfterburner.cfg)")
    st = ab.check_ab_setup()
    out.check(st["cfg_found"], "Einstellungsdatei gefunden")
    out.check(st["voltage_control"], "Spannungssteuerung freigeschaltet")
    out.check(st["voltage_monitoring"], "Spannungsüberwachung freigeschaltet")
    if st["voltage_graph"] is not None:
        out(f"  Graph 'GPU-Spannung' laut Einstellungsdatei: {'an' if st['voltage_graph'] else 'aus'}")
    out(f"  Profile gesperrt (Schloss): {'ja' if st['profiles_locked'] else 'nein'}   "
        f"Minimiert starten: {'ja' if st['start_minimized'] else 'nein (empfohlen: ja)'}")
    sp = ab.settings_path()
    if sp:
        with open(sp, "rb") as fh:
            items = ProfileFile(decode_cfg(fh.read())[0]).items("Settings")
        for k in ("UnlockVoltageControl", "UnlockVoltageMonitoring", "LockProfiles",
                  "StartWithWindows", "StartMinimized", "SwAutoFanControl",
                  "ProfileContents", "RestoreAfterSuspendedMode"):
            out(f"    {k}={items.get(k.lower(), '(fehlt)')}")
        if "sources" in items:
            srcs = [x.strip() for x in items.get("sources", "").split(",") if x.strip()]
            on = [x[1:] for x in srcs if x.startswith("+")]
            out(f"    Aktive Graphen ({len(on)}): {', '.join(on[:14])}{' …' if len(on) > 14 else ''}")
        else:
            out("    (keine Graphen-Liste in der Datei — maßgeblich ist das Monitoring unten)")

    out.head("Profildatei der Grafikkarte")
    path, why = ab.find_gpu_profile()
    out.check(bool(path), "gefunden", os.path.basename(path) + f" ({why})" if path else why)
    if path:
        with open(path, "rb") as fh:
            text, enc = decode_cfg(fh.read())
        pf = ProfileFile(text)
        out(f"  Kodierung {enc}, Zeilenende {'CRLF' if pf.eol == chr(13) + chr(10) else 'LF'}, "
            f"Abschnitte: {', '.join(pf.sections())}")
        for sec in ("Startup", "Profile1", "Profile2", "Profile3", "Profile4",
                    "Profile5", "Defaults", "PreSuspendedMode"):
            if pf.has_section(sec):
                out(f"  [{sec}] {describe_slot(pf, sec)}")
        curve, src = pick_curve(pf, "Profile2")
        out.check(curve is not None, "V/F-Kurve lesbar",
                  f"Basis für neue Kurven: [{src}]" if curve else
                  "keine — in Afterburner 'Speichern' → Slot 1 klicken")
        if curve:
            act = curve.active_points()
            out(f"  {curve.summary()}")
            for target in (700, 800, 850, 900, 950, 1000, 1050, 1100):
                p = min(act, key=lambda q: abs(q.voltage_mv - target))
                if abs(p.voltage_mv - target) <= 13:
                    out(f"    {p.voltage_mv:7.2f} mV  Basis {p.base_mhz:6.0f} MHz  "
                        f"Offset {p.offset_mhz:+5.0f}  -> {p.effective_mhz:6.0f} MHz")

    out.head("Afterburner-Monitoring (MAHM)")
    entries = mon.mahm.debug_entries()
    out.check(bool(entries), "Shared Memory lesbar",
              f"{len(entries)} Quellen" if entries else (mon.mahm.error or "Afterburner läuft nicht?"))
    if entries:
        volt = [e for e in entries if e[4] == 0x40 and e[3] in (0, 0xFFFFFFFF)]
        out.check(bool(volt), "Graph 'GPU-Spannung' aktiv (Monitoring liefert Spannung)",
                  f"{volt[0][2]:.3f} {volt[0][1]}" if volt else
                  "AB → Einstellungen → Überwachung → Haken bei 'GPU-Spannung' → OK")
        pw = [e for e in entries if e[4] == 0x61 and e[3] in (0, 0xFFFFFFFF)]
        if pw:
            out(f"  Leistung laut Afterburner: {pw[0][2]:.1f} {pw[0][1]} (Quelle 0x61)")
    for name, units, val, gpu, sid in entries:
        g = "global" if gpu == 0xFFFFFFFF else f"GPU{gpu}"
        sid_s = f"{sid:#06x}" if isinstance(sid, int) else "?"
        out(f"    {name:<24} {val:>10.2f} {units:<6} {g:<7} id={sid_s}")


# ── dryrun ────────────────────────────────────────────────────────────────────

def _short(line: str) -> str:
    k, sep, v = line.partition("=")
    if sep and len(v) > 48:
        return f"{k}={v[:40]}… ({len(v)} Zeichen)"
    return line


def show_plan(out: Out, ab: AfterburnerController, slot: int, prof: TuneProfile) -> bool:
    path, why = ab.find_gpu_profile()
    if not path:
        out.check(False, "Profildatei", why)
        return False
    with open(path, "rb") as fh:
        old, _enc = decode_cfg(fh.read())
    try:
        new, notes = apply_slot(old, slot, ab._settings_for(prof))
    except ProfileError as e:
        out.check(False, "Profil berechnen", str(e))
        return False
    sec = f"Profile{slot}"
    a, b = ProfileFile(old), ProfileFile(new)
    out(f"  Datei: {os.path.basename(path)}   Abschnitt [{sec}]")
    for n in notes:
        out(f"  • {n}")
    diff = list(difflib.unified_diff(
        [_short(x) for x in a.section_body(sec)], [_short(x) for x in b.section_body(sec)],
        "vorher", "nachher", lineterm="", n=0))
    if diff:
        for d in diff[2:]:
            out(f"    {d}")
    else:
        out("    (keine Änderung — der Slot enthält diese Werte schon)")
    raw_new = b.get(sec, "VFCurve")
    if raw_new:
        c = VFCurve.from_hex(raw_new)
        out(f"  Kurve nachher: {c.summary()}")
    plus = sum(1 for x in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
               if x.startswith("+") and not x.startswith("+++"))
    others = [x for x in a.sections() if x.lower() != sec.lower()]
    untouched = (all(a.items(x) == b.items(x) for x in others) and
                 [x.lower() for x in b.sections() if x.lower() != sec.lower()] ==
                 [x.lower() for x in others])
    out.check(untouched, f"{plus} Zeile(n) neu/geändert, alle anderen Abschnitte unverändert",
              "" if untouched else "ANDERE ABSCHNITTE WÜRDEN SICH ÄNDERN")
    return untouched


def cmd_dryrun(out: Out, ab: AfterburnerController, args):
    out.head(f"Trockenlauf Slot {args.slot} — es wird NICHTS geschrieben")
    prof = TuneProfile(name="__dryrun__", core_offset_mhz=args.core, mem_offset_mhz=args.mem,
                       power_limit_pct=args.power, lock_voltage_mv=args.lock_mv,
                       lock_freq_mhz=args.lock_mhz)
    show_plan(out, ab, args.slot, prof)


# ── live ──────────────────────────────────────────────────────────────────────

def hold(out: Out, seconds: int, what: str):
    out(f"  >>> Jetzt in Afterburner nachsehen: {what}")
    if seconds <= 0:
        return
    end = time.monotonic() + seconds
    while True:
        left = int(end - time.monotonic())
        if left <= 0:
            break
        out(f"      … noch {left} s")
        time.sleep(min(5, left))


def measure(out: Out, mon: GpuMonitor, want_w: float, want_core=None, label=""):
    time.sleep(1.0)
    cur, _mn, _mx, _d = nvml_power(mon)
    out.check(abs(cur - want_w) <= max(2.0, want_w * 0.01),
              f"{label}Power-Limit laut Treiber", f"{cur} W (erwartet {want_w:.0f} W)")
    offs = nvml_offsets(mon)
    if want_core is not None:
        if offs is None:
            out("  [INFO] Core-Offset nicht per NVML auslesbar — bitte in Afterburner prüfen")
        elif offs[0] == want_core:
            out.check(True, f"{label}Core-Offset laut Treiber", f"{offs[0]:+d} MHz")
        else:
            out(f"  [INFO] {label}Core-Offset laut NVML {offs[0]:+d} MHz (erwartet {want_core:+d}) "
                "— NVML meldet Afterburners Offset evtl. nicht; Afterburner-Anzeige zählt")


def cmd_live(out: Out, ab: AfterburnerController, mon: GpuMonitor, args):
    out.head(f"Live-Test Slot {args.slot}")
    if not is_admin():
        out.check(False, "Admin-Rechte", "bitte in einem Administrator-Terminal starten")
        return
    path, why = ab.find_gpu_profile()
    if not ab.available or not path or not mon.nvml.available:
        out.check(False, "Voraussetzungen", why if ab.available else "Afterburner fehlt")
        return
    busy = gpu_busy(mon)
    if busy > 30:
        out.check(False, "GPU im Leerlauf", f"GPU-Last bis {busy:.0f} % — bitte Spiele/3D-Apps schließen")
        return
    out.check(True, "GPU im Leerlauf", f"max. {busy:.0f} % Last")

    with open(path, "rb") as fh:
        original = fh.read()
    _cur, _mn, _mx, dflt = nvml_power(mon)
    if dflt <= 0:
        out.check(False, "Standard-Power-Limit per NVML", "nicht lesbar")
        return
    out(f"  Standard-Power-Limit {dflt} W — Test setzt 90 % = {dflt * 0.9:.0f} W")

    # startup=None: test values never become what the PC boots with (Afterburner [Startup])
    try:
        # A — plain offsets (restart path)
        out.head("A: Core +15 MHz, Power 90 % (Afterburner wird neu gestartet)")
        pa = TuneProfile(name="__selftest__", core_offset_mhz=15, power_limit_pct=90)
        show_plan(out, ab, args.slot, pa)
        t = time.monotonic()
        ok, err = ab.write_and_apply(args.slot, pa, startup=None)
        out.check(ok, "Schreiben + Afterburner-Neustart", err or f"{time.monotonic() - t:.1f} s")
        if ab.last_backup:
            out(f"  Backup der Originaldatei: {ab.last_backup}")
        if ok:
            measure(out, mon, dflt * 0.9, 15, "A: ")
            hold(out, args.hold, "Core Clock +15, Power Limit 90 %")

            # A2 — same values again: must NOT restart Afterburner
            out.head("A2: dieselben Werte nochmal (ohne Neustart)")
            t = time.monotonic()
            ok2, err2 = ab.write_and_apply(args.slot, pa, startup=None)
            dt = time.monotonic() - t
            out.check(ok2 and dt < 6, "Nur -Profile gesendet, kein Neustart", err2 or f"{dt:.1f} s")
            out.check(ab.is_running(), "Afterburner läuft")

        # B — flat V/F curve (only with --curve)
        if args.curve:
            out.head("B: flache V/F-Kurve (Undervolt-Deckel, kein OC)")
            with open(path, "rb") as fh:
                pf = ProfileFile(decode_cfg(fh.read())[0])
            curve, src = pick_curve(pf, f"Profile{args.slot}")
            if curve is None:
                out.check(False, "V/F-Kurve vorhanden", "keine Kurve im Profil")
            else:
                lp = curve.lock_point(1000)
                pb = TuneProfile(name="__selftest_vf__", lock_voltage_mv=round(lp.voltage_mv),
                                 lock_freq_mhz=round(lp.base_mhz))
                show_plan(out, ab, args.slot, pb)
                ok, err = ab.write_and_apply(args.slot, pb, startup=None)
                out.check(ok, "Kurve schreiben + Neustart", err)
                if ok:
                    measure(out, mon, dflt, None, "B: ")
                    hold(out, args.hold, f"Strg+F (Kurven-Editor): Kurve ab {lp.voltage_mv:.0f} mV "
                                         f"flach bei {lp.base_mhz:.0f} MHz")
    finally:
        out.head("Zurücksetzen")
        ok, err = ab.reset_to_stock(args.slot, startup=None)
        out.check(ok, "Werkswerte in den Slot + anwenden", err)
        if ok:
            measure(out, mon, dflt, 0, "Reset: ")
        ab.close()
        try:
            ab._write_bytes(path, original)
            with open(path, "rb") as fh:
                out.check(fh.read() == original, "Originale Profildatei wiederhergestellt")
        except OSError as e:
            out.check(False, "Originale Profildatei wiederhergestellt", str(e))
        ok, err = ab.start()
        out.check(ok, "Afterburner wieder gestartet", err)


def cmd_restore(out: Out, ab: AfterburnerController, args):
    out.head("Backup zurückspielen")
    path, why = ab.find_gpu_profile()
    if not path:
        out.check(False, "Profildatei", why)
        return
    src = args.file
    if not src:
        cands = sorted(glob.glob(os.path.join(ab.backup_dir(), "*_" + os.path.basename(path))))
        if not cands:
            out.check(False, "Backup gefunden", f"keins in {ab.backup_dir()}")
            return
        src = cands[-1]
    if not is_admin():
        out.check(False, "Admin-Rechte", "bitte in einem Administrator-Terminal starten")
        return
    ok, err = ab.restore_file(src)
    out.check(ok, f"{os.path.basename(src)} -> {os.path.basename(path)}", err)


def main():
    ap = argparse.ArgumentParser(description="GameOptimizerPro — Afterburner-Selbsttest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    d = sub.add_parser("dryrun")
    d.add_argument("--slot", type=int, default=2)
    d.add_argument("--core", type=int, default=15)
    d.add_argument("--mem", type=int, default=0)
    d.add_argument("--power", type=int, default=90)
    d.add_argument("--lock-mv", type=int, default=0)
    d.add_argument("--lock-mhz", type=int, default=0)
    lv = sub.add_parser("live")
    lv.add_argument("--slot", type=int, default=2)
    lv.add_argument("--hold", type=int, default=20)
    lv.add_argument("--curve", action="store_true")
    lv.add_argument("--pause", action="store_true")
    r = sub.add_parser("restore")
    r.add_argument("file", nargs="?")
    args = ap.parse_args()

    out = Out(args.cmd)
    mon = GpuMonitor()
    ab = AfterburnerController(mon.nvml.get_pci_identity())
    ab.on_ab_closing = mon.mahm.suspend
    ab.on_ab_started = mon.mahm.resume
    out(f"GameOptimizerPro Afterburner-Selbsttest — {args.cmd} — {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        if args.cmd == "info":
            cmd_info(out, ab, mon)
        elif args.cmd == "dryrun":
            cmd_dryrun(out, ab, args)
        elif args.cmd == "live":
            cmd_live(out, ab, mon, args)
        elif args.cmd == "restore":
            cmd_restore(out, ab, args)
    finally:
        out.head("Ergebnis")
        out(f"  {out.fails} Fehler.   Protokoll: {out.path}")
        out.close()
        mon.close()
        if getattr(args, "pause", False):
            try:
                input("\nEnter drücken zum Schließen …")
            except EOFError:
                pass
    sys.exit(1 if out.fails else 0)


if __name__ == "__main__":
    main()
