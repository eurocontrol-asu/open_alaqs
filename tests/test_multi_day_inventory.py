"""
Multi-day inventory regression test.

Guards against the bug class where time-period arithmetic uses
`timedelta.seconds` (which drops the `.days` component) instead of
`timedelta.total_seconds()`. The bug was fixed in SourceModule and would
cause multi-day inventories to systematically under-count emissions.

Generates a 3-day synthetic inventory DB from the AIRPORT_A template:
  - Extends the meteo table to cover all three days.
  - Clones the existing movements into days 2 and 3 with the same times
    (so every day has identical activity).
  - Runs the emission calculation over each day as a 24-hour window AND
    over the full 3-day window.

Asserts:
  - Day-1, Day-2, Day-3 totals are (nearly) identical (identical activity,
    ambient differences are small).
  - The 3-day-window total equals the sum of the three single-day totals
    to within 0.1%.  If this fails, either (a) the day-spanning arithmetic
    is dropping days, or (b) the per-day interval iteration skips a day.
"""

import datetime
import shutil
import sqlite3
from datetime import timedelta

import pytest

from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from tests.utils import aggregate_emissions, get_data_path

GRID_CONFIG = {
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 1,
    "x_resolution": 100,
    "y_resolution": 100,
    "z_resolution": 100,
    "reference_latitude": 51.96,
    "reference_longitude": 4.44,
    "reference_altitude": 0.0,
}


def _build_three_day_db(src_db, dst_db):
    """Clone AIRPORT_A_out.alaqs and extend to a 3-day inventory:
    - meteo rows for day-2 and day-3 (same diurnal profile as day-1)
    - movement rows cloned to day-2 and day-3 at the same times-of-day
    """
    shutil.copy(src_db, dst_db)
    conn = sqlite3.connect(dst_db)

    # 1. Extend meteo — clone day-1 rows into day-2 and day-3.
    # First DELETE any existing day-2/day-3 rows so the clone produces an
    # exact replica of day-1 (the upstream fixture now ships with all 3 days).
    conn.execute(
        "DELETE FROM tbl_InvMeteo WHERE DateTime LIKE '2025-12-02%' "
        "OR DateTime LIKE '2025-12-03%'"
    )
    day1_meteo = conn.execute(
        "SELECT Scenario, DateTime, Temperature, Humidity, RelativeHumidity, "
        "SeaLevelPressure, WindSpeed, WindDirection, ObukhovLength, "
        "MixingHeight, SpeedOfSound FROM tbl_InvMeteo "
        "WHERE DateTime LIKE '2025-12-01%'"
    ).fetchall()
    for day_offset in (1, 2):  # generate day-2 and day-3
        for row in day1_meteo:
            new_dt = row[1].replace("2025-12-01", f"2025-12-0{1 + day_offset}")
            conn.execute(
                "INSERT OR REPLACE INTO tbl_InvMeteo (Scenario, DateTime, Temperature, "
                "Humidity, RelativeHumidity, SeaLevelPressure, WindSpeed, "
                "WindDirection, ObukhovLength, MixingHeight, SpeedOfSound) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row[0], new_dt, *row[2:]),
            )

    # 2. Clone movements into day-2 and day-3.
    # First DELETE any existing day-2/day-3 movements so the clone produces
    # an exact replica of day-1 (the upstream fixture now ships with all 3
    # days populated; without this, day-1 != day-2 and the equal-activity
    # invariant below fails).
    conn.execute(
        "DELETE FROM user_aircraft_movements "
        "WHERE (runway_time LIKE '2025-12-02%' OR runway_time LIKE '2025-12-03%') "
        "AND NOT (runway_time LIKE '2025-12-01%' OR block_time LIKE '2025-12-01%')"
    )
    mov_cols = [
        r[1] for r in conn.execute("PRAGMA table_info(user_aircraft_movements)")
    ]
    mov_cols.index("runway") if "runway" in mov_cols else None
    day1_movs = conn.execute(
        "SELECT * FROM user_aircraft_movements WHERE runway_time LIKE '2025-12-01%' "
        "OR block_time LIKE '2025-12-01%'"
    ).fetchall()
    # Get the max oid so we can assign new primary keys
    max_oid = (
        conn.execute("SELECT MAX(oid) FROM user_aircraft_movements").fetchone()[0] or 0
    )

    for day_offset in (1, 2):
        for row in day1_movs:
            row_list = list(row)
            max_oid += 1
            row_list[0] = max_oid  # oid
            # Shift any timestamp-like column
            for i, v in enumerate(row_list):
                if isinstance(v, str) and v.startswith("2025-12-01"):
                    row_list[i] = v.replace("2025-12-01", f"2025-12-0{1 + day_offset}")
            placeholders = ",".join("?" for _ in row_list)
            conn.execute(
                f"INSERT INTO user_aircraft_movements VALUES ({placeholders})",
                tuple(row_list),
            )

    # 3. Update the inventory period
    conn.execute(
        "UPDATE tbl_InvPeriod SET min_time = '2025-12-01 00:00:00', "
        "max_time = '2025-12-04 00:00:00'"
    )

    conn.commit()
    conn.close()


def _calc(db_path, start_dt, end_dt, interval_s=3600, method="bymode"):
    cfg = EmissionCalculationConfig(
        db_path=str(db_path),
        start_dt_inclusive=start_dt,
        end_dt_inclusive=end_dt,
        time_interval=timedelta(seconds=interval_s),
        pollutant="CO",
        method=method,
        source_type="movement",
        grid_config=GRID_CONFIG,
    )
    svc = EmissionCalculatorService()
    result = svc.calculate_emissions(cfg)
    assert result.success, f"Calc failed: {result.error_message}"
    return aggregate_emissions(result.emissions_data)


class TestMultiDayInventory:

    @pytest.fixture(scope="class")
    def three_day_db(self, tmp_path_factory):
        tmp_dir = tmp_path_factory.mktemp("three_day_inventory")
        dst = tmp_dir / "airport_a_three_day.alaqs"
        src = get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"
        _build_three_day_db(src, dst)
        return dst

    def test_each_day_produces_emissions(self, three_day_db):
        """Each individual day must produce nonzero emissions — confirms
        the meteo + movement cloning worked."""
        day1 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 1, 0, 0, 0),
            datetime.datetime(2025, 12, 2, 0, 0, 0),
        )
        day2 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 2, 0, 0, 0),
            datetime.datetime(2025, 12, 3, 0, 0, 0),
        )
        day3 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 3, 0, 0, 0),
            datetime.datetime(2025, 12, 4, 0, 0, 0),
        )
        for d, label in [(day1, "day1"), (day2, "day2"), (day3, "day3")]:
            assert d["fuel_kg"] > 0, f"{label} has zero fuel — movements missing"
            assert d["co_kg"] > 0, f"{label} has zero CO"

    def test_three_day_total_equals_sum_of_days(self, three_day_db):
        """Running the calc over the 3-day window must equal the sum of
        three single-day runs to within 0.1%.  A larger discrepancy would
        indicate that either:
          - time_period.seconds is being used instead of total_seconds()
            (drops any .days component → multi-day runs underflow),
          - the ambient-lookup is returning day-1 ambient for day-2/3,
          - inclusive/exclusive boundary handling is double-counting or
            skipping a day.
        """
        day1 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 1, 0, 0, 0),
            datetime.datetime(2025, 12, 2, 0, 0, 0),
        )
        day2 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 2, 0, 0, 0),
            datetime.datetime(2025, 12, 3, 0, 0, 0),
        )
        day3 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 3, 0, 0, 0),
            datetime.datetime(2025, 12, 4, 0, 0, 0),
        )
        combined = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 1, 0, 0, 0),
            datetime.datetime(2025, 12, 4, 0, 0, 0),
        )
        sum_days_fuel = day1["fuel_kg"] + day2["fuel_kg"] + day3["fuel_kg"]
        sum_days_co = day1["co_kg"] + day2["co_kg"] + day3["co_kg"]
        assert combined["fuel_kg"] == pytest.approx(sum_days_fuel, rel=0.001), (
            f"3-day combined fuel {combined['fuel_kg']:.3f} kg "
            f"differs from sum of day-by-day {sum_days_fuel:.3f} kg "
            f"by more than 0.1% — likely a timedelta.seconds vs "
            f".total_seconds() regression."
        )
        assert combined["co_kg"] == pytest.approx(sum_days_co, rel=0.001)

    def test_day_2_equals_day_1_given_same_activity(self, three_day_db):
        """The meteo profile and movement set are cloned exactly between
        days 1 and 2.  So day-2 totals must equal day-1 totals to within
        floating-point noise.  If they drift, the ambient lookup is not
        tracking the date, or the per-day activity isn't being re-read."""
        day1 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 1, 0, 0, 0),
            datetime.datetime(2025, 12, 2, 0, 0, 0),
        )
        day2 = _calc(
            three_day_db,
            datetime.datetime(2025, 12, 2, 0, 0, 0),
            datetime.datetime(2025, 12, 3, 0, 0, 0),
        )
        for p in ("fuel_kg", "co_kg", "co2_kg", "nox_kg"):
            assert day1[p] == pytest.approx(day2[p], rel=1e-6), (
                f"day-1 {p}={day1[p]} differs from day-2 {p}={day2[p]} "
                f"despite identical meteo and movements"
            )
