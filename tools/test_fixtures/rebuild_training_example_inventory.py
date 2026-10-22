#!/usr/bin/env python3
"""Rebuild example/training/training_out.alaqs from the example's inputs.

Runs the plugin's own inventory creation (`alaqs.inventory_creation_new`, the
"Generate Emission Inventory" path of the dialog) on
example/training/training.alaqs with training_movements.csv and
training_meteo.csv, then imports training_ads_b_data.csv into the inventory
(`ads_b.import_adsb_file`, tier 1: reference point from each flight's runway
and taxi route in the movement CSV), as the dialog does when an ADS-B file is
given. Settings as in documents/TEST_CASE_STUDY.md ("Generate Emissions
Inventory"): 100 x 100 x 20 cells of 250 x 250 x 50 m, movements 2025-12-01
06:00 to 2025-12-03 09:00, vertical limit 914.4 m; study setup from training.alaqs.

Usage, from the repository root:

    QT_QPA_PLATFORM=offscreen python3 tools/test_fixtures/rebuild_training_example_inventory.py \
        [--input-dir DIR] [--end "YYYY-MM-DD HH:MM:SS"] [--out PATH]

--input-dir: folder holding training.alaqs, training_movements.csv,
training_meteo.csv and training_ads_b_data.csv (default example/training).
--end: end of the movements period (default 2025-12-03 09:00:00).
--out: default <input-dir>/training_out.alaqs.

Afterwards rebuild the example workbook (see
openalaqs_standalone/validation/tools/CAEP14_VALIDATION.md).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
EX = REPO / "example" / "training"
DEFAULT_END = "2025-12-03 09:00:00"

MODEL_PARAMETERS = {
    "movement_path": str(EX / "training_movements.csv"),
    "study_start_date": "2025-12-01 06:00:00",
    "study_end_date": DEFAULT_END,
    "towing_speed": 10.0,
    "vertical_limit": 914.4,
    "x_resolution": 250,
    "y_resolution": 250,
    "z_resolution": 50,
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 20,
    "include_stationary_sources": True,
    "include_parkings": True,
    "include_area_sources": True,
    "include_taxiway_queues": True,
    "include_gates": True,
    "include_building": True,
    "include_roadways": True,
    "use_fuel_flow": False,
    "use_3d_grid": True,
    "use_variable_mixing_height": False,
    "use_nox_correction": False,
    "use_copert": False,
    "use_smooth_and_shift": False,
}


def model_parameters(input_dir: Path = EX, end: str = DEFAULT_END) -> dict:
    """MODEL_PARAMETERS with the movement CSV of `input_dir` and end `end`."""
    params = dict(MODEL_PARAMETERS)
    params["movement_path"] = str(Path(input_dir) / "training_movements.csv")
    params["study_end_date"] = end
    return params


def _end_datetime(value: str) -> str:
    """argparse type for --end: ISO date-time, returned as YYYY-MM-DD HH:MM:SS."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--end {value!r} is not a date-time (YYYY-MM-DD HH:MM:SS)"
        ) from None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=EX,
        help="folder with training.alaqs and the movement, meteo and ADS-B "
        "CSVs (default: example/training)",
    )
    ap.add_argument(
        "--end",
        type=_end_datetime,
        default=DEFAULT_END,
        help=f"end of the movements period (default: {DEFAULT_END})",
    )
    ap.add_argument(
        "--out", default=None, help="default: <input-dir>/training_out.alaqs"
    )
    args = ap.parse_args(argv)
    if args.out is None:
        args.out = str(args.input_dir / "training_out.alaqs")
    return args


def _study_setup(project: Path) -> dict:
    with sqlite3.connect(project) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM user_study_setup").fetchone())


def main(argv=None) -> int:
    args = parse_args(argv)
    input_dir = args.input_dir
    params = model_parameters(input_dir, args.end)

    from qgis.testing import start_app

    start_app()
    from open_alaqs.core.alaqs import inventory_creation_new
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.tools import ads_b

    project = input_dir / "training.alaqs"
    out = Path(args.out)
    if out.exists():
        out.unlink()
    ProjectDatabase().path = str(project)
    inventory_creation_new(
        str(out),
        params,
        _study_setup(project),
        str(input_dir / "training_meteo.csv"),
    )
    ok, msg = ads_b.import_adsb_file(
        str(input_dir / "training_ads_b_data.csv"), str(out), params["movement_path"]
    )
    if not ok:
        raise SystemExit(f"ADS-B import failed: {msg}")
    print(f"wrote {out}; ADS-B: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
