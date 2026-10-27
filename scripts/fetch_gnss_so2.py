#!/usr/bin/env python3
"""Download the deformation (GNSS, NGL) and gas (SO2, NASA OMPS via GIBS) series for the Canary Islands.

    python scripts/fetch_gnss_so2.py            # everything
    python scripts/fetch_gnss_so2.py --so2-only # daily SO2 refresh (fast)

Sources and licences: data/PROVENANCE.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from volscan.datasets import DATA  # noqa: E402
from volscan.sources import gibs_so2, ngl_gnss  # noqa: E402

GNSS_DIR = DATA / "canarias" / "gnss"
SO2_CSV = DATA / "canarias" / "so2_omps_daily.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so2-only", action="store_true")
    a = ap.parse_args()
    if not a.so2_only:
        import requests
        s = requests.Session()
        steps = ngl_gnss.parse_steps(s.get(ngl_gnss.STEPS_URL, timeout=120).text)
        for code in ngl_gnss.STATIONS:
            try:
                n = ngl_gnss.fetch(code, steps, GNSS_DIR, s)
                print(f"GNSS {code}: {n} days")
            except Exception as e:
                print(f"GNSS {code}: failed ({e})")
    gibs_so2.sync(SO2_CSV, dt.date(2021, 8, 1), dt.date(2022, 1, 31))
    today = dt.datetime.now(dt.timezone.utc).date()
    gibs_so2.sync(SO2_CSV, today - dt.timedelta(days=730), today)


if __name__ == "__main__":
    main()
