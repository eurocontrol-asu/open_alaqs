"""Regression: helicopters of different types must not share one flight emission.

MovementSourceModule groups movements by (engine, profile_id, runway, taxi route)
and computes each group once. Helicopters carry an empty engine on the movement
(their engine lives on the Helicopter object), so without the aircraft type in
the key every helicopter type on the same profile and runway received the
emissions of the first member of the group.

The test adds an R44 departure (piston, HIO-540) next to the AS50 departure
(turboshaft, ARRIEL 1D1) of the training_v3 fixture, on the same runway with the
same empty profile, and requires the R44 result to equal the R44 computed alone.
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
    """Same isolation as test_zz_bymode_analytical_regression: the stores are
    singletons keyed to the first database path they see."""
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


def _prepare(tmp_path, name, keep_as50):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    dst = tmp_path / name
    shutil.copy(SRC, dst)
    with sqlite3.connect(dst) as conn:
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(user_aircraft_movements)")
        ]
        row = dict(
            zip(
                cols,
                conn.execute(
                    "SELECT * FROM user_aircraft_movements "
                    "WHERE aircraft = 'AS50' AND departure_arrival = 'D'"
                ).fetchone(),
            )
        )
        new = dict(row)
        new["oid"] = conn.execute(
            "SELECT MAX(oid) + 1 FROM user_aircraft_movements"
        ).fetchone()[0]
        new["aircraft"] = "R44"
        new["runway_time"] = "2025-12-01 06:45:00"
        new["block_time"] = "2025-12-01 06:45:00"
        conn.execute(
            "INSERT INTO user_aircraft_movements (%s) VALUES (%s)"
            % (",".join(cols), ",".join("?" * len(cols))),
            [new[c] for c in cols],
        )
        if not keep_as50:
            conn.execute("DELETE FROM user_aircraft_movements WHERE aircraft = 'AS50'")
        conn.commit()
    return str(dst), new["oid"]


def _nox_by_movement(db_path):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    ProjectDatabase().path = db_path
    cfg = EmissionCalculationConfig(
        db_path=db_path,
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="bymode",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 9),
        time_interval=timedelta(seconds=3600),
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    totals = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            name = str(source.getName())
            totals[name] = totals.get(name, 0.0) + sum(
                e.transposeToKilograms().getObject("nox_kg") or 0.0 for e in emissions
            )
    return totals


def _value_for_oid(totals, oid):
    hits = [v for k, v in totals.items() if k.startswith(f"id {oid}:")]
    assert len(hits) == 1, f"movement {oid} not found in {list(totals)}"
    return hits[0]


def _reset_singletons():
    from open_alaqs.core.alaqsdblite import Singleton

    Singleton._instances.clear()
    import open_alaqs.core.interfaces.Movement as _mov_mod

    if hasattr(_mov_mod, "_mem_traj_cache"):
        _mov_mod._mem_traj_cache.clear()


def test_two_helicopter_types_on_same_profile_do_not_share_emissions(tmp_path):
    both_db, r44_oid = _prepare(tmp_path, "both.alaqs", keep_as50=True)
    totals_both = _nox_by_movement(both_db)
    as50_oid = [int(k.split(":")[0][3:]) for k in totals_both if " AS50 D " in k][0]

    _reset_singletons()
    alone_db, r44_oid_alone = _prepare(tmp_path, "alone.alaqs", keep_as50=False)
    totals_alone = _nox_by_movement(alone_db)

    r44_with_as50 = _value_for_oid(totals_both, r44_oid)
    r44_alone = _value_for_oid(totals_alone, r44_oid_alone)
    as50 = _value_for_oid(totals_both, as50_oid)

    assert r44_alone > 0.0
    assert r44_alone != pytest.approx(
        as50, rel=1e-3
    ), "test premise: R44 and AS50 must have different emissions"
    assert r44_with_as50 == pytest.approx(r44_alone, rel=1e-9), (
        f"R44 got {r44_with_as50} kg NOx next to an AS50 ({as50} kg), "
        f"but {r44_alone} kg on its own"
    )
