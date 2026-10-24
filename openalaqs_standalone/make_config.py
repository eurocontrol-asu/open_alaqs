"""
make_config: scaffold a config.json from .alaqs metadata.

Reads the grid reference point from grid_3d_definition (the airport
reference point in user_study_setup if the grid definition is absent)
and basic study metadata from user_study_setup, computes a default
calculation grid centred on the grid reference point, and writes a config.json template consumed by the
`austal_prep` package.

The output sets sensible defaults:
    qs                          = 3   (quality level)
    z0                          = 0.1 (TA Luft roughness length of airports)
    d0                          = 6 z0 unless given (0.6 for z0 = 0.1)
    ha                          = 10 m + d0 unless given (10.6 for z0 = 0.1)
                                (the one default of the plugin's AUSTAL
                                module, the standalone and austal_prep:
                                surface_layer_atmosphere.site_parameters)
    grid                        read from alaqs grid_3d_definition
                                (fallback 75x75 of 250 m if absent)
    sk                          AUSTAL default vertical layers
    max_receptors               = 20  (AUSTAL hard cap)
    source_aggregation          = "by_type_per_pollutant"
    grid_writer_mode            = "hybrid"

These can be overridden on the command line. After scaffolding, edit
the JSON file directly to fine-tune for your study.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from pyproj import Transformer

from open_alaqs.core.tools import surface_layer_atmosphere as _sla
from open_alaqs.core.tools.utm import utm_epsg as _utm_epsg

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


def _grid_from_alaqs(alaqs_path: Path) -> dict | None:
    """Read the user-configured grid from grid_3d_definition.

    Mirrors the SQL the plugin runs in
    open_alaqs/gui/DispersionAnalysis.py: SELECT x_cells, y_cells,
    z_cells, x_resolution, y_resolution, z_resolution,
    reference_latitude, reference_longitude FROM grid_3d_definition.

    Returns a dict with keys x_cells, y_cells, z_cells, x_resolution,
    y_resolution, z_resolution (floats / ints), or None if the table
    is missing/empty. The reference lat/lon are read by
    _reference_lat_lon().
    """
    try:
        conn = sqlite3.connect(str(alaqs_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT x_cells, y_cells, z_cells, "
                "x_resolution, y_resolution, z_resolution "
                "FROM grid_3d_definition LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "x_cells": int(row[0]),
                "y_cells": int(row[1]),
                "z_cells": int(row[2]),
                "x_resolution": float(row[3]),
                "y_resolution": float(row[4]),
                "z_resolution": float(row[5]),
            }
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # Table does not exist (older alaqs files). Caller falls
        # back to its hardcoded defaults and prints a warning.
        return None


def _coord(value) -> float | None:
    """A latitude/longitude column value as float, None when missing."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return float(value)


def _grid_reference_from_alaqs(alaqs_path: Path) -> tuple[float, float] | None:
    """(reference_latitude, reference_longitude) of grid_3d_definition.

    None if the table is missing or empty or either value is missing.
    """
    try:
        conn = sqlite3.connect(str(alaqs_path))
        try:
            row = conn.execute(
                "SELECT reference_latitude, reference_longitude "
                "FROM grid_3d_definition LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    lat, lon = _coord(row[0]), _coord(row[1])
    if lat is None or lon is None:
        return None
    return lat, lon


def _reference_lat_lon(alaqs_path: Path, meta: dict) -> tuple[float, float]:
    """WGS84 point the AUSTAL calculation grid is centred on.

    The emission grid (geometry.grid_bounds_3857, the plugin's Grid3D)
    is centred on grid_3d_definition reference_latitude/longitude, and
    the hybrid writer reads alaqs cell indices relative to the config
    reference, so the config must use the same point. The airport
    reference point of user_study_setup is used only when the grid
    definition carries none.
    """
    ref = _grid_reference_from_alaqs(alaqs_path)
    if ref is not None:
        return ref
    lat = _coord(meta.get("airport_latitude"))
    lon = _coord(meta.get("airport_longitude"))
    if lat is None or lon is None:
        raise ValueError(
            f"{alaqs_path}: no reference point: grid_3d_definition has no "
            f"reference_latitude/reference_longitude and user_study_setup "
            f"has no airport_latitude/airport_longitude."
        )
    print(
        "  WARNING: grid_3d_definition has no reference point; using the "
        "airport reference point of user_study_setup "
        f"({lat:.7f}, {lon:.7f})."
    )
    return lat, lon


def make_config(
    alaqs_path: Path,
    out_path: Path,
    title: str | None = None,
    grid_size: int | None = None,
    grid_step_m: float | None = None,
    qs: int = 3,
    z0: float | None = None,
    d0: float | None = None,
    ha: float | None = None,
    pollutants: list | None = None,
    year: int | None = None,
    utm_epsg: int | None = None,
    time_window: tuple | list | None = None,
    grid_writer_mode: str = "hybrid",
    apply_nox_corrections: bool = False,
    atmosphere_model: str = "standard_lapse",
) -> dict:
    meta = _airport_metadata(alaqs_path)
    title = title or meta.get("airport_name") or meta.get("project_name") or "Untitled"

    lat, lon = _reference_lat_lon(alaqs_path, meta)
    if utm_epsg is None:
        utm_epsg = _utm_epsg(lat, lon)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    ref_x, ref_y = transformer.transform(lon, lat)

    # Grid is taken from the alaqs file's grid_3d_definition table,
    # matching the plugin which has no override mechanism. If the
    # caller passes grid_size or grid_step_m they are ignored with a
    # warning (kept in the signature so existing recipe call sites do
    # not break; remove them from the recipe to silence the warning).
    HARDCODED_FALLBACK_CELLS = 75
    HARDCODED_FALLBACK_RES = 250.0

    if grid_size is not None or grid_step_m is not None:
        print(
            f"  WARNING: grid_size={grid_size} / grid_step_m={grid_step_m} "
            f"argument(s) ignored. Grid is taken from alaqs "
            f"grid_3d_definition to match the plugin. Remove these "
            f"arguments from the recipe call to silence this warning."
        )

    alaqs_grid = _grid_from_alaqs(alaqs_path)
    if alaqs_grid is not None:
        nx = alaqs_grid["x_cells"]
        ny = alaqs_grid["y_cells"]
        dx = alaqs_grid["x_resolution"]
        dy = alaqs_grid["y_resolution"]
        if dx != dy:
            print(
                f"  WARNING: alaqs grid has non-square cells "
                f"({dx}x{dy}m). AUSTAL expects square cells; "
                f"using x_resolution for both axes."
            )
            dy = dx
        if nx != ny:
            print(
                f"  WARNING: alaqs grid has non-square shape "
                f"({nx}x{ny}). AUSTAL requires nx==ny; "
                f"using x_cells for both axes."
            )
            ny = nx
        print(f"  Grid: from alaqs grid_3d_definition: " f"{nx}x{ny} cells of {dx:g}m")
    else:
        nx = HARDCODED_FALLBACK_CELLS
        ny = HARDCODED_FALLBACK_CELLS
        dx = HARDCODED_FALLBACK_RES
        dy = HARDCODED_FALLBACK_RES
        print(
            f"  WARNING: grid_3d_definition not found in alaqs file; "
            f"falling back to hardcoded defaults "
            f"({nx}x{ny} of {dx:g}m). Configure the grid in QGIS."
        )

    grid_size = nx  # remaining code uses grid_size for both axes
    grid_step_m = dx

    # Calc-grid halo: AUSTAL requires the source bbox (declared at
    # xq = x0 + source_offset_cells * dd) to sit strictly INSIDE the
    # calc grid. Without a halo, the calc grid coincides with the
    # alaqs grid and the source dmna gets squeezed to
    # (grid_size - 2*source_offset_cells) cells. That cropping silently
    # drops alaqs cells at the calc-grid edges (climbout / approach
    # trajectory tails). Adding 2 halo cells on each side of the
    # alaqs grid makes the calc grid 2*halo_cells wider, so the source
    # dmna can be the FULL grid_size and cover every alaqs cell on the
    # HIGH end. Cells on the LOW end (alaqs ix or iy in {0,1}) are
    # still cropped because distribute.py emits cells in alaqs frame
    # [0, grid_size-1] while the writer treats them as calc-frame
    # indices and subtracts source_offset_cells; eliminating that
    # residual would require shifting distribute.py's indices by
    # halo_cells (a separate change).
    halo_cells = 2  # matches AustalStudyConfig.source_offset_cells default
    calc_size = grid_size + 2 * halo_cells
    half_extent = (calc_size * grid_step_m) / 2.0
    x0 = -half_extent
    y0 = -half_extent

    # Site parameters: the shared OpenALAQS defaults for those left empty
    # (z0 0.1 m, d0 6 z0, ha 10 m + d0).
    z0, d0, ha = _sla.site_parameters(z0, d0, ha)

    cfg = {
        "title": title,
        "qs": qs,
        "z0": z0,
        "d0": d0,
        "ha": ha,
        "os_options": "NOSTANDARD;NOTALUFT;SCINOTAT;Kmax=1",
        "mixing_height_included": True,
        "grid_writer_mode": grid_writer_mode,
        "source_offset_cells": halo_cells,
        "max_receptors": 20,
        "source_aggregation": "by_type_per_pollutant",
        # ICCAIA / CAEP14 v14 NOx ambient correction. False (default)
        # = bymode NOx EI used as-is (CAEP9-equivalent baseline);
        # True = correction applied at TO/CL segments. BFFM2 methods
        # ignore this flag; their EI calculation has built-in ambient
        # correction.
        "apply_nox_corrections": bool(apply_nox_corrections),
        "atmosphere_model": str(atmosphere_model),
        "grid": {
            "dd": float(grid_step_m),
            "nx": int(calc_size),
            "ny": int(calc_size),
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

    # Date window: time_window (narrow window) wins over year (full year).
    # Both are optional. time_window accepts:
    #   - tuple/list of two values: (start, end)
    #   - each value: ISO string, date/datetime object, or anything with
    #     isoformat(). Strings are passed through verbatim so the caller
    #     controls the exact format AUSTAL receives.
    if time_window is not None:
        if len(time_window) != 2:
            raise ValueError(
                f"time_window must have 2 elements (start, end); "
                f"got {len(time_window)}"
            )
        start_v, end_v = time_window

        def _to_iso(v):
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return str(v)

        cfg["start_dt"] = _to_iso(start_v)
        cfg["end_dt"] = _to_iso(end_v)
    elif year is not None:
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
        default=None,
        help="Number of cells per side. Default: read "
        "from alaqs grid_3d_definition table; "
        "fallback 75 if table missing.",
    )
    parser.add_argument(
        "--grid-step",
        type=float,
        default=None,
        help="Cell size in metres. Default: read from "
        "alaqs grid_3d_definition table; fallback "
        "250 if table missing.",
    )
    parser.add_argument("--qs", type=int, default=3)
    parser.add_argument(
        "--z0",
        type=float,
        default=None,
        help="AUSTAL roughness length (m), default 0.1 (TA Luft, airports)",
    )
    parser.add_argument(
        "--d0", type=float, default=None, help="displacement height (m), default 6 z0"
    )
    parser.add_argument(
        "--ha",
        type=float,
        default=None,
        help="anemometer height (m), default 10 m + d0",
    )
    parser.add_argument(
        "--pollutants", default=None, help="Comma-separated, e.g. nox,pm10,pm25"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Sets start_dt/end_dt to this calendar year "
        "(fallback if --time-window is not given).",
    )
    parser.add_argument(
        "--time-window",
        nargs=2,
        metavar=("START", "END"),
        default=None,
        help="Narrow simulation window as two ISO 8601 "
        "strings; overrides --year. Example: "
        "--time-window 2025-07-17T00:00:00 2025-07-23T00:00:00",
    )
    parser.add_argument(
        "--utm-epsg",
        type=int,
        default=None,
        help="Override the UTM zone derived from the grid reference point",
    )
    args = parser.parse_args(argv)

    pols = [p.strip() for p in args.pollutants.split(",")] if args.pollutants else None
    tw = tuple(args.time_window) if args.time_window else None
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
        time_window=tw,
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
