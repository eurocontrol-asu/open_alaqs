from open_alaqs.alaqs_core.alaqslogging import get_logger

logger = get_logger(__name__)


def calculate_fuel_flow_from_power_setting(power_setting, icao_eedb):
    """
    Calculates the fuel flow associated to a particular power setting with the
     twin-quadratic fit method

    :param power_setting: float in interval [0.,1.]
    :param icao_eedb: dict with power:fuel flow values from ICAO Emissions
    :return float: calculated fuel flow in kg/s
    """

    for key in [0.07, 0.30, 0.85, 1.0]:
        if key not in icao_eedb:
            logger.error(
                "Did not find key %f with type 'float' in engine-thrust "
                "settings [%%] from ICAO EEDB!", key)
            return None

    if .07 <= power_setting <= .85:
        # based on the 7 per cent, 30 per cent and 85 per cent thrust
        x1 = 0.07
        x2 = 0.30
        x3 = 0.85

    elif .85 < power_setting <= 1.00:
        # based on the 30 per cent, 85 per cent and 100 per cent thrust
        x1 = 0.30
        x2 = 0.85
        x3 = 1.0
    else:
        raise ValueError('The power setting should be between 0.6 and 1.0 '
                         '(inclusive).')

    # Y = AX**2 + BX + C
    # with three known points:
    # Y1=AX1**2 +BX1+C, Y2=AX2**2 +BX2+C, Y3=AX3**2 +BX3+C
    # icao_eedb keys (X) = (thrust)/(maximum rated thrust),
    # quadratic defined by values X1, X2, X3, X4;
    # icao_eedb value pairs (Y) = fuel flow /(fuel flow @ maximum rated thrust),
    # values Y1, Y2, Y3, Y4.

    _x = power_setting

    y1 = icao_eedb[x1] / icao_eedb[1]
    y2 = icao_eedb[x2] / icao_eedb[1]
    y3 = icao_eedb[x3] / icao_eedb[1]

    # Allowing solution for A, B and C as:
    a = (y3 - y1) / ((x3 - x1) * (x1 - x2)) - (y3 - y2) / (
            (x3 - x2) * (x1 - x2))
    b = (y3 - y1) / (x3 - x1) - a * (x3 + x1)
    c = y3 - a * x3 ** 2 - b * x3

    _y = a * _x ** 2 + b * _x + c

    # multiply by ICAO EEDB maximum rated thrust fuel
    max_rated_t = icao_eedb[1.0]

    fuel_flow_in_kg_s = _y * max_rated_t  # in kg/s

    return max(0., fuel_flow_in_kg_s)


# if __name__ == "__main__":
#     # create a logger for this module
#     logger.setLevel(logging.DEBUG)
#     # create console handler and set level to debug
#     ch = logging.StreamHandler()
#     ch.setLevel(logging.DEBUG)
#     # create formatter
#     formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # add formatter to ch
#     ch.setFormatter(formatter)
#     # add ch to logger
#     logger.addHandler(ch)
#
#     # Example calculation for power setting at xx % (0.xx) thrust level
#     power = 0.05
#
#     # Example calculation for UID 1CM004, CFM56-3-B1
#     icao_values = {
#         1.: 0.946,  # Takeoff
#         0.85: 0.792,  # Climbout
#         0.30: 0.29,  # Approach
#         0.07: 0.114  # Idle
#     }
#
#     # # Example calculation for UID 8RR044, Rolls-Royce Trent 553-61
#     # icao_values = {
#     #         1.:2.11, #Takeoff
#     #         0.85:1.73, #Climbout
#     #         0.30:0.6, #Approach
#     #         0.07:0.23 #Idle
#     #     }
#
#     logger.info("Calculated fuel flow for power setting '%.2f' is '%.4f'", (
#         power, calculate_fuel_flow_from_power_setting(power, icao_values)))
#
#     # Plot function
#     import numpy as np
#     import matplotlib.pyplot as plt
#
#     plt.ion()
#     plt.figure()
#     x = np.linspace(0, 1, 1000)  # 1000 linearly spaced numbers
#     for i in x:
#         y = calculate_fuel_flow_from_power_setting(i, icao_values)
#         p1, = plt.plot(100 * i, y, 'ok', ms=4)
#     p2, = plt.plot(100 * np.array([0.07, 0.3, 0.85, 1]),
#                    [icao_values[0.07], icao_values[0.3], icao_values[0.85],
#                     icao_values[1]], 'rx', ms=10, mew=5)
#     plt.legend([p1, p2], ["Twin Quadratic Curve Fit", "ICAO EEDB Data"],
#                numpoints=1, loc=2)
#     plt.xlabel('Power setting (%)')
#     plt.ylabel('Fuel flow [kg/s]')
#     plt.title('Twin Quadratic curve fit')
