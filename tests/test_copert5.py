from pathlib import Path

import pandas as pd
from pandas import testing as tm

from alaqs_core.tools.copert5_utils import ef_query, calculate_emissions, average_emission_factors
from database.generate_templates import get_engine

TEMPLATES_DIR = Path(__file__).parents[1] / 'alaqs_core/templates'

VEHICLE_CATEGORIES = {
    "bus": "Buses",
    "motorcycle": "Motorcycles",
    "lcv": "Light Commercial Vehicles",
    "pc": "Passenger Cars",
    "hdt": "Heavy Duty Trucks"
}


def test_query():
    """
    Check if the query is built correctly
    """

    # Set the country
    country = 'Belgium'

    # Set the speed
    speed = 15.1

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f'project.alaqs')

    # Get the contents of the table
    data = pd.read_sql(sql, template_engine)

    assert data.shape == (1255, 7)


def test_calculation():
    """
    Check if the calculation is performed correctly
    """

    # Set the country
    country = 'EU27'

    # Set the speed
    speed = 50

    # Set the fleet mix
    fleet = pd.DataFrame([{
        'vehicle_category': 'pc',
        'fuel': 'petrol',
        'euro_standard': 'Euro 4',
        'N': 100,
        'M[km]': 1000
    }])

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f'project.alaqs')

    # Get the contents of the table
    ef_data = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame({
        'category_short': VEHICLE_CATEGORIES.keys(),
        'category_long': VEHICLE_CATEGORIES.values(),
    })

    # Change column names
    ef_data['fuel'] = ef_data['fuel'].str.lower()
    ef_data['vehicle_category'] = \
        ef_data.merge(vc, how='left', left_on='vehicle_category', right_on='category_long')['category_short']

    # Calculate the emissions
    emissions = calculate_emissions(fleet, ef_data)

    # Calculate the average emission factors
    emission_factors = average_emission_factors(emissions)

    # Set the reference values (hot emission factors)
    emission_factor_refs = pd.Series({
        'eCO[g/km]': 0.198159277,
        'eNOx[g/km]': 0.045065088,
        'eVOC[g/km]': 0.012275,
    })

    tm.assert_series_equal(emission_factors, emission_factor_refs)
