import sys
import os
import struct
import logging
import sqlite3 as sqlite

logger = logging.getLogger("alaqs.%s" % __name__)


def connect(database_path: str) -> sqlite.Connection:
    """
    Creates a connection to a SQLite database.

    :param database_path:
    :type database_path: str
    :return curs: a cursor object for the database provided
    :rtype: object
    """
    try:
        conn = sqlite.connect(database_path)
        # always return bytestrings
        conn.text_factory = str
        conn.enable_load_extension(True)

        spatial_dll_filename = "mod_spatialite.dll"
        if 8 * struct.calcsize("P") == 64:
            spatial_dll_folder = os.path.abspath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                             "spatialite-4.0.0-DLL"))
        else:
            raise Exception("64bit installation of QGIS is now supported. "
                            "Please try to use the 64bit installation.")

        if spatial_dll_folder not in sys.path:
            sys.path.append(spatial_dll_folder)
        if spatial_dll_folder not in os.environ['PATH']:
            os.environ['PATH'] = spatial_dll_folder + os.pathsep + os.environ[
                'PATH']

        conn.execute('SELECT load_extension("%s")' % spatial_dll_filename)

        return conn
    except Exception as e:
        msg = "Connection could not be established: %s" % e
        raise Exception(msg)


def query_text(database_path, sql_text):
    """
    Execute a query against a given SQLite database
    :param database_path: the path to the database that is being queried
    :param sql_text: the SQL text to be executed
    :return data: the result of the query
    :raise ValueError: if database returns a string (error) instead of list
    """

    # Create a blank connection object
    conn = None

    try:
        # Create a connection
        conn = connect(database_path)
        conn.text_factory = str
        curs = conn.cursor()
        # Execute the query
        curs.execute(sql_text)
        # Collect the result
        data = curs.fetchall()
        # Process the result
        if isinstance(data, str):
            raise TypeError("Query returned an error: %s" % data)
        elif data is None or data == []:
            # logger.debug("Query successful")
            return True
        else:
            # logger.debug("Query successful")
            return data
    except Exception as e:
        logger.error("Query could not be completed: %s" % e)
        return None
    finally:
        # Commit any changes the query performed and close the connection. This
        # is in a try-except block in case there was no connection established
        # and no query to commit. Without this, an error will be raised
        try:
            conn.commit()
            conn.close()
        except Exception as e:
            pass


def pd_query_text(database_path, sql_text):
    """
    Execute a query against a given SQLite database using Pandas
    :param database_path: the path to the database that is being queried
    :param sql_text: the SQL text to be executed
    :return data: the result of the query
    :raise ValueError: if database returns a string (error) instead of list
    """
    import pandas as pd

    try:
        # Create a connection
        conn = sqlite.connect(database_path)
        conn.text_factory = str
        data = pd.read_sql(sql_text, conn)
        if not data.empty:
            return data
        elif data.empty:
            return True
        else:
            raise TypeError("Query returned an error: %s" % data)
    except Exception as e:
        logger.error("Query could not be completed: %s" % e)
        return None


def query_insert_many(database_path, sql_text, data_list):
    """
    This function is used to insert many records into the database concurrently.
    It is faster to use this function than to make multiple insert queries.

    :param database_path: the path of the database to be worked with
    :param sql_text: the SQL query to be run in the correct (?,?,?,...) format
    :param data_list: a list of data lists to be inserted
    :return: bool of success
    """
    conn = None
    try:
        # Create a connection
        conn = connect(database_path)
        curs = conn.cursor()
        # Execute the query
        curs.executemany(sql_text, data_list)
        conn.commit()
        # logger.debug("Query successful")
        return True
    except Exception as e:
        logger.error(e)
        return "Query could not be completed: %s" % e
    finally:
        try:
            conn.commit()
            conn.close()
        except Exception as e:
            pass


def hasTable(database_path, table_name):
    """
    Check if a database at path
    :param database_path: the path to the database that is being queried
    :param table_name: the table name that is searched for
    :return bool: table found or not
    """
    found = False
    conn = None

    try:
        # Create a connection
        conn = connect(database_path)
        curs = conn.cursor()
        # Execute the query
        sql_text = "SELECT * FROM %s" % (table_name)
        curs.execute(sql_text)
        # Collect the result
        data = curs.fetchall()
        # Process the result
        if not isinstance(data, str):
            found = True
    except Exception as e:
        pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception as e:
            pass

    return found
