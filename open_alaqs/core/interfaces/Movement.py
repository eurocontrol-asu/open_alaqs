import copy
import difflib
import math
import sys
from collections import OrderedDict
from inspect import currentframe, getframeinfo
from typing import TypedDict

import matplotlib
import numpy as np
import pandas as pd
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)
from qgis.PyQt import QtCore, QtWidgets
from shapely.geometry import LineString, MultiLineString
from shapely.wkt import loads

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Aircraft import Aircraft, AircraftStore
from open_alaqs.core.interfaces.AircraftTrajectory import (
    AircraftTrajectory,
    AircraftTrajectoryPoint,
    AircraftTrajectoryStore,
)
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.EngineStore import EngineStore, HeliEngineStore
from open_alaqs.core.interfaces.Gate import GateStore
from open_alaqs.core.interfaces.Runway import RunwayStore
from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.core.interfaces.Store import Store
from open_alaqs.core.interfaces.Taxiway import TaxiwayRoutesStore
from open_alaqs.core.interfaces.Track import TrackStore
from open_alaqs.core.tools import conversion, spatial
from open_alaqs.core.tools.nox_correction_ambient import (
    nox_correction_for_ambient_conditions,
)
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
    "pm10_prefoa3_g": 0.0,
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
    "pm10_prefoa3_g_kg": 0.0,
    "pm10_nonvol_g_kg": 0.0,
    "pm10_sul_g_kg": 0.0,
    "pm10_organic_g_kg": 0.0,
    "nvpm_g_kg": 0.0,
    "nvpm_number": 0.0,
}


class EmissionsDict(TypedDict):
    distance_space: float
    distance_time: float
    emissions: list[Emission]


class Movement:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._time = None
        _col = "runway_time"
        if _col not in val:
            if len(val):
                logger.error("'%s' not set, but necessary input" % (_col))
        else:
            self._time = conversion.convertTimeToSeconds(val[_col])
            if self._time is None:
                logger.error(
                    "Could not convert '%s', which is of type '%s', to a valid time format."
                    % (str(val[_col]), str(type(val[_col])))
                )
        self._block_time = None
        _col = "block_time"
        if _col not in val:
            if len(val):
                logger.error("'%s' not set, but necessary input" % (_col))
        else:
            self._block_time = conversion.convertTimeToSeconds(val[_col])
            if self._block_time is None:
                logger.error(
                    "Could not convert '%s', which is of type '%s', to a valid time format."
                    % (str(val[_col]), str(type(val[_col])))
                )

        self._engine_name = str(val.get("engine_name", ""))
        self._apu_code = (
            int(val["apu_code"]) if "apu_code" in val and val["apu_code"] else 0
        )
        # self._apu_code = 0 #(stand only), 1 (stand and taxiway) or 2 ()stand, taxiing and take - off / climb - out or approach / landing

        self._oid = val.get("oid", None)
        self._domestic = str(val.get("domestic", ""))
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
            val.get("engine_thrust_level_taxiing"), 0.07
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

    def loadAPUinfo(self, seg):
        gate_type = self.getGate().getType()
        ac_type = self.getAircraft().getGroup()
        apu_time_ = 0
        apu_emis_ = None
        try:
            if ac_type and gate_type:
                apu_emis_ = self.getAircraft().getApuEmissions()
                _apu_times = self.getAircraft().getApuTimes()
                if ac_type in _apu_times:
                    _ac_apu_times = _apu_times[ac_type]
                    if gate_type in _ac_apu_times:
                        _gate_apu_times = _ac_apu_times[gate_type]
                        apu_time_ = _gate_apu_times[
                            "arr_s" if self.isArrival() else "dep_s"
                        ]
        except Exception:
            if seg == 0:
                logger.info(
                    "No APU info for %s (AC type: %s, gate type: %s)"
                    % (self.getName(), ac_type, gate_type)
                )
        return apu_time_, apu_emis_

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

    def calculateGateEmissions(self, sas="none") -> list[EmissionsDict]:
        """Calculate gate emissions for a specific source based on the source
         name and time period. The method for calculating emissions from gates
         requires establishing the sum of three types of emissions:

        1. Emissions from GSE - Data comes from default_gate
        2. Emissions from GPU
        3. Emissions from APU
        4. Emissions from Main Engine Start-up
        """
        emissions: list[EmissionsDict] = []
        # calculate emissions for ground equipment (i.e. GPU and GSE)
        if (
            self.getGate() is not None
            and not self.getAircraft().getGroup() == "HELICOPTER"
        ):
            # GPU emissions
            gpu_emissions = Emission(defaultValues=defaultEmissions)
            # GPU, lower edge: 0m, upper edge: 5m
            if sas == "default" or sas == "smooth & shift":
                gpu_emissions.setVerticalExtent({"z_min": 0, "z_max": 5})
            # GSE emissions
            gse_emissions = Emission(defaultValues=defaultEmissions)
            # GSE, lower edge: 0m, upper edge: 5m
            if sas == "default" or sas == "smooth & shift":
                gse_emissions.setVerticalExtent({"z_min": 0, "z_max": 5})

            ac_group_GSE = self.getAircraftGroupMatch("gse")  # e.g. 'JET SMALL'
            ac_group_GPU = self.getAircraftGroupMatch("gpu")  # e.g. 'JET SMALL'

            # if ac_group_GSE is None:
            occupancy_in_min_GSE = self.getGateOccupancy(ac_group_GSE, "gse")
            occupancy_in_min_GPU = self.getGateOccupancy(ac_group_GPU, "gpu")

            gpu_emission_index = self.getGate().getEmissionIndexGPU(
                ac_group_GPU, self._departure_arrival
            )
            pollutants = (
                PollutantType.CO,
                PollutantType.HC,
                PollutantType.NOx,
                PollutantType.SOx,
                PollutantType.PM10,
            )

            if gpu_emission_index is not None:
                for pollutant_type in pollutants:
                    value_kg_hour = gpu_emission_index.get_value(
                        pollutant_type, "kg_hour"
                    )
                    gpu_emissions.add_value(
                        pollutant_type,
                        PollutantUnit.GRAM,
                        # TODO OPENGIS.ch: move the kg_hour conversion within the `Emission.add_value` method
                        (value_kg_hour * 1000.0 * occupancy_in_min_GPU / 60.0),
                    )

                gpu_emissions.setGeometryText(self.getGate().getGeometryText())
                emissions.append(
                    {
                        "distance_space": 0.0,
                        "distance_time": 0.0,
                        "emissions": gpu_emissions,
                    }
                )
            # else:
            #     logger.warning("No GPU emissions for %s"%self.getName())

            gse_emission_index = self.getGate().getEmissionIndexGSE(
                ac_group_GSE, self._departure_arrival
            )
            if gse_emission_index is not None:
                for pollutant_type in pollutants:
                    value_kg_hour = gse_emission_index.get_value(
                        pollutant_type, "kg_hour"
                    )
                    gpu_emissions.add_value(
                        pollutant_type,
                        PollutantUnit.GRAM,
                        # TODO OPENGIS.ch: move the kg_hour conversion within the `Emission.add_value` method
                        (value_kg_hour * 1000.0 * occupancy_in_min_GSE / 60.0),
                    )

                gse_emissions.setGeometryText(self.getGate().getGeometryText())
                emissions.append(
                    {
                        "distance_space": 0.0,
                        "distance_time": 0.0,
                        "emissions": gse_emissions,
                    }
                )
            # else:
            #     logger.warning("No GSE emissions for %s"%self.getName())

        else:
            if not self.getAircraft().getGroup() == "HELICOPTER":
                logger.warning(
                    "Did not find a gate for movement '%s'" % (self.getName())
                )
            else:
                logger.warning(
                    "Zero GPU/GSE emissions will be added for %s" % (self.getName())
                )
                if self.getGate() is not None:
                    # GSE emissions
                    gse_emissions = Emission(defaultValues=defaultEmissions)
                    # GSE, lower edge: 0m, upper edge: 5m
                    if sas == "default" or sas == "smooth & shift":
                        gse_emissions.setVerticalExtent({"z_min": 0, "z_max": 5})
                    gse_emissions.setGeometryText(self.getGate().getGeometryText())
                    emissions.append(
                        {
                            "distance_space": 0.0,
                            "distance_time": 0.0,
                            "emissions": gse_emissions,
                        }
                    )

        return emissions

    def CalculateParallels(
        self, geometry_wkt_init, width, height, shift, EPSG_source, EPSG_target
    ):

        (geo_wkt, swap) = spatial.reproject_geometry(
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

    def calculateTaxiingEmissions(  # noqa: C901
        self, method=None, mode="TX", sas="none"
    ):
        if method is None:
            method = {"name": "bymode", "config": {}}
        try:
            total_taxiing_time = abs(self.getBlockTime() - self.getRunwayTime())
        except Exception:
            total_taxiing_time = None
        # print("total_taxiing_time %s"%total_taxiing_time)
        emissions = []

        if self.getTaxiRoute() is not None:
            if not self.getAircraft().getGroup() == "HELICOPTER":

                # calculate taxiing_length and taxiing_time_from_segments (initial)
                taxiing_length = 0.0
                init_taxiing_time_from_segments = 0.0
                for index_segment_, taxiway_segment_ in enumerate(
                    self.getTaxiRoute().getSegments()
                ):
                    taxiing_length += taxiway_segment_.getLength()
                    init_taxiing_time_from_segments += taxiway_segment_.getTime()
                    # taxiway_segment_.getLength()/taxiway_segment_.getSpeed() # getLength in m, getSpeed in m/s
                    # taxiway_segment_.setSpeed(10) #setSpeed is in m/s, in Open-ALAQS km/h, default value is 30 km/h or ~8 m/s
                # print("init_taxiing_time_from_segments %s"%init_taxiing_time_from_segments)
                # print("taxiing_length %s"%taxiing_length)

                if total_taxiing_time is None:
                    total_taxiing_time = init_taxiing_time_from_segments
                    # in m/s
                    taxiing_average_speed = conversion.convertToFloat(
                        taxiing_length
                    ) / conversion.convertToFloat(init_taxiing_time_from_segments)
                else:
                    taxiing_average_speed = conversion.convertToFloat(
                        taxiing_length
                    ) / conversion.convertToFloat(total_taxiing_time)
                # print("taxiing_average_speed %s"%taxiing_average_speed)

                # Total taxiing time for calculating taxiing emissions is taken from the Movements Table
                # Queuing emissions are added when taxiing time (traffic log) is greater than user defined taxiroute info (speed, time, etc)
                queuing_time = (
                    (total_taxiing_time - init_taxiing_time_from_segments)
                    if total_taxiing_time > init_taxiing_time_from_segments
                    else 0
                )
                # print("queuing_time %s"%queuing_time)

                emission_index_ = None
                # ToDo: Only bymode method for now ..
                if method["name"] == "bymode":
                    emission_index_ = (
                        self.getAircraftEngine()
                        .getEmissionIndex()
                        .getEmissionIndexByMode(mode)
                    )
                else:
                    # get emission indices based on the engine-thrust setting as defined in the movements table
                    emission_index_ = (
                        self.getAircraftEngine()
                        .getEmissionIndex()
                        .getEmissionIndexByPowerSetting(
                            self.getEngineThrustLevelTaxiing(), method=method
                        )
                    )

                if emission_index_ is None:
                    logger.error(
                        "Did not find emission index for aircraft with type '%s'."
                        % (self.getAircraft())
                    )
                else:
                    taxiing_time_while_aircraft_moving = 0.0

                    # set the geometry as line with linear interpolation between start and endpoint
                    for index_segment_, taxiway_segment_ in enumerate(
                        self.getTaxiRoute().getSegments()
                    ):
                        em_ = Emission(defaultValues=defaultEmissions)

                        if sas == "default" or sas == "smooth & shift":
                            sas_method = "default" if sas == "default" else "sas"

                            # try:
                            hor_ext = (
                                self.getAircraft()
                                .getEmissionDynamicsByMode()["TX"]
                                .getEmissionDynamics(sas_method)["horizontal_extension"]
                            )
                            ver_ext = (
                                self.getAircraft()
                                .getEmissionDynamicsByMode()["TX"]
                                .getEmissionDynamics(sas_method)["vertical_extension"]
                            )
                            ver_shift = (
                                self.getAircraft()
                                .getEmissionDynamicsByMode()["TX"]
                                .getEmissionDynamics(sas_method)["vertical_shift"]
                            )
                            logger.debug(f"{getframeinfo(currentframe())}")
                            logger.debug("ver_shift: %s", ver_shift)
                            logger.debug("ver_ext: %s", ver_ext)
                            logger.debug("hor_ext: %s", hor_ext)
                            # print(hor_ext, ver_ext, ver_shift)

                            em_.setVerticalExtent(
                                {"z_min": 0.0 + ver_shift, "z_max": ver_ext + ver_shift}
                            )

                            logger.debug(
                                {"z_min": 0.0 + ver_shift, "z_max": ver_ext + ver_shift}
                            )

                            # ToDo: add height
                            multipolygon = spatial.ogr.Geometry(
                                spatial.ogr.wkbMultiPolygon
                            )
                            all_points = spatial.getAllPoints(
                                taxiway_segment_.getGeometryText()
                            )
                            for p_, point_ in enumerate(all_points):
                                # point_ example (802522.928722, 5412293.034699, 0.0)
                                if p_ + 1 < len(all_points):
                                    # break
                                    geometry_wkt_i = (
                                        "LINESTRING Z(%s %s %s, %s %s %s)"
                                        % (
                                            all_points[p_][0],
                                            all_points[p_][1],
                                            all_points[p_][2],
                                            all_points[p_ + 1][0],
                                            all_points[p_ + 1][1],
                                            all_points[p_ + 1][2],
                                        )
                                    )
                                    leftline, rightline = self.CalculateParallels(
                                        geometry_wkt_i, hor_ext, 0, 0, 3857, 4326
                                    )  # in lon / lat !
                                    poly_geo = spatial.getRectangleXYZFromBoundingBox(
                                        leftline, rightline, 3857, 4326
                                    )
                                    multipolygon.AddGeometry(poly_geo)
                                    em_.setGeometryText(multipolygon.ExportToWkt())
                            # except Exception:
                            #     logger.warning("Error while retrieving Smooth & Shift parameters. Switching to normal method.")
                            #     em_.setGeometryText(taxiway_segment_.getGeometryText())

                        else:
                            # logger.info("Calculate taxiing emissions WITHOUT Smooth & Shift Approach.")
                            em_.setGeometryText(taxiway_segment_.getGeometryText())

                        #   add emission factors,
                        #   multiply with occupancy time and number of engines

                        # If time spent in segments < taxiing time in movement table
                        if total_taxiing_time <= init_taxiing_time_from_segments:
                            new_taxiway_segment_time = (
                                taxiway_segment_.getLength() / taxiing_average_speed
                            )
                        else:
                            new_taxiway_segment_time = (
                                taxiway_segment_.getLength()
                                / taxiway_segment_.getSpeed()
                            )

                        taxiing_time_while_aircraft_moving += new_taxiway_segment_time

                        number_of_engines = self.getAircraft().getEngineCount()
                        taxi_fuel_ratio = 1.0

                        start_emissions = self.getAircraftEngine().getStartEmissions()
                        include_start_emissions = True
                        if start_emissions is None:
                            include_start_emissions = False
                        started_engine_set = False

                        # load APU time and emission factors
                        apu_t, apu_em = self.loadAPUinfo(index_segment_)
                        apu_time = 0
                        if (apu_t is not None and apu_em is not None) and (apu_t > 0):
                            # APU emissions will be added to the stand only
                            if self.getAPUCode() == 1 and index_segment_ == 0:
                                apu_time = apu_t
                            # APU emissions will be added to the stand and the taxiroute
                            elif self.getAPUCode() == 2:
                                if apu_t < total_taxiing_time:
                                    # + additional time based on the assumption that the APU is running longer than usual
                                    # first segment taxiing time is included in apu_t (assumption)
                                    apu_time = (
                                        apu_t
                                        if index_segment_ == 0
                                        else new_taxiway_segment_time
                                    )

                                elif apu_t >= total_taxiing_time:
                                    # first segment gets most of the APU emissions, rest is as per taxiing time
                                    apu_time = (
                                        (apu_t - total_taxiing_time)
                                        + new_taxiway_segment_time
                                        if index_segment_ == 0
                                        else new_taxiway_segment_time
                                    )
                            else:
                                apu_time = 0
                                # logger.error("No APU or wrong APU code for mov %s. APU emissions will be set to 0."
                                #              %self.getName())

                            if "fuel_kg_sec" in apu_em:
                                em_.addFuel(apu_em["fuel_kg_sec"] * apu_time)
                            if "co2_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.CO2,
                                    PollutantUnit.GRAM,
                                    apu_em["co2_g_s"] * apu_time,
                                )
                            if "co_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.CO,
                                    PollutantUnit.GRAM,
                                    apu_em["co_g_s"] * apu_time,
                                )
                            if "hc_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.HC,
                                    PollutantUnit.GRAM,
                                    apu_em["hc_g_s"] * apu_time,
                                )
                            if "nox_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.NOx,
                                    PollutantUnit.GRAM,
                                    apu_em["nox_g_s"] * apu_time,
                                )
                            if "sox_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.SOx,
                                    PollutantUnit.GRAM,
                                    apu_em["sox_g_s"] * apu_time,
                                )
                            if "pm10_g_s" in apu_em:
                                em_.add_value(
                                    PollutantType.PM10,
                                    PollutantUnit.GRAM,
                                    apu_em["pm10_g_s"] * apu_time,
                                )

                        # else:
                        #     print("No APU or wrong APU code for mov %s (%s, %s)"%(self.getName(),
                        #                                                           self.getAircraft().getGroup(), self.getGate().getType()))

                        # cnt_apu_time += apu_time
                        # CAEPPORT
                        self.setTaxiEngineCount(self.getAircraft().getEngineCount())

                        if self.isDeparture():

                            # Single-Engine Taxiing
                            if self.getTaxiEngineCount() is not None:

                                if (
                                    self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()
                                    is not None
                                ):
                                    if (
                                        taxiing_time_while_aircraft_moving
                                        <= self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()
                                    ):
                                        number_of_engines = float(
                                            min(
                                                self.getTaxiEngineCount(),
                                                self.getAircraft().getEngineCount(),
                                            )
                                        )
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                                        if (
                                            include_start_emissions
                                            and not started_engine_set
                                        ):
                                            number_of_engines_to_start = (
                                                number_of_engines
                                            )
                                            em_ += (
                                                start_emissions
                                                * number_of_engines_to_start
                                            )
                                            started_engine_set = True

                                    if index_segment_ == 0:
                                        if include_start_emissions:
                                            number_of_engines_to_start = self.getAircraft().getEngineCount() - float(
                                                min(
                                                    self.getTaxiEngineCount(),
                                                    self.getAircraft().getEngineCount(),
                                                )
                                            )
                                            em_ += (
                                                start_emissions
                                                * number_of_engines_to_start
                                            )

                                elif (
                                    not self.getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff()
                                    is None
                                ):
                                    if abs(
                                        taxiing_time_while_aircraft_moving
                                        + self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()
                                    ) >= abs(
                                        self.getRunwayTime() - self.getBlockTime()
                                    ):

                                        number_of_engines = float(
                                            min(
                                                self.getTaxiEngineCount(),
                                                self.getAircraft().getEngineCount(),
                                            )
                                        )
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                                        if (
                                            include_start_emissions
                                            and not started_engine_set
                                        ):
                                            number_of_engines_to_start = (
                                                number_of_engines
                                            )
                                            em_ += (
                                                start_emissions
                                                * number_of_engines_to_start
                                            )
                                            started_engine_set = True

                                    if index_segment_ == 0:
                                        if include_start_emissions:
                                            number_of_engines_to_start = self.getAircraft().getEngineCount() - float(
                                                min(
                                                    self.getTaxiEngineCount(),
                                                    self.getAircraft().getEngineCount(),
                                                )
                                            )
                                            em_ += (
                                                start_emissions
                                                * number_of_engines_to_start
                                            )

                                elif (
                                    self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()
                                    is None
                                    and self.getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff()
                                    is None
                                ):
                                    if include_start_emissions and index_segment_ == 0:
                                        number_of_engines_to_start = (
                                            self.getAircraft().getEngineCount()
                                        )
                                        # logger.debug("Main-engine start of %f engines at first taxiway segment for departures"
                                        #              %(number_of_engines - self.getAircraft().getEngineCount()))
                                        em_ += (
                                            start_emissions * number_of_engines_to_start
                                        )
                            else:
                                logger.info(
                                    "No Taxi Engine Count for %s", self.getName()
                                )

                        # --- ARRIVALS ---
                        elif self.isArrival():
                            if index_segment_ == 0:
                                if (
                                    self.getAircraft().getMTOW() is not None
                                    and self.getAircraft().getMTOW() > 18632
                                ):  # in kg:
                                    em_.add_value(
                                        PollutantType.PM10,
                                        PollutantUnit.GRAM,
                                        self.getAircraft().getMTOW() * 0.000476 - 8.74,
                                    )

                            if self.getTaxiEngineCount() is not None:
                                if (
                                    not self.getSingleEngineTaxiingMainEngineOffAfterRunwayExit()
                                    is None
                                ):
                                    if (
                                        abs(taxiing_time_while_aircraft_moving)
                                        >= self.getSingleEngineTaxiingMainEngineOffAfterRunwayExit()
                                    ):
                                        number_of_engines = float(
                                            min(
                                                self.getTaxiEngineCount(),
                                                self.getAircraft().getEngineCount(),
                                            )
                                        )
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                        # print(new_taxiway_segment_time,number_of_engines,taxi_fuel_ratio)
                        em_.add(
                            emission_index_,
                            new_taxiway_segment_time
                            * number_of_engines
                            * taxi_fuel_ratio,
                        )

                        # queuing_time = 0.
                        if index_segment_ == len(self.getTaxiRoute().getSegments()) - 1:
                            # Queuing emissions
                            # if queuing_time > 0:
                            # logger.info("Queuing emissions for mov %s (TX_T: %s / Q_T: %s) "%(self.getName(),
                            #                                             init_taxiing_time_from_segments, queuing_time))
                            em_.add(emission_index_, queuing_time * number_of_engines)

                            # add emissions due to stop & go's
                            if (
                                self.getNumberOfStops() is not None
                                or self.getNumberOfStops() == 0.0
                            ):
                                average_duration_of_stop_and_gos_in_s = 9.0
                                em_.add(
                                    emission_index_,
                                    average_duration_of_stop_and_gos_in_s
                                    * self.getNumberOfStops(),
                                )

                        emissions.append(
                            {
                                "emissions": em_,
                                "distance_time": new_taxiway_segment_time
                                + queuing_time,
                                "distance_space": taxiway_segment_.getLength(),
                            }
                        )

            elif self.getAircraft().getGroup() == "HELICOPTER":
                # print("TX emissions for HELI %s"%self.getAircraft().getName())
                TX_segs = self.getTaxiRoute().getSegments()
                # Helicopter taxiing emissions will be added to the first segment of the taxiway
                taxiway_segment_1 = TX_segs[0] if len(TX_segs) > 0 else None
                if total_taxiing_time > 0 and taxiway_segment_1 is not None:
                    em_ = Emission(defaultValues=defaultEmissions)
                    # check number of engines if 2 get GI2 as well
                    number_of_engines = self.getAircraft().getEngineCount()
                    if number_of_engines > 1:
                        ei1 = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode("GI1")
                        )
                        tx_time_1 = (
                            ei1.getObject("time_min") * 60.0
                            if ei1.hasKey("time_min")
                            else 0.0
                        )
                        em_.add(ei1, max(total_taxiing_time, tx_time_1))

                        ei2 = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode("GI2")
                        )
                        tx_time_2 = (
                            ei2.getObject("time_min") * 60.0
                            if ei2.hasKey("time_min")
                            else 0.0
                        )
                        em_.add(
                            ei2,
                            max(total_taxiing_time * tx_time_2 / tx_time_1, tx_time_2),
                        )
                        em_.add(ei2, total_taxiing_time)

                    else:
                        emission_index_ = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode("GI1")
                        )
                        em_.add(emission_index_, total_taxiing_time)
                    em_.setGeometryText(taxiway_segment_1.getGeometryText())
                    emissions.append(
                        {
                            "emissions": em_,
                            "distance_time": total_taxiing_time,
                            "distance_space": 0.0,
                        }
                    )

        else:
            # ToDo: Add zero emissions ?
            logger.error(
                "Did not find a taxi route for movement '%s'. Cannot calculate taxiing emissions.",
                self.getName(),
            )
            # emissions.append({"emissions": Emission(defaultValues=defaultEmissions), "distance_time": 0.0, "distance_space": 0.0})

        return emissions

    def calculateFlightEmissions(self, atRunway=True, method=None, mode="", limit=None):
        if limit is None:
            limit = {}
        if method is None:
            method = {"name": "bymode", "config": {}}
        emissions = []
        distance_time_all_segments_in_mode = 0.0
        distance_space_all_segments_in_mode = 0.0
        traj = self.getTrajectoryAtRunway() if atRunway else self.getTrajectory()

        if traj is None:
            return emissions

        if self.getAircraft().getGroup() != "HELICOPTER":
            # get all individual segments (pairs  of points) for the particular
            # mode
            for startPoint_, endPoint_ in traj.getPointPairs(mode):
                emissions_dict_ = self.calculateEmissionsPerSegment(
                    startPoint_,
                    endPoint_,
                    atRunway=atRunway,
                    method=method,
                    limit=limit,
                )
                distance_time_all_segments_in_mode += emissions_dict_["distance_time"]
                distance_space_all_segments_in_mode += emissions_dict_["distance_space"]
                emissions.append(emissions_dict_)
        else:
            # Based on FOCA Guidance on the Determination of Helicopter Emissions and the FOCA Engine Emissions Databank
            heli_emissions = Emission(defaultValues=defaultEmissions)
            emission_index_ = self.getAircraftEngine().getEmissionIndex()

            number_of_engines = (
                self.getAircraft().getEngineCount()
                if (
                    self.getAircraft() is not None
                    and self.getAircraft().getEngineCount() is not None
                )
                else 1
            )

            # get all individual segments (pairs  of points) for the geometry
            emissions_geo = []
            for startPoint_, endPoint_ in traj.getPointPairs(mode):
                emissions_geo.append(
                    loads(
                        spatial.getLineGeometryText(
                            startPoint_.getGeometryText(), endPoint_.getGeometryText()
                        )
                    )
                )
            entire_heli_geometry = MultiLineString(emissions_geo)
            heli_emissions.setGeometryText(entire_heli_geometry)
            space_in_segment_ = entire_heli_geometry.length

            # the emissions are calculated for the whole trajectory not for each segment
            ei_ = (
                emission_index_.getEmissionIndexByMode("TO")
                if self.isDeparture()
                else emission_index_.getEmissionIndexByMode("AP")
            )
            time_in_segment_ = (
                ei_.getObject("time_min") * 60.0 if ei_.hasKey("time_min") else 0.0
            )

            heli_emissions.add(ei_, time_in_segment_ * number_of_engines)
            emissions_dict_ = {
                "emissions": heli_emissions,
                "distance_time": float(time_in_segment_),
                "distance_space": float(space_in_segment_),
            }
            emissions.append(emissions_dict_)

        return emissions

    def calculateEmissionsPerSegment(
        self, startPoint_, endPoint_, atRunway=True, method=None, limit=None
    ):
        if limit is None:
            limit = {}
        if method is None:
            method = {"name": "", "config": {}}
        emissions = Emission(defaultValues=defaultEmissions)
        EPSG_id_source = 3857
        EPSG_id_target = 4326

        # ToDo : Permanent definition
        try:
            T = method["config"]["ambient_conditions"].getTemperature()
            # Celsius temperature: T − 273.15
            speed_of_sound = float(331.3 + 0.606 * (T - 273.15))  # in m/s
            mach_value = {
                "mach_number": (startPoint_.getTrueAirspeed() / speed_of_sound)
                * ((288.15 / float(T)) ** (1.0 / 2))
            }
        except Exception:
            mach_value = {"mach_number": 0.0}
        method["config"].update(mach_value)

        time_in_segment_ = 0.0
        space_in_segment_ = 0.0

        # Apply limits
        if "max_height" in limit:
            unit_in_feet = False

            if "height_unit_in_feet" in limit and limit["height_unit_in_feet"]:
                unit_in_feet = limit["height_unit_in_feet"]  # True

            # TODO OPENGIS.ch: if the height of the emission is above the "sacred number" of 914.14 meters, we ignore all the following emissions,
            # as assumed they are getting higher and higher than this point
            if (
                startPoint_.getZ(unit_in_feet) >= limit["max_height"]
                and endPoint_.getZ(unit_in_feet) >= limit["max_height"]
            ):
                # ignore point
                emissions.setGeometryText(None)
                return {
                    "emissions": emissions,
                    "distance_time": float(time_in_segment_),
                    "distance_space": float(space_in_segment_),
                }

            elif (
                startPoint_.getZ(unit_in_feet) > limit["max_height"]
                and endPoint_.getZ(unit_in_feet) < limit["max_height"]
            ):
                # make a copy of the point and modify height
                startPoint_ = AircraftTrajectoryPoint(startPoint_)
                startPoint_.setZ(limit["max_height"], unit_in_feet)

            elif (
                startPoint_.getZ(unit_in_feet) < limit["max_height"]
                and endPoint_.getZ(unit_in_feet) > limit["max_height"]
            ):
                # make a copy of the point and modify height
                endPoint_ = AircraftTrajectoryPoint(endPoint_)
                endPoint_.setZ(limit["max_height"], unit_in_feet)

        emissions.setGeometryText(
            spatial.getLineGeometryText(
                startPoint_.getGeometryText(), endPoint_.getGeometryText()
            )
        )

        startPoint_copy, endPoint_copy = copy.deepcopy(startPoint_), copy.deepcopy(
            endPoint_
        )
        # Smooth & Shift Approach
        sas = (
            method["config"]["apply_smooth_and_shift"]
            if "config" in method and "apply_smooth_and_shift" in method["config"]
            else "none"
        )

        if sas == "default" or sas == "smooth & shift":
            # logger.debug("Calculate RWY emissions with Smooth & Shift Approach: '%s'" % (sas))

            sas_method = "default" if sas == "default" else "sas"
            # try:
            hor_ext = (
                self.getAircraft()
                .getEmissionDynamicsByMode()[startPoint_.getMode()]
                .getEmissionDynamics(sas_method)["horizontal_extension"]
            )
            ver_ext = (
                self.getAircraft()
                .getEmissionDynamicsByMode()[startPoint_.getMode()]
                .getEmissionDynamics(sas_method)["vertical_extension"]
            )
            ver_shift = (
                self.getAircraft()
                .getEmissionDynamicsByMode()[startPoint_.getMode()]
                .getEmissionDynamics(sas_method)["vertical_shift"]
            )
            hor_shift = (
                self.getAircraft()
                .getEmissionDynamicsByMode()[startPoint_.getMode()]
                .getEmissionDynamics("default")["horizontal_shift"]
            )

            # x1_, y1_, z1_ = (
            #     self.getTrajectory()
            #     .getPoints()[startPoint_.getIdentifier() - 1]
            #     .getX(),
            #     self.getTrajectory()
            #     .getPoints()[startPoint_.getIdentifier() - 1]
            #     .getY(),
            #     self.getTrajectory()
            #     .getPoints()[startPoint_.getIdentifier() - 1]
            #     .getZ(),
            # )
            z1_ = (
                self.getTrajectory()
                .getPoints()[startPoint_.getIdentifier() - 1]
                .getZ(),
            )

            # x2_, y2_, z2_ = (
            #     self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getX(),
            #     self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getY(),
            #     self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getZ(),
            # )
            z2_ = (
                self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getX(),
                self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getY(),
                self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getZ(),
            )

            x_shift = self.getTrajectory().get_sas_point(
                abs(ver_shift), self.isDeparture()
            )

            emissions.setVerticalExtent(
                {"z_min": startPoint_.getZ(), "z_max": ver_ext + startPoint_.getZ()}
            )

            if startPoint_.getMode() == "AP":
                # until here apply ver_shift
                if abs(z1_) - abs(ver_shift) > abs(ver_shift) and abs(z2_) - abs(
                    ver_shift
                ) > abs(ver_shift):
                    # Update Z values
                    startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setZ(
                        max(endPoint_.getZ() + ver_shift, abs(ver_shift))
                    )
                    endPoint_copy.updateGeometryText()

                # break in two segments now
                elif abs(z1_) - abs(ver_shift) > abs(ver_shift) and abs(z2_) - abs(
                    ver_shift
                ) <= abs(ver_shift):

                    (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(
                            startPoint_.getGeometryText(), endPoint_.getGeometryText()
                        ),
                        EPSG_id_source,
                        EPSG_id_target,
                    )

                    start_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0]
                    end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                    inverse_distance_segment = spatial.getInverseDistance(
                        start_point[0], start_point[1], end_point[0], end_point[1]
                    )

                    start_point_azimuth = inverse_distance_segment["azi1"]
                    target_point_distance = abs(
                        abs(
                            self.getTrajectory()
                            .getPoints()[startPoint_.getIdentifier() - 1]
                            .getX()
                        )
                        - abs(x_shift)
                    )
                    target_projected = spatial.getDistance(
                        start_point[0],
                        start_point[1],
                        start_point_azimuth,
                        target_point_distance,
                    )
                    target_projected_wkt = spatial.getPointGeometryText(
                        target_projected["lat2"], target_projected["lon2"], 0.0, swap
                    )
                    (target_projected_wkt, swap_) = spatial.reproject_geometry(
                        target_projected_wkt, EPSG_id_target, EPSG_id_source
                    )

                    self.getTrajectory().setTouchdownPoint(
                        spatial.CreateGeometryFromWkt(target_projected_wkt)
                    )

                    # geometry_text_list = []
                    startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                    endPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                    endPoint_copy.setZ(0)
                    endPoint_copy.updateGeometryText()

                else:
                    (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(
                            startPoint_.getGeometryText(),
                            self.getTrajectory().getTouchdownPoint(),
                        ),
                        EPSG_id_source,
                        EPSG_id_target,
                    )
                    start_point, end_point = (
                        spatial.getAllPoints(segment_geometry_wkt, swap)[0],
                        spatial.getAllPoints(segment_geometry_wkt, swap)[-1],
                    )
                    dist_startPoint_sasPoint = spatial.getInverseDistance(
                        start_point[0], start_point[1], end_point[0], end_point[1]
                    )["s12"]

                    (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(
                            self.getTrajectory().getTouchdownPoint(),
                            endPoint_.getGeometryText(),
                        ),
                        EPSG_id_source,
                        EPSG_id_target,
                    )
                    start_point, end_point = (
                        spatial.getAllPoints(segment_geometry_wkt, swap)[0],
                        spatial.getAllPoints(segment_geometry_wkt, swap)[-1],
                    )
                    dist_sasPoint_endPoint = spatial.getInverseDistance(
                        start_point[0], start_point[1], end_point[0], end_point[1]
                    )["s12"]

                    if dist_startPoint_sasPoint > dist_sasPoint_endPoint:
                        startPoint_copy.setX(
                            spatial.getAllPoints(
                                self.getTrajectory().getTouchdownPoint()
                            )[0][0]
                        )
                        startPoint_copy.setY(
                            spatial.getAllPoints(
                                self.getTrajectory().getTouchdownPoint()
                            )[0][1]
                        )
                    startPoint_copy.setZ(0)
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setZ(0)
                    endPoint_copy.updateGeometryText()

            elif startPoint_.getMode() == "TO" or startPoint_.getMode() == "CL":
                if z2_ > 0:
                    hor_ext = (
                        self.getAircraft()
                        .getEmissionDynamicsByMode()["CL"]
                        .getEmissionDynamics(sas_method)["horizontal_extension"]
                    )
                    ver_ext = (
                        self.getAircraft()
                        .getEmissionDynamicsByMode()["CL"]
                        .getEmissionDynamics(sas_method)["vertical_extension"]
                    )
                    ver_shift = (
                        self.getAircraft()
                        .getEmissionDynamicsByMode()["CL"]
                        .getEmissionDynamics(sas_method)["vertical_shift"]
                    )
                    hor_shift = (
                        self.getAircraft()
                        .getEmissionDynamicsByMode()["CL"]
                        .getEmissionDynamics("default")["horizontal_shift"]
                    )

                (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                    spatial.getLineGeometryText(
                        startPoint_.getGeometryText(), endPoint_.getGeometryText()
                    ),
                    EPSG_id_source,
                    EPSG_id_target,
                )

                start_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0]
                end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                inverse_distance_segment = spatial.getInverseDistance(
                    start_point[0], start_point[1], end_point[0], end_point[1]
                )
                start_point_azimuth, end_point_azimuth = (
                    inverse_distance_segment["azi1"],
                    inverse_distance_segment["azi2"],
                )

                target_projected = spatial.getDistance(
                    start_point[0], start_point[1], start_point_azimuth, -hor_shift
                )
                target_projected_wkt = spatial.getPointGeometryText(
                    target_projected["lat2"], target_projected["lon2"], 0.0, swap
                )
                (target_projected_wkt, swap_) = spatial.reproject_geometry(
                    target_projected_wkt, EPSG_id_target, EPSG_id_source
                )
                startPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                startPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                startPoint_copy.updateGeometryText()

                target_projected = spatial.getDistance(
                    end_point[0], end_point[1], end_point_azimuth, -hor_shift
                )
                target_projected_wkt = spatial.getPointGeometryText(
                    target_projected["lat2"], target_projected["lon2"], 0.0, swap
                )
                (target_projected_wkt, swap_) = spatial.reproject_geometry(
                    target_projected_wkt, EPSG_id_target, EPSG_id_source
                )
                endPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                endPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                endPoint_copy.setZ(max(0, endPoint_.getZ() + ver_shift))
                endPoint_copy.updateGeometryText()

                emissions.setVerticalExtent(
                    {
                        "z_min": startPoint_copy.getZ(),
                        "z_max": ver_ext + startPoint_copy.getZ(),
                    }
                )

            multipolygon = spatial.ogr.Geometry(spatial.ogr.wkbMultiPolygon)
            all_points = spatial.getAllPoints(
                spatial.getLineGeometryText(
                    startPoint_copy.getGeometryText(), endPoint_copy.getGeometryText()
                )
            )
            for p_, point_ in enumerate(all_points):
                # point_ example (802522.928722, 5412293.034699, 0.0)
                if p_ + 1 == len(all_points):
                    break
                geometry_wkt_i = "LINESTRING Z(%s %s %s, %s %s %s)" % (
                    all_points[p_][0],
                    all_points[p_][1],
                    all_points[p_][2],
                    all_points[p_ + 1][0],
                    all_points[p_ + 1][1],
                    all_points[p_ + 1][2],
                )
                leftline, rightline = self.CalculateParallels(
                    geometry_wkt_i, hor_ext, 0, 0, 3857, 4326
                )  # in lon / lat !
                poly_geo = spatial.getRectangleXYZFromBoundingBox(
                    leftline, rightline, 3857, 4326
                )
                multipolygon.AddGeometry(poly_geo)
                emissions.setGeometryText(multipolygon.ExportToWkt())

        else:
            # logger.debug("Calculate RWY emissions WITHOUT Smooth & Shift Approach.")
            emissions.setVerticalExtent({"z_min": 0, "z_max": 0})
            emissions.setGeometryText(
                spatial.getLineGeometryText(
                    startPoint_.getGeometryText(), endPoint_.getGeometryText()
                )
            )

        # emissions calculation
        traj = self.getTrajectory() if not atRunway else self.getTrajectoryAtRunway()
        if traj is not None:
            # time spent in segment
            time_in_segment_ = traj.calculateDistanceBetweenPoints(
                startPoint_, endPoint_, "time"
            )
            # distance in segment
            space_in_segment_ = traj.calculateDistanceBetweenPoints(
                startPoint_, endPoint_, "space"
            )

            emission_index_ = None
            if method["name"] == "bymode":
                emission_index_ = (
                    self.getAircraftEngine()
                    .getEmissionIndex()
                    .getEmissionIndexByMode(startPoint_.getMode())
                )

                copy_emission_index_ = copy.deepcopy(emission_index_)
                if method["config"]["apply_nox_corrections"]:
                    logger.info("Applying NOx Correction for Ambient Conditions")
                    corr_nox_ei = nox_correction_for_ambient_conditions(
                        emission_index_.get_value(PollutantType.NOx, "g_kg"),
                        method["config"]["airport_altitude"],
                        self.getTakeoffWeightRatio(),
                        ac=method["config"]["ambient_conditions"],
                    )
                    copy_emission_index_.setObject("nox_g_kg", corr_nox_ei)

            else:
                # get emission indices based on the engine-thrust setting of the particular segment
                emission_index_ = (
                    self.getAircraftEngine()
                    .getEmissionIndex()
                    .getEmissionIndexByPowerSetting(
                        startPoint_.getEngineThrust(), method=method
                    )
                )

                # ToDo: Permanent fix for PM10
                if method["name"] == "BFFM2":
                    if emission_index_ is None:
                        # logger.error("Error: Cannot calculate EI w. BFFM2. The 'by mode' method will be used for source: '%s'" %(self.getName()))
                        copy_emission_index_ = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode(startPoint_.getMode())
                        )
                    else:
                        copy_emission_index_ = copy.deepcopy(emission_index_)

                        pm10_g_kg = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode(startPoint_.getMode())
                            .get_value(PollutantType.PM10, "g_kg")
                        )
                        try:
                            copy_emission_index_.setObject("pm10_g_kg", pm10_g_kg[0])
                        except Exception:
                            logger.error(
                                "Couldn't add emission index for PM10 (%s)"
                                % self.getName()
                            )

                        sox_g_kg = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode(startPoint_.getMode())
                            .get_value(PollutantType.SOx, "g_kg")
                        )
                        try:
                            copy_emission_index_.setObject("sox_g_kg", sox_g_kg[0])
                        except Exception:
                            logger.error(
                                "Couldn't add emission index for SOx (%s)"
                                % self.getName()
                            )

                    if method["config"]["apply_nox_corrections"]:
                        logger.info(
                            "Applying NOx Correction for Ambient Conditions. NOx EI will be calculated using 'By mode' method."
                        )
                        nox_g_kg = (
                            self.getAircraftEngine()
                            .getEmissionIndex()
                            .getEmissionIndexByMode(startPoint_.getMode())
                            .get_value(PollutantType.NOx, "g_kg")
                        )
                        corr_nox_ei = nox_correction_for_ambient_conditions(
                            nox_g_kg,
                            method["config"]["airport_altitude"],
                            self.getTakeoffWeightRatio(),
                            ac=method["config"]["ambient_conditions"],
                        )
                        copy_emission_index_.setObject("nox_g_kg", corr_nox_ei)

            if copy_emission_index_ is None:
                logger.error(
                    "Did not find emission index for aircraft with type '%s'."
                    % (self.getAircraft())
                )

            # Calculate the effective time (s)
            effective_time_s = (
                float(time_in_segment_) * self.getAircraft().getEngineCount()
            )

            emissions.add(copy_emission_index_, effective_time_s)

        return {
            "emissions": emissions,
            "distance_time": float(time_in_segment_),
            "distance_space": float(space_in_segment_),
        }

    def calculateEmissions(self, atRunway=True, method=None, mode="", limit=None):
        # emissions_list = mov.calculateEmissions(method=method, limit=limit)
        # emissions = sum(em_["emissions"] for em_ in emissions_list)
        if limit is None:
            limit = {}
        if method is None:
            method = {"name": "bymode", "config": {}}
        emissions: list[EmissionsDict] = []

        # add emissions on flight trajectory (incl. runway)
        emissions.extend(self.calculateFlightEmissions(atRunway, method, mode, limit))

        # add emissions at gate (gpu, gse etc.)
        emissions.extend(
            self.calculateGateEmissions(sas=method["config"]["apply_smooth_and_shift"])
        )

        # add taxiing emissions
        emissions.extend(
            self.calculateTaxiingEmissions(
                sas=method["config"]["apply_smooth_and_shift"]
            )
        )

        # print("calculateEmissions: About to do some plots ")
        # fig, ax = plt.subplots()
        # for em_ in emissions:
        #     geom = em_['emissions'].getGeometry()
        #     ax.set_title("%s (calculateEmissions)" % self.getName())
        #     gpd.GeoSeries(geom).plot(ax=ax, color='r', alpha=0.25)
        #     plt.savefig("./%s_v3.png" % (self.getName().translate({ord(" "): "_", ord(":"): "_", ord("-"): "_"})), dpi=300,
        #                 bbox_inches="tight")

        return emissions

    def getAircraftGroupMatch(self, source_type):
        ac_group = None
        if ac_group in self.getGate().getEmissionProfileGroups():
            ac_group = self.getAircraft().getGroup()
        else:
            matched = difflib.get_close_matches(
                self.getAircraft().getGroup(),
                self.getGate().getEmissionProfileGroups(source_type=source_type),
            )
            if matched:
                ac_group = matched[0]
                if not ac_group.lower() == self.getAircraft().getGroup().lower():
                    logger.warning(
                        "Did not find a gate emission profile for source type '%s' and aircraft group '%s', "
                        "but matched to '%s'. Probably update the table 'default_gate_profiles'."
                        % (source_type, ac_group, self.getAircraft().getGroup())
                    )
        # if ac_group is None:
        #     logger.error("Unknown aircraft group identifier for source type '%s'. Aircraft is '%s'. Update default association in default_aircraft." % (source_type, self.getAircraft().getName()))

        return ac_group

    def getGateOccupancy(self, ac_group, source_type):
        occupancy_in_min = 0.0
        profile_ = self.getGate().getEmissionProfile(
            ac_group, self._departure_arrival, source_type
        )
        if profile_ is not None:
            occupancy_in_min = profile_.getOccupancy()
        # ToDo: Default time in no information ?
        # if not profile_ is None:
        #     if self.isDeparture():
        #         #40% of the emission index corresponds to departures
        #         if not profile_ is None:
        #             # occupancy_in_min  = profile_.getDepartureOccupancy() * 0.4
        #             occupancy_in_min  = profile_.getOccupancy() * 0.4
        #     else:
        #         #60% of the emission index corresponds to arrivals
        #         if not profile_ is None:
        #             # occupancy_in_min  = profile_.getArrivalOccupancy() * 0.6
        #             occupancy_in_min  = profile_.getOccupancy() * 0.6
        return occupancy_in_min

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
        self.setTrajectoryAtRunway(
            self.calculateTrajectoryAtRunway(offset_by_touchdown=True)
        )

    def setTrajectoryAtRunway(self, var):
        self._trajectory_at_runway = var
        self._trajectory_at_runway.setIsCartesian(False)

    def calculateTrajectoryAtRunway(self, offset_by_touchdown=True):
        trajectory = None
        if self.getTrajectory() is None:
            logger.error(
                "Could not find trajectory for movement at runway "
                f"time '{self.getRunwayTime(as_str=True)}'."
            )
            return trajectory
        elif self.getRunway() is None:
            logger.error(
                "Could not find runway for movement at runway time "
                f"'{self.getRunwayTime(as_str=True)}'."
            )
            return trajectory
        elif not (self.getRunwayDirection() in self.getRunway().getDirections()):
            logger.error(
                f"Could not find runway direction "
                f"'{self.getRunwayDirection()}' (movement runway "
                f"time='{self.getRunwayTime(as_str=True)}'."
            )
            return trajectory

        # Shift coordinates by touchdown offset (only for arrivals)
        if offset_by_touchdown:
            offset_by_touchdown = self.isArrival()

        # Set the EPSG identifiers for the source and target projection
        epsg_id_source = 3857
        epsg_id_target = 4326
        tr = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem(epsg_id_source),
            QgsCoordinateReferenceSystem(epsg_id_target),
            QgsProject.instance(),
        )
        # Create a measure object
        source_crs = QgsCoordinateReferenceSystem(epsg_id_source)
        d = QgsDistanceArea()
        d.setSourceCrs(source_crs, QgsProject.instance().transformContext())
        d.setEllipsoid(source_crs.ellipsoidAcronym())

        runway_geom = QgsGeometry.fromWkt(self.getRunway().getGeometryText())
        runway_points = runway_geom.get().points()

        if len(runway_points) < 2:
            logger.error("Did not find enough points for geometry '%s'", runway_geom)
            return trajectory

        runway_start_point = QgsPointXY(runway_points[0])
        runway_end_point = QgsPointXY(runway_points[-1])
        runway_directions = self.getRunway().getDirections()

        if self.getRunwayDirection() == runway_directions[1]:
            runway_backup_point = runway_start_point
            runway_azimuth_deg = (
                math.degrees(d.bearing(runway_start_point, runway_end_point)) + 360
            ) % 360
        elif self.getRunwayDirection() == runway_directions[0]:
            runway_backup_point = runway_end_point
            runway_azimuth_deg = (
                math.degrees(d.bearing(runway_end_point, runway_start_point)) + 360
            ) % 360
        else:
            raise Exception(
                f"Runway direction {self.getRunwayDirection()} was not found in {runway_directions}!"
            )

        taxi_geom = QgsGeometry.fromWkt(
            self.getTaxiRoute().getSegmentsAsLineString().wkt
        )
        # NOTE QGIS 3.34.2 is returning and empty geometry and newer QGIS is returning a null geometry
        runway_intersection_projected = runway_geom.buffer(1, 10).intersection(
            taxi_geom
        )

        if (
            runway_intersection_projected.isNull()
            or runway_intersection_projected.isEmpty()
        ):
            # TODO OPENGIS.ch: in addition to just logging here,
            # make sure the taxiway and the runway are intersecting, otherwise you cannot save the Movement
            logger.error(
                'No intersection point between runway "%s" and taxi route "%s"',
                self.getRunwayDirection(),
                self.getTaxiRoute().getName(),
            )
            runway_intersection_geographic = tr.transform(runway_backup_point)
        else:
            runway_intersection_geographic = tr.transform(
                runway_intersection_projected.centroid().asPoint()
            )

        if not self.has_track():
            trajectory = AircraftTrajectory(
                self.getTrajectory(),
                skipPointInitialization=True,
            )
            trajectory.setIsCartesian(False)

            for point in self.getTrajectory().getPoints():
                # the target point is with cartesian coordinates, therefore we can calculate the distance with Pythagorian theorem
                distance = math.sqrt(point.getX() ** 2 + point.getY() ** 2)

                # get target point (calculation in 4326 projection)
                target_point_geographic = d.computeSpheroidProject(
                    runway_intersection_geographic,
                    distance,
                    math.radians(runway_azimuth_deg),
                )
                target_point_geographic = d.computeSpheroidProject(
                    runway_intersection_geographic,
                    distance,
                    math.radians(runway_azimuth_deg),
                )
                target_point_projected = tr.transform(
                    target_point_geographic,
                    QgsCoordinateTransform.ReverseTransform,
                )

                trajectory_point = AircraftTrajectoryPoint(point)
                # Update x and y coordinates (z coordinate is not updated by distance calculation)
                trajectory_point.setCoordinates(
                    target_point_projected.x(),
                    target_point_projected.y(),
                    point.getZ(),
                )
                trajectory.addPoint(trajectory_point)
        else:
            # process track

            # build distance to point array from aircraft profile
            profile_points = self.getTrajectory().getPoints()
            profile_distances = []
            previous_point = (0.0, 0.0, 0.0)
            cumulative_distance = 0.0
            for point in profile_points:
                point = point.getCoordinates()
                distance = spatial.getDistanceBetweenPoints(
                    point[0],
                    point[1],
                    point[2],
                    previous_point[0],
                    previous_point[1],
                    previous_point[2],
                )
                cumulative_distance = cumulative_distance + distance
                profile_distances.append(cumulative_distance)
                previous_point = point

            difference = (
                self.getTrack()
                .getGeometry()
                .difference(self.getRunway().getGeometry().buffer(10))
            )
            track_line = difference
            max_length = 0.0
            # check if the track has been broken into multipe parts, pick the longest one
            if difference.geom_type == "MultiLineString":
                for line in list(difference.geoms):
                    if line.length > max_length:
                        max_length = line.length
                        track_line = line

            track_line_points = list(track_line.coords)
            if self.getTrack().getDepartureArrivalFlag() == "A":
                # reverse arrival track so ordering begins at runway
                track_line_points.reverse()

            (point, point_wkt) = spatial.reproject_Point(
                runway_intersection_geographic.x(),
                runway_intersection_geographic.y(),
                epsg_id_target,
                epsg_id_source,
            )
            track_line_points.insert(0, (point.GetX(), point.GetY(), 0))
            track_line = LineString(track_line_points)

            trajectory = AircraftTrajectory()
            trajectory.setIdentifier(self.getTrajectory().getIdentifier())
            trajectory.setStage(self.getTrajectory().getStage())
            trajectory.setSource(self.getTrajectory().getSource())
            trajectory.setDepartureArrivalFlag(
                self.getTrajectory().getDepartureArrivalFlag()
            )
            trajectory.setWeight(self.getTrajectory().getWeight())

            # match track points to closest point from the profile trajectory
            previous_point = list(track_line.coords)[0]
            cumulative_distance = 0.0
            for point in list(track_line.coords):
                distance = spatial.getDistanceBetweenPoints(
                    point[0],
                    point[1],
                    point[2],
                    previous_point[0],
                    previous_point[1],
                    previous_point[2],
                )
                cumulative_distance = cumulative_distance + distance

                closest_distance = profile_distances[-1]
                closest_idx = len(profile_distances) - 1
                for idx, d in enumerate(profile_distances):
                    if abs(distance - d) < closest_distance:
                        closest_distance = abs(distance - d)
                        closest_idx = idx

                trajectory_point = AircraftTrajectoryPoint(profile_points[closest_idx])
                trajectory_point.setCoordinates(point[0], point[1], point[2])
                trajectory_point.updateGeometryText()
                trajectory.addPoint(trajectory_point)
            trajectory.updateGeometryText()

        return trajectory

    def has_track(self) -> bool:
        if self.getTrack() is None:
            return None

        if self.getTaxiRoute().getRunway() != self.getTrack().getRunway():
            logger.warning(
                "Paired taxi route '%s' and track '%s' do not share the same runway, reverting movement to default airplane profile"
                % (self.getTaxiRoute().getName(), self.getTrack().getName())
            )
            return False

        if self.getDepartureArrivalFlag() != self.getTrack().getDepartureArrivalFlag():
            logger.warning(
                "Track '%s' departure/arrival flag does not match movement, using default airplane profile instead"
                % (self.getTrack().getName())
            )
            return False

        return True

    def getRunway(self):
        return self._runway

    def setRunway(self, var):
        self._runway = var

    def setTrack(self, var):
        self._track = var

    def getTrack(self):
        return self._track

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

    def setDomesticFlag(self, val):
        self._domestic = val

    def getDomesticFlag(self):
        return self._domestic

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
        val += "\n\t Domestic Flag: %s" % (str(self.getDomesticFlag()))
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

    def __init__(self, db_path="", db=None, debug=False):
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

        # instantiate all movement objects
        self.initMovements(debug)

    def getMovementDatabase(self):
        return self._movement_db

    def getRunwayStore(self):
        return RunwayStore(self._db_path)

    def getAircraftStore(self):
        return AircraftStore(self._db_path)

    def getEngineStore(self):
        return EngineStore(self._db_path)

    def getHeliEngineStore(self):
        return HeliEngineStore(self._db_path)

    def getAircraftTrajectoryStore(self):
        return AircraftTrajectoryStore(self._db_path)

    def getGateStore(self):
        return GateStore(self._db_path)

    def getTaxiRouteStore(self):
        return TaxiwayRoutesStore(self._db_path)

    def getTrackStore(self):
        return TrackStore(self._db_path)

    def ProgressBarWidget(self):
        progressbar = QtWidgets.QProgressDialog("Please wait...", "Cancel", 0, 99)
        progressbar.setWindowTitle("Initializing Movements from Database")
        progressbar.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()

        return progressbar

    def initMovements(self, debug=False):  # noqa: C901

        # Start a progressbar, since this might take a while to process
        progressbar = self.ProgressBarWidget()

        # Use stages to update the progress bar
        stage_1 = ProgressBarStage.firstStage(progressbar, 7, maximum=7)

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
        stage_1.nextValue()

        aircraft_store = self.getAircraftStore()
        for acf in mdf["aircraft"].unique():
            store_has_key = aircraft_store.hasKey(acf)
            eq_mdf.loc[mdf.aircraft == acf, "aircraft"] = (
                acf if store_has_key else np.nan
            )
            if not store_has_key:
                logger.error("Aircraft %s wasn't found in the DB" % acf)

        # Check if engines exist in the database
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
                if len(rwy_used) > 0:
                    logger.warning(
                        f"Runway {rwy} was found in the DB multiple " "times."
                    )
                eq_mdf.loc[indices, "runway"] = rwy_used[0]

            else:
                eq_mdf.loc[indices, "runway"] = np.nan
                logger.warning(f"Runway {rwy} wasn't found in the DB")

        # Check if gates exist in the database
        stage_1.nextValue()

        gate_store = self.getGateStore()
        for gte in mdf["gate"].unique():
            store_has_key = gate_store.hasKey(gte)
            eq_mdf.loc[mdf["gate"] == gte, "gate"] = gte if store_has_key else np.nan
            if not store_has_key:
                logger.warning("Gate %s wasn't found in the DB" % gte)

        # Check if taxi routes exist in the database
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
                eq_mdf.loc[indices, "taxi_route"] = np.NaN
                logger.warning(
                    f'Taxiroute "{txr}" was not found in the taxi routes database!'
                )

            # TODO OPENGIS.ch: the alternitive taxi route finder below causes multiple taxi alternative taxi routes to be assigned to a movement
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
            #         eq_mdf.loc[indices, "taxi_route"] = np.NaN

        # Check if track exist in the database
        stage_1.nextValue()

        track_store = self.getTrackStore()
        for trk in mdf["track_id"].unique():
            store_has_key = track_store.hasKey(trk)
            eq_mdf.loc[mdf.track_id == trk, "track_id"] = trk if store_has_key else ""
            if not store_has_key:
                logger.warning("Track %s wasn't found in the DB" % trk)

        # Check if profiles exist in the database
        stage_1.nextValue()

        # Check if there are any profiles unspecified
        profile_isna_any = mdf["profile_id"].isna().any()

        # Get the unique profiles
        profile_unique = mdf["profile_id"].astype(str).unique()

        # Check if the profiles exist in the store
        trajectory_store = self.getAircraftTrajectoryStore()
        profile_haskey_all = np.all(
            list(trajectory_store.hasKey(prf) for prf in profile_unique)
        )

        # Add a default profile
        if profile_isna_any and not profile_haskey_all:
            for ag, airgroup in mdf.groupby(["aircraft", "departure_arrival"]):
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
                        continue
                    eq_mdf.loc[ij_, "profile_id"] = profile_id
                else:
                    logger.debug("AC %s not in AircraftStore", _ac)
                    continue

        # Add nones if it matches the conditions
        for prf in profile_unique:
            indices = mdf[mdf["profile_id"] == prf].index
            if (
                len(indices) != 0
                and prf
                and not pd.isna(prf)
                and trajectory_store.hasKey(prf)
            ):
                eq_mdf.loc[indices, "profile_id"] = prf

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
        stage_2 = stage_1.nextStage(duration=10, maximum=len(eq_mdf.groupby(u_columns)))
        logger.debug(
            f"finished stage 1 "
            f"(n={stage_1._max - stage_1._min}) "
            f"in {stage_1._end_time - stage_1._start_time}"
        )

        for (rwy, rwy_dir, tx_route, prf_id, trk_id), mov_df in eq_mdf.groupby(
            u_columns
        ):
            # Get the indices
            inds = mov_df.index

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
                proxy_mov.updateTrajectoryAtRunway()
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

            stage_2.nextValue()

        # Get the movements to retain
        mdf_retained = eq_mdf[~eq_mdf[df_cols].isna().any(axis=1)]
        logger.info("Number of movements retained: %s" % mdf_retained.shape[0])

        # Start the final stage
        stage_3 = stage_2.finalStage(maximum=mdf.shape[0])
        logger.debug(
            f"finished stage 2 "
            f"(n={stage_2._max - stage_2._min}) "
            f"in {stage_2._end_time - stage_2._start_time}"
        )

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
            stage_3.nextValue()
            if progressbar.wasCanceled():
                logger.warning(
                    "user canceled initMovements, " "so it might be incomplete"
                )
                break

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
                    ("aircraft_registration", "TEXT"),
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
                    ("domestic", "TEXT"),
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
