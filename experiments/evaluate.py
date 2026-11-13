"""Step 4 — Compare the raw condition with a CALIBRE condition on gold-labelled claims.

    python experiments/evaluate.py experiments/results/<file>.jsonl

Prints ICR / FAR / NRR / VRR / flag rate for: raw (accept all), CALIBRE (flag = not accepted),
CALIBRE worst case (flag = accepted), plus 95% bootstrap CI for ICR and the H1 relative reduction.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.evaluation.metrics import bootstrap_ci, outcome_metrics, relative_reduction  # noqa: E402
from calibre.schema import _iter_jsonl  # noqa: E402


def fmt(m: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = [r for r in _iter_jsonl(args.results) if r.get("gold_label")]
    if not rows:
        sys.exit("no gold-labelled rows: annotate claims before evaluating")
    y = [r["gold_label"] for r in rows]
    d = [r["decision"] for r in rows]

    raw = outcome_metrics(y, ["accept"] * len(y))
    cal = outcome_metrics(y, d)
    worst = outcome_metrics(y, d, flagged_counts_as_accepted=True)
    n = len(rows)
    ci_raw = bootstrap_ci(lambda ix: outcome_metrics([y[i] for i in ix], ["accept"] * len(ix))["ICR"], n)
    ci_cal = bootstrap_ci(lambda ix: outcome_metrics([y[i] for i in ix], [d[i] for i in ix])["ICR"], n)

    report = {
        "raw": raw, "calibre": cal, "calibre_worst_case": worst,
        "ICR_CI95": {"raw": ci_raw, "calibre": ci_cal},
        "H1_relative_ICR_reduction": relative_reduction(raw["ICR"], cal["ICR"]),
        "H1_threshold": 0.50,
    }
    by_class = defaultdict(Counter)
    for r in rows:
        if r["gold_label"] == "invalid":
            by_class[r.get("hallucination_class") or "unclassified"][r["decision"]] += 1
    report["invalid_by_hallucination_class"] = {k: dict(v) for k, v in by_class.items()}

    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"n = {n} gold-labelled claims  ({dict(Counter(y))})\n")
    print("raw                 ", fmt(raw))
    print("CALIBRE             ", fmt(cal))
    print("CALIBRE (flag=acc.) ", fmt(worst))
    print(f"\nICR 95% CI  raw {ci_raw[0]:.3f}-{ci_raw[1]:.3f}   CALIBRE {ci_cal[0]:.3f}-{ci_cal[1]:.3f}")
    print(f"H1 relative ICR reduction = {report['H1_relative_ICR_reduction']:.1%}  (threshold >= 50%)")
    print("\ninvalid claims by hallucination class -> decisions:")
    for k, v in sorted(report["invalid_by_hallucination_class"].items()):
        print(f"  {k:<32} {dict(v)}")
    if n < 100:
        print("\n[pilot] n < 100: estimates are for pipeline debugging only, not hypothesis tests.")


if __name__ == "__main__":
    main()
