"""Concrete Hexagonal Interoperability & Security Audit Adapters (CAP 1.2, OGC GeoJSON, ReportLab PDF/CSV, SHA-256 Audit)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

from .. import cap, geoexport, pdfexport, security
from ..ports.interop import (
    AuditTrailPort,
    EmergencyAlertExportPort,
    GeospatialFeatureExportPort,
    OperationalReportExportPort,
)


class OasisCap12Adapter(EmergencyAlertExportPort):
    """Implements EmergencyAlertExportPort for OASIS CAP 1.2 (ITU-T X.1303) XML alerts."""

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
        return cap.build(
            kind=kind,
            ref=ref,
            sent=sent,
            headline=headline,
            description=description,
            bands=bands,
            isolated=isolated,
            expires=expires,
            parameters=parameters,
        )

    def status(self) -> dict[str, Any]:
        return dict(
            port="EmergencyAlertExportPort",
            adapter="OasisCap12Adapter",
            standard="OASIS CAP 1.2 (ITU-T X.1303)",
            ready=True,
        )


class OgcGeoJsonAdapter(GeospatialFeatureExportPort):
    """Implements GeospatialFeatureExportPort for OGC API Features Part 1 (CRS84 GeoJSON)."""

    def probability_bands(self, grid: Any, p: Any, levels: Sequence[float] = (0.05, 0.25, 0.5, 0.75)) -> list[dict[str, Any]]:
        return geoexport.probability_bands(grid, p, levels=levels)

    def feature_collection(self, features: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        return geoexport.feature_collection(features, **extra)

    def status(self) -> dict[str, Any]:
        return dict(
            port="GeospatialFeatureExportPort",
            adapter="OgcGeoJsonAdapter",
            standard="OGC API Features 1.0 (GeoJSON CRS84)",
            ready=True,
        )


class ReportLabPdfCsvAdapter(OperationalReportExportPort):
    """Implements OperationalReportExportPort for institutional A4 PDF and UTF-8 BOM CSV exports."""

    def report_pdf(self, rep: dict[str, Any]) -> bytes:
        return pdfexport.report_pdf(rep)

    def report_csv(self, rep: dict[str, Any]) -> bytes:
        return pdfexport.report_csv(rep)

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
        return pdfexport.impact_pdf(title, subtitle, kpis, facilities, isolation, places, method, sources)

    def impact_csv(self, facilities: list[dict[str, Any]], isolation: list[dict[str, Any]]) -> bytes:
        return pdfexport.impact_csv(facilities, isolation)

    def status(self) -> dict[str, Any]:
        return dict(
            port="OperationalReportExportPort",
            adapter="ReportLabPdfCsvAdapter",
            formats=["application/pdf", "text/csv"],
            ready=True,
        )


class Sha256JsonlAuditAdapter(AuditTrailPort):
    """Implements AuditTrailPort with an append-only SHA-256 hash chain (ENS traceability)."""

    def record(self, entry: dict[str, Any]) -> None:
        security.audit(entry)

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        return security.read_audit(limit=limit)

    def verify(self) -> dict[str, Any]:
        return security.verify_audit()
