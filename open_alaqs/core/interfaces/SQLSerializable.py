from typing import Any, Literal, Optional, TypedDict, cast

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import sql_interface

logger = get_logger(__name__)


class GeometryColumn(TypedDict):
    column_name: str
    SRID: int
    geometry_type: Literal["POLYGON"]
    geometry_type_dimension: Literal[2, 3]


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
        geometry_columns: Optional[list[GeometryColumn]] = None,
    ) -> None:

        self._db_path = db_path_string
        self._table_name = table_name_string
        self._table_columns = table_columns_type_dict
        # TODO OPENGIS.ch: make the geometry_columns argument a regular member of "table_columns_type_dict"
        self._geometry_columns = geometry_columns or []
        self._entries = {}

        assert self._db_path
        assert self._table_name
        assert isinstance(table_columns_type_dict, dict)

        self._primary_key = primary_key or self._guess_pk_name()

        assert self._primary_key

    def getDatabasePath(self) -> str:
        return self._db_path

    def setEntry(self, key: Any, value_object: dict[str, Any]) -> None:
        if self.hasEntry(key):
            logger.warning(
                "Already found entry with key '%s'. Replacing existing entry."
                % (str(key))
            )

        self._entries[key] = value_object

    def hasEntry(self, key: Any) -> bool:
        return key in self._entries

    def getEntries(self) -> dict[str, Any]:
        return self._entries

    def serialize(self, path: str = "") -> bool:
        db_path = path or self._db_path

        try:
            self._recreate_table(db_path)

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

    def deserialize(self) -> None:
        # all usual sql columns
        columns = list(
            map(lambda c: sql_interface.quote_identifier(c), self._table_columns.keys())
        )

        for column_def in self._geometry_columns:
            columns.append(
                f'AsText({sql_interface.quote_identifier(column_def["column_name"])}) AS geometry'
            )

        result = cast(
            list,
            sql_interface.db_execute_sql(
                self._db_path,
                f"""
                    SELECT {", ".join(columns)}
                    FROM {sql_interface.quote_identifier(self._table_name)}
                """,
                fetchone=False,
            ),
        )

        for row in result:
            assert self._primary_key in row.keys()

            self.setEntry(row[self._primary_key], dict(row))

    def _guess_pk_name(self) -> Optional[str]:
        for key in self._table_columns:
            if "PRIMARY KEY".lower() in self._table_columns[key].lower():
                return key

        return None

    def _recreate_table(self, db_path: str = "") -> None:
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
                [
                    self._table_name,
                    geom_col_definition["column_name"],
                    geom_col_definition["SRID"],
                    geom_col_definition["geometry_type"],
                    geom_col_definition["geometry_type_dimension"],
                ],
            )

        logger.debug("Table '%s' created", (self._table_name))
