"""Phase 1b: standalone-side extract_sources filter for engine-test sites.

Verifies that ``_extract_area_sources`` skips rows flagged
``is_test_site='1'`` and emits a diagnostic log line, while continuing
to yield normal area sources unchanged. Backward compatibility for
pre-v1b projects (rows without the column) is preserved.

QGIS-free. Uses a scratch SQLite DB with the current
``shapes_area_sources`` shape.
"""

from __future__ import annotations

import io
import os
import sqlite3
import tempfile
from contextlib import redirect_stdout

from openalaqs_standalone.extract_sources import _extract_area_sources


def _make_scratch_db_with_column(rows):
    """Create a scratch DB whose shapes_area_sources includes is_test_site."""
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE shapes_area_sources (
            oid INTEGER PRIMARY KEY,
            source_id TEXT,
            unit_year TEXT,
            height DECIMAL,
            heat_flux DECIMAL,
            hourly_profile TEXT,
            daily_profile TEXT,
            monthly_profile TEXT,
            co_kg_unit DECIMAL,
            hc_kg_unit DECIMAL,
            nox_kg_unit DECIMAL,
            sox_kg_unit DECIMAL,
            pm10_kg_unit DECIMAL,
            p1_kg_unit DECIMAL,
            p2_kg_unit DECIMAL,
            instudy TEXT DEFAULT '1',
            is_test_site TEXT DEFAULT '0',
            geometry BLOB
        )
        """
    )
    for r in rows:
        placeholders = ", ".join(["?"] * len(r))
        cols = ", ".join(r.keys())
        conn.execute(
            f"INSERT INTO shapes_area_sources ({cols}) VALUES ({placeholders})",
            list(r.values()),
        )
    conn.commit()
    return path, conn


def _make_scratch_db_pre_v1b(rows):
    """Create a scratch DB whose shapes_area_sources omits is_test_site
    (pre-v1b schema shape)."""
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE shapes_area_sources (
            oid INTEGER PRIMARY KEY,
            source_id TEXT,
            unit_year TEXT,
            height DECIMAL,
            heat_flux DECIMAL,
            hourly_profile TEXT,
            daily_profile TEXT,
            monthly_profile TEXT,
            co_kg_unit DECIMAL,
            hc_kg_unit DECIMAL,
            nox_kg_unit DECIMAL,
            sox_kg_unit DECIMAL,
            pm10_kg_unit DECIMAL,
            p1_kg_unit DECIMAL,
            p2_kg_unit DECIMAL,
            instudy TEXT DEFAULT '1',
            geometry BLOB
        )
        """
    )
    for r in rows:
        placeholders = ", ".join(["?"] * len(r))
        cols = ", ".join(r.keys())
        conn.execute(
            f"INSERT INTO shapes_area_sources ({cols}) VALUES ({placeholders})",
            list(r.values()),
        )
    conn.commit()
    return path, conn


# ---------------------------------------------------------------------------


def test_extract_skips_test_sites_and_logs():
    """A row with is_test_site='1' is filtered out; the diagnostic log
    line reports how many were skipped."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
            {"source_id": "N1", "is_test_site": "1", "geometry": None},
            {"source_id": "A2", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rows = _extract_area_sources(conn)
        conn.close()

        # A1 and A2 kept, N1 skipped
        labels = sorted(r["label"] for r in rows)
        assert labels == ["A1", "A2"], f"expected A1, A2; got {labels}"

        # Diagnostic printed with correct count
        out = buf.getvalue()
        assert "1 engine-test site(s) skipped" in out, f"log missing: {out!r}"
    finally:
        os.unlink(path)


def test_extract_multiple_test_sites_counted():
    """Two test-site rows yields a count of 2 in the log line."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "N1", "is_test_site": "1", "geometry": None},
            {"source_id": "COMP", "is_test_site": "1", "geometry": None},
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 1
        assert rows[0]["label"] == "A1"
        assert "2 engine-test site(s) skipped" in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_no_test_sites_silent():
    """When no rows are flagged, no diagnostic is emitted."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
            {"source_id": "A2", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 2
        # No skip-log line at all
        assert "engine-test site(s) skipped" not in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_pre_v1b_schema_no_column_treated_as_normal():
    """Backward compat: a pre-v1b project whose shapes_area_sources has
    no is_test_site column yields all rows as normal area sources, with
    no diagnostic emitted."""
    path, conn = _make_scratch_db_pre_v1b(
        [
            {"source_id": "A1", "geometry": None},
            {"source_id": "A2", "geometry": None},
        ]
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 2
        assert sorted(r["label"] for r in rows) == ["A1", "A2"]
        assert "engine-test site(s) skipped" not in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_null_and_empty_string_treated_as_normal():
    """is_test_site=NULL and is_test_site='' are treated as normal area
    sources (equivalent to '0')."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "A1", "is_test_site": None, "geometry": None},
            {"source_id": "A2", "is_test_site": "", "geometry": None},
        ]
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 2
        assert "engine-test site(s) skipped" not in buf.getvalue()
    finally:
        os.unlink(path)
