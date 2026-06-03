"""
compute_apu_movements: per-movement APU emissions.

The aircraft's onboard Auxiliary Power Unit (APU) burns fuel while
the aircraft is parked at the gate/stand. It is a movement-driven
emission like the gate (GSE/GPU) and aircraft taxi/take-off
emissions, and the plugin folds it into the same Movement source
type. This module is the standalone equivalent.

Model, ported from the plugin's `MovementEmissionCalculator.
_apply_apu_emissions` / `_load_apu_info` (open_alaqs/core/modules):

  - An aircraft type has an `apu_id` (an APU model name) in
    `default_aircraft`. The apu_id may be NULL or the literal string
    "None" for aircraft without an APU (small propeller aircraft,
    general aviation); both are treated as "no APU".
  - `default_aircraft_apu_ef` gives the emission rate of an APU in
    kilograms per hour, per pollutant, keyed by `apu_id`. The rows
    cover co, hc, nox, sox, and pm10. (No co2, no pm25 in this
    table; both default to 0.0.)
  - `default_apu_times` gives the APU's runtime in minutes for the
    arrival and departure phases, keyed by (ac_category, stand_type).
    `ac_category` is the same vocabulary as `default_aircraft.ac_group`
    (JET LARGE, JET MEDIUM, ..., TURBOPROP). `stand_type` is the gate
    type from `shapes_gates.gate_type` (PIER, REMOTE, CARGO).
  - The emission per pollutant for one movement is:
        emission_kg = ef_kg_h * (time_min / 60)
    where time_min is `time_arr_min` for arrivals and `time_dep_min`
    for departures.

This module implements the apu_code=1 ("APU at stand only") variant.
The plugin also supports apu_code=2 ("APU at stand + entire taxi"),
which adds the taxi-phase APU runtime to the stand time. The v3
study files we have do not carry `apu_code` per movement, so the
default behaviour matches the plugin's apu_code=1 path. If
`apu_code` does appear on the movement (column `apu_code` in
`user_aircraft_movements`), it is honoured: 0 or -1 suppresses,
1 uses stand time only, 2 adds the full taxi time.

The result is a per-pollutant dict in kg. It is returned as a
`apu_em_kg` field and folded into the per-movement `total_em_kg`,
mirroring the gate fold in `compute_movements.compute_for_movement`.
This means standalone aircraft cells (after the fold) carry
LTO + GSE/GPU + APU, just like the plugin's Movement source type.

The dict is all-zero when:
  - the aircraft has no apu_id in default_aircraft
  - the apu_id is NULL, blank, or the literal "None"
  - default_aircraft_apu_ef has no row for the apu_id
  - the movement has no gate, or the gate is not in shapes_gates
  - default_apu_times has no row for (ac_group, gate_type)
  - the relevant arr/dep time is 0 or NULL
  - apu_code is 0 or -1

Imports only the standard library and openalaqs_standalone. No QGIS,
no PyQt.
"""

from __future__ import annotations

import difflib
import sqlite3
from typing import Optional

from openalaqs_standalone import compute_gate_movements as _cg

# The five pollutants default_aircraft_apu_ef carries. Same as
# GATE_POLLUTANTS so the fold into total_em_kg is a no-op for any
# pollutant the aircraft core also computes.
APU_POLLUTANTS = ("co", "hc", "nox", "sox", "pm10")

# Mapping from default_aircraft_apu_ef column names to APU_POLLUTANTS.
# The table uses *_kg_h suffixes; pm2.5 has no column (and isn't
# emitted by APUs at the resolution the table targets).
_EF_COLUMN_MAP = {
    "co": "co_kg_h",
    "hc": "hc_kg_h",
    "nox": "nox_kg_h",
    "sox": "sox_kg_h",
    "pm10": "pm10_kg_h",
}

# Treated as "no APU": NULL, blank, the literal strings "None" and
# "none" (case-insensitive). The data has all four shapes in
# practice.
_NO_APU_SENTINELS = {"", "none", "null"}


# ---------------------------------------------------------------------------
# apu_id resolution
# ---------------------------------------------------------------------------


def _resolve_apu_id(search: str, available) -> Optional[str]:
    """Fuzzy-match an apu_id against the apu_ids in
    default_aircraft_apu_ef.

    The plugin's reference behaviour, ported from
    open_alaqs/core/utils/utils.fuzzy_match (called from
    open_alaqs/core/interfaces/Aircraft.py:360 via
    Aircraft.setApuEmissions), is to run difflib.get_close_matches
    with n=1 and the default cutoff (0.6) -- unconditionally, no
    exact-match-first preference. Exact matches still win because
    they have SequenceMatcher ratio 1.0; fuzzy matches only kick in
    when no exact key exists.

    This matters because default_aircraft.apu_id can use a short
    canonical name (e.g. 'GTCP 36-150') while
    default_aircraft_apu_ef stores bracketed variant tags
    ('GTCP 36-150[]' = unsuffixed, 'GTCP 36-150[RR]' = Rolls-Royce
    variant). Exact-match dict lookup misses the connection and the
    apu silently emits zero; difflib bridges it.

    Returns the matched key or None.
    """
    if not search or not available:
        return None
    matched = difflib.get_close_matches(search, list(available), n=1)
    return matched[0] if matched else None


# ---------------------------------------------------------------------------
# Context loaders (each table is small and movement-independent;
# load once per study run and pass to compute_apu_emissions_for_movement
# via the keyword args, so the per-movement code stays SELECT-free)
# ---------------------------------------------------------------------------


def get_apu_efs(conn: sqlite3.Connection) -> dict:
    """Return {apu_id: {pollutant: kg_per_hour}}.

    Missing APU IDs simply do not appear in the dict; callers should
    use `.get(apu_id, {})` and treat absence as zero emissions.
    """
    cols = ", ".join(f"{c} AS {p}_h" for p, c in _EF_COLUMN_MAP.items())
    rows = conn.execute(
        f"SELECT apu_id, {cols} FROM default_aircraft_apu_ef"
    ).fetchall()
    out = {}
    for r in rows:
        apu_id = r[0]
        if apu_id is None or str(apu_id).strip().lower() in _NO_APU_SENTINELS:
            continue
        out[apu_id] = {p: float(r[i + 1] or 0.0) for i, p in enumerate(APU_POLLUTANTS)}
    return out


def get_apu_times(conn: sqlite3.Connection) -> dict:
    """Return {(ac_category, stand_type): (arr_min, dep_min)}.

    Times are minutes; None or 0 in either slot means "no APU runtime
    for this combo and phase".
    """
    rows = conn.execute(
        "SELECT ac_category, stand_type, time_arr_min, time_dep_min "
        "FROM default_apu_times"
    ).fetchall()
    out = {}
    for ac_cat, stand, arr, dep in rows:
        if ac_cat is None or stand is None:
            continue
        out[(ac_cat, stand)] = (
            float(arr) if arr is not None else 0.0,
            float(dep) if dep is not None else 0.0,
        )
    return out


def get_gate_types(conn: sqlite3.Connection) -> dict:
    """Return {gate_id: gate_type}.

    Mirrors shapes_gates. A gate id missing here cannot be resolved
    and the movement gets zero APU emissions.
    """
    rows = conn.execute("SELECT gate_id, gate_type FROM shapes_gates").fetchall()
    return {gid: gtype for gid, gtype in rows if gid is not None}


def get_aircraft_apu_ids(conn: sqlite3.Connection) -> dict:
    """Return {icao: (apu_id, ac_group)}.

    `apu_id` may be None, blank, or the literal "None"; the caller
    normalises via `_NO_APU_SENTINELS`. `ac_group` is the key into
    apu_times.
    """
    rows = conn.execute(
        "SELECT icao, apu_id, ac_group FROM default_aircraft"
    ).fetchall()
    return {icao: (apu_id, ac_group) for icao, apu_id, ac_group in rows}


# ---------------------------------------------------------------------------
# Per-movement compute
# ---------------------------------------------------------------------------


def compute_apu_emissions_for_movement(
    conn: sqlite3.Connection,
    mov: dict,
    apu_efs: Optional[dict] = None,
    apu_times: Optional[dict] = None,
    gate_types: Optional[dict] = None,
    aircraft_apu_ids: Optional[dict] = None,
) -> dict:
    """Compute APU emissions for one movement.

    Parameters
    ----------
    conn
        Open .alaqs connection. Only used when a context dict is not
        supplied (so per-movement loops can skip the redundant
        per-table SELECTs).
    mov
        Movement dict from `movements.get_movement`. Reads
        `aircraft`, `gate`, `departure_arrival`, and (if present)
        `apu_code`.
    apu_efs, apu_times, gate_types, aircraft_apu_ids
        Pre-loaded context tables. Pass these once per study run
        instead of paying the SELECT cost per movement.

    Returns
    -------
    A dict mapping each APU_POLLUTANTS key to kg. All keys are
    always present; the dict is all-zero when any of the lookup
    steps fail (see module docstring for the full list).
    """
    zero = {p: 0.0 for p in APU_POLLUTANTS}

    # apu_code: -1, 0 => suppress; 1 => stand only (the default if
    # the column is absent or blank); 2 => stand + taxi. Unknown /
    # non-integer codes are treated as 1 (include, stand only) per
    # the plugin's permissive fallback.
    code_raw = mov.get("apu_code")
    apu_code = 1
    if code_raw is not None:
        try:
            apu_code = int(code_raw)
        except (ValueError, TypeError):
            apu_code = 1
    if apu_code <= 0:
        return dict(zero)

    # Resolve apu_id and ac_group for the aircraft.
    aircraft = mov.get("aircraft")
    if aircraft is None:
        return dict(zero)
    if aircraft_apu_ids is None:
        row = conn.execute(
            "SELECT apu_id, ac_group FROM default_aircraft WHERE icao=?",
            (aircraft,),
        ).fetchone()
        if row is None:
            return dict(zero)
        apu_id, ac_group = row
    else:
        info = aircraft_apu_ids.get(aircraft)
        if info is None:
            return dict(zero)
        apu_id, ac_group = info

    if apu_id is None or str(apu_id).strip().lower() in _NO_APU_SENTINELS:
        return dict(zero)
    if ac_group is None or str(ac_group).strip() == "":
        return dict(zero)

    # Resolve gate -> gate_type (= stand_type in apu_times).
    gate_id = mov.get("gate")
    if gate_id is None or str(gate_id).strip() == "":
        return dict(zero)
    if gate_types is None:
        row = conn.execute(
            "SELECT gate_type FROM shapes_gates WHERE gate_id=?",
            (str(gate_id),),
        ).fetchone()
        if row is None:
            return dict(zero)
        stand_type = row[0]
    else:
        stand_type = gate_types.get(str(gate_id))
        if stand_type is None:
            return dict(zero)

    # Resolve emission factors via fuzzy match against the EF
    # table's keys, mirroring the plugin's Aircraft.setApuEmissions
    # path (open_alaqs/core/interfaces/Aircraft.py:360). On-demand
    # lookup loads the EF table once to know the available keys; the
    # production path is the context-cached form where the caller
    # has pre-loaded apu_efs via get_apu_efs(conn).
    if apu_efs is None:
        apu_efs = get_apu_efs(conn)
    matched_apu_id = _resolve_apu_id(apu_id, apu_efs.keys())
    if matched_apu_id is None:
        return dict(zero)
    ef = apu_efs[matched_apu_id]

    # Resolve runtime. Match ac_group against the categories in
    # default_apu_times; reuse the gate module's group matcher
    # (exact, then difflib close-match) so spelling drift between
    # default_aircraft.ac_group and default_apu_times.ac_category
    # resolves the same way it does in the gate path.
    if apu_times is None:
        apu_times = get_apu_times(conn)
    categories_for_stand = sorted(
        {cat for (cat, st) in apu_times.keys() if st == stand_type}
    )
    matched_cat = _cg._match_ac_group(ac_group, categories_for_stand)
    if matched_cat is None:
        return dict(zero)

    arr_min, dep_min = apu_times[(matched_cat, stand_type)]
    is_arrival = mov.get("departure_arrival") == "A"
    stand_min = arr_min if is_arrival else dep_min

    # apu_code 2: add the full taxi time on top of stand time. The
    # plugin's _apply_apu_emissions splits this across taxi segments
    # for spatial assignment; here we want only the total mass per
    # movement (spatial assignment happens later in
    # austal_aircraft.build_aircraft_austal_tables), so we add the
    # whole taxi duration to the runtime budget.
    extra_min = 0.0
    if apu_code == 2:
        rt = mov.get("runway_time")
        bt = mov.get("block_time")
        if rt and bt:
            from datetime import datetime

            def _parse(s):
                if hasattr(s, "year"):
                    return s
                # Permissive parse: accept "YYYY-MM-DD HH:MM:SS" and ISO.
                s = str(s).replace("T", " ")
                return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")

            try:
                taxi_s = abs((_parse(rt) - _parse(bt)).total_seconds())
                extra_min = taxi_s / 60.0
            except (ValueError, TypeError):
                extra_min = 0.0

    total_min = stand_min + extra_min
    if total_min <= 0.0:
        return dict(zero)

    hours = total_min / 60.0
    return {p: ef[p] * hours for p in APU_POLLUTANTS}


# ---------------------------------------------------------------------------
# Diagnostic helper
# ---------------------------------------------------------------------------


def compute_apu_emissions_for_all_movements(
    conn: sqlite3.Connection,
    oids: Optional[list] = None,
) -> dict:
    """Compute APU emissions over the whole study.

    Returns a dict with:
      - 'totals'         {pollutant: total_kg}
      - 'per_movement'   list of (oid, dict)
      - 'skipped'        {reason: count}

    Useful for validation outside the main compute_movements loop.
    """
    from openalaqs_standalone import movements as mv

    apu_efs = get_apu_efs(conn)
    apu_times = get_apu_times(conn)
    gate_types = get_gate_types(conn)
    aircraft_apu_ids = get_aircraft_apu_ids(conn)

    if oids is None:
        oids = mv.get_movement_oids(conn)

    totals = {p: 0.0 for p in APU_POLLUTANTS}
    per_movement = []
    skipped = {
        "no_aircraft_row": 0,
        "no_apu_id": 0,
        "no_ef_row": 0,
        "no_gate_or_stand": 0,
        "no_apu_time": 0,
        "zero_time": 0,
        "ok": 0,
    }
    for oid in oids:
        mov = mv.get_movement(conn, oid)
        if mov is None:
            skipped["no_aircraft_row"] += 1
            continue
        em = compute_apu_emissions_for_movement(
            conn,
            mov,
            apu_efs=apu_efs,
            apu_times=apu_times,
            gate_types=gate_types,
            aircraft_apu_ids=aircraft_apu_ids,
        )
        per_movement.append((oid, em))
        total = sum(em.values())
        if total == 0.0:
            # Categorise the zero reason. This is a re-run of the
            # checks; cheap because the dicts are pre-loaded.
            info = aircraft_apu_ids.get(mov.get("aircraft"))
            if info is None:
                skipped["no_aircraft_row"] += 1
                continue
            apu_id, ac_group = info
            if apu_id is None or str(apu_id).strip().lower() in _NO_APU_SENTINELS:
                skipped["no_apu_id"] += 1
                continue
            if _resolve_apu_id(apu_id, apu_efs.keys()) is None:
                skipped["no_ef_row"] += 1
                continue
            gate_id = mov.get("gate")
            stand_type = gate_types.get(str(gate_id) if gate_id else "")
            if stand_type is None:
                skipped["no_gate_or_stand"] += 1
                continue
            cats_for_stand = sorted({c for (c, st) in apu_times if st == stand_type})
            matched = _cg._match_ac_group(ac_group, cats_for_stand)
            if matched is None:
                skipped["no_apu_time"] += 1
                continue
            skipped["zero_time"] += 1
        else:
            skipped["ok"] += 1
            for p, kg in em.items():
                totals[p] += kg

    return {"totals": totals, "per_movement": per_movement, "skipped": skipped}
