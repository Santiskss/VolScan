"""Loaders for the prepared case-study data (see scripts/fetch_lapalma_2021.py)."""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .grid import Grid

DATA = Path(__file__).resolve().parents[1] / "data"

#: Eruption onset of Tajogaite (Cumbre Vieja), La Palma. IGN gives 15:10 local
#: time (WEST, UTC+1) on 19 September 2021, i.e. 14:10 UTC.
LAPALMA_2021_ONSET = dt.datetime(2021, 9, 19, 14, 10, tzinfo=dt.timezone.utc)


def parse_utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_grid_npz(path) -> Grid:
    d = np.load(path)
    return Grid(elev=d["elev"].astype(float), west=float(d["west"]), north=float(d["north"]), step=float(d["step"]))


@dataclass(frozen=True)
class LavaObservation:
    observed_at: dt.datetime
    polygons: list          # MultiPolygon coordinates, lon/lat
    area_ha_reported: float | None
    layer_id: int


def load_lava_extents(path) -> list[LavaObservation]:
    fc = json.loads(Path(path).read_text())
    out = []
    for f in fc["features"]:
        p = f["properties"]
        out.append(LavaObservation(parse_utc(p["observed_at"]), f["geometry"]["coordinates"],
                                   p.get("area_ha_reported"), int(p["layer_id"])))
    out.sort(key=lambda o: o.observed_at)
    return out


@dataclass(frozen=True)
class Earthquake:
    time: dt.datetime
    lat: float
    lon: float
    depth_km: float | None
    mag: float | None
    mag_type: str
    author: str
    event_id: str


def load_fdsn_text(path) -> list[Earthquake]:
    """FDSN 'text' format (pipe-separated, header starting with #). Missing values stay None."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = csv.reader(fh, delimiter="|")
        header = None
        for row in rows:
            if not row:
                continue
            if row[0].startswith("#"):
                header = [h.strip().lstrip("#").lower() for h in row]
                continue
            if header is None:
                raise ValueError("FDSN text file without a header")
            r = dict(zip(header, row))

            def num(k):
                v = (r.get(k) or "").strip()
                return float(v) if v else None
            out.append(Earthquake(time=parse_utc(r["time"]), lat=float(r["latitude"]), lon=float(r["longitude"]),
                                  depth_km=num("depth/km"), mag=num("magnitude"), mag_type=(r.get("magtype") or "").strip(),
                                  author=(r.get("author") or "").strip(), event_id=r["eventid"].strip()))
    out.sort(key=lambda e: e.time)
    return out
