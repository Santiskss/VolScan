"""LLM provider behind an OpenAI-compatible API.

Today: Ollama, a local model on the operator's Mac (http://localhost:11434/v1).
Tomorrow: Meta Model API (Muse Spark) on the same endpoint format, with only
the base URL, the key and the model changing. Configuration through
environment variables (or `.env`):

  VOLSCAN_LLM_BASE   default http://localhost:11434/v1
  VOLSCAN_LLM_MODEL  default qwen3:8b
  VOLSCAN_LLM_KEY    (Ollama ignores it; for Meta use META_API_KEY)
  META_API_KEY       if present and VOLSCAN_LLM_BASE isn't set, Meta is used:
                     base https://api.meta.ai/v1, model muse-spark-1.3

If no model responds, `chat` raises LLMUnavailable. Whoever calls it decides
what to show. We never invent an answer "as if" it came from the AI.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


class LLMUnavailable(RuntimeError):
    pass


def _load_dotenv():
    f = Path(__file__).resolve().parents[2] / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


@dataclass(frozen=True)
class LLMConfig:
    base: str
    model: str
    key: str | None
    provider: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        _load_dotenv()
        meta_key = os.environ.get("META_API_KEY")
        if os.environ.get("VOLSCAN_LLM_BASE") or not meta_key:
            base = os.environ.get("VOLSCAN_LLM_BASE", "http://localhost:11434/v1")
            return cls(base.rstrip("/"), os.environ.get("VOLSCAN_LLM_MODEL", "qwen3:8b"),
                       os.environ.get("VOLSCAN_LLM_KEY") or meta_key, "meta" if "meta.ai" in base else "local")
        return cls(os.environ.get("META_API_BASE", "https://api.meta.ai/v1").rstrip("/"),
                   os.environ.get("VOLSCAN_LLM_MODEL", "muse-spark-1.3"), meta_key, "meta")

    def public(self) -> dict:
        return dict(provider=self.provider, model=self.model, base=self.base if self.provider == "local" else "Meta Model API")


_THINK = re.compile(r"<think>.*?</think>", re.S)


def chat(messages, cfg: LLMConfig | None = None, temperature: float = 0.2, max_tokens: int = 900,
         timeout: float = 120.0) -> str:
    import requests
    cfg = cfg or LLMConfig.from_env()
    headers = {"Content-Type": "application/json"}
    if cfg.key:
        headers["Authorization"] = f"Bearer {cfg.key}"
    body = dict(model=cfg.model, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=False)
    try:
        r = requests.post(f"{cfg.base}/chat/completions", headers=headers, data=json.dumps(body), timeout=timeout)
    except Exception as e:
        raise LLMUnavailable(f"{cfg.provider} no responde en {cfg.base}: {type(e).__name__}") from e
    if r.status_code != 200:
        raise LLMUnavailable(f"{cfg.provider} devolvió HTTP {r.status_code}: {r.text[:200]}")
    try:
        text = r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:
        raise LLMUnavailable(f"respuesta inesperada de {cfg.provider}") from e
    return _THINK.sub("", text).strip()


def embed(texts, cfg: LLMConfig | None = None, model: str | None = None, timeout: float = 60.0):
    """Embeddings via /embeddings (Ollama: nomic-embed-text). Returns None if unavailable."""
    import requests
    cfg = cfg or LLMConfig.from_env()
    model = model or os.environ.get("VOLSCAN_EMBED_MODEL", "nomic-embed-text")
    headers = {"Content-Type": "application/json"}
    if cfg.key:
        headers["Authorization"] = f"Bearer {cfg.key}"
    try:
        r = requests.post(f"{cfg.base}/embeddings", headers=headers,
                          data=json.dumps(dict(model=model, input=list(texts))), timeout=timeout)
        if r.status_code != 200:
            return None
        return [d["embedding"] for d in r.json()["data"]]
    except Exception:
        return None


def ping(cfg: LLMConfig | None = None) -> dict:
    import requests
    cfg = cfg or LLMConfig.from_env()
    try:
        h = {"Authorization": f"Bearer {cfg.key}"} if cfg.key else {}
        r = requests.get(f"{cfg.base}/models", headers=h, timeout=5)
        ok = r.status_code == 200
        models = [m.get("id") for m in r.json().get("data", [])] if ok else []
        return dict(ok=ok, models=models[:30], **cfg.public())
    except Exception as e:
        return dict(ok=False, error=type(e).__name__, **cfg.public())
