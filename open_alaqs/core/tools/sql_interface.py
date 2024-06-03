import sqlite3 as sqlite
from typing import Any, Optional, Union

from qgis.utils import spatialite_connect

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)


def connect(database_path: str) -> sqlite.Connection:
    """
    Creates a connection to a SQLite database.

    :param database_path:
    :type database_path: str
    :return curs: a cursor object for the database provided
    :rtype: object
    """
    try:
        conn = spatialite_connect(database_path)
        # always return bytestrings
        conn.text_factory = str
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
        except Exception:
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
    except Exception:
        pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    return found


class SqlExpression:
    def __init__(self, expression: str, *values: Any) -> None:
        self.expression = expression
        self.values = values

    def __str__(self) -> str:
        return self.expression


class get_db_connection:
    """
    Executes a code block with a connection to SQLite database.

    Example:
    ```
    with get_db_connection(sqlite_filename) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
    ```
    """

    def __init__(self, sqlite_filename: str) -> None:
        self.sqlite_filename = sqlite_filename
        self.conn = None

    def __enter__(self) -> sqlite.Connection:
        self.conn = spatialite_connect(self.sqlite_filename)

        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.conn:
            self.conn.close()

        return exc_type is None


def db_execute_sql(
    db_filename: str,
    sql: str,
    params: Optional[list] = None,
    fetchone: bool = True,
) -> Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
    """Executes SQL statement and returns the resulting row.

    Args:
        db_filename (str): filename of the database
        sql (str): SQL query statement
        params (Optional[list], optional): Optional list of parameters that will replace the `?` placeholders in the SQL. Defaults to None.
        fetchone (bool, optional): Fetch only one row or all rows. Defaults to True.

    Returns:
        dict[str, Any] | list[dict[str, Any] | None: A single row as a dict, multiple rows if `fetchone=False`, or None if no rows available.
    """
    params = params or []

    with get_db_connection(db_filename) as conn:
        conn.text_factory = str
        conn.row_factory = sqlite.Row

        cur = conn.cursor()
        cur.execute(sql, params)

        conn.commit()

        if fetchone:
            result = cur.fetchone()

            if result is None:
                return None
            else:
                return dict(result)
        else:
            return [dict(r) for r in cur.fetchall()]


def perform_sql(
    db_filename: str,
    sql: str,
    params: Optional[list] = None,
) -> None:
    """Performs SQL statement and returns None.

    Args:
        db_filename (str): filename of the database
        sql (str): SQL query statement
        params (Optional[list], optional): Optional list of paramaeters that will replace the `?` placeholders in the SQL. Defaults to None.
    """
    if not params:
        params = []

    with get_db_connection(db_filename) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)

        conn.commit()


def quote_identifier(identifier: str) -> str:
    """Quotes identifiers, e.g. table or column names."""
    return f'''"{identifier.replace('"', '""')}"'''


def db_update_table(
    db_filename: str,
    table_name: str,
    attribute_values: dict[str, Any],
    where_values: dict[str, Any],
) -> list[dict[str, Any]]:
    attribute_expression_pairs = []
    values = []

    for attr_name, attr_value in attribute_values.items():
        if isinstance(attr_value, SqlExpression):
            expression = attr_value.expression
            values += attr_value.values
        else:
            expression = "?"
            values.append(attr_value)

        attribute_expression_pairs.append(
            f"{quote_identifier(attr_name)} = {expression}"
        )

    values_str = ", ".join(attribute_expression_pairs)
    sql = f"""
        UPDATE {quote_identifier(table_name)}
        SET {values_str}
    """

    if where_values:
        where_expression_pairs = []

        for attr_name, attr_value in where_values.items():
            if isinstance(attr_value, SqlExpression):
                expression = attr_value.expression
                values += attr_value.values
            else:
                expression = "?"
                values.append(attr_value)

            where_expression_pairs.append(
                f"{quote_identifier(attr_name)} = {expression}"
            )

        where_values_str = " AND ".join(where_expression_pairs)

        sql += f"""
            WHERE {where_values_str}
        """

    return db_execute_sql(db_filename, sql, values, False)


def insert_into_table(
    db_filename: str,
    table_name: str,
    records: Union[dict[str, Any], list[dict[str, Any]]],
) -> list[sqlite.Row]:
    attr_names = []
    rows = []
    values = []

    if not isinstance(records, list):
        records = [records]

    for record_idx, record in enumerate(records):
        attr_expressions = []

        for attr_name, attr_value in record.items():
            if record_idx == 0:
                attr_names.append(quote_identifier(attr_name))

            if isinstance(attr_value, SqlExpression):
                expression = attr_value.expression
                values += attr_value.values
            else:
                expression = "?"
                values.append(attr_value)

            attr_expressions.append(expression)

        attr_expressions_str = ", ".join(attr_expressions)
        rows.append(f"({attr_expressions_str})")

    attr_names_str = ", ".join(attr_names)
    rows_str = ", ".join(rows)
    sql = f"""
        INSERT INTO {quote_identifier(table_name)} (
            {attr_names_str}
        )
        VALUES {rows_str}
    """

    return db_execute_sql(db_filename, sql, values)
