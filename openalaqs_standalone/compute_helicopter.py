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


def compute_helicopter(conn, mov: dict) -> Optional[dict]:
    """Compute FOCA Appendix A half-LTO totals for one helicopter movement.

    Parameters
    ----------
    conn
        An open `.alaqs` connection (from `movements.connect`).
    mov
        The movement dict from `movements.get_movement`. A helicopter
        movement is one with no `profile_id`; the dispatch layer is
        responsible for routing such movements here.

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

    # Half-LTO totals: GI plus the active mode, converted g -> kg.
    # SOx is not modelled by FOCA; it is zero, matching the reference.
    em = {
        "co": (gi.co_g + active.co_g) / 1000.0,
        "co2": (gi.co2_g + active.co2_g) / 1000.0,
        "hc": (gi.hc_g + active.hc_g) / 1000.0,
        "nox": (gi.nox_g + active.nox_g) / 1000.0,
        "sox": 0.0,
        "pm10": (gi.pm_g + active.pm_g) / 1000.0,
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
            active.mode: active.fuel_kg,
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
