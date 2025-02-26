import shutil
import sqlite3 as sqlite
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from qgis.utils import spatialite_connect

from open_alaqs.alaqs_config import ALAQS_ROOT_PATH, ALAQS_TEMPLATE_DB_FILENAME
from open_alaqs.core import alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools.sql_interface import (
    db_delete_records,
    db_execute_sql,
    db_update_table,
)

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


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ProjectDatabase(metaclass=Singleton):
    path: str


def execute_sql(
    sql: str,
    params: Optional[list] = None,
    fetchone: bool = True,
) -> Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
    """Executes SQL statement and returns the resulting row on the currently opened project.

    Args:
        sql (str): SQL query statement
        params (Optional[list], optional): Optional list of parameters that will replace the `?` placeholders in the SQL. Defaults to None.
        fetchone (bool, optional): Fetch only one row or all rows. Defaults to True.

    Returns:
        dict[str, Any] | list[dict[str, Any] | None: A single row as a dict, multiple rows if `fetchone=False`, or None if no rows available.
    """
    return db_execute_sql(ProjectDatabase().path, sql, params, fetchone)


def update_table(
    table_name: str,
    attribute_values: dict[str, Any],
    where_values: dict[str, Any],
) -> list[sqlite.Row]:
    return db_update_table(
        ProjectDatabase().path,
        table_name,
        attribute_values,
        where_values,
    )


def delete_records(
    table_name: str,
    where_values: dict[str, Any],
) -> list[sqlite.Row]:
    return db_delete_records(
        ProjectDatabase().path,
        table_name,
        where_values,
    )


def connect():
    """
    Establish a database connection to a supplied database. Requires a minimum
     of database name, username and password if host and port are PostgreSQL
     defaults.

    ARGS:
        -
    RETURNS:
        - conn : a connection object that can be used to query the database
        - error : None for successful connection, otherwise error message
    RAISES:
        - None
    """

    # Get the path to the project database
    db_name = ProjectDatabase().path

    try:
        conn = spatialite_connect(db_name)
    except Exception as e:
        error = alaqsutils.print_error(connect.__name__, Exception, e, log=logger)
        return None, error

    return conn, None


class connect_to_alaqs_db:
    """
    Executes a code block with a connection to the current ALAQS database.

    Example:
    ```
    with connect_to_alaqs_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
    ```
    """

    def __init__(self, project_database: ProjectDatabase = ProjectDatabase()) -> None:
        self.project_database = project_database
        self.conn = None

    def __enter__(self) -> sqlite.Connection:
        if not hasattr(self.project_database, "path"):
            raise Exception("Cannot connec to to undefined ALAQS database!")

        self.conn = spatialite_connect(self.project_database.path)

        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.conn:
            self.conn.close()

        return exc_type is None


def create_project_database(alaqs_db_filename: str) -> None:
    """
    Create a new database in the PostgreSQL database that contains all of
    the default tables used in an Open ALAQS project. This function takes
    SQL from an external file and uses this to rebuild the ALAQS default
    database.

    db_name : the name of the database to be created
    """

    # Store the filename in-memory for future use
    project_database = ProjectDatabase()
    project_database.path = alaqs_db_filename

    shutil.copy2(
        ALAQS_ROOT_PATH.joinpath(ALAQS_TEMPLATE_DB_FILENAME),
        Path(alaqs_db_filename).absolute(),
    )

    logger.info("[+] Created a blank ALAQS study file in %s", alaqs_db_filename)

    # Update the study created date to now
    execute_sql(
        """
            UPDATE user_study_setup SET date_created = DATETIME('now')
        """,
    )


def query_string(sql_text: str) -> list:
    """
    A specific query for accessing project databases. Checks the query
    using regular expressions to try and make sure that the critical
    databases are not deleted or updated (as this may have detrimental
    effects on other projects that do not require the same changes)

    :param: sql_text : the query to be executed
    :return: result : the query response
    :return: error : Result if query is successful. None if error
    :raise: None
    """
    try:
        # Tidy up the string a bit. Mainly cosmetic for log file
        sql_text = sql_text.replace("  ", "")

        with connect_to_alaqs_db() as conn:
            # Start a connection to the database
            conn.text_factory = str
            cur = conn.cursor()
            cur.execute(sql_text)
            conn.commit()
            result = cur.fetchall()
            return result

    except Exception as error:
        if "no results to fetch" in str(error):
            logger.debug('INFO: Query "%s" executed successfully' % sql_text)
        else:
            alaqsutils.print_error(query_string.__name__, Exception, error, log=logger)


def query_string_df(sql_text: str) -> pd.DataFrame:
    """
    A specific query for accessing project databases. Checks the query
    using regular expressions to try and make sure that the critical
    databases are not deleted or updated (as this may have detrimental
    effects on other projects that do not require the same changes)

    :param: sql_text : the query to be executed
    :return: result : the query response
    :return: error : Result if query is successful. None if error
    :raise: None
    """
    try:
        # Tidy up the string a bit. Mainly cosmetic for log file
        sql_text = sql_text.replace("  ", "")

        # Start a connection to the database
        conn, result = connect()
        if conn is None:
            raise Exception("Could not connect to database.")

        data = pd.read_sql(sql_text, conn)
        conn.close()

        return data
    except Exception as error:
        if "no results to fetch" in str(error):
            logger.debug('INFO: Query "%s" executed successfully' % sql_text)
        else:
            alaqsutils.print_error(query_string.__name__, Exception, error, log=logger)


# #################################################
# #########        STUDY SETUP         ############
# #################################################


@catch_errors
def get_roadway_euro_standards(country: str, fleet_year: str) -> dict:
    """
    Return a list of Euro standards for roadway fleet
    """
    euro_standards_query = (
        f"SELECT vehicle_category, euro_standard "
        f"FROM default_vehicle_fleet_euro_standards "
        f"WHERE country = '{country}' AND fleet_year = '{fleet_year}';"
    )

    euro_standards = query_string(euro_standards_query)

    return {
        vehicle_category: euro_standard
        for (vehicle_category, euro_standard) in euro_standards
    }


# #################################################
# #########       TAXIWAY ROUTES       ############
# #################################################


def delete_taxiway_route(taxi_route_name):
    """
    Delete an existing taxiway route from the current study
    :param taxi_route_name: The name of the taxiway route to be deleted
    """
    try:
        sql_text = (
            'DELETE FROM user_taxiroute_taxiways WHERE route_name="%s";'
            % taxi_route_name
        )
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(
            delete_taxiway_route.__name__, Exception, e, log=logger
        )
        return error


def get_taxiway_route(taxiway_route_name):
    """
    Get all data on a specific taxiway route from the current study using the taxiway route name
    :param taxiway_route_name: the name of the route to return data for
    """
    try:
        sql_text = (
            'SELECT * FROM user_taxiroute_taxiways WHERE route_name="%s";'
            % taxiway_route_name
        )
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(
            get_taxiway_routes.__name__, Exception, e, log=logger
        )
        return error


def get_taxiway_routes():
    """
    Return data for all taxiway routes in the current study
    """
    try:
        sql_text = "SELECT * FROM user_taxiroute_taxiways ORDER BY instance_id;"
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(
            get_taxiway_routes.__name__, Exception, e, log=logger
        )
        return error


def add_taxiway_route(taxiway_route):
    """
    Add a taxiway route to the current study
    :param taxiway_route: description of the route as a dict
    """
    try:
        sql_text = (
            "INSERT INTO user_taxiroute_taxiways (gate, route_name, runway, "
            "departure_arrival, instance_id, sequence, groups) VALUES "
            '("%s","%s","%s","%s",%s,"%s","%s")'
            % (
                taxiway_route["gate"],
                taxiway_route["name"],
                taxiway_route["runway"],
                taxiway_route["dept_arr"],
                taxiway_route["instance"],
                taxiway_route["sequence"],
                taxiway_route["groups"],
            )
        )
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(
            add_taxiway_route.__name__, Exception, e, log=logger
        )
        return error


# #################################################
# #########          PROFILES         #############
# #################################################


def get_hourly_profiles():
    """
    Return data on all hourly profiles in the currently active study
    """
    try:
        sql_text = (
            "SELECT * FROM user_hour_profile ORDER BY profile_name COLLATE NOCASE;"
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_hourly_profiles.__name__, Exception, e, log=logger
        )
        return error


def get_daily_profiles():
    """
    Return data on all daily profiles in the currently active study
    """
    try:
        sql_text = (
            "SELECT * FROM user_day_profile ORDER BY profile_name COLLATE NOCASE;"
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_daily_profiles.__name__, Exception, e, log=logger
        )
        return error


def get_monthly_profiles():
    """
    Return data on all monthly profiles in the currently active study
    """
    try:
        sql_text = (
            "SELECT * FROM user_month_profile ORDER BY profile_name COLLATE NOCASE;"
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_monthly_profiles.__name__, Exception, e, log=logger
        )
        return error


def get_hourly_profile(profile_name):
    """
    Return data on a specific hourly profile based on profile name
    :param profile_name: the name of the profile to look up
    """
    try:
        sql_text = (
            'SELECT * FROM user_hour_profile WHERE profile_name = "%s";' % profile_name
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_hourly_profile.__name__, Exception, e, log=logger
        )
        return error


def get_daily_profile(profile_name):
    """
    Return data on a specific daily profile based on the profile name
    :param profile_name: the name of the profile to look up
    """
    try:
        sql_text = (
            'SELECT * FROM user_day_profile WHERE profile_name = "%s";' % profile_name
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_daily_profile.__name__, Exception, e, log=logger
        )
        return error


def get_monthly_profile(profile_name):
    """
    Return data for a specific monthly profile based on the profile name
    :param profile_name: the name of the monthly profile to be looked up
    """
    try:
        sql_text = (
            'SELECT * FROM user_month_profile WHERE profile_name = "%s";' % profile_name
        )
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            get_monthly_profile.__name__, Exception, e, log=logger
        )
        return error


def add_hourly_profile(properties):
    """
    Add a new hourly profile to the currently active study database
    :param properties: the properties of the new profile to be added
    """
    try:
        # Split out and validate properties
        p0 = properties[0]  # name
        p1 = properties[1]  # h00
        p2 = properties[2]  # h01
        p3 = properties[3]  # h02
        p4 = properties[4]  # h03
        p5 = properties[5]  # h04
        p6 = properties[6]  # h05
        p7 = properties[7]  # h06
        p8 = properties[8]  # h07
        p9 = properties[9]  # h08
        p10 = properties[10]  # h09
        p11 = properties[11]  # h10
        p12 = properties[12]  # h11
        p13 = properties[13]  # h12
        p14 = properties[14]  # h13
        p15 = properties[15]  # h14
        p16 = properties[16]  # h15
        p17 = properties[17]  # h16
        p18 = properties[18]  # h17
        p19 = properties[19]  # h18
        p20 = properties[20]  # h19
        p21 = properties[21]  # h20
        p22 = properties[22]  # h21
        p23 = properties[23]  # h22
        p24 = properties[24]  # h23

        # Check if profile already exists
        sql_text = (
            'SELECT * FROM user_hour_profile WHERE profile_name="%s";'
            % p0.replace("'", "")
        )
        result = query_string(sql_text)
        logger.debug(str(result))

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        # if result is [] or result is "" or result is None:
        if len(result) == 0:
            sql_text = (
                "INSERT INTO user_hour_profile (profile_name,h01,h02,h03,h04,h05,h06,h07,h08,h09,h10,h11,"
                'h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24) VALUES ("%s",%s,%s,%s,%s,%s,%s,%s,%s,'
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);"
                % (
                    p0,
                    p1,
                    p2,
                    p3,
                    p4,
                    p5,
                    p6,
                    p7,
                    p8,
                    p9,
                    p10,
                    p11,
                    p12,
                    p13,
                    p14,
                    p15,
                    p16,
                    p17,
                    p18,
                    p19,
                    p20,
                    p21,
                    p22,
                    p23,
                    p24,
                )
            )
        else:
            sql_text = (
                'UPDATE user_hour_profile SET profile_name="%s",h01=%s,h02=%s,h03=%s,h04=%s,h05=%s,h06=%s,'
                "h07=%s,h08=%s,h09=%s,h10=%s,h11=%s,h12=%s,h13=%s,h14=%s,h15=%s,h16=%s,h17=%s,h18=%s,h19=%s,"
                'h20=%s,h21=%s,h22=%s,h23=%s,h24=%s WHERE profile_name="%s";'
                % (
                    p0,
                    p1,
                    p2,
                    p3,
                    p4,
                    p5,
                    p6,
                    p7,
                    p8,
                    p9,
                    p10,
                    p11,
                    p12,
                    p13,
                    p14,
                    p15,
                    p16,
                    p17,
                    p18,
                    p19,
                    p20,
                    p21,
                    p22,
                    p23,
                    p24,
                    p0,
                )
            )
        result = query_string(sql_text)
        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            add_hourly_profile.__name__, Exception, e, log=logger
        )
        return error


def add_daily_profile(properties):
    """
    Add a new daily profile to the currently active study database
    :param properties: The properties of the new profile to be added as a dict
    """
    try:
        # Split out and validate properties
        p0 = properties[0]  # name
        p1 = properties[1]  # mon
        p2 = properties[2]  # tue
        p3 = properties[3]  # wed
        p4 = properties[4]  # thu
        p5 = properties[5]  # fri
        p6 = properties[6]  # sat
        p7 = properties[7]  # sun

        # Check if profile already exists
        sql_text = (
            'SELECT * FROM user_day_profile WHERE profile_name="%s";'
            % p0.replace("'", "")
        )
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        if len(result) == 0:
            sql_text = (
                'INSERT INTO user_day_profile (profile_name,mon,tue,wed,thu,fri,sat,sun) VALUES ( \
                "%s",%s,%s,%s,%s,%s,%s,%s)'
                % (p0, p1, p2, p3, p4, p5, p6, p7)
            )
        else:
            sql_text = (
                'UPDATE user_day_profile SET profile_name="%s",mon=%s,tue=%s,wed=%s,thu=%s,fri=%s,sat=%s,'
                'sun=%s WHERE profile_name="%s";' % (p0, p1, p2, p3, p4, p5, p6, p7, p0)
            )
        result = query_string(sql_text)

        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            add_daily_profile.__name__, Exception, e, log=logger
        )
        return error


def add_monthly_profile(properties):
    """
    Add a new monthly profile to the currently active database
    :param properties: the properties of the new profile to be added
    """
    try:
        # Split out and validate properties
        p0 = properties[0]  # name
        p1 = properties[1]  # jan
        p2 = properties[2]  # feb
        p3 = properties[3]  # mar
        p4 = properties[4]  # apr
        p5 = properties[5]  # may
        p6 = properties[6]  # jun
        p7 = properties[7]  # jul
        p8 = properties[8]  # aug
        p9 = properties[9]  # sep
        p10 = properties[10]  # oct
        p11 = properties[11]  # nov
        p12 = properties[12]  # dec

        # Check if profile already exists
        sql_text = (
            'SELECT * FROM user_month_profile WHERE profile_name="%s";'
            % p0.replace("'", "")
        )
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        if len(result) == 0:
            sql_text = (
                'INSERT INTO user_month_profile (profile_name,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec) \
                VALUES ( "%s",%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
                % (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12)
            )
        else:
            sql_text = (
                'UPDATE user_month_profile SET profile_name="%s",jan=%s,feb=%s,mar=%s,apr=%s,may=%s,jun=%s,'
                'jul=%s,aug=%s,sep=%s,oct=%s,nov=%s,dec=%s WHERE profile_name="%s";'
                % (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p0)
            )
        result = query_string(sql_text)
        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(
            add_monthly_profile.__name__, Exception, e, log=logger
        )
        return error


# #################################################
# #########       CALCULATIONS        #############
# #################################################
