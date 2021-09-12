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

from open_alaqs.alaqs_core import alaqsdblite
from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools.create_output import create_alaqs_output

logger = get_logger(__name__)


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

        result = alaqsdblite.create_project_database(database_name)
        if result is not None:
            error = f"Problem from alaqsdblite.create_project_database():" \
                    f" {result}"
            raise Exception(error)

        return None

    except Exception as e:
        error = alaqsutils.print_error(create_project.__name__, Exception, e)
        return error


# ##########################
# ###### STUDY SETUP #######
# ##########################


def load_study_setup():
    """
    This function will load the login credentials for the Spatialite database
    to be used for a specific Open ALAQS study.

    :return: result : None if successful. Error message if not successful
    :raise: None
    """
    try:
        study_data = alaqsdblite.get_study_setup()

        if not study_data:
            return None

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
        error = alaqsutils.print_error(load_study_setup.__name__, Exception, e, log=logger)
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
            raise Exception(f"Incorrect number of study parameters supplied. "
                            f"{len(study_setup)} provided - 15 needed")
        for param in study_setup:
            if param == "":
                raise Exception("Study setup parameters cannot be blank")
        result = alaqsdblite.save_study_setup(study_setup)
        if result is None:
            return None

        raise Exception("Study setup could not be saved: %s" % result)
    except Exception as e:
        error = alaqsutils.print_error(save_study_setup.__name__, Exception, e)
        return error


def save_study_setup_dict(study_setup):
    """
    This function updates the study setup table in the currently OpenALAQS
     database.

    :param: study_setup : a list containing all values from the study_setup UI
    :return: error : None if successful. Error message if not successful
    :raises: None
    """
    try:
        if len(study_setup) != 19:
            raise Exception("Incorrect number of study parameters supplied. "
                            "%d provided - 20 needed" % len(study_setup))
        for param in study_setup:
            if param == "":
                raise Exception("Study setup parameters cannot be blank")
        result = alaqsdblite.save_study_setup_dict(study_setup)
        if result is None:
            return None
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
        if isinstance(result, str):
            raise Exception("Airport lookup failed: %s" % result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(airport_lookup.__name__, Exception, e)
        return error


# ######################
# ###### ROADWAYS ######
# ######################


def add_roadway_dict(roadway_dict):
    try:
        result = alaqsdblite.add_roadway_dict(roadway_dict)
        if result is not True:
            raise Exception(result)
        return result
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
        raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_methods.__name__, Exception,
                                       e)
        return error


def get_roadway_countries():
    """
    Get a list of countries available for roadway modelling
    """
    try:
        result = alaqsdblite.get_roadway_countries()
        if result is not None:
            return result
        raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_countries.__name__,
                                       Exception, e)
        return error


def get_roadway_fleet_years():
    """
    Get a list of years available for roadway modelling
    """
    try:
        result = alaqsdblite.get_roadway_years()
        if result is not None:
            return result
        raise Exception("No roadway methods were returned from this database")
    except Exception as e:
        error = alaqsutils.print_error(get_roadway_fleet_years.__name__,
                                       Exception, e)
        return error


# ###################
# ###### GATES ######
# ###################


def add_gate_dict(gate_dict):
    try:
        result = alaqsdblite.add_gate_dict(gate_dict)
        if result is not True:
            raise Exception(result)
        return result
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_gates.__name__, Exception, e)
        return error


# #####################
# ###### RUNWAYS ######
# #####################


def add_runway_dict(runway_dict):
    try:
        result = alaqsdblite.add_runway_dict(runway_dict)
        if result is not True:
            raise Exception(result)
        return result
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_runways.__name__, Exception, e)
        return error


# ######################
# ###### TAXIWAYS ######
# ######################


def add_taxiway_dict(taxiway_dict):
    try:
        result = alaqsdblite.add_taxiway_dict(taxiway_dict)
        if result is not True:
            raise Exception(result)
        return result
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiways.__name__, Exception, e)
        return error


# ############################
# ###### TAXIWAY ROUTES ######
# ############################


def delete_taxiway_route(taxi_route_name):
    try:
        result = alaqsdblite.delete_taxiway_route(taxi_route_name)
        if isinstance(result, str):
            raise Exception(result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(delete_taxiway_route.__name__, Exception,
                                       e)
        return error


def get_taxiway_route(taxiway_route_name):
    try:
        result = alaqsdblite.get_taxiway_route(taxiway_route_name)
        if isinstance(result, str):
            raise Exception(result)
        if result is None or result == []:
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception,
                                       e)
        return error


def get_taxiway_routes():
    try:
        result = alaqsdblite.get_taxiway_routes()
        if isinstance(result, str):
            raise Exception(result)
        if result is None or result == []:
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception,
                                       e)
        return error


def add_taxiway_route(taxiway_route):
    try:
        result = alaqsdblite.add_taxiway_route(taxiway_route)
        if result is not None:
            raise Exception(result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(add_taxiway_route.__name__, Exception, e)
        return error


#  ####################
#  ###### TRACKS ######
#  ####################


def get_track(track_id):
    """
    Description
    """
    try:
        result = alaqsdblite.get_track(track_id)
        if isinstance(result, str):
            raise Exception("Track could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_tracks.__name__, Exception, e)
        return error


# ################################
# ###### STATIONARY SOURCES ######
# ################################


def add_point_source(point_source_dict):
    """
    This function is used to add a new point source to the currently active
     database. This is used only when the tool is being used independently of
     QGIS.

    :param point_source_dict: a dictionary of stationary source properties
    :return: Should be True if successful
    """
    try:
        result = alaqsdblite.add_point_source(point_source_dict)
        if result is None:
            raise Exception(result)
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
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
            raise Exception(
                "Stationary category could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_category.__name__, Exception,
                                       e)
        return error


def get_point_categories():
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_categories()
        if isinstance(result, str):
            raise Exception(
                "Source categories could not be returned: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_categories.__name__, Exception,
                                       e)
        return error


def get_point_type(type_name):
    """
    Description
    """
    try:
        result = alaqsdblite.get_point_type(type_name)
        if isinstance(result, str):
            raise Exception("Type details could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_types.__name__, Exception, e)
        return error


# #######################
# ###### BUILDINGS ######
# #######################


def add_building(building_dict):
    """"
    This function is used to add a new building to the currently active
     database. This is used only when the tool is being used independently of
     QGIS.

    :param building_dict: a dictionary of building properties in format defined
     by new_building()
    :return: True if successful
    """
    try:
        result = alaqsdblite.add_building(building_dict)
        if result is not True:
            raise Exception(result)
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_buildings.__name__, Exception, e)
        return error


# ######################
# ###### PARKINGS ######
# ######################


def add_parking(parking_dict):
    """"
    This function is used to add a new building to the currently active
     database. This is used only when the tool is being used independently of
     QGIS.
    :param parking_dict: a dictionary of building properties in format defined
     by new_building()
    :return: True if successful
    """
    try:
        result = alaqsdblite.add_parking(parking_dict)
        if result is not True:
            raise Exception(result)
        return result
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
        if (result == []) or (result is None):
            return None
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
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_parkings.__name__, Exception, e)
        return error


# ######################
# ###### PROFILES ######
# ######################


def add_hourly_profile_dict(hourly_profile_dict):
    try:
        result = alaqsdblite.add_hourly_profile_dict(hourly_profile_dict)
        if result is not True:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception,
                                       e)
        return error


def add_daily_profile_dict(daily_profile_dict):
    try:
        result = alaqsdblite.add_daily_profile_dict(daily_profile_dict)
        if result is None or result == []:
            raise Exception(result)
        return True
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception,
                                       e)
        return error


def add_monthly_profile_dict(monthly_profile_dict):
    try:
        result = alaqsdblite.add_monthly_profile_dict(monthly_profile_dict)
        if result is None or result == []:
            raise Exception(result)
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
            raise Exception(
                "Hourly profiles could not be returned: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profiles.__name__, Exception,
                                       e)
        return error


def get_daily_profiles():
    """
    Description
    """
    try:
        result = alaqsdblite.get_daily_profiles()
        if isinstance(result, str):
            raise Exception("Daily profiles could not be returned: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profiles.__name__, Exception,
                                       e)
        return error


def get_monthly_profiles():
    """
    Description
    """
    try:
        result = alaqsdblite.get_monthly_profiles()
        if isinstance(result, str):
            raise Exception("Daily profiles could not be returned: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profiles.__name__, Exception,
                                       e)
        return error


def get_hourly_profile(profile_name):
    try:
        if (profile_name == "") or (profile_name == []) or \
                (profile_name is None) or (profile_name == "New Profile"):
            return None
        result = alaqsdblite.get_hourly_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Hour profile could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profile.__name__, Exception,
                                       e)
        return error


def get_daily_profile(profile_name):
    try:
        if (profile_name == "") or (profile_name == []) or \
                (profile_name is None) or (profile_name == "New Profile"):
            return None
        result = alaqsdblite.get_daily_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Day profile could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profile.__name__, Exception, e)
        return error


def get_monthly_profile(profile_name):
    try:
        if (profile_name == "") or (profile_name == []) or \
                (profile_name is None) or (profile_name == "New Profile"):
            return None
        result = alaqsdblite.get_monthly_profile(profile_name)
        if isinstance(result, str):
            raise Exception("Month profile could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profile.__name__, Exception,
                                       e)
        return error


def delete_hourly_profile(profile_name):
    try:
        result = alaqsdblite.delete_hourly_profile(profile_name)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(delete_hourly_profile.__name__,
                                       Exception, e)
        return error


def delete_daily_profile(profile_name):
    try:
        result = alaqsdblite.delete_daily_profile(profile_name)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(delete_daily_profile.__name__, Exception,
                                       e)
        return error


def delete_monthly_profile(profile_name):
    try:
        result = alaqsdblite.delete_monthly_profile(profile_name)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(delete_monthly_profile.__name__,
                                       Exception, e)
        return error


def add_hourly_profile(properties):
    try:
        result = alaqsdblite.add_hourly_profile(properties)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception,
                                       e)
        return error


def add_daily_profile(properties):
    try:
        result = alaqsdblite.add_daily_profile(properties)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception,
                                       e)
        return error


def add_monthly_profile(properties):
    try:
        result = alaqsdblite.add_monthly_profile(properties)
        if result is not None:
            raise Exception(result)
        return result
    except Exception as e:
        error = alaqsutils.print_error(add_daily_profile.__name__, Exception, e)
        return error


def get_lasport_scenarios():
    try:
        result = alaqsdblite.get_lasport_scenarios()
        if isinstance(result, str):
            raise Exception("Lasport scenarios could not be found: %s" % result)
        if (result == []) or (result is None):
            return None
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_lasport_scenarios.__name__,
                                       Exception, e)
        return error


# #############################
# ###### BUILD INVENTORY ######
# #############################


def inventory_creation_new(inventory_path, model_parameters, study_setup,
                           met_csv_path=""):
    try:
        result = create_alaqs_output(inventory_path, model_parameters,
                                     study_setup, met_csv_path=met_csv_path)
        return result
    except Exception as e:
        error = alaqsutils.print_error(inventory_creation_new.__name__,
                                       Exception, e)
        return error


def inventory_source_list(inventory_path, source_type):
    try:
        source_list = alaqsdblite.inventory_source_list(inventory_path,
                                                        source_type)
        if isinstance(source_list, str):
            raise Exception(source_list)
        return source_list
    except Exception as e:
        error = alaqsutils.print_error(inventory_source_list.__name__,
                                       Exception, e)
        return error


def inventory_copy_study_setup(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_study_setup(inventory_path)
        if result is not None:
            raise Exception("Study setup could not be copied to ALAQS output "
                            "file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_study_setup.__name__,
                                       Exception, e)
        return error


def inventory_copy_gate_profiles(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_gate_profiles(inventory_path)
        if result is not None:
            raise Exception("Gate profiles could not be copied to ALAQS output "
                            "file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_gate_profiles.__name__,
                                       Exception, e)
        return error


def inventory_copy_emission_dynamics(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_emission_dynamics(inventory_path)
        if result is not None:
            raise Exception(
                "Emission dynamics could not be copied to ALAQS output "
                "file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(
            inventory_copy_emission_dynamics.__name__, Exception, e)
        return error


def inventory_insert_movements(inventory_path, movement_path):
    """
    Thin layer to pass off the creation of a new ALAQS output database to the
     database layer.

    :param inventory_path: the path of the output to be created [string]
    :param movement_path: the path of the movement file to be worked with
    """
    try:
        result = alaqsdblite.inventory_insert_movements(inventory_path,
                                                        movement_path)
        if result is not None:
            raise Exception("Movements could not be added to ALAQS output "
                            "file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_insert_movements.__name__,
                                       Exception, e)
        return error


def inventory_copy_activity_profiles(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_activity_profiles(inventory_path)
        if result is not None:
            raise Exception(
                "Activity profiles could not be copied to ALAQS output "
                "file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(
            inventory_copy_activity_profiles.__name__, Exception, e)
        return error


def inventory_copy_vector_layers(inventory_path):
    try:
        result = alaqsdblite.inventory_copy_vector_layers(inventory_path)
        if result is not None:
            raise Exception(
                "Vector could not be copied to ALAQS output file: %s" % result)
        return None
    except Exception as e:
        error = alaqsutils.print_error(inventory_copy_vector_layers.__name__,
                                       Exception, e)
        return error
