"""
geometry: QGIS-free spatial primitives for the OpenALAQS standalone.

This module is the standalone's replacement for the QGIS-coupled
`open_alaqs/core/tools/spatial.py` and `core/GeoTransformation.py`. It
is a faithful port of the spatial helpers in the CAEP14 validation
reference (`validation/tools/compute_caep14_reference.py`, lines
~128-300), which were themselves verified against the plugin's own
implementation to sub-millimetre precision.

Two groups of functions:

1. SpatiaLite BLOB reading. The `.alaqs` file stores geometry columns
   as SpatiaLite BLOBs. The reference reads them via `ST_AsText(...)`,
   which requires the `mod_spatialite` native extension. This module
   instead parses the BLOB directly with shapely, removing that native
   dependency. `spatialite_blob_to_shapely` is the entry point.

   Divergence from the reference: `ST_AsText` rounds coordinates to 6
   decimal places; this parser keeps full float64 precision. The
   divergence is at most ~5e-7 m at the coordinate level, far below
   the validation tolerance, and the WKB parse is the more accurate of
   the two (it is bit-identical to the stored data). The standalone
   deliberately uses full precision.

2. Spatial math: runway alignment, trajectory projection, grid
   clipping, ground distance. These are ported verbatim from the
   reference; the only changes are docstrings and the removal of the
   leading underscore from the public names.

All coordinates are in EPSG:3857 unless a function name or argument
says otherwise. EPSG:3857 is the working frame for the aircraft
pipeline because that is the frame the plugin and the reference both
use; ground distances are always computed geodesically on WGS84, never
as planar 3857 distances.
"""

from __future__ import annotations

import math
import struct
from typing import Optional

import pyproj
from shapely import wkb as _shapely_wkb
from shapely.geometry import LineString, box

# ---------------------------------------------------------------------------
# Shared transformers and constants (match the CAEP14 reference)
# ---------------------------------------------------------------------------

# Geodesic on the WGS84 ellipsoid. All ground distances and bearings go
# through this, never planar 3857 math.
GEOD = pyproj.Geod(ellps="WGS84")

# EPSG:3857 <-> EPSG:4326 transformers. always_xy=True keeps the axis
# order (lon, lat) / (x, y) consistent regardless of CRS definition.
TO_WGS84 = pyproj.Transformer.from_crs(3857, 4326, always_xy=True)
TO_3857 = pyproj.Transformer.from_crs(4326, 3857, always_xy=True)

# Buffer applied to the runway centreline when intersecting it with a
# taxi route, in metres. Matches the reference's RUNWAY_BUFFER_M.
RUNWAY_BUFFER_M = 1.0

# Cache of (3857 -> UTM, UTM -> 3857) transformer pairs, keyed by UTM
# EPSG code. Transformer construction is not free; the reference caches
# these and so do we.
_UTM_TRANSFORMER_CACHE: dict[int, tuple] = {}


def utm_transformers(utm_epsg: int) -> tuple[pyproj.Transformer, pyproj.Transformer]:
    """Return the cached (3857 -> UTM, UTM -> 3857) transformer pair.

    Ported from the reference's `_utm_transformers`.
    """
    if utm_epsg not in _UTM_TRANSFORMER_CACHE:
        _UTM_TRANSFORMER_CACHE[utm_epsg] = (
            pyproj.Transformer.from_crs(3857, utm_epsg, always_xy=True),
            pyproj.Transformer.from_crs(utm_epsg, 3857, always_xy=True),
        )
    return _UTM_TRANSFORMER_CACHE[utm_epsg]


# ---------------------------------------------------------------------------
# SpatiaLite BLOB reading (replaces the reference's ST_AsText path)
# ---------------------------------------------------------------------------


def spatialite_blob_to_shapely(blob: bytes):
    """Parse a SpatiaLite geometry BLOB into a shapely geometry.

    The `.alaqs` file stores geometry columns in the SpatiaLite BLOB
    format, not as plain WKB. The layout is:

        byte 0        0x00            start marker
        byte 1        endianness      0x00 big-endian, 0x01 little-endian
        bytes 2-5     SRID            int32
        bytes 6-37    MBR             4 doubles (min_x, min_y, max_x, max_y)
        byte 38       0x7C            MBR_END marker
        bytes 39..n-2 geometry body   standard WKB *without* its leading
                                      endianness byte
        byte n-1      0xFE            end marker

    Standard WKB is `[endian:1][type:4][...]`; the SpatiaLite body omits
    that leading endian byte, so we re-insert it and hand the result to
    shapely.

    This was verified against `ST_AsText` on every runway and taxiway
    geometry in `training_v3.alaqs`: geometry type and point count match
    exactly, coordinates agree to within ~5e-7 m (the difference being
    that `ST_AsText` rounds to 6 decimal places while this parser keeps
    full precision).

    Raises ValueError if the BLOB is empty or does not start with the
    SpatiaLite 0x00 marker.
    """
    if not blob or blob[0] != 0x00:
        raise ValueError(
            "not a SpatiaLite geometry BLOB " "(expected leading 0x00 marker)"
        )
    endian = blob[1]  # 0x00 big-endian, 0x01 little-endian
    body = blob[39:-1]
    standard_wkb = bytes([endian]) + body
    return _shapely_wkb.loads(standard_wkb)


def spatialite_blob_srid(blob: bytes) -> int:
    """Return the SRID stored in a SpatiaLite geometry BLOB header."""
    if not blob or blob[0] != 0x00:
        raise ValueError(
            "not a SpatiaLite geometry BLOB " "(expected leading 0x00 marker)"
        )
    endian = blob[1]
    fmt = "<i" if endian == 1 else ">i"
    return struct.unpack(fmt, blob[2:6])[0]


# ---------------------------------------------------------------------------
# Runway alignment and bearings
# ---------------------------------------------------------------------------


def bearing_deg(p1_3857: tuple, p2_3857: tuple) -> float:
    """Forward azimuth from p1 to p2, in degrees clockwise from north.

    Both points are EPSG:3857. The bearing is computed geodesically on
    WGS84, not as a planar angle. Ported from the reference's
    `_bearing_deg`.
    """
    lon1, lat1 = TO_WGS84.transform(p1_3857[0], p1_3857[1])
    lon2, lat2 = TO_WGS84.transform(p2_3857[0], p2_3857[1])
    fwd_az, _, _ = GEOD.inv(lon1, lat1, lon2, lat2)
    return fwd_az % 360.0


def _runway_endpoint_assignment(runway: dict):
    """Map each runway designator to its (pt1_3857 or pt2_3857) endpoint.

    Helper shared by `runway_azimuth_deg` and `runway_backup_3857` to
    avoid duplicating the bearing-matching logic. Returns a dict
    {designator_int: (x, y)} for the two designators in
    `runway["directions"]`.

    The mapping uses the measured centreline bearing pt1->pt2 against
    each designator's nominal heading (designator * 10 degrees), pairs
    the smaller-difference designator with pt1, and the other with pt2.
    """
    az = bearing_deg(runway["pt1_3857"], runway["pt2_3857"])
    expected = {d: (d * 10) % 360 for d in runway["directions"]}
    diffs = {d: min(abs(az - hdg), 360 - abs(az - hdg)) for d, hdg in expected.items()}
    start_dir = min(diffs, key=diffs.get)
    end_dir = [d for d in runway["directions"] if d != start_dir][0]
    return {start_dir: runway["pt1_3857"], end_dir: runway["pt2_3857"]}


def runway_azimuth_deg(runway: dict, runway_direction: int, is_dep: bool) -> float:
    """Azimuth of the runway in the direction the aircraft travels.

    `runway` is the dict returned by the runway reader: it carries
    `pt1_3857`, `pt2_3857` (the two centreline endpoints) and
    `directions` (the two runway-designator integers, e.g. [6, 24]).
    `runway_direction` is the designator the movement uses;
    `is_dep` is True for a departure, False for an arrival.

    The logic: each runway designator maps to a nominal heading
    (designator * 10 degrees). Match the measured centreline bearing to
    whichever designator is closest to identify which physical endpoint
    is which. Then a departure runs from the threshold towards the
    opposite end; an arrival runs towards the named threshold.

    Ported verbatim from the reference's `_runway_azimuth_deg`.
    """
    points = _runway_endpoint_assignment(runway)
    start_dir = next(d for d, p in points.items() if p is runway["pt1_3857"])
    end_dir = next(d for d in points if d != start_dir)
    opp = end_dir if runway_direction == start_dir else start_dir
    backup = points[runway_direction] if is_dep else points[opp]
    target = points[opp] if is_dep else points[runway_direction]
    return bearing_deg(backup, target)


def runway_backup_3857(runway: dict, runway_direction: int, is_dep: bool) -> tuple:
    """Fallback origin for the trajectory projection when the
    runway/taxi intersection is empty.

    Mirrors the plugin's `runway_backup_point` selection in
    `GeoTransformation._get_runway_dir_azimuth`:
      - departures: the active direction's own threshold (where takeoff
        starts).
      - arrivals: the opposite endpoint (where the rollout exits, used
        as a stand-in when the actual exit taxi route is not known to
        intersect the runway).

    The previous standalone fallback returned `runway["pt1_3857"]`
    unconditionally, which placed every fallback movement at the NW
    end of the runway regardless of the active direction. For RWY 33
    (or any movement whose pt1 is not on the relevant side) this
    pushed mass to the wrong threshold. Using the plugin's per-
    direction selection eliminates that asymmetry.

    Affects only movements whose taxi route's geometry does not cross
    the runway-centreline buffer (1 m). For a representative study this is ~39 of 744
    RWY 15 A movements (5%); the remaining 95% use the runway-taxi
    intersection itself and are unaffected.
    """
    points = _runway_endpoint_assignment(runway)
    start_dir = next(d for d, p in points.items() if p is runway["pt1_3857"])
    end_dir = next(d for d in points if d != start_dir)
    opp = end_dir if runway_direction == start_dir else start_dir
    return points[runway_direction] if is_dep else points[opp]


def runway_threshold_3857(runway: dict, runway_direction: int) -> tuple:
    """Return the threshold endpoint for the active runway direction.

    Independent of D/A: this is the end of the runway where the named
    designator is painted (where the "15" marking sits for RWY 15
    movements). Use for cases that need a stable per-direction anchor
    without departure/arrival asymmetry: helicopter point-source
    placement, and the deep distribute fallback when all per-segment
    placement has failed.

    For trajectory-projection fallback (departure: active threshold;
    arrival: opposite end) use `runway_backup_3857` instead.

    Defined here because `distribute_pathB.py` already calls this name
    from two paths (helicopter and the late `need_fallback` branch);
    without the function those paths would raise AttributeError on
    the rare studies that exercise them.
    """
    points = _runway_endpoint_assignment(runway)
    return points[runway_direction]


def runway_taxi_intersection_3857(runway_geom, taxi_geom) -> Optional[tuple]:
    """Centroid of the runway-centreline / taxi-route intersection.

    The runway centreline is buffered by RUNWAY_BUFFER_M (1 m) before
    intersecting, so a taxi route that merely touches or crosses the
    centreline produces a small intersection polygon or line whose
    centroid is the alignment reference point.

    Both geometries are EPSG:3857. Returns (x, y) or None if the taxi
    geometry is missing or does not intersect.

    Ported from the reference's `_runway_taxi_intersection_3857`.
    """
    if taxi_geom is None:
        return None
    inter = runway_geom.buffer(RUNWAY_BUFFER_M, quad_segs=10).intersection(taxi_geom)
    if inter.is_empty:
        return None
    c = inter.centroid
    return (c.x, c.y)


# ---------------------------------------------------------------------------
# Trajectory point projection
# ---------------------------------------------------------------------------


def project_anp(intersection_3857: tuple, az_deg: float, x: float, y: float) -> tuple:
    """Project an ANP-profile local (x, y) offset to EPSG:3857.

    ANP trajectory points are given as local offsets from the
    trajectory origin: `x` along the runway axis (signed: positive in
    the configured azimuth direction, negative in the opposite
    direction), `y` across it. ANP profiles in practice have y=0 for
    every point, so the relevant geometry is one-dimensional along the
    runway axis.

    Sign of `x` matters: for arrival profiles, approach points have
    x<0 (= behind the touchdown in motion direction) and rollout points
    have x>0 (= ahead). Without sign preservation both walk in the
    same direction from the origin, producing physically impossible
    trajectories. We honour the sign by walking |distance| at the
    configured azimuth for x>=0 and at (azimuth+180) for x<0. For
    departures (all x>=0) this is a no-op and the previous behaviour is
    preserved verbatim.

    Returns the projected (x, y) in EPSG:3857.
    """
    distance = math.hypot(x, y)
    effective_az = az_deg if x >= 0 else (az_deg + 180.0) % 360.0
    lon0, lat0 = TO_WGS84.transform(*intersection_3857)
    lon, lat, _ = GEOD.fwd(lon0, lat0, effective_az, distance)
    return TO_3857.transform(lon, lat)


def project_custom(
    intersection_3857: tuple, utm_epsg: int, x: float, y: float
) -> tuple:
    """Project a CUSTOM/ADS-B local (x, y) offset to EPSG:3857.

    CUSTOM (ADS-B-derived) trajectory points carry local offsets that
    are applied in the study's UTM frame, not geodesically: convert the
    intersection point to UTM, add the (x, y) offset in metres, convert
    back to EPSG:3857.

    Returns the projected (x, y) in EPSG:3857. Ported from the
    reference's `_project_custom`.
    """
    to_utm, to_3857 = utm_transformers(utm_epsg)
    ref_x_utm, ref_y_utm = to_utm.transform(*intersection_3857)
    return to_3857.transform(ref_x_utm + x, ref_y_utm + y)


# ---------------------------------------------------------------------------
# Ground distance
# ---------------------------------------------------------------------------


def ground_distance_m(p1_3857: tuple, p2_3857: tuple) -> float:
    """Geodesic ground distance between two EPSG:3857 points, in metres.

    EPSG:3857 is a conformal projection with severe distance distortion
    away from the equator, so the distance is computed by converting
    both points to WGS84 and taking the geodesic inverse, never as a
    planar 3857 distance. This matches the plugin's
    `ellipsoidal_2d_distance`.

    Ported from the reference's `_ground_distance_m`.
    """
    if p1_3857 == p2_3857:
        return 0.0
    lon1, lat1 = TO_WGS84.transform(*p1_3857)
    lon2, lat2 = TO_WGS84.transform(*p2_3857)
    _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)
    return dist


# ---------------------------------------------------------------------------
# Grid clipping
# ---------------------------------------------------------------------------


def clip_segment_2d(p1: tuple, p2: tuple, grid_bounds: dict) -> Optional[tuple]:
    """Clip a 2D segment against the axis-aligned grid bounds.

    `grid_bounds` is the dict returned by `grid_bounds_3857`: it carries
    `x_min`, `y_min`, `x_max`, `y_max` in EPSG:3857.

    Returns (clipped_p1, clipped_p2) for the portion of the segment
    inside the grid, or None if the segment is entirely outside or only
    touches the boundary at a point.

    Mirrors the plugin's `spatial.clip_segment_to_grid`
    (QgsClipper.clippedLine). Ported from the reference's
    `_clip_segment_2d`.
    """
    line = LineString([p1, p2])
    clip_box = box(
        grid_bounds["x_min"],
        grid_bounds["y_min"],
        grid_bounds["x_max"],
        grid_bounds["y_max"],
    )
    inter = line.intersection(clip_box)
    if inter.is_empty or inter.geom_type == "Point":
        return None
    if inter.geom_type == "LineString":
        cs = list(inter.coords)
        return (cs[0], cs[-1])
    if inter.geom_type == "MultiLineString":
        parts = list(inter.geoms)
        return (list(parts[0].coords)[0], list(parts[-1].coords)[-1])
    return None


# ---------------------------------------------------------------------------
# Grid bounds derivation
# ---------------------------------------------------------------------------


def grid_bounds_3857(
    x_cells: int,
    y_cells: int,
    x_res: float,
    y_res: float,
    ref_lat: float,
    ref_lon: float,
) -> dict:
    """Derive the AUSTAL grid bounds in EPSG:3857 from the grid definition.

    The grid is defined in `grid_3d_definition` by a cell count, a cell
    resolution in metres, and a reference lat/lon at the grid centre.
    The reference point is converted to the local UTM zone, the grid
    origin (south-west corner) is found by stepping half the grid
    extent south and west in UTM metres, then the origin is converted
    to EPSG:3857.

    The `scale = 1 / cos(ref_lat)` factor on `x_max`/`y_max` accounts
    for EPSG:3857's latitude-dependent distance distortion: a grid that
    is `x_cells * x_res` metres wide on the ground spans
    `x_cells * x_res * scale` units in EPSG:3857. This is the plugin's
    convention and the reference reproduces it; it is preserved here
    verbatim.

    Returns a dict with `x_min`, `y_min`, `x_max`, `y_max` (EPSG:3857)
    and `utm_epsg` (the derived UTM zone EPSG code).

    Ported from the reference's `_grid_bounds_3857`. The signature
    takes the six grid-definition fields directly rather than a SQLite
    connection, so this function stays free of any database concern;
    the caller (the movements/DB layer) reads `grid_3d_definition` and
    passes the fields in.
    """
    utm_zone = int((ref_lon + 180) // 6) + 1
    utm_epsg = utm_zone + (32600 if ref_lat >= 0 else 32700)
    to_utm = pyproj.Transformer.from_crs(4326, utm_epsg, always_xy=True)
    to_3857 = pyproj.Transformer.from_crs(utm_epsg, 3857, always_xy=True)
    ref_x_utm, ref_y_utm = to_utm.transform(ref_lon, ref_lat)
    origin_x_utm = ref_x_utm - (x_cells / 2.0) * x_res
    origin_y_utm = ref_y_utm - (y_cells / 2.0) * y_res
    x_min_3857, y_min_3857 = to_3857.transform(origin_x_utm, origin_y_utm)
    scale = 1.0 / math.cos(math.radians(ref_lat))
    return {
        "x_min": x_min_3857,
        "y_min": y_min_3857,
        "x_max": x_min_3857 + x_cells * x_res * scale,
        "y_max": y_min_3857 + y_cells * y_res * scale,
        "utm_epsg": utm_epsg,
        "origin_x_utm": origin_x_utm,
        "origin_y_utm": origin_y_utm,
        "ref_x_utm": ref_x_utm,
        "ref_y_utm": ref_y_utm,
        "x_res_m": float(x_res),
        "y_res_m": float(y_res),
    }


# ---------------------------------------------------------------------------
# UTM-native cell indexing
# ---------------------------------------------------------------------------
#
# The plugin computes cell indices in the LOCAL UTM CRS: 100 m on the
# ground = 100 m in UTM = exactly one cell. The standalone previously
# computed indices in EPSG:3857 with a constant `scale = 1/cos(ref_lat)`
# correction; that correction is exact only at the grid SW corner and
# drifts away from UTM by ~150-200 m by the time it reaches the airport
# centre, shifting cells by (+1, -1) to (+2, -1) vs the plugin.
#
# `make_3857_to_cell` and `make_3857_to_utm` are factory helpers that
# return closures sized to one grid definition. The closure caches the
# pyproj transformer (one construction per study run) so the per-point
# cost is one transform call, not three.


def make_3857_to_cell(grid_bounds: dict, grid_definition: dict):
    """Return a function (x_3857, y_3857) -> (ix, iy) using UTM cells.

    Replaces the 3857-via-scale `distribute.cell_index` for any caller
    that has 3857 coords and wants UTM-native cell indexing. The closure
    captures one `pyproj.Transformer` (3857 -> UTM) and the grid origin
    in UTM metres, so each call is one `Transformer.transform` plus two
    floor-divides.

    Cells outside [0, x_cells) x [0, y_cells) are CLAMPED into the
    boundary cell, the same convention the legacy `cell_index` used.
    """
    utm_epsg = int(grid_bounds["utm_epsg"])
    origin_x_utm = float(grid_bounds["origin_x_utm"])
    origin_y_utm = float(grid_bounds["origin_y_utm"])
    x_res = float(grid_bounds.get("x_res_m") or grid_definition["x_resolution"])
    y_res = float(grid_bounds.get("y_res_m") or grid_definition["y_resolution"])
    x_cells = int(grid_definition["x_cells"])
    y_cells = int(grid_definition["y_cells"])
    transformer = pyproj.Transformer.from_crs(3857, utm_epsg, always_xy=True)

    def to_cell(x_3857: float, y_3857: float) -> tuple:
        ux, uy = transformer.transform(x_3857, y_3857)
        ix = int((ux - origin_x_utm) // x_res)
        iy = int((uy - origin_y_utm) // y_res)
        if ix < 0:
            ix = 0
        elif ix >= x_cells:
            ix = x_cells - 1
        if iy < 0:
            iy = 0
        elif iy >= y_cells:
            iy = y_cells - 1
        return (ix, iy)

    return to_cell


def make_3857_to_utm(grid_bounds: dict):
    """Return a function (x_3857, y_3857) -> (x_utm, y_utm).

    Lighter-weight than `make_3857_to_cell` for callers that need to do
    geometric work in UTM (e.g. cut a polyline at grid lines for
    length-weighted cell apportionment). Caches the transformer the
    same way.
    """
    utm_epsg = int(grid_bounds["utm_epsg"])
    transformer = pyproj.Transformer.from_crs(3857, utm_epsg, always_xy=True)

    def to_utm_func(x_3857: float, y_3857: float) -> tuple:
        return transformer.transform(x_3857, y_3857)

    return to_utm_func
