"""Append-only JSONL logging of every external call (LLM or database).

Every record carries a UTC timestamp, the target (model snapshot or DB name),
and its version string, so that results can be tied to the exact model and
database release they were produced against (version-drift risk).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
DEFAULT_LOG = Path(os.environ.get("CALIBRE_LOG_DIR", "experiments/logs")) / "calls.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_call(kind: str, target: str, version: str | None, request: Any, response: Any,
             *, ok: bool = True, latency_ms: float | None = None,
             path: str | Path | None = None, **extra: Any) -> dict[str, Any]:
    record = {
        "ts": utc_now(),
        "kind": kind,            # "llm" | "db"
        "target": target,        # model snapshot id or database endpoint
        "version": version,      # pinned snapshot / DB release
        "ok": ok,
        "latency_ms": latency_ms,
        "request": request,
        "response": response,
        **extra,
    }
    p = Path(path) if path else DEFAULT_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record
