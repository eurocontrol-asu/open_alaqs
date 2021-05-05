from __future__ import absolute_import
from builtins import str
from builtins import object
from future.utils import with_metaclass
__author__ = 'ENVISA'
import logging
loaded_color_logger= False
try:
    from rainbow_logging_handler import RainbowLoggingHandler
    loaded_color_logger = True
except ImportError:
    loaded_color_logger= False
logger = logging.getLogger("__alaqs__.%s" % (__name__))

import os
import sys
from collections import OrderedDict

from .SQLSerializable import SQLSerializable
from .Singleton import Singleton
from tools import Conversions

from .Store import Store

import calendar
from datetime import datetime, timedelta

MONTH_MAP = {
    1:"jan",
    2:"feb",
    3:"mar",
    4:"apr",
    5:"may",
    6:"jun",
    7:"jul",
    8:"aug",
    9:"sep",
    10:"oct",
    11:"nov",
    12:"dec"
}

WEEKDAY_MAP = {
    1:"mon",
    2:"tue",
    3:"wed",
    4:"thu",
    5:"fri",
    6:"sat",
    7:"sun"
}

class InventoryTimeSeries(object):
    def __init__(self, val={}):
        self._format = '%Y-%m-%d %H:%M:%S'

        self._timeid = int(val["time_id"]) if "time_id" in val else -1
        self._time = Conversions.convertTimeToSeconds(str(val["time"]) if "time" in val else "2000-01-01 00:00:00", self._format)
        self._year = int(val["year"]) if "year" in val else 2015
        self._month = int(val["month"]) if "month" in val else 1
        self._day = int(val["day"]) if "day" in val else 1
        self._hour = int(val["hour"]) if "hour" in val else 1
        self._weekday_id = int(val["weekday_id"]) if "weekday_id" in val else 1
        self._mix_height = float(val["mix_height"]) if "mix_height" in val else 914.4

    def getTimeID(self):
        return self._timeid
    def setTimeID(self, val):
        self._timeid = int(val)

    def getTime(self):
        return self._time

    def getTimeAsString(self):
        return Conversions.convertSecondsToTimeString(self._time, self._format)

    def getTimeAsTimeTuple(self):
        return Conversions.convertSecondsToTime(self._time, self._format)

    def getTimeAsDateTime(self):
        return Conversions.convertSecondsToDateTime(self._time, self._format)

    def setTime(self, val):
        self._time = Conversions.convertTimeToSeconds(val, self._format)

    def getYear(self):
        return self._year
    def setYear(self, val):
        self._year= int(val)

    def getMonth(self):
        if self._month in MONTH_MAP:
            return MONTH_MAP[self._month]
        return None

    def getMonthID(self):
        return self._month

    def setMonth(self, val):
        if isinstance(val, str):
            if val.lower() in [value_ for key_, value_ in list(MONTH_MAP.items())]:
                self._month = MONTH_MAP[val.lower()]
            else:
                raise Exception("Did not find index for month with name '%s'. Valid names are '%s'." % (val, ",".join([value_ for key_, value_ in list(MONTH_MAP.items())])))
        elif isinstance(val, int) or isinstance(val, float):
            self._month= int(val)
        else:
            raise Exception("'%s' is of type '%s', but 'str' or int' expected.'" % (val, str(type(val))))

    def getDay(self):
        if (datetime(self._year, self._month, self._day).weekday() + 1) in WEEKDAY_MAP:
            return WEEKDAY_MAP[1 + datetime(self._year, self._month, self._day).weekday()]
        return None

    def getDayID(self):
        return self._day

    def setDay(self, val):
        if isinstance(val, str):
            if val.lower() in [value_ for key_, value_ in list(WEEKDAY_MAP.items())]:
                self._day = WEEKDAY_MAP[val.lower()]
            else:
                raise Exception("Did not find index for month with name '%s'. Valid names are '%s'." % (val, ",".join([value_ for key_, value_ in list(WEEKDAY_MAP.items())])))
        elif isinstance(val, int) or isinstance(val, float):
            self._day= int(val)
        else:
            raise Exception("'%s' is of type '%s', but 'str' or int' expected.'" % (val, str(type(val))))

    def getHour(self):
        return self._hour
    def setHour(self, val):
        self._hour= int(val)
    def getWeekdayID(self):
        return self._weekday_id
    def setWeekdayID(self, val):
        self._weekday_id= int(val)
    def getMixingHeight(self):
        return self._mix_height
    def setMixingHeight(self, val):
        self._mix_height= float(val)

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
        return datetime.strftime(self.offsetAsDateTime(**kwargs),  self.getFormat())

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

class InventoryTimeSeriesStore(with_metaclass(Singleton, Store)):
    """
    Class to store instances of 'InventoryTimeSeries' objects
    """

    def __init__(self, db_path="", db={}):
        Store.__init__(self)

        self._db_path = db_path

        #Engine Modes
        self._inventory_timeseries_db = None
        if  "inventory_timeseries_db" in db:
            if isinstance(db["inventory_timeseries_db"], InventoryTimeSeriesDatabase):
                self._inventory_timeseries_db = db["inventory_timeseries_db"]
            elif isinstance(db["inventory_timeseries_db"], str) and os.path.isfile(db["inventory_timeseries_db"]):
                self._inventory_timeseries_db = InventoryTimeSeriesDatabase(db["inventory_timeseries_db"])

        if self._inventory_timeseries_db is None:
            self._inventory_timeseries_db = InventoryTimeSeriesDatabase(db_path)

        #instantiate all InventoryTimeSeries objects
        self.initInventoryTimeSeries()

    def initInventoryTimeSeries(self):
        for key, timeseries_dict in list(self.getInventoryTimeSeriesDatabase().getEntries().items()):
            #add engine to store
            self.setObject(timeseries_dict["time_id"] if "time_id" in timeseries_dict else -1, InventoryTimeSeries(timeseries_dict))

    def getInventoryTimeSeriesDatabase(self):
        return self._inventory_timeseries_db

    def getTimeSeries(self):
        # for index_, ts_ in self.getObjects().items():
        for index_, ts_ in sorted(self.getObjects().items()):
            yield ts_

class InventoryTimeSeriesDatabase(with_metaclass(Singleton, SQLSerializable)):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="tbl_InvTime",
                 table_columns_type_dict=OrderedDict([
                    ("time_id" , "INTEGER PRIMARY KEY NOT NULL"),
                    ("time" , "DATETIME"),
                    ("year" , "INT"),
                    ("month" , "INT"),
                    ("day" , "INT"),
                    ("hour", "DATETIME"),
                    ("weekday_id" , "INT"),
                    ("mix_height" , "DECIMAL")
                ]),
                 primary_key="time_id",
                 geometry_columns=[]
        ):
        SQLSerializable.__init__(self, db_path_string, table_name_string, table_columns_type_dict, primary_key, geometry_columns)

        if self._db_path:
            self.deserialize()

if __name__ == "__main__":
    # create a logger for this module
    #logging.basicConfig(level=logging.DEBUG)

    # logger.setLevel(logging.DEBUG)
    # # create console handler and set level to debug
    # ch = logging.StreamHandler()
    # if loaded_color_logger:
    #     ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
    #
    # ch.setLevel(logging.DEBUG)
    # # create formatter
    # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
    # # add formatter to ch
    # ch.setFormatter(formatter)
    # # add ch to logger
    # logger.addHandler(ch)

    path_to_database = os.path.join("..", "..", "example", "lfmn2_out.alaqs")

    Timestore = InventoryTimeSeriesStore(path_to_database)

    # for ts_id, ts in Timestore.getObjects().items():
    #     print ts
    #     print datetime(ts.getYear(), ts.getMonthID(), ts.getDayID()).weekday()
    #     print WEEKDAY_MAP[1 + datetime(ts.getYear(), ts.getMonthID(), ts.getDayID()).weekday()]
    #     # logger.debug(ts)