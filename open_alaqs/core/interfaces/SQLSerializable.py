import re
from collections import OrderedDict
from typing import Optional

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import conversion, sql_interface

logger = get_logger(__name__)


class SQLSerializable:
    """
    Class that serves as a container for data stored in a database.
    The class provides methods to serialize and deserialize objects to the database
    """

    def __init__(
        self,
        db_path_string: str,
        table_name_string: str,
        table_columns_type_dict: dict[str, str],
        primary_key: str = "",
        geometry_columns: list[Optional[str]] = None,
    ) -> None:

        self._db_path = db_path_string
        self._table_name = table_name_string
        self._table_columns = table_columns_type_dict
        self._geometry_columns = geometry_columns or []
        self._entries = {}

        assert self._db_path
        assert self._table_name
        assert isinstance(table_columns_type_dict, dict)

        self._primary_key = primary_key or self._guess_pk()

        assert self._primary_key

    def _guess_pk(self) -> Optional[str]:
        for key in self._table_columns:
            if "PRIMARY KEY".lower() in self._table_columns[key].lower():
                return key

        return None

    def getDatabasePath(self) -> str:
        return self._db_path

    def setEntry(self, key, value_object):
        if self.hasEntry(key):
            logger.warning(
                "Already found entry with key '%s'. Replacing existing entry."
                % (str(key))
            )
        self._entries[key] = value_object

    def hasEntry(self, key):
        if key in self._entries:
            return True
        return False

    def getEntries(self):
        return self._entries

    def serialize(self, path: str = "") -> bool:
        db_path = path or self._db_path

        try:
            self.create_table(db_path)

            result = sql_interface.insert_into_table(
                db_path,
                self._table_name,
                [self.getEntries()[key] for key in self.getEntries()],
            )

            logger.debug(
                "Inserted rows to table '%s' in database '%s'. Result was '%s'."
                % (self._table_name, db_path, str(result))
            )
        except Exception as e:
            logger.error(
                "Failed to serialize the class '%s' with error '%s'"
                % (self.__class__.__name__, str(e))
            )
            return False

        return True

    def deserialize(self):
        if not self._table_columns or not self._table_name:
            logger.error(
                "Did not find table column ('%s') or table name definition ('%s')"
                % (str(self._table_columns), str(self._table_name))
            )
            return False
        if not isinstance(self._table_columns, OrderedDict):
            logger.error(
                "Expected type for table columns is '%s' but got '%s'."
                % (str(type(OrderedDict())), type(self._table_columns))
            )
            return False

        # all usual sql columns
        columns_ = list(self._table_columns.keys())
        # all spatialite sql columns
        if self._geometry_columns:
            geometry_column_names_ = []
            for k_ in self._geometry_columns:
                if "column_name" in k_:
                    geometry_column_names_.append(
                        "AsText(%s)" % (str(k_["column_name"]))
                    )
            columns_.extend(geometry_column_names_)

        sql_text = "SELECT %s FROM %s;" % (",".join(columns_), self._table_name)
        # result = SQLInterface.pd_query_text(self._db_path, sql_text)
        result = sql_interface.query_text(self._db_path, sql_text)

        if isinstance(result, str):
            raise Exception(result)
        elif isinstance(result, bool):
            logger.info(
                "Table '%s' in database '%s' is empty."
                % (self._table_name, self._db_path)
            )
        elif result is None:
            logger.error(
                "Deserialization of database '%s' and table '%s' failed. Either file not found or table headers do not match expected headers."
                % (self._db_path, self._table_name)
            )
        else:
            for row in result:
                values_dict = self.result_to_dict(columns_, row)
                if values_dict is None:
                    logger.error(
                        "Deserialization failed. Database '%s' with table '%s' returned dimension %i but expected %i."
                        % (self._db_path, self._table_name, len(row), len(columns_))
                    )
                else:
                    if self._primary_key not in values_dict:
                        logger.error(
                            "Primary key '%s' is not contained in returned values. Database is '%s' with table '%s' and requested columns '%s'."
                            % (
                                self._primary_key,
                                self._db_path,
                                self._table_name,
                                str(columns_),
                            )
                        )
                    else:
                        try:
                            # correct for NULL values
                            for key in values_dict:
                                if isinstance(values_dict[key], str):
                                    if values_dict[key] == "NULL":
                                        values_dict[key] = None

                            # fix int/float conversion when reading from SQL DB
                            for key in values_dict:
                                if values_dict[key] is None:
                                    continue
                                else:
                                    if (
                                        key in self._table_columns
                                        and self._table_columns[key].lower()
                                        in ["decimal"]
                                    ):
                                        values_dict[key] = conversion.convertToFloat(
                                            values_dict[key]
                                        )
                            self.setEntry(
                                values_dict[self._primary_key],
                                self.getObject(values_dict),
                            )

                        except Exception as exc_:
                            logger.error(exc_)
            # logger.info("Deserialized %i rows from table '%s' in database '%s' " % (len(result), self._table_name, self._db_path))

    @staticmethod
    def result_to_dict(columns, data):
        if len(data) == len(columns):
            data_dict = OrderedDict()
            for col_index, col_name in enumerate(columns):
                # convert AsText(bla) to bla
                geometry_type_ = re.search(r"AsText\((.+?)\)", col_name)
                if geometry_type_:
                    data_dict[geometry_type_.group(1)] = data[col_index]
                else:
                    data_dict[col_name] = data[col_index]
            return data_dict

        return None

    def create_table(self, db_path: str = "") -> None:
        """
        Create a new table
        :param path_: database path
        :raise ValueError or Exception: if the query generates a string response (an error)
        """
        db_path = db_path or self._db_path

        col_definitions = []
        for col_name, col_definition in self._table_columns.items():
            assert col_definition

            col_definitions.append(
                f"{sql_interface.quote_identifier(col_name)} {col_definition}"
            )

        sql_interface.perform_sql(
            db_path,
            f"""
                DROP TABLE IF EXISTS {sql_interface.quote_identifier(self._table_name)}
            """,
        )

        col_definitions_sql = ", ".join(col_definitions)

        sql_interface.perform_sql(
            db_path,
            f"""
                CREATE TABLE {sql_interface.quote_identifier(self._table_name)} ({col_definitions_sql})
            """,
        )

        # add geometry columns
        for geom_col_definition in self._geometry_columns:
            assert geom_col_definition.get("column_name")
            assert geom_col_definition.get("SRID")
            assert geom_col_definition.get("geometry_type")
            assert geom_col_definition.get("geometry_type_dimension")

            sql_interface.perform_sql(
                db_path,
                """
                SELECT AddGeometryColumn(?, ?, ?, ?, ?)
                """,
                (
                    self._table_name,
                    geom_col_definition["column_name"],
                    geom_col_definition["SRID"],
                    geom_col_definition["geometry_type"],
                    geom_col_definition["geometry_type_dimension"],
                ),
            )

        logger.debug("Table '%s' created", (self._table_name))
