import re
from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools import conversion, sql_interface

logger = get_logger(__name__)


class SQLSerializable:
    """
    Class that serves as a container for data stored in a database.
    The class provides methods to serialize and deserialize objects to the database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string,
        table_columns_type_dict,
        primary_key="",
        geometry_columns: list = None,
    ):

        self._db_path = str(db_path_string)
        self._table_name = str(table_name_string)
        self._table_columns = OrderedDict()

        if not isinstance(table_columns_type_dict, dict):
            raise Exception(
                "Expected type '%s' for columns-type mapping but got type '%s'."
                % (str(type(OrderedDict())), type(table_columns_type_dict))
            )
        else:
            self._table_columns = table_columns_type_dict

        self._primary_key = primary_key
        if not self._primary_key:
            # try to identify the primary key from the columns types
            for key in self._table_columns:
                if "PRIMARY KEY".lower() in self._table_columns[key].lower():
                    self._primary_key = key
                    # print("Identified '%s' as primary key from column types." % (key))
        if not self._primary_key:
            raise Exception("Primary key is empty or not valid.")
        if self._primary_key not in self._table_columns:
            raise Exception(
                "Did not find primary key '%s' in dict for columns-type mapping."
                % (str(self._primary_key))
            )

        self._geometry_columns = geometry_columns
        if self._geometry_columns is None:
            self._geometry_columns = []

        self._entries = OrderedDict()

    def getDatabasePath(self):
        return self._db_path

    def getPrimaryKey(self):
        return self._primary_key

    def setEntry(self, key, value_object):
        if self.hasEntry(key):
            logger.warning(
                "Already found entry with key '%s'. Replacing existing entry."
                % (str(key))
            )
        self._entries[key] = value_object
        # raise NotImplementedError("Should have implemented method with name '%s'." %(self.setEntry.__name__))

    def removeEntry(self, key):
        return self._entries.pop(key, None)

    def hasEntry(self, key):
        if key in self._entries:
            return True
        return False

    def getEntry(self, key):
        if not self.hasEntry(key):
            return None
        else:
            return self._entries[key]

    def getEntries(self):
        return self._entries

    def serialize(self, path_=""):
        if not path_:
            path_ = self._db_path

        try:
            result = self.create_table(path_)
            if result is not True:
                raise Exception(
                    "Error while creating table '%s'. Result was '%s'."
                    % (self._table_name, str(result))
                )
            else:
                # insert rows
                result = self.insert_rows(
                    path_, [self.getEntries()[key] for key in self.getEntries()]
                )
                if result is not True:
                    raise Exception(
                        "Error while inserting rows to table '%s'. Result was '%s'."
                        % (self._table_name, str(result))
                    )
                else:
                    logger.debug(
                        "Inserted rows to table '%s' in database '%s'. Result was '%s'."
                        % (self._table_name, path_, str(result))
                    )
                return True
        except Exception as e:
            logger.error(
                "Failed to serialize the class '%s' with error '%s'"
                % (self.__class__.__name__, str(e))
            )
            return False

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
                    if not self.getPrimaryKey() in values_dict:
                        logger.error(
                            "Primary key '%s' is not contained in returned values. Database is '%s' with table '%s' and requested columns '%s'."
                            % (
                                self.getPrimaryKey(),
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
                                values_dict[self.getPrimaryKey()],
                                self.getObject(values_dict),
                            )

                        except Exception as exc_:
                            logger.error(exc_)
            # logger.info("Deserialized %i rows from table '%s' in database '%s' " % (len(result), self._table_name, self._db_path))

    # Can be overwritten by subclass to store user-defined objects
    def getObject(self, values_dict):
        return values_dict

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

    def insert_rows(self, path_, list_of_key_values_dicts):
        """
        This function inserts cell hashes into the table.
        :param path_: database path
        :param list_of_key_values_dicts: list of dictionaries with key:value association that are inserted to the table
        :return: bool if operation was successful
        :raise ValueError: if the database returns an error
        """
        try:
            values_str = "?" + ", ?" * (len(list(self._table_columns.keys())) - 1)
            sql_text = "INSERT INTO %s VALUES (%s);" % (self._table_name, values_str)

            # check compatibility
            entries = []
            for entry in list_of_key_values_dicts:
                skip = False
                for k in list(self._table_columns.keys()):
                    if not (k in entry):
                        logger.error(
                            "Could not insert entry '%s'. Did not find necessary key '%s' for this entry."
                            % (str(k), str(k))
                        )
                        skip = True
                if not skip:
                    entries.append(entry)

            result = sql_interface.query_insert_many(
                path_,
                sql_text,
                [
                    [entry[k] for k in list(self._table_columns.keys())]
                    for entry in entries
                ],
            )
            if isinstance(result, str):
                logger.error("Row was not inserted: %s" % result)
                raise ValueError(result)
            elif result is False:
                logger.error("Row was not inserted: function returned False")
                return False

            logger.debug("Row was inserted in table '%s'" % (self._table_name))
            return True
        except Exception as e:
            return e

    def create_table(self, path_=""):
        """
        Create a new table
        :param path_: database path
        :return: bool
        :raise ValueError or Exception: if the query generates a string response (an error)
        """
        if not path_:
            path_ = self._db_path
        try:
            types_string = ""
            for index_, key_ in enumerate(self._table_columns.keys()):
                if not self._table_columns[key_]:
                    raise Exception(
                        "Could not create table. Column type for column '%s' is not valid."
                        % (key_)
                    )
                if index_:
                    types_string += ","
                types_string += '"%s" %s' % (key_, self._table_columns[key_])

            sql_query = 'DROP TABLE IF EXISTS "%s";' % self._table_name
            sql_interface.query_text(path_, sql_query)

            sql_query = "CREATE TABLE %s (%s);" % (self._table_name, types_string)
            result = sql_interface.query_text(path_, sql_query)

            if isinstance(result, str):
                logger.error("Table not created: %s" % result)
                raise ValueError(result)
            elif result is False:
                logger.error("Table not created: query returned False")
                return False

            # add geometry columns
            for geom_col_dict_ in self._geometry_columns:
                if all(
                    k in geom_col_dict_
                    for k in [
                        "column_name",
                        "SRID",
                        "geometry_type",
                        "geometry_type_dimension",
                    ]
                ):
                    query_text_geom_ = (
                        "SELECT AddGeometryColumn('%s', '%s', %i, %s, %i);"
                        % (
                            str(self._table_name),
                            str(geom_col_dict_["column_name"]),
                            int(geom_col_dict_["SRID"]),
                            str(geom_col_dict_["geometry_type"]),
                            int(geom_col_dict_["geometry_type_dimension"]),
                        )
                    )
                    result = sql_interface.query_text(path_, query_text_geom_)
                    if isinstance(result, str):
                        logger.error("Table not created: %s" % result)
                        raise ValueError(result)
                    elif result is False:
                        logger.error(
                            "Table not created: Query 'AddGeometryColumn' returned False"
                        )
                        return False

            logger.debug("Table '%s' created" % (self._table_name))
            return True
        except Exception as e:
            logger.error(str(e))
            return False


# if __name__ == "__main__":
#     # ======================================================
#     # ==================    UNIT TESTS     =================
#     # ======================================================
#     import time
#     start_time = time.time()
#
#     # # create a logger for this module
#     # logger.setLevel(logging.DEBUG)
#     # # create console handler and set level to debug
#     # ch = logging.StreamHandler()
#     # ch.setLevel(logging.DEBUG)
#     # # create formatter
#     # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # # add formatter to ch
#     # ch.setFormatter(formatter)
#     # # add ch to logger
#     # if len(logger.handlers)==0:
#     #     logger.addHandler(ch)
#
#     # path_to_database = os.path.join("..", "..", "example", "exeter_out.alaqs")
#     path_to_database = os.path.join("..", "..", "example", "CAEPport", "old", "06042020_out.alaqs")
#
#     if not os.path.isfile(path_to_database):
#         print("File %s doesn't exist !")
#
#     table_name_ = "default_aircraft"
#     table_columns = [
#         ("oid", "INTEGER PRIMARY KEY"),
#         ("icao", "TEXT"),
#         ("ac_group_code", "TEXT"),
#         ("ac_group", "TEXT"),
#         ("manufacturer", "TEXT"),
#         ("name", "TEXT"),
#         ("engine_count", "INTEGER"),
#         ("engine_name", "TEXT"),
#         ("engine", "TEXT"),
#         ("departure_profile", "TEXT"),
#         ("arrival_profile", "TEXT"),
#         ("bada_id", "TEXT"),
#         ("wake_category", "TEXT"),
#         ("apu_id", "TEXT")
#     ]
#
#     columns = OrderedDict()
#     table_name_string=table_name_
#     table_columns_type_dict=OrderedDict(table_columns)
#
#     # table_columns_type_dict=OrderedDict([
#     #     ("oid", "INTEGER PRIMARY KEY"),
#     #     ("runway_time", "TIMESTAMP"),
#     #     ("block_time", "TIMESTAMP"),
#     #     ("aircraft_registration", "TEXT"),
#     #     ("aircraft", "TEXT"),
#     #     ("gate", "TEXT"),
#     #     ("departure_arrival", "TEXT"),
#     #     ("runway", "TEXT"),
#     #     ("engine_name", "TEXT"),
#     #     ("profile_id", "TEXT"),
#     #     ("track_id", "TEXT"),
#     #     ("taxi_route", "TEXT"),
#     #     ("tow_ratio", "DECIMAL NULL"),
#     #     ("apu_code", "INTEGER"),
#     #     ("taxi_engine_count", "INTEGER"),
#     #     ("set_time_of_main_engine_start_after_block_off_in_s", "DECIMAL NULL"),
#     #     ("set_time_of_main_engine_start_before_takeoff_in_s", "DECIMAL NULL"),
#     #     ("set_time_of_main_engine_off_after_runway_exit_in_s", "DECIMAL NULL"),
#     #     ("engine_thrust_level_for_taxiing", "DECIMAL NULL"),
#     #     ("taxi_fuel_ratio", "DECIMAL NULL"),
#     #     ("number_of_stop_and_gos", "DECIMAL NULL"),
#     #     ("domestic", "TEXT"),
#     #     ("annual_operation", "DECIMAL NULL")
#     # ])
#     primary_key="oid",
#     deserialize=True
#     db = SQLSerializable(path_to_database, table_name_, table_columns_type_dict)
#     db.deserialize()
#
#     print("--- %s seconds ---" % (time.time() - start_time))
#
#     # df = pd.read_sql_query("SELECT * FROM rides WHERE tripduration < 500 ", path_to_database)
#     # df = pd.DataFrame.from_dict(db.getEntries(), orient='index')
#
#     start_time = time.time()
#     for key, values_dict in list(db.getEntries().items()):
#         if "icao" in values_dict and values_dict["icao"] == "L410":
#             print(values_dict)
#         # print(key)
#         # print(dict_)
#         # print("+++++++++++")
#         # mov = Movement(movement_dict)
#     print("--- %s seconds ---" % (time.time() - start_time))
#
#     # db_path_string, table_name_string, table_columns_type_dict, primary_key)
#
#     # columns["oid"] = "INTEGER PRIMARY KEY"
#     # columns["icao"] = "TEXT"
#     # columns["ac_group_code"] ="TEXT"
#     # columns["ac_group"] ="TEXT"
#     # columns["manufacturer"] ="TEXT"
#     # columns["name"] ="TEXT"
#     # columns["mtow"] ="TEXT"
#     # columns["engine_count"] ="INTEGER"
#     # columns["engine_name"] ="TEXT"
#     # columns["engine"] ="TEXT"
#     # columns["departure_profile"] ="TEXT"
#     # columns["arrival_profile"] ="TEXT"
#     # columns["bada_id"] ="INTEGER"
#     # columns["wake_category"] ="TEXT"
#     # columns["apu_id"] ="TEXT"
#
#
#     # columns["time_id"] = "INTEGER PRIMARY KEY"
#     # columns["time"] = "TIMESTAMP"
#     # columns["year"] ="INTEGER"
#     # columns["month"] ="INTEGER"
#     # columns["day"] ="INTEGER"
#     # columns["hour"] ="TEXT"
#     # columns["weekday_id"] ="TEXT"
#     # columns["mix_height"] ="TEXT"
#     # db = SQLSerializable(path_to_database, "tbl_InvTime", columns)
#
#
#
#     # for key in db.getEntries():
#     #     if db.getEntry(key)['icao'].startswith('B735'):
#     #         print key, db.getEntry(key)['icao'], db.getEntry(key)['departure_profile']
#     # #    logger.info(key, db.getEntry(key))
