"""How often has the unrest index been this high, and how often did an eruption follow?

An index between 0 and 10 means little on its own. What an emergency
manager needs is its track record: in the 15 years of IGN catalogue we have,
every time a zone crossed a threshold, did an eruption follow?

We run the index every 2 days, from 2011 to today, in every zone. An
"episode" is a run of days at or above the threshold (with gaps of 30 days or
less merged). An episode "preceded an eruption" if the eruption began within
120 days of the episode start and no more than 30 days after its end, which
also covers precursor episodes that pause before the eruption. Eruptions in
this period: El Hierro (Tagoro, submarine) 10 Oct 2011, and La Palma
(Tajogaite) 19 Sep 2021.

Two eruptions are not enough for a probability, and we don't give one. The
table is a base rate: "N episodes at this level, of which 2 preceded an
eruption". The other episodes are real unrest (La Palma 2017–2020 deep
swarms, El Hierro 2013), not errors.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from .seismic import DAY, Catalog, unrest

ERUPTIONS = {"el_hierro": (dt.date(2011, 10, 10), "El Hierro · Tagoro (submarina)"),
             "la_palma": (dt.date(2021, 9, 19), "La Palma · Tajogaite")}
THRESHOLDS = (3, 4, 5, 6, 7)
START = dt.date(2011, 1, 1)
STEP_DAYS = 2


def index_series(cat: Catalog, start: dt.date, end_ts: float, step_days: int = STEP_DAYS):
    t = dt.datetime(start.year, start.month, start.day, tzinfo=dt.timezone.utc).timestamp()
    out = []
    while t <= end_ts:
        u = unrest(cat, t)
        out.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), u.index))
        t += step_days * DAY
    return out


def episodes(series, threshold: float, merge_days: int = 30):
    eps = []
    for d, ix in series:
        if ix is not None and ix >= threshold:
            if eps and (d - eps[-1][1]).days <= merge_days:
                eps[-1][1] = d
                eps[-1][2] = max(eps[-1][2], ix)
            else:
                eps.append([d, d, ix])
    return eps


def classify(zone: str, ep) -> str:
    e = ERUPTIONS.get(zone)
    if not e:
        return "sin erupción"
    onset = e[0]
    a, b = ep[0], ep[1]
    if a <= onset <= b + dt.timedelta(days=30) and (onset - a).days <= 120:
        return "precedió a la erupción"
    if a > onset and (a - onset).days < 200:
        return "durante o tras la erupción"
    return "sin erupción"


def calibrate(zone_catalogs: dict[str, Catalog], end_ts: float) -> dict:
    series = {z: index_series(c, START, end_ts) for z, c in zone_catalogs.items()}
    table = []
    for T in THRESHOLDS:
        rows, n_days, n_alarm = [], 0, 0
        for z, s in series.items():
            n_days += len(s)
            n_alarm += sum(1 for _, ix in s if ix is not None and ix >= T)
            for ep in episodes(s, T):
                rows.append(dict(zone=z, start=ep[0].isoformat(), end=ep[1].isoformat(), peak=round(ep[2], 1),
                                 outcome=classify(z, ep)))
        pre = [r for r in rows if r["outcome"] == "precedió a la erupción"]
        caught = sorted({r["zone"] for r in pre})
        lead = {z: (ERUPTIONS[z][0] - min(dt.date.fromisoformat(r["start"]) for r in pre if r["zone"] == z)).days for z in caught}
        table.append(dict(threshold=T, episodes=len([r for r in rows if r["outcome"] != "durante o tras la erupción"]),
                          preceded_eruption=len(caught), eruptions=len(ERUPTIONS), lead_days=lead,
                          share_of_time_pct=round(100 * n_alarm / max(1, n_days), 2),
                          list=[r for r in rows if r["outcome"] != "durante o tras la erupción"]))
    last = {z: (s[-1][0].isoformat(), s[-1][1]) for z, s in series.items() if s}
    return dict(start=START.isoformat(), end=dt.datetime.fromtimestamp(end_ts, dt.timezone.utc).date().isoformat(),
                step_days=STEP_DAYS, eruptions={z: dict(date=d.isoformat(), name=n) for z, (d, n) in ERUPTIONS.items()},
                table=table, last=last,
                series={z: [(d.isoformat(), None if ix is None else round(ix, 2)) for d, ix in s] for z, s in series.items()})


def context_line(cal: dict, zone: str, index: float | None) -> str | None:
    """Plain-language track record for the current index of a zone."""
    if index is None or not cal:
        return None
    rows = [r for r in cal["table"] if r["threshold"] <= index]
    if not rows:
        lo = cal["table"][0]
        return (f"Below {lo['threshold']}: usual level. Since {cal['start'][:4]}, the index exceeded "
                f"{lo['threshold']} in {lo['episodes']} episodes across the archipelago; {lo['preceded_eruption']} "
                f"preceded an eruption.")
    r = rows[-1]
    return (f"Since {cal['start'][:4]}, the index reached {r['threshold']} or more in {r['episodes']} episodes across the "
            f"archipelago; {r['preceded_eruption']} of them preceded an eruption (El Hierro 2011, La Palma 2021). "
            f"It is not a probability: two eruptions are not enough to compute one.")


def load_or_build(path: Path, zone_catalogs_fn, end_ts: float, max_age_days: float = 7) -> dict:
    if path.exists():
        d = json.loads(path.read_text())
        age = (dt.datetime.fromtimestamp(end_ts, dt.timezone.utc).date() - dt.date.fromisoformat(d["end"])).days
        if age <= max_age_days:
            return d
    d = calibrate(zone_catalogs_fn(), end_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d))
    return d
