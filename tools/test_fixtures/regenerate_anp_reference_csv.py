#!/usr/bin/env python3
"""
Regenerate `ANP_emissions_table_by_aggregation_co.csv` from the current
EmissionCalculatorService output.

WHY THIS EXISTS
---------------
The reference CSV was produced before the rebuild's Grid3D UTM fix and
spatial.py B1-B10 fixes. The current calculator produces different totals
for spatial-sensitive pollutants:

    CO:   -0.05% drift (CO is weakly spatial-dependent)
    CO2:  -2.31% drift
    NOx:  -2.82% drift
    SOx:  -2.28% drift
    PM10: -0.94% drift
    HC:   -0.07% drift
    P1:   -1.55% drift
    P2:   -1.12% drift

The calculator is the source of truth post-fix; the reference CSV needs
to follow it. This script snapshots the current calculator output into
the same 14-column CSV format (one row per hourly timestamp, aggregating
across all sources with `source_type=total, source_name=total`).

The drift values above were the pre-fix state captured during the #52
session. They should be approximately reproduced if this script is run
again against an unchanged calculator; significantly different output
would indicate a further calculator change that the reviewer should
investigate before committing the new CSV.

USAGE
-----
From the repo root:

    QT_QPA_PLATFORM=offscreen python tests/data/ANP/regenerate_reference_csv.py

Then run:

    python -m pytest tests/test_emission_calculator_service.py::TestANPEmissions

Both CO and all-pollutants tests should pass (no more xfail). The three
xfail decorators on those tests can then be removed.

OUTPUT FORMAT
-------------
Matches the existing 14-column format exactly:

    timestamp, source_type, source_name, co_kg, co2_kg, hc_kg, nox_kg,
    sox_kg, pm10_kg, p1_kg, p2_kg, pm10_organic_kg, pm10_nonvol_kg,
    pm10_sul_kg, wkt

- `timestamp`: ISO format `2023-03-01T06:00:00`
- `source_type`: always `"total"`
- `source_name`: always `"total"`
- `*_kg`: aggregate emission in kg across all sources for that hour
- `wkt`: always empty (matches existing CSV)
- One row per hour from 2023-03-01 06:00 through 2023-03-01 21:00 inclusive

No trailing newline on the final row (matches existing CSV).
"""

from __future__ import annotations

import csv
import datetime
import sys
from datetime import timedelta
from pathlib import Path

# Repo root is 3 levels up from this file
REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from open_alaqs.core.EmissionCalculatorService import (  # noqa: E402
    EmissionCalculationConfig,
    EmissionCalculatorService,
)

# Grid config must match what the tests use. Copied from
# tests/test_emission_calculator_service.py (ANP_GRID_CONFIG).
ANP_GRID_CONFIG = {
    "x_cells": 10,
    "y_cells": 10,
    "z_cells": 1,
    "x_resolution": 500.0,
    "y_resolution": 500.0,
    "z_resolution": 50.0,
    "reference_latitude": 51.9561,
    "reference_longitude": 4.4431,
}

# Test date range: 2023-03-01 06:00 → 22:00 hourly (inclusive-exclusive
# gives 16 hourly slots from 06:00 through 21:00).
START_DT = datetime.datetime(2023, 3, 1, 6, 0, 0)
END_DT = datetime.datetime(2023, 3, 1, 22, 0, 0)
TIME_INTERVAL = timedelta(seconds=3600)

# Output pollutant order must match the existing CSV header
CSV_COLUMNS = [
    "timestamp",
    "source_type",
    "source_name",
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
    "wkt",
]

# Pollutant keys (as emitted by EmissionIndex.transposeToKilograms) that
# map to the CSV *_kg columns. The order here must match CSV_COLUMNS
# starting at index 3.
POLLUTANT_KEYS = [
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

ANP_DIR = REPO_ROOT / "tests" / "data" / "ANP"
DB_PATH = ANP_DIR / "ANP_out.alaqs"
OUT_CSV = ANP_DIR / "ANP_emissions_table_by_aggregation_co.csv"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"ANP_out.alaqs not found at {DB_PATH}")

    service = EmissionCalculatorService()

    # Use pollutant="CO" to match the historical CSV filename convention.
    # The result actually contains all pollutants — CO is just the filter
    # hint for the config validator; aggregate_emissions sums everything.
    config = EmissionCalculationConfig(
        db_path=str(DB_PATH),
        start_dt_inclusive=START_DT,
        end_dt_inclusive=END_DT,
        time_interval=TIME_INTERVAL,
        pollutant="CO",
        method="bymode",
        source_type="all",
        grid_config=ANP_GRID_CONFIG,
    )

    result = service.calculate_emissions(config)
    if not result.success:
        raise SystemExit(f"Calculation failed: {result.error_message}")

    # Aggregate per-timestamp across all (source, emissions) pairs.
    # result.emissions_data is a dict[datetime, list[tuple[source, list[emission]]]]
    per_ts_totals: dict[datetime.datetime, dict[str, float]] = {}
    for ts, period_emissions in result.emissions_data.items():
        ts_totals = {k: 0.0 for k in POLLUTANT_KEYS}
        for _source, emissions_list in period_emissions:
            for emission in emissions_list:
                emission_kg = emission.transposeToKilograms()
                for key in POLLUTANT_KEYS:
                    if emission_kg.hasKey(key):
                        ts_totals[key] += emission_kg.getObject(key)
        per_ts_totals[ts] = ts_totals

    # Write CSV in the exact same format as the existing reference file:
    # - header on line 1
    # - one "total/total" row per timestamp, sorted by timestamp
    # - wkt column empty
    # - no trailing newline on the final row
    rows = []
    for ts in sorted(per_ts_totals.keys()):
        totals = per_ts_totals[ts]
        row = [
            ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "total",
            "total",
        ]
        row.extend(repr(totals[k]) for k in POLLUTANT_KEYS)
        row.append("")  # wkt
        rows.append(row)

    # Use newline="" per Python csv module docs (and #291 fix) — avoids
    # double line endings on Windows. But override csv.writer's default
    # CRLF terminator with LF to match the existing file's Unix-style
    # line endings (the repo convention).
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)

    print(f"Wrote {OUT_CSV}")
    print(f"  {len(rows)} hourly rows from {START_DT} through {END_DT - TIME_INTERVAL}")

    # Echo the totals for quick visual sanity-check
    grand_totals = {k: 0.0 for k in POLLUTANT_KEYS}
    for ts, totals in per_ts_totals.items():
        for k in POLLUTANT_KEYS:
            grand_totals[k] += totals[k]
    print("  Grand totals (sum of all 16 rows):")
    for k in POLLUTANT_KEYS:
        print(f"    {k}: {grand_totals[k]:.6e}")


if __name__ == "__main__":
    main()
