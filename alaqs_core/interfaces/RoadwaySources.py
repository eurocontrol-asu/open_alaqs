import os
from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Emissions import EmissionIndex
from open_alaqs.alaqs_core.interfaces.Source import Source
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import spatial
from open_alaqs.alaqs_core.tools.Singleton import Singleton

logger = get_logger(__name__)


class RoadwaySources(Source):
    def __init__(self, val=None, *args, **kwargs):
        super().__init__(val, *args, **kwargs)
        if val is None:
            val = {}

        self._id = str(val["roadway_id"]) if "roadway_id" in val else None
        self._scenario = str(val.get("scenario", ""))
        self._vehicle_year = float(val.get("vehicle_year", 0))
        _distance = val.get("distance", 0)
        self._distance = 0.0 if _distance is None else float(_distance)
        self._speed = float(val.get("speed", 0))
        self._fleet_mix = {
            "vehicle_light": float(val.get("vehicle_light", 0)),
            "vehicle_medium": float(val.get("vehicle_medium", 0)),
            "vehicle_heavy": float(val.get("vehicle_heavy", 0)),
        }

        if self._geometry_text and self._height is not None:
            self.setGeometryText(
                spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight())
            )

        init_values = {}
        default_values = {}
        for key_ in [
            "co_gm_km",
            "hc_gm_km",
            "nox_gm_km",
            "sox_gm_km",
            "pm10_gm_km",
            "p1_gm_km",
            "p2_gm_km",
        ]:
            if key_ in val:
                init_values[key_] = float(val[key_])
                default_values[key_] = 0.0

        self._emissionIndex = EmissionIndex(init_values, default_values)

        # internal cacheing
        self.__length = None

    def resetLengthCache(self):
        self.__length = None

    def getUnitsPerYear(self):
        return self._vehicle_year

    def setUnitsPerYear(self, var):
        self._vehicle_year = var

    def getDistance(self):
        return self._distance

    def setDistance(self, var):
        self._distance = var

    def getSpeed(self):
        return self._speed

    def setSpeed(self, var):
        self._speed = var

    def getFleetMix(self):
        return self._fleet_mix

    def setFleetMix(self, var):
        self._fleet_mix = var

    def getScenario(self):
        return self._scenario

    def setScenario(self, var):
        self._scenario = var

    def getLength(self, unitInKM=False):
        # Get the length of the road in meters (internally, length is stored in meters)
        if self.__length is None:
            self.setLength(
                spatial.getDistanceOfLineStringXY(self.getGeometryText())
                / (1000.0 if unitInKM else 1.0)
            )
        return self.__length

    def setLength(self, val):
        self.__length = val

    def setGeometryText(self, val):
        self._geometry_text = val
        self.resetLengthCache()

    def __str__(self):
        val = "\n RoadwaySources with id '%s'" % (self.getName())
        val += "\n\t Vehicles per Year: %f" % (self.getUnitsPerYear())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Distance: %s" % (self.getDistance())
        val += "\n\t Speed: %s" % (self.getSpeed())
        val += "\n\t Fleet Mix: %s" % (
            ", ".join(
                [
                    "%s:%f" % (key_, self.getFleetMix()[key_])
                    for key_ in sorted(self.getFleetMix().keys())
                ]
            )
        )
        val += "\n\t Hour Profile: %s" % (self.getHourProfile())
        val += "\n\t Daily Profile: %s" % (self.getDailyProfile())
        val += "\n\t Month Profile: %s" % (self.getMonthProfile())
        val += "\n\t Emission Index: %s" % (self.getEmissionIndex())
        val += "\n\t Scenario: %s" % (self.getScenario())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class RoadwaySourcesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'RoadwaySources' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        # Engine Modes
        self._roadway_db = None
        if "roadway_db" in db:
            if isinstance(db["roadway_db"], RoadwaySourcesDatabase):
                self._roadway_db = db["roadway_db"]
            elif isinstance(db["roadway_db"], str) and os.path.isfile(db["roadway_db"]):
                self._roadway_db = RoadwaySourcesDatabase(db["roadway_db"])

        if self._roadway_db is None:
            self._roadway_db = RoadwaySourcesDatabase(db_path)

        # instantiate all roadway objects
        self.initRoadwaySourcess()

    def initRoadwaySourcess(self):
        for key, roadway_dict in list(
            self.getRoadwaySourcesDatabase().getEntries().items()
        ):
            # add engine to store
            if (
                not roadway_dict["geometry"]
                .replace("LINESTRING", "")
                .replace("(", "")
                .replace(")", "")
            ):
                logger.debug("Empty segment: %s" % (roadway_dict["roadway_id"]))
            else:
                self.setObject(
                    roadway_dict.get("roadway_id", "unknown"),
                    RoadwaySources(roadway_dict),
                )

    def getRoadwaySourcesDatabase(self):
        return self._roadway_db


class RoadwaySourcesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to roadway shape file in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="shapes_roadways",
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("roadway_id", "TEXT"),
                    ("vehicle_year", "DECIMAL"),
                    ("height", "DECIMAL"),
                    ("distance", "DECIMAL"),
                    ("speed", "DECIMAL"),
                    ("vehicle_light", "DECIMAL"),
                    ("vehicle_medium", "DECIMAL"),
                    ("vehicle_heavy", "DECIMAL"),
                    ("hour_profile", "TEXT"),
                    ("daily_profile", "TEXT"),
                    ("month_profile", "TEXT"),
                    ("co_gm_km", "DECIMAL"),
                    ("hc_gm_km", "DECIMAL"),
                    ("nox_gm_km", "DECIMAL"),
                    ("sox_gm_km", "DECIMAL"),
                    ("pm10_gm_km", "DECIMAL"),
                    ("p1_gm_km", "DECIMAL"),
                    ("p2_gm_km", "DECIMAL"),
                    ("method", "TEXT"),
                    ("scenario", "TEXT"),
                    ("instudy", "DECIMAL"),
                ]
            )
        if geometry_columns is None:
            geometry_columns = [
                {
                    "column_name": "geometry",
                    "SRID": 3857,
                    "geometry_type": "LINESTRING",
                    "geometry_type_dimension": 2,
                }
            ]

        SQLSerializable.__init__(
            self,
            db_path_string,
            table_name_string,
            table_columns_type_dict,
            primary_key,
            geometry_columns,
        )

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
#     path_to_database = os.path.join("..", "..", "example", "ex_out.alaqs")
#
#     store = RoadwaySourcesStore(path_to_database)
#     for roadway_name, roadway in list(store.getObjects().items()):
#         # fix_print_with_import
#         print(roadway_name, roadway)
#         # logger.debug(roadway)
