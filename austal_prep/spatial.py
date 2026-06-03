"""
Layer 1: spatial distribution.

Computes how each source's geometry distributes across the calculation
grid cells. Output is a CellWeights structure: a list of (i, j, k)
indices and a parallel array of weights summing to 1.0. Time-invariant.
Runs ONCE per source.

Input: WKT geometries in the calculation grid CRS (UTM metres). The
caller is responsible for any reprojection from EPSG:3857 (the storage
CRS used by sources.parquet) to the grid CRS. See io.sources_loader
for the helper that does this.

This module avoids QGIS, GeoPandas, and any heavyweight stack. Only
dependencies are shapely (pure Python, with optional C speedups) and
numpy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from shapely import wkt as shapely_wkt
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from austal_prep.config import GridSpec


@dataclass
class CellWeights:
    """Per-source spatial distribution.

    indices: int32 array shape (N, 3) of (i, j, k) cell coordinates.
        i = x-cell index (0..nx-1)
        j = y-cell index (0..ny-1)
        k = z-cell index (0..n_layers-1)
    weights: float64 array shape (N,) summing to 1.0.
    bbox_metres: (x_min, y_min, x_max, y_max) in grid CRS.
    """

    indices: np.ndarray
    weights: np.ndarray
    bbox_metres: Tuple[float, float, float, float]


def _iter_primitives(geom: BaseGeometry) -> Iterable[Tuple[BaseGeometry, float]]:
    """Yield (sub-geometry, weight) pairs.

    For a Multi-geometry, weight is the sub-geometry's length/area share
    of the total. For a simple geometry, weight is 1.0.
    """
    if isinstance(geom, MultiLineString):
        total = geom.length
        for g in geom.geoms:
            sub = g.length
            yield g, sub / total if total > 0 else 0.0
    elif isinstance(geom, MultiPolygon):
        total = geom.area
        for g in geom.geoms:
            sub = g.area
            yield g, sub / total if total > 0 else 0.0
    elif isinstance(geom, MultiPoint):
        n = len(geom.geoms)
        for g in geom.geoms:
            yield g, 1.0 / n if n > 0 else 0.0
    else:
        yield geom, 1.0


def _xy_indices_from_bbox(
    bbox: Tuple[float, float, float, float], grid: GridSpec
) -> Iterable[Tuple[int, int]]:
    """Yield (i, j) cell indices that overlap a bbox in grid CRS metres.

    Indices outside the grid are skipped. The grid origin is at
    (grid.x0, grid.y0); cell (i, j) covers
    [x0 + i*dd, x0 + (i+1)*dd] × [y0 + j*dd, y0 + (j+1)*dd].
    """
    xmin, ymin, xmax, ymax = bbox
    i_min = max(0, int((xmin - grid.x0) // grid.dd))
    i_max = min(grid.nx - 1, int((xmax - grid.x0) // grid.dd))
    j_min = max(0, int((ymin - grid.y0) // grid.dd))
    j_max = min(grid.ny - 1, int((ymax - grid.y0) // grid.dd))
    for i in range(i_min, i_max + 1):
        for j in range(j_min, j_max + 1):
            yield i, j


def _cell_polygon(i: int, j: int, grid: GridSpec) -> Polygon:
    x_lo = grid.x0 + i * grid.dd
    x_hi = x_lo + grid.dd
    y_lo = grid.y0 + j * grid.dd
    y_hi = y_lo + grid.dd
    return Polygon([(x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi)])


def _xy_efficiency(geom: BaseGeometry, i: int, j: int, grid: GridSpec) -> float:
    """Efficiency in (i, j) cell, in 0..1.

    Point: 1.0 if the point falls inside the cell, 0 otherwise.
    Line: cell-clipped length / total length.
    Polygon: cell-clipped area / total area.

    For a Multi-geometry the caller should already have decomposed via
    _iter_primitives and reweighted.
    """
    cell = _cell_polygon(i, j, grid)

    if isinstance(geom, Point):
        # Use intersects rather than contains — points exactly on the
        # cell boundary should still be assigned to one cell.
        return 1.0 if cell.intersects(geom) else 0.0

    if isinstance(geom, LineString):
        total = geom.length
        if total == 0:
            return 0.0
        clipped = geom.intersection(cell)
        return clipped.length / total

    if isinstance(geom, Polygon):
        total = geom.area
        if total == 0:
            return 0.0
        clipped = geom.intersection(cell)
        return clipped.area / total

    raise TypeError(f"Unsupported simple geometry type: {type(geom).__name__}")


def _z_layers_for_source(
    z_min: float, z_max: float, grid: GridSpec
) -> List[Tuple[int, float]]:
    """Distribute the source's vertical extent across grid layers.

    Returns list of (k, weight) pairs where weight is the fraction of
    the [z_min, z_max] extent that falls into vertical layer k.

    For z_min == z_max (point release): pick the layer containing
    z_min and assign weight 1.0.
    """
    sk = grid.sk
    n_layers = grid.n_layers

    if z_min == z_max:
        # Point in z. Locate the layer.
        for k in range(n_layers):
            if sk[k] <= z_min < sk[k + 1]:
                return [(k, 1.0)]
        # If z is exactly at the top of the highest layer, assign there
        if z_min == sk[-1]:
            return [(n_layers - 1, 1.0)]
        # Out of range
        return []

    extent = z_max - z_min
    out: List[Tuple[int, float]] = []
    for k in range(n_layers):
        lo, hi = sk[k], sk[k + 1]
        overlap_lo = max(lo, z_min)
        overlap_hi = min(hi, z_max)
        if overlap_hi > overlap_lo:
            out.append((k, (overlap_hi - overlap_lo) / extent))
    return out


def compute_cell_weights(
    wkt_grid_crs: str,
    grid: GridSpec,
    height_m: float = 0.0,
    delta_z_m: float = 0.0,
) -> Optional[CellWeights]:
    """Decompose a WKT geometry into grid cell weights summing to 1.0.

    wkt_grid_crs: WKT string in the CALCULATION GRID CRS (typically a
        local UTM projection in metres). NOT EPSG:3857. The caller is
        responsible for reprojecting before calling this function.

    height_m: ground-level release height of the source (m above
        ground). Defaults to 0 (surface release).

    delta_z_m: vertical extent above height_m (m). Defaults to 0
        (point release in z). For an area or line source at ground
        level both default to 0 and the source occupies only the
        lowest grid layer.

    Returns None if the geometry falls entirely outside the grid in
    horizontal or vertical extent.
    """
    geom = make_valid(shapely_wkt.loads(wkt_grid_crs))
    if geom.is_empty:
        return None

    # Vertical layer distribution: shared across all (i, j) cells of
    # this source because we treat the source as having a uniform
    # vertical density.
    z_layers = _z_layers_for_source(height_m, height_m + delta_z_m, grid)
    if not z_layers:
        return None

    # Horizontal: iterate primitives, accumulate per-cell xy weight.
    # Use a dict keyed by (i, j) so multi-geometry sub-pieces in the
    # same cell stack additively.
    xy_weight: Dict[Tuple[int, int], float] = {}
    for primitive, sub_weight in _iter_primitives(geom):
        if sub_weight == 0:
            continue
        if primitive.is_empty:
            continue
        bbox = primitive.bounds
        for i, j in _xy_indices_from_bbox(bbox, grid):
            eff = _xy_efficiency(primitive, i, j, grid)
            if eff > 0:
                xy_weight[(i, j)] = xy_weight.get((i, j), 0.0) + sub_weight * eff

    if not xy_weight:
        return None

    # Combine xy and z. Total cells = len(xy_weight) * len(z_layers).
    indices: List[Tuple[int, int, int]] = []
    weights: List[float] = []
    for (i, j), w_xy in xy_weight.items():
        for k, w_z in z_layers:
            indices.append((i, j, k))
            weights.append(w_xy * w_z)

    indices_arr = np.asarray(indices, dtype=np.int32)
    weights_arr = np.asarray(weights, dtype=np.float64)

    # Normalise to sum=1.0 to absorb any floating-point drift from the
    # bbox/intersection arithmetic. The reference AUSTAL files have
    # exactly sum=1.0 per source.
    total = weights_arr.sum()
    if total <= 0:
        return None
    weights_arr /= total

    return CellWeights(
        indices=indices_arr,
        weights=weights_arr,
        bbox_metres=geom.bounds,
    )


def build_spatial_distribution(
    sources_grid_crs: Dict[str, dict],
    grid: GridSpec,
) -> Dict[str, CellWeights]:
    """Compute CellWeights for every source.

    sources_grid_crs: dict keyed by source_id with values:
        {
            "wkt": str,             # WKT in grid CRS (UTM metres)
            "height_m": float,      # ground-level release height
            "delta_z_m": float,     # vertical extent above height
        }

    Returns dict keyed by source_id with CellWeights values. Sources
    falling outside the grid are omitted (caller can subtract input
    keys from output keys to detect them).
    """
    out: Dict[str, CellWeights] = {}
    for source_id, src in sources_grid_crs.items():
        cw = compute_cell_weights(
            wkt_grid_crs=src["wkt"],
            grid=grid,
            height_m=src.get("height_m", 0.0),
            delta_z_m=src.get("delta_z_m", 0.0),
        )
        if cw is not None:
            out[source_id] = cw
    return out
