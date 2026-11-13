"""Step 1 — Query a pinned model with pilot prompts and store structured claims.

    python experiments/generate_claims.py --model llama8b --prompts data/prompts/pilot_prompts.jsonl

Output: data/generated/<model>/<UTC date>.jsonl — one Claim per line, gold_label = null,
ready for double annotation (experiments/export_for_annotation.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.llm import LLM  # noqa: E402
from calibre.schema import Claim, _iter_jsonl, write_jsonl  # noqa: E402

SYSTEM = {
    "amr": (
        "You are an expert in antimicrobial resistance. Answer the question, then output ONLY a JSON "
        "array of atomic claims. Each claim: {\"text\": str, \"gene\": str, \"organism\": str|null, "
        "\"drug_class\": str|null, \"mechanism\": str|null, \"pmids\": [str], \"dois\": [str]}. "
        "Cite PubMed IDs or DOIs if you know them."
    ),
    "molecular": (
        "You are a medicinal chemist. Answer the question, then output ONLY a JSON array of atomic "
        "claims. Each claim: {\"text\": str, \"name\": str|null, \"smiles\": str, \"formula\": str|null, "
        "\"mw\": number|null, \"pmids\": [str], \"dois\": [str]}."
    ),
}


def parse_claims(raw: str) -> list[dict]:
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("text")]


def to_claim(d: dict, prompt: dict, model_key: str, idx: int) -> Claim:
    ents = {k: v for k, v in d.items() if k != "text" and v not in (None, "", [])}
    return Claim(
        claim_id=f"{prompt['prompt_id']}-{model_key}-{idx:02d}",
        domain=prompt["domain"],
        claim_type=prompt.get("claim_type", "unspecified"),
        text=d["text"],
        entities=ents,
        source=f"llm:{model_key}",
        label_status="unlabelled",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="key in configs/models.toml")
    ap.add_argument("--prompts", default=str(ROOT / "data/prompts/pilot_prompts.jsonl"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    llm = LLM(args.model)
    claims, failures = [], 0
    for prompt in _iter_jsonl(args.prompts):
        raw = llm.chat(SYSTEM[prompt["domain"]], prompt["prompt"], prompt_id=prompt["prompt_id"])
        parsed = parse_claims(raw)
        if not parsed:
            failures += 1
            print(f"[warn] {prompt['prompt_id']}: no parsable claims", file=sys.stderr)
        claims += [to_claim(d, prompt, args.model, i) for i, d in enumerate(parsed)]

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.out or ROOT / f"data/generated/{args.model}/{day}.jsonl")
    write_jsonl(out, (c.to_dict() for c in claims))
    print(f"{len(claims)} claims -> {out}  ({failures} prompts unparsable)")


if __name__ == "__main__":
    main()
