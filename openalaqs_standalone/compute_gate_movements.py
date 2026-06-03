"""
compute_gate_movements: per-movement gate emissions (Phase A2).

Gate emissions are the ground support equipment (GSE) and ground
power unit (GPU) emissions produced while an aircraft occupies a
gate. They are a per-movement quantity -- driven by the aircraft
movements, computed alongside the aircraft trajectory and taxi
emissions -- not a stationary spread of a pre-computed factor. That
is why this lives next to `compute_aircraft` / `compute_helicopter`
and not with the stationary `compute_gate` stub (which this module
makes obsolete for the movement-driven case).

The model, ported from the plugin's `GateEmissionCalculator` and
`DefaultGateEmissionProfile`:

  - A movement references a gate (`user_aircraft_movements.gate`) and
    carries a `gate_emissions_code` (1 = include gate emissions,
    0 = suppress them for this movement).
  - The gate has a type (PIER, REMOTE, CARGO, ...).
  - The aircraft has a group (JET SMALL, JET LARGE, TURBOPROP, ...).
  - `default_gate_profiles` is keyed by
    (gate_type, ac_group, emis_type, op_type) where emis_type is GPU
    or GSE and op_type is A or D. Each row gives an occupancy `time`
    in minutes and per-pollutant emission rates in grams/hour.
  - The emission for one (emis_type) is, per pollutant:
        emission_kg = (rate_g_per_hour / 1000) * (time_min / 60)
    The plugin reaches the same number by a longer route: its
    profile loader divides the grams/hour rate by 1000 to a
    kg_hour rate, and its calculator multiplies by occupancy_min/60.
    Both `emis_unit` must be "grams/hour" and `time_unit` "minutes";
    the plugin raises otherwise, and so does this module.
  - The movement's gate emission is the sum over GPU and GSE.
  - Helicopters have no gate, so they produce no gate emission.

Aircraft-group matching: the plugin tries an exact group match first,
then a `difflib` close-match fallback. This module does the same, so
a movement whose aircraft group is not spelled exactly as in
`default_gate_profiles` still resolves the way the plugin resolves it.

The result is a per-pollutant emission dict in kg. It is returned
separately (a `gate_em_kg` field on the movement result) rather than
folded into the aircraft `total_em_kg`: the plugin emits gate
emissions as their own source type, distinct from the Movement
source, and the Phase A0 validation CSVs contain only the Movement
rows. Keeping gate emissions separate keeps the Phase A0 gate test
meaningful and matches the plugin's own source-type split.

This module imports only the standalone's own packages, the standard
library, and difflib. No QGIS and no PyQt.
"""

from __future__ import annotations

import difflib
from typing import Optional

from openalaqs_standalone import movements as mv

# The five pollutants `default_gate_profiles` carries. Note this is
# five, not the six of the aircraft core: gate profiles have no CO2
# column. The aircraft POLLUTANTS tuple includes co2; gate emissions
# simply contribute 0.0 to co2.
GATE_POLLUTANTS = ("co", "hc", "nox", "sox", "pm10")

# The emission source types a gate profile is split into.
GATE_EMIS_TYPES = ("GPU", "GSE")

# Required unit strings in default_gate_profiles. The plugin raises if
# the table carries anything else; this module does the same, because
# the conversion arithmetic below assumes exactly these units.
_REQUIRED_EMIS_UNIT = "grams/hour"
_REQUIRED_TIME_UNIT = "minutes"


def _match_ac_group(
    ac_group: str,
    available_groups: list,
) -> Optional[str]:
    """Resolve an aircraft group against the groups a gate profile has.

    Exact match first; then a difflib close-match fallback, the same
    two-step the plugin's `_get_aircraft_group_match` uses. Returns the
    matched group string, or None if neither step finds one.
    """
    if ac_group in available_groups:
        return ac_group
    matched = difflib.get_close_matches(ac_group, available_groups)
    if matched:
        return matched[0]
    return None


def compute_gate_emissions_for_movement(
    conn,
    mov: dict,
    gate_profiles: Optional[dict] = None,
) -> dict:
    """Compute the gate (GSE + GPU) emission for one movement.

    Parameters
    ----------
    conn
        An open `.alaqs` connection.
    mov
        A movement dict from `movements.get_movement`. The fields used
        are `aircraft` (ICAO), `gate` (gate id, may be None or blank),
        `departure_arrival` ("A" or "D"), and `gate_emissions_code`.
    gate_profiles
        Optionally, the dict from `movements.get_gate_profiles`. The
        whole table is small and movement-independent, so a caller
        looping over movements should read it once and pass it in; if
        omitted it is read here.

    Returns
    -------
    A dict mapping each of GATE_POLLUTANTS to kg, the movement's gate
    emission summed over GPU and GSE. Every key is always present;
    the dict is all-zero when the movement has no gate emission, which
    happens when:
      - the movement references no gate (`gate` is None or blank),
      - `gate_emissions_code` is 0 (gate emissions suppressed),
      - the aircraft is a helicopter (helicopters have no gate),
      - the aircraft group has no profile in `default_gate_profiles`,
      - the referenced gate id is not in `shapes_gates`.

    The arithmetic, per emis_type and pollutant:
        kg = (rate_grams_per_hour / 1000) * (occupancy_minutes / 60)
    summed over GPU and GSE.
    """
    zero = {p: 0.0 for p in GATE_POLLUTANTS}

    # gate_emissions_code 0 suppresses gate emissions for this movement.
    code = mov.get("gate_emissions_code")
    if code is not None:
        try:
            if int(code) == 0:
                return dict(zero)
        except (ValueError, TypeError):
            # an unparseable code is treated as the default (include),
            # matching the plugin's Movement.__init__ fallback.
            pass

    # A movement with no gate reference produces no gate emission.
    gate_id = mov.get("gate")
    if gate_id is None or str(gate_id).strip() == "":
        return dict(zero)

    # Helicopters have no gate. The aircraft group is the helicopter
    # tell here: get_aircraft_group returns None for a helicopter ICAO
    # (its default_aircraft row has no fixed-wing ac_group), and a
    # group is needed for the profile lookup anyway.
    ac_group = mv.get_aircraft_group(conn, mov["aircraft"])
    if ac_group is None:
        return dict(zero)

    gate = mv.get_gate(conn, str(gate_id))
    if gate is None:
        return dict(zero)
    gate_type = gate["gate_type"]

    if gate_profiles is None:
        gate_profiles = mv.get_gate_profiles(conn)

    op_type = mov["departure_arrival"]

    # The groups that have a profile for this gate type, for the
    # close-match fallback.
    groups_for_type = sorted({key[1] for key in gate_profiles if key[0] == gate_type})
    matched_group = _match_ac_group(ac_group, groups_for_type)
    if matched_group is None:
        return dict(zero)

    em = {p: 0.0 for p in GATE_POLLUTANTS}
    for emis_type in GATE_EMIS_TYPES:
        key = (gate_type, matched_group, emis_type, op_type)
        profile = gate_profiles.get(key)
        if profile is None:
            continue
        # The conversion arithmetic assumes these exact units; the
        # plugin raises on anything else, and so do we.
        if profile["emis_unit"] != _REQUIRED_EMIS_UNIT:
            raise ValueError(
                f"default_gate_profiles row {key} has emis_unit "
                f"{profile['emis_unit']!r}, expected "
                f"{_REQUIRED_EMIS_UNIT!r}"
            )
        if profile["time_unit"] != _REQUIRED_TIME_UNIT:
            raise ValueError(
                f"default_gate_profiles row {key} has time_unit "
                f"{profile['time_unit']!r}, expected "
                f"{_REQUIRED_TIME_UNIT!r}"
            )
        occupancy_min = profile["time_min"]
        for p in GATE_POLLUTANTS:
            rate_g_per_hour = profile[p]
            # g/h -> kg/h is /1000; minutes -> hours is /60.
            em[p] += (rate_g_per_hour / 1000.0) * (occupancy_min / 60.0)

    return em
