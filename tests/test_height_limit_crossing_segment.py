"""FlightEmissionCalculator.apply_height_limits: segments crossing the ceiling.

A segment with one endpoint below and one above the vertical limit (mixing
height) must contribute only its part below the limit. The endpoint above the
limit is moved along the segment to where the segment meets the limit (altitude
assumed linear along the segment). Distance, time, emissions and the emission
geometry downstream are all computed from the returned points, so moving the
point is what removes the part above the limit.

Previously only the altitude of that endpoint was capped and its x/y kept, so
the full horizontal length of the segment was counted.
"""

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.interfaces.AircraftTrajectory import (  # noqa: E402
    AircraftTrajectoryPoint,
)
from open_alaqs.core.MovementEmissionCalculator import (  # noqa: E402
    FlightEmissionCalculator,
)

LIMIT = {"max_height": 1000.0, "height_unit_in_feet": False}


def _pt(x, y, z, tas=80.0, mode="CL"):
    return AircraftTrajectoryPoint(
        {"x": x, "y": y, "z": z, "tas_metres": tas, "mode": mode, "power": 0.8}
    )


def _xyz(p):
    return tuple(round(v, 9) for v in p.getCoordinates())


def test_climbing_segment_end_moved_to_crossing():
    start, end = _pt(100.0, 200.0, 500.0), _pt(1100.0, 2200.0, 1500.0)
    s, e = FlightEmissionCalculator.apply_height_limits(start, end, LIMIT)
    assert _xyz(s) == (100.0, 200.0, 500.0)
    # crossing at half the climb: halfway along the segment
    assert _xyz(e) == (600.0, 1200.0, 1000.0)
    assert e.getGeometryText() == "POINTZ(600.000000 1200.000000 1000.000000)"
    # attributes of the moved point are those of the original end point
    assert e.getTrueAirspeed() == end.getTrueAirspeed()
    assert e.getMode() == end.getMode()
    # inputs are not modified
    assert _xyz(end) == (1100.0, 2200.0, 1500.0)


def test_descending_segment_start_moved_to_crossing():
    start, end = _pt(0.0, 0.0, 1800.0, mode="AP"), _pt(4000.0, 0.0, 200.0, mode="AP")
    s, e = FlightEmissionCalculator.apply_height_limits(start, end, LIMIT)
    # 800 m of the 1600 m descent lie above the limit: crossing at x = 2000
    assert _xyz(s) == (2000.0, 0.0, 1000.0)
    assert _xyz(e) == (4000.0, 0.0, 200.0)
    assert _xyz(start) == (0.0, 0.0, 1800.0)


@pytest.mark.parametrize(
    "z1,z2,expected",
    [
        (900.0, 1200.0, 1.0 / 3.0),
        (999.0, 1001.0, 0.5),
        (10.0, 1010.0, 0.99),
    ],
)
def test_fraction_kept_equals_fraction_below_limit(z1, z2, expected):
    start, end = _pt(0.0, 0.0, z1), _pt(300.0, 400.0, z2)  # 500 m long
    s, e = FlightEmissionCalculator.apply_height_limits(start, end, LIMIT)
    kept = ((e.getX() - s.getX()) ** 2 + (e.getY() - s.getY()) ** 2) ** 0.5
    assert kept / 500.0 == pytest.approx(expected, rel=1e-12)


def test_segments_not_crossing_are_unchanged():
    below = (_pt(0.0, 0.0, 100.0), _pt(500.0, 0.0, 900.0))
    s, e = FlightEmissionCalculator.apply_height_limits(*below, LIMIT)
    assert (_xyz(s), _xyz(e)) == ((0.0, 0.0, 100.0), (500.0, 0.0, 900.0))

    touching = (_pt(0.0, 0.0, 500.0), _pt(500.0, 0.0, 1000.0))
    s, e = FlightEmissionCalculator.apply_height_limits(*touching, LIMIT)
    assert (_xyz(s), _xyz(e)) == ((0.0, 0.0, 500.0), (500.0, 0.0, 1000.0))

    above = (_pt(0.0, 0.0, 1000.0), _pt(500.0, 0.0, 1500.0))
    assert FlightEmissionCalculator.apply_height_limits(*above, LIMIT) == (None, None)
