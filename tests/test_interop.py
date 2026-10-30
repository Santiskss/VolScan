import datetime as dt
import xml.etree.ElementTree as ET

import numpy as np

from volscan import cap
from volscan.geoexport import mask_polygons, mask_rings, probability_bands, signed_area
from volscan.grid import Grid

NS = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
G = Grid(elev=np.zeros((40, 40)), west=220000.0, north=3170000.0, step=25.0)


def test_rings_outer_and_hole():
    m = np.zeros((10, 10), bool)
    m[2:8, 2:8] = True
    m[4:6, 4:6] = False
    areas = sorted(signed_area(r) for r in mask_rings(m))
    assert areas == [-36.0, 4.0]                      # outer 6x6 (sign = outer), hole 2x2
    polys = mask_polygons(G, m, tol_cells=0.5, min_cells=1)
    assert len(polys) == 1 and len(polys[0]["coordinates"]) == 2
    ring = polys[0]["coordinates"][0]
    assert ring[0] == ring[-1] and -18 < ring[0][0] < -17 and 28 < ring[0][1] < 29


def test_nested_outer_ring_does_not_duplicate_hole():
    m = np.zeros((14, 14), bool)
    m[1:13, 1:13] = True
    m[3:11, 3:11] = False
    m[5:9, 5:9] = True
    m[6:8, 6:8] = False
    polys = mask_polygons(G, m, tol_cells=0.0, min_cells=1)
    assert len(polys) == 2
    assert sum(len(p["coordinates"]) - 1 for p in polys) == 2


def test_bands_and_cap_message():
    yy, xx = np.mgrid[0:40, 0:40]
    p = np.clip(1 - np.hypot(yy - 20, xx - 20) / 15, 0, 1)
    bands = probability_bands(G, p)
    assert [b["properties"]["band"] for b in bands] == ["probable", "posible", "poco probable"]
    xml = cap.build(kind="tenerife", ref="x", sent=dt.datetime(2026, 10, 27, tzinfo=dt.timezone.utc), headline="h",
                    description="d", bands=bands, isolated=[dict(name="Barrio", lon=-17.8, lat=28.6, p_isolated=0.3)],
                    parameters=dict(edificios=10))
    root = ET.fromstring(xml)
    assert root.find("c:status", NS).text == "Exercise" and root.find("c:scope", NS).text == "Restricted"
    assert root.find(".//c:certainty", NS).text == "Likely"
    polys = [e.text.split() for e in root.findall(".//c:polygon", NS)]
    assert polys and all(pp[0] == pp[-1] and len(pp) >= 4 for pp in polys)
    lat, lon = map(float, polys[0][0].split(","))
    assert 28 < lat < 29 and -18 < lon < -17                    # CAP order is lat,lon
    assert root.find(".//c:circle", NS).text.startswith("28.60000,-17.80000")
