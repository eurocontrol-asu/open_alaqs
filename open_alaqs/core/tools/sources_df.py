"""
sources_df: build pandas DataFrames of stationary sources from the
plugin's already-populated Singleton stores.

This module is read-only and feeds the AUSTAL time-indexed writer. The Singleton-store
architecture already amortises every shape-table SQL hit to a single
SELECT at module init, so this module is NOT about reducing SQL: it
prepares a tabular layout that the AUSTAL writer can consume
with vectorised numpy ops (cell-weight × emission-factor products
over all sources of one type at once), mirroring the data shape that
`austal_prep` operates on internally.

What this module is and isn't
-----------------------------
- IS  a thin, read-only adapter that walks the populated source
       Singleton stores (RoadwaySourcesStore, ParkingSourcesStore,
       PointSourcesStore, AreaSourcesStore) and produces one
       `pd.DataFrame` per type, indexed by a `<type>:<id>` source key.
- IS  the convergence point for the source-id naming convention agreed
       in the plan: every row's index is `road:<id>`, `parking:<id>`,
       `point:<id>`, `area:<id>`. The bare `<id>` is preserved as a
       column so legacy callers that need it can read it back without
       having to split the prefix off.
- ISN'T a replacement for the Singleton stores. The stores remain
        authoritative for UI dialogs, the legacy time-major path, and
        anything that needs the Source instances themselves.
- ISN'T a SQL adapter. No database access lives here.

Schema (one row per source, columns common to all types)
--------------------------------------------------------
    source_id        str    `<type>:<bare_id>` — the DataFrame index
    type             str    one of {'road', 'parking', 'point', 'area'}
    bare_id          str    the raw id from the source's `_id` field
    geometry_wkt     str    WKT, possibly with embedded height
    height           float  metres
    hour_profile     str    profile name (resolves via UserHourProfileStore)
    daily_profile    str
    month_profile    str
    annual_units     float  `getUnitsPerYear()`, or `getOpsYear()` for point
    instudy          bool   True if the source is included in the run

Per-type pollutant columns (g per activity unit, source's native unit)
----------------------------------------------------------------------
    road    : co_gm_km, hc_gm_km, nox_gm_km, sox_gm_km, pm10_gm_km,
              p1_gm_km, p2_gm_km
    parking : co_gm_vh, hc_gm_vh, nox_gm_vh, sox_gm_vh, pm10_gm_vh,
              p1_gm_vh, p2_gm_vh
    point   : co_kg_k, hc_kg_k, nox_kg_k, sox_kg_k, pm10_kg_k,
              p1_kg_k, p2_kg_k
    area    : co_kg_unit, hc_kg_unit, nox_kg_unit, sox_kg_unit,
              pm10_kg_unit, p1_kg_unit, p2_kg_unit

The AUSTAL writer will use these column conventions to vectorise the EI ×
activity products that today live in each `*SourceModule.process()`
as a single `addGeneric(EI, activity, unit)` call.
"""
from __future__ import annotations
from typing import Dict, Iterable, Mapping, Optional

import pandas as pd

# Pollutant column suffixes per source type. Ordered for predictable
# DataFrame column layout. Sources whose DB row does not include a
# given pollutant column will produce a NaN here (preserved as 0.0
# downstream by the AUSTAL writer if needed).
_POLLUTANTS = ("co", "hc", "nox", "sox", "pm10", "p1", "p2")

__all__ = [
    "dataframe_from_sources",
    "build_sources_df",
    "pollutant_columns",
]

_TYPE_SCHEMA: Dict[str, Dict[str, str]] = {
    "road":    {"unit_suffix": "gm_km",   "annual_attr": "getUnitsPerYear"},
    "parking": {"unit_suffix": "gm_vh",   "annual_attr": "getUnitsPerYear"},
    "point":   {"unit_suffix": "kg_k",    "annual_attr": "getOpsYear"},
    "area":    {"unit_suffix": "kg_unit", "annual_attr": "getUnitsPerYear"},
}


def _emission_index_to_dict(source) -> Dict[str, float]:
    """Read the underlying numeric values from a Source's EmissionIndex
    in a stable order. EmissionIndex is a Store keyed by the original
    DB column name (e.g. 'nox_gm_km'); we just dereference its
    `getObjects()` and coerce to float so the row is well-typed."""
    ei = source.getEmissionIndex()
    if ei is None:
        return {}
    return {k: float(v) if v is not None else 0.0 for k, v in ei.getObjects().items()}


def _row_for_source(source, type_label: str, bare_id: str) -> Dict[str, object]:
    """Build a single DataFrame row dict from one Source instance.

    All values are read via the public Source API rather than the
    `_private` attributes, so this stays correct if a subclass
    overrides an accessor (e.g. PointSources' `getOpsYear`).
    """
    schema = _TYPE_SCHEMA[type_label]
    annual = float(getattr(source, schema["annual_attr"])() or 0.0)

    row: Dict[str, object] = {
        "source_id":     f"{type_label}:{bare_id}",
        "type":          type_label,
        "bare_id":       bare_id,
        "geometry_wkt":  source.getGeometryText() or "",
        "height":        float(source.getHeight() or 0.0),
        "hour_profile":  source.getHourProfile(),
        "daily_profile": source.getDailyProfile(),
        "month_profile": source.getMonthProfile(),
        "annual_units":  annual,
        "instudy":       bool(source.isInStudy()),
    }
    # Emission-factor columns are taken straight from the source's
    # EmissionIndex (already populated from the DB row at Source
    # construction time). Missing pollutants are not added here;
    # the DataFrame builder reindexes to the canonical pollutant set
    # afterwards, filling with 0.0 — matching the default_values=0.0
    # that EmissionIndex itself uses on construction.
    row.update(_emission_index_to_dict(source))
    return row


def dataframe_from_sources(
    sources: Mapping[str, object],
    type_label: str,
) -> pd.DataFrame:
    """Build a DataFrame from a `{bare_id: Source}` mapping.

    Parameters
    ----------
    sources
        Dict of source_id -> Source instance, exactly the shape
        returned by `SourceModule.getSources()`.
    type_label
        One of 'road', 'parking', 'point', 'area'. Used for the
        `<type>:<id>` source_id prefix and to pick the per-type
        pollutant unit suffix.

    Returns
    -------
    pd.DataFrame indexed by `source_id` (the `<type>:<bare_id>`
    string), preserving insertion order. Empty input → empty
    DataFrame with the common columns declared.
    """
    if type_label not in _TYPE_SCHEMA:
        raise ValueError(
            f"unknown type_label {type_label!r}; expected one of "
            f"{sorted(_TYPE_SCHEMA)}"
        )

    rows = [
        _row_for_source(src, type_label, bare_id)
        for bare_id, src in sources.items()
    ]

    if not rows:
        # Empty DataFrame still carries the common columns + the canonical
        # pollutant columns for the type so callers can `.empty` /
        # `.reindex` without special-casing.
        common = [
            "source_id", "type", "bare_id", "geometry_wkt", "height",
            "hour_profile", "daily_profile", "month_profile",
            "annual_units", "instudy",
        ]
        pollutants = list(pollutant_columns(type_label))
        return pd.DataFrame(columns=common + pollutants).set_index("source_id")

    df = pd.DataFrame(rows).set_index("source_id")

    # Reindex to guarantee every canonical pollutant column is present
    # for the type, filling missing values with 0.0 (matching the
    # default_values=0.0 used in EmissionIndex construction in each
    # Source subclass). This keeps AUSTAL writer callers free to iterate
    # `pollutant_columns(type_label)` without per-row presence checks.
    canonical = list(pollutant_columns(type_label))
    for col in canonical:
        if col not in df.columns:
            df[col] = 0.0
    df[canonical] = df[canonical].fillna(0.0)
    return df


def build_sources_df(
    modules: Mapping[str, object],
    type_label_by_module_name: Optional[Mapping[str, str]] = None,
) -> Dict[str, pd.DataFrame]:
    """walk a `{module_name: SourceModule}` mapping
    (the `_source_modules` dict of EmissionCalculation) and produce
    `{type_label: DataFrame}` for every stationary module present.

    Parameters
    ----------
    modules
        Mapping of module name to module instance. Typically
        `EmissionCalculation.getModules()`.
    type_label_by_module_name
        Optional mapping that overrides the default name-to-type
        resolution. Defaults to:
            'RoadwaySource'  -> 'road'
            'ParkingSource'  -> 'parking'
            'PointSource'    -> 'point'
            'AreaSource'     -> 'area'
        Modules whose name is not in this mapping are skipped (e.g.
        MovementSource).

    Returns
    -------
    `{type_label: DataFrame}`. Types whose module is absent or empty
    are omitted from the dict. Caller can rely on
    `result.get('road', pd.DataFrame())` for safe access.
    """
    if type_label_by_module_name is None:
        type_label_by_module_name = {
            "RoadwaySource": "road",
            "ParkingSource": "parking",
            "PointSource":   "point",
            "AreaSource":    "area",
        }

    out: Dict[str, pd.DataFrame] = {}
    for mod_name, mod_obj in modules.items():
        type_label = type_label_by_module_name.get(mod_name)
        if type_label is None:
            continue
        # Defensive: only consider stationary modules. The
        # MovementSource module has time_invariant_geometry=False, but
        # nothing stops a future module from sharing a type name; the
        # explicit flag is the source of truth.
        if not getattr(mod_obj, "time_invariant_geometry", False):
            continue
        sources = mod_obj.getSources()
        if not sources:
            continue
        out[type_label] = dataframe_from_sources(sources, type_label)
    return out


def pollutant_columns(type_label: str) -> Iterable[str]:
    """Return the list of pollutant column names for a given source
    type, in canonical order. Useful for AUSTAL writer callers that want to
    reindex the DataFrame to a known column layout before doing
    vector ops."""
    if type_label not in _TYPE_SCHEMA:
        raise ValueError(f"unknown type_label {type_label!r}")
    suffix = _TYPE_SCHEMA[type_label]["unit_suffix"]
    return tuple(f"{p}_{suffix}" for p in _POLLUTANTS)
