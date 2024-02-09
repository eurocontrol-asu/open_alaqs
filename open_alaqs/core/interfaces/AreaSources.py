import os
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import EmissionIndex
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools import spatial
from open_alaqs.core.tools.Singleton import Singleton

loaded_color_logger = False
try:
    pass

    loaded_color_logger = True
except ImportError:
    loaded_color_logger = False

logger = get_logger(__name__)


class AreaSources(Source):
    def __init__(self, val=None, *args, **kwargs):
        super().__init__(val, *args, **kwargs)
        if val is None:
            val = {}

        self._id = str(val["source_id"]) if "source_id" in val else None
        self._unit_year = float(val.get("unit_year", 0))
        self._heat_flux = float(val["heat_flux"]) if "heat_flux" in val else None

        if self._geometry_text and self._height is not None:
            self.setGeometryText(
                spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight())
            )

        init_values = {}
        default_values = {}
        for key_ in [
            "co_kg_unit",
            "hc_kg_unit",
            "nox_kg_unit",
            "sox_kg_unit",
            "pm10_kg_unit",
            "p1_kg_unit",
            "p2_kg_unit",
        ]:
            if key_ in val:
                init_values[key_] = float(val[key_])
                default_values[key_] = 0.0

        self._emissionIndex = EmissionIndex(init_values, default_values)

    def getHeatFlux(self):
        return self._heat_flux

    def setHeatFlux(self, var):
        self._heat_flux = var

    def __str__(self):
        val = "\n AreaSources with id '%s'" % (self.getName())
        val += "\n\t Units per Year: %f" % (self.getUnitsPerYear())
        val += "\n\t Heat Flux: %s" % (self.getHeatFlux())
        val += "\n\t Height: %f" % (self.getHeight())
        val += "\n\t Hour Profile: %s" % (self.getHourProfile())
        val += "\n\t Daily Profile: %s" % (self.getDailyProfile())
        val += "\n\t Month Profile: %s" % (self.getMonthProfile())
        val += "\n\t Emission Index: %s" % (self.getEmissionIndex())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class AreaSourcesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'AreaSources' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        # Engine Modes
        self._area_db = None
        if "area_db" in db:
            if isinstance(db["area_db"], AreaSourcesDatabase):
                self._area_db = db["area_db"]
            elif isinstance(db["area_db"], str) and os.path.isfile(db["area_db"]):
                self._area_db = AreaSourcesDatabase(db["area_db"])

        if self._area_db is None:
            self._area_db = AreaSourcesDatabase(db_path)

        # instantiate all area objects
        self.initAreaSourcess()

    def initAreaSourcess(self):
        for key, area_dict in list(self.getAreaSourcesDatabase().getEntries().items()):
            # add engine to store
            self.setObject(
                area_dict["source_id"] if "source_id" in area_dict else "unknown",
                AreaSources(area_dict),
            )

    def getAreaSourcesDatabase(self):
        return self._area_db


class AreaSourcesDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to area shape file in the spatialite database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="shapes_area_sources",
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("source_id", "TEXT"),
                    ("unit_year", "DECIMAL"),
                    ("height", "DECIMAL"),
                    ("heat_flux", "DECIMAL"),
                    ("hourly_profile", "TEXT"),
                    ("daily_profile", "TEXT"),
                    ("monthly_profile", "TEXT"),
                    ("co_kg_unit", "DECIMAL"),
                    ("hc_kg_unit", "DECIMAL"),
                    ("nox_kg_unit", "DECIMAL"),
                    ("sox_kg_unit", "DECIMAL"),
                    ("pm10_kg_unit", "DECIMAL"),
                    ("p1_kg_unit", "DECIMAL"),
                    ("p2_kg_unit", "DECIMAL"),
                    ("instudy", "DECIMAL"),
                ]
            )
        if geometry_columns is None:
            geometry_columns = [
                {
                    "column_name": "geometry",
                    "SRID": 3857,
                    "geometry_type": "POLYGON",
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
#     logging.basicConfig(level=logging.DEBUG)
#
#     # logger.setLevel(logging.DEBUG)
#     # create console handler and set level to debug
#     ch = logging.StreamHandler()
#     if loaded_color_logger:
#         ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
#
#     ch.setLevel(logging.DEBUG)
#     # create formatter
#     formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # add formatter to ch
#     ch.setFormatter(formatter)
#     # add ch to logger
#     logger.addHandler(ch)
#
#     # path_to_database = os.path.join("..", "..", "example", "exeter_out.alaqs")
#
#     store = AreaSourcesStore(path_to_database)
#     for area_name, area in list(store.getObjects().items()):
#         logger.debug(area)
#         # fix_print_with_import
#         print(area_name, area)
