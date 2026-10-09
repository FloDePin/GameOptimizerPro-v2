"""Round 20 — tweak review: the new 'Optimizations for windowed games' (apply / revert keep the
other DirectX flags), the Store-recommendations check reads 'access denied' as applied, the
shader-cache cleanup is an action (no status, no drift, not in a preset).
The registry part runs on a throwaway HKCU key, never the real DirectX settings."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label, flush=True)
    if not cond:
        FAILS.append(label)


from core.tweaks import ALL_TWEAKS, get_by_id
from core.tweak_verifier import VERIFY_MAP
from core import tweak_presets as TP
from core.tweak_i18n import TWEAK_DESC_EN, TWEAK_NAME_EN

print("the tweak list")
t = get_by_id("windowed_game_optimizations")
check(t and t.category == "Gaming" and t.group == "GPU & Driver" and t.risk == "safe"
      and "windowed_game_optimizations" in VERIFY_MAP and "windowed_game_optimizations" in TWEAK_DESC_EN
      and TWEAK_NAME_EN.get("windowed_game_optimizations") == "Optimizations for windowed games",
      "new: optimizations for windowed games (Gaming, safe, status check, English text)")
medium = set(TP._MEDIUM_EXTRA)
hard = set(TP._HARD_EXTRA)
check("windowed_game_optimizations" in medium and "clear_shader_cache" not in hard,
      "presets: 'Mittel' turns it on; 'Hart' no longer wipes the shader cache")
check("clear_shader_cache" not in VERIFY_MAP and "einmalige Aktion" in get_by_id("clear_shader_cache").desc,
      "the shader-cache cleanup is an action: no status (a cache that fills again was 'drift')")
check(len(ALL_TWEAKS) == 107 and len({x.id for x in ALL_TWEAKS}) == 107, "107 tweaks, ids unique")

if os.name != "nt":
    print("  (not Windows: registry checks skipped)")
    sys.exit(2)

print("apply / revert on a throwaway key")
TEST_KEY = f"HKCU:\\Software\\GOP_test_{os.getpid()}"
REAL = "HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"


def ps(cmd: str) -> str:
    cmd = cmd.replace(REAL, TEST_KEY)
    assert REAL not in cmd
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=60, creationflags=0x08000000)
    return (r.stdout or "").strip()


def value() -> str:
    return ps(f'(Get-ItemProperty "{TEST_KEY}" -Name DirectXUserGlobalSettings -EA SilentlyContinue)'
              f'.DirectXUserGlobalSettings')


check_cmd = VERIFY_MAP["windowed_game_optimizations"]
try:
    ps(f'New-Item -Path "{TEST_KEY}" -Force | Out-Null; Set-ItemProperty -Path "{TEST_KEY}" '
       f'-Name DirectXUserGlobalSettings -Value "VRROptimizeEnable=0;AutoHDREnable=1;" -Type String')
    check(ps(check_cmd) == "0", "before: the check says off")
    ps(t.ps_command)
    v1 = value()
    check(v1 == "VRROptimizeEnable=0;AutoHDREnable=1;SwapEffectUpgradeEnable=1;" and ps(check_cmd) == "1",
          f"apply: the flag added, the other flags kept: {v1!r}")
    ps(t.ps_command)
    check(value() == v1, "applied twice: no duplicate")
    ps(t.revert_cmd)
    check(value() == "VRROptimizeEnable=0;AutoHDREnable=1;" and ps(check_cmd) == "0",
          f"revert: only our flag removed (Windows' default again): {value()!r}")
    ps(f'Remove-ItemProperty -Path "{TEST_KEY}" -Name DirectXUserGlobalSettings')
    ps(t.ps_command)
    check(value() == "SwapEffectUpgradeEnable=1;", f"without a value before: just the flag: {value()!r}")
    ps(t.revert_cmd)
    check(value() == "", "revert: the value removed again (nothing else was in it)")
finally:
    ps(f'Remove-Item -Path "{TEST_KEY}" -Recurse -Force -EA SilentlyContinue')

print("Store recommendations: 'access denied' is the tweak working")
src = VERIFY_MAP["store_no_recommended"]
check("UnauthorizedAccessException" in src and "2>&1" in src,
      "the deny rule also blocks reading the rules — that reads as applied, not as 'not active'")

print("\n%d failure(s)" % len(FAILS))
for f in FAILS:
    print("  -", f)
sys.exit(1 if FAILS else 0)
