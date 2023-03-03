from pathlib import Path

import pandas as pd
from pandas import testing as tm

from alaqs_core.tools.copert5_utils import ef_query, calculate_emissions, average_emission_factors, \
    calculate_evaporation, average_evaporation
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


def test_roadway_calculation():
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
    efs = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame({
        'category_short': VEHICLE_CATEGORIES.keys(),
        'category_long': VEHICLE_CATEGORIES.values(),
    })

    # Change column names
    efs['fuel'] = efs['fuel'].str.lower()
    efs['vehicle_category'] = \
        efs.merge(vc, how='left', left_on='vehicle_category', right_on='category_long')['category_short']

    # Calculate the emissions
    emissions = calculate_emissions(fleet, efs)

    # Calculate the average emission factors
    emission_factors = average_emission_factors(emissions)

    # Set the reference values (hot emission factors)
    emission_factor_refs = pd.Series({
        'eCO[g/km]': 0.198159277,
        'eNOx[g/km]': 0.045065088,
        'eVOC[g/km]': 0.012275,
    })

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
    efs = pd.read_sql(sql, template_engine)

    # Get the categories
    vc = pd.DataFrame({
        'category_short': VEHICLE_CATEGORIES.keys(),
        'category_long': VEHICLE_CATEGORIES.values(),
    })

    # Change column names
    efs['fuel'] = efs['fuel'].str.lower()
    efs['vehicle_category'] = \
        efs.merge(vc, how='left', left_on='vehicle_category', right_on='category_long')['category_short']

    # Calculate the emissions
    emissions = calculate_emissions(fleet, efs)

    # Calculate the evaporation
    evaporation = calculate_evaporation(fleet, efs)

    # Calculate the average evaporation per vehicle
    mean_evaporation = average_evaporation(evaporation, idle_time)

    # Calculate the average emission factors
    mean_emission_factors = average_emission_factors(emissions)

    # Calculate the average emissions per vehicle
    emission_factors = pd.Series({
        'eCO[g/km]': mean_emission_factors['eCO[g/km]'] * distance,
        'eVOC[g/km]': mean_emission_factors['eVOC[g/km]'] * distance + mean_evaporation['eVOC[g/vh]'],
        'eNOx[g/km]': mean_emission_factors['eNOx[g/km]'] * distance,
    })

    # Set the reference values (hot emission factors)
    evaporation_refs = pd.Series({
        'eVOC[g/vh]': 0.033798717802083,
    })

    # Set the reference values (hot emission factors)
    emission_factor_refs = pd.Series({
        'eCO[g/km]': 0.198159277 * distance,
        'eVOC[g/km]': 0.012275 * distance + 0.033798717802083,
        'eNOx[g/km]': 0.045065088 * distance,
    })

    tm.assert_series_equal(emission_factors, emission_factor_refs)

    tm.assert_series_equal(mean_evaporation, evaporation_refs)

    pass
