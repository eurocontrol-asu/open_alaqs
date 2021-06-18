"""
@author: Dan Pearce
"""
import csv
import datetime
import os
import pickle
import shutil
import sqlite3 as sqlite
import struct
import sys

from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def connectToDatabase(database_path):
    """
    Creates a connection to a SQLite database
    :param database_path:
    :type database_path: str
    :return curs: a cursor object for the database provided
    :rtype: object
    """
    try:
        conn = sqlite.connect(database_path)
        #logger.info("Connection to database '%s' created" %(database_path))
        return conn
    except Exception as e:
        msg = "Connection could not be established: %s" % e
        logger.error(msg)
        return msg

def query_text(database_path, sql_text):
    """
    Execute a query against a given SQLite database
    :param database_path: the path to the database that is being queried
    :param sql_text: the SQL text to be executed
    :return data: the result of the query
    :raise ValueError: if database returns a string (error) instead of list
    """

    # Log the incoming database and sql text
    #logger.debug("Query to database '%s'" % (database_path))
    #logger.debug(sql_text)

    # Create a blank connection object
    conn = None

    try:
        # Create a connection
        conn = connectToDatabase(database_path)
        curs = conn.cursor()
        # Execute the query
        curs.execute(sql_text)
        # Collect the result
        data = curs.fetchall()
        # Process the result
        if isinstance(data, str):
            raise TypeError("Query returned an error: %s" % data)
        elif data is None or data == []:
            return None
        else:
            return data
    except Exception as e:
        logger.error("Query could not be completed: %s" % (str(e)))
        return "Query could not be completed: %s" % (str(e))
    finally:
        # Commit any changes the query  performed and close the connection. This is in a try-except block in case there
        # was no connection established and no query to commit. Without this, an error will be raised
        try:
            conn.commit()
            conn.close()
        except:
            pass

def save_database_credentials(dbhost="NA", dbport="NA", db_name="NA", dbuser="NA", dbpass="NA"):
    """
    This function actually loads the credentials of the active database into
    a file that can then be easily retrieved as the application runs.
    Consequently, a connection can be easily opened and closed.

    Database credentials are added to a list and pickled for simple recovery
    as and when a new database connection is required or a new database is
    accessed.

    :param: dbhost :  the database host (localhost or ip address) - not relevant for SQLite but retained so that the
    syntax is the same across all database access modules
    :param: dbport :  the port number the database is listening to - not relevant for SQLite but retained so that the
    syntax is the same across all database access modules
    :param: db_name : a valid alaqs database
    :param: dbuser :  a valid database username - not relevant for SQLite but retained so that the syntax is the same
    across all database access modules
    :param: dbpass :  a valid database password - not relevant for SQLite but retained so that the syntax is the same
    across all database access modules
    :returns: error : None if successful. Exception message if not successful
    :raises: None
    """

    try:
        db_name = os.path.abspath(db_name)
        active_database = [dbhost, dbport, db_name, dbuser, dbpass, "SQLite"]
        with open(os.path.join(os.path.dirname(__file__), 'adbs.pckl'), 'wb') as pkl:
            pickle.dump(active_database, pkl)
        pkl.close()
        # p = os.path.join(os.path.dirname(__file__), 'adbs.pckl')
        # # f = open(p, 'w')
        # f = open(p, 'ab') # QGIS3?
        # pickle.dump(active_database, f)
        # f.close()
        logger.info("INFO: New database credentials pickled: %s" % active_database)
        # with open('adbs.txt', 'a+') as filehandle:
        #     for listitem in active_database:
        #         filehandle.write('%s\n' % listitem)
        # logger.info("INFO: New database credentials written to adbs.txt: %s" % active_database)
        return None
    except Exception as e:
        error = alaqsutils.print_error(save_database_credentials.__name__, Exception, e)
        return error


def get_database_credentials():
    """
    This function serialises pickled database credentials back into a Python
    list. This is used either by the _connect() function to return a connection
    object or by functions that need to modify the database credentials, for
    example create_new_project()

    ARGS
        - None
    RETURNS
        - Database credentials as a list or an error string
    RAISES:
        - None
    """
    f = None
    try:
        credentials = []
        # # open file and read the content in a list
        # with open('adbs.txt', 'a+') as filehandle:
        #     for line_ in filehandle:
        #         # remove linebreak which is the last character of the string, add item to the list
        #         current_ = line_[:-1]
        #         credentials.append(current_)
        with open(os.path.join(os.path.dirname(__file__), 'adbs.pckl'), 'rb') as f:
            credentials = pickle.load(f)
        # p = os.path.join(os.path.dirname(__file__), 'adbs.pckl')
        # f = open(p)
        # credentials = pickle.load(f)
        if len(credentials) is not 6:
            raise Exception("ERROR: problem loading database credentials")
        else:
            return credentials
    except Exception as e:
        error = alaqsutils.print_error(get_database_credentials.__name__, Exception, e)
        return error
    finally:
        try:
            f.close()
        except:
            pass


def connect():
    """
    Establish a database connection to a supplied database. Requires a
    minimum of database name, username and password if host and port are
    PostgreSQL defaultSs.

    ARGS:
        -
    RETURNS:
        - conn : a connection object that can be used to query the database
        - error : None for successful connection, otherwise error message
    RAISES:
        - None
    """

    db = get_database_credentials()
    db_name = db[2]

    try:
        conn = sqlite.connect(db_name)
    except Exception as e:
        error = alaqsutils.print_error(connect.__name__, Exception, e)
        return None, error
    try:
        # Execute a basic query to be sure we're all good
        # cur = conn.cursor()
        # Load the spatialite dll. It is really important to make sure that the
        # folder containing the DLLs is on PATH and not simply to use sys.path.append
        # as this is temporary and will not allow the dependent (linked) DLLs to be
        # found.
        conn.enable_load_extension(True)

        # spatial_dll_filename = "libspatialite-4.dll"
        # if 8 * struct.calcsize("P") == 64:
        #     spatial_dll_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spatialite-4.0.0-DLL-win-amd64")
        #     raise Exception("64bit installation of QGIS are not supported. Please use the 32bit installation.")
        # else:
        #     spatial_dll_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spatialite-4.0.0-DLL")

        spatial_dll_filename = "mod_spatialite.dll"
        if 8 * struct.calcsize("P") == 64:
            spatial_dll_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spatialite-4.0.0-DLL")
        else:
            spatial_dll_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spatialite-4.0.0-DLL")
            raise Exception("64bit installation of QGIS is now supported. Please try to use the 64bit installation.")


        if not spatial_dll_folder in sys.path:
            sys.path.append(spatial_dll_folder)

        if not spatial_dll_folder in os.environ['PATH']:
            #os.environ['PATH'] += os.pathsep + spatial_dll_folder
            #os.environ['PATH'] = spatial_dll_folder + ';' + os.environ['PATH']
            os.environ['PATH'] = spatial_dll_folder + os.pathsep + os.environ['PATH']

        # logger.debug("Searching library '%s' at '%s'" % (spatial_dll_filename, spatial_dll_folder))

        conn.execute('SELECT load_extension("%s")' % (spatial_dll_filename))

        #try:
        #    conn.execute("SELECT InitSpatialMetaData()")
        #except:
        #    pass

        return conn, None
    except Exception as e:
        error = alaqsutils.print_error(connect.__name__, Exception, e)
        return None, error


def create_project_database(db_name):
    """
    Create a new database in the PostgreSQL database that contains all of
    the default tables used in an Open ALAQS project. This function takes
    SQL from an external file and uses this to rebuild the ALAQS default
    database.

    db_name : the name of the database to be created
    """
    try:
        # Modifying this routine to instead copy a blank database
        result = save_database_credentials(db_name=db_name)
        if result is not None:
            raise Exception("Problem with save_database_credentials(): %s" % result)
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'templates/new_blank_study.alaqs'), db_name)
        msg = "[+] Created a blank ALAQS study file in %s" % db_name
        logger.info(msg)

        # Update the study created date to now
        query_string("UPDATE user_study_setup SET date_created = DATETIME('now');")

        return None

    except Exception as e:
        error = alaqsutils.print_error(create_project_database.__name__, Exception, e)
        return error


def query_string(sql_text):
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
        sql_text = sql_text.replace("", "")
        sql_text = sql_text.replace("  ", "")
        conn, result = connect()
        if conn is None:
            raise Exception("Could not connect to database.")

        conn.text_factory = str
        cur = conn.cursor()
        cur.execute(sql_text)
        conn.commit()
        result = cur.fetchall()
        conn.close()
        return result
    except Exception as e:
        if "no results to fetch" in e:
            logger.debug("INFO: Query \"%s\" executed successfully" % sql_text)
        else:
            alaqsutils.print_error(query_string.__name__, Exception, e)
        return None


def query_file(sql_file_name):
    """
    This internal function runs through all of the queries in a SQL text file
    and executes them against a supplied database connection.

    :param sql_file_name : the sql file to be executed
    :return result : None if query is successful. None if error
    """
    try:
        sql_file = open(sql_file_name, 'rt')
        sql_text = sql_file.read()
        sql_queries = sql_text.split(';')
        conn, error = connect()
        cur = conn.cursor()
        for query in sql_queries:
            if query.strip() is not "":
                cur.execute(query)
        sql_file.close()
        logger.debug("INFO: Queries from \"%s\" executed successfully" % sql_file_name)

        conn.commit()
        conn.close()
        return None
    except Exception as e:
        error = alaqsutils.print_error(query_file.__name__, Exception, e)
        return error


def load_csv_data(table_name, csv_file):
    """
    This function loads the CSV data from a plain text file into a SQLite
    table. The number of columns in the CSV file must match the number of
    columns in the named table, otherwise the insert will fail.

    :param table_name: the name of the table data is to be added to (string)
    :param csv_file: path to the CSV file to be added (string)
    :return error: None if successful, error message if failure
    """
    try:
        f = open(csv_file, 'rb')
        csv_data = csv.reader(f)
        result = query_string("PRAGMA table_info(%s);" % table_name)
        column_names = []
        question_marks = []
        for row in result:
            column_names.append(row[1])
            question_marks.append("?")
        column_names = ",".join(column_names)
        question_marks = ",".join(question_marks)
        sql_query = "INSERT INTO %s (%s) VALUES (%s);" % (table_name, column_names, question_marks)
        # Create connection and commit
        conn, error = connect()
        conn.text_factory = str     # Very important, especially if Excel is used for CSV
        cur = conn.cursor()
        cur.executemany(sql_query, csv_data)
        conn.commit()
        conn.close()
        return None
    except Exception as e:
        error = alaqsutils.print_error(load_csv_data.__name__, Exception, e)
        return error


def create_airport(properties):
    """
    This creates a blank airport record in the user_study_setup table.
    The only valid entries in the new airport entry are the unique airport id
    and the alaqs version. All other values will need to be modified using
    appropriate functions.

    :param properties:
    """
    try:
        airport_id = properties[0]
        alaqs_version = properties[1]
        project_name = properties[2]
        airport_name = properties[3]
        airport_code = properties[4]
        airport_country = properties[5]
        airport_latitude = properties[6]
        airport_longitude = properties[7]
        airport_elevation = properties[8]
        airport_temperature = properties[9]
        vertical_limit = properties[10]
        roadway_method = properties[11]
        roadway_fleet_year = properties[12]
        roadway_country = properties[13]
        parking_method = properties[14]
        study_info = properties[15]

        sql_text = "INSERT INTO user_study_setup ('airport_id','alaqs_version','project_name','airport_name'," \
                   "'airport_code','airport_country','airport_latitude','airport_longitude','airport_elevation'," \
                   "'airport_temperature','vertical_limit','roadway_method','roadway_fleet_year','roadway_country'," \
                   "'parking_method','study_info','date_created','date_modified') VALUES (\"%s\",\"%s\",\"%s\"," \
                   "\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\"," \
                   "DATETIME('NOW'),DATETIME('NOW'))" % (airport_id, alaqs_version, project_name, airport_name,
                                                         airport_code, airport_country, airport_latitude,
                                                         airport_longitude, airport_elevation, airport_temperature,
                                                         vertical_limit, roadway_method, roadway_fleet_year,
                                                         roadway_country, parking_method, study_info)
        result = query_string(sql_text)
        if result is None:
            return None
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(create_project_database.__name__, Exception, e)
        return error


def airport_lookup(airport_code):
    """
    Lookup an airport in the current database using the ICAO code
    :param airport_code:
    :return:
    """
    try:
        airport_query = "SELECT * FROM default_airports WHERE airport_code=\"%s\";" % airport_code
        airport_data = query_string(airport_query)
        return airport_data
    except Exception as e:
        alaqsutils.print_error(airport_lookup.__name__, Exception, e)
        return None


##################################################
##########        STUDY SETUP         ############
##################################################


def get_study_setup():
    """
    This function searches for and returns the complete airport information record
    from the user_study_setup table.
    """
    try:
        #sql_text = "SELECT * FROM user_study_setup WHERE airport_id=\"%s\";" % airport_id
        sql_text = "SELECT * FROM user_study_setup"
        result = query_string(sql_text)

        if not result is None:
            if len(result) > 0:
                return result
            elif result is []:
                return None

        raise Exception("Could not retrieve study setup from database. Query result is '%s'." % (str(result)))

    except Exception as e:
        error = alaqsutils.print_error(get_study_setup.__name__, Exception, e)
        return error


def get_roadway_methods():
    """
    Return a list of types of available roadway methods from database
    """
    try:
        methods = ["ALAQS Method"]
        return methods
    except Exception as e:
        alaqsutils.print_error(get_roadway_methods.__name__, Exception, e)
        return None


def get_roadway_countries():
    """
    Return a list of unique countries that are available in the roadway emissions database
    """
    try:
        country_query = "SELECT DISTINCT(country) FROM default_cost319_vehicle_fleet ORDER BY country;"
        countries = query_string(country_query)

        return countries
    except Exception as e:
        alaqsutils.print_error(get_roadway_countries.__name__, Exception, e)
        return None


def get_roadway_years():
    """
    Return a list of unique years for which roadway fleet data is available
    """
    try:
        years = ["1990", "1995", "2000", "2005", "2010", "2015", "2020"]
        return years
    except Exception as e:
        alaqsutils.print_error(get_roadway_years.__name__, Exception, e)
        return None


def save_study_setup(study_setup):
    """
    This function updates the study setup record for the currently active project
    """
    try:
        project_name = study_setup[0]
        airport_name = study_setup[1]
        airport_id = study_setup[2]
        icao_code = study_setup[3]
        airport_country = study_setup[4]
        airport_lat = study_setup[5]
        airport_lon = study_setup[6]
        airport_elevation = study_setup[7]
        airport_temp = study_setup[8]
        vertical_limit = study_setup[9]
        parking_method = study_setup[10]
        roadway_method = study_setup[11]
        roadway_fleet_year = study_setup[12]
        roadway_country = study_setup[13]
        study_info = study_setup[14]

        sql_text = "UPDATE user_study_setup SET \
        airport_id=%s, project_name=\"%s\", airport_name=\"%s\", airport_code=\"%s\", \
        airport_country=\"%s\", airport_latitude=%f, airport_longitude=%f, \
        airport_elevation='%f', airport_temperature=%f, vertical_limit=%f, \
        roadway_method=\"%s\", roadway_fleet_year=\"%s\", roadway_country=\"%s\", \
        parking_method=\"%s\", study_info=\"%s\", date_modified=DATETIME('now') \
        WHERE airport_id=%s;" % (airport_id, project_name, airport_name, icao_code, airport_country, airport_lat,
                                 airport_lon, airport_elevation, airport_temp, vertical_limit, roadway_method,
                                 roadway_fleet_year, roadway_country, parking_method, study_info, airport_id)

        result = query_string(sql_text)
        if (result is None) or (result == []):
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(save_study_setup.__name__, Exception, e)
        return error


def save_study_setup_dict(study_setup_dict):
    """
    This function updates the study setup record for the currently active project
    """
    try:
        project_name = study_setup_dict['project_name']
        airport_name = study_setup_dict['airport_name']
        airport_id = study_setup_dict['airport_id']
        icao_code = study_setup_dict['airport_code']
        airport_country = study_setup_dict['airport_country']
        airport_lat = study_setup_dict['airport_latitude']
        airport_lon = study_setup_dict['airport_longitude']
        airport_elevation = study_setup_dict['airport_elevation']
        airport_temp = study_setup_dict['airport_temperature']
        vertical_limit = study_setup_dict['vertical_limit']
        parking_method = study_setup_dict['parking_method']
        roadway_method = study_setup_dict['roadway_method']
        roadway_fleet_year = study_setup_dict['roadway_fleet_year']
        roadway_country = study_setup_dict['roadway_country']
        study_info = study_setup_dict['study_info']

        sql_text = "UPDATE user_study_setup SET \
        airport_id=%s, project_name=\"%s\", airport_name=\"%s\", airport_code=\"%s\", \
        airport_country=\"%s\", airport_latitude=%f, airport_longitude=%f, \
        airport_elevation='%f', airport_temperature=%f, vertical_limit=%f, \
        roadway_method=\"%s\", roadway_fleet_year=\"%s\", roadway_country=\"%s\", \
        parking_method=\"%s\", study_info=\"%s\", date_modified=DATETIME('now') \
        WHERE airport_id=%s;" % (airport_id, project_name, airport_name, icao_code, airport_country, airport_lat,
                                 airport_lon, airport_elevation, airport_temp, vertical_limit, roadway_method,
                                 roadway_fleet_year, roadway_country, parking_method, study_info, airport_id)

        result = query_string(sql_text)
        if (result is None) or (result == []):
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(save_study_setup.__name__, Exception, e)
        return error


##################################################
##########           GATES            ############
##################################################


def add_gate_dict(gate_dict):
    try:
        # Split out and validate properties
        p0 = gate_dict['gate_id']
        p1 = gate_dict['gate_type']
        p2 = gate_dict['gate_height']
        p3 = gate_dict['gate_instudy']
        p4 = gate_dict['gate_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_gates WHERE gate_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving gate: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_gates (gate_id,gate_type,instudy,gate_height,geometry) \
                VALUES ('%s','%s','%s','%s',ST_Transform(GeomFromText('%s', 4326), 3857))" % \
                (p0, p1, p3, p2, p4)
            logger.info("Added gate %s to database" % p0)
        else:
            sql_text = "UPDATE shapes_gates SET gate_id='%s', gate_type='%s', instudy='%s', gate_height='%s', \
                geometry=ST_Transform(GeomFromText('%s', 4326),3857) WHERE gate_id='%s';" % \
                (p0, p1, p3, p2, p4, p0)
            logger.info("Updated gate %s in database" % p0)

        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_gate_dict.__name__, Exception, e)
        return error


def get_gate(gate_name):
    """
    Return all data on a specific gate from the current database
    """
    try:
        sql_text = "SELECT oid, gate_id, gate_type, instudy, height, AsText(geometry) FROM shapes_gates WHERE " \
                   "gate_id = \"%s\";" % gate_name
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_gates.__name__, Exception, e)
        return error


def get_gates():
    """
    Return data on all gates from the current database
    """
    try:
        sql_text = "SELECT oid, gate_id, gate_type, gate_height, instudy FROM shapes_gates ORDER BY gate_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception(result)
        elif result is [] or result is None:
            return None
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_gates.__name__, Exception, e)
        return error


##################################################
##########         ROADWAYS           ############
##################################################


def add_roadway_dict(roadway_dict):
    try:
        # Split out and validate taxiway properties
        p0 = roadway_dict['roadway_id']
        p1 = roadway_dict['roadway_vehicle_year']
        #p2 = roadway_dict['roadway_vehicle_hour']
        p3 = roadway_dict['roadway_speed']
        p4 = roadway_dict['roadway_distance']
        p5 = roadway_dict['roadway_height']
        p6 = roadway_dict['roadway_vehicle_light']
        p7 = roadway_dict['roadway_vehicle_medium']
        p8 = roadway_dict['roadway_vehicle_heavy']
        #p9 = roadway_dict['roadway_year_hour']
        p10 = roadway_dict['roadway_hour_profile']
        p11 = roadway_dict['roadway_daily_profile']
        p12 = roadway_dict['roadway_month_profile']
        p13 = roadway_dict['roadway_co_gm_km']
        p14 = roadway_dict['roadway_hc_gm_km']
        p15 = roadway_dict['roadway_nox_gm_km']
        p16 = roadway_dict['roadway_sox_gm_km']
        p17 = roadway_dict['roadway_pm10_gm_km']
        p18 = roadway_dict['roadway_p1_gm_km']
        p19 = roadway_dict['roadway_p2_gm_km']
        p20 = roadway_dict['roadway_method']
        p21 = roadway_dict['roadway_instudy']
        p22 = roadway_dict['roadway_scenario']
        #p23 = roadway_dict['roadway_vehicle_years']
        p24 = roadway_dict['roadway_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_roadways WHERE roadway_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving gate: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_roadways (roadway_id,vehicle_year,speed,distance,height," \
                       "vehicle_light,vehicle_medium,vehicle_heavy,hour_profile,daily_profile,month_profile," \
                       "co_gm_km,hc_gm_km,nox_gm_km,sox_gm_km,pm10_gm_km,p1_gm_km,p2_gm_km,method,instudy,scenario," \
                       "geometry) VALUES ('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "'%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "ST_Transform(GeomFromText('%s', 4326), 3857))" % \
                       (p0, p1, p3, p4, p5, p6, p7, p8, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20,
                        p21, p22, p24)
            logger.info("Added roadway %s to database" % p0)
        else:
            sql_text = "UPDATE shapes_roadways SET roadway_id='%s', vehicle_year='%s', speed='%s', " \
                       "distance='%s', height='%s', vehicle_light='%s', vehicle_medium='%s', vehicle_heavy='%s', " \
                       "hour_profile='%s', daily_profile='%s', month_profile='%s', co_gm_km='%s', " \
                       "hc_gm_km='%s', nox_gm_km='%s', sox_gm_km='%s', pm10_gm_km='%s', p1_gm_km='%s', p2_gm_km='%s', " \
                       "method='%s', instudy='%s', scenario='%s', " \
                       "geometry=ST_Transform(GeomFromText('%s', 4326), 3857) WHERE roadway_id='%s';" % \
                       (p0, p1, p3, p4, p5, p6, p7, p8, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20,
                        p21, p22, p24, p0)
            logger.info("Updated roadway %s in database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_roadway_dict.__name__, Exception, e)
        return error


def get_roadway(roadway_id):
    """
    Return data on a specific roadway based on the roadway_id (name)
    """
    try:
        sql_text = "SELECT oid, roadway_id, vehicle_year, vehicle_hour, speed, distance, height, \
            vehicle_light, vehicle_medium, vehicle_heavy, year_hour, hour_profile, daily_profile, month_profile, \
            co_gm_km, hc_gm_km, nox_gm_km, sox_gm_km, pm10_gm_km, p1_gm_km, p2_gm_km, method, instudy, \
            scenario,vehicle_years_old,AsText(geometry) FROM shapes_roadways WHERE roadway_id=\"%s\";" % roadway_id
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_roadway.__name__, Exception, e)
        return error


def get_roadways():
    """
    Return data on all roadways in the current study
    """
    try:
        sql_text = "SELECT * FROM shapes_roadways ORDER BY roadway_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_roadways.__name__, Exception, e)
        return error


##################################################
##########         RUNWAYS            ############
##################################################


def add_runway_dict(runway_dict):
    try:
        # Split out and validate runway properties
        p0 = runway_dict['runway_id']
        p1 = runway_dict['runway_capacity']
        p2 = runway_dict['runway_touchdown']
        p3 = runway_dict['runway_max_queue_speed']
        p4 = runway_dict['runway_peak_queue_time']
        p5 = runway_dict['runway_instudy']
        p6 = runway_dict['runway_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_runways WHERE runway_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving runway: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_runways (runway_id, capacity, touchdown, max_queue_speed, peak_queue_time, " \
                       "instudy, geometry) VALUES ('%s','%s','%s','%s','%s','%s'," \
                       "ST_Transform(GeomFromText('%s', 4326), 3857))" % \
                       (p0, p1, p2, p3, p4, p5, p6)
            logger.info("Added runway %s to database" % p0)
        else:
            sql_text = "UPDATE shapes_runways SET runway_id='%s', capacity='%s', touchdown='%s', max_queue_speed='%s', " \
                       "peak_queue_time='%s',instudy='%s', geometry=ST_Transform(GeomFromText('%s', 4326), 3857) " \
                       "WHERE runway_id='%s';" % (p0, p2, p1, p3, p4, p5, p6, p0)
            logger.info("Updated runway %s in database" % p0)

        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_runway_dict.__name__, Exception, e)
        return error


def get_runway(runway_id):
    """
    Return data on a specific runway based on the runway_id (name)
    """
    try:
        sql_text = "SELECT runway_id, max_queue_speed, peak_queue_time, instudy, AsText(geometry) FROM " \
                   "shapes_runways WHERE runway_id=\"%s\";" % runway_id
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_roadway.__name__, Exception, e)
        return error


def get_runways():
    """
    Return data on all runways in the current study
    """
    try:
        sql_text = "SELECT runway_id, max_queue_speed, peak_queue_time, instudy, AsText(geometry) FROM " \
                   "shapes_runways ORDER BY runway_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is None or result == []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_runways.__name__, Exception, e)
        return error


##################################################
##########           TAXIWAYS         ############
##################################################


def add_taxiway_dict(taxiway_dict):
    try:
        # Split out and validate taxiway properties
        p0 = taxiway_dict['taxiway_id']
        p1 = taxiway_dict['taxiway_speed']
        p2 = taxiway_dict['taxiway_time']
        p3 = taxiway_dict['taxiway_instudy']
        p4 = taxiway_dict['taxiway_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_taxiways WHERE taxiway_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving taxiway: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_taxiways (taxiway_id,speed,time,instudy,geometry) VALUES " \
                       "('%s','%s','%s','%s',ST_Transform(GeomFromText('%s', 4326), 3857))" % (p0, p1, p2, p3, p4)
        else:
            sql_text = "UPDATE shapes_taxiways SET taxiway_id='%s', speed='%s', time='%s', instudy='%s', " \
                       "geometry=ST_Transform(GeomFromText('%s', 4326), ,3857) WHERE taxiway_id='%s';" % \
                       (p0, p1, p2, p3, p4, p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_taxiway_dict.__name__, Exception, e)
        return error


##################################################
##########       TAXIWAY ROUTES       ############
##################################################


def delete_taxiway_route(taxi_route_name):
    """
    Delete an existing taxiway route from the current study
    :param taxi_route_name: The name of the taxiway route to be deleted
    """
    try:
        sql_text = "DELETE FROM user_taxiroute_taxiways WHERE route_name=\"%s\";" % taxi_route_name
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(delete_taxiway_route.__name__, Exception, e)
        return error


def get_taxiway_route(taxiway_route_name):
    """
    Get all data on a specific taxiway route from the current study using the taxiway route name
    :param taxiway_route_name: the name of the route to return data for
    """
    try:
        sql_text = "SELECT * FROM user_taxiroute_taxiways WHERE route_name=\"%s\";" % taxiway_route_name
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception, e)
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
        error = alaqsutils.print_error(get_taxiway_routes.__name__, Exception, e)
        return error


def add_taxiway_route(taxiway_route):
    """
    Add a taxiway route to the current study
    :param taxiway_route: description of the route as a dict
    """
    try:
        sql_text = "INSERT INTO user_taxiroute_taxiways (gate, route_name, runway, " \
                   "departure_arrival, instance_id, sequence, groups) VALUES " \
                   "(\"%s\",\"%s\",\"%s\",\"%s\",%s,\"%s\",\"%s\")" % (taxiway_route['gate'], taxiway_route['name'],
                                                                       taxiway_route['runway'], taxiway_route['dept_arr'],
                                                                       taxiway_route['instance'], taxiway_route['sequence'],
                                                                       taxiway_route['groups'])
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Could not save taxi route: %s" % result)
        else:
            return None
    except Exception as e:
        error = alaqsutils.print_error(add_taxiway_route.__name__, Exception, e)
        return error


def get_taxiway(taxiway_id):
    """
    Return data on a specific taxiway based on the taxiway_id (name)
    :param: taxiway_id: the name of the taxiway to return data for
    """
    try:
        sql_text = "SELECT taxiway_id,speed,time,instudy,AsText(geometry) FROM shapes_taxiways " \
                   "WHERE taxiway_id=\"%s\";" % taxiway_id
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_taxiway.__name__, Exception, e)
        return error


def get_taxiways():
    """
    Return data for all taxiways in the current study
    """
    try:
        sql_text = "SELECT taxiway_id,speed,time,instudy,AsText(geometry) FROM shapes_taxiways ORDER BY taxiway_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_runways.__name__, Exception, e)
        return error


##################################################
##########          TRACKS           #############
##################################################


def get_track(track_id):
    """
    Return data on a specific track based on the track_id (name)
    :param: track_id: the name of the track to look up
    """
    try:
        sql_text = "SELECT track_id,runway,departure_arrival,points,AsText(geometry) FROM shapes_tracks WHERE " \
                   "track_id=\"%s\";" % track_id
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_track.__name__, Exception, e)
        return error


def get_tracks():
    """
    Return data on all tracks in the current study
    """
    try:
        sql_text = "SELECT track_id,runway,departure_arrival,points,AsText(geometry) FROM shapes_tracks " \
                   "ORDER BY track_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_tracks.__name__, Exception, e)
        return error


##################################################
##########        POINT SOURCES      #############
##################################################


def add_point_source(point_source_dict):
    """
    This function adds a new point source to the currently active database. This is accessed by command line only and
    not used when Open ALAQS is being used as a plugin

    :param point_source_dict: The properties of the new point source
    :return: Boolean of insert success
    """
    try:
        # Split out and validate track properties
        p0 = point_source_dict['source_id']
        p1 = point_source_dict['source_height']
        p2 = point_source_dict['source_category']
        p3 = point_source_dict['source_type']
        p4 = point_source_dict['source_substance']
        p5 = point_source_dict['source_temperature']
        p6 = point_source_dict['source_diameter']
        p7 = point_source_dict['source_velocity']
        p8 = point_source_dict['source_ops_year']
        p11 = point_source_dict['source_hour_profile']
        p12 = point_source_dict['source_daily_profile']
        p13 = point_source_dict['source_monthly_profile']
        p14 = point_source_dict['source_co_kg_k']
        p15 = point_source_dict['source_hc_kg_k']
        p16 = point_source_dict['source_nox_kg_k']
        p17 = point_source_dict['source_sox_kg_k']
        p18 = point_source_dict['source_pm10_kg_k']
        p19 = point_source_dict['source_p1_kg_k']
        p20 = point_source_dict['source_p2_kg_k']
        p21 = point_source_dict['source_instudy']
        p22 = point_source_dict['source_wkt']

        # Check if point already exists
        sql_text = "SELECT * FROM shapes_point_sources WHERE source_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Problem saving stationary sources: %s" % result)
        elif (result == []) or (result is None):
            sql_text = "INSERT INTO shapes_point_sources (source_id, height, category, type, substance, temperature, " \
                       "diameter, velocity, ops_year, hour_profile, daily_profile, month_profile, " \
                       "co_kg_k, hc_kg_k, nox_kg_k, sox_kg_k, pm10_kg_k, p1_kg_k, p2_kg_k, instudy, geometry) VALUES " \
                       "('%s','%s','%s','%s','%s','%s','%s','%s', '%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "'%s','%s','%s','%s', ST_Transform(GeomFromText('%s', 4326), 3857))" % \
                       (p0, p1, p2, p3, p4, p5, p6, p7, p8, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22)
            logger.info("Added point source %s to database" % p0)
        else:
            sql_text = "UPDATE shapes_point_sources SET source_id='%s',height='%s',category='%s',type='%s', " \
                       "substance='%s',temperature='%s',diameter='%s',velocity='%s',ops_year='%s',hour_profile='%s'," \
                       "daily_profile='%s',month_profile='%s',co_kg_k='%s',hc_kg_k='%s',nox_kg_k='%s',sox_kg_k='%s'," \
                       "sox_kg_k='%s',pm10_kg_k='%s',p1_kg_k='%s',p2_kg_k='%s'," \
                       "geometry=ST_Transform(GeomFromText('%s', 4326), 3857) WHERE source_id='%s';" % \
                       (p0, p1, p2, p3, p4, p5, p6, p7, p8, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22, p0)
            logger.info("Updated point source %s in database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        alaqsutils.print_error(add_point_source.__name__, Exception, e)
        return False


def get_point_source(source_id):
    """
    Return data on a specific point source in the study by source_id (name)
    :param source_id: the name of the point source to look up
    """
    try:
        sql_text = "SELECT source_id, height, category, type, substance, temperature, diameter, velocity, \
            ops_year, ops_hour, year_hour, hour_profile, daily_profile, month_profile, co_kg_k, hc_kg_k, \
            nox_kg_k, sox_kg_k, pm10_kg_k, p1_kg_k, p2_kg_k, instudy, AsText(geometry) \
            FROM shapes_point_sources WHERE source_id=\"%s\";" % source_id
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_source.__name__, Exception, e)
        return error


def get_point_sources():
    """
    return data on all point sources in the current study
    """
    try:
        sql_text = "SELECT * FROM shapes_point_sources ORDER BY source_id COLLATE NOCASE;"
        result = query_string(sql_text)

        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_point_sources.__name__, Exception, e)
        return error


def get_point_category(category_name):
    """
    Return the source category of a specific point source by name
    :param category_name: the name of the point source category to look up
    """
    try:
        sql_text = "SELECT * FROM default_stationary_category WHERE category_name=\"%s\";" % category_name
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_category.__name__, Exception, e)
        return error


def get_point_categories():
    """
    Return all point sources from the current database
    """
    try:
        sql_text = "SELECT * FROM default_stationary_category ORDER BY category_name COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_point_categories.__name__, Exception, e)
        return error


def get_point_type(type_name):
    """
    Get the specific point type of a point source based on the type name
    """
    try:
        sql_text = "SELECT * FROM default_stationary_ef WHERE description=\"%s\";" % type_name
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_type.__name__, Exception, e)
        return error


def get_point_types(category_number):
    """
    Return all point types from the currently active study
    """
    try:
        sql_text = "SELECT * FROM default_stationary_ef WHERE category=\"%s\";" % category_number
        result = query_string(sql_text)
        return result
    except Exception as e:
        error = alaqsutils.print_error(get_point_category.__name__, Exception, e)
        return error


##################################################
##########         BUILDINGS         #############
##################################################


def add_building(building_dict):
    """
    This function adds a building to the currently active database. This is accessed by command line only and not used
    when Open ALAQS is being used as a plugin.

    :param building_dict: The properties of the new point source
    :return: Boolean of insert success
    """
    try:
        # Split out and validate properties
        p0 = building_dict['building_id']
        p1 = building_dict['building_height']
        p2 = building_dict['building_instudy']
        p3 = building_dict['building_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_buildings WHERE building_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)
        if isinstance(result, str):
            raise Exception("Problem saving building: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_buildings (building_id,height,instudy,geometry) \
                VALUES ('%s','%s','%s',ST_Transform(GeomFromText('%s', 4326), 3857))" % (p0, p1, p2, p3)
            logger.info("Added building %s to database" % building_dict['building_id'])
        else:
            sql_text = "UPDATE shapes_buildings SET building_id='%s', height='%s', instudy='%s',\
                geometry=ST_Transform(GeomFromText('%s', 4326), 3857) WHERE building_id='%s';" % (p0, p1, p2, p3, p0)
            logger.info("Updated building %s in database" % building_dict['building_id'])
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_building.__name__, Exception, e)
        return error


def get_building(building_id):
    """
    Return data on a specific building based on the building_id (name)
    """
    try:
        sql_text = "SELECT oid, building_id, height, instudy, AsText(geometry) FROM shapes_buildings WHERE " \
                   "building_id = \"%s\";" % building_id
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_building.__name__, Exception, e)
        return error


def get_buildings():
    """
    Return data on all buildings in the current study
    """
    try:
        sql_text = "SELECT oid, building_id, height, instudy, AsText(geometry) FROM shapes_buildings ORDER BY " \
                   "building_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_buildings.__name__, Exception, e)
        return error


##################################################
##########          PARKINGS         #############
##################################################


def add_parking(properties):
    """
    This function adds a new parking to the currently active database. This is accessed by command line only and
    not used when Open ALAQS is being used as a plugin

    :param properties: The properties of the new point source
    :return: Boolean of insert success
    """
    try:
        # Split out and validate properties
        p0 = properties['parking_id']
        p1 = properties['parking_height']
        p2 = properties['parking_distance']
        p3 = properties['parking_idle_time']
        p4 = properties['parking_park_time']
        p5 = properties['parking_vehicle_light']
        p6 = properties['parking_vehicle_medium']
        p7 = properties['parking_vehicle_heavy']
        p8 = properties['parking_vehicle_year']
        #p9 = properties['parking_vehicle_hour']
        #p10 = properties['parking_year_hour']
        p11 = properties['parking_speed']
        p12 = properties['parking_hour_profile']
        p13 = properties['parking_daily_profile']
        p14 = properties['parking_month_profile']
        p15 = properties['parking_co_gm_vh']
        p16 = properties['parking_hc_gm_vh']
        p17 = properties['parking_nox_gm_vh']
        p18 = properties['parking_sox_gm_vh']
        p19 = properties['parking_pm10_gm_vh']
        p20 = properties['parking_p1_gm_vh']
        p21 = properties['parking_p2_gm_vh']
        p22 = properties['parking_method']
        p23 = properties['parking_instudy']
        p24 = properties['parking_wkt']

        # Check if gate already exists
        sql_text = "SELECT * FROM shapes_parking WHERE parking_id='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving parking: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO shapes_parking (parking_id,height,distance,idle_time,park_time,vehicle_light," \
                       "vehicle_medium,vehicle_heavy,vehicle_year,speed,hour_profile," \
                       "daily_profile,month_profile,co_gm_vh,hc_gm_vh,nox_gm_vh,sox_gm_vh,pm10_gm_vh,p1_gm_vh," \
                       "p2_gm_vh,method,instudy,geometry) VALUES ('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "'%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "ST_Transform(GeomFromText('%s', 4326),3857))" % \
                       (p0, p1, p2, p3, p4, p5, p6, p7, p8, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21,
                        p22, p23, p24)
            logger.info("Added parking %s to database" % p0)
        else:
            sql_text = "UPDATE shapes_parking SET parking_id='%s',height='%s',distance='%s',idle_time='%s'," \
                       "park_time='%s',vehicle_light='%s',vehicle_medium='%s',vehicle_heavy='%s', vehicle_year='%s'," \
                       "speed='%s',hour_profile='%s',daily_profile='%s',month_profile='%s',co_gm_vh='%s'," \
                       "hc_gm_vh='%s',nox_gm_vh='%s',sox_gm_vh='%s',pm10_gm_vh='%s',p1_gm_vh='%s',p2_gm_vh='%s'," \
                       "method='%s',instudy='%s',geometry=ST_Transform(GeomFromText('%s', 4326),3857) " \
                       "WHERE parking_id='%s';" % \
                       (p0, p1, p2, p3, p4, p5, p6, p7, p8, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21,
                        p22, p23, p24, p0)
            logger.info("Updated parking %s in database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_parking.__name__, Exception, e)
        return error


def get_parking(parking_id):
    """
    Return data on a specific parking area source based on the parking_id (name)
    :param parking_id: the name of the parking area source to look up
    """
    try:
        sql_text = "SELECT parking_id,height,distance, idle_time,park_time,vehicle_light,\
        vehicle_medium,vehicle_heavy,vehicle_year,vehicle_hour,year_hour,speed,hour_profile,\
        daily_profile,month_profile,co_gm_vh,hc_gm_vh,nox_gm_vh,sox_gm_vh,pm10_gm_vh,\
        p1_gm_vh,p2_gm_vh,method,instudy,AsText(geometry) FROM shapes_parking WHERE parking_id = \"%s\";" % parking_id
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_parking.__name__, Exception, e)
        return error


def get_parkings():
    """
    Return data on all parking sources in the currently active study
    """
    try:
        sql_text = "SELECT parking_id,height,distance, idle_time,park_time,vehicle_light,\
        vehicle_medium,vehicle_heavy,vehicle_year,vehicle_hour,year_hour,speed,hour_profile,\
        daily_profile,month_profile,co_gm_vh,hc_gm_vh,nox_gm_vh,sox_gm_vh,pm10_gm_vh,\
        p1_gm_vh,p2_gm_vh,method,instudy,AsText(geometry) FROM shapes_parking ORDER BY parking_id COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_parkings.__name__, Exception, e)
        return error


##################################################
##########          PROFILES         #############
##################################################


def add_hourly_profile_dict(hourly_profile_dict):
    try:
        # Split out and validate properties
        p0 = hourly_profile_dict['name']
        p1 = hourly_profile_dict['h00']
        p2 = hourly_profile_dict['h01']
        p3 = hourly_profile_dict['h02']
        p4 = hourly_profile_dict['h03']
        p5 = hourly_profile_dict['h04']
        p6 = hourly_profile_dict['h05']
        p7 = hourly_profile_dict['h06']
        p8 = hourly_profile_dict['h07']
        p9 = hourly_profile_dict['h08']
        p10 = hourly_profile_dict['h09']
        p11 = hourly_profile_dict['h10']
        p12 = hourly_profile_dict['h11']
        p13 = hourly_profile_dict['h12']
        p14 = hourly_profile_dict['h13']
        p15 = hourly_profile_dict['h14']
        p16 = hourly_profile_dict['h15']
        p17 = hourly_profile_dict['h16']
        p18 = hourly_profile_dict['h17']
        p19 = hourly_profile_dict['h18']
        p20 = hourly_profile_dict['h19']
        p21 = hourly_profile_dict['h20']
        p22 = hourly_profile_dict['h21']
        p23 = hourly_profile_dict['h22']
        p24 = hourly_profile_dict['h23']

        # Check if profile already exists
        sql_text = "SELECT * FROM user_hour_profile WHERE profile_name='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO user_hour_profile (profile_name,h01,h02,h03,h04,h05,h06,h07,h08,h09,h10,h11,h12," \
                       "h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24) VALUES ('%s','%s','%s','%s','%s','%s'," \
                       "'%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s'," \
                       "'%s','%s')" % (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17,
                                       p18, p19, p20, p21, p22, p23, p24)
            logger.info("Added hour profile %s to database" % p0)
        else:
            sql_text = "UPDATE user_hour_profile SET profile_name='%s',h01='%s',h02='%s',h03='%s',h04='%s',h05='%s'," \
                       "h06='%s',h07='%s',h08='%s',h09='%s',h10='%s',h11='%s',h12='%s',h13='%s',h14='%s',h15='%s'," \
                       "h16='%s',h17='%s',h18='%s',h19='%s',h20='%s',h21='%s',h22='%s',h23='%s',h24='%s' " \
                       "WHERE profile_name='%s';" % (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14,
                                                     p15, p16, p17, p18, p19, p20, p21, p22, p23, p24, p0)
            logger.info("Updated hour profile %s to database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception, e)
        return error


def add_daily_profile_dict(daily_profile_dict):
    try:
        # Split out and validate properties
        p0 = daily_profile_dict['name']
        p1 = daily_profile_dict['mon']
        p2 = daily_profile_dict['tue']
        p3 = daily_profile_dict['wed']
        p4 = daily_profile_dict['thu']
        p5 = daily_profile_dict['fri']
        p6 = daily_profile_dict['sat']
        p7 = daily_profile_dict['sun']

        # Check if profile already exists
        sql_text = "SELECT * FROM user_day_profile WHERE profile_name='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO user_day_profile (profile_name,mon,tue,wed,thu,fri,sat,sun) VALUES ( \
                '%s','%s','%s','%s','%s','%s','%s','%s')" % (p0, p1, p2, p3, p4, p5, p6, p7)
            logger.info("Added daily profile %s to database" % p0)
        else:
            sql_text = "UPDATE user_day_profile SET profile_name='%s',mon='%s',tue='%s',wed='%s',thu='%s',\
                fri='%s',sat='%s',sun='%s' WHERE profile_name='%s';" % (p0, p1, p2, p3, p4, p5, p6, p7, p0)
            logger.info("Updated daily profile %s in database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_daily_profile.__name__, Exception, e)
        return error


def add_monthly_profile_dict(monthly_profile_dict):
    try:
        # Split out and validate properties
        p0 = monthly_profile_dict['name']
        p1 = monthly_profile_dict['jan']
        p2 = monthly_profile_dict['feb']
        p3 = monthly_profile_dict['mar']
        p4 = monthly_profile_dict['apr']
        p5 = monthly_profile_dict['may']
        p6 = monthly_profile_dict['jun']
        p7 = monthly_profile_dict['jul']
        p8 = monthly_profile_dict['aug']
        p9 = monthly_profile_dict['sep']
        p10 = monthly_profile_dict['oct']
        p11 = monthly_profile_dict['nov']
        p12 = monthly_profile_dict['dec']

        # Check if profile already exists
        sql_text = "SELECT * FROM user_month_profile WHERE profile_name='%s';" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)
        elif result is None or result == []:
            sql_text = "INSERT INTO user_month_profile (profile_name,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec) \
                VALUES ( '%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s')" % \
                (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12)
            logger.info("Added month profile %s to database" % p0)
        else:
            sql_text = "UPDATE user_month_profile SET profile_name='%s',jan='%s',feb='%s',mar='%s',apr='%s',\
                may='%s',jun='%s',jul='%s',aug='%s',sep='%s',oct='%s',nov='%s',dec='%s' WHERE profile_name='%s';" % \
                (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p0)
            logger.info("Updated monthly profile %s to database" % p0)
        result = query_string(sql_text)
        if result is None or result == []:
            return True
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception, e)
        return error


def get_hourly_profiles():
    """
    Return data on all hourly profiles in the currently active study
    """
    try:
        sql_text = "SELECT * FROM user_hour_profile ORDER BY profile_name COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profiles.__name__, Exception, e)
        return error


def get_daily_profiles():
    """
    Return data on all daily profiles in the currently active study
    """
    try:
        sql_text = "SELECT * FROM user_day_profile ORDER BY profile_name COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profiles.__name__, Exception, e)
        return error


def get_monthly_profiles():
    """
    Return data on all monthly profiles in the currently active study
    """
    try:
        sql_text = "SELECT * FROM user_month_profile ORDER BY profile_name COLLATE NOCASE;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profiles.__name__, Exception, e)
        return error


def get_hourly_profile(profile_name):
    """
    Return data on a specific hourly profile based on profile name
    :param profile_name: the name of the profile to look up
    """
    try:
        sql_text = "SELECT * FROM user_hour_profile WHERE profile_name = \"%s\";" % profile_name
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_hourly_profile.__name__, Exception, e)
        return error


def get_daily_profile(profile_name):
    """
    Return data on a specific daily profile based on the profile name
    :param profile_name: the name of the profile to look up
    """
    try:
        sql_text = "SELECT * FROM user_day_profile WHERE profile_name = \"%s\";" % profile_name
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_daily_profile.__name__, Exception, e)
        return error


def get_monthly_profile(profile_name):
    """
    Return data for a specific monthly profile based on the profile name
    :param profile_name: the name of the monthly profile to be looked up
    """
    try:
        sql_text = "SELECT * FROM user_month_profile WHERE profile_name = \"%s\";" % profile_name
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_monthly_profile.__name__, Exception, e)
        return error


def add_hourly_profile(properties):
    """
    Add a new hourly profile to the currently active study database
    :param properties: the properties of the new profile to be added
    """
    try:
        # Split out and validate properties
        p0 = properties[0]   # name
        p1 = properties[1]   # h00
        p2 = properties[2]   # h01
        p3 = properties[3]   # h02
        p4 = properties[4]   # h03
        p5 = properties[5]   # h04
        p6 = properties[6]   # h05
        p7 = properties[7]   # h06
        p8 = properties[8]   # h07
        p9 = properties[9]   # h08
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
        sql_text = "SELECT * FROM user_hour_profile WHERE profile_name=\"%s\";" % p0.replace("'", "")
        result = query_string(sql_text)
        logger.debug(str(result))

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        #if result is [] or result is "" or result is None:
        if len(result) == 0:
            sql_text = "INSERT INTO user_hour_profile (profile_name,h01,h02,h03,h04,h05,h06,h07,h08,h09,h10,h11," \
                       "h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24) VALUES (\"%s\",%s,%s,%s,%s,%s,%s,%s,%s," \
                       "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);" % (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9,
                                                                              p10, p11, p12, p13, p14, p15, p16, p17,
                                                                              p18, p19, p20, p21, p22, p23, p24)
        else:
            sql_text = "UPDATE user_hour_profile SET profile_name=\"%s\",h01=%s,h02=%s,h03=%s,h04=%s,h05=%s,h06=%s," \
                       "h07=%s,h08=%s,h09=%s,h10=%s,h11=%s,h12=%s,h13=%s,h14=%s,h15=%s,h16=%s,h17=%s,h18=%s,h19=%s," \
                       "h20=%s,h21=%s,h22=%s,h23=%s,h24=%s WHERE profile_name=\"%s\";" % (p0, p1, p2, p3, p4, p5, p6,
                                                                                          p7, p8, p9, p10, p11, p12,
                                                                                          p13, p14, p15, p16, p17, p18,
                                                                                          p19, p20, p21, p22, p23, p24,
                                                                                          p0)
        result = query_string(sql_text)
        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_hourly_profile.__name__, Exception, e)
        return error


def add_daily_profile(properties):
    """
    Add a new daily profile to the currently active study database
    :param properties: The properties of the new profile to be added as a dict
    """
    try:
        # Split out and validate properties
        p0 = properties[0]   # name
        p1 = properties[1]   # mon
        p2 = properties[2]   # tue
        p3 = properties[3]   # wed
        p4 = properties[4]   # thu
        p5 = properties[5]   # fri
        p6 = properties[6]   # sat
        p7 = properties[7]   # sun

        # Check if profile already exists
        sql_text = "SELECT * FROM user_day_profile WHERE profile_name=\"%s\";" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        if len(result) == 0:
            sql_text = "INSERT INTO user_day_profile (profile_name,mon,tue,wed,thu,fri,sat,sun) VALUES ( \
                \"%s\",%s,%s,%s,%s,%s,%s,%s)" % \
                (p0, p1, p2, p3, p4, p5, p6, p7)
        else:
            sql_text = "UPDATE user_day_profile SET profile_name=\"%s\",mon=%s,tue=%s,wed=%s,thu=%s,fri=%s,sat=%s," \
                       "sun=%s WHERE profile_name=\"%s\";" % \
                (p0, p1, p2, p3, p4, p5, p6, p7, p0)
        result = query_string(sql_text)

        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_daily_profile.__name__, Exception, e)
        return error


def add_monthly_profile(properties):
    """
    Add a new monthly profile to the currently active database
    :param properties: the properties of the new profile to be added
    """
    try:
        # Split out and validate properties
        p0 = properties[0]   # name
        p1 = properties[1]   # jan
        p2 = properties[2]   # feb
        p3 = properties[3]   # mar
        p4 = properties[4]   # apr
        p5 = properties[5]   # may
        p6 = properties[6]   # jun
        p7 = properties[7]   # jul
        p8 = properties[8]   # aug
        p9 = properties[9]   # sep
        p10 = properties[10]   # oct
        p11 = properties[11]   # nov
        p12 = properties[12]   # dec

        # Check if profile already exists
        sql_text = "SELECT * FROM user_month_profile WHERE profile_name=\"%s\";" % p0.replace("'", "")
        result = query_string(sql_text)

        if isinstance(result, str):
            raise Exception("Problem saving profile: %s" % result)

        if len(result) == 0:
            sql_text = "INSERT INTO user_month_profile (profile_name,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec) \
                VALUES ( \"%s\",%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)" % \
                (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12)
        else:
            sql_text = "UPDATE user_month_profile SET profile_name=\"%s\",jan=%s,feb=%s,mar=%s,apr=%s,may=%s,jun=%s," \
                       "jul=%s,aug=%s,sep=%s,oct=%s,nov=%s,dec=%s WHERE profile_name=\"%s\";" % \
                (p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p0)
        result = query_string(sql_text)
        if len(result) == 0:
            return None
        else:
            raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(add_monthly_profile.__name__, Exception, e)
        return error


def delete_hourly_profile(profile_name):
    """
    Remove an existing hourly profile from the currently active database
    :param profile_name: the name of the hourly profile to be removed
    """
    try:
        sql_text = "DELETE FROM user_hour_profile WHERE profile_name=\"%s\";" % profile_name
        result = query_string(sql_text)
        if result is None:
            return None
        else:
            if len(result) == 0:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(delete_hourly_profile.__name__, Exception, e)
        return error


def delete_daily_profile(profile_name):
    """
    Remove an existing daily profile from the currently active project database
    :param profile_name: the name of the daily profile to be removed
    """
    try:
        sql_text = "DELETE FROM user_day_profile WHERE profile_name=\"%s\";" % profile_name
        result = query_string(sql_text)
        if result is None:
            return None
        else:
            if len(result) == 0:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(delete_daily_profile.__name__, Exception, e)
        return error


def delete_monthly_profile(profile_name):
    """
    Remove an exiting monthly profile from the currently active project database
    :param profile_name: the name of the monthly profile to be removed
    """
    try:
        sql_text = "DELETE FROM user_month_profile WHERE profile_name=\"%s\";" % profile_name
        result = query_string(sql_text)
        if result is None:
            return None
        else:
            if len(result) == 0:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(delete_monthly_profile.__name__, Exception, e)
        return error


##################################################
##########       CALCULATIONS        #############
##################################################


def get_lasport_scenarios():
    """
    Return a list of LASPORT scenarios from the currently active database
    """
    try:
        sql_text = "SELECT DISTINCT scenario FROM default_lasport_road;"
        result = query_string(sql_text)
        if len(result) > 0:
            return result
        else:
            if result is []:
                return None
            else:
                raise Exception(result)
    except Exception as e:
        error = alaqsutils.print_error(get_lasport_scenarios.__name__, Exception, e)
        return error


def inventory_source_list(inventory_path, source_type):
    """
    Return a list of all sources (shape layers) from the currently active project database. This is used by the results
    UI at the very least.
    :param inventory_path: a path to the current study output file
    :param source_type: the type of shape files to be returned
    """
    try:
        conn = sqlite.connect(inventory_path)
        cur = conn.cursor()
        if source_type == "stationary":
            cur.execute("SELECT source_id FROM shapes_point_sources;")
        elif source_type == "area":
            cur.execute("SELECT source_id FROM shapes_area_sources;")
        elif source_type == "parking":
            cur.execute("SELECT parking_id FROM shapes_parking;")
        elif source_type == "roadway":
            cur.execute("SELECT roadway_id FROM shapes_roadways;")
        elif source_type == "gates":
            cur.execute("SELECT gate_id FROM shapes_gates;")
        elif source_type == "taxiway":
            cur.execute("SELECT taxiway_id FROM shapes_taxiways;")
        elif source_type == "runway":
            cur.execute("SELECT runway_id FROM shapes_runways;")
        elif source_type == "runway":
            cur.execute("SELECT track_id FROM shapes_tracks;")
        else:
            return None
        source_list = cur.fetchall()

        conn.close()
        if isinstance(source_list, str):
            raise Exception(source_list)
        elif source_list is None or source_list == [] or not (type(source_list) == type([])):
            return None
        else:
            source_list_ = []
            for s_ in source_list:
                if type(s_) == type(()) and len(s_):
                    if not (s_[0] is None):
                        source_list_.append(s_)
            return source_list_

    except Exception as e:
        error = alaqsutils.print_error(inventory_source_list.__name__, Exception, e)
        return error

def inventory_time_series(inventory_path):
    return query_text(inventory_path, "SELECT * FROM tbl_InvTime;")

def inventory_calc_taxiway_emissions(inventory_path, taxiway_name):
    """
    Calculate taxiway emissions for a specific source based on the source name and time period
    :param inventory_path: path to the alaqs output file being displayed/examined
    :param taxiway_name: the name of the source to be reviewed
    """
    try:
        if taxiway_name == "" or taxiway_name is None:
            return None

        conn = sqlite.connect(inventory_path)
        curs = conn.cursor()

        # Get data for the gate
        sql_text = "SELECT * FROM shapes_taxiways WHERE taxiway_id=\"%s\";" % taxiway_name
        curs.execute(sql_text)
        taxiway_data = curs.fetchall()

        if isinstance(taxiway_data, str):
            raise Exception(taxiway_data)
        elif taxiway_data is None or taxiway_data == []:
            return None
        else:
            taxiway_dict = alaqsutils.dict_taxiway_data(taxiway_data[0])

            taxiway_length_km = get_linestring_length(curs, "shapes_taxiways", "taxiway_id", taxiway_name)
            taxiway_time = taxiway_length_km / taxiway_dict['speed'] * 3600       # *3600 to go from hours to seconds

            # Get the time series for this inventory
            curs.execute("SELECT * FROM tbl_InvTime;")
            inventory_time_series = curs.fetchall()

            emission_profile = []

            # Loop through the time series...
            for interval in inventory_time_series:

                co = 0
                hc = 0
                nox = 0
                sox = 0
                pm10 = 0
                p1 = 0
                p2 = 0

                # Make details of the interval into a dict
                interval_data = alaqsutils.dict_interval_data(interval)

                # Fetch movements that use this taxiway for this time period
                movements = get_movements_datetime_between(inventory_path, interval_data['interval_start'],
                                                           interval_data['interval_end'])

                if movements is None or movements == []:
                    pass
                else:
                    for movement_data in movements:
                        movement_dict = alaqsutils.dict_movement(movement_data)
                        taxiway_route = movement_dict['taxi_route']

                        # Fetch taxi route data for this movement
                        if taxiway_route == "":
                            # We build the taxiway route name
                            taxiway_route = "%s/%s/%s/%s" % (movement_dict['gate'], movement_dict['runway'],
                                                             movement_dict['departure_arrival'], "1")

                        sql_text = "SELECT * FROM user_taxiroute_taxiways WHERE route_name=\"%s\";" % taxiway_route
                        taxi_route_data = query_string(sql_text)

                        if taxi_route_data is []:
                            # Then no route is defined for this runway/gate combination
                            alaqsutils.print_error("No taxiway route for movement")
                        else:
                            # Else lets see if this taxi route is relevant for us now...
                            taxi_route_dict = alaqsutils.dict_taxiroute_data(taxi_route_data[0])
                            sequence_data = taxi_route_dict['sequence'].split(',')
                            if taxiway_name in sequence_data:

                                # Get details of the aircraft
                                sql_text = "SELECT * FROM default_aircraft WHERE icao=\"%s\";" % movement_dict['aircraft']
                                aircraft_data = query_string(sql_text)
                                aircraft_dict = alaqsutils.dict_aircraft(aircraft_data[0])

                                # Get details of the engine
                                sql_text = "SELECT * FROM default_aircraft_engine_ei WHERE engine_name=\"%s\" AND mode=\"TX\";" \
                                           % movement_dict['engine_name']
                                engine_data = query_string(sql_text)
                                try:
                                    engine_dict = alaqsutils.dict_engine(engine_data[0])
                                    co += float(taxiway_time) * float(engine_dict['fuel_kg_sec']) * float(engine_dict['co_ei']) * float(aircraft_dict['engine_count'])
                                    hc += float(taxiway_time) * float(engine_dict['fuel_kg_sec']) * float(engine_dict['hc_ei']) * float(aircraft_dict['engine_count'])
                                    nox += float(taxiway_time) * float(engine_dict['fuel_kg_sec']) * float(engine_dict['nox_ei']) * float(aircraft_dict['engine_count'])
                                    sox += float(taxiway_time) * float(engine_dict['fuel_kg_sec']) * float(engine_dict['sox_ei']) * float(aircraft_dict['engine_count'])
                                    pm10 += float(taxiway_time) * float(engine_dict['fuel_kg_sec']) * float(engine_dict['pm10_ei']) * float(aircraft_dict['engine_count'])
                                except:
                                    pass

                                # TODO add queuing emissions for departures

                record = [interval_data['interval_start'], co, hc, nox, sox, pm10, p1, p2]
                emission_profile.append(record)

        conn.close()

        return emission_profile
    except Exception as e:
        error = alaqsutils.print_error(inventory_calc_taxiway_emissions.__name__, Exception, e)
        return error


def get_arr_dep_from_movement(movement_dict):
    """
    Calculate whether a movement is an arrival or departure based on datetime and block time
    :param movement_dict: a dict containing complete data on the movement
    """
    try:
        runway_time = datetime.datetime.strptime(movement_dict['runway_time'], "%Y-%m-%d %h:%m:%s")
        block_time = datetime.datetime.strptime(movement_dict['block_time'], "%Y-%m-%d %h:%m:%s")
        if runway_time < block_time:
            arr_dep = "A"
        else:
            arr_dep = "D"
        return arr_dep
    except Exception as e:
        error = alaqsutils.print_error(get_arr_dep_from_movement.__name__, Exception, e)
        return error


def get_movements_for_gate(inventory_path, gate_name, start_time, end_time):
    """
    Return movements for a specific gate for a given time period
    :param inventory_path: path to the alaqs output file being reviewed
    :param gate_name: name of the gate being investigated
    :param start_time: the start time of the interval
    :param end_time: the end time of the interval
    """
    try:
        sql_query = "SELECT * FROM user_aircraft_movements WHERE gate=\"%s\" AND " \
                    "datetime(\"runway_time\") > datetime(\"%s\") " \
                    "AND datetime(\"runway_time\") < datetime(\"%s\");" % (gate_name, start_time, end_time)
        conn = sqlite.connect(inventory_path)
        curs = conn.cursor()

        curs.execute(sql_query)
        movement_data = curs.fetchall()

        if isinstance(movement_data, str):
            raise Exception("Problem querying movements: %s" % movement_data)
        elif movement_data is None or movement_data == []:
            return None
        else:
            # We have movement data!
            return movement_data
    except Exception as e:
        error = alaqsutils.print_error(get_movements_datetime_between.__name__, Exception, e)
        return error


def get_movements_datetime_between(inventory_path, start_time, end_time):
    """
    Return movements that have a datetime between two values
    :param inventory_path: path to the results file
    :param start_time: a datetime stamp in format YYYY-MM-DD HH:MM:SS
    :type start_time: str
    :param end_time: a datetime stamp in format YYYY-MM-DD HH:MM:SS
    :type end_time: str
    :return: movements as a dict
    """
    try:
        sql_query = "SELECT * FROM user_aircraft_movements WHERE datetime(\"runway_time\") > datetime(\"%s\") " \
                    "AND datetime(\"runway_time\") < datetime(\"%s\");" % (start_time, end_time)
        conn = sqlite.connect(inventory_path)
        curs = conn.cursor()

        curs.execute(sql_query)
        movement_data = curs.fetchall()
        if isinstance(movement_data, str):
            raise Exception("Problem querying movements: %s" % movement_data)
        elif movement_data is None or movement_data == []:
            return None
        else:
            return movement_data
    except Exception as e:
        error = alaqsutils.print_error(get_movements_datetime_between.__name__, Exception, e)
        return error


def get_geometry_as_text(table_name, feature_id, feature_name, epsg_id):
    """
    This function returns the geometry of a feature from the database as a
    :param table_name:
    :param feature_id:
    :param feature_name:
    :return:
    """
    try:
        result = query_string('SELECT ST_AsText(ST_Transform(geometry, %s)) FROM %s WHERE %s=\"%s\";' %
                              (epsg_id, table_name, feature_id, feature_name))
        return result[0][0]
    except Exception as e:
        alaqsutils.print_error(get_geometry_as_text.__name__, Exception, e)
        return None


def get_linestring_length(geometry, epsg_id):
    """
    Calculates the length of a linear feature in meters using ellipsoidal projections.

    :param geometry: a WKT formatted shape geometry as a string
    :param epsg_id: the projection of the WKT being passed (4326=decimal, 3857=meters) as a string
    :return: length: in meters
    :rtype: float
    """
    try:
        result = query_string("SELECT ST_Length(ST_Transform(ST_LineFromText('%s', %s), 3857));") % (geometry, epsg_id)
        length = float(result[0][0]) / 1000
        return length
    except Exception as e:
        alaqsutils.print_error(get_linestring_length.__name__, Exception, e)
        return None


def get_polygon_area(geometry):
    """
    Calculates the area of a polygon feature in meters

    :param table_name: the name of the table containing the shape's geometry
    :param feature_name: the name of the feature whose length is required
    :return: area: in meters
    :rtype: float
    """
    try:
        result = []
        area = result[0][0]
        return area
    except Exception as e:
        alaqsutils.print_error(get_polygon_area.__name__, Exception, e)
        return None


def get_intersection_length(geometry_one, geometry_two):
    """
    This function returns the length of the intersection of two geometry polygons. For example, consider the below two
    overlapping polygons (A) and (B):

            ---------
            |   B   |
        ---------   |
        |   | C |   |
        |   |---|---|
        |   A   |
        ---------
        geometry_one (A): 'POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))'
        geometry_two (B): 'POLYGON ((1 1, 3 1, 3 3, 1 3, 1 1))'
        Intersection (C): 'POLYGON((1 2, 2 2, 2 1, 1 1, 1 2))'

    The function would return the area of the intersection, shape C. Note that this function returns the PLANAR area of
    the intersection, not the ellipsoidal (e.g. use_spheroid) area. At time of writing, the use_spheroid option is not
    available in spatialite.
    :param geometry_one: the first geometry as a BLOB
    :param geometry_two: the second geometry as a BLOB
    :return: the area of the intersection
    """
    query_string = "SELECT ST_Length(ST_Intersection(ST_PolygonFromText('%s', 4326), ST_LineFromText('%s', 4326)), 1);"


def get_intersection_area(geometry_one, geometry_two):
    """
    This function returns the area of the intersection of two geometry polygons. For example, consider the below two
    overlapping polygons (A) and (B):
            ---------
            |   B   |
        ---------   |
        |   | C |   |
        |   |---|---|
        |   A   |
        ---------
        geometry_one (A): 'POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))'
        geometry_two (B): 'POLYGON ((1 1, 3 1, 3 3, 1 3, 1 1))'
        Intersection (C): 'POLYGON((1 2, 2 2, 2 1, 1 1, 1 2))'
    The function would return the area of the intersection, shape C. Note that this function returns the PLANAR area of
    the intersection, not the ellipsoidal (e.g. use_spheroid) area. At time of writing, the use_spheroid option is not
    available in spatialite.
    :param geometry_one: the first geometry as a BLOB
    :param geometry_two: the second geometry as a BLOB
    :return: the area of the intersection
    """
    pass


def make_wkt_bounding_box(d):
    """
    This function takes a dict that defines two opposite corners of a bounding box (south-west and north-east corners)
    and uses these to generate a bounding box in Well-known Text. This is returned as a string
    :param d: dict of dimensions x_min, y_min, x_max,  y_max.
    :return: the percentage of th shape that sits within the bounding box.
    """
    try:
        bbox = "POLYGON ((%s %s, %s %s, %s %s, %s %s, %s %s))" % (d['x_min'], d['y_min'], d['x_min'], d['y_max'],
                                                                  d['x_max'], d['y_max'], d['x_max'], d['y_min'],
                                                                  d['x_min'], d['y_min'])
        return bbox
    except Exception as e:
        pass

# if __name__ == "__main__":
#     # Use this section for unit testing
#
#     data = get_line_length("shapes_roadways", "roadway_id", "M5")
#     # fix_print_with_import
#     print(data)
#     data = get_polygon_area("shapes_gates", "gate_id", "Gate01")
#     # fix_print_with_import
#     print(data)