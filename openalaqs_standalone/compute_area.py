"""
compute_area: hourly emissions for area sources.

SCOPE - IMPORTANT:
    This module is a SPREADER, not a calculator. It reads the per-unit
    emission factors that the upstream OpenALAQS plugin already wrote
    into the `shapes_area_sources` table (`nox_kg_unit`, `pm10_kg_unit`,
    etc.) and multiplies them by unit_year and the temporal profile.

    See the package README for the full workflow.

Each row in shapes_area_sources carries:
    - height               release height above ground (m)
    - heat_flux            buoyancy in MW (used by AUSTAL for plume rise,
                           not for emission calculation)
    - unit_year            annual operating quantity ("unit" in the EF
                           refers to this; could be hours, units of fuel,
                           etc.)
    - hourly/daily/monthly_profile names of activity profiles
                           NOTE: the column names here use a slightly
                           different convention than other source types
                           (hourly_profile vs hour_profile, monthly_profile
                           vs month_profile)
    - {co,hc,nox,sox,pm10,p1,p2}_kg_unit   per-unit EFs

Annual emission per pollutant:
    annual_kg = ef_kg_per_unit * unit_year

PM column convention:
    Same as point sources:
        pm10 <- pm10_kg_unit    (total PM10)
        pm25 <- p2_kg_unit      (PM2.5 fraction)
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

AREA_POLLUTANT_COLS = {
    "nox": "nox_kg_unit",
    "co": "co_kg_unit",
    "hc": "hc_kg_unit",
    "sox": "sox_kg_unit",
    "pm10": "pm10_kg_unit",
    "pm25": "p2_kg_unit",
}


def _annual_kg(ef_kg_per_unit: float, unit_year: float) -> float:
    if not all(np.isfinite([ef_kg_per_unit, unit_year])):
        return 0.0
    if ef_kg_per_unit <= 0 or unit_year <= 0:
        return 0.0
    return ef_kg_per_unit * unit_year


def compute_area_emissions(
    alaqs_path: Path,
    year: int,
    pollutants: Optional[list] = None,
    time_window: Optional[tuple] = None,
) -> pd.DataFrame:
    """Compute hourly emissions for all in-study area sources."""
    if pollutants is None:
        pollutants = list(STATIONARY_POLLUTANTS)
    pol_cols = {p: AREA_POLLUTANT_COLS[p] for p in pollutants}

    conn = sqlite3.connect(str(alaqs_path))
    try:
        profiles = load_profiles(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM shapes_area_sources WHERE instudy = '1'")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
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

    for r in rows:
        raw_id = r.get("source_id") or r.get("oid")
        source_id = f"area:{raw_id}"
        try:
            unit_year = float(r.get("unit_year") or 0.0)
        except (TypeError, ValueError):
            continue
        if unit_year <= 0:
            continue

        # Note column name difference: hourly_profile / monthly_profile
        # (vs hour_profile / month_profile in road, parking, point)
        mults = hourly_multipliers(
            profiles,
            r.get("hourly_profile"),
            r.get("daily_profile"),
            r.get("monthly_profile"),
            year,
        )

        for pol, col in pol_cols.items():
            ef = float(r.get(col) or 0.0)
            if ef <= 0.0:
                continue
            annual_kg = _annual_kg(ef, unit_year)
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
    df = compute_area_emissions(args.alaqs_file, args.year, pols)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"Wrote {len(df):,} rows to {args.out}")
    if len(df) == 0:
        print("  (No in-study area sources with non-zero unit_year and EFs)")
        return
    print(f"  Sources: {df['source_id'].nunique()}")
    print(f"  Pollutants: {sorted(df['pollutant'].unique())}")
    print(f"  Hours:    {df['timestamp'].nunique()}")
    annual = df.groupby("pollutant")["kg_in_hour"].sum()
    print("  Annual totals (kg):")
    for p, v in annual.items():
        print(f"    {p:6} = {v:.2f}")


if __name__ == "__main__":
    main()
