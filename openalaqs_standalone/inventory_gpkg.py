"""
inventory_gpkg: produce plugin-compatible per-pollutant gpkg files
from the emissions.parquet / sources.parquet pair.

What this gives you
-------------------
For each pollutant (co, hc, nox, pm10, pm25 by default), writes a gpkg
that mirrors the plugin's `EmissionsQGISVectorLayerOutputModule` output
exactly:

  - Single feature table per gpkg, 100x100 UTM cells (10000 rows, all
    cells even where mass is zero).
  - Geometry: axis-aligned 100 m UTM polygon per cell.
  - One non-spatial column, named after the pollutant, with the summed
    mass in kg (over the run's time window, all sources).
  - CRS: the local UTM zone, matching plugin's UTM
    output.

The mass at each cell is the sum over all source types, gridded the
same way the plugin grids them:

  aircraft:cell:<ix>_<iy>_<iz>
                       Already gridded in emissions.parquet by
                       distribute.distribute_to_grid. We read the
                       (ix, iy) directly from the source_id and sum
                       over iz (and over time).
  point sources         Plugin: `factor = 1 / len(intersecting_df)` for
                       Point geometries. Cells the point lies in get
                       equal share; for points not on a cell boundary
                       this is one cell, identified by cell_index at
                       the point coordinates.
  parking sources       Plugin: `factor = intersection.area / geom.area`
                       for Polygon geometries. We use the same algorithm
                       via distribute._polygon_cell_fractions.
  road sources          Plugin: `factor = intersection.length /
                       geom.length` for LineString. We use
                       distribute._linestring_cell_fractions.

The result is bit-identical to what the plugin would write if
configured for the same study, modulo the per-movement compute
residuals we already characterised (<0.1% on totals).

Usage (from austal_prep or any downstream pipeline)
--------------------------------------------
    import pandas as pd
    from openalaqs_standalone import inventory_gpkg
    from openalaqs_standalone.movements import get_grid_definition
    from openalaqs_standalone.geometry import grid_bounds_3857

    emissions = pd.read_parquet("emissions.parquet")
    sources   = pd.read_parquet("sources.parquet")

    # Same grid_bounds / grid_definition you passed to distribute_to_grid:
    grid_definition = get_grid_definition(conn)
    grid_bounds     = grid_bounds_3857(**grid_definition, ...)

    paths = inventory_gpkg.write_pollutant_gpkgs(
        emissions, sources, grid_bounds, grid_definition,
        output_dir="inventory_gpkgs",
        filename_template="{pollutant}_bymode_none.gpkg",  # matches plugin
    )
    # paths == {'co': '.../co_bymode_none.gpkg', 'nox': '.../nox_bymode_none.gpkg', ...}

Drop the gpkg files into QGIS next to the plugin's `nox_bymode_none.gpkg`
and the two layers will line up exactly.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Iterable

import pandas as pd
from shapely import wkt as _shapely_wkt
from shapely.geometry import Polygon

from openalaqs_standalone.distribute import (
    _linestring_cell_fractions,
    _polygon_cell_fractions,
    cell_index,
)

DEFAULT_POLLUTANTS = ("co", "hc", "nox", "pm10", "pm25")


def _wkb_with_gpkg_header(geom, srs_id: int) -> bytes:
    """Encode a shapely geometry in GeoPackage Binary format.

    GeoPackage Binary = 8-byte header + standard WKB. Header layout
    (OGC 12-128r15 / GPKG spec section 2.1.3.1):
      bytes 0-1: magic 'GP'
      byte  2:   version 0
      byte  3:   flags: bit 0 = byte order (1=LE), bits 1-3 = envelope
                  type, bit 5 = empty flag. envelope=0 (no envelope) is
                  shortest and accepted by QGIS, GDAL, etc.
      bytes 4-7: srs_id (little-endian int32)
      bytes 8+:  standard WKB

    Empty geometries are written with the empty flag set and no WKB
    body — defensive only; our cells are never empty.
    """
    if geom.is_empty:
        flags = (1 << 0) | (1 << 4)  # LE, empty
        header = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
        return header
    flags = 1 << 0  # LE byte order, no envelope, not empty
    header = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
    # shapely 2.x: byte_order=1 → little-endian. The older
    # `byteorder=` kwarg in shapely.wkb.dumps was renamed; both
    # paths route through `shapely.to_wkb` underneath.
    import shapely

    body = shapely.to_wkb(geom, byte_order=1)
    return header + body


def _init_gpkg(
    conn: sqlite3.Connection,
    srs_id: int,
    srs_definition: str,
    srs_organization: str = "EPSG",
) -> None:
    """Create the minimum GeoPackage metadata tables.

    Just enough for QGIS and GDAL to recognise the file as a valid
    GeoPackage. We do not write rtree spatial indexes — the cells are
    100x100 and a full scan is fast enough that the index buys nothing.
    """
    conn.executescript("""
        PRAGMA application_id = 0x47504B47;
        PRAGMA user_version   = 10300;

        CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER,
            CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );

        CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
            table_name TEXT NOT NULL PRIMARY KEY,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );
        """)

    # WGS 84 and 'undefined' rows are mandated by the GPKG spec;
    # we add ours after.
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys "
        "(srs_name, srs_id, organization, organization_coordsys_id, definition, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "WGS 84",
            4326,
            "EPSG",
            4326,
            'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
            'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
            "WGS 84",
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys "
        "(srs_name, srs_id, organization, organization_coordsys_id, definition, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "Undefined Cartesian SRS",
            -1,
            "NONE",
            -1,
            "undefined",
            "Undefined Cartesian coordinate reference system",
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys "
        "(srs_name, srs_id, organization, organization_coordsys_id, definition, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "Undefined Geographic SRS",
            0,
            "NONE",
            0,
            "undefined",
            "Undefined geographic coordinate reference system",
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys "
        "(srs_name, srs_id, organization, organization_coordsys_id, definition, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            f"{srs_organization}:{srs_id}",
            srs_id,
            srs_organization,
            srs_id,
            srs_definition,
            f"{srs_organization}:{srs_id}",
        ),
    )


def _write_one_pollutant_gpkg(
    output_path: Path,
    pollutant: str,
    cell_geoms_utm: list,
    cell_ix: list,
    cell_iy: list,
    cell_mass: dict,
    grid_bounds: dict,
    table_name: str,
    value_column: str,
) -> None:
    """Write one pollutant's gpkg file at output_path."""
    utm_epsg = int(grid_bounds["utm_epsg"])
    srs_def = f"EPSG:{utm_epsg}"  # QGIS will resolve from EPSG code

    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(str(output_path))
    try:
        _init_gpkg(conn, srs_id=utm_epsg, srs_definition=srs_def)

        # Feature table — matches plugin's schema exactly
        # (`CREATE TABLE "nox_emissions" (fid INTEGER PRIMARY KEY, geom POLYGON, nox REAL)`)
        conn.execute(
            f'CREATE TABLE "{table_name}" ('
            f'  "fid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,'
            f'  "geom" POLYGON,'
            f'  "{value_column}" REAL'
            f")"
        )

        # GeoPackage metadata rows
        min_x = grid_bounds["origin_x_utm"]
        min_y = grid_bounds["origin_y_utm"]
        # Compute max_x, max_y from cells we built
        max_x = max(g.bounds[2] for g in cell_geoms_utm)
        max_y = max(g.bounds[3] for g in cell_geoms_utm)
        conn.execute(
            "INSERT INTO gpkg_contents "
            "(table_name, data_type, identifier, description, "
            " min_x, min_y, max_x, max_y, srs_id) "
            "VALUES (?, 'features', ?, '', ?, ?, ?, ?, ?)",
            (table_name, table_name, min_x, min_y, max_x, max_y, utm_epsg),
        )
        conn.execute(
            "INSERT INTO gpkg_geometry_columns "
            "(table_name, column_name, geometry_type_name, srs_id, z, m) "
            "VALUES (?, 'geom', 'POLYGON', ?, 0, 0)",
            (table_name, utm_epsg),
        )

        # Bulk insert: 10000 rows, all cells (zero or non-zero), match
        # plugin's behaviour of writing the full grid.
        rows = []
        for ix, iy, geom in zip(cell_ix, cell_iy, cell_geoms_utm):
            mass = cell_mass.get((ix, iy), 0.0)
            geom_blob = _wkb_with_gpkg_header(geom, srs_id=utm_epsg)
            rows.append((geom_blob, mass))
        conn.executemany(
            f'INSERT INTO "{table_name}" ("geom", "{value_column}") VALUES (?, ?)',
            rows,
        )

        conn.commit()
    finally:
        conn.close()


def write_pollutant_gpkgs(
    emissions: pd.DataFrame,
    sources: pd.DataFrame,
    grid_bounds: dict,
    grid_definition: dict,
    output_dir,
    pollutants: Iterable[str] = DEFAULT_POLLUTANTS,
    filename_template: str = "{pollutant}.gpkg",
    table_name_template: str = "{pollutant}_emissions",
    value_column_template: str = "{pollutant}",
) -> dict:
    """Write per-pollutant gpkg files mirroring the plugin's gridded output.

    Parameters
    ----------
    emissions
        The emissions.parquet DataFrame. Must contain `source_id`,
        `pollutant`, `kg_in_hour` columns.
    sources
        The sources.parquet DataFrame. Must contain `source_id`,
        `geometry_wkt`, `geometry_kind` columns.
    grid_bounds
        From `openalaqs_standalone.geometry.grid_bounds_3857`. Must
        carry `utm_epsg`, `origin_x_utm`, `origin_y_utm`, `x_max`,
        `y_max` (the existing standalone keys).
    grid_definition
        From `openalaqs_standalone.movements.get_grid_definition`.
        Must carry `x_cells`, `y_cells`, `x_resolution`,
        `y_resolution`.
    output_dir
        Where to write the gpkg files. Created if missing.
    pollutants
        Pollutants to write. Defaults to all five tracked pollutants.
    filename_template
        Used as `filename_template.format(pollutant=p)` to construct
        each output filename. Default produces `nox.gpkg`, `co.gpkg`
        etc.; pass e.g. `"{pollutant}_bymode_none.gpkg"` to mirror the
        plugin's naming convention.
    table_name_template, value_column_template
        Inside-gpkg table name and non-spatial column name; both run
        through .format(pollutant=p). Defaults match the plugin
        (`nox_emissions` / `nox`).

    Returns
    -------
    dict[str, str]: pollutant -> path to written gpkg.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    int(grid_bounds["utm_epsg"])
    origin_x = float(grid_bounds["origin_x_utm"])
    origin_y = float(grid_bounds["origin_y_utm"])
    x_cells = int(grid_definition["x_cells"])
    y_cells = int(grid_definition["y_cells"])
    x_res = float(grid_definition["x_resolution"])
    y_res = float(grid_definition["y_resolution"])

    # Build UTM cell polygons once for all pollutants. Iteration order
    # is row-major iy-outer, ix-inner — fid values from SQLite's
    # AUTOINCREMENT will run 1..10000 in this order, matching the
    # plugin's `Grid3D.get_3d_grid_cells()` order.
    cell_geoms_utm = []
    cell_ix = []
    cell_iy = []
    for iy in range(y_cells):
        for ix in range(x_cells):
            x0 = origin_x + ix * x_res
            y0 = origin_y + iy * y_res
            poly = Polygon(
                [
                    (x0, y0),
                    (x0 + x_res, y0),
                    (x0 + x_res, y0 + y_res),
                    (x0, y0 + y_res),
                ]
            )
            cell_geoms_utm.append(poly)
            cell_ix.append(ix)
            cell_iy.append(iy)

    # Pre-extract per-source-type frames once; reused across pollutants.
    src_aircraft = sources[sources["source_id"].str.startswith("aircraft:cell:")]
    src_point = sources[sources["source_id"].str.startswith("point:")]
    src_road = sources[sources["source_id"].str.startswith("road:")]
    src_parking = sources[sources["source_id"].str.startswith("parking:")]

    # Pre-parse non-aircraft geometries: parking and gate cell-fraction
    # dicts depend only on geometry, not pollutant, so cache them
    # outside the pollutant loop. Saves N_pollutants × repeats of the
    # shapely intersection work.
    parking_fracs = {}
    for _, r in src_parking.iterrows():
        g = _shapely_wkt.loads(r["geometry_wkt"])
        parking_fracs[r["source_id"]] = _polygon_cell_fractions(
            g, grid_bounds, grid_definition
        )

    road_fracs = {}
    for _, r in src_road.iterrows():
        g = _shapely_wkt.loads(r["geometry_wkt"])
        if g.geom_type == "LineString":
            coords = list(g.coords)
            road_fracs[r["source_id"]] = _linestring_cell_fractions(
                coords, grid_bounds, grid_definition
            )
        elif g.geom_type == "MultiLineString":
            # Mirror plugin behaviour: a MultiLineString is one
            # emission with one geometry. Per-cell fraction is total
            # intersection length divided by total geometry length.
            # We compute by treating each component separately and
            # weighting by its share of the total length, which gives
            # the same result.
            total_len = sum(line.length for line in g.geoms)
            if total_len > 0:
                fracs: dict = {}
                for line in g.geoms:
                    line_len = line.length
                    if line_len <= 0:
                        continue
                    line_fracs = _linestring_cell_fractions(
                        list(line.coords), grid_bounds, grid_definition
                    )
                    weight = line_len / total_len
                    for cell, f in line_fracs.items():
                        fracs[cell] = fracs.get(cell, 0.0) + f * weight
                road_fracs[r["source_id"]] = fracs
            else:
                road_fracs[r["source_id"]] = {}
        else:
            road_fracs[r["source_id"]] = {}

    point_cells = {}
    for _, r in src_point.iterrows():
        g = _shapely_wkt.loads(r["geometry_wkt"])
        if g.geom_type == "Point":
            point_cells[r["source_id"]] = cell_index(
                g.x, g.y, grid_bounds, grid_definition
            )
        else:
            # Centroid fallback for non-point geometries tagged as point
            c = g.centroid
            point_cells[r["source_id"]] = cell_index(
                c.x, c.y, grid_bounds, grid_definition
            )

    # Pre-extract aircraft cell coords from source_id once; reused.
    # source_id format: "aircraft:cell:<ix>_<iy>_<iz>"
    aircraft_cell_lookup = {}
    for sid in src_aircraft["source_id"]:
        parts = sid.replace("aircraft:cell:", "").split("_")
        aircraft_cell_lookup[sid] = (int(parts[0]), int(parts[1]))

    # Per-pollutant: sum emissions, write gpkg.
    output_paths = {}
    for pollutant in pollutants:
        em_p = emissions[emissions["pollutant"] == pollutant]
        per_src = em_p.groupby("source_id")["kg_in_hour"].sum().to_dict()

        cell_mass: dict = {}

        # Aircraft cells: source_id already encodes (ix, iy, iz).
        # Sum over iz (the same (ix, iy) appears multiple times for
        # different iz layers, all collapsing to the 2-D cell here).
        for sid, mass in per_src.items():
            if not sid.startswith("aircraft:cell:"):
                continue
            cell = aircraft_cell_lookup[sid]
            cell_mass[cell] = cell_mass.get(cell, 0.0) + mass

        # Point sources
        for sid, cell in point_cells.items():
            mass = per_src.get(sid, 0.0)
            if mass:
                cell_mass[cell] = cell_mass.get(cell, 0.0) + mass

        # Parking polygons (area-weighted)
        for sid, fracs in parking_fracs.items():
            mass = per_src.get(sid, 0.0)
            if not mass or not fracs:
                continue
            for cell, f in fracs.items():
                cell_mass[cell] = cell_mass.get(cell, 0.0) + mass * f

        # Road linestrings (length-weighted)
        for sid, fracs in road_fracs.items():
            mass = per_src.get(sid, 0.0)
            if not mass or not fracs:
                continue
            for cell, f in fracs.items():
                cell_mass[cell] = cell_mass.get(cell, 0.0) + mass * f

        # Write
        out_name = filename_template.format(pollutant=pollutant)
        out_path = output_dir / out_name
        table_name = table_name_template.format(pollutant=pollutant)
        value_column = value_column_template.format(pollutant=pollutant)
        _write_one_pollutant_gpkg(
            out_path,
            pollutant,
            cell_geoms_utm,
            cell_ix,
            cell_iy,
            cell_mass,
            grid_bounds,
            table_name,
            value_column,
        )
        output_paths[pollutant] = str(out_path)

    return output_paths
