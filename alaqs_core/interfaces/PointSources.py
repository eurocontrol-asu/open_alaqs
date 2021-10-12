import os
from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Source import Source
from open_alaqs.alaqs_core.tools.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.interfaces.Emissions import EmissionIndex

from open_alaqs.alaqs_core.tools import spatial

logger = get_logger(__name__)


class PointSources(Source):
    def __init__(self, val=None, *args, **kwargs):
        super().__init__(val, *args, **kwargs)
        if val is None:
            val = {}

        self._id = str(val["source_id"]) if "source_id" in val else None
        self._category = str(val.get("category", ""))
        self._type = str(val.get("type", ""))
        self._substance = str(val.get("substance", ""))
        self._temperature = \
            float(val["temperature"]) if "temperature" in val else None
        self._diameter = float(val["diameter"]) if "diameter" in val else None
        self._velocity = float(val["velocity"]) if "velocity" in val else None
        self._ops_year = float(val.get("ops_year", 0))

        if self._geometry_text and self._height is not None:
            self.setGeometryText(
                spatial.addHeightToGeometryWkt(
                    self.getGeometryText(), self.getHeight()))

        init_values = {}
        default_values = {}
        for key_ in ["co_kg_k", "hc_kg_k", "nox_kg_k", "sox_kg_k", "pm10_kg_k",
                     "p1_kg_k", "p2_kg_k"]:
            if key_ in val:
                init_values[key_] = float(val[key_])
                default_values[key_] = 0.

        self._emissionIndex = EmissionIndex(init_values, default_values)

    def getType(self):
        return self._type

    def setType(self, var):
        self._type = var

    def getSubstance(self):
        return self._substance

    def setSubstance(self, var):
        self._substance = var

    def getCategory(self):
        return self._category

    def setCategory(self, var):
        self._category = var

    def getTemperature(self):
        return self._temperature

    def setTemperature(self, var):
        self._temperature = var

    def getDiameter(self):
        return self._diameter

    def setDiameter(self, var):
        self._diameter = var

    def getVelocity(self):
        return self._velocity

    def setVelocity(self, var):
        self._velocity = var

    def getOpsYear(self):
        return self._ops_year

    def setOpsYear(self, var):
        self._ops_year = var

    def __str__(self):
        val = "\n PointSources with id '%s'" % (self.getName())
        val += "\n\t Type: %s" % (self.getType())
        val += "\n\t Substance: %s" % (self.getSubstance())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Category: %s" % (self.getCategory())
        val += "\n\t Temperature: %f" % (self.getTemperature())
        val += "\n\t Diameter: %f" % (self.getDiameter())
        val += "\n\t Velocity: %f" % (self.getVelocity())
        val += "\n\t Ops Year: %f" % (self.getOpsYear())
        val += "\n\t Hour Profile: %s" % (self.getHourProfile())
        val += "\n\t Daily Profile: %s" % (self.getDailyProfile())
        val += "\n\t Month Profile: %s" % (self.getMonthProfile())
        val += "\n\t Emission Index: %s" % (self.getEmissionIndex())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class PointSourcesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'PointSources' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        # Engine Modes
        self._point_db = None
        if "point_db" in db:
            if isinstance(db["point_db"], PointSourcesDatabase):
                self._point_db = db["point_db"]
            elif isinstance(db["point_db"], str) and \
                    os.path.isfile(db["point_db"]):
                self._point_db = PointSourcesDatabase(db["point_db"])

        if self._point_db is None:
            self._point_db = PointSourcesDatabase(db_path)

        # instantiate all point objects
        self.initPointSources()

    def initPointSources(self):
        for key, point_dict in list(
                self.getPointSourcesDatabase().getEntries().items()):
            # add engine to store
            self.setObject(
                point_dict.get("source_id", "unknown"),
                PointSources(point_dict))

    def getPointSourcesDatabase(self):
        return self._point_db


class PointSourcesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to point/stationary shape file in the spatialite
     database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_point_sources",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("source_id", "TEXT"),
                ("height", "DECIMAL"),
                ("category", "TEXT"),
                ("type", "TEXT"),
                ("substance", "TEXT"),
                ("temperature", "DECIMAL"),
                ("diameter", "DECIMAL"),
                ("velocity", "DECIMAL"),
                ("ops_year", "DECIMAL"),
                ("hour_profile", "TEXT"),
                ("daily_profile", "TEXT"),
                ("month_profile", "TEXT"),
                ("co_kg_k", "DECIMAL"),
                ("hc_kg_k", "DECIMAL"),
                ("nox_kg_k", "DECIMAL"),
                ("sox_kg_k", "DECIMAL"),
                ("pm10_kg_k", "DECIMAL"),
                ("p1_kg_k", "DECIMAL"),
                ("p2_kg_k", "DECIMAL"),
                ("instudy", "DECIMAL")
            ])
        if geometry_columns is None:
            geometry_columns = [{
                "column_name": "geometry",
                "SRID": 3857,
                "geometry_type": "POINT",
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
#     path_to_database = os.path.join("..", "..", "example/CAEPport_training", "caepport_out.alaqs")
#
#     store = PointSourcesStore(path_to_database)
#     for point_name, point in list(store.getObjects().items()):
#         # fix_print_with_import
#         print(point)