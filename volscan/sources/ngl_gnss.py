"""GNSS daily positions from the Nevada Geodetic Laboratory (NGL), Canary Islands stations.

NGL processes the public GNSS stations of the world every day and publishes
the time series openly (Blewitt, Hammond & Kreemer, 2018, Eos 99,
doi:10.1029/2018EO104623). We use the "AF" series: positions relative to the
fixed Nubian (African) plate, so plate motion is already removed and what is
left is local deformation plus noise.

Format: tenv3 (one line per day; east, north, up in metres split into an
integer and a fractional part). Equipment changes (antenna, receiver) cause
steps that are not deformation; NGL lists them in steps.txt. We remove each
step by the difference of the medians 20 days before and after it.

WHAT THIS NETWORK CAN AND CANNOT SEE
------------------------------------
These are the stations NGL processes, not every station in the islands.
The closest ones to the 2021 vent (MAZO, 10 km; LPAL, 17 km) recorded the
co-eruptive deflation clearly (MAZO −44 mm vertical by December), but NOT the
~10 cm pre-eruptive uplift that IGN measured right next to the vent: the IGN
near-field stations (e.g. LP03) are not in NGL's processing. More stations
need an agreement with IGN or GRAFCAN.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
from pathlib import Path

import numpy as np

URL = "https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/AF/{code}.AF.tenv3"
STEPS_URL = "https://geodesy.unr.edu/NGLStationPages/steps.txt"
CITATION = ("Nevada Geodetic Laboratory (Blewitt, Hammond & Kreemer, 2018, Eos 99, doi:10.1029/2018EO104623), "
            "IGS20, Nubia-fixed (AF) daily series")

# station -> (zone key, place)
STATIONS = {
    "LPAL": ("la_palma", "Roque de los Muchachos"), "MAZO": ("la_palma", "Villa de Mazo"),
    "LP01": ("la_palma", "Fuencaliente"),
    "FRON": ("el_hierro", "La Frontera"), "LRES": ("el_hierro", "La Restinga"), "EH01": ("el_hierro", "El Hierro"),
    "TN01": ("tenerife", "La Laguna"), "TN02": ("tenerife", "La Orotava"), "TN03": ("tenerife", "Arona"),
    "IZAN": ("tenerife", "Izaña"), "SNMG": ("tenerife", "Santiago del Teide"), "GRAF": ("tenerife", "Santa Cruz"),
    "LLAG": ("tenerife", "La Laguna"), "STEI": ("tenerife", "Cañadas del Teide"), "STTE": ("tenerife", "Cañadas del Teide"),
    "ALAJ": ("la_gomera", "Alajeró"), "ALJR": ("la_gomera", "Alajeró"), "GOM1": ("la_gomera", "San Sebastián"),
    "GOME": ("la_gomera", "San Sebastián"), "VHMO": ("la_gomera", "Vallehermoso"),
    "ARG1": ("gran_canaria", "Arguineguín"), "TERR": ("gran_canaria", "Teror"), "AGUI": ("gran_canaria", "Agüimes"),
    "TIAS": ("lanzarote_fuerteventura", "Tías"), "YAIZ": ("lanzarote_fuerteventura", "Yaiza"),
    "HRIA": ("lanzarote_fuerteventura", "Haría"), "LZ01": ("lanzarote_fuerteventura", "Lanzarote"),
    "LZ02": ("lanzarote_fuerteventura", "Lanzarote"),
}


def parse_tenv3(text: str):
    """→ (decimal_year, lat, lon, e, n, u) arrays; e/n/u in metres (absolute, Nubia-fixed)."""
    rows = []
    for line in text.splitlines():
        p = line.split()
        if len(p) < 23 or p[0] == "site":
            continue
        try:
            rows.append((float(p[2]), float(p[20]), float(p[21]), float(p[7]) + float(p[8]),
                         float(p[9]) + float(p[10]), float(p[11]) + float(p[12])))
        except ValueError:
            continue
    a = np.array(rows, float).reshape(-1, 6)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]


def decyear_to_date(t: float) -> dt.date:
    y = int(t)
    start = dt.date(y, 1, 1)
    days = (dt.date(y + 1, 1, 1) - start).days
    return start + dt.timedelta(days=int(round((t - y) * days)))


def date_to_decyear(d: dt.date) -> float:
    start = dt.date(d.year, 1, 1)
    return d.year + (d - start).days / (dt.date(d.year + 1, 1, 1) - start).days


def parse_steps(text: str) -> dict[str, list[dt.date]]:
    """Equipment-change steps (type 1) per station from NGL steps.txt."""
    out: dict[str, set] = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 3 and p[2] == "1":
            try:
                d = dt.datetime.strptime(p[1], "%y%b%d").date()
            except ValueError:
                continue
            out.setdefault(p[0], set()).add(d)
    return {k: sorted(v) for k, v in out.items()}


def remove_steps(t: np.ndarray, x: np.ndarray, step_dates: list[dt.date], window_days: int = 20) -> np.ndarray:
    """Remove offsets at equipment changes (median after − median before, ±window)."""
    x = x.copy()
    for d in step_dates:
        ts = date_to_decyear(d)
        w = window_days / 365.25
        before = (t >= ts - w) & (t < ts)
        after = (t >= ts) & (t < ts + w)
        if before.sum() >= 5 and after.sum() >= 5:
            x[t >= ts] -= np.median(x[after]) - np.median(x[before])
    return x


def write_series(path: Path, code: str, t, e, n, u, lat: float, lon: float):
    """Compact daily CSV (gzip): date, east/north/up in mm relative to the first day."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    buf.write(f"# {code} lat={lat:.5f} lon={lon:.5f} source=NGL IGS20 AF; mm relative to first epoch; steps removed\n")
    buf.write("date,e_mm,n_mm,u_mm\n")
    for ti, a, b, c in zip(t, (e - e[0]) * 1000, (n - n[0]) * 1000, (u - u[0]) * 1000):
        buf.write(f"{decyear_to_date(ti).isoformat()},{a:.1f},{b:.1f},{c:.1f}\n")
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(buf.getvalue())


def read_series(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        head = fh.readline()
        meta = dict(kv.split("=") for kv in head.strip("# \n").split() if "=" in kv)
        fh.readline()
        rows = [ln.strip().split(",") for ln in fh if ln.strip()]
    d = np.array([dt.date.fromisoformat(r[0]).toordinal() for r in rows], int)
    v = np.array([[float(x) for x in r[1:4]] for r in rows], float).reshape(-1, 3)
    return dict(code=head.split()[1], lat=float(meta.get("lat", "nan")), lon=float(meta.get("lon", "nan")),
                day=d, e=v[:, 0], n=v[:, 1], u=v[:, 2])


def fetch(code: str, steps: dict, out_dir: Path, session=None):
    import requests
    s = session or requests.Session()
    r = s.get(URL.format(code=code), timeout=180)
    r.raise_for_status()
    t, lat, lon, e, n, u = parse_tenv3(r.text)
    if t.size == 0:
        return None
    st = steps.get(code, [])
    e, n, u = (remove_steps(t, x, st) for x in (e, n, u))
    write_series(out_dir / f"{code}.csv.gz", code, t, e, n, u, float(np.median(lat)), float(np.median(lon)))
    return t.size
