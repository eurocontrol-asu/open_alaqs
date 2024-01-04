from pathlib import Path

import pandas as pd

from open_alaqs.alaqs_core.tools.copert5_utils import (
    VEHICLE_CATEGORIES,
    average_emission_factors,
    calculate_emissions,
    ef_query,
)
from open_alaqs.database.generate_templates import get_engine

TEMPLATES_DIR = Path(__file__).parents[1] / "alaqs_core/templates"


def test_query():
    """
    Check if the query is built correctly
    """

    # Build the query
    sql = ef_query(15.1, country="Belgium")

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f"project.alaqs")

    # Get the contents of the table
    data = pd.read_sql(sql, template_engine)

    assert data.shape == (1255, 7)


def test_emissions_passenger_cars():
    # Set the combination
    fleet = pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": "Euro 1",
                "N": 1000000,
                "M[km]": 1000,
            }
        ]
    )

    # Build the query
    sql = ef_query(15.1, country="Belgium")

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f"project.alaqs")

    # Get the contents of the table
    ef_data = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame(
        {
            "category_short": VEHICLE_CATEGORIES.keys(),
            "category_long": VEHICLE_CATEGORIES.values(),
        }
    )

    # Change column names
    ef_data["fuel"] = ef_data["fuel"].str.lower()
    ef_data["vehicle_category"] = ef_data.merge(
        vc, how="left", left_on="vehicle_category", right_on="category_long"
    )["category_short"]

    # Calculate the emissions
    e = calculate_emissions(fleet, ef_data)

    # Calculate the average emission factors
    average_emission_factors(e)
