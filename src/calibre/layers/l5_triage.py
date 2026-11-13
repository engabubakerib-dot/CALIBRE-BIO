"""L5 — Novelty-aware triage: accept / flag-for-human-review / reject.

Pilot rule (deterministic, used until L4 risk scores exist):
  * any layer FAIL                    -> reject
  * every applicable layer PASS       -> accept
  * otherwise (some UNKNOWN)          -> flag   (candidate novelty: no constraint violated,
                                                 but not confirmed by curated evidence)

The full L5 (month 5-6) replaces the "flag" bucket split with the conformal
label set from L4 plus an embedding distance to training-like patterns, so that
novel-but-valid claims are routed to review instead of being filtered out —
the contrast with the distribution-based filter tested in H3.
"""
from __future__ import annotations

from enum import Enum

from ..schema import LayerResult, Verdict


class Decision(str, Enum):
    ACCEPT = "accept"
    FLAG = "flag"
    REJECT = "reject"


def triage(results: list[LayerResult]) -> tuple[Decision, list[str]]:
    applicable = [r for r in results if r.verdict != Verdict.SKIP]
    if any(r.verdict == Verdict.FAIL for r in applicable):
        return Decision.REJECT, [f"{r.layer}:FAIL" for r in applicable if r.verdict == Verdict.FAIL]
    if applicable and all(r.verdict == Verdict.PASS for r in applicable):
        return Decision.ACCEPT, ["ALL_LAYERS_PASS"]
    if not applicable:
        return Decision.FLAG, ["NO_APPLICABLE_LAYER"]
    return Decision.FLAG, [f"{r.layer}:UNKNOWN" for r in applicable if r.verdict == Verdict.UNKNOWN]
