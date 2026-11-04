"""Backup source for the live catalogue: EMSC-CSEM FDSN event service (seismicportal.eu).

VolScan's reference catalogue is IGN's, read from its public web form
(volscan.sources.ign_catalog). If that page changes or goes down, VolScan
must not stop updating silently. EMSC republishes the IGN locations within
minutes through a standard FDSN service, with fewer small events (a higher
magnitude threshold). We use it only to fill the gap since the last good IGN
download. Every event carries an "emsc:" id, so the interface can say where it
came from.
"""
from __future__ import annotations

import datetime as dt

from .ign_catalog import CANARIAS_BOX, IgnEvent

URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
CITATION = "EMSC-CSEM, FDSN event service (seismicportal.eu); locations authored by IGN where stated"


def parse_text(text: str) -> list[IgnEvent]:
    out = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split("|")
        if len(p) < 13:
            continue
        try:
            t = dt.datetime.fromisoformat(p[1].replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            depth = float(p[4]) if p[4] else None
            mag = float(p[10]) if p[10] else None
        except ValueError:
            continue
        out.append(IgnEvent(f"emsc:{p[0]}", t, float(p[2]), float(p[3]), depth, mag, p[9] or "", "",
                            f"{p[12].strip()} · EMSC ({p[5] or 'autor desconocido'})"))
    return out


def fetch(start: dt.datetime, end: dt.datetime, box=CANARIAS_BOX, session=None) -> list[IgnEvent]:
    import requests
    s = session or requests.Session()
    r = s.get(URL, params=dict(format="text", minlat=box[0], maxlat=box[1], minlon=box[2], maxlon=box[3],
                               starttime=start.strftime("%Y-%m-%dT%H:%M:%S"), endtime=end.strftime("%Y-%m-%dT%H:%M:%S"),
                               limit=5000), timeout=60)
    if r.status_code == 204:
        return []
    r.raise_for_status()
    return parse_text(r.text)
