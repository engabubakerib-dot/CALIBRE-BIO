"""Runs the enabled layers over claims and applies triage.

``layers`` selects which layers are active, which is how ablation conditions are
expressed (e.g. ``("L1",)``, ``("L1", "L2")``, ``("L1", "L2", "L3")``).
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Iterable

from .amr_reference import AMRIndex
from .layers import EvidenceLayer, OntologyLayer, PhysicsLayer, triage
from .schema import Claim

ROOT = Path(__file__).resolve().parents[2]


def load_db_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else ROOT / "configs" / "databases.toml"
    with p.open("rb") as fh:
        return tomllib.load(fh)


def load_amr_index(cfg: dict | None = None) -> AMRIndex:
    cfg = cfg or load_db_config()
    card = cfg["card"]
    path = Path(card["aro_index"])
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        seed = cfg["card_seed"]
        return AMRIndex.from_tsv(ROOT / seed["aro_index"], release=seed["release"], complete=False)
    return AMRIndex.from_tsv(path, release=card["release"], complete=True)


class Pipeline:
    def __init__(self, layers: Iterable[str] = ("L1", "L2", "L3"), amr_index: AMRIndex | None = None,
                 **l1_kwargs):
        self.enabled = tuple(layers)
        amr = amr_index if amr_index is not None else load_amr_index()
        self.amr = amr
        self._layers = {
            "L1": OntologyLayer(amr, **l1_kwargs),
            "L2": PhysicsLayer(),
            "L3": EvidenceLayer(amr),
        }

    def run(self, claim: Claim) -> dict:
        results = [self._layers[name].check(claim) for name in self.enabled]
        decision, why = triage(results)
        return {
            "claim_id": claim.claim_id,
            "domain": claim.domain,
            "claim_type": claim.claim_type,
            "gold_label": claim.gold_label,
            "hallucination_class": claim.hallucination_class,
            "layers": [r.to_dict() for r in results],
            "decision": decision.value,
            "decision_reasons": why,
            "enabled_layers": list(self.enabled),
            "evidence_index": f"CARD:{self.amr.release}" + ("" if self.amr.complete else " (SEED, not citable)"),
        }
