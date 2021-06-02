import logging
import math
import os
from collections import OrderedDict

import numpy as np

from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.tools import conversion, Spatial

logger = logging.getLogger(__name__)


class AircraftTrajectory:
    def __init__(self, val=None, skipPointInitialization=False):
        if val is None:
            val = {}
        if isinstance(val, AircraftTrajectory):
            self.setIdentifier(val.getIdentifier())
            self.setStage(val.getStage())
            self.setSource(val.getSource())
            self.setDepartureArrivalFlag(val.getDepartureArrivalFlag())
            self.setWeight(val.getWeight())
            self._geometry_text = ""
            self._points = []

            #updates _geometry_text
            if not skipPointInitialization:
                for p in val.getPoints():
                    self.addPoint(p)
        else:
            self._id = str(val["profile_id"]) if "profile_id" in val else ""
            self._stage = int(val["stage"]) if "stage" in val else None
            self._source = str(val["source"]) if "source" in val else ""
            self._departure_arrival = str(val["arrival_departure"]) if "arrival_departure" in val else None
            self._points = []
            self._weight = conversion.convertToFloat(val["weight_kgs"]) if "weight_kgs" in val else None
            self._touchdown = ""
            self._geometry_text = ""

        self._isCartesian = True

    def setIsCartesian(self, value):
        self._isCartesian = value

    def isCartesian(self):
        return self._isCartesian

    def getGeometryTextByMode(self, mode=""):
        geometry_text_list = []
        for (startPoint, endPoint) in self.getPointPairs(mode):
            geometry_text_list.append("(%s, %s)" % (startPoint.getCoordinatesString(), endPoint.getCoordinatesString()))
        return "MULTILINESTRINGZ(%s)" % (",".join(geometry_text_list))

    def calculateDistanceBetweenPoints(self, point1, point2, dimension="space"):
        if dimension.lower() == "space":
            return abs(self.calculateSpaceDistance(point1.getCoordinates(), point2.getCoordinates()))
        elif dimension.lower() == "time":
            return self.calculateTimeDistance(point1, point2)

    def calculateTimeDistance(self, point1, point2, avgSpeed=True):
        speed = 1.
        if avgSpeed:
            speed = (point2.getTrueAirspeed()+point1.getTrueAirspeed())/2.
        else:
            speed = point1.getTrueAirspeed()
        distance = self.calculateDistanceBetweenPoints(point1, point2, "space")
        if speed > 0:
            return abs(float(distance)/float(speed))
        else:
            return 0

    def calculateSpaceDistance(self, xxx_todo_changeme, xxx_todo_changeme1):
        (x1,y1,z1) = xxx_todo_changeme
        (x2,y2,z2) = xxx_todo_changeme1
        if self.isCartesian():
            return ((x2 - x1) ** 2. + (y2 - y1) ** 2. + (z2 - z1) ** 2.)** 0.5
        else:
            return Spatial.getDistanceOfLineStringXYZ(Spatial.getLine(Spatial.getPoint("", x1,y1,z1), Spatial.getPoint("", x2,y2,z2)), abs(z2-z1))

    def getTimeInMode(self, mode):
        return self.getDistance(mode, "time")

    def getDistance(self, mode="", dimension="space"):
        d_ = 0.
        for (startPoint, endPoint) in self.getPointPairs(mode):
            d_+= self.calculateDistanceBetweenPoints(startPoint, endPoint, dimension)
        return d_

    def getGeometryText(self):
        return self._geometry_text

    def updateGeometryText(self):
        self._geometry_text = self.getGeometryTextByMode()

    def getWeight(self):
        return self._weight

    def setWeight(self, var):
        self._weight = var

    def setDepartureArrivalFlag(self, val):
        self._departure_arrival = val

    def getDepartureArrivalFlag(self):
        return self._departure_arrival

    def getIdentifier(self):
        return self._id

    def setIdentifier(self, val):
        self._id = val

    def getStage(self):
        return self._stage

    def setStage(self, val):
        self._stage = val

    def getSource(self):
        return self._source

    def setSource(self, val):
        self._source = val

    def setTouchdownPoint(self, val):
        self._touchdown = val
    def getTouchdownPoint(self):
        return self._touchdown

    def addPoint(self, val, id=None):
        if isinstance(val, AircraftTrajectoryPoint):
            self._points.append(val)
        else:
            p = AircraftTrajectoryPoint(val)
            if not id is None:
                p.setIdentifier(id)
            self._points.append(p)
        self.updateGeometryText()

    def getPoints(self, id="", mode=""):
        if not id and not mode:
            return self._points
        else:
            matched_ = []
            for point in self._points:
                if isinstance(point, TrajectoryPoint):
                    if (id and id == point.getIdentifier()) or (mode and mode==point.getMode()):
                        matched_.append(point)
            return matched_

    def getPointPairs(self, mode=""):
        matched_ = []
        for i_, startPoint in enumerate(self._points):
            if mode and not startPoint.getMode().lower() == mode.lower():
                continue

            if i_ < len(self._points)-1:
                matched_.append((startPoint, self._points[i_+1]))

        return matched_

    def get_angle_wrt_x(self):
        """Return the angle between B-A and the positive x-axis.
        Values go from 0 to pi in the upper half-plane, and from
        0 to -pi in the lower half-plane.
        A = (560023.44957588764, 6362057.3904932579)
        B = (560036.44957588764, 6362071.8904932579)
        """
        ax, ay = (0,0)
        # must be increasing
        zp = [p.getZ() for p in self._points if (p.getZ() >= 0 and p.getZ() < 1000 and p.getX() < 0)][0]
        xp = [p.getX() for p in self._points if (p.getZ() >= 0 and p.getZ() < 1000 and p.getX() < 0)][0]
        bx, by = (xp, zp)
        return math.tan(math.atan2(by - ay, bx - ax))

    def get_sas_point(self, vert_height, op):
        if op:
            # for DEP
            zp = [p.getZ() for p in self._points if (p.getZ() >= 0 and p.getZ() < 300 and p.getX() > 0)]
            xp = [p.getX() for p in self._points if (p.getZ() >= 0 and p.getZ() < 300 and p.getX() > 0)]
            zp.reverse()
        else:
            # for ARR
            zp = [abs(p.getZ()) for p in self._points if (p.getZ() >= 0 and p.getZ() < 300 and p.getX() <= 0)]
            xp = [abs(p.getX()) for p in self._points if (p.getZ() >= 0 and p.getZ() < 300 and p.getX() <= 0)]
            zp.reverse()
            xp.reverse()
        sas_point = np.interp(vert_height, zp, xp)

        return sas_point


    def getPointModes(self):
        modes_ = []
        for p in self.getPoints():
            if not p.getMode() in modes_:
                modes_.append(p.getMode())
        return modes_

    def removePoint(self, index):
        del self._points[index]
        self.updateGeometryText()

    def __str__(self):
        val = "\n Aircraft trajectory with id '%s':" % (str(self.getIdentifier()))
        val += "\n\t Source: %s" % (str(self.getSource()))
        val += "\n\t Departure/Arrival Flag: '%s'" % (str(self.getDepartureArrivalFlag()))
        val += "\n\t Total distance [m]: %f" % (float(self.getDistance(dimension="space")))
        val += "\n\t Total distance [s]: %f" % (float(self.getDistance(dimension="time")))
        for m_ in self.getPointModes():
            val += "\n\t\t In mode '%s': %f m" % (str(m_), float(self.getDistance(m_,dimension="space")))
            val += "\n\t\t In mode '%s': %f s" % (str(m_), float(self.getDistance(m_, dimension="time")))
        val += "\n\t Geometry (WKT): '%s'" % (str(self.getGeometryText()))
        val += "\n\t Points:"
        for p in self.getPoints():
            val += "\n\t\t".join(str(p).split("\n"))
        return val

class TrajectoryPoint(object):
    def __init__(self, val={}):
        if isinstance(val, TrajectoryPoint):
            val_ = {}
            val_["id"] = val.getIdentifier()
            val_["geometry_text"] =val.getGeometryText()
            val_["x"]=val.getX()
            val_["y"]=val.getY()
            val_["z"]=val.getZ()
            val = val_

        self._id = int(val["id"]) if "id" in val else None
        self._geometry_text = str(val["geometry_text"]) if "geometry_text" in val and val["geometry_text"] else ""
        self._x = conversion.convertToFloat(val["x"]) if "x" in val else None
        self._y = conversion.convertToFloat(val["y"]) if "y" in val else None
        self._z = conversion.convertToFloat(val["z"]) if "z" in val else None

    def getIdentifier(self):
        return self._id
    def setIdentifier(self, var):
        self._id = var

    def updateGeometryText(self):
        self.setGeometryText("POINTZ(%f %f %f)" % (
                        self.getCoordinates()[0],
                        self.getCoordinates()[1],
                        self.getCoordinates()[2]))

    def getGeometryText(self):
        if not self._geometry_text:
            self.updateGeometryText()
        return self._geometry_text

    def setGeometryText(self, var):
        self._geometry_text = var

    def getX(self, unit_in_feet=False):
        if not unit_in_feet:
            return self._x
        else:
            return conversion.convertMetersToFeet(self._x)
    def getY(self, unit_in_feet=False):
        if not unit_in_feet:
            return self._y
        else:
            return conversion.convertMetersToFeet(self._y)
    def getZ(self, unit_in_feet=False):
        if not unit_in_feet:
            return self._z
        else:
            return conversion.convertMetersToFeet(self._z)
    def getCoordinatesString(self, unit_in_feet=False):
        return "%f %f %f" % (self.getCoordinates(unit_in_feet))

    def getCoordinates(self, unit_in_feet=False):
        return (self.getX(unit_in_feet), self.getY(unit_in_feet), self.getZ(unit_in_feet))

    def setCoordinates(self, x, y, z, unit_in_feet=False):
        self._x = x if not unit_in_feet else conversion.convertFeetToMeters(x)
        self._y = y if not unit_in_feet else conversion.convertFeetToMeters(y)
        self._z = z if not unit_in_feet else conversion.convertFeetToMeters(z)

    def setX(self, x, unit_in_feet=False):
        self._x = x if not unit_in_feet else conversion.convertFeetToMeters(x)

    def setY(self, y, unit_in_feet=False):
        self._y = y if not unit_in_feet else conversion.convertFeetToMeters(y)

    def setZ(self, z, unit_in_feet=False):
        self._z = z if not unit_in_feet else conversion.convertFeetToMeters(z)

    def addCoordinates(self, x, y, z, unit_in_feet=False):
        self._x += (x if not unit_in_feet else conversion.convertFeetToMeters(x))
        self._y += (y if not unit_in_feet else conversion.convertFeetToMeters(y))
        self._z += (z if not unit_in_feet else conversion.convertFeetToMeters(z))

    def __str__(self):
        val = "\n Trajectory point with id '%s':" % (str(self.getIdentifier()))
        val += "\n\t Geometry (WKT): %s" % (str(self.getGeometryText()))
        val += "\n\t Point [m]: x=%.5f, y=%.5f, z=%.5f" % (
            self.getCoordinates()[0], self.getCoordinates()[1], self.getCoordinates()[2])
        return val


class AircraftTrajectoryPoint(TrajectoryPoint):
    def __init__(self, val={}):
        if isinstance(val, AircraftTrajectoryPoint):
            TrajectoryPoint.__init__(self, {
                "id":val.getIdentifier(),
                "geometry_text":val.getGeometryText(),
                "x":val.getX(),
                "y":val.getY(),
                "z":val.getZ()
            })

            self.setTrueAirspeed(val.getTrueAirspeed())
            self.setPower(val.getPower())
            self.setWeight(val.getWeight())
            self.setMode(val.getMode())
        else:
            TrajectoryPoint.__init__(self, val)
            #properties
            self._true_airspeed = conversion.convertToFloat(val["tas_metres"]) if "tas_metres" in val else None
            self._engine_thrust = conversion.convertToFloat(val["power"]) if "power" in val else None
            self._mode = str(val["mode"]) if "mode" in val else ""
            self._weight = conversion.convertToFloat(val["weight"]) if "weight" in val else ""

    def getIdentifier(self):
        return self._id

    def setIdentifier(self, val):
        self._id = val

    def setMode(self, val):
        self._mode = val

    def getMode(self):
        return self._mode

    def getEngineThrust(self):
        return self._engine_thrust

    def setEngineThrust(self, var):
        self._engine_thrust = var

    def getPower(self):
        return self._engine_thrust

    def setPower(self, var):
        self._engine_thrust = var

    def setWeight(self,val):
        self._weight = val

    def getWeight(self):
        return self._weight

    def getTrueAirspeed(self, unit_in_feet=False):
        if unit_in_feet:
            return conversion.convertMetersToFeet(self._true_airspeed)
        else:
            return self._true_airspeed

    def setTrueAirspeed(self, var, unit_in_feet=False):
        self._true_airspeed = var if not unit_in_feet else conversion.convertFeetToMeters(var)

    def __str__(self):
        val = "\n Aircraft trajectory point with id '%s':" % (str(self.getIdentifier()))
        val += "\n\t True airspeed [m]: %s" % (self.getTrueAirspeed())
        val += "\n\t Engine-power setting [%%]: %s" % (self.getEngineThrust())
        val += "\n\t Mode : '%s'" % (str(self.getMode()))
        val += "\n\t".join(str(TrajectoryPoint.__str__(self)).split("\n"))
        return val


class AircraftTrajectoryStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Runway' objects
    """

    def __init__(self, db_path="", db=None):
        if db is None:
            db = {}
        Store.__init__(self)

        self._db_path = db_path

        self._trajectory_db = None
        if "trajectory_db" in db:
            if isinstance(db["trajectory_db"], AircraftTrajectoryDatabase):
                self._trajectory_db = db["trajectory_db"]
            elif isinstance(db["trajectory_db"], str) and os.path.isfile(db["trajectory_db"]):
                self._trajectory_db = AircraftTrajectoryDatabase(db["trajectory_db"])

        if self._trajectory_db is None:
            self._trajectory_db = AircraftTrajectoryDatabase(db_path)

        #instantiate all runway objects
        self.initAircraftTrajectories()

    def initAircraftTrajectories(self):

        # double_ids = []
        for key, trajectory_dict in self.getAircraftTrajectoryDatabase().getEntries().items():

            id_ = trajectory_dict["profile_id"] if "profile_id" in trajectory_dict else "unknown"

            #create a new aircraft-trajectory point
            trajectory_point_ = AircraftTrajectoryPoint({
                "x": conversion.convertToFloat(trajectory_dict["horizontal_metres"]) if "horizontal_metres" in trajectory_dict else 0.,
                "y": 0.,
                "z": conversion.convertToFloat(trajectory_dict["vertical_metres"]) if "vertical_metres" in trajectory_dict else 0.,
                "tas_metres": conversion.convertToFloat(trajectory_dict["tas_metres"]) if "tas_metres" in trajectory_dict else None,
                "power": conversion.convertToFloat(trajectory_dict["power"]) if "power" in trajectory_dict else None,
                "mode": str(trajectory_dict["mode"]) if "mode" in trajectory_dict else None
            })

            if "point" in trajectory_dict:
                trajectory_point_.setIdentifier(trajectory_dict["point"])

            #add point aircraft trajectory if existing
            if self.hasKey(id_):
                self.getObject(id_).addPoint(trajectory_point_)

            #add aircraft trajectory with new point to store if not existing
            else:
                trajectory_ = AircraftTrajectory(trajectory_dict)
                trajectory_.addPoint(trajectory_point_)
                self.setObject(id_, trajectory_)

    def getAircraftTrajectoryDatabase(self):
        return self._trajectory_db

    # def getAircraftTrajectoryDataFrame(self):
    #     #import pandas as pd
    #     return pd.DataFrame.from_dict(store.getAircraftTrajectoryDatabase().getEntries(), orient='index')


class AircraftTrajectoryDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to runway shape file in the spatialite database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="default_aircraft_profiles",
                 table_columns_type_dict=None,
                 primary_key=""
                 ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
                ("oid", "INTEGER PRIMARY KEY"),
                ("profile_id", "VARCHAR(20)"),
                ("arrival_departure", "VARCHAR(1)"),
                ("stage", "INTEGER"),
                ("point", "INTEGER"),
                ("weight_lbs", "DECIMAL NULL"),
                ("horizontal_feet", "DECIMAL NULL"),
                ("vertical_feet", "DECIMAL NULL"),
                ("tas_knots", "DECIMAL NULL"),
                ("weight_kgs", "DECIMAL NULL"),
                ("horizontal_metres", "DECIMAL NULL DEFAULT 0"),
                ("vertical_metres", "DECIMAL NULL DEFAULT 0"),
                ("tas_metres", "DECIMAL NULL"),
                ("power", "DECIMAL NULL"),
                ("mode", "VARCHAR(5)"),
                ("course", "VARCHAR(15)")
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        if self._db_path:
            self.deserialize()


if __name__ == "__main__":
    # sys.path.append("..")

    # create a logger for this module
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    import pandas as pd

    # st_ = time.time()

    path_to_database = os.path.join("..","..", "example", "CAEPport", "31032020_out.alaqs")
    if not os.path.isfile(path_to_database):
        print("file %s not found" % path_to_database)

    store = AircraftTrajectoryStore(path_to_database)
    AircraftTrajectoryDataFrame = pd.DataFrame.from_dict(store.getAircraftTrajectoryDatabase().getEntries(), orient='index')

    # trajectory = AircraftTrajectory(self.getTrajectory(), skipPointInitialization=True)

    for name, profile in list(store.getObjects().items()):
        if name == "737500-A-1":
            # fix_print_with_import
            print(name, profile)
            break
        # logger.debug(profile)

    # et_ = time.time()
    # print "Time elapsed: %s"%(et_-st_)
