"""
austal_aircraft: AUSTAL input for aircraft emissions (Phase A5).

This module bridges the Phase A3 gridded aircraft emissions to the
`austal_prep` package, so aircraft emissions reach AUSTAL through the
same path the stationary sources already use.

The shape of the problem
------------------------
`austal_prep` is source-based. It reads two parquet files:

  sources.parquet      one row per emitting source: a `source_id`, a
                       geometry (`geometry_wkt` in EPSG:3857, plus a
                       `geometry_kind`), a height, an in-study flag.
  emissions.parquet    long form: one row per (timestamp, source_id,
                       pollutant) with the hourly emission in
                       `kg_in_hour`.

It joins the two on `source_id`, pivots the emissions to an hourly
g/s rate array, and writes the AUSTAL input files. The stationary
computes already produce exactly this pair, so stationary sources
flow straight through.

Aircraft emissions, after Phase A3, are not source-based: they are a
*grid*. `distribute.distribute_to_grid` produces per-(time bucket,
grid cell, pollutant) emission. To feed `austal_prep` unchanged, each
occupied grid cell is turned into a synthetic area source:

  - `source_id` is `aircraft:cell:<ix>_<iy>_<iz>`. The `aircraft:`
    prefix keeps the namespace distinct from `road:`, `parking:`,
    `gate:`, `point:`, `area:`, so a combined sources.parquet has no
    id collisions and a consumer can tell aircraft pseudo-sources
    apart. The trailing `_<iz>` encodes the AUSTAL vertical layer
    the source releases into so a column of stacked 3D sources at
    the same (ix, iy) stays distinct.
  - the geometry is the grid cell's polygon in EPSG:3857, so
    `geometry_kind` is `polygon`. A gridded emission is naturally an
    area source: the emission is spread over the cell, not at a
    point. This matches how `austal_prep` already treats area
    sources.
  - the emission rows are that cell's hourly `kg_in_hour` series.

The result is that aircraft emissions become "just more area
sources" as far as `austal_prep` is concerned. No change to
`austal_prep` is needed.

Hourly only
-----------
AUSTAL consumes hourly emission series. Phase A3's `distribute_to_grid`
can bin at sub-hour resolution, but that capability is for general
emission-results output, not for AUSTAL. This module always calls
`distribute_to_grid` with the default one-hour interval and asserts
the result is hourly (via `distribute.assert_hourly_for_austal`)
before writing anything. A sub-hour interval cannot reach the AUSTAL
files through this module.

Scope
-----
This module produces the aircraft half of the AUSTAL `sources.parquet`
and `emissions.parquet`. Combining it with the stationary half (from
`orchestrate`) into one pair of files, and running `austal_prep`
itself, are separate steps; `build_aircraft_austal_tables` returns the
two DataFrames so a caller can concatenate them with the stationary
tables or write them alone.

This module imports only the standalone's own packages, pandas, and
the standard library. No QGIS and no PyQt.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from openalaqs_standalone import compute_movements as _cm
from openalaqs_standalone import distribute as _dist

POLLUTANTS = _cm.POLLUTANTS

# AUSTAL default vertical grid (sk values, m above ground). Mirrors
# DEFAULT_SK in make_config.py — kept here too so this module is
# self-contained for callers that build the AUSTAL tables without
# also constructing a make_config dict (e.g. tests).
DEFAULT_SK = [
    0,
    3,
    6,
    10,
    16,
    25,
    40,
    65,
    100,
    150,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    1000,
    1200,
    1500,
]

# The synthetic source-id prefix for an aircraft grid cell. A cell at
# index (ix, iy, iz) becomes the source id
# f"{_CELL_SOURCE_PREFIX}{ix}_{iy}_{iz}". (Earlier 2D versions used
# "{ix}_{iy}"; the trailing _<iz> is a strict suffix so existing
# substring matches on "aircraft:cell:" still work.)
_CELL_SOURCE_PREFIX = "aircraft:cell:"

# Column schemas, fixed to match what austal_prep's loaders require.
# emissions.parquet: the loader's `required` set is exactly these four.
_EMISSIONS_COLUMNS = ["timestamp", "source_id", "pollutant", "kg_in_hour"]
# sources.parquet: the loader's `required` set is source_id,
# source_type, geometry_wkt, geometry_kind, height_m, in_study; the
# stationary extractor also writes label, extent_m2, length_m,
# extra_json, so the full set is written here too for a uniform file.
# delta_z_m is an optional column the loader reads via getattr; the
# aircraft path populates it to encode per-z-layer release height
# extent.
_SOURCES_COLUMNS = [
    "source_id",
    "source_type",
    "label",
    "geometry_wkt",
    "geometry_kind",
    "height_m",
    "delta_z_m",
    "extent_m2",
    "length_m",
    "in_study",
    "extra_json",
]


def cell_source_id(ix: int, iy: int, iz: int = 0) -> str:
    """Return the synthetic source id for grid cell (ix, iy, iz).

    iz defaults to 0 for callers from the pre-3D era; the AUSTAL
    pipeline always passes an explicit iz so each (ix, iy, iz) cell
    has a distinct source.
    """
    return f"{_CELL_SOURCE_PREFIX}{ix}_{iy}_{iz}"


def cell_polygon_wkt(
    ix: int,
    iy: int,
    grid_bounds: dict,
    grid_definition: dict,
) -> str:
    """Return the EPSG:3857 polygon WKT for grid cell (ix, iy).

    The cell is the axis-aligned rectangle
        [x_min + ix*cell_w, x_min + (ix+1)*cell_w]
      x [y_min + iy*cell_h, y_min + (iy+1)*cell_h]
    with the ring closed (first vertex repeated last), south-west
    corner first, counter-clockwise. The grid arithmetic matches
    `distribute.cell_index` exactly, so a point binned into (ix, iy)
    by `cell_index` lies within the polygon this returns.
    """
    x_cells = int(grid_definition["x_cells"])
    y_cells = int(grid_definition["y_cells"])
    x_min = grid_bounds["x_min"]
    y_min = grid_bounds["y_min"]
    cell_w = (grid_bounds["x_max"] - x_min) / x_cells
    cell_h = (grid_bounds["y_max"] - y_min) / y_cells

    x0 = x_min + ix * cell_w
    x1 = x_min + (ix + 1) * cell_w
    y0 = y_min + iy * cell_h
    y1 = y_min + (iy + 1) * cell_h

    # Closed ring, SW -> SE -> NE -> NW -> SW (counter-clockwise).
    return f"POLYGON (({x0} {y0}, {x1} {y0}, {x1} {y1}, " f"{x0} {y1}, {x0} {y0}))"


def build_aircraft_austal_tables(
    results: dict,
    conn,
    grid_bounds: dict,
    grid_definition: dict,
    time_window: tuple | None = None,
    sk: list | None = None,
    source_dynamics: str = "none",
) -> tuple:
    """Build the aircraft `emissions` and `sources` tables for AUSTAL.

    Turns the Phase A0 per-movement results into the source-based pair
    of DataFrames that `austal_prep` consumes, by gridding the
    aircraft emissions (Phase A3) and treating each occupied (ix, iy,
    iz) grid cell as a synthetic area source. The vertical axis (iz)
    is encoded in the source's height_m (= sk[iz]) and delta_z_m
    (= sk[iz+1] - sk[iz]); compute_cell_weights in austal_prep reads
    these and places the source's mass in the matching AUSTAL z-layer
    when building the dmna.

    Parameters
    ----------
    results
        The dict from `compute_movements.compute_all_movements`.
    conn
        An open `.alaqs` connection (passed through to
        `distribute_to_grid`).
    grid_bounds
        The dict from `geometry.grid_bounds_3857`, also available as
        `build_context(conn)["grid_bounds"]`.
    grid_definition
        The dict from `movements.get_grid_definition`.
    time_window
        Optional (start, end) tuple; half-open window. Bucket rows
        outside the window are dropped (a movement at 13:55 on the
        last day may have segments that emit after the window end).
    sk
        Optional AUSTAL vertical layer boundary list (length k+1 for
        k layers). When omitted, DEFAULT_SK is used. The list must
        match the AUSTAL run's sk; otherwise the z-layer indices in
        the synthetic source heights will not align with the dmna
        layers AUSTAL writes.

    Returns
    -------
    (emissions_df, sources_df)

    emissions_df has columns timestamp, source_id, pollutant,
    kg_in_hour: one row per (hour, occupied (ix,iy,iz) cell,
    pollutant) that carries non-zero emission. `timestamp` is the
    bucket start.

    sources_df has the full sources.parquet column set with the new
    delta_z_m column: one row per occupied (ix, iy, iz) cell,
    `source_type` "aircraft", `geometry_kind` "polygon",
    `geometry_wkt` the cell polygon in EPSG:3857, `height_m` =
    sk[iz], `delta_z_m` = sk[iz+1] - sk[iz], `in_study` True.
    `extent_m2` is the cell area; `length_m` is 0.0; `label` echoes
    the source_id; `extra_json` is "{}".

    Both tables are empty (with the right columns) if `results` is
    empty or no cell receives emission.
    """
    if sk is None:
        sk = DEFAULT_SK
    n_layers = len(sk) - 1

    # Grid at hourly resolution -- the AUSTAL requirement. Do not
    # expose a bin_interval parameter here: a sub-hour grid must never
    # become AUSTAL input, and the clearest way to guarantee that is
    # to not offer the option on the AUSTAL path at all. Pass `sk` so
    # distribute_to_grid apportions segment emissions across z-layers
    # (Issue 3 vertical distribution).
    gridded = _dist.distribute_to_grid(
        results,
        conn,
        grid_bounds,
        grid_definition,
        bin_interval=timedelta(hours=1),
        sk=sk,
        source_dynamics=source_dynamics,
    )
    # Belt and braces: confirm hourly before building anything. If a
    # future change to distribute_to_grid ever broke the hourly
    # guarantee, this fails loudly here rather than producing AUSTAL
    # input AUSTAL cannot use.
    _dist.assert_hourly_for_austal(gridded)

    # Per-segment window filter. The caller already filtered movements
    # by start time before invoking compute_movements; here we also
    # drop the per-bucket emission rows that fall outside the window.
    # This is the dispersion-correct interpretation: a movement
    # starting at 13:55 on the last day of the window will have some
    # of its segments emit after the window end, and those segments
    # are correctly excluded. Half-open convention matches
    # _profiles.window_mask.
    if time_window is not None and not gridded.empty:
        _start, _end = time_window
        _ts = gridded["bucket_start"]
        _mask = pd.Series(True, index=gridded.index)
        if _start is not None:
            _mask &= _ts >= pd.Timestamp(_start)
        if _end is not None:
            _mask &= _ts < pd.Timestamp(_end)
        gridded = gridded[_mask].reset_index(drop=True)

    if gridded.empty:
        return (
            pd.DataFrame(columns=_EMISSIONS_COLUMNS),
            pd.DataFrame(columns=_SOURCES_COLUMNS),
        )

    # ---- emissions table ----
    # distribute_to_grid (now sk-aware) gives one row per (bucket, ix,
    # iy, iz, pollutant) with non-zero kg. Rename to the
    # emissions.parquet column names and attach the synthetic source
    # id which now embeds iz so per-layer sources stay distinct.
    emissions_df = gridded.copy()
    emissions_df["source_id"] = [
        cell_source_id(int(ix), int(iy), int(iz))
        for ix, iy, iz in zip(
            emissions_df["ix"], emissions_df["iy"], emissions_df["iz"]
        )
    ]
    emissions_df = emissions_df.rename(
        columns={"bucket_start": "timestamp", "kg": "kg_in_hour"}
    )
    emissions_df = emissions_df[_EMISSIONS_COLUMNS].reset_index(drop=True)

    # ---- sources table ----
    # One row per occupied (ix, iy, iz) cell. The set of occupied
    # cells is exactly the distinct (ix, iy, iz) triples in the
    # gridded emissions. Each cell becomes a single source whose
    # horizontal footprint is the 2D cell polygon and whose vertical
    # release window is the iz-th AUSTAL layer [sk[iz], sk[iz+1]).
    # austal_prep's compute_cell_weights reads height_m + delta_z_m
    # and places the source's mass in the matching dmna z-layer; the
    # by-type aggregator then merges all aircraft cells into a
    # single AUSTAL source with full 3D weights.
    x_cells = int(grid_definition["x_cells"])
    y_cells = int(grid_definition["y_cells"])
    cell_w = (grid_bounds["x_max"] - grid_bounds["x_min"]) / x_cells
    cell_h = (grid_bounds["y_max"] - grid_bounds["y_min"]) / y_cells
    cell_area_m2 = cell_w * cell_h

    occupied = (
        gridded[["ix", "iy", "iz"]]
        .drop_duplicates()
        .sort_values(["ix", "iy", "iz"])
        .reset_index(drop=True)
    )
    source_rows = []
    for ix, iy, iz in zip(occupied["ix"], occupied["iy"], occupied["iz"]):
        ix_i, iy_i, iz_i = int(ix), int(iy), int(iz)
        # Guard against an iz that somehow exceeds the sk range; in
        # practice _iz_layer_fractions clamps to top layer so this
        # is defensive only.
        if iz_i < 0 or iz_i >= n_layers:
            iz_i = max(0, min(iz_i, n_layers - 1))
        sid = cell_source_id(ix_i, iy_i, iz_i)
        z_base = float(sk[iz_i])
        z_top = float(sk[iz_i + 1])
        source_rows.append(
            {
                "source_id": sid,
                "source_type": "aircraft",
                "label": sid,
                "geometry_wkt": cell_polygon_wkt(
                    ix_i, iy_i, grid_bounds, grid_definition
                ),
                "geometry_kind": "polygon",
                "height_m": z_base,
                "delta_z_m": z_top - z_base,
                "extent_m2": cell_area_m2,
                "length_m": 0.0,
                "in_study": True,
                "extra_json": "{}",
            }
        )
    sources_df = pd.DataFrame(source_rows, columns=_SOURCES_COLUMNS)

    return emissions_df, sources_df
