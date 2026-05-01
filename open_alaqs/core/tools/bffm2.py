import copy
from dataclasses import dataclass

import numpy as np
from numpy import dot, empty_like

from open_alaqs.core.alaqslogging import get_logger

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
    p3t3_y_exponent: float = 0.5,
):
    """
    Calculates the emission index associated to a particular fuel flow with the
     BFFM2 method (SAE AIR-5715 / CAEP14).

    :param pollutant: str either "NOx", "CO", or "HC"
    :param fuel_flow: float, AMBIENT fuel flow at segment conditions (kg/s).
                     This must be the actual in-flight FF, NOT the EEDB reference FF.
                     Callers must convert beforehand using the CAEP14 inverse:
                         FF_amb = FF_ref * delta / theta^3.8 / exp(0.2 * M^2)
                     where FF_ref is the EEDB reference FF at the segment's
                     power setting / mode.
    :param icao_eedb: dict with fuel_flow emission index values from ICAO EEDB,
                     structured as {pollutant: {mode: {ff_ref: ei}}}
    :param ambient_conditions: dict with parameters for ambient corrections.
                     Defaults to ISA sea-level if not provided.
    :param installation_corrections: dict (mode: factor) adjusting EEDB FF
                     reference points for installation effects (default CAEP14
                     values: TO x1.010, CL x1.013, AP x1.020, Idle x1.100).
    :param p3t3_y_exponent: NOx P3T3 exponent y (0.5 for standard/LTO engines;
                     0.3 for lean-burn engines at non-LTO conditions per CAEP14
                     BFFM2 V2 update). Caller must pass 0.3 for lean-burn non-LTO.
    :return float: calculated emission index in g/kg fuel

    Formula conventions (SAE AIR-5715 / CAEP14, verified against CAEP14 v12):
      ff_ref = ff_amb / delta * theta^3.8 * exp(0.2 * M^2)
        CAEP14 applies this formula universally for both LTO and non-LTO.
        ICAO Doc 9889 App 2 uses sqrt(theta)/delta at LTO only; this code
        follows CAEP14 throughout.

      NOx humidity: h = -19 * (omega - 0.00634)
        SAE-5715 relative correction vs ISA reference-day humidity omega_0=0.00634.
        CAEP14 USER INPUTS "Humidity coefficient H" confirms this formula.

      NOx ambient: EI_NOx = EI_ref * exp(h) * (delta^1.02 / theta^3.3)^y
        y=0.5 confirmed in CAEP14 BFFM2 NOX sheet "p3t3 exponent value = 0.5".

      CO/HC ambient: EI = EI_ref * (theta^3.3 / delta^1.02)^x, x=1
        CAEP14 BFFM2 CO and HC sheets both apply this correction (x=1).

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

    installation_corrections_ = {
        "Takeoff": 1.010,  # 100%
        "Climbout": 1.013,  # 85%
        "Approach": 1.020,  # 30%
        "Idle": 1.100,  # 7%
    }
    installation_corrections_.update(installation_corrections)
    installation_corrections = installation_corrections_

    ambient_conditions_ = {
        "temperature_in_Kelvin": 288.15,  # ISA conditions
        "pressure_in_Pa": 1013.25 * 100.0,  # ISA conditions
        "relative_humidity": 0.6,  # normal day at ISA conditions
        "mach_number": 0.0,  # ground or laboratory
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

    # h = Humidity coefficient (SAE AIR-5715 relative correction vs ISA ref day omega_0=0.00634)
    # Positive h means drier than ISA reference day => higher NOx.
    # Negative h means more humid than ISA reference day => lower NOx.
    h = -19.0 * (omega - 0.00634)

    # P3T3 exponent (default value is 1.0)
    x = 1.0

    # P3T3 exponent: 0.5 for standard engines, 0.3 for lean-burn at non-LTO conditions.
    # Caller must pass p3t3_y_exponent=0.3 for lean-burn non-LTO segments.
    y = p3t3_y_exponent

    # FF_ref = Fuel flow at reference conditions (kg/s)
    # fuel_flow = Fuel flow at AMBIENT (non-reference) conditions (kg/s)
    # SAE AIR-5715 / CAEP14 formula — same for both LTO and non-LTO.
    # Note: ICAO Doc 9889 App 2 uses sqrt(theta)/delta for LTO only;
    #       CAEP14 uses theta^3.8/delta universally (verified against CAEP14 v12).
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

    # elif ikey == 'Climbout': # sets up the EI
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

    y1 = np.log10(eedb_idle_values)
    y2 = np.log10(eedb_approach_values)
    y3 = np.log10(eedb_climbout_values)
    y4 = np.log10(eedb_takeoff_values)

    # Use np.all() for element-wise comparison on numpy arrays.
    # A plain chain (y1 == y2 == y3 == y4 == 0.0) is undefined for arrays.
    if (
        np.all(y1 == 0.0)
        and np.all(y2 == 0.0)
        and np.all(y3 == 0.0)
        and np.all(y4 == 0.0)
    ):
        logger.error(
            "All input values are zero. Reference points from database"
            " for pollutant '%s':" % pollutant
        )
        logger.error(icao_eedb[pollutant])
        return 0.0

    x_ff_log = np.log10(ff_ref if ff_ref else constants.epsilon)

    # STANDARD DATA BEHAVIOR

    y_ff_log = None

    # NOx case:
    # Points in-between each pair of adjacent certification points are
    # determined through linear interpolations on the Log-Log scales
    if pollutant.lower() == "nox":
        if x_ff_log < x1:
            y_ff_log = y1  # Cap the y value of the point to be the same as the first point (ID)

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
            y_ff_log = (
                y4  # Cap the y value of the point to be the same as the last point (TO)
            )

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
            y_ff_log = y1  # Before ID stay on the same y level as the first point

        elif x1 <= x_ff_log <= x2:
            y_ff_log = np.interp(
                x_ff_log, np.concatenate([x1, x2]), np.concatenate([y1, y2])
            )

        elif x2 <= x_ff_log <= x3:
            if data_behavior == 1:  # standard
                # CAEP14 v14 / SAE AIR-5715 "HC_CO Slope To Mean Value" rule for the
                # standard-intersection case (intersection of the IDLE-APP slanting line
                # and the (CL, TO)-mean horizontal line falls inside the [APP, CL] FF
                # range).  In this case the CAEP procedure snaps the EI to the
                # horizontal value (mean of CL and TO anchor EIs) for ANY FF above the
                # APP anchor, producing a step discontinuity at the APP boundary.
                # Physically this reflects that CO/HC reach their combustion-complete
                # floor almost immediately past approach thrust.
                #
                # The previous implementation kept the slanting line up to the
                # intersection and only snapped beyond.  That smoothed the step but
                # disagreed with the CAEP14 reference sheet by up to a factor of 8 at
                # borderline cases (e.g. warm-humid APP-anchor segments).
                y_ff_log = lin_av
            elif data_behavior == 2:  # non-standard: log-linear APP→horizontal
                # When the SL/HL intersection falls outside [APP, CL] the CAEP
                # procedure draws a log-linear line from (APP_FF, APP_EI) to
                # (CL_FF, horizontal) and reads off the segment FF on it.
                y_ff_log = np.interp(
                    x_ff_log, np.concatenate([x2, x3]), np.concatenate([y2, lin_av])
                )

        else:  # x_ff_log > x3 (region includes CL-TO and above-TO)
            y_ff_log = lin_av  # stay on the mean horizontal line, beyond TO as well
    else:
        logger.error(f"Pollutant '{pollutant}' unknown.")

    if y_ff_log is None or np.isnan(y_ff_log):
        y_ff_log = np.log10(constants.epsilon)

    # Ensure y_ff_log is a plain Python float so downstream arithmetic works
    # regardless of whether it came from np.interp, np.log10, or a scalar.
    y_ff_log = float(np.asarray(y_ff_log).flat[0])

    ############################################################################
    #   3. Calculate EI
    ############################################################################

    if pollutant.lower() == "nox":
        # ein_x_ref = NOx EI at reference conditions (g/kg)
        ein_ox_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = NOx EI at non-reference conditions (g/kg)
        # SAE AIR-5715 / CAEP14: exp(h) x (delta^1.02 / theta^3.3)^y
        #   h = -19*(omega - 0.00634)  relative humidity correction vs ISA ref day
        #   y = 0.5 for standard/LTO (CAEP14 BFFM2 NOX p3t3 exponent = 0.5)
        ei = ein_ox_ref * np.exp(h) * (delta**1.02 / theta**3.3) ** y

    elif pollutant.lower() == "co":

        # ei_co_ref = CO EI at reference conditions (g/kg)
        ei_co_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = CO EI at non-reference conditions (g/kg)
        # SAE AIR-5715 / CAEP14: (theta^3.3 / delta^1.02)^x, x=1
        # CAEP14 BFFM2 CO sheet applies this correction (verified: factor = 0.8824 at test segment).
        ei = ei_co_ref * (theta**3.3 / delta**1.02) ** x

    elif pollutant.lower() == "hc":

        # ei_hc_ref = THC EI at reference conditions (g/kg)
        ei_hc_ref = 10**y_ff_log if 10 ** (y_ff_log) > constants.epsilon else 0.0

        # ei = THC EI at non-reference conditions (g/kg)
        # Same ambient correction as CO: (theta^3.3 / delta^1.02)^x, x=1
        ei = float(ei_hc_ref) * (theta**3.3 / delta**1.02) ** x

    else:
        logger.error(f"Pollutant '{pollutant}' unknown.")

    # Emission index in g/kg
    emission_index = ei[0] if (isinstance(ei, np.ndarray) and ei.size == 1) else ei

    return emission_index
