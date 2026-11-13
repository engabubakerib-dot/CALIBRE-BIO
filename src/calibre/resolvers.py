"""Thin, cached, logged clients for public identifier services used by L1.

Design rules
------------
* Every network call is logged (``apilog.log_call``) with the endpoint and date.
* Responses are cached on disk (``CALIBRE_CACHE_DIR``), so re-runs are
  reproducible and do not hammer NCBI / UniProt / Crossref.
* ``CALIBRE_OFFLINE=1`` disables the network: resolvers return ``None``
  ("could not decide"), never a false negative.
* A resolver returns True (exists), False (definitively absent, e.g. HTTP 404
  or empty search), or None (undecidable: offline, timeout, 5xx, rate limit).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .apilog import log_call, sha256, utc_now

try:  # requests is optional so offline unit tests run on a bare interpreter
    import requests
except ImportError:  # pragma: no cover
    requests = None

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNIPROT = "https://rest.uniprot.org/uniprotkb"
DOI_HANDLE = "https://doi.org/api/handles"
USER_AGENT = "CALIBRE-Bio/0.1 (research prototype)"

UNIPROT_ACC_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$"
)
PMID_RE = re.compile(r"^[1-9][0-9]{0,8}$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def offline() -> bool:
    return os.environ.get("CALIBRE_OFFLINE", "0") == "1" or requests is None


class _Cache:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("CALIBRE_CACHE_DIR", ".cache/resolvers"))

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def put(self, key: str, value: Any) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding="utf-8")


class Resolver:
    """Base class: one cached + logged GET with a definitive/undecidable outcome."""

    min_interval_s = 0.34  # NCBI allows ~3 req/s without an API key

    def __init__(self, cache: _Cache | None = None, timeout: float = 15.0):
        self.cache = cache or _Cache()
        self.timeout = timeout
        self._last = 0.0

    def _get(self, url: str, params: dict[str, Any] | None = None) -> tuple[int | None, Any]:
        key = sha256(url + json.dumps(params or {}, sort_keys=True))
        hit = self.cache.get(key)
        if hit is not None:
            return hit["status"], hit["body"]
        if offline():
            return None, None
        wait = self.min_interval_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        t0 = time.monotonic()
        status, body = None, None
        try:
            r = requests.get(url, params=params, timeout=self.timeout,
                             headers={"User-Agent": USER_AGENT})
            status = r.status_code
            try:
                body = r.json()
            except ValueError:
                body = None
        except Exception as exc:  # network error -> undecidable
            body = {"error": repr(exc)}
        finally:
            self._last = time.monotonic()
        log_call("db", url, f"accessed:{utc_now()[:10]}", params, {"status": status},
                 ok=status == 200, latency_ms=(time.monotonic() - t0) * 1000)
        if status in (200, 404):  # only cache definitive answers
            self.cache.put(key, {"status": status, "body": body})
        return status, body


class NCBI(Resolver):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = os.environ.get("NCBI_API_KEY")
        if self.api_key:
            self.min_interval_s = 0.11

    def _params(self, **p: Any) -> dict[str, Any]:
        p["retmode"] = "json"
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    def pmid_exists(self, pmid: str) -> bool | None:
        pmid = str(pmid).strip()
        if not PMID_RE.match(pmid):
            return False
        status, body = self._get(f"{EUTILS}/esummary.fcgi", self._params(db="pubmed", id=pmid))
        if status != 200 or not body:
            return None
        rec = body.get("result", {}).get(pmid)
        if rec is None:
            return None
        return "error" not in rec

    def gene_hits(self, symbol: str, organism: str | None = None) -> int | None:
        term = f"{symbol}[Gene Name]"
        if organism:
            term += f" AND {organism}[Organism]"
        status, body = self._get(f"{EUTILS}/esearch.fcgi", self._params(db="gene", term=term))
        if status != 200 or not body:
            return None
        try:
            return int(body["esearchresult"]["count"])
        except (KeyError, ValueError, TypeError):
            return None


class UniProt(Resolver):
    min_interval_s = 0.1

    def accession_exists(self, acc: str) -> bool | None:
        acc = acc.strip().upper()
        if not UNIPROT_ACC_RE.match(acc):
            return False
        status, _ = self._get(f"{UNIPROT}/{acc}.json", {"fields": "accession"})
        if status == 200:
            return True
        if status in (400, 404):
            return False
        return None


class DOI(Resolver):
    """Resolves through the doi.org Handle API, so Crossref, DataCite, mEDRA... all count."""

    min_interval_s = 0.1

    def doi_exists(self, doi: str) -> bool | None:
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
        if not DOI_RE.match(doi):
            return False
        status, body = self._get(f"{DOI_HANDLE}/{quote(doi, safe='/')}")
        if status == 200 and isinstance(body, dict):
            return body.get("responseCode") == 1
        if status == 404:
            return False  # responseCode 100: handle not found
        return None
