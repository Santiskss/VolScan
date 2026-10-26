import numpy as np
import pytest

from volscan.geo import lonlat_to_utm28, utm28_to_lonlat
from volscan.grid import Grid

# Reference values computed with PROJ (EPSG:4258 -> EPSG:25828) on 2026-10-26.
REFERENCE = [
    ((-17.8667, 28.6131), (219686.457, 3168481.684)),   # Tajogaite, La Palma
    ((-16.6425, 28.2723), (338900.782, 3128460.971)),   # Teide, Tenerife
    ((-13.5, 29.0), (646108.809, 3208912.979)),         # Lanzarote
    ((-18.1, 27.7), (194274.926, 3067817.545)),         # off El Hierro
]


@pytest.mark.parametrize("lonlat,en", REFERENCE)
def test_utm28_matches_proj_to_the_centimetre(lonlat, en):
    e, n = lonlat_to_utm28(*lonlat)
    assert abs(float(e) - en[0]) < 0.01
    assert abs(float(n) - en[1]) < 0.01


@pytest.mark.parametrize("lonlat,en", REFERENCE)
def test_utm28_inverse_round_trip(lonlat, en):
    lon, lat = utm28_to_lonlat(*en)
    assert abs(float(lon) - lonlat[0]) < 1e-7
    assert abs(float(lat) - lonlat[1]) < 1e-7


def test_vectorised_conversion():
    lons = np.array([r[0][0] for r in REFERENCE])
    lats = np.array([r[0][1] for r in REFERENCE])
    e, n = lonlat_to_utm28(lons, lats)
    assert e.shape == (4,) and n.shape == (4,)


def plane(rows=20, cols=10, step=25.0, drop_per_row=5.0):
    elev = np.tile((rows - np.arange(rows))[:, None] * drop_per_row, (1, cols)).astype(float)
    return Grid(elev=elev, west=1000.0, north=5000.0, step=step)


def test_cell_centre_round_trip():
    g = plane()
    x, y = g.ij_to_xy(3, 7)
    assert (x, y) == (1000 + 7.5 * 25, 5000 - 3.5 * 25)
    i, j = g.xy_to_ij(x, y)
    assert (int(i), int(j)) == (3, 7)


def test_bounds():
    g = plane()
    assert g.east == 1000 + 10 * 25 and g.south == 5000 - 20 * 25


def test_slope_of_known_plane():
    g = plane(drop_per_row=25.0)        # 25 m drop over 25 m -> 45 degrees
    s = g.slope_deg()
    assert np.isnan(s[0, 0])            # edges have no central difference
    assert s[5, 5] == pytest.approx(45.0)


def test_from_json_dict_keeps_gaps_as_nan():
    d = dict(width=2, height=2, west_m=0, north_m=100, step_m=50, elevations_m=[1, None, 3, 4])
    g = Grid.from_json_dict(d)
    assert np.isnan(g.elev[0, 1]) and g.elev[1, 0] == 3


def test_from_json_dict_rejects_wrong_size():
    with pytest.raises(ValueError):
        Grid.from_json_dict(dict(width=2, height=2, west_m=0, north_m=0, step_m=1, elevations_m=[1, 2, 3]))
