"""Vertical layer split of segments at or below ground level.

ADS-B (CUSTOM) profiles carry heights relative to MSL (the importer uses
reference altitude 0). At an airport below sea level (EHRD, -15 ft) the
ground-roll points are negative. `_iz_layer_fractions` must put such
segments in the ground layer, not in the top layer.
"""

from __future__ import annotations

import pytest

from openalaqs_standalone.distribute import _iz_layer_fractions

# AUSTAL vertical grid used by austal_prep (19 layers to 1500 m)
SK = [
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


@pytest.mark.parametrize(
    "z1, z2",
    [
        (-0.9, -4.6),  # both ends below ground (EHRD ground roll)
        (-4.6, -0.9),  # same, other order
        (-4.572, 0.0),  # one end exactly at ground level
        (0.0, -4.572),
        (-3.0, -3.0),  # point below ground
    ],
)
def test_below_ground_goes_to_ground_layer(z1, z2):
    assert _iz_layer_fractions(z1, z2, SK) == {0: 1.0}


def test_partly_below_ground_unchanged():
    # Only the part above 0 m is apportioned, as before the fix.
    f = _iz_layer_fractions(-2.0, 5.0, SK)
    assert f.keys() == {0, 1}
    assert f[0] == pytest.approx(0.6)
    assert f[1] == pytest.approx(0.4)


@pytest.mark.parametrize(
    "z1, z2, expected",
    [
        (0.0, 0.0, {0: 1.0}),
        (2.0, 7.0, {0: 0.2, 1: 0.6, 2: 0.2}),
        (1100.0, 1600.0, {17: 0.25, 18: 0.75}),
        (1600.0, 1700.0, {18: 1.0}),  # above the grid: top-layer fallback kept
    ],
)
def test_above_ground_unchanged(z1, z2, expected):
    f = _iz_layer_fractions(z1, z2, SK)
    assert f.keys() == expected.keys()
    for k, v in expected.items():
        assert f[k] == pytest.approx(v)


@pytest.mark.parametrize("z1, z2", [(-0.9, -4.6), (-2.0, 5.0), (3.0, 450.0)])
def test_fractions_sum_to_one(z1, z2):
    assert sum(_iz_layer_fractions(z1, z2, SK).values()) == pytest.approx(1.0)
