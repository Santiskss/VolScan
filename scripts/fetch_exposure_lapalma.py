#!/usr/bin/env python3
"""Exposure inventory for La Palma 2021 → data/lapalma2021/exposure/

- Copernicus EMS EMSR546 built-up and transport grading (IGME MapServer layers 1 and 2):
  pre-event inventory of buildings and roads in the activation area, with final damage grade.
- OpenStreetMap as of 2021-09-01 (Overpass attic query): services, places, irrigation reservoirs, road network.
"""
import json
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "lapalma2021" / "exposure"
IGME = "https://mapas.igme.es/gis/rest/services/Copernicus/Copernicus_EMSR546/MapServer"
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "28.55,-17.98,28.70,-17.80"
UA = {"User-Agent": "VolScan (hackathon; contact: santiagoconcep19@gmail.com)"}
AMENITY = "school|kindergarten|hospital|clinic|doctors|pharmacy|fire_station|police|townhall|community_centre|social_facility|place_of_worship|fuel|marketplace"


def igme_layer(layer: int):
    out, off = [], 0
    while True:
        r = requests.get(f"{IGME}/{layer}/query", params=dict(where="1=1", outFields="*", outSR=4326, f="geojson",
                                                             resultOffset=off, resultRecordCount=1000), timeout=120)
        fs = r.json().get("features", [])
        out += fs
        if len(fs) < 1000:
            return dict(type="FeatureCollection", features=out)
        off += 1000


def overpass(q: str):
    r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=300)
    r.raise_for_status()
    return r.json()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cems_builtup_grading.geojson").write_text(json.dumps(igme_layer(1)))
    (OUT / "cems_transport_grading.geojson").write_text(json.dumps(igme_layer(2)))
    head = '[out:json][timeout:180][date:"2021-09-01T00:00:00Z"];'
    q1 = head + f"""(node["amenity"~"^({AMENITY})$"]({BBOX}); way["amenity"~"^({AMENITY})$"]({BBOX});
 node["place"~"^(town|village|hamlet|neighbourhood|suburb|locality|isolated_dwelling)$"]({BBOX});
 node["power"="substation"]({BBOX}); way["power"="substation"]({BBOX});
 way["man_made"~"^(water_tower|reservoir_covered|water_works|wastewater_plant)$"]({BBOX}); way["landuse"="reservoir"]({BBOX}););
out center tags;"""
    q2 = head + f"""way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track)$"]({BBOX});
out geom tags;"""
    (OUT / "osm_facilities_places_20210901.json").write_text(json.dumps(overpass(q1)))
    (OUT / "osm_roads_20210901.json").write_text(json.dumps(overpass(q2)))
    print("done", OUT)


if __name__ == "__main__":
    main()
