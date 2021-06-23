from collections import OrderedDict

from shapely import geometry
from shapely.wkt import loads

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import spatial

logger = get_logger(__name__)


class TaxiwayRoute:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._id = str(val["route_name"]) if "route_name" in val else None
        self._gate = str(val["gate"]) if "gate" in val else None
        self._runway = str(val["runway"]) if "runway" in val else None
        self._departure_arrival = str(val["departure_arrival"]) if "departure_arrival" in val else None
        self._instance_id = int(val["instance_id"]) if "instance_id" in val else 0
        self._groups = str(val["groups"]).split(",") if "groups" in val else []
        self._segments = []

    def getSegments(self):
        return self._segments
    def setSegments(self, var):
        self._segments = var
    def addSegment(self, var):
        self._segments.append(var)
    def addSegments(self, var_list):
        self._segments.extend(var_list)

    def getName(self):
        return self._id
    def setName(self, val):
        self._id = val

    def getGate(self):
        return self._gate
    def setGate(self, var):
        self._gate = var

    def getRunway(self):
        return self._runway
    def setRunway(self, var):
        self._runway = var

    def getInstance(self):
        return self._instance_id
    def setInstance(self, var):
        self._instance_id = var

    def getSegmentsAsLineString(self):
        from shapely.geometry import MultiLineString
        if self.getSegments():
            return MultiLineString([x.getGeometry() for x in self.getSegments()])
        else:
            logger.error("Cannot create MultiLineString from segments.")
            return MultiLineString()
        # return self._segments

    def getAircraftGroups(self):
        return self._groups
    def setAircraftGroups(self, var):
        self.__groups= var

    def isDeparture(self):
        return self._departure_arrival.lower() == "d"

    def isArrival(self):
        return self._departure_arrival.lower() == "a"

    def setInStudy(self, val):
        self._instudy = val

    def __str__(self):
        val = "\n TaxiwayRoute with id '%s'" % (self.getName())
        val += "\n\t Instance: %s" % (self.getInstance())
        val += "\n\t Gate: %s" % (self.getGate())
        val += "\n\t Runway: %s" % (self.getRunway())
        val += "\n\t Is used by departures: %s" % (self.isDeparture())
        val += "\n\t Is used by arrivals: %s" % (self.isArrival())
        val += "\n\t Aircraft groups: %s" % (", ".join(self.getAircraftGroups()))
        val += "\n\t Taxiway segments: %s" % ("".join([str(x).replace("\n", "\n\t\t") for x in self.getSegments()]))

        return val


class TaxiwaySegment:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._id = str(val["taxiway_id"]) if "taxiway_id" in val else None
        self._height = float(val["height"]) if "height" in val and not val["height"] is None else 0.

        self._speed_in_m_s = float(val["speed"])/3.6 if "speed" in val and not val["speed"] is None else 0.

        self._instudy = int(val["instudy"]) if "instudy" in val else 1
        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""
        self._geometry = loads(str(val["geometry"])) if "geometry" in val else geometry.GeometryCollection()

        self._length = None

        if self._geometry_text and not self._height is None:
            self.setGeometryText(spatial.addHeightToGeometryWkt(self.getGeometryText(), self.getHeight()))
            self._length = spatial.getDistanceOfLineStringXY(self.getGeometryText(), epsg_id_source=3857, epsg_id_target=4326)

        self._time_in_s = 0.
        if not self._length is None:
            self._time_in_s = self._length/self._speed_in_m_s

    def getName(self):
        return self._id
    def setName(self, val):
        self._id = val

    def getHeight(self):
        return self._height
    def setHeight(self, var):
        self._height = var

    def getLength(self):
        return self._length
    def setLength(self, var):
        self._length = var

    def getSpeed(self):
        return self._speed_in_m_s
    def setSpeed(self, var):
        self._speed_in_m_s = var

    def getTime(self):
        return self._time_in_s
    def setTime(self, var):
        self._time_in_s = var

    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getGeometry(self):
        return self._geometry


    def getInStudy(self):
        return self._instudy
    def setInStudy(self, val):
        self._instudy = val

    def __str__(self):
        val = "\n TaxiwaySegment with id '%s'" % (self.getName())
        val += "\n\t Height [m]: %s" % (self.getHeight())
        val += "\n\t Length [m]: %s" % (self.getLength())
        val += "\n\t Speed [m/s]: %s" % (self.getSpeed())
        val += "\n\t Time [s]: %f" % (self.getTime())
        val += "\n\t Instudy: %i" % (self.getInStudy())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class TaxiwayRoutesStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'TaxiwayRoute' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        #Store with taxiway segments
        self._taxiway_segments_store = TaxiwaySegmentsStore(self._db_path)

        #Store with taxiway routes
        self._taxiway_routes_db = TaxiwayRouteDatabase(self._db_path)

        #instantiate all TaxiwayRoutes objects
        self.initTaxiwayRoutes()

    def getTaxiwaySegmentsStore(self):
        return self._taxiway_segments_store

    def getTaxiwayRoutesDatabase(self):
        return self._taxiway_routes_db

    def initTaxiwayRoutes(self):

        for key, _dict in list(self.getTaxiwayRoutesDatabase().getEntries().items()):
            sequence = []
            if "sequence" in _dict:
                sequence = _dict["sequence"]
                _dict.pop("sequence", None)

            taxiway_route = TaxiwayRoute(_dict)

            # Add all segments to this route
            if type(sequence) == type(""):
                segments_ = sequence.split(",")

                for segment_ in segments_:
                    if self.getTaxiwaySegmentsStore().hasKey(segment_):
                        taxiway_route.addSegment(self.getTaxiwaySegmentsStore().getObject(segment_))

            self.setObject(_dict["route_name"] if "route_name" in _dict else "unknown", taxiway_route)


class TaxiwaySegmentsStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Taxiway' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path
        self._taxiway_segments_db = TaxiwaySegmentsDatabase(self._db_path)
        #instantiate all TaxiwaySegment objects
        self.initTaxiwaySegments()

    def getTaxiwaySegmentsDatabase(self):
        return self._taxiway_segments_db

    def initTaxiwaySegments(self):

        for key, taxiway_dict in list(self.getTaxiwaySegmentsDatabase().getEntries().items()):
            #add taxiway to store

            if not taxiway_dict['geometry'].replace("LINESTRING", "").replace("(", "").replace(")", ""):
                logger.debug("Empty segment: %s"%(taxiway_dict['taxiway_id']))
            else:
                taxiway = TaxiwaySegment(taxiway_dict)
                self.setObject(taxiway_dict["taxiway_id"] if "taxiway_id" in taxiway_dict else "unknown", taxiway)


class TaxiwaySegmentsDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to taxiway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_taxiways",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("taxiway_id", "TEXT"),
                ("speed", "DECIMAL"),
                ("time", "DECIMAL"),
                ("instudy", "DECIMAL")
            ])
        if geometry_columns is None:
            geometry_columns = [{
                "column_name": "geometry",
                "SRID": 3857,
                "geometry_type": "POLYGON",
                "geometry_type_dimension": 2
            }]

        SQLSerializable.__init__(self, db_path_string, table_name_string, table_columns_type_dict, primary_key, geometry_columns)

        if self._db_path:
            self.deserialize()


class TaxiwayRouteDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to taxiway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="user_taxiroute_taxiways",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("gate", "TEXT"),
                ("route_name", "TEXT"),
                ("runway", "TEXT"),
                ("departure_arrival", "VARCHAR(1)"),
                ("instance_id", "INTEGER"),
                ("sequence", "TEXT"),
                ("groups", "TEXT")
            ])

        if geometry_columns is None:
            geometry_columns = []

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key,
                                 geometry_columns)

        if self._db_path:
            self.deserialize()

# if __name__ == "__main__":
#     # import alaqslogging
#     # logger.setLevel(logging.DEBUG)
#
#     path_to_database = os.path.join("..","..", "example/", "CAEPport_training", "caepport_out.alaqs")
#     if not os.path.isfile(path_to_database):
#         raise Exception("File %s doesn't exist !")
#     print("Running Open-ALAQS for file: %s"%path_to_database)
#
#     store = TaxiwaySegmentsStore(path_to_database)
#     for taxiway_name, taxiway_segment in list(store.getObjects().items()):
#         # taxiway_segment.setSpeed(10)
#         # fix_print_with_import
#         print(taxiway_segment.getName(), taxiway_segment.getSpeed())
#         # logger.debug(taxiway_segment)
#
#     # store = TaxiwayRoutesStore(path_to_database)
#     # for taxiway_name, taxiway_route in store.getObjects().items():
#     #     logger.debug(taxiway_route)