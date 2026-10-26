#!/usr/bin/env python3
"""Download and prepare the public data for the La Palma 2021 (Tajogaite) case study.

Writes to data/lapalma2021/:
  dem_utm25.npz          pre-eruption terrain, resampled to a 25 m UTM 28N grid
  lava_extents.geojson   Copernicus EMS EMSR546 lava flow extents, one feature per observation
  seismic_emsc.csv       earthquakes (EMSC FDSN; IGN-located events have author MDD)
  manifest.json          URLs, SHA256 hashes, retrieval time, licences

Why Copernicus GLO-30 and not the IGN MDT: GLO-30 comes from TanDEM-X data
acquired 2011-2015, so it is a guaranteed PRE-eruption surface. National DEMs
of La Palma may already include the 2021 lava field, and backtesting on
terrain that already contains the lava would be cheating. GLO-30 is a surface
model (DSM): buildings and trees are in it. For lava flows that's not a
defect — lava also has to get past them.

Usage:  python scripts/fetch_lapalma_2021.py [--out data/lapalma2021]
Extra deps (only for this script): requests, tifffile, imagecodecs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from volscan.geo import utm28_to_lonlat  # noqa: E402

GLO30 = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N28_00_W018_00_DEM/"
DEM_URL = GLO30 + "Copernicus_DSM_COG_10_N28_00_W018_00_DEM.tif"
WBM_URL = GLO30 + "AUXFILES/Copernicus_DSM_COG_10_N28_00_W018_00_WBM.tif"
IGME = "https://mapas.igme.es/gis/rest/services/Copernicus/Copernicus_EMSR546/MapServer"
EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"

# Study area: Cumbre Vieja west flank, from the vent to the coast (UTM 28N, metres).
WEST, EAST, SOUTH, NORTH, STEP = 205000.0, 223000.0, 3160000.0, 3174000.0, 25.0
SEISMIC_BOX = dict(minlat=28.35, maxlat=28.90, minlon=-18.10, maxlon=-17.60)
SEISMIC_START, SEISMIC_END = "2021-08-01", "2022-01-01"

LICENCES = {
    "dem": "Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, "
           "provided under COPERNICUS by the European Union and ESA; all rights reserved (free licence).",
    "lava": "Copernicus Emergency Management Service (© 2021 European Union), EMSR546. Served by IGME.",
    "seismic": "EMSC-CSEM FDSN event service; locations authored by IGN (MDD) where stated.",
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url, **kw) -> bytes:
    import requests
    r = requests.get(url, timeout=120, **kw)
    r.raise_for_status()
    return r.content


def read_geotiff(raw: bytes):
    import tifffile
    with tifffile.TiffFile(io.BytesIO(raw)) as t:
        p = t.pages[0]
        a = p.asarray()
        scale = p.tags[33550].value
        tie = p.tags[33922].value
    return a, scale, tie


def resample_dem(dem_raw: bytes, wbm_raw: bytes):
    """Bilinear DEM and nearest-neighbour water mask from geographic 1" to the UTM grid."""
    dem, scale, tie = read_geotiff(dem_raw)
    wbm, wscale, wtie = read_geotiff(wbm_raw)
    cols = int(round((EAST - WEST) / STEP))
    rows = int(round((NORTH - SOUTH) / STEP))
    xs = WEST + (np.arange(cols) + 0.5) * STEP
    ys = NORTH - (np.arange(rows) + 0.5) * STEP
    X, Y = np.meshgrid(xs, ys)
    lon, lat = utm28_to_lonlat(X, Y)

    # GLO-30 is PixelIsPoint: sample (r, c) sits exactly at (lon0 + c*dx, lat0 - r*dy).
    c = (lon - tie[3]) / scale[0]
    r = (tie[4] - lat) / scale[1]
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    z = (dem[r0, c0] * (1 - fc) * (1 - fr) + dem[r0, c0 + 1] * fc * (1 - fr)
         + dem[r0 + 1, c0] * (1 - fc) * fr + dem[r0 + 1, c0 + 1] * fc * fr).astype(np.float64)

    # The water mask is a separate raster; its pixel convention may differ, so use its own tags.
    wc = np.rint((lon - wtie[3]) / wscale[0]).astype(int)
    wr = np.rint((wtie[4] - lat) / wscale[1]).astype(int)
    water = wbm[np.clip(wr, 0, wbm.shape[0] - 1), np.clip(wc, 0, wbm.shape[1] - 1)]
    z[water == 1] = np.nan          # 1 = ocean; we never invent elevations at sea
    return z.astype(np.float32), int((water == 1).sum())


def fetch_lava(manifest):
    info = json.loads(get(IGME, params={"f": "pjson"}))
    layers = [l for l in info["layers"] if l["name"].startswith("Lava flow (")]
    feats = []
    for l in layers:
        raw = get(f"{IGME}/{l['id']}/query",
                  params={"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"})
        fc = json.loads(raw)
        stamp = l["name"][len("Lava flow ("):-1].strip().rstrip(")")
        when = dt.datetime.strptime(stamp.replace(" UTC", ""), "%d/%m/%Y %H:%M").replace(tzinfo=dt.timezone.utc)
        polys = []
        for f in fc["features"]:
            g = f["geometry"]
            parts = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            # 6 decimals ≈ 0.1 m: far below the 25 m grid; documented in manifest
            polys.extend([[[[round(v, 6) for v in pt] for pt in ring] for ring in poly] for poly in parts])
        area = sum(float(f["properties"].get("area") or 0) for f in fc["features"])
        feats.append(dict(type="Feature",
                          properties=dict(layer_id=l["id"], observed_at=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                          area_ha_reported=round(area, 3), n_parts=len(polys),
                                          method=fc["features"][0]["properties"].get("det_method") if fc["features"] else None),
                          geometry=dict(type="MultiPolygon", coordinates=polys)))
        manifest["sources"][f"lava_layer_{l['id']}"] = dict(url=f"{IGME}/{l['id']}/query", sha256=sha(raw))
    feats.sort(key=lambda f: f["properties"]["observed_at"])
    return dict(type="FeatureCollection", name="EMSR546 lava flow extents",
                crs_note="CRS84 lon/lat, coordinates rounded to 6 decimals (~0.1 m)",
                attribution=LICENCES["lava"], features=feats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/lapalma2021")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = dict(retrieved_at=now, licences=LICENCES, sources={},
                    grid=dict(crs="EPSG:4083 (REGCAN95 / UTM 28N)", west=WEST, north=NORTH, step=STEP,
                              east=EAST, south=SOUTH))

    print("DEM (Copernicus GLO-30)…")
    dem_raw, wbm_raw = get(DEM_URL), get(WBM_URL)
    manifest["sources"]["dem"] = dict(url=DEM_URL, sha256=sha(dem_raw))
    manifest["sources"]["wbm"] = dict(url=WBM_URL, sha256=sha(wbm_raw))
    z, n_sea = resample_dem(dem_raw, wbm_raw)
    np.savez_compressed(out / "dem_utm25.npz", elev=z, west=WEST, north=NORTH, step=STEP)
    manifest["grid"].update(rows=z.shape[0], cols=z.shape[1], sea_cells=n_sea,
                            method="bilinear from GLO-30 (PixelIsPoint); ocean from WBM set to NaN")

    print("Lava extents (CEMS EMSR546 via IGME)…")
    lava = fetch_lava(manifest)
    (out / "lava_extents.geojson").write_text(json.dumps(lava, separators=(",", ":")))
    print(f"  {len(lava['features'])} observations")

    print("Earthquakes (EMSC FDSN)…")
    params = dict(starttime=SEISMIC_START, endtime=SEISMIC_END, format="text", **SEISMIC_BOX)
    raw = get(EMSC, params=params)
    (out / "seismic_emsc.csv").write_bytes(raw)
    manifest["sources"]["seismic"] = dict(url=EMSC, params=params, sha256=sha(raw))
    n_events = raw.count(b"\n") - 1
    print(f"  {n_events} events")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("done →", out)


if __name__ == "__main__":
    main()
