"""Regression: extract_sources skips missing tables instead of crashing.

Triggered by a user run on Windows where the .alaqs lacked
shapes_roadways. The pre-fix code did a bare `cur.execute(SELECT ...)`
on each of roadways/parking/gates/point/area; three of them had a
try/except, two (roadways, parking) did not. The two that didn't
crashed the whole pipeline on the first missing table.

Post-fix: all five extract functions wrap the SELECT in try/except,
log a one-line warning to stdout when the table is absent, and
return an empty list. Studies that legitimately have no sources of
a given type run through cleanly.

What this test pins:
  1. Each of the 5 extract functions is robust to a missing table.
  2. The top-level extract_sources() returns successfully when only
     ONE of the source-type tables exists.
  3. The top-level extract_sources() returns an empty DataFrame when
     NONE of the source tables exist (degenerate case).
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from openalaqs_standalone.extract_sources import (
    _extract_area_sources,
    _extract_gates,
    _extract_parking,
    _extract_point_sources,
    _extract_roadways,
    extract_sources,
)


def _empty_db(tmp_path, *create_sql):
    """Build a sqlite db at tmp_path/test.db with the given CREATE
    statements (or none). Returns the path."""
    p = tmp_path / "test.db"
    c = sqlite3.connect(p)
    for s in create_sql:
        c.execute(s)
    c.commit()
    c.close()
    return p


def _conn(p):
    return sqlite3.connect(str(p))


# ---------------------------------------------------------------------------
# Each extractor handles its own missing table without raising
# ---------------------------------------------------------------------------


def test_extract_roadways_missing_table_returns_empty(tmp_path, capsys):
    db = _empty_db(tmp_path)
    c = _conn(db)
    rows = _extract_roadways(c)
    c.close()
    assert rows == []
    captured = capsys.readouterr()
    assert "shapes_roadways not present" in captured.out


def test_extract_parking_missing_table_returns_empty(tmp_path, capsys):
    db = _empty_db(tmp_path)
    c = _conn(db)
    rows = _extract_parking(c)
    c.close()
    assert rows == []
    captured = capsys.readouterr()
    assert "shapes_parking not present" in captured.out


def test_extract_gates_missing_table_returns_empty(tmp_path, capsys):
    db = _empty_db(tmp_path)
    c = _conn(db)
    rows = _extract_gates(c)
    c.close()
    assert rows == []
    captured = capsys.readouterr()
    assert "shapes_gates not present" in captured.out


def test_extract_point_sources_missing_table_returns_empty(tmp_path, capsys):
    db = _empty_db(tmp_path)
    c = _conn(db)
    rows = _extract_point_sources(c)
    c.close()
    assert rows == []
    captured = capsys.readouterr()
    assert "shapes_point_sources not present" in captured.out


def test_extract_area_sources_missing_table_returns_empty(tmp_path, capsys):
    db = _empty_db(tmp_path)
    c = _conn(db)
    rows = _extract_area_sources(c)
    c.close()
    assert rows == []
    captured = capsys.readouterr()
    assert "shapes_area_sources not present" in captured.out


# ---------------------------------------------------------------------------
# Top-level extract_sources handles the mixed and degenerate cases
# ---------------------------------------------------------------------------


def test_extract_sources_all_tables_missing(tmp_path):
    """Degenerate: empty .alaqs with no shape tables.
    extract_sources must return an empty DataFrame, not crash."""
    db = _empty_db(tmp_path)
    df = extract_sources(db)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_extract_sources_only_one_table_present(tmp_path):
    """Mixed: shapes_point_sources exists with one row; the other 4
    tables are missing. extract_sources must produce one row in the
    output DataFrame.
    """
    db = _empty_db(
        tmp_path,
        # minimal point source schema
        """CREATE TABLE shapes_point_sources (
            oid INTEGER PRIMARY KEY,
            source_id TEXT,
            height REAL,
            geometry BLOB
        )""",
        # one row with no geometry (extractor tolerates None geometry)
        """INSERT INTO shapes_point_sources (oid, source_id, height) VALUES (1, 'P1', 10.0)""",
    )
    df = extract_sources(db)
    assert isinstance(df, pd.DataFrame)
    # The single point row should make it through
    pt_rows = df[df["source_type"] == "point"] if len(df) else df
    assert len(pt_rows) == 1
    # Other source types: none
    for t in ("road", "parking", "gate", "area"):
        assert len(df[df["source_type"] == t]) == 0 if len(df) else True
