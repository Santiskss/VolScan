#!/usr/bin/env python3
"""Exposure for the Tenerife scenarios → data/tenerife/exposure/ (OpenStreetMap, current).

- building centroids, services and places, and the road network inside the Tenerife lava grid.
Overpass is busy at times: the script retries with backoff. Output is compacted and gzipped.
"""
import gzip
import json
import sys
import time
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "tenerife" / "exposure"
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "27.98,-16.95,28.50,-16.29"
UA = {"User-Agent": "VolScan (hackathon; contact: santiagoconcep19@gmail.com)"}
AMENITY = "school|kindergarten|hospital|clinic|doctors|pharmacy|fire_station|police|townhall|community_centre|social_facility|place_of_worship|fuel|marketplace"
ROADS = "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified|residential|living_street"


def overpass(q: str):
    for k in range(6):
        r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=300)
        if r.ok and r.text.lstrip().startswith("{"):
            return r.json()
        time.sleep(15 * 2 ** k)
    sys.exit("Overpass unavailable; try later")


def dump(name: str, obj):
    with gzip.open(OUT / name, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))


def main(tag: str = time.strftime("%Y%m%d")):
    OUT.mkdir(parents=True, exist_ok=True)
    b = overpass(f'[out:json][timeout:160];way["building"]({BBOX});out center;')["elements"]
    ll = [[round(e["center"]["lon"], 6), round(e["center"]["lat"], 6)] for e in b if "center" in e]
    dump(f"osm_buildings_{tag}.json.gz", dict(attribution="© OpenStreetMap contributors (ODbL)", retrieved=tag, n=len(ll), lonlat=ll))
    f = overpass(f"""[out:json][timeout:160];(node["amenity"~"^({AMENITY})$"]({BBOX});way["amenity"~"^({AMENITY})$"]({BBOX});
node["place"~"^(town|village|hamlet|neighbourhood|suburb|locality)$"]({BBOX});node["power"="substation"]({BBOX});way["power"="substation"]({BBOX});
way["man_made"~"^(water_tower|reservoir_covered|water_works|wastewater_plant)$"]({BBOX});way["landuse"="reservoir"]({BBOX}););out center tags;""")["elements"]
    keep = ("name", "amenity", "place", "power", "man_made", "landuse")
    el = [dict(type=e["type"], id=e["id"], lat=e.get("lat", e.get("center", {}).get("lat")), lon=e.get("lon", e.get("center", {}).get("lon")),
               tags={k: v for k, v in e.get("tags", {}).items() if k in keep}) for e in f]
    dump(f"osm_facilities_places_{tag}.json.gz", dict(elements=el, attribution="© OpenStreetMap contributors (ODbL)", retrieved=tag))
    r = overpass(f'[out:json][timeout:170];way["highway"~"^({ROADS})$"]({BBOX});out geom;')["elements"]
    ways = [dict(type="way", id=w["id"], geometry=[dict(lat=round(p["lat"], 5), lon=round(p["lon"], 5)) for p in w["geometry"]])
            for w in r if w.get("geometry")]
    dump(f"osm_roads_{tag}.json.gz", dict(elements=ways, attribution="© OpenStreetMap contributors (ODbL)", retrieved=tag))
    print(f"{len(ll)} buildings, {len(el)} services/places, {len(ways)} road ways → {OUT}")


if __name__ == "__main__":
    main(*sys.argv[1:])
