"""L4 — Calibration layer: split conformal prediction over claim-level risk scores.

What is implemented now
-----------------------
* ``SplitConformal`` / ``MondrianConformal``: distribution-free coverage
  guarantee P(y in C(x)) >= 1 - alpha under exchangeability. Mondrian
  ("segmented") conformal calibrates separately per stratum (e.g. per domain or
  claim type), which is what H2 tests.
* ``empirical_coverage`` for the H2 check (target 0.90 +/- 0.03).

What comes next (month 3-5)
---------------------------
* Risk score = f(semantic entropy over k sampled answers [Farquhar et al.,
  Nature 2024], L1-L3 verdict features). Semantic entropy needs k samples per
  prompt and an NLI model for meaning-clustering; ``semantic_entropy`` below
  implements the entropy over given clusters so the sampler/NLI can be plugged in.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Hashable, Sequence

LABELS = ("valid", "invalid")


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Finite-sample corrected (1-alpha) quantile: the ceil((n+1)(1-alpha))-th smallest score."""
    n = len(scores)
    if n == 0:
        raise ValueError("empty calibration set")
    k = math.ceil((n + 1) * (1 - alpha))
    if k > n:
        return math.inf  # too few calibration points for this alpha: predict the full label set
    return sorted(scores)[k - 1]


class SplitConformal:
    """Binary label-set predictor. Input: p_invalid in [0,1] from any risk model."""

    def __init__(self, alpha: float = 0.10):
        self.alpha = alpha
        self.qhat: float | None = None

    @staticmethod
    def score(p_invalid: float, label: str) -> float:
        # nonconformity = 1 - model probability of the true label
        return 1 - (p_invalid if label == "invalid" else 1 - p_invalid)

    def fit(self, p_invalid: Sequence[float], labels: Sequence[str]) -> "SplitConformal":
        self.qhat = conformal_quantile([self.score(p, y) for p, y in zip(p_invalid, labels)], self.alpha)
        return self

    def predict_set(self, p_invalid: float) -> set[str]:
        if self.qhat is None:
            raise RuntimeError("call fit() first")
        return {y for y in LABELS if self.score(p_invalid, y) <= self.qhat}


class MondrianConformal:
    """Per-stratum calibration (stratum = domain, claim type, ...)."""

    def __init__(self, alpha: float = 0.10):
        self.alpha = alpha
        self.models: dict[Hashable, SplitConformal] = {}

    def fit(self, p_invalid, labels, strata) -> "MondrianConformal":
        groups: dict[Hashable, tuple[list, list]] = defaultdict(lambda: ([], []))
        for p, y, s in zip(p_invalid, labels, strata):
            groups[s][0].append(p)
            groups[s][1].append(y)
        self.models = {s: SplitConformal(self.alpha).fit(ps, ys) for s, (ps, ys) in groups.items()}
        return self

    def predict_set(self, p_invalid: float, stratum: Hashable) -> set[str]:
        if stratum not in self.models:
            return set(LABELS)  # unseen stratum: abstain
        return self.models[stratum].predict_set(p_invalid)


def empirical_coverage(sets: Sequence[set[str]], labels: Sequence[str]) -> float:
    return sum(y in s for s, y in zip(sets, labels)) / len(labels)


def semantic_entropy(cluster_ids: Sequence[Hashable]) -> float:
    """Discrete semantic entropy over meaning clusters of k sampled answers (natural log)."""
    n = len(cluster_ids)
    counts: dict[Hashable, int] = defaultdict(int)
    for c in cluster_ids:
        counts[c] += 1
    return -sum((m / n) * math.log(m / n) for m in counts.values())
