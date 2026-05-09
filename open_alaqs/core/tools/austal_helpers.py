"""
austal_helpers: pure-function helpers for the AUSTAL time-indexed
output path.

Reimplements (does NOT import) the maths from
`austal_prep/{spatial,aggregation,writers/grid_files}.py`, keeping
the plugin self-contained while letting `AUSTALOutputModule` write
grid files in the time-indexed layout AUSTAL consumes natively.

Module boundary
---------------
- IS  pure functions and one dataclass. No QGIS imports. No file I/O.
       The actual file writing lives in `AUSTALOutputModule` so it can
       continue to use the existing output-path conventions.
- IS  numpy + shapely only. Both are already plugin dependencies.
- ISN'T a replacement for `core/tools/spatial.py`, which serves the
        per-hour `getMatchedCellCoeffs` path used for non-stationary
        sources (movements / gates / taxiways).

Contents
--------
    AustalGridSpec                — dataclass describing the calc grid
                                    in the form the helpers consume.
    CellWeights                   — sparse (i,j,k) → weight, sum=1.0
    compute_cell_weights(...)     — WKT (UTM metres) → CellWeights
    aggregate_sources_by_type(...)— group sources by `<type>:` prefix,
                                    emission-weighted spatial combine
    expand_to_dense(...)          — sparse → dense (nx, ny, nz)
    serialise_dense_kji(...)      — dense → list of text lines in
                                    AUSTAL's k+,j-,i+ order
    format_time_offset(...)       — datetime → AUSTAL "D.HH:MM:SS"
    format_grid_value(...)        — float → AUSTAL-compatible repr

Reference for invariants
------------------------
- CellWeights.weights summing to 1.0 — required by AUSTAL's grid file
  format ("relative spatial distribution"). The renormalisation step
  in compute_cell_weights absorbs floating-point drift.
- "k+,j-,i+" data ordering matches every reference e0001.dmna in the
  AUSTAL ecosystem (verified against austal_prep's reference files).
- `aggregate_sources_by_type`'s spatial combination is
  emission-weighted: combined_weight(cell) = sum_i(annual_i *
  weight_i(cell)) / sum_i(annual_i). Preserves total emitted mass per
  cell exactly when the underlying spatial distributions are
  time-invariant — which is the precondition for stationary sources.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
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

__all__ = [
    "AustalGridSpec",
    "CellWeights",
    "compute_cell_weights",
    "aggregate_sources_by_type",
    "expand_to_dense",
    "format_grid_value",
    "serialise_dense_kji",
    "format_time_offset",
    "grid_file_header_lines",
    "iq_value_for_hour",
    "KG_PER_HOUR_TO_G_PER_S",
]


# -----------------------------------------------------------------------------
# Data structures
# -----------------------------------------------------------------------------


@dataclass
class AustalGridSpec:
    """Calc-grid description in the canonical form the helpers expect.

    Mirrors `austal_prep.config.GridSpec` so the maths is portable, but
    populated from the plugin's `Grid3D` object via
    `AustalGridSpec.from_grid3d` rather than from a parquet header.

    dd        : horizontal mesh width (m). AUSTAL requires square cells.
    nx, ny    : horizontal cell counts.
    x0, y0    : south-west corner of the calc grid in metres relative to
                the user's reference point. With the plugin's
                `DEFAULT_CONCENTRATION_GRID_FACTOR=2` halo this is
                `-((nx/2 + 2) * dd)` for symmetric grids.
    sk        : vertical level top heights (m), length n_layers + 1.
    """
    dd: float
    nx: int
    ny: int
    x0: float
    y0: float
    sk: Tuple[float, ...]

    @property
    def n_layers(self) -> int:
        return len(self.sk) - 1


@dataclass
class CellWeights:
    """Per-source spatial distribution in sparse form.

    indices : int32 (N, 3) of (i, j, k) cell coordinates in the calc
              grid frame. i = x-cell (0..nx-1), j = y-cell (0..ny-1),
              k = z-layer (0..n_layers-1).
    weights : float64 (N,) summing to 1.0.
    bbox_m  : (xmin, ymin, xmax, ymax) in grid-CRS metres, useful for
              audits and for the source dispatch in austal.txt.
    """
    indices: np.ndarray
    weights: np.ndarray
    bbox_m: Tuple[float, float, float, float]


# -----------------------------------------------------------------------------
# Spatial: WKT -> CellWeights
# -----------------------------------------------------------------------------


def _iter_primitives(geom: BaseGeometry) -> Iterable[Tuple[BaseGeometry, float]]:
    """Yield (sub-geometry, weight) pairs.

    For a Multi-geometry, weight is the sub-geometry's length/area
    share of the total. Simple geometries pass through with weight=1.
    Mirrors `austal_prep.spatial._iter_primitives` behaviour.
    """
    if isinstance(geom, MultiLineString):
        total = geom.length
        for g in geom.geoms:
            yield g, (g.length / total) if total > 0 else 0.0
    elif isinstance(geom, MultiPolygon):
        total = geom.area
        for g in geom.geoms:
            yield g, (g.area / total) if total > 0 else 0.0
    elif isinstance(geom, MultiPoint):
        n = len(geom.geoms)
        for g in geom.geoms:
            yield g, (1.0 / n) if n > 0 else 0.0
    else:
        yield geom, 1.0


def _xy_indices_from_bbox(
    bbox: Tuple[float, float, float, float], grid: AustalGridSpec
) -> Iterable[Tuple[int, int]]:
    """Yield (i, j) cell indices that overlap a primitive's bbox.

    Indices outside [0, nx) x [0, ny) are skipped. Cell (i, j) covers
    [x0 + i*dd, x0 + (i+1)*dd] x [y0 + j*dd, y0 + (j+1)*dd].
    """
    xmin, ymin, xmax, ymax = bbox
    i_min = max(0, int((xmin - grid.x0) // grid.dd))
    i_max = min(grid.nx - 1, int((xmax - grid.x0) // grid.dd))
    j_min = max(0, int((ymin - grid.y0) // grid.dd))
    j_max = min(grid.ny - 1, int((ymax - grid.y0) // grid.dd))
    for i in range(i_min, i_max + 1):
        for j in range(j_min, j_max + 1):
            yield i, j


def _cell_polygon(i: int, j: int, grid: AustalGridSpec) -> Polygon:
    x_lo = grid.x0 + i * grid.dd
    x_hi = x_lo + grid.dd
    y_lo = grid.y0 + j * grid.dd
    y_hi = y_lo + grid.dd
    return Polygon([(x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi)])


def _xy_efficiency(
    geom: BaseGeometry, i: int, j: int, grid: AustalGridSpec
) -> float:
    """Fraction of `geom` that falls inside cell (i, j), in [0, 1]."""
    cell = _cell_polygon(i, j, grid)

    if isinstance(geom, Point):
        # `intersects` so that boundary-coincident points still get
        # assigned to one cell.
        return 1.0 if cell.intersects(geom) else 0.0

    if isinstance(geom, LineString):
        total = geom.length
        if total == 0:
            return 0.0
        return geom.intersection(cell).length / total

    if isinstance(geom, Polygon):
        total = geom.area
        if total == 0:
            return 0.0
        return geom.intersection(cell).area / total

    raise TypeError(
        f"Unsupported simple geometry type: {type(geom).__name__}. "
        "Multi-geometries should be decomposed via _iter_primitives."
    )


def _z_layers_for_source(
    z_min: float, z_max: float, grid: AustalGridSpec
) -> List[Tuple[int, float]]:
    """Distribute a source's vertical extent across grid layers.

    Returns list of (k, weight) where weight is the fraction of
    [z_min, z_max] that overlaps layer k. Point release (z_min ==
    z_max) goes entirely to the layer containing z_min; sources whose
    extent falls outside the grid altogether yield an empty list.
    """
    sk = grid.sk
    n_layers = grid.n_layers

    if z_min == z_max:
        for k in range(n_layers):
            if sk[k] <= z_min < sk[k + 1]:
                return [(k, 1.0)]
        if z_min == sk[-1]:
            return [(n_layers - 1, 1.0)]
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
    grid: AustalGridSpec,
    height_m: float = 0.0,
    delta_z_m: float = 0.0,
) -> Optional[CellWeights]:
    """WKT (in calc-grid CRS metres) → sparse CellWeights summing to 1.

    The caller is responsible for any reprojection from EPSG:3857 (the
    plugin's storage CRS) to the calc-grid CRS (UTM metres). The
    plugin's `AUSTALOutputModule._transform_wkt_to_utm` does this.

    Returns None if the geometry is empty, falls entirely outside the
    horizontal grid, or has no vertical overlap with any layer.

    Time-invariant: stationary sources can cache the result and reuse
    it for every hour of the run.
    """
    geom = make_valid(shapely_wkt.loads(wkt_grid_crs))
    if geom.is_empty:
        return None

    z_layers = _z_layers_for_source(height_m, height_m + delta_z_m, grid)
    if not z_layers:
        return None

    # Horizontal accumulation. Multi-geometry sub-pieces falling in the
    # same (i, j) cell stack additively.
    xy_weight: Dict[Tuple[int, int], float] = {}
    for primitive, sub_weight in _iter_primitives(geom):
        if sub_weight == 0 or primitive.is_empty:
            continue
        for i, j in _xy_indices_from_bbox(primitive.bounds, grid):
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

    total = weights_arr.sum()
    if total <= 0:
        return None

    # Renormalise to sum=1.0 to absorb FP drift from intersection
    # arithmetic. AUSTAL reference files have exactly sum=1.0.
    weights_arr /= total

    return CellWeights(
        indices=indices_arr,
        weights=weights_arr,
        bbox_m=geom.bounds,
    )


# -----------------------------------------------------------------------------
# Aggregation: per-source weights + rates -> per-group weights + rates
# -----------------------------------------------------------------------------


def _group_key_by_type(source_id: str) -> str:
    """Group key = prefix before the first ':' in source_id.

    `road:OostSidelinge_001` → `road`
    `parking:ES.1`           → `parking`
    `bare_id_no_prefix`      → `bare_id_no_prefix` (own group)
    """
    return source_id.split(":", 1)[0] if ":" in source_id else source_id


def _combine_cell_weights(
    constituents: List[Tuple[CellWeights, float]],
) -> CellWeights:
    """Emission-weighted spatial combination of N constituent CellWeights.

    constituents : list of (CellWeights, annual_total_emission) pairs.
                   Annual totals weight the spatial averaging.

    Returns a CellWeights with weights renormalised to sum=1.0 and
    bbox = union of constituent bboxes. Single-element input passes
    through unchanged. Zero-emission constituents fall back to uniform
    weighting so the result still has a usable cell pattern.
    """
    if not constituents:
        raise ValueError("Cannot combine zero constituents.")
    if len(constituents) == 1:
        return constituents[0][0]

    total_emission = sum(e for _, e in constituents)
    if total_emission <= 0:
        return _combine_cell_weights([(cw, 1.0) for cw, _ in constituents])

    accum: Dict[Tuple[int, int, int], float] = {}
    bbox_xmin = float("inf")
    bbox_ymin = float("inf")
    bbox_xmax = float("-inf")
    bbox_ymax = float("-inf")

    for cw, e in constituents:
        if e <= 0:
            continue
        for (i, j, k), w in zip(cw.indices, cw.weights):
            key = (int(i), int(j), int(k))
            accum[key] = accum.get(key, 0.0) + e * float(w)
        bx0, by0, bx1, by1 = cw.bbox_m
        bbox_xmin = min(bbox_xmin, bx0)
        bbox_ymin = min(bbox_ymin, by0)
        bbox_xmax = max(bbox_xmax, bx1)
        bbox_ymax = max(bbox_ymax, by1)

    if not accum:
        raise ValueError(
            "Combined cell weights are empty — all constituents had "
            "zero emission and zero geometry."
        )

    indices = np.array(list(accum.keys()), dtype=np.int32)
    weights = np.array(list(accum.values()), dtype=np.float64)
    weights /= weights.sum()

    return CellWeights(
        indices=indices,
        weights=weights,
        bbox_m=(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax),
    )


def aggregate_sources_by_type(
    source_ids: List[str],
    cell_weights: Dict[str, CellWeights],
    rates: np.ndarray,
) -> Tuple[List[str], Dict[str, CellWeights], np.ndarray]:
    """Group sources by `<type>:` prefix, combine spatial weights with
    emission weighting, sum hourly rates across constituents.

    Parameters
    ----------
    source_ids : list of `<type>:<bare_id>` strings, in the order they
                 appear along the source axis of `rates`.
    cell_weights : `{source_id: CellWeights}`. Must contain every
                   entry in `source_ids`.
    rates : ndarray (n_hours, n_sources, n_pollutants), in g/s.

    Returns
    -------
    (new_source_ids, new_cell_weights, new_rates)
        - `new_source_ids` is the sorted list of group IDs.
        - `new_cell_weights[gid]` is the emission-weighted combined
          spatial pattern for group `gid`.
        - `new_rates` has shape (n_hours, n_groups, n_pollutants); the
          source axis is in the same order as `new_source_ids`.

    Why this matters
    ----------------
    AUSTAL's DMNA reader has a fixed line buffer. With many sources ×
    pollutants in a single `series.dmna`, the form line grows linearly
    with sources × pollutants and overflows. Grouping by type keeps
    the file small without losing the temporal distinction between
    types (which differs sharply between e.g. roadway daily curves and
    parking weekly curves).
    """
    groups: Dict[str, List[int]] = {}
    for s_idx, sid in enumerate(source_ids):
        gid = _group_key_by_type(sid)
        groups.setdefault(gid, []).append(s_idx)

    new_source_ids = sorted(groups.keys())
    n_hours, _, n_pol = rates.shape

    # Per-source annual totals across all hours and pollutants
    # (proportional to annual mass; sign-stable for the weighted
    # average step).
    per_source_annual = rates.sum(axis=(0, 2))

    new_rates = np.zeros(
        (n_hours, len(new_source_ids), n_pol), dtype=rates.dtype
    )
    new_cell_weights: Dict[str, CellWeights] = {}

    for new_idx, gid in enumerate(new_source_ids):
        member_indices = groups[gid]

        for src_idx in member_indices:
            new_rates[:, new_idx, :] += rates[:, src_idx, :]

        constituents = [
            (cell_weights[source_ids[src_idx]], float(per_source_annual[src_idx]))
            for src_idx in member_indices
        ]
        new_cell_weights[gid] = _combine_cell_weights(constituents)

    return new_source_ids, new_cell_weights, new_rates


# -----------------------------------------------------------------------------
# Dense expansion + AUSTAL-format serialisation
# -----------------------------------------------------------------------------


def expand_to_dense(
    weights: CellWeights,
    grid: AustalGridSpec,
    source_offset_cells: int = 0,
) -> np.ndarray:
    """Expand sparse CellWeights into a dense (nx, ny, n_layers) array.

    The grid file's frame is anchored at (xq, yq), where
    `xq = x0 + source_offset_cells * dd`. So a calc-grid cell at
    (i, j) maps to grid-file index (i - source_offset_cells,
    j - source_offset_cells). Indices that fall outside [0, nx) ×
    [0, ny) after shifting are silently dropped — those cells lie
    outside the source's grid-file footprint.

    Mirrors `austal_prep.writers.grid_files._expand_to_dense`.
    """
    arr = np.zeros((grid.nx, grid.ny, grid.n_layers), dtype=np.float64)
    nx, ny, nz = grid.nx, grid.ny, grid.n_layers
    for (i, j, k), w in zip(weights.indices, weights.weights):
        i_grid = i - source_offset_cells
        j_grid = j - source_offset_cells
        if 0 <= i_grid < nx and 0 <= j_grid < ny and 0 <= k < nz:
            arr[i_grid, j_grid, k] = w
    return arr


def format_grid_value(v: float) -> str:
    """Format one cell weight for an AUSTAL grid file body.

    Reference behaviour: zeros emit as "0.0"; non-zeros emit
    full-precision repr. Numpy 2.x's repr emits 'np.float64(...)'
    which AUSTAL won't parse — coerce to Python float first.
    """
    f = float(v)
    if f == 0.0:
        return "0.0"
    return repr(f)


def serialise_dense_kji(arr: np.ndarray) -> List[str]:
    """Serialise a dense (nx, ny, nz) array in AUSTAL's k+,j-,i+ order.

    Each output line is one (k, j) row of nx tab-separated values. A
    blank line separates k-blocks (matches the reference
    `e0001.dmna` byte-for-byte). Returns the lines as a list so the
    caller can join with the AUSTAL line terminator.
    """
    nx, ny, nz = arr.shape
    lines: List[str] = []
    for k in range(nz):
        for j in range(ny - 1, -1, -1):  # j descending
            row = arr[:, j, k]            # i ascending
            lines.append("\t".join(format_grid_value(v) for v in row))
        # Trailing blank between each k-slab matches the reference.
        lines.append("")
    return lines


def format_time_offset(ts: datetime, year_start: datetime) -> str:
    """Format a timestamp as 'D.HH:MM:SS' relative to year_start.

    AUSTAL convention for the t1/t2 fields in grid file headers.
    Day count is 0-based from year_start.
    """
    delta = ts - year_start
    return f"{delta.days}.{ts.strftime('%H:%M:%S')}"


# -----------------------------------------------------------------------------
# Header builders for grid files
# -----------------------------------------------------------------------------


def grid_file_header_lines(
    t1: str,
    t2: str,
    grid: AustalGridSpec,
) -> List[str]:
    """Build the header lines (everything above the data block) for an
    AUSTAL e????.dmna file. Matches the reference layout.

    The same shape works for both legacy mode (t1, t2 spanning a
    single hour) and time-indexed mode (t1, t2 spanning the full
    study period). The data block beneath has identical format in
    both modes; only t1/t2 and the surrounding `iq` semantics
    differ.
    """
    return [
        f"t1\t{t1}",
        f"t2\t{t2}",
        f"dd\t{grid.dd:g}",
        "sk\t" + " ".join(f"{s:g}" for s in grid.sk),
        "-",
        'mode\t"text"',
        'form\t"Eq%5.1f"',
        'vldf\t"V"',
        'artp\t"M"',
        "dims\t3",
        'axes\t"xyz"',
        "sequ\tk+,j-,i+",
        "-",
        "lowb\t1 1 1",
        f"hghb\t{grid.nx} {grid.ny} {grid.n_layers}",
        "*",
    ]


# -----------------------------------------------------------------------------
# Helpers for the time-indexed series.dmna iq column
# -----------------------------------------------------------------------------


def iq_value_for_hour(
    h_idx: int,
    is_time_invariant_source: bool,
) -> int:
    """Return the iq column value for one (source, hour) cell.

    - Time-invariant source (stationary; only e0001.dmna exists):
      iq = 1 always. AUSTAL reads the same spatial pattern for every
      hour; the temporal modulation is carried by the emission rate
      column.
    - Time-varying source (movement; one eNNNN.dmna per hour):
      iq = h_idx + 1, pointing at e0001..eNNNN.dmna respectively.
    """
    return 1 if is_time_invariant_source else h_idx + 1


KG_PER_HOUR_TO_G_PER_S: float = 1000.0 / 3600.0
"""Unit conversion constant: emission inventory is in kg/h; AUSTAL
expects g/s in series.dmna. Multiply kg/h by this constant."""
