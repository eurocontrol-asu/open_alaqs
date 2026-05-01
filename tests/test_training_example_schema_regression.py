"""
Regression test for the schema of the shipped training-example .alaqs files.

The runway form was simplified in the rebuild: the columns
``max_queue_speed`` and ``peak_queue_time`` were dropped from
``shapes_runways`` because no code path read them. The current templates
(open_alaqs/core/templates/project.alaqs and inventory.alaqs) ship the
6-column schema:

    oid INTEGER, runway_id TEXT, capacity INT, touchdown INT,
    instudy DECIMAL, geometry LINESTRING

The example files in example/training/ MUST track that 6-column schema.
If they drift back to the legacy 8-column schema, create_output.py
fails at the runway-copy step with::

    Problem copying runways: Incorrect number of bindings supplied.
    The current statement uses 6, and there are 8 supplied.

The downstream effect is worse: shapes_runways ends up empty in the
generated _out.alaqs, RunwayStore loads 0 runways at calc time, every
movement gets dropped because ``RunwayStore.isinKey('06')`` returns
False against an empty store, and the user gets an empty inventory
with no obvious indication that the SQL error upstream caused it.

This test locks both shipped example .alaqs files at the 6-column
schema so that a future repackaging with stale legacy files is caught
in CI rather than discovered by a user running the training example.
"""

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Both shipped example files. training.alaqs is the input study;
# training_out.alaqs is the post-create_output reference. Both must
# carry the current 6-column shapes_runways schema.
EXAMPLE_FILES = {
    "training.alaqs": REPO / "example/training/training.alaqs",
    "training_out.alaqs": REPO / "example/training/training_out.alaqs",
}

# Authoritative column set for the rebuild. Order matters: positional
# INSERT statements in create_output.py rely on it.
EXPECTED_COLUMNS = [
    "oid",
    "runway_id",
    "capacity",
    "touchdown",
    "instudy",
    "geometry",
]

# Columns dropped during the rebuild. If any of these reappears in a
# shipped example, the file is stale and must be re-migrated via
# scripts/migrate_alaqs.py --drop-extra-columns.
DROPPED_COLUMNS = {"max_queue_speed", "peak_queue_time"}


def _shapes_runways_columns(db_path: Path) -> list[str]:
    """Return ordered column names of shapes_runways in `db_path`."""
    assert db_path.exists(), f"Example file is missing: {db_path}"
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("PRAGMA table_info(shapes_runways)").fetchall()
    finally:
        con.close()
    return [r[1] for r in rows]


@pytest.mark.parametrize("name,path", EXAMPLE_FILES.items())
def test_shapes_runways_has_exactly_six_columns(name, path):
    """Each shipped example file must have shapes_runways with the
    current 6-column schema; legacy 8-column files break the runway
    copy in create_output.py."""
    cols = _shapes_runways_columns(path)
    assert len(cols) == len(EXPECTED_COLUMNS), (
        f"{name}: shapes_runways has {len(cols)} columns "
        f"(expected {len(EXPECTED_COLUMNS)}). Columns present: {cols}. "
        f"If any of {DROPPED_COLUMNS} are present, the file is on the "
        f"legacy 8-column schema and must be migrated with: "
        f"python scripts/migrate_alaqs.py {path} --drop-extra-columns"
    )


@pytest.mark.parametrize("name,path", EXAMPLE_FILES.items())
def test_shapes_runways_has_expected_column_names_in_order(name, path):
    """Lock both column names AND their order: create_output.py uses
    a positional INSERT so a reordering would silently corrupt data."""
    cols = _shapes_runways_columns(path)
    assert cols == EXPECTED_COLUMNS, (
        f"{name}: shapes_runways column names/order drifted.\n"
        f"  expected: {EXPECTED_COLUMNS}\n"
        f"  actual:   {cols}"
    )


@pytest.mark.parametrize("name,path", EXAMPLE_FILES.items())
def test_shapes_runways_has_no_legacy_columns(name, path):
    """Catch the specific failure mode: presence of dropped columns."""
    cols = set(_shapes_runways_columns(path))
    leaked = cols & DROPPED_COLUMNS
    assert not leaked, (
        f"{name}: shapes_runways still carries legacy columns {leaked}. "
        f"Re-migrate with: "
        f"python scripts/migrate_alaqs.py {path} --drop-extra-columns"
    )


@pytest.mark.parametrize("name,path", EXAMPLE_FILES.items())
def test_shapes_runways_data_intact_after_migration(name, path):
    """The migration script must not lose the runway row. Both files
    should retain the single 06/24 runway with its known capacity and
    touchdown values from the EHRD training-data study."""
    con = sqlite3.connect(str(path))
    try:
        rows = con.execute(
            "SELECT runway_id, capacity, touchdown, instudy " "FROM shapes_runways"
        ).fetchall()
    finally:
        con.close()

    assert len(rows) == 1, f"{name}: expected 1 runway, found {len(rows)}"
    runway_id, capacity, touchdown, instudy = rows[0]
    assert (
        runway_id == "06/24"
    ), f"{name}: runway_id drifted from '06/24' to {runway_id!r}"
    assert capacity == 60, f"{name}: capacity drifted from 60 to {capacity}"
    assert touchdown == 250, f"{name}: touchdown drifted from 250 to {touchdown}"
    assert int(instudy) == 1, f"{name}: instudy drifted from 1 to {instudy}"
