"""Parallel runways: the standalone keys runways by their full designator.

`movements.get_runways` keyed every runway by its designator number only, so
06L/24R and 06R/24L both mapped to 6 and 24 and the second row won: a movement
on 24R was placed on 24L, with 24L's Touchdown Offset. Runways are now keyed by
the full designator ("24R") only, and `movements.runway_of` refuses, naming the
movement, a plain "24" on parallel runways (it took the first runway of the
table) and a "24R" on a plain 06/24 (it fell back to 06/24 silently). The
plugin (MovementStore.initMovements) refuses the same cases, see
tests/test_parallel_runways_plugin.py.

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
from openalaqs_standalone import runway_checks as rc
from openalaqs_standalone.compute_movements import build_context, compute_for_movement

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"
OID = 1  # A20N arrival on 24, route G4/24/A/1


def make_parallel(src: Path, db: Path) -> Path:
    """A copy of `src` with its runway renamed 06L/24R and a copy 06R/24L."""
    shutil.copy(src, db)
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


@pytest.fixture
def parallel(tmp_path):
    return make_parallel(SRC, tmp_path / "parallel.alaqs")


@pytest.fixture
def single(tmp_path):
    db = tmp_path / "single.alaqs"
    shutil.copy(SRC, db)
    return db


def _set_runway(db, runway, oid=OID):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET runway = ? WHERE oid = ?",
            (runway, oid),
        )


def test_designator():
    assert mv.runway_designator("6l") == "06L"
    assert mv.runway_designator(" 24R ") == "24R"
    assert mv.runway_designator("24") == "24"
    assert mv.runway_designator("") == ""


def test_runways_keyed_by_full_designator_only(parallel):
    with sqlite3.connect(parallel) as conn:
        runways = mv.get_runways(conn)
    left, right = runways["06L"], runways["06R"]
    assert left["runway_id"] == "06L/24R" and right["runway_id"] == "06R/24L"
    assert runways["24R"] is left and runways["24L"] is right
    # no plain-number key: nothing to fall back to
    assert set(runways) == {"06L", "24R", "06R", "24L"}
    assert left["touchdown_offset_m"] == {6: 100.0, 24: 150.0}
    assert right["touchdown_offset_m"] == {6: 300.0, 24: 350.0}


@pytest.mark.parametrize(
    "runway, runway_id, touchdown",
    [("24R", "06L/24R", 150.0), ("24L", "06R/24L", 350.0)],
)
def test_movement_uses_its_own_parallel_runway(parallel, runway, runway_id, touchdown):
    _set_runway(parallel, runway)
    with sqlite3.connect(parallel) as conn:
        mov = mv.get_movement(conn, OID)
        ctx = build_context(conn)
        assert mv.runway_of(ctx["runways"], mov)["runway_id"] == runway_id
        assert (
            rc._Study(conn).runway(mov["runway_direction"], mov["runway_designator"])[
                "runway_id"
            ]
            == runway_id
        )
        res = compute_for_movement(conn, OID, ctx, method="bymode")
    assert res is not None
    assert res["arrival_touchdown_m"] == pytest.approx(touchdown)


def test_plain_number_on_parallel_runways_is_refused(parallel):
    """rc6 review F3: "24" on 06L/24R and 06R/24L took the first runway."""
    _set_runway(parallel, "24")
    with sqlite3.connect(parallel) as conn:
        mov = mv.get_movement(conn, OID)
        ctx = build_context(conn)
        with pytest.raises(ValueError) as err:
            mv.runway_of(ctx["runways"], mov)
        assert str(err.value) == (
            "movement id 1: A20N A 2025-12-01 06:05: runway '24' matches "
            "06L/24R and 06R/24L; name the runway end with its letter"
        )
        with pytest.raises(ValueError, match="matches 06L/24R and 06R/24L"):
            compute_for_movement(conn, OID, ctx, method="bymode")
        assert rc._Study(conn).runway(24, "24") is None
        with pytest.raises(ValueError, match="matches 06L/24R and 06R/24L"):
            rc.check_study(conn)


def test_letter_on_a_plain_runway_is_refused(single):
    """rc6 review F3: "24R" on a plain 06/24 fell back to 06/24 silently."""
    _set_runway(single, "24R")
    with sqlite3.connect(single) as conn:
        mov = mv.get_movement(conn, OID)
        ctx = build_context(conn)
        with pytest.raises(ValueError) as err:
            mv.runway_of(ctx["runways"], mov)
        assert str(err.value) == (
            "movement id 1: A20N A 2025-12-01 06:05: runway '24R' matches no "
            "runway end of the study (runways: 06/24); name the runway end as "
            "in the runway table"
        )
        with pytest.raises(ValueError, match="matches no runway end"):
            compute_for_movement(conn, OID, ctx, method="bymode")
        with pytest.raises(ValueError, match="matches no runway end"):
            rc.check_study(conn)


def test_plain_number_on_a_single_runway_still_works(single):
    with sqlite3.connect(single) as conn:
        mov = mv.get_movement(conn, OID)
        ctx = build_context(conn)
        assert mv.runway_of(ctx["runways"], mov)["runway_id"] == "06/24"
        assert rc._Study(conn).runway(24, "24")["runway_id"] == "06/24"
        assert rc._Study(conn).runway(24)["runway_id"] == "06/24"
