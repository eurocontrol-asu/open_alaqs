"""The per-pollutant GeoPackage carries every source kind.

write_pollutant_gpkgs used to grid only aircraft cells, point, road and
parking sources; area sources (e.g. other airside fuel) and engine run-up
sources were left out, so the GeoPackage total fell short of
emissions.parquet (EHRD, 5 August 2025: 1.369 kg NOx of area sources).
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, Point

from openalaqs_standalone.geometry import grid_bounds_3857
from openalaqs_standalone.inventory_gpkg import write_pollutant_gpkgs

REF_LAT, REF_LON = 51.9574, 4.4417
GRID_DEF = dict(x_cells=10, y_cells=10, x_resolution=250.0, y_resolution=250.0)


def _bounds():
    return grid_bounds_3857(10, 10, 250.0, 250.0, REF_LAT, REF_LON)


def _xy(dx, dy):
    """EPSG:3857 point dx, dy metres (ground) from the grid reference."""
    t = Transformer.from_crs(4326, 3857, always_xy=True)
    x, y = t.transform(REF_LON, REF_LAT)
    import math

    s = 1 / math.cos(math.radians(REF_LAT))
    return x + dx * s, y + dy * s


def _square(cx, cy, half):
    pts = [_xy(cx - half, cy - half), _xy(cx + half, cy - half),
           _xy(cx + half, cy + half), _xy(cx - half, cy + half)]
    return Polygon(pts)


def test_gpkg_total_includes_area_engine_test_and_point(tmp_path):
    sources = pd.DataFrame(
        [
            ("road:r1", LineString([_xy(-600, 0), _xy(600, 0)]).wkt),
            ("parking:p1", _square(300, 300, 50).wkt),
            ("area:airside", _square(-300, -300, 200).wkt),
            ("engine_test:t1", _square(400, -400, 20).wkt),
            ("point:s1", Point(*_xy(-100, 400)).wkt),
        ],
        columns=["source_id", "geometry_wkt"],
    )
    masses = {"road:r1": 1.0, "parking:p1": 0.2, "area:airside": 0.3,
              "engine_test:t1": 0.05, "point:s1": 0.01, "aircraft:cell:4_4_0": 0.7}
    emissions = pd.DataFrame(
        [(pd.Timestamp("2025-08-05 05:00"), sid, "nox", kg) for sid, kg in masses.items()],
        columns=["timestamp", "source_id", "pollutant", "kg_in_hour"],
    )
    sources = pd.concat(
        [sources, pd.DataFrame([("aircraft:cell:4_4_0", "")], columns=sources.columns)],
        ignore_index=True,
    )
    paths = write_pollutant_gpkgs(emissions, sources, _bounds(), GRID_DEF, tmp_path, pollutants=["nox"])
    conn = sqlite3.connect(paths["nox"])
    table = conn.execute("select table_name from gpkg_contents").fetchone()[0]
    total = conn.execute(f'select sum(nox) from "{table}"').fetchone()[0]
    assert total == pytest.approx(sum(masses.values()), rel=1e-9)
