"""
compute_parking: hourly emissions for parking lots.

SCOPE — IMPORTANT:
    This module is a SPREADER, not a calculator. It reads the per-vehicle
    emission factors that the upstream OpenALAQS plugin already wrote
    into the `shapes_parking` table (`nox_gm_vh`, `pm10_gm_vh`, etc.)
    and multiplies them by movement counts and the temporal profile.

    It does NOT run COPERT5. It does NOT apply cold-start logic. It
    does NOT apply parking-specific scaling factors.

    Whatever EFs are in the .alaqs file are what the pipeline uses.
    For studies that need the PR2 cold-start fix (cold-start applied
    at trip scale, not parking-segment scale), the upstream plugin
    run that built the .alaqs file must include the PR2 patches.

    See the package README for the full workflow.

Each row in shapes_parking carries:
    - vehicle_year             annual movement count
    - distance, idle_time, speed   (used by the upstream plugin to
                                    compute g/vh; not used here)
    - hour/daily/month_profile names
    - {nox,co,hc,sox,pm10,p1,p2}_gm_vh   per-vehicle EFs, pre-computed

Annual emission per pollutant:
    annual_kg = ef_g_per_vh * vehicle_year / 1000

The spread across the calendar year (8760 or 8784 hours) uses the same activity-profile mechanism
as compute_road.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from openalaqs_standalone._profiles import (
    STATIONARY_POLLUTANTS,
    hourly_multipliers,
    hourly_timestamps,
    load_profiles,
    spread_annual,
    window_mask,
)

# Mapping ALAQS column names -> standardised pollutant labels.
#   pm10_gm_vh = total PM10 (g/vh)
#   p1_gm_vh   = PM0.1 ultrafine fraction (NOT used here)
#   p2_gm_vh   = PM2.5 fraction (g/vh)
PARKING_POLLUTANT_COLS = {
    "nox": "nox_gm_vh",
    "co": "co_gm_vh",
    "hc": "hc_gm_vh",
    "sox": "sox_gm_vh",
    "pm10": "pm10_gm_vh",
    "pm25": "p2_gm_vh",
}


def _annual_kg(ef_g_per_vh: float, vehicle_year: float) -> float:
    if not all(np.isfinite([ef_g_per_vh, vehicle_year])):
        return 0.0
    if ef_g_per_vh <= 0 or vehicle_year <= 0:
        return 0.0
    grams = ef_g_per_vh * vehicle_year
    return grams / 1000.0


def compute_parking_emissions(
    alaqs_path: Path,
    year: int,
    pollutants: Optional[list] = None,
    time_window: Optional[tuple] = None,
) -> pd.DataFrame:
    """Compute hourly emissions for all parking lots.

    Vectorised the same way as compute_road_emissions: builds per-
    (source, pollutant) ndarrays then vstacks once at the end.
    """
    if pollutants is None:
        pollutants = list(STATIONARY_POLLUTANTS)
    pol_cols = {p: PARKING_POLLUTANT_COLS[p] for p in pollutants}

    conn = sqlite3.connect(str(alaqs_path))
    try:
        profiles = load_profiles(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM shapes_parking WHERE instudy = '1'")
        cols = [d[0] for d in cur.description]
        parkings = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

    timestamps = hourly_timestamps(year)
    len(timestamps)
    # Window filter: if time_window is given, drop the hours
    # outside [start, end). The per-hour mass for kept hours is
    # unchanged, so conservation per kept hour holds. Half-open
    # convention matches _profiles.window_mask. Full-year run is
    # the all-True case (no slicing penalty).
    if time_window is not None:
        _start, _end = time_window
        _mask = window_mask(timestamps, _start, _end)
        timestamps = timestamps[_mask]
    else:
        _mask = None
    n_h = len(timestamps)
    ts_arr = timestamps.values

    chunks_ts: list[np.ndarray] = []
    chunks_sid: list[np.ndarray] = []
    chunks_pol: list[np.ndarray] = []
    chunks_kg: list[np.ndarray] = []

    for r in parkings:
        source_id = f"parking:{r['parking_id']}"
        try:
            veh_year = float(r.get("vehicle_year") or 0.0)
        except (TypeError, ValueError):
            continue
        if veh_year <= 0:
            continue

        mults = hourly_multipliers(
            profiles,
            r.get("hour_profile"),
            r.get("daily_profile"),
            r.get("month_profile"),
            year,
        )

        for pol, col in pol_cols.items():
            ef = float(r.get(col) or 0.0)
            if ef <= 0.0:
                continue
            annual_kg = _annual_kg(ef, veh_year)
            if annual_kg <= 0.0:
                continue
            hourly_kg = spread_annual(annual_kg, mults)
            if _mask is not None:
                hourly_kg = hourly_kg[_mask]
            chunks_ts.append(ts_arr)
            chunks_sid.append(np.full(n_h, source_id, dtype=object))
            chunks_pol.append(np.full(n_h, pol, dtype=object))
            chunks_kg.append(hourly_kg.astype(np.float64))

    if not chunks_kg:
        return pd.DataFrame(
            columns=["timestamp", "source_id", "pollutant", "kg_in_hour"]
        )

    df = pd.DataFrame(
        {
            "timestamp": np.concatenate(chunks_ts),
            "source_id": np.concatenate(chunks_sid),
            "pollutant": np.concatenate(chunks_pol),
            "kg_in_hour": np.concatenate(chunks_kg),
        }
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alaqs_file", type=Path)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--pollutants", default=",".join(STATIONARY_POLLUTANTS))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    pols = [p.strip() for p in args.pollutants.split(",")]
    df = compute_parking_emissions(args.alaqs_file, args.year, pols)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"Wrote {len(df):,} rows to {args.out}")
    print(f"  Sources: {df['source_id'].nunique()}")
    print(f"  Pollutants: {sorted(df['pollutant'].unique())}")
    print(f"  Hours:    {df['timestamp'].nunique()}")
    annual = df.groupby("pollutant")["kg_in_hour"].sum()
    print("  Annual totals (kg):")
    for p, v in annual.items():
        print(f"    {p:6} = {v:.2f}")


if __name__ == "__main__":
    main()
