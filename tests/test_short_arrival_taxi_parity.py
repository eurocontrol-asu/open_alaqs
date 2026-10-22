"""An arrival whose block to runway time is no longer than its landing roll.

Since 5.4.0 the arrival's runway time is the touchdown, so the landing roll is
taken out of block - runway time and the taxi time can reach 0 s. The plugin
then skipped every taxi emission (stop-and-go, brake wear, APU) with "taxi
route not defined properly", while the standalone clamps the taxi time to 0
and keeps them. Both now agree for such a movement.

A movement whose block time equals its runway time (taxi time 0 s before the
roll is taken out) was still skipped by the plugin; it now keeps APU,
stop-and-go and brake wear too, with no route or queuing time.
"""

import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()


@pytest.fixture(autouse=True)
def _restore_project_database():
    """Leave the ProjectDatabase singleton (and its path) as other tests set it."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    previous = getattr(ProjectDatabase(), "path", None)
    yield
    ProjectDatabase().path = previous


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "openalaqs_standalone" / "validation" / "data" / "training_v3.alaqs"
POLLUTANTS = ("co", "co2", "hc", "nox", "sox", "pm10")
OID = 1  # A20N arrival, JET-SMALL-A-1, runway time 06:05:00


def _plugin_totals(db: str) -> dict:
    import datetime

    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.EmissionCalculatorService import (
        EmissionCalculationConfig,
        EmissionCalculatorService,
    )

    with sqlite3.connect(db) as conn:
        g = conn.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, "
            "z_resolution, reference_latitude, reference_longitude "
            "FROM grid_3d_definition"
        ).fetchone()
        elev = conn.execute("SELECT airport_elevation FROM user_study_setup").fetchone()
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
    grid = dict(zip(keys, g), reference_altitude=float(elev[0]))
    ProjectDatabase().path = db
    start = datetime.datetime(2025, 12, 1)
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="movement",
            grid_config=grid,
            method="bymode",
            bffm2_ff_source="trajectory",
            should_apply_nox_corrections=False,
            start_dt_inclusive=start,
            end_dt_inclusive=start + timedelta(days=1),
            time_interval=timedelta(seconds=3600),
        )
    )
    assert result.success, result.error_message
    totals = {p: 0.0 for p in POLLUTANTS}
    for _ts, period in result.emissions_data.items():
        for _source, emissions in period:
            for e in emissions:
                kg = e.transposeToKilograms()
                for p in POLLUTANTS:
                    totals[p] += kg.getObject(f"{p}_kg") or 0.0
    return totals


@pytest.fixture
def short_arrival(tmp_path):
    db = tmp_path / "short.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid <> ?", (OID,))
        # 5 s from touchdown to block (shorter than the landing roll), 2 stops
        conn.execute(
            "UPDATE user_aircraft_movements SET block_time = '2025-12-01 06:05:05', "
            "number_of_stop_and_gos = 2 WHERE oid = ?",
            (OID,),
        )
    return db


def _standalone(db, oid: int) -> dict:
    from openalaqs_standalone.compute_movements import (
        build_context,
        compute_for_movement,
    )

    with sqlite3.connect(db) as conn:
        sa = compute_for_movement(
            conn,
            oid,
            build_context(conn),
            method="bymode",
            use_isa_meteo=False,
            apply_nox_corrections=False,
        )
    assert sa is not None
    return sa


def test_short_arrival_keeps_taxi_emissions_like_the_standalone(short_arrival):
    plugin = _plugin_totals(str(short_arrival))
    sa = _standalone(short_arrival, OID)
    assert sa["rollout_time_s"] > 5.0  # the roll is longer than block - runway time
    for p in POLLUTANTS:
        assert plugin[p] == pytest.approx(sa["total_em_kg"][p], rel=2e-4, abs=1e-9), p


@pytest.mark.parametrize("oid", [OID, 2])  # the A20N arrival and a departure
def test_block_time_equal_to_runway_time_keeps_taxi_emissions(tmp_path, oid):
    db = tmp_path / "equal.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid <> ?", (oid,))
        conn.execute(
            "UPDATE user_aircraft_movements SET block_time = runway_time, "
            "number_of_stop_and_gos = 2 WHERE oid = ?",
            (oid,),
        )
    plugin = _plugin_totals(str(db))
    sa = _standalone(db, oid)
    assert sa["taxi_time_s"] == 0.0
    assert sa["stop_em_kg"]["co"] > 0.0
    for p in POLLUTANTS:
        assert plugin[p] == pytest.approx(sa["total_em_kg"][p], rel=2e-4, abs=1e-9), p


def test_movement_without_block_time_is_refused_by_both(tmp_path):
    """No block time: neither implementation guesses a taxi time (the plugin's
    calculation fails, the standalone raises), so they cannot disagree."""
    db = tmp_path / "noblock.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid <> ?", (OID,))
        conn.execute("UPDATE user_aircraft_movements SET block_time = NULL")
    with pytest.raises(AssertionError, match="Not supported value"):
        _plugin_totals(str(db))
    with pytest.raises(TypeError):
        _standalone(db, OID)
