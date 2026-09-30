"""Parse (never execute) every PowerShell snippet the app can run: tweak apply +
revert commands, verifier checks (wrapped exactly like TweakVerifier does), and
the Services Manager scripts."""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.tweaks import ALL_TWEAKS
from core.tweak_verifier import VERIFY_MAP

snips = {}
for t in ALL_TWEAKS:
    snips[f"{t.id}:apply"] = t.ps_command.strip()
    if (t.revert_cmd or "").strip():
        snips[f"{t.id}:revert"] = t.revert_cmd.strip()
for tid, cmd in VERIFY_MAP.items():
    snips[f"{tid}:verify"] = (f'try {{ $__r=$({cmd.strip()}); Write-Output "{tid}|$__r" }}'
                              f' catch {{ Write-Output "{tid}|0" }}')

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
sys.exit(0 if "BAD=0" in r.stdout else 1)
