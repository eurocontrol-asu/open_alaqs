"""
Source aggregation: merge multiple sources into a smaller number of
super-sources before writing AUSTAL inputs.

Why this exists: AUSTAL's DMNA reader has a fixed line buffer (a few
KB). With our standard layout (1 timestamp + 4 meteo + N iq columns +
N*M emission columns), the form line in series.dmna grows linearly
with N (sources) times M (pollutants). For 330 sources and 3
pollutants it's ~21 KB and AUSTAL refuses with "Buffer overflow in
line 1".

Aggregation strategies preserve total emitted mass per cell exactly,
since:
    annual_emitted(cell) = sum over sources of (annual_total_i * weight_i(cell))
                         = (sum of annual_total_i) * combined_weight(cell)
where combined_weight(cell) = sum(annual_total_i * weight_i(cell)) / sum(annual_total_i).

Hourly emission rates simply sum across constituents, so the time
series in the aggregated source equals the sum of constituent time
series. This is exact for time-invariant spatial distributions.

Per-pollutant spatial bias
--------------------------
The "by_type" strategy combines constituents weighted by their TOTAL
emission (sum across all pollutants). When constituents within a
group have heterogeneous pollutant compositions (e.g. a stack source
with zero NOx but non-zero HC), the combined spatial pattern is
biased: the zero-NOx constituent's geometry leaks into the NOx
spatial pattern via its non-NOx emission weight. When AUSTAL then
distributes the super-source's NOx mass over the combined pattern,
some NOx mass gets placed at the zero-NOx constituent's location.

The "by_type_per_pollutant" strategy fixes this. It produces one
sub-source per (group, pollutant) pair, with each sub-source's
spatial weights computed from ONLY the constituents that emit that
pollutant (weighted by THAT pollutant's emission). The total
super-source mass for any pollutant is preserved; the spatial
pattern for each pollutant is computed from only the emitters of
that pollutant.

Trade-off: per-pollutant produces N_groups * N_pollutants sub-sources
instead of N_groups. For typical airport inventories (4-5 groups, 6
pollutants), this is ~24-30 sub-sources, still well below the
"by_type"-was-introduced threshold of ~330 raw sources.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from austal_prep.spatial import CellWeights


def _group_key_by_type(source_id: str) -> str:
    """Split on ':' and take the prefix; if no colon, use the whole ID.

    Examples:
        "road:Rijksweg_A13_016" -> "road"
        "parking:ES.1"          -> "parking"
        "stack_42"              -> "stack_42"
    """
    if ":" in source_id:
        return source_id.split(":", 1)[0]
    return source_id


def _group_key_passthrough(source_id: str) -> str:
    """No-op grouping: each source stays in its own group."""
    return source_id


STRATEGY_FUNCTIONS: Dict[str, Callable[[str], str]] = {
    "none": _group_key_passthrough,
    "by_type": _group_key_by_type,
    # "by_type_per_pollutant" reuses the by_type grouping function but
    # is handled with a different aggregation code path that produces
    # per-pollutant sub-sources. See aggregate_sources.
    "by_type_per_pollutant": _group_key_by_type,
}


def _combine_cell_weights(
    constituents: List[Tuple[CellWeights, float]],
) -> CellWeights:
    """Merge a list of (CellWeights, annual_total_emission) pairs into
    one CellWeights, with per-cell weights equal to the
    emission-weighted average across constituents.

    The output's weights sum to 1.0 (renormalised after combining).
    The bbox is the union of constituent bboxes.
    """
    if not constituents:
        raise ValueError("Cannot combine zero constituents.")

    if len(constituents) == 1:
        # Pass through, no combining needed
        return constituents[0][0]

    total_emission = sum(e for _, e in constituents)
    if total_emission <= 0:
        # All constituents have zero annual emission; fall back to
        # uniform weighting so we still produce a usable cell pattern.
        equal_w = [(cw, 1.0) for cw, _ in constituents]
        return _combine_cell_weights(equal_w)

    # Accumulate per-cell weighted contributions in a dict keyed by
    # (i, j, k). Then renormalise.
    accum: Dict[Tuple[int, int, int], float] = {}
    bbox_xmin = float("inf")
    bbox_ymin = float("inf")
    bbox_xmax = float("-inf")
    bbox_ymax = float("-inf")

    for cw, e in constituents:
        if e <= 0:
            continue
        for (i, j, k), w in zip(cw.indices, cw.weights):
            key = (int(i), int(j), int(k))
            accum[key] = accum.get(key, 0.0) + e * float(w)

        bx0, by0, bx1, by1 = cw.bbox_metres
        bbox_xmin = min(bbox_xmin, bx0)
        bbox_ymin = min(bbox_ymin, by0)
        bbox_xmax = max(bbox_xmax, bx1)
        bbox_ymax = max(bbox_ymax, by1)

    if not accum:
        raise ValueError(
            "Combined cell weights are empty — all constituents had "
            "zero emission and zero geometry."
        )

    indices = np.array(list(accum.keys()), dtype=np.int32)
    weights = np.array(list(accum.values()), dtype=np.float64)
    weights /= weights.sum()  # renormalise to sum to 1.0

    return CellWeights(
        indices=indices,
        weights=weights,
        bbox_metres=(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax),
    )


def aggregate_sources(
    source_ids: List[str],
    cell_weights: Dict[str, CellWeights],
    rates: np.ndarray,
    strategy: str = "none",
    pollutants: Optional[List[str]] = None,
) -> Tuple[List[str], Dict[str, CellWeights], np.ndarray]:
    """Aggregate sources according to a grouping strategy.

    Parameters
    ----------
    source_ids
        List of source IDs in the order they appear in `rates`.
    cell_weights
        Mapping {source_id: CellWeights}. Must contain every entry in
        source_ids.
    rates
        Shape (n_hours, n_sources, n_pollutants) in g/s.
    strategy
        One of:
        - "none": pass-through. Returns inputs unchanged.
        - "by_type": group by the prefix before the first ':'. Spatial
          weights are combined using each constituent's TOTAL emission
          (sum across all pollutants) as the combining weight. Has a
          known per-pollutant bias when constituents within a group
          have heterogeneous pollutant compositions (see module
          docstring). Kept for backward compatibility.
        - "by_type_per_pollutant": group by the prefix before the
          first ':', then split each group into one sub-source per
          pollutant. Each sub-source's spatial weights are computed
          from only the constituents that emit that pollutant
          (weighted by THAT pollutant's emission). Sub-sources are
          named "<group>_<pollutant>". Their rates are zero for all
          pollutant columns except the one they represent. This is
          the spatially-correct per-pollutant strategy.
    pollutants
        List of pollutant names matching the last axis of `rates`.
        Required when strategy is "by_type_per_pollutant".

    Returns
    -------
    new_source_ids, new_cell_weights, new_rates
        The aggregated counterparts. Group IDs are sorted
        alphabetically; rates' source axis is in the same order as
        new_source_ids.
    """
    if strategy not in STRATEGY_FUNCTIONS:
        raise ValueError(
            f"Unknown aggregation strategy {strategy!r}. "
            f"Valid: {sorted(STRATEGY_FUNCTIONS)}"
        )
    if strategy == "none":
        return list(source_ids), dict(cell_weights), rates

    key_fn = STRATEGY_FUNCTIONS[strategy]

    # Build {group_id: list_of_constituent_indices_in_source_ids}
    groups: Dict[str, List[int]] = {}
    for s_idx, sid in enumerate(source_ids):
        gid = key_fn(sid)
        groups.setdefault(gid, []).append(s_idx)

    n_hours, _, n_pol = rates.shape

    if strategy == "by_type_per_pollutant":
        if pollutants is None:
            raise ValueError(
                "by_type_per_pollutant aggregation requires the "
                "`pollutants` argument so spatial weights can be "
                "computed per pollutant."
            )
        if len(pollutants) != n_pol:
            raise ValueError(
                f"pollutants ({len(pollutants)}) does not match "
                f"the rates' pollutant axis length ({n_pol})."
            )

        # Per-constituent per-pollutant annual emission (shape
        # (n_sources, n_pol)). Used as the spatial-combination weight
        # for the matching pollutant only.
        per_source_per_pol = rates.sum(axis=0)

        new_source_ids: List[str] = []
        new_cell_weights: Dict[str, CellWeights] = {}
        rates_columns: List[np.ndarray] = []

        for gid in sorted(groups.keys()):
            member_indices = groups[gid]
            for p_idx, pol in enumerate(pollutants):
                # Constituents weighted by THIS pollutant's emission
                # only. A constituent that emits zero of this
                # pollutant contributes nothing to the spatial
                # pattern and is excluded entirely.
                constituents = [
                    (
                        cell_weights[source_ids[src_idx]],
                        float(per_source_per_pol[src_idx, p_idx]),
                    )
                    for src_idx in member_indices
                    if per_source_per_pol[src_idx, p_idx] > 0.0
                ]
                if not constituents:
                    # No constituent in this group emits this
                    # pollutant — skip the sub-source entirely.
                    # Keeps the output compact and avoids zero
                    # sources downstream.
                    continue

                sub_sid = f"{gid}_{pol}"
                new_source_ids.append(sub_sid)
                new_cell_weights[sub_sid] = _combine_cell_weights(constituents)

                # Build the rate column for this sub-source. Only
                # the matching pollutant column is non-zero. This
                # mirrors the existing per-pollutant aircraft split
                # in runner.py — each sub-source carries ONLY its
                # assigned pollutant.
                rate_col = np.zeros((n_hours, n_pol), dtype=rates.dtype)
                for src_idx in member_indices:
                    rate_col[:, p_idx] += rates[:, src_idx, p_idx]
                rates_columns.append(rate_col)

        new_rates = np.zeros((n_hours, len(new_source_ids), n_pol), dtype=rates.dtype)
        for k, col in enumerate(rates_columns):
            new_rates[:, k, :] = col

        return new_source_ids, new_cell_weights, new_rates

    # strategy == "by_type" — legacy behaviour, kept for backward
    # compatibility. Has per-pollutant spatial bias when constituents
    # have heterogeneous pollutant compositions (see module docstring).
    new_source_ids = sorted(groups.keys())

    # Per-source annual totals (sum across hours and pollutants in g/s,
    # which is proportional to annual mass). Used as weights for the
    # spatial combination step.
    per_source_annual = rates.sum(axis=(0, 2))  # shape (n_sources,)

    new_rates = np.zeros((n_hours, len(new_source_ids), n_pol), dtype=rates.dtype)
    new_cell_weights = {}

    for new_idx, gid in enumerate(new_source_ids):
        member_indices = groups[gid]

        # Sum hourly rates across constituents
        for src_idx in member_indices:
            new_rates[:, new_idx, :] += rates[:, src_idx, :]

        # Combine spatial weights, weighted by each constituent's
        # annual total emission
        constituents = [
            (cell_weights[source_ids[src_idx]], float(per_source_annual[src_idx]))
            for src_idx in member_indices
        ]
        new_cell_weights[gid] = _combine_cell_weights(constituents)

    return new_source_ids, new_cell_weights, new_rates
