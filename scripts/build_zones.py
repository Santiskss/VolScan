#!/usr/bin/env python3
"""Volcanic zones as shapes instead of lat/lon boxes → data/canarias/zones_raster.npz (+ zones_bbox.json).

Each island (Lanzarote, La Graciosa and Fuerteventura together) is its land
area plus the sea nearer to it than to any other island, out to 25 km off the
coast. The Tenerife–Gran Canaria channel around the submarine Volcán de Enmedio
is its own zone. Everything else is "atlantico". Built from the Copernicus DEM
land mask (500 m), on a 0.01° grid (~1 km). The boxes overlapped at the edges
(first match won); these shapes don't.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from volscan.datasets import DATA, load_grid_npz  # noqa: E402
from volscan.geo import lonlat_to_utm28  # noqa: E402

LAT0, LAT1, LON0, LON1, RES = 26.5, 30.0, -19.0, -12.5, 0.01
KEYS = ["atlantico", "el_hierro", "la_palma", "la_gomera", "tenerife", "enmedio", "gran_canaria", "lanzarote_fuerteventura"]
SEEDS = {"el_hierro": (27.75, -18.0), "la_palma": (28.65, -17.85), "la_gomera": (28.10, -17.22), "tenerife": (28.27, -16.6),
         "gran_canaria": (27.95, -15.6), "lanzarote_fuerteventura": (28.6, -13.95)}
OFFSHORE_KM = 25.0
ENMEDIO = dict(lat=28.10, lon=-15.95, radius_km=22.0)    # channel between Tenerife and Gran Canaria


def main():
    g = load_grid_npz(DATA / "canarias" / "terrain_archipelago_500m.npz")
    lats = LAT1 - (np.arange(int(round((LAT1 - LAT0) / RES))) + 0.5) * RES
    lons = LON0 + (np.arange(int(round((LON1 - LON0) / RES))) + 0.5) * RES
    LON, LAT = np.meshgrid(lons, lats)
    x, y = lonlat_to_utm28(LON, LAT)
    i, j = g.xy_to_ij(x, y)
    i, j = np.asarray(i).astype(int), np.asarray(j).astype(int)
    ok = (i >= 0) & (i < g.shape[0]) & (j >= 0) & (j < g.shape[1])
    land = np.zeros(LON.shape, bool)
    land[ok] = ~np.isnan(g.elev[i[ok], j[ok]])
    comp, n = ndimage.label(land)
    label = np.zeros(LON.shape, np.uint8)
    _, (ni, nj) = ndimage.distance_transform_edt(~land, return_indices=True)
    for key, (la, lo) in SEEDS.items():
        r, c = int((LAT1 - la) / RES), int((lo - LON0) / RES)
        k = comp[ni[r, c], nj[r, c]]            # the land component at (or nearest to) the seed
        label[comp == k] = KEYS.index(key)
    # Lanzarote, La Graciosa, Fuerteventura, Lobos: every land component east of -14.6
    label[land & (LON > -14.6) & (label == 0)] = KEYS.index("lanzarote_fuerteventura")
    # sea → nearest labelled land, within OFFSHORE_KM (distance in km, anisotropic grid)
    island = label > 0
    dist, (ri, ci) = ndimage.distance_transform_edt(~island, sampling=(RES * 111.2, RES * 111.2 * np.cos(np.radians(28.3))),
                                                    return_indices=True)
    sea = ~island & (dist <= OFFSHORE_KM)
    label[sea] = label[ri[sea], ci[sea]]
    dk = np.hypot((LAT - ENMEDIO["lat"]) * 111.2, (LON - ENMEDIO["lon"]) * 111.2 * np.cos(np.radians(28.1)))
    label[(dk <= ENMEDIO["radius_km"]) & ~island] = KEYS.index("enmedio")
    out = DATA / "canarias" / "zones_raster.npz"
    np.savez_compressed(out, label=label, lat1=LAT1, lon0=LON0, res=RES, keys=np.array(KEYS))
    bbox = {}
    for k, key in enumerate(KEYS[1:], start=1):
        ys, xs = np.nonzero(label == k)
        bbox[key] = [float(LAT1 - (ys.max() + 1) * RES), float(LAT1 - ys.min() * RES),
                     float(LON0 + xs.min() * RES), float(LON0 + (xs.max() + 1) * RES)]   # lat_min, lat_max, lon_min, lon_max
    (DATA / "canarias" / "zones_bbox.json").write_text(json.dumps(bbox, indent=1) + "\n")
    for k, key in enumerate(KEYS):
        print(f"{key:26s} {int((label == k).sum()):7d} cells")


if __name__ == "__main__":
    main()
