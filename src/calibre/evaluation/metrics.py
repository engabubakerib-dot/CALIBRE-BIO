"""Pre-registered outcome metrics (definitions mirror docs/preregistration.md §4).

Every condition (raw, self-consistency, retrieval-only, distribution filter,
CALIBRE full, ablations) is a *filter* over the same bank of LLM-generated,
gold-labelled claims, producing accept / flag / reject per claim.

* ICR  (Invalid Claim Rate)       = invalid accepted / all accepted
* FAR  (False Acceptance Rate)    = invalid accepted / all invalid       (the "budget" in H3)
* NRR  (Novelty Retention Rate)   = novel_plausible not rejected / all novel_plausible
* VRR  (Valid Retention Rate)     = valid accepted / all valid
* Flag rate                       = flagged / all  (human-review cost)

"Raw" accepts everything, so raw ICR = prevalence of invalid claims among outputs.
Claims labelled ``unresolvable`` are excluded from the primary analysis.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from typing import Callable, Sequence

ACCEPT, FLAG, REJECT = "accept", "flag", "reject"


def _safe(num: int, den: int) -> float:
    return num / den if den else float("nan")


def outcome_metrics(labels: Sequence[str], decisions: Sequence[str],
                    *, flagged_counts_as_accepted: bool = False) -> dict[str, float]:
    """``flagged_counts_as_accepted`` gives the worst case if reviewers rubber-stamp flags."""
    pairs = [(y, d) for y, d in zip(labels, decisions) if y != "unresolvable"]
    acc = {ACCEPT, FLAG} if flagged_counts_as_accepted else {ACCEPT}
    accepted = [y for y, d in pairs if d in acc]
    n_invalid = sum(y == "invalid" for y, _ in pairs)
    n_novel = sum(y == "novel_plausible" for y, _ in pairs)
    n_valid = sum(y == "valid" for y, _ in pairs)
    return {
        "n": len(pairs),
        "n_accepted": len(accepted),
        "ICR": _safe(sum(y == "invalid" for y in accepted), len(accepted)),
        "FAR": _safe(sum(y == "invalid" and d in acc for y, d in pairs), n_invalid),
        "NRR": _safe(sum(y == "novel_plausible" and d != REJECT for y, d in pairs), n_novel),
        "VRR": _safe(sum(y == "valid" and d == ACCEPT for y, d in pairs), n_valid),
        "flag_rate": _safe(sum(d == FLAG for _, d in pairs), len(pairs)),
    }


def relative_reduction(baseline: float, treated: float) -> float:
    """H1 effect: (ICR_raw - ICR_calibre) / ICR_raw."""
    return (baseline - treated) / baseline if baseline else float("nan")


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("annotation vectors must be non-empty and equal length")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def bootstrap_ci(stat: Callable[[list[int]], float], n: int, *, b: int = 2000,
                 level: float = 0.95, seed: int = 20261108) -> tuple[float, float]:
    """Percentile bootstrap over claim indices (resample claims, not prompts, in the pilot)."""
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        v = stat([rng.randrange(n) for _ in range(n)])
        if not math.isnan(v):
            vals.append(v)
    vals.sort()
    lo = vals[int((1 - level) / 2 * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 + level) / 2 * len(vals)))]
    return lo, hi
