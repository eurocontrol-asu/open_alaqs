import copy
from dataclasses import dataclass

import numpy as np
from numpy import dot, empty_like

from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


@dataclass(init=False, frozen=True)
class _Constants:
    """
    An immutable dataclass for constants

    """

    epsilon: float = 1e-4


constants = _Constants()


def perp(a):
    b = empty_like(a)
    b[0] = -a[1]
    b[1] = a[0]
    return b


def seg_intersect(a1, a2, b1, b2):
    np.seterr(divide="ignore", invalid="ignore")

    da = a2 - a1
    db = b2 - b1
    dp = a1 - b1
    dap = perp(da)
    denom = dot(dap, db)
    num = dot(dap, dp)

    return (num / denom) * db + b1


def calculate_emission_index(  # noqa: C901
    pollutant,
    fuel_flow,
    icao_eedb,
    ambient_conditions=None,
    installation_corrections=None,
):
    """
    Calculates the emission index associated to a particular fuel flow with the
     BFFM2 method.

    :param pollutant: str either "NOx", "CO", or "HC"
    :param fuel_flow: float in units kg/s
    :param icao_eedb: dict with fuel_flow emission index values from ICAO
     Emissions
    :param ambient_conditions: dict with parameters to correct for ambient
     conditions, default is ISA
    :param installation_corrections: dict (mode: factor) with adjustment factors
     for installation effects
    :return float: calculated fuel flow in kg/s

    An issue concerns the modeling of zero values from the certification data,
     especially concerning EITHC values.
    Since zero values cannot be converted to Logs, a substitution to a small
     value is recommended.
    For the 85% and 100% power points or if all power point EIs are zero, any
     value < 10-4 should suffice.
    If the 7% power point is non-zero and the 30% power point is zero, then
     values < 10-3 may result in excessive extrapolation below the 7% power
     setting.
    These solutions are reasonable since the zero values in the ICAO data
     likely represents small values that were rounded to zero as opposed to
     actually implying zero emissions.
    """

    # Adjustment factors for installation effects (in not explicitly specified):
    # Mode       Power Setting (%)    Adjustment Factor
    # Takeoff        100                 1.010
    # Climbout       85                  1.013
    # Approach       30                  1.020
    # Idle           7                   1.100
    if installation_corrections is None:
        installation_corrections = {}
    if ambient_conditions is None:
        ambient_conditions = {}
    icao_eedb = copy.deepcopy(icao_eedb)

    # installation_corrections_ = {
    #     "Takeoff":1.0,    # 100%
    #     "Climbout":1.0,   # 85%
    #     "Approach":1.0,   # 30%
    #     "Idle":1.0        # 7%
    # }

    installation_corrections_ = {
        "Takeoff": 1.010,  # 100%
        "Climbout": 1.012,  # 85%
        "Approach": 1.020,  # 30%
        "Idle": 1.100,  # 7%
    }
    installation_corrections_.update(installation_corrections)
    installation_corrections = installation_corrections_

    ambient_conditions_ = {
        "temperature_in_Kelvin": 288.15,  # ISA conditions
        "pressure_in_Pa": 1013.25 * 100.0,  # ISA conditions
        "relative_humidity": 0.6,  # normal day at ISA conditions
        "mach_number": 0.0  # ground or laboratory
        # "humidity_ratio_in_kg_water_per_kg_dry_air": 0.00634 #ISA default
    }

    ambient_conditions_.update(ambient_conditions)
    ambient_conditions = ambient_conditions_

    # some sanity checks
    fuel_flow = max(0.0, fuel_flow)

    for key_ in list(installation_corrections.keys()):
        for p_ in icao_eedb:
            if key_ not in icao_eedb[p_]:
                logger.error(f"Did not find mandatory key '{key_}' in ICAO EEDB.")

    for p_ in icao_eedb:
        if not len(list(icao_eedb[p_].keys())) == 4:
            keys_should = ", ".join(list(installation_corrections.keys()))
            keys_are = ", ".join(list(icao_eedb[pollutant].keys()))

            logger.error(
                "Found not exactly four points in values provided for "
                f"ICAO EEDB. Keys should be '{keys_should}', but are "
                f"'{keys_are}'."
            )

    # 1. Multiply FF ref values with the above (default) adjustment factors if
    # not any other factors are passed into the function
    for ikey in icao_eedb[pollutant].keys():
        for ik, _ in list(icao_eedb[pollutant][ikey].items()):
            icao_eedb[pollutant][ikey][ik * installation_corrections[ikey]] = icao_eedb[
                pollutant
            ][ikey].pop(ik)

    # t_a = Ambient temperature (K)
    t_a = ambient_conditions["temperature_in_Kelvin"]

    # t_ac = Ambient temperature (°C)
    t_ac = t_a - 273.15

    # p_a = Ambient pressure (kPa)
    p_a = ambient_conditions["pressure_in_Pa"]

    # p_psia = Ambient pressure (psia) with 1 kPa = 0.14504 psia
    p_psia = p_a * 0.14504 * 1e-3

    # rh = Relative humidity
    rh = ambient_conditions["relative_humidity"]

    # m = Mach number
    m = ambient_conditions["mach_number"]

    omega = ambient_conditions.get("humidity_ratio_in_kg_water_per_kg_dry_air", None)

    # p_sat = Saturation vapor pressure (mbar)
    # t_ac in ° Celsius (C = K-273.15) !!
    p_sat = 6.107 * 10 ** ((7.5 * t_ac) / (237.3 + t_ac))

    # theta = Temperature ratio (ambient to sea level)
    theta = t_a / 288.15

    # delta = Pressure ratio (ambient to sea level)
    delta = p_a / float(101325)
    if delta < 0.001:
        logger.debug(
            f"delta (Pressure ratio) is unnatural: {delta:.3f}. "
            f"Pressure should be in Pa"
        )

    # omega = Humidity ratio (kg H2O/kg of dry air)
    if omega is None:
        omega = (0.62197058 * rh * p_sat) / (p_psia * 68.9473 - rh * p_sat)

    # h = Humidity coefficient
    h = -19.0 * (omega - 0.00634)

    # P3T3 exponent (default value is 1.0)
    x = 1.0

    # P3T3 exponent (default value is 0.5)
    y = 0.5

    # FF_ref = Fuel flow at reference conditions (kg/s)
    # fuel_flow = Fuel flow at non-reference conditions (kg/s)
    ff_ref = (fuel_flow / delta) * (theta**3.8) * np.exp(0.2 * m**2)

    ############################################################################
    # 2. Develop Log-Log relationship between EI_ref and adjusted FF_ref values
    ############################################################################

    # Modeling of zero values from the certification data (especially concerning
    #  EITHC values): Since zero values cannot be converted to Logs, a
    #  substitution to a small value is recommended.

    eedb_idle = icao_eedb[pollutant]["Idle"]
    eedb_approach = icao_eedb[pollutant]["Approach"]
    eedb_climbout = icao_eedb[pollutant]["Climbout"]
    eedb_takeoff = icao_eedb[pollutant]["Takeoff"]

    # if ikey == 'Idle':
    idle_check = 1
    for ik, _ in list(eedb_idle.items()):
        if eedb_idle[ik] == 0:
            idle_check = 0
            eedb_idle[ik] = constants.epsilon * 10

    # elif ikey == 'Approach':
    for ik, _ in list(eedb_approach.items()):
        if eedb_approach[ik] == 0 and idle_check > 0:
            eedb_approach[ik] = constants.epsilon * 10
        elif eedb_approach[ik] == 0 and idle_check == 0:
            eedb_approach[ik] = constants.epsilon

    # For the 85 and 100 power points or if all power point EIs are zero, any
    #  value <= 10-4 should suffice.

    # elif ikey == 'Climbout':
    for ik, _ in list(eedb_climbout.items()):
        if eedb_climbout[ik] == 0:
            eedb_climbout[ik] = constants.epsilon

    # elif ikey == 'Takeoff':
    for ik, _ in list(eedb_takeoff.items()):
        if eedb_takeoff[ik] == 0:
            eedb_takeoff[ik] = constants.epsilon

    # These solutions are reasonable since the zero values in the ICAO data
    # likely represents small values that were rounded to zero as opposed to
    # actually implying zero emissions.
    x1 = np.log10(list(eedb_idle.keys()))
    x2 = np.log10(list(eedb_approach.keys()))
    x3 = np.log10(list(eedb_climbout.keys()))
    x4 = np.log10(list(eedb_takeoff.keys()))

    eedb_idle_values = list(eedb_idle.values())
    eedb_approach_values = list(eedb_approach.values())
    eedb_climbout_values = list(eedb_climbout.values())
    eedb_takeoff_values = list(eedb_takeoff.values())

    y1 = 0.0 if eedb_idle_values == [0.0] else np.log10(eedb_idle_values)
    y2 = 0.0 if eedb_approach_values == [0.0] else np.log10(eedb_approach_values)
    y3 = 0.0 if eedb_climbout_values == [0.0] else np.log10(eedb_climbout_values)
    y4 = 0.0 if eedb_takeoff_values == [0.0] else np.log10(eedb_takeoff_values)

    if y1 == y2 == y3 == y4 == 0.0:
        logger.error(
            "All input values are zero. Reference points from database"
            " for pollutant '%s':" % pollutant
        )
        logger.error(icao_eedb[pollutant])
        return 0.0

    x_ff_log = np.log10(ff_ref if ff_ref else constants.epsilon)

    # First (7-30%) line equation (y=ax+b)
    coef_a1 = (y2 - y1) / (x2 - x1)
    coef_b1 = y2 - coef_a1 * x2

    # STANDARD DATA BEHAVIOR

    y_ff_log = None

    # NOx case:
    # Points in-between each pair of adjacent certification points are
    # determined through linear interpolations on the Log-Log scales
    if pollutant.lower() == "nox":
        if x_ff_log < x1:
            y_ff_log = coef_a1 * x_ff_log + coef_b1

        elif x1 <= x_ff_log <= x2:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x1, x2]), np.concatenate([y1, y2])
            )

        elif x2 < x_ff_log <= x3:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x2, x3]), np.concatenate([y2, y3])
            )

        elif x3 < x_ff_log <= x4:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x3, x4]), np.concatenate([y3, y4])
            )

        elif x_ff_log > x4:
            # First (>100%) line equation (y=ax+b)
            coef_a100 = (y4 - y3) / (x4 - x3)
            coef_b100 = y4 - coef_a100 * x4
            y_ff_log = coef_a100 * x_ff_log + coef_b100

    elif pollutant.lower() == "co" or pollutant.lower() == "hc":
        # linear avg of y3,y4
        lin_av = np.log10(
            1
            / 2.0
            * (np.asarray(eedb_climbout_values) + np.asarray(eedb_takeoff_values))
        )

        # Calculate the intersection between the two lines
        a = np.concatenate([x1, y1])
        b = np.concatenate([x2, y2])
        c = np.concatenate([x3, lin_av])
        d = np.concatenate([x4, lin_av])

        ip = seg_intersect(a, b, c, d)

        # Define Standard or non-standard behaviour
        data_behavior = 1  # Standard
        if ip[0] > min([x3, x4]) or ip[0] < max([x1, x2]):
            data_behavior = 2  # Non-Standard

        if x_ff_log < x1:
            coef_a = (y2 - y1) / (x2 - x1)
            coef_b = y2 - coef_a * x2
            y_ff_log = coef_a * x_ff_log + coef_b

        elif x1 <= x_ff_log <= x2:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x1, x2]), np.concatenate([y1, y2])
            )

        elif x2 <= x_ff_log <= x3:
            if data_behavior == 1:
                if x2 < x_ff_log <= ip[0]:
                    coef_a = (ip[1] - y2) / (ip[0] - x2)
                    coef_b = y2 - coef_a * x2
                    y_ff_log = coef_a * x_ff_log + coef_b
                elif ip[0] < x_ff_log <= x3:
                    coef_a = (ip[1] - y3) / (ip[0] - x3)
                    coef_b = y3 - coef_a * x3
                    y_ff_log = coef_a * x_ff_log + coef_b

            elif data_behavior == 2:
                y_ff_log = np.interp(
                    x_ff_log, np.concatenate([x2, x3]), np.concatenate([y2, lin_av])
                )

        elif x3 < x_ff_log <= x4:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x3, x4]), np.concatenate([y3, y4])
            )

        elif x_ff_log > x4:
            coef_a = (ip[1] - lin_av) / (ip[0] - x4)
            coef_b = ip[1] - coef_a * ip[0]
            y_ff_log = coef_a * x_ff_log + coef_b
    else:
        logger.error(f"Pollutant '{pollutant}' unknown.")

    if y_ff_log is None or np.isnan(y_ff_log):
        y_ff_log = np.log10(constants.epsilon)

    ############################################################################
    #   3. Calculate EI
    ############################################################################

    if pollutant.lower() == "nox":
        # ein_x_ref = NOx EI at reference conditions (g/kg)
        ein_ox_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = NOx EI at non-reference conditions (g/kg)
        ei = ein_ox_ref * np.exp(h) * (delta**1.02 / theta**3.3) ** y

    elif pollutant.lower() == "co":

        # ei_co_ref = CO EI at reference conditions (g/kg)
        ei_co_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = CO EI at non-reference conditions (g/kg)
        ei = ei_co_ref * (theta**3.3 / delta**1.02) ** x

    elif pollutant.lower() == "hc":

        # ei_hc_ref = THC EI at reference conditions (g/kg)
        ei_hc_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = THC EI at non-reference conditions (g/kg)
        ei = float(ei_hc_ref) * (theta**3.3 / delta**1.02) ** x

    else:
        logger.error(f"Pollutant '{pollutant}' unknown.")

    # Emission index in kg/s
    emission_index = ei[0] if (isinstance(ei, np.ndarray) and ei.size == 1) else ei

    return emission_index


# if __name__ == "__main__":
#     # create a logger for this module
#     # logger.setLevel(logging.DEBUG)
#     # # create console handler and set level to debug
#     # ch = logging.StreamHandler()
#     # ch.setLevel(logging.DEBUG)
#     # # create formatter
#     # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # # add formatter to ch
#     # ch.setFormatter(formatter)
#     # # add ch to logger
#     # logger.addHandler(ch)
#
#     # Input conditions for this example are:
#     pollutant = "NOx"
#
#     # # Example: These values correspond to a cruise point or segment of a flight trajectory using the Trent 892 engine with an ICAO UID of 2RR027
#     # # For each pollutant, the reference FF (non-adjusted) and EI are given
#
#     # Engine	1CM008 (CFM56-5-A1)
#     # Engine fuel flow rate (in kg/s at reference conditions)
#     # fuel_flow = 0.882 # Engine fuel flow rate = 0.882 # in kg/s (or 7000 lb/hr/engine)
#     fuel_flow = 0.319894549
#     ff_to = 1.051
#     ff_co = 0.862
#     ff_app = 0.291
#     ff_idle = 0.1011
#
#     icao_values = {
#         'CO': OrderedDict({'Idle': {ff_idle: 17.6}, 'Approach': {ff_app: 2.5}, 'Climbout': {ff_co: 0.9}, 'Takeoff': {ff_to: 0.9}}),
#         'NOx': OrderedDict({'Idle': {ff_idle: 4.0}, 'Approach': {ff_app: 8.0}, 'Climbout': {ff_co: 19.6}, 'Takeoff': {ff_to: 24.6}}),
#         'HC': OrderedDict({'Idle': {ff_idle: 1.4}, 'Approach': {ff_app: 0.4}, 'Climbout': {ff_co: 0.23}, 'Takeoff': {ff_to: 0.23}})
#     }
#
#     # Altitude = 39000 # in ft
#     # Standard day (ISA conditions)
#     ambient_conditions = {
#     "temperature_in_Kelvin":288.15, #ISA conditions
#     "pressure_in_Pa":1013.25*100., #ISA conditions
#     "relative_humidity":0.6, #normal day at ISA conditions
#     "mach_number":0.779999728 #ground or laboratory
#     # "humidity_ratio_in_kg_water_per_kg_dry_air":0.00634 #ISA default
#     }
#
#     # ambient_conditions = {
#     #         "temperature_in_Kelvin":216.65,
#     #         "pressure_in_Pa":19677,
#     #         "mach_number":0.84,
#     #         "relative_humidity":0.60,
#     #         #either relative humidity or absolute humidity ratio has to be defined
#     #         # "humidity_ratio_in_kg_water_per_kg_dry_air":0.000053
#     #     }
#
#     # ambient_conditions = {}
#
#     installation_corrections = {
#             "Takeoff":1.010,    # 100%
#             "Climbout":1.013,   # 85%
#             "Approach":1.020,   # 30%
#             "Idle":1.100        # 7%
#         }
#
#     #Don't correct for installation
#     # installation_corrections = {}
#
#     #logger.info("Calculated emission index '%s' for fuel flow '%.2f' is '%.2f'" % (pollutant, fuel_flow, calculate_emission_index(pollutant, fuel_flow, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections)))
#
#     # fix_print_with_import
#     print(calculate_emission_index(pollutant, fuel_flow, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections))
#
#     plotEmissionIndex(pollutant, icao_values)
#     plotEmissionIndexNominal(pollutant, icao_values, ambient_conditions=ambient_conditions, installation_corrections=installation_corrections, range_relative_fuelflow=[1.00, 1.0], steps=51, suffix="")
