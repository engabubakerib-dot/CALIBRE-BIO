"""L3 — Evidence layer (pilot slice): does curated evidence support the asserted relation?

Pilot scope: AMR gene -> drug class and gene -> resistance mechanism, checked
against the pinned CARD release. Every result records the database release
(``evidence_version``) so that a verdict can always be traced to the exact
evidence snapshot (stored under data/evidence_versions/).

Absence from CARD is *not* evidence of falsity: an unlisted relation is
UNKNOWN (possible novelty), only an explicit contradiction is FAIL.
"""
from __future__ import annotations

from ..amr_reference import AMRIndex, norm_class, norm_mechanism
from ..schema import Claim, LayerResult, Verdict

LAYER = "L3"


class EvidenceLayer:
    def __init__(self, amr_index: AMRIndex | None = None):
        self.amr = amr_index

    def check(self, claim: Claim) -> LayerResult:
        e = claim.entities or {}
        if claim.domain != "amr" or self.amr is None or not e.get("gene"):
            return LayerResult(LAYER, claim.claim_id, Verdict.SKIP, ["NOT_IN_L3_PILOT_SCOPE"])
        version = {"evidence_version": f"CARD:{self.amr.release}"}
        gene = self.amr.lookup(e["gene"])
        if gene is None:
            return LayerResult(LAYER, claim.claim_id, Verdict.UNKNOWN, ["GENE_NOT_IN_EVIDENCE"], version)

        verdicts, reasons = [], []
        for cls in _as_list(e.get("drug_class")) + _as_list(e.get("drug")):
            if gene.covers_class(cls):
                verdicts.append(Verdict.PASS)
                reasons.append(f"DRUG_CLASS_SUPPORTED:{cls}")
            else:
                # CARD lists the gene but not this class. With a complete curated index this
                # is a contradiction; with the seed index it is only "not supported".
                verdicts.append(Verdict.FAIL if self.amr.complete else Verdict.UNKNOWN)
                reasons.append(f"DRUG_CLASS_NOT_SUPPORTED:{cls}:card={sorted(gene.drug_classes)}")

        if e.get("mechanism"):
            m = norm_mechanism(e["mechanism"])
            if m is None:
                verdicts.append(Verdict.UNKNOWN)
                reasons.append(f"MECHANISM_UNPARSED:{e['mechanism']}")
            elif m in gene.mechanisms:
                verdicts.append(Verdict.PASS)
                reasons.append(f"MECHANISM_SUPPORTED:{m}")
            else:
                # mechanism categories are mutually exclusive for a given CARD model
                verdicts.append(Verdict.FAIL)
                reasons.append(f"MECHANISM_CONTRADICTED:claimed={m}:card={sorted(gene.mechanisms)}")

        if not verdicts:
            return LayerResult(LAYER, claim.claim_id, Verdict.SKIP, ["NO_RELATION_ASSERTED"], version)
        if Verdict.FAIL in verdicts:
            v = Verdict.FAIL
        elif Verdict.UNKNOWN in verdicts:
            v = Verdict.UNKNOWN
        else:
            v = Verdict.PASS
        return LayerResult(LAYER, claim.claim_id, v, reasons, version)


def _as_list(x) -> list[str]:
    if not x:
        return []
    return [x] if isinstance(x, str) else list(x)
