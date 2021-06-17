#!bin/python
"""
Open ALAQS Application Layer

This script is the primary logic manager for the alaqs project. This script
contains all ALAQS core calculations and operations. Use of Open ALAQS in
any application is possible using functions in this file only - there should
be no need for any application to access the database layer at all.

While this module proves all core functionality for ALAQS calculations, no SQL
is included in this module - all SQL and default data is handled explicitly by
the database layer.

@author: Dan Pearce (it@env-isa.com)
"""
# the database layer of the ALAQS project
from open_alaqs.alaqs_core import alaqsdblite
# general utility functions
from open_alaqs.alaqs_core import alaqsutils
# Functions for creating a new ALAQS output file
from open_alaqs.alaqs_core import create_output


def create_project(database_name):
    """
    This function is used to create a new project database with all default
    tables completed. Initially, all user tables are blank and must be
    completed.

    :param: database_name : string name for the new project database
    :return: error : None if successful. Error message if not successful
    :raise: None
    """
    try:
        if database_name.strip() == "":
            raise Exception("database_name cannot be empty")
        else:
            result = alaqsdblite.create_project_database(database_name)
            if result is not None:
                error = "Problem from alaqsdblite.create_project_database(): %s" % result
                raise Exception(error)
            else:
                return None
    except Exception as e:
        error = alaqsutils.print_error(create_project.__name__, Exception, e)
        return error


def save_database_credentials(filepath):
    """
    This function is used to store the database credentials so that OpenALAQS can
    create ah hoc connections to the database.

    :param: filepath : string that details the path to the OpenALAQS database
    :return: error : None if successful. Error message if not successful
    :raise: None
    """
    try:
        result = alaqsdblite.save_database_credentials(db_name=filepath)
        if result is not None:
            error = "Problem saving database credentials: %s" % result
            raise Exception(error)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(save_database_credentials.__name__, Exception, e)
        return error


def query_text(sql_text):
    """
    This is a development query and will probably not be needed in a public release. The API for ALAQS should not have
    direct read/write access to the database.
    :param sql_text: the sql text to be executed
    :return result: the result of the query
    """
    try:
        result = alaqsdblite.query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(save_database_credentials.__name__, Exception, e)
        return error


#############################################
########       STUDY SETUP           ########
#############################################


def load_study_setup():
    """
    This function will load the login credentials for the Spatialite database
    to be used for a specific Open ALAQS study.

    :return: result : None if successful. Error message if not successful
    :raise: None
    """
    try:
        study_data = alaqsdblite.get_study_setup()

        if study_data is []:
            return None
        else:
            return study_data
    except Exception as e:
        error = alaqsutils.print_error(load_study_setup.__name__, Exception, e)
        return error


def load_study_setup_dict():
    """
    This function will load the login credentials for the SQLITE database
    to be used for a specific Open ALAQS study.

    :return: result : None if successful. Error message if not successful
    :raise: None
    """
    try:
        study_data = alaqsdblite.get_study_setup()
        study_data_dict = alaqsutils.dict_study_setup(study_data[0])
        return study_data_dict
    except Exception as e:
        error = alaqsutils.print_error(load_study_setup.__name__, Exception, e)
        return error


def save_study_setup(study_setup):
    """
    This function updates the study setup table in the currently OpenALAQS
    database.

    :param: study_setup : a list containing all values from the study_setup UI
    :return: error : None if successful. Error message if not successful
    :raises: None
    """
    try:
        if len(study_setup) != 15:
            raise Exception("Incorrect number of study parameters supplied. %d provided - 15 needed" % len(study_setup))
        for param in study_setup:
            if param == "":
                raise Exception("Study setup parameters cannot be blank")
        result = alaqsdblite.save_study_setup(study_setup)
        if result is None:
            return None
        else:
            raise Exception("Study setup could not be saved: %s" % result)
    except Exception as e:
        error = alaqsutils.print_error(save_study_setup.__name__, Exception, e)
        return error


def save_study_setup_dict(study_setup):
    """
    This function updates the study setup table in the currently OpenALAQS database

    :param: study_setup : a list containing all values from the study_setup UI
    :return: error : None if successful. Error message if not successful
    :raises: None
    """
    try:
        if len(study_setup) != 19:
            raise Exception("Incorrect number of study parameters supplied. %d provided - 20 needed" % len(study_setup))
        for param in study_setup:
            if param == "":
                raise Exception("Study setup parameters cannot be blank")
        result = alaqsdblite.save_study_setup_dict(study_setup)
        if result is None:
            return None
        else:
            raise Exception("Study setup could not be saved: %s" % result)
    except Exception as e:
        error = alaqsutils.print_error(save_study_setup.__name__, Exception, e)
        return error


def airport_lookup(airport_code):
    """
    Look up an airport based on its ICAO name and return data if available
    :param airport_code: the ICAO code of the airport being looked up
    """
    try:
        result = alaqsdblite.airport_lookup(airport_code)
        if result is None or result == []:
            return None
        elif isinstance(result, str):
            raise Exception("Airport lookup failed: %s" % result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(airport_lookup.__name__, Exception, e)
        return error


def airport_lookup_dict(airport_code):
    """
    Look up an airport based on its ICAO name and return data if available
    :param airport_code: the ICAO code of the airport being looked up
    """
    try:
        result = alaqsdblite.airport_lookup(airport_code)
        if result is None or result == []:
            return None
        elif isinstance(result, str):
            raise Exception("Airport lookup failed: %s" % result)
        else:
            return alaqsutils.dict_airport_data(result[0])
    except Exception as e:
        error = alaqsutils.print_error(airport_lookup.__name__, Exception, e)
        return error


#############################################
########          ROADWAYS           ########
#############################################


def new_roadway_dict():
    roadway_dict = dict()
    roadway_dict['roadway_id'] = "Not set"
    roadway_dict['roadway_vehicle_year'] = "2000"
    roadway_dict['roadway_speed'] = 140
    roadway_dict['roadway_distance'] = 0
    roadway_dict['roadway_height'] = 0
    roadway_dict['roadway_vehicle_light'] = 50
    roadway_dict['roadway_vehicle_medium'] = 25
    roadway_dict['roadway_vehicle_heavy'] = 25
    roadway_dict['roadway_hour_profile'] = "default"
    roadway_dict['roadway_daily_profile'] = "default"
    roadway_dict['roadway_month_profile'] = "default"
    roadway_dict['roadway_co_gm_km'] = 0
    roadway_dict['roadway_hc_gm_km'] = 0
    roadway_dict['roadway_nox_gm_km'] = 0
    roadway_dict['roadway_sox_gm_km'] = 0
    roadway_dict['roadway_pm10_gm_km'] = 0
    roadway_dict['roadway_p1_gm_km'] = 0
    roadway_dict['roadway_p2_gm_km'] = 0
    roadway_dict['roadway_method'] = "DEFAULT"
    roadway_dict['roadway_instudy'] = 1
    roadway_dict['roadway_scenario'] = "Not applicable"
    roadway_dict['roadway_wkt'] = 'LINESTRING (0 0, 2 2)'
    return roadway_dict


def add_roadway_dict(roadway_dict):
    try:
        result = alaqsdblite.add_roadway_dict(roadway_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_roadway_dict.__name__, Exception, e)
        return error


def get_roadway_methods():
    """
    Get a list of available roadway methods from the database
    """
    try:
        result = alaqsdblite.get_roadway_methods()
        if result is not None:
            return result
        else:
            raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_methods.__name__, Exception, e)
        return error


def get_roadway_countries():
    """
    Get a list of countries available for roadway modelling
    """
    try:
        result = alaqsdblite.get_roadway_countries()
        if result is not None:
            return result
        else:
            raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_countries.__name__, Exception, e)
        return error


def get_roadway_fleet_years():
    """
    Get a list of years available for roadway modelling
    """
    try:
        result = alaqsdblite.get_roadway_years()
        if result is not None:
            return result
        else:
            raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_fleet_years.__name__, Exception, e)
        return error

#############################################
########            GATES            ########
#############################################

def new_gate_dict():
    gate_dict = dict()
    gate_dict['gate_id'] = "Not set"
    gate_dict['gate_type'] = "Remote"
    gate_dict['gate_height'] = 0
    gate_dict['gate_instudy'] = 1
    gate_dict['gate_wkt'] = 'POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))'
    return gate_dict

def add_gate_dict(gate_dict):
    try:
        result = alaqsdblite.add_gate_dict(gate_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_gate_dict.__name__, Exception, e)
        return error


def get_gate(gate_name):
    """
    Get data on a specific gate based on the gate name.
    """
    try:
        result = alaqsdblite.get_gate(gate_name)
        if isinstance(result, str):
            raise Exception("Gate could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_gate.__name__, Exception, e)
        return error


def get_gates():
    """
    Return data on all gates defined in the currently active alaqs study
    """
    try:
        result = alaqsdblite.get_gates()
        if isinstance(result, str):
            raise Exception("Gates could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_gates.__name__, Exception, e)
        return error


#############################################
########          RUNWAYS            ########
#############################################


def new_runway_dict():
    runway_dict = dict()
    runway_dict['runway_id'] = "Not set"
    runway_dict['runway_capacity'] = 60
    runway_dict['runway_touchdown'] = 150
    runway_dict['runway_max_queue_speed'] = 10
    runway_dict['runway_peak_queue_time'] = 10
    runway_dict['runway_instudy'] = 1
    runway_dict['runway_wkt'] = 'LINESTRING (0 3, 1 3)'
    return runway_dict


def add_runway_dict(runway_dict):
    try:
        result = alaqsdblite.add_runway_dict(runway_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_runway_dict.__name__, Exception, e)
        return error


def get_runway(runway_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_runway(runway_id)
        if isinstance(result, str):
            raise Exception("Runway could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_runway.__name__, Exception, e)
        return error


def get_runways():
    """
    Description
    """
    try:
        result = alaqsdblite.get_runways()
        if isinstance(result, str):
            raise Exception("Runways could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_runways.__name__, Exception, e)
        return error


#############################################
########          TAXIWAYS           ########
#############################################


def new_taxiway_dict():
    taxiway_dict = dict()
    taxiway_dict['taxiway_id'] = "Not set"
    taxiway_dict['taxiway_speed'] = 10
    taxiway_dict['taxiway_time'] = 10
    taxiway_dict['taxiway_instudy'] = 1
    taxiway_dict['taxiway_wkt'] = 'LINESTRING (2 2, 3 3)'
    return taxiway_dict


def add_taxiway_dict(taxiway_dict):
    try:
        result = alaqsdblite.add_taxiway_dict(taxiway_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_taxiway_dict.__name__, Exception, e)
        return error


def get_taxiway(taxiway_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_taxiway(taxiway_id)
        if isinstance(result, str):
            raise Exception("Taxiway could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway.__name__, Exception, e)
        return error


def get_taxiways():
    """
    Description
    """
    try:
        result = alaqsdblite.get_taxiways()
        if isinstance(result, str):
            raise Exception("Taxiways could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiways.__name__, Exception, e)
        return error


#############################################
########      TAXIWAY ROUTES         ########
#############################################


def delete_taxiway_route(taxi_route_name):
    try:
        result = alaqsdblite.delete_taxiway_route(taxi_route_name)
        if isinstance(result, str):
            raise Exception(result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(delete_taxiway_route.__name__, Exception, e)
        return error


def get_taxiway_route(taxiway_route_name):
    try:
        result = alaqsdblite.get_taxiway_route(taxiway_route_name)
        if isinstance(result, str):
            raise Exception(result)
        elif result is None or result == []:
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception, e)
        return error


def get_taxiway_routes():
    try:
        result = alaqsdblite.get_taxiway_routes()
        if isinstance(result, str):
            raise Exception(result)
        elif result is None or result == []:
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception, e)
        return error


def add_taxiway_route(taxiway_route):
    try:
        result = alaqsdblite.add_taxiway_route(taxiway_route)
        if result is not None:
            raise Exception(result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(add_taxiway_route.__name__, Exception, e)
        return error


#############################################
########            TRACKS           ########
#############################################


def get_track(track_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_track(track_id)
        if isinstance(result, str):
            raise Exception("Track could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_track.__name__, Exception, e)
        return error


def get_tracks():
    """
    Description
    """
    try:
        result = alaqsdblite.get_tracks()
        if isinstance(result, str):
            raise Exception("Tracks could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_tracks.__name__, Exception, e)
        return error


#############################################
########     STATIONARY SOURCES      ########
#############################################


def new_point_source():
    """
    This function returns a blank dictionary in the correct format for create a new point source. This is not used when
    ALAQS is being used as a QGIS plugin, but is used when Open ALAQS is being used as a python module. Being able to
    create a correctly formatted point source object on demand simplifies the creation of new sources

    :return: a dict that describes a blank point source
    """
    point_source_dict = dict()
    point_source_dict['source_id'] = "Not set"
    point_source_dict['source_height'] = 5
    point_source_dict['source_category'] = "Fuel Tank"
    point_source_dict['source_type'] = "Fuel Oil/Diesel"
    point_source_dict['source_substance'] = "Liquid"
    point_source_dict['source_temperature'] = 50
    point_source_dict['source_diameter'] = 1
    point_source_dict['source_velocity'] = 4
    point_source_dict['source_ops_year'] = 0
    point_source_dict['source_hour_profile'] = "default"
    point_source_dict['source_daily_profile'] = "default"
    point_source_dict['source_monthly_profile'] = "default"
    point_source_dict['source_co_kg_k'] = 0
    point_source_dict['source_hc_kg_k'] = 0
    point_source_dict['source_nox_kg_k'] = 0
    point_source_dict['source_sox_kg_k'] = 0
    point_source_dict['source_pm10_kg_k'] = 0
    point_source_dict['source_p1_kg_k'] = 0
    point_source_dict['source_p2_kg_k'] = 0
    point_source_dict['source_instudy'] = 0
    point_source_dict['source_wkt'] = 'POINT (0 0)'
    return point_source_dict


def add_point_source(point_source_dict):
    """
    This function is used to add a new point source to the currently active database. This is used only when the tool
    is being used independently of QGIS
    :param point_source_dict: a dictionary of stationary source properties
    :return: Should be True if successful
    """
    try:
        result = alaqsdblite.add_point_source(point_source_dict)
        if result is None:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_point_source.__name__, Exception, e)
        return error


def get_point_source(source_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_source(source_id)
        if isinstance(result, str):
            raise Exception("Stationary source could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_source.__name__, Exception, e)
        return error


def get_point_sources():
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_sources()
        if isinstance(result, str):
            raise Exception("Sources could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_sources.__name__, Exception, e)
        return error


def get_point_category(category_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_category(category_id)
        if isinstance(result, str):
            raise Exception("Stationary category could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_category.__name__, Exception, e)
        return error


def get_point_categories():
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_categories()
        if isinstance(result, str):
            raise Exception("Source categories could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_categories.__name__, Exception, e)
        return error


def get_point_type(type_name):
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_type(type_name)
        if isinstance(result, str):
            raise Exception("Type details could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_type.__name__, Exception, e)
        return error


def get_point_types(category_number):
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_types(category_number)
        if isinstance(result, str):
            raise Exception("Category types could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_types.__name__, Exception, e)
        return error


#############################################
########          BUILDINGS          ########
#############################################


def new_building():
    """
    This function returns a blank dictionary in the correct format for create a new building. This is not used when
    ALAQS is being used as a QGIS plugin, but is used when Open ALAQS is being used as a python module. Being able to
    create a correctly formatted point source object on demand simplifies the creation of new sources

    :return: a dict that describes a blank building
    """
    building_dict = dict()
    building_dict['building_id'] = "Not set"
    building_dict['building_height'] = 10
    building_dict['building_instudy'] = 1
    building_dict['building_wkt'] = 'POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))'
    return building_dict


def add_building(building_dict):
    """"
    This function is used to add a new building to the currently active database. This is used only when the tool is
    being used independently of QGIS
    :param building_dict: a dictionary of building properties in format defined by new_building()
    :return: True if successful
    """
    try:
        result = alaqsdblite.add_building(building_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_building.__name__, Exception, e)
        return error


def get_building(building_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_building(building_id)
        if isinstance(result, str):
            raise Exception("Building could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_building.__name__, Exception, e)
        return error


def get_buildings():
    """
    Description
    """
    try:
        result = alaqsdblite.get_buildings()
        if isinstance(result, str):
            raise Exception("Buildings could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_buildings.__name__, Exception, e)
        return error


#############################################
########          PARKINGS          ########
#############################################


def new_parking():
    """
    This function returns a blank dictionary in the correct format for create a new parking. This is not used when
    ALAQS is being used as a QGIS plugin, but is used when Open ALAQS is being used as a python module. Being able to
    create a correctly formatted point source object on demand simplifies the creation of new sources

    :return: a dict that describes a blank parking
    """
    parking_dict = dict()
    parking_dict['parking_id'] = "Not set"
    parking_dict['parking_height'] = 0
    parking_dict['parking_distance'] = 0
    parking_dict['parking_idle_time'] = 0
    parking_dict['parking_park_time'] = 0
    parking_dict['parking_vehicle_light'] = 50
    parking_dict['parking_vehicle_medium'] = 25
    parking_dict['parking_vehicle_heavy'] = 25
    parking_dict['parking_vehicle_year'] = 0
    parking_dict['parking_speed'] = 0
    parking_dict['parking_hour_profile'] = "default"
    parking_dict['parking_daily_profile'] = "default"
    parking_dict['parking_month_profile'] = "default"
    parking_dict['parking_co_gm_vh'] = 0
    parking_dict['parking_hc_gm_vh'] = 0
    parking_dict['parking_nox_gm_vh'] = 0
    parking_dict['parking_sox_gm_vh'] = 0
    parking_dict['parking_pm10_gm_vh'] = 0
    parking_dict['parking_p1_gm_vh'] = 0
    parking_dict['parking_p2_gm_vh'] = 0
    parking_dict['parking_method'] = "DEFAULT"
    parking_dict['parking_instudy'] = 1
    parking_dict['parking_wkt'] = 'POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))'
    return parking_dict


def add_parking(parking_dict):
    """"
    This function is used to add a new building to the currently active database. This is used only when the tool is
    being used independently of QGIS
    :param parking_dict: a dictionary of building properties in format defined by new_building()
    :return: True if successful
    """
    try:
        result = alaqsdblite.add_parking(parking_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_parking.__name__, Exception, e)
        return error


def get_parking(parking_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_parking(parking_id)
        if isinstance(result, str):
            raise Exception("Parking could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_parking.__name__, Exception, e)
        return error


def get_parkings():
    """
    Description
    """
    try:
        result = alaqsdblite.get_parkings()
        if isinstance(result, str):
            raise Exception("Parkings could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_parkings.__name__, Exception, e)
        return error


#############################################
########          PROFILES           ########
#############################################


def new_hourly_profile_dict():
    hourly_profile_dict = dict()
    hourly_profile_dict['name'] = "Not set"
    hourly_profile_dict['h00'] = 1
    hourly_profile_dict['h01'] = 1
    hourly_profile_dict['h02'] = 1
    hourly_profile_dict['h03'] = 1
    hourly_profile_dict['h04'] = 1
    hourly_profile_dict['h05'] = 1
    hourly_profile_dict['h06'] = 1
    hourly_profile_dict['h07'] = 1
    hourly_profile_dict['h08'] = 1
    hourly_profile_dict['h09'] = 1
    hourly_profile_dict['h10'] = 1
    hourly_profile_dict['h11'] = 1
    hourly_profile_dict['h12'] = 1
    hourly_profile_dict['h13'] = 1
    hourly_profile_dict['h14'] = 1
    hourly_profile_dict['h15'] = 1
    hourly_profile_dict['h16'] = 1
    hourly_profile_dict['h17'] = 1
    hourly_profile_dict['h18'] = 1
    hourly_profile_dict['h19'] = 1
    hourly_profile_dict['h20'] = 1
    hourly_profile_dict['h21'] = 1
    hourly_profile_dict['h22'] = 1
    hourly_profile_dict['h23'] = 1
    return hourly_profile_dict


def new_daily_profile_dict():
    daily_profile_dict = dict()
    daily_profile_dict['name'] = "Not set"
    daily_profile_dict['mon'] = 1
    daily_profile_dict['tue'] = 1
    daily_profile_dict['wed'] = 1
    daily_profile_dict['thu'] = 1
    daily_profile_dict['fri'] = 1
    daily_profile_dict['sat'] = 1
    daily_profile_dict['sun'] = 1
    return daily_profile_dict


def new_monthly_profile_dict():
    monthly_profile_dict = dict()
    monthly_profile_dict['name'] = "Not set"
    monthly_profile_dict['jan'] = 1
    monthly_profile_dict['feb'] = 1
    monthly_profile_dict['mar'] = 1
    monthly_profile_dict['apr'] = 1
    monthly_profile_dict['may'] = 1
    monthly_profile_dict['jun'] = 1
    monthly_profile_dict['jul'] = 1
    monthly_profile_dict['aug'] = 1
    monthly_profile_dict['sep'] = 1
    monthly_profile_dict['oct'] = 1
    monthly_profile_dict['nov'] = 1
    monthly_profile_dict['dec'] = 1
    return monthly_profile_dict


def add_hourly_profile_dict(hourly_profile_dict):
    try:
        result = alaqsdblite.add_hourly_profile_dict(hourly_profile_dict)
        if result is not True:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception, e)
        return error


def add_daily_profile_dict(daily_profile_dict):
    try:
        result = alaqsdblite.add_daily_profile_dict(daily_profile_dict)
        if result is None or result == []:
            raise Exception(result)
        else:
            return True
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception, e)
        return error


def add_monthly_profile_dict(monthly_profile_dict):
    try:
        result = alaqsdblite.add_monthly_profile_dict(monthly_profile_dict)
        if result is None or result == []:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(add_daily_profile.__name__, Exception, e)
        return error


def get_hourly_profiles():
    """
    Description
    """
    try:
        result = alaqsdblite.get_hourly_profiles()
        if isinstance(result, str):
            raise Exception("Hourly profiles could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profiles.__name__, Exception, e)
        return error


def get_daily_profiles():
    """
    Description
    """
    try:
        result = alaqsdblite.get_daily_profiles()
        if isinstance(result, str):
            raise Exception("Daily profiles could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profiles.__name__, Exception, e)
        return error


def get_monthly_profiles():
    """
    Description
    """
    try:
        result = alaqsdblite.get_monthly_profiles()
        if isinstance(result, str):
            raise Exception("Daily profiles could not be returned: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profiles.__name__, Exception, e)
        return error


def get_hourly_profile(profile_name):
    try:
        if profile_name == "" or profile_name == [] or profile_name is None or profile_name == "New Profile":
            return None
        result = alaqsdblite.get_hourly_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Hour profile could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profile.__name__, Exception, e)
        return error


def get_daily_profile(profile_name):
    try:
        if profile_name == "" or profile_name == [] or profile_name is None or profile_name == "New Profile":
            return None
        result = alaqsdblite.get_daily_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Day profile could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profile.__name__, Exception, e)
        return error


def get_monthly_profile(profile_name):
    try:
        if profile_name == "" or profile_name == [] or profile_name is None or profile_name == "New Profile":
            return None
        result = alaqsdblite.get_monthly_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Month profile could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profile.__name__, Exception, e)
        return error


def delete_hourly_profile(profile_name):
    try:
        result = alaqsdblite.delete_hourly_profile(profile_name)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(delete_hourly_profile.__name__, Exception, e)
        return error


def delete_daily_profile(profile_name):
    try:
        result = alaqsdblite.delete_daily_profile(profile_name)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(delete_daily_profile.__name__, Exception, e)
        return error


def delete_monthly_profile(profile_name):
    try:
        result = alaqsdblite.delete_monthly_profile(profile_name)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(delete_monthly_profile.__name__, Exception, e)
        return error


def add_hourly_profile(properties):
    try:
        result = alaqsdblite.add_hourly_profile(properties)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception, e)
        return error


def add_daily_profile(properties):
    try:
        result = alaqsdblite.add_daily_profile(properties)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception, e)
        return error


def add_monthly_profile(properties):
    try:
        result = alaqsdblite.add_monthly_profile(properties)
        if result is not None:
            raise Exception(result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(add_daily_profile.__name__, Exception, e)
        return error


def get_lasport_scenarios():
    """

    """
    try:
        result = alaqsdblite.get_lasport_scenarios()
        if isinstance(result, str):
            raise Exception("Lasport scenarios could not be found: %s" % result)
        elif (result == []) or (result is None):
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_lasport_scenarios.__name__, Exception, e)
        return error


#############################################
########       BUILD INVENTORY       ########
#############################################

def inventory_creation_new(inventory_path, model_parameters, study_setup, met_csv_path=""):
    try:
        result = create_output.create_alaqs_output(inventory_path, model_parameters, study_setup, met_csv_path=met_csv_path)
        return result
    except Exception as e:
        error = alaqsutils.print_error(inventory_creation_new.__name__, Exception, e)
        return error


def inventory_source_list(inventory_path, source_type):
    try:
        source_list = alaqsdblite.inventory_source_list(inventory_path, source_type)
        if isinstance(source_list, str):
            raise Exception(source_list)
        else:
            return source_list
    except Exception as e:
        error = alaqsutils.print_error(inventory_source_list.__name__, Exception, e)
        return error


def inventory_copy_study_setup(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_study_setup(inventory_path)
        if result is not None:
            raise Exception("Study setup could not be copied to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_study_setup.__name__, Exception, e)
        return error


def inventory_copy_gate_profiles(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_gate_profiles(inventory_path)
        if result is not None:
            raise Exception("Gate profiles could not be copied to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_gate_profiles.__name__, Exception, e)
        return error


def inventory_copy_emission_dynamics(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_emission_dynamics(inventory_path)
        if result is not None:
            raise Exception("Emission dynamics could not be copied to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_emission_dynamics.__name__, Exception, e)
        return error

def inventory_insert_movements(inventory_path, movement_path):
    """
    Thin layer to pass off the creation of a new ALAQS output database to the database layer.

    :param inventory_path: the path of the output to be created [string]
    :param movement_path: the path of the movement file to be worked with
    """
    try:
        result = alaqsdblite.inventory_insert_movements(inventory_path, movement_path)
        if result is not None:
            raise Exception("Movements could not be added to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_insert_movements.__name__, Exception, e)
        return error


def inventory_copy_activity_profiles(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_activity_profiles(inventory_path)
        if result is not None:
            raise Exception("Activity profiles could not be copied to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_activity_profiles.__name__, Exception, e)
        return error


def inventory_copy_vector_layers(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_vector_layers(inventory_path)
        if result is not None:
            raise Exception("Vector could not be copied to ALAQS output file: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_vector_layers.__name__, Exception, e)
        return error


def inventory_copy_raster_layers(inventory_path):
    return inventory_path