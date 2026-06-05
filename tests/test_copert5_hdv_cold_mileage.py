"""
Regression tests for the HDV/Bus diesel cold-mileage fraction formula.

Pins the corrected formula
    beta = min(8.25 / ltrip, 1)
against EMEP/EEA Guidebook 2023 Update 2025, chapter 1.A.3.b.i-iv,
section 3.4, page 77:

    "The beta parameter is calculated as a function of the ltrip with the
     assumption that the operating distance in cold conditions of a
     heavy-duty vehicle is 8.25 km using the following equation.
        beta = 8.25 / ltrip
        if beta > 1 then beta = 1"

Prior to the fix, copert5_utils.py used max(8.25/L, 1) which produced beta >= 1
for all trip lengths, i.e. floored cold mileage at 100%.

These tests would FAIL against the pre-fix code:
- at L=12.4 (default trip length), pre-fix beta == 1.0; post-fix beta == 8.25/12.4
- at L=50.0, pre-fix beta == 1.0; post-fix beta == 0.165
"""

import math

from open_alaqs.core.tools.copert5_utils import cold_mileage_fractions


def _hdt_diesel_betas(fractions):
    """Return the list of beta values for all HDT diesel and bus diesel rows.

    cold_mileage_fractions returns a DataFrame with a MultiIndex on
    (vehicle_category, fuel, euro_standard).
    """
    idx = fractions.index
    fuel_mask = idx.get_level_values("fuel") == "diesel"
    cat_mask = idx.get_level_values("vehicle_category").isin(["hdt", "bus"])
    return fractions.loc[fuel_mask & cat_mask, "beta"].tolist()


def test_hdt_diesel_short_trip_capped_at_one():
    """L < 8.25 km: 8.25/L > 1, so beta must be clamped to 1.0."""
    fractions = cold_mileage_fractions(trip_length=4.0)
    betas = _hdt_diesel_betas(fractions)
    assert betas, "no HDT/Bus diesel rows found"
    assert all(b == 1.0 for b in betas), betas


def test_hdt_diesel_boundary_trip_equals_one():
    """L == 8.25 km: 8.25/L == 1.0 exactly."""
    fractions = cold_mileage_fractions(trip_length=8.25)
    betas = _hdt_diesel_betas(fractions)
    assert betas
    assert all(b == 1.0 for b in betas), betas


def test_hdt_diesel_default_trip_below_one():
    """L = 12.4 km (function default): beta = 8.25/12.4 ~= 0.66532."""
    fractions = cold_mileage_fractions(trip_length=12.4)
    betas = _hdt_diesel_betas(fractions)
    assert betas
    expected = 8.25 / 12.4
    assert all(math.isclose(b, expected, rel_tol=1e-9) for b in betas), betas


def test_hdt_diesel_long_trip_well_below_one():
    """L = 50 km: beta = 8.25/50 = 0.165."""
    fractions = cold_mileage_fractions(trip_length=50.0)
    betas = _hdt_diesel_betas(fractions)
    assert betas
    assert all(math.isclose(b, 0.165, rel_tol=1e-9) for b in betas), betas


def test_hdt_diesel_beta_never_exceeds_one():
    """For any positive trip length, beta must lie in (0, 1]."""
    for L in (0.5, 1.0, 4.0, 8.25, 8.26, 12.4, 50.0, 200.0):
        fractions = cold_mileage_fractions(trip_length=L)
        betas = _hdt_diesel_betas(fractions)
        assert betas
        assert all(0.0 < b <= 1.0 for b in betas), (L, betas)
