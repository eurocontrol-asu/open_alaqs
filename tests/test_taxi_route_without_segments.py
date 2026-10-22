"""A taxi route without segments keeps the stand emissions of the movement.

TaxiingEmissionCalculator adds queuing, APU, engine start, stop-and-go and
brake wear to the last segment of the route, so a route whose taxiways do not
exist (no segments) added nothing: the movement lost them silently, with the
0 s taxi warning saying they were still counted. They are now placed at the
gate on a stand-in segment of 0 m and 0 s. Not reachable with the bundled
studies (every route of training_v3 has segments).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)
OID = 1  # A20N arrival (MTOW above 18,632 kg: brake wear applies)


@pytest.fixture(autouse=True)
def _restore_project_database():
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.tools.Singleton import Singleton

    previous = getattr(ProjectDatabase(), "path", None)
    Singleton.reset_all()
    yield
    Singleton.reset_all()
    ProjectDatabase().path = previous


def _movement(tmp_path, stops):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore

    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET number_of_stop_and_gos = ?, "
            "apu_code = 1 WHERE oid = ?",
            (stops, OID),
        )
    ProjectDatabase().path = str(db)
    return MovementStore(str(db), show_progress=False).getObject(OID)


def _kg(emissions, pollutant):
    return sum(
        e.transposeToKilograms().getObject(f"{pollutant}_kg") or 0.0
        for em in emissions
        for e in em["emissions"]
    )


def test_route_without_segments_keeps_stand_emissions(tmp_path, caplog):
    import logging

    from open_alaqs.core.interfaces.Taxiway import TaxiwayRoute
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    movement = _movement(tmp_path, stops=2)
    route = movement.getTaxiRoute()
    with_segments = TaxiingEmissionCalculator(movement).calculate_emissions()
    assert len(with_segments) >= len(route.getSegments()) >= 1  # plus a runway stretch

    empty = TaxiwayRoute(
        {
            "route_name": route.getName(),
            "gate": route.getGate(),
            "runway": "24",
            "departure_arrival": "A",
        }
    )
    assert empty.getSegments() == []
    movement.setTaxiRoute(empty)
    with caplog.at_level(logging.DEBUG):
        emissions = TaxiingEmissionCalculator(movement).calculate_emissions()
    # one warning names the route; the empty geometry is not an error (rc7 N3)
    records = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "Track" not in r.getMessage()
    ]
    assert [r.levelno for r in records] == [logging.WARNING]
    assert "has no segments" in records[0].getMessage()

    # the stand-in segment (the arrival's runway stretch, from the placement
    # of the profile, is the other entry)
    stand = [em for em in emissions if em["distance_space"] == 0.0]
    assert len(stand) == 1 and len(emissions) <= 2
    (em,) = stand[0]["emissions"]
    assert em.getGeometryText() == movement.getGate().getGeometryText()
    # stop-and-go (2 stops at idle) and the queuing time burn fuel
    assert _kg(stand, "fuel") > 0.0
    assert _kg(stand, "nox") > 0.0
    # brake wear of the arrival
    assert _kg(stand, "pm10") > 0.0
    # the stand emissions are the same whether the route has segments or not
    # (the route time of the segments is what differs): no more than with them
    assert _kg(emissions, "nox") <= _kg(with_segments, "nox")
