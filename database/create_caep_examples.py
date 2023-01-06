"""
How to run this script:

1. Within QGIS, open the python console (ctrl + alt + p)

2. Import this script:
`from open_alaqs.database.create_caep_examples import *`

3. Execute `create_caep_examples()` to create all examples or select one the other functions.

"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

import qgis

logging.basicConfig(level=logging.DEBUG)

SRC_DIR = Path(__file__).parent / 'src'
EXAMPLES_DIR = Path(__file__).parents[1] / 'example'
TEMPLATES_DIR = Path(__file__).parents[1] / 'alaqs_core/templates'


def sql_insert_into(table: str, data: dict) -> str:
    column_names = []
    values = []
    for k, v in data.items():
        qv = f"'{v}'"
        if k == 'wkt':
            k = 'geometry'
            qv = f"ST_GeomFromText('{v}', 3857)"
        column_names.append(k)
        values.append(qv)

    return f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({', '.join(values)})"


def create_caep_case_1():
    """
    Elevated point source. This is probably the simplest dispersion situation one can think of. Wind
    tunnel data for validation are available.

    - Passive point source at 60 m height above ground at x=0 m/y=0 m
    - Emission 1 g/s NOx, no chemical conversion
    - Wind speed at source exit 10 m/s
    - Obukhov length infinity (neutral stratification)
    - Surface roughness length 0.7 m, no displacement height
    - Stationary concentration distribution at 1.5 m height above ground
    - Horizontal resolution at least 30 m
    - Extent -100 m<x<4000 m, -2000 m<y<2000 m

    From CAEP/12-MDG-FESG/3-IP/14 22/02/2020
    """

    # Set the source properties
    point_source_dict = {
        'source_id': 1,
        'source_height': 60,
        'source_category': 'Other',
        'source_type': 'NA',
        'source_substance': '',
        'source_temperature': 15.,
        'source_diameter': 1.,
        'source_velocity': 0.,
        'source_ops_year': 1,
        'source_hour_profile': 'default',
        'source_daily_profile': 'default',
        'source_monthly_profile': 'default',
        'source_co_kg_k': 0.,
        'source_hc_kg_k': 0.,
        'source_nox_kg_k': 31536.,
        'source_sox_kg_k': 0.,
        'source_pm10_kg_k': 0.,
        'source_p1_kg_k': 0.,
        'source_p2_kg_k': 0.,
        'source_instudy': 1,
        'source_wkt': Point(0, 0).wkt
    }

    # Set the meteorological properties
    meteorology_dict = {
        'Scenario': 'default',
        'DateTime(YYYY-mm-dd hh:mm:ss)': datetime.utcnow().strftime('%Y-01-01 00:00:00'),
        'Temperature(K)': 288.5,
        'Humidity(kg_water/kg_dry_air)': 0.00634,
        'RelativeHumidity(%)': 0.68,
        'SeaLevelPressure(mb)': 97600,
        'WindSpeed(m/s)': 10,
        'WindDirection(degrees)': 270,
        'ObukhovLength(m)': 99999,
        'MixingHeight(m)': 914.4
    }

    # Set the path to the example
    example_path = EXAMPLES_DIR / 'case_1.alaqs'
    example_mov_path = EXAMPLES_DIR / 'case_1_movement.csv'
    example_met_path = EXAMPLES_DIR / 'case_1_meteorology.csv'

    # Get the path to the template
    template_path = TEMPLATES_DIR / 'project.alaqs'

    # Duplicate the template to act as basis for the new example project
    logging.info(f'Duplicate {template_path.name}')
    shutil.copy(template_path, example_path)

    # Connect to the example project
    con = qgis.utils.spatialite_connect(str(example_path))

    # Create the SQL query
    sql_text = sql_insert_into('shapes_point_sources', {
        'source_id': point_source_dict['source_id'],
        'height': point_source_dict['source_height'],
        'category': point_source_dict['source_category'],
        'point_type': point_source_dict['source_type'],
        'substance': point_source_dict['source_substance'],
        'temperature': point_source_dict['source_temperature'],
        'diameter': point_source_dict['source_diameter'],
        'velocity': point_source_dict['source_velocity'],
        'ops_year': point_source_dict['source_ops_year'],
        'hour_profile': point_source_dict['source_hour_profile'],
        'daily_profile': point_source_dict['source_daily_profile'],
        'month_profile': point_source_dict['source_monthly_profile'],
        'co_kg_k': point_source_dict['source_co_kg_k'],
        'hc_kg_k': point_source_dict['source_hc_kg_k'],
        'nox_kg_k': point_source_dict['source_nox_kg_k'],
        'sox_kg_k': point_source_dict['source_sox_kg_k'],
        'pm10_kg_k': point_source_dict['source_pm10_kg_k'],
        'p1_kg_k': point_source_dict['source_p1_kg_k'],
        'p2_kg_k': point_source_dict['source_p2_kg_k'],
        'instudy': point_source_dict['source_instudy'],
        'wkt': point_source_dict['source_wkt']
    })

    # Dump the query for debugging
    logging.debug(sql_text)

    # Execute the sql query
    try:
        curs = con.cursor()
        curs.execute(sql_text)
        con.commit()
        logging.info("Added point source %s to database" % point_source_dict['source_id'])
    except Exception as e:
        logging.error(e)
        logging.error(f'Couldn\'t add point source {point_source_dict["source_id"]} to database')
    finally:
        con.close()

    # Create the movement file
    logging.info("Create empty movement file")
    pd.DataFrame(columns=(
        'runway_time',
        'block_time',
        'aircraft_registration',
        'aircraft',
        'gate',
        'departure_arrival',
        'runway',
        'engine_name',
        'prof_id',
        'track_id',
        'taxi_route',
        'tow_ratio',
        'apu_code',
        'taxi_engine_count',
        'set_time_of_main_engine_start_after_block_off_in_s',
        'set_time_of_main_engine_start_before_takeoff_in_s',
        'set_time_of_main_engine_off_after_runway_exit_in_s',
        'engine_thrust_level_for_taxiing',
        'taxi_fuel_ratio',
        'number_of_stop_and_gos',
        'domestic'
    )).to_csv(example_mov_path, index=False, sep=';')

    # Create the meteorology file
    logging.info("Create meteorology file")
    pd.DataFrame([meteorology_dict]).to_csv(example_met_path, index=False)


def create_caep_case_2():
    """
    Point source near ground. This case with a source near ground (influence of wind shear) and in
    case b with deposition is slightly more complex. The setup is taken from the Prairie Grass
    Validation Data Set (No. 24). Close to the ground (below 5 m or so), a fine vertical resolution is
    required.

    - Passive point source at 0.4 m height above ground
    - Emission 1 g/s SO2, no chemical conversion
    - Calculation a) without and b) with dry deposition (deposition velocity 0.009 m/s)
    - Wind speed at 2 m height above ground 6.2 m/s
    - Obukhov length 248 m, friction velocity 0.38 m/s
    - Surface roughness length 0.008 m, no displacement height
    - Stationary concentration distribution at 0.5 m height above ground
    - Extent -100 m<x<1000 m, -500 m<y<500 m
    - Horizontal resolution at least 10 m

    From CAEP/12-MDG-FESG/3-IP/14 22/02/2020
    """

    # Set the source properties
    point_source_dict = {
        'source_id': 1,
        'source_height': 0.4,
        'source_category': 'Other',
        'source_type': 'NA',
        'source_substance': '',
        'source_temperature': 15.,
        'source_diameter': 1.,
        'source_velocity': 0.,
        'source_ops_year': 1,
        'source_hour_profile': 'default',
        'source_daily_profile': 'default',
        'source_monthly_profile': 'default',
        'source_co_kg_k': 0.,
        'source_hc_kg_k': 0.,
        'source_nox_kg_k': 0.,
        'source_sox_kg_k': 31536.,
        'source_pm10_kg_k': 0.,
        'source_p1_kg_k': 0.,
        'source_p2_kg_k': 0.,
        'source_instudy': 1,
        'source_wkt': 'POINT (0 0)'
    }

    # Set the meteorological properties
    meteorology_dict = {
        'Scenario': 'default',
        'DateTime(YYYY-mm-dd hh:mm:ss)': datetime.utcnow().strftime('%Y-01-01 00:00:00'),
        'Temperature(K)': 288.5,
        'Humidity(kg_water/kg_dry_air)': 0.00634,
        'RelativeHumidity(%)': 0.68,
        'SeaLevelPressure(mb)': 97600,
        'WindSpeed(m/s)': 6.2,
        'WindDirection(degrees)': 270,
        'ObukhovLength(m)': 248,
        'MixingHeight(m)': 914.4
    }

    # Set the path to the example
    example_path = EXAMPLES_DIR / 'case_2.alaqs'
    example_mov_path = EXAMPLES_DIR / 'case_2_movement.csv'
    example_met_path = EXAMPLES_DIR / 'case_2_meteorology.csv'

    # Get the path to the template
    template_path = TEMPLATES_DIR / 'project.alaqs'

    # Duplicate the template to act as basis for the new example project
    logging.info(f'Duplicate {template_path.name}')
    shutil.copy(template_path, example_path)

    # Connect to the example project
    con = qgis.utils.spatialite_connect(str(example_path))

    # Create the SQL query
    sql_text = sql_insert_into('shapes_point_sources', {
        'source_id': point_source_dict['source_id'],
        'height': point_source_dict['source_height'],
        'category': point_source_dict['source_category'],
        'point_type': point_source_dict['source_type'],
        'substance': point_source_dict['source_substance'],
        'temperature': point_source_dict['source_temperature'],
        'diameter': point_source_dict['source_diameter'],
        'velocity': point_source_dict['source_velocity'],
        'ops_year': point_source_dict['source_ops_year'],
        'hour_profile': point_source_dict['source_hour_profile'],
        'daily_profile': point_source_dict['source_daily_profile'],
        'month_profile': point_source_dict['source_monthly_profile'],
        'co_kg_k': point_source_dict['source_co_kg_k'],
        'hc_kg_k': point_source_dict['source_hc_kg_k'],
        'nox_kg_k': point_source_dict['source_nox_kg_k'],
        'sox_kg_k': point_source_dict['source_sox_kg_k'],
        'pm10_kg_k': point_source_dict['source_pm10_kg_k'],
        'p1_kg_k': point_source_dict['source_p1_kg_k'],
        'p2_kg_k': point_source_dict['source_p2_kg_k'],
        'instudy': point_source_dict['source_instudy'],
        'wkt': point_source_dict['source_wkt']
    })

    # Dump the query for debugging
    logging.debug(sql_text)

    # Execute the sql query
    try:
        curs = con.cursor()
        curs.execute(sql_text)
        con.commit()
        logging.info("Added point source %s to database" % point_source_dict['source_id'])
    except Exception as e:
        logging.error(e)
        logging.error(f'Couldn\'t add point source {point_source_dict["source_id"]} to database')
    finally:
        con.close()

    # Create the movement file
    logging.info("Create empty movement file")
    pd.DataFrame(columns=(
        'runway_time',
        'block_time',
        'aircraft_registration',
        'aircraft',
        'gate',
        'departure_arrival',
        'runway',
        'engine_name',
        'prof_id',
        'track_id',
        'taxi_route',
        'tow_ratio',
        'apu_code',
        'taxi_engine_count',
        'set_time_of_main_engine_start_after_block_off_in_s',
        'set_time_of_main_engine_start_before_takeoff_in_s',
        'set_time_of_main_engine_off_after_runway_exit_in_s',
        'engine_thrust_level_for_taxiing',
        'taxi_fuel_ratio',
        'number_of_stop_and_gos',
        'domestic'
    )).to_csv(example_mov_path, index=False, sep=';')

    # Create the meteorology file
    logging.info("Create meteorology file")
    pd.DataFrame([meteorology_dict]).to_csv(example_met_path, index=False)


def create_caep_case_3_profile() -> pd.DataFrame:
    # Create a new profile
    custom_aircraft_profile = pd.DataFrame([
        {
            "profile_id": "A319-131-D-C",
            "arrival_departure": "D",
            "stage": 1,
            "point": 1,
            "weight_lbs": 125900,
            "horizontal_metres": 0,
            "vertical_metres": 0,
            "tas_metres": 0,
            "power": None,
            "mode": "TO",
            "course": "ANP2.2"
        },
        {
            "profile_id": "A319-131-D-C",
            "arrival_departure": "D",
            "stage": 1,
            "point": 2,
            "weight_lbs": 125900,
            "horizontal_metres": 1500,
            "vertical_metres": 0,
            "tas_metres": 75,
            "power": None,
            "mode": "TO",
            "course": "ANP2.2"
        },
    ])

    # Get the values from the profile for interpolation
    tas = custom_aircraft_profile['tas_metres']
    s = custom_aircraft_profile['horizontal_metres']

    # Set the known parameters
    t = pd.Series([0, 40], name='time_seconds')  # in seconds, by definition
    a = 1.875  # m/s^2 - derived from other values!

    # Find the additional points to achieve delta TAS < 10 m/s
    p = tas.shape[0]
    while (tas.diff() > 10).any():
        p += 1

        # Calculate the timestamps
        t = pd.Series(np.linspace(0, 40, p), name='seconds')

        # Calculate the distance and speed
        s = .5 * a * t ** 2
        tas = a * t

    # Add the additional points
    custom_aircraft_profile = pd.DataFrame({
        'tas_metres': tas,
        'horizontal_metres': s
    })
    custom_aircraft_profile["profile_id"] = "A319-131-D-C"
    custom_aircraft_profile["arrival_departure"] = "D"
    custom_aircraft_profile["stage"] = 1
    custom_aircraft_profile["weight_lbs"] = 125900
    custom_aircraft_profile["vertical_metres"] = 0
    custom_aircraft_profile["power"] = None
    custom_aircraft_profile["mode"] = "TO"
    custom_aircraft_profile["course"] = "ANP2.2"
    custom_aircraft_profile['point'] = custom_aircraft_profile.index + 1

    # Perform unit conversions
    custom_aircraft_profile["tas_knots"] = \
        custom_aircraft_profile["tas_metres"] / 1852 * 3600
    custom_aircraft_profile["vertical_feet"] = \
        custom_aircraft_profile["vertical_metres"] / .3048
    custom_aircraft_profile["horizontal_feet"] = \
        custom_aircraft_profile["horizontal_metres"] / .3048
    custom_aircraft_profile["weight_kgs"] = \
        custom_aircraft_profile["weight_lbs"] / 2.204623

    return custom_aircraft_profile


def create_caep_case_3():
    """
    Aircraft at idle and take-off. This is still a simple, but more practise-related configuration.
    Dispersion results will not only depend on the dispersion and meteorological model as in the
    previous test cases, but also on how the aircraft and exhaust dynamics are modelled. Note that for
    the daily average, it does not matter how the 20 aircraft departures are distributed over the day;
    one could even model just one departure with an emission enhanced by a factor of 20. The test
    could be split alternatively in two, one only with taxiing emissions and one only with take-off
    emissions.

    - For a day with constant meteorological conditions, modelling of 20 aircraft of type A319
    with taxiing from the apron area to the runway and subsequent take-off. The daily mean
    concentration is calculated.
    - Taxiway from 0 m/1500 m to 0 m/0 m, taxiing speed 10 m/s (taxing time 150 s), both
    engines at certification IDLE power.
    - Take-off at runway from 0 m/0 m at rest to lift-off at 1500 m/0 m with end speed 75 m/s
    after 40 s (constant acceleration), both engines at certification TAKEOFF power. Fuel
    flow and NOx emission indices for IDLE and TAKEOFF from ICAO EEDB Issue 25 or
    newer, UID 10IA012. Emissions at climb should be set to zero.
    - Calculation without deposition
    - Wind speed at 10 m height above ground 3 m/s, wind direction 225 deg
    - Obukhov length infinity (neutral stratification)
    - Surface roughness length 0.5 m, no displacement height
    - For cross-checking, total emission should be reported
    - Daily mean concentration of NOx at 1.5 m height above ground
    - Extent -3000 m<x<3000 m, -1000 m<y<3000 m
    - Horizontal resolution at least 50 m

    From CAEP/12-MDG-FESG/3-IP/14 22/02/2020
    """

    # Set the source properties
    runway_dict = {
        'runway_id': '27/09',
        'capacity': 100,
        'touchdown': 0,
        'max_queue_speed': 100.,
        'peak_queue_time': 0.,
        'instudy': 1,
        'wkt': LineString([[0, 0], [-1500, 0]]).wkt
    }
    gate_dict = {
        'gate_id': 'caep_gate',
        'gate_type': 'REMOTE',
        'gate_height': 0.,
        'instudy': 1,
        'wkt': Point([0, 1500]).buffer(100).wkt
    }
    taxiway_dict = {
        'taxiway_id': 'caep_taxiway',
        'speed': 10.,
        'time': None,
        'instudy': 1,
        'wkt': LineString([[0, 1500], [0, 0]]).wkt
    }

    # Set the taxi routes
    taxiroute_dict = {
        'gate': 'caep_gate',
        'route_name': 'caep_gate/27/D/1',
        'runway': '27',
        'departure_arrival': 'D',
        'instance_id': 1,
        'sequence': 'caep_taxiway',
        'groups': 'JET BUSINESS,JET LARGE,JET MEDIUM,JET REGIONAL,JET SMALL,TURBOPROP'
    }

    # Create the custom profile
    case_3_profile = create_caep_case_3_profile()

    # Set the movement properties
    movement_dict = {
        'runway_time': '2015-01-01 00:30:00',
        'block_time': '2015-01-01 00:27:30',
        'aircraft_registration': None,
        'aircraft': 'A319',
        'gate': 'caep_gate',
        'departure_arrival': 'D',
        'runway': '27',
        'engine_name': '10IA012',
        'prof_id': 'A319-131-D-C',
        'track_id': None,
        'taxi_route': 'caep_gate/27/D/1',
        'tow_ratio': None,
        'apu_code': None,
        'taxi_engine_count': 1,
        'set_time_of_main_engine_start_after_block_off_in_s': None,
        'set_time_of_main_engine_start_before_takeoff_in_s': None,
        'set_time_of_main_engine_off_after_runway_exit_in_s': None,
        'engine_thrust_level_for_taxiing': None,
        'taxi_fuel_ratio': 0.07,
        'number_of_stop_and_gos': 1,
        'domestic': None
    }

    # Set the meteorological properties
    meteorology_dict = {
        'Scenario': 'default',
        'DateTime(YYYY-mm-dd hh:mm:ss)': datetime.utcnow().strftime('%Y-01-01 00:00:00'),
        'Temperature(K)': 288.5,
        'Humidity(kg_water/kg_dry_air)': 0.00634,
        'RelativeHumidity(%)': 0.68,
        'SeaLevelPressure(mb)': 97600,
        'WindSpeed(m/s)': 3,
        'WindDirection(degrees)': 225,
        'ObukhovLength(m)': 99999,
        'MixingHeight(m)': 914.4
    }

    # Set the path to the example
    example_path = EXAMPLES_DIR / 'case_3.alaqs'
    example_mov_path = EXAMPLES_DIR / 'case_3_movement.csv'
    example_met_path = EXAMPLES_DIR / 'case_3_meteorology.csv'

    # Get the path to the template
    template_path = TEMPLATES_DIR / 'project.alaqs'

    # Duplicate the template to act as basis for the new example project
    logging.info(f'Duplicate {template_path.name}')
    shutil.copy(template_path, example_path)

    # Connect to the example project
    con = qgis.utils.spatialite_connect(str(example_path))

    # Create the SQL query
    sql_text_runways = sql_insert_into('shapes_runways', runway_dict)
    sql_text_taxiways = sql_insert_into('shapes_taxiways', taxiway_dict)
    sql_text_gates = sql_insert_into('shapes_gates', gate_dict)
    sql_text_taxiroutes = sql_insert_into('user_taxiroute_taxiways', taxiroute_dict)

    # Dump the query for debugging
    logging.debug(sql_text_runways)
    logging.debug(sql_text_taxiways)
    logging.debug(sql_text_gates)
    logging.debug(sql_text_taxiroutes)

    # Add the custom profile to the database
    case_3_profile.to_sql('default_aircraft_profiles', con, index=False, if_exists='append')
    logging.info("Added custom profile %s to database" % movement_dict['prof_id'])

    # Execute the sql query
    try:
        curs = con.cursor()
        curs.execute(sql_text_runways)
        curs.execute(sql_text_taxiways)
        curs.execute(sql_text_gates)
        curs.execute(sql_text_taxiroutes)
        con.commit()
        logging.info("Added runway %s to database" % runway_dict['runway_id'])
        logging.info("Added taxiway %s to database" % taxiway_dict['taxiway_id'])
        logging.info("Added gate %s to database" % gate_dict['gate_id'])
        logging.info("Added taxi route %s to database" % taxiroute_dict['route_name'])
    except Exception as e:
        logging.error(e)
        logging.error(f"Could not add runway {runway_dict['runway_id']} to database")
        logging.error(f"Could not add taxiway {taxiway_dict['taxiway_id']} to database")
        logging.error(f"Could not add gate {gate_dict['gate_id']} to database")
        logging.error(f"Could not add taxi route {taxiroute_dict['route_name']} to database")
    finally:
        con.close()

    # Create the movement file
    logging.info("Create movement file")
    movements = pd.DataFrame(20 * [movement_dict])

    # Set the timestamp format
    time_format = "%Y-%m-%d %H:%M:%S"

    # Generate new timestamps
    runway_time_deltas = np.linspace(0, 23, num=20)
    runway_date = datetime.strptime(movements['runway_time'].iloc[0], time_format)
    runway_date = runway_date.replace(hour=0, minute=30, second=0, microsecond=0)

    # Generate list of timestamps
    runway_times = runway_date + pd.Series(runway_time_deltas) * pd.to_timedelta(1, unit='h')

    # Calculate block times
    block_times = runway_times - pd.to_timedelta(150, unit='s')

    # Update the data in the table
    movements['runway_time'] = runway_times.dt.strftime(time_format)
    movements['block_time'] = block_times.dt.strftime(time_format)

    # Store the movements file
    movements.to_csv(example_mov_path, index=False, sep=';')

    # Create the meteorology file
    logging.info("Create meteorology file")
    pd.DataFrame([meteorology_dict]).to_csv(example_met_path, index=False)


def create_caep_examples():
    """
    Create 3 CAEP case studies.
    """
    create_caep_case_1()
    create_caep_case_2()
    create_caep_case_3()


if __name__ == "__main__":
    create_caep_examples()
