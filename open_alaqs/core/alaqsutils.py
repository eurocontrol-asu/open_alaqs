"""
Set of utility functions used by the Open ALAQS application. These include
basic unit conversion routines, text parsing/formatting functions, logging
and error processing functions ...

Created on 21 Mar 2013
@author: Dan Pearce
"""
import os
import sys
import traceback

from qgis.core import Qgis, QgsMessageLog

from open_alaqs.core import alaqsdblite
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.tools import conversion

logger = get_logger(__name__)

alaqs_main_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if alaqs_main_directory not in sys.path:
    sys.path.append(alaqs_main_directory)
tools_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
if tools_directory not in sys.path:
    sys.path.append(tools_directory)


def print_error(function_name, exception_object, e_object, log=logger):
    """
    Add entry to the ALAQS error-log file
    """

    try:
        # fix_print_with_import
        print(exception_object, e_object)
    except Exception:
        pass

    exc_type, exc_obj, exc_tb = sys.exc_info()
    error_msg = "[-] Error in %s() [line %d]: %s %s" % (
        function_name,
        exc_tb.tb_lineno,
        exc_type,
        exc_obj,
    )

    log.error(error_msg, exc_info=exception_object)

    formatted_errror = traceback.format_exception(
        None, e_object, e_object.__traceback__
    )
    QgsMessageLog.logMessage(
        (error_msg + "\n" + "".join(formatted_errror)),
        tag="Open ALAQS",
        level=Qgis.MessageLevel.Critical,
    )

    return error_msg


# ===========================================================
#           FUNCTIONS TO TURN LISTS INTO DICT
# ===========================================================


def dict_study_setup(study_setup_data):
    study_setup_dict = dict()
    study_setup_dict["oid"] = conversion.convertToInt(study_setup_data[0])
    study_setup_dict["airport_id"] = study_setup_data[1]
    study_setup_dict["alaqs_version"] = study_setup_data[2]
    study_setup_dict["project_name"] = study_setup_data[3]
    study_setup_dict["airport_name"] = study_setup_data[4]
    study_setup_dict["airport_code"] = study_setup_data[5]
    study_setup_dict["airport_country"] = study_setup_data[6]
    study_setup_dict["airport_latitude"] = study_setup_data[7]
    study_setup_dict["airport_longitude"] = study_setup_data[8]
    study_setup_dict["airport_elevation"] = study_setup_data[
        9
    ]  # *0.3048 # from ft to m
    study_setup_dict["airport_temperature"] = study_setup_data[10]
    study_setup_dict["vertical_limit"] = conversion.convertToFloat(
        study_setup_data[11], 0.0
    )
    study_setup_dict["roadway_method"] = study_setup_data[12]
    study_setup_dict["roadway_fleet_year"] = study_setup_data[13]
    study_setup_dict["roadway_country"] = study_setup_data[14]
    study_setup_dict["parking_method"] = study_setup_data[15]
    study_setup_dict["study_info"] = study_setup_data[16]
    study_setup_dict["date_created"] = study_setup_data[17]
    study_setup_dict["date_modified"] = study_setup_data[18]
    return study_setup_dict


def dict_airport_data(airport_data):
    airport_data_dict = dict()
    airport_data_dict["airport_code"] = airport_data[1]
    airport_data_dict["airport_name"] = airport_data[2]
    airport_data_dict["airport_country"] = airport_data[3]
    airport_data_dict["airport_latitude"] = airport_data[4]
    airport_data_dict["airport_longitude"] = airport_data[5]
    airport_data_dict["airport_elevation"] = conversion.convertToFloat(
        airport_data[6], 0.0
    )
    return airport_data_dict


def dict_roadway_data(roadway_data):
    try:
        dict_data = dict()
        dict_data["oid"] = conversion.convertToInt(roadway_data[0])
        dict_data["roadway_id"] = str(roadway_data[1])
        dict_data["vehicle_year"] = conversion.convertToFloat(roadway_data[2])
        dict_data["height"] = conversion.convertToFloat(roadway_data[3], 0.0)
        dict_data["distance"] = conversion.convertToFloat(roadway_data[4], 0.0)
        dict_data["speed"] = conversion.convertToFloat(roadway_data[5], 0.0)
        dict_data["vehicle_light"] = conversion.convertToFloat(roadway_data[6], 0.0)
        dict_data["vehicle_medium"] = conversion.convertToFloat(roadway_data[7], 0.0)
        dict_data["vehicle_heavy"] = conversion.convertToFloat(roadway_data[8], 0.0)
        dict_data["hour_profile"] = str(roadway_data[9])
        dict_data["daily_profile"] = str(roadway_data[10])
        dict_data["month_profile"] = str(roadway_data[11])
        dict_data["co_gm_km"] = conversion.convertToFloat(roadway_data[12], 0.0)
        dict_data["hc_gm_km"] = conversion.convertToFloat(roadway_data[13], 0.0)
        dict_data["nox_gm_km"] = conversion.convertToFloat(roadway_data[14], 0.0)
        dict_data["sox_gm_km"] = conversion.convertToFloat(roadway_data[15], 0.0)
        dict_data["pm10_gm_km"] = conversion.convertToFloat(roadway_data[16], 0.0)
        dict_data["p1_gm_km"] = conversion.convertToFloat(roadway_data[17], 0.0)
        dict_data["p2_gm_km"] = conversion.convertToFloat(roadway_data[18], 0.0)
        dict_data["method"] = str(roadway_data[19])
        dict_data["scenario"] = str(roadway_data[20])
        dict_data["instudy"] = conversion.convertToInt(roadway_data[21], 1)
        return dict_data
    except Exception as e:
        print_error(dict_roadway_data.__name__, Exception, e)
        return None


def dict_parking_data(parking_data):
    try:
        dict_data = dict()
        dict_data["oid"] = conversion.convertToInt(parking_data[0])
        dict_data["parking_id"] = parking_data[1]
        dict_data["height"] = conversion.convertToFloat(parking_data[2], 0.0)
        dict_data["distance"] = conversion.convertToFloat(parking_data[3], 0.0)
        dict_data["idle_time"] = conversion.convertToFloat(parking_data[4], 0.0)
        dict_data["park_time"] = conversion.convertToFloat(parking_data[5], 0.0)
        dict_data["vehicle_light"] = conversion.convertToFloat(parking_data[6], 0.0)
        dict_data["vehicle_medium"] = conversion.convertToFloat(parking_data[7], 0.0)
        dict_data["vehicle_heavy"] = conversion.convertToFloat(parking_data[8], 0.0)
        dict_data["vehicle_year"] = conversion.convertToFloat(parking_data[9], 0.0)
        dict_data["speed"] = conversion.convertToFloat(parking_data[10], 0.0)
        dict_data["hour_profile"] = parking_data[11]
        dict_data["daily_profile"] = parking_data[12]
        dict_data["month_profile"] = parking_data[13]
        dict_data["co_gm_vh"] = conversion.convertToFloat(parking_data[14], 0.0)
        dict_data["hc_gm_vh"] = conversion.convertToFloat(parking_data[15], 0.0)
        dict_data["nox_gm_vh"] = conversion.convertToFloat(parking_data[16], 0.0)
        dict_data["sox_gm_vh"] = conversion.convertToFloat(parking_data[17], 0.0)
        dict_data["pm10_gm_vh"] = conversion.convertToFloat(parking_data[18], 0.0)
        dict_data["p1_gm_vh"] = conversion.convertToFloat(parking_data[19], 0.0)
        dict_data["p2_gm_vh"] = conversion.convertToFloat(parking_data[20], 0.0)
        dict_data["method"] = parking_data[21]
        dict_data["instudy"] = conversion.convertToInt(parking_data[22], 1)
        dict_data["geometry"] = parking_data[23]
        return dict_data
    except Exception:
        return None


def dict_stationary_source(source_data):
    try:
        dict_source_data = dict()
        dict_source_data["oid"] = conversion.convertToInt(source_data[0])
        dict_source_data["source_id"] = source_data[1]
        dict_source_data["height"] = conversion.convertToFloat(source_data[2], 0.0)
        dict_source_data["category"] = source_data[3]
        dict_source_data["type"] = source_data[4]
        dict_source_data["substance"] = source_data[5]
        dict_source_data["temperature"] = conversion.convertToFloat(source_data[6], 0.0)
        dict_source_data["diameter"] = conversion.convertToFloat(source_data[7], 0.0)
        dict_source_data["velocity"] = conversion.convertToFloat(source_data[8], 0.0)
        dict_source_data["ops_year"] = conversion.convertToFloat(source_data[9], 0.0)
        dict_source_data["hour_profile"] = source_data[10]
        dict_source_data["daily_profile"] = source_data[11]
        dict_source_data["month_profile"] = source_data[12]
        dict_source_data["co_kg_k"] = conversion.convertToFloat(source_data[13], 0.0)
        dict_source_data["hc_kg_k"] = conversion.convertToFloat(source_data[14], 0.0)
        dict_source_data["nox_kg_k"] = conversion.convertToFloat(source_data[15], 0.0)
        dict_source_data["sox_kg_k"] = conversion.convertToFloat(source_data[16], 0.0)
        dict_source_data["pm10_kg_k"] = conversion.convertToFloat(source_data[17], 0.0)
        dict_source_data["p1_kg_k"] = conversion.convertToFloat(source_data[18], 0.0)
        dict_source_data["p2_kg_k"] = conversion.convertToFloat(source_data[19], 0.0)
        return dict_source_data
    except Exception:
        return None


def dict_area_source(source_data):
    try:
        dict_source_data = dict()
        dict_source_data["oid"] = conversion.convertToInt(source_data[0])
        dict_source_data["source_id"] = source_data[1]
        dict_source_data["unit_year"] = conversion.convertToFloat(source_data[2], 0.0)
        dict_source_data["height"] = conversion.convertToFloat(source_data[3], 0.0)
        dict_source_data["heat_flux"] = conversion.convertToFloat(source_data[4], 0.0)
        dict_source_data["hour_profile"] = source_data[5]
        dict_source_data["daily_profile"] = source_data[6]
        dict_source_data["month_profile"] = source_data[7]
        dict_source_data["co_kg_unit"] = conversion.convertToFloat(source_data[8], 0.0)
        dict_source_data["hc_kg_unit"] = conversion.convertToFloat(source_data[9], 0.0)
        dict_source_data["nox_kg_unit"] = conversion.convertToFloat(
            source_data[10], 0.0
        )
        dict_source_data["sox_kg_unit"] = conversion.convertToFloat(
            source_data[11], 0.0
        )
        dict_source_data["pm10_kg_unit"] = conversion.convertToFloat(
            source_data[12], 0.0
        )
        dict_source_data["p1_kg_unit"] = conversion.convertToFloat(source_data[13], 0.0)
        dict_source_data["p2_kg_unit"] = conversion.convertToFloat(source_data[14], 0.0)
        dict_source_data["instudy"] = conversion.convertToInt(source_data[15], 1)
        dict_source_data["geometry"] = source_data[16]
        return dict_source_data
    except Exception:
        return None


def dict_taxiroute_data(taxiroute_data):
    taxiroute_dict = dict()
    taxiroute_dict["oid"] = conversion.convertToInt(taxiroute_data[0])
    taxiroute_dict["gate"] = taxiroute_data[1]
    taxiroute_dict["route_name"] = taxiroute_data[2]
    taxiroute_dict["runway"] = taxiroute_data[3]
    taxiroute_dict["departure_arrival"] = taxiroute_data[4]
    taxiroute_dict["instance_id"] = taxiroute_data[5]
    taxiroute_dict["sequence"] = taxiroute_data[6]
    taxiroute_dict["groups"] = taxiroute_data[7]
    return taxiroute_dict


def dict_runway_data(runway_data):
    runway_dict = dict()
    runway_dict["oid"] = conversion.convertToInt(runway_data[0])
    runway_dict["runway_id"] = runway_data[1]
    runway_dict["capacity"] = conversion.convertToFloat(runway_data[2], 0.0)
    runway_dict["touchdown"] = conversion.convertToFloat(runway_data[3], 0.0)
    runway_dict["max_queue_speed"] = conversion.convertToFloat(runway_data[4], 0.0)
    runway_dict["peak_queue_time"] = conversion.convertToFloat(runway_data[5], 0.0)
    runway_dict["instudy"] = conversion.convertToInt(runway_data[6], 1)
    return runway_dict


def dict_movement(movement_data):
    movement_dict = dict()
    movement_dict["runway_time"] = conversion.convertStringToTime(movement_data[0])
    movement_dict["block_time"] = conversion.convertStringToTime(movement_data[1])
    movement_dict["aircraft_registration"] = str(movement_data[2])
    movement_dict["aircraft"] = str(movement_data[3])
    movement_dict["gate"] = str(movement_data[4])
    movement_dict["departure_arrival"] = str(movement_data[5])
    movement_dict["runway"] = str(movement_data[6])
    movement_dict["engine_name"] = str(movement_data[7])
    movement_dict["profile_id"] = str(movement_data[8])
    movement_dict["track_id"] = str(movement_data[9])
    movement_dict["taxi_route"] = str(movement_data[10])
    movement_dict["tow_ratio"] = float(movement_data[11]) if movement_data[11] else None
    movement_dict["apu_code"] = int(movement_data[12]) if movement_data[12] else None
    movement_dict["taxi_engine_count"] = (
        float(movement_data[13]) if movement_data[13] else None
    )
    movement_dict["set_time_of_main_engine_start_after_block_off_in_s"] = (
        float(movement_data[14]) if movement_data[14] else None
    )
    movement_dict["set_time_of_main_engine_start_before_takeoff_in_s"] = (
        float(movement_data[15]) if movement_data[15] else None
    )
    movement_dict["set_time_of_main_engine_off_after_runway_exit_in_s"] = (
        float(movement_data[16]) if movement_data[16] else None
    )
    movement_dict["engine_thrust_level_for_taxiing"] = (
        float(movement_data[17]) if movement_data[17] else None
    )
    movement_dict["taxi_fuel_ratio"] = (
        float(movement_data[18]) if movement_data[18] else None
    )
    movement_dict["number_of_stop_and_gos"] = (
        float(movement_data[19]) if movement_data[19] else None
    )
    movement_dict["domestic"] = str(movement_data[20])

    # for key_ in movement_dict:
    for key_ in [
        "runway_time",
        "block_time",
        "aircraft",
        "gate",
        "departure_arrival",
        "runway",
    ]:  # some fields are not mandatory
        if movement_dict[key_] is None:
            raise Exception(
                "Field '%s' is '%s' or empty" % (key_, str(movement_dict[key_]))
            )

    return movement_dict


def dict_mode_data(mode_data):
    mode_dict = dict()
    mode_dict["oid"] = conversion.convertToInt(mode_data[0])
    mode_dict["mode"] = mode_data[1]
    mode_dict["thrust"] = conversion.convertToFloat(mode_data[2], 0.0)
    mode_dict["description"] = mode_data[3]
    return mode_dict


def dict_gate(gate_data):
    gate_dict = dict()
    gate_dict["oid"] = conversion.convertToInt(gate_data[0])
    gate_dict["gate_id"] = gate_data[1]
    gate_dict["gate_type"] = gate_data[2]
    gate_dict["gate_height"] = conversion.convertToFloat(gate_data[3], 0.0)
    gate_dict["instudy"] = conversion.convertToInt(gate_data[4], 1)
    gate_dict["geometry"] = gate_data[5]
    return gate_dict


def dict_taxiway_data(taxiway_data):
    taxiway_dict = dict()
    taxiway_dict["oid"] = conversion.convertToInt(taxiway_data[0])
    taxiway_dict["taxiway_id"] = taxiway_data[1]
    taxiway_dict["speed"] = conversion.convertToFloat(taxiway_data[2], 0.0)
    taxiway_dict["time"] = conversion.convertToFloat(taxiway_data[3], 0.0)
    taxiway_dict["instudy"] = conversion.convertToInt(taxiway_data[4], 1)
    taxiway_dict["geometry"] = taxiway_data[5]
    return taxiway_dict


def dict_start_profile_data(start_profile_data):
    dict_start_profile = dict()
    dict_start_profile["oid"] = conversion.convertToInt(start_profile_data[0])
    dict_start_profile["aircraft_group"] = start_profile_data[1]
    dict_start_profile["aircraft_code"] = start_profile_data[2]
    dict_start_profile["emission_unit"] = start_profile_data[3]
    dict_start_profile["co"] = conversion.convertToFloat(start_profile_data[4], 0.0)
    dict_start_profile["hc"] = conversion.convertToFloat(start_profile_data[5], 0.0)
    dict_start_profile["nox"] = conversion.convertToFloat(start_profile_data[6], 0.0)
    dict_start_profile["sox"] = conversion.convertToFloat(start_profile_data[7], 0.0)
    dict_start_profile["pm10"] = conversion.convertToFloat(start_profile_data[8], 0.0)
    dict_start_profile["p1"] = conversion.convertToFloat(start_profile_data[9], 0.0)
    dict_start_profile["p2"] = conversion.convertToFloat(start_profile_data[10], 0.0)
    return dict_start_profile


def dict_aircraft(aircraft_data):
    aircraft_dict = dict()
    aircraft_dict["oid"] = conversion.convertToInt(aircraft_data[0])
    aircraft_dict["icao"] = aircraft_data[1]
    aircraft_dict["ac_group_code"] = aircraft_data[2]
    aircraft_dict["ac_group"] = aircraft_data[3]
    aircraft_dict["manufacturer"] = aircraft_data[4]
    aircraft_dict["name"] = aircraft_data[5]
    aircraft_dict["class"] = aircraft_data[6]
    aircraft_dict["mtow"] = conversion.convertToFloat(aircraft_data[7], 0.0)
    aircraft_dict["engine_count"] = conversion.convertToFloat(aircraft_data[8], 0.0)
    aircraft_dict["engine_name"] = aircraft_data[9]
    aircraft_dict["engine"] = aircraft_data[10]
    aircraft_dict["departure_profile"] = aircraft_data[11]
    aircraft_dict["arrival_profile"] = aircraft_data[12]
    aircraft_dict["bada_id"] = aircraft_data[13]
    aircraft_dict["wake_category"] = aircraft_data[14]
    aircraft_dict["apu_id"] = aircraft_data[15]
    return aircraft_dict


def dict_apu(apu_data):
    apu_dict = dict()
    apu_dict["oid"] = conversion.convertToInt(apu_data[0])
    apu_dict["apu_id"] = apu_data[1]
    apu_dict["mode"] = apu_data[2]
    apu_dict["time_a"] = apu_data[3]
    apu_dict["time_b"] = apu_data[4]
    apu_dict["fuel"] = conversion.convertToFloat(apu_data[5], 0.0)
    apu_dict["co"] = conversion.convertToFloat(apu_data[6], 0.0)
    apu_dict["hc"] = conversion.convertToFloat(apu_data[7], 0.0)
    apu_dict["nox"] = conversion.convertToFloat(apu_data[8], 0.0)
    apu_dict["sox"] = conversion.convertToFloat(apu_data[9], 0.0)
    apu_dict["pm10"] = conversion.convertToFloat(apu_data[10], 0.0)
    apu_dict["pm10_a"] = conversion.convertToFloat(apu_data[11], 0.0)
    apu_dict["pm10_b"] = conversion.convertToFloat(apu_data[12], 0.0)
    return apu_dict


def dict_engine(engine_data):
    engine_dict = dict()
    engine_dict["oid"] = conversion.convertToInt(engine_data[0])
    engine_dict["engine_type"] = engine_data[1]
    engine_dict["engine_full_name"] = engine_data[2]
    engine_dict["engine_name"] = engine_data[3]
    engine_dict["thrust"] = conversion.convertToFloat(engine_data[4], 0.0)
    engine_dict["mode"] = engine_data[5]
    engine_dict["fuel_kg_sec"] = conversion.convertToFloat(engine_data[6], 0.0)

    if engine_data[7] == "" or engine_data[7] is None:
        engine_dict["co_ei"] = 0.0
    else:
        engine_dict["co_ei"] = conversion.convertToFloat(engine_data[7], 0.0)

    if engine_data[8] == "" or engine_data[8] is None:
        engine_dict["hc_ei"] = 0.0
    else:
        engine_dict["hc_ei"] = conversion.convertToFloat(engine_data[8], 0.0)

    if engine_data[9] == "" or engine_data[9] is None:
        engine_dict["nox_ei"] = 0.0
    else:
        engine_dict["nox_ei"] = conversion.convertToFloat(engine_data[9], 0.0)

    if engine_data[10] == "" or engine_data[9] is None:
        engine_dict["sox_ei"] = 0.0
    else:
        engine_dict["sox_ei"] = conversion.convertToFloat(engine_data[10], 0.0)

    if engine_data[11] == "" or engine_data[10] is None:
        engine_dict["pm10_ei"] = 0.0
    else:
        engine_dict["pm10_ei"] = conversion.convertToFloat(engine_data[11], 0.0)

    engine_dict["p1_ei"] = conversion.convertToFloat(engine_data[12], 0.0)
    engine_dict["p2_ei"] = conversion.convertToFloat(engine_data[13], 0.0)

    engine_dict["smoke_number"] = conversion.convertToFloat(engine_data[14], 0.0)
    engine_dict["smoke_number_maximum"] = conversion.convertToFloat(
        engine_data[15], 0.0
    )
    engine_dict["fuel_type"] = engine_data[16]
    engine_dict["manufacturer"] = engine_data[17]
    engine_dict["source"] = engine_data[18]
    engine_dict["remark"] = engine_data[19]
    engine_dict["status"] = engine_data[20]
    engine_dict["engine_name_type"] = engine_data[21]
    engine_dict["coolant"] = engine_data[22]
    engine_dict["combustion_tech"] = engine_data[23]
    engine_dict["technology_age"] = engine_data[24]
    engine_dict["pm10_prefoa3"] = conversion.convertToFloat(engine_data[25], 0.0)
    engine_dict["pm10_nonvol"] = conversion.convertToFloat(engine_data[26], 0.0)
    engine_dict["pm10_sul"] = conversion.convertToFloat(engine_data[27], 0.0)
    engine_dict["pm10_organic"] = conversion.convertToFloat(engine_data[28], 0.0)
    engine_dict["nvpm_ei"] = conversion.convertToFloat(engine_data[29], 0.0)
    engine_dict["nvpm_number_ei"] = conversion.convertToFloat(engine_data[30], 0.0)

    return engine_dict


def dict_gate_profile(gate_data):
    try:
        gate_dict = dict()
        gate_dict["oid"] = conversion.convertToInt(gate_data[0])
        gate_dict["gate_type"] = gate_data[1]
        gate_dict["ac_group"] = gate_data[2]
        gate_dict["emission_type"] = gate_data[3]
        gate_dict["time_unit"] = gate_data[4]
        gate_dict["departure"] = gate_data[5]
        gate_dict["arrival"] = gate_data[6]
        gate_dict["emission_unit"] = gate_data[7]
        gate_dict["co"] = conversion.convertToFloat(gate_data[8], 0.0)
        gate_dict["hc"] = conversion.convertToFloat(gate_data[9], 0.0)
        gate_dict["nox"] = conversion.convertToFloat(gate_data[10], 0.0)
        gate_dict["sox"] = conversion.convertToFloat(gate_data[11], 0.0)
        gate_dict["pm10"] = conversion.convertToFloat(gate_data[12], 0.0)
        gate_dict["source"] = gate_data[13]
        return gate_dict
    except Exception as e:
        error = print_error(dict_gate_profile.__name__, Exception, e)
        return error


def inventory_time_series(inventory_path):
    return alaqsdblite.inventory_time_series(inventory_path)
