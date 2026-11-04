"""Hexagonal Application Layer: Dependency Injection Container & Port-to-Adapter Wiring."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..adapters.interop import (
    OasisCap12Adapter,
    OgcGeoJsonAdapter,
    ReportLabPdfCsvAdapter,
    Sha256JsonlAuditAdapter,
)
from ..adapters.meta_ai import (
    MetaGlimmerLocalAdapter,
    MetaLlamaAdapter,
    MetaMuseSparkAdapter,
    MetaSAM3Adapter,
    OllamaLocalAdapter,
    OpenAICompatibleAdapter,
)
from ..adapters.telemetry import IgnEmscSeismicAdapter, NasaOmpsSo2Adapter, NglGnssAdapter
from ..ai.agent import VolScanAgent
from ..ai.llm import GLIMMER_DEFAULT_MODEL, LLMConfig, _load_dotenv
from ..ports import (
    AuditTrailPort,
    EmbeddingPort,
    EmergencyAlertExportPort,
    GeodeticDeformationPort,
    GeospatialFeatureExportPort,
    LanguageModelPort,
    LavaSegmentationPort,
    MultimodalVisionLanguagePort,
    OperationalReportExportPort,
    SeismicCatalogPort,
    VolcanicGasPort,
)

META_MODEL_PRESETS = {
    "meta_glimmer_local": {
        "adapter": "MetaGlimmerLocalAdapter",
        "provider": "meta-local",
        "model": GLIMMER_DEFAULT_MODEL,
        "base": "http://localhost:11434/v1",
        "description": "Meta Muse Glimmer 30B, self-hosted (open weights, text + image + tool calling, works offline)",
    },
    "meta_muse": {
        "adapter": "MetaMuseSparkAdapter",
        "provider": "meta",
        "model": "muse-spark-1.3",
        "base": "https://api.meta.ai/v1",
        "description": "Meta Muse Spark 1.3 (multimodal reasoning + tool calling)",
    },
    "meta_llama4": {
        "adapter": "MetaLlamaAdapter",
        "provider": "meta",
        "model": "Llama-4-Maverick-17B-128E-Instruct",
        "base": "https://api.llama.com/compat/v1",
        "description": "Meta Llama 4 Maverick 17B-128E Instruct (multimodal MoE + tool calling)",
    },
    "meta_llama3_70b": {
        "adapter": "MetaLlamaAdapter",
        "provider": "meta",
        "model": "Llama-3.3-70B-Instruct",
        "base": "https://api.llama.com/compat/v1",
        "description": "Meta Llama 3.3 70B Instruct (institutional summaries and reports)",
    },
    "ollama_local": {
        "adapter": "OllamaLocalAdapter",
        "provider": "local",
        "model": "qwen3:8b",
        "base": "http://localhost:11434/v1",
        "description": "Local Ollama (runs in an emergency room with no internet connection)",
    },
}


def resolve_llm_adapter(preset: str | None = None, model: str | None = None, base: str | None = None, api_key: str | None = None) -> OpenAICompatibleAdapter:
    """Resolve the active LanguageModelPort / EmbeddingPort / MultimodalVisionLanguagePort adapter."""
    _load_dotenv()
    choice = (preset or os.environ.get("VOLSCAN_LLM_ADAPTER") or "auto").strip().lower()
    if choice in ("meta_glimmer_local", "glimmer", "meta_local"):
        return MetaGlimmerLocalAdapter(model=model, base=base)
    if choice in ("meta_muse", "muse", "meta"):
        return MetaMuseSparkAdapter(api_key=api_key, model=model, base=base)
    if choice in ("meta_llama", "meta_llama4", "meta_llama3_70b", "llama"):
        default_m = "Llama-3.3-70B-Instruct" if choice == "meta_llama3_70b" else model
        return MetaLlamaAdapter(api_key=api_key, model=default_m, base=base)
    if choice in ("ollama", "ollama_local", "local"):
        return OllamaLocalAdapter(model=model, base=base)
    cfg = LLMConfig.from_env()
    if model or base or api_key:
        cfg = LLMConfig(
            base=(base or cfg.base).rstrip("/"),
            model=model or cfg.model,
            key=api_key or cfg.key,
            provider=cfg.provider,
            adapter_name=cfg.adapter_name,
        )
    return OpenAICompatibleAdapter(cfg=cfg)


@dataclass
class VolScanContainer:
    """Hexagonal Dependency Injection Container binding all Domain Ports to Concrete Adapters."""

    llm: LanguageModelPort = field(default_factory=resolve_llm_adapter)
    embeddings: EmbeddingPort = field(default_factory=resolve_llm_adapter)
    vlm: MultimodalVisionLanguagePort = field(default_factory=resolve_llm_adapter)
    segmentation: LavaSegmentationPort = field(default_factory=MetaSAM3Adapter)
    seismic: SeismicCatalogPort = field(default_factory=IgnEmscSeismicAdapter)
    deformation: GeodeticDeformationPort = field(default_factory=NglGnssAdapter)
    gas: VolcanicGasPort = field(default_factory=NasaOmpsSo2Adapter)
    cap_export: EmergencyAlertExportPort = field(default_factory=OasisCap12Adapter)
    ogc_export: GeospatialFeatureExportPort = field(default_factory=OgcGeoJsonAdapter)
    report_export: OperationalReportExportPort = field(default_factory=ReportLabPdfCsvAdapter)
    audit: AuditTrailPort = field(default_factory=Sha256JsonlAuditAdapter)

    def switch_llm_adapter(self, preset: str, model: str | None = None, base: str | None = None, api_key: str | None = None) -> dict[str, Any]:
        """Hot-swap the active LLM / VLM / Embeddings adapter at runtime without touching domain logic."""
        adapter = resolve_llm_adapter(preset=preset, model=model, base=base, api_key=api_key)
        self.llm = adapter
        self.embeddings = adapter
        self.vlm = adapter
        return self.llm.status()

    def switch_segmentation_adapter(self, model: str | None = None, endpoint: str | None = None, checkpoint: str | None = None) -> dict[str, Any]:
        """Hot-swap the active LavaSegmentationPort (Meta SAM 3.1) adapter configuration at runtime."""
        self.segmentation = MetaSAM3Adapter(model=model, endpoint=endpoint, checkpoint=checkpoint)
        return self.segmentation.status()

    def agent(self) -> VolScanAgent:
        return VolScanAgent(llm_port=self.llm, seg_port=self.segmentation)

    def manifest(self) -> dict[str, Any]:
        ag = self.agent()
        llm_status = self.llm.status()
        seg_status = self.segmentation.status()
        return dict(
            architecture="hexagonal-ports-and-adapters",
            llm_port=llm_status,
            segmentation_port=seg_status,
            ports=dict(
                LanguageModelPort=llm_status,
                MultimodalVisionLanguagePort=dict(
                    port="MultimodalVisionLanguagePort",
                    adapter=llm_status.get("adapter", "OpenAICompatibleAdapter"),
                    model=llm_status.get("model"),
                ),
                LavaSegmentationPort=seg_status,
                SeismicCatalogPort=dict(port="SeismicCatalogPort", adapter="IgnEmscSeismicAdapter"),
                GeodeticDeformationPort=dict(port="GeodeticDeformationPort", adapter="NglGnssAdapter"),
                VolcanicGasPort=dict(port="VolcanicGasPort", adapter="NasaOmpsSo2Adapter"),
                EmergencyAlertExportPort=self.cap_export.status(),
                GeospatialFeatureExportPort=self.ogc_export.status(),
                OperationalReportExportPort=self.report_export.status(),
                AuditTrailPort=dict(port="AuditTrailPort", adapter="Sha256JsonlAuditAdapter", standard="ENS SHA-256 JSONL"),
            ),
            meta_presets=META_MODEL_PRESETS,
            registered_tools=[dict(name=t.name, description=t.description) for t in ag.tools],
        )


_CONTAINER: VolScanContainer | None = None


def get_container() -> VolScanContainer:
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = VolScanContainer()
    return _CONTAINER
