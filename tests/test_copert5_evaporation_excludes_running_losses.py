"""
Regression test for the B7 fix: parking-source evaporation excludes Running
losses, per EMEP/EEA Guidebook 2023 Update 2025, chapter 1.A.3.b.v "Gasoline
evaporation" §4.7 (p.28-29).

Verbatim Guidebook reference (§4.7 Gridding, p.28-29):

    "Running losses are proportional to the mileage driven by the vehicles.
     Therefore, their allocation to urban areas, rural areas and highways
     has to follow the mileage split assumed for the calculation of exhaust
     emissions."

i.e. Running losses are mileage-based and belong on driving (road) sources,
not on parking sources. Parking should sum only Diurnal + Hot soak.

Prior to the fix, calculate_evaporation summed all three modes (Diurnal,
Hot soak, Running losses) into eVOC[g/day]. The pre-fix code would fail
these tests.

When the next EMEP/EEA Guidebook update lands, re-verify against the new
§4.7 of chapter 1.A.3.b.v to confirm the spatial-allocation rule has not
changed.
"""

import pandas as pd

from open_alaqs.core.tools.copert5_utils import calculate_evaporation


def _build_synthetic_efs(diurnal: float, hot_soak: float, running_losses: float):
    """Construct a minimal EF DataFrame with known values for each evaporation
    split mode for a single (pc, petrol, Conventional) technology row."""
    rows = [
        {
            "vehicle_category": "pc",
            "fuel": "petrol",
            "euro_standard": "Conventional",
            "hot-cold-evaporation": "Evaporation",
            "evaporation_split": "Diurnal",
            "e[g/km]": diurnal,
        },
        {
            "vehicle_category": "pc",
            "fuel": "petrol",
            "euro_standard": "Conventional",
            "hot-cold-evaporation": "Evaporation",
            "evaporation_split": "Hot soak",
            "e[g/km]": hot_soak,
        },
        {
            "vehicle_category": "pc",
            "fuel": "petrol",
            "euro_standard": "Conventional",
            "hot-cold-evaporation": "Evaporation",
            "evaporation_split": "Running losses",
            "e[g/km]": running_losses,
        },
    ]
    return pd.DataFrame(rows)


def _build_fleet():
    fleet = pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": "Conventional",
                "N": 100,
            }
        ]
    )
    fleet["M[km]"] = 1000
    return fleet


def test_evaporation_excludes_running_losses_modern_fleet():
    """Modern Euro 1+ fleet: small but non-zero Running losses share."""
    efs = _build_synthetic_efs(diurnal=4.0, hot_soak=0.18, running_losses=0.056)
    result = calculate_evaporation(_build_fleet(), efs)
    expected = 4.0 + 0.18  # Diurnal + Hot soak only (Guidebook §4.7)
    actual = float(result["eVOC[g/day]"].iloc[0])
    assert actual == expected, (
        f"Expected {expected} g/day (Diurnal + Hot soak only), got {actual}. "
        f"Pre-fix code would have returned {expected + 0.056}."
    )


def test_evaporation_excludes_running_losses_uncontrolled_fleet():
    """Pre-Euro 1 fleet: Running losses are a much larger share (~17%)."""
    efs = _build_synthetic_efs(diurnal=4.0, hot_soak=1.35, running_losses=1.07)
    result = calculate_evaporation(_build_fleet(), efs)
    expected = 4.0 + 1.35  # Diurnal + Hot soak only
    actual = float(result["eVOC[g/day]"].iloc[0])
    assert actual == expected, (
        f"Expected {expected} g/day (Diurnal + Hot soak only), got {actual}. "
        f"Pre-fix code would have returned {expected + 1.07} (Running losses "
        f"are 17% of pre-fix total on pre-Euro 1 fleets)."
    )


def test_evaporation_defensive_when_running_losses_missing():
    """Missing Running losses column should not break the calculation."""
    rows = [
        {
            "vehicle_category": "pc",
            "fuel": "petrol",
            "euro_standard": "Conventional",
            "hot-cold-evaporation": "Evaporation",
            "evaporation_split": "Diurnal",
            "e[g/km]": 4.0,
        },
        {
            "vehicle_category": "pc",
            "fuel": "petrol",
            "euro_standard": "Conventional",
            "hot-cold-evaporation": "Evaporation",
            "evaporation_split": "Hot soak",
            "e[g/km]": 0.2,
        },
    ]
    efs = pd.DataFrame(rows)
    result = calculate_evaporation(_build_fleet(), efs)
    assert float(result["eVOC[g/day]"].iloc[0]) == 4.2


def test_evaporation_total_emissions_scale_with_N():
    """EVOC[g/day] = N * eVOC[g/day]: the total should be N times the per-vehicle EF."""
    efs = _build_synthetic_efs(diurnal=2.0, hot_soak=0.5, running_losses=0.1)
    fleet = _build_fleet()  # N=100
    result = calculate_evaporation(fleet, efs)
    # eVOC[g/day] = 2.0 + 0.5 = 2.5 (Diurnal + Hot soak)
    # EVOC[g/day] = N * eVOC[g/day] = 100 * 2.5 = 250
    assert float(result["EVOC[g/day]"].iloc[0]) == 250.0
