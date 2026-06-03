"""
distribute: the per-time-bucket per-cell distribution layer (Phase A3).

This module turns the Phase A0 per-movement *totals* into per-(time
bucket, grid cell) emission *distributions* -- the step from output
mode "(a)" to output mode "(c)" in the strategy document.

What A0 produced
----------------
`compute_movements.compute_all_movements` returns, per movement, a
result dict whose `total_em_kg` is the whole-LTO emission summed over
every trajectory segment and the taxi phase. That is mode "(a)": one
number per movement per pollutant.

What A3 adds
------------
Two orthogonal axes of resolution:

  Time. Each movement is an event at a single instant -- its
    `runway_time`. A3 assigns the movement's emission to the time
    bucket that instant falls in. The bucket size is configurable via
    `bin_interval`:
      - bin_interval = 1 hour (the default) gives hourly results.
      - bin_interval = 15 minutes gives sub-hourly results, matching
        the sub-hour resolution the QGIS plugin's EmissionCalculation
        supports through its `time_interval` parameter.
    The emission physics does not change with bin size; only the
    granularity of the temporal binning does. A movement is treated
    as instantaneous at LTO timescale relative to even a 15-minute
    bucket, so its whole emission lands in one bucket. (If a future
    requirement needs a movement spread across buckets -- e.g. a long
    taxi phase straddling a bucket boundary -- that is a separate,
    additive change; it is not needed for parity with the plugin's
    current behaviour.)

  Space. `distribute_movements` keeps a movement's emission spatially
    lumped: one entry per movement, carrying the movement's identity
    and time bucket. `distribute_to_grid` adds the spatial axis: it
    walks each retained trajectory segment's clipped EPSG:3857
    geometry, finds the grid cells the segment crosses, and
    apportions the segment's emission across those cells by the
    fraction of the segment's length that falls in each. The result
    is per-(time bucket, grid cell, pollutant) emission -- the full
    "(c)" output. Helicopters have no trajectory segments, so their
    emission is placed at a single cell (the grid cell their
    runway/helipad position falls in); see `distribute_to_grid` for
    that case.

AUSTAL must stay hourly
-----------------------
AUSTAL consumes hourly emission series. The sub-hour capability is for
general emission-results output, NOT for AUSTAL input preparation. The
AUSTAL output path (Phase A5) must always call this module with
`bin_interval` left at its 1-hour default. `assert_hourly_for_austal`
is provided so the AUSTAL path can assert that invariant explicitly,
and `test_distribute.py` confirms the sub-hour capability does not
leak into the hourly path.

This module imports only the standalone's own packages, pandas, and
the standard library. No QGIS and no PyQt.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from openalaqs_standalone import compute_movements as _cm
from openalaqs_standalone import movements as _mv
from openalaqs_standalone import source_dynamics as _sd

# The six pollutants carried through from the A0 core.
POLLUTANTS = _cm.POLLUTANTS

# The default time-bucket size. One hour: the resolution AUSTAL needs
# and the resolution the per-movement-totals consumers expect unless
# they ask for finer.
DEFAULT_BIN_INTERVAL = timedelta(hours=1)

# The reference epoch for bucket-index arithmetic. Bucket boundaries
# are aligned to this instant, so a 1-hour interval gives buckets on
# the hour, a 15-minute interval gives buckets on :00/:15/:30/:45, and
# so on. Using a fixed epoch (rather than, say, the first movement's
# time) makes the binning deterministic and independent of which
# movements happen to be in the study.
_EPOCH = datetime(1970, 1, 1, 0, 0, 0)


def _parse_runway_time(s: str) -> datetime:
    """Parse a movement `runway_time` string to a datetime.

    The `.alaqs` stores these as 'YYYY-MM-DD HH:MM:SS'. This matches
    `compute_aircraft._parse_dt`; it is duplicated here rather than
    imported so the distribution layer does not depend on the
    fixed-wing compute module.
    """
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def bucket_start(when: datetime, bin_interval: timedelta) -> datetime:
    """Return the start instant of the time bucket `when` falls in.

    Buckets are aligned to `_EPOCH` and are `bin_interval` wide. The
    bucket is half-open `[start, start + bin_interval)`, so an instant
    exactly on a boundary belongs to the bucket that boundary opens.

    Examples, with bin_interval = 15 minutes:
        06:05:00 -> 06:00:00
        06:14:59 -> 06:00:00
        06:15:00 -> 06:15:00
    """
    interval_s = bin_interval.total_seconds()
    if interval_s <= 0:
        raise ValueError(f"bin_interval must be positive, got {bin_interval!r}")
    elapsed_s = (when - _EPOCH).total_seconds()
    bucket_index = int(elapsed_s // interval_s)
    return _EPOCH + timedelta(seconds=bucket_index * interval_s)


def distribute_movements(
    results: dict,
    conn,
    bin_interval: timedelta = DEFAULT_BIN_INTERVAL,
) -> pd.DataFrame:
    """Bin per-movement emission totals into time buckets.

    Parameters
    ----------
    results
        The dict returned by `compute_movements.compute_all_movements`:
        oid -> per-movement result dict.
    conn
        An open `.alaqs` connection, used to read each movement's
        `runway_time` (the instant the movement is binned at). The
        result dicts do not carry the runway_time, so it is read here.
    bin_interval
        The width of a time bucket. Defaults to one hour. Pass a
        smaller `timedelta` (e.g. `timedelta(minutes=15)`) for
        sub-hourly resolution. Must be positive.

    Returns
    -------
    A long-form DataFrame with one row per (time bucket, movement,
    pollutant), columns:

        bucket_start   datetime   start of the time bucket
        bin_seconds    int        bucket width in seconds
        oid            int        movement oid
        aircraft       str        ICAO type
        departure_arrival str
        pollutant      str        one of POLLUTANTS
        kg             float      emission in that bucket for that
                                  movement and pollutant

    Because a movement is treated as instantaneous, each movement
    contributes exactly len(POLLUTANTS) rows, all sharing one
    `bucket_start`. Summing `kg` over all rows of a pollutant
    reproduces the mode-"(a)" study total for that pollutant: the
    binning is a pure repartition, it neither creates nor destroys
    emission.

    The `bin_seconds` column makes every row self-describing, so a
    consumer can tell hourly output from sub-hourly output without
    inspecting the caller.
    """
    if bin_interval.total_seconds() <= 0:
        raise ValueError(f"bin_interval must be positive, got {bin_interval!r}")

    bin_seconds = int(bin_interval.total_seconds())
    rows: list[dict] = []

    for oid in sorted(results):
        res = results[oid]
        mov = _mv.get_movement(conn, oid)
        if mov is None:
            # The result exists but the movement row does not; this
            # should not happen for a result that came out of
            # compute_all_movements, but guard rather than crash.
            continue
        when = _parse_runway_time(mov["runway_time"])
        b_start = bucket_start(when, bin_interval)
        totals = res["total_em_kg"]
        for p in POLLUTANTS:
            rows.append(
                {
                    "bucket_start": b_start,
                    "bin_seconds": bin_seconds,
                    "oid": res["oid"],
                    "aircraft": res["aircraft"],
                    "departure_arrival": res["departure_arrival"],
                    "pollutant": p,
                    "kg": totals[p],
                }
            )

    columns = [
        "bucket_start",
        "bin_seconds",
        "oid",
        "aircraft",
        "departure_arrival",
        "pollutant",
        "kg",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def aggregate_by_bucket(distributed: pd.DataFrame) -> pd.DataFrame:
    """Collapse a distributed DataFrame to per-(bucket, pollutant) totals.

    Sums over movements, so the result is one row per (time bucket,
    pollutant): the total emission in each bucket regardless of which
    movement produced it. This is the shape a time-series consumer
    (a plot, an AUSTAL hourly series, a sub-hourly results export)
    wants.

    Columns: bucket_start, bin_seconds, pollutant, kg.

    An empty input yields an empty DataFrame with the right columns.
    """
    columns = ["bucket_start", "bin_seconds", "pollutant", "kg"]
    if distributed.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        distributed.groupby(
            ["bucket_start", "bin_seconds", "pollutant"], as_index=False
        )["kg"]
        .sum()
        .sort_values(["bucket_start", "pollutant"])
        .reset_index(drop=True)
    )
    return grouped[columns]


def assert_hourly_for_austal(distributed: pd.DataFrame) -> None:
    """Assert a distributed DataFrame is at hourly resolution.

    AUSTAL consumes hourly emission series. The sub-hour capability of
    `distribute_movements` is for general emission-results output and
    must never feed the AUSTAL input path. The AUSTAL output stage
    (Phase A5) calls this on the DataFrame it is about to convert, so
    a sub-hourly DataFrame reaching the AUSTAL path fails loudly here
    rather than silently producing AUSTAL input AUSTAL cannot use.

    Raises ValueError if any row's `bin_seconds` is not exactly 3600.
    An empty DataFrame passes (nothing to distribute is trivially
    hourly-compatible).
    """
    if distributed.empty:
        return
    bad = sorted(int(v) for v in distributed["bin_seconds"].unique() if int(v) != 3600)
    if bad:
        raise ValueError(
            "AUSTAL input requires hourly resolution (bin_seconds=3600), "
            f"but the distributed emissions carry bin_seconds={bad}. "
            "The sub-hour resolution option must not be used for AUSTAL "
            "input preparation; rebuild the distribution with "
            "bin_interval=timedelta(hours=1)."
        )


# ---------------------------------------------------------------------------
# Spatial distribution: per-(time bucket, grid cell, pollutant)
# ---------------------------------------------------------------------------
#
# The spatial axis of Phase A3. `distribute_movements` above bins a
# movement's emission in time but keeps it spatially lumped. The
# functions below add the spatial axis, producing the full "(c)"
# output: emission resolved to (time bucket, grid cell, pollutant).
#
# The grid is the inventory's AUSTAL grid: `grid_definition` gives the
# cell counts (x_cells, y_cells), `grid_bounds` gives the EPSG:3857
# extent. A cell is identified by an integer index pair (ix, iy) with
# 0 <= ix < x_cells and 0 <= iy < y_cells; cell (0, 0) is the
# south-west corner.
#
# A trajectory segment's clipped geometry (p1_3857 -> p2_3857, retained
# on each A0 result's `segments` list) is guaranteed by the A0 clipping
# step to lie within the grid bounds. The segment's emission is
# apportioned across the cells the segment crosses, weighted by the
# fraction of the segment's EPSG:3857 length in each cell. The
# EPSG:3857 length is distorted relative to true ground length, but
# the distortion is locally near-constant over one short LTO segment,
# so it cancels in the per-cell *ratio*. (The physics -- fuel from
# time and fuel flow -- already used the true geodesic length upstream
# in compute_aircraft; this step only divides an already-correct
# segment emission between cells.)


def cell_index(
    x_3857: float,
    y_3857: float,
    grid_bounds: dict,
    grid_definition: dict,
) -> tuple:
    """Return the (ix, iy) grid-cell index a point falls in.

    `grid_bounds` is the dict from `geometry.grid_bounds_3857`
    (x_min, y_min, x_max, y_max in EPSG:3857, plus the UTM origin and
    EPSG code). `grid_definition` is the dict from
    `movements.get_grid_definition` (x_cells, y_cells, x_resolution,
    y_resolution).

    The indexing happens in the LOCAL UTM CRS, the same way the plugin
    does it (`AUSTALOutputModule._transform_wkt_to_utm` then
    `CalculateCellHashEfficiency` against UTM cell bounds). This is
    physically correct: 100 m on the ground = 100 m in UTM = exactly
    one cell. The previous 3857-via-scale approximation (cell_w_3857 =
    x_res * (1/cos(ref_lat))) was exact only at the SW corner and
    drifted by 1-2 cells over the airport area.

    Cell (0, 0) is the south-west corner. A point a hair outside the
    grid is CLAMPED into the boundary cell, the legacy convention; a
    clipped segment endpoint on the grid boundary is still placed.

    Returns (ix, iy) with 0 <= ix < x_cells, 0 <= iy < y_cells.
    """
    # The closure is cached on `grid_bounds` so all callers in one
    # study share a single Transformer instance.
    fn = grid_bounds.get("_to_cell_utm")
    if fn is None:
        from openalaqs_standalone.geometry import make_3857_to_cell

        fn = make_3857_to_cell(grid_bounds, grid_definition)
        try:
            grid_bounds["_to_cell_utm"] = fn
        except TypeError:
            pass  # frozen dict or similar; closure still usable below
    return fn(x_3857, y_3857)


def _get_to_utm(grid_bounds: dict):
    """Return a cached 3857->UTM transformer closure scoped to one grid.

    Used by polyline cell-apportionment so that the line is cut at
    grid lines in UTM (where 1 cell = 100 m) instead of in 3857
    (where 1 cell = ~148 m with non-uniform distortion).
    """
    fn = grid_bounds.get("_to_utm_fn")
    if fn is None:
        from openalaqs_standalone.geometry import make_3857_to_utm

        fn = make_3857_to_utm(grid_bounds)
        try:
            grid_bounds["_to_utm_fn"] = fn
        except TypeError:
            pass
    return fn


def _build_cells_3857(grid_bounds: dict, grid_definition: dict) -> tuple:
    """Build the grid of cells reprojected from UTM into EPSG:3857.

    Matches the plugin's gridding exactly. The plugin builds the cells
    in the local UTM CRS (axis-aligned 100 m squares) via
    `Grid3D.get_df_from_2d_grid_cells()`, then immediately calls
    `to_crs("EPSG:3857")` in
    `EmissionsQGISVectorLayerOutputModule.beginJob()`. The per-corner
    reprojection turns each UTM square into a 3857 quadrilateral that
    is NOT axis-aligned: at mid-latitudes (~47.5 N) each side stretches by
    ~1/cos(lat) = 1.48, and the top and bottom edges differ very
    slightly in length (the local Mercator scale varies with latitude).
    This matters for cell-edge apportionment, which is then done in
    3857 by `GridOutputModule._process_grid` using shapely.

    Returns (polygons, tree, cell_idx):
        polygons: list of N=x_cells*y_cells shapely Polygons in 3857
        tree: shapely.strtree.STRtree built from polygons
        cell_idx: parallel list of (ix, iy) tuples
    """
    import pyproj
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree

    utm_epsg = int(grid_bounds["utm_epsg"])
    origin_x_utm = float(grid_bounds["origin_x_utm"])
    origin_y_utm = float(grid_bounds["origin_y_utm"])
    x_cells = int(grid_definition["x_cells"])
    y_cells = int(grid_definition["y_cells"])
    x_res = float(grid_definition["x_resolution"])
    y_res = float(grid_definition["y_resolution"])

    transformer = pyproj.Transformer.from_crs(utm_epsg, 3857, always_xy=True)

    polygons: list = []
    cell_idx: list = []
    for iy in range(y_cells):
        for ix in range(x_cells):
            x0 = origin_x_utm + ix * x_res
            y0 = origin_y_utm + iy * y_res
            x1 = x0 + x_res
            y1 = y0 + y_res
            # 4 UTM corners -> 4 3857 corners (per-corner transform,
            # matching geopandas .to_crs() which preserves vertices only).
            c00 = transformer.transform(x0, y0)
            c10 = transformer.transform(x1, y0)
            c11 = transformer.transform(x1, y1)
            c01 = transformer.transform(x0, y1)
            polygons.append(Polygon([c00, c10, c11, c01]))
            cell_idx.append((ix, iy))

    tree = STRtree(polygons)
    return polygons, tree, cell_idx


def _get_cells_3857(grid_bounds: dict, grid_definition: dict) -> tuple:
    """Lazy-build and cache the 3857-quadrilateral cell index.

    Cached on `grid_bounds` so build_context can stash it across the
    whole emission run. 10000 cells with their STRtree take ~50 ms to
    build and ~5 MB of memory.
    """
    cells = grid_bounds.get("_cells_3857")
    if cells is None:
        cells = _build_cells_3857(grid_bounds, grid_definition)
        try:
            grid_bounds["_cells_3857"] = cells
        except TypeError:
            # grid_bounds is a frozen mapping: skip caching, build fresh
            # each call (slower but correct).
            pass
    return cells


def _segment_cell_fractions(
    p1: tuple,
    p2: tuple,
    grid_bounds: dict,
    grid_definition: dict,
) -> dict:
    """Apportion a segment across the grid cells it crosses.

    Plugin-equivalent algorithm. Matches
    `open_alaqs.core.interfaces.OutputModule.GridOutputModule._process_grid`
    (the only place the plugin assigns mass to cells):

        intersecting = grid_df[grid_df.intersects(geom)]
        factor = intersecting.intersection(geom).length / geom.length

    where grid_df is the 100x100 UTM cell grid reprojected to EPSG:3857
    via `to_crs("EPSG:3857")` (see `EmissionsQGISVectorLayerOutputModule
    .beginJob()`). Cells are 3857 quadrilaterals, not axis-aligned
    rectangles, due to Mercator distortion at non-zero latitude.

    Inputs (p1, p2) are EPSG:3857 endpoints, identical convention to
    what the rest of the standalone carries. The 3857 segment is
    intersected against 3857 cell polygons via shapely; per-cell
    fraction is `intersection.length / segment.length` in 3857.
    Although 3857 metres are ~1.48x ground metres at mid-latitudes,
    the ratio cancels: a uniform stretch applied to both numerator
    and denominator leaves the fraction unchanged.

    A degenerate (zero-length) segment is placed wholly in the cell
    of p1, by the same cell_index mapping used by the fallback path.
    """
    from shapely.geometry import LineString
    from shapely.validation import make_valid

    seg = LineString([(float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))])
    seg_len = seg.length
    if seg_len == 0.0:
        return {cell_index(p1[0], p1[1], grid_bounds, grid_definition): 1.0}

    polygons, tree, cell_idx = _get_cells_3857(grid_bounds, grid_definition)

    # make_valid mirrors plugin's `make_valid(emission.getGeometry())`
    # in OutputModule._process_grid line ~98. For a 2-point LineString
    # this is a no-op except for zero-length degenerates already
    # filtered above; the call is cheap and keeps behaviour identical.
    seg_valid = make_valid(seg)

    candidate_idxs = tree.query(seg_valid, predicate="intersects")

    fractions: dict = {}
    for ci in candidate_idxs:
        inter = polygons[ci].intersection(seg_valid)
        # MultiLineString or GeometryCollection result inherits `.length`;
        # Point/empty results give 0 and are skipped.
        if inter.length > 0.0:
            fractions[cell_idx[ci]] = inter.length / seg_len
    return fractions


def _linestring_cell_fractions(
    coords: list,
    grid_bounds: dict,
    grid_definition: dict,
) -> dict:
    """Apportion a polyline across the grid cells it crosses.

    Plugin-equivalent. The plugin treats each emission as one geometry
    and runs the apportionment once per emission, not per-segment:
    `factor = intersecting.intersection(geom).length / geom.length`
    where `geom` is the whole LineString (or MultiLineString) and
    `intersecting` is the subset of cells whose 3857-reprojected
    polygons intersect it. This is `_process_grid` in
    `open_alaqs/core/interfaces/OutputModule.py`.

    `coords` is a list of (x, y) tuples in EPSG:3857. Returns a dict
    mapping (ix, iy) -> fraction, summing to 1.0. The intersection is
    done in 3857 directly against the per-corner-reprojected UTM
    cells; the length ratio is invariant to the local Mercator stretch
    so the per-cell fraction is correct as a share of the line.

    Coordinates with fewer than 2 vertices, or whose total length is
    zero, return an empty dict (caller falls back to single-cell
    placement at the first coordinate).
    """
    from shapely.geometry import LineString
    from shapely.validation import make_valid

    if not coords or len(coords) < 2:
        return {}

    line = LineString([(float(c[0]), float(c[1])) for c in coords])
    line_len = line.length
    if line_len == 0.0:
        return {}

    polygons, tree, cell_idx = _get_cells_3857(grid_bounds, grid_definition)
    line_valid = make_valid(line)
    candidate_idxs = tree.query(line_valid, predicate="intersects")

    fractions: dict = {}
    for ci in candidate_idxs:
        inter = polygons[ci].intersection(line_valid)
        if inter.length > 0.0:
            fractions[cell_idx[ci]] = inter.length / line_len
    return fractions


def _polygon_cell_fractions(
    polygon,
    grid_bounds: dict,
    grid_definition: dict,
) -> dict:
    """Apportion a polygon's mass across the grid cells it covers.

    Plugin-equivalent. The plugin handles polygon emissions
    (gate GSE/GPU, parking polygons, anything with non-zero area) in
    `GridOutputModule._process_grid`:

        factor = intersecting.intersection(geom).area / geom.area

    The polygon is intersected against 3857-quadrilateral cells (the
    same per-corner-reprojected cells used by the line-apportionment
    path) and each cell receives a fraction proportional to its share
    of the polygon's area.

    `polygon` is a shapely Polygon or MultiPolygon in EPSG:3857. A
    degenerate (zero-area) input is placed wholly in the cell of the
    polygon's centroid, matching the cell_index fallback used by the
    line path for zero-length segments.

    Returns a dict {(ix, iy): fraction} with fractions summing to 1.0.
    """
    from shapely.validation import make_valid

    poly_valid = make_valid(polygon)
    poly_area = poly_valid.area
    if poly_area == 0.0:
        c = polygon.centroid
        return {cell_index(c.x, c.y, grid_bounds, grid_definition): 1.0}

    polygons, tree, cell_idx = _get_cells_3857(grid_bounds, grid_definition)
    candidate_idxs = tree.query(poly_valid, predicate="intersects")

    fractions: dict = {}
    for ci in candidate_idxs:
        inter = polygons[ci].intersection(poly_valid)
        # GeometryCollection / MultiPolygon result inherits `.area`;
        # Point/LineString/empty results give 0 and are skipped.
        if inter.area > 0.0:
            fractions[cell_idx[ci]] = inter.area / poly_area
    return fractions


def _iz_layer_fractions(z1: float, z2: float, sk: list) -> dict:
    """Apportion a segment across vertical AUSTAL grid layers.

    `sk` is the AUSTAL vertical-grid boundary list (length n_layers + 1):
    sk[k]..sk[k+1] is the half-open extent of layer k. For a segment
    that spans altitudes z1 to z2 (metres above ground; in either
    order, the function takes |z2 - z1|), returns a dict
    {iz: fraction} whose values sum to 1.0 and represent the share of
    the segment's altitude extent in each layer.

    Edge cases:
      - z1 == z2: places the entire fraction in the single layer
        containing that altitude (degenerate ground-only segment).
      - z value at or above sk[-1]: caller is expected to have
        clipped these out already (compute_aircraft.py drops segments
        whose both endpoints are above max_height_m). For defensive
        behaviour, altitudes above sk[-1] map to the top layer.

    Used by `distribute_to_grid(sk=...)` to expand the 2D segment
    apportionment into 3D (bucket, ix, iy, iz, pollutant) records.
    """
    n_layers = len(sk) - 1
    if not sk or n_layers < 1:
        return {0: 1.0}
    z_lo = min(z1, z2)
    z_hi = max(z1, z2)
    extent = z_hi - z_lo
    if extent <= 0.0:
        # Point altitude: find the layer it falls in.
        for iz in range(n_layers):
            if sk[iz] <= z_lo < sk[iz + 1]:
                return {iz: 1.0}
        if z_lo >= sk[-1]:
            return {n_layers - 1: 1.0}
        return {0: 1.0}
    fractions: dict = {}
    for iz in range(n_layers):
        lo, hi = sk[iz], sk[iz + 1]
        overlap = min(hi, z_hi) - max(lo, z_lo)
        if overlap > 0.0:
            fractions[iz] = overlap / extent
    if not fractions:
        # Both endpoints above top of sk: dump in top layer.
        fractions[n_layers - 1] = 1.0
    # Normalise to remove floating-point drift so the apportionment
    # conserves the segment mass exactly.
    total = sum(fractions.values())
    if total > 0.0:
        for iz in list(fractions):
            fractions[iz] /= total
    return fractions


def distribute_to_grid(  # noqa: C901 — top-level spatial+temporal distribution orchestrator
    results: dict,
    conn,
    grid_bounds: dict,
    grid_definition: dict,
    bin_interval: timedelta = DEFAULT_BIN_INTERVAL,
    sk: Optional[list] = None,
    source_dynamics: str = "none",
) -> pd.DataFrame:
    """Distribute per-movement emissions to (time bucket, grid cell).

    This is the full "(c)" output: each movement's emission resolved
    both in time (the bucket its `runway_time` falls in) and in space
    (the grid cells its trajectory segments cross).

    Parameters
    ----------
    results
        The dict from `compute_movements.compute_all_movements`.
    conn
        An open `.alaqs` connection, used to read each movement's
        `runway_time` and -- for helicopters -- its runway position.
    grid_bounds
        The dict from `geometry.grid_bounds_3857` (also available as
        `build_context(conn)["grid_bounds"]`).
    grid_definition
        The dict from `movements.get_grid_definition`.
    bin_interval
        Time-bucket width, as for `distribute_movements`. Defaults to
        one hour. Sub-hour intervals are supported for general
        emission-results output but must not feed the AUSTAL path;
        see `assert_hourly_for_austal`.

    Returns
    -------
    A long-form DataFrame with one row per (time bucket, grid cell,
    pollutant) that receives emission, columns:

        bucket_start   datetime   start of the time bucket
        bin_seconds    int        bucket width in seconds
        ix             int        grid cell x index (0 = west edge)
        iy             int        grid cell y index (0 = south edge)
        pollutant      str        one of POLLUTANTS
        kg             float      emission in that (bucket, cell) for
                                  that pollutant

    A movement's emission is split across cells like this:

      - Trajectory (segment) emission: each retained segment's
        `em_kg` is apportioned across the cells its clipped p1 -> p2
        line crosses, by length fraction.
      - Taxi emission (`tx_em_kg`): placed at the single cell the
        runway/taxi intersection point falls in. The taxi phase has
        no retained per-segment geometry, so it is treated as a point
        source at the movement's ground reference. (A future step
        could spread it along the taxi route; that is additive.)
      - Helicopters: no trajectory segments, so the whole
        `total_em_kg` is placed at the single cell the helicopter's
        runway position falls in.

    Summing `kg` over all cells and buckets for a pollutant reproduces
    the mode-"(a)" study total: the spatial distribution, like the
    temporal binning, is a pure repartition.
    """
    if bin_interval.total_seconds() <= 0:
        raise ValueError(f"bin_interval must be positive, got {bin_interval!r}")
    bin_seconds = int(bin_interval.total_seconds())

    # 3D mode is opted into by passing the vertical-grid boundary list.
    # When sk is None the function emits the legacy 2D rows (no iz
    # column) so existing callers continue to work; when sk is a list
    # of layer boundaries the function emits one row per
    # (bucket, ix, iy, iz, pollutant) and adds an iz column. The
    # AUSTAL path calls with sk; other consumers (e.g. cli.py general
    # emission results) pass None.
    use_3d = sk is not None

    # accumulator: (bucket_start, ix, iy, [iz,] pollutant) -> kg
    acc: dict = {}

    # Source-dynamics (smooth-and-shift) setup. When enabled, each
    # aircraft FLIGHT segment and each TAXI sub-segment is apportioned by
    # the AREA of its footprint rectangle (centreline widened to the
    # mode's horizontal extent) instead of by centreline LENGTH. This
    # mirrors the plugin: SmoothAndShiftTransformer replaces each
    # per-segment emission's line geometry with a 3-D box, and
    # GridOutputModule._process_grid then apportions a polygon/volume
    # emission by intersection.area / geom.area (a purely 2-D/horizontal
    # operation -- the box's vertical extent does not affect the 2-D grid
    # output, only the AUSTAL z layering). The emission MASS is unchanged;
    # only its spatial repartition differs, so this is done here at
    # distribution time rather than in the emission compute, exactly as
    # the plugin applies the transform after the emission calculation.
    _sas_method = _sd.resolve_method(source_dynamics)
    if _sas_method is not None:
        _emission_dynamics = _sd.load_emission_dynamics(conn)
        _aircraft_groups = _mv.get_aircraft_groups(conn)
    else:
        _emission_dynamics = None
        _aircraft_groups = None

    def _taxiway_seg_fracs(seg_coords, tx_params):
        """Per-segment cell fractions for one taxiway segment under SAS-TX.

        The plugin emits one emission per taxiway segment with that
        segment's geometry, then SmoothAndShiftTransformer builds a box
        per sub-segment (lto_mode='TX') and _process_grid apportions the
        segment's mass by total footprint area. We replicate that by
        apportioning each sub-segment by its own TX footprint rectangle,
        weighted by the sub-segment's length share, then summing. For a
        2-point taxiway segment this reduces to a single rectangle.

        Falls back to the line apportionment for any degenerate
        sub-segment (zero length) or if the rectangle has zero area.
        Returns {(ix, iy): fraction} summing to ~1.0.
        """
        # Per-sub-segment lengths (for the length-weighted combine).
        sub = []
        total_len = 0.0
        for i in range(len(seg_coords) - 1):
            c0 = seg_coords[i]
            c1 = seg_coords[i + 1]
            dx = float(c1[0]) - float(c0[0])
            dy = float(c1[1]) - float(c0[1])
            ln = (dx * dx + dy * dy) ** 0.5
            if ln <= 0.0:
                continue
            sub.append((c0, c1, ln))
            total_len += ln
        if not sub or total_len <= 0.0:
            # Degenerate; fall back to the plain line apportionment.
            if len(seg_coords) == 2:
                return _segment_cell_fractions(
                    seg_coords[0],
                    seg_coords[-1],
                    grid_bounds,
                    grid_definition,
                )
            return _linestring_cell_fractions(seg_coords, grid_bounds, grid_definition)

        combined: dict = {}
        for c0, c1, ln in sub:
            # TX is ground-level; z is irrelevant to the 2-D footprint.
            footprint, _zmin, _zmax = _sd.segment_footprint(
                c0, c1, 0.0, 0.0, _sas_method, tx_params
            )
            if footprint is not None and footprint.area > 0.0:
                sub_fracs = _polygon_cell_fractions(
                    footprint, grid_bounds, grid_definition
                )
            else:
                sub_fracs = _segment_cell_fractions(
                    c0, c1, grid_bounds, grid_definition
                )
            w = ln / total_len
            for cell, f in sub_fracs.items():
                combined[cell] = combined.get(cell, 0.0) + w * f
        return combined

    # --- Per-cell diagnostic (optional, gated by env vars) ---
    # OPENALAQS_CELL_DIAG_IXIY  = "ix,iy" or "ix0,iy0,ix1,iy1" (inclusive range)
    # OPENALAQS_CELL_DIAG_PARQUET = path to write the diagnostic parquet
    # When both are set, every _add call that lands in a target cell is
    # logged with full context (mov_oid, seg_idx, taxiway_id, kind, pollutant,
    # kg). Use to chase per-cell discrepancies without polluting normal runs.
    import os as _os_diag

    _diag_ixiy_str = _os_diag.environ.get("OPENALAQS_CELL_DIAG_IXIY", "")
    _diag_parquet = _os_diag.environ.get("OPENALAQS_CELL_DIAG_PARQUET", "")
    _diag_cells: set = set()
    _diag_records: list = []
    if _diag_ixiy_str and _diag_parquet:
        try:
            _parts = [int(p) for p in _diag_ixiy_str.split(",")]
            if len(_parts) == 2:
                _diag_cells = {(_parts[0], _parts[1])}
            elif len(_parts) == 4:
                _diag_cells = {
                    (_ix, _iy)
                    for _ix in range(_parts[0], _parts[2] + 1)
                    for _iy in range(_parts[1], _parts[3] + 1)
                }
        except (ValueError, IndexError):
            _diag_cells = set()
    _diag_enabled = bool(_diag_cells)

    def _diag_log(mov_oid, taxi_route, seg_idx, tid, ix, iy, kind, p, kg):
        if not _diag_enabled or (ix, iy) not in _diag_cells or kg == 0.0:
            return
        _diag_records.append(
            {
                "mov_oid": mov_oid,
                "taxi_route": taxi_route,
                "seg_idx": seg_idx,
                "taxiway_id": tid,
                "ix": ix,
                "iy": iy,
                "kind": kind,
                "pollutant": p,
                "kg": kg,
            }
        )

    def _add(bucket, ix, iy, pollutant, kg, iz=0):
        if kg == 0.0:
            return
        if use_3d:
            key = (bucket, ix, iy, iz, pollutant)
        else:
            key = (bucket, ix, iy, pollutant)
        acc[key] = acc.get(key, 0.0) + kg

    runways = None  # lazily loaded, only if a helicopter or taxi needs it
    # Path B caches, scoped to one distribute_to_grid call.
    #
    # route_segments_cache : route_name -> list[{
    #     "tid": taxiway_id (str),
    #     "length": segment length in metres (EPSG:3857),
    #     "fracs": dict[(ix, iy)] = length fraction,
    # }]
    # The list is in the stored order of user_taxiroute_taxiways.sequence
    # (NOT necessarily gate-to-runway; plugin trusts the sequence order).
    # An empty list means the route lookup failed -- caller falls back
    # to the intersection cell.
    #
    # gate_cell_cache : gate_id -> dict[(ix, iy)] -> area-fraction | None
    # The polygon-area fractions for the shapes_gates polygon, computed
    # once via _polygon_cell_fractions and reused across all movements
    # that share the same gate_id. None if the gate_id is not in
    # shapes_gates.
    route_segments_cache = {}
    gate_cell_cache = {}

    for oid in sorted(results):
        res = results[oid]
        mov = _mv.get_movement(conn, oid)
        if mov is None:
            continue
        when = _parse_runway_time(mov["runway_time"])
        b_start = bucket_start(when, bin_interval)

        # Per-movement source-dynamics resolution (no-op when disabled).
        if _sas_method is not None:
            _dyn_group = _sd.dynamic_group_for(
                _aircraft_groups.get(mov.get("aircraft"))
            )
            _is_arrival = mov.get("departure_arrival") == "A"
        else:
            _dyn_group = None
            _is_arrival = False

        segments = res.get("segments", [])

        if segments:
            # Fixed-wing: apportion each segment's emission across the
            # cells its clipped line crosses.
            for seg in segments:
                # Source-dynamics footprint: when enabled and the
                # aircraft group / stage resolve to a dynamics row, the
                # segment is apportioned by its footprint RECTANGLE area
                # (width = the stage's horizontal extent) instead of by
                # centreline length. sas_zmin/sas_zmax carry the box's
                # vertical envelope for the AUSTAL (iz) path. When the
                # dynamics row is missing or the footprint is degenerate
                # we fall back to the line apportionment, matching the
                # plugin's zero-extension default.
                sas_zmin = sas_zmax = None
                fractions = None
                if _sas_method is not None and _dyn_group is not None:
                    _stage = _sd.sas_mode_for_segment(
                        _is_arrival,
                        seg.get("z1_m", 0.0),
                        seg.get("z2_m", 0.0),
                    )
                    _params = _sd.lookup_params(
                        _emission_dynamics, _dyn_group, _stage, _sas_method
                    )
                    if _params is not None:
                        _fp, sas_zmin, sas_zmax = _sd.segment_footprint(
                            seg["p1_3857"],
                            seg["p2_3857"],
                            seg.get("z1_m", 0.0),
                            seg.get("z2_m", 0.0),
                            _sas_method,
                            _params,
                        )
                        if _fp is not None and _fp.area > 0.0:
                            fractions = _polygon_cell_fractions(
                                _fp, grid_bounds, grid_definition
                            )
                if fractions is None:
                    fractions = _segment_cell_fractions(
                        seg["p1_3857"],
                        seg["p2_3857"],
                        grid_bounds,
                        grid_definition,
                    )
                if use_3d:
                    # 3D path: cross-multiply horizontal cell fractions
                    # by vertical layer fractions. Without SAS the band is
                    # the segment's [z1, z2]; with SAS it is the box's
                    # vertical envelope [z_min, z_max] (clamped at 0 for
                    # the AUSTAL layer stack, which starts at ground).
                    # NOTE: the SAS->AUSTAL z mapping is provisional and
                    # has not yet been validated against the plugin's
                    # AUSTAL volume-source output; the 2-D grid output
                    # (sk=None) is unaffected by this branch.
                    if sas_zmin is not None:
                        _z_lo = max(0.0, sas_zmin)
                        _z_hi = max(0.0, sas_zmax)
                    else:
                        _z_lo = seg.get("z1_m", 0.0)
                        _z_hi = seg.get("z2_m", 0.0)
                    iz_fracs = _iz_layer_fractions(
                        _z_lo,
                        _z_hi,
                        sk,
                    )
                    for (ix, iy), frac in fractions.items():
                        for iz, iz_frac in iz_fracs.items():
                            for p in POLLUTANTS:
                                _add(
                                    b_start,
                                    ix,
                                    iy,
                                    p,
                                    seg["em_kg"][p] * frac * iz_frac,
                                    iz=iz,
                                )
                else:
                    for (ix, iy), frac in fractions.items():
                        in_diag = _diag_enabled and (ix, iy) in _diag_cells
                        for p in POLLUTANTS:
                            v = seg["em_kg"][p] * frac
                            _add(b_start, ix, iy, p, v)
                            if in_diag:
                                _diag_log(
                                    oid,
                                    mov.get("taxi_route"),
                                    seg.get("idx", -1),
                                    f"_traj_seg_{seg.get('idx', '?')}_",
                                    ix,
                                    iy,
                                    "traj",
                                    p,
                                    v,
                                )

            # Path B spatial placement. Mirrors the plugin's per-segment
            # apportionment in MovementEmissionCalculator.TaxiingEmissionCalculator:
            #
            #   TAXI ........... per-segment, weighted by segment length
            #                    (length-proportional == time-proportional
            #                    for uniform segment speeds; the test studies and CAEP14
            #                    studies use a single taxi speed so the two
            #                    match exactly).
            #   APU code=1 ..... entire apu_em added to first segment
            #                    (sequence[0]) -- the plugin's
            #                    `index_segment == 0` placement.
            #   APU code=2 ..... apu_em is distributed across all taxi
            #                    segments proportional to segment length
            #                    (length-fraction == time-fraction under
            #                    uniform taxi speeds, the same assumption
            #                    used for `tx_em`). Mass-conserving over
            #                    the apu_em that compute_apu_movements
            #                    returned. The plugin's exact algorithm
            #                    splits apu_em by per-segment APU time
            #                    using a case-specific rule; for the
            #                    case where apu_t >= total_taxi the
            #                    plugin allocation matches this length-
            #                    proportional split under uniform speeds.
            #                    The plugin's sub-case where apu_t <
            #                    total_taxi sums to more than apu_t
            #                    (over-counts; see plugin
            #                    MovementEmissionCalculator lines
            #                    446-460). Std does not replicate that
            #                    overcount; mass conservation wins.
            #   ENGINE START ... added at sequence[0] -- plugin's
            #                    `_apply_start_engine_emissions` is gated on
            #                    `index_segment == 0`.
            #   GATE GSE/GPU ... at the gate's shapes_gates centroid cell,
            #                    matching the plugin's
            #                    `emission_.setGeometryText(self._gate.getGeometryText())`.
            #
            # Sequence ordering: the plugin trusts user_taxiroute_taxiways.sequence
            # as given; segment index 0 is whatever the user put first.
            # We do the same -- no geographic re-ordering. If the data is
            # stored gate-first, the gate-side segment receives APU+START;
            # if stored runway-first, the runway-side does. Either way we
            # match the plugin bit-for-bit on placement.
            tx_em = res.get("tx_em_kg") or {}
            queue_em = res.get("queue_em_kg") or {}
            stop_em = res.get("stop_em_kg") or {}
            gate_em = res.get("gate_em_kg") or {}
            apu_em = res.get("apu_em_kg") or {}
            start_em = res.get("start_em_kg") or {}
            brake_wear_em = res.get("brake_wear_em_kg") or {}
            has_tx = any(v != 0.0 for v in tx_em.values())
            has_queue = any(v != 0.0 for v in queue_em.values())
            has_stop = any(v != 0.0 for v in stop_em.values())
            has_gate = any(v != 0.0 for v in gate_em.values())
            has_apu = any(v != 0.0 for v in apu_em.values())
            has_start = any(v != 0.0 for v in start_em.values())
            has_brake_wear = any(v != 0.0 for v in brake_wear_em.values())
            # apu_code drives the spatial split of `apu_em` across taxi
            # segments. The plugin's _apply_apu_emissions (MovementEmissionCalculator
            # lines 421-499) maps to three cases:
            #   <=0  : no APU (compute_apu_movements has already zeroed
            #          apu_em upstream, so this branch is mass-zero here).
            #     1  : APU at stand only -> all of apu_em at segment idx=0.
            #          (Matches the plugin's `index_segment_ == 0` gate.)
            #     2  : APU runs during stand AND the entire taxi phase ->
            #          apu_em is distributed across all segments. The std
            #          uses length-proportional apportionment (mass-conserving,
            #          uniform-speed assumption -- consistent with how
            #          `tx_em` is already split by `length_frac` in the
            #          same loop). The plugin's exact algorithm splits
            #          apu_em by per-segment APU time using a case-specific
            #          rule (apu_t vs total_taxi_time). When apu_t >=
            #          total_taxi the plugin allocation is mass-conserving
            #          and equivalent to length-proportional under uniform
            #          speeds; when apu_t < total_taxi the plugin allocation
            #          sums to more than apu_t (over-counts; see plugin code
            #          lines 446-460). Std's length-proportional approach
            #          conserves the mass that compute_apu_movements
            #          reported and does not replicate the plugin's
            #          overcount in that sub-case. Bit-parity for the
            #          overcount sub-case is not pursued here; a real
            #          apu_code=2 study would need that decision revisited.
            #   None : treated as 1 (the plugin's permissive default and
            #          the behaviour compute_apu_movements falls back to
            #          when the DB column is absent).
            _apu_code_raw = res.get("apu_code")
            try:
                _apu_code = int(_apu_code_raw) if _apu_code_raw not in (None, "") else 1
            except (ValueError, TypeError):
                _apu_code = 1
            if (
                has_tx
                or has_queue
                or has_stop
                or has_gate
                or has_apu
                or has_start
                or has_brake_wear
            ):
                if runways is None:
                    runways = _mv.get_runways(conn)
                runway = runways[mov["runway_direction"]]
                from openalaqs_standalone import geometry as _geo

                rn = mov["taxi_route"]

                # Source-dynamics TX parameters for this movement's group.
                # The TX footprint width depends on the aircraft's dynamic
                # group, so under SAS the route cache must be keyed by
                # (route, group) -- two aircraft groups on the same route
                # get different footprints. Without SAS the key is the
                # route name alone (unchanged behaviour).
                _tx_params = None
                if _sas_method is not None and _dyn_group is not None:
                    _tx_params = _sd.lookup_params(
                        _emission_dynamics, _dyn_group, "TX", _sas_method
                    )
                _cache_key = (rn, _dyn_group) if _tx_params is not None else rn

                # Vertical (iz) distribution for the taxi phase. The plugin
                # gives taxi a SmoothAndShift(TX) box -- a ground source
                # (z=0) extended by the TX vertical extension -- rather than
                # placing it at the surface, so taxi emission overlaps the
                # AUSTAL sk layers just like a flight segment. The box is the
                # same for every taxi sub-segment of this movement (z is 0 at
                # both endpoints), so the iz fractions depend only on the
                # group's TX params; compute them once here. Stays None in the
                # 2D path (sk is None) -> taxi keeps iz=0 as before.
                _tx_iz_fracs = None
                if sk is not None and _tx_params is not None:
                    _, _tx_zlo, _tx_zhi = _sd.segment_footprint(
                        (0.0, 0.0), (1.0, 0.0), 0.0, 0.0, _sas_method, _tx_params
                    )
                    _tx_iz_fracs = _iz_layer_fractions(
                        max(0.0, _tx_zlo), max(0.0, _tx_zhi), sk
                    )

                # Resolve and cache the route's segment list + per-segment
                # cell fractions. Cached so 80+ movements through the same
                # route do the SQLite + geometry work once.
                if _cache_key in route_segments_cache:
                    segments_data = route_segments_cache[_cache_key]
                else:
                    segments_data = []
                    try:
                        seq_row = conn.execute(
                            "SELECT sequence FROM user_taxiroute_taxiways "
                            "WHERE route_name=?",
                            (rn,),
                        ).fetchone()
                    except Exception:
                        seq_row = None
                    if seq_row and seq_row[0]:
                        for tid_raw in seq_row[0].split(","):
                            tid = tid_raw.strip()
                            if not tid:
                                continue
                            try:
                                geom_row = conn.execute(
                                    "SELECT geometry FROM shapes_taxiways "
                                    "WHERE taxiway_id=?",
                                    (tid,),
                                ).fetchone()
                            except Exception:
                                geom_row = None
                            if not geom_row:
                                continue
                            seg_geom = _geo.spatialite_blob_to_shapely(geom_row[0])
                            seg_coords = list(seg_geom.coords)
                            if len(seg_coords) < 2:
                                continue
                            if _tx_params is not None:
                                # SAS-TX: apportion the taxiway segment by
                                # its footprint rectangle(s) (width = TX
                                # horizontal extent), per sub-segment.
                                seg_fracs = _taxiway_seg_fracs(seg_coords, _tx_params)
                            elif len(seg_coords) == 2:
                                seg_fracs = _segment_cell_fractions(
                                    seg_coords[0],
                                    seg_coords[-1],
                                    grid_bounds,
                                    grid_definition,
                                )
                            else:
                                seg_fracs = _linestring_cell_fractions(
                                    seg_coords,
                                    grid_bounds,
                                    grid_definition,
                                )
                            segments_data.append(
                                {
                                    "tid": tid,
                                    "length": seg_geom.length,
                                    "fracs": seg_fracs,
                                }
                            )
                    route_segments_cache[_cache_key] = segments_data

                total_seg_length = sum(s["length"] for s in segments_data)

                # --- TAXI + APU + START + QUEUE + STOP + BRAKE_WEAR per-segment placement. ---
                # Mass split per the plugin
                # (MovementEmissionCalculator.py lines 327, 380-403):
                #   tx_em      -- natural-time taxi, distributed by segment
                #                 length. Engine-only.
                #   apu_em     -- placed at segment idx == 0 only (plugin
                #                 apu_code == 1 logic; for code == 2 the
                #                 plugin distributes too, the standalone
                #                 only models code == 1, the most common case).
                #   start_em   -- also at idx == 0.
                #   brake_wear_em -- arrivals only (heavy aircraft); placed
                #                 at idx == 0, the FIRST segment of the
                #                 arrival taxi route. Matches plugin's
                #                 _apply_single_engine_taxiing_emissions_for_arrival
                #                 `index_segment == 0` gate.
                #   queue_em   -- queuing-time excess, placed at the LAST
                #                 segment only. Captures the bulk of the
                #                 taxi time the standalone previously
                #                 smeared along the route.
                #   stop_em    -- stop-and-go (n_stops * 9 s of idle),
                #                 also at the LAST segment. Zero for studies
                #                 v3 (all-zero number_of_stop_and_gos),
                #                 nonzero for studies that record stops.
                taxi_handled = False
                apu_handled = False
                start_handled = False
                queue_handled = False
                stop_handled = False
                brake_wear_handled = False
                if segments_data and total_seg_length > 0:
                    last_idx = len(segments_data) - 1
                    for idx, seg in enumerate(segments_data):
                        length_frac = seg["length"] / total_seg_length
                        # Per-source contributions for this segment (full,
                        # before cell-fraction split). Kept separate so the
                        # diagnostic can record each kind individually.
                        nat_p = {
                            p: (tx_em.get(p, 0.0) * length_frac if has_tx else 0.0)
                            for p in POLLUTANTS
                        }
                        # APU placement -- see the apu_code block above
                        # for the case rationale and the divergence from
                        # plugin's apu_code=2 overcount sub-case.
                        if not has_apu:
                            apu_p = {p: 0.0 for p in POLLUTANTS}
                        elif _apu_code == 2:
                            apu_p = {
                                p: apu_em.get(p, 0.0) * length_frac for p in POLLUTANTS
                            }
                        else:
                            apu_p = (
                                {p: apu_em.get(p, 0.0) for p in POLLUTANTS}
                                if idx == 0
                                else {p: 0.0 for p in POLLUTANTS}
                            )
                        start_p = (
                            {p: start_em.get(p, 0.0) for p in POLLUTANTS}
                            if (idx == 0 and has_start)
                            else {p: 0.0 for p in POLLUTANTS}
                        )
                        brake_wear_p = (
                            {p: brake_wear_em.get(p, 0.0) for p in POLLUTANTS}
                            if (idx == 0 and has_brake_wear)
                            else {p: 0.0 for p in POLLUTANTS}
                        )
                        queue_p = (
                            {p: queue_em.get(p, 0.0) for p in POLLUTANTS}
                            if (idx == last_idx and has_queue)
                            else {p: 0.0 for p in POLLUTANTS}
                        )
                        stop_p = (
                            {p: stop_em.get(p, 0.0) for p in POLLUTANTS}
                            if (idx == last_idx and has_stop)
                            else {p: 0.0 for p in POLLUTANTS}
                        )
                        for (ix, iy), frac in seg["fracs"].items():
                            in_diag = _diag_enabled and (ix, iy) in _diag_cells
                            for p in POLLUTANTS:
                                total = (
                                    nat_p[p]
                                    + apu_p[p]
                                    + start_p[p]
                                    + queue_p[p]
                                    + stop_p[p]
                                    + brake_wear_p[p]
                                ) * frac
                                if _tx_iz_fracs is not None:
                                    for _iz, _izf in _tx_iz_fracs.items():
                                        _add(
                                            b_start,
                                            ix,
                                            iy,
                                            p,
                                            total * _izf,
                                            iz=_iz,
                                        )
                                else:
                                    _add(b_start, ix, iy, p, total)
                                if in_diag:
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "nat",
                                        p,
                                        nat_p[p] * frac,
                                    )
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "apu",
                                        p,
                                        apu_p[p] * frac,
                                    )
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "start",
                                        p,
                                        start_p[p] * frac,
                                    )
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "brake_wear",
                                        p,
                                        brake_wear_p[p] * frac,
                                    )
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "queue",
                                        p,
                                        queue_p[p] * frac,
                                    )
                                    _diag_log(
                                        mov["oid"],
                                        mov.get("taxi_route"),
                                        idx,
                                        seg["tid"],
                                        ix,
                                        iy,
                                        "stop",
                                        p,
                                        stop_p[p] * frac,
                                    )
                    if has_tx:
                        taxi_handled = True
                    if has_apu:
                        apu_handled = True
                    if has_start:
                        start_handled = True
                    if has_brake_wear:
                        brake_wear_handled = True
                    if has_queue:
                        queue_handled = True
                    if has_stop:
                        stop_handled = True

                # --- GATE GSE/GPU at gate polygon geometry. ---
                # Matches plugin's `_calculate_ground_equipment_emissions`
                # (MovementEmissionCalculator.py line 90):
                #
                #     emissions.setGeometryText(self._gate.getGeometryText())
                #
                # which gives the GSE+GPU emissions the gate's full polygon
                # as their geometry. Plugin then runs the standard
                # `_process_grid` polygon branch:
                #
                #     factor = intersecting.intersection(geom).area / geom.area
                #
                # Distributes the gate mass across all cells whose
                # 3857-quadrilateral overlaps the gate polygon, weighted by
                # area share. Single-cell placement (the earlier standalone
                # behaviour) over-concentrates gate mass at the centroid
                # cell, causing ~10 kg/cell shifts at any clustered gate area.
                gate_handled = False
                if has_gate:
                    gate_id_raw = mov.get("gate")
                    if gate_id_raw is not None and str(gate_id_raw).strip():
                        gid = str(gate_id_raw)
                        if gid in gate_cell_cache:
                            gate_fracs = gate_cell_cache[gid]
                        else:
                            gate_fracs = None
                            try:
                                gate_row = conn.execute(
                                    "SELECT geometry FROM shapes_gates "
                                    "WHERE gate_id=?",
                                    (gid,),
                                ).fetchone()
                            except Exception:
                                gate_row = None
                            if gate_row:
                                gg = _geo.spatialite_blob_to_shapely(gate_row[0])
                                gate_fracs = _polygon_cell_fractions(
                                    gg,
                                    grid_bounds,
                                    grid_definition,
                                )
                            gate_cell_cache[gid] = gate_fracs
                        if gate_fracs:
                            for (gix, giy), gfrac in gate_fracs.items():
                                in_diag = _diag_enabled and (gix, giy) in _diag_cells
                                for p in POLLUTANTS:
                                    val = gate_em.get(p, 0.0) * gfrac
                                    _add(b_start, gix, giy, p, val)
                                    if in_diag:
                                        _diag_log(
                                            mov["oid"],
                                            mov.get("taxi_route"),
                                            -1,
                                            "_gate_polygon_",
                                            gix,
                                            giy,
                                            "gate",
                                            p,
                                            val,
                                        )
                            gate_handled = True

                # --- Fallback (intersection cell, else threshold) for any
                # phase we could not place above. This runs only when the
                # route data is missing or all segments degenerated; for a
                # healthy study it should never fire.
                need_fallback = (
                    (has_tx and not taxi_handled)
                    or (has_apu and not apu_handled)
                    or (has_gate and not gate_handled)
                    or (has_start and not start_handled)
                    or (has_queue and not queue_handled)
                    or (has_stop and not stop_handled)
                    or (has_brake_wear and not brake_wear_handled)
                )
                if need_fallback:
                    ctx_like = {"runways": runways}
                    from openalaqs_standalone.compute_aircraft import (
                        _intersection_cached,
                    )

                    inter = _intersection_cached(ctx_like, conn, rn, runway)
                    if inter is None:
                        inter = _geo.runway_threshold_3857(
                            runway, mov["runway_direction"]
                        )
                    ix, iy = cell_index(
                        inter[0], inter[1], grid_bounds, grid_definition
                    )
                    in_diag_fb = _diag_enabled and (ix, iy) in _diag_cells
                    for p in POLLUTANTS:
                        if has_tx and not taxi_handled:
                            v = tx_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "nat_fb",
                                    p,
                                    v,
                                )
                        if has_apu and not apu_handled:
                            v = apu_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "apu_fb",
                                    p,
                                    v,
                                )
                        if has_gate and not gate_handled:
                            v = gate_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "gate_fb",
                                    p,
                                    v,
                                )
                        if has_start and not start_handled:
                            v = start_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "start_fb",
                                    p,
                                    v,
                                )
                        if has_brake_wear and not brake_wear_handled:
                            v = brake_wear_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "brake_wear_fb",
                                    p,
                                    v,
                                )
                        if has_queue and not queue_handled:
                            v = queue_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "queue_fb",
                                    p,
                                    v,
                                )
                        if has_stop and not stop_handled:
                            v = stop_em.get(p, 0.0)
                            _add(b_start, ix, iy, p, v)
                            if in_diag_fb:
                                _diag_log(
                                    mov["oid"],
                                    mov.get("taxi_route"),
                                    -1,
                                    "_fallback_",
                                    ix,
                                    iy,
                                    "stop_fb",
                                    p,
                                    v,
                                )
        else:
            # Helicopter (or any movement with no retained segments):
            # the whole total is a point source at the runway
            # threshold for the movement's direction (not pt1
            # unconditionally; for direction-33 movements that would
            # pick the wrong end of the runway).
            if runways is None:
                runways = _mv.get_runways(conn)
            runway = runways[mov["runway_direction"]]
            from openalaqs_standalone import geometry as _geo

            pos = _geo.runway_threshold_3857(runway, mov["runway_direction"])
            ix, iy = cell_index(pos[0], pos[1], grid_bounds, grid_definition)
            for p in POLLUTANTS:
                _add(b_start, ix, iy, p, res["total_em_kg"][p])

    # --- Write per-cell diagnostic, if enabled ---
    if _diag_enabled and _diag_records:
        try:
            _diag_df = pd.DataFrame(_diag_records)
            _diag_df.to_parquet(_diag_parquet, index=False)
        except Exception as _diag_e:
            import sys as _sys

            print(f"[distribute] diagnostic write failed: {_diag_e}", file=_sys.stderr)

    if use_3d:
        columns = [
            "bucket_start",
            "bin_seconds",
            "ix",
            "iy",
            "iz",
            "pollutant",
            "kg",
        ]
        if not acc:
            return pd.DataFrame(columns=columns)
        rows = [
            {
                "bucket_start": bucket,
                "bin_seconds": bin_seconds,
                "ix": ix,
                "iy": iy,
                "iz": iz,
                "pollutant": pollutant,
                "kg": kg,
            }
            for (bucket, ix, iy, iz, pollutant), kg in acc.items()
        ]
        df = pd.DataFrame(rows, columns=columns)
        return df.sort_values(
            ["bucket_start", "ix", "iy", "iz", "pollutant"]
        ).reset_index(drop=True)

    columns = [
        "bucket_start",
        "bin_seconds",
        "ix",
        "iy",
        "pollutant",
        "kg",
    ]
    if not acc:
        return pd.DataFrame(columns=columns)

    rows = [
        {
            "bucket_start": bucket,
            "bin_seconds": bin_seconds,
            "ix": ix,
            "iy": iy,
            "pollutant": pollutant,
            "kg": kg,
        }
        for (bucket, ix, iy, pollutant), kg in acc.items()
    ]
    df = pd.DataFrame(rows, columns=columns)
    return df.sort_values(["bucket_start", "ix", "iy", "pollutant"]).reset_index(
        drop=True
    )
