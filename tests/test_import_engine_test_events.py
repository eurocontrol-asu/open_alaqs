"""Tests for ``scripts/import_engine_test_events.py``.

QGIS-free. Uses raw sqlite3 fixtures and StringIO for CSVs.

Coverage:
  * validate_csv_rows: all 8 row-level error codes + all warnings.
  * validate_against_db: reference-table cross-checks.
  * apply_insert: three modes (append / replace-for-source / replace-all).
  * CLI end-to-end: dry-run, --apply, exit codes, --tolerate-warnings,
    --i-mean-it protection.
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Add the scripts/ dir to sys.path so the module is importable. Tests
# run from the repo root under pytest.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import import_engine_test_events as importer  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _rows_from_string(csv_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


def _make_scratch_db(
    area_sources: list[dict] = None,
    default_aircraft: list[str] = None,
    default_engine_ei_uids: list[str] = None,
) -> tuple[str, sqlite3.Connection]:
    """Create a scratch .alaqs-shaped DB with just the tables the
    importer reads. Returns (path, open connection)."""
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    conn = sqlite3.connect(path)

    conn.execute(
        """
        CREATE TABLE shapes_area_sources (
            oid INTEGER PRIMARY KEY,
            source_id TEXT,
            is_test_site TEXT DEFAULT '0'
        )
        """
    )
    for src in area_sources or []:
        conn.execute(
            "INSERT INTO shapes_area_sources (source_id, is_test_site) VALUES (?, ?)",
            (src["source_id"], src.get("is_test_site", "0")),
        )

    conn.execute("CREATE TABLE default_aircraft (icao TEXT)")
    for icao in default_aircraft or []:
        conn.execute("INSERT INTO default_aircraft (icao) VALUES (?)", (icao,))

    conn.execute("CREATE TABLE default_aircraft_engine_ei (engine_full_name TEXT)")
    for uid in default_engine_ei_uids or []:
        conn.execute(
            "INSERT INTO default_aircraft_engine_ei (engine_full_name) VALUES (?)",
            (uid,),
        )

    conn.execute(
        """
        CREATE TABLE engine_test_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            test_id TEXT,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            aircraft_type TEXT NOT NULL,
            engine_uid TEXT,
            engine_count INTEGER,
            t_TX_s INTEGER NOT NULL DEFAULT 0,
            t_AP_s INTEGER NOT NULL DEFAULT 0,
            t_CL_s INTEGER NOT NULL DEFAULT 0,
            t_TO_s INTEGER NOT NULL DEFAULT 0,
            thrust_mode TEXT NOT NULL DEFAULT 'snap',
            instudy TEXT NOT NULL DEFAULT '1'
        )
        """
    )
    conn.commit()
    return path, conn


CSV_HEADER = (
    "source_id,start_datetime,end_datetime,aircraft_type,test_id,"
    "engine_uid,engine_count,t_TX_s,t_AP_s,t_CL_s,t_TO_s,instudy"
)


def _row(
    source_id="N1",
    start="2024-12-01T09:00:00",
    end="2024-12-01T09:30:00",
    aircraft="C56X",
    test_id="",
    engine_uid="",
    engine_count="",
    t_TX_s="",
    t_AP_s="",
    t_CL_s="",
    t_TO_s="",
    instudy="",
):
    return (
        f"{source_id},{start},{end},{aircraft},{test_id},"
        f"{engine_uid},{engine_count},{t_TX_s},{t_AP_s},{t_CL_s},{t_TO_s},"
        f"{instudy}"
    )


def _csv_text(*rows: str) -> str:
    return CSV_HEADER + "\n" + "\n".join(rows) + "\n"


# ═══════════════════════════════════════════════════════════════════════
# Section 1: read_csv header check
# ═══════════════════════════════════════════════════════════════════════


def test_read_csv_flags_missing_required_column(tmp_path):
    """CSV missing the aircraft_type header → header_error returned; no
    rows returned. Whole-file abort."""
    p = tmp_path / "bad.csv"
    p.write_text("source_id,start_datetime,end_datetime\nN1,x,y\n")
    rows, err = importer.read_csv(p)
    assert rows == []
    assert err is not None
    assert "aircraft_type" in err


def test_read_csv_accepts_extra_columns(tmp_path):
    """Unknown columns are ignored (forward-compatible)."""
    p = tmp_path / "ok.csv"
    p.write_text(CSV_HEADER + ",extra_column\n" + _row() + ",whatever\n")
    rows, err = importer.read_csv(p)
    assert err is None
    assert len(rows) == 1


def test_read_csv_handles_utf8_bom(tmp_path):
    """utf-8-sig strips the BOM if the CSV was saved from Excel."""
    p = tmp_path / "bom.csv"
    p.write_bytes(("\ufeff" + _csv_text(_row())).encode("utf-8"))
    rows, err = importer.read_csv(p)
    assert err is None
    assert len(rows) == 1
    assert rows[0]["source_id"] == "N1"


# ═══════════════════════════════════════════════════════════════════════
# Section 2: validate_csv_rows — row-level errors
# ═══════════════════════════════════════════════════════════════════════


def test_valid_row_produces_no_issues():
    rows = _rows_from_string(_csv_text(_row(t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    assert result.errors == []
    assert result.warnings == []
    assert len(result.valid_rows) == 1
    r = result.valid_rows[0]
    assert r.source_id == "N1"
    assert r.t_CL_s == 900


def test_missing_required_column_value_rejects():
    rows = _rows_from_string(_csv_text(_row(source_id="")))
    result = importer.validate_csv_rows(rows)
    assert len(result.errors) == 1
    assert result.errors[0].code == "missing_required"
    assert result.valid_rows == []


def test_unparseable_datetime_rejects():
    rows = _rows_from_string(_csv_text(_row(start="not-a-date")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "unparseable_datetime" for e in result.errors)


def test_end_before_start_rejects():
    rows = _rows_from_string(
        _csv_text(
            _row(start="2024-12-01T10:00:00", end="2024-12-01T09:30:00"),
        )
    )
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "end_before_start" for e in result.errors)


def test_end_equal_start_rejects():
    """end == start is not a valid event window."""
    rows = _rows_from_string(
        _csv_text(
            _row(start="2024-12-01T09:00:00", end="2024-12-01T09:00:00"),
        )
    )
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "end_before_start" for e in result.errors)


def test_negative_mode_time_rejects():
    rows = _rows_from_string(_csv_text(_row(t_CL_s="-100")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "invalid_mode_time" for e in result.errors)


def test_non_integer_mode_time_rejects():
    rows = _rows_from_string(_csv_text(_row(t_CL_s="900.5")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "invalid_mode_time" for e in result.errors)


def test_zero_or_negative_engine_count_rejects():
    """engine_count present but not a POSITIVE integer."""
    rows = _rows_from_string(_csv_text(_row(engine_count="0", t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "invalid_engine_count" for e in result.errors)


def test_non_numeric_engine_count_rejects():
    rows = _rows_from_string(_csv_text(_row(engine_count="two", t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "invalid_engine_count" for e in result.errors)


def test_invalid_instudy_rejects():
    rows = _rows_from_string(_csv_text(_row(instudy="maybe", t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    assert any(e.code == "invalid_instudy" for e in result.errors)


def test_duplicate_row_rejected():
    """Same (source_id, start_datetime, aircraft_type) in two rows."""
    r1 = _row(source_id="N1", start="2024-12-01T09:00:00", aircraft="C56X")
    r2 = _row(
        source_id="N1",
        start="2024-12-01T09:00:00",
        end="2024-12-01T10:00:00",  # different, but key still matches
        aircraft="C56X",
    )
    result = importer.validate_csv_rows(_rows_from_string(_csv_text(r1, r2)))
    assert any(e.code == "duplicate_row" for e in result.errors)


def test_multiple_errors_all_reported():
    """One row can accumulate multiple errors; all are surfaced so users
    fix everything in one pass."""
    rows = _rows_from_string(_csv_text(_row(start="bad", end="also-bad", t_CL_s="-1")))
    result = importer.validate_csv_rows(rows)
    codes = {e.code for e in result.errors}
    # start and end each unparseable → 2 "unparseable_datetime" errors
    # negative t_CL_s → "invalid_mode_time"
    assert "unparseable_datetime" in codes
    assert "invalid_mode_time" in codes


def test_empty_optional_columns_take_defaults():
    """Empty engine_uid, engine_count, mode-time cols → None or 0."""
    rows = _rows_from_string(_csv_text(_row(t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    r = result.valid_rows[0]
    assert r.engine_uid is None
    assert r.engine_count is None
    assert r.t_TX_s == 0
    assert r.t_AP_s == 0
    assert r.t_TO_s == 0
    assert r.instudy == "1"


def test_row_numbers_are_1_indexed_from_header():
    """Header is line 1, first data row is line 2. Errors reference the
    spreadsheet-visible line number."""
    rows = _rows_from_string(_csv_text(_row(t_CL_s="900"), _row(source_id="")))
    result = importer.validate_csv_rows(rows)
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3


# ═══════════════════════════════════════════════════════════════════════
# Section 3: validate_csv_rows — warnings
# ═══════════════════════════════════════════════════════════════════════


def test_running_exceeds_window_warns():
    """Sum of mode-times * engine_count exceeds window by > 60s → warn."""
    # window = 30min = 1800s. mode times sum = 1900 * 2 engines = 3800s.
    # Over by 2000s, well past 60s tolerance.
    rows = _rows_from_string(_csv_text(_row(t_CL_s="1900", engine_count="2")))
    result = importer.validate_csv_rows(rows)
    assert any(w.code == "running_exceeds_window" for w in result.warnings)
    # But still valid; not an error.
    assert len(result.valid_rows) == 1


def test_running_within_tolerance_no_warning():
    """Within 60s tolerance → no warning."""
    # window = 30min = 1800s. mode times sum = 1830 * 1 engine = 1830s.
    # Over by 30s, within 60s tolerance.
    rows = _rows_from_string(_csv_text(_row(t_CL_s="1830", engine_count="1")))
    result = importer.validate_csv_rows(rows)
    assert not any(w.code == "running_exceeds_window" for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════
# Section 4: validate_against_db — reference lookups
# ═══════════════════════════════════════════════════════════════════════


def test_unknown_source_id_warns():
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": "N1", "is_test_site": "1"}]
    )
    try:
        rows = _rows_from_string(_csv_text(_row(source_id="GHOST")))
        result = importer.validate_csv_rows(rows)
        assert result.errors == []
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        assert any(w.code == "unknown_source_id" for w in db_warnings)
    finally:
        conn.close()
        os.unlink(path)


def test_source_id_not_test_site_warns():
    """source_id exists but is_test_site='0' → compute would ignore
    events. Surface as a warning."""
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": "A1", "is_test_site": "0"}]
    )
    try:
        rows = _rows_from_string(_csv_text(_row(source_id="A1")))
        result = importer.validate_csv_rows(rows)
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        assert any(w.code == "source_not_test_site" for w in db_warnings)
    finally:
        conn.close()
        os.unlink(path)


def test_unknown_aircraft_warns():
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": "N1", "is_test_site": "1"}],
        default_aircraft=["B738", "C56X"],
    )
    try:
        rows = _rows_from_string(_csv_text(_row(aircraft="A380")))
        result = importer.validate_csv_rows(rows)
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        assert any(w.code == "unknown_aircraft_type" for w in db_warnings)
    finally:
        conn.close()
        os.unlink(path)


def test_unknown_engine_uid_warns():
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": "N1", "is_test_site": "1"}],
        default_engine_ei_uids=["B602", "B603"],
    )
    try:
        rows = _rows_from_string(_csv_text(_row(engine_uid="B999")))
        result = importer.validate_csv_rows(rows)
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        assert any(w.code == "unknown_engine_uid" for w in db_warnings)
    finally:
        conn.close()
        os.unlink(path)


def test_no_warnings_when_all_references_resolve():
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": "N1", "is_test_site": "1"}],
        default_aircraft=["C56X"],
        default_engine_ei_uids=["B602"],
    )
    try:
        rows = _rows_from_string(_csv_text(_row(engine_uid="B602")))
        result = importer.validate_csv_rows(rows)
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        assert db_warnings == []
    finally:
        conn.close()
        os.unlink(path)


def test_missing_reference_tables_do_not_crash():
    """Bare DB without default_aircraft / default_aircraft_engine_ei →
    lookups silently return empty sets; no lookup produces spurious
    'unknown' warnings (since we can't check against nothing)."""
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE shapes_area_sources (source_id TEXT, is_test_site TEXT)"
        )
        conn.execute("INSERT INTO shapes_area_sources VALUES ('N1', '1')")
        conn.commit()

        rows = _rows_from_string(_csv_text(_row(engine_uid="whatever")))
        result = importer.validate_csv_rows(rows)
        db_warnings = importer.validate_against_db(result.valid_rows, conn)
        # source_id is known, and engine_uid check is skipped when
        # the ref table has no rows.
        assert db_warnings == []
        conn.close()
    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
# Section 5: apply_insert — three modes
# ═══════════════════════════════════════════════════════════════════════


def _apply_prep(mode: str):
    """Set up a DB with one pre-existing event and one validated row
    ready to insert."""
    path, conn = _make_scratch_db(
        area_sources=[
            {"source_id": "N1", "is_test_site": "1"},
            {"source_id": "COMP", "is_test_site": "1"},
        ]
    )
    conn.execute(
        "INSERT INTO engine_test_events "
        "(source_id, start_datetime, end_datetime, aircraft_type) "
        "VALUES ('N1', '2024-11-15T08:00:00', '2024-11-15T08:20:00', 'C56X')"
    )
    conn.commit()

    row = importer.ValidatedRow(
        row_number=2,
        source_id="N1",
        test_id=None,
        start_datetime="2024-12-01T09:00:00",
        end_datetime="2024-12-01T09:30:00",
        aircraft_type="C56X",
        engine_uid=None,
        engine_count=2,
        t_TX_s=0,
        t_AP_s=0,
        t_CL_s=900,
        t_TO_s=0,
        instudy="1",
    )
    return path, conn, row


def test_apply_append_leaves_existing_rows():
    path, conn, row = _apply_prep("append")
    try:
        importer.apply_insert(conn, [row], "append")
        n = conn.execute("SELECT COUNT(*) FROM engine_test_events").fetchone()[0]
        assert n == 2  # 1 pre-existing + 1 new
    finally:
        conn.close()
        os.unlink(path)


def test_apply_replace_for_source_deletes_matching_source_only():
    path, conn, row = _apply_prep("replace-for-source")
    # Add another pre-existing event on a DIFFERENT source
    conn.execute(
        "INSERT INTO engine_test_events "
        "(source_id, start_datetime, end_datetime, aircraft_type) "
        "VALUES ('COMP', '2024-11-15T14:00:00', '2024-11-15T14:15:00', 'B738')"
    )
    conn.commit()
    try:
        importer.apply_insert(conn, [row], "replace-for-source")
        rows_after = conn.execute(
            "SELECT source_id FROM engine_test_events ORDER BY source_id"
        ).fetchall()
        # N1: pre-existing deleted, new inserted (1 total).
        # COMP: pre-existing preserved (1 total).
        assert [r[0] for r in rows_after] == ["COMP", "N1"]
    finally:
        conn.close()
        os.unlink(path)


def test_apply_replace_all_wipes_the_table():
    path, conn, row = _apply_prep("replace-all")
    try:
        importer.apply_insert(conn, [row], "replace-all")
        rows_after = conn.execute("SELECT source_id FROM engine_test_events").fetchall()
        assert [r[0] for r in rows_after] == ["N1"]  # only the new one
    finally:
        conn.close()
        os.unlink(path)


def test_apply_returns_per_source_counts():
    path, conn = _make_scratch_db(
        area_sources=[{"source_id": s, "is_test_site": "1"} for s in ("N1", "COMP")]
    )

    def _r(sid, i):
        return importer.ValidatedRow(
            row_number=i,
            source_id=sid,
            test_id=None,
            start_datetime=f"2024-12-{i:02d}T09:00:00",
            end_datetime=f"2024-12-{i:02d}T09:30:00",
            aircraft_type="C56X",
            engine_uid=None,
            engine_count=1,
            t_TX_s=0,
            t_AP_s=0,
            t_CL_s=900,
            t_TO_s=0,
            instudy="1",
        )

    rows = [_r("N1", 2), _r("N1", 3), _r("COMP", 4)]
    try:
        per_source = importer.apply_insert(conn, rows, "append")
        assert per_source == {"N1": 2, "COMP": 1}
    finally:
        conn.close()
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
# Section 6: CLI end-to-end
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def scratch_db_with_test_site(tmp_path):
    path = str(tmp_path / "study.alaqs")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE shapes_area_sources ("
        "oid INTEGER PRIMARY KEY, source_id TEXT, is_test_site TEXT DEFAULT '0')"
    )
    conn.execute(
        "INSERT INTO shapes_area_sources (source_id, is_test_site) "
        "VALUES ('N1', '1')"
    )
    conn.execute("CREATE TABLE default_aircraft (icao TEXT)")
    conn.execute("INSERT INTO default_aircraft VALUES ('C56X')")
    conn.execute("CREATE TABLE default_aircraft_engine_ei (engine_full_name TEXT)")
    conn.execute("INSERT INTO default_aircraft_engine_ei VALUES ('B602')")
    conn.execute(
        """
        CREATE TABLE engine_test_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            test_id TEXT,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            aircraft_type TEXT NOT NULL,
            engine_uid TEXT,
            engine_count INTEGER,
            t_TX_s INTEGER NOT NULL DEFAULT 0,
            t_AP_s INTEGER NOT NULL DEFAULT 0,
            t_CL_s INTEGER NOT NULL DEFAULT 0,
            t_TO_s INTEGER NOT NULL DEFAULT 0,
            thrust_mode TEXT NOT NULL DEFAULT 'snap',
            instudy TEXT NOT NULL DEFAULT '1'
        )
        """
    )
    conn.commit()
    conn.close()
    return path


def _write_csv(tmp_path, name, *rows):
    p = tmp_path / name
    p.write_text(_csv_text(*rows))
    return str(p)


def test_cli_dry_run_returns_0_for_clean_csv(
    scratch_db_with_test_site, tmp_path, capsys
):
    csv_path = _write_csv(
        tmp_path,
        "clean.csv",
        _row(engine_uid="B602", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Rows valid:             1" in out
    assert "Dry-run OK" in out


def test_cli_dry_run_returns_2_on_errors(scratch_db_with_test_site, tmp_path, capsys):
    csv_path = _write_csv(
        tmp_path,
        "bad.csv",
        _row(start="not-a-date", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Rows rejected:          1" in captured.out
    assert "unparseable_datetime" in captured.out


def test_cli_returns_2_on_warnings_without_tolerate(
    scratch_db_with_test_site, tmp_path, capsys
):
    """Unknown engine_uid: warning. Without --tolerate-warnings, fails."""
    csv_path = _write_csv(
        tmp_path,
        "warn.csv",
        _row(engine_uid="B999", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path])
    assert rc == 2
    out = capsys.readouterr().out
    assert "unknown_engine_uid" in out


def test_cli_returns_0_with_tolerate_warnings(
    scratch_db_with_test_site, tmp_path, capsys
):
    csv_path = _write_csv(
        tmp_path,
        "warn.csv",
        _row(engine_uid="B999", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path, "--tolerate-warnings"])
    assert rc == 0


def test_cli_apply_inserts_rows(scratch_db_with_test_site, tmp_path, capsys):
    csv_path = _write_csv(
        tmp_path,
        "apply.csv",
        _row(engine_uid="B602", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path, "--apply"])
    assert rc == 0
    conn = sqlite3.connect(scratch_db_with_test_site)
    n = conn.execute("SELECT COUNT(*) FROM engine_test_events").fetchone()[0]
    conn.close()
    assert n == 1
    out = capsys.readouterr().out
    assert "Applied (append)" in out
    assert "N1: 1 event(s)" in out


def test_cli_replace_all_requires_i_mean_it(
    scratch_db_with_test_site, tmp_path, capsys
):
    csv_path = _write_csv(
        tmp_path,
        "replace.csv",
        _row(engine_uid="B602", t_CL_s="900"),
    )
    rc = importer.main(
        [scratch_db_with_test_site, csv_path, "--apply", "--mode", "replace-all"]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "--i-mean-it" in err


def test_cli_replace_all_with_i_mean_it_works(
    scratch_db_with_test_site, tmp_path, capsys
):
    # Pre-load a stale event
    conn = sqlite3.connect(scratch_db_with_test_site)
    conn.execute(
        "INSERT INTO engine_test_events "
        "(source_id, start_datetime, end_datetime, aircraft_type) "
        "VALUES ('STALE', '2024-01-01T00:00:00', '2024-01-01T00:30:00', 'X')"
    )
    conn.commit()
    conn.close()

    csv_path = _write_csv(
        tmp_path,
        "replace.csv",
        _row(engine_uid="B602", t_CL_s="900"),
    )
    rc = importer.main(
        [
            scratch_db_with_test_site,
            csv_path,
            "--apply",
            "--mode",
            "replace-all",
            "--i-mean-it",
        ]
    )
    assert rc == 0
    conn = sqlite3.connect(scratch_db_with_test_site)
    rows = conn.execute("SELECT source_id FROM engine_test_events").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["N1"]  # STALE gone; N1 inserted


def test_cli_dry_run_makes_no_writes(scratch_db_with_test_site, tmp_path, capsys):
    csv_path = _write_csv(
        tmp_path,
        "dry.csv",
        _row(engine_uid="B602", t_CL_s="900"),
    )
    rc = importer.main([scratch_db_with_test_site, csv_path])
    assert rc == 0
    conn = sqlite3.connect(scratch_db_with_test_site)
    n = conn.execute("SELECT COUNT(*) FROM engine_test_events").fetchone()[0]
    conn.close()
    assert n == 0


def test_cli_missing_csv_returns_1(scratch_db_with_test_site, tmp_path, capsys):
    rc = importer.main(
        [scratch_db_with_test_site, str(tmp_path / "does-not-exist.csv")]
    )
    assert rc == 1


def test_cli_missing_alaqs_returns_1(tmp_path, capsys):
    csv_path = _write_csv(tmp_path, "x.csv", _row(t_CL_s="900"))
    rc = importer.main([str(tmp_path / "no.alaqs"), csv_path])
    assert rc == 1


# ═══════════════════════════════════════════════════════════════════════
# Section 7: implicit_source_id (per-source dialog scope)
# ═══════════════════════════════════════════════════════════════════════


def test_read_csv_source_id_optional_when_implicit_supplied(tmp_path):
    """With implicit_source_id set, source_id column is not required
    in the header. Rows get their source_id filled in."""
    p = tmp_path / "no_source.csv"
    p.write_text(
        "start_datetime,end_datetime,aircraft_type,test_id,engine_uid,"
        "engine_count,t_TX_s,t_AP_s,t_CL_s,t_TO_s,instudy\n"
        "2024-12-01T09:00:00,2024-12-01T09:15:00,C56X,,,,600,0,300,0,1\n"
    )
    rows, err = importer.read_csv(p, implicit_source_id="TESTPAD_A")
    assert err is None
    assert len(rows) == 1
    assert rows[0]["source_id"] == "TESTPAD_A"


def test_read_csv_source_id_still_read_when_present_in_header(tmp_path):
    """With implicit_source_id set AND source_id column in header, the
    CSV values pass through unchanged. Validation catches mismatches."""
    p = tmp_path / "with_source.csv"
    p.write_text(_csv_text(_row(source_id="TESTPAD_B")))
    rows, err = importer.read_csv(p, implicit_source_id="TESTPAD_A")
    assert err is None
    assert rows[0]["source_id"] == "TESTPAD_B"  # unchanged


def test_validate_csv_rows_mismatched_source_id_errors_out():
    """A row whose source_id doesn't match the implicit_source_id
    should be rejected as an error, not a warning."""
    rows = _rows_from_string(_csv_text(_row(source_id="TESTPAD_B", t_CL_s="900")))
    result = importer.validate_csv_rows(rows, implicit_source_id="TESTPAD_A")
    assert len(result.errors) == 1
    assert result.errors[0].code == "mismatched_source_id"
    assert "TESTPAD_A" in result.errors[0].message
    assert "TESTPAD_B" in result.errors[0].message


def test_validate_csv_rows_matching_source_id_passes():
    """A row whose source_id matches the implicit_source_id should
    validate normally."""
    rows = _rows_from_string(_csv_text(_row(source_id="TESTPAD_A", t_CL_s="900")))
    result = importer.validate_csv_rows(rows, implicit_source_id="TESTPAD_A")
    assert result.errors == []
    assert len(result.valid_rows) == 1


def test_validate_csv_rows_no_implicit_source_id_backward_compat():
    """When implicit_source_id is None (default, CLI path), any
    source_id is accepted; no mismatched_source_id error possible."""
    rows = _rows_from_string(_csv_text(_row(source_id="ANY_SOURCE", t_CL_s="900")))
    result = importer.validate_csv_rows(rows)
    assert result.errors == []
    assert result.valid_rows[0].source_id == "ANY_SOURCE"


def test_read_csv_still_requires_source_id_when_no_implicit(tmp_path):
    """Backward compat: without implicit_source_id, source_id is still
    a required column."""
    p = tmp_path / "no_source.csv"
    p.write_text(
        "start_datetime,end_datetime,aircraft_type\n"
        "2024-12-01T09:00:00,2024-12-01T09:15:00,C56X\n"
    )
    rows, err = importer.read_csv(p)
    assert err is not None
    assert "source_id" in err


def test_end_to_end_dialog_flow_no_source_id_column(tmp_path):
    """Simulate the dialog flow: CSV lacks source_id column, dialog
    supplies TESTPAD_A. All rows get validated with source_id filled
    in, no mismatch errors."""
    p = tmp_path / "dialog_scenario.csv"
    p.write_text(
        "start_datetime,end_datetime,aircraft_type,t_CL_s\n"
        "2024-12-01T09:00:00,2024-12-01T09:15:00,C56X,300\n"
        "2024-12-02T10:00:00,2024-12-02T10:20:00,PC24,600\n"
    )
    rows, err = importer.read_csv(p, implicit_source_id="TESTPAD_A")
    assert err is None
    result = importer.validate_csv_rows(rows, implicit_source_id="TESTPAD_A")
    assert result.errors == []
    assert len(result.valid_rows) == 2
    assert all(r.source_id == "TESTPAD_A" for r in result.valid_rows)
