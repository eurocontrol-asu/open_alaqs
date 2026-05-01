"""
Regression test for ``scripts/migrate_alaqs.py`` against legacy ``.alaqs``
files that ship pre-rebuild SpatiaLite metadata.

Pre-rebuild Open-ALAQS files (4.x-era) carry a ``type`` column on the
SpatiaLite metadata tables ``geometry_columns`` and
``virts_geometry_columns`` that was dropped in later SpatiaLite releases.
Running ``migrate_alaqs.py --drop-extra-columns --drop-extra-tables`` on
such a file would previously fail with::

    error in trigger ggi_<table>_geometry: no such table: main.geometry_columns

because:

  * SQLite has no native ``DROP COLUMN`` so the migrator rebuilds the
    table via the create-temp / copy / drop original / rename pattern.
  * SpatiaLite ships dependent views (``vector_layers``,
    ``geom_cols_ref_sys``, ...) and dependent triggers
    (``ggi_shapes_*_geometry``, ``geometry_columns_*_insert``, ...) whose
    bodies reference the metadata tables.
  * SQLite's schema-consistency check fires on the RENAME step because
    the dependent views/triggers reference an about-to-disappear table.

The fix wraps ``apply_plan`` with snapshot-and-restore for those
dependent views and triggers, plus a stale-row cleanup for metadata
tables that reference dropped tables.

This test rebuilds the offending shape in a synthetic ``.alaqs`` file
(small enough to keep in git, no external dependencies) and asserts the
migrator runs to completion and produces a coherent file.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MIGRATE = REPO / "scripts" / "migrate_alaqs.py"
REFERENCE_PROJECT = REPO / "open_alaqs" / "core" / "templates" / "project.alaqs"


def _create_legacy_fixture(path: Path) -> None:
    """Build a minimal pre-rebuild .alaqs file that triggers the bug.

    The shape we need:

      * geometry_columns has the legacy ``type`` column (=> column-drop required).
      * SpatiaLite ``ggi_*`` validation triggers exist whose bodies reference
        ``geometry_columns`` (these come for free from the reference template).
      * One legacy "extra" table (no longer in the reference) so
        ``--drop-extra-tables`` has work to do.
      * A dependent view (``vector_layers``, also from the template).
    """
    # Start from a copy of the reference template (gives us all the canonical
    # tables, the ggi_* triggers, and the vector_layers view for free), then
    # add the legacy bits.
    shutil.copy2(REFERENCE_PROJECT, path)
    conn = sqlite3.connect(path)

    # Add the legacy ``type`` column to geometry_columns. Since the migrator
    # drops the table to drop the column, the rebuild must handle the fact
    # that the inherited ggi_* triggers reference it.
    conn.execute("ALTER TABLE geometry_columns ADD COLUMN type TEXT")

    # Add a legacy table that no longer exists in the reference (forces
    # --drop-extra-tables to do work).
    conn.execute("CREATE TABLE default_pollutants (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO default_pollutants(name) VALUES ('CO'), ('NOx')")

    conn.commit()
    conn.close()


def _run_migrate(alaqs_path: Path, *flags: str) -> subprocess.CompletedProcess:
    """Run scripts/migrate_alaqs.py as a subprocess and return the result."""
    cmd = [sys.executable, str(MIGRATE), str(alaqs_path), *flags]
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)


def test_migrate_legacy_spatialite_metadata(tmp_path: Path) -> None:
    """End-to-end: legacy .alaqs file migrates without the trigger error.

    Without the apply_plan view/trigger snapshot fix, this would fail with::

        ERROR: migration failed: error in trigger ggi_shapes_runways_geometry:
        no such table: main.geometry_columns

    and silently restore from the .bak-<timestamp> backup, leaving the user's
    file unchanged (the original symptom — QGIS still crashes when opening it).
    """
    fixture = tmp_path / "legacy.alaqs"
    _create_legacy_fixture(fixture)

    # Sanity: the fixture really has the legacy column and the ggi_ triggers.
    conn = sqlite3.connect(fixture)
    cols = [
        r[1] for r in conn.execute("PRAGMA table_info(geometry_columns)").fetchall()
    ]
    assert "type" in cols, "fixture must have legacy 'type' column to exercise the bug"
    n_ggi = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'ggi_%_geometry'"
    ).fetchone()[0]
    assert n_ggi > 0, "fixture must have ggi_ triggers to exercise the bug"
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='default_pollutants'"
        ).fetchone()[0]
        == 1
    )
    conn.close()

    # Run the migration with both drop flags — this is the user's command line.
    result = _run_migrate(
        fixture, "--drop-extra-tables", "--drop-extra-columns", "--no-backup"
    )

    assert result.returncode == 0, (
        f"migration failed with rc={result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Migration applied successfully" in result.stdout, result.stdout

    # Verify the file is now coherent.
    conn = sqlite3.connect(fixture)

    # Legacy 'type' column gone
    cols = [
        r[1] for r in conn.execute("PRAGMA table_info(geometry_columns)").fetchall()
    ]
    assert "type" not in cols

    # Legacy table gone
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='default_pollutants'"
        ).fetchone()[0]
        == 0
    )

    # The dependent ggi_ triggers were recreated from captured DDL.
    n_ggi_after = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'ggi_%_geometry'"
    ).fetchone()[0]
    assert (
        n_ggi_after == n_ggi
    ), f"ggi_ trigger count changed: before={n_ggi}, after={n_ggi_after}"

    # The vector_layers view (inherited from the template, references
    # geometry_columns) is back and queryable.
    rows = conn.execute("SELECT COUNT(*) FROM vector_layers").fetchone()
    assert rows[0] >= 0  # query succeeded

    # No stale geometry_columns rows pointing at non-existent tables
    db_tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    geom_refs = [
        r[0]
        for r in conn.execute("SELECT f_table_name FROM geometry_columns").fetchall()
    ]
    stale = [r for r in geom_refs if r not in db_tables]
    assert stale == [], f"stale geometry_columns rows: {stale}"

    conn.close()


def test_migrate_no_op_when_no_legacy_metadata(tmp_path: Path) -> None:
    """Sanity: running the migrator on a clean copy of the reference template
    is a no-op and does not regress the apply_plan path.
    """
    fixture = tmp_path / "clean.alaqs"
    shutil.copy2(REFERENCE_PROJECT, fixture)

    result = _run_migrate(fixture, "--no-backup")
    # rc=0 with "Nothing to do." or success message — both acceptable.
    assert result.returncode == 0, (
        f"clean migration unexpectedly failed: rc={result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.parametrize(
    "kind,name,sql,expected_host",
    [
        (
            "TRIGGER",
            "t1",
            'CREATE TRIGGER "t1" BEFORE INSERT ON "shapes_runways" FOR EACH ROW BEGIN SELECT 1; END',
            "shapes_runways",
        ),
        (
            "TRIGGER",
            "t2",
            "CREATE TRIGGER t2 AFTER UPDATE ON my_table BEGIN SELECT 1; END",
            "my_table",
        ),
        (
            "TRIGGER",
            "t3",
            "CREATE TRIGGER t3 INSTEAD OF DELETE ON 'quoted_name' BEGIN SELECT 1; END",
            "quoted_name",
        ),
    ],
)
def test_get_trigger_host_from_ddl(
    kind: str, name: str, sql: str, expected_host: str
) -> None:
    """The host-extractor handles the three quoting styles SQLite emits."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import migrate_alaqs

        host = migrate_alaqs._get_trigger_host_from_ddl(sql)
    finally:
        sys.path.pop(0)

    assert host == expected_host, f"expected {expected_host!r}, got {host!r}"
