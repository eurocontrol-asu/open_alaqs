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


def test_extract_test_sites_emitted_as_engine_test_type():
    """A row with is_test_site='1' is emitted as source_type
    'engine_test' with source_id prefixed 'engine_test:' — not skipped.
    Regular area rows still come through as 'area'."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
            {"source_id": "N1", "is_test_site": "1", "geometry": None},
            {"source_id": "A2", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        rows = _extract_area_sources(conn)
        conn.close()

        # All 3 rows emitted
        assert len(rows) == 3
        by_id = {r["label"]: r for r in rows}

        # A1, A2 → source_type 'area', source_id 'area:...'
        assert by_id["A1"]["source_type"] == "area"
        assert by_id["A1"]["source_id"] == "area:A1"
        assert by_id["A2"]["source_type"] == "area"
        assert by_id["A2"]["source_id"] == "area:A2"

        # N1 → source_type 'engine_test', source_id 'engine_test:...'
        assert by_id["N1"]["source_type"] == "engine_test"
        assert by_id["N1"]["source_id"] == "engine_test:N1"
        # is_test_site flag also in extra_json for downstream consumers
        import json as _json

        extra = _json.loads(by_id["N1"]["extra_json"])
        assert extra["is_test_site"] == "1"
    finally:
        os.unlink(path)


def test_extract_multiple_test_sites_all_emitted_as_engine_test():
    """Two test-site rows both emitted with engine_test source_type."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "N1", "is_test_site": "1", "geometry": None},
            {"source_id": "COMP", "is_test_site": "1", "geometry": None},
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 3
        engine_test_rows = [r for r in rows if r["source_type"] == "engine_test"]
        area_rows = [r for r in rows if r["source_type"] == "area"]
        assert len(engine_test_rows) == 2
        assert len(area_rows) == 1
        assert sorted(r["label"] for r in engine_test_rows) == ["COMP", "N1"]
    finally:
        os.unlink(path)


def test_extract_no_test_sites_all_area():
    """When no rows are flagged, all come through as source_type
    'area'. No engine_test rows produced."""
    path, conn = _make_scratch_db_with_column(
        [
            {"source_id": "A1", "is_test_site": "0", "geometry": None},
            {"source_id": "A2", "is_test_site": "0", "geometry": None},
        ]
    )
    try:
        rows = _extract_area_sources(conn)
        conn.close()
        assert len(rows) == 2
        assert all(r["source_type"] == "area" for r in rows)
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
