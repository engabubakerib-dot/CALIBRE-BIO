# CALIBRE-Bio

**Calibrated, Architecture-Layered Inspection of Biological Reasoning and Evidence** — a
layered, constraint-based verification architecture with conformal-prediction uncertainty
calibration, built to reduce biologically invalid LLM outputs *without* suppressing
scientifically novel ones.

> Research question: can a layered, constraint-based verification architecture, coupled with
> formally guaranteed uncertainty calibration through conformal prediction, substantially
> reduce biologically invalid LLM outputs without suppressing scientifically novel ones,
> across heterogeneous biological claim types and multiple model families?

Pilot domains (pilot-first strategy): **antimicrobial resistance (AMR)** and
**small-molecule design**. Protein function and clinical variant interpretation are
expansion domains, gated on the month-6 milestone.

---

## The five layers

| layer | question it answers | implementation | status |
|---|---|---|---|
| **L1 ontology** | Do the named entities and citations exist? | local CARD index, NCBI Gene/PubMed, UniProt, doi.org | **working** |
| **L2 physics** | Can the molecule exist as written? | RDKit parse / valence / kekulisation, formula + MW consistency | **working** (small molecules; ESMFold stub) |
| **L3 evidence** | Does curated evidence support the asserted relation? | CARD gene→drug-class and gene→mechanism, release-pinned | **pilot slice** |
| **L4 calibration** | How much should we trust the score? | split + Mondrian conformal prediction, semantic entropy | **core working**, risk model pending |
| **L5 triage** | accept / flag for human review / reject | deterministic rule now; novelty-aware embedding distance later | **pilot rule** |

Two invariants protect the novelty-preservation hypothesis (H3) and are enforced by tests:

1. **Absence of evidence is `unknown`, never `fail`.** An unlisted relation is a novelty
   candidate, not a falsehood.
2. **A known gene family with an unknown allele number is flagged, not rejected**, by
   default. Hard rejection (`--allele-miss-policy reject`) exists for ablation only.

A layer that cannot reach its data source returns `unknown`. No layer ever returns `pass`
because a lookup was unavailable.

---

## Quick start

```bash
git clone <your-remote> calibre-bio && cd calibre-bio
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,chem,analysis]"      # chem brings RDKit
cp .env.example .env                       # then fill in your keys

pytest -q                                  # 64 tests, no network required
```

The 10 skipped tests are the RDKit ones; they run once `rdkit` is installed.

### Get the real evidence base

A fresh clone contains only `data/reference/amr_seed_index.tsv` — a 15-gene hand-made
subset in CARD's `aro_index.tsv` column layout, for unit tests and the first few pilot
claims. It is marked `complete = False`, which makes every layer refuse to conclude
absence. **No reported result may use it.**

```bash
# download card-data from https://card.mcmaster.ca/download, then:
mkdir -p data/reference/card && tar -xjf card-data.tar.bz2 -C data/reference/card aro_index.tsv
sha256sum data/reference/card/aro_index.tsv > data/evidence_versions/card.sha256
# finally, set card.release in configs/databases.toml
```

### The four-step loop

```bash
# 1. generate claims from a pinned model snapshot
python experiments/generate_claims.py --model llama8b --prompts data/prompts/pilot_prompts.jsonl

# 2. annotate (two annotators, independently), then check agreement
python experiments/agreement.py annot_A.jsonl annot_B.jsonl      # target kappa >= 0.70

# 3. run the layers (CALIBRE_OFFLINE=1 to work without network)
python experiments/run_layers.py --claims data/gold_claims/pilot_amr.jsonl
python experiments/run_layers.py --claims data/gold_claims/pilot_amr.jsonl --layers L1   # ablation

# 4. metrics: ICR, FAR, NRR, VRR, flag rate, + the H1 reduction
python experiments/evaluate.py experiments/results/pilot_amr__L1-L2-L3.jsonl
```

Step 3 before step 2 is fine for debugging, but **ICR is undefined without gold labels** —
`evaluate.py` refuses to run on unlabelled claims by design.

---

## Layout

```
calibre-bio/
├── configs/
│   ├── databases.toml          # pinned DB releases (CARD, UniProt, ...)
│   └── models.toml             # pinned model snapshots, one per family
├── data/
│   ├── gold_claims/            # adjudicated claim bank (TEMPLATE.jsonl documents the schema)
│   ├── evidence_versions/      # checksums + release manifests of every evidence snapshot
│   ├── prompts/                # fixed prompt set per domain
│   └── reference/              # CARD index (downloaded) + seed subset (committed)
├── src/calibre/
│   ├── schema.py               # Claim, LayerResult, Verdict — the contract between layers
│   ├── apilog.py               # append-only JSONL log of every model and DB call
│   ├── resolvers.py            # cached, logged, offline-safe NCBI / UniProt / DOI clients
│   ├── amr_reference.py        # CARD index + drug→class and mechanism normalisation
│   ├── llm.py                  # pinned-snapshot client (OpenAI-compatible + Anthropic)
│   ├── pipeline.py             # layer selection (= ablation conditions) + triage
│   ├── layers/l1..l5
│   └── evaluation/metrics.py   # ICR, FAR, NRR, VRR, kappa, bootstrap CI
├── experiments/                # generate → agreement → run_layers → evaluate
├── docs/
│   ├── claim_taxonomy.md       # normative: claim types, labels, hallucination classes
│   └── preregistration.md      # OSF draft: H1–H4 with thresholds, analysis plan
└── tests/                      # 64 tests; all network resolvers stubbed
```

## Reproducibility rules

- **Every** external call is appended to `experiments/logs/calls.jsonl` with a UTC
  timestamp, the model snapshot or endpoint, and the version string.
- Resolver responses are cached on disk, so a re-run reproduces verdicts without network.
- Every L3 verdict carries its `evidence_version`; a verdict without one is a bug.
- Model snapshots are dated IDs. Floating aliases (`gpt-4o`, `deepseek-chat`) are not
  admissible — they change underneath you, which is the project's largest identified risk.
  Verified constraint (2026-11-08): Claude 3.5 Sonnet was **retired from the API on
  2025-10-28**; `configs/models.toml` uses a current snapshot instead.

## Pre-registration first

`docs/preregistration.md` is the OSF draft: H1 (ICR ↓ ≥ 50%), H2 (coverage 90% ± 3 points),
H3 (NRR ≥ 2× the distribution filter at matched FAR), H4 (cross-family spread ≤ 10 points),
plus the metric definitions, the analysis plan and the sensitivity analyses. Register it
before running the experiments it describes; its open items are listed at the end of the file.
