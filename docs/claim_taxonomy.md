# CALIBRE-Bio claim taxonomy and annotation guide

Version 0.1 — 2026-11-08. Pilot domains: **AMR** and **molecular design**.
This document defines the unit of evaluation, the claim types, the gold labels, and the
hallucination classes. It is normative: the annotation files and the layer reason codes
must use exactly the strings defined here.

---

## 1. The unit of evaluation: one atomic claim

A **claim** is one biological assertion that can be adjudicated on its own against
curated evidence or a physical constraint. A model answer is decomposed into atomic
claims before annotation; metrics are computed per claim, not per answer.

Rules for decomposition:

- One claim asserts **one** relation. "blaKPC-2 is a carbapenemase found in *K. pneumoniae*"
  becomes two claims (gene→mechanism, gene→organism).
- A citation attached to an assertion is part of that claim (it is checked by L1), not a
  separate claim.
- Hedged assertions ("may contribute to") are annotated as claims and marked
  `hedged: true` in `notes`; the sensitivity analysis reports metrics with and without them.
- Pure boilerplate ("consult a clinical microbiologist") is not a claim and is dropped.

### Record schema (`data/gold_claims/*.jsonl`, one JSON object per line)

| field | type | meaning |
|---|---|---|
| `claim_id` | str | stable id, `<prompt_id>-<model>-<nn>` for generated claims |
| `domain` | `amr` \| `molecular` \| `protein` \| `variant` | the last two are expansion domains |
| `claim_type` | str | from §2 |
| `text` | str | the claim as asserted, verbatim where possible |
| `entities` | object | machine-checkable fields the layers read (§4) |
| `gold_label` | `valid` \| `invalid` \| `novel_plausible` \| `unresolvable` | §3 |
| `hallucination_class` | str \| null | from §3.2; required when `gold_label = invalid` |
| `difficulty` | `easy` \| `medium` \| `hard` | §5 |
| `source` | str | `llm:<model-key>` or `handwritten:<annotator>` |
| `label_status` | str | `unlabelled` → `single_annotated` → `double_annotated` → `adjudicated` |
| `notes` | str \| null | evidence consulted, DB release, hedging, adjudication rationale |

A claim is only admissible in a reported result when `label_status = adjudicated`
(or `double_annotated` with both annotators agreeing).

---

## 2. Claim types

### 2.1 AMR (`domain = amr`)

| `claim_type` | asserts | checked primarily by |
|---|---|---|
| `gene_existence` | a named resistance gene/allele exists | L1 |
| `gene_drug_class` | gene confers resistance to a drug or drug class | L3 |
| `gene_mechanism` | gene acts by a named resistance mechanism | L3 |
| `gene_organism` | gene is found in a named taxon | L3 |
| `gene_mobility` | gene is plasmid-borne / chromosomal / on a named element | L3 |
| `breakpoint_or_phenotype` | quantitative MIC or susceptibility statement | L3 (+ expert) |
| `citation_support` | a named PMID/DOI supports the assertion | L1 |

### 2.2 Molecular design (`domain = molecular`)

| `claim_type` | asserts | checked primarily by |
|---|---|---|
| `structure_validity` | the given SMILES denotes a well-formed molecule | L2 |
| `structure_identity` | the SMILES/formula/MW corresponds to a named compound | L2 + L3 |
| `property_value` | a computed or measured property value (logP, TPSA, MW) | L2 + L3 |
| `target_activity` | the compound acts on a named protein target | L3 |
| `synthetic_accessibility` | the compound is synthesisable by a stated route | L2 (+ expert) |
| `admet_claim` | an ADMET/toxicity statement | L3 (+ expert) |
| `citation_support` | as above | L1 |

---

## 3. Gold labels and hallucination classes

### 3.1 Labels

- **`valid`** — the assertion is supported by the pinned curated evidence, or is a direct
  consequence of it, and violates no physical/chemical constraint.
- **`invalid`** — the assertion contradicts curated evidence, is physically impossible, or
  refers to an entity or citation that does not exist. Requires a `hallucination_class`.
- **`novel_plausible`** — not supported by the pinned evidence, **and** no constraint is
  violated, **and** a domain expert judges it a legitimate hypothesis. This is the class
  the firewall must *not* destroy (H3). The standing instruction to annotators: when torn
  between `invalid` and `novel_plausible`, the deciding question is whether a *constraint*
  is broken or merely *support is absent*. Absence of support is never `invalid`.
- **`unresolvable`** — annotators cannot decide with the available evidence (ambiguous
  wording, evidence conflicts, needs wet-lab data). Excluded from the primary analysis;
  its rate is reported.

### 3.2 Hallucination classes (for `invalid` claims)

| class | definition | typical detector |
|---|---|---|
| `fabricated_entity` | the gene, protein, compound or identifier does not exist in any reference | L1 |
| `fabricated_identifier` | identifier is well-formed but unassigned (accession, allele number) | L1 |
| `fabricated_citation` | PMID/DOI does not resolve, or resolves to unrelated work | L1 |
| `misattributed_relation` | both entities real, relation contradicts curated evidence | L3 |
| `impossible_structure` | invalid SMILES, valence or kekulisation error | L2 |
| `inconsistent_descriptor` | stated formula/MW/property contradicts the stated structure | L2 |
| `quantitative_error` | numeric value wrong beyond the stated tolerance | L2/L3 |
| `conflated_entity` | two distinct entities merged (e.g. gene family treated as allele) | L1/L3 |
| `outdated_claim` | true in an earlier release, superseded in the pinned release | L3 |
| `unsupported_extrapolation` | overgeneralisation beyond what evidence supports | expert |

`fabricated_identifier` vs `fabricated_entity` is decided by whether the *family* exists:
a plausible allele number on a real gene family is `fabricated_identifier`.

---

## 4. The `entities` object — what the layers read

Only these keys are consumed by the current layers; unknown keys are preserved and ignored.

```json
{
  "gene": "mecA",                 // single gene (L1, L3)
  "genes": ["mecA", "tet(M)"],    // or several (L1)
  "organism": "Staphylococcus aureus",
  "drug_class": "cephalosporin",  // or "drug": "ceftazidime" — normalised to a CARD class
  "mechanism": "antibiotic target replacement",
  "uniprot": ["P0A0D7"],
  "pmids": ["12345678"],
  "dois": ["10.1093/bib/xxxxx"],
  "smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "smiles_list": ["...", "..."],
  "formula": "C9H8O4",            // stated by the model — L2 compares with computed
  "mw": 180.16                    // stated by the model — L2 compares with computed
}
```

Annotator rule: `entities` records **what the model asserted**, never a corrected version.
Corrections belong in `notes`.

---

## 5. Difficulty strata

Used for stratified sampling and for Mondrian (per-stratum) conformal calibration in L4.

- `easy` — decidable from a single curated record (gene in CARD; SMILES parses or not).
- `medium` — needs two or more records, or a normalisation step (drug→class mapping, synonym).
- `hard` — needs primary literature, quantitative judgement, or expert interpretation.

---

## 6. Layer verdict semantics (binding on all layer implementations)

Each layer returns one of four verdicts per claim:

- `pass` — positive support found, or no violation of that layer's constraints.
- `fail` — a **hard** violation. Only use for a definitive contradiction or impossibility.
- `unknown` — the layer could not decide: service unavailable, offline, missing release,
  or the relation is simply absent from curated evidence.
- `skip` — the layer does not apply (no relevant entities in the claim).

Two rules exist to protect H3 and must not be weakened for better H1 numbers:

1. **Absence of evidence is `unknown`, never `fail`.** An unlisted gene–drug relation is a
   novelty candidate, not a falsehood.
2. **A known family with an unknown allele number is `unknown` by default**
   (`allele_miss_policy = "flag"`). The `"reject"` policy exists for ablation only and must
   be declared when used.

Triage (L5): any `fail` → `reject`; all applicable layers `pass` → `accept`; otherwise
`flag` for human review. The flag rate is reported as the human-review cost of the firewall.
