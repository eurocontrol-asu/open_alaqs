from open_alaqs.core.tools.twin_quadratic_fit_method import (
    calculate_fuel_flow_from_power_setting,
)


def test_example_calculation_1():
    """
    Example calculation for UID 8RR044, Rolls-Royce Trent 553-61
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020
    """

    # ICAO EEDB fuel flow data
    eedb = {
        1.0: 2.11,  # Takeoff
        0.85: 1.73,  # Climbout
        0.30: 0.6,  # Approach
        0.07: 0.23,  # Idle
    }

    # Case 1: thrust setting of 70 percent
    thrust_setting_1 = 0.7

    # Calculate the fuel flow
    fuel_flow_1 = calculate_fuel_flow_from_power_setting(thrust_setting_1, eedb)

    # Set the reference fuel flow
    fuel_flow_1_ref = 1.388  # kg/s

    assert round(fuel_flow_1, 3) == fuel_flow_1_ref


def test_example_calculation_2():
    """
    Example calculation for UID 8RR044, Rolls-Royce Trent 553-61
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020
    """

    # ICAO EEDB fuel flow data
    eedb = {
        1.0: 2.11,  # Takeoff
        0.85: 1.73,  # Climbout
        0.30: 0.6,  # Approach
        0.07: 0.23,  # Idle
    }

    # Case 2: thrust setting of 90 percent
    thrust_setting_2 = 0.9

    # Calculate the fuel flow
    fuel_flow_2 = calculate_fuel_flow_from_power_setting(thrust_setting_2, eedb)

    # Case 2
    fuel_flow_2_ref = 1.853  # kg/s

    assert round(fuel_flow_2, 3) == fuel_flow_2_ref
