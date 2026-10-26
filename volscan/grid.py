"""Regular terrain grid in UTM 28N (EPSG:4083 / REGCAN95).

Convention: rows run north → south, columns west → east. Values are cell
centres. Cell (i, j) has its centre at
    x = west + (j + 0.5) * step
    y = north - (i + 0.5) * step
"No data" (sea, or a gap in the source) is NaN. We never fill it in: a lava
path that enters a NaN cell stops there and is reported as such.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Grid:
    elev: np.ndarray          # (rows, cols) float, metres, NaN = no data
    west: float               # metres, left edge of the grid
    north: float              # metres, top edge of the grid
    step: float               # metres, square cells
    crs: str = "EPSG:4083"

    def __post_init__(self):
        if self.elev.ndim != 2:
            raise ValueError("elev must be 2-D")
        if not (self.step > 0):
            raise ValueError("step must be positive")

    @property
    def shape(self):
        return self.elev.shape

    @property
    def east(self) -> float:
        return self.west + self.shape[1] * self.step

    @property
    def south(self) -> float:
        return self.north - self.shape[0] * self.step

    def xy_to_ij(self, x, y):
        """Metres → (row, col) of the containing cell. Returns ints, may be out of bounds."""
        j = np.floor((np.asarray(x, float) - self.west) / self.step).astype(int)
        i = np.floor((self.north - np.asarray(y, float)) / self.step).astype(int)
        return i, j

    def ij_to_xy(self, i, j):
        x = self.west + (np.asarray(j, float) + 0.5) * self.step
        y = self.north - (np.asarray(i, float) + 0.5) * self.step
        return x, y

    def inside(self, i, j) -> bool:
        return 0 <= i < self.shape[0] and 0 <= j < self.shape[1]

    def cell_centres(self):
        """Arrays (X, Y) of cell-centre coordinates with the grid's shape."""
        rows, cols = self.shape
        xs = self.west + (np.arange(cols) + 0.5) * self.step
        ys = self.north - (np.arange(rows) + 0.5) * self.step
        return np.meshgrid(xs, ys)

    def slope_deg(self) -> np.ndarray:
        """Slope in degrees by central differences. NaN wherever a neighbour is missing."""
        z = self.elev
        dzdx = np.full_like(z, np.nan)
        dzdy = np.full_like(z, np.nan)
        dzdx[:, 1:-1] = (z[:, 2:] - z[:, :-2]) / (2 * self.step)
        dzdy[1:-1, :] = (z[:-2, :] - z[2:, :]) / (2 * self.step)
        return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))

    @classmethod
    def from_json_dict(cls, d: dict) -> "Grid":
        """Build a grid from {width, height, west_m, north_m, step_m, elevations_m}, row-major north-first."""
        w, h = int(d["width"]), int(d["height"])
        raw = d["elevations_m"]
        if len(raw) != w * h:
            raise ValueError(f"expected {w * h} elevations, got {len(raw)}")
        elev = np.array([np.nan if v is None else float(v) for v in raw]).reshape(h, w)
        return cls(elev=elev, west=float(d["west_m"]), north=float(d["north_m"]),
                   step=float(d["step_m"]), crs=d.get("crs", "EPSG:4083"))
