"""
GameOptimizerPro — Windows update check for the tweak list (developer tool, read-only)

Run after a Windows update:
    python tools/windows_watch.py            state of every tweak + what changed since the last run
    python tools/windows_watch.py --scan     + are the tweaks' registry value names still in Windows' files?
    python tools/windows_watch.py --winget   + are the program installer's ids still in winget's source?
    python tools/windows_watch.py --out DIR  where the report + state go (default: privat/, not published)

What it reports:
  * Windows build / version / edition, and the build of the last run
  * tweaks the app applied that are no longer active (an update reset them), every status change since the
    last run (active -> inactive, or a tweak Windows now sets by itself), checks that fail
  * targets that are gone: services, scheduled tasks, power settings, Store apps a removal tweak looks for
  * --scan: value names no Windows file contains any more (the setting is probably not read: a dead tweak)
  * --winget: installer ids winget no longer knows
Nothing on the system is changed: status checks, Get-Service / Get-ScheduledTask / registry reads, a
read-only search of Windows' own files, `winget show`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# value names too generic to tell anything when found in a Windows file
_GENERIC = {"value", "enabled", "flags", "priority", "start", "default", "(default)", "affinity", "type",
            "acsettingindex",
            "sr_audiopriority"}          # the app's own marker (HKLM\SOFTWARE\GameOptimizerPro)
# names Windows builds at run time — searched by their fixed part
_SCAN_AS = [(re.compile(r"^SubscribedContent-\d+Enabled$"), "SubscribedContent-"),
            (re.compile(r"^StateFlags\d{4}$"), "StateFlags")]
# read by a program outside Windows' folders (its folder is searched too when it is installed)
EXTERNAL = {"KFMBlockOptIn": "OneDrive", "NVLatency": "NVIDIA-Treiber", "EnableULPS": "AMD-Treiber",
            "EnableULPS_NA": "AMD-Treiber", "DisableAIFeatures": "Editor (Store-App)"}
# Store apps whose own policy values tweaks set: their install folders are searched too
_APP_PACKAGES = ("Microsoft.Paint", "Microsoft.WindowsNotepad")
# status checks that need administrator rights (they fail in a run without them)
ADMIN_ONLY = {"remove_xbox", "remove_bloatware", "remove_m365_copilot_devhome", "disable_hpet",
              "disable_reserved_storage"}


def _ps(script: str, timeout: int = 180) -> str:
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW)
    return (r.stdout or "").strip()


def _is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def system_info() -> dict:
    out = _ps("$cv=Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'; "
              "@{build=\"$($cv.CurrentBuild).$($cv.UBR)\"; version=[string]$cv.DisplayVersion; "
              "edition=[string]$cv.EditionID} | ConvertTo-Json -Compress")
    try:
        return json.loads(out)
    except ValueError:
        return {"build": "", "version": "", "edition": ""}


# ── what each tweak touches ──────────────────────────────────────────────────────────────────────
_RX_V = re.compile(r"/v\s+\"?([A-Za-z0-9_\-{}.,+ ]+?)\"?\s+/(?:t|f|d)\b")
_RX_NAME = re.compile(r"-Name\s+['\"]?([A-Za-z_][A-Za-z0-9_\-{}.,]*)['\"]?")
_RX_ROW = re.compile(r"@\('(?:HKCU|HKLM)','[^']*','([^']+)',")
_RX_SVC = re.compile(r"(?:Set|Stop|Start|Get)-Service\s+(?:-Name\s+)?['\"]?([A-Za-z][A-Za-z0-9_]+)")
_RX_SVC_LIST = re.compile(r"\$svcs\s*=\s*@\(([^)]*)\)")
_RX_TASK = re.compile(r"'(\\Microsoft\\Windows\\[^']+)'")
_RX_TASK_TN = re.compile(r'/TN\s+"(\\Microsoft\\Windows\\[^"]+)"')
_RX_PWR = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+"
                     r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
_RX_APPX = re.compile(r"'(\*[A-Za-z0-9.\-]+\*)'|\"(\*[A-Za-z0-9.\-]+\*)\"")


def targets(tweak) -> dict:
    """Registry value names, services, scheduled tasks, power settings and Store app patterns a tweak uses."""
    cmd = (tweak.ps_command or "") + "\n" + (tweak.revert_cmd or "")
    apply = tweak.ps_command or ""         # value names: what the tweak SETS (a revert may clean up old ones)
    values = set(_RX_V.findall(apply)) | set(_RX_NAME.findall(apply)) | set(_RX_ROW.findall(apply))
    values = {v.strip() for v in values if v.strip() and not v.startswith("$")}
    svcs = set(_RX_SVC.findall(cmd))
    for lst in _RX_SVC_LIST.findall(cmd):
        svcs |= set(re.findall(r"'([A-Za-z][A-Za-z0-9_\-]+)'", lst))
    tasks = set(_RX_TASK.findall(cmd)) | set(_RX_TASK_TN.findall(cmd))
    power = {(a.lower(), b.lower()) for a, b in _RX_PWR.findall(cmd)}
    appx = {a or b for a, b in _RX_APPX.findall(cmd)} if "Get-AppxPackage" in cmd else set()
    return {"values": sorted(values), "services": sorted(svcs), "tasks": sorted(tasks),
            "power": sorted(power), "appx": sorted(appx)}


def existence(all_targets: dict) -> dict:
    """Which services / tasks / power settings / Store apps exist on this Windows (read-only)."""
    svcs = sorted({s for t in all_targets.values() for s in t["services"]})
    tasks = sorted({s for t in all_targets.values() for s in t["tasks"]})
    power = sorted({p for t in all_targets.values() for p in t["power"]})
    appx = sorted({a for t in all_targets.values() for a in t["appx"]})
    q = lambda xs: "@(" + ",".join("'" + x.replace("'", "''") + "'" for x in xs) + ")"
    script = (
        "$r=@{}; "
        f"$r.services=@(foreach($s in {q(svcs)}){{ if(Get-Service -Name $s -EA SilentlyContinue){{ $s }} }}); "
        f"$r.tasks=@(foreach($t in {q(tasks)}){{ $i=$t.LastIndexOf('\\'); "
        "if(Get-ScheduledTask -TaskPath $t.Substring(0,$i+1) -TaskName $t.Substring($i+1) -EA SilentlyContinue){ $t } }); "
        f"$r.power=@(foreach($p in {q([a + '|' + b for a, b in power])}){{ $a,$b=$p.Split('|'); "
        "if(Test-Path \"HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerSettings\\$a\\$b\"){ $p } }); "
        f"$r.appx=@(foreach($a in {q(appx)}){{ if(Get-AppxPackage -AllUsers $a -EA SilentlyContinue){{ $a }} "
        "elseif(Get-AppxPackage $a -EA SilentlyContinue){ $a } }); "
        "$r | ConvertTo-Json -Compress -Depth 3")
    try:
        got = json.loads(_ps(script, timeout=300) or "{}")
    except ValueError:
        got = {}
    present = {k: set(got.get(k) or []) for k in ("services", "tasks", "power", "appx")}
    return {"services": {s: s in present["services"] for s in svcs},
            "tasks": {t: t in present["tasks"] for t in tasks},
            "power": {f"{a}|{b}": f"{a}|{b}" in present["power"] for a, b in power},
            "appx": {a: a in present["appx"] for a in appx}}


def scan_values(names, roots=None) -> dict:
    """name -> number of Windows files containing it (UTF-16 or ASCII). Read-only."""
    win = os.environ.get("WINDIR", r"C:\Windows")
    roots = roots or [os.path.join(win, d) for d in ("System32", "SystemApps")]
    enc = {n: (n.encode("utf-16-le"), n.encode("ascii", "ignore")) for n in names}
    hits = {n: 0 for n in names}
    def walk_all():
        # explorer.exe and the other programs directly in the Windows folder (not recursive)
        if os.path.isdir(win):
            yield win, [], [f for f in os.listdir(win) if os.path.isfile(os.path.join(win, f))]
        for root in roots:
            yield from os.walk(root)          # top-down: clearing dn below prunes the walk

    for dp, dn, fn in walk_all():
        if True:                              # (keeps the block below as it was)
            low = dp.lower()
            if "\\winsxs" in low or "\\driverstore" in low or "\\catroot" in low:
                dn[:] = []
                continue
            for f in fn:
                if not f.lower().endswith((".dll", ".exe", ".sys", ".cpl", ".ocx", ".js", ".json", ".winmd", ".xbf")):
                    continue
                p = os.path.join(dp, f)
                try:
                    if os.path.getsize(p) > 120_000_000:
                        continue
                    with open(p, "rb") as fh:
                        data = fh.read()
                except OSError:
                    continue
                for n, (u, a) in enc.items():
                    if u in data or (a and a in data):
                        hits[n] += 1
    return hits


def winget_missing(ids) -> list[str]:
    from core import winget_installer as WI
    exe = WI.winget_exe()
    if not exe:
        return ["(winget not found)"]
    missing = []
    for pid in ids:
        for attempt in range(3):                 # one at a time: parallel calls fail now and then
            r = subprocess.run([exe, "show", "--id", pid, "-e", "--source", "winget", "--accept-source-agreements",
                                "--disable-interactivity"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, creationflags=NO_WINDOW)
            if r.returncode == 0:
                break
            if (r.returncode & 0xFFFFFFFF) == 0x8A150014:      # no package found
                missing.append(pid)
                break
            time.sleep(2)
        else:
            missing.append(pid + " (winget error)")
    return missing


def tweak_states(ids) -> dict:
    from core.tweak_verifier import TweakVerifier
    res = TweakVerifier(timeout_s=60).verify_all(ids, {i: True for i in ids})
    return {i: ("error" if (res.get(i) is None or res[i].error) else ("active" if res[i].actual else "inactive"))
            for i in ids}


def run(out_dir: Path, scan: bool = False, winget: bool = False) -> tuple[Path, dict]:
    from core.tweaks import ALL_TWEAKS
    from core.tweak_verifier import VERIFY_MAP
    out_dir.mkdir(parents=True, exist_ok=True)
    state_file = out_dir / "windows_watch.json"
    try:
        last = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    try:
        applied = set(json.loads((BASE / "logs" / "applied_tweaks.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        applied = set()

    info = system_info()
    ids = [t.id for t in ALL_TWEAKS if t.id in VERIFY_MAP]
    states = tweak_states(ids)
    tg = {t.id: targets(t) for t in ALL_TWEAKS}
    ex = existence(tg)
    scan_hits = {}
    if scan:
        names = sorted({v for t in tg.values() for v in t["values"] if len(v) >= 8 and v.lower() not in _GENERIC})
        alias = {n: next((fixed for rx, fixed in _SCAN_AS if rx.match(n)), n) for n in names}
        extra = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "OneDrive"),
                 os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Microsoft OneDrive")]
        locs = _ps("(Get-AppxPackage -Name " + ",".join(_APP_PACKAGES) +
                   " -EA SilentlyContinue | ForEach-Object { $_.InstallLocation }) -join '|'")
        extra += [x for x in locs.split("|") if x]
        extra = [d for d in extra if d and os.path.isdir(d)]
        roots = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), d) for d in ("System32", "SystemApps")] + extra
        found = scan_values(sorted(set(alias.values())), roots)
        scan_hits = {n: found[alias[n]] for n in names}
    missing_ids = []
    if winget:
        from core import winget_installer as WI
        missing_ids = winget_missing([p.id for p in WI.CATALOG])

    prev = last.get("states", {})
    drift = [i for i in ids if i in applied and states[i] == "inactive"]
    changed = [(i, prev[i], states[i]) for i in ids if i in prev and prev[i] != states[i]]
    errors = [i for i in ids if states[i] == "error"]
    gone = {k: [x for x, ok in v.items() if not ok] for k, v in ex.items()}

    def users_of(kind, x):
        if kind == "power":
            return [t for t, d in tg.items() if x in {f"{a}|{b}" for a, b in d["power"]}]
        return [t for t, d in tg.items() if x in d[kind]]
    by_target = {k: {x: users_of(k, x) for x in xs} for k, xs in gone.items()}
    dead = sorted(n for n, c in scan_hits.items() if c == 0)
    dead_by = {n: [t for t, d in tg.items() if n in d["values"]] for n in dead}

    lines = [f"# Windows-Check {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Windows {info.get('version')} · Build {info.get('build')} · {info.get('edition')}"
             + (f" — letzter Lauf: Build {last.get('build')} ({last.get('date', '?')})" if last else " — erster Lauf"),
             ""]
    if last and last.get("build") != info.get("build"):
        lines += [f"**Windows wurde aktualisiert:** {last.get('build')} → {info.get('build')}", ""]
    lines += ["## Von der App angewendet, aber nicht mehr aktiv", ""]
    lines += [f"- {i}" for i in drift] or ["- keine"]
    lines += ["", "## Status geändert seit dem letzten Lauf", ""]
    lines += [f"- {i}: {a} → {b}" + (" (setzt Windows das jetzt selbst? Standard prüfen)" if b == "active" and i not in applied else "")
              for i, a, b in changed] or ["- keine" if last else "- (erster Lauf — nichts zum Vergleichen)"]
    lines += ["", "## Prüfungen mit Fehler", ""]
    admin = _is_admin()
    lines += [f"- {i}" + (" (braucht Administratorrechte — dieser Lauf hatte keine)" if i in ADMIN_ONLY and not admin else "")
              for i in errors] or ["- keine"]
    lines += ["", "## Ziele, die es auf diesem Windows nicht gibt", ""]
    any_gone = False
    for k, label in (("services", "Dienst"), ("tasks", "Aufgabe"), ("power", "Energieoption"), ("appx", "Store-App")):
        for x in gone[k]:
            any_gone = True
            lines.append(f"- {label} `{x}` — Tweaks: {', '.join(by_target[k].get(x) or ['?'])}")
    if not any_gone:
        lines.append("- keine")
    lines.append("")
    lines.append("(Store-Apps, die fehlen, sind meist schon entfernt — kein Fehler. Fehlende Dienste/Aufgaben/"
                 "Energieoptionen: Tweak prüfen, evtl. nicht mehr nötig.)")
    if scan:
        lines += ["", f"## Registry-Namen in keiner Windows-Datei mehr ({len(scan_hits)} gesucht)", ""]
        lines += [f"- `{n}` — Tweaks: {', '.join(dead_by[n])}"
                  + (f" (liest {EXTERNAL[n]}, nicht Windows — hier nicht prüfbar)" if n in EXTERNAL else " ← prüfen")
                  for n in dead] or ["- keine — alle Namen kommen noch vor"]
        lines.append("")
        lines.append("(Nicht gefunden heißt: wahrscheinlich nicht mehr gelesen. Manche Werte liest eine App außerhalb "
                     "von System32/SystemApps (OneDrive, Treiber) — dort gegenprüfen.)")
    if winget:
        lines += ["", "## winget-IDs, die winget nicht mehr kennt", ""]
        lines += [f"- {i}" for i in missing_ids] or ["- keine"]
    lines.append("")
    report = out_dir / f"windows_watch_{datetime.now():%Y%m%d_%H%M}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    summary = {"date": f"{datetime.now():%Y-%m-%d %H:%M}", "build": info.get("build"), "version": info.get("version"),
               "edition": info.get("edition"), "states": states, "gone": gone, "dead_values": dead,
               "winget_missing": missing_ids, "drift": drift, "changed": changed, "errors": errors}
    state_file.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return report, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only Windows update check for GameOptimizerPro's tweaks")
    ap.add_argument("--scan", action="store_true", help="search Windows' files for the registry value names")
    ap.add_argument("--winget", action="store_true", help="check the installer's winget ids")
    ap.add_argument("--out", default=str(BASE / "privat"), help="folder for the report and the state")
    a = ap.parse_args(argv)
    if os.name != "nt":
        print("Windows only")
        return 2
    try:                                    # the file search reads a few GB: never in a game's way
        import psutil
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    except Exception:
        pass
    t0 = time.time()
    report, s = run(Path(a.out), scan=a.scan, winget=a.winget)
    n = len(s["states"])
    act = sum(1 for v in s["states"].values() if v == "active")
    print(f"Windows {s['version']} build {s['build']} ({s['edition']}): {act}/{n} tweaks active, "
          f"{len(s['drift'])} applied but inactive, {len(s['changed'])} changed, {len(s['errors'])} check errors, "
          f"{sum(len(v) for v in s['gone'].values())} targets missing"
          + (f", {len(s['dead_values'])} value names not found" if a.scan else "")
          + (f", {len(s['winget_missing'])} winget ids missing" if a.winget else "")
          + f" — {time.time() - t0:.0f} s")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
