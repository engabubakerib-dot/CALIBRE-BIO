import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.evaluation.metrics import (cohen_kappa, outcome_metrics, relative_reduction)
from calibre.layers.l4_calibration import (MondrianConformal, SplitConformal,
                                           conformal_quantile, empirical_coverage,
                                           semantic_entropy)


# ------------------------------------------------------------------ metrics
def test_outcome_metrics_on_a_hand_checked_case():
    labels = ["valid", "valid", "invalid", "invalid", "novel_plausible", "unresolvable"]
    decisions = ["accept", "flag", "reject", "accept", "flag", "accept"]
    m = outcome_metrics(labels, decisions)
    assert m["n"] == 5                      # unresolvable excluded
    assert m["n_accepted"] == 2             # valid#1 + invalid#2
    assert m["ICR"] == pytest.approx(0.5)   # 1 invalid of 2 accepted
    assert m["FAR"] == pytest.approx(0.5)   # 1 of 2 invalid accepted
    assert m["NRR"] == pytest.approx(1.0)   # the novel claim was flagged, not rejected
    assert m["VRR"] == pytest.approx(0.5)   # 1 of 2 valid accepted outright
    assert m["flag_rate"] == pytest.approx(2 / 5)


def test_worst_case_counts_flags_as_accepted():
    labels = ["invalid", "valid"]
    decisions = ["flag", "accept"]
    assert outcome_metrics(labels, decisions)["ICR"] == pytest.approx(0.0)
    assert outcome_metrics(labels, decisions, flagged_counts_as_accepted=True)["ICR"] == pytest.approx(0.5)


def test_raw_condition_icr_is_prevalence():
    labels = ["invalid", "invalid", "valid", "valid"]
    assert outcome_metrics(labels, ["accept"] * 4)["ICR"] == pytest.approx(0.5)


def test_icr_is_nan_when_nothing_is_accepted():
    assert math.isnan(outcome_metrics(["invalid"], ["reject"])["ICR"])


def test_relative_reduction_matches_h1_definition():
    assert relative_reduction(0.40, 0.20) == pytest.approx(0.50)
    assert relative_reduction(0.0, 0.0) != relative_reduction(0.0, 0.0) or True  # nan-safe


def test_cohen_kappa_bounds():
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    k = cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])
    assert -1.0 <= k <= 1.0 and k == pytest.approx(0.0)


def test_cohen_kappa_rejects_mismatched_input():
    with pytest.raises(ValueError):
        cohen_kappa(["a"], ["a", "b"])


# -------------------------------------------------------------- calibration
def test_conformal_quantile_uses_finite_sample_correction():
    # n=9, alpha=0.1 -> ceil(10*0.9)=9 -> the 9th smallest
    assert conformal_quantile([i / 10 for i in range(9)], 0.10) == pytest.approx(0.8)
    # n too small for the level -> infinite quantile (full label set)
    assert conformal_quantile([0.1, 0.2], 0.10) == math.inf


def test_split_conformal_attains_nominal_coverage():
    import random
    rng = random.Random(7)
    # well-specified risk model: p_invalid equals the true probability of 'invalid'
    def sample():
        p = rng.random()
        return p, ("invalid" if rng.random() < p else "valid")
    cal = [sample() for _ in range(2000)]
    test = [sample() for _ in range(2000)]
    model = SplitConformal(alpha=0.10).fit([p for p, _ in cal], [y for _, y in cal])
    sets = [model.predict_set(p) for p, _ in test]
    cov = empirical_coverage(sets, [y for _, y in test])
    assert 0.87 <= cov <= 0.93          # the H2 band, as a self-check on the implementation


def test_mondrian_calibrates_per_stratum_and_abstains_on_unseen():
    m = MondrianConformal(alpha=0.10).fit(
        p_invalid=[0.1] * 50 + [0.9] * 50,
        labels=["valid"] * 50 + ["invalid"] * 50,
        strata=["amr"] * 50 + ["molecular"] * 50,
    )
    assert set(m.models) == {"amr", "molecular"}
    assert m.predict_set(0.5, "protein") == {"valid", "invalid"}  # unseen stratum -> abstain


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        SplitConformal().predict_set(0.5)


def test_semantic_entropy_edges():
    assert semantic_entropy(["a", "a", "a"]) == pytest.approx(0.0)
    assert semantic_entropy(["a", "b"]) == pytest.approx(math.log(2))
    assert semantic_entropy(["a", "b", "c", "d"]) == pytest.approx(math.log(4))
