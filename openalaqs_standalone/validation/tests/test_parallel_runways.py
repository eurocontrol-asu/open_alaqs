"""Parallel runways: the standalone keys runways by their full designator.

`movements.get_runways` keyed every runway by its designator number only, so
06L/24R and 06R/24L both mapped to 6 and 24 and the second row won: a movement
on 24R was placed on 24L, with 24L's Touchdown Offset. The plugin keys by name.
Runways are now also keyed by the full designator ("24R"); a movement that
names a plain number ("24") still finds a runway (the first of the table, as
the plugin's name match).

Fixture: ``training_v3.alaqs`` with its runway renamed 06L/24R and a copy
06R/24L added, each with its own touchdown offset (the copy keeps the
geometry: only the runway selected matters here).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import movements as mv
from openalaqs_standalone.compute_movements import build_context, compute_for_movement
from openalaqs_standalone.runway_checks import _Study

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"
OID = 1  # A20N arrival on 24, route G4/24/A/1


@pytest.fixture
def parallel(tmp_path):
    db = tmp_path / "parallel.alaqs"
    shutil.copy(SRC, db)
    with sqlite3.connect(db) as conn:
        # the insert trigger checks the geometry with SpatiaLite functions
        conn.execute("DROP TRIGGER IF EXISTS ggi_shapes_runways_geometry")
        conn.execute(
            "UPDATE shapes_runways SET runway_id = '06L/24R', touchdown = 100, "
            "touchdown_2 = 150"
        )
        conn.execute(
            "INSERT INTO shapes_runways (oid, runway_id, touchdown, instudy, "
            "geometry, touchdown_2) SELECT 2, '06R/24L', 300, instudy, geometry, "
            "350 FROM shapes_runways WHERE oid = 1"
        )
    return db


def test_designator():
    assert mv.runway_designator("6l") == "06L"
    assert mv.runway_designator(" 24R ") == "24R"
    assert mv.runway_designator("24") == "24"
    assert mv.runway_designator("") == ""


def test_runways_keyed_by_full_designator(parallel):
    with sqlite3.connect(parallel) as conn:
        runways = mv.get_runways(conn)
    left, right = runways["06L"], runways["06R"]
    assert left["runway_id"] == "06L/24R" and right["runway_id"] == "06R/24L"
    assert runways["24R"] is left and runways["24L"] is right
    # plain numbers: the first runway of the table
    assert runways[6] is left and runways[24] is left
    assert left["touchdown_offset_m"] == {6: 100.0, 24: 150.0}
    assert right["touchdown_offset_m"] == {6: 300.0, 24: 350.0}


@pytest.mark.parametrize(
    "runway, runway_id, touchdown",
    [("24R", "06L/24R", 150.0), ("24L", "06R/24L", 350.0), ("24", "06L/24R", 150.0)],
)
def test_movement_uses_its_own_parallel_runway(parallel, runway, runway_id, touchdown):
    with sqlite3.connect(parallel) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET runway = ? WHERE oid = ?",
            (runway, OID),
        )
        mov = mv.get_movement(conn, OID)
        ctx = build_context(conn)
        assert mv.runway_of(ctx["runways"], mov)["runway_id"] == runway_id
        assert (
            _Study(conn).runway(mov["runway_direction"], mov["runway_designator"])[
                "runway_id"
            ]
            == runway_id
        )
        res = compute_for_movement(conn, OID, ctx, method="bymode")
    assert res is not None
    assert res["arrival_touchdown_m"] == pytest.approx(touchdown)
