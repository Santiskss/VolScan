"""Concrete Hexagonal Telemetry Adapters (IGN + EMSC Seismic, NGL GNSS, NASA OMPS SO2)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from .. import catalog_store as store
from .. import deformation as D
from ..ports.telemetry import GeodeticDeformationPort, SeismicCatalogPort, VolcanicGasPort
from ..seismic import Catalog
from ..sources import gibs_so2, ign_catalog, ngl_gnss


class IgnEmscSeismicAdapter(SeismicCatalogPort):
    """Implements SeismicCatalogPort using IGN primary catalogue with automatic EMSC FDSN fallback."""

    def load_events(self, force: bool = False) -> list[Any]:
        return store.load_events(force=force)

    def load_catalog(self) -> Catalog:
        return store.load_catalog()

    def refresh_live(self, min_interval_s: float = 600.0) -> dict[str, Any]:
        return store.refresh_live(min_interval_s=min_interval_s)

    def status(self) -> dict[str, Any]:
        st = store.status()
        return dict(
            port="SeismicCatalogPort",
            adapter="IgnEmscSeismicAdapter",
            primary_source=ign_catalog.CITATION,
            fallback_source="EMSC FDSN (seismicportal.eu)",
            **st,
        )


class NglGnssAdapter(GeodeticDeformationPort):
    """Implements GeodeticDeformationPort using Nevada Geodetic Laboratory (NGL) GPS/GNSS series."""

    def zone_deformation(self, zone: str, day: dt.date) -> dict[str, Any]:
        return D.zone_deformation(zone, day)

    def status(self) -> dict[str, Any]:
        stations = D.load_gnss()
        return dict(
            port="GeodeticDeformationPort",
            adapter="NglGnssAdapter",
            n_stations=len(stations),
            citation=ngl_gnss.CITATION,
        )


class NasaOmpsSo2Adapter(VolcanicGasPort):
    """Implements VolcanicGasPort using NASA GIBS OMPS Sulphur Dioxide (SO2) Middle Troposphere."""

    def so2_status(self, day: dt.date, window_days: int = 7) -> dict[str, Any]:
        return D.so2_status(day, window_days=window_days)

    def so2_series(self, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        return D.so2_series(start, end)

    def status(self) -> dict[str, Any]:
        today = dt.datetime.now(dt.timezone.utc).date()
        st = D.so2_status(today)
        return dict(
            port="VolcanicGasPort",
            adapter="NasaOmpsSo2Adapter",
            citation=gibs_so2.CITATION,
            latest_status=st,
        )
