"""Volcanic zones of the Canary Islands used to group seismicity.

Each zone is an island (Lanzarote, La Graciosa and Fuerteventura together)
plus the sea nearer to it than to any other island, out to 25 km off its coast.
The Tenerife–Gran Canaria channel around the submarine Volcán de Enmedio is its
own zone. Anything else is "atlantico" and still counts towards the
archipelago totals. The shapes come from the Copernicus DEM land mask on a
0.01° grid (scripts/build_zones.py). They replace the lat/lon boxes of v0.1,
which overlapped at the edges (the first box won).

They are an analysis aid, not official limits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data" / "canarias"


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    lat_min: float          # bounding box of the zone's shape (for display and centring only)
    lat_max: float
    lon_min: float
    lon_max: float
    note: str = ""

    def contains(self, lat: float, lon: float) -> bool:
        return zone_of(lat, lon).key == self.key

    @property
    def centroid(self):
        return (self.lat_min + self.lat_max) / 2, (self.lon_min + self.lon_max) / 2


_INFO = [
    ("el_hierro", "El Hierro", "incluye Tagoro (erupción submarina 2011-2012)"),
    ("la_palma", "La Palma", "Cumbre Vieja: San Juan 1949, Teneguía 1971, Tajogaite 2021"),
    ("la_gomera", "La Gomera", "sin erupciones holocenas"),
    ("tenerife", "Tenerife", "Teide–Pico Viejo y dorsales; Chinyero 1909"),
    ("enmedio", "Canal Tenerife–Gran Canaria", "zona submarina del volcán de Enmedio"),
    ("gran_canaria", "Gran Canaria", ""),
    ("lanzarote_fuerteventura", "Lanzarote y Fuerteventura", "Timanfaya 1730-36, Tao 1824"),
]
_BBOX = json.loads((DATA / "zones_bbox.json").read_text())
ZONES = [Zone(k, n, *_BBOX[k], note=t) for k, n, t in _INFO]
OTHER = Zone("atlantico", "Atlántico (fuera de zonas)", -90, 90, -180, 180)
BY_KEY = {z.key: z for z in ZONES + [OTHER]}


@lru_cache(maxsize=1)
def _raster():
    d = np.load(DATA / "zones_raster.npz")
    return d["label"], float(d["lat1"]), float(d["lon0"]), float(d["res"]), [str(k) for k in d["keys"]]


def zone_keys(lat, lon) -> np.ndarray:
    """Vectorised: zone key for each (lat, lon)."""
    label, lat1, lon0, res, keys = _raster()
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    r = np.floor((lat1 - lat) / res).astype(int)
    c = np.floor((lon - lon0) / res).astype(int)
    ok = (r >= 0) & (r < label.shape[0]) & (c >= 0) & (c < label.shape[1])
    idx = np.zeros(lat.shape, int)
    idx[ok] = label[r[ok], c[ok]]
    return np.asarray(keys, dtype=object)[idx]


def in_zone(lat, lon, key: str) -> np.ndarray:
    return zone_keys(lat, lon) == key


def zone_of(lat: float, lon: float) -> Zone:
    return BY_KEY[str(zone_keys(np.array([lat]), np.array([lon]))[0])]
