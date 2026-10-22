"""Parallel runways in the plugin: a movement's runway must name one runway end.

MovementStore.initMovements matched the movement's runway as a substring of
the runway names: a plain "24" on a study with 06L/24R and 06R/24L matched
both (a warning "found in the DB multiple times", the first runway taken),
the runway direction "24" was then not an end of that runway and the
trajectory placement failed ("Could not find runway direction"), so the
movement was silently absent from the results. "24R" on a plain 06/24 study
matched nothing (a warning) and the movement was dropped the same way.

rc6 review F3: both now stop the calculation with a readable error naming
the movement (the exception path the inventory dialog reports as
"Calculation Failed"), as the standalone's `movements.runway_of` does
(openalaqs_standalone/validation/tests/test_parallel_runways.py). Full
designators work in both.
"""

import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

from openalaqs_standalone.validation.tests.test_parallel_runways import (
    SRC,
    make_parallel,
)

start_app()

OID = 1  # A20N arrival on 24


@pytest.fixture(autouse=True)
def _restore_project_database():
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.tools.Singleton import Singleton

    previous = getattr(ProjectDatabase(), "path", None)
    Singleton.reset_all()
    yield
    Singleton.reset_all()
    ProjectDatabase().path = previous


def _store(db: Path):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore

    ProjectDatabase().path = str(db)
    return MovementStore(str(db), show_progress=False)


def _parallel(tmp_path) -> Path:
    """The two-parallel-runway study with every movement on a full
    designator (06 on 06L, 24 on 24R): the plugin checks the whole study."""
    db = make_parallel(SRC, tmp_path / "parallel.alaqs")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET runway = '06L' WHERE runway = '06'"
        )
        conn.execute(
            "UPDATE user_aircraft_movements SET runway = '24R' WHERE runway = '24'"
        )
    return db


def _set_runway(db: Path, runway: str, oid: int = OID):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET runway = ? WHERE oid = ?",
            (runway, oid),
        )


@pytest.mark.parametrize("runway, runway_id", [("24R", "06L/24R"), ("24L", "06R/24L")])
def test_full_designator_selects_its_parallel_runway(tmp_path, runway, runway_id):
    db = _parallel(tmp_path)
    _set_runway(db, runway)
    store = _store(db)
    mov = store.getObject(OID)
    assert mov.getRunway().getName() == runway_id
    assert mov.getRunwayDirection() == runway
    assert mov.getTrajectoryAtRunway() is not None


def test_plain_number_on_parallel_runways_stops_the_calculation(tmp_path):
    db = _parallel(tmp_path)
    _set_runway(db, "24")
    with pytest.raises(ValueError) as err:
        _store(db)
    assert str(err.value) == (
        "movement id 1: A20N A 2025-12-01 06:05: runway '24' matches 06L/24R "
        "and 06R/24L; name the runway end with its letter"
    )


def test_letter_on_a_plain_runway_stops_the_calculation(tmp_path):
    db = tmp_path / "single.alaqs"
    db.write_bytes(SRC.read_bytes())
    _set_runway(db, "24R")
    with pytest.raises(ValueError) as err:
        _store(db)
    assert str(err.value) == (
        "movement id 1: A20N A 2025-12-01 06:05: runway '24R' matches no runway "
        "end of the study (runways: 06/24); name the runway end as in the "
        "runway table"
    )


def test_several_movements_are_listed(tmp_path):
    db = _parallel(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_aircraft_movements SET runway = '24'")
        n = conn.execute(
            "SELECT COUNT(*) FROM user_aircraft_movements WHERE runway = '24'"
        ).fetchone()[0]
    with pytest.raises(ValueError) as err:
        _store(db)
    message = str(err.value)
    assert message.startswith("movements id 1: A20N A 2025-12-01 06:05; id ")
    assert f"; {n - 3} more: runway '24' matches 06L/24R and 06R/24L" in message


def test_plain_number_on_a_single_runway_still_works(tmp_path):
    db = tmp_path / "single.alaqs"
    db.write_bytes(SRC.read_bytes())
    store = _store(db)
    mov = store.getObject(OID)
    assert mov.getRunway().getName() == "06/24"
    assert mov.getRunwayDirection() == "24"
    assert mov.getTrajectoryAtRunway() is not None


def test_get_runway_by_direction_refuses_an_ambiguous_end(tmp_path):
    """ADS-B import: an ambiguous or unknown end gives no runway (it took
    the first) and the import falls back to the closest track point."""
    from open_alaqs.core.alaqs import get_runway_by_direction
    from open_alaqs.core.interfaces.Runway import RunwayStore

    db = make_parallel(SRC, tmp_path / "parallel.alaqs")
    store = RunwayStore(str(db))
    assert get_runway_by_direction("24R", store)[1].getName() == "06L/24R"
    assert get_runway_by_direction("6r", store)[1].getName() == "06R/24L"
    assert get_runway_by_direction("24", store) == (False, None)
    assert get_runway_by_direction("24C", store) == (False, None)


def test_letter_that_matches_no_parallel_runway_is_unknown_not_ambiguous(tmp_path):
    """ "24C" on 06L/24R + 06R/24L is unknown: the message must not ask for a
    letter that was given (rc7 review N1)."""
    db = _parallel(tmp_path)
    _set_runway(db, "24C")
    with pytest.raises(ValueError) as err:
        _store(db)
    assert str(err.value) == (
        "movement id 1: A20N A 2025-12-01 06:05: runway '24C' matches no runway "
        "end of the study (runways: 06L/24R, 06R/24L); name the runway end as in "
        "the runway table"
    )


def test_message_echoes_the_normalised_end(tmp_path):
    """A single-digit end is echoed as the two-digit end, as the standalone
    does (rc7 review N2)."""
    db = _parallel(tmp_path)
    _set_runway(db, "6")
    with pytest.raises(ValueError) as err:
        _store(db)
    assert "runway '06' matches 06L/24R and 06R/24L" in str(err.value)
