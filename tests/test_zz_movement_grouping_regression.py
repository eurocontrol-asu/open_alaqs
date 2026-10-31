"""Regression: movements calculated together must not share per-movement inputs.

MovementSourceModule computes the flight emissions once per group of movements
with the same engine, profile, runway and taxi route. The group's first
movement supplied the aircraft (engine count) and the take-off weight ratio of
the NOx correction, so a second movement of the group with another aircraft
type or another tow_ratio got the first one's flight emissions.

Each test adds a copy of an A20N departure of the training_v3 fixture in the
same hour, on the same engine, profile, runway and taxi route, with one input
changed, and requires its result to equal the copy calculated alone.

The trajectory at the runway also follows the movement's track (shapes_tracks)
and its runway direction; a movement with a track took the trajectory of a
group member without one (test_track_is_not_shared_within_a_group).
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


# A departure track from the north-east end of runway 06/24 of the fixture
# (EPSG:3857), turning east: its trajectory differs from the straight profile.
TRACK_WKT = (
    "LineStringZ (495940.69 6793405.68 0, 498500 6795060 0, 501000 6797500 0, "
    "506000 6798500 0, 512000 6797000 0)"
)


def _add_track(db_path, track_id):
    """Add a departure track to shapes_tracks through the QGIS provider."""
    from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer

    layer = QgsVectorLayer(
        f"dbname='{db_path}' table=\"shapes_tracks\" (geometry) sql=",
        "tracks",
        "spatialite",
    )
    assert layer.isValid()
    feature = QgsFeature(layer.fields())
    feature.setAttribute("track_id", track_id)
    feature.setAttribute("runway", "06/24")
    feature.setAttribute("departure_arrival", "D")
    feature.setAttribute("instudy", 1)
    feature.setGeometry(QgsGeometry.fromWkt(TRACK_WKT))
    assert layer.startEditing()
    assert layer.addFeature(feature)
    assert layer.commitChanges(), layer.commitErrors()


def _prepare(tmp_path, name, keep_original, track=None, **changes):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    dst = tmp_path / name
    shutil.copy(SRC, dst)
    if track:
        _add_track(str(dst), track)
    with sqlite3.connect(dst) as conn:
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(user_aircraft_movements)")
        ]
        row = dict(
            zip(
                cols,
                conn.execute(
                    "SELECT * FROM user_aircraft_movements WHERE oid = 2"
                ).fetchone(),
            )
        )
        new = dict(row)
        new["oid"] = conn.execute(
            "SELECT MAX(oid) + 1 FROM user_aircraft_movements"
        ).fetchone()[0]
        new.update(changes)
        conn.execute(
            "INSERT INTO user_aircraft_movements (%s) VALUES (%s)"
            % (",".join(cols), ",".join("?" * len(cols))),
            [new[c] for c in cols],
        )
        if not keep_original:
            conn.execute("DELETE FROM user_aircraft_movements WHERE oid = 2")
        conn.commit()
    return str(dst), new["oid"]


def _nox_by_movement(db_path, nox_corrections):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    ProjectDatabase().path = db_path
    cfg = EmissionCalculationConfig(
        db_path=db_path,
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="bymode",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 7),
        time_interval=timedelta(seconds=3600),
        should_apply_nox_corrections=nox_corrections,
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


def _check(tmp_path, nox_corrections, track=None, **changes):
    both_db, new_oid = _prepare(tmp_path, "both.alaqs", True, track, **changes)
    totals_both = _nox_by_movement(both_db, nox_corrections)
    _reset_singletons()
    alone_db, new_oid_alone = _prepare(tmp_path, "alone.alaqs", False, track, **changes)
    totals_alone = _nox_by_movement(alone_db, nox_corrections)

    original = _value_for_oid(totals_both, 2)
    together = _value_for_oid(totals_both, new_oid)
    alone = _value_for_oid(totals_alone, new_oid_alone)
    assert alone != pytest.approx(
        original, rel=1e-3
    ), "test premise: the changed movement must differ from the original"
    assert together == pytest.approx(alone, rel=1e-9), (
        f"changed movement got {together} kg NOx next to the original "
        f"({original} kg), but {alone} kg on its own"
    )


def test_tow_ratio_is_not_shared_within_a_group(tmp_path):
    _check(tmp_path, True, tow_ratio=0.8)


def test_engine_count_is_not_shared_within_a_group(tmp_path):
    # A4 has one engine (default_aircraft), the A20N two; the movement keeps
    # the A20N engine and profile.
    _check(tmp_path, False, aircraft="A4")


def test_gate_emissions_code_is_not_shared_within_a_group(tmp_path):
    # Same gate, aircraft group and direction as the original, but with the
    # gate emissions switched (the fixture's departure has code 0).
    _check(tmp_path, False, gate_emissions_code=1)


def test_track_is_not_shared_within_a_group(tmp_path):
    # Same engine, profile, runway and taxi route as the original, but flown
    # along a track: its trajectory, and so its emissions, differ.
    _check(tmp_path, False, track="T1", track_id="T1")
