"""Coordinate conversion between geographic (lon/lat) and UTM zone 28N.

The Canary Islands use REGCAN95 (EPSG:4081). For our purposes it is equal to
ETRS89/WGS84 at the sub-metre level. Grids from IGN come in EPSG:4083
(REGCAN95 / UTM 28N). Earthquake catalogues and Copernicus EMS products come in
lon/lat (CRS84).

This is the closed-form Transverse Mercator from Snyder, "Map Projections — A
Working Manual" (USGS PP 1395, 1987), eqs. 8-9 to 8-25, on the GRS80
ellipsoid. Accuracy is well under 1 mm inside the zone, which is plenty for
grids of 25 m or coarser. We don't take on a PROJ dependency for one zone.
"""
from __future__ import annotations

import math

import numpy as np

A = 6378137.0                 # GRS80 semi-major axis (m)
F = 1 / 298.257222101         # GRS80 flattening
E2 = F * (2 - F)              # first eccentricity squared
EP2 = E2 / (1 - E2)           # second eccentricity squared
K0 = 0.9996
FALSE_EASTING = 500000.0
LON0_ZONE28 = math.radians(-15.0)


def _meridian_arc(phi):
    e4, e6 = E2 * E2, E2 * E2 * E2
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * np.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * np.sin(4 * phi)
                - (35 * e6 / 3072) * np.sin(6 * phi))


def lonlat_to_utm28(lon, lat):
    """Lon/lat in degrees → (easting, northing) in metres, UTM zone 28N.

    Accepts scalars or numpy arrays.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    phi = np.radians(lat)
    lam = np.radians(lon) - LON0_ZONE28
    n = A / np.sqrt(1 - E2 * np.sin(phi) ** 2)
    t = np.tan(phi) ** 2
    c = EP2 * np.cos(phi) ** 2
    a = lam * np.cos(phi)
    m = _meridian_arc(phi)
    x = K0 * n * (a + (1 - t + c) * a ** 3 / 6
                  + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = K0 * (m + n * np.tan(phi) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                                     + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return x + FALSE_EASTING, y


def utm28_to_lonlat(easting, northing):
    """(easting, northing) in metres, UTM zone 28N → lon/lat in degrees."""
    x = np.asarray(easting, dtype=float) - FALSE_EASTING
    y = np.asarray(northing, dtype=float)
    m = y / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    c1 = EP2 * np.cos(phi1) ** 2
    t1 = np.tan(phi1) ** 2
    n1 = A / np.sqrt(1 - E2 * np.sin(phi1) ** 2)
    r1 = A * (1 - E2) / (1 - E2 * np.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * K0)
    lat = phi1 - (n1 * np.tan(phi1) / r1) * (
        d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = LON0_ZONE28 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                         + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120
                         ) / np.cos(phi1)
    return np.degrees(lon), np.degrees(lat)
