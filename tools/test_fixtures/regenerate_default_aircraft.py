#!/usr/bin/env python3
"""
Bring the default profile columns of the `default_aircraft` table in the
.alaqs fixture files in line with the canonical
`open_alaqs/database/data/default_aircraft.csv`.

WHAT THIS DOES
--------------
For each target .alaqs file, every row whose `icao` is in the CSV gets the
CSV's `departure_profile` and `arrival_profile`. Nothing else is written:
other columns, and rows that are not in the CSV (study-specific types such as
helicopters added to a fixture), are left as they are. A fixture whose
`default_aircraft` is not a copy of the CSV (another column of a CSV type
differs, e.g. a study with its own engine assignments) is skipped and left
unchanged.

USAGE
-----
    python3 tools/test_fixtures/regenerate_default_aircraft.py

RE-RUNNABLE. Running it twice changes nothing the second time.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "open_alaqs" / "database" / "data" / "default_aircraft.csv"

# Same targets as regenerate_default_aircraft_profiles.py.
ALAQS_FILES = [
    REPO_ROOT / "example" / "training" / "training.alaqs",
    REPO_ROOT / "example" / "training" / "training_out.alaqs",
    REPO_ROOT / "tests" / "data" / "ANP" / "ANP.alaqs",
    REPO_ROOT / "tests" / "data" / "ANP" / "ANP_out.alaqs",
    REPO_ROOT / "tests" / "data" / "AIRPORT_A" / "AIRPORT_A.alaqs",
    REPO_ROOT / "tests" / "data" / "AIRPORT_A" / "AIRPORT_A_out.alaqs",
    REPO_ROOT / "open_alaqs" / "core" / "templates" / "project.alaqs",
]

PROFILE_COLUMNS = ("departure_profile", "arrival_profile")
CHECK_COLUMNS = ("name", "class", "engine_count", "engine")


def norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def regenerate_one(path: Path, csv_rows: dict[str, dict]) -> None:
    if not path.exists():
        print(f"  SKIP (not found): {path}")
        return
    conn = sqlite3.connect(path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(default_aircraft)")]
        db = {
            r[cols.index("icao")]: dict(zip(cols, r))
            for r in conn.execute("SELECT * FROM default_aircraft")
        }
        for icao, row in csv_rows.items():
            if icao not in db:
                continue
            for c in CHECK_COLUMNS:
                if norm(db[icao][c]) != norm(row[c]):
                    print(
                        f"  SKIP {path.name}: its default_aircraft is not a copy of "
                        f"the CSV ({icao} {c}: {db[icao][c]!r} vs {row[c]!r}); "
                        "left unchanged"
                    )
                    return
        changed = 0
        for icao, row in csv_rows.items():
            if icao not in db:
                continue
            if tuple(norm(db[icao][c]) for c in PROFILE_COLUMNS) != tuple(
                row[c] for c in PROFILE_COLUMNS
            ):
                conn.execute(
                    "UPDATE default_aircraft SET departure_profile = ?, "
                    "arrival_profile = ? WHERE icao = ?",
                    (row["departure_profile"], row["arrival_profile"], icao),
                )
                changed += 1
        conn.commit()
        print(f"  {path.name}: {changed} types updated, {len(db)} rows")
    finally:
        conn.close()
    if not changed:
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def main() -> int:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        csv_rows = {r["icao"]: r for r in csv.DictReader(f)}
    print(f"Canonical CSV: {len(csv_rows)} types")
    for p in ALAQS_FILES:
        regenerate_one(p, csv_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
