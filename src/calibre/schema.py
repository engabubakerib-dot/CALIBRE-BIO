"""Core data types shared by every CALIBRE layer.

A *claim* is the atomic unit of evaluation: one biological assertion extracted
from an LLM output (or written by an annotator for the gold bank). Every layer
returns a ``LayerResult`` per claim; the triage layer (L5) aggregates them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator


class Domain(str, Enum):
    AMR = "amr"
    MOLECULAR = "molecular"
    PROTEIN = "protein"      # expansion domain (after month 6)
    VARIANT = "variant"      # expansion domain (after month 6)


class GoldLabel(str, Enum):
    VALID = "valid"                    # consistent with curated evidence
    INVALID = "invalid"                # contradicts evidence / physically impossible / fabricated
    NOVEL_PLAUSIBLE = "novel_plausible"  # not in curated DBs, but no constraint violated
    UNRESOLVABLE = "unresolvable"      # annotators cannot decide; excluded from primary analysis


class Verdict(str, Enum):
    PASS = "pass"        # layer found positive support / no violation
    FAIL = "fail"        # layer found a hard violation
    UNKNOWN = "unknown"  # layer could not decide (missing data, offline, out of scope)
    SKIP = "skip"        # layer not applicable to this claim


@dataclass
class Claim:
    claim_id: str
    domain: str
    claim_type: str
    text: str
    entities: dict[str, Any] = field(default_factory=dict)
    gold_label: str | None = None
    hallucination_class: str | None = None
    difficulty: str | None = None
    source: str | None = None
    label_status: str = "draft_unverified"
    notes: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayerResult:
    layer: str
    claim_id: str
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


def read_claims(path: str | Path) -> list[Claim]:
    return [Claim.from_dict(d) for d in _iter_jsonl(path)]


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: invalid JSON ({exc})") from exc
