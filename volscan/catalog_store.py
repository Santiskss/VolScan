"""Local store of the IGN catalogue for the Canary Islands, with live refresh of the current month."""
from __future__ import annotations

import datetime as dt
import threading
import time

import numpy as np

from .datasets import DATA
from .seismic import Catalog
from .sources import ign_catalog as ign
from .zones import zone_of

STORE = DATA / "canarias" / "ign"
_lock = threading.Lock()
_state = dict(events=None, loaded_at=0.0, refreshed_at=0.0, refresh_error=None)


def load_events(force: bool = False):
    with _lock:
        if _state["events"] is None or force:
            _state["events"] = ign.load_cache(STORE)
            _state["loaded_at"] = time.time()
        return _state["events"]


def load_catalog() -> Catalog:
    return Catalog.from_events(load_events())


def refresh_live(min_interval_s: float = 600.0) -> dict:
    """Download the current (and previous, during the first days of a month) month again. Throttled."""
    now = time.time()
    if now - _state["refreshed_at"] < min_interval_s:
        return status()
    today = dt.datetime.now(dt.timezone.utc).date()
    start = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1) if today.day <= 3 else today.replace(day=1)
    try:
        ign.sync_monthly(STORE, start, today, refresh_after=start, log=lambda m: None)
        _state["refresh_error"] = None
    except Exception as e:  # network down: keep serving the cache and say so
        _state["refresh_error"] = f"{type(e).__name__}: {e}"
    _state["refreshed_at"] = now
    load_events(force=True)
    return status()


def status() -> dict:
    ev = _state["events"] or []
    return dict(n_events=len(ev), first=ev[0].time_utc.isoformat() if ev else None,
                last=ev[-1].time_utc.isoformat() if ev else None,
                refreshed_at=_state["refreshed_at"] or None, refresh_error=_state["refresh_error"],
                citation=ign.CITATION)


def events_between(start: dt.datetime, end: dt.datetime, zone: str | None = None, min_mag: float | None = None,
                   limit: int = 20000):
    out = []
    for e in load_events():
        if e.time_utc < start or e.time_utc >= end:
            continue
        if min_mag is not None and (e.mag is None or e.mag < min_mag):
            continue
        z = zone_of(e.lat, e.lon).key
        if zone and z != zone:
            continue
        out.append(dict(id=e.evid, t=e.time_utc.isoformat(), lat=e.lat, lon=e.lon, depth=e.depth_km, mag=e.mag,
                        mag_type=e.mag_type, zone=z, place=e.location))
    return out[-limit:]


def zone_catalog(cat: Catalog, key: str) -> Catalog:
    from .zones import BY_KEY, ZONES
    if key == "atlantico":
        inside = np.zeros(len(cat), bool)
        for z in ZONES:
            inside |= (cat.lat >= z.lat_min) & (cat.lat <= z.lat_max) & (cat.lon >= z.lon_min) & (cat.lon <= z.lon_max)
        return cat.select(~inside)
    z = BY_KEY[key]
    # first-match semantics: exclude events claimed by an earlier zone
    m = (cat.lat >= z.lat_min) & (cat.lat <= z.lat_max) & (cat.lon >= z.lon_min) & (cat.lon <= z.lon_max)
    for prev in ZONES:
        if prev.key == key:
            break
        m &= ~((cat.lat >= prev.lat_min) & (cat.lat <= prev.lat_max) & (cat.lon >= prev.lon_min) & (cat.lon <= prev.lon_max))
    return cat.select(m)
