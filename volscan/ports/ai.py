"""AI & Vision Domain Ports (Meta SAM 3.1, Meta Muse Spark, Meta Llama 4, Ollama)."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..ai.ports import (
    EmbeddingPort,
    LanguageModelPort,
    LavaSegmentationPort,
    ModelTurn,
    PromptPoint,
    SegmentationResult,
    ThermalScene,
    ToolCall,
    ToolDefinition,
    ToolExecutionRecord,
)


@runtime_checkable
class MultimodalVisionLanguagePort(Protocol):
    """Port for multimodal visual-language analysis (Meta Llama 4 Maverick / Muse Spark Vision)."""

    def analyze_image(
        self,
        image_png_b64: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 500,
    ) -> ModelTurn:
        ...

    def status(self) -> dict[str, Any]:
        ...


__all__ = [
    "EmbeddingPort",
    "LanguageModelPort",
    "LavaSegmentationPort",
    "ModelTurn",
    "MultimodalVisionLanguagePort",
    "PromptPoint",
    "SegmentationResult",
    "ThermalScene",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutionRecord",
]
