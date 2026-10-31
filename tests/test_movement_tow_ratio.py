"""tow_ratio of a movement: empty gives 1; zero, negative or NaN is no ratio and
gives 1 (as in the standalone), instead of a negative NOx correction factor."""

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.interfaces.Movement import Movement  # noqa: E402


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", 1.0),
        (None, 1.0),
        ("0.8", 0.8),
        (1.2, 1.2),
        (0, 1.0),
        ("0", 1.0),
        ("-0.5", 1.0),
        ("nan", 1.0),
    ],
)
def test_tow_ratio(raw, expected):
    movement = Movement(
        {
            "oid": 1,
            "tow_ratio": raw,
            "runway_time": "2025-12-01 06:15:00",
            "block_time": "2025-12-01 06:10:00",
        }
    )
    assert movement.getTakeoffWeightRatio() == pytest.approx(expected)
