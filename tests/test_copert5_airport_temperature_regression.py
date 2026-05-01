"""
Regression test for the COPERT5 'airport_temperature' KeyError.

`copert5.roadway_emission_factors(input_data, study_data)` is called by
both `ui_parkings.py` and `ui_roadways.py` when the user clicks
"Recalculate" on a Parking or Roadway feature. The function previously
read the airport temperature from `input_data["airport_temperature"]`,
but that dict is built from the per-feature attribute form (which has
no temperature field). The temperature lives on `study_data`, populated
from `user_study_setup.airport_temperature` (default 15 °C from the
blank-study template).

Result before the fix: clicking Recalculate raised
`KeyError: 'airport_temperature'` and the UI showed
"Emissions could not be calculated: 'airport_temperature'".
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_copert5_reads_airport_temperature_from_study_data():
    """The fix must move the temperature read from input_data to study_data.
    Pinning the source line guards against a regression where someone
    'cleans up' by re-uniting the two dicts and accidentally restores the
    old key path."""
    src = (REPO / "open_alaqs" / "core" / "tools" / "copert5.py").read_text()

    # The buggy form must be absent.
    assert 'input_data["airport_temperature"]' not in src, (
        "copert5.py still reads airport_temperature from input_data. "
        "It must read it from study_data instead, otherwise clicking "
        '"Recalculate" on a Parking or Roadway feature raises '
        'KeyError("airport_temperature") because the per-feature form '
        "dict has no such key."
    )
    # The fixed form must be present.
    assert 'study_data["airport_temperature"]' in src, (
        "copert5.py must read airport_temperature from study_data, which is "
        "populated from user_study_setup.airport_temperature."
    )


def test_copert5_function_signature_takes_two_dicts():
    """Locks the calling convention. If someone refactors
    roadway_emission_factors to take a single merged dict, the fix above
    becomes meaningless and this test must be updated together."""
    src = (REPO / "open_alaqs" / "core" / "tools" / "copert5.py").read_text()
    assert "def roadway_emission_factors(input_data: dict, study_data: dict)" in src, (
        "roadway_emission_factors signature must remain "
        "(input_data: dict, study_data: dict). The regression fix at "
        "line 133 assumes airport_temperature lives on study_data."
    )
