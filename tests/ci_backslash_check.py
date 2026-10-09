"""Exactly the CI regex (8 backslashes in a raw string = 4 literal backslashes
in the SOURCE text, i.e. a reg.exe path that would contain 2 at runtime)."""
import os, re, sys
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tweaks_src = open("core/tweaks.py", encoding="utf-8").read()
bad = re.findall(r'reg (?:add|delete) "[^"]*\\\\\\\\[^"]*"', tweaks_src)
print("CI check - doubled-backslash reg.exe paths:", len(bad))
for b in bad[:10]:
    print("  ", b[:140])

# Stronger runtime check: evaluate every tweak command string and look at the
# reg.exe paths as PowerShell will actually receive them.
sys.path.insert(0, ".")
from core.tweaks import ALL_TWEAKS
rt_bad = []
for t in ALL_TWEAKS:
    for kind, cmd in (("apply", t.ps_command), ("revert", t.revert_cmd or "")):
        for m in re.finditer(r'reg(?:\.exe)? (?:add|delete|query) "([^"]+)"', cmd, re.I):
            if "\\\\" in m.group(1):
                rt_bad.append(f"{t.id}:{kind}: {m.group(1)}")
print("runtime reg.exe paths with a doubled backslash:", len(rt_bad))
for b in rt_bad[:10]:
    print("  ", b)
sys.exit(1 if bad or rt_bad else 0)
