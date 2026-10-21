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

from qgis.testing import start_app

start_app()

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
    from open_alaqs.core.alaqsdblite import Singleton as DbSingleton
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
    DbSingleton._instances.clear()
    ProjectDatabase().path = str(db)
    try:
        MovementStore(str(db), show_progress=False)
        gates = GateStore()
        assert seen, "no runway alignment was computed"
        assert seen == [gates.getObject("G4").getGeometryText()]
        assert seen[0] != gates.getObject("G7").getGeometryText()
    finally:
        Singleton.reset_all()
