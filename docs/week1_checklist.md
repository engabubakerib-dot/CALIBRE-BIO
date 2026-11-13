# Week 1 — what is already done and what is yours

Phase 0 of the plan, with the state of each item as of 2026-11-08.

## Done in this repository

- [x] Repository structure, packaging (`pyproject.toml`), `.gitignore`, `.env.example`
- [x] `Claim` / `LayerResult` / `Verdict` contract shared by all layers (`src/calibre/schema.py`)
- [x] Append-only call log with timestamps and version strings (`src/calibre/apilog.py`)
- [x] Cached, offline-safe resolvers for NCBI Gene, PubMed, UniProt, doi.org
- [x] **L1 ontology layer** — gene existence, accession, PMID and DOI resolution
- [x] **L2 physics layer** — RDKit parse / valence / kekulisation + formula and MW consistency
- [x] **L3 evidence layer** (pilot slice) — CARD gene→drug-class and gene→mechanism, release-pinned
- [x] **L4 calibration** — split and Mondrian conformal prediction with the finite-sample
      quantile correction, coverage check, semantic-entropy function
- [x] **L5 triage** — deterministic accept / flag / reject rule
- [x] Metrics: ICR, FAR, NRR, VRR, flag rate, Cohen's κ, bootstrap CI
- [x] Four runnable scripts: generate → agreement → run_layers → evaluate
- [x] Claim taxonomy and annotation guide (`docs/claim_taxonomy.md`)
- [x] OSF pre-registration draft with H1–H4 thresholds (`docs/preregistration.md`)
- [x] 64 tests passing with no network access

## Yours, in order

1. **Download CARD** (`data/reference/card/aro_index.tsv`) and set `card.release` in
   `configs/databases.toml`. Until then every layer treats the index as incomplete and
   refuses to conclude absence — correct, but it produces no usable ICR.
2. **Verify each model snapshot**: one test call per family, then change `status` in
   `configs/models.toml` to `verified <date>`. Note that Claude 3.5 Sonnet is retired
   (2025-10-28) and `deepseek-chat` is a floating alias — pin a DeepSeek V3 revision via
   vLLM or a provider that exposes one.
3. **Install RDKit** (`pip install -e ".[chem]"`) and confirm the 10 skipped tests pass.
4. **Start the claim bank.** Copy `data/gold_claims/TEMPLATE.jsonl`, write the first 20 AMR
   claims against CARD, and have a second annotator label them independently. Run
   `experiments/agreement.py` — κ ≥ 0.70 is the gate before scaling up.
5. **Baseline ICR.** Run `generate_claims.py` on one local model, annotate the output, then
   `run_layers.py` + `evaluate.py`. The number that comes out is the reference point for
   all four hypotheses — but with n < 100 `evaluate.py` labels it a debugging estimate, not
   a result, and that label is deliberate.
6. **Fill the open items** at the end of `docs/preregistration.md`, then register on OSF.
   Register before the experiments the protocol describes, not after.

## Two decisions still open

- **Annotator two.** H1–H4 all rest on the gold labels; a single-annotator bank cannot
  support the κ claim the protocol makes. Who is the second annotator, and who adjudicates?
- **The distribution-filter comparator** (condition 4, the H3 contrast) needs a concrete
  parameterisation before registration, or H3 is untestable as written.
