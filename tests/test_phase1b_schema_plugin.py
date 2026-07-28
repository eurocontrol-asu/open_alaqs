"""Phase 1b: plugin-side schema tests.

Verifies:
  * ``AreaSources`` dataclass exposes the ``is_test_site`` flag with the
    expected default and TEXT '1'/'0' round-trip.
  * ``EngineTestEventsDatabase`` creates the table with the expected
    schema when instantiated against a scratch database.
  * The ``shapes_area_sources`` column dict on ``AreaSourcesDatabase``
    contains ``is_test_site``.

Requires QGIS Python for the SQLSerializable-based instantiation of
``EngineTestEventsDatabase``, because SQLSerializable imports
``sql_interface`` which pulls in ``qgis.utils.spatialite_connect``.
Run under OSGeo4W shell:

    python-qgis-ltr -m pytest tests/test_phase1b_schema_plugin.py -v
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

try:
    from qgis.core import QgsApplication  # noqa: F401

    from open_alaqs.core.interfaces.AreaSources import (
        AreaSources,
        AreaSourcesDatabase,
    )
    from open_alaqs.core.interfaces.EngineTestEvents import (
        EngineTestEventsDatabase,
    )

    HAS_QGIS = True
except Exception:  # pragma: no cover
    HAS_QGIS = False


pytestmark = pytest.mark.skipif(
    not HAS_QGIS, reason="QGIS Python not importable in this environment"
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset the Singleton caches on the two Database classes before every
    test so each test instantiates a fresh instance against its own
    tempfile. Without this, a Database created by an earlier test (in this
    file or the wider suite) is returned by the Singleton metaclass and
    still points at a now-deleted temp path, causing INSERT/SELECT against
    the current test's tempfile to see an empty database.
    """
    if HAS_QGIS:
        AreaSourcesDatabase.reset()
        EngineTestEventsDatabase.reset()
    yield
    if HAS_QGIS:
        AreaSourcesDatabase.reset()
        EngineTestEventsDatabase.reset()


# ---------------------------------------------------------------------------
# AreaSources dataclass: is_test_site flag
# ---------------------------------------------------------------------------


def test_area_sources_is_test_site_default_false():
    """A row with no is_test_site field is treated as a normal area source
    (False), preserving backward compatibility with pre-v1b rows.
    """
    src = AreaSources({"source_id": "A1"})
    assert src.isTestSite() is False


def test_area_sources_is_test_site_true_when_flagged():
    """A row with is_test_site='1' is a test site."""
    src = AreaSources({"source_id": "A1", "is_test_site": "1"})
    assert src.isTestSite() is True


def test_area_sources_is_test_site_zero_string_false():
    """A row with is_test_site='0' is not a test site."""
    src = AreaSources({"source_id": "A1", "is_test_site": "0"})
    assert src.isTestSite() is False


def test_area_sources_is_test_site_setter():
    """setTestSite flips the flag."""
    src = AreaSources({"source_id": "A1"})
    src.setTestSite(True)
    assert src.isTestSite() is True
    src.setTestSite(False)
    assert src.isTestSite() is False


# ---------------------------------------------------------------------------
# AreaSourcesDatabase: columns dict contains is_test_site
# ---------------------------------------------------------------------------


def test_area_sources_database_columns_dict_has_is_test_site():
    """The static column-definition dict on the database class contains
    is_test_site so the template pipeline creates the column on new
    projects.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        # deserialize=False: the test is about the class's column dict,
        # not the DB state. Instantiating against an empty tempfile with
        # deserialize=True would run SELECT against a non-existent table
        # and raise sqlite3.OperationalError before the assertion runs.
        db = AreaSourcesDatabase(tmp, deserialize=False)
        cols = list(db._table_columns.keys())
        assert "is_test_site" in cols, f"is_test_site absent from cols: {cols}"
        # Positioned after instudy per convention
        assert cols.index("is_test_site") > cols.index("instudy")
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# EngineTestEventsDatabase: table creation and defaults
# ---------------------------------------------------------------------------


def test_engine_test_events_table_created():
    """recreate_table creates the engine_test_events table with the
    expected column set.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        db = EngineTestEventsDatabase(tmp)
        db.recreate_table()
        with sqlite3.connect(tmp) as c:
            info = c.execute("PRAGMA table_info(engine_test_events)").fetchall()
        col_names = [r[1] for r in info]
        assert col_names == [
            "event_id",
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
        ]
    finally:
        os.unlink(tmp)


def test_engine_test_events_defaults():
    """A row inserted with only required fields picks up the defaults
    (zero seconds, 'snap' thrust mode, in-study).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        db = EngineTestEventsDatabase(tmp)
        db.recreate_table()
        with sqlite3.connect(tmp) as c:
            c.execute(
                "INSERT INTO engine_test_events "
                "(source_id, start_datetime, end_datetime, aircraft_type) "
                "VALUES (?, ?, ?, ?)",
                ("N1", "2024-12-01T09:15:00", "2024-12-01T09:45:00", "C56X"),
            )
            row = c.execute(
                "SELECT t_TX_s, t_AP_s, t_CL_s, t_TO_s, thrust_mode, instudy "
                "FROM engine_test_events"
            ).fetchone()
        assert row == (0, 0, 0, 0, "snap", "1")
    finally:
        os.unlink(tmp)


def test_engine_test_events_source_id_not_null_enforced():
    """SQLite enforces the NOT NULL constraint on source_id."""
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        db = EngineTestEventsDatabase(tmp)
        db.recreate_table()
        with sqlite3.connect(tmp) as c:
            with pytest.raises(sqlite3.IntegrityError):
                c.execute(
                    "INSERT INTO engine_test_events "
                    "(start_datetime, end_datetime, aircraft_type) "
                    "VALUES (?, ?, ?)",
                    ("2024-12-01T09:15:00", "2024-12-01T09:45:00", "C56X"),
                )
    finally:
        os.unlink(tmp)
