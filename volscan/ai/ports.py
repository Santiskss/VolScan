"""Hexagonal Architecture Ports (Domain Contracts) for AI & Vision models.

VolScan's core physics engine (lava Monte Carlo, Bayesian assimilation, seismic
unrest, exposure & OGC/CAP exports) never depends directly on a vendor SDK.
Instead, application services depend on these abstract ports, while Meta AI
models (SAM 3.1, Muse Spark, Llama 4) and local air-gapped models (Ollama,
physics-seeded segmentation) are plugged in as interchangeable adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

import numpy as np

from ..grid import Grid


# ------------------------------------------------------------------ Vision / Segmentation Port (Meta SAM 3.1)
@dataclass(frozen=True)
class PromptPoint:
    """Spatial prompt in UTM Zone 28N coordinates (metres). label=1 foreground, label=0 background."""
    x: float
    y: float
    label: int = 1
    kind: str = "hotspot"     # vent | front_hotspot | prior_core | cold_background


@dataclass(frozen=True)
class ThermalScene:
    """Satellite thermal/SWIR observation projected onto the terrain Grid."""
    grid: Grid
    swir_radiance: np.ndarray               # 2D (rows, cols) normalised SWIR/TIRS anomaly [0..1]
    brightness_temp_k: np.ndarray           # 2D (rows, cols) brightness temperature (Kelvin)
    vent_xy: tuple[float, float]
    observed_at: str
    prior_mask_flat: np.ndarray | None = None
    text_prompt: str = "active volcanic lava flow"
    sensor: str = "Sentinel-2 MSI SWIR / Landsat-8 TIRS"


@dataclass(frozen=True)
class SegmentationResult:
    """Output of a LavaSegmentationPort adapter on the terrain Grid."""
    mask_flat: np.ndarray                   # 1D bool array (rows * cols)
    confidence_flat: np.ndarray             # 1D float array [0..1]
    area_ha: float
    reach_m: float
    prompt_points: list[PromptPoint]
    prompt_box_xy: tuple[float, float, float, float] | None
    adapter: str                            # e.g. "meta-sam3", "meta-sam3-local", "sam3-thermal-seeded"
    model: str                              # e.g. "sam-3.1-hiera-large"
    mode: str                               # "remote_api" | "local_weights" | "physics_prompt_seeded"
    latency_ms: float

    def public_meta(self) -> dict[str, Any]:
        return dict(
            adapter=self.adapter,
            model=self.model,
            mode=self.mode,
            latency_ms=round(self.latency_ms, 1),
            area_ha=round(self.area_ha, 1),
            reach_m=round(self.reach_m),
            n_prompt_points=len(self.prompt_points),
            prompt_points=[dict(x=round(p.x, 1), y=round(p.y, 1), label=p.label, kind=p.kind) for p in self.prompt_points[:12]],
            prompt_box_xy=[round(v, 1) for v in self.prompt_box_xy] if self.prompt_box_xy else None,
        )


@runtime_checkable
class LavaSegmentationPort(Protocol):
    """Port for segmenting active lava perimeters from satellite thermal/optical imagery."""

    def segment(self, scene: ThermalScene) -> SegmentationResult:
        ...

    def status(self) -> dict[str, Any]:
        ...


# ------------------------------------------------------------------ Reasoning / Tool-Calling LLM Port (Meta Muse Spark / Llama)
@dataclass(frozen=True)
class ToolDefinition:
    """Deterministic VolScan domain tool exposed to the reasoning model."""
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def openai_schema(self) -> dict[str, Any]:
        return dict(
            type="function",
            function=dict(name=self.name, description=self.description, parameters=self.parameters),
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolExecutionRecord:
    name: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    duration_ms: float


@dataclass(frozen=True)
class ModelTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = "meta"
    model: str = "muse-spark-1.3"
    adapter: str = "meta-openai-compatible"
    latency_ms: float = 0.0
    raw_ai: bool = True

    def public_model(self) -> dict[str, Any]:
        return dict(
            provider=self.provider,
            model=self.model,
            adapter=self.adapter,
            latency_ms=round(self.latency_ms, 1),
            ok=self.raw_ai,
        )


@runtime_checkable
class LanguageModelPort(Protocol):
    """Port for chat completion and structured tool-calling (Meta Muse Spark, Llama 4, Ollama)."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[ToolDefinition] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> ModelTurn:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class EmbeddingPort(Protocol):
    """Port for text vector embeddings used in hybrid BM25 + Cosine RAG."""

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        ...
