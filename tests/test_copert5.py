from pathlib import Path

import pandas as pd
from pandas import testing as tm

from open_alaqs.core.tools.copert5_utils import (
    average_emission_factors,
    average_evaporation,
    calculate_emissions,
    calculate_evaporation,
    ef_query,
)
from open_alaqs.database.generate_templates import get_engine

TEMPLATES_DIR = Path(__file__).parents[1] / "core/templates"

VEHICLE_CATEGORIES = {
    "bus": "Buses",
    "motorcycle": "Motorcycles",
    "lcv": "Light Commercial Vehicles",
    "pc": "Passenger Cars",
    "hdt": "Heavy Duty Trucks",
}


def test_query():
    """
    Check if the query is built correctly
    """

    # Set the country
    country = "Belgium"

    # Set the speed
    speed = 15.1

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / "project.alaqs")

    # Get the contents of the table
    data = pd.read_sql(sql, template_engine)

    assert data.shape == (1255, 7)


def test_roadway_calculation():
    """
    Check if the calculation is performed correctly
    """

    # Set the country
    country = "EU27"

    # Set the speed
    speed = 50

    # Set the fleet mix
    fleet = pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": "Euro 4",
                "N": 100,
                "M[km]": 1000,
            }
        ]
    )

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / "project.alaqs")

    # Get the contents of the table
    efs = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame(
        {
            "category_short": VEHICLE_CATEGORIES.keys(),
            "category_long": VEHICLE_CATEGORIES.values(),
        }
    )

    # Change column names
    efs["fuel"] = efs["fuel"].str.lower()
    efs["vehicle_category"] = efs.merge(
        vc, how="left", left_on="vehicle_category", right_on="category_long"
    )["category_short"]

    # Calculate the emissions
    emissions = calculate_emissions(fleet, efs)

    # Calculate the average emission factors
    emission_factors = average_emission_factors(emissions)

    # Set the reference values (hot emission factors)
    emission_factor_refs = pd.Series(
        {
            "eCH4[g/km]": 0.001982406,
            "eCO[g/km]": 0.198159277,
            "eCO2[g/km]": 164.3222752,
            "eNH3[g/km]": 0.011199387,
            "eNOx[g/km]": 0.045065088,
            "ePM0.1[g/km]": 0.000104992,
            "ePM2.5[g/km]": 0.001049922,
            "eSO2[g/km]": 0.000538297,
            "eVOC[g/km]": 0.012275,
        }
    )

    tm.assert_series_equal(emission_factors, emission_factor_refs)


def test_parking_calculation():
    """
    Check if the calculation is performed correctly
    """

    # Set the idle time [min]
    idle_time = 15

    # Set the travel distance [km]
    distance = 25

    # Set the country
    country = "EU27"

    # Set the speed
    speed = 50

    # Set the fleet mix
    fleet = pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": "Euro 4",
                "N": 100,
                "M[km]": 1000,
            }
        ]
    )

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / "project.alaqs")

    # Get the contents of the table
    efs = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame(
        {
            "category_short": VEHICLE_CATEGORIES.keys(),
            "category_long": VEHICLE_CATEGORIES.values(),
        }
    )

    # Change column names
    efs["fuel"] = efs["fuel"].str.lower()
    efs["vehicle_category"] = efs.merge(
        vc, how="left", left_on="vehicle_category", right_on="category_long"
    )["category_short"]

    # Calculate the emissions
    emissions = calculate_emissions(fleet, efs)

    # Calculate the evaporation
    evaporation = calculate_evaporation(fleet, efs)

    # Calculate the average evaporation per vehicle
    mean_evaporation = average_evaporation(evaporation, idle_time)

    # Calculate the average emission factors
    mean_emission_factors = average_emission_factors(emissions)

    # Calculate the average emissions per vehicle
    emission_factors = pd.Series(
        {
            "eCH4[g/km]": mean_emission_factors["eCH4[g/km]"] * distance,
            "eCO[g/km]": mean_emission_factors["eCO[g/km]"] * distance,
            "eCO2[g/km]": mean_emission_factors["eCO2[g/km]"] * distance,
            "eNH3[g/km]": mean_emission_factors["eNH3[g/km]"] * distance,
            "eNOx[g/km]": mean_emission_factors["eNOx[g/km]"] * distance,
            "ePM0.1[g/km]": mean_emission_factors["ePM0.1[g/km]"] * distance,
            "ePM2.5[g/km]": mean_emission_factors["ePM2.5[g/km]"] * distance,
            "eSO2[g/km]": mean_emission_factors["eSO2[g/km]"] * distance,
            "eVOC[g/km]": mean_emission_factors["eVOC[g/km]"] * distance
            + mean_evaporation["eVOC[g/vh]"],
        }
    )

    # Set the reference values (hot emission factors)
    evaporation_refs = pd.Series(
        {
            "eVOC[g/vh]": 0.033798717802083,
        }
    )

    # Set the reference values (hot emission factors)
    emission_factor_refs = pd.Series(
        {
            "eCH4[g/km]": 0.001982406 * distance,
            "eCO[g/km]": 0.198159277 * distance,
            "eCO2[g/km]": 164.3222752 * distance,
            "eNH3[g/km]": 0.011199387 * distance,
            "eNOx[g/km]": 0.045065088 * distance,
            "ePM0.1[g/km]": 0.000104992 * distance,
            "ePM2.5[g/km]": 0.001049922 * distance,
            "eSO2[g/km]": 0.000538297 * distance,
            "eVOC[g/km]": 0.012275 * distance + 0.033798717802083,
        }
    )

    tm.assert_series_equal(emission_factors, emission_factor_refs)

    tm.assert_series_equal(mean_evaporation, evaporation_refs)
