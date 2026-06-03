"""CAEP14 reference emissions per movement, reproducing the OpenALAQS plugin
calculation exactly so that the result can be compared 1:1 with the plugin
emissions CSV output.

Method coverage
---------------
* bymode  : implemented (this file)
* bffm2_traj, bffm2_anchor : TODO (will reuse open_alaqs/core/tools/bffm2.py)

Inputs are read from the *same* _out.alaqs database the plugin reads:
* default_aircraft_profiles            : trajectory points (ANP or CUSTOM)
* default_aircraft_engine_ei           : engine emission indices and ff
* default_aircraft.engine_count        : engines per aircraft
* user_aircraft_movements              : runway_time, block_time, taxi route,
                                         taxi fuel ratio, profile, runway, ...
* shapes_runways, shapes_taxiways      : geometries used for runway-aligned
                                         coordinate projection (EPSG:3857)
* user_taxiroute_taxiways              : the taxi-route sequence per movement
* grid_3d_definition + user_study_setup: grid bounds derivation
* tbl_InvMeteo                         : meteorology (not used by bymode itself
                                         but kept for future BFFM2 use)

Plugin-equivalence summary (bymode)
-----------------------------------
For each fixed-wing movement:
* TX (taxi-out / taxi-in):
    taxi_time_s = abs(runway_time - block_time)            from movements
    TX_fuel     = taxi_time_s * ff_TX * n_engines * taxi_fuel_ratio
    em[p]      += TX_fuel * EI_TX[p] / 1000   for each pollutant
    CO2        += TX_fuel * 3.16

* Trajectory (TO/CL for D, AP for A) per segment:
    1. Vertical clip at 914.4 m, with 1e-6 m tolerance (matches the
       apply_height_limits ULP fix).  If both endpoints are at or above
       the ceiling, the segment is dropped.
    2. Runway-aligned projection of both endpoints to EPSG:3857:
       - ANP profile: geodesic forward projection of distance =
         sqrt(local_x^2 + local_y^2) from the runway-taxi-route
         intersection at the runway azimuth.
       - CUSTOM (ADS-B) profile: convert intersection to UTM, add
         (local_x, local_y) UTM offsets, convert back to EPSG:3857.
    3. 2D grid clip in EPSG:3857 using flat Liang-Barsky (Shapely's
       intersection with the bounding box).  If outside grid, segment
       is dropped; if partially inside, the clipped endpoints are kept.
    4. Compute ground metres of the (possibly clipped) segment via
       geodesic inverse on WGS84.  This matches the plugin's
       ellipsoidal_2d_distance for points in EPSG:3857.
    5. seg_time = ground_metres / avg_TAS  (avg_TAS from original points)
       seg_fuel = seg_time * ff[mode] * n_engines
       em[p]   += seg_fuel * EI[mode][p] / 1000
       CO2     += seg_fuel * 3.16

Stop-and-go is zero in the training fixture; not implemented yet.
Helicopters (no profile_id) are skipped: handled by FOCA module
separately and already validated.
"""

import argparse
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Third-party - already required by the plugin's ADS-B importer and tests
import pyproj
from shapely import wkt as _shapely_wkt
from shapely.geometry import LineString, box
from shapely.ops import linemerge

# Plugin-side FOCA helicopter math (pure Python, no QGIS dependency)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from open_alaqs.core.tools.bffm2 import (  # noqa: E402
    calculate_emission_index as bffm2_ei,
)
from open_alaqs.core.tools.foca_heli import (  # noqa: E402
    GI_ARRIVAL_FRACTION,
    GI_DEPARTURE_FRACTION,
    PROFILES,
    HelicopterCategory,
    derive_category,
)
from open_alaqs.core.tools.foca_heli_utils import (  # noqa: E402
    _mode_result,
    compute_mode_emissions,
)

# ---------------------------------------------------------------------------
# Constants (must match the plugin)
# ---------------------------------------------------------------------------

MAX_HEIGHT_M = 914.4
EPS_VERTICAL_M = 1e-6


def _mixing_height_at(conn, runway_time: str) -> float:
    """Return the inventory vertical ceiling (m) for the meteo period
    containing `runway_time`. Mirrors the plugin's
    `ambient_conditions.getMixingHeight()` lookup, which the plugin
    uses as `max_height` in `apply_height_limits`.

    Lookup: the `tbl_InvMeteo` row whose `DateTime` is the latest at or
    before `runway_time` (same temporal rule as `_get_meteo_at`).

    Fallback chain, matching the standalone's `get_mixing_height_at`
    and the plugin's `MovementSourceModule.process`:
      1. `tbl_InvMeteo.MixingHeight` for the matched period.
      2. `user_study_setup.vertical_limit` (typically 914.4 m).
      3. `MAX_HEIGHT_M` (914.4 m).

    This replaces the earlier hardcoded `MAX_HEIGHT_M`. The training_v3
    fixture has `MixingHeight = 914.4` at every movement hour, so the
    constant matched the per-hour lookup by coincidence. The val_out
    fixture deliberately varies MixingHeight (e.g. 1500 m at mov 8's
    hour, 600 m at mov 10's hour) to test per-hour handling.
    """
    try:
        row = conn.execute(
            "SELECT MixingHeight FROM tbl_InvMeteo WHERE DateTime <= ? "
            "ORDER BY DateTime DESC LIMIT 1",
            (runway_time,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is not None and row[0] is not None:
        return float(row[0])
    try:
        vl = conn.execute(
            "SELECT vertical_limit FROM user_study_setup LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        vl = None
    if vl is not None and vl[0] is not None:
        return float(vl[0])
    return MAX_HEIGHT_M


CO2_PER_KG_FUEL = 3.16
RUNWAY_BUFFER_M = 1.0
# Brake-wear PM10 emission for arrivals (per MovementEmissionCalculator
# _apply_single_engine_taxiing_emissions_for_arrival).  Applied once on the
# first taxi-in segment for arriving aircraft whose MTOW exceeds the
# threshold.  Linear model: brake_wear_g = MTOW * slope - intercept.
BRAKE_WEAR_MTOW_THRESHOLD_KG = 18632.0
BRAKE_WEAR_SLOPE = 0.000476
BRAKE_WEAR_INTERCEPT = 8.74
POLLUTANTS = ("co", "co2", "hc", "nox", "sox", "pm10", "pm25")
EI_COLS = {
    "co": "co_ei",
    "hc": "hc_ei",
    "nox": "nox_ei",
    "sox": "sox_ei",
    "pm10": "pm10_ei",
}
# Mapping from default_aircraft_engine_ei mode labels to the bffm2 module's
# expected dict keys.
BFFM2_MODE_NAMES = {
    "TX": "Idle",
    "AP": "Approach",
    "CL": "Climbout",
    "TO": "Takeoff",
}
# CAEP14 default installation corrections (same as bffm2 module defaults but
# kept explicit here for traceability against SAE AIR-5715).
BFFM2_INSTALLATION_CORRECTIONS = {
    "Takeoff": 1.010,
    "Climbout": 1.013,
    "Approach": 1.020,
    "Idle": 1.100,
}

_GEOD = pyproj.Geod(ellps="WGS84")
_TO_WGS84 = pyproj.Transformer.from_crs(3857, 4326, always_xy=True)
_TO_3857 = pyproj.Transformer.from_crs(4326, 3857, always_xy=True)
_UTM_TRANSFORMER_CACHE: dict = {}


def _utm_transformers(utm_epsg: int):
    if utm_epsg not in _UTM_TRANSFORMER_CACHE:
        _UTM_TRANSFORMER_CACHE[utm_epsg] = (
            pyproj.Transformer.from_crs(3857, utm_epsg, always_xy=True),
            pyproj.Transformer.from_crs(utm_epsg, 3857, always_xy=True),
        )
    return _UTM_TRANSFORMER_CACHE[utm_epsg]


# ---------------------------------------------------------------------------
# Spatial helpers
# ---------------------------------------------------------------------------


def _connect(alaqs_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(alaqs_path)
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")
    return conn


def _get_runway(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT runway_id, ST_AsText(geometry) FROM shapes_runways"
    ).fetchone()
    if not row:
        raise RuntimeError("No runway found in shapes_runways")
    runway_id, geom_wkt = row
    geom = _shapely_wkt.loads(geom_wkt)
    coords = list(geom.coords)
    dirs = [int("".join(ch for ch in d if ch.isdigit())) for d in runway_id.split("/")]
    return {
        "runway_id": runway_id,
        "geom_3857": geom,
        "pt1_3857": (coords[0][0], coords[0][1]),
        "pt2_3857": (coords[-1][0], coords[-1][1]),
        "directions": dirs,
    }


def _get_taxi_route_linestring(
    conn: sqlite3.Connection, route_name: str
) -> Optional[LineString]:
    row = conn.execute(
        "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name=?",
        (route_name,),
    ).fetchone()
    if not row:
        return None
    parts = []
    for name in row[0].split(","):
        sub = conn.execute(
            "SELECT ST_AsText(geometry) FROM shapes_taxiways WHERE taxiway_id=?",
            (name,),
        ).fetchone()
        if sub:
            parts.append(_shapely_wkt.loads(sub[0]))
    if not parts:
        return None
    merged = linemerge(parts) if len(parts) > 1 else parts[0]
    if merged.geom_type == "MultiLineString":
        merged = list(merged.geoms)[0]
    return merged


def _runway_taxi_intersection_3857(runway_geom, taxi_geom) -> Optional[tuple]:
    if taxi_geom is None:
        return None
    inter = runway_geom.buffer(RUNWAY_BUFFER_M, quad_segs=10).intersection(taxi_geom)
    if inter.is_empty:
        return None
    c = inter.centroid
    return (c.x, c.y)


def _bearing_deg(p1_3857: tuple, p2_3857: tuple) -> float:
    lon1, lat1 = _TO_WGS84.transform(p1_3857[0], p1_3857[1])
    lon2, lat2 = _TO_WGS84.transform(p2_3857[0], p2_3857[1])
    fwd_az, _, _ = _GEOD.inv(lon1, lat1, lon2, lat2)
    return fwd_az % 360.0


def _runway_azimuth_deg(runway: dict, runway_direction: int, is_dep: bool) -> float:
    az = _bearing_deg(runway["pt1_3857"], runway["pt2_3857"])
    expected = {d: (d * 10) % 360 for d in runway["directions"]}
    diffs = {d: min(abs(az - hdg), 360 - abs(az - hdg)) for d, hdg in expected.items()}
    start_dir = min(diffs, key=diffs.get)
    end_dir = [d for d in runway["directions"] if d != start_dir][0]
    points = {start_dir: runway["pt1_3857"], end_dir: runway["pt2_3857"]}
    opp = end_dir if runway_direction == start_dir else start_dir
    backup = points[runway_direction] if is_dep else points[opp]
    target = points[opp] if is_dep else points[runway_direction]
    return _bearing_deg(backup, target)


def _project_anp(intersection_3857, az_deg, x, y) -> tuple:
    distance = math.hypot(x, y)
    lon0, lat0 = _TO_WGS84.transform(*intersection_3857)
    lon, lat, _ = _GEOD.fwd(lon0, lat0, az_deg, distance)
    return _TO_3857.transform(lon, lat)


def _project_custom(intersection_3857, utm_epsg: int, x, y) -> tuple:
    to_utm, to_3857 = _utm_transformers(utm_epsg)
    ref_x_utm, ref_y_utm = to_utm.transform(*intersection_3857)
    return to_3857.transform(ref_x_utm + x, ref_y_utm + y)


def _ground_distance_m(p1_3857, p2_3857) -> float:
    if p1_3857 == p2_3857:
        return 0.0
    lon1, lat1 = _TO_WGS84.transform(*p1_3857)
    lon2, lat2 = _TO_WGS84.transform(*p2_3857)
    _, _, dist = _GEOD.inv(lon1, lat1, lon2, lat2)
    return dist


def _clip_segment_2d(p1, p2, gb: dict) -> Optional[tuple]:
    """2D segment clipping against the axis-aligned grid bounds (Shapely).

    Mirrors spatial.clip_segment_to_grid (QgsClipper.clippedLine).
    Returns (clipped_p1, clipped_p2) or None.
    """
    line = LineString([p1, p2])
    clip_box = box(gb["x_min"], gb["y_min"], gb["x_max"], gb["y_max"])
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


def _grid_bounds_3857(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT x_cells, y_cells, x_resolution, y_resolution, "
        "reference_latitude, reference_longitude FROM grid_3d_definition"
    ).fetchone()
    x_cells, y_cells, x_res, y_res, ref_lat, ref_lon = row
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
    }


# ---------------------------------------------------------------------------
# Database accessors
# ---------------------------------------------------------------------------


def _get_movement(conn, oid: int) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT oid, runway_time, block_time, aircraft, departure_arrival,
               engine_name, profile_id, taxi_route, runway, taxi_fuel_ratio,
               number_of_stop_and_gos
        FROM user_aircraft_movements WHERE oid=?
        """,
        (oid,),
    ).fetchone()
    if not row:
        return None
    return {
        "oid": row[0],
        "runway_time": row[1],
        "block_time": row[2],
        "aircraft": row[3],
        "departure_arrival": row[4],
        "engine_name": row[5],
        "profile_id": row[6],
        "taxi_route": row[7],
        "runway_direction": int("".join(ch for ch in row[8] if ch.isdigit())),
        "taxi_fuel_ratio": row[9] if row[9] is not None else 1.0,
        "number_of_stop_and_gos": row[10] or 0,
    }


def _get_engine_count(conn, icao: str) -> int:
    row = conn.execute(
        "SELECT engine_count FROM default_aircraft WHERE icao=?", (icao,)
    ).fetchone()
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (ValueError, TypeError):
        return 0


def _get_mtow_kg(conn, icao: str) -> Optional[float]:
    row = conn.execute(
        "SELECT mtow FROM default_aircraft WHERE icao=?", (icao,)
    ).fetchone()
    if not row or row[0] is None:
        return None
    try:
        return float(row[0])
    except (ValueError, TypeError):
        return None


def _get_engine_ei(conn, engine_name: str) -> dict:
    result = {}
    for r in conn.execute(
        """
        SELECT mode, fuel_kg_sec, co_ei, hc_ei, nox_ei, sox_ei, pm10_ei
        FROM default_aircraft_engine_ei WHERE engine_full_name LIKE ?
        """,
        (f"%{engine_name}%",),
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


def _get_trajectory(conn, profile_id: str) -> list:
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


# ---------------------------------------------------------------------------
# Per-movement compute
# ---------------------------------------------------------------------------


def _get_meteo_at(conn, runway_time: str, use_isa: bool = True) -> dict:
    """Return ambient conditions for the BFFM2 calculation.

    Two modes:
      - use_isa=True (default): return ISA conditions (288.15 K, 1013.25 hPa,
        RH=0.6).  This matches the plugin's current emission-calc output,
        which was generated with ISA conditions rather than the loaded
        meteo (see the validation notes for plugin behaviour).
      - use_isa=False: look up the meteo row whose DateTime is the closest
        bucket <= runway_time (matches the plugin's intended meteo lookup
        per EmissionCalculation.getAmbientCondition).
    """
    if use_isa:
        return {
            "T_K": 288.15,
            "P_Pa": 101325.0,
            "RH": 0.6,
            "Humidity": 0.00634,
            "speed_of_sound_m_s": 340.29,
        }
    row = conn.execute(
        "SELECT Temperature, SeaLevelPressure, RelativeHumidity, Humidity "
        "FROM tbl_InvMeteo WHERE DateTime <= ? "
        "ORDER BY DateTime DESC LIMIT 1",
        (runway_time,),
    ).fetchone()
    if row is None:
        return _get_meteo_at(conn, runway_time, use_isa=True)
    T_K = float(row[0])
    return {
        "T_K": T_K,
        "P_Pa": float(row[1]),
        "RH": float(row[2]),
        "Humidity": float(row[3]) if row[3] is not None else None,
        "speed_of_sound_m_s": 331.3 + 0.606 * (T_K - 273.15),
    }


def _build_icao_eedb(engine_ei: dict) -> dict:
    """Build the icao_eedb nested dict bffm2.calculate_emission_index expects.

    Format: {"NOx" / "CO" / "HC": {bffm2_mode: {ff_ref_kg_s: ei_g_kg}}}
    The bffm2 module applies installation_corrections internally to the
    ff_ref keys; callers MUST pass the raw EEDB ff values (un-corrected).
    """
    eedb = {p: {} for p in ("NOx", "CO", "HC")}
    pol_map = {"NOx": "nox_ei", "CO": "co_ei", "HC": "hc_ei"}
    for ei_mode, bffm2_mode in BFFM2_MODE_NAMES.items():
        if ei_mode not in engine_ei:
            continue
        ff_ref = engine_ei[ei_mode]["ff"]
        for pol_name, ei_col in pol_map.items():
            eedb[pol_name][bffm2_mode] = {ff_ref: engine_ei[ei_mode][ei_col]}
    return eedb


def _segment_mach(tas_start: float, tas_end: float, T_K: float) -> float:
    """Per-segment Mach number, per MovementEmissionCalculator line 941-944.

    Uses the START point's TAS (consistent with the plugin) and corrects to
    ISA reference via sqrt(288.15 / T).
    """
    sos = 331.3 + 0.606 * (T_K - 273.15)
    if sos <= 0:
        return 0.0
    return (tas_start / sos) * math.sqrt(288.15 / T_K)


def _segment_ei_bffm2(
    pollutant: str,
    ff_amb_kg_s: float,
    icao_eedb: dict,
    meteo: dict,
    mach: float,
) -> float:
    """Per-segment BFFM2 ambient EI for one of NOx / CO / HC."""
    return bffm2_ei(
        pollutant,
        ff_amb_kg_s,
        icao_eedb,
        ambient_conditions={
            "temperature_in_Kelvin": meteo["T_K"],
            "pressure_in_Pa": meteo["P_Pa"],
            "relative_humidity": meteo["RH"],
            "mach_number": mach,
        },
        installation_corrections=BFFM2_INSTALLATION_CORRECTIONS,
    )


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _add_em(em: dict, fuel_kg: float, ei: dict) -> None:
    for p, col in EI_COLS.items():
        em[p] += fuel_kg * ei[col] / 1000.0
    em["pm25"] += fuel_kg * ei["pm10_ei"] / 1000.0
    em["co2"] += fuel_kg * CO2_PER_KG_FUEL


def _intersection_cached(ctx: dict, conn, route_name: str) -> Optional[tuple]:
    cache = ctx.setdefault("intersection_cache", {})
    if route_name not in cache:
        taxi = _get_taxi_route_linestring(conn, route_name)
        cache[route_name] = _runway_taxi_intersection_3857(
            ctx["runway"]["geom_3857"], taxi
        )
    return cache[route_name]


def compute_for_movement(
    conn,
    oid: int,
    ctx: dict,
    method: str = "bymode",
    use_isa_meteo: bool = True,
) -> Optional[dict]:
    """Dispatch on method and aircraft type.

    use_isa_meteo: when True (default), BFFM2 ambient corrections use ISA
        conditions, matching the plugin's actual emission CSV output.  Set
        to False to use the meteo loaded into tbl_InvMeteo (the plugin's
        documented but currently un-applied behaviour).
    """
    mov = _get_movement(conn, oid)
    if mov is None:
        return None
    # Helicopter: FOCA Appendix A is identical for all three fixed-wing
    # methods (FOCA doesn't go through BFFM2).
    if not mov["profile_id"]:
        return _compute_helicopter_for_movement(conn, mov)
    return _compute_fixed_wing(conn, mov, ctx, method, use_isa_meteo)


# Backward-compat alias used by earlier callers / tests.
def compute_bymode_for_movement(conn, oid: int, ctx: dict) -> Optional[dict]:
    return compute_for_movement(conn, oid, ctx, method="bymode")


def _compute_helicopter_for_movement(conn, mov: dict) -> Optional[dict]:
    """FOCA Appendix A half-LTO totals for one helicopter movement.

    Departure half: TO (full time) + GI * GI_DEPARTURE_FRACTION (80%).
    Arrival half:   AP (full time) + GI * GI_ARRIVAL_FRACTION   (20%).
    """
    heli = conn.execute(
        "SELECT mtow_kg, engine_count, engine_name, max_shp_per_engine "
        "FROM default_helicopter WHERE icao=?",
        (mov["aircraft"],),
    ).fetchone()
    if heli is None:
        return None
    mtow_kg, n_eng, engine_name, max_shp = heli
    eng = conn.execute(
        "SELECT engine_type FROM default_helicopter_engines WHERE engine_name=?",
        (engine_name,),
    ).fetchone()
    if eng is None:
        return None
    engine_type = eng[0]
    category = derive_category(engine_type, int(n_eng), float(mtow_kg))
    profile = PROFILES[category]
    is_dep = mov["departure_arrival"] == "D"
    gi_fraction = GI_DEPARTURE_FRACTION if is_dep else GI_ARRIVAL_FRACTION
    gi_em = compute_mode_emissions(category, float(max_shp), profile.gi_power)
    gi = _mode_result(
        "GI",
        profile.gi_power,
        profile.gi_time_min * gi_fraction,
        gi_em,
        int(n_eng),
    )
    if is_dep:
        to_em = compute_mode_emissions(category, float(max_shp), profile.to_power)
        active = _mode_result(
            "TO", profile.to_power, profile.to_time_min, to_em, int(n_eng)
        )
    else:
        ap_em = compute_mode_emissions(category, float(max_shp), profile.ap_power)
        active = _mode_result(
            "AP", profile.ap_power, profile.ap_time_min, ap_em, int(n_eng)
        )
    em = {
        "co": (gi.co_g + active.co_g) / 1000.0,
        "co2": (gi.co2_g + active.co2_g) / 1000.0,
        "hc": (gi.hc_g + active.hc_g) / 1000.0,
        "nox": (gi.nox_g + active.nox_g) / 1000.0,
        "sox": 0.0,
        "pm10": (gi.pm_g + active.pm_g) / 1000.0,
        # FOCA 2015 writes helicopter PM mass only to PM10; PM1/PM2.5
        # are not split out (see open_alaqs/core/interfaces/Emissions.py
        # line 200 and its docstring). The earlier mirror into pm25 was
        # incorrect and made both the standalone and this reference
        # jointly disagree with QGIS plugin output. Fixed 2026-05-18.
        "pm25": 0.0,
    }
    return {
        "oid": mov["oid"],
        "aircraft": mov["aircraft"],
        "departure_arrival": mov["departure_arrival"],
        "profile_id": f"FOCA[{category.value}]",
        "n_engines": int(n_eng),
        "taxi_time_s": 0.0,
        "tx_fuel_kg": 0.0,
        "brake_wear_pm10_kg": 0.0,
        "traj_fuel_by_mode_kg": {
            "GI": gi.fuel_kg,
            active.mode: active.fuel_kg,
        },
        "segments_included": 0,
        "segments_skipped_vertical": 0,
        "segments_skipped_grid": 0,
        "segments_partially_clipped": 0,
        "tx_em_kg": {p: 0.0 for p in POLLUTANTS},
        "total_em_kg": em,
    }


def _compute_fixed_wing(
    conn,
    mov: dict,
    ctx: dict,
    method: str = "bymode",
    use_isa_meteo: bool = True,
) -> Optional[dict]:
    """Compute per-movement emissions for a fixed-wing aircraft.

    Methods supported:
      - bymode        : EI from EEDB table at the segment's mode; pure
                        fuel × EI_table / 1000 (the original implementation
                        validated to 0.00% across CO/CO2/NOx/PM10 for 14/15
                        training movements).
      - bffm2_anchor  : Replace NOx/CO/HC EI with the BFFM2-ambient EI
                        computed at the mode's anchor FF; fuel is still
                        ff_anchor × time × n_eng so CO2 matches bymode.
      - bffm2_traj    : Replace fuel AND NOx/CO/HC EI per segment using
                        either trajectory FF (CUSTOM via fuel_flow_kgm /
                        n_eng) or twin_quadratic_fit on the segment's
                        `power` setting (ANP), with BFFM2 ambient corrections.
                        Mach number computed per segment from start TAS.

    SOx and PM10 always use the EEDB-table EI (no BFFM2 path for them per
    the plugin's BFFM2 implementation in MovementEmissionCalculator.py).
    """
    if method not in ("bymode", "bffm2_anchor", "bffm2_traj"):
        raise ValueError(f"Unknown method: {method!r}")

    engine_ei = _get_engine_ei(conn, mov["engine_name"])
    if "TX" not in engine_ei:
        return None
    n_eng = _get_engine_count(conn, mov["aircraft"])
    if n_eng <= 0:
        return None

    # BFFM2 setup: build the icao_eedb dict once per movement, fetch meteo.
    icao_eedb = _build_icao_eedb(engine_ei) if method != "bymode" else None
    meteo = (
        _get_meteo_at(conn, mov["runway_time"], use_isa=use_isa_meteo)
        if method != "bymode"
        else None
    )
    # Per-movement vertical ceiling. Reads `tbl_InvMeteo.MixingHeight`
    # for the period containing `runway_time`, with `vertical_limit`
    # fallback. Matches the plugin's behaviour and the standalone's
    # `get_mixing_height_at`. Replaces the earlier hardcoded
    # `MAX_HEIGHT_M = 914.4` used in the segment-include check below.
    max_height_m = _mixing_height_at(conn, mov["runway_time"])

    # ---- TX (taxi) ----
    taxi_time_s = abs(
        (_parse_dt(mov["runway_time"]) - _parse_dt(mov["block_time"])).total_seconds()
    )
    tx = engine_ei["TX"]
    # For BFFM2 the plugin's TaxiingEmissionCalculator routes through
    # `Engine.getEmissionIndexByEngineState(power_setting, method=BFFM2)`
    # with `fuel_flow=None`, which applies the SAE AIR-5715 inverse
    # correction `ff_amb = ff_ref * delta / theta^3.8 / exp(0.2 * M^2)`
    # (mach=0 at taxi) before using the FF for the segment fuel mass.
    if method != "bymode":
        theta = meteo["T_K"] / 288.15
        delta = meteo["P_Pa"] / 101325.0
        tx_ff_amb = tx["ff"] * delta / (theta**3.8)  # mach=0 at taxi
    else:
        tx_ff_amb = tx["ff"]
    tx_fuel = taxi_time_s * tx_ff_amb * n_eng * mov["taxi_fuel_ratio"]
    em = {p: 0.0 for p in POLLUTANTS}
    if method == "bymode":
        _add_em(em, tx_fuel, tx)
    else:
        # BFFM2: NOx/CO/HC corrected at the (ambient) idle anchor FF with mach=0
        _bffm2_apply_segment(em, tx_ff_amb, tx_fuel, tx, icao_eedb, meteo, mach=0.0)

    # Brake wear PM10 (arrivals only, MTOW > threshold).  Per the plugin,
    # this is added on the first taxi-in segment, once, regardless of method.
    brake_wear_kg = 0.0
    if mov["departure_arrival"] == "A":
        mtow = _get_mtow_kg(conn, mov["aircraft"])
        if mtow is not None and mtow > BRAKE_WEAR_MTOW_THRESHOLD_KG:
            brake_wear_kg = (
                mtow * BRAKE_WEAR_SLOPE - BRAKE_WEAR_INTERCEPT
            ) / 1000.0  # g → kg
            em["pm10"] += brake_wear_kg
            em["pm25"] += brake_wear_kg
    tx_em = dict(em)

    # ---- Spatial setup ----
    intersection_3857 = _intersection_cached(ctx, conn, mov["taxi_route"])
    if intersection_3857 is None:
        intersection_3857 = ctx["runway"]["pt1_3857"]
    is_dep = mov["departure_arrival"] == "D"
    az_deg = _runway_azimuth_deg(ctx["runway"], mov["runway_direction"], is_dep)

    # ---- Trajectory ----
    traj = _get_trajectory(conn, mov["profile_id"])
    if not traj:
        return None
    is_custom = traj[0][6] == "CUSTOM"
    fuel_by_mode = {"TO": 0.0, "CL": 0.0, "AP": 0.0}
    segs_inc = segs_skip_v = segs_skip_g = segs_part = 0

    def _proj(x, y):
        if is_custom:
            return _project_custom(
                intersection_3857, ctx["grid_bounds"]["utm_epsg"], x, y
            )
        return _project_anp(intersection_3857, az_deg, x, y)

    for i in range(len(traj) - 1):
        # Profile row layout: (point, x_m, y_m, z_m, tas_metres, mode, course)
        # but with the columns we SELECT in _get_trajectory we have positional
        # indices 0..6.  The full DB rows additionally carry power and
        # fuel_flow_kgm which we'd need for bffm2_traj.  Refetch them here
        # if traj method is selected.
        pt1 = traj[i]
        pt2 = traj[i + 1]
        _, x1, y1, z1, tas1, mode1, _ = pt1
        _, x2, y2, z2, tas2, mode2, _ = pt2

        if z1 >= max_height_m - EPS_VERTICAL_M and z2 >= max_height_m - EPS_VERTICAL_M:
            segs_skip_v += 1
            continue
        if mode1 not in engine_ei or tas1 + tas2 <= 0:
            continue

        p1 = _proj(x1, y1)
        p2 = _proj(x2, y2)
        clipped = _clip_segment_2d(p1, p2, ctx["grid_bounds"])
        if clipped is None:
            segs_skip_g += 1
            continue
        if clipped != (p1, p2):
            segs_part += 1
            p1, p2 = clipped

        ground_m = _ground_distance_m(p1, p2)
        if ground_m <= 0.0:
            continue
        seg_time = ground_m / ((tas1 + tas2) / 2.0)
        eng = engine_ei[mode1]

        # Per-segment Mach (BFFM2 only; bymode ignores).  Plugin uses
        # start_point.TAS, not avg, per line 943 of MovementEmissionCalculator.
        mach = _segment_mach(tas1, tas2, meteo["T_K"]) if method != "bymode" else 0.0

        if method in ("bymode", "bffm2_anchor"):
            seg_ff_amb = eng["ff"]
        else:  # bffm2_traj
            seg_ff_amb = _bffm2_traj_ff_amb(
                conn, mov, pt1, eng, engine_ei, meteo, mach, n_eng
            )

        seg_fuel = seg_time * seg_ff_amb * n_eng
        if method == "bymode":
            _add_em(em, seg_fuel, eng)
        else:
            _bffm2_apply_segment(em, seg_ff_amb, seg_fuel, eng, icao_eedb, meteo, mach)
        fuel_by_mode[mode1] = fuel_by_mode.get(mode1, 0.0) + seg_fuel
        segs_inc += 1

    return {
        "oid": mov["oid"],
        "aircraft": mov["aircraft"],
        "departure_arrival": mov["departure_arrival"],
        "profile_id": mov["profile_id"],
        "n_engines": n_eng,
        "method": method,
        "taxi_time_s": taxi_time_s,
        "tx_fuel_kg": tx_fuel,
        "brake_wear_pm10_kg": brake_wear_kg,
        "traj_fuel_by_mode_kg": fuel_by_mode,
        "segments_included": segs_inc,
        "segments_skipped_vertical": segs_skip_v,
        "segments_skipped_grid": segs_skip_g,
        "segments_partially_clipped": segs_part,
        "tx_em_kg": tx_em,
        "total_em_kg": em,
    }


def _bffm2_apply_segment(
    em: dict,
    ff_amb_per_engine_kg_s: float,
    fuel_kg: float,
    eng: dict,
    icao_eedb: dict,
    meteo: dict,
    mach: float,
) -> None:
    """Compute BFFM2-ambient NOx/CO/HC EIs and add segment emissions."""
    em["pm10"] += fuel_kg * eng["pm10_ei"] / 1000.0
    em["pm25"] += fuel_kg * eng["pm10_ei"] / 1000.0
    em["sox"] += fuel_kg * eng["sox_ei"] / 1000.0
    em["co2"] += fuel_kg * CO2_PER_KG_FUEL
    for pol_name, dest_key in (("NOx", "nox"), ("CO", "co"), ("HC", "hc")):
        ei = _segment_ei_bffm2(pol_name, ff_amb_per_engine_kg_s, icao_eedb, meteo, mach)
        em[dest_key] += fuel_kg * ei / 1000.0


def _bffm2_traj_ff_amb(conn, mov, pt, eng, engine_ei, meteo, mach, n_eng) -> float:
    """Determine per-engine ambient FF for the bffm2_traj method.

    Mirrors MovementEmissionCalculator.py line 1082-1124:
      - If fuel_flow_kgm is supplied (ADS-B / CUSTOM): use fuel_flow_kgm / n_eng,
        with a TO-anchor ceiling fallback (anchor FF) if exceeded.
      - Otherwise (ANP): use twin_quadratic_fit on the segment's `power`
        setting to get the EEDB reference FF, then convert to ambient FF
        via the SAE AIR-5715 / CAEP14 inverse correction:
            ff_amb = ff_ref * delta / theta^3.8 / exp(0.2 * M^2).

    Power column comes from the profile row's `power` field; fuel_flow_kgm
    from the `fuel_flow_kgm` field.  Both need to be re-read because
    _get_trajectory currently SELECTs only 7 columns.
    """
    # Re-read the relevant profile-row fields for this point.
    point_idx = pt[0]
    row = conn.execute(
        "SELECT power, fuel_flow_kgm FROM default_aircraft_profiles "
        "WHERE profile_id=? AND point=?",
        (mov["profile_id"], point_idx),
    ).fetchone()
    power = row[0] if row else None
    ff_kgm = row[1] if row else None

    # ADS-B / CUSTOM path: fuel_flow_kgm is already an ambient (in-flight) FF
    # for ALL engines combined.
    ff_to_ceiling = engine_ei["TO"]["ff"]
    if ff_kgm not in (None, 0):
        ff_per_engine = ff_kgm / n_eng
        if ff_per_engine > ff_to_ceiling:
            return eng["ff"]  # ceiling fallback to mode anchor
        return ff_per_engine

    # ANP path: twin_quadratic_fit-style log-log interpolation on power.
    # The 4 anchors are (power_pct, ff_kg_s).  Plugin uses these power %s:
    #   Idle 7%, Approach 30%, Climbout 85%, Takeoff 100%.
    if power is None:
        return eng["ff"]  # fall back to mode anchor if power missing
    ff_ref = _twin_quadratic_ff_from_power(power, engine_ei)
    # Inverse ambient correction (SAE AIR-5715 / CAEP14).
    theta = meteo["T_K"] / 288.15
    delta = meteo["P_Pa"] / 101325.0
    ff_amb = ff_ref * delta / (theta**3.8) / math.exp(0.2 * mach**2)
    return ff_amb


def _twin_quadratic_ff_from_power(power: float, engine_ei: dict) -> float:
    """Replicate the plugin's twin_quadratic_fit_method exactly.

    The plugin uses a piecewise 3-point quadratic (NOT a 4-point least-squares
    fit through all anchors):
      - power < 0.85: parabola through (0.07, 0.30, 0.85)
      - power >= 0.85: parabola through (0.30, 0.85, 1.0)
    Values are normalized by the 100% (Takeoff) FF, then de-normalized.
    For power < 0.07 the result is clamped to the Idle FF.

    See open_alaqs/core/tools/twin_quadratic_fit_method.py for the original.
    """
    # icao_eedb in plugin form: {power_pct: ff_kg_s}
    ff_by_p = {}
    for mode_label, power_pct in (
        ("TX", 0.07),
        ("AP", 0.30),
        ("CL", 0.85),
        ("TO", 1.00),
    ):
        if mode_label in engine_ei:
            ff_by_p[power_pct] = engine_ei[mode_label]["ff"]
    if any(k not in ff_by_p for k in (0.07, 0.30, 0.85, 1.00)):
        return engine_ei.get("AP", engine_ei.get("TX", {"ff": 0.0}))["ff"]

    if power <= 0.85:
        x1, x2, x3 = 0.07, 0.30, 0.85
    else:
        x1, x2, x3 = 0.30, 0.85, 1.00

    max_rated_t = ff_by_p[1.0]
    y1 = ff_by_p[x1] / max_rated_t
    y2 = ff_by_p[x2] / max_rated_t
    y3 = ff_by_p[x3] / max_rated_t

    # Solve y = a x^2 + b x + c through three points.
    a = (y3 - y1) / ((x3 - x1) * (x1 - x2)) - (y3 - y2) / ((x3 - x2) * (x1 - x2))
    b = (y3 - y1) / (x3 - x1) - a * (x3 + x1)
    c = y3 - a * x3**2 - b * x3
    y = a * power**2 + b * power + c

    ff = y * max_rated_t
    if power < 0.07:
        ff = max(ff, ff_by_p[0.07])  # clamp at idle
    return max(0.0, ff)


# ---------------------------------------------------------------------------
# Plugin CSV comparison helper
# ---------------------------------------------------------------------------


def _load_plugin_totals(csv_path: str) -> dict:
    import csv as _csv
    import re

    totals: dict = {}
    with open(csv_path) as f:
        for row in _csv.DictReader(f):
            m = re.match(r"id\s+(\d+):", row.get("source_name", ""))
            if not m:
                continue
            oid = int(m.group(1))
            t = totals.setdefault(oid, {p: 0.0 for p in POLLUTANTS})
            for p in POLLUTANTS:
                v = row.get(f"{p}_kg")
                if v not in (None, ""):
                    try:
                        t[p] += float(v)
                    except ValueError:
                        pass
    return totals


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("alaqs_path", help="Path to the _out.alaqs database")
    parser.add_argument(
        "--method",
        default="bymode",
        choices=("bymode", "bffm2_anchor", "bffm2_traj"),
    )
    parser.add_argument(
        "--use-meteo",
        action="store_true",
        help="Use the actual meteo from tbl_InvMeteo for BFFM2 ambient "
        "corrections.  Default is ISA conditions, matching the plugin's "
        "current emission-CSV output behaviour.",
    )
    parser.add_argument("--oid", type=int, default=None)
    parser.add_argument("--plugin-csv", default=None)
    parser.add_argument("--verbose-diag", action="store_true")
    args = parser.parse_args(argv)

    if not Path(args.alaqs_path).is_file():
        print(f"Alaqs file not found: {args.alaqs_path}", file=sys.stderr)
        return 2

    conn = _connect(args.alaqs_path)
    try:
        ctx = {
            "runway": _get_runway(conn),
            "grid_bounds": _grid_bounds_3857(conn),
        }
        if args.verbose_diag:
            print(f"Runway: {ctx['runway']['runway_id']}")
            print(f"Grid bounds (EPSG:3857): {ctx['grid_bounds']}\n")

        if args.oid is None:
            oids = [
                r[0]
                for r in conn.execute(
                    "SELECT oid FROM user_aircraft_movements ORDER BY oid"
                )
            ]
        else:
            oids = [args.oid]

        plugin_totals = _load_plugin_totals(args.plugin_csv) if args.plugin_csv else {}
        if plugin_totals:
            print(
                f"{'oid':>3} {'CO_ref':>8} {'CO_plg':>8} {'Δ%':>6}  "
                f"{'CO2_ref':>9} {'CO2_plg':>9} {'Δ%':>6}  "
                f"{'NOx_ref':>8} {'NOx_plg':>8} {'Δ%':>6}  "
                f"{'PM10_ref':>9} {'PM10_plg':>9} {'Δ%':>6}"
            )
            print("-" * 130)

        for oid in oids:
            result = compute_for_movement(
                conn,
                oid,
                ctx,
                method=args.method,
                use_isa_meteo=not args.use_meteo,
            )
            if result is None:
                print(f"{oid:>3}  (skipped: no profile or helicopter)")
                continue
            if args.verbose_diag:
                fuel_by_mode = result["traj_fuel_by_mode_kg"]
                fuel_str = " ".join(
                    f"{m}={fuel_by_mode.get(m, 0.0):.2f}" for m in sorted(fuel_by_mode)
                )
                print(
                    f"oid={oid} aircraft={result['aircraft']} "
                    f"DA={result['departure_arrival']} "
                    f"profile={result['profile_id']} "
                    f"n_eng={result['n_engines']}\n"
                    f"  taxi_time={result['taxi_time_s']:.0f}s "
                    f"tx_fuel={result['tx_fuel_kg']:.2f}kg "
                    f"brake_pm10={result['brake_wear_pm10_kg']:.6f}kg\n"
                    f"  traj fuel kg: {fuel_str}\n"
                    f"  segments: inc={result['segments_included']} "
                    f"vskip={result['segments_skipped_vertical']} "
                    f"gskip={result['segments_skipped_grid']} "
                    f"part={result['segments_partially_clipped']}\n"
                )
            ref = result["total_em_kg"]
            if plugin_totals:
                plg = plugin_totals.get(oid, {p: 0.0 for p in POLLUTANTS})

                def _d(p):
                    return (
                        100.0 * (plg[p] - ref[p]) / ref[p]
                        if ref[p] != 0
                        else float("nan")
                    )

                print(
                    f"{oid:>3} {ref['co']:>8.4f} {plg['co']:>8.4f} {_d('co'):+6.2f}  "
                    f"{ref['co2']:>9.3f} {plg['co2']:>9.3f} {_d('co2'):+6.2f}  "
                    f"{ref['nox']:>8.4f} {plg['nox']:>8.4f} {_d('nox'):+6.2f}  "
                    f"{ref['pm10']:>9.5f} {plg['pm10']:>9.5f} {_d('pm10'):+6.2f}"
                )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
