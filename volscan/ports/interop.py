"""Interoperability, Export, and Security Audit Ports (CAP 1.2, OGC API Features, PDF/CSV, ENS Audit)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Protocol, Sequence, runtime_checkable


@runtime_checkable
class EmergencyAlertExportPort(Protocol):
    """Port for building standard emergency alerts (OASIS CAP 1.2 XML for 112 / ES-Alert)."""

    def build_alert(
        self,
        kind: str,
        ref: str,
        sent: dt.datetime,
        headline: str,
        description: str,
        bands: Sequence[dict[str, Any]],
        isolated: Sequence[dict[str, Any]] = (),
        expires: dt.datetime | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> bytes:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class GeospatialFeatureExportPort(Protocol):
    """Port for converting raster probability maps into OGC GeoJSON polygons and FeatureCollections."""

    def probability_bands(self, grid: Any, p: Any, levels: Sequence[float] = (0.05, 0.25, 0.5, 0.75)) -> list[dict[str, Any]]:
        ...

    def feature_collection(self, features: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class OperationalReportExportPort(Protocol):
    """Port for exporting institutional PDF and UTF-8 CSV reports."""

    def report_pdf(self, rep: dict[str, Any]) -> bytes:
        ...

    def report_csv(self, rep: dict[str, Any]) -> bytes:
        ...

    def impact_pdf(
        self,
        title: str,
        subtitle: str,
        kpis: list[tuple[str, str, str]],
        facilities: list[dict[str, Any]],
        isolation: list[dict[str, Any]],
        places: list[dict[str, Any]],
        method: str,
        sources: str,
    ) -> bytes:
        ...

    def impact_csv(self, facilities: list[dict[str, Any]], isolation: list[dict[str, Any]]) -> bytes:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class AuditTrailPort(Protocol):
    """Port for append-only tamper-evident audit logging (ENS compliance)."""

    def record(self, entry: dict[str, Any]) -> None:
        ...

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        ...

    def verify(self) -> dict[str, Any]:
        ...
