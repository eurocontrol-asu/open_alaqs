from __future__ import print_function
from __future__ import absolute_import
from builtins import str
from builtins import object
from . import __init__ #setup the paths for direct calls of the module
from future.utils import with_metaclass

__author__ = ''

import sys, os
from collections import OrderedDict

import alaqslogging

try:
    from .SQLSerializable import SQLSerializable
    from .Singleton import Singleton
    from .Store import Store
    # from .Emissions import EmissionIndex
except:
    from SQLSerializable import SQLSerializable
    from Singleton import Singleton
    from Store import Store

from tools import Spatial

logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class ReceptorPoints(object):
    def __init__(self, val={}):
        self._id = str(val["source_id"]) if "source_id" in val else None
        self._height = float(val["height"]) if "height" in val else 0.
        self._xcoord = float(val["xcoord"]) if "xcoord" in val else None
        self._ycoord = float(val["ycoord"]) if "ycoord" in val else None
        self._instudy = int(val["instudy"]) if "instudy" in val else 1
        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""

        if self._geometry_text and not self._height is None:
            self.setGeometryText(Spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight()))

    def getName(self):
        return self._id
    def setName(self, val):
        self._id = val

    def getHeight(self):
        return self._height
    def setHeight(self, var):
        self._height = var    

    def getXcoord(self):
        return self._xcoord
    def setXcoord(self, var):
        self._xcoord = var

    def getYcoord(self):
        return self._ycoord
    def setYcoord(self, var):
        self._ycoord = var

    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getInStudy(self):
        return self._instudy
    def setInStudy(self, val):
        self._instudy = val

    def __str__(self):
        val = "\n PointSources with id '%s'" % (self.getName())
        val += "\n\t X coord: %f" % (self.getXcoord())
        val += "\n\t Y coord: %f" % (self.getYcoord())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val

class ReceptorPointsStore(with_metaclass(Singleton, Store)):
    """
    Class to store instances of 'PointSources' objects
    """

    def __init__(self, db_path="", db={}):
        Store.__init__(self)

        self._db_path = db_path

        self._rc_point_db = None
        # if "_rc_point_db" in db:
        #     if isinstance(db["_rc_point_db"], ReceptorPointsDatabase):
        #         self._rc_point_db = db["_rc_point_db"]
        #     elif isinstance(db["_rc_point_db"], str) and os.path.isfile(db["_rc_point_db"]):
        #         self._rc_point_db = ReceptorPointsDatabase(db["_rc_point_db"])
    #
        if self._rc_point_db is None:
            self._rc_point_db = ReceptorPointsDatabase(db_path)
    #
    #     #instantiate all point objects
        self.initReceptorPoints()

    def initReceptorPoints(self):
        for key, point_dict in list(self.getReceptorPointsDatabase().getEntries().items()):
            self.setObject(point_dict["source_id"] if "source_id" in point_dict else "unknown", ReceptorPoints(point_dict))

    def getReceptorPointsDatabase(self):
        return self._rc_point_db


class ReceptorPointsDatabase(with_metaclass(Singleton, SQLSerializable)):
    """
    Class that grants access to receptor points shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_receptor_points",
                 table_columns_type_dict=OrderedDict([
                    ("oid" , "INTEGER PRIMARY KEY NOT NULL"),
                    ("source_id" , "TEXT"),
                    ("height" , "DECIMAL"),
                    ("xcoord" , "DECIMAL"),
                    ("ycoord" , "DECIMAL"),
                    ("instudy" , "TEXT")
                ]),
                 primary_key="",
                 geometry_columns=[{
                    "column_name":"geometry",
                    "SRID":3857,
                    "geometry_type":"POINT",
                    "geometry_type_dimension":2
                 }]
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

    path_to_database = os.path.join("..", "..", "example/CAEPport_training", "caepport_out.alaqs")

    store = ReceptorPointsStore(path_to_database)
    for point_name, point in list(store.getObjects().items()):
        # fix_print_with_import
        print(point)