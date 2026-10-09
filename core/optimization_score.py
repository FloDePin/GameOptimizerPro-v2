"""
GameOptimizerPro v2.0 — Optimierungs-Score & Drift-Erkennung (aus v1)

Score: Anteil der SICHEREN, auf diesem PC anwendbaren und prüfbaren Tweaks, die
gerade wirklich aktiv sind (echter Systemzustand über den Tweak-Verifier, nicht
die App-Liste). Moderate/fortgeschrittene Tweaks zählen bewusst nicht mit — ein
hoher Score soll nicht zu riskanten Eingriffen verleiten. Einmal-Aktionen und
Entweder-oder-Wahlen (Energiesparplan, DNS-Anbieter) ebenfalls nicht.

Drift: Tweaks, die laut App angewendet wurden, aber nicht (mehr) vollständig
aktiv sind — z. B. von einem Windows-Funktionsupdate zurückgesetzt oder weil eine
neuere Tweak-Version mehr setzt als die damals angewendete.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.tweaks import ALL_TWEAKS, Tweak
from core.tweak_verifier import TweakVerifier, VERIFY_MAP

# One-time actions (their check says nothing about an optimized state) and
# either-or choices (only one power plan / DNS provider can be active).
SCORE_EXCLUDE = {"flush_dns", "clear_shader_cache", "run_disk_cleanup",
                 "ultimate_performance", "power_high", "power_balanced",
                 "dns_cloudflare", "dns_google"}
# Never re-applied automatically after a drift: one-time actions.
DRIFT_EXCLUDE = {"flush_dns", "clear_shader_cache", "run_disk_cleanup"}


def applicable(tweak: Tweak, hw) -> bool:
    """Hardware filter (the same one the Optimizer uses everywhere)."""
    if hw is None:
        return True
    if tweak.requires_nvidia and not getattr(hw, "is_nvidia", False):
        return False
    if tweak.requires_amd and not getattr(hw, "is_amd_gpu", False):
        return False
    if getattr(tweak, "requires_nvme", False) and not getattr(hw, "has_nvme", False):
        return False
    return True


def score_ids(hw) -> list[str]:
    return [t.id for t in ALL_TWEAKS
            if t.risk == "safe" and t.id in VERIFY_MAP and t.id not in SCORE_EXCLUDE
            and applicable(t, hw)]


@dataclass
class ScoreResult:
    active:    int = 0
    checkable: int = 0            # checked without error
    unknown:   int = 0            # check failed (no output / timeout)
    inactive:  list = field(default_factory=list)

    @property
    def score(self) -> int:
        return round(self.active / self.checkable * 100) if self.checkable else 0


def compute_score(hw, verifier: TweakVerifier | None = None) -> ScoreResult:
    ids = score_ids(hw)
    res = (verifier or TweakVerifier()).verify_all(ids, {i: True for i in ids})
    out = ScoreResult()
    for i in ids:
        r = res.get(i)
        if r is None or r.error:
            out.unknown += 1
            continue
        out.checkable += 1
        if r.actual:
            out.active += 1
        else:
            out.inactive.append(i)
    return out


def check_applied(applied_ids, hw, verifier: TweakVerifier | None = None):
    """-> (drifted, switched).
    drifted:  applied (per the app's state) but not active any more.
    switched: [(old, new)] — an either-or tweak the app applied is not active,
              but ANOTHER choice of its group is (e.g. the DNS was set to
              Cloudflare by hand after the app set Google). That is the user's
              current choice, not drift: offering to "re-apply" the old one would
              switch it back. Checks that fail (no output / timeout) never count."""
    from core.tweaks import alternatives_of
    by_id = {t.id: t for t in ALL_TWEAKS}
    ids = [i for i in applied_ids
           if i in by_id and i in VERIFY_MAP and i not in DRIFT_EXCLUDE
           and applicable(by_id[i], hw)]
    if not ids:
        return [], []
    extra = [a for i in ids for a in alternatives_of(i)
             if a in VERIFY_MAP and a not in ids and applicable(by_id[a], hw)]
    check = list(dict.fromkeys(ids + extra))
    res = (verifier or TweakVerifier()).verify_all(check, {i: True for i in check})

    def state(i):
        r = res.get(i)
        return None if r is None or r.error else bool(r.actual)

    drifted, switched = [], []
    for i in ids:
        if state(i) is not False:
            continue
        alt = next((a for a in alternatives_of(i) if state(a) is True), None)
        if alt:
            switched.append((i, alt))
        else:
            drifted.append(i)
    return drifted, switched


def find_drift(applied_ids, hw, verifier: TweakVerifier | None = None) -> list[str]:
    """Applied but not active any more (see check_applied)."""
    return check_applied(applied_ids, hw, verifier)[0]
