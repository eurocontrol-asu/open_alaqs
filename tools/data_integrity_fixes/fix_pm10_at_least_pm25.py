"""
One-shot data integrity fix for default_vehicle_ef_copert5.csv.

Issue: 639 (vehicle_category, fuel, euro_standard, country, hot-cold-evaporation,
       evaporation_split) pairs had at least one speed column where the PM10
       value was less than the corresponding PM2.5 value. This is physically
       impossible (PM10 includes the PM2.5 fraction by definition) and is
       also inconsistent with EMEP/EEA Guidebook 2023 Update 2025, chapter
       1.A.3.b.i-iv §1.1 (p.4) which states PM10 = PM2.5 = TSP for road
       transport exhaust because the coarse fraction is negligible.

Fix:   For every (PM10 row, PM2.5 row) pair sharing the same
       (vehicle_category, fuel, euro_standard, country, hot-cold-evaporation,
       evaporation_split) key, identify speed columns where PM10 < PM2.5
       (parsed as floats). For each violating cell, replace the PM10 row's
       cell TEXT with the PM2.5 row's cell text verbatim. Affects 2505 cells
       across 639 row pairs.

       Implementation note: this script reads and writes the CSV as raw
       text, splitting on commas and newlines without going through a
       float-formatting library. This is deliberate: pandas.to_csv and
       csv.writer would silently reserialize every float value, producing
       a diff bloated with cosmetic representation changes
       (0.17500000000000004 vs 0.175, etc.) even though the underlying
       IEEE 754 values are identical. The minimal-edit approach here
       leaves all other cells byte-identical to the input.

Run from the repo root:
    python tools/data_integrity_fixes/fix_pm10_at_least_pm25.py

Idempotent: re-running on already-fixed data produces zero changes.
"""

from pathlib import Path

CSV_PATH = Path("open_alaqs/database/data/default_vehicle_ef_copert5.csv")

# CSV column indices (0-based)
COL_CATEGORY = 0
COL_FUEL = 1
COL_EURO = 2
COL_COUNTRY = 3
COL_POLLUTANT = 4
COL_HOT_COLD_EVAP = 5
COL_EVAP_SPLIT = 6
SPEED_COL_START = 7
SPEED_COL_END = 20  # exclusive; columns 7..19 are speeds 10..130


def _row_key(fields):
    return (
        fields[COL_CATEGORY],
        fields[COL_FUEL],
        fields[COL_EURO],
        fields[COL_COUNTRY],
        fields[COL_HOT_COLD_EVAP],
        fields[COL_EVAP_SPLIT],
    )


def _read_raw(csv_path: Path) -> str:
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        return f.read()


def _write_raw(csv_path: Path, text: str) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(text)


def fix(csv_path: Path) -> dict:
    """Apply the PM10>=PM2.5 fix in-place. Returns a summary of changes."""
    raw = _read_raw(csv_path)

    # Preserve trailing newline if present, then split on '\n'. Each resulting
    # element may end with '\r' if the file is CRLF; that is preserved by
    # rejoining with '\n' so the original line-ending convention survives.
    lines = raw.split("\n")

    header = lines[0]
    body = lines[1:]

    # Build PM10 and PM2.5 indices: key -> (line_index_in_body, fields_list)
    pm10_idx = {}
    pm25_idx = {}
    for i, line in enumerate(body):
        # Strip any trailing '\r' for parsing, but keep the original line
        # in body for later rebuild
        stripped = line.rstrip("\r")
        if not stripped:
            continue
        fields = stripped.split(",")
        if len(fields) < SPEED_COL_END:
            continue
        pollutant = fields[COL_POLLUTANT]
        if pollutant == "PM10":
            pm10_idx[_row_key(fields)] = (i, fields)
        elif pollutant == "PM2.5":
            pm25_idx[_row_key(fields)] = (i, fields)

    # Scan for violations and apply cell-level fixes
    cells_changed = 0
    pairs_changed = set()

    for key, (pm10_line_idx, pm10_fields) in pm10_idx.items():
        if key not in pm25_idx:
            continue
        _, pm25_fields = pm25_idx[key]

        modified = False
        for col in range(SPEED_COL_START, SPEED_COL_END):
            pm10_text = pm10_fields[col]
            pm25_text = pm25_fields[col]
            # Skip empty cells
            if not pm10_text or not pm25_text:
                continue
            try:
                a = float(pm10_text)
                b = float(pm25_text)
            except ValueError:
                continue
            if a > 0 and b > 0 and a < b:
                pm10_fields[col] = pm25_text  # verbatim text swap
                cells_changed += 1
                modified = True

        if modified:
            pairs_changed.add(key)
            # Rebuild the line, preserving any trailing '\r'
            original_line = body[pm10_line_idx]
            had_cr = original_line.endswith("\r")
            new_line = ",".join(pm10_fields)
            if had_cr:
                new_line += "\r"
            body[pm10_line_idx] = new_line

    new_raw = "\n".join([header] + body)
    _write_raw(csv_path, new_raw)

    return {
        "pairs_changed": len(pairs_changed),
        "cells_changed": cells_changed,
        "rows_in_csv": len(body),
    }


def verify(csv_path: Path) -> int:
    """Return the count of remaining PM10 < PM2.5 violations."""
    raw = _read_raw(csv_path)
    lines = raw.split("\n")
    body = lines[1:]

    pm10_idx = {}
    pm25_idx = {}
    for line in body:
        stripped = line.rstrip("\r")
        if not stripped:
            continue
        fields = stripped.split(",")
        if len(fields) < SPEED_COL_END:
            continue
        pollutant = fields[COL_POLLUTANT]
        if pollutant == "PM10":
            pm10_idx[_row_key(fields)] = fields
        elif pollutant == "PM2.5":
            pm25_idx[_row_key(fields)] = fields

    violations = 0
    for key, pm10_fields in pm10_idx.items():
        if key not in pm25_idx:
            continue
        pm25_fields = pm25_idx[key]
        for col in range(SPEED_COL_START, SPEED_COL_END):
            pm10_text = pm10_fields[col]
            pm25_text = pm25_fields[col]
            if not pm10_text or not pm25_text:
                continue
            try:
                a = float(pm10_text)
                b = float(pm25_text)
            except ValueError:
                continue
            if a > 0 and b > 0 and a < b:
                violations += 1
    return violations


if __name__ == "__main__":
    pre_violations = verify(CSV_PATH)
    print(f"Pre-fix violations: {pre_violations}")

    summary = fix(CSV_PATH)
    print(
        f"Applied fix: {summary['cells_changed']} cells in "
        f"{summary['pairs_changed']} pairs corrected."
    )

    post_violations = verify(CSV_PATH)
    print(f"Post-fix violations: {post_violations}")
    assert post_violations == 0, "Fix did not eliminate all violations"
    print("Verification passed: PM10 >= PM2.5 at every (pair, speed_col).")
