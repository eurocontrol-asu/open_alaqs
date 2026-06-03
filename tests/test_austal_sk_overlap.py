"""Unit tests for _austal_sk_overlap_layers - the AUSTAL z-binning fix.

These tests do not require QGIS. They exercise only the pure-Python
helper that replaced the plugin's uniform 50 m vertical binning.

Run from the openalaqs repo root:
    pytest tests/test_austal_sk_overlap.py -v
"""

from open_alaqs.core.modules.AUSTALOutputModule import (
    AUSTAL_DEFAULT_SK,
    _austal_sk_overlap_layers,
)


def test_ground_level_taxi_point():
    """Taxi at z=0 lands in layer 0 (sk[0]=0 <= 0 < sk[1]=3)."""
    assert _austal_sk_overlap_layers(0, 0) == [(0, 1.0)]


def test_point_at_layer_boundary():
    """z=3 belongs to layer 1 (sk[1]=3 <= 3 < sk[2]=6)."""
    assert _austal_sk_overlap_layers(3, 3) == [(1, 1.0)]


def test_point_at_top_boundary():
    """z = sk[-1] = 1500 ends up in the top layer (18)."""
    layers = _austal_sk_overlap_layers(1500, 1500)
    assert layers == [(len(AUSTAL_DEFAULT_SK) - 2, 1.0)]


def test_climbout_segment_splits_across_four_layers():
    """A 20-80 m segment overlaps sk layers 4 (16-25), 5 (25-40),
    6 (40-65), 7 (65-100). Fractions sum to 1.0."""
    got = dict(_austal_sk_overlap_layers(20, 80))
    extent = 80 - 20
    assert got == {
        4: 5 / extent,
        5: 15 / extent,
        6: 25 / extent,
        7: 15 / extent,
    }
    assert abs(sum(got.values()) - 1.0) < 1e-12


def test_high_altitude_segment():
    """A 600-1000 m segment spans layers 14 (600-700), 15 (700-800),
    16 (800-1000)."""
    got = dict(_austal_sk_overlap_layers(600, 1000))
    extent = 1000 - 600
    assert got == {
        14: 100 / extent,
        15: 100 / extent,
        16: 200 / extent,
    }
    assert abs(sum(got.values()) - 1.0) < 1e-12


def test_above_ceiling_is_clipped_not_redistributed():
    """1400-2000 m segment: only the 1400-1500 portion lands in
    layer 18. The 1500-2000 portion is clipped (gone), matching
    AUSTAL's own out-of-grid behaviour. Fractions sum to < 1."""
    got = _austal_sk_overlap_layers(1400, 2000)
    assert len(got) == 1
    assert got[0][0] == 18
    extent = 2000 - 1400
    assert got[0][1] == 100 / extent
    assert sum(f for _, f in got) < 1.0


def test_segment_below_ground_is_clipped():
    """Negative z_min is clipped at 0. -10 to 5 m gives only the
    0-3 m and 3-5 m overlaps."""
    got = dict(_austal_sk_overlap_layers(-10, 5))
    extent = 5 - (-10)  # 15
    assert got == {
        0: 3 / extent,  # 0-3 m
        1: 2 / extent,  # 3-5 m
    }
    assert sum(got.values()) < 1.0


def test_reversed_inputs_normalized():
    """If z_max < z_min the function swaps them."""
    a = _austal_sk_overlap_layers(80, 20)
    b = _austal_sk_overlap_layers(20, 80)
    assert a == b


def test_zero_extent_at_known_layers():
    """Point releases at each interior sk[k] land in layer k."""
    for k in range(1, len(AUSTAL_DEFAULT_SK) - 1):
        z = AUSTAL_DEFAULT_SK[k]
        assert _austal_sk_overlap_layers(z, z) == [
            (k, 1.0)
        ], f"point at sk[{k}]={z} should land in layer {k}"


def test_full_height_segment_sums_to_one():
    """A segment 0-1500 m (the full AUSTAL ceiling) has all 19
    layers populated and fractions sum to exactly 1."""
    got = _austal_sk_overlap_layers(0, 1500)
    assert len(got) == len(AUSTAL_DEFAULT_SK) - 1
    assert abs(sum(f for _, f in got) - 1.0) < 1e-12
    # Each layer's fraction equals its thickness / total extent
    for k, frac in got:
        expected = (AUSTAL_DEFAULT_SK[k + 1] - AUSTAL_DEFAULT_SK[k]) / 1500
        assert abs(frac - expected) < 1e-12
