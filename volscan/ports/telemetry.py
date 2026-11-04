"""Telemetry & Geophysical Observation Ports (IGN, EMSC, NGL GNSS, NASA OMPS SO2)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Protocol, runtime_checkable

from ..seismic import Catalog


@runtime_checkable
class SeismicCatalogPort(Protocol):
    """Port for loading and refreshing the earthquake catalogue."""

    def load_events(self, force: bool = False) -> list[Any]:
        ...

    def load_catalog(self) -> Catalog:
        ...

    def refresh_live(self, min_interval_s: float = 600.0) -> dict[str, Any]:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class GeodeticDeformationPort(Protocol):
    """Port for querying GNSS ground deformation anomalies per volcanic zone."""

    def zone_deformation(self, zone: str, day: dt.date) -> dict[str, Any]:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class VolcanicGasPort(Protocol):
    """Port for querying satellite SO2 column mass above the archipelago."""

    def so2_status(self, day: dt.date, window_days: int = 7) -> dict[str, Any]:
        ...

    def so2_series(self, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        ...

    def status(self) -> dict[str, Any]:
        ...
