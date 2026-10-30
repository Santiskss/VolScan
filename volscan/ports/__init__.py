"""Hexagonal Ports Layer: Abstract contracts between VolScan's domain/application and external infrastructure."""
from __future__ import annotations

from .ai import (
    EmbeddingPort,
    LanguageModelPort,
    LavaSegmentationPort,
    ModelTurn,
    MultimodalVisionLanguagePort,
    PromptPoint,
    SegmentationResult,
    ThermalScene,
    ToolCall,
    ToolDefinition,
    ToolExecutionRecord,
)
from .interop import (
    AuditTrailPort,
    EmergencyAlertExportPort,
    GeospatialFeatureExportPort,
    OperationalReportExportPort,
)
from .telemetry import GeodeticDeformationPort, SeismicCatalogPort, VolcanicGasPort

__all__ = [
    "AuditTrailPort",
    "EmbeddingPort",
    "EmergencyAlertExportPort",
    "GeodeticDeformationPort",
    "GeospatialFeatureExportPort",
    "LanguageModelPort",
    "LavaSegmentationPort",
    "ModelTurn",
    "MultimodalVisionLanguagePort",
    "OperationalReportExportPort",
    "PromptPoint",
    "SegmentationResult",
    "SeismicCatalogPort",
    "ThermalScene",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutionRecord",
    "VolcanicGasPort",
]
