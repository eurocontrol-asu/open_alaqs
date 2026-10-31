"""Meteo row and LTO ceiling: the standalone must follow the plugin.

Plugin (canonical): a movement belongs to the period containing its runway
time; the period uses the meteo row nearest in time to the period start
(EmissionCalculation.getAmbientCondition), and the LTO ceiling is that row's
MixingHeight, 914.4 m when it is empty (AmbientCondition default). The
study's vertical limit is never used.

The standalone used the latest row at or before the runway time, and fell
back to user_study_setup.vertical_limit when the MixingHeight was missing.
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
from openalaqs_standalone import movements as mv  # noqa: E402
from openalaqs_standalone.compute_movements import compute_all_movements  # noqa: E402
from openalaqs_standalone.validation.tools import (  # noqa: E402
    compute_caep14_reference as ref,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


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
        try:
            import open_alaqs.core.interfaces.Movement as _mov_mod

            if hasattr(_mov_mod, "_mem_traj_cache"):
                _mov_mod._mem_traj_cache.clear()
        except Exception:
            pass


def _copy(tmp_path):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    dst = tmp_path / "training.alaqs"
    shutil.copy(FIXTURE, dst)
    return str(dst)


def _plugin_nox(db, method):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    with sqlite3.connect(db) as conn:
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
    grid = dict(zip(keys, g), reference_altitude=0.0)
    ProjectDatabase().path = db
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="movements",
            grid_config=grid,
            method=method,
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 4, 0),
            time_interval=timedelta(seconds=3600),
        )
    )
    assert result.success, result.error_message
    totals = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            name = str(source.getName())
            if name.startswith("id "):
                oid = int(name.split(":")[0][3:])
                totals[oid] = totals.get(oid, 0.0) + sum(
                    e.transposeToKilograms().getObject("nox_kg") or 0.0
                    for e in emissions
                )
    return totals


def _assert_parity(db, plugin_method, sa_method):
    plugin = _plugin_nox(db, plugin_method)
    with sqlite3.connect(db) as conn:
        sa = compute_all_movements(conn, method=sa_method, use_isa_meteo=False)
    fixed_wing = [oid for oid in sorted(plugin) if oid in sa and oid not in (14, 15)]
    assert fixed_wing, "test premise: fixed-wing movements in both tools"
    for oid in fixed_wing:
        assert sa[oid]["total_em_kg"]["nox"] == pytest.approx(
            plugin[oid], rel=1e-6
        ), f"oid {oid}"


def test_ceiling_without_mixing_height_ignores_study_vertical_limit(tmp_path):
    db = _copy(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_study_setup SET vertical_limit = 300")
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = NULL")
        conn.commit()
        assert mv.get_mixing_height_at(conn, "2025-12-01 06:05:00") == 914.4
        assert ref._mixing_height_at(conn, "2025-12-01 06:05:00") == 914.4
    _assert_parity(db, "bymode", "bymode")


def _gappy_meteo(db):
    """Varied hourly meteo with 04:00 to 07:00 missing on every day: the
    rows nearest to the 06:00 and 07:00 period starts are then the 08:00
    rows, while the latest rows at or before the runway time are 03:00."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE tbl_InvMeteo SET "
            "MixingHeight = 300 + 40 * CAST(substr(DateTime, 12, 2) AS INTEGER), "
            "Temperature = 265 + CAST(substr(DateTime, 12, 2) AS INTEGER)"
        )
        conn.execute(
            "DELETE FROM tbl_InvMeteo "
            "WHERE substr(DateTime, 12, 2) IN ('04', '05', '06', '07')"
        )
        conn.commit()


def test_meteo_row_nearest_to_period_start(tmp_path):
    db = _copy(tmp_path)
    _gappy_meteo(db)
    with sqlite3.connect(db) as conn:
        # 08:00 row (300 + 40 * 8), not the 03:00 row (420)
        assert mv.get_mixing_height_at(conn, "2025-12-01 06:05:00") == 620.0
        assert ref._mixing_height_at(conn, "2025-12-01 06:05:00") == 620.0
        assert mv.get_meteo_at(conn, "2025-12-01 07:30:00", use_isa=False)[
            "T_K"
        ] == pytest.approx(273.0)
    _assert_parity(db, "BFFM2", "bffm2_traj")


def _mini_meteo(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tbl_InvMeteo (DateTime TEXT, Temperature REAL, "
        "SeaLevelPressure REAL, RelativeHumidity REAL, Humidity REAL, "
        "WindSpeed REAL, ObukhovLength REAL, MixingHeight REAL)"
    )
    conn.executemany(
        "INSERT INTO tbl_InvMeteo VALUES (?, 280, 101325, 0.6, 0.005, 3, 99999, ?)",
        rows,
    )
    return conn


@pytest.mark.parametrize(
    "rows,runway_time,expected",
    [
        # before the first row: the plugin takes the first row
        ([("2025-01-01 10:00:00", 500.0)], "2025-01-01 08:40:00", 500.0),
        # tie between 09:00 and 11:00 for the 10:00 period: the earlier row
        (
            [("2025-01-01 09:00:00", 500.0), ("2025-01-01 11:00:00", 700.0)],
            "2025-01-01 10:59:00",
            500.0,
        ),
        # off-hour rows (METAR at hh:50): 09:50 is nearest to 10:00
        (
            [("2025-01-01 09:50:00", 500.0), ("2025-01-01 10:50:00", 700.0)],
            "2025-01-01 10:55:00",
            500.0,
        ),
        # no row: 914.4 m
        ([], "2025-01-01 10:00:00", 914.4),
    ],
)
def test_period_row_rule(rows, runway_time, expected):
    conn = _mini_meteo(rows)
    assert mv.get_mixing_height_at(conn, runway_time) == expected
    assert ref._mixing_height_at(conn, runway_time) == expected

    # The plugin's rule on the same rows (period start = the hour).
    from open_alaqs.core.EmissionCalculation import EmissionCalculation
    from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition

    calc = EmissionCalculation.__new__(EmissionCalculation)
    calc._sorted_ac = [
        AmbientCondition({"DateTime": d, "MixingHeight": h}) for d, h in rows
    ]
    calc._sorted_ac_times = [ac.getDate() for ac in calc._sorted_ac]
    start = datetime.datetime.fromisoformat(runway_time).replace(minute=0, second=0)
    assert calc.getAmbientCondition(start.timestamp()).getMixingHeight() == (
        pytest.approx(expected)
    )
