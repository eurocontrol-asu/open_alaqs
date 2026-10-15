"""Re-export the pinned plugin outputs of the CAEP14 validation without QGIS's GUI.

Runs the plugin's EmissionCalculatorService (the code path of the QGIS dialog)
on the training fixture, all source types, and writes per period and source
the emissions in kg, in the layout of the Table View output module (without
the geometry column):

    data/plugin_output/training_movements_{bymode,bffm2_anchor,bffm2_traj,bymode_nox_corr}.csv
        the Movement rows of the run with that method
    data/plugin_output/training_sources_bymode.csv
        the stationary-source rows (area, parking, point, roadway) of the bymode run

`compute_caep14_reference.py --plugin-csv` and the validation tests read
`source_name` and the `*_kg` columns and sum the rows of one movement.

Needs the QGIS Python bindings (python3.12 on the reference machine) and a
display-less Qt: QT_QPA_PLATFORM=offscreen. The fixture is copied before each
run because the plugin writes its trajectory cache into the study. One run
computes every pollutant whatever the `pollutant` field says.

Usage, from the repository root:

    QT_QPA_PLATFORM=offscreen python3.12 \\
        openalaqs_standalone/validation/tools/regenerate_plugin_csvs.py \\
        [--fixture path/to/study.alaqs] [--out-dir dir] [--methods bymode ...]
"""

from __future__ import annotations

import argparse
import csv
import datetime
import shutil
import sqlite3
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
ROOT = HERE.parents[2]
COLUMNS = [
    "co_kg",
    "co2_kg",
    "hc_kg",
    "nox_kg",
    "sox_kg",
    "pm10_kg",
    "p1_kg",
    "p2_kg",
    "pm10_organic_kg",
    "pm10_nonvol_kg",
    "pm10_sul_kg",
]
# name -> (plugin method, bffm2 fuel-flow source, NOx ambient correction)
METHODS = {
    "bymode": ("bymode", "trajectory", False),
    "bffm2_anchor": ("BFFM2", "mode_anchor", False),
    "bffm2_traj": ("BFFM2", "trajectory", False),
    "bymode_nox_corr": ("bymode", "trajectory", True),
}
SOURCE_TYPES = {
    "AreaSources": "AreaSource",
    "ParkingSources": "ParkingSource",
    "PointSources": "PointSource",
    "RoadwaySources": "RoadwaySource",
}


def _period(conn) -> tuple:
    first, last = conn.execute(
        "SELECT MIN(runway_time), MAX(runway_time) FROM user_aircraft_movements"
    ).fetchone()
    start = datetime.datetime.fromisoformat(first).replace(hour=0, minute=0, second=0)
    end = datetime.datetime.fromisoformat(last).replace(hour=0, minute=0, second=0)
    return start, end + timedelta(days=1)


def _grid(conn) -> dict:
    g = conn.execute(
        "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, z_resolution, "
        "reference_latitude, reference_longitude FROM grid_3d_definition"
    ).fetchone()
    keys = [
        "x_cells",
        "y_cells",
        "z_cells",
        "x_resolution",
        "y_resolution",
        "z_resolution",
        "reference_latitude",
        "reference_longitude",
    ]
    # The QGIS dialog sets the grid's reference altitude to the study's airport
    # elevation (DispersionAnalysis); the NOx ambient correction reads it as the
    # airport altitude for the ISA temperature.
    elev = conn.execute(
        "SELECT airport_elevation FROM user_study_setup LIMIT 1"
    ).fetchone()
    ref_alt = float(elev[0]) if elev and elev[0] is not None else 0.0
    return dict(zip(keys, g), reference_altitude=ref_alt)


def run_plugin(db: str, method: str, ff_source: str, nox_corr: bool = False) -> list:
    """Rows (timestamp, source class, source name, {column: kg}) of one run, all sources."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton
    from open_alaqs.core.EmissionCalculatorService import (
        EmissionCalculationConfig,
        EmissionCalculatorService,
    )

    with sqlite3.connect(db) as conn:
        grid = _grid(conn)
        start, end = _period(conn)
    Singleton._instances.clear()
    ProjectDatabase().path = db
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="all",
            grid_config=grid,
            method=method,
            bffm2_ff_source=ff_source,
            should_apply_nox_corrections=nox_corr,
            start_dt_inclusive=start,
            end_dt_inclusive=end,
            time_interval=timedelta(seconds=3600),
        )
    )
    if not result.success:
        raise RuntimeError(result.error_message)
    rows = []
    for ts, period in result.emissions_data.items():
        for source, emissions in period:
            kg = {c: 0.0 for c in COLUMNS}
            for e in emissions:
                ek = e.transposeToKilograms()
                for c in COLUMNS:
                    kg[c] += ek.getObject(c) or 0.0
            rows.append(
                (ts.isoformat(), type(source).__name__, str(source.getName()), kg)
            )
    return rows


def _write(path: Path, rows: list) -> None:
    with open(path, "w", newline="") as f:
        # LF line endings, as the repository's mixed-line-ending hook wants.
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["timestamp", "source_type", "source_name"] + COLUMNS)
        for ts, stype, name, kg in rows:
            # float() first: under NumPy 2 the plugin can hand back np.float64, whose
            # repr is 'np.float64(...)' and would not parse back.
            w.writerow([ts, stype, name] + [repr(float(kg[c])) for c in COLUMNS])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", default=str(DATA / "training_v3.alaqs"))
    ap.add_argument("--out-dir", default=str(DATA / "plugin_output"))
    ap.add_argument(
        "--methods", nargs="+", default=list(METHODS), choices=list(METHODS)
    )
    args = ap.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from qgis.testing import start_app

    start_app()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for m in args.methods:
            db = Path(tmp) / f"{m}.alaqs"
            shutil.copy(args.fixture, db)
            method, ff, nox_corr = METHODS[m]
            rows = run_plugin(str(db), method, ff, nox_corr)
            movements = [r for r in rows if r[1] == "Movement"]
            _write(out_dir / f"training_movements_{m}.csv", movements)
            names = {r[2] for r in movements}
            print(
                f"training_movements_{m}.csv: {len(movements)} rows, {len(names)} movements"
            )
            if m == "bymode":
                stationary = [
                    (ts, stype, name, kg)
                    for ts, stype, name, kg in rows
                    if stype in SOURCE_TYPES
                ]
                _write(out_dir / "training_sources_bymode.csv", stationary)
                print(f"training_sources_bymode.csv: {len(stationary)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
