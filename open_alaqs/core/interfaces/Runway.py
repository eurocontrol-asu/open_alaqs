import os
from collections import OrderedDict

from shapely import geometry, ops
from shapely.wkt import loads

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.tools import spatial
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


def _offset(v):
    """A Touchdown Offset value as float, or None when empty."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


class Runway:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._name = str(val["runway_id"]) if "runway_id" in val else ""
        self._directions = self.getDirectionsByName(self._name)
        # Touchdown Offset (m) per landing direction: `touchdown` for the first-named end (e.g. 06 of
        # "06/24"), `touchdown_2` for the other; `touchdown_2` empty (or absent in older studies) = the value
        # of `touchdown`. 0 = each arrival profile's own threshold-crossing distance (50 ft point).
        self._touchdown_offset = _offset(val.get("touchdown")) or 0.0
        self._touchdown_offset_2 = _offset(val.get("touchdown_2"))

        self._height = 0.0
        self._geometry_text = (
            str(val["geometry"]) if val.get("geometry", None) is not None else ""
        )

        self._geometry = (
            loads(val["geometry"])
            if val.get("geometry", None) is not None
            else geometry.GeometryCollection()
        )
        # add height to self._geometry
        if self._geometry and self._height is not None:
            self._geometry = ops.transform(
                spatial.constant_z(self._height), self._geometry
            )

        if self._geometry_text and self._height is not None:
            self.setGeometryText(
                spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight())
            )

        # Capture the `instudy` flag for parity with Source / Gate. The
        # filter is NOT yet wired into MovementSourceModule (deferred to
        # ), so setting `instudy='0'` on a runway has no effect on
        # current emission output. The value is captured here so the
        # module can read it without a separate schema change.
        self._in_study = str(val.get("instudy", "1")).strip() == "1"

    def isInStudy(self) -> bool:
        """Return True if this runway should be included in the study.

        Currently informational only: the filter is not wired into
        MovementSourceModule yet. When LTO movement
        emissions are added, the filter goes in the movement
        processing loop.
        """
        return self._in_study

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

    def getTouchdownOffset(self):
        return self._touchdown_offset

    def setTouchdownOffset(self, val):
        self._touchdown_offset = val

    def getTouchdownOffset2(self):
        """Touchdown Offset of the second-named end; None when not set (the first end's value applies)."""
        return self._touchdown_offset_2

    def setTouchdownOffset2(self, val):
        self._touchdown_offset_2 = val

    def getTouchdownOffsetFor(self, direction) -> float:
        """Touchdown Offset (m) for landings on `direction` (a name such as "24"); 0 = profile's own."""
        dirs = self.getDirections()
        if (
            len(dirs) > 1
            and str(direction) == dirs[-1]
            and self._touchdown_offset_2 is not None
        ):
            return self._touchdown_offset_2
        return self._touchdown_offset or 0.0

    def getGeometryText(self):
        return self._geometry_text

    def setGeometryText(self, val):
        self._geometry_text = val

    def getGeometry(self):
        return self._geometry

    def __str__(self):
        val = "\n Runway with id '%s'" % (self.getName())
        val += "\n\t Touchdown offset: %s" % (self.getTouchdownOffset())
        val += "\n\t Touchdown offset (second end): %s" % (self.getTouchdownOffset2())
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
        if "runway_db" in db:
            if isinstance(db["runway_db"], RunwayDatabase):
                self._runway_db = db["runway_db"]
            elif isinstance(db["runway_db"], str) and os.path.isfile(db["runway_db"]):
                self._runway_db = RunwayDatabase(db["runway_db"])

        if self._runway_db is None:
            self._runway_db = RunwayDatabase(db_path)

        # instantiate all runway objects
        self.initRunways()

    def initRunways(self):
        for key, runway_dict in list(self.getRunwayDatabase().getEntries().items()):
            self.setObject(
                runway_dict["runway_id"] if "runway_id" in runway_dict else "unknown",
                Runway(runway_dict),
            )

    def getRunwayDatabase(self):
        return self._runway_db


class RunwayDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    TABLE_NAME = "shapes_runways"

    def __init__(
        self,
        db_path_string,
        table_columns_type_dict=None,
        primary_key="",
        geometry_columns=None,
        deserialize=True,
    ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                    ("runway_id", "TEXT"),
                    ("touchdown", "INT"),
                    ("touchdown_2", "INT"),
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
            self.TABLE_NAME,
            table_columns_type_dict,
            primary_key,
            geometry_columns,
        )

        if deserialize and self._db_path:
            # Studies made before touchdown_2 existed (and not yet migrated) still load: read only the
            # columns the table has.
            try:
                import sqlite3 as _sqlite3

                with _sqlite3.connect(self._db_path) as _conn:
                    _have = {
                        r[1]
                        for r in _conn.execute(
                            f'PRAGMA table_info("{self.TABLE_NAME}")'
                        )
                    }
                if _have:
                    self._table_columns = OrderedDict(
                        (k, v) for k, v in self._table_columns.items() if k in _have
                    )
            except Exception:
                pass
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
