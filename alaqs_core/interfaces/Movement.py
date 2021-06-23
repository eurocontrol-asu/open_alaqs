import copy
import difflib
import sys
from collections import OrderedDict

import matplotlib
import numpy as np
import pandas as pd
from PyQt5 import QtCore, QtWidgets
from shapely.geometry import MultiLineString
from shapely.wkt import loads

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.Aircraft import AircraftStore
from open_alaqs.alaqs_core.interfaces.AircraftTrajectory import \
    AircraftTrajectoryStore, AircraftTrajectoryPoint, AircraftTrajectory
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.EngineStore import EngineStore, \
    HeliEngineStore
from open_alaqs.alaqs_core.interfaces.Gate import GateStore
from open_alaqs.alaqs_core.interfaces.Runway import RunwayStore
from open_alaqs.alaqs_core.interfaces.SQLSerializable import SQLSerializable
from open_alaqs.alaqs_core.interfaces.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.Store import Store
from open_alaqs.alaqs_core.interfaces.Taxiway import TaxiwayRoutesStore
from open_alaqs.alaqs_core.tools import conversion, spatial
from open_alaqs.alaqs_core.tools.nox_correction_ambient import \
    nox_correction_for_ambient_conditions

sys.path.append("..")

matplotlib.use('Qt5Agg')

logger = get_logger(__name__)

defaultEmissions = {
    "fuel_kg": 0.,
    "co_g": 0.,
    "co2_g": 0.,
    "hc_g": 0.,
    "nox_g": 0.,
    "sox_g": 0.,
    "pm10_g": 0.,
    "p1_g": 0.,
    "p2_g": 0.,
    "pm10_prefoa3_g": 0.,
    "pm10_nonvol_g": 0.,
    "pm10_sul_g": 0.,
    "pm10_organic_g": 0.
}
defaultEI = {
    "fuel_kg_sec": 0.,
    "co_g_kg": 0.,
    "co2_g_kg": 3.16 * 1000.,
    "hc_g_kg": 0.,
    "nox_g_kg": 0.,
    "sox_g_kg": 0.,
    "pm10_g_kg": 0.,
    "p1_g_kg": 0.,
    "p2_g_kg": 0.,
    "smoke_number": 0.,
    "smoke_number_maximum": 0.,
    "fuel_type": "",
    "pm10_prefoa3_g_kg": 0.,
    "pm10_nonvol_g_kg": 0.,
    "pm10_sul_g_kg": 0.,
    "pm10_organic_g_kg": 0.
}


class Movement:
    def __init__(self, val=None):
        if val is None:
            val = {}

        self._time = None
        _col = "runway_time"
        if _col not in val:
            logger.error("'%s' not set, but necessary input" % (_col))
        else:
            self._time = conversion.convertTimeToSeconds(val[_col])
            if self._time is None:
                logger.error("Could not convert '%s', which is of type '%s', to a valid time format." % (str(val[_col]), str(type(val[_col]))))
        self._block_time = None
        _col = "block_time"
        if _col not in val:
            logger.error("'%s' not set, but necessary input" % (_col))
        else:
            self._block_time = conversion.convertTimeToSeconds(val[_col])
            if self._block_time is None:
                logger.error("Could not convert '%s', which is of type '%s', to a valid time format." % (str(val[_col]), str(type(val[_col]))))

        self._engine_name = str(val["engine_name"]) if "engine_name" in val else ""
        self._apu_code = int(val["apu_code"]) if "apu_code" in val and val["apu_code"] else 0
        # self._apu_code = 0 #(stand only), 1 (stand and taxiway) or 2 ()stand, taxiing and take - off / climb - out or approach / landing

        self._domestic = str(val["domestic"]) if "domestic" in val else ""
        self._departure_arrival = str(val["departure_arrival"]) if "departure_arrival" in val else ""
        self._profile_id = str(val["profile_id"]) if "profile_id" in val else ""
        self._track_id = str(val["track_id"]) if "track_id" in val else ""
        self._runway_direction = str(val["runway"]) if "runway" in val else ""

        self._gate_name = str(val["gate"]) if "gate" in val else ""
        self._gate = None
        self._taxi_route = None
        self._taxi_engine_count = int(val["taxi_engine_count"]) if "taxi_engine_count" in val and val["taxi_engine_count"] else 2
        self._tow_ratio = float(val["tow_ratio"]) if "tow_ratio" in val else 1.
        self._taxi_fuel_ratio = float(val["taxi_fuel_ratio"]) if "taxi_fuel_ratio" in val else 1.
        self._engine_thrust_level_taxiing = float(val["engine_thrust_level_taxiing"]) if "engine_thrust_level_taxiing" in val else 0.07

        self._set_time_of_main_engine_start_after_block_off_in_s = conversion.convertToFloat(val["set_time_of_main_engine_start_after_block_off_in_s"]) if "set_time_of_main_engine_start_after_block_off_in_s" in val else None
        self._set_time_of_main_engine_start_before_takeoff_in_s  = conversion.convertToFloat(val["set_time_of_main_engine_start_before_takeoff_in_s"]) if "set_time_of_main_engine_start_before_takeoff_in_s" in val else None
        self._set_time_of_main_engine_off_after_runway_exit_in_s = conversion.convertToFloat(val["set_time_of_main_engine_off_after_runway_exit_in_s"]) if "set_time_of_main_engine_off_after_runway_exit_in_s" in val else None

        if self._set_time_of_main_engine_start_after_block_off_in_s is not None:
            self._set_time_of_main_engine_start_after_block_off_in_s = \
                abs(self._set_time_of_main_engine_start_after_block_off_in_s)

        if self._set_time_of_main_engine_start_before_takeoff_in_s is not None:
            self._set_time_of_main_engine_start_before_takeoff_in_s = \
                abs(self._set_time_of_main_engine_start_before_takeoff_in_s)

        if self._set_time_of_main_engine_off_after_runway_exit_in_s is not None:
            self._set_time_of_main_engine_off_after_runway_exit_in_s = \
                abs(self._set_time_of_main_engine_off_after_runway_exit_in_s)

        self._number_of_stop_and_gos = conversion.convertToFloat(val["number_of_stop_and_gos"]) if "number_of_stop_and_gos" in val else 0.

        self._aircraft = None
        self._aircraftengine = None
        self._runway = None
        self._trajectory_cartesian = None
        self._trajectory_at_runway = None

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
                if ac_type in self.getAircraft().getApuTimes():
                    if gate_type in self.getAircraft().getApuTimes()[ac_type]:
                        apu_time_ = self.getAircraft().getApuTimes()[ac_type][gate_type]["arr_s"] if self.isArrival() else \
                            self.getAircraft().getApuTimes()[ac_type][gate_type]["dep_s"]
        except Exception as exp:
            if seg == 0:
                logger.info("No APU info for %s (AC type: %s, gate type: %s)"%(self.getName(), ac_type, gate_type))
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
        return "%s-%s-%s-%s" % (self.getAircraft().getICAOIdentifier(),self.getDepartureArrivalFlag(),
                                    self.getRunwayTime(as_str=True),self.getBlockTime(as_str=True))

    def getEngineThrustLevelTaxiing(self):
        return self._engine_thrust_level_taxiing
    def setEngineThrustLevelTaxiing(self, var):
        self._engine_thrust_level_taxiing = var

    def calculateGateEmissions(self, sas='none'):
        # logger.debug("Calculate gate emissions for aircraft of type '%s'" % (self.getAircraft().getType()))

        """Calculate gate emissions for a specific source based on the source name and time period. The method for calculating
        emissions from gates requires establishing the sum of three types of emissions:

        1. Emissions from GSE - Data comes from default_gate
        2. Emissions from GPU
        3. Emissions from APU
        4. Emissions from Main Engine Start-up
        """
        emissions = []
        #calculate emissions for ground equipment (i.e. GPU and GSE)
        if not self.getGate() is None and not self.getAircraft().getGroup() == "HELICOPTER":
            # GPU emissions
            gpu_emissions = Emission(defaultValues=defaultEmissions)
            # GPU, lower edge: 0m, upper edge: 5m
            if sas == 'default' or sas == 'smooth & shift':
                gpu_emissions.setVerticalExtent({'z_min': 0, 'z_max': 5})
            # GSE emissions
            gse_emissions = Emission(defaultValues=defaultEmissions)
            # GSE, lower edge: 0m, upper edge: 5m
            if sas == 'default' or sas == 'smooth & shift':
                gse_emissions.setVerticalExtent({'z_min': 0, 'z_max': 5})

            ac_group_GSE = self.getAircraftGroupMatch("gse")#e.g. 'JET SMALL'
            ac_group_GPU = self.getAircraftGroupMatch("gpu")#e.g. 'JET SMALL'

            #if ac_group_GSE is None:
            occupancy_in_min_GSE = self.getGateOccupancy(ac_group_GSE, "gse")
            occupancy_in_min_GPU = self.getGateOccupancy(ac_group_GPU, "gpu")

            gpu_emission_index = self.getGate().getEmissionIndexGPU(ac_group_GPU, self._departure_arrival)
            if not gpu_emission_index is None:
                gpu_emissions.addCO(gpu_emission_index.getCO("kg_hour")[0]*1000.* occupancy_in_min_GPU/60.)
                gpu_emissions.addHC(gpu_emission_index.getHC("kg_hour")[0]*1000.* occupancy_in_min_GPU/60.)
                gpu_emissions.addNOx(gpu_emission_index.getNOx("kg_hour")[0]*1000.* occupancy_in_min_GPU/60.)
                gpu_emissions.addSOx(gpu_emission_index.getSOx("kg_hour")[0]*1000.* occupancy_in_min_GPU/60.)
                gpu_emissions.addPM10(gpu_emission_index.getPM10("kg_hour")[0]*1000.* occupancy_in_min_GPU/60.)
                gpu_emissions.setGeometryText(self.getGate().getGeometryText())
                emissions.append({'distance_space': 0.0, 'distance_time': 0.0, 'emissions': gpu_emissions})
            # else:
            #     logger.warning("No GPU emissions for %s"%self.getName())

            gse_emission_index = self.getGate().getEmissionIndexGSE(ac_group_GSE, self._departure_arrival)
            if not gse_emission_index is None:
                gse_emissions.addCO(gse_emission_index.getCO("kg_hour")[0]*1000. * occupancy_in_min_GSE/60.)
                gse_emissions.addHC(gse_emission_index.getHC("kg_hour")[0]*1000.* occupancy_in_min_GSE/60.)
                gse_emissions.addNOx(gse_emission_index.getNOx("kg_hour")[0]*1000.* occupancy_in_min_GSE/60.)
                gse_emissions.addSOx(gse_emission_index.getSOx("kg_hour")[0]*1000.* occupancy_in_min_GSE/60.)
                gse_emissions.addPM10(gse_emission_index.getPM10("kg_hour")[0]*1000.* occupancy_in_min_GSE/60.)
                gse_emissions.setGeometryText(self.getGate().getGeometryText())
                emissions.append({'distance_space': 0.0, 'distance_time': 0.0, 'emissions': gse_emissions})
            # else:
            #     logger.warning("No GSE emissions for %s"%self.getName())

        else:
            if not self.getAircraft().getGroup() == "HELICOPTER":
                logger.warning("Did not find a gate for movement '%s'" % (self.getName()))
            else:
                logger.warning("Zero GPU/GSE emissions will be added for %s" % (self.getName()))
                if not self.getGate() is None:
                    # GSE emissions
                    gse_emissions = Emission(defaultValues=defaultEmissions)
                    # GSE, lower edge: 0m, upper edge: 5m
                    if sas == 'default' or sas == 'smooth & shift':
                        gse_emissions.setVerticalExtent({'z_min': 0, 'z_max': 5})
                    gse_emissions.setGeometryText(self.getGate().getGeometryText())
                    emissions.append({'distance_space': 0.0, 'distance_time': 0.0, 'emissions': gse_emissions})

        return emissions

    def CalculateParallels(self, geometry_wkt_init, width, height, shift, EPSG_source, EPSG_target):

        (geo_wkt, swap) = spatial.reproject_geometry(geometry_wkt_init, EPSG_source, EPSG_target)

        points = spatial.getAllPoints(geo_wkt, swap)
        lon1, lat1, alt1 = points[0][1], points[0][0], points[0][2]
        lon2, lat2, alt2 = points[1][1], points[1][0], points[1][2]

        inverseDistance_dict = spatial.getInverseDistance(lat1, lon1, lat2, lon2)
        azi1, azi2 = inverseDistance_dict["azi1"], inverseDistance_dict["azi2"]

        # left
        direct_dic1l = spatial.getDistance(lat1, lon1, 90 + azi1, conversion.convertToFloat(width) / 2, epsg_id=EPSG_target)
        direct_dic2l = spatial.getDistance(lat2, lon2, 90 + azi2, conversion.convertToFloat(width) / 2, epsg_id=EPSG_target)

        newline_left = 'LINESTRING Z(%s %s %s, %s %s %s)' % (
        direct_dic1l['lon2'], direct_dic1l['lat2'], alt1 + height, direct_dic2l['lon2'], direct_dic2l['lat2'], alt2 + height)

        # right
        direct_dic1r = spatial.getDistance(lat1, lon1, 270 + azi1, conversion.convertToFloat(width) / 2, epsg_id=EPSG_target)
        direct_dic2r = spatial.getDistance(lat2, lon2, 270 + azi2, conversion.convertToFloat(width) / 2, epsg_id=EPSG_target)

        newline_right = 'LINESTRING Z(%s %s %s, %s %s %s)' % (
        direct_dic1r['lon2'], direct_dic1r['lat2'], alt1 + height, direct_dic2r['lon2'], direct_dic2r['lat2'], alt2 + height)

        return newline_left, newline_right


    def calculateTaxiingEmissions(self, method=None, mode="TX", sas='none'):
        if method is None:
            method = {"name": "bymode", "config": {}}
        try:
            total_taxiing_time = conversion.convertTimeToSeconds(abs(self.getBlockTime() - self.getRunwayTime()))
        except:
            total_taxiing_time = None
        # print("total_taxiing_time %s"%total_taxiing_time)
        emissions = []

        if not self.getTaxiRoute() is None:
            if not self.getAircraft().getGroup() == "HELICOPTER":

                # calculate taxiing_length and taxiing_time_from_segments (initial)
                taxiing_length = 0.0
                init_taxiing_time_from_segments = 0.0
                for index_segment_, taxiway_segment_ in enumerate(self.getTaxiRoute().getSegments()):
                    taxiing_length += taxiway_segment_.getLength()
                    init_taxiing_time_from_segments += taxiway_segment_.getTime()
                    # taxiway_segment_.getLength()/taxiway_segment_.getSpeed() # getLength in m, getSpeed in m/s
                    # taxiway_segment_.setSpeed(10) #setSpeed is in m/s, in Open-ALAQS km/h, default value is 30 km/h or ~8 m/s
                # print("init_taxiing_time_from_segments %s"%init_taxiing_time_from_segments)
                # print("taxiing_length %s"%taxiing_length)

                if total_taxiing_time is None:
                    total_taxiing_time = init_taxiing_time_from_segments
                    # in m/s
                    taxiing_average_speed = \
                        conversion.convertToFloat(taxiing_length)/conversion.convertToFloat(init_taxiing_time_from_segments)
                else:
                    taxiing_average_speed = \
                        conversion.convertToFloat(taxiing_length)/conversion.convertToFloat(total_taxiing_time)
                # print("taxiing_average_speed %s"%taxiing_average_speed)

                # Total taxiing time for calculating taxiing emissions is taken from the Movements Table
                # Queuing emissions are added when taxiing time (traffic log) is greater than user defined taxiroute info (speed, time, etc)
                queuing_time = (total_taxiing_time - init_taxiing_time_from_segments) \
                    if total_taxiing_time > init_taxiing_time_from_segments else 0
                # print("queuing_time %s"%queuing_time)

                emission_index_ = None
                # ToDo: Only bymode method for now ..
                if method["name"]=="bymode":
                    emission_index_ = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(mode)
                else:
                    # get emission indices based on the engine-thrust setting as defined in the movements table
                    emission_index_ = \
                        self.getAircraftEngine().getEmissionIndex().getEmissionIndexByPowerSetting(self.getEngineThrustLevelTaxiing(), method=method)

                if emission_index_ is None:
                    logger.error("Did not find emission index for aircraft with type '%s'." % (self.getAircraft()))
                else:
                    taxiing_time_while_aircraft_moving = 0.

                    # set the geometry as line with linear interpolation between start and endpoint
                    for index_segment_, taxiway_segment_ in enumerate(self.getTaxiRoute().getSegments()):
                        em_ = Emission(defaultValues=defaultEmissions)

                        if sas == 'default' or sas == 'smooth & shift':
                            sas_method = 'default' if sas == 'default' else 'sas'

                            # try:
                            hor_ext = self.getAircraft().getEmissionDynamicsByMode()["TX"].getEmissionDynamics(sas_method)['horizontal_extension']
                            ver_ext = self.getAircraft().getEmissionDynamicsByMode()["TX"].getEmissionDynamics(sas_method)['vertical_extension']
                            ver_shift = self.getAircraft().getEmissionDynamicsByMode()["TX"].getEmissionDynamics(sas_method)['vertical_shift']
                            # print(hor_ext, ver_ext, ver_shift)

                            em_.setVerticalExtent({'z_min': 0.0+ver_shift, 'z_max': ver_ext+ver_shift})

                            # ToDo: add height
                            multipolygon = spatial.ogr.Geometry(spatial.ogr.wkbMultiPolygon)
                            all_points = spatial.getAllPoints(taxiway_segment_.getGeometryText())
                            for p_, point_ in enumerate(all_points):
                                # point_ example (802522.928722, 5412293.034699, 0.0)
                                if p_+1 < len(all_points):
                                    # break
                                    geometry_wkt_i = 'LINESTRING Z(%s %s %s, %s %s %s)' % (
                                        all_points[p_][0], all_points[p_][1], all_points[p_][2], all_points[p_+1][0], all_points[p_+1][1], all_points[p_+1][2]
                                    )
                                    leftline, rightline = self.CalculateParallels(geometry_wkt_i, hor_ext, 0, 0, 3857, 4326) #in lon / lat !
                                    poly_geo = spatial.getRectangleXYZFromBoundingBox(leftline, rightline, 3857, 4326)
                                    multipolygon.AddGeometry(poly_geo)
                                    em_.setGeometryText(multipolygon.ExportToWkt())
                            # except:
                            #     logger.warning("Error while retrieving Smooth & Shift parameters. Switching to normal method.")
                            #     em_.setGeometryText(taxiway_segment_.getGeometryText())

                        else:
                            # logger.info("Calculate taxiing emissions WITHOUT Smooth & Shift Approach.")
                            em_.setGeometryText(taxiway_segment_.getGeometryText())

                        #   add emission factors,
                        #   multiply with occupancy time and number of engines

                        # If time spent in segments < taxiing time in movement table
                        if total_taxiing_time <= init_taxiing_time_from_segments:
                            new_taxiway_segment_time = taxiway_segment_.getLength()/taxiing_average_speed
                        else:
                            new_taxiway_segment_time = taxiway_segment_.getLength()/taxiway_segment_.getSpeed()

                        taxiing_time_while_aircraft_moving += new_taxiway_segment_time

                        number_of_engines = self.getAircraft().getEngineCount()
                        taxi_fuel_ratio = 1.

                        start_emissions = self.getAircraftEngine().getStartEmissions()
                        include_start_emissions = True
                        if start_emissions is None:
                            include_start_emissions = False
                        started_engine_set = False

                        # load APU time and emission factors
                        apu_t, apu_em = self.loadAPUinfo(index_segment_)
                        apu_time = 0
                        if (not apu_t is None) and (apu_t > 0) :
                            # APU emissions will be added to the stand only
                            if self.getAPUCode() == 1 and index_segment_ == 0:
                                apu_time = apu_t
                            # APU emissions will be added to the stand and the taxiroute
                            elif self.getAPUCode() == 2:
                                if apu_t < total_taxiing_time:
                                    # + additional time based on the assumption that the APU is running longer than usual
                                    # first segment taxiing time is included in apu_t (assumption)
                                    apu_time = apu_t if index_segment_ == 0 else new_taxiway_segment_time

                                elif apu_t >= total_taxiing_time:
                                    # first segment gets most of the APU emissions, rest is as per taxiing time
                                    apu_time = (apu_t - total_taxiing_time) + new_taxiway_segment_time \
                                        if index_segment_ == 0 else new_taxiway_segment_time
                            else:
                                apu_time = 0
                                # logger.error("No APU or wrong APU code for mov %s. APU emissions will be set to 0."
                                #              %self.getName())

                            if "fuel_kg_sec" in apu_em:
                                em_.addFuel(apu_em["fuel_kg_sec"] * apu_time)
                            if "co2_g_s"  in apu_em:
                                em_.addCO2(apu_em["co2_g_s"] * apu_time)
                            if "co_g_s"  in apu_em:
                                em_.addCO(apu_em["co_g_s"] * apu_time)
                            if "hc_g_s"  in apu_em:
                                em_.addHC(apu_em["hc_g_s"] * apu_time)
                            if "nox_g_s"  in apu_em:
                                em_.addNOx(apu_em["nox_g_s"] * apu_time)
                            if "sox_g_s"  in apu_em:
                                em_.addSOx(apu_em["sox_g_s"] * apu_time)
                            if "pm10_g_s"  in apu_em:
                                em_.addPM10(apu_em["pm10_g_s"] * apu_time)

                        # else:
                        #     print("No APU or wrong APU code for mov %s (%s, %s)"%(self.getName(),
                        #                                                           self.getAircraft().getGroup(), self.getGate().getType()))

                            # cnt_apu_time += apu_time
                        # CAEPPORT
                        self.setTaxiEngineCount(self.getAircraft().getEngineCount())

                        if self.isDeparture():

                            # Single-Engine Taxiing
                            if not self.getTaxiEngineCount() is None:

                                if not self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff() is None:
                                    if taxiing_time_while_aircraft_moving <= self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff():
                                        number_of_engines = float(min(self.getTaxiEngineCount(), self.getAircraft().getEngineCount()))
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                                        if include_start_emissions and not started_engine_set:
                                            number_of_engines_to_start = number_of_engines
                                            em_ += start_emissions * number_of_engines_to_start
                                            started_engine_set = True

                                    if index_segment_ == 0:
                                        if include_start_emissions:
                                            number_of_engines_to_start = self.getAircraft().getEngineCount() - float(min(self.getTaxiEngineCount(), self.getAircraft().getEngineCount()))
                                            em_ += start_emissions * number_of_engines_to_start

                                elif not self.getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff() is None:
                                    if abs(taxiing_time_while_aircraft_moving + self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff()) \
                                            >= abs(self.getRunwayTime() - self.getBlockTime()):

                                        number_of_engines = float(min(self.getTaxiEngineCount(), self.getAircraft().getEngineCount()))
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                                        if include_start_emissions and not started_engine_set:
                                            number_of_engines_to_start = number_of_engines
                                            em_ += start_emissions * number_of_engines_to_start
                                            started_engine_set = True

                                    if index_segment_ == 0:
                                        if include_start_emissions:
                                            number_of_engines_to_start = self.getAircraft().getEngineCount() - float(min(self.getTaxiEngineCount(), self.getAircraft().getEngineCount()))
                                            em_ += start_emissions * number_of_engines_to_start


                                elif self.getSingleEngineTaxiingTimeOfMainEngineStartAfterBlockOff() is None \
                                        and self.getSingleEngineTaxiingTimeOfMainEngineStartBeforeTakeoff() is None:
                                    if include_start_emissions and index_segment_ == 0:
                                        number_of_engines_to_start = self.getAircraft().getEngineCount()
                                        # logger.debug("Main-engine start of %f engines at first taxiway segment for departures"
                                        #              %(number_of_engines - self.getAircraft().getEngineCount()))
                                        em_ += start_emissions * number_of_engines_to_start
                            else:
                                logger.info("No Taxi Engine Count for %s"%self.getName())

                        # --- ARRIVALS ---
                        elif self.isArrival():
                            if index_segment_ == 0:
                                if not self.getAircraft().getMTOW() is None and self.getAircraft().getMTOW() > 18632 : # in kg:
                                    em_.addPM10(self.getAircraft().getMTOW()*0.000476 - 8.74)

                            if not self.getTaxiEngineCount() is None:
                                if not self.getSingleEngineTaxiingMainEngineOffAfterRunwayExit() is None:
                                    if abs(taxiing_time_while_aircraft_moving) >= self.getSingleEngineTaxiingMainEngineOffAfterRunwayExit():
                                        number_of_engines = float(min(self.getTaxiEngineCount(), self.getAircraft().getEngineCount()))
                                        taxi_fuel_ratio = self.getTaxiFuelRatio()

                        # print(new_taxiway_segment_time,number_of_engines,taxi_fuel_ratio)
                        em_.add(emission_index_, new_taxiway_segment_time*number_of_engines*taxi_fuel_ratio)

                        # queuing_time = 0.
                        if index_segment_ == len(self.getTaxiRoute().getSegments())-1:
                            # Queuing emissions
                            # if queuing_time > 0:
                                # logger.info("Queuing emissions for mov %s (TX_T: %s / Q_T: %s) "%(self.getName(),
                                #                                             init_taxiing_time_from_segments, queuing_time))
                            em_.add(emission_index_, queuing_time * number_of_engines)

                            # add emissions due to stop & go's
                            if not self.getNumberOfStops() is None or self.getNumberOfStops() == 0.:
                                average_duration_of_stop_and_gos_in_s = 9.
                                em_.add(emission_index_, average_duration_of_stop_and_gos_in_s * self.getNumberOfStops())

                        emissions.append({"emissions":em_, "distance_time":new_taxiway_segment_time+queuing_time,
                                          "distance_space": taxiway_segment_.getLength()})

            elif self.getAircraft().getGroup() == "HELICOPTER":
                # print("TX emissions for HELI %s"%self.getAircraft().getName())
                TX_segs = self.getTaxiRoute().getSegments()
                # Helicopter taxiing emissions will be added to the first segment of the taxiway
                taxiway_segment_1 = TX_segs[0] if len(TX_segs)>0 else None
                if total_taxiing_time > 0 and not taxiway_segment_1 is None:
                    em_ = Emission(defaultValues=defaultEmissions)
                    #check number of engines if 2 get GI2 as well
                    number_of_engines = self.getAircraft().getEngineCount()
                    if number_of_engines > 1:
                        ei1 = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode("GI1")
                        tx_time_1 = ei1.getObject('time_min') * 60. if ei1.hasKey('time_min') else 0.
                        em_.add(ei1, max(total_taxiing_time, tx_time_1))

                        ei2 = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode("GI2")
                        tx_time_2 = ei2.getObject('time_min') * 60. if ei2.hasKey('time_min') else 0.
                        em_.add(ei2, max(total_taxiing_time*tx_time_2/tx_time_1, tx_time_2))
                        em_.add(ei2, total_taxiing_time)

                    else:
                        emission_index_ = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode("GI1")
                        em_.add(emission_index_, total_taxiing_time)
                    em_.setGeometryText(taxiway_segment_1.getGeometryText())
                    emissions.append({"emissions": em_, "distance_time": total_taxiing_time, "distance_space": 0.})

        else:
            # ToDo: Add zero emissions ?
            logger.error("Did not find a taxi route for movement '%s'. Cannot calculate taxiing emissions." % (self.getName()))
            # emissions.append({"emissions": Emission(defaultValues=defaultEmissions), "distance_time": 0.0, "distance_space": 0.0})

        return emissions

    def calculateFlightEmissions(self, atRunway = True, method=None, mode="",
                                 limit=None):
        if limit is None:
            limit = {}
        if method is None:
            method = {"name": "bymode", "config": {}}
        emissions = []
        distance_time_all_segments_in_mode = 0.
        distance_space_all_segments_in_mode = 0.
        traj = self.getTrajectory() if not atRunway else self.getTrajectoryAtRunway()

        if not traj is None:
            if not self.getAircraft().getGroup() == "HELICOPTER":
                # get all individual segments (pairs  of points) for the particular mode
                for (startPoint_, endPoint_) in traj.getPointPairs(mode):
                    emissions_dict_ = self.calculateEmissionsPerSegment(startPoint_, endPoint_, atRunway=atRunway,
                                                                        method=method, limit=limit)
                    distance_time_all_segments_in_mode += emissions_dict_["distance_time"]
                    distance_space_all_segments_in_mode += emissions_dict_["distance_space"]
                    emissions.append(emissions_dict_)
            else:
                # Based on FOCA Guidance on the Determination of Helicopter Emissions and the FOCA Engine Emissions Databank
                heli_emissions = Emission(defaultValues=defaultEmissions)
                emission_index_ = self.getAircraftEngine().getEmissionIndex()

                number_of_engines = self.getAircraft().getEngineCount() if \
                        (not self.getAircraft() is None and not self.getAircraft().getEngineCount() is None) else 1

                # get all individual segments (pairs  of points) for the geometry
                emissions_geo = []
                for (startPoint_, endPoint_) in traj.getPointPairs(mode):
                    emissions_geo.append(
                        loads(spatial.getLineGeometryText(startPoint_.getGeometryText(), endPoint_.getGeometryText())))
                entire_heli_geometry = MultiLineString(emissions_geo)
                heli_emissions.setGeometryText(entire_heli_geometry)
                space_in_segment_ = entire_heli_geometry.length

                # the emissions are calculated for the whole trajectory not for each segment
                ei_ = emission_index_.getEmissionIndexByMode("TO") if self.isDeparture() \
                    else emission_index_.getEmissionIndexByMode("AP")
                time_in_segment_ = ei_.getObject('time_min') * 60. if ei_.hasKey('time_min') else 0.

                heli_emissions.add(ei_, time_in_segment_*number_of_engines)
                emissions_dict_ = {"emissions": heli_emissions, "distance_time": float(time_in_segment_),
                                   "distance_space": float(space_in_segment_)}
                emissions.append(emissions_dict_)

        return emissions


    def calculateEmissionsPerSegment(self, startPoint_, endPoint_, atRunway=True,
                                     method=None, limit=None):
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
            speed_of_sound = float(331.3 + 0.606 * (T - 273.15)) # in m/s
            mach_value = {
                "mach_number": (startPoint_.getTrueAirspeed() / speed_of_sound) * ((288.15 / float(T)) ** (1. / 2))}
        except:
            mach_value = {"mach_number": 0.0}
        method["config"].update(mach_value)

        time_in_segment_ = 0.
        space_in_segment_ = 0.

        # Apply limits
        if "max_height" in limit:
            unit_in_feet = False

            if "height_unit_in_feet" in limit and limit["height_unit_in_feet"]:
                unit_in_feet = limit["height_unit_in_feet"]  # True

            if startPoint_.getZ(unit_in_feet) >= limit["max_height"] and endPoint_.getZ(unit_in_feet) >= limit[
                "max_height"]:
                # ignore point
                emissions.setGeometryText(None)
                return {"emissions": emissions, "distance_time": float(time_in_segment_),
                        "distance_space": float(space_in_segment_)}

            elif startPoint_.getZ(unit_in_feet) > limit["max_height"] and endPoint_.getZ(unit_in_feet) < limit[
                "max_height"]:
                # make a copy of the point and modify height
                startPoint_ = AircraftTrajectoryPoint(startPoint_)
                startPoint_.setZ(limit["max_height"], unit_in_feet)

            elif startPoint_.getZ(unit_in_feet) < limit["max_height"] and endPoint_.getZ(unit_in_feet) > limit[
                "max_height"]:
                # make a copy of the point and modify height
                endPoint_ = AircraftTrajectoryPoint(endPoint_)
                endPoint_.setZ(limit["max_height"], unit_in_feet)

        emissions.setGeometryText(
            spatial.getLineGeometryText(startPoint_.getGeometryText(), endPoint_.getGeometryText()))

        startPoint_copy, endPoint_copy = copy.deepcopy(startPoint_), copy.deepcopy(endPoint_)
        # Smooth & Shift Approach
        sas = method["config"]['apply_smooth_and_shift'] if "config" in method and "apply_smooth_and_shift" in method["config"] else "none"

        if sas == 'default' or sas == 'smooth & shift':
            # logger.debug("Calculate RWY emissions with Smooth & Shift Approach: '%s'" % (sas))

            sas_method = 'default' if sas == 'default' else 'sas'
            # try:
            hor_ext = self.getAircraft().getEmissionDynamicsByMode()[startPoint_.getMode()].getEmissionDynamics(sas_method)['horizontal_extension']
            ver_ext = self.getAircraft().getEmissionDynamicsByMode()[startPoint_.getMode()].getEmissionDynamics(sas_method)['vertical_extension']
            ver_shift = self.getAircraft().getEmissionDynamicsByMode()[startPoint_.getMode()].getEmissionDynamics(sas_method)['vertical_shift']
            hor_shift = self.getAircraft().getEmissionDynamicsByMode()[startPoint_.getMode()].getEmissionDynamics("default")['horizontal_shift']

            x1_, y1_, z1_ = self.getTrajectory().getPoints()[startPoint_.getIdentifier() - 1].getX(), \
                            self.getTrajectory().getPoints()[startPoint_.getIdentifier() - 1].getY(), \
                            self.getTrajectory().getPoints()[startPoint_.getIdentifier() - 1].getZ()

            x2_, y2_, z2_ = self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getX(), \
                        self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getY(), \
                        self.getTrajectory().getPoints()[endPoint_.getIdentifier() - 1].getZ()

            x_shift = self.getTrajectory().get_sas_point(abs(ver_shift), self.isDeparture())

            emissions.setVerticalExtent({'z_min': startPoint_.getZ(), 'z_max': ver_ext + startPoint_.getZ()})

            if startPoint_.getMode() == "AP":
                # until here apply ver_shift
                if abs(z1_) - abs(ver_shift) > abs(ver_shift) and abs(z2_) - abs(ver_shift) > abs(ver_shift):
                    # Update Z values
                    startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setZ(max(endPoint_.getZ()+ ver_shift, abs(ver_shift)))
                    endPoint_copy.updateGeometryText()

                # break in two segments now
                elif abs(z1_) - abs(ver_shift) > abs(ver_shift) and abs(z2_) - abs(ver_shift) <= abs(ver_shift):

                    (segment_geometry_wkt, swap) = \
                        spatial.reproject_geometry(spatial.getLineGeometryText(startPoint_.getGeometryText(), endPoint_.getGeometryText()), EPSG_id_source, EPSG_id_target)

                    start_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0]
                    end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                    inverse_distance_segment = spatial.getInverseDistance(start_point[0], start_point[1], end_point[0], end_point[1])

                    start_point_azimuth = inverse_distance_segment["azi1"]
                    target_point_distance = abs(abs(self.getTrajectory().getPoints()[startPoint_.getIdentifier()-1].getX()) - abs(x_shift))
                    target_projected = spatial.getDistance(start_point[0], start_point[1], start_point_azimuth, target_point_distance)
                    target_projected_wkt = spatial.getPointGeometryText(target_projected["lat2"], target_projected["lon2"], 0., swap)
                    (target_projected_wkt, swap_) = spatial.reproject_geometry(target_projected_wkt, EPSG_id_target, EPSG_id_source)

                    self.getTrajectory().setTouchdownPoint(spatial.CreateGeometryFromWkt(target_projected_wkt))

                    # geometry_text_list = []
                    startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                    endPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                    endPoint_copy.setZ(0)
                    endPoint_copy.updateGeometryText()

                else:
                    (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(startPoint_.getGeometryText(), self.getTrajectory().getTouchdownPoint()),
                        EPSG_id_source, EPSG_id_target)
                    start_point, end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0], spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                    dist_startPoint_sasPoint = spatial.getInverseDistance(start_point[0], start_point[1], end_point[0], end_point[1])['s12']

                    (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(self.getTrajectory().getTouchdownPoint(), endPoint_.getGeometryText()),
                        EPSG_id_source, EPSG_id_target)
                    start_point, end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0], spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                    dist_sasPoint_endPoint = spatial.getInverseDistance(start_point[0], start_point[1], end_point[0], end_point[1])['s12']

                    if dist_startPoint_sasPoint > dist_sasPoint_endPoint:
                        startPoint_copy.setX(spatial.getAllPoints(self.getTrajectory().getTouchdownPoint())[0][0])
                        startPoint_copy.setY(spatial.getAllPoints(self.getTrajectory().getTouchdownPoint())[0][1])
                    startPoint_copy.setZ(0)
                    startPoint_copy.updateGeometryText()
                    endPoint_copy.setZ(0)
                    endPoint_copy.updateGeometryText()

            elif startPoint_.getMode() == "TO" or startPoint_.getMode() == "CL":
                if z2_ > 0:
                    hor_ext = self.getAircraft().getEmissionDynamicsByMode()["CL"].getEmissionDynamics(sas_method)['horizontal_extension']
                    ver_ext = self.getAircraft().getEmissionDynamicsByMode()["CL"].getEmissionDynamics(sas_method)['vertical_extension']
                    ver_shift = self.getAircraft().getEmissionDynamicsByMode()["CL"].getEmissionDynamics(sas_method)['vertical_shift']
                    hor_shift = self.getAircraft().getEmissionDynamicsByMode()["CL"].getEmissionDynamics("default")['horizontal_shift']

                (segment_geometry_wkt, swap) = spatial.reproject_geometry(
                        spatial.getLineGeometryText(startPoint_.getGeometryText(), endPoint_.getGeometryText()),
                        EPSG_id_source, EPSG_id_target)

                start_point = spatial.getAllPoints(segment_geometry_wkt, swap)[0]
                end_point = spatial.getAllPoints(segment_geometry_wkt, swap)[-1]
                inverse_distance_segment = spatial.getInverseDistance(start_point[0], start_point[1], end_point[0], end_point[1])
                start_point_azimuth, end_point_azimuth = inverse_distance_segment["azi1"], inverse_distance_segment["azi2"]

                target_projected = spatial.getDistance(start_point[0], start_point[1], start_point_azimuth, -hor_shift)
                target_projected_wkt = spatial.getPointGeometryText(target_projected["lat2"], target_projected["lon2"], 0., swap)
                (target_projected_wkt, swap_) = spatial.reproject_geometry(target_projected_wkt, EPSG_id_target, EPSG_id_source)
                startPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                startPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                startPoint_copy.setZ(max(0, startPoint_.getZ() + ver_shift))
                startPoint_copy.updateGeometryText()

                target_projected = spatial.getDistance(end_point[0], end_point[1], end_point_azimuth, -hor_shift)
                target_projected_wkt = spatial.getPointGeometryText(target_projected["lat2"], target_projected["lon2"], 0., swap)
                (target_projected_wkt, swap_) = spatial.reproject_geometry(target_projected_wkt, EPSG_id_target, EPSG_id_source)
                endPoint_copy.setX(spatial.getAllPoints(target_projected_wkt)[0][0])
                endPoint_copy.setY(spatial.getAllPoints(target_projected_wkt)[0][1])
                endPoint_copy.setZ(max(0, endPoint_.getZ() + ver_shift))
                endPoint_copy.updateGeometryText()

                emissions.setVerticalExtent({'z_min': startPoint_copy.getZ(), 'z_max': ver_ext + startPoint_copy.getZ()})

            multipolygon = spatial.ogr.Geometry(spatial.ogr.wkbMultiPolygon)
            all_points = spatial.getAllPoints(spatial.getLineGeometryText(startPoint_copy.getGeometryText(), endPoint_copy.getGeometryText()))
            for p_, point_ in enumerate(all_points):
                # point_ example (802522.928722, 5412293.034699, 0.0)
                if p_ + 1 == len(all_points):
                    break
                geometry_wkt_i = 'LINESTRING Z(%s %s %s, %s %s %s)' % (
                    all_points[p_][0], all_points[p_][1], all_points[p_][2], all_points[p_ + 1][0],
                    all_points[p_ + 1][1], all_points[p_ + 1][2]
                )
                leftline, rightline = self.CalculateParallels(geometry_wkt_i, hor_ext, 0, 0, 3857, 4326)  # in lon / lat !
                poly_geo = spatial.getRectangleXYZFromBoundingBox(leftline, rightline, 3857, 4326)
                multipolygon.AddGeometry(poly_geo)
                emissions.setGeometryText(multipolygon.ExportToWkt())

        else:
            # logger.debug("Calculate RWY emissions WITHOUT Smooth & Shift Approach.")
            emissions.setVerticalExtent({'z_min': 0, 'z_max': 0})
            emissions.setGeometryText(spatial.getLineGeometryText(startPoint_.getGeometryText(), endPoint_.getGeometryText()))

        # emissions calculation
        traj = self.getTrajectory() if not atRunway else self.getTrajectoryAtRunway()
        if not traj is None:
            # time spent in segment
            time_in_segment_ = traj.calculateDistanceBetweenPoints(startPoint_, endPoint_, "time")
            # distance in segment
            space_in_segment_ = traj.calculateDistanceBetweenPoints(startPoint_, endPoint_, "space")

            emission_index_ = None
            if method["name"] == "bymode" :
                emission_index_ = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(
                    startPoint_.getMode())

                copy_emission_index_ = copy.deepcopy(emission_index_)
                if method["config"]["apply_nox_corrections"]:
                    logger.info("Applying NOx Correction for Ambient Conditions")
                    corr_nox_ei = nox_correction_for_ambient_conditions(emission_index_.getNOx(),
                                                                        method["config"]["airport_altitude"], self.getTakeoffWeightRatio(),
                                                                        ac=method["config"]["ambient_conditions"])
                    copy_emission_index_.setObject("nox_g_kg", corr_nox_ei)

            else:
                # get emission indices based on the engine-thrust setting of the particular segment
                emission_index_ = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByPowerSetting(
                    startPoint_.getEngineThrust(), method=method)

                # ToDo: Permanent fix for PM10
                if method["name"] == "BFFM2":
                    if emission_index_ is None:
                        # logger.error("Error: Cannot calculate EI w. BFFM2. The 'by mode' method will be used for source: '%s'" %(self.getName()))
                        copy_emission_index_ = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(
                            startPoint_.getMode())
                    else:
                        copy_emission_index_ = copy.deepcopy(emission_index_)

                        pm10_g_kg = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(
                            startPoint_.getMode()).getPM10()
                        try:
                            copy_emission_index_.setObject("pm10_g_kg", pm10_g_kg[0])
                        except:
                            logger.error("Couldn't add emission index for PM10 (%s)"%self.getName())

                        sox_g_kg = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(
                            startPoint_.getMode()).getSOx()
                        try:
                            copy_emission_index_.setObject("sox_g_kg", sox_g_kg[0])
                        except:
                            logger.error("Couldn't add emission index for SOx (%s)"%self.getName())

                    if method["config"]["apply_nox_corrections"]:
                        logger.info("Applying NOx Correction for Ambient Conditions. NOx EI will be calculated using 'By mode' method.")
                        nox_g_kg = self.getAircraftEngine().getEmissionIndex().getEmissionIndexByMode(
                            startPoint_.getMode()).getNOx()
                        corr_nox_ei = nox_correction_for_ambient_conditions(nox_g_kg,
                                                                            method["config"]["airport_altitude"], self.getTakeoffWeightRatio(), ac=method["config"]["ambient_conditions"])
                        copy_emission_index_.setObject("nox_g_kg", corr_nox_ei)


            if (copy_emission_index_ is None):
                logger.error("Did not find emission index for aircraft with type '%s'." % (self.getAircraft()))
            emissions.add(copy_emission_index_,
                              float(time_in_segment_) * float(self.getAircraft().getEngineCount()))

        return {"emissions": emissions, "distance_time": float(time_in_segment_),
                "distance_space": float(space_in_segment_)}

    def calculateEmissions(self, atRunway = True, method=None, mode="",
                           limit=None):
        # emissions_list = mov.calculateEmissions(method=method, limit=limit)
        # emissions = sum(em_["emissions"] for em_ in emissions_list)
        if limit is None:
            limit = {}
        if method is None:
            method = {"name": "bymode", "config": {}}
        emissions = []

        # add emissions on flight trajectory (incl. runway)
        emissions.extend(self.calculateFlightEmissions(atRunway, method, mode, limit))

        # # add emissions at gate (gpu, gse etc.)
        emissions.extend(self.calculateGateEmissions(sas=method["config"]["apply_smooth_and_shift"]))

        # # add taxiing emissions
        emissions.extend(self.calculateTaxiingEmissions(sas=method["config"]["apply_smooth_and_shift"]))

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
        if (ac_group in self.getGate().getEmissionProfileGroups()):
           ac_group = self.getAircraft().getGroup()
        else:
            matched = difflib.get_close_matches(self.getAircraft().getGroup(), self.getGate().getEmissionProfileGroups(source_type=source_type))
            if matched:
                ac_group = matched[0]
                if not ac_group.lower() == self.getAircraft().getGroup().lower():
                    logger.warning("Did not find a gate emission profile for source type '%s' and aircraft group '%s', "
                                   "but matched to '%s'. Probably update the table 'default_gate_profiles'."
                                   % (source_type, ac_group, self.getAircraft().getGroup()))
        # if ac_group is None:
        #     logger.error("Unknown aircraft group identifier for source type '%s'. Aircraft is '%s'. Update default association in default_aircraft." % (source_type, self.getAircraft().getName()))

        return ac_group

    def getGateOccupancy(self, ac_group, source_type):
        occupancy_in_min = 0.
        profile_ = self.getGate().getEmissionProfile(ac_group, self._departure_arrival, source_type)
        if not profile_ is None:
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


    def getAircraft(self):
        return self._aircraft
    def setAircraft(self, var):
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
        self.setTrajectoryAtRunway(self.calculateTrajectoryAtRunway(offset_by_touchdown=True))

    def setTrajectoryAtRunway(self, var):
        self._trajectory_at_runway = var
        self._trajectory_at_runway.setIsCartesian(False)

    def calculateTrajectoryAtRunway(self, offset_by_touchdown=True):
        trajectory = None
        if self.getTrajectory() is None:
            logger.error("Could not find trajectory for movement at runway time '%s'." % (str(self.getRunwayTime(as_str=True))))
        elif self.getRunway() is None:
            logger.error("Could not find runway for movement at runway time '%s'." % (str(self.getRunwayTime(as_str=True))))
        elif not (self.getRunwayDirection() in self.getRunway().getDirections()):
            logger.error("Could not find runway direction '%s' (movement runway time='%s'." % (str(self.getRunwayDirection()), str(self.getRunwayTime(as_str=True))))
        else:
            trajectory = AircraftTrajectory(self.getTrajectory(), skipPointInitialization=True)
            trajectory.setIsCartesian(False)
            # Shift coordinates by touchdown offset (only for arrivals)
            if offset_by_touchdown:
                offset_by_touchdown = True if self.isArrival() else False

            EPSG_id_source=3857
            EPSG_id_target=4326
            # Project geometry from 3857 to 4326
            (runway_geometry_wkt, swap) = spatial.reproject_geometry(self.getRunway().getGeometryText(), EPSG_id_source, EPSG_id_target)

            # Return tuple of points - runway ends
            runway_points_tuple_list = spatial.getAllPoints(runway_geometry_wkt, swap)
            if len(runway_points_tuple_list)>=2:
                # assumes that runway is a straight line (i.e. earth is flat!)
                start_point = runway_points_tuple_list[0] # e.g. (lon, lat, alt)
                end_point = runway_points_tuple_list[-1] # e.g. (43.6157352579433, 1.38014783105964, 0.0)

                #get the azimuth for the runway
                # getInverseDistance(lat1, lon1, lat2, lon2, EPSG_id=4326)
                # inverseDistance_dict = Spatial.getInverseDistance(start_point[0], start_point[1], end_point[0], end_point[1])
                inverseDistance_dict = spatial.getInverseDistance(start_point[1], start_point[0], end_point[1], end_point[0])
                start_point_azimuth = inverseDistance_dict["azi1"]
                end_point_azimuth = inverseDistance_dict["azi2"]

                # ----------------------------------------------------------------------------------------------------------------
                # get coordinate of runway threshold
                # runway_point = (0.,0.,0.)
                # runway_azimuth = 0.

                # ToDo: FIXME touchdown offset
                if offset_by_touchdown:
                    touchdown_offset = self.getRunway().getTouchdownOffset()

                # intersection = loads(self.getRunway().getGeometryText()).intersection(self.getTaxiRoute().getSegmentsAsLineString())
                intersection = self.getRunway().getGeometry().buffer(1).intersection(
                    self.getTaxiRoute().getSegmentsAsLineString())

                # osgeo.ogr.Geometry: Point(lat, lon)
                # Direction is either first or last point (assume that runway naming list represents direction of points)

                if not self.getRunway().getDirections().index(self.getRunwayDirection()):
                    runway_point, runway_azimuth = end_point, end_point_azimuth
                    runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180
                    # runway_point, runway_azimuth = end_point, end_point_azimuth
                    # runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180
                    # if self.getDepartureArrivalFlag() == "A":
                    #     (rwy_point, rwy_point_wkt) = Spatial.reproject_Point(intersection.x, intersection.y,
                    #                                                          EPSG_id_source, EPSG_id_target)
                    #     runway_point = (rwy_point.GetY(), rwy_point.GetX())

                else:
                    runway_point, runway_azimuth = start_point, start_point_azimuth

                try:
                    (rwy_point, rwy_point_wkt) = spatial.reproject_Point(intersection.centroid.x, intersection.centroid.y,
                                                                         EPSG_id_source, EPSG_id_target)
                    runway_point = (rwy_point.GetY(), rwy_point.GetX())
                except:
                    logger.warning("No intersection point between runway '%s' and taxiroute '%s'"%(self.getRunwayDirection(),
                                                                                                   self.getTaxiRoute().getName()))

                    # runway_point, runway_azimuth = start_point, start_point_azimuth
                    # # runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180
                    # if self.getDepartureArrivalFlag() == "A":
                    #     (rwy_point, rwy_point_wkt) = Spatial.reproject_Point(intersection.x, intersection.y,
                    #                                                          EPSG_id_source, EPSG_id_target)
                    #     runway_point = (rwy_point.GetY(), rwy_point.GetX())

                    # if self.getDepartureArrivalFlag() == "D":
                    #     runway_point, runway_azimuth = start_point, start_point_azimuth
                    # else:
                    #     runway_point, runway_azimuth = end_point, end_point_azimuth
                    #     if not intersection.is_empty:
                    #         (rwy_point, rwy_point_wkt) = Spatial.reproject_Point(intersection.x, intersection.y, EPSG_id_source, EPSG_id_target)
                    #         runway_point = (rwy_point.GetY(), rwy_point.GetX())

                # # # For ARR (only), take back azimuth (# Less than 180 degrees (< 3.141592 rad), then add 180 degrees):
                # if self.getDepartureArrivalFlag() == "A":
                #     runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180

                # DEP: construction starts with nearest point
                # ARR: construction starts with point most far away
                for point in self.getTrajectory().getPoints():

                    # aircraft trajectory point with from default_aircraft_profiles
                    origin = (0.,0.,0.)
                    #target point with cartesian coordinates
                    target_point = point.getCoordinates()
                    target_point_distance = spatial.getDistanceXY(target_point[0], target_point[1], target_point[2],
                                                                  origin[0], origin[1], origin[2])
                    # if self.getDepartureArrivalFlag() == "A":
                    #     target_point_distance = target_point_distance + self.getTrajectory().getPoints()[-1].getX()
                    # if self.getDepartureArrivalFlag() == "A":
                    #     if self.getRunway().getDirections().index(self.getRunwayDirection()):
                    #         target_point_distance = target_point_distance - self.getTrajectory().getPoints()[-1].getX()
                    #         if target_point == origin:
                    #             # for ARR, when landing take forward azimuth
                    #             runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180
                    #     else:
                    #         target_point_distance = target_point_distance - self.getTrajectory().getPoints()[-1].getX()
                    #         if target_point == origin:
                    #             # for ARR, when landing take forward azimuth
                    #             runway_azimuth = runway_azimuth + 180 if runway_azimuth < 180 else runway_azimuth - 180


                    #get target point (calculation in 4326 projection)
                    target_projected = spatial.getDistance(runway_point[1], runway_point[0], runway_azimuth, target_point_distance)
                    #target point (wkt) with coordinates in 4326
                    target_projected_wkt = spatial.getPointGeometryText(target_projected["lon2"], target_projected["lat2"], 0., swap)
                    #reproject target from 4326 to 3857
                    (target_projected_wkt, swap_) = spatial.reproject_geometry(target_projected_wkt, EPSG_id_target, EPSG_id_source)

                    #add target to list of points of the (shifted) trajectory
                    for p in spatial.getAllPoints(target_projected_wkt):
                        p_ = AircraftTrajectoryPoint(point)
                        # Update x and y coordinates (z coordinate is not updated by distance calculation)
                        p_.setCoordinates(p[0],p[1],target_point[2])
                        p_.updateGeometryText()
                        trajectory.addPoint(p_)
                    trajectory.updateGeometryText()
            else:
                logger.error("Did not find enough points for geometry '%s'" % (runway_geometry_wkt))

        return trajectory

    def getRunway(self):
        return self._runway
    def setRunway(self, var):
        self._runway = var

    #["08R", "26L"]
    def getRunwayDirection(self):
        return self._runway_direction

    def setRunwayDirection(self, var):
        self._runway_direction = var
        #if isinstance(var, str):
        #    var = ''.join(c for c in var if c.isdigit())
        #    var = conversion.convertToFloat(var)
        #self._runway_direction = var

    def getRunwayTime(self, as_str=False):
        if as_str:
            if not (conversion.convertToFloat(self._time) is None):
                return conversion.convertSecondsToTimeString(self._time)
        return self._time
    def setRunwayTime(self, val):
        self._time = val

    def getBlockTime(self, as_str=False):
        if as_str:
            if not (conversion.convertToFloat(self._block_time) is None):
                return conversion.convertSecondsToTimeString(self._block_time)

        return self._block_time
    def setBlockTime(self, val):
        self._block_time = val

    def setDomesticFlag(self, val):
        self._domestic= val
    def getDomesticFlag(self):
        return self._domestic

    def setDepartureArrivalFlag(self, val):
        self._departure_arrival= val
    def getDepartureArrivalFlag(self):
        return self._departure_arrival

    def isArrival(self):
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
        val += "\n\t Engine thrust level for taxiing: %f" % (float(self.getEngineThrustLevelTaxiing()))
        val += "\n\t Aircraft: %s" % ("\n\t".join(str(self.getAircraft()).split("\n")))
        val += "\n\t Trajectory: %s" % ("\n\t".join(str(self.getTrajectory()).split("\n")))
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

        #instantiate all movement objects
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

    def ProgressBarWidget(self):
        # from PyQt4 import QtGui, QtCore

        progressbar = QtWidgets.QProgressDialog("Please wait...", "Cancel", 0, 99)
        progressbar.setWindowTitle("Initializing Movements from Database")
        progressbar.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()
        # progressbar.canceled.connect(progressbar.cancel)
        # progressbar.closeEvent = progressbar.cancel()
        return progressbar

    def initMovements(self, debug=False):

        progressbar = self.ProgressBarWidget()
        progressbar.setValue(0)

        MovementDataFrame = pd.DataFrame.from_dict(self.getMovementDatabase().getEntries(), orient='index')
        if MovementDataFrame.empty:
            return
        logger.info("Number of movements in the DB: %s"%len(self.getMovementDatabase().getEntries()))

        df_cols = ["aircraft", "engine_name", "runway", "runway_direction", "gate", "taxi_route", "profile_id",
                   "trajectory", "runway_trajectory"]
        Eq_MovementDataFrame = pd.DataFrame(index=MovementDataFrame.index, columns=df_cols)
        Eq_MovementDataFrame = Eq_MovementDataFrame.fillna(np.nan)  # fill with None rather than NaNs

        aircraft_unique = MovementDataFrame["aircraft"].unique()
        for acf in aircraft_unique:
            indices = MovementDataFrame[MovementDataFrame.aircraft == acf].index
            Eq_MovementDataFrame.loc[indices, "aircraft"] = np.nan if not self.getAircraftStore().hasKey(acf) else acf
            if not self.getAircraftStore().hasKey(acf):
                logger.error("Aircraft %s wasn't found in the DB"%acf)

        engine_unique = MovementDataFrame["engine_name"].unique()
        for eng in engine_unique:
            indices = MovementDataFrame[MovementDataFrame["engine_name"] == eng].index
            Eq_MovementDataFrame.loc[indices, "engine_name"] = None

            if self.getEngineStore().hasKey(eng):
                Eq_MovementDataFrame.loc[indices, "engine_name"] = eng

            #     # if any(item == "HELICOPTER" for item in ac_types)
            #     if not "HELICOPTER" in ac_types:
            #         Eq_MovementDataFrame.loc[indices, "engine_name"] = eng

            elif self.getHeliEngineStore().hasKey(eng):
                Eq_MovementDataFrame.loc[indices, "engine_name"] = eng

            else:
                logger.debug("Engine %s not in ALAQS DB" % eng)
                if not MovementDataFrame[MovementDataFrame["engine_name"]==eng].empty:
                    def_ac = MovementDataFrame[MovementDataFrame["engine_name"]==eng]["aircraft"].iloc[0]
                    if self.getAircraftStore().hasKey(def_ac):
                        eng = self.getAircraftStore().getObject(acf).getDefaultEngine().getName()
                        logger.debug("\t +++ taking default engine %s for aircraft %s" %(eng, def_ac))
                        Eq_MovementDataFrame.loc[indices, "engine_name"] = eng \
                            if self.getEngineStore().hasKey(eng) or self.getEngineStore().hasKey(eng) else None

            #     if "HELICOPTER" in ac_types:
            #         Eq_MovementDataFrame.loc[indices, "engine_name"] = eng
            # else:
            #     print("Engine (%s) wasn't found in the DB"%eng)
            #     # Add default engine for acft if engine is missing or is unknown
            #     for ij_ in indices:
            #         if self.getAircraftStore().hasKey(MovementDataFrame.loc[ij_, "aircraft"]):
            #             Eq_MovementDataFrame.loc[ij_, "engine_name"] = self.getAircraftStore().getObject(
            #                         MovementDataFrame.loc[ij_, "aircraft"]).getDefaultEngine().getName()
            #
            #             logger.warning("Engine (%s) wasn't found in the DB, taking default engine (%s)"%(eng,
            #                 self.getAircraftStore().getObject(MovementDataFrame.loc[ij_, "aircraft"]).getDefaultEngine().getName()))

        runway_unique = MovementDataFrame["runway"].unique()
        for rwy in runway_unique:
            indices = MovementDataFrame[MovementDataFrame["runway"] == rwy].index
            if not self.getRunwayStore().isinKey(rwy):
                Eq_MovementDataFrame.loc[indices, "runway"] = np.nan
                logger.warning("Runway %s wasn't found in the DB"%rwy)
            else:
                Eq_MovementDataFrame.loc[indices, "runway_direction"] = rwy
                rwy_used = [key for key in list(self.getRunwayStore().getObjects().keys()) if rwy in key]
                Eq_MovementDataFrame.loc[indices, "runway"] = rwy_used[0]

        gate_unique = MovementDataFrame["gate"].unique()
        for gte in gate_unique:
            indices = MovementDataFrame[MovementDataFrame["gate"] == gte].index
            Eq_MovementDataFrame.loc[indices, "gate"] = np.nan if not self.getGateStore().hasKey(gte) else gte
            if not self.getGateStore().hasKey(gte):
                logger.warning("Gate %s wasn't found in the DB"%gte)

        empty_tx_ind = MovementDataFrame[(MovementDataFrame["taxi_route"] == "")|(MovementDataFrame["taxi_route"] == np.NaN)].index
        MovementDataFrame.loc[empty_tx_ind, "taxi_route"] = \
        (MovementDataFrame[['gate', 'runway', 'departure_arrival']].apply('/'.join, axis=1).astype(str) + "/1").loc[empty_tx_ind]

        taxiroute_unique = MovementDataFrame["taxi_route"].unique()
        all_taxi_routes = list(self.getTaxiRouteStore().getObjects().keys())

        for txr in taxiroute_unique:
            indices = MovementDataFrame[MovementDataFrame["taxi_route"] == txr].index
            if not self.getTaxiRouteStore().hasKey(txr):
                if "/D/" in txr:
                    alt_routes = difflib.get_close_matches(txr, [_tx_ for _tx_ in all_taxi_routes if "/D/" in _tx_])
                elif "/A/" in txr:
                    alt_routes = difflib.get_close_matches(txr, [_tx_ for _tx_ in all_taxi_routes if "/A/" in _tx_])
                if alt_routes:
                    Eq_MovementDataFrame.loc[indices, "taxi_route"] = alt_routes[0]
                    logger.warning("Taxiroute '%s' was replaced with '%s'"%(txr, alt_routes[0]))
                else:
                    logger.error("No taxiroute found to replace '%s' which is not in the database"%(txr))
                    Eq_MovementDataFrame.loc[indices, "taxi_route"] = np.NaN
            else:
                Eq_MovementDataFrame.loc[indices, "taxi_route"] = txr

        profile_unique = MovementDataFrame["profile_id"].astype(str).unique()
        for prf in profile_unique:
            indices = MovementDataFrame[MovementDataFrame["profile_id"] == prf].index
            # Add a default profile even when the profile_id is missing
            if len(indices)==0 or not prf or pd.isna(prf) or not self.getAircraftTrajectoryStore().hasKey(prf):
                for ag, airgroup in MovementDataFrame.groupby(["aircraft", "departure_arrival"]):
                    ij_ = airgroup.index
                    if self.getAircraftStore().hasKey(airgroup["aircraft"].iloc[0]):
                        if airgroup["departure_arrival"].iloc[0] == "A":
                            Eq_MovementDataFrame.loc[ij_, "profile_id"] = \
                                self.getAircraftStore().getObject(airgroup["aircraft"].iloc[0]).getDefaultArrivalProfileName()
                        elif airgroup["departure_arrival"].iloc[0] == "D":
                            Eq_MovementDataFrame.loc[ij_, "profile_id"] = \
                                self.getAircraftStore().getObject(airgroup["aircraft"].iloc[0]).getDefaultDepartureProfileName()
                    else:
                        logger.debug("AC %s not in AircraftStore" % (airgroup["aircraft"].iloc[0]))
                        continue

            # elif not prf or pd.isna(prf) or not self.getAircraftTrajectoryStore().hasKey(prf) :
            #     for ij_ in indices:
            #         if self.getAircraftStore().hasKey(MovementDataFrame.loc[ij_, "aircraft"]):
            #             if MovementDataFrame.loc[ij_, "departure_arrival"] == "A":
            #                 Eq_MovementDataFrame.loc[ij_, "profile_id"] =\
            #                     self.getAircraftStore().getObject(MovementDataFrame.loc[ij_, "aircraft"]).getDefaultArrivalProfileName()
            #             elif MovementDataFrame.loc[ij_, "departure_arrival"] == "D":
            #                 Eq_MovementDataFrame.loc[ij_, "profile_id"] =\
            #                     self.getAircraftStore().getObject(MovementDataFrame.loc[ij_, "aircraft"]).getDefaultDepartureProfileName()
            #             # print(Eq_MovementDataFrame.loc[ij_, "profile_id"])
            #         else:
            #             # print("AC %s not in AircraftStore"%(MovementDataFrame.loc[ij_, "aircraft"]))
            #             logger.debug("AC %s not in AircraftStore"%(MovementDataFrame.loc[ij_, "aircraft"]))
            else:
                Eq_MovementDataFrame.loc[indices, "profile_id"] = None

        # select unique combinations of Eq_MovementDataFrame where runway and profile_id
        unique_rwy_trajectories = \
            Eq_MovementDataFrame[
                ["runway", "runway_direction", "taxi_route", "profile_id"]].drop_duplicates().reset_index(drop=True)
        for trj_ind in unique_rwy_trajectories.index:
            # Should always have values for rwy, rwy_dir, tx_route, prf_id
            rwy = unique_rwy_trajectories.loc[trj_ind]["runway"]
            rwy_dir = unique_rwy_trajectories.loc[trj_ind]["runway_direction"]
            tx_route = unique_rwy_trajectories.loc[trj_ind]["taxi_route"]
            prf_id = unique_rwy_trajectories.loc[trj_ind]["profile_id"]

            # ToDo: Handle exceptions
            mov_df = Eq_MovementDataFrame[
                (Eq_MovementDataFrame.runway == rwy) & (Eq_MovementDataFrame.runway_direction == rwy_dir)
                & (Eq_MovementDataFrame.taxi_route == tx_route) & (Eq_MovementDataFrame.profile_id == prf_id)
            ]
            if mov_df.empty:
                logger.warning("No match found for RWY: %s, Direction: %s, Route: %s, Profile: %s"%(rwy, rwy_dir, tx_route, prf_id))
                continue
            else:
                inds = mov_df.index

                proxy_dict = {"runway_time":MovementDataFrame["runway_time"].iloc[0],
                              "block_time":MovementDataFrame["block_time"].iloc[0],
                              }
                proxy_mov = Movement(proxy_dict)
                if "/D/" in tx_route:
                    proxy_mov.setDepartureArrivalFlag("D")
                else:
                    proxy_mov.setDepartureArrivalFlag("A")
                proxy_mov.setGate(self.getGateStore().getObject(mov_df.iloc[0]["gate"]))
                proxy_mov.setAircraft(self.getAircraftStore().getObject(mov_df.iloc[0]["aircraft"]))

                if self.getEngineStore().hasKey(mov_df.iloc[0]["engine_name"]):
                    proxy_mov.setAircraftEngine(self.getEngineStore().getObject(mov_df.iloc[0]["engine_name"]))
                elif self.getHeliEngineStore().hasKey(mov_df.iloc[0]["engine_name"]):
                    proxy_mov.setAircraftEngine(self.getHeliEngineStore().getObject(mov_df.iloc[0]["engine_name"]))

                proxy_mov.setRunway(self.getRunwayStore().getObject(mov_df.iloc[0]["runway"]))
                proxy_mov.setRunwayDirection(mov_df.iloc[0]["runway_direction"])
                proxy_mov.setTaxiRoute(self.getTaxiRouteStore().getObject(mov_df.iloc[0]["taxi_route"]))
                proxy_mov.setTrajectory(self.getAircraftTrajectoryStore().getObject(mov_df.iloc[0]["profile_id"]))
                proxy_mov.updateTrajectoryAtRunway()

                Eq_MovementDataFrame.loc[inds, "runway"] = proxy_mov.getRunway()
                Eq_MovementDataFrame.loc[inds, "taxi_route"] = proxy_mov.getTaxiRoute()
                Eq_MovementDataFrame.loc[inds, "trajectory"] = proxy_mov.getTrajectory()
                Eq_MovementDataFrame.loc[inds, "runway_trajectory"] = proxy_mov.getTrajectoryAtRunway()

        Movements_df = Eq_MovementDataFrame.dropna()
        logger.info("Number of movements retained: %s"%Movements_df.shape[0])
        # progressbar = self.ProgressBarWidget()
        count_ = 0
        for key, movement_dict in self.getMovementDatabase().getEntries().items():
            mov = Movement(movement_dict)
            count_ += +1
            if (count_%10.0) == 0:
                progressbar.setValue(int(100 * float(count_) / len(
                    self.getMovementDatabase().getEntries())))
                QtCore.QCoreApplication.instance().processEvents()
            if progressbar.wasCanceled():
                break

            if not key in Movements_df.index:
                logger.warning("Operation with 'oid' = %s will not be accounted for due to missing data"%key)
                # self.getMovementDatabase().removeEntry(key)
                continue

            mov.setGate(self.getGateStore().getObject(Movements_df.loc[key]["gate"]))
            mov.setAircraft(self.getAircraftStore().getObject(Movements_df.loc[key]["aircraft"]))

            if self.getAircraftStore().getObject(Movements_df.loc[key]["aircraft"]).getGroup() == "HELICOPTER":
                if self.getHeliEngineStore().hasKey(Movements_df.loc[key]["engine_name"]):
                    mov.setAircraftEngine(self.getHeliEngineStore().getObject(Movements_df.loc[key]["engine_name"]))
                else:
                    # replace with Default Engine
                    default_eng=self.getAircraftStore().getObject(Movements_df.loc[key]["aircraft"]).getDefaultEngine()
                    logger.info("Engine wasn't found for movement %s. Will use default engine (%s)."%(mov.getName(), default_eng.getName()))
                    mov.setAircraftEngine(default_eng)
            else:
                if self.getEngineStore().hasKey(Movements_df.loc[key]["engine_name"]):
                    mov.setAircraftEngine(self.getEngineStore().getObject(Movements_df.loc[key]["engine_name"]))
                else:
                    # replace with Default Engine
                    default_eng=self.getAircraftStore().getObject(Movements_df.loc[key]["aircraft"]).getDefaultEngine()
                    logger.info("Engine wasn't found for movement %s. Will use default engine (%s)."%(mov.getName(), default_eng.getName()))
                    mov.setAircraftEngine(default_eng)

            mov.setRunway(Movements_df.loc[key]["runway"])
            mov.setRunwayDirection(Movements_df.loc[key]["runway_direction"])
            mov.setTaxiRoute(Movements_df.loc[key]["taxi_route"])
            mov.setTrajectory(Movements_df.loc[key]["trajectory"])
            mov.setTrajectoryAtRunway(Movements_df.loc[key]["runway_trajectory"])

            self.setObject(movement_dict["oid"] if "oid" in movement_dict else "unknown", mov)


class MovementDatabase(SQLSerializable, metaclass=Singleton):
    """
    Class that grants access to user-defined movements stored in the database
    """

    def __init__(self,
                 db_path_string,
                 table_name_string="user_aircraft_movements",
                 table_columns_type_dict=None,
                 primary_key="oid",
                 deserialize=True
                 ):
        if table_columns_type_dict is None:
            table_columns_type_dict = OrderedDict([
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
                ("set_time_of_main_engine_start_after_block_off_in_s",
                 "DECIMAL NULL"),
                ("set_time_of_main_engine_start_before_takeoff_in_s",
                 "DECIMAL NULL"),
                ("set_time_of_main_engine_off_after_runway_exit_in_s",
                 "DECIMAL NULL"),
                ("engine_thrust_level_for_taxiing", "DECIMAL NULL"),
                ("taxi_fuel_ratio", "DECIMAL NULL"),
                ("number_of_stop_and_gos", "DECIMAL NULL"),
                ("domestic", "TEXT"),
                ("annual_operations", "DECIMAL NULL"),
            ])

        SQLSerializable.__init__(self, db_path_string, table_name_string,
                                 table_columns_type_dict, primary_key)

        if self._db_path and deserialize:
            self.deserialize()

#
# if __name__ == "__main__":
#     # print("--- %s seconds ---" % (time.time() - start_time))
#
#     # from qgis.PyQt import QtGui
#     # from python_qt_binding import QtGui, QtCore  # new imports
#     # app = QtWidgets.QApplication(sys.argv)
#     app = QtWidgets.QApplication.instance()
#     if app is None:
#         app = QtWidgets.QApplication(sys.argv)
#         print('QApplication instance created: %s' % str(app))
#     else:
#         app.processEvents()
#         app.closeAllWindows()
#         print('QApplication instance already exists: %s' % str(app))
#     # from . import __init__
#     # import alaqslogging
#
#     import matplotlib
#     matplotlib.use('Qt5Agg')
#     import matplotlib.pyplot as plt
#     plt.ion()    # logging.getLogger('matplotlib.font_manager').disabled = True
#     # from shapely.wkt import loads
#
#
#     # path_to_database = os.path.join("..","..","example/", "CAEPport", "CAEPport_out.alaqs")
#     # path_to_database = os.path.join("..","..","example/", "CAEPport", "CAEPport_out_noAPU.alaqs")
#     path_to_database = os.path.join("..", "..", "example/", "CAEPport_training", "caepport_out.alaqs")
#
#
#     if not os.path.isfile(path_to_database):
#         # fix_print_with_import
#         print("Database %s not found"%path_to_database)
#
#     store = MovementStore(path_to_database, debug=False)
#     # for key, movement_dict in  store.getMovementDatabase().getEntries().iteritems():
#     #     print(key, movement_dict)
#     #     #gate
#     #     if "gate" in movement_dict:
#     #         if store.getGateStore().hasKey(movement_dict["gate"]):
#     #             print store.getGateStore().getObject(movement_dict["gate"])
#     #                 self.getGateStore().getObject(mov_df.iloc[0]["gate"])
#     #         else:
#     #             print("Could not find gate with name '%s'." % (movement_dict["gate"]))
#
#     # print("--- %s seconds ---" % (time.time() - start_time))
#     # print("Number of Movements: %s"%len(store.getMovementDatabase().getEntries()))
#
# #     # then run calculateEmissionsPerSegment only once / unique mov and store result
# #     plot_ei = False
#
#     movements = []
#     for movement_name, movement in store.getObjects().items():
#         movements.append(movement)
#
#     limit = {
#         "max_height": 914.4,
#         "height_unit_in_feet":False
#     }
#     # max_limit = limit["max_height"] if limit['height_unit_in_feet'] is False else conversion.convertMetersToFeet(limit["max_height"])
#
#     installation_corrections = {
#                         "Takeoff":1.010,    # 100%
#                         "Climbout":1.012,   # 85%
#                         "Approach":1.020,   # 30%
#                         "Idle":1.100        # 7%
#     }
#
#     # ambient_conditions = {}
#     # try:
#     #     from .AmbientCondition import AmbientCondition, AmbientConditionStore
#     # except:
#     #     from AmbientCondition import AmbientCondition, AmbientConditionStore
#     ambient_conditions = AmbientCondition()
#
#     method={
#         "name":"bymode",
#         "config":{
#             "apply_smooth_and_shift": 'none',
#             # "apply_smooth_and_shift": 'default',
#             # "apply_smooth_and_shift": 'smooth & shift',
#             "apply_nox_corrections": False,
#             "airport_altitude": 0.,
#             "installation_corrections": installation_corrections,
#             "ambient_conditions": ambient_conditions
#         }
#     }
#
#     # for mov in movements[::-1]:
#     results_df = pd.DataFrame(index=range(0, len(movements)),
#                               columns=['name','gate','fuel_kg', 'co2_kg', 'co_g', 'hc_g', 'nox_g', 'sox_g', 'pm10_g'])
#     cnt = 0
#     for mov in movements:
#
#         print(mov.getName(), mov.getRunwayDirection(), mov.getAircraft().getName(),mov.getAircraftEngine().getName(), mov.getTrajectory().getIdentifier())
#
#         emissions_list = mov.calculateEmissions(method=method, limit=limit)
#         emissions = sum(em_["emissions"] for em_ in emissions_list)
#         try:
#             # fix_print_with_import
#             print("Fuel:",emissions.getFuel()[0],"\t CO2(kg):",emissions.getCO2()[0]/1000.,
#                   "\t CO(g):",emissions.getValue("CO", "g")[0], "\t NOx(g):",emissions.getValue("NOx", "g")[0])
#             # print mov.getAircraft().getType(), mov.getAircraftEngine().getName(), \
#             #     conversion.convertTimeToSeconds(abs(mov.getBlockTime() - mov.getRunwayTime())), \
#             #     mov.getDepartureArrivalFlag(), prof_id, mov.getGate().getName(), mov.getGate().getType(), \
#             #     emissions.getFuel()[0], emissions.getValue("CO2", "g")[0], emissions.getValue("CO", "g")[0], \
#             #     emissions.getValue("NOx", "g")[0], emissions.getValue("SOx", "g")[0], emissions.getValue("HC", "g")[0], \
#             #     emissions.getValue("PM10", "g")[0]
#         except:
#             # fix_print_with_import
#             print("----------------------------------")
#             # fix_print_with_import
#             print("Error for movement: %s"%mov.getName())
#             # fix_print_with_import
#             print("----------------------------------")
#
#         # fig, ax = plt.subplots()
#         # for em_ in emissions_list:
#         #     geom = em_["emissions"].getGeometry()
#         #     ax.set_title(mov.getName())
#         #     gpd.GeoSeries(geom).plot(ax=ax, color='r', alpha=0.25)
#
#         # gdf = gpd.GeoDataFrame(index=range(0, len(emissions_list)), columns=["CO", "geometry", "source", "L"])
#         # geoms = []
#         # cntgdf = 0
#         # for em_ in emissions_list:
#         #     try:
#         #         gdf.loc[cntgdf, "geometry"] = em_['emissions'].getGeometry()
#         #     except:
#         #         gdf.loc[cntgdf, "geometry"] = LineString()
#         #     # geoms.append(em_['emissions'].getGeometry())
#         #     gdf.loc[cntgdf, "CO"] = em_['emissions'].getValue('CO','g')[0]/1000
#         #     gdf.loc[cntgdf, "source"] = mov.getName()
#         #     gdf.loc[cntgdf, "L"] = em_['emissions'].getGeometry().length  # emissions_.getGeometry()
#         #     cntgdf += +1
#         #
#         # # gdf.loc[:, "geometry"] = geoms
#         # fig, ax = plt.subplots()
#         # ax.plot(mov.getRunway().getGeometry().xy[0], mov.getRunway().getGeometry().xy[1], linewidth=3, alpha=0.5, color="k")
#         # gdf[gdf.L>0].plot(ax=ax, column="L", legend=False, categorical=True, cmap='Set2')
#         # ax.set_title(mov.getName()+" / "+mov.getRunwayDirection())
#         # plt.show()
#         # break
#
#         # try:
#         #     results_df.loc[cnt, "name"] = mov.getName()
#         #     results_df.loc[cnt, "gate"] = mov.getGate().getName()
#         #     results_df.loc[cnt, "fuel_kg"] = emissions.getFuel()[0]
#         #     results_df.loc[cnt, "co2_kg"] = emissions.getCO2()[0]/1000.
#         #     results_df.loc[cnt, "co_g"] = emissions.getValue("CO", "g")[0]
#         #     results_df.loc[cnt, "hc_g"] = emissions.getValue("HC", "g")[0]
#         #     results_df.loc[cnt, "nox_g"] = emissions.getValue("NOx", "g")[0]
#         #     results_df.loc[cnt, "sox_g"] = emissions.getValue("SOx", "g")[0]
#         #     results_df.loc[cnt, "pm10_g"] = emissions.getValue("PM10", "g")[0]
#         # except:
#         #     results_df.loc[cnt, "name"] = mov.getName()
#         #     results_df.loc[cnt, "gate"] = mov.getGate().getName()
#         #     results_df.loc[cnt, "fuel_kg"] = np.nan
#         #     results_df.loc[cnt, "co2_kg"] = np.nan
#         #     results_df.loc[cnt, "co_g"] = np.nan
#         #     results_df.loc[cnt, "hc_g"] = np.nan
#         #     results_df.loc[cnt, "nox_g"] = np.nan
#         #     results_df.loc[cnt, "sox_g"] = np.nan
#         #     results_df.loc[cnt, "pm10_g"] = np.nan
#         #     # break
#         # cnt += +1
#
#     # results_df.to_excel("emissions_%s.xlsx"%(datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")), index=False)
#
#     # # gdf.dropna(how='all').to_csv(emissions_CO_%s.csv"%(datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")),index=False)
#     # gdf.dropna(how='all').plot(ax=ax, column="CO2", legend=True, categorical=True, cmap='jet')
#     # plt.show()
#     # # mplleaflet.show(fig=ax.figure, crs={'init': 'epsg:3857'}, tiles="cartodb_positron",
#     # #         path=os.path.join("..","..","example/", "CAEPport_training", "emissions_CO_%s.html"%(datetime.datetime.now().strftime("%Y_%m_%d_%H_%M"))))
#     # # plt.savefig(emissions_CO_%s.png"%(datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")), dpi=300, bbox_inches="tight")
#
#     # sys.exit(app.exec_())
#     app.quit()
#
# # CAEPport
# # if index_segment_ == 0 :
# # apu_time = None
# # if self.isArrival():
# #     if self.getAircraft().getGroup() == "JET LARGE" or self.getAircraft().getGroup() == "JET MEDIUM":
# #         apu_time = 0 if self.getGate().getType() == "PIER" else 30
# #     elif self.getAircraft().getGroup() == "JET REGIONAL" or self.getAircraft().getGroup() == "JET SMALL":
# #         apu_time = 0 if self.getGate().getType() == "PIER" else 15
# #
# # elif self.isDeparture():
# #     if self.getAircraft().getGroup() == "JET LARGE" or self.getAircraft().getGroup() == "JET MEDIUM":
# #         apu_time = 5 if self.getGate().getType() == "PIER" else 45
# #     elif self.getAircraft().getGroup() == "JET REGIONAL" or self.getAircraft().getGroup() == "JET SMALL":
# #         apu_time = 5 if self.getGate().getType() == "PIER" else 30
#
# # if not apu_time is None:
# #     apu_emiss_ = self.getAircraft().getApu().getEmissions("NR")
# #
# #     if "fuel_kg_sec" in apu_emiss_:
# #         em_.addFuel(apu_emiss_["fuel_kg_sec"] * apu_time)
# #     if "co_g_s" in apu_emiss_:
# #         em_.addCO(apu_emiss_["co_g_s"] * apu_time)
# #     if "co2_g_s" in apu_emiss_:
# #         em_.addCO2(apu_emiss_["co2_g_s"] * apu_time)
# #     if "hc_g_s" in apu_emiss_:
# #         em_.addHC(apu_emiss_["hc_g_s"] * apu_time)
# #     if "nox_g_s" in apu_emiss_:
# #         em_.addNOx(apu_emiss_["nox_g_s"] * apu_time)
#
#
# # if total APU time (theoretical) is greater than total taxiing time
# # if apu_time > abs(self.getBlockTime()-self.getRunwayTime()):
#
# #
# #     # 1: stand and taxiway
# #     elif self.getAPUCode()==1:
# #
# #     # 2: stand, taxiing and take-off/climb-out or approach/landing
# #     elif self.getAPUCode()==1:
# #
# #     else:
# #         logger.error("Wrong APU Code for movement %s"%(mov.getName()))
# #
# # else:
# #     apu_time = abs(self.getBlockTime()-self.getRunwayTime())
#
# # if index_segment_ == 0 and (self.isDeparture() or (self.isArrival() and self.getAPUCode()==1)):
# # add apu emissions to the first segment
# # apu_time = abs(self.getBlockTime()-self.getRunwayTime())
#
# # if not self.getAircraft().getApu() is None:
# #     apu_emiss_ = self.getAircraft().getApu().getEmissions("NL")
# #     if "fuel_kg_sec" in apu_emiss_:
# #         em_.addFuel(apu_emiss_["fuel_kg_sec"] * apu_time)
# #     if "co_g_s"  in apu_emiss_:
# #         em_.addCO(apu_emiss_["co_g_s"] * apu_time)
# #     if "co2_g_s"  in apu_emiss_:
# #         em_.addCO2(apu_emiss_["co2_g_s"] * apu_time)
# #     if "hc_g_s"  in apu_emiss_:
# #         em_.addHC(apu_emiss_["hc_g_s"] * apu_time)
# #     if "nox_g_s"  in apu_emiss_:
# #         em_.addNOx(apu_emiss_["nox_g_s"] * apu_time)
#
# # if not self.getAPUCode() is None and self.getAPUCode()>0:
# #     apu_time = self.getAircraft().getApuTimes()["arr_s"] if self.isArrival() else self.getAircraft().getApuTimes()["dep_s"]
# #     print(apu_time, self.getName())
#
# # apu_time = new_taxiway_segment_time
# # if not self.getAircraft().getApu() is None:
# #     apu_emiss_ = self.getAircraft().getApu().getEmissions("NR")
# #
# #     if "fuel_kg_sec" in apu_emiss_:
# #         em_.addFuel(apu_emiss_["fuel_kg_sec"] * apu_time)
# #     if "co_g_s"  in apu_emiss_:
# #         em_.addCO(apu_emiss_["co_g_s"] * apu_time)
# #     if "co2_g_s"  in apu_emiss_:
# #         em_.addCO2(apu_emiss_["co2_g_s"] * apu_time)
# #     if "hc_g_s"  in apu_emiss_:
# #         em_.addHC(apu_emiss_["hc_g_s"] * apu_time)
# #     if "nox_g_s"  in apu_emiss_:
# #         em_.addNOx(apu_emiss_["nox_g_s"] * apu_time)
# #         # em_.setCategory("APU")
#
# # Remaining emissions are queueing emissions.
# # These emissions are added to the last segment of the taxiway route for both departures and arrivals
