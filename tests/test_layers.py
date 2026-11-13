"""Layer behaviour tests. All network resolvers are stubbed: no live calls in CI."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.amr_reference import AMRIndex
from calibre.layers.l1_ontology import OntologyLayer
from calibre.layers.l2_physics import HAVE_RDKIT, PhysicsLayer, check_smiles
from calibre.layers.l3_evidence import EvidenceLayer
from calibre.layers.l5_triage import Decision, triage
from calibre.schema import Claim, LayerResult, Verdict

SEED = ROOT / "data/reference/amr_seed_index.tsv"


def index(complete: bool) -> AMRIndex:
    return AMRIndex.from_tsv(SEED, release="seed-test", complete=complete)


class StubNCBI:
    """Deterministic stand-in: only ids/symbols registered here 'exist'."""

    def __init__(self, pmids=(), genes=(), undecidable=False):
        self.pmids, self.genes, self.undecidable = set(pmids), set(genes), undecidable

    def pmid_exists(self, pmid):
        return None if self.undecidable else pmid in self.pmids

    def gene_hits(self, symbol, organism=None):
        return None if self.undecidable else (1 if symbol in self.genes else 0)


class StubUniProt:
    def __init__(self, accs=()):
        self.accs = set(accs)

    def accession_exists(self, acc):
        return acc.upper() in self.accs


class StubDOI:
    def __init__(self, dois=()):
        self.dois = {d.lower() for d in dois}

    def doi_exists(self, doi):
        return doi.lower().lstrip("https://doi.org/") in self.dois or doi.lower() in self.dois


def claim(**kw) -> Claim:
    base = dict(claim_id="C1", domain="amr", claim_type="gene_existence", text="t")
    base.update(kw)
    return Claim(**base)


# --------------------------------------------------------------------- L1
def l1(complete=True, **stubs) -> OntologyLayer:
    kw = dict(ncbi=StubNCBI(), uniprot=StubUniProt(), doi=StubDOI())
    kw.update(stubs)
    return OntologyLayer(index(complete), **kw)


def test_l1_known_gene_passes():
    r = l1().check(claim(entities={"gene": "mecA"}))
    assert r.verdict is Verdict.PASS
    assert any("GENE_IN_CARD" in x for x in r.reasons)


def test_l1_absent_gene_fails_with_complete_index():
    r = l1().check(claim(entities={"gene": "zzsyntheticabsent-1"}))
    assert r.verdict is Verdict.FAIL
    assert any("GENE_NOT_FOUND" in x for x in r.reasons)


def test_l1_absent_gene_is_unknown_with_seed_index():
    """A 15-gene seed index must never produce a FAIL on absence."""
    r = l1(complete=False).check(claim(entities={"gene": "zzsyntheticabsent-1"}))
    assert r.verdict is Verdict.UNKNOWN


def test_l1_unknown_allele_of_known_family_is_flagged_not_rejected():
    r = l1().check(claim(entities={"gene": "KPC-99"}))
    assert r.verdict is Verdict.UNKNOWN
    assert any("ALLELE_NOT_FOUND_FAMILY_EXISTS" in x for x in r.reasons)


def test_l1_reject_policy_is_opt_in():
    layer = OntologyLayer(index(True), ncbi=StubNCBI(), uniprot=StubUniProt(), doi=StubDOI(),
                          allele_miss_policy="reject")
    assert layer.check(claim(entities={"gene": "KPC-99"})).verdict is Verdict.FAIL


def test_l1_bad_policy_rejected():
    with pytest.raises(ValueError):
        OntologyLayer(index(True), allele_miss_policy="nonsense")


def test_l1_gene_found_via_ncbi_when_not_in_card():
    r = l1(ncbi=StubNCBI(genes={"gyrA"})).check(claim(entities={"gene": "gyrA"}))
    assert r.verdict is Verdict.PASS
    assert any("GENE_IN_NCBI" in x for x in r.reasons)


def test_l1_offline_resolver_yields_unknown_never_pass():
    r = l1(ncbi=StubNCBI(undecidable=True)).check(claim(entities={"gene": "gyrA"}))
    assert r.verdict is Verdict.UNKNOWN


def test_l1_unresolvable_pmid_fails():
    r = l1(ncbi=StubNCBI(pmids={"11111111"})).check(
        claim(entities={"gene": "mecA", "pmids": ["99999999"]}))
    assert r.verdict is Verdict.FAIL
    assert any("PMID_NOT_FOUND" in x for x in r.reasons)


def test_l1_malformed_identifiers_fail_without_network():
    r = l1().check(claim(entities={"uniprot": ["NOT_AN_ACC"], "dois": ["not-a-doi"]}))
    assert r.verdict is Verdict.FAIL


def test_l1_valid_identifiers_pass():
    r = l1(uniprot=StubUniProt({"P0A0D7"}), doi=StubDOI({"10.1093/bib/bbaf601"})).check(
        claim(entities={"uniprot": ["P0A0D7"], "dois": ["10.1093/bib/bbaf601"]}))
    assert r.verdict is Verdict.PASS


def test_l1_skips_claims_without_entities():
    assert l1().check(claim(entities={})).verdict is Verdict.SKIP


# --------------------------------------------------------------------- L2
@pytest.mark.skipif(not HAVE_RDKIT, reason="RDKit not installed")
@pytest.mark.parametrize("smi", ["CC(=O)Oc1ccccc1C(=O)O", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C", "c1ccccc1"])
def test_l2_valid_smiles_pass(smi):
    v, reasons, details = check_smiles(smi)
    assert v is Verdict.PASS and "VALID_STRUCTURE" in reasons and details["formula"]


@pytest.mark.skipif(not HAVE_RDKIT, reason="RDKit not installed")
@pytest.mark.parametrize("smi,code", [
    ("C(((C", "SMILES_SYNTAX_ERROR"),
    ("c1ccc1", "KEKULIZE_ERROR"),
    ("C(C)(C)(C)(C)C", "VALENCE_ERROR"),
    ("", "EMPTY_SMILES"),
])
def test_l2_impossible_structures_fail(smi, code):
    v, reasons, _ = check_smiles(smi)
    assert v is Verdict.FAIL and any(r.startswith(code) for r in reasons)


@pytest.mark.skipif(not HAVE_RDKIT, reason="RDKit not installed")
def test_l2_formula_mismatch_detected():
    v, reasons, _ = check_smiles("CC(=O)Oc1ccccc1C(=O)O", stated_formula="C9H9O4")
    assert v is Verdict.FAIL and any("FORMULA_MISMATCH" in r for r in reasons)


@pytest.mark.skipif(not HAVE_RDKIT, reason="RDKit not installed")
def test_l2_correct_formula_and_mw_pass():
    v, _, _ = check_smiles("CC(=O)Oc1ccccc1C(=O)O", stated_formula="C9H8O4", stated_mw=180.16)
    assert v is Verdict.PASS


@pytest.mark.skipif(not HAVE_RDKIT, reason="RDKit not installed")
def test_l2_mw_mismatch_detected():
    v, reasons, _ = check_smiles("CC(=O)Oc1ccccc1C(=O)O", stated_mw=512.0)
    assert v is Verdict.FAIL and any("MW_MISMATCH" in r for r in reasons)


@pytest.mark.skipif(HAVE_RDKIT, reason="only meaningful without RDKit")
def test_l2_without_rdkit_is_unknown_not_pass():
    v, reasons, _ = check_smiles("CC(=O)Oc1ccccc1C(=O)O")
    assert v is Verdict.UNKNOWN and "RDKIT_UNAVAILABLE" in reasons


def test_l2_skips_claims_without_smiles():
    r = PhysicsLayer().check(claim(domain="molecular", entities={"name": "x"}))
    assert r.verdict is Verdict.SKIP


# --------------------------------------------------------------------- L3
def test_l3_supported_drug_class_passes():
    r = EvidenceLayer(index(True)).check(
        claim(claim_type="gene_drug_class", entities={"gene": "KPC-2", "drug_class": "carbapenem"}))
    assert r.verdict is Verdict.PASS
    assert r.details["evidence_version"].startswith("CARD:")


def test_l3_contradicted_drug_class_fails_only_with_complete_index():
    c = claim(claim_type="gene_drug_class", entities={"gene": "mcr-1", "drug_class": "carbapenem"})
    assert EvidenceLayer(index(True)).check(c).verdict is Verdict.FAIL
    assert EvidenceLayer(index(False)).check(c).verdict is Verdict.UNKNOWN


def test_l3_contradicted_mechanism_fails():
    r = EvidenceLayer(index(True)).check(
        claim(claim_type="gene_mechanism", entities={"gene": "mcr-1", "mechanism": "efflux pump"}))
    assert r.verdict is Verdict.FAIL
    assert any("MECHANISM_CONTRADICTED" in x for x in r.reasons)


def test_l3_supported_mechanism_passes():
    r = EvidenceLayer(index(True)).check(
        claim(claim_type="gene_mechanism",
              entities={"gene": "tet(M)", "mechanism": "ribosomal protection"}))
    assert r.verdict is Verdict.PASS


def test_l3_gene_absent_from_evidence_is_unknown_not_fail():
    r = EvidenceLayer(index(True)).check(
        claim(entities={"gene": "zzsyntheticabsent-1", "drug_class": "carbapenem"}))
    assert r.verdict is Verdict.UNKNOWN


def test_l3_out_of_scope_domain_skips():
    r = EvidenceLayer(index(True)).check(claim(domain="molecular", entities={"smiles": "C"}))
    assert r.verdict is Verdict.SKIP


# --------------------------------------------------------------------- L5
def res(layer, verdict):
    return LayerResult(layer, "C1", verdict)


def test_triage_rules():
    assert triage([res("L1", Verdict.PASS), res("L3", Verdict.PASS)])[0] is Decision.ACCEPT
    assert triage([res("L1", Verdict.PASS), res("L3", Verdict.FAIL)])[0] is Decision.REJECT
    assert triage([res("L1", Verdict.PASS), res("L3", Verdict.UNKNOWN)])[0] is Decision.FLAG
    assert triage([res("L1", Verdict.SKIP)])[0] is Decision.FLAG
    # a FAIL anywhere dominates an UNKNOWN elsewhere
    assert triage([res("L1", Verdict.UNKNOWN), res("L3", Verdict.FAIL)])[0] is Decision.REJECT
