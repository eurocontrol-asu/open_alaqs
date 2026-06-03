"""
Top-level orchestrator: run_austal_prep.

Reads sources.parquet, emissions.parquet, the receptor CSV, and the
meteo CSV; runs the three pure layers (spatial distribution → emission
rates → writers); produces austal.txt + series.dmna + per-source grid
files in the output directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from austal_prep.aggregation import aggregate_sources
from austal_prep.config import AustalPrepReport, AustalStudyConfig
from austal_prep.io.loaders import load_emissions, load_sources
from austal_prep.io.meteo import (
    load_meteo,
    load_receptors,
    missing_meteo_hours,
)
from austal_prep.parallel import write_grids_parallel
from austal_prep.rates import (
    build_emission_rates_fast,
    per_source_pollutant_mask,
)
from austal_prep.spatial import build_spatial_distribution
from austal_prep.writers.austal_txt import write_austal_config
from austal_prep.writers.grid_files import (
    write_grid_per_hour_aircraft,
    write_grids_for_source,
)
from austal_prep.writers.series_dmna import write_series


def _derive_timestamps(
    emissions_df: pd.DataFrame,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[pd.Timestamp]:
    """Build a continuous hourly timeline for the AUSTAL run.

    The timeline drives THREE downstream consumers:
      - `build_emission_rates_fast` (sizes the rates ndarray; missing
         hours stay at zero, the writer's 1e-30 floor turns those into
         AUSTAL-acceptable near-zero rates).
      - `load_meteo` (returns AUSTAL-default sentinels for hours not
         in the meteo CSV: wd=999, ws=0, L=99999, mixing=800).
      - `write_series` (writes series.dmna with one row per timestamp;
         AUSTAL reads hghb=len(timestamps) and treats the rows as
         sequential hours t=1..hghb starting at the simulation epoch).

    The previous derivation (`sorted(emissions_df.timestamp.unique())`)
    had one concrete failure mode: when the emissions data had
    INTERNAL GAPS (an hour with no emission rows mid-window between
    two hours that do have rows), the gap-hour was silently dropped
    from the timestamp list. AUSTAL then ran fewer hours than the
    wall-clock span and printed
    `Quelle ist nicht definiert nach Stunde H` (source not valid
    after hour H) at the first uncovered hour, aborting the run.

    The fix closes that bug by filling every hour between the data's
    first and last emission timestamp. Missing rates are zero-filled
    by `build_emission_rates_fast`'s pivot; missing meteo hours get
    AUSTAL-default sentinels from `load_meteo`; the `1e-30` floor in
    `write_series` keeps AUSTAL from aborting on exact-zero rates.

    Bounds policy
    -------------
    Bounds are taken from `emissions_df.timestamp.min()..max()`, NOT
    from the user-supplied `start_dt`/`end_dt`. Rationale: the caller
    already FILTERS `emissions_df` against the window before reaching
    this function (runner.py lines 108-111), so the data's min/max
    already lie inside the window. Using data-derived bounds matches
    the plugin's AUSTAL behaviour exactly (the plugin sizes its
    simulation from the inventory's actual emission rows, not from
    an explicit user-side window). Bit-parity on training_v3 (51
    hours of dense emissions inside a 52-hour configured window)
    requires this matching choice.

    Sparse aircraft-only studies whose configured window extends
    BEYOND the data's last hour still see a shrunken simulation in
    this implementation -- the timeline runs only to data-max, not
    to end_dt. That's the plugin's behaviour and we deliberately
    mirror it. A future "honor window beyond data" mode could be
    added behind a flag if needed.

    `start_dt`/`end_dt` are accepted for signature compatibility but
    intentionally ignored. The caller filters emissions before calling.

    Parameters
    ----------
    emissions_df : DataFrame with a `timestamp` column (already filtered
        by start_dt/end_dt at the caller). Must be non-empty.
    start_dt, end_dt : retained for signature compatibility; ignored.

    Returns
    -------
    List of pandas Timestamps, hourly cadence, sorted ascending,
    spanning data.min() to data.max() inclusive.

    Notes
    -----
    Requires hourly cadence in the input data and produces hourly
    timestamps. Sub-hourly emissions parquets are not supported by
    AUSTAL anyway (it expects one rate per source per hour); upstream
    aggregation should already have rolled sub-hourly bins up.
    """
    # The runner clears emissions_df early with a clearer error;
    # this is a defensive guard.
    if emissions_df.empty or emissions_df["timestamp"].empty:
        raise ValueError(
            "_derive_timestamps called with empty emissions_df; "
            "caller should have raised before this point."
        )

    ts = emissions_df["timestamp"]
    lo = pd.Timestamp(ts.min())
    hi = pd.Timestamp(ts.max())

    if lo > hi:
        raise ValueError(f"timestamp window has start > end: {lo} > {hi}")

    # `freq='h'` is the modern pandas alias (lowercase). 'H' raises a
    # FutureWarning since pandas 2.2.
    rng = pd.date_range(start=lo, end=hi, freq="h")
    return list(rng)


def run_austal_prep(
    sources_parquet: Path,
    emissions_parquet: Path,
    receptor_csv: Path,
    meteo_csv: Path,
    output_dir: Path,
    study_config: AustalStudyConfig,
    *,
    selected_pollutants: Optional[List[str]] = None,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    processes: Optional[int] = None,
) -> AustalPrepReport:
    """Generate AUSTAL input files in output_dir.

    sources_parquet, emissions_parquet: cross-project schema produced
        by `openalaqs_standalone` (`extract_sources.py` writes the
        sources side; `inventory_gpkg.py` writes the emissions side).
    receptor_csv: columns name, x, y, z (absolute UTM metres + m AGL).
    meteo_csv: columns timestamp, wind_direction_deg, wind_speed_ms,
        obukhov_length_m, mixing_height_m (last optional).
    output_dir: directory to populate. Will be created if missing.
        Existing files in this directory are NOT removed; a clean
        directory is the caller's responsibility.

    selected_pollutants: optional whitelist. Defaults to all pollutants
        present in emissions.parquet.
    start_dt, end_dt: optional time-window restriction. Defaults to
        the full span found in emissions.parquet.

    Aircraft super-source per-pollutant split (hybrid mode only)
    ------------------------------------------------------------
    AUSTAL applies one spatial dmna per source to ALL of that source's
    pollutants. The aircraft super-source aggregates many per-cell
    sources whose pollutant compositions vary by aircraft mode
    (taxi-rich in CO/HC, climb-rich in NOx), so a single shared dmna
    would bias per-pollutant spatial output. The orchestrator splits
    the aircraft super-source into one sub-source per pollutant
    (`aircraft_nox`, `aircraft_co`, ...), each carrying only that
    pollutant's mass and spatial pattern. Stationary sources are
    unaffected since their per-cell pollutant ratios are constant
    (same geometry for every pollutant). Mirrors the plugin's
    per-pollutant bundle structure.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load sources, reproject to grid CRS and translate to ref ----
    sources = load_sources(
        sources_parquet,
        target_utm_epsg=study_config.grid.utm_epsg,
        source_epsg=3857,
        reference_x=study_config.grid.reference_x,
        reference_y=study_config.grid.reference_y,
    )

    # ---- Load emissions ----
    emissions_df = load_emissions(
        emissions_parquet,
        source_ids=set(sources.keys()),
        pollutants=set(selected_pollutants) if selected_pollutants else None,
    )
    if emissions_df.empty:
        raise ValueError(
            "No emissions data after filtering by sources/pollutants. "
            "Check that source_ids in sources.parquet match those in "
            "emissions.parquet."
        )

    # ---- Determine timestamps and pollutants ----
    emissions_df["timestamp"] = pd.to_datetime(emissions_df["timestamp"])
    if start_dt is not None:
        emissions_df = emissions_df[emissions_df["timestamp"] >= pd.Timestamp(start_dt)]
    if end_dt is not None:
        emissions_df = emissions_df[emissions_df["timestamp"] <= pd.Timestamp(end_dt)]

    if emissions_df.empty:
        raise ValueError("No emissions data in the requested time window.")

    timestamps = _derive_timestamps(emissions_df, start_dt, end_dt)
    if selected_pollutants is None:
        pollutants = sorted(set(emissions_df["pollutant"]))
    else:
        pollutants = list(selected_pollutants)

    # ---- Determine source ordering (deterministic) ----
    # Sources with no emissions in the window are dropped here so we
    # don't write empty grid files. Track them for the report.
    emitting_sources = set(emissions_df["source_id"].unique())
    sources_skipped_no_emissions = sorted(set(sources.keys()) - emitting_sources)
    source_ids = sorted(s for s in sources.keys() if s in emitting_sources)

    # ---- Layer 1: spatial distribution (runs once) ----
    sd_input = {sid: sources[sid] for sid in source_ids}
    cell_weights = build_spatial_distribution(sd_input, study_config.grid)
    sources_skipped_no_geometry = sorted(set(source_ids) - set(cell_weights.keys()))
    # Drop sources that had no overlap with the grid
    source_ids = [s for s in source_ids if s in cell_weights]

    if not source_ids:
        raise ValueError(
            "No sources remained after spatial distribution. "
            "All input sources fell outside the grid extent or had "
            "empty geometries."
        )

    # ---- Layer 2: emission rates → 3D array ----
    rates = build_emission_rates_fast(emissions_df, source_ids, pollutants, timestamps)

    # ---- Optional source aggregation ----
    # Collapse multiple input sources into super-sources before
    # writing AUSTAL files. Required when the input source count
    # exceeds AUSTAL's series.dmna form-line buffer (~100 sources
    # depending on pollutant count).
    n_sources_before_aggregation = len(source_ids)
    source_ids, cell_weights, rates = aggregate_sources(
        source_ids=source_ids,
        cell_weights=cell_weights,
        rates=rates,
        strategy=study_config.source_aggregation,
        pollutants=pollutants,
    )

    emit_mask = per_source_pollutant_mask(rates)

    # ---- Per-pollutant aircraft expansion (hybrid mode only) ----
    # See module docstring "Aircraft super-source per-pollutant split"
    # for the rationale. Replaces the single "aircraft" entry in
    # source_ids with one entry per pollutant ("aircraft_nox",
    # "aircraft_co", ...). Each sub-source carries only its own
    # pollutant's rate (other pollutant columns are zeroed) and gets
    # its own spatial dmna built downstream from that pollutant's
    # mass distribution.
    #
    # Only applied in hybrid mode: in time_indexed mode the aircraft
    # spatial pattern is the geometry-derived annual aggregate (same
    # for every pollutant by construction), so no bias to correct.
    #
    # Naturally skipped when source_aggregation = "by_type_per_pollutant"
    # because that strategy already produces per-pollutant sub-sources
    # ("aircraft_nox", "aircraft_co", ...) directly, with the additional
    # benefit of using per-pollutant spatial weights (this block uses
    # SHARED weights, which is the legacy bias). The "aircraft in
    # source_ids" check below evaluates False after per-pollutant
    # aggregation and the block is a no-op. Kept here so that legacy
    # source_aggregation = "by_type" still produces a workable (if
    # biased) split for aircraft.
    if study_config.grid_writer_mode == "hybrid" and "aircraft" in source_ids:
        ac_idx = source_ids.index("aircraft")
        n_pol = len(pollutants)

        # Expand source_ids in place: replace "aircraft" with one
        # entry per pollutant, preserving surrounding ordering.
        new_source_ids: List[str] = (
            source_ids[:ac_idx]
            + [f"aircraft_{p}" for p in pollutants]
            + source_ids[ac_idx + 1 :]
        )

        # Expand rates: each aircraft sub-source carries only its
        # own pollutant column; non-matching pollutant columns are
        # zero. Shape grows from (n_hours, n_src, n_pol) to
        # (n_hours, n_src + n_pol - 1, n_pol).
        new_n_src = len(new_source_ids)
        new_rates = np.zeros((len(timestamps), new_n_src, n_pol), dtype=rates.dtype)
        new_rates[:, :ac_idx, :] = rates[:, :ac_idx, :]
        new_rates[:, ac_idx + n_pol :, :] = rates[:, ac_idx + 1 :, :]
        for p_i in range(n_pol):
            new_rates[:, ac_idx + p_i, p_i] = rates[:, ac_idx, p_i]

        # Share the aggregated aircraft cell_weights across every
        # sub-source. Only the receptor-capping centroid loop reads
        # cell_weights for non-stationary sources, and it just sums
        # weighted centres - sharing the same CellWeights object is
        # safe (read-only) and preserves the original aircraft
        # contribution to the centroid (sum of sub-source weights
        # by per_source_mass equals the original aircraft total).
        ac_cw = cell_weights.pop("aircraft", None)
        if ac_cw is not None:
            for p in pollutants:
                cell_weights[f"aircraft_{p}"] = ac_cw

        source_ids = new_source_ids
        rates = new_rates
        emit_mask = per_source_pollutant_mask(rates)

    # Set of aircraft sub-source names used by the grid dispatch and
    # the per_source_legacy flag construction below. Empty when not
    # in hybrid mode or when there are no aircraft sources.
    aircraft_sub_sources: dict = (
        {f"aircraft_{p}": p for p in pollutants}
        if (
            study_config.grid_writer_mode == "hybrid"
            and any(sid.startswith("aircraft_") for sid in source_ids)
        )
        else {}
    )

    # ---- Receptors ----
    rx, ry, rz = load_receptors(
        receptor_csv,
        reference_x=study_config.grid.reference_x,
        reference_y=study_config.grid.reference_y,
    )
    n_receptors_total = len(rx)

    # AUSTAL has a hard internal cap on the number of receptors. If
    # exceeded, AUSTAL either silently truncates or rejects the input.
    # Cap the receptor list ourselves and keep the receptors closest to
    # the source-emission centroid (weighted by total emitted mass over
    # the period).
    rx, ry, rz = _cap_receptors(
        rx,
        ry,
        rz,
        max_receptors=study_config.max_receptors,
        cell_weights=cell_weights,
        source_ids=source_ids,
        rates=rates,
        grid=study_config.grid,
    )
    n_receptors_kept = len(rx)
    receptors = {"xp": rx, "yp": ry, "hp": rz}

    # ---- Meteo ----
    missing_hours = missing_meteo_hours(meteo_csv, timestamps)
    meteo = load_meteo(
        meteo_csv,
        timestamps,
        mixing_height_included=study_config.mixing_height_included,
    )

    # ---- Layer 3: writers ----
    write_austal_config(
        out_path=output_dir / "austal.txt",
        study=study_config,
        source_ids=source_ids,
        pollutants=pollutants,
        receptors=receptors,
        source_emits_pollutant=emit_mask,
    )

    # In "hybrid" mode, aircraft sub-sources use per-hour spatial
    # dmnas (legacy iq scheme); other sources stay time_indexed.
    # Build the per-source iq selector once and reuse it for both
    # series.dmna and the grid file dispatch below.
    if study_config.grid_writer_mode == "hybrid":
        per_source_legacy = [sid in aircraft_sub_sources for sid in source_ids]
    else:
        per_source_legacy = None

    write_series(
        out_path=output_dir / "series.dmna",
        timestamps=timestamps,
        meteo=meteo,
        emission_rates=rates,
        source_ids=source_ids,
        pollutants=pollutants,
        source_emits_pollutant=emit_mask,
        mixing_height_included=study_config.mixing_height_included,
        grid_writer_mode=study_config.grid_writer_mode,
        pm10_fine_fraction=study_config.pm10_fine_fraction,
        per_source_legacy=per_source_legacy,
    )

    # Per-source grid files. Source dir index is 1-based, 2-digit
    # zero-padded ("01", "02", ...) matching the reference layout.
    # Each source's writes are independent of every other source's,
    # so when `processes` > 1 the loop runs across a process pool.
    # Output is byte-for-byte identical to the serial path; see
    # austal_prep/parallel.py for the parity guarantee.
    if study_config.grid_writer_mode == "hybrid":
        # Per-source dispatch: each aircraft sub-source gets per-hour
        # spatial files filtered to its own pollutant (reads
        # pre-aggregation emissions_df for cell-level data); other
        # sources use time_indexed single-file mode.
        n_grid_files = 0
        for s_idx, sid in enumerate(source_ids):
            if sid in aircraft_sub_sources:
                pollutant = aircraft_sub_sources[sid]
                ac_em = emissions_df[
                    emissions_df["source_id"].str.startswith("aircraft:cell:")
                    & (emissions_df["pollutant"] == pollutant)
                ]
                n_grid_files += write_grid_per_hour_aircraft(
                    out_dir=output_dir,
                    source_dir_index=s_idx + 1,
                    aircraft_emissions_df=ac_em,
                    timestamps=timestamps,
                    grid=study_config.grid,
                    source_offset_cells=study_config.source_offset_cells,
                    processes=processes,
                    pollutant=pollutant,
                )
            else:
                n_grid_files += write_grids_for_source(
                    out_dir=output_dir,
                    source_dir_index=s_idx + 1,
                    timestamps=timestamps,
                    weights=cell_weights[sid],
                    grid=study_config.grid,
                    mode="time_indexed",
                    source_offset_cells=study_config.source_offset_cells,
                )
    elif processes is not None and processes != 1:
        n_grid_files = write_grids_parallel(
            out_dir=output_dir,
            source_ids=source_ids,
            timestamps=timestamps,
            cell_weights=cell_weights,
            grid=study_config.grid,
            mode=study_config.grid_writer_mode,
            source_offset_cells=study_config.source_offset_cells,
            processes=processes,
        )
    else:
        n_grid_files = 0
        for s_idx, sid in enumerate(source_ids):
            n_grid_files += write_grids_for_source(
                out_dir=output_dir,
                source_dir_index=s_idx + 1,
                timestamps=timestamps,
                weights=cell_weights[sid],
                grid=study_config.grid,
                mode=study_config.grid_writer_mode,
                source_offset_cells=study_config.source_offset_cells,
            )

    return AustalPrepReport(
        n_sources=len(source_ids),
        n_hours=len(timestamps),
        n_pollutants=len(pollutants),
        n_grid_files_written=n_grid_files,
        output_dir=output_dir,
        missing_meteo_hours=missing_hours,
        sources_skipped_no_geometry=sources_skipped_no_geometry,
        sources_skipped_no_emissions=sources_skipped_no_emissions,
        pollutants_used=pollutants,
        n_receptors_total=n_receptors_total,
        n_receptors_kept=n_receptors_kept,
        n_sources_before_aggregation=n_sources_before_aggregation,
        aggregation_strategy=study_config.source_aggregation,
    )


def _cap_receptors(
    rx: List[float],
    ry: List[float],
    rz: List[float],
    *,
    max_receptors: Optional[int],
    cell_weights: dict,
    source_ids: List[str],
    rates: np.ndarray,
    grid,
) -> tuple:
    """Trim the receptor list to at most max_receptors entries, keeping
    those closest to the emission-weighted source centroid.

    If max_receptors is None or the list is already within the cap, the
    inputs are returned unchanged.
    """
    n = len(rx)
    if max_receptors is None or n <= max_receptors:
        return rx, ry, rz

    # Compute per-source total emitted mass across all hours and
    # pollutants. Shape of rates is (n_hours, n_sources, n_pollutants).
    # axis=(0, 2) sums across hours and pollutants. Result is (n_sources,)
    # in g/s units; we want a relative weight so units cancel.
    per_source_mass = rates.sum(axis=(0, 2))  # (n_sources,)
    total_mass = per_source_mass.sum()
    if total_mass <= 0:
        # Fall back to uniform weights if there's nothing to weight by.
        per_source_mass = np.ones_like(per_source_mass)
        total_mass = per_source_mass.sum()

    # Centroid of each source's spatial distribution, in calc-grid
    # frame metres. Weight by per-source emitted mass.
    centroid_x = 0.0
    centroid_y = 0.0
    for s_idx, sid in enumerate(source_ids):
        cw = cell_weights.get(sid)
        if cw is None or cw.weights.size == 0:
            continue
        # cw.indices is (M, 3) with (i, j, k) calc-frame cell indices.
        # Cell centre absolute coord = x0 + (i + 0.5)*dd.
        cx = grid.x0 + (cw.indices[:, 0] + 0.5) * grid.dd
        cy = grid.y0 + (cw.indices[:, 1] + 0.5) * grid.dd
        # Weighted mean of cell centres for this source.
        sx = float((cx * cw.weights).sum())
        sy = float((cy * cw.weights).sum())
        w = per_source_mass[s_idx] / total_mass
        centroid_x += sx * w
        centroid_y += sy * w

    rx_arr = np.asarray(rx, dtype=np.float64)
    ry_arr = np.asarray(ry, dtype=np.float64)
    rz_arr = np.asarray(rz, dtype=np.float64)

    # Distance from each receptor to the emission-weighted centroid
    # (both in calc-grid frame metres).
    dist2 = (rx_arr - centroid_x) ** 2 + (ry_arr - centroid_y) ** 2
    keep_idx = np.argsort(dist2)[:max_receptors]
    keep_idx.sort()  # preserve original ordering for stability

    return (
        rx_arr[keep_idx].tolist(),
        ry_arr[keep_idx].tolist(),
        rz_arr[keep_idx].tolist(),
    )
