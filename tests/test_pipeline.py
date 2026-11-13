import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from calibre.amr_reference import AMRIndex
from calibre.pipeline import Pipeline, load_amr_index, load_db_config
from calibre.schema import Claim

SEED = ROOT / "data/reference/amr_seed_index.tsv"


def pipe(layers=("L1", "L2", "L3")) -> Pipeline:
    return Pipeline(layers, amr_index=AMRIndex.from_tsv(SEED, release="seed-test", complete=True),
                    use_ncbi_gene_fallback=False)


def c(**kw) -> Claim:
    base = dict(claim_id="C1", domain="amr", claim_type="gene_drug_class", text="t")
    base.update(kw)
    return Claim(**base)


def test_config_falls_back_to_seed_index_when_card_absent():
    idx = load_amr_index(load_db_config())
    # CARD is not downloaded in a fresh clone, so the seed index must be used and marked incomplete
    assert idx.complete is False and len(idx) == 15


def test_pipeline_accepts_a_supported_claim():
    out = pipe().run(c(entities={"gene": "KPC-2", "drug_class": "carbapenem"}))
    assert out["decision"] == "accept"
    assert out["enabled_layers"] == ["L1", "L2", "L3"]
    assert out["evidence_index"].startswith("CARD:")


def test_pipeline_rejects_a_contradicted_relation():
    out = pipe().run(c(entities={"gene": "mcr-1", "drug_class": "carbapenem"}))
    assert out["decision"] == "reject"
    assert any("L3:FAIL" in r for r in out["decision_reasons"])


def test_pipeline_flags_an_unknown_allele():
    out = pipe().run(c(entities={"gene": "KPC-99", "drug_class": "carbapenem"}))
    assert out["decision"] == "flag"


def test_ablation_changes_the_enabled_layers_only():
    claim = c(entities={"gene": "mcr-1", "drug_class": "carbapenem"})
    l1_only = pipe(("L1",)).run(claim)
    full = pipe().run(claim)
    assert l1_only["decision"] == "accept"      # L1 alone cannot see the relation error
    assert full["decision"] == "reject"
    assert [r["layer"] for r in l1_only["layers"]] == ["L1"]


def test_result_rows_are_json_serialisable():
    import json
    json.dumps(pipe().run(c(entities={"gene": "mecA", "drug_class": "methicillin"})))


def test_template_gold_file_parses():
    from calibre.schema import read_claims
    claims = read_claims(ROOT / "data/gold_claims/TEMPLATE.jsonl")
    assert len(claims) == 2 and all(x.gold_label is None for x in claims)
