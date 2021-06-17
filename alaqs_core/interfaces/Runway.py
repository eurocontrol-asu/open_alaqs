import logging
import os
from collections import OrderedDict

from shapely import geometry, ops
from shapely.wkt import loads

from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import Spatial

logger = logging.getLogger("__alaqs__.%s" % __name__)


class Runway:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._name = str(val["runway_id"]) if "runway_id" in val else ""
        self._directions = self.getDirectionsByName(self._name)
        self._touchdown_offset = int(val["touchdown"]) if "touchdown" in val else 0
        self._capacity = int(val["capacity"]) if "capacity" in val else 0
        self._max_queue_speed = float(val["max_queue_speed"]) if "max_queue_speed" in val else 0.
        self._peak_queue_time = float(val["peak_queue_time"]) if "peak_queue_time" in val else 0.

        self._height = 0.
        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""

        self._geometry = loads(val["geometry"]) if "geometry" in val else geometry.GeometryCollection()
        # add height to self._geometry
        if self._geometry and not (self._height is None):
            self._geometry = ops.transform(lambda x, y, z=None: (x, y, self._height), self._geometry)

        if self._geometry_text and not (self._height is None):
            self.setGeometryText(Spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight()))

    def getHeight(self):
        return self._height
    def setHeight(self, var):
        self._height = var

    def getDirections(self):
        return self._directions
    def getDirectionsByName(self, val):
        if val:
            return val.replace(" ", "").split("/")
        return []

    def getName(self):
        return self._name
    def setName(self, val):
        self._name = val
    def getTouchdownOffset(self):
        return self._touchdown_offset
    def setTouchdownOffset(self, val):
        self._touchdown_offset = val
    def getCapacity(self):
        return self._capacity
    def setCapacity(self, val):
        self._capacity = val
    def getQueueSpeed(self):
        return self._max_queue_speed
    def setQueueSpeed(self, val):
        self._max_queue_speed = val
    def getPeakQueueTime(self):
        return self._peak_queue_time
    def setPeakQueueTime(self, val):
        self._peak_queue_time = val
    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getGeometry(self):
        return self._geometry


    def __str__(self):
        val = "\n Runway with id '%s'" % (self.getName())
        val += "\n\t Touchdown offset: %i" % (self.getTouchdownOffset())
        val += "\n\t Capacity: %i" % (self.getCapacity())
        val += "\n\t Queue speed: %i" % (self.getQueueSpeed())
        val += "\n\t Peak queue time: %i" % (self.getPeakQueueTime())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class RunwayStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Runway' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._runway_db = None
        if  "runway_db" in db:
            if isinstance(db["runway_db"], RunwayDatabase):
                self._runway_db = db["runway_db"]
            elif isinstance(db["runway_db"], str) and os.path.isfile(db["runway_db"]):
                self._runway_db = RunwayDatabase(db["runway_db"])

        if self._runway_db is None:
            self._runway_db = RunwayDatabase(db_path)

        #instantiate all runway objects
        self.initRunways()

    def initRunways(self):
        for key, runway_dict in list(self.getRunwayDatabase().getEntries().items()):
            self.setObject(runway_dict["runway_id"] if "runway_id" in runway_dict else "unknown", Runway(runway_dict))

    def getRunwayDatabase(self):
        return self._runway_db


class RunwayDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_runways",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("runway_id", "TEXT"),
                ("capacity", "INT"),
                ("touchdown", "INT"),
                ("max_queue_speed", "DECIMAL"),
                ("peak_queue_time", "DECIMAL"),
                ("instudy", "DECIMAL")
            ])
        if geometry_columns is None:
            geometry_columns = [{
                "column_name": "geometry",
                "SRID": 3857,
                "geometry_type": "LINESTRING",
                "geometry_type_dimension": 2
            }]

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
#     # create console handler and set level to debug
#     # ch = logging.StreamHandler()
#     # if loaded_color_logger:
#     #     ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
#
#     # ch.setLevel(logging.DEBUG)
#     # # create formatter
#     # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # # add formatter to ch
#     # ch.setFormatter(formatter)
#     # # add ch to logger
#     # logger.addHandler(ch)
#
#     # path_to_database = os.path.join("..", "..", "example", "exeter_out.alaqs")
#     path_to_database = os.path.join("..","..",  "example/", "test_movs.alaqs")
#
#
#     store = RunwayStore(path_to_database)
#     for rwy_name, rwy in list(store.getObjects().items()):
#         # fix_print_with_import
#         print(rwy_name, rwy)
#         # logger.debug(rwy)