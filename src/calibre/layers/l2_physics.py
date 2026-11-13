"""L2 — Physical/chemical layer: can the stated molecule exist as written?

Small molecules (RDKit):
  1. SMILES parse without sanitisation -> SMILES_SYNTAX_ERROR
  2. ``Chem.DetectChemistryProblems`` -> VALENCE_ERROR / KEKULIZE_ERROR / ...
  3. Full sanitisation must succeed
  4. Claim-consistency: stated molecular formula / MW vs. computed -> FORMULA_MISMATCH / MW_MISMATCH
  5. Soft flags (do not fail the layer): radicals, multiple fragments, extreme formal charge

Proteins (ESMFold pLDDT/PAE) are a later milestone; see ``check_protein`` stub.
If RDKit is not installed the layer returns UNKNOWN, never PASS.
"""
from __future__ import annotations

import re

from ..schema import Claim, LayerResult, Verdict

LAYER = "L2"

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDLogger.DisableLog("rdApp.*")
    HAVE_RDKIT = True
except ImportError:  # pragma: no cover - exercised only without RDKit
    HAVE_RDKIT = False

_PROBLEM_CODES = {
    "AtomValenceException": "VALENCE_ERROR",
    "AtomKekulizeException": "KEKULIZE_ERROR",
    "KekulizeException": "KEKULIZE_ERROR",
}
MW_TOLERANCE_DA = 0.5


def _formula_counts(formula: str) -> dict[str, int]:
    f = formula.replace(" ", "")
    charge = re.search(r"([+-]\d*)$", f)
    if charge:
        f = f[: charge.start()]
    counts: dict[str, int] = {}
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", f):
        counts[el] = counts.get(el, 0) + (int(n) if n else 1)
    return counts


def check_smiles(smiles: str, stated_formula: str | None = None,
                 stated_mw: float | None = None) -> tuple[Verdict, list[str], dict]:
    if not HAVE_RDKIT:
        return Verdict.UNKNOWN, ["RDKIT_UNAVAILABLE"], {}
    smiles = (smiles or "").strip()
    if not smiles:
        return Verdict.FAIL, ["EMPTY_SMILES"], {}

    raw = Chem.MolFromSmiles(smiles, sanitize=False)
    if raw is None:
        return Verdict.FAIL, ["SMILES_SYNTAX_ERROR"], {}
    problems = Chem.DetectChemistryProblems(raw)
    if problems:
        codes = sorted({_PROBLEM_CODES.get(p.GetType(), "CHEMISTRY_ERROR:" + p.GetType()) for p in problems})
        return Verdict.FAIL, codes, {"messages": [p.Message() for p in problems]}

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return Verdict.FAIL, ["SANITIZATION_FAILED"], {}

    formula = rdMolDescriptors.CalcMolFormula(mol)
    mw = Descriptors.MolWt(mol)
    details = {
        "canonical_smiles": Chem.MolToSmiles(mol),
        "inchikey": Chem.MolToInchiKey(mol) if hasattr(Chem, "MolToInchiKey") else None,
        "formula": formula,
        "mw": round(mw, 3),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
    }
    reasons, verdict = ["VALID_STRUCTURE"], Verdict.PASS

    if stated_formula and _formula_counts(stated_formula) != _formula_counts(formula):
        verdict = Verdict.FAIL
        reasons.append(f"FORMULA_MISMATCH:stated={stated_formula},computed={formula}")
    if stated_mw is not None and abs(float(stated_mw) - mw) > MW_TOLERANCE_DA:
        verdict = Verdict.FAIL
        reasons.append(f"MW_MISMATCH:stated={stated_mw},computed={mw:.2f}")

    # soft flags: recorded for analysis / L5, do not fail the layer
    if any(a.GetNumRadicalElectrons() for a in mol.GetAtoms()):
        reasons.append("FLAG_RADICAL")
    if len(Chem.GetMolFrags(mol)) > 1:
        reasons.append("FLAG_MULTI_FRAGMENT")
    if any(abs(a.GetFormalCharge()) > 1 for a in mol.GetAtoms()):
        reasons.append("FLAG_HIGH_FORMAL_CHARGE")
    return verdict, reasons, details


class PhysicsLayer:
    def check(self, claim: Claim) -> LayerResult:
        e = claim.entities or {}
        smiles_list = e.get("smiles_list") or ([e["smiles"]] if e.get("smiles") else [])
        if not smiles_list:
            return LayerResult(LAYER, claim.claim_id, Verdict.SKIP, ["NO_L2_ENTITIES"])
        verdicts, reasons, details = [], [], {}
        for i, smi in enumerate(smiles_list):
            # formula / MW claims are only meaningful for a single stated molecule
            single = len(smiles_list) == 1
            v, r, d = check_smiles(smi, e.get("formula") if single else None,
                                   e.get("mw") if single else None)
            verdicts.append(v)
            reasons += r
            details[f"mol{i}"] = d
        if Verdict.FAIL in verdicts:
            v = Verdict.FAIL
        elif Verdict.UNKNOWN in verdicts:
            v = Verdict.UNKNOWN
        else:
            v = Verdict.PASS
        return LayerResult(LAYER, claim.claim_id, v, reasons, details)


def check_protein(sequence: str):  # pragma: no cover - milestone stub
    """ESMFold pLDDT / PAE plausibility for protein claims (Phase 2, month 3-4)."""
    raise NotImplementedError("ESMFold integration is scheduled after the AMR/molecular pilot")
