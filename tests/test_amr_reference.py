import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.amr_reference import AMRIndex, family_key, name_keys, norm_class, norm_mechanism

SEED = ROOT / "data/reference/amr_seed_index.tsv"


@pytest.fixture(scope="module")
def idx() -> AMRIndex:
    return AMRIndex.from_tsv(SEED, release="seed-test", complete=False)


def test_seed_index_loads(idx):
    assert len(idx) == 15
    assert idx.complete is False


@pytest.mark.parametrize("query", ["KPC-2", "blaKPC-2", "kpc-2", "  KPC-2 "])
def test_bla_prefix_and_case_are_equivalent(idx, query):
    g = idx.lookup(query)
    assert g is not None and g.aro_accession == "SEED-01"


def test_parenthesised_names_normalise(idx):
    assert idx.lookup("tetM") is idx.lookup("tet(M)")


def test_alias_lookup(idx):
    assert idx.lookup("erm(B)") is idx.lookup("ErmB")


def test_absent_gene_returns_none(idx):
    assert idx.lookup("zzsyntheticabsent-1") is None


def test_family_known_vs_allele_unknown(idx):
    # the KPC family is in the index; this specific allele number is not
    assert idx.lookup("KPC-99") is None
    assert idx.family_known("KPC-99") is True
    assert idx.family_known("zzsyntheticabsent-1") is False


def test_name_keys_and_family_key():
    assert "kpc-2" in name_keys("blaKPC-2")
    assert family_key("CTX-M-15") == "ctx-m"
    assert family_key("tet(M)") == "tetm"


@pytest.mark.parametrize("drug,expected", [
    ("colistin", "peptide"),
    ("meropenem", "carbapenem"),
    ("Ceftazidime", "cephalosporin"),
    ("tetracycline antibiotic", "tetracycline"),
    ("penicillins", "penam"),
])
def test_drug_to_class_mapping(drug, expected):
    assert norm_class(drug) == expected


def test_beta_lactam_umbrella_matches_any_sub_class(idx):
    kpc = idx.lookup("KPC-2")
    assert kpc.covers_class("beta-lactam") is True
    assert kpc.covers_class("carbapenem") is True
    assert kpc.covers_class("tetracycline") is False


def test_mecA_covers_methicillin_via_penam(idx):
    assert idx.lookup("mecA").covers_class("methicillin") is True


@pytest.mark.parametrize("text,expected", [
    ("beta-lactamase hydrolysis of the ring", "antibiotic inactivation"),
    ("efflux pump", "antibiotic efflux"),
    ("ribosomal protection protein", "antibiotic target protection"),
    ("phosphoethanolamine transferase modifies lipid A", "antibiotic target alteration"),
    ("alternative PBP2a bypasses the target", "antibiotic target replacement"),
    ("antibiotic efflux", "antibiotic efflux"),
])
def test_mechanism_normalisation(text, expected):
    assert norm_mechanism(text) == expected


def test_unparsable_mechanism_is_none():
    assert norm_mechanism("it simply stops working somehow") is None
