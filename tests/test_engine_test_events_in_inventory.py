"""Regression: engine test events must reach the inventory (*_out.alaqs).

``EngineTestSourceModule`` reads ``engine_test_events`` from the database
being calculated. Before this fix the inventory template had no such table
and Create Output did not copy it, so every engine test site computed to
zero, and loading events while the inventory was open in QGIS failed with
"no such table: engine_test_events".
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.tools.create_output import (  # noqa: E402
    inventory_copy_engine_test_events,
    inventory_create_blank,
)

TEMPLATES = Path(__file__).parents[1] / "open_alaqs" / "core" / "templates"

EVENTS = [
    (
        "TESTPAD_A",
        "RUN-1",
        "2025-12-01T10:00:00",
        "2025-12-01T10:15:00",
        "A20N",
        None,
        None,
        600,
        0,
        120,
        0,
        "snap",
        "1",
    ),
    (
        "TESTPAD_A",
        "RUN-2",
        "2025-12-01T14:00:00",
        "2025-12-01T14:20:00",
        "E75L",
        None,
        1,
        900,
        180,
        0,
        0,
        "bffm2",
        "1",
    ),
]
COLS = (
    "source_id",
    "test_id",
    "start_datetime",
    "end_datetime",
    "aircraft_type",
    "engine_uid",
    "engine_count",
    "t_TX_s",
    "t_AP_s",
    "t_CL_s",
    "t_TO_s",
    "thrust_mode",
    "instudy",
)


@pytest.fixture
def project_with_events(tmp_path):
    project = tmp_path / "study.alaqs"
    shutil.copy(TEMPLATES / "project.alaqs", project)
    with sqlite3.connect(project) as conn:
        conn.executemany(
            f"INSERT INTO engine_test_events ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
            EVENTS,
        )
    saved = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(project)
    yield project
    if saved is not None:
        ProjectDatabase().path = saved


def _events(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            f"SELECT {','.join(COLS)} FROM engine_test_events ORDER BY test_id"
        ).fetchall()


def test_inventory_template_has_engine_test_events_table():
    with sqlite3.connect(TEMPLATES / "inventory.alaqs") as conn:
        inv = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='engine_test_events'"
        ).fetchone()
    with sqlite3.connect(TEMPLATES / "project.alaqs") as conn:
        prj = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='engine_test_events'"
        ).fetchone()
    assert inv is not None, "inventory template lacks engine_test_events"
    assert inv == prj


def test_create_output_copies_engine_test_events(project_with_events, tmp_path):
    out = tmp_path / "study_out.alaqs"
    inventory_create_blank(str(out))
    inventory_copy_engine_test_events(str(out))
    assert _events(out) == [tuple(e) for e in EVENTS]


def test_copy_creates_table_in_older_inventory(project_with_events, tmp_path):
    out = tmp_path / "old_out.alaqs"
    inventory_create_blank(str(out))
    with sqlite3.connect(out) as conn:
        conn.execute("DROP TABLE engine_test_events")
    inventory_copy_engine_test_events(str(out))
    assert _events(out) == [tuple(e) for e in EVENTS]


def test_project_without_table_is_skipped(tmp_path):
    project = tmp_path / "legacy.alaqs"
    shutil.copy(TEMPLATES / "project.alaqs", project)
    with sqlite3.connect(project) as conn:
        conn.execute("DROP TABLE engine_test_events")
    saved = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(project)
    try:
        out = tmp_path / "legacy_out.alaqs"
        inventory_create_blank(str(out))
        inventory_copy_engine_test_events(str(out))
        assert _events(out) == []
    finally:
        if saved is not None:
            ProjectDatabase().path = saved
