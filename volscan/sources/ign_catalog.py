"""IGN earthquake catalogue (Instituto Geográfico Nacional), Canary Islands.

The IGN catalogue is the reference catalogue for Spain, and it is complete
down to much smaller magnitudes than international aggregators. As an example,
EMSC has 280 events for October 2011 in El Hierro, while IGN has thousands.
IGN doesn't publish an FDSN service. It does have a public web form that
returns pages of 50 events, so we query it page by page, politely (with a
pause between requests), and keep a monthly cache.

Citation required by IGN: Instituto Geográfico Nacional (IGN). Catálogo de
terremotos. https://doi.org/10.7419/162.03.2022

Columns per event: IGN id, UTC time, lat, lon, depth (km), magnitude,
magnitude type, maximum intensity (if any), location label. Empty cells stay
empty (None). We never fill them in.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import html
import re
import time
from dataclasses import dataclass
from pathlib import Path

SEARCH = "https://www.ign.es/web/ign/portal/sis-catalogo-terremotos/-/catalogo-terremotos/searchTerremoto"
CITATION = "Instituto Geográfico Nacional (IGN). Catálogo de terremotos. https://doi.org/10.7419/162.03.2022"
CANARIAS_BOX = (26.5, 30.0, -19.0, -12.5)    # lat min, lat max, lon min, lon max
PAGE = 50
FIELDS = ["evid", "time_utc", "lat", "lon", "depth_km", "mag", "mag_type", "int_max", "location"]

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TOTAL = re.compile(r"([\d.]+) terremotos")


@dataclass(frozen=True)
class IgnEvent:
    evid: str
    time_utc: dt.datetime
    lat: float
    lon: float
    depth_km: float | None
    mag: float | None
    mag_type: str
    int_max: str
    location: str


def _num(s: str):
    s = (s or "").strip().replace(",", ".")
    return float(s) if s else None


def parse_rows(page_html: str) -> list[IgnEvent]:
    """Parse the events table of one results page."""
    out = []
    for tr in _ROW.findall(page_html):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in _CELL.findall(tr)]
        if len(cells) < 9 or not cells[0] or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", cells[1]):
            continue
        evid, fecha, hora_utc, _hora_local, lat, lon, prof, mag, mtype = cells[:9]
        int_max = cells[9] if len(cells) > 9 else ""
        loc = cells[10] if len(cells) > 10 else ""
        t = dt.datetime.strptime(f"{fecha} {hora_utc}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        out.append(IgnEvent(evid, t, float(lat), float(lon), _num(prof), _num(mag), mtype, int_max, loc))
    return out


def parse_total(page_html: str) -> int | None:
    m = _TOTAL.search(page_html)
    return int(m.group(1).replace(".", "")) if m else None


def _query(start: dt.date, end: dt.date, box, indice=None) -> dict:
    q = dict(latMin=box[0], latMax=box[1], longMin=box[2], longMax=box[3],
             startDate=start.strftime("%d/%m/%Y"), endDate=end.strftime("%d/%m/%Y"),
             selIntensidad="N", selMagnitud="N", intMin="", intMax="", magMin="", magMax="",
             selProf="N", profMin="", profMax="", fases="no", cond="")
    if indice is not None:
        q["indice"] = indice
    return q


def fetch_range(start: dt.date, end: dt.date, box=CANARIAS_BOX, pause_s: float = 0.5, session=None,
                retries: int = 3) -> list[IgnEvent]:
    """All events between two dates (both inclusive), page by page."""
    import requests
    s = session or requests.Session()

    def get(indice):
        for k in range(retries):
            try:
                r = s.post(SEARCH, params=_query(start, end, box, indice), timeout=120)
                r.raise_for_status()
                return r.text
            except Exception:
                if k == retries - 1:
                    raise
                time.sleep(2 * (k + 1))

    first = get(None)
    total = parse_total(first)
    events = parse_rows(first)
    if total is None:
        return events                       # "no results" page has no total
    page = 1
    while len(events) < total:
        time.sleep(pause_s)
        rows = parse_rows(get(PAGE * (page + 1)))
        if not rows:
            break
        events.extend(rows)
        page += 1
    # de-duplicate by IGN id (pages can shift if the catalogue is updated mid-download)
    uniq = {e.evid: e for e in events}
    return sorted(uniq.values(), key=lambda e: (e.time_utc, e.evid))


def write_csv(events, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for e in events:
            w.writerow([e.evid, e.time_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), e.lat, e.lon,
                        "" if e.depth_km is None else e.depth_km, "" if e.mag is None else e.mag,
                        e.mag_type, e.int_max, e.location])


def read_csv(path) -> list[IgnEvent]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(IgnEvent(r["evid"], dt.datetime.fromisoformat(r["time_utc"].replace("Z", "+00:00")),
                                float(r["lat"]), float(r["lon"]), _num(r["depth_km"]), _num(r["mag"]),
                                r["mag_type"], r["int_max"], r["location"]))
    return out


def month_ranges(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        a = max(start, dt.date(y, m, 1))
        b = min(end, dt.date(y, m, calendar.monthrange(y, m)[1]))
        yield a, b
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def sync_monthly(cache_dir, start: dt.date, end: dt.date, refresh_after: dt.date | None = None, log=print):
    """Fill the cache with one CSV per month. Closed months are downloaded once.
    Months on or after `refresh_after` are always downloaded again."""
    cache_dir = Path(cache_dir)
    for a, b in month_ranges(start, end):
        f = cache_dir / f"ign_{a:%Y_%m}.csv"
        if f.exists() and not (refresh_after and b >= refresh_after):
            continue
        ev = fetch_range(a, b)
        write_csv(ev, f)
        log(f"{a:%Y-%m}: {len(ev)} events")


def load_cache(cache_dir) -> list[IgnEvent]:
    ev = []
    for f in sorted(Path(cache_dir).glob("ign_*.csv")):
        ev.extend(read_csv(f))
    return sorted({e.evid: e for e in ev}.values(), key=lambda e: e.time_utc)
