"""The taxi route is oriented by its own gate, not the movement's gate.

The runway trajectory (landing roll, exit, runway stretch) is computed once
per (runway, direction, taxi route, profile, track) group and cached without
the gate, so the route must be oriented by its own gate
(user_taxiroute_taxiways.gate), as the standalone and the CAEP14 reference
do. The plugin used the gate of the first movement of the group.
"""

import shutil
import sqlite3
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


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


def test_route_is_oriented_by_the_route_gate(tmp_path, monkeypatch):
    from open_alaqs.core import GeoTransformation
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Gate import GateStore
    from open_alaqs.core.interfaces.Movement import MovementStore
    from open_alaqs.core.tools.Singleton import Singleton

    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid <> 1")
        # Movement 1 takes route G4/24/A/1 but stands at G7
        conn.execute("UPDATE user_aircraft_movements SET gate = 'G7' WHERE oid = 1")
        table = MovementStore._TRAJ_CACHE_TABLE
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?", (table,)
        ).fetchone():
            conn.execute(f"DELETE FROM {table}")

    seen = []
    original = GeoTransformation.TrajectoryTransformer.__init__

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("gate_geometry_text"))
        original(self, *args, **kwargs)

    monkeypatch.setattr(GeoTransformation.TrajectoryTransformer, "__init__", spy)
    Singleton.reset_all()
    ProjectDatabase().path = str(db)
    try:
        MovementStore(str(db), show_progress=False)
        gates = GateStore()
        assert seen, "no runway alignment was computed"
        assert seen == [gates.getObject("G4").getGeometryText()]
        assert seen[0] != gates.getObject("G7").getGeometryText()
    finally:
        Singleton.reset_all()


def test_route_is_oriented_by_its_own_flag_like_the_standalone(tmp_path, monkeypatch):
    """A departure that takes an arrival route: the route is oriented as an
    arrival route (towards its gate), by the route's departure_arrival flag,
    as the standalone does; the plugin used the movement's flag."""
    from open_alaqs.core import GeoTransformation
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore
    from open_alaqs.core.tools.Singleton import Singleton
    from openalaqs_standalone.runway_placement import route_parts_from_study

    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    route = "G4/06/A/1"
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid <> 2")
        assert conn.execute(
            "SELECT departure_arrival FROM user_aircraft_movements"
        ).fetchone() == ("D",)
        assert conn.execute(
            "SELECT departure_arrival FROM user_taxiroute_taxiways WHERE route_name = ?",
            (route,),
        ).fetchone() == ("A",)
        conn.execute("UPDATE user_aircraft_movements SET taxi_route = ?", (route,))
        table = MovementStore._TRAJ_CACHE_TABLE
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?", (table,)
        ).fetchone():
            conn.execute(f"DELETE FROM {table}")
        standalone = route_parts_from_study(conn, route)

    seen = []
    original = GeoTransformation.TrajectoryTransformer._route_lines

    def spy(self, is_dep):
        lines = original(self, is_dep)
        seen.append((is_dep, lines))
        return lines

    monkeypatch.setattr(GeoTransformation.TrajectoryTransformer, "_route_lines", spy)
    Singleton.reset_all()
    ProjectDatabase().path = str(db)
    try:
        MovementStore(str(db), show_progress=False)
    finally:
        Singleton.reset_all()
    assert seen, "no runway alignment was computed"
    is_dep, plugin = seen[0]
    assert is_dep  # the movement is a departure
    assert len(plugin) == len(standalone) > 1

    def coords(lines):
        return [[tuple(round(v, 3) for v in c[:2]) for c in ln.coords] for ln in lines]

    assert coords(plugin) == coords(standalone)
