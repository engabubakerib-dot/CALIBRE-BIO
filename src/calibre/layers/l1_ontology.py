"""L1 — Ontological layer: do the named entities and references exist?

Checks (each produces reason codes; see docs/claim_taxonomy.md §3):

* AMR gene names against the local CARD index (exact allele -> family -> absent),
  with NCBI Gene as a secondary lookup for non-CARD genes.
* UniProt accessions (format + REST lookup).
* PMIDs (NCBI esummary) and DOIs (doi.org handle API) -> fabricated-reference detection.

L1 never judges *what* a claim asserts about an entity (that is L3); it only
asks whether the entities and citations are real.
"""
from __future__ import annotations

from ..amr_reference import AMRIndex
from ..resolvers import DOI, NCBI, UniProt
from ..schema import Claim, LayerResult, Verdict

LAYER = "L1"


class OntologyLayer:
    def __init__(self, amr_index: AMRIndex | None = None, *, ncbi: NCBI | None = None,
                 uniprot: UniProt | None = None, doi: DOI | None = None,
                 use_ncbi_gene_fallback: bool = True, allele_miss_policy: str = "flag"):
        if allele_miss_policy not in ("flag", "reject"):
            raise ValueError("allele_miss_policy must be 'flag' or 'reject'")
        self.allele_miss_policy = allele_miss_policy
        self.amr = amr_index
        self.ncbi = ncbi or NCBI()
        self.uniprot = uniprot or UniProt()
        self.doi = doi or DOI()
        self.use_ncbi_gene_fallback = use_ncbi_gene_fallback

    # ------------------------------------------------------------------ genes
    def _check_gene(self, gene: str, organism: str | None) -> tuple[Verdict, str, dict]:
        family = False
        if self.amr is not None:
            hit = self.amr.lookup(gene)
            if hit:
                return Verdict.PASS, "GENE_IN_CARD", {"matched": hit.name, "aro": hit.aro_accession}
            family = self.amr.family_known(gene)
        if family:
            # Known family, unknown allele number: either a fabricated allele or one
            # assigned after the pinned CARD release. Hard-rejecting would destroy
            # genuinely new alleles (H3), so the default policy routes it to review.
            v = Verdict.FAIL if self.allele_miss_policy == "reject" else Verdict.UNKNOWN
            return v, "ALLELE_NOT_FOUND_FAMILY_EXISTS", {}
        complete = self.amr is not None and self.amr.complete
        if self.use_ncbi_gene_fallback:
            n = self.ncbi.gene_hits(gene, organism)
            if n is None:
                # the secondary lookup could not answer: never conclude absence from silence
                return Verdict.UNKNOWN, "GENE_UNRESOLVED", {"ncbi": "undecidable"}
            if n > 0:
                return Verdict.PASS, "GENE_IN_NCBI", {"ncbi_hits": n}
            if complete:
                return Verdict.FAIL, "GENE_NOT_FOUND", {"ncbi_hits": 0}
        elif complete:
            return Verdict.FAIL, "GENE_NOT_FOUND", {}
        return Verdict.UNKNOWN, "GENE_UNRESOLVED", {}

    # ------------------------------------------------------------------ main
    def check(self, claim: Claim) -> LayerResult:
        e = claim.entities or {}
        reasons: list[str] = []
        details: dict = {}
        verdicts: list[Verdict] = []

        genes = e.get("genes") or ([e["gene"]] if e.get("gene") else [])
        for g in genes:
            v, code, d = self._check_gene(g, e.get("organism"))
            verdicts.append(v)
            reasons.append(f"{code}:{g}")
            details[f"gene:{g}"] = d

        for acc in e.get("uniprot", []) or []:
            ok = self.uniprot.accession_exists(acc)
            verdicts.append(_tri(ok))
            reasons.append(f"{_code(ok, 'UNIPROT')}:{acc}")

        for pmid in e.get("pmids", []) or []:
            ok = self.ncbi.pmid_exists(str(pmid))
            verdicts.append(_tri(ok))
            reasons.append(f"{_code(ok, 'PMID')}:{pmid}")

        for doi in e.get("dois", []) or []:
            ok = self.doi.doi_exists(doi)
            verdicts.append(_tri(ok))
            reasons.append(f"{_code(ok, 'DOI')}:{doi}")

        if not verdicts:
            return LayerResult(LAYER, claim.claim_id, Verdict.SKIP, ["NO_L1_ENTITIES"])
        return LayerResult(LAYER, claim.claim_id, combine(verdicts), reasons, details)


def combine(verdicts: list[Verdict]) -> Verdict:
    """Any hard violation fails the layer; otherwise any undecided item -> UNKNOWN."""
    if Verdict.FAIL in verdicts:
        return Verdict.FAIL
    if Verdict.UNKNOWN in verdicts:
        return Verdict.UNKNOWN
    if all(v == Verdict.SKIP for v in verdicts):
        return Verdict.SKIP
    return Verdict.PASS


def _tri(ok: bool | None) -> Verdict:
    return {True: Verdict.PASS, False: Verdict.FAIL, None: Verdict.UNKNOWN}[ok]


def _code(ok: bool | None, what: str) -> str:
    return {True: f"{what}_FOUND", False: f"{what}_NOT_FOUND", None: f"{what}_UNRESOLVED"}[ok]
