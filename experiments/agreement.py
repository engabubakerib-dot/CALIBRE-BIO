"""Step 2b — Inter-annotator agreement (Cohen's kappa) between two annotation files.

    python experiments/agreement.py annot_A.jsonl annot_B.jsonl

Each file: JSONL with at least {"claim_id", "gold_label"}; optional "hallucination_class".
Reports kappa for the label and for the hallucination class, and lists disagreements
for adjudication. Pre-registered target: kappa >= 0.70 on gold_label before scaling up.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.evaluation.metrics import cohen_kappa  # noqa: E402
from calibre.schema import _iter_jsonl  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a = {r["claim_id"]: r for r in _iter_jsonl(sys.argv[1])}
    b = {r["claim_id"]: r for r in _iter_jsonl(sys.argv[2])}
    ids = sorted(set(a) & set(b))
    if not ids:
        sys.exit("no overlapping claim_ids")
    for field in ("gold_label", "hallucination_class"):
        xa = [str(a[i].get(field)) for i in ids]
        xb = [str(b[i].get(field)) for i in ids]
        print(f"{field:<20} kappa = {cohen_kappa(xa, xb):.3f}   (n = {len(ids)})")
    dis = [i for i in ids if a[i].get("gold_label") != b[i].get("gold_label")]
    print(f"\n{len(dis)} label disagreements to adjudicate:")
    for i in dis:
        print(f"  {i}: A={a[i].get('gold_label')}  B={b[i].get('gold_label')}")


if __name__ == "__main__":
    main()
