"""Regression: a profile point with no power setting and a zero or negative fuel
flow must not stop a BFFM2 calculation.

The segment test for "no power and no fuel flow" (bymode index for the segment)
only caught a missing fuel flow. A negative `fuel_flow_kgm` with an empty
`power` went on to the twin-quadratic fit with no power setting and raised a
TypeError, so the whole calculation failed. Such a segment now takes the bymode
index, like a point with neither value.
"""

import datetime
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.EmissionCalculatorService import (  # noqa: E402
    EmissionCalculationConfig,
    EmissionCalculatorService,
)

SRC = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)

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


@pytest.fixture(autouse=True)
def _isolate_singletons():
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton

    saved_path = getattr(ProjectDatabase(), "path", None)
    saved_instances = dict(Singleton._instances)
    Singleton._instances.clear()
    try:
        yield
    finally:
        Singleton._instances.clear()
        Singleton._instances.update(saved_instances)
        if saved_path is not None:
            ProjectDatabase().path = saved_path
        _clear_trajectory_cache()


def _clear_trajectory_cache():
    import open_alaqs.core.interfaces.Movement as _mov_mod

    if hasattr(_mov_mod, "_mem_traj_cache"):
        _mov_mod._mem_traj_cache.clear()


def _nox_of_departure(tmp_path, name, fuel_flow_sql):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton

    Singleton._instances.clear()
    _clear_trajectory_cache()
    db = tmp_path / name
    shutil.copy(SRC, db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE default_aircraft_profiles SET power = NULL, fuel_flow_kgm = %s "
            "WHERE profile_id = 'JET-SMALL-D-1' AND point = 3" % fuel_flow_sql
        )
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'cache_%'"
        ).fetchall():
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    ProjectDatabase().path = str(db)
    cfg = EmissionCalculationConfig(
        db_path=str(db),
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="BFFM2",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 7),
        time_interval=timedelta(seconds=3600),
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            if str(source.getName()).startswith("id 2:"):
                return sum(
                    e.transposeToKilograms().getObject("nox_kg") or 0.0
                    for e in emissions
                )
    raise AssertionError("movement 2 not found")


def test_negative_fuel_flow_without_power_uses_bymode(tmp_path):
    no_values = _nox_of_departure(tmp_path, "none.alaqs", "NULL")
    negative = _nox_of_departure(tmp_path, "negative.alaqs", "-1")
    zero = _nox_of_departure(tmp_path, "zero.alaqs", "0")
    assert no_values > 0.0
    assert negative == pytest.approx(no_values, rel=1e-12)
    assert zero == pytest.approx(no_values, rel=1e-12)


def _nox_with_taxi_thrust(tmp_path, name, thrust):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton

    Singleton._instances.clear()
    _clear_trajectory_cache()
    db = tmp_path / name
    shutil.copy(SRC, db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET engine_thrust_level_for_taxiing = ? "
            "WHERE oid = 2",
            (thrust,),
        )
        conn.commit()
    ProjectDatabase().path = str(db)
    cfg = EmissionCalculationConfig(
        db_path=str(db),
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="BFFM2",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 7),
        time_interval=timedelta(seconds=3600),
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            if str(source.getName()).startswith("id 2:"):
                return sum(
                    e.transposeToKilograms().getObject("nox_kg") or 0.0
                    for e in emissions
                )
    raise AssertionError("movement 2 not found")


def test_taxi_thrust_outside_range_does_not_stop_bffm2(tmp_path, caplog):
    """engine_thrust_level_for_taxiing 7 (7 % typed as a percentage) raised in
    the twin-quadratic fit and stopped the whole BFFM2 calculation; the taxi now
    takes the bymode (TX) index, with an error in the log."""
    nominal = _nox_with_taxi_thrust(tmp_path, "nominal.alaqs", 0.07)
    for thrust in (7.0, -0.1):
        value = _nox_with_taxi_thrust(tmp_path, f"t{thrust}.alaqs", thrust)
        assert value > 0.0
        assert value == pytest.approx(nominal, rel=0.05)
    assert "is not a thrust fraction" in caplog.text
