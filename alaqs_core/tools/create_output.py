"""
This class is used to create an ALAQS output file from an existing ALAQS study.
"""
import os
import shutil
import sqlite3 as sqlite
from datetime import datetime, timedelta

from open_alaqs.alaqs_core import alaqsdblite
from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.AmbientCondition import \
    AmbientConditionStore
from open_alaqs.alaqs_core.tools import sql_interface
from open_alaqs.alaqs_core.tools.Grid3D import Grid3D

logger = get_logger(__name__)


def create_alaqs_output(inventory_path, model_parameters, study_setup,
                        met_csv_path=""):
    """
    This is the only function in this class that should be called by an external
     function. This function creates a new ALAQS output file based on the
     current study setup, vector layers, and aircraft movements.

    :param inventory_path: the path to the new inventory profile to be created
    :param model_parameters: a dictionary with parameters related to the calculation
    :param study_setup: a dictionary with parameters related to the airport model
    :param met_csv_path: the path to the meteorological data
    :type inventory_path: str
    :return: bool
    """

    # model_parameters
    # {'use_fuel_flow': False,
    # 'include_parkings': True,
    # 'include_area_sources': True,
    # 'include_taxiway_queues': True,
    # 'use_3d_grid': False,
    # 'use_variable_mixing_height': False,
    # 'include_gates': True,
    # 'z_resolution': 10,
    # 'study_end_date': datetime.datetime(2000, 1, 2, 0, 41),
    # 'x_resolution': 250,
    # 'y_resolution': 250,
    # 'x_cells': 40,
    # 'include_building': True,
    # 'study_start_date': datetime.datetime(2000, 1, 1, 1, 41),
    # 'include_roadways': True,
    # 'towing_speed': 10.0,
    # 'vertical_limit': 914.4,
    # 'use_copert': False,
    # 'movement_path': os.path.join("..", "example", "movements_exeter.csv"),
    # 'z_cells': 20,
    # 'include_stationary_sources': True,
    # 'use_smooth_and_shift': False,
    # 'y_cells': 40,
    # 'use_nox_correction': False}

    # study_setup
    # {'airport_latitude': 50.734444,
    # 'airport_country': 'UK',
    # 'project_name': 'Exeter Airport',
    # 'alaqs_version': '0.0.1',
    # 'parking_method': 'DEFAULT',
    # 'airport_code': 'EGTE',
    # 'date_modified': '2014-01-24 14:37:57',
    # 'oid': 1,
    # 'roadway_fleet_year': '2010',
    # 'airport_name': 'Exeter',
    # 'roadway_method': 'ALAQS Method',
    # 'vertical_limit': 913,
    # 'airport_id': 1,
    # 'airport_longitude': -3.413889,
    # 'study_info': 'This is my demo project.',
    # 'date_created': '2014-01-24 14:35:32',
    # 'roadway_country': 'UK',
    # 'airport_elevation': 100,
    # 'airport_temperature': 15}

    result = inventory_create_blank(inventory_path)
    if result is False:
        pass

    inventory_update_tbl_inv_period(inventory_path, model_parameters, study_setup)
    inventory_update_tbl_inv_time(inventory_path, model_parameters)
    inventory_insert_movements(inventory_path, model_parameters)
    inventory_update_mixing_heights(inventory_path)
    inventory_copy_activity_profiles(inventory_path)
    inventory_copy_vector_layers(inventory_path)
    inventory_copy_aircraft(inventory_path)
    inventory_copy_aircraft_engine_ei(inventory_path)
    inventory_copy_gate_profiles(inventory_path)
    inventory_copy_aircraft_start_ef(inventory_path)
    inventory_copy_stationary_substance(inventory_path)
    inventory_copy_stationary_category(inventory_path)
    inventory_copy_aircraft_engine_mode(inventory_path)
    inventory_copy_aircraft_profiles(inventory_path)
    inventory_copy_taxiway_routes(inventory_path)
    inventory_copy_emission_dynamics(inventory_path)
    inventory_copy_study_setup(inventory_path)

    # 3D Grid configuration
    grid_configuration_ = {
        'x_cells': 10,
        'y_cells': 10,
        'z_cells' : 1,
        'x_resolution': 100,
        'y_resolution': 100,
        'z_resolution': 100,
        'reference_latitude': '0.0',  # airport_latitude
        'reference_longitude': '0.0'  # airport_longitude
    }

    grid_cells_header = ['x_resolution', 'y_resolution', 'z_resolution', 'x_cells', 'y_cells', 'z_cells']
    for head in grid_cells_header:
        if head not in model_parameters:
            raise Exception("Did not find '%s' in '%s'." % (head, "model_parameters"))
        else:
            grid_configuration_[head] = model_parameters[head]

    grid_cells_header = ['airport_latitude', 'airport_longitude']
    for head in grid_cells_header:
        if head not in study_setup:
            raise Exception("Did not find '%s' in '%s'." % (head, "study_setup"))
        else:
            grid_configuration_[head.replace("airport", "reference")] = study_setup[head]

    # add grid configuration to sqlite database
    grid = Grid3D(inventory_path, grid_configuration_, deserialize=False)
    # add grid to the database
    grid.serializeConfiguration()

    # save ambient conditions to database
    if met_csv_path:
        store = AmbientConditionStore(inventory_path, init_csv_path=met_csv_path)
        store.serialize()

    logger.info("New output file with path '%s' has been created" % (str(inventory_path)))
    return None


def inventory_create_blank(inventory_name):
    """
    Copy a blank version of the ALAQS inventory to the desired location
    :param inventory_name: the path where the inventory file is to be copied
    :return: None if successful, error otherwise
    """
    try:
        shutil.copy2(os.path.join(os.path.dirname(__file__),
                                  '../templates/inventory_template.alaqs'), inventory_name)
        msg = "[+] Created a blank ALAQS output file"
        logger.info(msg)
        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_create_blank.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_update_tbl_inv_period(database_path, model_parameters, study_setup):
    """
    Add records to the study output that lists one hour intervals for the whole of the user defined study duration
    :param database_path: the path to the study output file
    :param model_parameters: a list of model parameters used to generate an ALAQS output
    """
    try:

        try:
            min_time = datetime.strptime(model_parameters['study_start_date'], "%Y-%m-%d %H:%M:%S")
            max_time = datetime.strptime(model_parameters['study_end_date'], "%Y-%m-%d %H:%M:%S")
        except:
            min_time = datetime.strftime(model_parameters['study_start_date'], "%Y-%m-%d %H:%M:%S")
            max_time = datetime.strftime(model_parameters['study_end_date'], "%Y-%m-%d %H:%M:%S")

        logger.info("Min time: %s" % min_time)
        logger.info("Max time: %s" % max_time)

        interval = 1 / 24
        temp_isa = 273.16 + 15 + study_setup['airport_elevation'] / 1000 * -6.5
        copert = 0
        nox_corr = 0
        ffm = 0
        mix_height = 0
        smsh = 0

        if model_parameters['use_copert'] is True:
            copert = 1
        if model_parameters['use_nox_correction'] is True:
            nox_corr = 1
        if model_parameters['use_fuel_flow'] is True:
            ffm = 1
        if model_parameters['use_smooth_and_shift'] is True:
            smsh = 1
        if model_parameters['use_variable_mixing_height'] is True:
            mix_height = 1

        sql_interface.query_text(database_path, "UPDATE tbl_InvPeriod SET interval=%d, temp_isa=%d, vert_limit=%d, apt_elev=%d, "
                                  "copert=%d, nox_corr=%d, ffm=%d, smsh=%d, mix_height=%d, min_time=\"%s\", "
                                  "max_time=\"%s\";" % (interval, temp_isa, model_parameters['vertical_limit'],
                                                        study_setup['airport_elevation'], copert, nox_corr, ffm,
                                                        smsh, mix_height, min_time, max_time))
        msg = "[+] Updated the output inventory period"
        logger.info(msg)
        return None

    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_update_tbl_inv_period.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_update_tbl_inv_time(inventory_path, model_parameters):
    """
    Update the invTime table with hourly intervals based on the user study definitions
    :param inventory_path: a path to the alaqs study output file
    :param model_parameters: a dict of user defined parameters for the current output
    :return:
    """
    try:
        time_list = []
        hour_delta = timedelta(hours=1)
        try:
            start_time = datetime.strptime(model_parameters['study_start_date'], "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(model_parameters['study_end_date'], "%Y-%m-%d %H:%M:%S")
        except:
            start_time = model_parameters['study_start_date']
            end_time = model_parameters['study_end_date']

        # Create a time stamp for the start of the first hour - kind of floor(start_time)
        current_hour = start_time - timedelta(minutes=start_time.minute % 60, seconds=start_time.second,
                                                       microseconds=start_time.microsecond)

        # Build a list of hours we need to model
        while current_hour <= end_time:

            interval_start = current_hour
            year = interval_start.strftime("%Y")
            month = interval_start.strftime("%m")
            day = interval_start.strftime("%d")
            hour = interval_start.strftime("%H")
            weekday_id = interval_start.weekday()
            mix_height = '914.4'

            time_list.append([interval_start, year, month, day, hour, weekday_id, mix_height])
            current_hour = current_hour + hour_delta

        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        cur.executemany("INSERT INTO tbl_InvTime (time, year, month, day, hour, weekday_id, mix_height) VALUES (?,?,?,?,?,?,?);",
                        time_list)
        conn.commit()
        conn.close()
        msg = "[+] Updated the output time table"
        logger.info(msg)


    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_update_tbl_inv_time.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_insert_movements(inventory_name, model_parameters):
    """
    Insert user defined movement table into the alaqs output file
    :param inventory_name: path to the alaqs output file
    :param model_parameters: a list of user defined model parameters used to generate the study output
    """
    try:
        conn = sqlite.connect(inventory_name)
        cur = conn.cursor()

        with open(model_parameters['movement_path'], 'rt') as movements:
            all_movements = []
            movement_line = 0
            columns_ = 0
            for movement in movements:
                movement_line += 1
                if movement_line > 1:
                    movement_data = \
                        [movement_line - 1] + movement.strip().split(";")
                    if not columns_:
                        columns_ = len(movement_data)
                    all_movements.append(movement_data)

        values_str_ = "?,"*columns_
        values_str_ = values_str_[:-1]
        cur.executemany('INSERT INTO user_aircraft_movements VALUES (%s)' %(values_str_), all_movements)
        conn.commit()
        conn.close()
        msg = "[+] Aircraft movements copied to output file"
        logger.info(msg)

        return None

    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_insert_movements.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_study_setup(inventory_path):
    """
    This function copies data from the currently active project to the inventory output file

    :param inventory_path:
    :return:
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()

        study_setup_data = alaqsdblite.query_string("SELECT * FROM user_study_setup;")
        cur.execute('INSERT INTO user_study_setup VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);', study_setup_data[0])
        conn.commit()
        conn.close()
        msg = "[+] Copied the study setup"
        logger.info(msg)

        return None

    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_study_setup.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_update_mixing_heights(inventory_path):
    # fix_print_with_import
    print("Need to update mixing heights using study_setup")


def inventory_copy_activity_profiles(inventory_path):
    """
    Copy all activity profiles from the currently active project database to the output file
    :param inventory_path: path ot the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()

        hourly_activity_profiles = alaqsdblite.query_string("SELECT * FROM user_hour_profile;")
        cur.executemany('INSERT INTO user_hour_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        hourly_activity_profiles)

        daily_activity_profiles = alaqsdblite.query_string("SELECT * FROM user_day_profile;")
        cur.executemany('INSERT INTO user_day_profile VALUES (?,?,?,?,?,?,?,?,?)', daily_activity_profiles)

        monthly_activity_profiles = alaqsdblite.query_string("SELECT * FROM user_month_profile;")
        cur.executemany('INSERT INTO user_month_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        monthly_activity_profiles)

        conn.commit()
        conn.close()
        msg = "[+] Copied the activity profiles"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_activity_profiles.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_gate_profiles(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        gate_profiles = alaqsdblite.query_string("SELECT * FROM default_gate_profiles;")
        cur.executemany('INSERT INTO default_gate_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', gate_profiles)
        conn.commit()
        conn.close()
        msg = "[+] Copied the gate profiles"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_gate_profiles.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_emission_dynamics(inventory_path):
    """
    Copy all emission_dynamics from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        emission_dynamics = alaqsdblite.query_string("SELECT * FROM default_emission_dynamics;")
        cur.executemany('INSERT INTO default_emission_dynamics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', emission_dynamics)
        conn.commit()
        conn.close()
        msg = "[+] Copied the emission dynamics"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_emission_dynamics.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_taxiway_routes(inventory_path):
    """
    Copy all taxiway routes from the currently active project database to alaqs output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        gate_profiles = alaqsdblite.query_string("SELECT * FROM user_taxiroute_taxiways;")
        cur.executemany('INSERT INTO user_taxiroute_taxiways VALUES (?,?,?,?,?,?,?,?)', gate_profiles)
        conn.commit()
        conn.close()
        msg = "[+] Copied the taxiway routes"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_taxiway_routes.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_vector_layers(inventory_path):
    """
    Copy all vector layers from the currently active alaqs project file to the output file
    :param inventory_path: path to the alaqs output file
    """

    try:
        conn = sql_interface.connect(inventory_path)
        curs = conn.cursor()

        try:
            area_sources = alaqsdblite.query_string("SELECT * FROM shapes_area_sources;")
            curs.executemany('INSERT INTO shapes_area_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', area_sources)
            conn.commit()
            msg = "[+] Area sources copied to output file"
            logger.info(msg)

        except Exception as e:
            # fix_print_with_import
            print(e)
            msg = "Problem copying area sources: %s" % e
            logger.error(msg)


        try:
            buildings = alaqsdblite.query_string("SELECT * FROM shapes_buildings;")
            curs.executemany('INSERT INTO shapes_buildings VALUES (?,?,?,?,?)', buildings)
            conn.commit()
            msg = "[+] Buildings copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying buildings: %s" % e
            logger.error(msg)


        try:
            gates = alaqsdblite.query_string("SELECT * FROM shapes_gates;")
            curs.executemany('INSERT INTO shapes_gates VALUES (?,?,?,?,?,?)', gates)
            conn.commit()
            msg = "[+] Gates copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying gates: %s" % e
            logger.error(msg)


        try:
            parking = alaqsdblite.query_string("SELECT * FROM shapes_parking;")
            curs.executemany('INSERT INTO shapes_parking VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             parking)
            conn.commit()
            msg = "[+] Parkings copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying parking: %s" % e
            logger.error(msg)

        try:
            receptors = alaqsdblite.query_string("SELECT * FROM shapes_receptor_points;")
            curs.executemany('INSERT INTO shapes_receptor_points VALUES (?,?,?,?,?,?)', receptors)
            conn.commit()
            msg = "[+] Receptor points copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying receptor points: %s" % e
            logger.error(msg)

        # try:
        #     receptors = alaqsdblite.query_string("SELECT * FROM shapes_receptors;")
        #     curs.executemany('INSERT INTO shapes_receptors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', receptors)
        #     conn.commit()
        #     msg = "[+] Receptors copied to output file"
        #     logger.info(msg)
        #
        # except Exception as e:
        #     msg = "Problem copying receptors: %s" % e
        #     logger.error(msg)


        try:
            roadways = alaqsdblite.query_string("SELECT * FROM shapes_roadways;")
            curs.executemany('INSERT INTO shapes_roadways VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             roadways)
            conn.commit()
            msg = "[+] Roadways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying roadways: %s" % e
            logger.error(msg)


        try:
            runways = alaqsdblite.query_string("SELECT * FROM shapes_runways;")
            curs.executemany('INSERT INTO shapes_runways VALUES (?,?,?,?,?,?,?,?)', runways)
            conn.commit()
            msg = "[+] Runways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying runways: %s" % e
            logger.error(msg)


        try:
            point_sources = alaqsdblite.query_string("SELECT * FROM shapes_point_sources;")
            curs.executemany('INSERT INTO shapes_point_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             point_sources)
            conn.commit()
            msg = "[+] Point sources copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying point sources: %s" % e
            logger.error(msg)


        try:
            taxiways = alaqsdblite.query_string("SELECT * FROM shapes_taxiways;")
            curs.executemany('INSERT INTO shapes_taxiways VALUES (?,?,?,?,?,?)', taxiways)
            conn.commit()
            msg = "[+] Taxiways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying taxiways: %s" % e
            logger.error(msg)


        try:
            tracks = alaqsdblite.query_string("SELECT * FROM shapes_tracks;")
            curs.executemany('INSERT INTO shapes_tracks VALUES (?,?,?,?,?,?)', tracks)
            conn.commit()
            msg = "[+] Tracks copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying tracks: %s" % e
            logger.error(msg)


        msg = "[+] Copied all vector layers"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_activity_profiles.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg
    finally:
        conn.close()


def inventory_copy_aircraft(inventory_path):
    """
    We only need to take forward data on the aircraft that are in the movement
     table.
    :param inventory_path: the path of the inventory file being written to
    """
    try:
        # Establish a connection
        conn = sqlite.connect(inventory_path)
        conn.text_factory = str
        cur = conn.cursor()

        data = alaqsdblite.query_string("SELECT * FROM default_aircraft;")
        cur.executemany(
            'INSERT INTO default_aircraft VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            data)

        # movement_aircraft = alaqsdblite.query_string("SELECT DISTINCT aircraft FROM user_aircraft_movements;")
        ##for aircraft_name in movement_aircraft:
        #
        #    # Get details of this aircraft from the main project database
        #    sql_text = "SELECT * FROM default_aircraft WHERE icao=\"%s\";" % aircraft_name
        #    data = alaqsdblite.query_string(sql_text)
        #    # insert into the output
        #    curs.executemany('INSERT INTO default_aircraft VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', data)

        # House keeping
        conn.commit()
        conn.close()
        msg = "[+] Copied unique aircraft data"
        logger.info(msg)


    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_aircraft.__name__,
                                           Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_aircraft_engine_ei(inventory_path):
    """
    We only need to take forward data on the engine ei that are in the movement table.
    :param inventory_path: the path of the inventory file being written to
    """
    try:
        # Establish a connection
        conn = sqlite.connect(inventory_path)
        curs = conn.cursor()
        conn.text_factory = str
        # aircraft_engines = alaqsdblite.query_string("SELECT DISTINCT engine FROM default_aircraft;")

        # SS
        # aircraft_engines = alaqsdblite.query_string("SELECT DISTINCT engine FROM default_aircraft;")
        aircraft_engines = alaqsdblite.query_string("SELECT DISTINCT engine_name FROM default_aircraft_engine_ei;")

        for engine in aircraft_engines:
            # Get details of this aircraft from the main project database
            sql_text = "SELECT * FROM default_aircraft_engine_ei WHERE engine_name=\"%s\";" % engine
            data = alaqsdblite.query_string(sql_text)
            # insert into the output
            curs.executemany('INSERT INTO default_aircraft_engine_ei VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', data)
        # House keeping
        conn.commit()
        conn.close()

        msg = "[+] Copied unique aircraft engine data"
        logger.info(msg)

    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_aircraft_engine_ei.__name__, Exception, e)
        return error


def inventory_copy_aircraft_profiles(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        profiles = alaqsdblite.query_string("SELECT * FROM default_aircraft_profiles;")
        cur.executemany('INSERT INTO default_aircraft_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', profiles)
        conn.commit()
        conn.close()
        msg = "[+] Copied aircraft profiles"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_aircraft_profiles.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_aircraft_start_ef(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        start_ef = alaqsdblite.query_string("SELECT * FROM default_aircraft_start_ef;")
        cur.executemany('INSERT INTO default_aircraft_start_ef VALUES (?,?,?,?,?,?,?,?,?,?,?)', start_ef)
        conn.commit()
        conn.close()
        msg = "[+] Copied unique aircraft start emissions"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_aircraft_start_ef.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_stationary_substance(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        start_ef = alaqsdblite.query_string("SELECT * FROM default_stationary_substance;")
        cur.executemany('INSERT INTO default_stationary_substance VALUES (?,?,?)', start_ef)
        conn.commit()
        conn.close()
        msg = "[+] Copied stationary substances"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_stationary_substance.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_stationary_category(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        start_ef = alaqsdblite.query_string("SELECT * FROM default_stationary_category;")
        cur.executemany('INSERT INTO default_stationary_category VALUES (?,?,?)', start_ef)
        conn.commit()
        conn.close()
        msg = "[+] Copied stationary categories"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_stationary_category.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg


def inventory_copy_aircraft_engine_mode(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        start_ef = alaqsdblite.query_string("SELECT * FROM default_aircraft_engine_mode;")
        cur.executemany('INSERT INTO default_aircraft_engine_mode VALUES (?,?,?,?)', start_ef)
        conn.commit()
        conn.close()
        msg = "[+] Copied unique aircraft engine modes"
        logger.info(msg)

        return None
    except Exception as e:
        error_msg = alaqsutils.print_error(inventory_copy_aircraft_engine_mode.__name__, Exception, e)
        logger.error(error_msg)
        return error_msg
