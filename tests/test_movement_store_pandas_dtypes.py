"""MovementStore builds its movement table without pandas FutureWarnings.

initMovements created the per-movement table with all-NaN columns and then
`fillna(np.nan)`, which downcast them to float64; every later assignment of
a name or an object (aircraft, engine, runway, gate, taxi route, profile,
trajectories) raised "Setting an item of incompatible dtype is deprecated",
an error in a future pandas. The columns are now object columns.
"""

import shutil
import sqlite3
import warnings
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


@pytest.fixture(autouse=True)
def _restore_project_database():
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    previous = getattr(ProjectDatabase(), "path", None)
    yield
    ProjectDatabase().path = previous


def test_init_movements_emits_no_future_warning(tmp_path):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore
    from open_alaqs.core.tools.Singleton import Singleton

    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM user_aircraft_movements").fetchone()[0]
    Singleton.reset_all()
    ProjectDatabase().path = str(db)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            store = MovementStore(str(db), show_progress=False)
        assert len(store.getObjects()) == n
    finally:
        Singleton.reset_all()
    ours = [
        f"{Path(w.filename).name}:{w.lineno}: {w.message}"
        for w in caught
        if issubclass(w.category, FutureWarning) and "open_alaqs" in w.filename
    ]
    assert ours == []
