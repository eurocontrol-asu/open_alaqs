"""Tests for ``_copy_shape_table_schema_robust`` in
``open_alaqs.core.tools.create_output``.

Covers the schema-robustness invariants:
  * A destination column absent from the source (like ``is_test_site``
    added to ``shapes_area_sources`` by Phase 1b) does not raise; the row
    is inserted with the destination column taking its DEFAULT value.
  * A source column absent from the destination is ignored (used to
    happen with legacy ``max_queue_speed`` / ``peak_queue_time`` on
    ``shapes_runways``).
  * When the source table is empty the destination stays empty and no
    exception is raised.
  * When the source table is entirely missing the helper returns a
    skip-status string, does not raise.

Runs QGIS-free: uses raw sqlite3 fixtures and monkeypatches
``alaqsdblite.ProjectDatabase`` / ``alaqsdblite.query_string`` so no
plugin bootstrap is needed.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

try:
    from open_alaqs.core.tools.create_output import (
        _copy_shape_table_schema_robust,
    )

    HAS_MODULE = True
except Exception:  # pragma: no cover
    HAS_MODULE = False


pytestmark = pytest.mark.skipif(
    not HAS_MODULE, reason="open_alaqs core tools not importable"
)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def source_and_dest(tmp_path, monkeypatch):
    """Two independent SQLite dbs, plus monkeypatches so the helper uses
    them. Yields a tuple ``(dst_conn, dst_cursor, src_path)``.
    """
    from open_alaqs.core import alaqsdblite

    src_path = tempfile.NamedTemporaryFile(
        suffix=".alaqs", delete=False, dir=tmp_path
    ).name
    dst_path = tempfile.NamedTemporaryFile(
        suffix=".alaqs", delete=False, dir=tmp_path
    ).name

    # ProjectDatabase is a Singleton. Provide a stub whose ``.path``
    # attribute returns the src_path.
    class _StubProject:
        path = src_path

    monkeypatch.setattr(alaqsdblite, "ProjectDatabase", lambda: _StubProject)

    def _query_string(sql: str) -> list:
        # Minimal reimplementation over src_path; mirrors the return
        # shape of the real query_string (list of tuples), used only for
        # SELECT.
        with sqlite3.connect(src_path) as _c:
            return _c.execute(sql.rstrip(";")).fetchall()

    monkeypatch.setattr(alaqsdblite, "query_string", _query_string)

    dst_conn = sqlite3.connect(dst_path)
    dst_cursor = dst_conn.cursor()

    yield src_path, dst_conn, dst_cursor

    dst_conn.close()


# ── Tests ───────────────────────────────────────────────────────────────


def test_helper_copies_matching_schema(source_and_dest):
    """Baseline: source and destination have identical schemas. Rows copy
    row-for-row."""
    src_path, dst_conn, dst_cursor = source_and_dest
    ddl = """
        CREATE TABLE shapes_area_sources (
            oid INTEGER, source_id TEXT, height REAL, instudy TEXT
        )
    """
    with sqlite3.connect(src_path) as sc:
        sc.execute(ddl)
        sc.executemany(
            "INSERT INTO shapes_area_sources (oid, source_id, height, instudy) "
            "VALUES (?, ?, ?, ?)",
            [(1, "A1", 3.0, "1"), (2, "A2", 4.5, "1")],
        )
    dst_cursor.execute(ddl)

    msg = _copy_shape_table_schema_robust(dst_cursor, dst_conn, "shapes_area_sources")
    assert "copied to output file" in msg

    rows = dst_cursor.execute(
        "SELECT oid, source_id, height, instudy FROM shapes_area_sources "
        "ORDER BY oid"
    ).fetchall()
    assert rows == [(1, "A1", 3.0, "1"), (2, "A2", 4.5, "1")]


def test_helper_destination_has_extra_column_takes_default(source_and_dest):
    """Regression for the Phase 1b bug: destination has a new column
    (``is_test_site``) that the source lacks. Rows must still copy; the
    new column takes its DEFAULT.
    """
    src_path, dst_conn, dst_cursor = source_and_dest
    # Source: v1b-minus-1 schema (no is_test_site)
    with sqlite3.connect(src_path) as sc:
        sc.execute(
            """
            CREATE TABLE shapes_area_sources (
                oid INTEGER, source_id TEXT, height REAL, instudy TEXT
            )
            """
        )
        sc.execute(
            "INSERT INTO shapes_area_sources (oid, source_id, height, instudy) "
            "VALUES (?, ?, ?, ?)",
            (1, "A1", 3.0, "1"),
        )
    # Destination: v1b schema (adds is_test_site TEXT DEFAULT '0')
    dst_cursor.execute(
        """
        CREATE TABLE shapes_area_sources (
            oid INTEGER, source_id TEXT, height REAL, instudy TEXT,
            is_test_site TEXT DEFAULT '0'
        )
        """
    )

    msg = _copy_shape_table_schema_robust(dst_cursor, dst_conn, "shapes_area_sources")
    assert "copied to output file" in msg

    row = dst_cursor.execute(
        "SELECT oid, source_id, height, instudy, is_test_site "
        "FROM shapes_area_sources"
    ).fetchone()
    # Source values preserved; is_test_site defaulted to '0'.
    assert row == (1, "A1", 3.0, "1", "0")


def test_helper_source_has_extra_column_ignored(source_and_dest):
    """Regression for the pre-existing shapes_runways case: source has
    legacy columns that the destination has since dropped. Those columns
    are ignored on copy; the copy still succeeds.
    """
    src_path, dst_conn, dst_cursor = source_and_dest
    with sqlite3.connect(src_path) as sc:
        sc.execute(
            """
            CREATE TABLE shapes_runways (
                oid INTEGER, name TEXT,
                max_queue_speed REAL, peak_queue_time REAL
            )
            """
        )
        sc.execute(
            "INSERT INTO shapes_runways VALUES (?, ?, ?, ?)",
            (1, "24", 5.0, 3.0),
        )
    dst_cursor.execute("CREATE TABLE shapes_runways (oid INTEGER, name TEXT)")

    msg = _copy_shape_table_schema_robust(dst_cursor, dst_conn, "shapes_runways")
    assert "copied to output file" in msg

    row = dst_cursor.execute("SELECT oid, name FROM shapes_runways").fetchone()
    assert row == (1, "24")


def test_helper_empty_source_produces_empty_destination(source_and_dest):
    """Source table exists but has no rows. Destination stays empty; no
    exception raised."""
    src_path, dst_conn, dst_cursor = source_and_dest
    ddl = "CREATE TABLE shapes_area_sources (oid INTEGER, source_id TEXT)"
    with sqlite3.connect(src_path) as sc:
        sc.execute(ddl)
    dst_cursor.execute(ddl)

    msg = _copy_shape_table_schema_robust(dst_cursor, dst_conn, "shapes_area_sources")
    assert "copied to output file" in msg

    count = dst_cursor.execute("SELECT COUNT(*) FROM shapes_area_sources").fetchone()[0]
    assert count == 0


def test_helper_no_common_columns_skips_gracefully(source_and_dest):
    """Source and destination share no column names. Skip status
    returned; no exception raised."""
    src_path, dst_conn, dst_cursor = source_and_dest
    with sqlite3.connect(src_path) as sc:
        sc.execute("CREATE TABLE shapes_area_sources (a INTEGER, b TEXT)")
    dst_cursor.execute("CREATE TABLE shapes_area_sources (x INTEGER, y TEXT)")

    msg = _copy_shape_table_schema_robust(dst_cursor, dst_conn, "shapes_area_sources")
    assert "skipped" in msg

    count = dst_cursor.execute("SELECT COUNT(*) FROM shapes_area_sources").fetchone()[0]
    assert count == 0
