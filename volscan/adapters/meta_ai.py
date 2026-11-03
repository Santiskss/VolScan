"""Concrete Hexagonal Adapters for Meta AI Models (Muse Glimmer local, SAM 3.1, Muse Spark, Llama 4) and Local Air-Gapped Ollama."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from ..ai.llm import (
    GLIMMER_DEFAULT_MODEL,
    LLMConfig,
    LLMUnavailable,
    OpenAICompatibleAdapter,
    _clean_text,
    _load_dotenv,
    with_reasoning_strength,
)
from ..ai.sam3_adapter import MetaSAM3Adapter
from ..ports.ai import ModelTurn, MultimodalVisionLanguagePort


class _BaseVisionLanguageMixin(MultimodalVisionLanguagePort):
    """Implements MultimodalVisionLanguagePort over OpenAI-compatible vision chat completions."""

    cfg: LLMConfig
    timeout: float

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def analyze_image(
        self,
        image_png_b64: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 500,
    ) -> ModelTurn:
        import requests

        t0 = time.perf_counter()
        url_data = image_png_b64 if image_png_b64.startswith("data:") else f"data:image/png;base64,{image_png_b64}"
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append(dict(role="system", content=system_prompt))
        messages.append(
            dict(
                role="user",
                content=[
                    dict(type="text", text=prompt),
                    dict(type="image_url", image_url=dict(url=url_data)),
                ],
            )
        )
        body = dict(
            model=self.cfg.model,
            messages=with_reasoning_strength(messages, self.cfg.model),
            temperature=0.2,
            max_tokens=max_tokens,
            stream=False,
        )
        try:
            r = requests.post(
                f"{self.cfg.base}/chat/completions",
                headers=self._headers(),
                data=json.dumps(body),
                timeout=self.timeout,
            )
        except Exception as e:
            raise LLMUnavailable(f"{self.cfg.provider} vision no responde en {self.cfg.base}: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMUnavailable(f"{self.cfg.provider} vision devolvió HTTP {r.status_code}: {r.text[:200]}")
        try:
            text = _clean_text(r.json()["choices"][0]["message"].get("content") or "")
        except Exception as e:
            raise LLMUnavailable(f"respuesta inesperada de {self.cfg.provider} vision") from e
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return ModelTurn(
            content=text,
            tool_calls=[],
            provider=self.cfg.provider,
            model=self.cfg.model,
            adapter=self.cfg.adapter_name,
            latency_ms=dt_ms,
            raw_ai=True,
        )


class MetaMuseSparkAdapter(OpenAICompatibleAdapter, _BaseVisionLanguageMixin):
    """Hexagonal Adapter for Meta's Muse Spark (`muse-spark-1.3`) via Meta Model API."""

    def __init__(self, api_key: str | None = None, model: str | None = None, base: str | None = None, timeout: float = 120.0):
        _load_dotenv()
        cfg = LLMConfig(
            base=(base or os.environ.get("META_API_BASE") or "https://api.meta.ai/v1").rstrip("/"),
            model=model or os.environ.get("META_MUSE_MODEL") or "muse-spark-1.3",
            key=api_key or os.environ.get("META_API_KEY") or os.environ.get("VOLSCAN_LLM_KEY"),
            provider="meta",
            adapter_name="MetaMuseSparkAdapter",
        )
        super().__init__(cfg=cfg, timeout=timeout)


class MetaLlamaAdapter(OpenAICompatibleAdapter, _BaseVisionLanguageMixin):
    """Hexagonal Adapter for Meta Llama 4 Maverick / Llama 3.3 70B Instruct via Meta Llama API or vLLM."""

    def __init__(self, api_key: str | None = None, model: str | None = None, base: str | None = None, timeout: float = 120.0):
        _load_dotenv()
        cfg = LLMConfig(
            base=(base or os.environ.get("LLAMA_API_BASE") or os.environ.get("META_API_BASE") or "https://api.llama.com/compat/v1").rstrip("/"),
            model=model or os.environ.get("LLAMA_MODEL") or "Llama-4-Maverick-17B-128E-Instruct",
            key=api_key or os.environ.get("LLAMA_API_KEY") or os.environ.get("META_API_KEY") or os.environ.get("VOLSCAN_LLM_KEY"),
            provider="meta",
            adapter_name="MetaLlamaAdapter",
        )
        super().__init__(cfg=cfg, timeout=timeout)


class MetaGlimmerLocalAdapter(OpenAICompatibleAdapter, _BaseVisionLanguageMixin):
    """Hexagonal Adapter for Meta Muse Glimmer 30B (open weights, Apache-2.0) served on the operator's own
    machine through Ollama or llama.cpp. Text + images in, tool calling, no data leaves the room."""

    def __init__(self, model: str | None = None, base: str | None = None, timeout: float = 300.0):
        _load_dotenv()
        env_model = os.environ.get("VOLSCAN_LLM_MODEL") or ""
        cfg = LLMConfig(
            base=(base or os.environ.get("VOLSCAN_GLIMMER_BASE") or os.environ.get("VOLSCAN_LLM_BASE") or "http://localhost:11434/v1").rstrip("/"),
            model=model or os.environ.get("VOLSCAN_GLIMMER_MODEL") or (env_model if "glimmer" in env_model.lower() else GLIMMER_DEFAULT_MODEL),
            key=os.environ.get("VOLSCAN_LLM_KEY"),
            provider="meta-local",
            adapter_name="MetaGlimmerLocalAdapter",
        )
        super().__init__(cfg=cfg, timeout=timeout)


class OllamaLocalAdapter(OpenAICompatibleAdapter, _BaseVisionLanguageMixin):
    """Hexagonal Adapter for air-gapped local inference via Ollama (e.g. `llama3.2`, `qwen3:8b`)."""

    def __init__(self, model: str | None = None, base: str | None = None, timeout: float = 120.0):
        _load_dotenv()
        cfg = LLMConfig(
            base=(base or os.environ.get("VOLSCAN_LLM_BASE") or "http://localhost:11434/v1").rstrip("/"),
            model=model or os.environ.get("VOLSCAN_LLM_MODEL") or "qwen3:8b",
            key=os.environ.get("VOLSCAN_LLM_KEY"),
            provider="local",
            adapter_name="OllamaLocalAdapter",
        )
        super().__init__(cfg=cfg, timeout=timeout)


__all__ = [
    "MetaGlimmerLocalAdapter",
    "MetaLlamaAdapter",
    "MetaMuseSparkAdapter",
    "MetaSAM3Adapter",
    "OllamaLocalAdapter",
    "OpenAICompatibleAdapter",
]
