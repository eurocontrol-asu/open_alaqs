"""
adapt_meteo: convert OpenALAQS meteo data to the standard format
expected by austal_prep.

Two input modes:

1. From an .alaqs SpatiaLite database (uses tbl_InvMeteo).
2. From a standalone meteo CSV (OpenALAQS-style export).

OpenALAQS meteo schema (in tbl_InvMeteo or CSV export):
    Scenario, DateTime, Temperature, Humidity, RelativeHumidity,
    SeaLevelPressure, WindSpeed, WindDirection, ObukhovLength,
    MixingHeight, [SpeedOfSound]

Standard meteo.csv expected by austal_prep:
    timestamp                ISO 8601
    wind_direction_deg       0..360 (degrees from north, clockwise)
    wind_speed_ms            m/s
    obukhov_length_m         m (positive = stable; OpenALAQS uses 99999 for neutral)
    mixing_height_m          m (optional, set 'mixing_height_included' in
                                config.json to false if unavailable)

Optional year shift:
    If the inventory year differs from the meteo year (e.g. 2025
    inventory + 2024 KNMI data), use --year-shift-to to remap
    timestamps to the inventory year.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def _from_alaqs_db(alaqs_path: Path) -> pd.DataFrame:
    """Extract tbl_InvMeteo from an .alaqs SpatiaLite database."""
    conn = sqlite3.connect(str(alaqs_path))
    try:
        df = pd.read_sql_query("SELECT * FROM tbl_InvMeteo", conn)
    finally:
        conn.close()
    return df


def _from_csv(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def adapt_meteo(
    in_path: Path,
    out_csv: Path,
    year_shift_to: int | None = None,
    time_window: tuple | None = None,
) -> int:
    """Adapt meteo from either an .alaqs database or an OpenALAQS CSV.

    If `time_window=(start, end)` is given, only rows whose
    `timestamp` falls in the half-open interval `[start, end)` are
    written. The year shift, when also given, is applied first; the
    window is then evaluated against the post-shift timestamps. This
    matches the convention used by the stationary computes.
    """
    if in_path.suffix.lower() == ".alaqs":
        df = _from_alaqs_db(in_path)
    else:
        df = _from_csv(in_path)

    # Normalise column names by stripping any "(unit)" suffix.
    # The OpenALAQS QGIS plugin writes meteo CSVs with headers like
    # "DateTime(YYYY-mm-dd hh:mm:ss)" and "WindSpeed(m/s)" -- units
    # baked into the column name. The rest of this function matches
    # columns by their plain name ("DateTime", "WindSpeed", etc.), so
    # we strip the parenthetical suffix here and everything downstream
    # works for both header conventions (plain names from the .alaqs
    # database read, suffixed names from the plugin's CSV export).
    import re as _re

    df.columns = [_re.sub(r"\s*\([^)]*\)\s*$", "", str(c)).strip() for c in df.columns]

    # Try to find the timestamp column under either name
    if "DateTime" in df.columns:
        ts_col = "DateTime"
    elif "timestamp" in df.columns:
        ts_col = "timestamp"
    else:
        raise ValueError(
            f"Input meteo data must have a 'DateTime' or 'timestamp' "
            f"column. Found: {list(df.columns)}"
        )

    df["timestamp"] = pd.to_datetime(df[ts_col])
    if year_shift_to is not None:
        # Replace the year while keeping month/day/hour. Drop Feb 29
        # if shifting from a leap year to a non-leap year.
        is_feb29 = (df["timestamp"].dt.month == 2) & (df["timestamp"].dt.day == 29)
        df = df.loc[~is_feb29].copy()
        df["timestamp"] = df["timestamp"].apply(lambda t: t.replace(year=year_shift_to))

    rename_map = {
        "WindDirection": "wind_direction_deg",
        "WindSpeed": "wind_speed_ms",
        "ObukhovLength": "obukhov_length_m",
        "MixingHeight": "mixing_height_m",
    }
    for old, new in rename_map.items():
        if old in df.columns:
            df[new] = df[old]

    keep = ["timestamp"] + [v for v in rename_map.values() if v in df.columns]
    out = df[keep].copy()
    out = out.sort_values("timestamp").reset_index(drop=True)

    # Apply the time window if requested. Evaluated against the
    # (possibly already year-shifted) timestamps so a window expressed
    # in inventory-year coordinates filters correctly even when the
    # raw meteo was for a different year.
    if time_window is not None and len(out) > 0:
        _start, _end = time_window
        if _start is not None:
            out = out.loc[out["timestamp"] >= pd.Timestamp(_start)]
        if _end is not None:
            out = out.loc[out["timestamp"] < pd.Timestamp(_end)]
        out = out.reset_index(drop=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    return len(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "in_path", type=Path, help="Input: either .alaqs database or meteo CSV"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--year-shift-to", type=int, default=None, help="Re-stamp each row to this year"
    )
    args = parser.parse_args(argv)

    n = adapt_meteo(args.in_path, args.out, args.year_shift_to)
    print(f"Wrote {n} hours to {args.out}")


if __name__ == "__main__":
    main()
