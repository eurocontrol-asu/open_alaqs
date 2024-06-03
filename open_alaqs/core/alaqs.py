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

from typing import Any, Optional

from open_alaqs.core import alaqsdblite, alaqsutils
from open_alaqs.core.alaqsdblite import execute_sql, update_table
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools.create_output import create_alaqs_output
from open_alaqs.core.tools.sql_interface import SqlExpression
from open_alaqs.typing import AirportDict, StudySetup

logger = get_logger(__name__)


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e, log=logger)
            raise e

    return wrapper


@catch_errors
def create_project(database_name):
    """
    This function is used to create a new project database with all default
    tables completed. Initially, all user tables are blank and must be
    completed.

    :param: database_name : string name for the new project database
    :return: error : None if successful. Error message if not successful
    :raise: None
    """
    if database_name.strip() == "":
        raise Exception("database_name cannot be empty")

    alaqsdblite.create_project_database(database_name)


# ##########################
# ###### STUDY SETUP #######
# ##########################


@catch_errors
def load_study_setup() -> StudySetup:
    """Load project data for the current ALAQS study."""
    return execute_sql("SELECT * FROM user_study_setup")


@catch_errors
def save_study_setup(study_setup: StudySetup) -> None:
    """
    This function updates the study setup table in the currently OpenALAQS
    database.

    :param: study_setup : a list containing all values from the study_setup UI
    :return: error : None if successful. Error message if not successful
    :raises: None
    """
    if len(study_setup) != 15:
        raise Exception(
            f"Incorrect number of study parameters supplied. "
            f"{len(study_setup)} provided - 15 needed"
        )

    for param in study_setup:
        if param == "":
            raise Exception("Study setup parameters cannot be blank")

    update_table(
        "user_study_setup",
        {
            **study_setup,
            "date_modified": SqlExpression("DATETIME('now')"),
        },
        {
            "airport_id": study_setup["airport_id"],
        },
    )


@catch_errors
def get_airport_codes() -> list[str]:
    """Return a list of airport ICAO codes"""
    return execute_sql(
        """
            SELECT airport_code
            FROM default_airports
            ORDER BY airport_code
        """,
        fetchone=False,
    )


@catch_errors
def airport_lookup(icao_code: str) -> Optional[AirportDict]:
    """Look up an airport based on its ICAO code and return data if available.

    Args:
        icao_code (str): ICAO code to look for

    Returns:
        AirportDict | None: airport data
    """
    return execute_sql(
        """
            SELECT *
            FROM default_airports
            WHERE
                airport_code = ?
        """,
        [icao_code],
    )


# ######################
# ###### ROADWAYS ######
# ######################


def get_roadway_methods() -> tuple[str]:
    """
    Get a list of available roadway methods from the database
    """
    return ("COPERT 5",)


def get_roadway_countries() -> list[dict[str]]:
    """Get a list of countries available for roadway modelling"""
    return execute_sql(
        """
            SELECT DISTINCT(country)
            FROM default_vehicle_fleet_euro_standards
            ORDER BY country
        """,
        fetchone=False,
    )


def get_roadway_fleet_years():
    """Get a list of years available for roadway modelling"""
    return execute_sql(
        """
            SELECT DISTINCT(fleet_year)
            FROM default_vehicle_fleet_euro_standards
            ORDER BY country
        """,
        fetchone=False,
    )


@catch_errors
def get_roadway_euro_standards(country: str, fleet_year: str) -> dict:
    """
    Get a list of Euro standards for roadway modelling
    """
    result = alaqsdblite.get_roadway_euro_standards(country, fleet_year)
    if result is None:
        raise Exception("No Euro standards were returned from this database")
    return result


def get_gates() -> list[dict[str, Any]]:
    """Return data on all gates defined in the currently active alaqs study"""
    return execute_sql(
        """
            SELECT *
            FROM shapes_gates
            ORDER BY gate_id COLLATE NOCASE
        """,
        fetchone=False,
    )


def get_runways() -> list[dict[str, Any]]:
    return execute_sql(
        """
            SELECT *, AsText(geometry) AS geometry
            FROM shapes_runways
            ORDER BY runway_id COLLATE NOCASE
        """,
        fetchone=False,
    )


# ############################
# ###### TAXIWAY ROUTES ######
# ############################


@catch_errors
def delete_taxiway_route(taxi_route_name):
    result = alaqsdblite.delete_taxiway_route(taxi_route_name)
    if isinstance(result, str):
        raise Exception(result)
    return None


@catch_errors
def get_taxiway_route(taxiway_route_name):
    result = alaqsdblite.get_taxiway_route(taxiway_route_name)
    if isinstance(result, str):
        raise Exception(result)
    if result is None or result == []:
        return None
    return result


@catch_errors
def get_taxiway_routes():
    result = alaqsdblite.get_taxiway_routes()
    if isinstance(result, str):
        raise Exception(result)
    if result is None or result == []:
        return None
    return result


@catch_errors
def add_taxiway_route(taxiway_route):
    result = alaqsdblite.add_taxiway_route(taxiway_route)
    if result is not None:
        raise Exception(result)
    return None


#  ####################
#  ###### TRACKS ######
#  ####################


@catch_errors
def get_track(track_id):
    """
    Description
    """
    result = alaqsdblite.get_track(track_id)
    if isinstance(result, str):
        raise Exception("Track could not be found: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_tracks():
    """
    Description
    """
    result = alaqsdblite.get_tracks()
    if isinstance(result, str):
        raise Exception("Tracks could not be returned: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


def get_point_category(category_id: str) -> dict[str, Any]:
    """Return the source category of a specific point source by category id."""
    return execute_sql(
        """
            SELECT *
            FROM default_stationary_category
            WHERE category_name = ?
        """,
        [category_id],
    )


def get_point_categories() -> list[dict[str, Any]]:
    """Return the source category of a specific point source by name"""
    return execute_sql(
        """
            SELECT *
            FROM default_stationary_category
            ORDER BY category_name COLLATE NOCASE
        """,
        fetchone=False,
    )


def get_point_type(type_name: str) -> dict[str, Any]:
    """Get the specific point type of a point source based on the type name"""
    return execute_sql(
        """
            SELECT *
            FROM default_stationary_ef
            WHERE description = ?
        """,
        [type_name],
    )


def get_point_types(category_number: int) -> list[dict[str, Any]]:
    """Return all point types from the currently active study"""
    return execute_sql(
        """
            SELECT *
            FROM default_stationary_ef
            WHERE category = ?
        """,
        [category_number],
        fetchone=False,
    )


# #######################
# ###### BUILDINGS ######
# #######################


@catch_errors
def add_building(building_dict):
    """ "
    This function is used to add a new building to the currently active
     database. This is used only when the tool is being used independently of
     QGIS.

    :param building_dict: a dictionary of building properties in format defined
     by new_building()
    :return: True if successful
    """
    result = alaqsdblite.add_building(building_dict)
    if result is not True:
        raise Exception(result)
    return True


@catch_errors
def get_building(building_id):
    """
    Description
    """
    result = alaqsdblite.get_building(building_id)
    if isinstance(result, str):
        raise Exception("Building could not be found: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_buildings():
    """
    Description
    """
    result = alaqsdblite.get_buildings()
    if isinstance(result, str):
        raise Exception("Buildings could not be returned: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_hourly_profiles():
    """
    Description
    """
    result = alaqsdblite.get_hourly_profiles()
    if isinstance(result, str):
        raise Exception("Hourly profiles could not be returned: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_daily_profiles():
    """
    Description
    """
    result = alaqsdblite.get_daily_profiles()
    if isinstance(result, str):
        raise Exception("Daily profiles could not be returned: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_monthly_profiles():
    """
    Description
    """
    result = alaqsdblite.get_monthly_profiles()
    if isinstance(result, str):
        raise Exception("Daily profiles could not be returned: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_hourly_profile(profile_name):
    if (
        (profile_name == "")
        or (profile_name == [])
        or (profile_name is None)
        or (profile_name == "New Profile")
    ):
        return None
    result = alaqsdblite.get_hourly_profile(profile_name)
    if isinstance(result, str):
        raise Exception("Hour profile could not be found: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_daily_profile(profile_name):
    if (
        (profile_name == "")
        or (profile_name == [])
        or (profile_name is None)
        or (profile_name == "New Profile")
    ):
        return None
    result = alaqsdblite.get_daily_profile(profile_name)
    if isinstance(result, str):
        raise Exception("Day profile could not be found: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def get_monthly_profile(profile_name):
    if (
        (profile_name == "")
        or (profile_name == [])
        or (profile_name is None)
        or (profile_name == "New Profile")
    ):
        return None
    result = alaqsdblite.get_monthly_profile(profile_name)
    if isinstance(result, str):
        raise Exception("Month profile could not be found: %s" % result)
    if (result == []) or (result is None):
        return None
    return result


@catch_errors
def add_hourly_profile(properties):
    result = alaqsdblite.add_hourly_profile(properties)
    if result is not None:
        raise Exception(result)
    return result


@catch_errors
def add_daily_profile(properties):
    result = alaqsdblite.add_daily_profile(properties)
    if result is not None:
        raise Exception(result)
    return result


@catch_errors
def add_monthly_profile(properties):
    result = alaqsdblite.add_monthly_profile(properties)
    if result is not None:
        raise Exception(result)
    return result


# #############################
# ###### BUILD INVENTORY ######
# #############################


@catch_errors
def inventory_creation_new(
    inventory_path, model_parameters, study_setup, met_csv_path=""
):
    create_alaqs_output(
        inventory_path, model_parameters, study_setup, met_csv_path=met_csv_path
    )
