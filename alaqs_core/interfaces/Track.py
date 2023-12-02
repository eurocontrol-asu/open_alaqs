import os
from collections import OrderedDict

from shapely import geometry, ops
from shapely.wkt import loads

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.tools.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import spatial

logger = get_logger(__name__)


class Track:
    def __init__(self, val=None):
        if val is None:
            val = {}
        self._name = str(val["track_id"]) if "track_id" in val else ""
        self._runway = str(val["runway"]) if "runway" in val else ""
        self._departure_arrival = str(val["departure_arrival"]) if "departure_arrival" in val else ""

        self._geometry_text = str(val["geometry"]) if "geometry" in val else ""
        self._geometry = loads(val["geometry"]) if "geometry" in val else geometry.GeometryCollection()

    def getName(self):
        return self._name
    def setName(self, val):
        self._name = val

    def getRunway(self):
        return self._runway
    def setRunway(self, val):
        self._runway = val
        
    def getDepartureArrival(self):
        return self._departure_arrival
    def setDepartureArrival(self, val):
        self._departure_arrival = val
        
    def getGeometryText(self):
        return self._geometry_text
    def setGeometryText(self, val):
        self._geometry_text = val

    def getGeometry(self):
        return self._geometry


    def __str__(self):
        val = "\n Track with id '%s'" % (self.getName())
        val += "\n\t Runway: %i" % (self.getRunway())
        val += "\n\t Departure/Arrival: %i" % (self.getDepartureArrival())
        val += "\n\t Geometry text: '%s'" % (self.getGeometryText())
        return val


class TrackStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Track' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._track_db = None
        if "track_db" in db:
            if isinstance(db["track_db"], TrackStore):
                self._track_db = db["track_db"]
            elif isinstance(db["track_db"], str) and os.path.isfile(db["track_db"]):
                self._track_db = TrackDatabase(db["track_db"])

        if self._track_db is None:
            self._track_db = TrackDatabase(db_path)

        #instantiate all track objects
        self.initTracks()

    def initTracks(self):
        for key, track_dict in list(self.getTrackDatabase().getEntries().items()):
            self.setObject(track_dict["track_id"] if "track_id" in track_dict else "unknown", Track(track_dict))

    def getTrackDatabase(self):
        return self._track_db


class TrackDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to tracks in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="shapes_tracks",
                 table_columns_type_dict=None,
                 primary_key="",
                 geometry_columns=None
                 ):

        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY NOT NULL"),
                ("track_id", "TEXT"),
                ("runway", "TEXT"),
                ("departure_arrival", "TEXT"),
                ("instudy", "INTEGER")
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
