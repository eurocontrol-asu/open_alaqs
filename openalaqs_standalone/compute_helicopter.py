"""
compute_helicopter: helicopter emission core (FOCA 2015 Appendix A).

This module is the standalone's port of the helicopter emission path
in the CAEP14 validation reference
(`validation/tools/compute_caep14_reference.py`):
`_compute_helicopter_for_movement`.

Helicopters do not go through BFFM2 and do not have a fixed-wing
trajectory profile. They are detected upstream by the absence of a
`profile_id` on the movement. Their emissions follow the FOCA 2015
Appendix A half-LTO model:

  Departure half:  TO at full mode time, plus ground-idle (GI) at
                   GI_DEPARTURE_FRACTION (80 percent) of the GI time.
  Arrival half:    AP at full mode time, plus ground-idle (GI) at
                   GI_ARRIVAL_FRACTION (20 percent) of the GI time.

The actual FOCA formulas (piston vs turboshaft fuel flow, emission
indices, category derivation, the operational-profile power and time
tables) live in the shared core modules
`open_alaqs.core.tools.foca_heli` and
`open_alaqs.core.tools.foca_heli_utils`. Those are byte-identical to
the modules the plugin ships; this module only orchestrates them, the
same way the reference does.

The result dict has the same shape as `compute_aircraft`'s fixed-wing
result, so the dispatch layer can treat the two interchangeably. The
fields that only make sense for fixed-wing aircraft (taxi time, taxi
fuel, brake wear, the segment counters) are present and zeroed, again
matching the reference.

Differences from the reference, both deliberate:
  - The two database reads (`default_helicopter`,
    `default_helicopter_engines`) go through the `movements` accessors
    `get_helicopter` and `get_helicopter_engine_type` instead of
    inline SQL.
  - The FOCA names are imported from the shared
    `open_alaqs.core.tools.*` path, the same path the plugin uses.
"""

from __future__ import annotations

from typing import Optional

from open_alaqs.core.tools.foca_heli import (
    GI_ARRIVAL_FRACTION,
    GI_DEPARTURE_FRACTION,
    PROFILES,
    derive_category,
)
from open_alaqs.core.tools.foca_heli_utils import (
    _mode_result,
    compute_mode_emissions,
)
from openalaqs_standalone import movements as mv

# The six pollutants the per-movement totals carry. Kept as a module
# constant here (rather than imported from compute_aircraft) so this
# module does not depend on the fixed-wing module; the dispatch layer
# is what ties them together. The tuple is identical to
# compute_aircraft.POLLUTANTS by construction.
POLLUTANTS = ("co", "co2", "hc", "nox", "sox", "pm10", "pm25")


def compute_helicopter(conn, mov: dict, ctx: Optional[dict] = None) -> Optional[dict]:
    """Compute FOCA Appendix A half-LTO totals for one helicopter movement.

    Parameters
    ----------
    conn
        An open `.alaqs` connection (from `movements.connect`).
    mov
        The movement dict from `movements.get_movement`. A helicopter
        movement is one with no `profile_id`; the dispatch layer is
        responsible for routing such movements here.
    ctx
        The per-study context from `compute_movements.build_context`
        (runways, grid bounds). When given, the active mode (TO or AP) is
        limited to the part of the FOCA flight path below the movement's
        mixing height and inside the grid, as the plugin does
        (`FlightEmissionCalculator._helicopter_active_retained`). When None,
        nothing is cut (the reference's behaviour).

    Returns
    -------
    A per-movement result dict with the same shape as
    `compute_aircraft.compute_fixed_wing`'s result, or None if the
    aircraft is not a known helicopter or its engine is not in
    `default_helicopter_engines`.

    Ported from the reference's `_compute_helicopter_for_movement`. The
    two DB reads are routed through the `movements` accessors; the FOCA
    math is unchanged (it lives in the shared core modules).
    """
    heli = mv.get_helicopter(conn, mov["aircraft"])
    if heli is None:
        return None
    engine_type = mv.get_helicopter_engine_type(conn, heli["engine_name"])
    if engine_type is None:
        return None

    n_eng = int(heli["engine_count"])
    mtow_kg = float(heli["mtow_kg"])
    max_shp = float(heli["max_shp_per_engine"])

    category = derive_category(engine_type, n_eng, mtow_kg)
    profile = PROFILES[category]
    is_dep = mov["departure_arrival"] == "D"

    # Ground-idle: present in both halves, but only a fraction of the
    # GI mode time is attributed to each half (80 percent to the
    # departure half, 20 percent to the arrival half).
    gi_fraction = GI_DEPARTURE_FRACTION if is_dep else GI_ARRIVAL_FRACTION
    gi_em = compute_mode_emissions(category, max_shp, profile.gi_power)
    gi = _mode_result(
        "GI",
        profile.gi_power,
        profile.gi_time_min * gi_fraction,
        gi_em,
        n_eng,
    )

    # Active mode: TO for the departure half, AP for the arrival half,
    # each at its full mode time.
    if is_dep:
        active_em = compute_mode_emissions(category, max_shp, profile.to_power)
        active = _mode_result(
            "TO", profile.to_power, profile.to_time_min, active_em, n_eng
        )
    else:
        active_em = compute_mode_emissions(category, max_shp, profile.ap_power)
        active = _mode_result(
            "AP", profile.ap_power, profile.ap_time_min, active_em, n_eng
        )

    # Vertical limit and grid (plugin parity): scale the active mode by the
    # share of its time spent below the mixing height and inside the grid.
    a = 1.0
    if ctx is not None:
        a = _active_retained_fraction(conn, mov, ctx, category, is_dep)

    # Half-LTO totals: GI plus the active mode, converted g -> kg.
    # SOx is not modelled by FOCA; it is zero, matching the reference.
    em = {
        "co": (gi.co_g + a * active.co_g) / 1000.0,
        "co2": (gi.co2_g + a * active.co2_g) / 1000.0,
        "hc": (gi.hc_g + a * active.hc_g) / 1000.0,
        "nox": (gi.nox_g + a * active.nox_g) / 1000.0,
        "sox": 0.0,
        "pm10": (gi.pm_g + a * active.pm_g) / 1000.0,
        # Helicopter PM is written to PM10 only, matching the plugin's
        # FOCA 2015 behaviour (interfaces/Emissions.py writes the FOCA
        # pm_g value to PollutantType.PM10 and explicitly does not split
        # into PM1/PM2.5). The earlier mirror into pm25 was incorrect
        # for helicopters (verified against QGIS validation CSV which
        # reports p2_kg=0 for AS50 movements while pm10_kg matches).
        "pm25": 0.0,
    }

    return {
        "oid": mov["oid"],
        "aircraft": mov["aircraft"],
        "departure_arrival": mov["departure_arrival"],
        "profile_id": f"FOCA[{category.value}]",
        "n_engines": n_eng,
        "taxi_time_s": 0.0,
        "tx_fuel_kg": 0.0,
        "brake_wear_pm10_kg": 0.0,
        "traj_fuel_by_mode_kg": {
            "GI": gi.fuel_kg,
            active.mode: a * active.fuel_kg,
        },
        "segments_included": 0,
        "segments_skipped_vertical": 0,
        "segments_skipped_grid": 0,
        "segments_partially_clipped": 0,
        # Helicopters have no fixed-wing trajectory segments (FOCA is a
        # half-LTO mode model, not a per-segment integration), so the
        # per-segment record list is empty. The key is present so the
        # result shape is uniform with the fixed-wing result and the
        # Phase A3 distribution layer can treat the two the same way.
        "segments": [],
        "tx_em_kg": {p: 0.0 for p in POLLUTANTS},
        "brake_wear_em_kg": {p: 0.0 for p in POLLUTANTS},
        "total_em_kg": em,
    }


def _active_retained_fraction(
    conn, mov: dict, ctx: dict, category, is_dep: bool
) -> float:
    """Share of the active-mode time below the mixing height and inside the
    grid, on the same FOCA flight path the plugin builds: origin at the
    helicopter's gate centroid (its helipad) or else the active runway end;
    departure along the runway, arrival back along the approach."""
    from open_alaqs.core.tools.foca_heli_trajectory import (
        active_mode_retained,
        build_arrival,
        build_departure,
    )
    from openalaqs_standalone import geometry as geo

    runway = ctx["runways"][mov["runway_direction"]]
    origin = None
    if mov.get("gate"):
        gate = mv.get_gate(conn, mov["gate"])
        if gate is not None and gate["geom_3857"] is not None:
            c = gate["geom_3857"].centroid
            origin = (c.x, c.y)
    if origin is None:
        origin = geo.runway_threshold_3857(runway, mov["runway_direction"])
    az = geo.runway_azimuth_deg(runway, mov["runway_direction"], is_dep=is_dep)

    local_pts = build_departure(category) if is_dep else build_arrival(category)
    world = []
    for p in local_pts:
        if p.x_m == 0.0:
            x, y = origin
        else:
            x, y = geo.project_anp(origin, az, p.x_m, 0.0)
        world.append((x, y, p.z_m))

    bounds = ctx["grid_bounds"]

    def _clip(p1, p2):
        clipped = geo.clip_segment_2d(p1[:2], p2[:2], bounds)
        if clipped is None:
            return None
        (cx1, cy1), (cx2, cy2) = clipped
        full = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5

        def _z(cx, cy):
            f = ((cx - p1[0]) ** 2 + (cy - p1[1]) ** 2) ** 0.5 / full
            return p1[2] + f * (p2[2] - p1[2])

        return (cx1, cy1, _z(cx1, cy1)), (cx2, cy2, _z(cx2, cy2))

    max_height = mv.get_mixing_height_at(conn, mov["runway_time"])
    fraction, _ = active_mode_retained(
        local_pts, world, max_height_m=max_height, clip_2d=_clip
    )
    return fraction
