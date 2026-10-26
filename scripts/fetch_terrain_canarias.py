#!/usr/bin/env python3
"""Pre-2021 terrain for the 3D views: whole La Palma island (100 m) and the archipelago (500 m).

Source: Copernicus DEM GLO-30 (TanDEM-X, 2011-2015) from the AWS open-data
bucket, with ocean masked by its WBM water mask. Tiles that don't exist
(open ocean) count as sea. Output in UTM 28N, same convention as volscan.grid.

Usage: python scripts/fetch_terrain_canarias.py
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from volscan.geo import utm28_to_lonlat  # noqa: E402

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
OUT = Path(__file__).resolve().parents[1] / "data" / "canarias"
LICENCE = ("Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, "
           "provided under COPERNICUS by the European Union and ESA")

PRODUCTS = {
    "terrain_lapalma_100m": dict(west=208000.0, east=236000.0, south=3146000.0, north=3196000.0, step=100.0),
    "terrain_archipelago_500m": dict(west=170000.0, east=670000.0, south=3055000.0, north=3262000.0, step=500.0),
}


def tile_name(lat0: int, lon0: int, kind: str = "DEM") -> str:
    ns = f"N{lat0:02d}" if lat0 >= 0 else f"S{-lat0:02d}"
    ew = f"W{-lon0:03d}" if lon0 < 0 else f"E{lon0:03d}"
    base = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
    if kind == "DEM":
        return f"{BUCKET}/{base}/{base}.tif"
    return f"{BUCKET}/{base}/AUXFILES/{base.replace('_DEM', '')}_WBM.tif"


def read_geotiff(raw: bytes):
    import tifffile
    with tifffile.TiffFile(io.BytesIO(raw)) as t:
        p = t.pages[0]
        return p.asarray(), p.tags[33550].value, p.tags[33922].value


_cache: dict = {}


def tile(lat0, lon0, manifest):
    key = (lat0, lon0)
    if key in _cache:
        return _cache[key]
    import requests
    r = requests.get(tile_name(lat0, lon0), timeout=180)
    if r.status_code in (403, 404):
        _cache[key] = None
        manifest[f"{lat0}_{lon0}"] = "absent (open ocean)"
        return None
    r.raise_for_status()
    w = requests.get(tile_name(lat0, lon0, "WBM"), timeout=180)
    w.raise_for_status()
    dem, scale, tie = read_geotiff(r.content)
    wbm, wscale, wtie = read_geotiff(w.content)
    manifest[f"{lat0}_{lon0}"] = dict(dem=tile_name(lat0, lon0), sha256=hashlib.sha256(r.content).hexdigest())
    _cache[key] = (dem, scale, tie, wbm, wscale, wtie)
    return _cache[key]


def build(spec, manifest):
    cols = int(round((spec["east"] - spec["west"]) / spec["step"]))
    rows = int(round((spec["north"] - spec["south"]) / spec["step"]))
    xs = spec["west"] + (np.arange(cols) + 0.5) * spec["step"]
    ys = spec["north"] - (np.arange(rows) + 0.5) * spec["step"]
    X, Y = np.meshgrid(xs, ys)
    lon, lat = utm28_to_lonlat(X, Y)
    z = np.full(X.shape, np.nan, np.float32)
    lat0s, lon0s = np.floor(lat).astype(int), np.floor(lon).astype(int)
    for la0, lo0 in sorted(set(zip(lat0s.ravel().tolist(), lon0s.ravel().tolist()))):
        t = tile(la0, lo0, manifest)
        if t is None:
            continue
        dem, scale, tie, wbm, wscale, wtie = t
        m = (lat0s == la0) & (lon0s == lo0)
        c = (lon[m] - tie[3]) / scale[0]
        r = (tie[4] - lat[m]) / scale[1]
        c0 = np.clip(np.floor(c).astype(int), 0, dem.shape[1] - 2)
        r0 = np.clip(np.floor(r).astype(int), 0, dem.shape[0] - 2)
        fc, fr = c - c0, r - r0
        v = (dem[r0, c0] * (1 - fc) * (1 - fr) + dem[r0, c0 + 1] * fc * (1 - fr)
             + dem[r0 + 1, c0] * (1 - fc) * fr + dem[r0 + 1, c0 + 1] * fc * fr)
        wc = np.clip(np.rint((lon[m] - wtie[3]) / wscale[0]).astype(int), 0, wbm.shape[1] - 1)
        wr = np.clip(np.rint((wtie[4] - lat[m]) / wscale[1]).astype(int), 0, wbm.shape[0] - 1)
        v = np.where(wbm[wr, wc] == 1, np.nan, v)
        z[m] = v
    return z


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in PRODUCTS.items():
        print("building", name)
        z = build(spec, manifest)
        np.savez_compressed(OUT / f"{name}.npz", elev=z, west=spec["west"], north=spec["north"], step=spec["step"])
        print(f"  {z.shape}, land cells {int(np.isfinite(z).sum())}, max {np.nanmax(z):.0f} m")
    (OUT / "terrain_manifest.json").write_text(json.dumps(dict(licence=LICENCE, tiles=manifest, products=PRODUCTS),
                                                          indent=1) + "\n")


if __name__ == "__main__":
    main()
