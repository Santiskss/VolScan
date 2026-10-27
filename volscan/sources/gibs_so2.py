"""Volcanic SO2 seen from space over the Canary Islands (NASA OMPS, through NASA GIBS).

WHY THIS SOURCE
---------------
SO2 is the gas that says magma is near the surface. Ground stations (INVOLCAN)
need an agreement; satellite SO2 is open. The best instrument for small
plumes is TROPOMI (Sentinel-5P), but its data need an account. OMPS (Suomi-NPP
and NOAA-20) is coarser (50 km pixels), but NASA GIBS serves it every day,
without an account, as colour-mapped images with a published colour table.
We decode the colours back to Dobson Units (DU).

WHAT THE NUMBER MEANS, AND ITS LIMITS
-------------------------------------
- The "lower troposphere" product (plume assumed at ~3 km), which suits a
  basaltic eruption like La Palma 2021.
- GIBS draws only pixels at or above 1 DU and saturates at 32 DU. So we report
  the SO2 mass visible above 1 DU in a box around the archipelago, in kilotonnes.
  That is a LOWER BOUND on the SO2 burden in the box, not the volcano's
  emission rate (the plume drifts, accumulates and leaves the box).
- A clean day and a day without data look the same in the images. We only
  count dates inside the layer's published availability periods.
- It detects eruptions and strong degassing, not the weak diffuse CO2/He
  degassing that precedes them. Those need ground stations.

Check: La Palma 2021 reads 0 before 19 Sep, tens of kt during the eruption,
and 0 again after mid-December.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from pathlib import Path

import numpy as np

WMS = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
       "&LAYERS={layer}&CRS=EPSG:4326&BBOX={s},{w},{n},{e}&WIDTH={W}&HEIGHT={H}&FORMAT=image/png&TIME={date}")
COLORMAP = "https://gibs.earthdata.nasa.gov/colormaps/v1.3/{layer}.xml"
CAPABILITIES = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml"
LAYERS = ("OMPS_SO2_Lower_Troposphere", "OMPS_NOAA20_SO2_Lower_Troposphere")   # Suomi-NPP first, NOAA-20 fills gaps
BOX = (25.5, -20.5, 31.5, -11.0)       # south, west, north, east: archipelago plus margin downwind
DU_TO_G_M2 = 0.02854                    # 1 DU = 2.687e20 molecules/m2 of SO2 (64.07 g/mol)
CITATION = "NASA OMPS SO2 (Suomi-NPP, NOAA-20), lower troposphere; imagery via NASA GIBS / Worldview"


def parse_colormap(xml: str) -> dict[int, float]:
    """RGB (packed int) -> lower bound of the DU bin; values below 1 DU map to 0."""
    lut = {}
    for rgb, val in re.findall(r'rgb="(\d+,\d+,\d+)" transparent="false" sourceValue="[^"]*" value="\[([^,]+),', xml):
        r, g, b = (int(x) for x in rgb.split(","))
        lut[(r << 16) | (g << 8) | b] = 0.0 if val == "-INF" else float(val)
    return lut


def availability(capabilities_xml: str, layer: str) -> list[tuple[dt.date, dt.date]]:
    i = capabilities_xml.find(f"<ows:Identifier>{layer}<")
    if i < 0:
        return []
    j = capabilities_xml.find("</Layer>", i)
    out = []
    for v in re.findall(r"<Value>(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})/P1D</Value>", capabilities_xml[i:j]):
        out.append((dt.date.fromisoformat(v[0]), dt.date.fromisoformat(v[1])))
    return out


def covered(periods, d: dt.date) -> bool:
    return any(a <= d <= b for a, b in periods)


def decode(png: bytes, lut: dict[int, float]) -> np.ndarray:
    """DU per pixel (NaN = not drawn, i.e. below 1 DU or no data)."""
    from PIL import Image
    a = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))
    key = (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2]
    v = np.full(key.shape, np.nan)
    for k, du in lut.items():
        v[key == k] = du
    v[a[..., 3] == 0] = np.nan
    return v


def mass_kt(du: np.ndarray, box=BOX) -> tuple[float, float]:
    """SO2 mass above 1 DU (kt) and the maximum DU in the image."""
    s, w, n, e = box
    H, W = du.shape
    lat = np.linspace(n, s, H)
    dy = (n - s) / H * 111_195.0
    dx = (e - w) / W * 111_195.0 * np.cos(np.radians(lat))[:, None]
    m = np.where(du >= 1.0, du, 0.0) * DU_TO_G_M2 * dy * dx
    return float(np.nansum(m) / 1e9), float(np.nanmax(du)) if np.isfinite(du).any() else 0.0


def fetch_day(d: dt.date, layer: str, lut: dict[int, float], session=None, box=BOX, px_per_deg: int = 20) -> dict:
    import requests
    s = session or requests.Session()
    sb, wb, nb, eb = box
    W, H = int((eb - wb) * px_per_deg), int((nb - sb) * px_per_deg)
    r = s.get(WMS.format(layer=layer, s=sb, w=wb, n=nb, e=eb, W=W, H=H, date=d.isoformat()), timeout=90)
    r.raise_for_status()
    du = decode(r.content, lut)
    kt, mx = mass_kt(du, box)
    return dict(date=d.isoformat(), so2_kt=round(kt, 2), max_du=round(mx, 2), layer=layer)


FIELDS = ["date", "so2_kt", "max_du", "layer"]


def read_csv(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="") as fh:
        return [dict(date=r["date"], so2_kt=float(r["so2_kt"]), max_du=float(r["max_du"]), layer=r["layer"])
                for r in csv.DictReader(fh)]


def write_csv(path: Path, rows: list[dict]):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted({r["date"]: r for r in rows}.values(), key=lambda r: r["date"])
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)


def sync(path: Path, start: dt.date, end: dt.date, workers: int = 8, log=print) -> int:
    """Fill missing days between start and end (inclusive). Returns the number of new days."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    have = {r["date"]: r for r in read_csv(path)}
    s = requests.Session()
    caps = s.get(CAPABILITIES, timeout=120).text
    periods = {L: availability(caps, L) for L in LAYERS}
    luts = {L: parse_colormap(s.get(COLORMAP.format(layer=L), timeout=60).text) for L in LAYERS}
    todo = []
    d = start
    while d <= end:
        if d.isoformat() not in have:
            L = next((L for L in LAYERS if covered(periods[L], d)), None)
            if L:
                todo.append((d, L))
        d += dt.timedelta(days=1)
    if not todo:
        return 0
    with ThreadPoolExecutor(workers) as ex:
        for row in ex.map(lambda a: fetch_day(a[0], a[1], luts[a[1]], s), todo):
            have[row["date"]] = row
    write_csv(path, list(have.values()))
    log(f"SO2: {len(todo)} new days")
    return len(todo)
