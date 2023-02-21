from pathlib import Path

import pandas as pd
import pytest

from alaqs_core.tools.copert5_utils import normalize_speed, ef_query
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


@pytest.mark.skip(reason="Validation results need to be reviewed")
def test_calculation():
    """
    Check if the calculation is performed correctly
    """

    # Set the country
    country = 'Belgium'

    # Set the speed
    speed = 10

    # Set the fleet mix
    fleet = {
        "pc": {
            "euro_standard": "Euro 5",
            "mix": {
                "petrol": 12.5,
                "diesel": 12.5,
            },
        },
        "lcv": {
            "euro_standard": "Euro 5",
            "mix": {
                "petrol": 12.5,
                "diesel": 12.5,
            },
        },
        "hdt": {
            "euro_standard": "Euro V",
            "mix": {
                "petrol": 12.5,
                "diesel": 12.5,
            },
        },
        "motorcycle": {
            "euro_standard": "Euro 5",
            "mix": {
                "petrol": 12.5,
            },
        },
        "bus": {
            "euro_standard": "Euro V",
            "mix": {
                "diesel": 12.5,
            },
        },
    }

    # Build the query
    sql = ef_query(speed, country)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f'project.alaqs')

    # Get the contents of the table
    data = pd.read_sql(sql, template_engine)

    assert data.shape == (1255, 7)

    # todo: Determine average trip length
    # todo: Determine average temperature

    efs = []
    for vehicle_category, vc_settings in fleet.items():

        # Get the data for this vehicle category
        data_vc = data[
            (data['vehicle_category'] == VEHICLE_CATEGORIES[vehicle_category]) &
            (data['euro_standard'] == vc_settings['euro_standard']) &
            (data['hot-cold-evaporation'] == 'Hot')
            ]

        assert not data_vc.empty

        assert not data_vc.duplicated(['vehicle_category', 'pollutant', 'fuel']).any()

        for fuel, data_vc_fuel in data_vc.groupby('fuel'):
            # todo: Determine Hot emissions

            # todo: Determine Cold emissions

            # Determine the fleet percentage
            percentage = vc_settings['mix'][fuel.lower()]

            assert data_vc_fuel['pollutant'].unique().shape[0] == 10

            # Scale the emission factors
            data_vc_fuel_ef = data_vc_fuel[['pollutant', 'e[g/km]']].set_index('pollutant') * percentage / 100

            efs.append(data_vc_fuel_ef)

    # Combine all emission factors
    efs = pd.concat(efs, axis=1).sum(axis=1)

    # todo: Update the reference values from the file
    assert abs(efs['CH4'] - 0.028530671) < 1e-5, 'CH4'
    assert abs(efs['NH3'] - 0.004395411) < 1e-5, 'NH3'
    assert abs(efs['CO'] - 1.830404253) < 1e-5, 'CO'
    assert abs(efs['CO2'] - 610.6688142) < 1e-5, 'CO2'
    assert abs(efs['NOx'] - 3.795697097) < 1e-5, 'NOx'
    assert abs(efs['PM0.1'] - 0.002388824) < 1e-5, 'PM0.1'
    assert abs(efs['PM2.5'] - 0.023888237) < 1e-5, 'PM2.5'
    assert abs(efs['PM10'] - 0.02389) < 1e-5, 'PM10'
    assert abs(efs['SO2'] - 0.002308892) < 1e-5, 'SO2'
    assert abs(efs['VOC'] - 0.997554748) < 1e-5, 'VOC'
