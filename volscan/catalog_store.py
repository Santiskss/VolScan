"""Local store of the IGN catalogue for the Canary Islands, with live refresh of the current month."""
from __future__ import annotations

import datetime as dt
import threading
import time

import numpy as np

from .datasets import DATA
from .seismic import Catalog
from .sources import ign_catalog as ign

STORE = DATA / "canarias" / "ign"
BACKUP = DATA / "canarias" / "emsc_backup.csv"
STALE_H = 6.0          # no good IGN download for this long → "retrasado"
QUIET_H = 48.0         # no event at all in the archipelago for this long is unusual → say so
_lock = threading.Lock()
_state = dict(events=None, loaded_at=0.0, refreshed_at=0.0, refresh_error=None, backup_used=False, backup_error=None)


def _last_ign_download() -> float | None:
    """When the IGN cache was last written successfully (mtime of the newest monthly file)."""
    files = sorted(STORE.glob("ign_*.csv"))
    return files[-1].stat().st_mtime if files else None


def load_events(force: bool = False):
    """IGN cache, plus EMSC backup events only AFTER the last IGN event (to fill a gap, never to duplicate)."""
    with _lock:
        if _state["events"] is None or force:
            ev = ign.load_cache(STORE)
            if BACKUP.exists():
                last = ev[-1].time_utc if ev else None
                extra = [e for e in ign.read_csv(BACKUP) if last is None or e.time_utc > last]
                ev = ev + extra
            _state["events"] = ev
            _state["loaded_at"] = time.time()
        return _state["events"]


def load_catalog() -> Catalog:
    return Catalog.from_events(load_events())


def refresh_live(min_interval_s: float = 600.0) -> dict:
    """Download the current (and previous, during the first days of a month) month again. Throttled.

    If IGN fails (network, or its page changed format), fill the gap since the
    last IGN event with EMSC, and say so in the status.
    """
    now = time.time()
    if now - _state["refreshed_at"] < min_interval_s:
        return status()
    today = dt.datetime.now(dt.timezone.utc).date()
    start = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1) if today.day <= 3 else today.replace(day=1)
    try:
        ign.sync_monthly(STORE, start, today, refresh_after=start, log=lambda m: None)
        _state["refresh_error"] = None
        _state["backup_used"] = False
    except Exception as e:  # network down or format change: keep serving the cache, fill with EMSC, and say so
        _state["refresh_error"] = f"{type(e).__name__}: {e}"
        _fill_from_backup()
    _state["refreshed_at"] = now
    load_events(force=True)
    return status()


def _fill_from_backup():
    from .sources import emsc_fdsn
    cached = ign.load_cache(STORE)
    since = cached[-1].time_utc if cached else dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    try:
        ev = emsc_fdsn.fetch(since, dt.datetime.now(dt.timezone.utc))
        ign.write_csv(sorted(ev, key=lambda e: e.time_utc), BACKUP)
        _state["backup_used"], _state["backup_error"] = True, None
    except Exception as e:
        _state["backup_used"], _state["backup_error"] = False, f"{type(e).__name__}: {e}"


def health(now: float | None = None) -> dict:
    """Is the live catalogue current? Plain-language level and message for the interface."""
    now = now or time.time()
    ev = _state["events"] or []
    ign_ev = [e for e in ev if not e.evid.startswith("emsc:")]
    last_dl = _last_ign_download()
    dl_age = (now - last_dl) / 3600 if last_dl else None
    last_ev = ev[-1].time_utc.timestamp() if ev else None
    ev_age = (now - last_ev) / 3600 if last_ev else None
    n_backup = len(ev) - len(ign_ev)
    err = _state["refresh_error"]
    if err and "IgnFormatChanged" in err:
        level, msg = "fuente cambiada", "The IGN page changed format: VolScan cannot read it."
    elif err:
        level, msg = "sin conexión con el IGN", "The IGN catalogue could not be downloaded."
    elif dl_age is not None and dl_age > STALE_H:
        level, msg = "retrasado", f"The last IGN download was {dl_age:.0f} h ago."
    else:
        level, msg = "al día", "IGN catalogue downloaded recently."
    if n_backup:
        msg += f" Showing {n_backup} EMSC backup earthquakes since the last IGN record."
    elif err and _state.get("backup_error"):
        msg += " The EMSC backup did not respond either."
    if ev_age is not None and ev_age > QUIET_H:
        msg += f" The last recorded earthquake was {ev_age:.0f} h ago, unusual for the Canaries."
    return dict(level=level, ok=level == "al día", message=msg, last_download_age_h=None if dl_age is None else round(dl_age, 1),
                last_event_age_h=None if ev_age is None else round(ev_age, 1), backup_events=n_backup)


def status() -> dict:
    ev = _state["events"] or []
    return dict(n_events=len(ev), first=ev[0].time_utc.isoformat() if ev else None,
                last=ev[-1].time_utc.isoformat() if ev else None,
                refreshed_at=_state["refreshed_at"] or None, refresh_error=_state["refresh_error"],
                health=health(), citation=ign.CITATION)


_zk = dict(events=None, keys=None)


def event_zone_keys():
    """Zone key per loaded event (cached for the current list of events)."""
    from .zones import zone_keys
    ev = load_events()
    if _zk["events"] is not ev:
        _zk["keys"] = zone_keys(np.array([e.lat for e in ev]), np.array([e.lon for e in ev])) if ev else np.array([], object)
        _zk["events"] = ev
    return _zk["keys"]


def events_between(start: dt.datetime, end: dt.datetime, zone: str | None = None, min_mag: float | None = None,
                   limit: int = 20000):
    out = []
    keys = event_zone_keys()
    for e, z in zip(load_events(), keys):
        if e.time_utc < start or e.time_utc >= end:
            continue
        if min_mag is not None and (e.mag is None or e.mag < min_mag):
            continue
        if zone and z != zone:
            continue
        out.append(dict(id=e.evid, t=e.time_utc.isoformat(), lat=e.lat, lon=e.lon, depth=e.depth_km, mag=e.mag,
                        mag_type=e.mag_type, zone=z, place=e.location))
    return out[-limit:]


def zone_catalog(cat: Catalog, key: str) -> Catalog:
    from .zones import in_zone
    return cat.select(in_zone(cat.lat, cat.lon, key))
