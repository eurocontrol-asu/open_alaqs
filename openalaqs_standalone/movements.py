"""
movements: database accessor layer for the aircraft emission pipeline.

This module is the standalone's port of the database accessors in the
CAEP14 validation reference
(`validation/tools/compute_caep14_reference.py`, lines ~156-426). It
reads movements, aircraft, engines, trajectories, runway and taxi-route
geometry, and meteo from an OpenALAQS `.alaqs` SQLite file.

Two differences from the reference, both deliberate:

1. No `mod_spatialite`. The reference reads geometry columns via
   `ST_AsText(geometry)`, which needs the native SpatiaLite extension.
   This module reads the raw geometry BLOBs and parses them with
   `geometry.spatialite_blob_to_shapely`. The parsed coordinates are
   full float64 precision; the reference's `ST_AsText` path rounds to
   6 decimal places. The divergence is at most ~5e-7 m, far below the
   validation tolerance, and the WKB parse is the more accurate of the
   two. See `geometry.py` for the BLOB-format detail.

2. `get_runway` does not read `grid_3d_definition`. The reference's
   `_grid_bounds_3857` bundled the grid read with a SQLite connection;
   here the grid read is a separate accessor (`get_grid_definition`)
   and the bounds derivation lives in `geometry.grid_bounds_3857`,
   which takes plain fields. This keeps the database layer and the
   geometry math cleanly separated.

The accessors return plain dicts / lists / tuples, the same shapes the
reference produces, so the downstream compute code (ported next) can
consume either interchangeably. All geometry is EPSG:3857.

Connection helper: `connect(path)` opens a plain read-only-friendly
`sqlite3` connection. It does NOT enable extension loading and does
NOT load `mod_spatialite`. The `.alaqs` file is treated as read-only
for the duration of a calculation.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from shapely.geometry import LineString
from shapely.ops import linemerge

from openalaqs_standalone.geometry import spatialite_blob_to_shapely

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def connect(alaqs_path: str) -> sqlite3.Connection:
    """Open a connection to an `.alaqs` SQLite file.

    Unlike the reference's `_connect`, this does not enable extension
    loading and does not load `mod_spatialite`: geometry columns are
    read as raw BLOBs and parsed with shapely. The `.alaqs` is treated
    as read-only during a calculation; callers should not write to it.
    """
    return sqlite3.connect(alaqs_path)


# ---------------------------------------------------------------------------
# Runway and taxi-route geometry (WKB-sourced, no ST_AsText)
# ---------------------------------------------------------------------------


def get_runways(conn: sqlite3.Connection) -> dict:
    """Read every runway in `shapes_runways`, keyed by direction.

    Returns a dict mapping each runway-designator integer (e.g. 15, 33,
    7, 25) to the runway dict that direction belongs to. For a runway
    "33/15" both keys 33 and 15 point at the SAME runway dict, so the
    caller can look up by either end.

    Each runway dict has the same shape as `get_runway`'s return:
      runway_id, geom_3857, pt1_3857, pt2_3857, directions.

    Raises RuntimeError if `shapes_runways` is empty.

    Multi-runway support. Plugin-shaped studies with two or more
    runways (a study with 07/25 and 33/15 active) need per-movement runway
    selection, since `mov["runway_direction"]` identifies one of the
    two thresholds. The earlier `get_runway` reader was single-runway
    only and would silently pick whichever row sqlite returned first,
    making azimuth lookup fail with KeyError on movements that named
    a direction on a different runway. `get_runways` covers both
    cases; for single-runway studies the result is a 2-key dict
    pointing at one runway, identical-behavior under the lookup.
    """
    rows = conn.execute("SELECT runway_id, geometry FROM shapes_runways").fetchall()
    if not rows:
        raise RuntimeError("No runway found in shapes_runways")
    out: dict = {}
    for runway_id, geom_blob in rows:
        geom = spatialite_blob_to_shapely(geom_blob)
        coords = list(geom.coords)
        dirs = [
            int("".join(ch for ch in d if ch.isdigit())) for d in runway_id.split("/")
        ]
        rwy = {
            "runway_id": runway_id,
            "geom_3857": geom,
            "pt1_3857": (coords[0][0], coords[0][1]),
            "pt2_3857": (coords[-1][0], coords[-1][1]),
            "directions": dirs,
        }
        for d in dirs:
            out[d] = rwy
    return out


def get_runway(conn: sqlite3.Connection) -> dict:
    """Read the single runway from `shapes_runways`.

    Returns a dict with:
      runway_id   the raw designator string, e.g. "06/24"
      geom_3857   the shapely LineString of the centreline (EPSG:3857)
      pt1_3857    the first centreline endpoint, (x, y)
      pt2_3857    the last centreline endpoint, (x, y)
      directions  the two designator integers, e.g. [6, 24]

    Ported from the reference's `_get_runway`. The only change is that
    the geometry is read from the raw BLOB via
    `spatialite_blob_to_shapely` instead of `ST_AsText` + `wkt.loads`.

    Raises RuntimeError if `shapes_runways` is empty, matching the
    reference.
    """
    row = conn.execute("SELECT runway_id, geometry FROM shapes_runways").fetchone()
    if not row:
        raise RuntimeError("No runway found in shapes_runways")
    runway_id, geom_blob = row
    geom = spatialite_blob_to_shapely(geom_blob)
    coords = list(geom.coords)
    dirs = [int("".join(ch for ch in d if ch.isdigit())) for d in runway_id.split("/")]
    return {
        "runway_id": runway_id,
        "geom_3857": geom,
        "pt1_3857": (coords[0][0], coords[0][1]),
        "pt2_3857": (coords[-1][0], coords[-1][1]),
        "directions": dirs,
    }


def get_taxi_route_linestring(
    conn: sqlite3.Connection, route_name: str
) -> Optional[LineString]:
    """Read and merge the taxiway segments of a named taxi route.

    `user_taxiroute_taxiways.sequence` is a comma-separated list of
    `shapes_taxiways.taxiway_id` values. Each segment's geometry is
    read from its BLOB, the segments are merged into a single
    LineString, and if the merge produces a MultiLineString (segments
    that do not connect end-to-end) the first part is taken.

    Returns the merged LineString (EPSG:3857) or None if the route name
    is unknown or has no segments.

    Ported from the reference's `_get_taxi_route_linestring`. The only
    change is that each segment geometry is read from the raw BLOB via
    `spatialite_blob_to_shapely` instead of `ST_AsText` + `wkt.loads`.
    """
    row = conn.execute(
        "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name=?",
        (route_name,),
    ).fetchone()
    if not row:
        return None
    parts = []
    for name in row[0].split(","):
        sub = conn.execute(
            "SELECT geometry FROM shapes_taxiways WHERE taxiway_id=?",
            (name,),
        ).fetchone()
        if sub:
            parts.append(spatialite_blob_to_shapely(sub[0]))
    if not parts:
        return None
    merged = linemerge(parts) if len(parts) > 1 else parts[0]
    if merged.geom_type == "MultiLineString":
        merged = list(merged.geoms)[0]
    return merged


# ---------------------------------------------------------------------------
# Grid definition
# ---------------------------------------------------------------------------


def get_grid_definition(conn: sqlite3.Connection) -> dict:
    """Read the inventory grid definition from `grid_3d_definition`.

    Returns a dict with `x_cells`, `y_cells`, `x_resolution`,
    `y_resolution`, `reference_latitude`, `reference_longitude`.

    This accessor did not exist in the reference as a standalone
    function: the reference's `_grid_bounds_3857` read these fields
    inline. Splitting the database read out lets
    `geometry.grid_bounds_3857` stay free of any SQLite concern. The
    caller reads the definition here and passes the fields to the
    geometry function.
    """
    row = conn.execute(
        "SELECT x_cells, y_cells, x_resolution, y_resolution, "
        "reference_latitude, reference_longitude FROM grid_3d_definition"
    ).fetchone()
    return {
        "x_cells": row[0],
        "y_cells": row[1],
        "x_resolution": row[2],
        "y_resolution": row[3],
        "reference_latitude": row[4],
        "reference_longitude": row[5],
    }


# ---------------------------------------------------------------------------
# Movements
# ---------------------------------------------------------------------------


def get_movement(conn: sqlite3.Connection, oid: int) -> Optional[dict]:
    """Read one movement from `user_aircraft_movements` by oid.

    Returns a dict with the movement fields, or None if the oid does
    not exist. `runway_direction` is parsed to an integer from the
    `runway` designator string; `taxi_fuel_ratio` defaults to 1.0 when
    NULL; `number_of_stop_and_gos` defaults to 0 when NULL.

    Ported from the reference's `_get_movement`, with three added
    fields: `gate` (the gate id the movement references, may be None),
    `gate_emissions_code` (1 to include gate emissions, 0 to suppress
    them, may be None), and `apu_code` (the APU run mode the user
    set on the movement: -1/0 = no APU, 1 = APU at stand only,
    2 = APU at stand and during taxi; may be None, in which case the
    APU compute treats it as 1 to match the plugin's permissive
    fallback). The reference's aircraft trajectory pipeline did not
    need these; the per-movement gate and APU computes do. The
    addition is purely additive: every field the reference returned is
    still returned unchanged.
    """
    row = conn.execute(
        """
        SELECT oid, runway_time, block_time, aircraft, departure_arrival,
               engine_name, profile_id, taxi_route, runway, taxi_fuel_ratio,
               number_of_stop_and_gos, gate, gate_emissions_code, tow_ratio,
               apu_code
        FROM user_aircraft_movements WHERE oid=?
        """,
        (oid,),
    ).fetchone()
    if not row:
        return None

    # Numeric-field coercion. Plugin-shaped studies leave
    # taxi_fuel_ratio and number_of_stop_and_gos as empty strings on
    # every movement and rely on the plugin to default them at compute
    # time. SQLite returns those as Python str '', not None, so the
    # earlier "is not None" / "or 0" guards passed the empty string
    # through unchanged and downstream multiplications hit a TypeError.
    # Coerce both: None/empty-string -> default, otherwise the typed
    # value. Robust against accidental string-encoded numbers like
    # '1.0' too.
    def _as_float(v, default):
        if v is None or v == "":
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def _as_int(v, default):
        if v is None or v == "":
            return default
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    return {
        "oid": row[0],
        "runway_time": row[1],
        "block_time": row[2],
        "aircraft": row[3],
        "departure_arrival": row[4],
        "engine_name": row[5],
        "profile_id": row[6],
        "taxi_route": row[7],
        "runway_direction": int(
            "".join(ch for ch in (row[8] or "") if ch.isdigit()) or "0"
        ),
        "taxi_fuel_ratio": _as_float(row[9], 1.0),
        "number_of_stop_and_gos": _as_int(row[10], 0),
        "gate": row[11],
        "gate_emissions_code": row[12],
        # tow_ratio: take-off-weight ratio (actual TOGW / max certified
        # TOGW). Used only by the NOx ambient correction (apply_nox_
        # corrections=True). Defaults to None when unset; the
        # correction module then drops the weight term (treats it as
        # ratio=1.0).
        "tow_ratio": _as_float(row[13], None) if row[13] not in (None, "") else None,
        # apu_code: user-set APU run mode on the movement.
        # -1 / 0 = suppress APU emissions; 1 = APU at stand only;
        # 2 = APU at stand and during taxi. None / NULL is passed
        # through; compute_apu_movements treats None as 1 (match the
        # plugin's permissive fallback when the column is absent).
        "apu_code": row[14],
    }


def get_movement_oids(conn: sqlite3.Connection) -> list[int]:
    """Return all movement oids in ascending order.

    Convenience accessor for iterating the whole study. The reference
    did this inline in `main()`; pulling it into the database layer
    keeps the compute code free of raw SQL.
    """
    return [
        r[0]
        for r in conn.execute("SELECT oid FROM user_aircraft_movements ORDER BY oid")
    ]


def get_movement_oids_in_window(
    conn: sqlite3.Connection,
    start,
    end,
) -> list[int]:
    """Return movement oids whose start timestamp falls in `[start, end)`.

    Start-time semantics differ by direction. A departure starts at
    the gate and ends at takeoff, so its start is `block_time`. An
    arrival starts at touchdown and ends at the gate, so its start is
    `runway_time`. This function applies the direction-aware rule so
    both are filtered symmetrically.

    `start` and `end` are compared lexicographically against the SQLite
    TIMESTAMP columns, which are stored as ISO-like strings
    ('YYYY-MM-DD HH:MM:SS'). The caller must pass values that compare
    correctly under that ordering (datetime.isoformat with a space
    separator works; so does a str in that exact shape).

    Either bound may be None to mean "unbounded on that side".
    """
    start_s = (
        start.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(start, "strftime")
        else (start if start is not None else None)
    )
    end_s = (
        end.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(end, "strftime")
        else (end if end is not None else None)
    )

    # CASE expression picks the right column per direction. 'D'
    # (departure) uses block_time as start; otherwise (arrival)
    # uses runway_time. Movements with NULL on the relevant column
    # are excluded, matching how the compute treats missing data.
    where_parts = []
    params = []
    start_expr = (
        "CASE departure_arrival " "WHEN 'D' THEN block_time ELSE runway_time END"
    )
    if start_s is not None:
        where_parts.append(f"{start_expr} >= ?")
        params.append(start_s)
    if end_s is not None:
        where_parts.append(f"{start_expr} < ?")
        params.append(end_s)
    where_parts.append(f"{start_expr} IS NOT NULL")

    sql = (
        "SELECT oid FROM user_aircraft_movements "
        f"WHERE {' AND '.join(where_parts)} "
        "ORDER BY oid"
    )
    return [r[0] for r in conn.execute(sql, params)]


# ---------------------------------------------------------------------------
# Aircraft and engines
# ---------------------------------------------------------------------------


def get_engine_count(conn: sqlite3.Connection, icao: str) -> int:
    """Engine count for an aircraft ICAO type.

    Returns 0 if the type is unknown or the value is NULL or
    unparseable. Ported verbatim from the reference's
    `_get_engine_count`.
    """
    row = conn.execute(
        "SELECT engine_count FROM default_aircraft WHERE icao=?", (icao,)
    ).fetchone()
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (ValueError, TypeError):
        return 0


def get_aircraft_groups(conn: sqlite3.Connection) -> dict:
    """Return {icao: ac_group} for every default_aircraft row.

    Read once per study and used by the source-dynamics (smooth-and-shift)
    apportionment to resolve each movement's aircraft group, which keys the
    default_emission_dynamics lookup. NULL/empty groups map to None (the
    source_dynamics code then falls back to line apportionment for that
    aircraft, matching the plugin's zero-extension default).
    """
    out: dict = {}
    for icao, ac_group in conn.execute("SELECT icao, ac_group FROM default_aircraft"):
        out[icao] = ac_group if ac_group else None
    return out


def get_mtow_kg(conn: sqlite3.Connection, icao: str) -> Optional[float]:
    """Maximum take-off weight in kg for an aircraft ICAO type.

    Returns None if the type is unknown or the value is NULL or
    unparseable. Ported verbatim from the reference's `_get_mtow_kg`.
    """
    row = conn.execute(
        "SELECT mtow FROM default_aircraft WHERE icao=?", (icao,)
    ).fetchone()
    if not row or row[0] is None:
        return None
    try:
        return float(row[0])
    except (ValueError, TypeError):
        return None


def get_engine_ei(conn: sqlite3.Connection, engine_name: str) -> dict:
    """Per-mode EEDB fuel flow and emission indices for an engine.

    Returns a dict keyed by mode label (TX, AP, CL, TO), each value a
    dict with `ff` (fuel flow, kg/s/engine) and the five `*_ei`
    emission indices (g/kg). NULL emission indices are coerced to 0.0.

    The match is exact on `engine_full_name`. The earlier LIKE
    `%engine_name%` pattern was incorrect: short engine names that are
    substrings of longer ones (e.g. "FOI-3" inside FOI-30..FOI-39,
    "FOI-1" inside FOI-10..FOI-199, "ECTL_1" inside ECTL_10..ECTL_19)
    would match multiple engines, and the dict assignment below would
    silently overwrite earlier rows with the LAST match. Concretely:
    SB20 (engine FOI-3) was getting FOI-39 EI values, producing ~1/3
    the correct fuel flow and ~1/2 the correct NOx EI. Plugin reference
    does NOT use LIKE; it loads the full EI table into an in-memory
    OrderedDict keyed by engine_name (see EngineEmissionIndicesDatabase
    in interfaces/EngineDatabases.py), which is an exact-match lookup.
    """
    result: dict = {}
    for r in conn.execute(
        """
        SELECT mode, fuel_kg_sec, co_ei, hc_ei, nox_ei, sox_ei, pm10_ei
        FROM default_aircraft_engine_ei WHERE engine_full_name = ?
        """,
        (engine_name,),
    ):
        result[r[0]] = {
            "ff": r[1],
            "co_ei": r[2] or 0.0,
            "hc_ei": r[3] or 0.0,
            "nox_ei": r[4] or 0.0,
            "sox_ei": r[5] or 0.0,
            "pm10_ei": r[6] or 0.0,
        }
    return result


# ---------------------------------------------------------------------------
# Trajectories
# ---------------------------------------------------------------------------


def get_trajectory(conn: sqlite3.Connection, profile_id: str) -> list:
    """Read a trajectory profile's points, ordered by point index.

    Returns a list of rows, each
    `(point, x_m, y_m, z_m, tas_metres, mode, course)`. ANP and
    CUSTOM/ADS-B profiles share the table; the `mode` column of the
    first point distinguishes them downstream ("CUSTOM" for ADS-B).

    Ported verbatim from the reference's `_get_trajectory`. The
    `power` and `fuel_flow_kgm` columns the bffm2_traj method needs are
    re-read on demand by the compute layer, exactly as the reference
    does; this accessor keeps the same 7-column shape.
    """
    return list(
        conn.execute(
            """
            SELECT point, x_m, y_m, z_m, tas_metres, mode, course
            FROM default_aircraft_profiles WHERE profile_id=?
            ORDER BY point
            """,
            (profile_id,),
        )
    )


def get_trajectory_point_power_ff(
    conn: sqlite3.Connection, profile_id: str, point: int
) -> tuple:
    """Read the `power` and `fuel_flow_kgm` of one trajectory point.

    The bffm2_traj method needs these two columns, which the 7-column
    `get_trajectory` does not return. The reference re-reads them
    per-point inside `_bffm2_traj_ff_amb`; this accessor exposes that
    same query so the compute layer carries no raw SQL.

    Returns `(power, fuel_flow_kgm)`, either of which may be None.
    """
    row = conn.execute(
        "SELECT power, fuel_flow_kgm FROM default_aircraft_profiles "
        "WHERE profile_id=? AND point=?",
        (profile_id, point),
    ).fetchone()
    if row is None:
        return (None, None)
    return (row[0], row[1])


# ---------------------------------------------------------------------------
# Helicopters
# ---------------------------------------------------------------------------


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """True iff the named table exists in this connection.

    Used by the helicopter readers below so that a study without any
    helicopter support (no `default_helicopter` / `default_helicopter_engines`
    tables, e.g. the upstream `example/training` fixture) is handled
    gracefully -- every aircraft is treated as fixed-wing.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def get_helicopter(conn: sqlite3.Connection, icao: str) -> Optional[dict]:
    """Read a helicopter's catalog row from `default_helicopter`.

    Returns a dict with `mtow_kg`, `engine_count`, `engine_name`,
    `max_shp_per_engine`, or None if the ICAO type is not a known
    helicopter, or if the `default_helicopter` table is absent
    altogether (a study without any helicopter support, such as the
    upstream `example/training` fixture, has no such table; every
    aircraft in those studies is fixed-wing).

    The reference read these fields inline in
    `_compute_helicopter_for_movement`; pulling the read into the
    database layer keeps the compute code SQL-free.
    """
    if not _table_exists(conn, "default_helicopter"):
        return None
    row = conn.execute(
        "SELECT mtow_kg, engine_count, engine_name, max_shp_per_engine "
        "FROM default_helicopter WHERE icao=?",
        (icao,),
    ).fetchone()
    if row is None:
        return None
    return {
        "mtow_kg": row[0],
        "engine_count": row[1],
        "engine_name": row[2],
        "max_shp_per_engine": row[3],
    }


def get_helicopter_engine_type(
    conn: sqlite3.Connection, engine_name: str
) -> Optional[str]:
    """Read a helicopter engine's `engine_type` from
    `default_helicopter_engines`.

    Returns the engine-type string, or None if the engine is unknown,
    or if the `default_helicopter_engines` table is absent (same
    rationale as `get_helicopter`).
    """
    if not _table_exists(conn, "default_helicopter_engines"):
        return None
    row = conn.execute(
        "SELECT engine_type FROM default_helicopter_engines " "WHERE engine_name=?",
        (engine_name,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


# ---------------------------------------------------------------------------
# Meteo
# ---------------------------------------------------------------------------

# ISA reference conditions. Matches the reference's `_get_meteo_at`
# use_isa branch and the plugin's actual emission-CSV output (which was
# generated with ISA regardless of the loaded meteo; see the validation
# notes). The speed_of_sound value is the ISA sea-level figure.
ISA_AMBIENT = {
    "T_K": 288.15,
    "P_Pa": 101325.0,
    "RH": 0.6,
    "Humidity": 0.00634,
    "speed_of_sound_m_s": 340.29,
}


def get_meteo_at(
    conn: sqlite3.Connection, runway_time: str, use_isa: bool = True
) -> dict:
    """Return ambient conditions for the BFFM2 calculation.

    Two modes:
      use_isa=True (default): ISA conditions (288.15 K, 101325 Pa,
        RH 0.6). This matches the plugin's current emission-CSV output,
        which was generated with ISA regardless of the loaded meteo.
      use_isa=False: the `tbl_InvMeteo` row whose `DateTime` is the
        latest at or before `runway_time`. Matches the plugin's
        intended meteo lookup (`EmissionCalculation.getAmbientCondition`).
        Falls back to ISA if `tbl_InvMeteo` has no qualifying row.

    The ISA-vs-meteo choice is explicit and surfaced to the caller, per
    the validation finding that silent ISA fallback was a real defect.

    Ported verbatim from the reference's `_get_meteo_at`, with the ISA
    dict factored out as the module constant `ISA_AMBIENT`.
    """
    if use_isa:
        return dict(ISA_AMBIENT)
    row = conn.execute(
        "SELECT Temperature, SeaLevelPressure, RelativeHumidity, Humidity "
        "FROM tbl_InvMeteo WHERE DateTime <= ? "
        "ORDER BY DateTime DESC LIMIT 1",
        (runway_time,),
    ).fetchone()
    if row is None:
        return get_meteo_at(conn, runway_time, use_isa=True)
    T_K = float(row[0])
    return {
        "T_K": T_K,
        "P_Pa": float(row[1]),
        "RH": float(row[2]),
        "Humidity": float(row[3]) if row[3] is not None else None,
        "speed_of_sound_m_s": 331.3 + 0.606 * (T_K - 273.15),
    }


# Default LTO vertical ceiling: 3000 ft (914.4 m). The plugin reads
# user_study_setup.vertical_limit; if that table or column is missing
# this constant is used as the final fallback.
DEFAULT_VERTICAL_LIMIT_M = 914.4


def get_vertical_limit_m(conn: sqlite3.Connection) -> float:
    """Return user_study_setup.vertical_limit (m), falling back to 914.4
    if the table or column is missing or NULL. Used as the fallback
    max_height when tbl_InvMeteo has no MixingHeight for a given time.
    Matches the plugin's MovementSourceModule.process() fallback at the
    `except AttributeError` branch.
    """
    try:
        row = conn.execute(
            "SELECT vertical_limit FROM user_study_setup LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return DEFAULT_VERTICAL_LIMIT_M
    if row is None or row[0] is None:
        return DEFAULT_VERTICAL_LIMIT_M
    return float(row[0])


def get_airport_elevation_m(conn: sqlite3.Connection) -> float:
    """Return user_study_setup.airport_elevation (m), defaulting to 0.0.

    Used by the NOx ambient correction (nox_correction module) to
    compute the ISA temperature at the airport for the temperature
    deviation term. The plugin reads the same value via
    `self._method["config"]["airport_altitude"]` in
    MovementEmissionCalculator._apply_nox_corrections.
    """
    try:
        row = conn.execute(
            "SELECT airport_elevation FROM user_study_setup LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0.0
    if row is None or row[0] is None:
        return 0.0
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return 0.0


def get_mixing_height_at(conn: sqlite3.Connection, runway_time: str) -> float:
    """Return MixingHeight (m) for the meteo period containing
    `runway_time`. Mirrors the plugin's
    `ambient_conditions.getMixingHeight()` lookup, which the plugin uses
    as `max_height` in `apply_height_limits`.

    Lookup: the `tbl_InvMeteo` row whose `DateTime` is the latest at or
    before `runway_time` (the same temporal rule `get_meteo_at` uses).

    Fallback chain, matching MovementSourceModule.process():
      1. `tbl_InvMeteo.MixingHeight` for the matched period.
      2. `user_study_setup.vertical_limit` (typically 914.4 m).
      3. `DEFAULT_VERTICAL_LIMIT_M` (914.4 m).
    """
    try:
        row = conn.execute(
            "SELECT MixingHeight FROM tbl_InvMeteo WHERE DateTime <= ? "
            "ORDER BY DateTime DESC LIMIT 1",
            (runway_time,),
        ).fetchone()
    except sqlite3.OperationalError:
        return get_vertical_limit_m(conn)
    if row is None or row[0] is None:
        return get_vertical_limit_m(conn)
    return float(row[0])


# ---------------------------------------------------------------------------
# Gate accessors (Phase A2)
# ---------------------------------------------------------------------------
#
# Gate emissions are per-movement: the ground support equipment (GSE)
# and ground power unit (GPU) running while an aircraft occupies a
# gate. The emission for one movement depends on the gate's type, the
# aircraft's group, and the operation type (arrival or departure),
# looked up in the `default_gate_profiles` table. These accessors
# expose the three pieces the gate compute needs.


def get_aircraft_group(conn: sqlite3.Connection, icao: str) -> Optional[str]:
    """Return the aircraft group string for an ICAO type.

    The group (e.g. 'JET LARGE', 'JET SMALL') is the key used to look
    up a gate emission profile in `default_gate_profiles`. Returns
    None if the type is unknown or the group is NULL or blank.
    """
    row = conn.execute(
        "SELECT ac_group FROM default_aircraft WHERE icao=?", (icao,)
    ).fetchone()
    if not row or row[0] is None:
        return None
    group = str(row[0]).strip()
    return group or None


def get_gate(conn: sqlite3.Connection, gate_id: str) -> Optional[dict]:
    """Return a gate's record by its gate_id.

    The dict carries `gate_id`, `gate_type` (e.g. 'PIER', 'REMOTE',
    'CARGO'), `height_m`, `instudy` (bool), and `geom_3857` (the gate
    polygon as a shapely geometry, parsed from the SpatiaLite BLOB).
    Returns None if no gate has that id.
    """
    row = conn.execute(
        "SELECT gate_id, gate_type, gate_height, instudy, geometry "
        "FROM shapes_gates WHERE gate_id=?",
        (gate_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        height = float(row[2]) if row[2] is not None else 0.0
    except (ValueError, TypeError):
        height = 0.0
    return {
        "gate_id": row[0],
        "gate_type": str(row[1]) if row[1] is not None else "",
        "height_m": height,
        "instudy": str(row[3]) == "1",
        "geom_3857": spatialite_blob_to_shapely(row[4]),
    }


def get_gate_profiles(conn: sqlite3.Connection) -> dict:
    """Return the whole `default_gate_profiles` table as a lookup dict.

    Keyed by (gate_type, ac_group, emis_type, op_type), each value is
    a dict with `time_min` (gate occupancy in minutes), `time_unit`,
    `emis_unit`, and the per-pollutant emission rates `co`, `hc`,
    `nox`, `sox`, `pm10`. The rates are in grams/hour in the training
    data; `emis_unit` is carried through so the consumer can assert
    that rather than assuming it.

    The whole table is small (tens of rows), so it is read once and
    reused for every movement, the same caching pattern used for the
    runway/taxi intersections.
    """
    out: dict = {}
    rows = conn.execute(
        "SELECT gate_type, ac_group, emis_type, op_type, time, "
        "time_unit, emis_unit, co, hc, nox, sox, pm10 "
        "FROM default_gate_profiles"
    ).fetchall()
    for r in rows:
        gate_type, ac_group, emis_type, op_type = r[0], r[1], r[2], r[3]
        key = (
            str(gate_type),
            str(ac_group),
            str(emis_type),
            str(op_type),
        )

        def _f(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return 0.0

        out[key] = {
            "time_min": _f(r[4]),
            "time_unit": str(r[5]) if r[5] is not None else "",
            "emis_unit": str(r[6]) if r[6] is not None else "",
            "co": _f(r[7]),
            "hc": _f(r[8]),
            "nox": _f(r[9]),
            "sox": _f(r[10]),
            "pm10": _f(r[11]),
        }
    return out
