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
