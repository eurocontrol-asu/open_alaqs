"""
Sync the fixed default_vehicle_ef_copert5.csv into all .alaqs SQLite caches
that hold a copy of the table.

Run AFTER fix_pm10_at_least_pm25.py. Re-populates the embedded
default_vehicle_ef_copert5 table in each .alaqs file from the on-disk CSV.

Usage from the repo root:
    python tools/data_integrity_fixes/sync_csv_into_alaqs_caches.py

Idempotent: re-running on already-synced files produces zero net change.
"""

import sqlite3
from pathlib import Path

import pandas as pd

CSV_PATH = Path("open_alaqs/database/data/default_vehicle_ef_copert5.csv")
TABLE = "default_vehicle_ef_copert5"

# .alaqs files known to embed the EF table with the full 46435 rows.
# inventory.alaqs and Inventory.alaqs have the empty table only (no data);
# they are left alone.
TARGETS = [
    "open_alaqs/core/templates/project.alaqs",
    "example/training/training.alaqs",
    "example/training/training_out.alaqs",
    "tests/data/generic/generic_out.alaqs",
    "tests/data/ANP/ANP.alaqs",
    "tests/data/ANP/ANP_out.alaqs",
    "gse_application/tests/example_db.alaqs",
]


def sync_one(db_path: Path, csv_df: pd.DataFrame) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE}'"
        )
        if not cur.fetchone():
            return {"status": "skip (no table)", "rows_before": 0, "rows_after": 0}
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        before = cur.fetchone()[0]
        if before == 0:
            return {"status": "skip (empty table)", "rows_before": 0, "rows_after": 0}
        # Capture original column order from DB to preserve schema layout
        cur.execute(f"PRAGMA table_info({TABLE})")
        db_cols = [row[1] for row in cur.fetchall()]
        # Reorder CSV df to DB column order, drop any DB-only extras (e.g. oid)
        df_aligned = csv_df.copy()
        if "oid" in db_cols and "oid" not in df_aligned.columns:
            df_aligned.insert(0, "oid", range(1, len(df_aligned) + 1))
        df_aligned = df_aligned[[c for c in db_cols if c in df_aligned.columns]]
        # Replace table contents
        cur.execute(f"DELETE FROM {TABLE}")
        df_aligned.to_sql(TABLE, conn, if_exists="append", index=False)
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        after = cur.fetchone()[0]
        conn.commit()
        return {"status": "synced", "rows_before": before, "rows_after": after}
    finally:
        conn.close()


if __name__ == "__main__":
    csv_df = pd.read_csv(CSV_PATH)
    print(f"Source CSV: {CSV_PATH} ({len(csv_df)} rows)")
    for t in TARGETS:
        p = Path(t)
        if not p.exists():
            print(f"  {t}: missing, skip")
            continue
        result = sync_one(p, csv_df)
        print(f"  {t}: {result}")
    print("Done.")
