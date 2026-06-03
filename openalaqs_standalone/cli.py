"""
cli: command-line entry points for the openalaqs_standalone package.

This module holds the CLI command implementations. The package entry
point (`python -m openalaqs_standalone`, see `__main__.py`) dispatches
to the functions here.

Two commands exist today:

  aircraft   Run the Phase A0 aircraft emission core against an
             `.alaqs` file and write per-movement emission totals.
             This is the "(a)" output mode: one row per movement per
             pollutant, summed over the whole LTO. Implemented here.

  austal     Build the six-folder austal_prep input structure (the
             stationary-source + AUSTAL-config pipeline). This is the
             pre-existing `orchestrate.orchestrate` driver, exposed as
             a subcommand. Dispatched in `__main__.py`.

The `aircraft` command is the first runnable surface for the validated
Phase A0 core: until now the aircraft computes existed only as
importable modules exercised by the test suite. This makes them
usable from a shell, which is also the first integration check that
the A0 modules compose correctly end to end.

Output: the `aircraft` command writes a CSV with one row per
(movement oid, pollutant), columns:

    oid, aircraft, departure_arrival, profile_id, method,
    co_kg, co2_kg, hc_kg, nox_kg, sox_kg, pm10_kg

so the result is directly comparable to the validation bundle's
`plugin_output/*.csv` (which `compute_movements.load_plugin_totals`
parses) and to the reference implementation's output.

This module imports only the standalone's own packages and the
standard library. It does not import QGIS or PyQt.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from openalaqs_standalone import austal_aircraft as aa
from openalaqs_standalone import compute_movements as cm
from openalaqs_standalone import movements as mv
from openalaqs_standalone import parallel as par

# Column order for the per-movement totals CSV. The pollutant columns
# are suffixed `_kg` to match the plugin-output CSV convention that
# `compute_movements.load_plugin_totals` already parses.
_CSV_COLUMNS = ["oid", "aircraft", "departure_arrival", "profile_id", "method"] + [
    f"{p}_kg" for p in cm.POLLUTANTS
]


def _write_totals_csv(
    results: dict, out_path: Path, aircraft_only: bool = False
) -> int:
    """Write the per-movement totals dict to a CSV.

    `results` is the dict returned by `compute_all_movements`: oid ->
    per-movement result dict. Returns the number of movement rows
    written.

    If `aircraft_only` is True, the CSV value for each pollutant is the
    aircraft-trajectory contribution only, i.e. `total_em_kg` with the
    gate (GSE+GPU), APU, and engine-start folds subtracted. This is the
    quantity directly comparable to the plugin's `source_type =
    "Movement"` rows in its emissions CSV. Default False preserves the
    historical behaviour (total = trajectory + gate + APU + start).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_COLUMNS)
        for oid in sorted(results):
            res = results[oid]
            totals = res["total_em_kg"]
            row = [
                res["oid"],
                res["aircraft"],
                res["departure_arrival"],
                res["profile_id"],
                res["method"],
            ]
            if aircraft_only:
                # Pollutant keys in the fold dicts are bare (e.g. "co"),
                # while POLLUTANTS uses the same bare-key convention.
                # Fold dicts only carry the five non-CO2 pollutants per
                # the plugin's source-split convention; missing keys are
                # treated as zero so co2 passes through unchanged.
                gate = res.get("gate_em_kg") or {}
                apu = res.get("apu_em_kg") or {}
                start = res.get("start_em_kg") or {}
                vals = []
                for p in cm.POLLUTANTS:
                    v = float(totals[p])
                    v -= float(gate.get(p, 0.0))
                    v -= float(apu.get(p, 0.0))
                    v -= float(start.get(p, 0.0))
                    vals.append(v)
                row += vals
            else:
                row += [totals[p] for p in cm.POLLUTANTS]
            writer.writerow(row)
            rows_written += 1
    return rows_written


def _write_austal_tables(
    results: dict, conn, out_dir: Path, source_dynamics: str = "none"
) -> None:
    """Write the Phase A5 AUSTAL input pair for the aircraft emissions.

    Builds the gridded aircraft emissions as synthetic per-cell area
    sources (see `austal_aircraft.build_aircraft_austal_tables`) and
    writes them to `out_dir` as `emissions.parquet` and
    `sources.parquet`, the schema the `austal_prep` package consumes.
    Always hourly, as AUSTAL requires.

    `conn` must still be open: the gridding reads movement runway
    times and the runway geometry from it.
    """
    ctx = cm.build_context(conn)
    grid_bounds = ctx["grid_bounds"]
    grid_definition = mv.get_grid_definition(conn)

    emissions_df, sources_df = aa.build_aircraft_austal_tables(
        results,
        conn,
        grid_bounds,
        grid_definition,
        source_dynamics=source_dynamics,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    emissions_path = out_dir / "emissions.parquet"
    sources_path = out_dir / "sources.parquet"
    emissions_df.to_parquet(emissions_path, index=False)
    sources_df.to_parquet(sources_path, index=False)

    print(
        f"  wrote AUSTAL aircraft input to {out_dir}: "
        f"{len(sources_df)} cell sources, {len(emissions_df)} "
        f"emission rows"
    )


def _print_summary(results: dict, method: str, aircraft_only: bool = False) -> None:
    """Print a short per-pollutant study total to stdout.

    When `aircraft_only` is True, the totals printed match the
    aircraft-only values written to the CSV (gate + APU + engine-start
    folds subtracted). Otherwise the historical merged totals are
    printed.
    """
    study_totals = {p: 0.0 for p in cm.POLLUTANTS}
    for res in results.values():
        totals = res["total_em_kg"]
        if aircraft_only:
            gate = res.get("gate_em_kg") or {}
            apu = res.get("apu_em_kg") or {}
            start = res.get("start_em_kg") or {}
            for p in cm.POLLUTANTS:
                v = float(totals[p])
                v -= float(gate.get(p, 0.0))
                v -= float(apu.get(p, 0.0))
                v -= float(start.get(p, 0.0))
                study_totals[p] += v
        else:
            for p in cm.POLLUTANTS:
                study_totals[p] += totals[p]
    n_fixed = sum(1 for r in results.values() if r["profile_id"][:5] != "FOCA[")
    n_heli = len(results) - n_fixed
    print(f"  method:     {method}")
    print(
        f"  movements:  {len(results)} " f"({n_fixed} fixed-wing, {n_heli} helicopter)"
    )
    label = "aircraft-only" if aircraft_only else "total"
    print(f"  study totals (kg, {label}):")
    for p in cm.POLLUTANTS:
        print(f"    {p:5} = {study_totals[p]:,.6f}")


def run_aircraft(argv: list | None = None) -> int:
    """The `aircraft` subcommand: per-movement aircraft emission totals.

    Runs the Phase A0 aircraft core against an `.alaqs` file and writes
    a per-movement totals CSV. Returns a process exit code: 0 on
    success, 2 on a usage or input error.
    """
    parser = argparse.ArgumentParser(
        prog="python -m openalaqs_standalone aircraft",
        description=(
            "Compute per-movement aircraft emission totals from an "
            ".alaqs file (the Phase A0 core). Writes one CSV row per "
            "movement per pollutant."
        ),
    )
    parser.add_argument(
        "alaqs_file",
        type=Path,
        help="Path to the OpenALAQS .alaqs study file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Path for the per-movement totals CSV.",
    )
    parser.add_argument(
        "--method",
        default="bymode",
        choices=cm.METHODS,
        help=(
            "Emission method. bymode: EEDB-table EI. bffm2_anchor: "
            "BFFM2-ambient EI at the mode anchor fuel flow. "
            "bffm2_traj: BFFM2-ambient EI with per-segment trajectory "
            "fuel flow. Default: bymode."
        ),
    )
    parser.add_argument(
        "--use-meteo",
        action="store_true",
        default=True,
        help=(
            "Use the meteo loaded in tbl_InvMeteo for the BFFM2 "
            "ambient correction (default).  Matches the QGIS plugin's "
            "emission-CSV output when meteo is populated. No effect "
            "for --method bymode or for helicopter movements."
        ),
    )
    parser.add_argument(
        "--isa-meteo",
        dest="use_meteo",
        action="store_false",
        help=(
            "Force ISA conditions (288.15 K, 101 325 Pa, RH 0.6) for "
            "the BFFM2 ambient correction, ignoring tbl_InvMeteo. "
            "Use only to reproduce older standalone runs that "
            "hard-coded ISA."
        ),
    )
    parser.add_argument(
        "--oids",
        default=None,
        help=(
            "Comma-separated movement oids to compute. If omitted, "
            "every movement in the study is computed."
        ),
    )
    parser.add_argument(
        "--austal-out",
        type=Path,
        default=None,
        help=(
            "Optional directory. If given, also writes the AUSTAL "
            "input pair for the aircraft emissions: emissions.parquet "
            "and sources.parquet, with each occupied grid cell as a "
            "synthetic area source (Phase A5). Always hourly, as "
            "AUSTAL requires."
        ),
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=1,
        help=(
            "Number of worker processes for the movement compute. "
            "The default, 1, runs the serial driver. A value above 1 "
            "runs the multiprocessing driver (Phase A4), which "
            "produces results identical to the serial driver but "
            "spreads the per-movement work across processes. Worth it "
            "for studies with many movements."
        ),
    )
    parser.add_argument(
        "--source-dynamics",
        default="none",
        choices=("none", "default", "sas"),
        help=(
            "Aircraft source-dynamics (smooth-and-shift) mode for the "
            "spatial apportionment of the --austal-out output, "
            "matching the QGIS plugin's Calculate-Inventory "
            "'source dynamics' dropdown. 'none' (default) apportions "
            "each flight/taxi segment by its centreline; 'default' and "
            "'sas' widen each segment to the per-group, per-stage "
            "horizontal extent from default_emission_dynamics and "
            "apportion by footprint area ('sas' uses the larger "
            "'smooth & shift' extents, 'default' the smaller ones). "
            "Only the spatial distribution changes; the per-movement "
            "emission totals (the --out CSV) are identical across modes."
        ),
    )
    parser.add_argument(
        "--apply-nox-corrections",
        action="store_true",
        default=False,
        dest="apply_nox_corrections",
        help=(
            "Apply the ICCAIA / CAEP14 v14 NOx ambient correction at "
            "takeoff (TO) and climb-out (CL) segments. Reads ambient "
            "temperature, pressure and relative humidity from "
            "tbl_InvMeteo per inventory period, plus airport elevation "
            "from user_study_setup. tow_ratio from user_aircraft_"
            "movements is used when set (defaults to 1.0 = no weight "
            "term). Active only with --method bymode; ignored for "
            "BFFM2 methods, which incorporate their own ambient "
            "correction. Default: off."
        ),
    )
    parser.add_argument(
        "--aircraft-only",
        action="store_true",
        default=False,
        dest="aircraft_only",
        help=(
            "Write per-movement aircraft-trajectory totals only "
            "(subtract gate + APU + engine-start contributions from "
            "total_em_kg before writing). The resulting CSV value per "
            "pollutant is directly comparable to the plugin's "
            '`source_type = "Movement"` rows in its emissions CSV. '
            "Required for VALIDATION_GUIDE.md V2 / V5 procedures that "
            "diff the standalone CSV against pinned plugin per-source "
            "CSVs. Default off (preserves historical behaviour, where "
            "the CSV total includes the gate/APU/start folds)."
        ),
    )
    args = parser.parse_args(argv)

    if not args.alaqs_file.is_file():
        print(
            f"error: .alaqs file not found: {args.alaqs_file}",
            file=sys.stderr,
        )
        return 2

    # Parse the optional oid subset.
    oids = None
    if args.oids is not None:
        try:
            oids = [int(tok) for tok in args.oids.split(",") if tok.strip()]
        except ValueError:
            print(
                f"error: --oids must be a comma-separated list of "
                f"integers, got {args.oids!r}",
                file=sys.stderr,
            )
            return 2
        if not oids:
            print("error: --oids was empty", file=sys.stderr)
            return 2

    if args.processes < 1:
        print(
            f"error: --processes must be at least 1, got " f"{args.processes}",
            file=sys.stderr,
        )
        return 2

    print(f"Computing aircraft emissions from {args.alaqs_file}")
    if args.processes > 1:
        print(f"  using {args.processes} worker processes")

    conn = mv.connect(str(args.alaqs_file))
    try:
        if args.processes > 1:
            # Phase A4 parallel driver. It opens its own per-worker
            # connections; the `conn` above is kept open only for the
            # downstream --austal-out step, which reads
            # the runway and grid geometry. The parallel result is
            # bit-identical to the serial compute_all_movements.
            results = par.compute_all_movements_parallel(
                str(args.alaqs_file),
                method=args.method,
                use_isa_meteo=not args.use_meteo,
                oids=oids,
                processes=args.processes,
                apply_nox_corrections=args.apply_nox_corrections,
            )
        else:
            results = cm.compute_all_movements(
                conn,
                method=args.method,
                use_isa_meteo=not args.use_meteo,
                oids=oids,
                apply_nox_corrections=args.apply_nox_corrections,
            )

        if not results:
            # Either the study has no movements, or the requested oids
            # did not resolve to any computable movement. Not a crash,
            # but worth a clear message and a non-zero exit so a
            # caller in a pipeline notices.
            if oids is not None:
                print(
                    f"error: none of the requested oids {oids} resolved "
                    f"to a computable movement",
                    file=sys.stderr,
                )
            else:
                print(
                    "error: the study has no computable aircraft " "movements",
                    file=sys.stderr,
                )
            return 2

        n_written = _write_totals_csv(
            results,
            args.out,
            aircraft_only=args.aircraft_only,
        )
        _print_summary(results, args.method, aircraft_only=args.aircraft_only)
        print(f"  wrote {n_written} movement rows to {args.out}")

        # Optional Phase A5 output: the AUSTAL input pair. Needs the
        # connection still open (distribute_to_grid reads movement
        # runway times and the runway geometry), which is why this
        # sits inside the same `try` rather than after the close.
        if args.austal_out is not None:
            _write_austal_tables(results, conn, args.austal_out, args.source_dynamics)

        # Optional GeoPackage output: total emissions per grid cell.
        # Also needs the connection open, for the same reason.
    finally:
        conn.close()

    return 0
