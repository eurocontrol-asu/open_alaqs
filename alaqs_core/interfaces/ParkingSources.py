from __future__ import absolute_import
from builtins import str
from builtins import object
from . import __init__ #setup the paths for direct calls of the module
from future.utils import with_metaclass


__author__ = 'ENVISA'
import logging
loaded_color_logger= False
try:
    from rainbow_logging_handler import RainbowLoggingHandler
    loaded_color_logger = True
except ImportError:
    loaded_color_logger= False
#logger = logging.getLogger("__alaqs__.%s" % (__name__))
logger = logging.getLogger(__name__)

import os
import sys
from collections import OrderedDict

from .SQLSerializable import SQLSerializable
from .Singleton import Singleton

from .Store import Store
from .Emissions import EmissionIndex

from tools import Spatial

class ParkingSources(object):
    def __init__(self, val={}):
        self._id = str(val["parking_id"]) if "parking_id" in val else None
        self._vehicle_year = float(val["vehicle_year"]) if "vehicle_year" in val else 0.

        self._height = float(val["height"]) if "height" in val else 0.
        self._distance = float(val["distance"]) if "distance" in val else 0.
        self._park_time = float(val["park_time"]) if "park_time" in val else 0.
        self._idle_time= float(val["idle_time"]) if "idle_time" in val else 0.
        self._speed= float(val["speed"]) if "speed" in val else 0.

        self._hour_profile = str(val["hour_profile"]) if "hour_profile" in val else "default"
        self._daily_profile = str(val["daily_profile"]) if "daily_profile" in val else "default"
        self._month_profile = str(val["month_profile"]) if "month_profile" in val else "default"

        self._fleet_mix = {
            "vehicle_light" : float(val["vehicle_light"]) if "vehicle_light" in val else 0.,
            "vehicle_medium":float(val["vehicle_medium"]) if "vehicle_medium" in val else 0.,
            "vehicle_heavy": float(val["vehicle_heavy"]) if "vehicle_heavy" in val else 0.
        }

        self._instudy = int(val["instudy"]) if "instudy" in val else 1
        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""

        if self._geometry_text and not self._height is None:
            self.setGeometryText(Spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight()))

        initValues = {}
        defaultValues = {}
        for key_ in ["co_gm_vh", "hc_gm_vh", "nox_gm_vh","sox_gm_vh", "pm10_gm_vh", "p1_gm_vh", "p2_gm_vh"]:
            if key_ in val:
                initValues[key_] = float(val[key_])
                defaultValues[key_] = 0.


        self._emissionIndex = EmissionIndex(initValues=initValues, defaultValues=defaultValues)

    def getName(self):
        return self._id
    def setName(self, val):
        self._id = val

    def getEmissionIndex(self):
        return self._emissionIndex
    def setEmissionIndex(self, val):
        self._emissionIndex = val

    def getUnitsPerYear(self):
        return self._vehicle_year
    def setUnitsPerYear(self, var):
        self._vehicle_year = var

    def getHeight(self):
        return self._height
    def setHeight(self, var):
        self._height = var

    def getDistance(self):
        return self._distance
    def setDistance(self, var):
        self._distance = var

    def getIdleTime(self):
        return self._idle_time
    def setIdleTime(self, var):
        self._idle_time = var
    def getParkTime(self):
        return self._park_time
    def setParkTime(self, var):
        self._park_time = var
    def getSpeed(self):
        return self._speed
    def setSpeed(self, var):
        self._speed = var
    def getFleetMix(self):
        return self._fleet_mix
    def setFleetMix(self, var):
        self._fleet_mix = var
    def getHourProfile(self):
        return self._hour_profile
    def setHourProfile(self, var):
        self._hour_profile = var

    def getDailyProfile(self):
        return self._daily_profile
    def setDailyProfile(self, var):
        self._daily_profile = var

    def getMonthProfile(self):
        return self._month_profile
    def setMonthProfile(self, var):
        self._month_profile = var

    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getInStudy(self):
        return self._instudy
    def setInStudy(self, val):
        self._instudy = val

    def __str__(self):
        val = "\n ParkingSources with id '%s'" % (self.getName())
        val += "\n\t Vehicle hours per Year: %f" % (self.getUnitsPerYear())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Distance: %s" % (self.getDistance())
        val += "\n\t Idle Time: %s" % (self.getIdleTime())
        val += "\n\t Park Time: %s" % (self.getParkTime())
        val += "\n\t Speed: %s" % (self.getSpeed())
        val += "\n\t Fleet Mix: %s" % (", ".join(["%s:%f" % (key_, self.getFleetMix()[key_]) for key_ in sorted(self.getFleetMix().keys())]))
        val += "\n\t Hour Profile: %s" % (self.getHourProfile())
        val += "\n\t Daily Profile: %s" % (self.getDailyProfile())
        val += "\n\t Month Profile: %s" % (self.getMonthProfile())
        val += "\n\t Emission Index: %s" % (self.getEmissionIndex())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val

class ParkingSourcesStore(with_metaclass(Singleton, Store)):
    """
    Class to store instances of 'ParkingSources' objects
    """

    def __init__(self, db_path="", db={}):
        Store.__init__(self)

        self._db_path = db_path

        #Engine Modes
        self._parking_db = None
        if  "parking_db" in db:
            if isinstance(db["parking_db"], ParkingSourcesDatabase):
                self._parking_db = db["parking_db"]
            elif isinstance(db["parking_db"], str) and os.path.isfile(db["parking_db"]):
                self._parking_db = ParkingSourcesDatabase(db["parking_db"])

        if self._parking_db is None:
            self._parking_db = ParkingSourcesDatabase(db_path)

        #instantiate all parking objects
        self.initParkingSourcess()

    def initParkingSourcess(self):
        for key, parking_dict in list(self.getParkingSourcesDatabase().getEntries().items()):
            #add engine to store
            self.setObject(parking_dict["parking_id"] if "parking_id" in parking_dict else "unknown", ParkingSources(parking_dict))

    def getParkingSourcesDatabase(self):
        return self._parking_db

class ParkingSourcesDatabase(with_metaclass(Singleton, SQLSerializable)):
    """
    Class that grants access to parking shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_parking",
                 table_columns_type_dict=OrderedDict([
                    ("oid" , "INTEGER PRIMARY KEY NOT NULL"),
                    ("parking_id" , "TEXT"),
                    ("height" , "DECIMAL"),
                    ("distance" , "DECIMAL"),
                    ("idle_time" , "DECIMAL"),
                    ("park_time" , "DECIMAL"),
                    ("vehicle_light" , "DECIMAL"),
                    ("vehicle_medium" , "DECIMAL"),
                    ("vehicle_heavy" , "DECIMAL"),
                    ("vehicle_year" , "DECIMAL"),
                    ("speed" , "DECIMAL"),
                    ("hour_profile" , "TEXT"),
                    ("daily_profile" , "TEXT"),
                    ("month_profile" , "TEXT"),
                    ("co_gm_vh" , "DECIMAL"),
                    ("hc_gm_vh" , "DECIMAL"),
                    ("nox_gm_vh" , "DECIMAL"),
                    ("sox_gm_vh" , "DECIMAL"),
                    ("pm10_gm_vh" , "DECIMAL"),
                    ("p1_gm_vh" , "DECIMAL"),
                    ("p2_gm_vh" , "DECIMAL"),
                    ("method" , "TEXT"),
                    ("instudy" , "DECIMAL")
                ]),
                 primary_key="",
                 geometry_columns=[{
                    "column_name":"geometry",
                    "SRID":3857,
                    "geometry_type":"POLYGON",
                    "geometry_type_dimension":2
                 }]
        ):
        SQLSerializable.__init__(self, db_path_string, table_name_string, table_columns_type_dict, primary_key, geometry_columns)

        if self._db_path:
            self.deserialize()

if __name__ == "__main__":
    # create a logger for this module
    #logging.basicConfig(level=logging.DEBUG)

    logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    if loaded_color_logger:
        ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))

    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)

    path_to_database = os.path.join("..", "..", "example", "test_out.alaqs")

    store = ParkingSourcesStore(path_to_database)
    for parking_name, parking in list(store.getObjects().items()):
        logger.debug(parking)