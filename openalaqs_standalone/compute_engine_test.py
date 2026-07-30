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
    for that mode, ``'meem'`` is not yet supported here and falls
    back to snap with a diagnostic (proper MEEM standalone port is
    a Phase 5 concern).
  * D5 one aircraft/engine per event: mixed run-ups appear as
    multiple events sharing source_id.
  * D10 interval-overlap: same strict ``<`` semantics.
"""

from __future__ import annotations

from datetime import datetime
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
      * ``co_ei_g_kg_fuel``, ``hc_ei_g_kg_fuel``, ``nox_ei_g_kg_fuel``,
        ``pm_ei_g_kg_fuel`` etc. (pollutant EI, grams per kilogram fuel).

    Matches Emission.add() in the plugin: fuel_burned = FF * t_effective;
    pollutant_g = EI[g_kg] * fuel_burned.
    """
    ff = ei_row.get("fuel_kg_sec")
    if ff is None:
        return
    fuel_burned = float(ff) * t_effective_s
    totals["fuel"] += fuel_burned

    _EI_KEY_MAP = {
        "co": "co_ei_g_kg_fuel",
        "co2": "co2_ei_g_kg_fuel",
        "hc": "hc_ei_g_kg_fuel",
        "nox": "nox_ei_g_kg_fuel",
        "sox": "sox_ei_g_kg_fuel",
        "pm10": "pm10_ei_g_kg_fuel",
        "p1": "p1_ei_g_kg_fuel",
        "p2": "p2_ei_g_kg_fuel",
        "pm10_nonvol": "pm10_nonvol_ei_g_kg_fuel",
        "pm10_sul": "pm10_sul_ei_g_kg_fuel",
        "pm10_organic": "pm10_organic_ei_g_kg_fuel",
    }
    for pol, ei_key in _EI_KEY_MAP.items():
        v = ei_row.get(ei_key)
        if v is None:
            continue
        # Emission mass in grams. Matches plugin convention.
        totals[pol] += float(v) * fuel_burned


def compute_engine_test_for_period(
    events: Iterable[Dict],
    period_start: datetime,
    period_end: datetime,
    ei_lookup: Dict[Tuple[str, str], Dict],
    aircraft_lookup: Dict,
    diagnostics: Optional[List[str]] = None,
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

    Returns
    -------
    dict keyed by ``source_id`` -> dict of totals per pollutant (grams,
    except ``"fuel"`` in kg). Same key set as ``_POLLUTANTS``. Sources
    with no contributions are omitted.
    """
    if diagnostics is None:
        diagnostics = []

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
        if thrust_mode not in ("snap", "meem"):
            diagnostics.append(
                f"event {event.get('event_id')}: unknown thrust_mode "
                f"{thrust_mode!r}; treating as 'snap'"
            )
            thrust_mode = "snap"

        # Standalone does not implement MEEM yet; fall back to snap.
        # Kept as an explicit diagnostic so callers know the coverage gap.
        if thrust_mode == "meem":
            diagnostics.append(
                f"event {event.get('event_id')}: meem thrust mode not "
                "implemented in standalone; falling back to snap"
            )

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
            _add_ei_to_totals(totals, ei_row, t_effective)
            contributed = True

        if not contributed and source_id in by_source:
            # Roll back the empty entry so callers can iterate meaningfully.
            if all(v == 0.0 for v in by_source[source_id].values()):
                by_source.pop(source_id, None)

    return by_source


__all__ = [
    "_period_window_fraction",
    "_resolve_engine_count",
    "_resolve_engine_uid",
    "compute_engine_test_for_period",
]
