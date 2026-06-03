"""
compute_point: hourly emissions for stationary point sources.

SCOPE - IMPORTANT:
    This module is a SPREADER, not a calculator. It reads the per-unit
    emission factors that the upstream OpenALAQS plugin already wrote
    into the `shapes_point_sources` table (`nox_kg_k`, `pm10_kg_k`,
    etc.) and multiplies them by ops_year and the temporal profile.

    It does NOT recompute EFs from default_stationary_ef templates.
    It does NOT apply substance/category logic. Whatever is in the
    `*_kg_k` columns is what the standalone uses.

    See the package README for the full workflow.

Each row in shapes_point_sources carries:
    - height, temperature, diameter, velocity   stack parameters
                                                (used by AUSTAL for plume rise,
                                                 not for emission calculation)
    - ops_year             annual operating quantity (typically operating hours
                           per year; "k" in the EF unit refers to this)
    - hour/daily/month_profile names of activity profiles
    - {co,hc,nox,sox,pm10,p1,p2}_kg_k   per-unit EFs in kg per "k"

Annual emission per pollutant:
    annual_kg = ef_kg_per_k * ops_year

The spread across the calendar year (8760 or 8784 hours) uses the same profile mechanism as
compute_road and compute_parking.

PM column convention:
    Following the parking convention (verified against EHRD baseline):
        pm10 <- pm10_kg_k    (total PM10)
        pm25 <- p2_kg_k      (PM2.5 fraction)
    The p1_kg_k column is assumed to be PM0.1 (ultrafine) and is not
    mapped to a standard label here. If your study uses point sources
    and the resulting PM2.5/PM10 ratio looks wrong, verify that the
    upstream plugin populated p2_kg_k with PM2.5 (not PM0.1) for your
    particular .alaqs file.
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

POINT_POLLUTANT_COLS = {
    "nox": "nox_kg_k",
    "co": "co_kg_k",
    "hc": "hc_kg_k",
    "sox": "sox_kg_k",
    "pm10": "pm10_kg_k",
    "pm25": "p2_kg_k",
}


def _annual_kg(ef_kg_per_k: float, ops_year: float) -> float:
    if not all(np.isfinite([ef_kg_per_k, ops_year])):
        return 0.0
    if ef_kg_per_k <= 0 or ops_year <= 0:
        return 0.0
    return ef_kg_per_k * ops_year


def compute_point_emissions(
    alaqs_path: Path,
    year: int,
    pollutants: Optional[list] = None,
    time_window: Optional[tuple] = None,
) -> pd.DataFrame:
    """Compute hourly emissions for all in-study point sources."""
    if pollutants is None:
        pollutants = list(STATIONARY_POLLUTANTS)
    pol_cols = {p: POINT_POLLUTANT_COLS[p] for p in pollutants}

    conn = sqlite3.connect(str(alaqs_path))
    try:
        profiles = load_profiles(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM shapes_point_sources WHERE instudy = '1'")
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
        # OpenALAQS schema uses the column name "source_id" inside the
        # shapes_point_sources table (different from the more general
        # naming we use). Map it to our standardised "point:<id>".
        raw_id = r.get("source_id") or r.get("oid")
        source_id = f"point:{raw_id}"
        try:
            ops_year = float(r.get("ops_year") or 0.0)
        except (TypeError, ValueError):
            continue
        if ops_year <= 0:
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
            annual_kg = _annual_kg(ef, ops_year) if ef > 0.0 else 0.0
            # Always emit a row per (source, hour, pollutant) for every
            # requested pollutant, even when EF is zero. The output is
            # then a complete grid with respect to `pollutants`, which
            # makes downstream consumers' lives easier (a missing
            # pollutant is unambiguously "we didn't ask for it" rather
            # than "the source had no EF for it"). Source-level filters
            # (`instudy='0'`, `ops_year<=0`) still drop the whole row.
            if annual_kg > 0.0:
                hourly_kg = spread_annual(annual_kg, mults)
                if _mask is not None:
                    hourly_kg = hourly_kg[_mask]
            else:
                hourly_kg = np.zeros(n_h, dtype=np.float64)
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
    df = compute_point_emissions(args.alaqs_file, args.year, pols)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"Wrote {len(df):,} rows to {args.out}")
    if len(df) == 0:
        print("  (No in-study point sources with non-zero ops_year and EFs)")
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
