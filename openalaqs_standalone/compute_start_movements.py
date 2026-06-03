"""
compute_start_movements: per-movement engine-start emissions.

Mirrors the plugin's _apply_start_engine_emissions logic from
open_alaqs/core/MovementEmissionCalculator.py:599. Each aircraft
engine contributes one start-emission event at the beginning of the
taxi-out phase. Per the plugin:

  - Departures only. The plugin's
    _apply_single_engine_taxiing_emissions_for_arrival (line 619) does
    NOT call _apply_start_engine_emissions; only the _for_departure
    counterpart (line 539, calling at line 573) does. Engines do not
    start on arrival.
  - Spatial placement is the first taxi segment (index_segment == 0)
    of the taxi-out route. The standalone follows its existing
    convention of lumping all stationary aircraft emissions (taxi,
    gate, APU) at the runway/taxi intersection cell; start emissions
    join them there. A future step can refine the placement.
  - Per movement, the added mass is
        start_emissions[ac_group][pollutant] * number_of_engines
    where number_of_engines = aircraft.getEngineCount() unless one of
    the set_time_of_main_engine_start fields is set (single-engine
    taxi configuration). The canonical test study has neither set; the standalone
    therefore always uses the full engine count, matching the plugin
    for this study.

Data source: default_aircraft_start_ef. One row per aircraft_group
(JET SMALL, JET MEDIUM, JET LARGE, JET BUSINESS, JET REGIONAL,
PROPELLER, TURBOPROP, SUPERSONIC, HELICOPTER LIGHT, HELICOPTER HEAVY).
The unit string in the table is "gram/aircraft" but the plugin
multiplies by getEngineCount(); the standalone matches that
convention.

The table populates HC only on every reference dataset checked so far
(every other pollutant column is 0.0). The module still propagates
all five emission_unit columns so that any future non-zero EF is
carried through without code change.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

# The five pollutants the table carries (CO, HC, NOx, SOx, PM10).
# Same set as GATE_POLLUTANTS and APU_POLLUTANTS so the per-movement
# result has consistent shape across the gate/APU/start trio.
START_POLLUTANTS = ("co", "hc", "nox", "sox", "pm10")


# ---------------------------------------------------------------------------
# Context loaders. The two tables are small and movement-independent;
# loaded once per study run and passed to compute_start_emissions_for_movement
# via keyword args so the per-movement code is SELECT-free.
# ---------------------------------------------------------------------------


def get_start_efs(conn: sqlite3.Connection) -> dict:
    """Read default_aircraft_start_ef into a per-group dict.

    Returns {aircraft_group: {pollutant: g_per_engine_start}}. Each
    pollutant defaults to 0.0 if the column is NULL.
    """
    out = {}
    for r in conn.execute(
        "SELECT aircraft_group, co, hc, nox, sox, pm10 "
        "FROM default_aircraft_start_ef"
    ):
        group = r[0]
        if group is None:
            continue
        out[str(group)] = {
            "co": float(r[1] or 0.0),
            "hc": float(r[2] or 0.0),
            "nox": float(r[3] or 0.0),
            "sox": float(r[4] or 0.0),
            "pm10": float(r[5] or 0.0),
        }
    return out


def get_aircraft_groups_and_engines(conn: sqlite3.Connection) -> dict:
    """Read default_aircraft into {icao: (ac_group, engine_count)}.

    engine_count is the table's TEXT column parsed to int (e.g. '2'
    -> 2). Returns None for that field on rows that fail to parse,
    which propagates to a zero start-emission result downstream.
    """
    out = {}
    for icao, group, n_eng_s in conn.execute(
        "SELECT icao, ac_group, engine_count FROM default_aircraft"
    ):
        if icao is None:
            continue
        try:
            n_eng = int(float(n_eng_s)) if n_eng_s not in (None, "") else None
        except (TypeError, ValueError):
            n_eng = None
        out[str(icao)] = (group, n_eng)
    return out


# ---------------------------------------------------------------------------
# Per-movement compute
# ---------------------------------------------------------------------------


def compute_start_emissions_for_movement(
    conn: sqlite3.Connection,
    mov: dict,
    *,
    start_efs: Optional[dict] = None,
    aircraft_groups: Optional[dict] = None,
) -> dict:
    """Per-movement start emissions in kg per pollutant.

    Returns a dict with all five START_POLLUTANTS keys. The dict is
    all-zero when any of the following applies:
      - mov["departure_arrival"] is not 'D' (arrivals never start
        engines; the plugin's arrival handler does not call
        _apply_start_engine_emissions),
      - the aircraft ICAO has no row in default_aircraft,
      - the aircraft's ac_group is NULL (helicopters detected via
        get_aircraft_group returning None elsewhere also land here),
      - engine_count cannot be parsed,
      - the aircraft's ac_group has no row in
        default_aircraft_start_ef.

    Parameters
    ----------
    start_efs, aircraft_groups
        Optional pre-loaded context dicts from get_start_efs and
        get_aircraft_groups_and_engines. Pass them for study-level
        calls so the per-movement code stays free of SELECTs; omit
        them for one-off calls and the module fetches on demand.
    """
    zero = {p: 0.0 for p in START_POLLUTANTS}

    # Arrivals: plugin's arrival handler never adds start emissions.
    if mov.get("departure_arrival") != "D":
        return dict(zero)

    if aircraft_groups is None:
        aircraft_groups = get_aircraft_groups_and_engines(conn)
    info = aircraft_groups.get(mov["aircraft"])
    if info is None:
        return dict(zero)
    group, n_eng = info
    if group is None or n_eng is None or n_eng <= 0:
        return dict(zero)

    if start_efs is None:
        start_efs = get_start_efs(conn)
    group_ef = start_efs.get(group)
    if group_ef is None:
        return dict(zero)

    # Per-engine grams x engine count -> grams, then to kg.
    return {p: group_ef.get(p, 0.0) * n_eng / 1000.0 for p in START_POLLUTANTS}


# ---------------------------------------------------------------------------
# Study-level driver (diagnostic; production path uses
# compute_movements.compute_all_movements which calls the per-movement
# function via the context dict)
# ---------------------------------------------------------------------------


def compute_start_emissions_for_all_movements(
    conn: sqlite3.Connection,
) -> dict:
    """Diagnostic helper: per-pollutant totals and skipped counts.

    Returns {"totals": {pollutant: kg}, "skipped": {reason: n}, "ok": n}.
    Use to sanity-check that the per-movement compute behaves as
    expected against a specific .alaqs without running the whole
    compute_movements pipeline.
    """
    start_efs = get_start_efs(conn)
    aircraft_groups = get_aircraft_groups_and_engines(conn)
    totals = {p: 0.0 for p in START_POLLUTANTS}
    skipped = {
        "arrival": 0,
        "no_aircraft_row": 0,
        "no_group_or_engine_count": 0,
        "no_start_ef_row": 0,
        "ok": 0,
    }
    for r in conn.execute(
        "SELECT oid, aircraft, departure_arrival FROM user_aircraft_movements"
    ):
        oid, ac, da = r
        if da != "D":
            skipped["arrival"] += 1
            continue
        info = aircraft_groups.get(ac)
        if info is None:
            skipped["no_aircraft_row"] += 1
            continue
        group, n_eng = info
        if group is None or n_eng is None or n_eng <= 0:
            skipped["no_group_or_engine_count"] += 1
            continue
        group_ef = start_efs.get(group)
        if group_ef is None:
            skipped["no_start_ef_row"] += 1
            continue
        skipped["ok"] += 1
        for p in START_POLLUTANTS:
            totals[p] += group_ef.get(p, 0.0) * n_eng / 1000.0
    return {"totals": totals, "skipped": skipped}
