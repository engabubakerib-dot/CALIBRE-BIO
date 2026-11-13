"""Step 3 — Run CALIBRE layers over (annotated) claims.

    python experiments/run_layers.py --claims data/gold_claims/pilot_amr_seed.jsonl
    python experiments/run_layers.py --claims ... --layers L1          # ablation
    CALIBRE_OFFLINE=1 python experiments/run_layers.py --claims ...    # no network

Output: experiments/results/<claims-stem>__<layers>.jsonl
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.pipeline import Pipeline  # noqa: E402
from calibre.schema import read_claims, write_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", nargs="+", required=True)
    ap.add_argument("--layers", default="L1,L2,L3")
    ap.add_argument("--allele-miss-policy", choices=["flag", "reject"], default="flag")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    layers = tuple(x.strip() for x in args.layers.split(",") if x.strip())
    pipe = Pipeline(layers, allele_miss_policy=args.allele_miss_policy)
    print(f"evidence index: CARD {pipe.amr.release} ({len(pipe.amr)} genes, complete={pipe.amr.complete})")

    rows = []
    for path in args.claims:
        for c in read_claims(path):
            rows.append(pipe.run(c))

    stem = "+".join(Path(p).stem for p in args.claims)
    out = Path(args.out or ROOT / f"experiments/results/{stem}__{'-'.join(layers)}.jsonl")
    write_jsonl(out, rows)
    print(dict(Counter(r["decision"] for r in rows)), "->", out)


if __name__ == "__main__":
    main()
