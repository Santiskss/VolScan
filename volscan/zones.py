"""Volcanic zones of the Canary Islands used to group seismicity.

These are simple lat/lon boxes, one per island or volcanic system, plus the
submarine channel between Tenerife and Gran Canaria (Volcán de Enmedio). They
are an analysis aid, not official limits. An event that falls in none of
them is labelled "atlantico" and still counts towards the archipelago totals.
Order matters: the first box that contains the event wins.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    note: str = ""

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max

    @property
    def centroid(self):
        return (self.lat_min + self.lat_max) / 2, (self.lon_min + self.lon_max) / 2


ZONES = [
    Zone("el_hierro", "El Hierro", 27.55, 27.92, -18.25, -17.85, "includes Tagoro (2011-2012 submarine eruption)"),
    Zone("la_palma", "La Palma", 28.40, 28.90, -18.05, -17.70, "Cumbre Vieja: San Juan 1949, Teneguía 1971, Tajogaite 2021"),
    Zone("la_gomera", "La Gomera", 27.95, 28.25, -17.40, -17.05, "no Holocene eruptions"),
    Zone("tenerife", "Tenerife", 27.95, 28.62, -16.95, -16.10, "Teide–Pico Viejo, ridges; Chinyero 1909"),
    Zone("enmedio", "Canal Tenerife–Gran Canaria", 27.75, 28.40, -16.10, -15.85, "submarine Volcán de Enmedio area"),
    Zone("gran_canaria", "Gran Canaria", 27.70, 28.20, -15.85, -15.33, ""),
    Zone("lanzarote_fuerteventura", "Lanzarote y Fuerteventura", 27.95, 29.45, -14.60, -13.30,
         "Timanfaya 1730-36, Tao 1824"),
]
OTHER = Zone("atlantico", "Atlántico (fuera de zonas)", -90, 90, -180, 180)
BY_KEY = {z.key: z for z in ZONES + [OTHER]}


def zone_of(lat: float, lon: float) -> Zone:
    for z in ZONES:
        if z.contains(lat, lon):
            return z
    return OTHER
