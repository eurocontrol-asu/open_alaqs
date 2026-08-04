"""Standalone compute for engine-test emissions.

QGIS-free twin of ``open_alaqs.core.modules.EngineTestSourceModule``.
Same math, same skip-with-warning contract, so Dataiku offline runs
produce identical per-period-per-source-per-pollutant masses to the
plugin.

Inputs are POD dicts / lists (no plugin classes) so the module has no
runtime dependency on QGIS or the plugin core. Callers wire this into
their Dataiku recipe alongside the existing ``austal_prep`` /
``compute_bffm2`` pipelines.

Design (per phase 0 memo):
  * D4 window-fraction hour-split: identical formula to the plugin,
    reimplemented here in native Python.
  * D2 thrust-mode override: per event; ``'snap'`` uses the raw EI
    for that mode. ``'meem'`` is accepted and produces numerically
    identical results to ``'snap'`` for engine-test events. This is
    NOT a coverage gap: MEEM V1 only corrects nvPM EIs, and its LTO
    branch is a log-log / linear interpolation across the four ICAO
    EEDB anchor points. Since engine-test events always run at one of
    those anchor thrust settings (TX=0.07, AP=0.30, CL=0.85, TO=1.00
    F00), the interpolation trivially returns the anchor's own nvPM
    value. Gas-phase pollutants (NOx, CO, HC, SOx) are untouched by
    MEEM V1 in any case. See the plugin's ``getEmissionIndexByModeWithMEEM``
    for the reference implementation. If future work introduces
    non-anchor thrust events, the standalone path here becomes
    non-trivial and must delegate to ``open_alaqs.core.tools.meem_v1``.
  * D5 one aircraft/engine per event: mixed run-ups appear as
    multiple events sharing source_id.
  * D10 interval-overlap: same strict ``<`` semantics.
"""

from __future__ import annotations

import sqlite3  # noqa: E402  (kept adjacent to the typing imports)
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Mode-keys shared with the plugin. Order preserved so downstream tables
# have a stable column order.
_MODE_KEYS: Tuple[str, ...] = ("TX", "AP", "CL", "TO")

_MODE_TIME_COL = {
    "TX": "t_TX_s",
    "AP": "t_AP_s",
    "CL": "t_CL_s",
    "TO": "t_TO_s",
}


# BFFM2 mode-name mapping: our short mode keys → the name-form the
# shared bffm2 module expects. Matches openalaqs_standalone.compute_aircraft.
_BFFM2_MODE_NAMES = {
    "TX": "Idle",
    "AP": "Approach",
    "CL": "Climbout",
    "TO": "Takeoff",
}

# CAEP14 installation corrections. Same as compute_aircraft's; kept
# adjacent for source-of-truth clarity.
_BFFM2_INSTALLATION_CORRECTIONS = {
    "Takeoff": 1.010,
    "Climbout": 1.013,
    "Approach": 1.020,
    "Idle": 1.100,
}


# Pollutants tracked. Same set as ``PollutantType`` in the plugin's
# Emissions.py.
_POLLUTANTS: Tuple[str, ...] = (
    "fuel",
    "co",
    "co2",
    "hc",
    "nox",
    "sox",
    "pm10",
    "p1",
    "p2",
    "pm10_nonvol",
    "pm10_sul",
    "pm10_organic",
)


def _parse_iso_datetime(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _period_window_fraction(
    event_start: Optional[datetime],
    event_end: Optional[datetime],
    period_start: datetime,
    period_end: datetime,
) -> float:
    """Fraction of ``[event_start, event_end]`` inside
    ``[period_start, period_end]``. Same math as the plugin helper.
    """
    if event_start is None or event_end is None:
        return 0.0
    total_s = (event_end - event_start).total_seconds()
    if total_s <= 0.0:
        return 0.0
    overlap_start = max(event_start, period_start)
    overlap_end = min(event_end, period_end)
    overlap_s = (overlap_end - overlap_start).total_seconds()
    if overlap_s <= 0.0:
        return 0.0
    return overlap_s / total_s


def _resolve_engine_count(event: Dict, aircraft_lookup: Dict) -> Optional[int]:
    """Row's engine_count wins; otherwise fall back to aircraft's
    ``engine_count`` in ``aircraft_lookup[aircraft_type]``. Returns None
    if neither is available.
    """
    n = event.get("engine_count")
    if n not in (None, ""):
        try:
            return int(n)
        except (TypeError, ValueError):
            pass
    aircraft = aircraft_lookup.get(event.get("aircraft_type"))
    if aircraft is None:
        return None
    n2 = aircraft.get("engine_count")
    if n2 in (None, ""):
        return None
    try:
        return int(n2)
    except (TypeError, ValueError):
        return None


def _resolve_engine_uid(event: Dict, aircraft_lookup: Dict) -> Optional[str]:
    """Row's engine_uid wins; otherwise fall back to aircraft's
    default engine_uid."""
    uid = event.get("engine_uid")
    if uid not in (None, ""):
        return str(uid)
    aircraft = aircraft_lookup.get(event.get("aircraft_type"))
    if aircraft is None:
        return None
    default_uid = aircraft.get("engine_uid")
    return str(default_uid) if default_uid not in (None, "") else None


def _add_ei_to_totals(
    totals: Dict[str, float],
    ei_row: Dict,
    t_effective_s: float,
) -> None:
    """Add one engine * mode * time-slice's emissions into a per-source
    running total.

    ``ei_row`` is a dict shaped like ``default_aircraft_engine_ei``:
      * ``fuel_kg_sec`` (fuel flow per engine).
      * ``co_ei``, ``hc_ei``, ``nox_ei``, ``sox_ei``, ``pm10_ei``,
        ``p1_ei``, ``p2_ei`` (pollutant EI, grams per kilogram fuel).
      * Optional: ``pm10_nonvol``, ``pm10_sul``, ``pm10_organic``
        (PM subclasses).

    Matches Emission.add() in the plugin: fuel_burned = FF * t_effective;
    pollutant_g = EI[g_kg] * fuel_burned.
    """
    ff = ei_row.get("fuel_kg_sec")
    if ff is None:
        return
    fuel_burned = float(ff) * t_effective_s
    totals["fuel"] += fuel_burned

    # Map internal totals-dict pollutant name → actual column name in
    # default_aircraft_engine_ei. The DB column names are compact
    # (co_ei, nox_ei); the totals dict uses the pollutant name alone
    # (co, nox). CO2 is computed from fuel_burned since default EI is
    # 3160 g/kg (matches Movement.py:defaultEI).
    _EI_KEY_MAP = {
        "co": "co_ei",
        "hc": "hc_ei",
        "nox": "nox_ei",
        "sox": "sox_ei",
        "pm10": "pm10_ei",
        "p1": "p1_ei",
        "p2": "p2_ei",
        "pm10_nonvol": "pm10_nonvol",
        "pm10_sul": "pm10_sul",
        "pm10_organic": "pm10_organic",
    }
    for pol, ei_key in _EI_KEY_MAP.items():
        v = ei_row.get(ei_key)
        if v is None:
            continue
        # Emission mass in grams. Matches plugin convention.
        totals[pol] += float(v) * fuel_burned

    # CO2 has no per-engine EI column in the EEDB; use the fixed
    # 3160 g/kg default that the plugin's Emissions.py:defaultEI also
    # uses. Passing through fuel_burned means CO2 = 3160 * fuel_burned.
    totals["co2"] += 3160.0 * fuel_burned


def _build_icao_eedb_for_engine(
    engine_uid: str, ei_lookup: Dict[Tuple[str, str], Dict]
) -> Optional[Dict]:
    """Build the BFFM2-shaped icao_eedb dict for one engine.

    Format expected by ``open_alaqs.core.tools.bffm2.calculate_emission_index``:
      ``{pollutant: {mode_name: {ff_ref_kg_s: ei_g_kg}}}``

    Where ``pollutant`` is ``PollutantType.NOx / .CO / .HC`` (or the
    string variants they map from), ``mode_name`` is the BFFM2 name
    (``"Idle" / "Approach" / "Climbout" / "Takeoff"``), and
    ``ff_ref_kg_s`` is the mode's reference fuel flow.

    Returns ``None`` if any of the four modes is missing from the
    lookup, or if any missing has no ``fuel_kg_sec``. BFFM2 without a
    complete 4-mode anchor set is undefined.
    """
    # Import lazily so snap-only callers don't pull it in.
    from open_alaqs.core.interfaces.Emissions import PollutantType

    eedb: Dict = {
        p: {} for p in (PollutantType.NOx, PollutantType.CO, PollutantType.HC)
    }
    _POL_MAP = {
        PollutantType.NOx: "nox_ei",
        PollutantType.CO: "co_ei",
        PollutantType.HC: "hc_ei",
    }
    for mode, bffm2_name in _BFFM2_MODE_NAMES.items():
        row = ei_lookup.get((engine_uid, mode))
        if row is None:
            return None
        ff = row.get("fuel_kg_sec")
        if ff is None:
            return None
        ff = float(ff)
        for pol, ei_key in _POL_MAP.items():
            v = row.get(ei_key)
            if v is None:
                return None
            eedb[pol][bffm2_name] = {ff: float(v)}
    return eedb


def _add_bffm2_ei_to_totals(
    totals: Dict[str, float],
    ei_row: Dict,
    icao_eedb: Dict,
    meteo: Dict,
    t_effective_s: float,
) -> None:
    """Add one segment's BFFM2-corrected gas emissions plus base PM/SOx
    to the running totals dict.

    Gas-phase EIs (NOx, CO, HC) come from ``bffm2.calculate_emission_index``
    at the segment's ambient fuel flow. PM10, PM sub-classes, SOx, and
    fuel burn come from the per-mode ``ei_row`` (same as snap). Matches
    the plugin's Engine.getEmissionIndexByModeWithBFFM2 composition:
    BFFM2 gas + EEDB PM (Design A per phase 5 memo).
    """
    # Ambient fuel flow conversion: FF_ref → FF_amb via θ/δ/Mach.
    #   FF_amb = FF_ref * δ / θ^3.8 / exp(0.2*M²)
    # Matches Engine.getEmissionIndexByEngineState's pre-conversion so the
    # bffm2 module's internal inverse correction cancels the pre-conversion
    # and lands on the correct EEDB interpolation position.
    import math

    from open_alaqs.core.interfaces.Emissions import PollutantType
    from open_alaqs.core.tools.bffm2 import calculate_emission_index as _bffm2_ei

    ff_ref = float(ei_row.get("fuel_kg_sec") or 0.0)
    if ff_ref <= 0.0:
        # Missing FF; can't do BFFM2. Fall through to snap for this mode
        # by delegating to the standard _add_ei_to_totals-style math.
        _add_ei_to_totals(totals, ei_row, t_effective_s)
        return

    T_K = meteo["T_K"]
    P_Pa = meteo["P_Pa"]
    RH = meteo["RH"]
    mach = float(meteo.get("mach_number", 0.0))
    theta = T_K / 288.15
    delta = P_Pa / 101325.0
    ff_amb = ff_ref * delta / (theta**3.8) / math.exp(0.2 * mach**2)

    fuel_burned = ff_amb * t_effective_s
    totals["fuel"] += fuel_burned

    ambient_conditions = {
        "temperature_in_Kelvin": T_K,
        "pressure_in_Pa": P_Pa,
        "relative_humidity": RH,
        "mach_number": mach,
    }

    for pol_enum, dest_key in (
        (PollutantType.NOx, "nox"),
        (PollutantType.CO, "co"),
        (PollutantType.HC, "hc"),
    ):
        ei = _bffm2_ei(
            pol_enum,
            ff_amb,
            icao_eedb,
            ambient_conditions=ambient_conditions,
            installation_corrections=_BFFM2_INSTALLATION_CORRECTIONS,
        )
        totals[dest_key] += float(ei) * fuel_burned

    # PM10, SOx, and PM sub-classes from the EEDB row unchanged. CO2
    # is computed from fuel_burned since default_aircraft_engine_ei has
    # no CO2 column; use the fixed 3160 g/kg matching the plugin's
    # Emissions.py:defaultEI.
    _EEDB_PASSTHROUGH = {
        "sox": "sox_ei",
        "pm10": "pm10_ei",
        "p1": "p1_ei",
        "p2": "p2_ei",
        "pm10_nonvol": "pm10_nonvol",
        "pm10_sul": "pm10_sul",
        "pm10_organic": "pm10_organic",
    }
    for pol, ei_key in _EEDB_PASSTHROUGH.items():
        v = ei_row.get(ei_key)
        if v is None:
            continue
        totals[pol] += float(v) * fuel_burned

    totals["co2"] += 3160.0 * fuel_burned


def compute_engine_test_for_period(
    events: Iterable[Dict],
    period_start: datetime,
    period_end: datetime,
    ei_lookup: Dict[Tuple[str, str], Dict],
    aircraft_lookup: Dict,
    diagnostics: Optional[List[str]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Dict[str, float]]:
    """Compute per-source emission totals for one period.

    Parameters
    ----------
    events : iterable of dict
        Rows from ``extract_engine_test_events`` (or equivalent). Each
        row must have the schema documented in that module.
    period_start, period_end : datetime
        Period window.
    ei_lookup : dict keyed by ``(engine_uid, mode)`` -> ei_row dict.
        Where ``mode`` is one of ``"TX"``, ``"AP"``, ``"CL"``, ``"TO"``.
        Callers typically build this from ``default_aircraft_engine_ei``.
    aircraft_lookup : dict keyed by ``aircraft_type`` -> aircraft dict.
        Used for engine-count and default-engine-uid fallback.
    diagnostics : optional list to append skip-warning strings to. If
        provided, callers can surface these in their run log.
    conn : optional sqlite3 connection to the ``.alaqs`` project.
        Required only for events with ``thrust_mode='bffm2'``: used to
        look up ``tbl_InvMeteo`` at each event's midpoint. If not
        supplied, BFFM2 events fall back to snap with a single
        diagnostic. If supplied but the table is empty, BFFM2 events
        fall back to ISA-with-diagnostic (once per call).

    Returns
    -------
    dict keyed by ``source_id`` -> dict of totals per pollutant (grams,
    except ``"fuel"`` in kg). Same key set as ``_POLLUTANTS``. Sources
    with no contributions are omitted.
    """
    if diagnostics is None:
        diagnostics = []

    # Once-per-call flags for BFFM2 diagnostics.
    _bffm2_isa_fallback_logged = False
    _bffm2_no_conn_logged = False

    by_source: Dict[str, Dict[str, float]] = {}

    for event in events:
        if str(event.get("instudy") or "1").strip() != "1":
            continue

        e_start = _parse_iso_datetime(event.get("start_datetime"))
        e_end = _parse_iso_datetime(event.get("end_datetime"))
        fraction = _period_window_fraction(e_start, e_end, period_start, period_end)
        if fraction <= 0.0:
            continue

        engine_count = _resolve_engine_count(event, aircraft_lookup)
        if engine_count is None or engine_count <= 0:
            diagnostics.append(
                f"event {event.get('event_id')}: engine count unresolved / "
                "non-positive; skipping"
            )
            continue

        engine_uid = _resolve_engine_uid(event, aircraft_lookup)
        if engine_uid is None:
            diagnostics.append(
                f"event {event.get('event_id')}: engine UID unresolved "
                f"(aircraft_type={event.get('aircraft_type')!r}); skipping"
            )
            continue

        thrust_mode = str(event.get("thrust_mode") or "snap")
        if thrust_mode not in ("snap", "meem", "bffm2"):
            diagnostics.append(
                f"event {event.get('event_id')}: unknown thrust_mode "
                f"{thrust_mode!r}; treating as 'snap'"
            )
            thrust_mode = "snap"

        # Standalone treats 'meem' as 'snap' for engine-test events
        # because MEEM V1 at an ICAO anchor thrust setting (which is
        # what every engine-test mode is) reduces to the anchor's own
        # nvPM value. Log-log/linear interpolation at a knot returns
        # the knot. Gas-phase EIs are unaffected by MEEM V1. Result:
        # snap and meem produce byte-identical numbers here. No
        # diagnostic emitted; users legitimately choosing 'meem' get
        # the answer they expect. See the module docstring for the
        # future-work note if non-anchor thrust events are ever added.
        if thrust_mode == "meem":
            thrust_mode = "snap"

        # BFFM2 setup: pre-build the icao_eedb once per event (all four
        # modes for the resolved engine) and resolve meteo at event
        # midpoint. If any prerequisite is missing, fall back to snap
        # with a diagnostic — matches the plugin's behaviour of falling
        # through to base EI on BFFM2 failure.
        bffm2_ready = False
        bffm2_icao_eedb = None
        bffm2_meteo = None
        if thrust_mode == "bffm2":
            if conn is None:
                if not _bffm2_no_conn_logged:
                    diagnostics.append(
                        "bffm2 events present but conn=None; falling back "
                        "to snap for all bffm2 events this call. Pass conn "
                        "to compute_engine_test_for_period to enable BFFM2."
                    )
                    _bffm2_no_conn_logged = True
                thrust_mode = "snap"
            else:
                bffm2_icao_eedb = _build_icao_eedb_for_engine(engine_uid, ei_lookup)
                if bffm2_icao_eedb is None:
                    diagnostics.append(
                        f"event {event.get('event_id')}: bffm2 requested but "
                        f"engine {engine_uid!r} lacks a complete 4-mode "
                        "EI+FF anchor set; falling back to snap"
                    )
                    thrust_mode = "snap"
                else:
                    # Meteo lookup at event midpoint.
                    mid_dt = e_start + (e_end - e_start) / 2
                    mid_iso = mid_dt.strftime("%Y-%m-%d %H:%M:%S")
                    # Delegate to movements.get_meteo_at which reads
                    # tbl_InvMeteo with "<= runway_time" semantics and
                    # falls back to ISA if the table has no matching
                    # row. Import lazily to avoid the standalone runtime
                    # dependency for snap-only callers.
                    from openalaqs_standalone import movements as _mv

                    row = conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master "
                        "WHERE type='table' AND name='tbl_InvMeteo'"
                    ).fetchone()
                    if row[0] == 0 and not _bffm2_isa_fallback_logged:
                        diagnostics.append(
                            "bffm2 events present but tbl_InvMeteo not in "
                            "the DB; BFFM2 will fall back to ISA defaults. "
                            "Populate tbl_InvMeteo to get real ambient "
                            "corrections. This message is shown once per "
                            "call."
                        )
                        _bffm2_isa_fallback_logged = True
                        bffm2_meteo = dict(_mv.ISA_AMBIENT)
                    else:
                        try:
                            bffm2_meteo = _mv.get_meteo_at(conn, mid_iso, use_isa=False)
                            # Warn once if the returned meteo is ISA
                            # (meaning tbl_InvMeteo had no <= mid_iso
                            # row, get_meteo_at recursively fell back).
                            if (
                                bffm2_meteo.get("T_K") == 288.15
                                and bffm2_meteo.get("P_Pa") == 101325.0
                                and not _bffm2_isa_fallback_logged
                            ):
                                diagnostics.append(
                                    "bffm2 events present but tbl_InvMeteo "
                                    "has no data at or before their midpoint; "
                                    "BFFM2 will fall back to ISA defaults. "
                                    "This message is shown once per call."
                                )
                                _bffm2_isa_fallback_logged = True
                        except Exception as _exc:
                            diagnostics.append(
                                f"bffm2 meteo lookup failed ({_exc}); "
                                "falling back to snap for this event"
                            )
                            thrust_mode = "snap"

                    if thrust_mode == "bffm2":
                        bffm2_ready = True

        source_id = event.get("source_id")
        if source_id is None:
            continue
        totals = by_source.setdefault(source_id, {pol: 0.0 for pol in _POLLUTANTS})

        contributed = False
        for mode in _MODE_KEYS:
            t_mode_s = event.get(_MODE_TIME_COL[mode]) or 0
            try:
                t_mode_s = int(t_mode_s)
            except (TypeError, ValueError):
                t_mode_s = 0
            if t_mode_s <= 0:
                continue
            ei_row = ei_lookup.get((engine_uid, mode))
            if ei_row is None:
                diagnostics.append(
                    f"event {event.get('event_id')}: no EI for engine "
                    f"{engine_uid!r} mode {mode!r}; skipping this mode"
                )
                continue
            t_effective = t_mode_s * engine_count * fraction
            if bffm2_ready:
                _add_bffm2_ei_to_totals(
                    totals, ei_row, bffm2_icao_eedb, bffm2_meteo, t_effective
                )
            else:
                _add_ei_to_totals(totals, ei_row, t_effective)
            contributed = True

        if not contributed and source_id in by_source:
            # Roll back the empty entry so callers can iterate meaningfully.
            if all(v == 0.0 for v in by_source[source_id].values()):
                by_source.pop(source_id, None)

    return by_source


# ══════════════════════════════════════════════════════════════════════
# Orchestration wrapper — matches the compute_area_emissions signature
# so orchestrate.py can dispatch to it uniformly.
# ══════════════════════════════════════════════════════════════════════

# Pollutant name mapping: internal keys from compute_engine_test_for_period
# vs the standard `pollutant` column in emissions.parquet used by all
# other computes. "pm25" in the standard schema is the p2 sub-fraction
# (matches AREA_POLLUTANT_COLS in compute_area).
_POLLUTANT_INTERNAL_TO_STANDARD = {
    "co": "co",
    "hc": "hc",
    "nox": "nox",
    "sox": "sox",
    "pm10": "pm10",
    "p2": "pm25",
}


def _load_ei_lookup(conn: sqlite3.Connection) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Load default_aircraft_engine_ei into (engine_name, mode) → row-dict.

    Mirrors what the plugin's EngineStore does internally, but as a
    plain dict for the standalone path. Only the columns needed by
    _add_ei_to_totals are read; the SELECT explicitly lists them so
    a schema drift on unrelated columns doesn't break this.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT engine_name, mode, thrust, fuel_kg_sec, "
        "co_ei, hc_ei, nox_ei, sox_ei, pm10_ei, p1_ei, p2_ei, "
        "pm10_nonvol, pm10_sul, pm10_organic "
        "FROM default_aircraft_engine_ei"
    )
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in cur.fetchall():
        if row[0] is None or row[1] is None:
            # NULL engine_name or mode: unusable. The plugin's
            # SQLSerializable loader also drops these (they collide
            # on key='None' in its in-memory dict).
            continue
        out[(row[0], row[1])] = {
            "thrust": row[2],
            "fuel_kg_sec": row[3],
            "co_ei": row[4],
            "hc_ei": row[5],
            "nox_ei": row[6],
            "sox_ei": row[7],
            "pm10_ei": row[8],
            "p1_ei": row[9],
            "p2_ei": row[10],
            "pm10_nonvol": row[11],
            "pm10_sul": row[12],
            "pm10_organic": row[13],
        }
    return out


def _load_aircraft_lookup(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Load default_aircraft into icao → row-dict."""
    cur = conn.cursor()
    cur.execute("SELECT icao, engine_count, engine FROM default_aircraft")
    return {
        icao: {"engine_count": ec, "engine_uid": eng}
        for icao, ec, eng in cur.fetchall()
    }


def compute_engine_test_emissions(
    alaqs_path: "Path",
    year: int,
    pollutants: Optional[list] = None,
    time_window: Optional[Tuple[Any, Any]] = None,
):
    """Compute hourly engine-test emissions for all in-study test sites.

    Signature mirrors ``compute_area_emissions`` so ``orchestrate.py``
    can dispatch to it uniformly alongside road / parking / point /
    area. Returns a long-form DataFrame with columns
    ``[timestamp, source_id, pollutant, kg_in_hour]``.

    Only hours where an event actually overlaps produce rows. Zero-
    emission hours are omitted to keep the parquet compact, matching
    the convention of the other stationary computes (which also skip
    zero-emission source-pollutant-hour combinations).

    ``pollutants`` filters the output; unknown pollutants are silently
    dropped. Passing ``None`` uses the standard set (STATIONARY_POLLUTANTS
    intersected with the pollutants engine-test emits: co, hc, nox,
    sox, pm10, pm25).

    ``time_window = (start, end)`` restricts emissions to the half-open
    interval [start, end). Any event whose overlap window falls fully
    outside is skipped; partial overlaps are clipped hour-by-hour by
    the per-period compute (which already handles this via
    ``_period_window_fraction``).

    The ``year`` argument is only used to bracket a full-year scan when
    ``time_window`` is None; it doesn't force events to be re-dated.
    """
    import pandas as pd

    if pollutants is None:
        pollutants = ["co", "hc", "nox", "sox", "pm10", "pm25"]

    # Load DB pieces once
    conn = sqlite3.connect(str(alaqs_path))
    try:
        # Import lazily to avoid a hard dependency at module import time
        # (the plugin path never needs extract_engine_test_events).
        from openalaqs_standalone.extract_engine_test_events import (
            extract_engine_test_events,
        )

        events = extract_engine_test_events(conn)
        ei_lookup = _load_ei_lookup(conn)
        aircraft_lookup = _load_aircraft_lookup(conn)
    finally:
        conn.close()

    if not events:
        return pd.DataFrame(
            columns=["timestamp", "source_id", "pollutant", "kg_in_hour"]
        )

    # Determine the hour range to scan. If a time_window is given, use
    # it directly. Otherwise bracket the union of event windows AND
    # clamp to the inventory year — passing an event dated outside
    # `year` still emits its own overlapping hours (the compute doesn't
    # gate on year), but this keeps the scan bounded.
    if time_window is not None:
        scan_start, scan_end = time_window
        if isinstance(scan_start, str):
            scan_start = datetime.fromisoformat(scan_start)
        if isinstance(scan_end, str):
            scan_end = datetime.fromisoformat(scan_end)
    else:
        year_start = datetime(year, 1, 1)
        year_end = datetime(year + 1, 1, 1)
        scan_start, scan_end = year_start, year_end

    # Which hours actually have overlapping events? For each event,
    # compute the set of hour-buckets it touches; take the union.
    # Cheaper than looping 8760 empty hours.
    touched_hours: set = set()
    for ev in events:
        try:
            e_start = datetime.fromisoformat(ev["start_datetime"])
            e_end = datetime.fromisoformat(ev["end_datetime"])
        except (KeyError, ValueError, TypeError):
            continue
        # Clip to scan window
        e_start_clip = max(e_start, scan_start)
        e_end_clip = min(e_end, scan_end)
        if e_start_clip >= e_end_clip:
            continue
        # Enumerate the hour buckets [floor(start_hour), ceil(end_hour))
        h = e_start_clip.replace(minute=0, second=0, microsecond=0)
        while h < e_end_clip:
            touched_hours.add(h)
            h = h + timedelta(hours=1)

    if not touched_hours:
        return pd.DataFrame(
            columns=["timestamp", "source_id", "pollutant", "kg_in_hour"]
        )

    # Compute per-hour, per-source per-pollutant totals in grams,
    # convert to kg, emit long-form rows. Only hours with non-zero
    # contribution produce rows.
    ts_out: list = []
    sid_out: list = []
    pol_out: list = []
    kg_out: list = []

    pollutants_set = set(pollutants)
    # Filter the internal-to-standard map to only requested pollutants.
    active_map = {
        k: v for k, v in _POLLUTANT_INTERNAL_TO_STANDARD.items() if v in pollutants_set
    }

    for hour in sorted(touched_hours):
        by_source = compute_engine_test_for_period(
            events=events,
            period_start=hour,
            period_end=hour + timedelta(hours=1),
            ei_lookup=ei_lookup,
            aircraft_lookup=aircraft_lookup,
            conn=None,
        )
        for raw_source_id, totals in by_source.items():
            # Prefix with "engine_test:" to match extract_sources.py's
            # source_id convention (its rows in sources.parquet use
            # the same prefix).
            source_id = f"engine_test:{raw_source_id}"
            for internal_key, standard_key in active_map.items():
                grams = totals.get(internal_key, 0.0)
                if grams <= 0.0:
                    continue
                kg = grams / 1000.0
                ts_out.append(hour)
                sid_out.append(source_id)
                pol_out.append(standard_key)
                kg_out.append(kg)

    df = pd.DataFrame(
        {
            "timestamp": ts_out,
            "source_id": sid_out,
            "pollutant": pol_out,
            "kg_in_hour": kg_out,
        }
    )
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


__all__ = [
    "_period_window_fraction",
    "_resolve_engine_count",
    "_resolve_engine_uid",
    "compute_engine_test_for_period",
    "compute_engine_test_emissions",
]
