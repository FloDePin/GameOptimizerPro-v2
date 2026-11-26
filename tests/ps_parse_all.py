"""Parse (never execute) every PowerShell snippet the app can run: tweak apply +
revert commands, verifier checks (wrapped exactly like TweakVerifier does), the
clean-ups of retired tweaks and the Services Manager scripts — in BOTH languages
(round 49: the messages are built in the app's language, and PowerShell reads the
German quotation marks „ “ as real quotes — a German-only text could break a script
the English parse never saw)."""
import importlib, json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import core.i18n as I18N
I18N._save_lang = lambda lang: None

snips = {}
for lang in ("en", "de"):
    I18N._current_lang = lang
    import core.tweaks as T
    import core.tweak_verifier as TV
    import core.services as SV
    T = importlib.reload(T)
    TV = importlib.reload(TV)
    for t in T.ALL_TWEAKS:
        snips[f"{lang}:{t.id}:apply"] = t.ps_command.strip()
        if (t.revert_cmd or "").strip():
            snips[f"{lang}:{t.id}:revert"] = t.revert_cmd.strip()
    for tid in TV.VERIFY_MAP:
        snips[f"{lang}:{tid}:verify"] = TV._check_line(tid)
    for tid, (_de, _en, cmd) in T.RETIRED_TWEAKS.items():      # "Revert all" / "Clean up leftovers"
        if cmd.strip():
            snips[f"{lang}:{tid}:retired-cleanup"] = cmd.strip()
    # the Services Manager's scripts, captured (never run): one service and several
    seen = []
    real_run, real_read, real_state = SV._run_ps, SV._read_start, SV.STATE_FILE
    SV._run_ps = lambda script, timeout=120: (seen.append(script), "")[1]
    SV._read_start = lambda n: (2, False)
    SV.STATE_FILE = os.path.join(tempfile.mkdtemp(prefix="gop_psparse_svc_"), "s.json")
    try:
        from pathlib import Path
        SV.STATE_FILE = Path(SV.STATE_FILE)
        for names in (["SysMain"], ["SysMain", "WSearch"]):
            SV.disable(names)
            SV.enable(names)
    finally:
        SV._run_ps, SV._read_start, SV.STATE_FILE = real_run, real_read, real_state
    for i, s in enumerate(seen):
        snips[f"{lang}:services:{i}"] = s

tmp = tempfile.mkdtemp(prefix="gop_psparse_")
f = os.path.join(tmp, "snips.json")
json.dump(snips, open(f, "w", encoding="utf-8"))
ps = (
    "$s = Get-Content -Raw -Encoding UTF8 '%s' | ConvertFrom-Json; $bad=0; $n=0; "
    "foreach($p in $s.PSObject.Properties){ $n++; $e=$null; "
    "[void][System.Management.Automation.Language.Parser]::ParseInput($p.Value,[ref]$null,[ref]$e); "
    "if($e.Count){ $bad++; \"ERR $($p.Name): $($e[0].Message) @ $($e[0].Extent.StartLineNumber):$($e[0].Extent.StartColumnNumber)\" } }; "
    "\"PARSED=$n BAD=$bad\"" % f)
r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
print(r.stdout.strip()[-3000:])
print(r.stderr.strip()[-1000:])
import shutil; shutil.rmtree(tmp, ignore_errors=True)
ok = "BAD=0" in r.stdout
print(("  ok   " if ok else "  FAIL ") + f"every snippet parses in English and German ({len(snips)})")
sys.exit(0 if ok else 1)
