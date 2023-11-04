import calendar
import os
from collections import OrderedDict
from datetime import datetime, timedelta

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.tools.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import conversion

logger = get_logger(__name__)

# Set the names of the month and days of the week to prevent locale issue
month_abbreviations = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dec"
}
weekday_abbreviations = {
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun"
}

abbreviation_weekdays = {v: k for k, v in weekday_abbreviations.items()}
abbreviation_months = {v: k for k, v in month_abbreviations.items()}


class InventoryTime:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._format = '%Y-%m-%d %H:%M:%S'

        self._time_id = int(val.get("time_id", -1))
        self._time = conversion.convertTimeToSeconds(str(
            val.get("time", "2000-01-01 00:00:00")
        ), self._format)
        self._year = int(val.get("year", 2015))
        self._month = int(val.get("month", 1))
        self._day = int(val.get("day", 1))
        self._hour = int(val.get("hour", 1))
        self._weekday_id = int(val.get("weekday_id", 1))
        self._mix_height = float(val.get("mix_height", 914.4))

    def getTimeID(self):
        return self._time_id

    def setTimeID(self, val):
        self._time_id = int(val)

    def getTime(self):
        return self._time

    def getTimeAsString(self):
        return conversion.convertSecondsToTimeString(self._time, self._format)

    def getTimeAsTimeTuple(self):
        return conversion.convertSecondsToTime(self._time)

    def getTimeAsDateTime(self):
        return conversion.convertSecondsToDateTime(self._time, self._format)

    def setTime(self, val):
        self._time = conversion.convertTimeToSeconds(val, self._format)

    def getYear(self):
        return self._year

    def setYear(self, val):
        self._year = int(val)

    def getMonth(self):
        if self._month in month_abbreviations:
            return month_abbreviations[self._month]
        return None

    def getMonthID(self):
        return self._month

    def setMonth(self, val):
        if isinstance(val, str):
            if val.lower() in abbreviation_months:
                self._month = abbreviation_months[val.lower()]
            else:
                raise Exception("Did not find index for month with name '%s'. "
                                "Valid names are '%s'." % (
                                    val,
                                    ",".join(abbreviation_months.keys())))
        elif isinstance(val, int) or isinstance(val, float):
            self._month = int(val)
        else:
            raise Exception(f"'{val}' is of type '{str(type(val))}', "
                            f"but 'str' or int' expected.'")

    def getDay(self):
        # Get the weekday (1-indexed)
        weekday = datetime(self._year, self._month, self._day).weekday() + 1
        if weekday in weekday_abbreviations:
            return weekday_abbreviations[weekday]
        return None

    def getDayID(self):
        return self._day

    def setDay(self, val):
        if isinstance(val, str):
            if val.lower() in abbreviation_weekdays:
                self._day = abbreviation_weekdays[val.lower()]
            else:
                raise Exception("Did not find index for month with name '%s'. "
                                "Valid names are '%s'." % (
                                    val,
                                    ",".join(abbreviation_weekdays.keys())))
        elif isinstance(val, (int, float)):
            self._day = int(val)
        else:
            raise Exception(f"'{val}' is of type '{str(type(val))}', "
                            f"but 'str' or int' expected.'")

    def getHour(self):
        return self._hour

    def setHour(self, val):
        self._hour = int(val)

    def getWeekdayID(self):
        return self._weekday_id

    def setWeekdayID(self, val):
        self._weekday_id = int(val)

    def getMixingHeight(self):
        return self._mix_height

    def setMixingHeight(self, val):
        self._mix_height = float(val)

    def getFormat(self):
        return self._format

    def setFormat(self, val):
        self._format = val

    # TODO what happens if the time period includes both? This is unresolved in original ALAQS and here
    def getTotalHoursInYear(self):
        if calendar.isleap(self.getYear()):
            return 8784.
        else:
            return 8760.

    def offsetAsDateTime(self, **kwargs):
        return self.getTimeAsDateTime() + timedelta(**kwargs)

    def offsetAsString(self, **kwargs):
        return datetime.strftime(self.offsetAsDateTime(**kwargs),
                                 self.getFormat())

    def __str__(self):
        val = "\n Time id: %i" % (self.getTimeID())
        val += "\n\t Time: %s" % (str(self.getTimeAsString()))
        val += "\n\t Year: %i" % (self.getYear())
        val += "\n\t Month: %i" % (self.getMonthID())
        val += "\n\t Day: %i" % (self.getDayID())
        val += "\n\t Hour: %i" % (self.getHour())
        val += "\n\t Weekday ID: %i" % (self.getWeekdayID())
        val += "\n\t Mixing Height: %f" % (self.getMixingHeight())

        return val


class InventoryTimeSeriesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'InventoryTimeSeries' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        # Engine Modes
        self._inventory_timeseries_db = None
        inventory_timeseries_db_ = db.get("inventory_timeseries_db")
        if isinstance(inventory_timeseries_db_, InventoryTimeSeriesDatabase):
            self._inventory_timeseries_db = inventory_timeseries_db_
        elif isinstance(inventory_timeseries_db_, str) \
                and os.path.isfile(inventory_timeseries_db_):
            self._inventory_timeseries_db = InventoryTimeSeriesDatabase(
                inventory_timeseries_db_)
        else:
            self._inventory_timeseries_db = InventoryTimeSeriesDatabase(db_path)

        # instantiate all InventoryTime objects
        self.initInventoryTimes()

    def initInventoryTimes(self):
        entries = self.getInventoryTimeSeriesDatabase().getEntries()
        for key, timeseries_dict in entries.items():
            self.setObject(
                timeseries_dict.get("time_id", -1),
                InventoryTime(timeseries_dict))

    def getInventoryTimeSeriesDatabase(self):
        return self._inventory_timeseries_db

    def getTimeSeries(self):
        for index_, ts_ in sorted(self.getObjects().items()):
            yield ts_


class InventoryTimeSeriesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="tbl_InvTime",
                 table_columns_type_dict=None, primary_key="time_id",
                 geometry_columns=None
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("time_id", "INTEGER PRIMARY KEY NOT NULL"),
                ("time", "DATETIME"),
                ("year", "INT"),
                ("month", "INT"),
                ("day", "INT"),
                ("hour", "DATETIME"),
                ("weekday_id", "INT"),
                ("mix_height", "DECIMAL")
            ])
        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key,
                                 geometry_columns)

        if self._db_path:
            self.deserialize()

# if __name__ == "__main__":
#     # create a logger for this module
#     #logging.basicConfig(level=logging.DEBUG)
#
#     # logger.setLevel(logging.DEBUG)
#     # # create console handler and set level to debug
#     # ch = logging.StreamHandler()
#     # if loaded_color_logger:
#     #     ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
#     #
#     # ch.setLevel(logging.DEBUG)
#     # # create formatter
#     # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # # add formatter to ch
#     # ch.setFormatter(formatter)
#     # # add ch to logger
#     # logger.addHandler(ch)
#
#     path_to_database = os.path.join("..", "..", "example", "lfmn2_out.alaqs")
#
#     Timestore = InventoryTimeSeriesStore(path_to_database)
#
#     # for ts_id, ts in Timestore.getObjects().items():
#     #     print ts
#     #     print datetime(ts.getYear(), ts.getMonthID(), ts.getDayID()).weekday()
#     #     print WEEKDAY_MAP[1 + datetime(ts.getYear(), ts.getMonthID(), ts.getDayID()).weekday()]
#     #     # logger.debug(ts)