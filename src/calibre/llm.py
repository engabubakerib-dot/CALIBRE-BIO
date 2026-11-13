"""Minimal LLM client for pinned snapshots (OpenAI-compatible + Anthropic).

OpenAI, DeepSeek, xAI and a local vLLM server all speak the OpenAI chat
completions protocol; Anthropic uses its Messages API. Every call is logged
with the snapshot id and the snapshot id the server reports back.
"""
from __future__ import annotations

import os
import time
import tomllib
from pathlib import Path

import requests

from .apilog import log_call

ROOT = Path(__file__).resolve().parents[2]


def load_models(path: str | Path | None = None) -> dict:
    with Path(path or ROOT / "configs" / "models.toml").open("rb") as fh:
        return tomllib.load(fh)


class LLM:
    def __init__(self, key: str, cfg: dict | None = None):
        cfg = cfg or load_models()
        self.key = key
        self.m = cfg["models"][key]
        self.gen = cfg.get("generation", {})
        self.api_key = os.environ.get(self.m["api_key_env"], "EMPTY")

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None, **meta) -> str:
        temperature = self.gen.get("temperature", 0.0) if temperature is None else temperature
        max_tokens = max_tokens or self.gen.get("max_tokens", 1024)
        t0 = time.monotonic()
        if self.m["provider"] == "anthropic":
            url = f"{self.m['base_url']}/messages"
            payload = {"model": self.m["snapshot"], "system": system, "max_tokens": max_tokens,
                       "temperature": temperature, "messages": [{"role": "user", "content": user}]}
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        else:
            url = f"{self.m['base_url']}/chat/completions"
            payload = {"model": self.m["snapshot"], "temperature": temperature, "max_tokens": max_tokens,
                       "seed": self.gen.get("seed"),
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}
            headers = {"Authorization": f"Bearer {self.api_key}"}
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        ok = r.status_code == 200
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text}
        text = ""
        if ok:
            if self.m["provider"] == "anthropic":
                text = "".join(b.get("text", "") for b in body.get("content", []))
            else:
                text = body["choices"][0]["message"]["content"] or ""
        log_call("llm", self.key, self.m["snapshot"], payload, body, ok=ok,
                 latency_ms=(time.monotonic() - t0) * 1000,
                 served_model=body.get("model"), hf_revision=self.m.get("hf_revision"), **meta)
        if not ok:
            raise RuntimeError(f"{self.key}: HTTP {r.status_code}: {str(body)[:300]}")
        return text
