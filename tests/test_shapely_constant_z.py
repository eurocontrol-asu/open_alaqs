"""Setting a constant Z with shapely.ops.transform works on shapely 2.1 and 2.2.

shapely 2.2 calls the coordinate function with whole arrays only. The former
lambdas returned the scalar height for Z, which shapely 2.1 tolerated (it fell
back to one point at a time) and 2.2 rejects with "'float' object is not
iterable". In CI (shapely 2.2.0) every runway, and so every calculation,
failed in RunwayStore.
"""

import pytest
import shapely.wkt
from qgis.testing import start_app

start_app()

from open_alaqs.core.interfaces.Runway import Runway  # noqa: E402
from open_alaqs.core.tools import spatial  # noqa: E402


def _z(geom):
    return [c[2] for c in shapely.get_coordinates(geom, include_z=True)]


@pytest.mark.parametrize(
    "wkt",
    [
        "LINESTRING (0 0, 100 0, 200 50)",
        "LINESTRING Z (0 0 5, 100 0 7)",
        "POINT (1 2)",
        "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
    ],
)
def test_add_height_to_geometry_wkt(wkt):
    out = shapely.wkt.loads(spatial.addHeightToGeometryWkt(wkt, -4.572))
    assert out.has_z
    assert _z(out) == pytest.approx([-4.572] * len(_z(out)))
    assert out.geom_type == shapely.wkt.loads(wkt).geom_type


def test_runway_geometry_gets_its_height():
    """Runway sets its height to 0 m and adds it as Z to the geometry."""
    runway = Runway(
        {
            "runway_id": "06/24",
            "capacity": 30,
            "offset": "0/0",
            "instudy": 1,
            "geometry": "LINESTRING (495941 6793406, 492953 6791467)",
        }
    )
    assert runway.getGeometry().has_z
    assert _z(runway.getGeometry()) == pytest.approx([0.0, 0.0])
