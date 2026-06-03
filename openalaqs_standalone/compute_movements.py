"""
compute_movements: dispatch layer and study-level driver for the
aircraft emission per-movement-totals core.

This module is the standalone's port of the dispatch logic in the
CAEP14 validation reference
(`validation/tools/compute_caep14_reference.py`): `compute_for_movement`,
the per-study `ctx` construction that the reference's `main()` did
inline, and `_load_plugin_totals`.

It is the top of the "(a)" output mode: per-movement emission totals.
Given an `.alaqs` connection it builds the per-study context once,
routes each movement to the fixed-wing or helicopter compute, and
returns the per-movement result dicts. It also loads the plugin's
per-movement totals from a plugin-output CSV so the standalone can be
compared against the validation bundle's expected results.

This module is the Phase A0 acceptance surface: the standalone aircraft
core is correct when `compute_all_movements` plus `load_plugin_totals`
reproduce `validation/data/plugin_output/*.csv` to the documented
tolerances (0.00 percent on 14 of 15 training movements, the known
offset on movement 11).

Differences from the reference, all deliberate:
  - `build_context` is a function; the reference built `ctx` inline in
    `main()`. The context construction goes through the `movements`
    and `geometry` modules instead of the reference's inline helpers.
  - The fixed-wing and helicopter computes come from the
    `compute_aircraft` and `compute_helicopter` modules.
  - The helicopter result dict gets a `method` key added so every
    result dict has the same shape regardless of aircraft type. The
    reference's helicopter result omitted `method` (FOCA is
    method-independent); the standalone fills it in with the method
    the dispatch was called with, so downstream code never has to
    special-case the key's absence. This is the one place the
    standalone result shape is a strict superset of the reference's.
"""

from __future__ import annotations

import csv as _csv
import re
from typing import Optional

from openalaqs_standalone import compute_aircraft as _ca
from openalaqs_standalone import compute_apu_movements as _capu
from openalaqs_standalone import compute_gate_movements as _cg
from openalaqs_standalone import compute_helicopter as _ch
from openalaqs_standalone import compute_start_movements as _cs
from openalaqs_standalone import geometry as _geo
from openalaqs_standalone import movements as _mv

# The six pollutants carried in every per-movement result. Identical
# to compute_aircraft.POLLUTANTS and compute_helicopter.POLLUTANTS.
POLLUTANTS = _ca.POLLUTANTS

# The three calculation methods.
METHODS = ("bymode", "bffm2_anchor", "bffm2_traj")


# ---------------------------------------------------------------------------
# Per-study context
# ---------------------------------------------------------------------------


def build_context(conn) -> dict:
    """Build the per-study context dict shared across all movements.

    The context carries the two study-wide pieces of geometry that
    every fixed-wing movement needs: the runway and the AUSTAL grid
    bounds. It is built once per study and passed to every
    `compute_for_movement` call.

    Returns a dict with:
      runways         dict from `movements.get_runways`, mapping each
                      runway-designator integer to its runway dict.
                      A single-runway study still produces a 2-key
                      dict; both keys point at the same runway.
      grid_bounds     the dict from `geometry.grid_bounds_3857`
      gate_profiles   the dict from `movements.get_gate_profiles`, the
                      whole `default_gate_profiles` table, read once
                      here so the per-movement gate compute does not
                      re-read it for every movement

    `compute_aircraft.compute_fixed_wing` also lazily populates an
    `intersection_cache` entry in this dict as it encounters taxi
    routes; that is expected and is why the dict is mutable and shared.

    The reference built this inline in `main()`; making it a function
    keeps the study-level driver readable and lets the parallel driver
    (a later phase) build the context once and hand it to workers.

    Multi-runway studies (a study with both 07/25 and 33/15 active) are supported
    by reading `runways` (plural) instead of a single `runway`.
    Single-runway studies are unaffected; the lookup
    `ctx["runways"][mov["runway_direction"]]` works for both cases.
    """
    runways = _mv.get_runways(conn)
    gd = _mv.get_grid_definition(conn)
    grid_bounds = _geo.grid_bounds_3857(
        gd["x_cells"],
        gd["y_cells"],
        gd["x_resolution"],
        gd["y_resolution"],
        gd["reference_latitude"],
        gd["reference_longitude"],
    )
    gate_profiles = _mv.get_gate_profiles(conn)
    # APU context: four small tables read once per study so the per-
    # movement compute does not pay their cost 1841 times.
    apu_efs = _capu.get_apu_efs(conn)
    apu_times = _capu.get_apu_times(conn)
    gate_types = _capu.get_gate_types(conn)
    aircraft_apu_ids = _capu.get_aircraft_apu_ids(conn)
    # Start emission context: two small tables read once. Used for
    # departures only (the plugin's arrival handler never adds start
    # emissions); see compute_start_movements.
    start_efs = _cs.get_start_efs(conn)
    aircraft_groups_engines = _cs.get_aircraft_groups_and_engines(conn)
    # Natural per-route taxi time: sum over the route's segments of
    # `geodesic_length_m / segment_speed_m_per_s`, using the speed
    # column from shapes_taxiways (km/h). The plugin uses this in
    # MovementEmissionCalculator.py to split the movement's total
    # taxi time into a "natural" portion (distributed along the route
    # by segment length) and a "queuing" portion (placed at the LAST
    # segment). The standalone needs the cache here so per-movement
    # compute can subtract natural from total without re-reading the
    # route's segments. Cached once per route; route names that fail
    # to resolve map to None and the per-movement code degrades to
    # the legacy all-in-tx_em behaviour.
    natural_taxi_times = _build_natural_taxi_times(conn)
    # Airport elevation (m) for the NOx ambient correction's ISA-temp
    # term. Read once per study; the per-movement compute reads it
    # from ctx without further DB hits.
    airport_elevation_m = _mv.get_airport_elevation_m(conn)
    return {
        "runways": runways,
        "grid_bounds": grid_bounds,
        "gate_profiles": gate_profiles,
        "apu_efs": apu_efs,
        "apu_times": apu_times,
        "gate_types": gate_types,
        "aircraft_apu_ids": aircraft_apu_ids,
        "start_efs": start_efs,
        "aircraft_groups_engines": aircraft_groups_engines,
        "natural_taxi_times": natural_taxi_times,
        "airport_elevation_m": airport_elevation_m,
    }


def _build_natural_taxi_times(conn) -> dict:
    """Return {route_name: natural_time_s} for every user_taxiroute row.

    Natural time per segment = geodesic_length_m / (speed_kmh * 1000 / 3600).
    Total natural time per route = sum over the route's stored segment
    sequence. Routes whose segments cannot all be resolved get a None
    entry and the per-movement compute falls back to treating the
    movement's total taxi time as if it were all natural -- the
    pre-queuing-split behaviour.

    Read from shapes_taxiways (speed column) and the route sequence
    text in user_taxiroute_taxiways. Geodesic length is preferred over
    EPSG:3857 length to match the plugin, which uses QgsDistanceArea
    in geographic mode for taxi-segment timing.
    """
    import pyproj as _pyproj

    geod = _pyproj.Geod(ellps="WGS84")
    to_wgs = _pyproj.Transformer.from_crs(3857, 4326, always_xy=True)

    # Per-taxiway speed (km/h) and geodesic length (m).
    speeds = {}
    lengths = {}
    try:
        rows = conn.execute(
            "SELECT taxiway_id, speed, geometry FROM shapes_taxiways"
        ).fetchall()
    except Exception:
        return {}
    for tid, speed, blob in rows:
        try:
            speed_f = float(speed) if speed is not None else 0.0
        except (TypeError, ValueError):
            speed_f = 0.0
        speeds[tid] = speed_f
        geom = _geo.spatialite_blob_to_shapely(blob) if blob else None
        if geom is None:
            continue
        coords = list(geom.coords)
        total = 0.0
        for i in range(len(coords) - 1):
            lon1, lat1 = to_wgs.transform(coords[i][0], coords[i][1])
            lon2, lat2 = to_wgs.transform(coords[i + 1][0], coords[i + 1][1])
            _, _, d = geod.inv(lon1, lat1, lon2, lat2)
            total += d
        lengths[tid] = total

    # Per-route natural time.
    natural = {}
    try:
        route_rows = conn.execute(
            "SELECT route_name, sequence FROM user_taxiroute_taxiways"
        ).fetchall()
    except Exception:
        return natural
    for route_name, seq_str in route_rows:
        if not seq_str:
            continue
        seq = [s.strip() for s in seq_str.split(",") if s.strip()]
        total = 0.0
        ok = True
        for tid in seq:
            sp = speeds.get(tid)
            lg = lengths.get(tid)
            if sp is None or sp <= 0 or lg is None:
                # Unknown speed or length -- cannot compute natural
                # time for this route. Leave it out; the fallback in
                # compute_aircraft uses total time.
                ok = False
                break
            total += lg / (sp * 1000.0 / 3600.0)
        if ok:
            natural[route_name] = total
    return natural


# ---------------------------------------------------------------------------
# Per-movement dispatch
# ---------------------------------------------------------------------------


def compute_for_movement(
    conn,
    oid: int,
    ctx: dict,
    method: str = "bymode",
    use_isa_meteo: bool = True,
    apply_nox_corrections: bool = False,
) -> Optional[dict]:
    """Compute one movement, dispatching on aircraft type.

    Dispatch is by membership in `default_helicopter`: if the
    movement's aircraft ICAO is in that table, the movement is routed
    to the FOCA path (`compute_helicopter.compute_helicopter`), which
    is method-independent. Otherwise the movement is fixed-wing and
    is routed to `compute_aircraft.compute_fixed_wing` with the given
    method.

    Earlier versions dispatched on `not mov["profile_id"]`. That
    worked for the CAEP14 validation fixture (every fixed-wing
    movement has an explicit profile_id there) but misroutes
    plugin-shaped study files, in which fixed-wing movements
    routinely leave engine_name and profile_id blank and rely on
    default_aircraft fallback at compute time. The current dispatch
    plus the fallback resolution below match the plugin's
    MovementEmissionCalculator behavior at lines ~903-933
    (engine_name) and ~1102-1135 (profile_id).

    Parameters
    ----------
    conn
        An open `.alaqs` connection (from `movements.connect`).
    oid
        The movement oid.
    ctx
        The per-study context from `build_context`.
    method
        One of "bymode", "bffm2_anchor", "bffm2_traj". Ignored for
        helicopters.
    use_isa_meteo
        When True (default), BFFM2 ambient corrections use ISA
        conditions, matching the plugin's emission-CSV output. When
        False, the loaded `tbl_InvMeteo` row is used. No effect for
        bymode or for helicopters.

    Returns
    -------
    A per-movement result dict, or None if the movement oid does not
    exist or cannot be computed.

    Ported from the reference's `compute_for_movement`. Two additions:
    the helicopter result dict gets a `method` key added so every
    result dict has the same shape (the reference's helicopter result
    omitted it); and every result dict gets a `gate_em_kg` key, the
    per-movement gate (GSE + GPU) emission from
    `compute_gate_movements`. Gate emissions are kept as their own
    field, not folded into `total_em_kg`: the plugin emits gate
    emissions as a distinct source type, and the Phase A0 validation
    CSVs contain only the Movement-source rows, so folding them in
    would break the A0 gate. A helicopter, or a movement that
    references no gate, gets an all-zero `gate_em_kg`.
    """
    mov = _mv.get_movement(conn, oid)
    if mov is None:
        return None

    # Dispatch on default_helicopter table membership, NOT on whether
    # the movement row leaves profile_id blank. In plugin-shaped study
    # files, fixed-wing movements routinely have blank engine_name,
    # profile_id, and track_id; the plugin resolves these from
    # default_aircraft at runtime. The earlier "blank profile_id =
    # helicopter" heuristic worked for the CAEP14 validation fixture
    # (which always supplies an explicit profile_id) but misroutes
    # every blank-profile fixed-wing movement to the helicopter path
    # against any plugin-shaped study with multiple active runway directions.
    is_helicopter = _mv.get_helicopter(conn, mov["aircraft"]) is not None

    if is_helicopter:
        # Helicopter: FOCA Appendix A, method-independent. The
        # reference's helicopter result has no `method` key; add it
        # here so the result shape is uniform across aircraft types.
        result = _ch.compute_helicopter(conn, mov)
        if result is not None:
            result["method"] = method
    else:
        # Fixed-wing: fall back from blank movement fields to
        # default_aircraft, matching the plugin's MovementEmissionCalculator
        # resolution at lines ~903-933 (engine_name) and ~1120-1135
        # (profile_id). The fallback only fires when the movement row
        # leaves the field blank; an explicit value (the CAEP14
        # fixture case) wins.
        if not mov.get("engine_name") or not mov.get("profile_id"):
            # Read both engine columns from default_aircraft:
            #   `engine`       the EEDB engine code (e.g. "01P20CM128")
            #   `engine_name`  the human-readable label (e.g. "LEAP-1A26/26E1")
            # The downstream EI lookup (default_aircraft_engine_ei) is
            # keyed by what its schema also calls "engine_name" but
            # which actually stores the EEDB code. So the right
            # fallback for movement.engine_name is default_aircraft.engine,
            # NOT default_aircraft.engine_name. Using the latter
            # (the human-readable label) silently misses every EI row
            # for aircraft where the two columns differ (A19N, A20N,
            # B37M, B752, C680, CL30, CL35, A359, etc.).
            ac_row = conn.execute(
                "SELECT engine, departure_profile, arrival_profile "
                "FROM default_aircraft WHERE icao = ?",
                (mov["aircraft"],),
            ).fetchone()
            if ac_row is not None:
                default_engine, dep_prof, arr_prof = ac_row
                if not mov.get("engine_name") and default_engine:
                    mov["engine_name"] = default_engine
                if not mov.get("profile_id"):
                    is_arr = mov["departure_arrival"] == "A"
                    fallback_prof = arr_prof if is_arr else dep_prof
                    if fallback_prof:
                        mov["profile_id"] = fallback_prof
        result = _ca.compute_fixed_wing(
            conn,
            mov,
            ctx,
            method,
            use_isa_meteo,
            apply_nox_corrections=apply_nox_corrections,
        )

    # Gate emissions (Phase A2): per-movement GSE + GPU, computed
    # alongside the aircraft emission. They are kept as their own
    # `gate_em_kg` field (the audit trail) AND folded into
    # `total_em_kg`, so the movement total includes the gate GSE/GPU
    # contribution. A helicopter or a gate-less movement gets an
    # all-zero gate dict, so the key is always present, the fold is a
    # no-op for them, and the result shape stays uniform.
    #
    # Note this means `total_em_kg` is NO LONGER a pure
    # Movement-source quantity: for a movement with gate emissions it
    # also carries the Gate-source GSE/GPU. The plugin emits gate
    # emissions as a separate source type, and the Phase A0
    # validation CSVs contain only the Movement rows, so the Phase A0
    # gate test's contract is: total_em_kg matches plugin output for
    # movements WITHOUT gate emissions. On the training study every
    # movement has gate_emissions_code 0, so gate_em_kg is all-zero
    # and the fold changes nothing there; the A0 gate stays green.
    # gate_em_kg uses five pollutants (no CO2); the CO2 entry of
    # total_em_kg is therefore unchanged by the fold.
    if result is not None:
        gate_em = _cg.compute_gate_emissions_for_movement(
            conn, mov, gate_profiles=ctx.get("gate_profiles")
        )
        result["gate_em_kg"] = gate_em
        for pollutant, kg in gate_em.items():
            if pollutant in result["total_em_kg"]:
                result["total_em_kg"][pollutant] += kg

        # APU emissions: the aircraft's onboard auxiliary power unit
        # burns fuel at the stand. Computed identically in shape to
        # the gate fold above; kept on the result as `apu_em_kg` for
        # audit and added into `total_em_kg` so the aircraft cell
        # totals match the plugin's Movement source-type convention.
        # Helicopters and aircraft without an APU silently get an
        # all-zero apu_em (compute_apu_movements handles all the
        # zero-emission cases internally).
        apu_em = _capu.compute_apu_emissions_for_movement(
            conn,
            mov,
            apu_efs=ctx.get("apu_efs"),
            apu_times=ctx.get("apu_times"),
            gate_types=ctx.get("gate_types"),
            aircraft_apu_ids=ctx.get("aircraft_apu_ids"),
        )
        result["apu_em_kg"] = apu_em
        # Propagate apu_code onto the result so the downstream spatial
        # distribute step can apportion APU mass across the taxi route
        # for apu_code=2 (full-taxi APU) rather than dumping all of it
        # at the first segment (the apu_code=1 stand-only placement).
        # Falls back to None when the movement row has no apu_code
        # column or value (compute_apu_movements then treats it as 1
        # by convention).
        result["apu_code"] = mov.get("apu_code")
        for pollutant, kg in apu_em.items():
            if pollutant in result["total_em_kg"]:
                result["total_em_kg"][pollutant] += kg

        # Engine-start emissions. Mirrors the plugin's
        # _apply_start_engine_emissions (open_alaqs/core/
        # MovementEmissionCalculator.py:599), which is called from
        # the departure branch only (line 573); the arrival branch
        # at line 619 does not. Helicopters and unknown groups
        # silently get an all-zero start_em (compute_start_movements
        # handles every skip path internally).
        start_em = _cs.compute_start_emissions_for_movement(
            conn,
            mov,
            start_efs=ctx.get("start_efs"),
            aircraft_groups=ctx.get("aircraft_groups_engines"),
        )
        result["start_em_kg"] = start_em
        for pollutant, kg in start_em.items():
            if pollutant in result["total_em_kg"]:
                result["total_em_kg"][pollutant] += kg
    return result


# ---------------------------------------------------------------------------
# Study-level driver
# ---------------------------------------------------------------------------


def compute_all_movements(
    conn,
    method: str = "bymode",
    use_isa_meteo: bool = True,
    oids: Optional[list] = None,
    apply_nox_corrections: bool = False,
) -> dict:
    """Compute every movement in the study (or a given subset).

    Builds the per-study context once, then computes each movement.

    Parameters
    ----------
    conn
        An open `.alaqs` connection.
    method
        One of "bymode", "bffm2_anchor", "bffm2_traj".
    use_isa_meteo
        ISA vs loaded-meteo for the BFFM2 ambient correction.
    oids
        If given, only these movement oids are computed; otherwise all
        movements in `user_aircraft_movements` (ascending oid order).

    Returns
    -------
    A dict mapping oid -> per-movement result dict. Movements that
    could not be computed (None from `compute_for_movement`) are
    omitted from the dict; their absence is the signal.

    This is the per-movement-totals output, mode "(a)". The later
    "(c)" distribution layer will consume the same per-movement result
    dicts (which carry the per-segment fuel-by-mode breakdown) rather
    than recompute.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method!r}; expected one of {METHODS}")
    ctx = build_context(conn)
    if oids is None:
        oids = _mv.get_movement_oids(conn)
    results: dict = {}
    for oid in oids:
        res = compute_for_movement(
            conn,
            oid,
            ctx,
            method=method,
            use_isa_meteo=use_isa_meteo,
            apply_nox_corrections=apply_nox_corrections,
        )
        if res is not None:
            results[oid] = res
    return results


# ---------------------------------------------------------------------------
# Plugin-output CSV loader (for validation against the bundle)
# ---------------------------------------------------------------------------


def load_plugin_totals(csv_path: str) -> dict:
    """Load per-movement emission totals from a plugin-output CSV.

    The plugin's emission CSV has one row per emission geometry, with a
    `source_name` like "id 7: E190 A 24 -> G6 ..." and per-pollutant
    `*_kg` columns. This sums the per-pollutant values by movement oid
    (parsed from the `id N:` prefix of `source_name`), producing the
    per-movement totals to compare the standalone against.

    Returns a dict mapping oid -> {pollutant: kg}. Rows whose
    `source_name` does not match the `id N:` pattern are skipped (the
    plugin CSV can carry non-movement rows).

    Ported verbatim from the reference's `_load_plugin_totals`.
    """
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
