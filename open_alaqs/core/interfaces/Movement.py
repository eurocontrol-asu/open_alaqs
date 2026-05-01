import json
import sqlite3 as _sqlite3
import sys
from collections import OrderedDict

import matplotlib
import numpy as np
import pandas as pd
from qgis.core import Qgis, QgsGeometry, QgsLineString
from qgis.PyQt import QtCore, QtWidgets
from shapely.geometry.base import BaseGeometry

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Aircraft import Aircraft, AircraftStore
from open_alaqs.core.interfaces.AircraftTrajectory import AircraftTrajectoryStore
from open_alaqs.core.interfaces.EngineStore import EngineStore, HeliEngineStore
from open_alaqs.core.interfaces.Gate import GateStore
from open_alaqs.core.interfaces.Runway import RunwayStore
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.interfaces.Taxiway import TaxiwayRoutesStore
from open_alaqs.core.interfaces.Track import TrackStore
from open_alaqs.core.tools import conversion, spatial
from open_alaqs.core.tools.ProgressBarStage import ProgressBarStage
from open_alaqs.core.tools.Singleton import Singleton

sys.path.append("..")

matplotlib.use("Qt5Agg")

logger = get_logger(__name__)

defaultEmissions = {
    "fuel_kg": 0.0,
    "co_g": 0.0,
    "co2_g": 0.0,
    "hc_g": 0.0,
    "nox_g": 0.0,
    "sox_g": 0.0,
    "pm10_g": 0.0,
    "p1_g": 0.0,
    "p2_g": 0.0,
    "pm10_nonvol_g": 0.0,
    "pm10_sul_g": 0.0,
    "pm10_organic_g": 0.0,
    "nvpm_g": 0.0,
    "nvpm_number": 0.0,
}
defaultEI = {
    "fuel_kg_sec": 0.0,
    "co_g_kg": 0.0,
    "co2_g_kg": 3.16 * 1000.0,
    "hc_g_kg": 0.0,
    "nox_g_kg": 0.0,
    "sox_g_kg": 0.0,
    "pm10_g_kg": 0.0,
    "p1_g_kg": 0.0,
    "p2_g_kg": 0.0,
    "smoke_number": 0.0,
    "smoke_number_maximum": 0.0,
    "fuel_type": "",
    "pm10_nonvol_g_kg": 0.0,
    "pm10_sul_g_kg": 0.0,
    "pm10_organic_g_kg": 0.0,
    "nvpm_g_kg": 0.0,
    "nvpm_number": 0.0,
}


class Movement:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._time = None
        _col = "runway_time"
        if _col not in val:
            if len(val):
                logger.error(f"'{_col}' not set, but necessary input")
        else:
            self._time = conversion.convertTimeToSeconds(val[_col])
            if self._time is None:
                logger.error(
                    f"Could not convert '{str(val[_col])}', which is of type '{str(type(val[_col]))}', to a valid time format."
                )
        self._block_time = None
        _col = "block_time"
        if _col not in val:
            if len(val):
                logger.error(f"{_col}' not set, but necessary input")
        else:
            self._block_time = conversion.convertTimeToSeconds(val[_col])
            if self._block_time is None:
                logger.error(
                    f"Could not convert '{str(val[_col])}', which is of type '{str(type(val[_col]))}', to a valid time format."
                )

        self._engine_name = str(val.get("engine_name", ""))
        # APU code semantics:
        #  -1  Explicit "no APU" — skip all APU emissions regardless of DB defaults
        #   0  No APU (same effect as -1; default when field is NULL or empty)
        #   1  APU running at gate/stand only (first taxi segment)
        #   2  APU running during full taxi (and optionally through LTO phases)
        # Any other value defaults to 0 (no APU).
        raw_apu = val.get("apu_code") if isinstance(val, dict) else None
        if raw_apu is None or raw_apu == "":
            self._apu_code = 0
        else:
            try:
                self._apu_code = int(raw_apu)
            except (TypeError, ValueError):
                self._apu_code = 0

        # gate_emissions_code controls whether GSE, GPU and MES gate emissions
        # are included for this movement.
        #   1 (default)  Include all gate emissions (GSE, GPU, MES).
        #   0            Suppress all gate emissions for this movement.
        raw_gate = val.get("gate_emissions_code") if isinstance(val, dict) else None
        if raw_gate is None or raw_gate == "":
            self._gate_emissions_code = 1
        else:
            try:
                self._gate_emissions_code = int(raw_gate)
            except (TypeError, ValueError):
                self._gate_emissions_code = 1

        self._oid = val.get("oid", None)
        self._departure_arrival = str(val.get("departure_arrival", ""))
        self._profile_id = str(val.get("profile_id", ""))
        self._track_id = str(val.get("track_id", ""))
        self._runway_direction = str(val.get("runway", ""))

        self._gate_name = str(val.get("gate", ""))
        self._gate = None
        self._taxi_route = None
        self._taxi_engine_count = conversion.convertToInt(
            val.get("taxi_engine_count"), 2
        )
        self._tow_ratio = conversion.convertToFloat(val.get("tow_ratio"), 1)
        self._taxi_fuel_ratio = conversion.convertToFloat(val.get("taxi_fuel_ratio"), 1)
        self._engine_thrust_level_taxiing = conversion.convertToFloat(
            val.get("engine_thrust_level_for_taxiing"), 0.07
        )

        self._set_time_of_main_engine_start_after_block_off_in_s = (
            conversion.convertToFloat(
                val.get("set_time_of_main_engine_start_after_block_off_in_s")
            )
        )
        self._set_time_of_main_engine_start_before_takeoff_in_s = (
            conversion.convertToFloat(
                val.get("set_time_of_main_engine_start_before_takeoff_in_s")
            )
        )
        self._set_time_of_main_engine_off_after_runway_exit_in_s = (
            conversion.convertToFloat(
                val.get("set_time_of_main_engine_off_after_runway_exit_in_s")
            )
        )

        if self._set_time_of_main_engine_start_after_block_off_in_s is not None:
            self._set_time_of_main_engine_start_after_block_off_in_s = abs(
                self._set_time_of_main_engine_start_after_block_off_in_s
            )

        if self._set_time_of_main_engine_start_before_takeoff_in_s is not None:
            self._set_time_of_main_engine_start_before_takeoff_in_s = abs(
                self._set_time_of_main_engine_start_before_takeoff_in_s
            )

        if self._set_time_of_main_engine_off_after_runway_exit_in_s is not None:
            self._set_time_of_main_engine_off_after_runway_exit_in_s = abs(
                self._set_time_of_main_engine_off_after_runway_exit_in_s
            )

        self._number_of_stop_and_gos = conversion.convertToFloat(
            val.get("number_of_stop_and_gos", 0)
        )

        self._aircraft: Aircraft = None
        self._aircraftengine = None
        self._runway = None
        self._trajectory_cartesian = None
        self._trajectory_at_runway = None
        self._track = None

    def getAPUCode(self):
        return self._apu_code

    def setAPUCode(self, var):
        self._apu_code = var

    def getGateEmissionsCode(self):
        return self._gate_emissions_code

    def setGateEmissionsCode(self, var):
        self._gate_emissions_code = var

    def getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff(self):
        return self._set_time_of_main_engine_start_after_block_off_in_s

    def setSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff(self, var):
        self._set_time_of_main_engine_start_after_block_off_in_s = var

    def getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff(self):
        return self._set_time_of_main_engine_start_before_takeoff_in_s

    def setSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff(self, var):
        self._set_time_of_main_engine_start_before_takeoff_in_s = var

    def getSingleEngineTaxiingMainEngineOffAfterRunwayExit(self):
        return self._set_time_of_main_engine_off_after_runway_exit_in_s

    def setSingleEngineTaxiingMainEngineOffAfterRunwayExit(self, var):
        self._set_time_of_main_engine_off_after_runway_exit_in_s = var

    def getNumberOfStops(self):
        return self._number_of_stop_and_gos

    def setNumberOfStops(self, var):
        self._number_of_stop_and_gos = var

    def getName(self):
        # if self.getAircraft() and self.getAircraft().getRegistration():
        #     return self.getAircraft().getRegistration()
        # else:
        return "id %s: %s-%s-%s-%s" % (
            self.getOid(),
            self.getAircraft().getICAOIdentifier(),
            self.getDepartureArrivalFlag(),
            self.getRunwayTime(as_str=True),
            self.getBlockTime(as_str=True),
        )

    def getEngineThrustLevelTaxiing(self):
        return self._engine_thrust_level_taxiing

    def setEngineThrustLevelTaxiing(self, var):
        self._engine_thrust_level_taxiing = var

    def _calculate_sas_geom(self, wkt: str, horizontal_extent: float) -> QgsGeometry:
        geom = QgsGeometry.fromWkt(wkt)

        if geom.wkbType() == Qgis.WkbType.LineString:
            raise NotImplementedError(f"Unsupported geometry type {geom.type()}!")

        ogr_multipolygon = spatial.ogr.Geometry(spatial.ogr.wkbMultiPolygon)

        line = geom.constGet()
        points = [line.pointN(i) for i in range(line.numPoints())]

        for p1, p2 in zip(points, points[1:]):
            # skip when the two points are exactly equal, which produces invalid polygon
            if p1 == p2:
                continue

            line = QgsLineString(p1, p2)

            # TODO OPENGIS.ch: this should be converted to proper QGIS method, but currently we copy/paste the implementation that was used before
            ogr_left_line, ogr_right_line = self.CalculateParallels(
                line.asWkt(), horizontal_extent, 0, 0, 3857, 4326
            )

            # TODO OPENGIS.ch: this should be converted to proper QGIS method, but currently we copy/paste the implementation that was used before
            ogr_poly_geom = spatial.getRectangleXYZFromBoundingBox(
                ogr_left_line, ogr_right_line, 3857, 4326
            )

            # TODO OPENGIS.ch: ideally this should be done with `QgsGeometry.addPart` into a multipolygon.
            # However, it was crashing QGIS and therefore we use the OGR implementation to add parts to a multipolygon.
            ogr_multipolygon.AddGeometry(ogr_poly_geom)
            # Crashing implementation:
            # 1) we create the multipolygon (should be outside the for-loop)
            # result_multipolygon = QgsGeometry.fromWkt("MULTIPOLYGON Z EMPTY")
            # 2) Add the geometry part
            # polygon = QgsGeometry.fromWkt(ogr_poly_geom.ExportToWkt()).get()
            # add_part_result = result_multipolygon.addPart(polygon) # BOOM!
            # 3) check if adding was successful
            # if add_part_result != Qgis.GeometryOperationResult.Success:
            #     raise Exception(
            #         f"Failed to add part to multipolygon: {add_part_result}"
            #     )

        return QgsGeometry.fromWkt(ogr_multipolygon.ExportToWkt())

    def CalculateParallels(
        self, geometry_wkt_init, width, height, shift, EPSG_source, EPSG_target
    ):

        geo_wkt, swap = spatial.reproject_geometry(
            geometry_wkt_init, EPSG_source, EPSG_target
        )

        points = spatial.getAllPoints(geo_wkt, swap)
        lon1, lat1, alt1 = points[0][1], points[0][0], points[0][2]
        lon2, lat2, alt2 = points[1][1], points[1][0], points[1][2]

        inverseDistance_dict = spatial.getInverseDistance(lat1, lon1, lat2, lon2)
        azi1, azi2 = inverseDistance_dict["azi1"], inverseDistance_dict["azi2"]

        # left
        direct_dic1l = spatial.getDistance(
            lat1,
            lon1,
            90 + azi1,
            conversion.convertToFloat(width) / 2,
            epsg_id=EPSG_target,
        )
        direct_dic2l = spatial.getDistance(
            lat2,
            lon2,
            90 + azi2,
            conversion.convertToFloat(width) / 2,
            epsg_id=EPSG_target,
        )

        newline_left = "LINESTRING Z(%s %s %s, %s %s %s)" % (
            direct_dic1l["lon2"],
            direct_dic1l["lat2"],
            alt1 + height,
            direct_dic2l["lon2"],
            direct_dic2l["lat2"],
            alt2 + height,
        )

        # right
        direct_dic1r = spatial.getDistance(
            lat1,
            lon1,
            270 + azi1,
            conversion.convertToFloat(width) / 2,
            epsg_id=EPSG_target,
        )
        direct_dic2r = spatial.getDistance(
            lat2,
            lon2,
            270 + azi2,
            conversion.convertToFloat(width) / 2,
            epsg_id=EPSG_target,
        )

        newline_right = "LINESTRING Z(%s %s %s, %s %s %s)" % (
            direct_dic1r["lon2"],
            direct_dic1r["lat2"],
            alt1 + height,
            direct_dic2r["lon2"],
            direct_dic2r["lat2"],
            alt2 + height,
        )

        return newline_left, newline_right

    def getAircraft(self) -> Aircraft:
        return self._aircraft

    def getOid(self) -> int:
        return self._oid

    def setAircraft(self, var: Aircraft) -> None:
        self._aircraft = var

    def setAircraftEngine(self, var):
        self._aircraftengine = var

    def getAircraftEngine(self):
        return self._aircraftengine

    def getTrajectory(self, cartesian=True):
        if cartesian:
            return self._trajectory_cartesian
        else:
            return self.getTrajectoryAtRunway()

    def setTrajectory(self, var):
        self._trajectory_cartesian = var

    def getTrajectoryAtRunway(self):
        return self._trajectory_at_runway

    def updateTrajectoryAtRunway(self):
        from open_alaqs.core.GeoTransformation import TrajectoryTransformer

        self.setTrajectoryAtRunway(
            TrajectoryTransformer(
                self.getTrajectory(),
                self.getTrack(),
                self.getRunway(),
                self.getRunwayTime(as_str=True),
                self.getRunwayDirection(),
                self.getTaxiRoute(),
                self.getDepartureArrivalFlag(),
            ).runway_alignment()
        )

    def setTrajectoryAtRunway(self, var):
        self._trajectory_at_runway = var
        if self._trajectory_at_runway is None:
            logger.warning(
                "setTrajectoryAtRunway: runway alignment returned None for "
                "movement at runway time '%s' (runway='%s', direction='%s'). "
                "Check that the runway and trajectory are configured correctly.",
                getattr(self, "_runway_time", "unknown"),
                getattr(self.getRunway(), "getName", lambda: "unknown")(),
                getattr(self, "_runway_direction", "unknown"),
            )
            return
        self._trajectory_at_runway.setIsCartesian(False)

    def getRunway(self):
        return self._runway

    def setRunway(self, var):
        self._runway = var

    def setTrack(self, var):
        self._track = var

    def getTrack(self):
        return self._track

    def getGeometryText(self):
        """
        Returns the WKT geometry text for this movement.
        Handles the following cases:
        - Track geometry (plain LineString WKT)
        - Trajectory at runway (LineString WKT, possibly a MultiLineString
            if the trajectory was clipped across grid bounds)
        - Helicopter trajectories, where a Shapely geometry object may have
            been stored directly instead of WKT
        - None / empty geometry
        """

        def _to_wkt(geom_text):
            """Normalize whatever getGeometryText() returns to a WKT string or None."""
            if geom_text is None:
                return None
            # Shapely geometry stored directly (helicopter case)
            if isinstance(geom_text, BaseGeometry):
                return geom_text.wkt if not geom_text.is_empty else None
            # Already a WKT string
            if isinstance(geom_text, str):
                return geom_text if geom_text.strip() else None
            # Fallback: try to coerce to string (e.g. ogr.Geometry)
            try:
                wkt = str(geom_text)
                return wkt if wkt.strip() else None
            except Exception:
                return None

        if self._track is not None:
            wkt = _to_wkt(self._track.getGeometryText())
            if wkt:
                return wkt

        if self._trajectory_at_runway is not None:
            wkt = _to_wkt(self._trajectory_at_runway.getGeometryText())
            if wkt:
                return wkt

        return None

    # ["08R", "26L"]
    def getRunwayDirection(self):
        return self._runway_direction

    def setRunwayDirection(self, var):
        self._runway_direction = var
        # if isinstance(var, str):
        #    var = ''.join(c for c in var if c.isdigit())
        #    var = conversion.convertToFloat(var)
        # self._runway_direction = var

    def getRunwayTime(self, as_str=False):
        if as_str:
            if conversion.convertToFloat(self._time) is not None:
                return conversion.convertSecondsToTimeString(self._time)
        return self._time

    def setRunwayTime(self, val):
        self._time = val

    def getBlockTime(self, as_str=False):
        if as_str:
            if conversion.convertToFloat(self._block_time) is not None:
                return conversion.convertSecondsToTimeString(self._block_time)

        return self._block_time

    def setBlockTime(self, val):
        self._block_time = val

    def setDepartureArrivalFlag(self, val):
        self._departure_arrival = val

    def getDepartureArrivalFlag(self):
        return self._departure_arrival

    def isArrival(self) -> bool:
        if self.getDepartureArrivalFlag().lower() in ["d", "dep", "departure"]:
            return False
        else:
            return True

    def isDeparture(self):
        return not self.isArrival()

    def getGate(self):
        return self._gate

    def setGate(self, var):
        self._gate = var

    def getGateName(self):
        return self._gate_name

    def setGateName(self, var):
        self._gate_name = var

    def getTaxiRoute(self):
        return self._taxi_route

    def setTaxiRoute(self, var):
        self._taxi_route = var

    def getTaxiEngineCount(self):
        return self._taxi_engine_count

    def setTaxiEngineCount(self, var):
        self._taxi_engine_count = var

    def getTakeoffWeightRatio(self):
        return self._tow_ratio

    def setTakeoffWeight(self, var):
        self._tow_ratio = var

    def getTaxiFuelRatio(self):
        return self._taxi_fuel_ratio

    def setTaxiFuelRatio(self, var):
        self._taxi_fuel_ratio = var

    def __str__(self):
        val = "\n Movement:"
        val += "\n\t Runway time: %s" % (str(self.getRunwayTime(as_str=True)))
        val += "\n\t Block time: %s" % (str(self.getBlockTime(as_str=True)))
        val += "\n\t Departure/Arrival Flag: %s" % (str(self.getDepartureArrivalFlag()))
        val += "\n\t Gate: %s" % (str(self.getGate()))
        val += "\n\t Taxi route: %s" % (str(self.getTaxiRoute()))
        val += "\n\t Engine thrust level for taxiing: %f" % (
            float(self.getEngineThrustLevelTaxiing())
        )
        val += "\n\t Aircraft: %s" % ("\n\t".join(str(self.getAircraft()).split("\n")))
        val += "\n\t Trajectory: %s" % (
            "\n\t".join(str(self.getTrajectory()).split("\n"))
        )
        val += "\n\t Runway direction [deg.]: %s" % (str(self.getRunwayDirection()))
        val += "\n\t Runway: %s" % ("\n\t".join(str(self.getRunway()).split("\n")))
        return val


class MovementStore(Store, metaclass=Singleton):
    """
    Class to store instances of 'Movement' objects
    """

    def __init__(self, db_path="", db=None, debug=False, show_progress=True):
        if db is None:
            db = {}
        Store.__init__(self, ordered=True)

        self._db_path = db_path

        self._movement_db = None
        # if "movement_db" in db:
        #     if isinstance(db["movement_db"], MovementDatabase):
        #         self._movement_db = db["movement_db"]
        #     elif isinstance(db["movement_db"], str) and os.path.isfile(db["movement_db"]):
        #         self._movement_db = MovementDatabase(db["movement_db"])

        if self._movement_db is None:
            self._movement_db = MovementDatabase(db_path)

        # G5 perf: cache store references so accessor methods return an
        # attribute read instead of triggering a Singleton registry lookup on
        # every call.  `initMovements()` calls each accessor hundreds of
        # times per movement group; caching here eliminates the repeated
        # lookups with no behavioural change (all *Store classes are
        # Singletons keyed by db_path).
        self._runway_store = RunwayStore(db_path)
        self._aircraft_store = AircraftStore(db_path)
        self._engine_store = EngineStore(db_path)
        self._heli_engine_store = HeliEngineStore(db_path)
        self._aircraft_trajectory_store = AircraftTrajectoryStore(db_path)
        self._gate_store = GateStore(db_path)
        self._taxi_route_store = TaxiwayRoutesStore(db_path)
        self._track_store = TrackStore(db_path)

        # instantiate all movement objects
        self.initMovements(debug, show_progress=show_progress)

    def getMovementDatabase(self):
        return self._movement_db

    def getRunwayStore(self):
        return self._runway_store

    def getAircraftStore(self):
        return self._aircraft_store

    def getEngineStore(self):
        return self._engine_store

    def getHeliEngineStore(self):
        return self._heli_engine_store

    def getAircraftTrajectoryStore(self):
        return self._aircraft_trajectory_store

    def getGateStore(self):
        return self._gate_store

    def getTaxiRouteStore(self):
        return self._taxi_route_store

    def getTrackStore(self):
        return self._track_store

    # ── G4: Runway trajectory cache helpers ───────────────────────────────
    #
    # runway_alignment() calls computeSpheroidProject() ~20 times per movement
    # at load time.  The result depends only on (runway, runway_direction,
    # taxi_route, profile_id, track_id) — the same five values for every
    # movement in a group.  We cache the computed AircraftTrajectory in two
    # layers:
    #
    #   1. In-memory per MovementStore instance (free after the first run per
    #      process invocation).
    #   2. Persistent JSON in the .alaqs DB (free on every subsequent run).
    #
    # The JSON schema stores per-point scalars so that the full
    # AircraftTrajectory — including mode, fuel_flow, power, and TAS values
    # needed by FlightEmissionCalculator — can be reconstructed exactly.

    _TRAJ_CACHE_TABLE = "cache_runway_trajectories"

    @staticmethod
    def _ensure_traj_cache_table(db_path: str) -> None:
        """Create cache_runway_trajectories if it does not yet exist."""
        conn = _sqlite3.connect(db_path)
        try:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {MovementStore._TRAJ_CACHE_TABLE} "
                f"(cache_key TEXT PRIMARY KEY, trajectory_json TEXT NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _load_traj_from_db(db_path: str, cache_key: str):
        """Return a reconstructed AircraftTrajectory from the DB cache, or None."""
        from open_alaqs.core.interfaces.AircraftTrajectory import (
            AircraftTrajectory,
            AircraftTrajectoryPoint,
        )

        conn = _sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                f"SELECT trajectory_json FROM {MovementStore._TRAJ_CACHE_TABLE} "
                f"WHERE cache_key = ?",
                (cache_key,),
            )
            row = cur.fetchone()
        except _sqlite3.OperationalError:
            # Table not yet present in this DB — will be created on first write
            return None
        finally:
            conn.close()

        if row is None:
            return None

        data = json.loads(row[0])
        traj = AircraftTrajectory()
        traj.setIdentifier(data.get("identifier", ""))
        traj.setStage(data.get("stage"))
        traj.setDepartureArrivalFlag(data.get("departure_arrival"))
        traj.setWeight(data.get("weight"))
        traj.setIsCartesian(data.get("is_cartesian", False))
        for pt_data in data.get("points", []):
            pt = AircraftTrajectoryPoint()
            pt.setCoordinates(pt_data["x"], pt_data["y"], pt_data["z"])
            if pt_data.get("mode") is not None:
                pt.setMode(pt_data["mode"])
            if pt_data.get("course") is not None:
                pt.setCourse(pt_data["course"])
            if pt_data.get("fuel_flow") is not None:
                pt.setFuelFlow(pt_data["fuel_flow"])
            if pt_data.get("power") is not None:
                pt.setPower(pt_data["power"])
            if pt_data.get("tas") is not None and hasattr(pt, "setTrueAirspeed"):
                pt.setTrueAirspeed(pt_data["tas"])
            if pt_data.get("weight") is not None:
                pt.setWeight(pt_data["weight"])
            traj.addPoint(pt)
        return traj

    @staticmethod
    def _save_traj_to_db(db_path: str, cache_key: str, traj) -> None:
        """Persist traj as JSON in the DB cache."""
        pts = []
        for pt in traj.getPoints():
            coords = pt.getCoordinates()
            pts.append(
                {
                    "x": coords[0],
                    "y": coords[1],
                    "z": coords[2],
                    "mode": pt.getMode(),
                    "course": pt.getCourse(),
                    "fuel_flow": pt.getFuelFlow(),
                    "power": pt.getPower(),
                    "tas": (
                        pt.getTrueAirspeed() if hasattr(pt, "getTrueAirspeed") else None
                    ),
                    "weight": pt.getWeight(),
                }
            )
        data = {
            "identifier": traj.getIdentifier(),
            "stage": traj.getStage(),
            "departure_arrival": traj.getDepartureArrivalFlag(),
            "weight": traj.getWeight(),
            "is_cartesian": traj.isCartesian(),
            "points": pts,
        }
        payload = json.dumps(data)
        conn = _sqlite3.connect(db_path)
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {MovementStore._TRAJ_CACHE_TABLE} "
                f"(cache_key, trajectory_json) VALUES (?, ?)",
                (cache_key, payload),
            )
            conn.commit()
        finally:
            conn.close()

    def ProgressBarWidget(self):
        progressbar = QtWidgets.QProgressDialog("Please wait...", "Cancel", 0, 99)
        progressbar.setWindowTitle("Initializing Movements from Database")
        progressbar.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()

        return progressbar

    def initMovements(self, debug=False, show_progress=True):  # noqa: C901

        # G4: Ensure the runway-trajectory cache table exists in the DB.
        # This is a no-op if the table is already present.
        try:
            MovementStore._ensure_traj_cache_table(self._db_path)
        except Exception as _e:
            logger.warning("Could not create runway trajectory cache table: %s", _e)

        # G4: In-memory trajectory cache for this invocation.
        # Key: (rwy, rwy_dir, tx_route_name, prf_id, trk_id)
        # Value: AircraftTrajectory (shared reference, read-only after creation)
        _mem_traj_cache: dict = {}

        # Start a progressbar only if show_progress is True
        progressbar = self.ProgressBarWidget() if show_progress else None

        # Use stages to update the progress bar
        stage_1 = (
            ProgressBarStage.firstStage(progressbar, 7, maximum=7)
            if progressbar
            else None
        )

        # Get the movements from the database as a dataframe
        mdf = pd.DataFrame.from_dict(
            self.getMovementDatabase().getEntries(), orient="index"
        )
        logger.info("Number of movements in the DB: %s", mdf.shape[0])
        if mdf.empty:
            return

        df_cols = [
            "aircraft",
            "engine_name",
            "runway",
            "runway_direction",
            "gate",
            "taxi_route",
            "profile_id",
            "trajectory",
            "runway_trajectory",
            "track_id",
        ]
        eq_mdf = pd.DataFrame(index=mdf.index, columns=df_cols)
        eq_mdf = eq_mdf.fillna(np.nan)  # fill with None rather than NaNs

        # Check if aircraft exist in the database
        if stage_1:
            stage_1.nextValue()

        aircraft_store = self.getAircraftStore()
        for acf in mdf["aircraft"].unique():
            store_has_key = aircraft_store.hasKey(acf)
            eq_mdf.loc[mdf.aircraft == acf, "aircraft"] = (
                acf if store_has_key else np.nan
            )
            if not store_has_key:
                logger.error(f"Aircraft '{acf}' wasn't found in the DB")

        # Check if engines exist in the database
        if stage_1:
            stage_1.nextValue()

        engine_store = self.getEngineStore()
        heli_engine_store = self.getHeliEngineStore()
        for eng in mdf["engine_name"].unique():

            indices = mdf["engine_name"] == eng

            if engine_store.hasKey(eng):
                eq_mdf.loc[indices, "engine_name"] = eng

            elif heli_engine_store.hasKey(eng):
                eq_mdf.loc[indices, "engine_name"] = eng

            else:
                logger.debug("Engine %s not in ALAQS DB", eng)

                # Get the aircraft
                def_ac = mdf[mdf["engine_name"] == eng]["aircraft"].iloc[0]

                # Check if the aircraft exists in the database
                if aircraft_store.hasKey(def_ac):

                    # Get the default engine for this aircraft
                    eng = aircraft_store.getObject(def_ac).getDefaultEngine().getName()

                    logger.debug(
                        "\t +++ taking default engine %s for aircraft %s", eng, def_ac
                    )

                    if engine_store.hasKey(eng):
                        eq_mdf.loc[indices, "engine_name"] = eng
                    else:
                        eq_mdf.loc[indices, "engine_name"] = None

        # Check if runways exist in the database
        if stage_1:
            stage_1.nextValue()

        runway_store = self.getRunwayStore()
        for rwy in mdf["runway"].unique():

            indices = mdf["runway"] == rwy

            # Make sure runways are always 2 characters or more
            rwy = rwy.zfill(2)

            if runway_store.isinKey(rwy):
                eq_mdf.loc[indices, "runway_direction"] = rwy
                rwy_used = [
                    key for key in list(runway_store.getObjects().keys()) if rwy in key
                ]
                if len(rwy_used) > 1:
                    logger.warning(
                        f"Runway {rwy} was found in the DB multiple " "times."
                    )
                eq_mdf.loc[indices, "runway"] = rwy_used[0]

            else:
                eq_mdf.loc[indices, "runway"] = np.nan
                logger.warning(f"Runway '{rwy}' wasn't found in the DB")

        # Check if gates exist in the database
        if stage_1:
            stage_1.nextValue()

        gate_store = self.getGateStore()
        for gte in mdf["gate"].unique():
            store_has_key = gate_store.hasKey(gte)
            eq_mdf.loc[mdf["gate"] == gte, "gate"] = gte if store_has_key else np.nan
            if not store_has_key:
                logger.warning(f"Gate '{gte}' wasn't found in the DB")

        # Check if taxi routes exist in the database
        if stage_1:
            stage_1.nextValue()

        # Fill empty taxi routes
        empty_tr = (mdf["taxi_route"] == "") | (mdf["taxi_route"].isna())
        default_tr_columns = ["gate", "runway", "departure_arrival"]
        mdf.loc[empty_tr, "taxi_route"] = (
            mdf.loc[empty_tr, default_tr_columns].apply("/".join, axis=1) + "/1"
        )

        taxi_route_store = self.getTaxiRouteStore()
        for txr in mdf["taxi_route"].unique():
            indices = mdf[mdf["taxi_route"] == txr].index
            if taxi_route_store.hasKey(txr):
                eq_mdf.loc[indices, "taxi_route"] = txr
            else:
                eq_mdf.loc[indices, "taxi_route"] = np.nan
                logger.warning(
                    f'Taxiroute "{txr}" was not found in the taxi routes database!'
                )

            # TODO OPENGIS.ch: the alternative taxi route finder below causes multiple taxi alternative taxi routes to be assigned to a movement
            # The alternatives should be constraint only for taxi routes from this or nearby gate and should be only one alternative.
            # else:
            #     alt_routes = []
            #     if "/D/" in txr:
            #         alt_routes = difflib.get_close_matches(txr, departure_taxi_routes)
            #     elif "/A/" in txr:
            #         alt_routes = difflib.get_close_matches(txr, arrival_taxi_routes)

            #     if len(alt_routes) > 0:
            #         eq_mdf.loc[indices, "taxi_route"] = alt_routes[0]
            #         logger.warning(
            #             "Taxiroute '%s' was replaced with '%s'", txr, alt_routes[0]
            #         )
            #     else:
            #         logger.error(
            #             "No taxiroute found to replace '%s' "
            #             "which is not in the database",
            #             txr,
            #         )
            #         eq_mdf.loc[indices, "taxi_route"] = np.nan

        # Check if track exist in the database
        if stage_1:
            stage_1.nextValue()

        track_store = self.getTrackStore()
        for trk in mdf["track_id"].unique():
            store_has_key = track_store.hasKey(trk)
            eq_mdf.loc[mdf.track_id == trk, "track_id"] = trk if store_has_key else ""
            if not store_has_key:
                if not trk:
                    logger.warning("Track has empty name and will be skipped!")
                else:
                    logger.warning(f"Track '{trk}' wasn't found in the DB")

        # Check if profiles exist in the database
        if stage_1:
            stage_1.nextValue()

        # Get the unique profiles
        profile_unique = mdf["profile_id"].astype(str).unique()

        # Check if the profiles exist in the store
        trajectory_store = self.getAircraftTrajectoryStore()

        # Add a default profile to the eq_mdf
        for _, airgroup in mdf.groupby(["aircraft", "departure_arrival"]):
            ij_ = airgroup.index
            _ac = airgroup["aircraft"].iloc[0]
            _aircraft = aircraft_store.getObject(_ac)
            if _aircraft is not None:
                _ad = airgroup["departure_arrival"].iloc[0]
                if _ad == "A":
                    profile_id = _aircraft.getDefaultArrivalProfileName()
                elif _ad == "D":
                    profile_id = _aircraft.getDefaultDepartureProfileName()
                else:
                    logger.debug(
                        "%s for AC %s is not recognised as either "
                        "and arrival or departure",
                        _ad,
                        _ac,
                    )

                    # setting to none, e.g. means not possible to set a default value
                    eq_mdf.loc[ij_, "profile_id"] = None

                    continue
                eq_mdf.loc[ij_, "profile_id"] = profile_id
            else:
                logger.debug("AC %s not in AircraftStore", _ac)
                continue

        # Add nones if it matches the conditions, e.g. set original profile
        # if it is among available profiles in trajectory_store
        for prf in profile_unique:
            indices = mdf[mdf["profile_id"] == prf].index
            if (
                len(indices) != 0
                and prf
                and not pd.isna(prf)
                and trajectory_store.hasKey(prf)
            ):
                eq_mdf.loc[indices, "profile_id"] = prf
            else:
                logger.warning(
                    f"Lack of profile_id: '{prf}' using default value: '{eq_mdf.loc[indices[0], 'profile_id']}' "
                    f"for movements: {mdf.loc[indices]['oid'].values}"
                )

        # now if remained a profile_id as None in eq_mdf means that:
        # A) profile_id in original mdf is None or
        # B) was not possible to get a default value
        # NOTE: that leaving None value to profile_id make it retained later
        # NOTE: not dropped elements from eq_mdf to maintain index parity with
        # original mdf
        none_profile_ids = eq_mdf["profile_id"].isna()
        for row in mdf[none_profile_ids].itertuples():
            logger.warning(
                f'Skip movement "{row.oid}" due to neither a profile "{row.profile_id}" in "default_aircraft_profiles" table, nor a default value for that aircraft!'
            )

        # Get unique combinations of eq_mdf
        u_columns = [
            "runway",
            "runway_direction",
            "taxi_route",
            "profile_id",
            "track_id",
        ]
        heli_engine_store = self.getHeliEngineStore()
        engine_store = self.getEngineStore()

        # Start the next stage
        if stage_1:
            stage_2 = stage_1.nextStage(
                duration=10, maximum=len(eq_mdf[~none_profile_ids].groupby(u_columns))
            )
            logger.debug(
                f"finished stage 1 "
                f"(n={stage_1._max - stage_1._min}) "
                f"in {stage_1._end_time - stage_1._start_time}"
            )
        else:
            stage_2 = None

        for (rwy, rwy_dir, tx_route, prf_id, trk_id), mov_df in eq_mdf[
            ~none_profile_ids
        ].groupby(u_columns):
            # Get the indices
            inds = mov_df.index

            # ── G4: Runway trajectory — compute once per group ────────────
            #
            # All movements in this group share the same (runway,
            # runway_direction, taxi_route, profile_id, track_id) so
            # runway_alignment() produces the same AircraftTrajectory for
            # every one of them.  We compute it once and reuse the result,
            # saving ~20 computeSpheroidProject() calls per repeated
            # movement.
            #
            # Lookup order:
            #   1. In-memory cache (free after the first group in this invocation)
            #   2. Persistent DB cache (free on every re-run of the same study)
            #   3. Full runway_alignment() computation (only on true first run)
            _traj_cache_key = (
                str(rwy),
                str(rwy_dir),
                str(tx_route) if tx_route else "",
                str(prf_id),
                str(trk_id) if trk_id else "",
            )
            _db_cache_key = "|".join(_traj_cache_key)

            _group_traj = _mem_traj_cache.get(_traj_cache_key)
            if _group_traj is None:
                try:
                    _group_traj = MovementStore._load_traj_from_db(
                        self._db_path, _db_cache_key
                    )
                except Exception as _e:
                    logger.debug("DB trajectory cache read failed: %s", _e)
                    _group_traj = None

            if _group_traj is None:
                # Cache miss — compute using the first movement in the group
                first_idx = inds[0]
                fm0 = eq_mdf.loc[first_idx]
                _proxy0 = Movement()
                _proxy0.setRunway(runway_store.getObject(fm0["runway"]))
                _proxy0.setRunwayDirection(fm0["runway_direction"])
                _proxy0.setTrack(track_store.getObject(fm0["track_id"]))
                _proxy0.setTaxiRoute(taxi_route_store.getObject(fm0["taxi_route"]))
                _proxy0.setTrajectory(trajectory_store.getObject(fm0["profile_id"]))
                _raw_t0 = mdf.loc[first_idx, "runway_time"]
                if isinstance(_raw_t0, str):
                    _proxy0._time = conversion.convertTimeToSeconds(_raw_t0)
                elif isinstance(_raw_t0, (int, float)):
                    _proxy0._time = float(_raw_t0)
                _proxy0.updateTrajectoryAtRunway()
                _group_traj = _proxy0.getTrajectoryAtRunway()

                # Persist in both caches (skip if computation failed)
                if _group_traj is not None:
                    _mem_traj_cache[_traj_cache_key] = _group_traj
                    try:
                        MovementStore._save_traj_to_db(
                            self._db_path, _db_cache_key, _group_traj
                        )
                    except Exception as _e:
                        logger.debug("DB trajectory cache write failed: %s", _e)
            else:
                _mem_traj_cache[_traj_cache_key] = _group_traj  # warm memory cache

            # Loop over all `mov_df` to set the correct aircraft, gate and departure flag
            # e.g. for all particular value that are not equal due to group by
            # NOTE: this implementation makes the group by less efficient, but ensures the correct values
            for eq_mdf_index in inds:

                # Create a proxy movement
                proxy_mov = Movement()

                fm = eq_mdf.loc[eq_mdf_index]
                fm_gate = gate_store.getObject(fm["gate"])
                fm_aircraft = aircraft_store.getObject(fm["aircraft"])
                fm_runway = runway_store.getObject(fm["runway"])
                fm_taxi_route = taxi_route_store.getObject(fm["taxi_route"])
                fm_trajectory = trajectory_store.getObject(fm["profile_id"])
                fm_track = track_store.getObject(fm["track_id"])

                if engine_store.hasKey(fm["engine_name"]):
                    fm_engine = engine_store.getObject(fm["engine_name"])
                elif heli_engine_store.hasKey(fm["engine_name"]):
                    fm_engine = heli_engine_store.getObject(fm["engine_name"])
                else:
                    fm_engine = None

                fm_departure_arrival = mdf.loc[eq_mdf_index]["departure_arrival"]

                # Set the parameters of the proxy movement
                proxy_mov.setGate(fm_gate)
                proxy_mov.setAircraft(fm_aircraft)
                proxy_mov.setAircraftEngine(fm_engine)
                proxy_mov.setRunway(fm_runway)
                proxy_mov.setRunwayDirection(fm["runway_direction"])
                proxy_mov.setTrack(fm_track)
                proxy_mov.setTaxiRoute(fm_taxi_route)
                proxy_mov.setTrajectory(fm_trajectory)
                _raw_rwy_time = mdf.loc[eq_mdf_index, "runway_time"]
                if isinstance(_raw_rwy_time, str):
                    proxy_mov._time = conversion.convertTimeToSeconds(_raw_rwy_time)
                elif isinstance(_raw_rwy_time, (int, float)):
                    proxy_mov._time = float(_raw_rwy_time)
                # else: leave as None; TrajectoryTransformer will log it
                # G4: assign pre-computed group trajectory (no per-movement
                # geodesic computation). setTrajectoryAtRunway replaces the
                # updateTrajectoryAtRunway() call that would otherwise re-run
                # runway_alignment().
                proxy_mov.setTrajectoryAtRunway(_group_traj)
                proxy_mov.setDepartureArrivalFlag(fm_departure_arrival)

                # Update the dataframe
                eq_mdf.loc[eq_mdf_index, "runway"] = proxy_mov.getRunway()
                eq_mdf.loc[eq_mdf_index, "taxi_route"] = proxy_mov.getTaxiRoute()
                eq_mdf.loc[eq_mdf_index, "track"] = proxy_mov.getTrack()
                eq_mdf.loc[eq_mdf_index, "trajectory"] = proxy_mov.getTrajectory()
                eq_mdf.loc[eq_mdf_index, "runway_trajectory"] = (
                    proxy_mov.getTrajectoryAtRunway()
                )
                eq_mdf.loc[eq_mdf_index, "departure_arrival"] = (
                    proxy_mov.getDepartureArrivalFlag()
                )

                eq_mdf.loc[eq_mdf_index, "gate_obj"] = proxy_mov.getGate()
                eq_mdf.loc[eq_mdf_index, "aircraft_obj"] = proxy_mov.getAircraft()
                eq_mdf.loc[eq_mdf_index, "engine_obj"] = proxy_mov.getAircraftEngine()

            if stage_2:
                stage_2.nextValue()

        # Get the movements to retain
        # NOTE: not available or not default configurable profiles would have "profile_id" as None
        mdf_retained = eq_mdf[~eq_mdf[df_cols].isna().any(axis=1)]
        logger.info("Number of movements retained: %s" % mdf_retained.shape[0])

        # Start the final stage
        if stage_2:
            stage_3 = stage_2.finalStage(maximum=mdf.shape[0])
            logger.debug(
                f"finished stage 2 "
                f"(n={stage_2._max - stage_2._min}) "
                f"in {stage_2._end_time - stage_2._start_time}"
            )
        else:
            stage_3 = None

        # Create a movement for every entry in the database
        movement_db_entries = self.getMovementDatabase().getEntries()
        for key, movement_dict in movement_db_entries.items():

            # Create a movement
            mov = Movement(movement_dict)

            # Get the relevant entry from mdf_retained
            try:
                mov_df_entry = mdf_retained.loc[key]
            except KeyError:
                logger.warning(
                    "Operation with 'oid' = %s will not be "
                    "accounted for due to missing data",
                    key,
                )
                continue

            # Get the relevant objects
            mov_aircraft = mov_df_entry["aircraft_obj"]

            if mov_aircraft.getGroup() == "HELICOPTER":

                # Get the helicopter engine
                mov_engine = heli_engine_store.getObject(mov_df_entry["engine_name"])
            else:

                # Get the aircraft engine
                mov_engine = engine_store.getObject(mov_df_entry["engine_name"])

            # Replace with Default Engine if it can't be found
            if mov_engine is None:
                mov_engine = mov_aircraft.getDefaultEngine()
                logger.info(
                    "Engine wasn't found for movement %s. "
                    "Will use default engine (%s).",
                    mov.getName(),
                    mov_engine.getName(),
                )

            # Add the relevant objects to the movement
            mov.setGate(mov_df_entry["gate_obj"])
            mov.setAircraft(mov_aircraft)
            mov.setAircraftEngine(mov_engine)
            mov.setRunway(mov_df_entry["runway"])
            mov.setRunwayDirection(mov_df_entry["runway_direction"])
            mov.setTaxiRoute(mov_df_entry["taxi_route"])
            mov.setTrack(mov_df_entry["track"])
            mov.setTrajectory(mov_df_entry["trajectory"])
            mov.setTrajectoryAtRunway(mov_df_entry["runway_trajectory"])

            self.setObject(movement_dict.get("oid", "unknown"), mov)

            # Update the progress bar
            if stage_3:
                stage_3.nextValue()
            if progressbar and progressbar.wasCanceled():
                logger.warning(
                    "user canceled initMovements, " "so it might be incomplete"
                )
                break

        if stage_3:
            stage_3.finish()
            logger.debug(
                f"finished stage 3 "
                f"(n={stage_3._max - stage_3._min}) "
                f"in {stage_3._end_time - stage_3._start_time}"
            )


class MovementDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to user-defined movements stored in the database
    """

    def __init__(
        self,
        db_path_string,
        table_name_string="user_aircraft_movements",
        table_columns_type_dict=None,
        primary_key="oid",
        deserialize=True,
    ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict(
                [
                    ("oid", "INTEGER PRIMARY KEY"),
                    ("runway_time", "TIMESTAMP"),
                    ("block_time", "TIMESTAMP"),
                    ("aircraft", "TEXT"),
                    ("gate", "TEXT"),
                    ("departure_arrival", "TEXT"),
                    ("runway", "TEXT"),
                    ("engine_name", "TEXT"),
                    ("profile_id", "TEXT"),
                    ("track_id", "TEXT"),
                    ("taxi_route", "TEXT"),
                    ("tow_ratio", "DECIMAL NULL"),
                    ("apu_code", "INTEGER"),
                    ("gate_emissions_code", "INTEGER DEFAULT 1"),
                    ("taxi_engine_count", "INTEGER"),
                    (
                        "set_time_of_main_engine_start_after_block_off_in_s",
                        "DECIMAL NULL",
                    ),
                    (
                        "set_time_of_main_engine_start_before_takeoff_in_s",
                        "DECIMAL NULL",
                    ),
                    (
                        "set_time_of_main_engine_off_after_runway_exit_in_s",
                        "DECIMAL NULL",
                    ),
                    ("engine_thrust_level_for_taxiing", "DECIMAL NULL"),
                    ("taxi_fuel_ratio", "DECIMAL NULL"),
                    ("number_of_stop_and_gos", "DECIMAL NULL"),
                ]
            )

        SQLSerializable.__init__(
            self,
            db_path_string,
            table_name_string,
            table_columns_type_dict,
            primary_key,
        )

        if self._db_path and deserialize:
            self.deserialize()
