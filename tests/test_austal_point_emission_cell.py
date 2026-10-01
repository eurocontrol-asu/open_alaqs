"""Regression: point emissions reach the AUSTAL emission grid.

``AUSTALDispersionModule.getEfficiencyXY`` gave a point the area ratio of
``spatial.getRelativeAreaInBoundingBox``, which returns 0 for any geometry
without area. Non-stationary point emissions (the helicopter ground idle at its
take-off spot) were therefore matched to no cell and dropped from the AUSTAL
input. A point now belongs entirely to the one cell that contains it.
"""

from collections import OrderedDict
from pathlib import Path

import pytest
from pyproj import Transformer
from qgis.testing import start_app

start_app()

from open_alaqs.core.interfaces.Emissions import Emission  # noqa: E402
from open_alaqs.core.modules.AUSTALOutputModule import (  # noqa: E402
    AUSTALDispersionModule,
)

CELL = {"x_min": 0.0, "x_max": 100.0, "y_min": 0.0, "y_max": 100.0}


def _module():
    return object.__new__(AUSTALDispersionModule)


@pytest.mark.parametrize(
    "wkt, expected",
    [
        ("POINT Z (50 50 0)", 1.0),
        ("POINT (50 50)", 1.0),
        ("POINT Z (150 50 0)", 0.0),
        ("POINT Z (0 0 0)", 1.0),  # lower-left corner belongs to this cell
        ("POINT Z (100 50 0)", 0.0),  # right edge belongs to the next cell
    ],
)
def test_point_efficiency_is_one_in_its_cell(wkt, expected):
    eff = _module().getEfficiencyXY(wkt, dict(CELL), True, False, False, False)
    assert eff == expected


def test_polygon_and_line_efficiency_unchanged():
    m = _module()
    poly = "POLYGON ((0 0, 200 0, 200 100, 0 100, 0 0))"
    line = "LINESTRING (0 50, 200 50)"
    assert m.getEfficiencyXY(poly, dict(CELL), False, False, True, False) == (
        pytest.approx(0.5)
    )
    assert m.getEfficiencyXY(line, dict(CELL), False, True, False, False) == (
        pytest.approx(0.5)
    )


def test_point_is_matched_to_exactly_one_grid_cell():
    """End to end through getMatchedCellCoeffs on a real Grid3D: the
    coefficients of a ground-level point sum to 1 (they summed to 0)."""
    from open_alaqs.core.tools.Grid3D import Grid3D

    db = (
        Path(__file__).resolve().parents[1]
        / "openalaqs_standalone"
        / "validation"
        / "data"
        / "training_v3.alaqs"
    )
    if not db.exists():
        pytest.skip(f"training inventory not found at {db}")
    grid = Grid3D(
        str(db),
        {
            "x_cells": 50,
            "y_cells": 50,
            "z_cells": 1,
            "x_resolution": 100,
            "y_resolution": 100,
            "z_resolution": 100,
            "reference_latitude": 51.96,
            "reference_longitude": 4.44,
            "reference_altitude": 0.0,
        },
        deserialize=False,
    )
    m = _module()
    m._source_geometries = OrderedDict()
    m._z_meshes = 19
    m._wkt_transformer = Transformer.from_crs(
        "EPSG:3857", f"EPSG:{grid.getUtmEpsg()}", always_xy=True
    )
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(
        4.44, 51.96
    )
    wkt = f"POINT Z ({x} {y} 0)"
    em = Emission()
    em.setGeometryText(wkt)
    em.setVerticalExtent({"z_min": 0.0, "z_max": 0.0})
    coeffs = m.getMatchedCellCoeffs(wkt, em, grid, True, False, False, False)
    assert len(coeffs) == 1
    assert sum(coeffs.values()) == pytest.approx(1.0)
