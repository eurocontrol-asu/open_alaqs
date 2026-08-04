"""
orchestrate: end-to-end pipeline that takes an .alaqs file plus
optional meteo/receptor inputs and produces the six folder structure
expected by the `austal_prep` package.

Output layout:
    <output_root>/
    ├── sources_folder/
    │   └── sources.parquet
    ├── emissions_folder/
    │   └── emissions.parquet
    ├── receptors_folder/
    │   └── receptors.csv
    ├── meteo_folder/
    │   └── meteo.csv
    ├── config_folder/
    │   └── config.json
    └── austal_folder/         (empty; populated by the recipe)

Steps:
    1. extract_sources  .alaqs -> sources.parquet
    2. compute_road     .alaqs -> road emissions
    3. compute_parking  .alaqs -> parking emissions
       (concatenate to a single emissions.parquet)
    4. adapt_meteo      .alaqs (or external CSV) -> meteo.csv
    5. adapt_receptors  external CSV -> receptors.csv
    6. make_config      .alaqs -> config.json

Steps 4 and 5 require external inputs; they're optional. Steps 1-3
and 6 are derived entirely from the .alaqs file.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from pyproj import Transformer

# Aircraft pipeline, used only when include_aircraft is requested.
from openalaqs_standalone import austal_aircraft as _aa
from openalaqs_standalone import compute_movements as _cm
from openalaqs_standalone import movements as _mv
from openalaqs_standalone._profiles import STATIONARY_POLLUTANTS
from openalaqs_standalone.adapt_meteo import adapt_meteo
from openalaqs_standalone.adapt_receptors import adapt_receptors
from openalaqs_standalone.compute_area import compute_area_emissions
from openalaqs_standalone.compute_engine_test import compute_engine_test_emissions
from openalaqs_standalone.compute_parking import compute_parking_emissions
from openalaqs_standalone.compute_point import compute_point_emissions
from openalaqs_standalone.compute_road import compute_road_emissions
from openalaqs_standalone.extract_sources import extract_sources
from openalaqs_standalone.make_config import (
    _airport_metadata,
    _utm_zone_for_lon,
    make_config,
)


def _build_aircraft_tables(
    alaqs_path: Path,
    method: str,
    pollutants: list[str],
    time_window: tuple | None = None,
    processes: int = 1,
    use_isa_meteo: bool = False,
    source_dynamics: str = "none",
    apply_nox_corrections: bool = False,
) -> tuple:
    """Compute the aircraft emissions and return the austal table pair.

    Runs the movement compute, grids the result, and builds the
    per-grid-cell `sources` and `emissions` DataFrames via
    `austal_aircraft.build_aircraft_austal_tables`. The emissions are
    then filtered to `pollutants`, so the combined emissions.parquet
    carries one consistent pollutant set across stationary and
    aircraft rows.

    `time_window`, when given, applies the dispersion-correct filter:
    movements are restricted to those whose start time
    (`block_time` for departures, `runway_time` for arrivals) is in
    the window, AND the per-bucket emissions of those movements are
    also clipped to the window. The combination is exactly what an
    AUSTAL run over the window needs: only emissions that physically
    occur in the window enter the dispersion calculation.

    `processes > 1` runs the parallel movement driver (a drop-in
    replacement for the serial one, results bit-identical). `1` runs
    the serial driver. Stationary computes are not affected by
    `processes` -- they are already numpy-vectorised.

    `use_isa_meteo` defaults to False: BFFM2 ambient corrections are
    driven by `tbl_InvMeteo` per inventory period (with fallback to
    ISA when a period is missing), matching the QGIS plugin's
    behaviour. Set to True only to force ISA for backward compatibility
    with older standalone runs that ignored loaded meteo. No effect
    when `method='bymode'` or for helicopter movements.

    Returns (aircraft_sources_df, aircraft_emissions_df). Both are
    empty (with the right columns) if the study has no movements or
    if the window leaves no movement.
    """
    conn = _mv.connect(str(alaqs_path))
    try:
        # Movement oids to compute. If a time window is set, restrict
        # to the direction-aware in-window movements; otherwise leave
        # oids None to let the driver compute the whole study.
        if time_window is not None:
            _start, _end = time_window
            oids = _mv.get_movement_oids_in_window(conn, _start, _end)
        else:
            oids = None

        if processes and processes > 1:
            # The parallel driver opens its own connections, so the
            # current `conn` is not passed in; alaqs_path goes in
            # instead.
            from openalaqs_standalone import parallel as _par

            results = _par.compute_all_movements_parallel(
                str(alaqs_path),
                method=method,
                oids=oids,
                processes=processes,
                use_isa_meteo=use_isa_meteo,
                apply_nox_corrections=apply_nox_corrections,
            )
        else:
            results = _cm.compute_all_movements(
                conn,
                method=method,
                oids=oids,
                use_isa_meteo=use_isa_meteo,
                apply_nox_corrections=apply_nox_corrections,
            )

        ctx = _cm.build_context(conn)
        grid_definition = _mv.get_grid_definition(conn)
        emissions_df, sources_df = _aa.build_aircraft_austal_tables(
            results,
            conn,
            ctx["grid_bounds"],
            grid_definition,
            time_window=time_window,
            source_dynamics=source_dynamics,
        )
    finally:
        conn.close()

    # Keep only the requested pollutants, so the combined
    # emissions.parquet is coherent with the stationary rows. The
    # aircraft core always produces its full six-pollutant set
    # (co, co2, hc, nox, sox, pm10); the stationary computes produce
    # only what was asked for. Filtering the aircraft emissions to
    # the same `pollutants` list keeps one consistent pollutant set
    # across stationary and aircraft rows. Note co2 has no stationary
    # counterpart at all, so it is dropped here unless explicitly
    # requested.
    if len(emissions_df) > 0:
        wanted = set(pollutants)
        emissions_df = emissions_df[emissions_df["pollutant"].isin(wanted)].reset_index(
            drop=True
        )

    return sources_df, emissions_df, results


def orchestrate(
    alaqs_path: Path,
    output_root: Path,
    year: int,
    pollutants: list[str] | None = None,
    meteo_input: Path | None = None,
    meteo_year_shift: int | None = None,
    receptor_input: Path | None = None,
    receptor_source_epsg: int | None = None,
    receptor_target_epsg: int | None = None,
    receptor_name_col: str | None = None,
    receptor_x_col: str | None = None,
    receptor_y_col: str | None = None,
    title: str | None = None,
    grid_size: int = 75,
    grid_step_m: float = 250.0,
    qs: int = 3,
    include_aircraft: bool = False,
    aircraft_method: str = "bymode",
    use_isa_meteo: bool = False,
    start: "datetime | None" = None,
    end: "datetime | None" = None,
    processes: int = 1,
    grid_writer_mode: str = "hybrid",
    source_dynamics: str = "none",
    apply_nox_corrections: bool = False,
) -> dict:
    """Build all six input folders. Returns a dict of {step: count}.

    When `include_aircraft` is True, the aircraft movement emissions
    are computed and folded into the same `sources.parquet` and
    `emissions.parquet` as the stationary sources, so a single
    austal_prep run covers the whole study. Each occupied inventory
    grid cell becomes a synthetic `aircraft:cell:<ix>_<iy>` area
    source (see `austal_aircraft`). In that mode the stationary gate
    stub is skipped: gate (GSE/GPU) emissions come from the movement
    path instead, where they are driven by the actual movements.
    `aircraft_method` selects the emission method (bymode,
    bffm2_anchor, bffm2_traj) and is ignored when include_aircraft is
    False.
    """
    if pollutants is None:
        pollutants = list(STATIONARY_POLLUTANTS)

    # Validate the time window. Both ends, when given, must lie inside
    # the inventory year's hour span [year-01-01 00:00, year+1-01-01).
    # `start < end` is required; equal bounds would produce an empty
    # output and is more likely a typo than intent.
    from datetime import datetime as _dt

    year_start = _dt(year, 1, 1)
    year_end = _dt(year + 1, 1, 1)
    if start is not None:
        if not (year_start <= start < year_end):
            raise ValueError(
                f"start={start!r} is outside the inventory year "
                f"[{year_start}, {year_end})"
            )
    if end is not None:
        if not (year_start < end <= year_end):
            raise ValueError(
                f"end={end!r} is outside the inventory year "
                f"({year_start}, {year_end}]"
            )
    if start is not None and end is not None and not (start < end):
        raise ValueError(f"start={start} must be strictly < end={end}")

    # The effective time window passed to each compute. None means
    # full-year, which all the computes treat as no-op (mask is
    # all-True, no slicing).
    time_window = (start, end) if (start is not None or end is not None) else None

    output_root.mkdir(parents=True, exist_ok=True)
    sources_folder = output_root / "sources_folder"
    emissions_folder = output_root / "emissions_folder"
    receptors_folder = output_root / "receptors_folder"
    meteo_folder = output_root / "meteo_folder"
    config_folder = output_root / "config_folder"
    austal_folder = output_root / "austal_folder"
    for f in (
        sources_folder,
        emissions_folder,
        receptors_folder,
        meteo_folder,
        config_folder,
        austal_folder,
    ):
        f.mkdir(parents=True, exist_ok=True)

    summary: dict = {}

    # Log the active time window so the user can see what's
    # included. Full-year runs say nothing, to avoid noise.
    if time_window is not None:
        _ws, _we = time_window
        _year_hours = (
            8784 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 8760
        )
        ws = _ws if _ws is not None else _dt(year, 1, 1)
        we = _we if _we is not None else _dt(year + 1, 1, 1)
        win_hours = int((we - ws).total_seconds() // 3600)
        print(
            f"  time window: {ws.isoformat()} to {we.isoformat()} "
            f"({win_hours} hours, {100 * win_hours / _year_hours:.2f}% of year)"
        )
        summary["time_window"] = {
            "start": ws.isoformat(),
            "end": we.isoformat(),
            "hours": win_hours,
        }
    if processes and processes > 1:
        print(f"  processes: {processes} (parallel aircraft compute)")

    # 1. Sources
    sources_path = sources_folder / "sources.parquet"
    sources_df = extract_sources(alaqs_path, sources_path)
    summary["sources"] = len(sources_df)
    if sources_df.empty or "source_type" not in sources_df.columns:
        # All stationary source tables were missing or empty. The
        # extract step prints one warning per missing table; we add a
        # consolidated note here. Aircraft cell sources may still get
        # appended below (when include_aircraft is set), so this is
        # not necessarily fatal -- but in practice an .alaqs missing
        # every shapes_* table is almost always corrupt or empty,
        # and downstream steps (aircraft compute, meteo, grid) will
        # also fail. Surface that possibility to the user.
        print(
            "  sources.parquet: 0 stationary sources "
            "(all shapes_* tables missing or empty; "
            ".alaqs may be corrupt or empty)"
        )
    else:
        print(
            f"  sources.parquet: {len(sources_df)} stationary sources "
            f"({dict(sources_df.source_type.value_counts())})"
        )

    # 2 + 3 + 4 + 5. Emissions: concatenate the stationary source
    # types.
    #
    # Gate emissions are NOT computed here. They are a movement-driven
    # quantity, not a stationary spread, so they come from the
    # aircraft pipeline (see `compute_gate_movements`, folded into the
    # movement totals) when include_aircraft is set. A study with no
    # movements has no gate activity and therefore no gate emissions.
    # Either way there is no stationary gate compute to call. The gate
    # geometries still appear in sources.parquet -- extract_sources
    # always reads shapes_gates -- and in include_aircraft mode they
    # are simply sources that carry no stationary emission, which
    # austal_prep tolerates.
    stationary_computes = [
        (compute_road_emissions, "road"),
        (compute_parking_emissions, "parking"),
        (compute_point_emissions, "point"),
        (compute_area_emissions, "area"),
        # Engine-test sites are area-source polygons in the DB but their
        # emissions come from per-event records in engine_test_events,
        # not from the *_kg_unit rates. compute_engine_test_emissions
        # produces the same long-form (timestamp, source_id, pollutant,
        # kg_in_hour) schema and emits only hours with actual event
        # overlap, so a study with zero test sites or no events adds
        # zero rows here.
        (compute_engine_test_emissions, "engine_test"),
    ]

    em_chunks: list[pd.DataFrame] = []
    by_type_summary: dict[str, int] = {}
    for compute_fn, label in stationary_computes:
        df = compute_fn(alaqs_path, year, pollutants, time_window=time_window)
        n = len(df)
        by_type_summary[label] = n
        if n > 0:
            em_chunks.append(df)

    # Aircraft: fold the movement emissions into the same sources +
    # emissions tables, as synthetic per-grid-cell area sources.
    # `ac_results` carries the per-movement compute dicts for
    # downstream diagnostic dumping; default {} when aircraft skipped.
    ac_results: dict = {}
    if include_aircraft:
        ac_sources_df, ac_emissions_df, ac_results = _build_aircraft_tables(
            alaqs_path,
            aircraft_method,
            pollutants,
            time_window=time_window,
            processes=processes,
            use_isa_meteo=use_isa_meteo,
            source_dynamics=source_dynamics,
            apply_nox_corrections=apply_nox_corrections,
        )
        by_type_summary["aircraft"] = len(ac_emissions_df)
        if len(ac_emissions_df) > 0:
            em_chunks.append(ac_emissions_df)
        if len(ac_sources_df) > 0:
            sources_df = pd.concat([sources_df, ac_sources_df], ignore_index=True)
            # rewrite sources.parquet with the combined table
            sources_df.to_parquet(sources_path, index=False)
        summary["sources"] = len(sources_df)
        print(
            f"  + {len(ac_sources_df)} aircraft cell sources "
            f"-> sources.parquet now {len(sources_df)} sources"
        )

    emissions_df = (
        pd.concat(em_chunks, ignore_index=True) if em_chunks else pd.DataFrame()
    )
    emissions_path = emissions_folder / "emissions.parquet"
    emissions_df.to_parquet(emissions_path, index=False)
    summary["emissions_rows"] = len(emissions_df)
    summary["emissions_by_type"] = by_type_summary
    print(f"  emissions.parquet: {len(emissions_df):,} rows")
    for label, n in by_type_summary.items():
        if n > 0:
            print(f"    {label:8} -> {n:>12,} rows")
    annuals = (
        emissions_df.groupby("pollutant")["kg_in_hour"].sum()
        if len(emissions_df)
        else pd.Series(dtype=float)
    )
    for p, v in annuals.items():
        print(f"    {p:6} = {v:,.2f} kg/yr")

    # ↓↓↓ 4-space indent (same as the `for` above), NOT inside the loop body ↓↓↓
    # 3b. Plugin-compatible per-pollutant gpkg files.
    print(
        "  [gpkg] entering inventory_gpkg block, "
        f"emissions_df has {len(emissions_df)} rows"
    )
    if len(emissions_df) > 0:
        try:
            import sqlite3 as _sqlite3

            from openalaqs_standalone import compute_movements as _cm
            from openalaqs_standalone import inventory_gpkg as _inv
            from openalaqs_standalone import movements as _mv

            _conn = _sqlite3.connect(str(alaqs_path))
            try:
                _grid_bounds = _cm.build_context(_conn)["grid_bounds"]
                _grid_definition = _mv.get_grid_definition(_conn)
            finally:
                _conn.close()

            _pollutants_for_gpkg = pollutants
            if not _pollutants_for_gpkg:
                _pollutants_for_gpkg = sorted(
                    emissions_df["pollutant"].unique().tolist()
                )

            # Write into emissions_folder so downstream pipelines pick them up
            gpkg_dir = emissions_folder
            print(f"  [gpkg] writing to {gpkg_dir.resolve()}")
            print(f"  [gpkg] pollutants: {_pollutants_for_gpkg}")

            paths = _inv.write_pollutant_gpkgs(
                emissions_df,
                sources_df,
                _grid_bounds,
                _grid_definition,
                output_dir=gpkg_dir,
                filename_template="{pollutant}_emissions.gpkg",
                pollutants=_pollutants_for_gpkg,
            )
            for p, path in paths.items():
                print(f"  [gpkg] wrote {p}: {path}")
        except Exception as _e:
            import traceback

            print(f"  [gpkg] FAILED: {_e}")
            traceback.print_exc()

    # 4. Meteo (use .alaqs if no external input given)
    meteo_src = meteo_input if meteo_input is not None else alaqs_path
    n_meteo = adapt_meteo(
        meteo_src,
        meteo_folder / "meteo.csv",
        meteo_year_shift,
        time_window=time_window,
    )
    summary["meteo_hours"] = n_meteo
    print(f"  meteo.csv: {n_meteo} hours")

    # 5. Receptors (optional)
    #
    # Read airport metadata once; reused for target EPSG derivation
    # AND for the absolute-UTM domain bounds against which receptors
    # get clipped. The grid CRS and the receptor CRS must be identical
    # (AUSTAL reads receptor x/y in the same metric frame the grid is
    # anchored in), so we derive a single value here and pass it to
    # both adapt_receptors and make_config.
    meta = _airport_metadata(alaqs_path)
    lon = float(meta.get("airport_longitude") or 0.0)
    lat = float(meta.get("airport_latitude") or 0.0)

    if receptor_target_epsg is None:
        if lon != 0.0:
            receptor_target_epsg = _utm_zone_for_lon(lon)
        # else: leave None; make_config falls back to 32631 internally,
        # but if a receptor CSV is present that case is an error (raised
        # below).

    # Compute the AUSTAL domain bounds in absolute UTM (target_epsg).
    # AUSTAL stops with "Outside computational area" when fed receptors
    # outside the grid; adapt_receptors uses these bounds to drop them
    # up front and log the dropped IDs.
    domain_bounds = None
    if receptor_target_epsg is not None and lon != 0.0 and lat != 0.0:
        tx = Transformer.from_crs(
            "EPSG:4326",
            f"EPSG:{receptor_target_epsg}",
            always_xy=True,
        )
        ref_x, ref_y = tx.transform(lon, lat)
        half = grid_size * grid_step_m / 2.0
        domain_bounds = (
            ref_x - half,
            ref_x + half,
            ref_y - half,
            ref_y + half,
        )

    if receptor_input is not None:
        if receptor_target_epsg is None:
            raise ValueError(
                "Cannot derive receptor target EPSG: user_study_setup has no "
                "airport_longitude. Set receptor_target_epsg explicitly."
            )
        n_rec = adapt_receptors(
            receptor_input,
            receptors_folder / "receptors.csv",
            source_epsg=receptor_source_epsg,
            target_epsg=receptor_target_epsg,
            name_col=receptor_name_col or "ID",
            x_col=receptor_x_col or "longitude",
            y_col=receptor_y_col or "latitude",
            domain_bounds=domain_bounds,
        )
        summary["receptors"] = n_rec
        print(f"  receptors.csv: {n_rec} receptors")
    else:
        # Empty receptor file. AUSTAL doesn't require any receptors;
        # output is still computed on the calculation grid.
        (receptors_folder / "receptors.csv").write_text("name,x,y,z\n")
        summary["receptors"] = 0
        print("  receptors.csv: 0 receptors (empty)")

    # 6. Config
    cfg = make_config(
        alaqs_path,
        config_folder / "config.json",
        title=title,
        grid_size=grid_size,
        grid_step_m=grid_step_m,
        qs=qs,
        pollutants=pollutants,
        year=year,
        utm_epsg=receptor_target_epsg,
        time_window=time_window,
        grid_writer_mode=grid_writer_mode,
        apply_nox_corrections=apply_nox_corrections,
    )
    summary["config"] = cfg
    print("  config.json: written")

    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alaqs_file", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output root directory (will contain six folders)",
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--pollutants", default=",".join(STATIONARY_POLLUTANTS))

    parser.add_argument(
        "--meteo-input",
        type=Path,
        default=None,
        help="External meteo CSV (uses .alaqs tbl_InvMeteo if omitted)",
    )
    parser.add_argument(
        "--meteo-year-shift", type=int, default=None, help="Re-stamp meteo to this year"
    )

    parser.add_argument("--receptor-input", type=Path, default=None)
    parser.add_argument(
        "--receptor-source-epsg",
        type=int,
        default=None,
        help="Source CRS of the receptor CSV. If omitted, "
        "read from the EPSG column in the CSV (QGIS "
        "format). Override for CSVs without that "
        "column (e.g. CIMLK in EPSG:28992).",
    )
    parser.add_argument(
        "--receptor-target-epsg",
        type=int,
        default=None,
        help="Target CRS for receptor reprojection. If "
        "omitted, derived from the airport longitude "
        "(matches the QGIS plugin behaviour).",
    )
    parser.add_argument(
        "--receptor-name-col",
        default=None,
        help="Column in the receptor CSV holding the "
        "receptor name (default: ID, matching the QGIS "
        "Open-ALAQS format)",
    )
    parser.add_argument(
        "--receptor-x-col",
        default=None,
        help="Column holding the x / longitude / easting " "(default: longitude)",
    )
    parser.add_argument(
        "--receptor-y-col",
        default=None,
        help="Column holding the y / latitude / northing " "(default: latitude)",
    )

    parser.add_argument("--title", default=None)
    parser.add_argument("--grid-size", type=int, default=75)
    parser.add_argument("--grid-step", type=float, default=250.0)
    parser.add_argument("--qs", type=int, default=3)

    parser.add_argument(
        "--include-aircraft",
        action="store_true",
        help="Also compute the aircraft movement emissions and fold "
        "them into the same sources.parquet and emissions.parquet "
        "as the stationary sources, so one austal_prep run covers "
        "the whole study. Each occupied inventory grid cell "
        "becomes a synthetic aircraft area source. In this mode "
        "the stationary gate stub is skipped; gate emissions come "
        "from the movement path.",
    )
    parser.add_argument(
        "--aircraft-method",
        default="bymode",
        choices=("bymode", "bffm2_anchor", "bffm2_traj"),
        help="Emission method for the aircraft compute when "
        "--include-aircraft is set. Default: bymode.",
    )
    parser.add_argument(
        "--use-isa-meteo",
        action="store_true",
        help="Force ISA conditions (288.15 K, 101 325 Pa, RH 0.6) for "
        "the BFFM2 ambient correction instead of reading per-period "
        "meteo from tbl_InvMeteo. Default is to use the loaded "
        "meteo, which matches the QGIS plugin's output. No effect "
        "for --aircraft-method bymode or helicopter movements.",
    )

    parser.add_argument(
        "--start",
        default=None,
        help="Optional time-window start (ISO format: 'YYYY-MM-DD' "
        "or 'YYYY-MM-DDTHH:MM[:SS]'). When set together with "
        "--end, only emissions inside the half-open interval "
        "[start, end) are produced. Stationary computes filter "
        "their hourly output, the aircraft compute filters "
        "movements by start time (direction-aware: block_time "
        "for departures, runway_time for arrivals) AND clips "
        "per-segment emissions to the window. Meteo and "
        "start_dt/end_dt in config.json are also trimmed. "
        "Default: full inventory year.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional time-window end (ISO format). See --start.",
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=1,
        help="Number of worker processes for the aircraft movement "
        "compute (only used with --include-aircraft). Default: "
        "1 (serial). Values above 1 run the multiprocessing "
        "driver, which produces bit-identical results to the "
        "serial driver. The stationary computes are already "
        "numpy-vectorised and are not parallelised.",
    )

    parser.add_argument(
        "--source-dynamics",
        default="none",
        choices=("none", "default", "sas"),
        help="Aircraft source-dynamics (smooth-and-shift) mode for the "
        "spatial apportionment, matching the QGIS plugin's "
        "Calculate-Inventory 'source dynamics' dropdown. 'none' "
        "(default) apportions each flight/taxi segment by its "
        "centreline; 'default' and 'sas' widen each segment to the "
        "per-group, per-stage horizontal extent from "
        "default_emission_dynamics and apportion by footprint area "
        "('sas' = the larger 'smooth & shift' extents, 'default' = "
        "the smaller default extents). Only the spatial "
        "distribution changes; movement emission totals are "
        "identical across modes.",
    )
    parser.add_argument(
        "--apply-nox-corrections",
        action="store_true",
        default=False,
        dest="apply_nox_corrections",
        help="Apply the ICCAIA / CAEP14 v14 NOx ambient correction at "
        "takeoff (TO) and climb-out (CL) segments. Reads ambient "
        "T/P/RH from tbl_InvMeteo and airport_elevation from "
        "user_study_setup. Only effective with "
        "--aircraft-method bymode. Default: off.",
    )
    parser.add_argument(
        "--grid-writer-mode",
        default="hybrid",
        choices=("legacy", "time_indexed", "hybrid"),
        help="Layout of the per-source AUSTAL grid files (e<NNNN>.dmna). "
        "'hybrid' (default): aircraft sub-sources get one e-file per "
        "hour with per-pollutant spatial weights (preserves the "
        "time-varying flight footprint and the per-pollutant emission "
        "mix); stationary sources get a single time-invariant e-file. "
        "Matches the QGIS plugin's aircraft handling. "
        "'time_indexed': all sources get a single time-invariant "
        "e-file (faster, smaller, but smears aircraft emissions over "
        "the full study period). "
        "'legacy': all sources get one e-file per hour (largest disk "
        "footprint; useful only if a downstream tool requires that "
        "exact layout).",
    )

    args = parser.parse_args(argv)

    # Parse --start / --end as ISO timestamps. fromisoformat accepts
    # 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:MM[:SS]'.
    from datetime import datetime as _dt

    start_dt = _dt.fromisoformat(args.start) if args.start else None
    end_dt = _dt.fromisoformat(args.end) if args.end else None

    pols = [p.strip() for p in args.pollutants.split(",")]
    print(f"Building input folders in {args.out}")
    print(f"  Source: {args.alaqs_file}")
    print(f"  Year:   {args.year}")
    orchestrate(
        args.alaqs_file,
        args.out,
        args.year,
        pols,
        meteo_input=args.meteo_input,
        meteo_year_shift=args.meteo_year_shift,
        receptor_input=args.receptor_input,
        receptor_source_epsg=args.receptor_source_epsg,
        receptor_target_epsg=args.receptor_target_epsg,
        receptor_name_col=args.receptor_name_col,
        receptor_x_col=args.receptor_x_col,
        receptor_y_col=args.receptor_y_col,
        title=args.title,
        grid_size=args.grid_size,
        grid_step_m=args.grid_step,
        qs=args.qs,
        include_aircraft=args.include_aircraft,
        aircraft_method=args.aircraft_method,
        use_isa_meteo=args.use_isa_meteo,
        start=start_dt,
        end=end_dt,
        processes=args.processes,
        source_dynamics=args.source_dynamics,
        apply_nox_corrections=args.apply_nox_corrections,
        grid_writer_mode=args.grid_writer_mode,
    )
    print()
    print("Done.")


if __name__ == "__main__":
    main()
