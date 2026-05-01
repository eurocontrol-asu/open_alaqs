"""
Regression test for CSV receptor schema where the altitude column is omitted.

The AUSTAL receptor pipeline accepts a CSV with `id, longitude, latitude`
and an optional `altitude` column. Earlier the loader required all three;
when altitude was absent the loader silently produced an empty
GeoDataFrame and AUSTAL ran with zero receptor points (only a single
WARNING line in the log).

Fix in `csv_interface.read_csv_to_geodataframe`: when `altitude` is
missing, build the geometry as 2D points using `longitude` and `latitude`
only. The default receptor breathing height (1.5 m) is applied
downstream by the AUSTAL output module.

This test locks both halves of the contract:
  1. A 3-column CSV (no altitude) yields a GeoDataFrame with one row per
     CSV record and a non-empty geometry column.
  2. A 4-column CSV (with altitude) yields the same row count with z
     coordinates preserved on the geometry.
"""

import os
import tempfile
from pathlib import Path


def _write_csv(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    Path(path).write_text(content, encoding="utf-8")
    return path


def test_receptor_csv_without_altitude_loads_all_rows():
    """3-column CSV (id, longitude, latitude) must produce a non-empty GDF."""
    from open_alaqs.core.tools.csv_interface import read_csv_to_geodataframe

    csv_text = (
        "id,longitude,latitude\n"
        "R1,4.4400,51.9600\n"
        "R2,4.4500,51.9700\n"
        "R3,4.4600,51.9800\n"
    )
    path = _write_csv(csv_text)
    try:
        gdf = read_csv_to_geodataframe(path)
        assert len(gdf) == 3, (
            f"Expected 3 receptor rows, got {len(gdf)}. The altitude column "
            f"is optional; the loader must not silently empty the result."
        )
        assert "geometry" in gdf.columns
        assert all(
            g is not None for g in gdf.geometry
        ), "All geometries must be non-null."
        # 2D points: has_z is False
        assert all(not g.has_z for g in gdf.geometry), (
            "When altitude is omitted the loader must produce 2D points; "
            "the breathing-height default (1.5 m) is applied downstream "
            "in AUSTALOutputModule.getGridXYFromReferencePoint."
        )
    finally:
        os.unlink(path)


def test_receptor_csv_with_altitude_preserves_z():
    """4-column CSV (id, longitude, latitude, altitude) must produce 3D points."""
    from open_alaqs.core.tools.csv_interface import read_csv_to_geodataframe

    csv_text = (
        "id,longitude,latitude,altitude\n"
        "R1,4.4400,51.9600,2.5\n"
        "R2,4.4500,51.9700,5.0\n"
        "R3,4.4600,51.9800,10.0\n"
    )
    path = _write_csv(csv_text)
    try:
        gdf = read_csv_to_geodataframe(path)
        assert len(gdf) == 3
        assert all(
            g.has_z for g in gdf.geometry
        ), "When altitude is present the loader must produce 3D points."
        zs = [g.z for g in gdf.geometry]
        assert zs == [2.5, 5.0, 10.0], f"Z values not preserved: {zs}"
    finally:
        os.unlink(path)


def test_receptor_csv_missing_lon_or_lat_logs_error_and_returns_empty():
    """If neither geometry nor longitude+latitude are present, the loader
    must return an empty GDF and log an error (not silently produce
    geometry-less rows)."""
    import logging

    from open_alaqs.core.tools.csv_interface import read_csv_to_geodataframe

    csv_text = "id,xcoord,ycoord\n" "R1,4.4400,51.9600\n"
    path = _write_csv(csv_text)
    try:
        # Capture logs from the csv_interface logger
        caplogs = []
        h = logging.Handler(level=logging.ERROR)
        h.emit = lambda r: caplogs.append(r.getMessage())
        target = logging.getLogger("open_alaqs.core.tools.csv_interface")
        target.addHandler(h)
        try:
            gdf = read_csv_to_geodataframe(path)
        finally:
            target.removeHandler(h)
        assert len(gdf) == 0, (
            f"Without longitude+latitude (or geometry) the loader must not "
            f"build any rows. Got {len(gdf)}."
        )
        assert any(
            "longitude" in m and "latitude" in m for m in caplogs
        ), f"Expected an error log mentioning the missing columns. Got: {caplogs}"
    finally:
        os.unlink(path)
