"""Hexagonal Adapters for LanguageModelPort & EmbeddingPort (Meta Muse Spark / Llama / Ollama).

Today: Ollama local model on the operator's Mac (http://localhost:11434/v1) or
Meta Model API (Muse Spark / Llama 4) on the same OpenAI-compatible contract.
Switching between local air-gapped execution and Meta's hosted API requires only
environment variables (or `.env`):

  VOLSCAN_LLM_ADAPTER  optional: "meta" | "ollama" | "auto" (default "auto")
  VOLSCAN_LLM_BASE     default http://localhost:11434/v1
  VOLSCAN_LLM_MODEL    default qwen3:8b (or llama3.2:latest / muse-spark-1.3)
  VOLSCAN_LLM_KEY      (Ollama ignores it; for Meta use META_API_KEY)
  META_API_KEY         if present and VOLSCAN_LLM_BASE isn't set, Meta is used:
                       base https://api.meta.ai/v1, model muse-spark-1.3

If no model responds, `chat` / `complete` raises `LLMUnavailable`. Whoever calls
it decides what to show. We never invent an answer "as if" it came from the AI.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .ports import EmbeddingPort, LanguageModelPort, ModelTurn, ToolCall, ToolDefinition


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
    adapter_name: str = "OpenAICompatibleAdapter"

    @classmethod
    def from_env(cls) -> "LLMConfig":
        _load_dotenv()
        forced = os.environ.get("VOLSCAN_LLM_ADAPTER", "auto").strip().lower()
        meta_key = os.environ.get("META_API_KEY")
        if forced == "meta" or (forced == "auto" and meta_key and not os.environ.get("VOLSCAN_LLM_BASE")):
            base = os.environ.get("META_API_BASE", os.environ.get("VOLSCAN_LLM_BASE", "https://api.meta.ai/v1")).rstrip("/")
            model = os.environ.get("VOLSCAN_LLM_MODEL", "muse-spark-1.3")
            return cls(base, model, meta_key or os.environ.get("VOLSCAN_LLM_KEY"), "meta", "MetaMuseSparkAdapter")
        base = os.environ.get("VOLSCAN_LLM_BASE", "http://localhost:11434/v1").rstrip("/")
        model = os.environ.get("VOLSCAN_LLM_MODEL", "qwen3:8b")
        is_meta = "meta.ai" in base or "llama" in base or model.startswith("muse-") or model.lower().startswith("llama")
        provider = "meta" if "meta.ai" in base else "local"
        adapter = "MetaMuseSparkAdapter" if is_meta and provider == "meta" else "OllamaLocalAdapter"
        return cls(base, model, os.environ.get("VOLSCAN_LLM_KEY") or meta_key, provider, adapter)

    def public(self) -> dict[str, Any]:
        return dict(
            provider=self.provider,
            model=self.model,
            adapter=self.adapter_name,
            base=self.base if self.provider == "local" else "Meta Model API",
        )


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _clean_text(text: str) -> str:
    return _THINK.sub("", text or "").strip()


class OpenAICompatibleAdapter(LanguageModelPort, EmbeddingPort):
    """Hexagonal Adapter implementing LanguageModelPort & EmbeddingPort over OpenAI-compatible HTTP APIs
    (Meta Muse Spark API, Meta Llama API, vLLM, or local Ollama).
    """

    def __init__(self, cfg: LLMConfig | None = None, timeout: float = 120.0):
        self.cfg = cfg or LLMConfig.from_env()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.cfg.key:
            h["Authorization"] = f"Bearer {self.cfg.key}"
        return h

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[ToolDefinition] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> ModelTurn:
        import requests

        t0 = time.perf_counter()
        body: dict[str, Any] = dict(
            model=self.cfg.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        if tools:
            body["tools"] = [t.openai_schema() for t in tools]
            body["tool_choice"] = "auto"

        try:
            r = requests.post(
                f"{self.cfg.base}/chat/completions",
                headers=self._headers(),
                data=json.dumps(body),
                timeout=self.timeout,
            )
            # If a local model does not support `tools` parameter (HTTP 400), retry without `tools`
            if r.status_code == 400 and tools:
                body.pop("tools", None)
                body.pop("tool_choice", None)
                r = requests.post(
                    f"{self.cfg.base}/chat/completions",
                    headers=self._headers(),
                    data=json.dumps(body),
                    timeout=self.timeout,
                )
        except Exception as e:
            raise LLMUnavailable(f"{self.cfg.provider} no responde en {self.cfg.base}: {type(e).__name__}") from e

        if r.status_code != 200:
            raise LLMUnavailable(f"{self.cfg.provider} devolvió HTTP {r.status_code}: {r.text[:200]}")

        try:
            msg = r.json()["choices"][0]["message"]
        except Exception as e:
            raise LLMUnavailable(f"respuesta inesperada de {self.cfg.provider}") from e

        content = _clean_text(msg.get("content") or "")
        parsed_calls: list[ToolCall] = []
        for idx, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            if fn.get("name"):
                parsed_calls.append(ToolCall(id=tc.get("id") or f"call_{idx}", name=fn["name"], arguments=args))

        dt_ms = (time.perf_counter() - t0) * 1000.0
        return ModelTurn(
            content=content,
            tool_calls=parsed_calls,
            provider=self.cfg.provider,
            model=self.cfg.model,
            adapter=self.cfg.adapter_name,
            latency_ms=dt_ms,
            raw_ai=True,
        )

    def embed(self, texts: Sequence[str], model: str | None = None) -> list[list[float]] | None:
        import requests

        embed_model = model or os.environ.get("VOLSCAN_EMBED_MODEL", "nomic-embed-text")
        try:
            r = requests.post(
                f"{self.cfg.base}/embeddings",
                headers=self._headers(),
                data=json.dumps(dict(model=embed_model, input=list(texts))),
                timeout=60.0,
            )
            if r.status_code != 200:
                return None
            return [d["embedding"] for d in r.json()["data"]]
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        import requests

        try:
            h = {"Authorization": f"Bearer {self.cfg.key}"} if self.cfg.key else {}
            r = requests.get(f"{self.cfg.base}/models", headers=h, timeout=5)
            ok = r.status_code == 200
            models = [m.get("id") for m in (r.json().get("data") or []) if isinstance(m, dict)] if ok else []
            return dict(ok=ok, models=models[:30], port="LanguageModelPort", **self.cfg.public())
        except Exception as e:
            return dict(ok=False, error=type(e).__name__, port="LanguageModelPort", **self.cfg.public())


def default_language_model_port(cfg: LLMConfig | None = None) -> LanguageModelPort:
    return OpenAICompatibleAdapter(cfg=cfg)


# ------------------------------------------------------------------ Backwards-compatible functional helpers
def chat(
    messages: list[dict[str, Any]],
    cfg: LLMConfig | None = None,
    temperature: float = 0.2,
    max_tokens: int = 900,
    timeout: float = 120.0,
) -> str:
    adapter = OpenAICompatibleAdapter(cfg=cfg, timeout=timeout)
    return adapter.complete(messages, temperature=temperature, max_tokens=max_tokens).content


def embed(texts: Sequence[str], cfg: LLMConfig | None = None, model: str | None = None, timeout: float = 60.0):
    adapter = OpenAICompatibleAdapter(cfg=cfg, timeout=timeout)
    return adapter.embed(texts, model=model)


def ping(cfg: LLMConfig | None = None) -> dict[str, Any]:
    return OpenAICompatibleAdapter(cfg=cfg).status()
