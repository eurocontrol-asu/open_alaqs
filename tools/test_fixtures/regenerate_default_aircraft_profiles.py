#!/usr/bin/env python3
"""
Regenerate the `default_aircraft_profiles` table in 6 .alaqs fixture files
from the canonical `open_alaqs/database/data/default_aircraft_profiles.csv`.

WHY THIS EXISTS
---------------
The .alaqs files are SQLite databases that ship pre-populated with the
profile catalogue as of their creation date. Since then the canonical CSV
has accumulated 8 new profiles (A321-232-A-1 + 7 × COMJET-*) and an
extension of JET-SMALL-A-1 from 13 to 27 points (finer trajectory).

`test_example_csv[EHRD_out-default_aircraft_profiles]` was marked xfail
because the example DB had 8730 rows versus the CSV's 8836. This isn't a
bug, just a stale fixture. Bringing every .alaqs into alignment with the
current CSV removes the drift.

USAGE
-----
    QT_QPA_PLATFORM=offscreen python3 tests/regenerate_default_aircraft_profiles.py

WHAT THIS DOES
--------------
For each of the 6 target .alaqs files:
  1. Opens the SQLite file
  2. DELETEs every row in `default_aircraft_profiles`
  3. INSERTs all rows from `default_aircraft_profiles.csv` in canonical
     column order
  4. VACUUMs the database to reclaim space

Column ordering: the DB schema stores columns as (oid, profile_id, ..., fuel_flow_kgm,
mode, course), while the CSV stores (mode, course, fuel_flow_kgm) at the
end. We insert by explicit column names so the order difference is a
non-issue.

RE-RUNNABLE. Byte-identical output across runs assuming CSV is unchanged.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = (
    REPO_ROOT / "open_alaqs" / "database" / "data" / "default_aircraft_profiles.csv"
)

ALAQS_FILES = [
    REPO_ROOT / "example" / "training" / "training.alaqs",
    REPO_ROOT / "example" / "training" / "training_out.alaqs",
    REPO_ROOT / "tests" / "data" / "ANP" / "ANP.alaqs",
    REPO_ROOT / "tests" / "data" / "ANP" / "ANP_out.alaqs",
    REPO_ROOT / "tests" / "data" / "AIRPORT_A" / "AIRPORT_A.alaqs",
    REPO_ROOT / "tests" / "data" / "AIRPORT_A" / "AIRPORT_A_out.alaqs",
    REPO_ROOT / "open_alaqs" / "core" / "templates" / "project.alaqs",
]

# Columns that should be parsed as numeric from the CSV. Everything else
# stays as string (or is left NULL if empty).
NUMERIC_COLUMNS = {
    "oid",
    "stage",
    "point",
    "weight_kgs",
    "x_m",
    "y_m",
    "z_m",
    "tas_metres",
    "power",
    "fuel_flow_kgm",
}


def load_csv_rows() -> tuple[list[str], list[dict]]:
    """Return (column_names, list_of_row_dicts) from the canonical CSV."""
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        rows = []
        for row in reader:
            # Normalize: empty strings → None (SQL NULL); numeric columns
            # to the correct type.
            clean = {}
            for col, val in row.items():
                if val == "":
                    clean[col] = None
                elif col in NUMERIC_COLUMNS:
                    # oid and point and stage are ints; others are floats.
                    try:
                        if col in ("oid", "point", "stage"):
                            clean[col] = int(val)
                        else:
                            clean[col] = float(val)
                    except ValueError:
                        clean[col] = val
                else:
                    clean[col] = val
            rows.append(clean)
    return columns, rows


def regenerate_one(alaqs_path: Path, columns: list[str], rows: list[dict]) -> None:
    """Replace the default_aircraft_profiles table contents in one .alaqs file."""
    if not alaqs_path.exists():
        print(f"  SKIP (not found): {alaqs_path}")
        return

    conn = sqlite3.connect(alaqs_path)
    try:
        # Verify the table exists and its schema matches
        db_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(default_aircraft_profiles)")
        }
        csv_cols = set(columns)
        missing_in_db = csv_cols - db_cols
        extra_in_db = db_cols - csv_cols
        if missing_in_db:
            print(f"  WARN: {alaqs_path.name}: DB missing CSV columns {missing_in_db}")
        if extra_in_db:
            print(f"  WARN: {alaqs_path.name}: DB has extra columns {extra_in_db}")

        # Row count before
        before = conn.execute(
            "SELECT COUNT(*) FROM default_aircraft_profiles"
        ).fetchone()[0]

        # Wipe and re-populate atomically
        conn.execute("DELETE FROM default_aircraft_profiles")

        # Build INSERT with explicit column names (handles schema order
        # differences transparently)
        usable_cols = [c for c in columns if c in db_cols]
        placeholders = ", ".join("?" for _ in usable_cols)
        insert_sql = (
            f"INSERT INTO default_aircraft_profiles "
            f"({', '.join(usable_cols)}) VALUES ({placeholders})"
        )
        conn.executemany(
            insert_sql, [tuple(row[c] for c in usable_cols) for row in rows]
        )
        conn.commit()

        after = conn.execute(
            "SELECT COUNT(*) FROM default_aircraft_profiles"
        ).fetchone()[0]
        print(f"  {alaqs_path.name}: {before} → {after} rows")
    finally:
        conn.close()

    # VACUUM runs outside a transaction
    conn = sqlite3.connect(alaqs_path)
    try:
        conn.execute("VACUUM")
    except sqlite3.OperationalError as e:
        print(f"  VACUUM failed on {alaqs_path.name}: {e}")
    finally:
        conn.close()


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: canonical CSV not found at {CSV_PATH}")
        return 1

    columns, rows = load_csv_rows()
    print(f"Canonical CSV: {len(rows)} rows across {len(columns)} columns")
    print()

    for alaqs_path in ALAQS_FILES:
        regenerate_one(alaqs_path, columns, rows)

    print()
    print("Done. Remove the xfail mark in tests/test_database.py:")
    print('  _DRIFTED_TABLES = {"default_aircraft_profiles"}  # → remove this entry')
    return 0


if __name__ == "__main__":
    sys.exit(main())
