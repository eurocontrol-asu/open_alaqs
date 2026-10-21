"""The movement module's airport altitude is the study's airport elevation.

It feeds the NOx ambient correction, the MEEM V1 ISA temperature and the LTO
cut. The standalone and the CAEP14 reference read
user_study_setup.airport_elevation; the plugin took the grid reference
altitude of the Dispersion dialog, which the user can set differently. The
grid altitude is now only the fallback for a study without an elevation.
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


def _module(db, reference_altitude):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.modules.MovementSourceModule import MovementSourceModule

    ProjectDatabase().path = str(db)
    return MovementSourceModule(
        {
            "database_path": str(db),
            "method": "bymode",
            "reference_altitude": reference_altitude,
            "show_progress": False,
        }
    )


def test_airport_altitude_is_the_study_elevation(tmp_path):
    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_study_setup SET airport_elevation = 1655")
    assert _module(db, reference_altitude=40.0).getAirportAltitude() == 1655.0


def test_grid_altitude_when_the_study_has_no_elevation(tmp_path):
    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE user_study_setup SET airport_elevation = NULL")
    assert _module(db, reference_altitude=40.0).getAirportAltitude() == 40.0
