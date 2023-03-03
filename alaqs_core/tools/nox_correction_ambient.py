from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


# A correction factor for ambient pressure is not required except that the temperature is based on the ISA standard day temperature
# for the ambient pressure altitude for the airport. 
# A separate correction for forward speed is not applied because the effects of the forward air speed are taken into account in the calculation of the other factors.

# In cases where meteorological data is missing for some time interval the meteorological correction will not be applied for those time intervals. 

# The NOx correction is applied after the NOx emissions for take-off and climb-out have been calculated with the simple method. 
# The correction factor is stored in a separate field in the inventory combined emission events table (tbl_InvEmisEvent, f4 field)
def nox_correction_for_ambient_conditions(init_nox_ei, elevation, tow_ratio,
                                          ac=None):
    """
    ICCAIA recommends that simple models for NOx produced by take-off and climb-out to 3000 ft above ground level 
    can be improved by applying a correction for: (i) aircraft weight (ii), ambient temperature & (iii) ambient humidity.
    The correction is only applied to take-off and climb-out emissions if the user has selected the "Apply NOx correction" 
    option and meteorological data is available for the inventory period. 
    It is not possible to select both the "Apply Fuel Flow method" and the "Apply NOx correction" options because this would result in a double NOx correction.
    """

    if ac is None:
        ac = {}
    import numpy as np
    # INPUT PARAMETERS: TEMP_actual,RH, APT_elev, NOX_orig, TOG_ratio

    # tow_ratio: The ratio of the actual TOGW to the maximum TOGW which is certified for that aircraft type and engine rating combination.
    # TOGW: takeoff gross weight, the TOGW ratio is an optional field in the movements table (tow_ratio) it should always be smaller or equal to one.
    # The weight correction will only be applied if the take-off gross weight ratio (TOG_ratio) is specified in the movements table (tow_ratio field).

    # T_a = Ambient temperature (K)
    try:
        T_a = ac.getTemperature()
    except Exception as e:
        T_a = 288.15 #ISA conditions
        logger.info("Error reading Temperature. Will take ISA value '%s'"%e)
    TEMP_actual = T_a # Ambient temperature (in Kelvin)

    # P_a = Ambient pressure (Pa)
    try:
        P_a = ac.getPressure()
    except Exception as e:
        P_a = 1013.25*100. #ISA conditions
        logger.info("Error reading Pressure. Will take ISA value '%s'"%e)
    P_psia = P_a * 1e-3 * 0.14504   # 1 kPa = 0.14504 psia    # P_psia = Ambient pressure (psia)

    # RH = Relative humidity
    try:
        RH = ac.getRelativeHumidity()
    except Exception as e:
        RH = 0.6 # normal day at ISA conditions
        logger.info("Error reading Relative Humidity. Will take ISA value '%s'"%e)

    # ISA: At mean sea level (msl), the pressure = 1013.25 hPa and temperature = 15.0 degC, From msl to 11 km, a decrease in temperature (or lapse rate) of 6.5 degC/km
    TEMP_isa = 273.15 + 15 + (float(elevation)/1000)*(-6.5)   # air_alt or APT_elev : Airport elevation above sea level in metres

    # TEMP_actual - TEMP_isa: The difference (in degrees C) between the ambient temperature at the airport and the ISA standard day temperature
    # for the pressure altitude which corresponds to the ambient pressure at the airport.

    # P_sat: saturated vapour pressure (in hPa)
    P_sat =  6.1078*10**( (7.5*(TEMP_actual - 273.15)) / (237.3 + (TEMP_actual - 273.15)) ) # in hPa (or mbar),  TEMP: The ambient temperature (degrees K)

    # h: The ambient humidity ratio (kg water per kg of dry air):
    h = (0.62197058 * RH * P_sat) / ( (P_psia * 68.9473) - (RH * P_sat))

    # Correction factor: This formula does not take into account any effect due to thrust reduction, either during takeoff or climbout.
    # init_nox_ei: NOx predicted by simple method for takeoff and climbout (not total LTO), created from brake release to 3000 feet agl and assumes 60% relative humidity,
    if init_nox_ei[1] != "g":
        logger.warning("NOx Correction: NOx EI is not in g, check units '%s' !"%[init_nox_ei])
    nox_ei = float(init_nox_ei[0])
    NOx_corrected = np.asarray(nox_ei) * (1 + 1.55*(tow_ratio - 1) + 0.012*(TEMP_actual - TEMP_isa) ) * np.exp( 19.0*(0.00634-h) )

    return round(NOx_corrected, 5)

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
#     ambient_conditions_ = {
#         "temperature_in_Kelvin":288.15, #ISA conditions
#         "pressure_in_Pa":1013.25*100., #ISA conditions
#         "relative_humidity":0.6, #normal day at ISA conditions
#         # "mach_number":0.20, #ground or laboratory
#         # "humidity_ratio_in_kg_water_per_kg_dry_air":0.00634 #ISA default
#     }
#
#     # ambient_conditions = {
#     #         "temperature_in_Kelvin":288.65,
#     #         "pressure_in_Pa":19677,
#     #         "mach_number":0.84,
#     #         "relative_humidity":0.60,
#     #
#     #         #either relative humidity or absolute humidity ratio has to be defined
#     #         # "humidity_ratio_in_kg_water_per_kg_dry_air":0.000053
#     #     }
#
#     airport_elevation = 10 # Airport elevation above sea level in metres
#     #Less NOx is produced during takeoffs from higher altitude airports (0.5-1.0% per 1000 feet ~ 300m)
#
#     tow = 1
#     # NOx varies ~1.5% for every 1% of TOGW
#
#     icao_values = {
#         "NOx":{
#             "Takeoff":{3.91:45.7},
#             "Climbout":{3.10:33.3},
#             "Approach":{1.00:11.58},
#             "Idle":{0.30:5.33},
#         },
#         "CO":{
#             "Takeoff":{3.91:0.28},
#             "Climbout":{3.10:0.2},
#             "Approach":{1.00:0.57},
#             "Idle":{0.30:13.07},
#         },
#         "HC":{
#             "Takeoff":{3.91:0.01},
#             "Climbout":{3.10:0},
#             "Approach":{1.00:0},
#             "Idle":{0.30:0.7},
#         }
#     }
#
#     import numpy as np
#
#     NOx_init = list(icao_values['NOx']['Takeoff'].values())
#     # fix_print_with_import
#     print("NOx EI is '%.3f'"%(np.asarray(NOx_init)))
#     # fix_print_with_import
#     print("NOx correction for_ambient conditions is '%.3f'" % nox_correction_for_ambient_conditions(NOx_init, airport_elevation, tow, ac=ambient_conditions_))
#
#     # for ik, ival in icao_values['NOx']['Takeoff'].items():
#     #     NOX_orig = icao_values['NOx']['Takeoff'][ik]
#     #     print "NOX_orig :%s"%NOX_orig
#     #     icao_values['NOx']['Takeoff'][ik] = nox_correction_for_ambient_conditions(NOX_orig, airport_elevation, ac=ambient_conditions_, tow_ratio=tow_ratio)
#     #     print "icao_values['NOx']['Takeoff'] :%s"%icao_values['NOx']['Takeoff'][ik]
#     #
#     # for ik, ival in icao_values['NOx']['Climbout'].items():
#     #     NOX_orig = icao_values['NOx']['Climbout'][ik]
#     #     icao_values['NOx']['Climbout'][ik] = nox_correction_for_ambient_conditions(NOX_orig, airport_elevation, ac=ambient_conditions_, tow_ratio=tow_ratio)
#     #
#
#     # logger.info("NOx correction for_ambient onditions is '%.3f'" % nox_correction_for_ambient_conditions(NOX_orig,airport_altitude,ambient_conditions))
#