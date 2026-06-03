"""
Load receptor points and meteorological time series.

Receptor CSV format (matches the EHRD pipeline output):
    name, x, y, z      where x, y are absolute UTM metres and z is m
                       above ground

Meteo CSV format: long-form with at minimum these columns:
    timestamp           ISO 8601 or sufficient to parse
    wind_direction_deg  0..360 (999 for VRB / calm)
    wind_speed_ms       m/s
    obukhov_length_m    m (99999 for neutral stability)
    mixing_height_m     m  (optional, only required if
                            study_config.mixing_height_included=True)

This is the cross-project schema. Project-specific meteo CSVs (e.g.
EHRD's tbl_InvMeteo dump) need a one-line adapter to rename columns.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def load_receptors(
    receptor_csv: Path,
    reference_x: float,
    reference_y: float,
) -> Tuple[List[float], List[float], List[float]]:
    """Read a receptor CSV and return (xp, yp, hp) lists in metres
    relative to the (reference_x, reference_y) origin.

    The CSV must have columns: name, x, y, z. x and y are absolute
    UTM metres in the same UTM zone as reference_x/y. z is height
    above ground in metres.

    A header-only file (zero rows) is valid and returns three empty
    lists. Without an explicit float cast pandas infers object dtype
    on the empty x/y columns and the subtraction below raises
    TypeError: Expected numeric dtype, got object instead.
    """
    df = pd.read_csv(receptor_csv)
    required = {"x", "y", "z"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"receptor CSV missing columns: {sorted(missing)}")
    x = df["x"].astype(float)
    y = df["y"].astype(float)
    z = df["z"].astype(float)
    xp = (x - reference_x).round(2).tolist()
    yp = (y - reference_y).round(2).tolist()
    hp = z.round(2).tolist()
    return xp, yp, hp


def load_meteo(
    meteo_csv: Path,
    timestamps: List[datetime],
    mixing_height_included: bool,
) -> Dict[datetime, dict]:
    """Read meteo CSV and return a dict keyed by timestamp with one
    record per requested hour.

    Hours present in `timestamps` but missing from the CSV get
    AUSTAL-default sentinels:
      wind_direction_deg = 999     (calm/variable)
      wind_speed_ms      = 0.0
      obukhov_length_m   = 99999   (neutral)
      mixing_height_m    = 800.0   (default mixing layer depth)

    These match the AmbientCondition class defaults in upstream
    OpenALAQS (see PR2 fix).
    """
    df = pd.read_csv(meteo_csv, parse_dates=["timestamp"])
    # Deduplicate by timestamp BEFORE setting the index. When the meteo
    # CSV has multiple rows per timestamp (e.g. a 30-minute logger
    # rounded to the hour, or two stations merged), df.loc[ts] later
    # returns a DataFrame instead of a Series and pd.isna(<Series>)
    # raises "truth value of a Series is ambiguous." Keep the last
    # row per timestamp — convention is that later writes overwrite
    # earlier ones in tabular meteo feeds.
    n_before = len(df)
    df = df.drop_duplicates(subset="timestamp", keep="last")
    if len(df) < n_before:
        # Don't silently drop; surface to the user how many rows went.
        # logging would be cleaner but austal_prep.io has no logger
        # convention here yet.
        print(
            f"[load_meteo] dropped {n_before - len(df)} duplicate "
            f"timestamp rows from {meteo_csv.name}"
        )
    df = df.set_index("timestamp")

    DEFAULTS = {
        "wind_direction_deg": 999.0,
        "wind_speed_ms": 0.0,
        "obukhov_length_m": 99999.0,
        "mixing_height_m": 800.0,
    }

    out: Dict[datetime, dict] = {}
    for ts in timestamps:
        if ts in df.index:
            row = df.loc[ts]
            # Defensive: if for any reason the dedup above didn't collapse
            # the index (e.g. a pandas version quirk on tz-aware columns),
            # take the first matching row rather than letting a DataFrame
            # leak through.
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            rec = {}
            for k, default in DEFAULTS.items():
                v = row.get(k, default) if k in df.columns else default
                if pd.isna(v):
                    v = default
                rec[k] = float(v)
        else:
            rec = dict(DEFAULTS)
        if not mixing_height_included:
            rec.pop("mixing_height_m", None)
        out[ts] = rec
    return out


def missing_meteo_hours(meteo_csv: Path, timestamps: List[datetime]) -> List[datetime]:
    """Return the subset of `timestamps` not present in the meteo CSV."""
    df = pd.read_csv(meteo_csv, parse_dates=["timestamp"])
    have = set(df["timestamp"].tolist())
    return [t for t in timestamps if pd.Timestamp(t) not in have]
