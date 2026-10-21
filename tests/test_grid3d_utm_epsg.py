"""Grid3D chooses its UTM zone with the helper shared with the standalone (open_alaqs.core.tools.utm)."""

import pytest

from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.utm import utm_epsg


@pytest.mark.parametrize(
    "lat, lon, expected",
    [
        (51.9574278, 4.4417028, 32631),
        (-33.9, 151.2, 32756),
        (51.5, 0.0, 32630),
        (50.0, 6.0, 32631),
        (-20.0, 6.0, 32731),
        (60.0, 5.0, 32631),
    ],
)
def test_grid3d_utm_epsg(lat, lon, expected):
    grid = Grid3D(
        grid_config={
            "x_cells": 10,
            "y_cells": 10,
            "z_cells": 1,
            "x_resolution": 100,
            "y_resolution": 100,
            "z_resolution": 50,
            "reference_latitude": lat,
            "reference_longitude": lon,
            "reference_altitude": 0.0,
        }
    )
    assert grid.getUtmEpsg() == expected == utm_epsg(lat, lon)
