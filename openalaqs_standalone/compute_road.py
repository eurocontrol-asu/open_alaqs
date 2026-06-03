"""
compute_road: hourly emissions for roadway segments.

SCOPE — IMPORTANT:
    This module is a SPREADER, not a calculator. It reads the per-km
    emission factors that the upstream OpenALAQS plugin already wrote
    into the `shapes_roadways` table (`nox_gm_km`, `pm10_gm_km`, etc.)
    and multiplies them by distance, vehicle counts, and the temporal
    profile.

    It does NOT run COPERT5. It does NOT apply fleet composition.
    It does NOT compute cold-start contributions.

    The .alaqs file must therefore have been produced by a prior plugin
    run that includes any required EF adjustments (e.g. PR2 cold-start
    fix). Whatever is in the table is what the standalone pipeline
    uses.

    See the package README for the full workflow and the rationale.

Each row in shapes_roadways carries:
    - distance (m)             segment length
    - vehicle_year             annual vehicle count for the segment
    - hour/daily/month_profile names of activity profiles
    - {nox,co,hc,sox,pm10,p1,p2}_gm_km   EFs in g/(vkm), pre-computed

For each segment and each pollutant, the annual emission is:
    annual_kg = ef_g_per_km * (distance_m / 1000) * vehicle_year / 1000

We then spread annual_kg across the calendar year (8760 or 8784 hours) using the profile triplet,
producing one row per (source_id, timestamp, pollutant) at hourly
resolution.
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
#
# The OpenALAQS column convention varies between source types because
# different upstream code paths populate different columns:
#
# Roadways (populated by tools/copert5.py from g/km EFs):
#   pm10_gm_km  = total PM10 (g/km)
#   p1_gm_km    = PM0.1 ultrafine fraction (g/km)
#   p2_gm_km    = PM2.5 fraction (g/km)   — typically equals pm10_gm_km
#                 for exhaust-only road EFs (no coarse fraction modelled),
#                 which is what the plugin emits.
#
# Parkings (populated by tools/copert5.py for parking):
#   pm10_gm_vh  = total PM10 (g/vh)
#   p1_gm_vh    = empty / 0 in current OpenALAQS
#   p2_gm_vh    = PM2.5 fraction (g/vh)
#
# Both source types use p2 for PM2.5 — historic confusion in this
# file's comments (claiming "p1 holds PM2.5 in roads, verified against
# EHRD parking totals") conflated parking and road validation. The
# parking module's PARKING_POLLUTANT_COLS already maps pm25 -> p2_gm_vh;
# the road mapping below now mirrors that, and matches the QGIS plugin's
# RoadwaySourceModule data on real .alaqs files (p2_gm_km = pm10_gm_km;
# p1_gm_km is ~10x smaller, the ultrafine fraction).
ROAD_POLLUTANT_COLS = {
    "nox": "nox_gm_km",
    "co": "co_gm_km",
    "hc": "hc_gm_km",
    "sox": "sox_gm_km",
    "pm10": "pm10_gm_km",
    "pm25": "p2_gm_km",
}


def _geodesic_length_m(geom_blob) -> float:
    """Geodesic length of a SpatiaLite-BLOB LineString in metres.

    Mirrors the QGIS plugin's
    ``spatial.getDistanceOfLineStringXY(geom_wkt, 3857, 4326)``:
    reproject EPSG:3857 vertices to WGS84 and sum geodesic distances
    between consecutive vertices on the WGS84 ellipsoid. This gives
    the true ground length, which is what the EFs (g/vkm) are
    multiplied against — Web Mercator's planar length would be
    distorted by ~1.5× at mid-latitudes.

    Returns 0.0 on any error (NULL blob, parse failure, non-line
    geometry, single-vertex line). The caller skips the road in that
    case, matching the column-based path.
    """
    if not geom_blob:
        return 0.0
    try:
        from pyproj import Geod, Transformer

        from openalaqs_standalone.geometry import spatialite_blob_to_shapely

        geom = spatialite_blob_to_shapely(geom_blob)
    except Exception:
        return 0.0
    coords = list(getattr(geom, "coords", []))
    if len(coords) < 2:
        return 0.0
    _to_wgs = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    _geod = Geod(ellps="WGS84")
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
        lon1, lat1 = _to_wgs.transform(x1, y1)
        lon2, lat2 = _to_wgs.transform(x2, y2)
        try:
            _, _, d_m = _geod.inv(lon1, lat1, lon2, lat2)
        except Exception:
            continue
        if d_m and np.isfinite(d_m):
            total += float(d_m)
    return total


def _annual_kg(ef_g_per_km: float, distance_m: float, vehicle_year: float) -> float:
    """g/km * km * vehicles -> g, then convert to kg."""
    if not all(np.isfinite([ef_g_per_km, distance_m, vehicle_year])):
        return 0.0
    if ef_g_per_km <= 0 or distance_m <= 0 or vehicle_year <= 0:
        return 0.0
    distance_km = distance_m / 1000.0
    grams = ef_g_per_km * distance_km * vehicle_year
    return grams / 1000.0


def compute_road_emissions(
    alaqs_path: Path,
    year: int,
    pollutants: Optional[list] = None,
    time_window: Optional[tuple] = None,
) -> pd.DataFrame:
    """Compute hourly emissions for all roadway segments.

    Returns a DataFrame with columns:
        timestamp     timestamp[us]
        source_id     str   ("road:OostSidelinge_001")
        pollutant     str   (nox, pm10, pm25, ...)
        kg_in_hour    float

    Vectorised: builds one ndarray per (source, pollutant), then
    flattens to a long-form dataframe in one pass. Memory scales as
    O(n_sources * n_pollutants * n_hours_in_year).
    """
    if pollutants is None:
        pollutants = list(STATIONARY_POLLUTANTS)
    pol_cols = {p: ROAD_POLLUTANT_COLS[p] for p in pollutants}

    conn = sqlite3.connect(str(alaqs_path))
    try:
        profiles = load_profiles(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM shapes_roadways WHERE instudy = '1'")
        cols = [d[0] for d in cur.description]
        roadways = [dict(zip(cols, row)) for row in cur.fetchall()]
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

    # Stage per-source data, then vstack at the end
    chunks_ts: list[np.ndarray] = []
    chunks_sid: list[np.ndarray] = []
    chunks_pol: list[np.ndarray] = []
    chunks_kg: list[np.ndarray] = []

    ts_arr = timestamps.values  # ndarray[datetime64[ns]]

    for r in roadways:
        source_id = f"road:{r['roadway_id']}"
        raw_distance = r.get("distance")
        try:
            # `distance` column NULL: fall back to geometry length, matching
            # the QGIS plugin's RoadwaySources.getLength() behaviour. This
            # is the EAP case (and any study where the column wasn't
            # pre-populated). The plugin reprojects EPSG:3857 vertices to
            # WGS84 and sums geodesic distances (see
            # core/tools/spatial.getDistanceOfLineStringXY), so we do the
            # same with pyproj.Geod via _geodesic_length_m.
            #
            # `distance` column explicitly 0 (or negative): keep as 0 and
            # let the >0 filter below drop the source. The plugin treats
            # an explicit 0 as "this road has no length" and excludes it
            # from emissions; the synthetic test fixture ZERO_DIST relies
            # on this distinction (it has a 100m geometry but distance=0
            # to assert the column is the authoritative driver when set).
            if raw_distance is None:
                distance_m = _geodesic_length_m(r.get("geometry"))
            else:
                distance_m = float(raw_distance)
            veh_year = float(r.get("vehicle_year") or 0.0)
        except (TypeError, ValueError):
            continue
        if distance_m <= 0 or veh_year <= 0:
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
            annual_kg = _annual_kg(ef, distance_m, veh_year)
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
    parser.add_argument(
        "--pollutants",
        default=",".join(STATIONARY_POLLUTANTS),
        help="Comma-separated pollutant list",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    pols = [p.strip() for p in args.pollutants.split(",")]
    df = compute_road_emissions(args.alaqs_file, args.year, pols)
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
