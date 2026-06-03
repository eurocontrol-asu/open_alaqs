"""
make_config: scaffold a config.json from .alaqs metadata.

Reads the airport reference point and basic study metadata from
user_study_setup, computes a default calculation grid centred on the
airport, and writes a config.json template consumed by `austal_prep`.

The output sets sensible defaults:
    qs                          = 3   (quality level)
    z0                          = 0.3 (urban/light forest)
    d0                          = 1.2 (= 4*z0)
    ha                          = 11.2 (anemometer height with displacement)
    grid                        75 x 75 cells of 250 m centred on airport
    sk                          AUSTAL default vertical layers
    max_receptors               = 20  (AUSTAL hard cap)
    source_aggregation          = "by_type_per_pollutant"
    grid_writer_mode            = "time_indexed"

These can be overridden on the command line. After scaffolding, edit
the JSON file directly to fine-tune for your study.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from pyproj import Transformer

# AUSTAL default vertical grid (sk values, m above ground)
DEFAULT_SK = [
    0,
    3,
    6,
    10,
    16,
    25,
    40,
    65,
    100,
    150,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    1000,
    1200,
    1500,
]


def _airport_metadata(alaqs_path: Path) -> dict:
    conn = sqlite3.connect(str(alaqs_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_study_setup LIMIT 1")
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if row is None:
            return {}
        return dict(zip(cols, row))
    finally:
        conn.close()


def _utm_zone_for_lon(lon_deg: float) -> int:
    """Compute the UTM zone for a longitude. EPSG = 32600 + zone for north."""
    zone = int((lon_deg + 180.0) // 6.0) + 1
    return 32600 + zone


def make_config(
    alaqs_path: Path,
    out_path: Path,
    title: str | None = None,
    grid_size: int = 75,
    grid_step_m: float = 250.0,
    qs: int = 3,
    z0: float = 0.3,
    d0: float | None = None,
    ha: float = 11.2,
    pollutants: list | None = None,
    year: int | None = None,
    utm_epsg: int | None = None,
) -> dict:
    meta = _airport_metadata(alaqs_path)
    title = title or meta.get("airport_name") or meta.get("project_name") or "Untitled"

    lat = float(meta.get("airport_latitude") or 0.0)
    lon = float(meta.get("airport_longitude") or 0.0)
    if utm_epsg is None:
        utm_epsg = _utm_zone_for_lon(lon) if lon != 0.0 else 32631
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    ref_x, ref_y = transformer.transform(lon, lat)

    # Centre the calc grid on the airport with a halo on the SW side
    # so source bboxes (anchored at xq = x0 + source_offset_cells * dd)
    # sit strictly inside the calc grid. Matches the QGIS plugin
    # convention (DEFAULT_CONCENTRATION_GRID_FACTOR = 2) and the
    # GridSpec.centered_on_reference() helper. Without this halo, the
    # grid file declared at xq with nx=grid_size cells overflows the
    # calc grid east/north edge by halo_cells * grid_step_m.
    halo_cells = 2
    x0 = -((grid_size / 2.0) + halo_cells) * grid_step_m
    y0 = -((grid_size / 2.0) + halo_cells) * grid_step_m

    if d0 is None:
        d0 = 4.0 * z0

    cfg = {
        "title": title,
        "qs": qs,
        "z0": z0,
        "d0": d0,
        "ha": ha,
        "os_options": "NOSTANDARD;SCINOTAT;Kmax=1",
        "pm10_fine_fraction": 0.9,
        # Runtime parameter: number of worker processes for the
        # per-source grid-file write loop. null/omitted -> os.cpu_count();
        # 1 -> serial path; >1 -> multiprocessing.Pool. Can be overridden
        # by the --processes CLI flag.
        "processes": None,
        "mixing_height_included": True,
        "grid_writer_mode": "time_indexed",
        "source_offset_cells": 2,
        "max_receptors": 20,
        "source_aggregation": "by_type_per_pollutant",
        "grid": {
            "dd": float(grid_step_m),
            "nx": int(grid_size),
            "ny": int(grid_size),
            "x0": float(x0),
            "y0": float(y0),
            "sk": DEFAULT_SK,
            "reference_x": float(ref_x),
            "reference_y": float(ref_y),
            "utm_epsg": int(utm_epsg),
        },
    }
    if pollutants is not None:
        cfg["selected_pollutants"] = list(pollutants)
    if year is not None:
        cfg["start_dt"] = f"{year}-01-01T00:00:00"
        cfg["end_dt"] = f"{year}-12-31T23:00:00"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cfg, indent=2))
    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alaqs_file", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--grid-size",
        type=int,
        default=75,
        help="Number of cells per side (default 75)",
    )
    parser.add_argument(
        "--grid-step",
        type=float,
        default=250.0,
        help="Cell size in metres (default 250)",
    )
    parser.add_argument("--qs", type=int, default=3)
    parser.add_argument("--z0", type=float, default=0.3)
    parser.add_argument("--d0", type=float, default=None)
    parser.add_argument("--ha", type=float, default=11.2)
    parser.add_argument(
        "--pollutants", default=None, help="Comma-separated, e.g. nox,pm10,pm25"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Sets start_dt/end_dt to this calendar year",
    )
    parser.add_argument(
        "--utm-epsg", type=int, default=None, help="Override auto-detected UTM zone"
    )
    args = parser.parse_args(argv)

    pols = [p.strip() for p in args.pollutants.split(",")] if args.pollutants else None
    cfg = make_config(
        args.alaqs_file,
        args.out,
        title=args.title,
        grid_size=args.grid_size,
        grid_step_m=args.grid_step,
        qs=args.qs,
        z0=args.z0,
        d0=args.d0,
        ha=args.ha,
        pollutants=pols,
        year=args.year,
        utm_epsg=args.utm_epsg,
    )
    print(f"Wrote {args.out}")
    print(f"  Title:     {cfg['title']}")
    print(
        f"  Grid:      {cfg['grid']['nx']}x{cfg['grid']['ny']} of {cfg['grid']['dd']}m"
    )
    print(f"  UTM zone:  {cfg['grid']['utm_epsg']}")
    print(
        f"  Reference: ({cfg['grid']['reference_x']:.2f}, {cfg['grid']['reference_y']:.2f})"
    )


if __name__ == "__main__":
    main()
