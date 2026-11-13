"""Local AMR gene reference index (CARD ``aro_index.tsv`` format).

Download the real index from https://card.mcmaster.ca/download (``card-data``
archive -> ``aro_index.tsv``) and record the release number in
``configs/databases.toml``. The bundled ``data/reference/amr_seed_index.tsv`` is a
15-gene hand-made subset in the same column layout, for unit tests and for the
first 20 pilot claims only. It is NOT a substitute for CARD and must not be
used for any reported result.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

_QUOTES = str.maketrans({"’": "'", "′": "'", "`": "'", "‘": "'"})

# Drug / drug-class synonyms -> CARD drug-class stem (CARD drops the word "antibiotic")
DRUG_TO_CLASS = {
    "colistin": "peptide", "polymyxin": "peptide", "polymyxin b": "peptide",
    "vancomycin": "glycopeptide", "teicoplanin": "glycopeptide",
    "methicillin": "penam", "oxacillin": "penam", "penicillin": "penam", "ampicillin": "penam",
    "penicillins": "penam",
    "meropenem": "carbapenem", "imipenem": "carbapenem", "ertapenem": "carbapenem",
    "ceftazidime": "cephalosporin", "cefotaxime": "cephalosporin", "ceftriaxone": "cephalosporin",
    "aztreonam": "monobactam",
    "ciprofloxacin": "fluoroquinolone", "levofloxacin": "fluoroquinolone", "quinolone": "fluoroquinolone",
    "gentamicin": "aminoglycoside", "amikacin": "aminoglycoside", "tobramycin": "aminoglycoside",
    "kanamycin": "aminoglycoside",
    "tetracycline": "tetracycline", "doxycycline": "tetracycline", "minocycline": "tetracycline",
    "erythromycin": "macrolide", "azithromycin": "macrolide", "clindamycin": "lincosamide",
    "sulfamethoxazole": "sulfonamide", "fosfomycin": "phosphonic acid",
    "beta-lactam": "beta-lactam", "β-lactam": "beta-lactam",
}
BETA_LACTAM_CLASSES = {"penam", "cephalosporin", "cephamycin", "carbapenem", "monobactam", "penem"}

# Free-text mechanism phrases -> CARD Resistance Mechanism terms
MECHANISM_SYNONYMS = {
    "antibiotic inactivation": ["inactivation", "hydrolysis", "hydrolyse", "hydrolyze", "enzymatic",
                                "acetylation", "acetyltransferase", "beta-lactamase", "carbapenemase",
                                "degrad", "modif"],
    "antibiotic target alteration": ["target alteration", "target modification", "methylation",
                                     "methyltransferase", "phosphoethanolamine", "lipid a modification",
                                     "ligase", "altered target", "mutation"],
    "antibiotic target replacement": ["target replacement", "alternative pbp", "pbp2a",
                                      "replacement", "bypass", "alternative dihydropteroate"],
    "antibiotic target protection": ["target protection", "ribosomal protection", "protects",
                                     "protection"],
    "antibiotic efflux": ["efflux", "pump", "export"],
    "reduced permeability to antibiotic": ["permeability", "porin", "impermeab"],
}


def norm_name(name: str) -> str:
    s = name.translate(_QUOTES).strip().lower()
    s = re.sub(r"\s+", "", s)
    return s


def name_keys(name: str) -> set[str]:
    """All lookup keys for a gene name: 'blaKPC-2' ~ 'KPC-2', 'tet(M)' ~ 'tetM'."""
    base = norm_name(name)
    keys = {base}
    if base.startswith("bla") and len(base) > 3:
        keys.add(base[3:].lstrip("_-"))
    keys |= {k.replace("(", "").replace(")", "") for k in list(keys)}
    return {k for k in keys if k}


def family_key(name: str) -> str:
    """'KPC-2' -> 'kpc'; 'CTX-M-15' -> 'ctx-m'; 'tet(M)' -> 'tetm'."""
    k = sorted(name_keys(name), key=len)[0]
    return re.sub(r"-\d+[a-z]?$", "", k)


def norm_class(term: str) -> str:
    t = term.strip().lower().replace("antibiotics", "").replace("antibiotic", "").strip()
    t = DRUG_TO_CLASS.get(t, t)
    if t.endswith("s") and t[:-1] in BETA_LACTAM_CLASSES | {"aminoglycoside", "macrolide",
                                                            "fluoroquinolone", "sulfonamide",
                                                            "tetracycline", "glycopeptide"}:
        t = t[:-1]
    return DRUG_TO_CLASS.get(t, t)


def norm_mechanism(text: str) -> str | None:
    """Map free text to one CARD mechanism term; the longest matching phrase wins."""
    t = text.strip().lower()
    if t in MECHANISM_SYNONYMS:
        return t
    best: tuple[int, str] | None = None
    for card_term, phrases in MECHANISM_SYNONYMS.items():
        for p in phrases:
            if p in t and (best is None or len(p) > best[0]):
                best = (len(p), card_term)
    return best[1] if best else None


@dataclass
class AMRGene:
    name: str
    aro_accession: str
    gene_family: str
    drug_classes: set[str] = field(default_factory=set)
    mechanisms: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)

    def covers_class(self, cls: str) -> bool:
        c = norm_class(cls)
        if c == "beta-lactam":
            return bool(self.drug_classes & BETA_LACTAM_CLASSES)
        return c in self.drug_classes


class AMRIndex:
    def __init__(self, genes: list[AMRGene], *, release: str, complete: bool):
        self.release = release
        self.complete = complete  # True only for a full CARD release
        self._by_key: dict[str, AMRGene] = {}
        self._families: set[str] = set()
        for g in genes:
            for n in {g.name, *g.aliases}:
                for k in name_keys(n):
                    self._by_key.setdefault(k, g)
                self._families.add(family_key(n))

    def __len__(self) -> int:
        return len({id(g) for g in self._by_key.values()})

    def lookup(self, name: str) -> AMRGene | None:
        for k in name_keys(name):
            if k in self._by_key:
                return self._by_key[k]
        return None

    def family_known(self, name: str) -> bool:
        return family_key(name) in self._families

    @classmethod
    def from_tsv(cls, path: str | Path, *, release: str, complete: bool) -> "AMRIndex":
        genes: list[AMRGene] = []
        with Path(path).open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                name = (row.get("CARD Short Name") or row.get("ARO Name") or "").strip()
                if not name:
                    continue
                aliases = {row.get("ARO Name", ""), row.get("Model Name", "")}
                aliases |= set((row.get("Aliases") or "").split(";"))
                genes.append(AMRGene(
                    name=name,
                    aro_accession=(row.get("ARO Accession") or "").strip(),
                    gene_family=(row.get("AMR Gene Family") or "").strip(),
                    drug_classes={norm_class(c) for c in (row.get("Drug Class") or "").split(";") if c.strip()},
                    mechanisms={m.strip().lower() for m in (row.get("Resistance Mechanism") or "").split(";") if m.strip()},
                    aliases={a.strip() for a in aliases if a and a.strip()},
                ))
        return cls(genes, release=release, complete=complete)
