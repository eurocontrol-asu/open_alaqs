"""
An implementation of the Tier 3 method
From EMEP/EEA air pollutant emission inventory guidebook 2019 – Update Oct. 2020
"""
import numpy as np
import pandas as pd

FUELS = ['petrol', 'diesel']
EURO_STANDARDS = ['Euro 1', 'Euro 2', 'Euro 3', 'Euro 4', 'Euro 5']
POLLUTANTS = ['CO', 'NOx', 'VOC']

VEHICLE_CATEGORIES = {
    "bus": "Buses",
    "motorcycle": "Motorcycles",
    "lcv": "Light Commercial Vehicles",
    "pc": "Passenger Cars",
    "hdt": "Heavy Duty Trucks"
}


def normalize_speed(v: float) -> int:
    """
    Get the closest decimal speed between 10 and 130 km/h.

    :param v: the speed [km/h]
    :return: the decimal speed [km/h]
    """

    # Get the available decimal speeds (min: 10, max: 130)
    vs = np.arange(10, 131, 10)

    # Return the closest decimal speed
    return vs[np.argmin(np.abs(vs - v))]


def ef_query(speed: float, country: str = 'EU27'):
    """
    Build the SQL query to get the relevant emission factors.

    :param speed: the average speed of the vehicles [km/h]
    :param country: one of the available EU countries (defaults to 'EU27')
    :return:
    """

    # Get the closest decimal speed
    normalized_speed = normalize_speed(speed)

    # Build the query
    return f"SELECT vehicle_category, fuel, euro_standard, pollutant, `hot-cold-evaporation`, evaporation_split," \
           f" `{normalized_speed}` AS `e[g/km]` FROM default_vehicle_ef_copert5 WHERE country = \'{country}\'"


def cold_mileage_fractions(trip_length: float = 12.4, temperature: float = 15) -> pd.DataFrame:
    """
    Determine the cold mileage fractions (incl. reduction factors) for each technology.

    :param trip_length: the average trip length [km]
    :param temperature: the ambient temperature [degrees Celsius]
    :return: the cold mileage fraction, beta, and the reduction factors for each pollutant [-]
    """

    # Calculate the default cold mileage fraction
    # Table 3-39: Cold mileage percentage β
    default_beta = 0.6474 - 0.02545 * trip_length - (0.00974 - 0.000385 * trip_length) * temperature
    # Method for diesel heavy-duty vehicles and buses
    beta_hdt_diesel = max(8.25 / trip_length, 1)

    # Calculate the cold mileage reduction factor
    # Table 3-43: β-reduction factors (bci,k) for Euro 6 petrol vehicles
    bc6pco = 0.1902 - 0.006 * trip_length
    bc6pnox = 0.1573 - 0.005 * trip_length
    bc6pvoc = 0.2072 - 0.0066 * trip_length
    # Table 3-46: β-reduction factors (bci,k) for Euro 6 diesel vehicles
    bc6dco = 0.2022 - 0.0064 * trip_length
    bc6dnox = 0.1719 - 0.0055 * trip_length
    bc6dvoc = 0.2398 - 0.0076 * trip_length

    # Map the fractions to each technology
    # The comments indicate the source of the β-reduction factors
    # Table 3-41: β-reduction factors (bci,k) for Euro 1 to Euro 5 petrol vehicles (relative to Euro 1)
    fractions = pd.DataFrame([
        ['pc', 'petrol', 'Conventional', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'petrol', 'Euro 1', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'petrol', 'Euro 2', default_beta, 0.72, 0.72, 0.56],  # Table 3-41
        ['pc', 'petrol', 'Euro 3', default_beta, 0.62, 0.32, 0.32],  # Table 3-41
        ['pc', 'petrol', 'Euro 4', default_beta, 0.18, 0.18, 0.18],  # Table 3-41
        ['pc', 'petrol', 'Euro 5', default_beta, 0.18, 0.18, 0.18],  # Table 3-41
        ['pc', 'petrol', 'Euro 6', default_beta, bc6pco, bc6pnox, bc6pvoc],  # Table 3-43
        ['pc', 'diesel', 'Conventional', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 1', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 2', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 3', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 4', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 5', default_beta, 1, 1, 1],  # Equation 10
        ['pc', 'diesel', 'Euro 6', default_beta, bc6dco, bc6dnox, bc6dvoc],  # Table 3-46
        ['lcv', 'petrol', 'Conventional', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'petrol', 'Euro 1', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'petrol', 'Euro 2', default_beta, 0.72, 0.72, 0.56],  # Table 3-41
        ['lcv', 'petrol', 'Euro 3', default_beta, 0.62, 0.32, 0.32],  # Table 3-41
        ['lcv', 'petrol', 'Euro 4', default_beta, 0.18, 0.18, 0.18],  # Table 3-41
        ['lcv', 'petrol', 'Euro 5', default_beta, 0.18, 0.18, 0.18],  # Table 3-41
        ['lcv', 'petrol', 'Euro 6', default_beta, bc6pco, bc6pnox, bc6pvoc],  # Table 3-43
        ['lcv', 'diesel', 'Conventional', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 1', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 2', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 3', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 4', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 5', default_beta, 1, 1, 1],  # Equation 10
        ['lcv', 'diesel', 'Euro 6', default_beta, 1, 1, 1],  # Equation 10
        ['hdt', 'petrol', 'Conventional', 0, 1, 1, 1],  # Only hot emissions
        ['hdt', 'diesel', 'Conventional', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro I', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro II', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro III', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro IV', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro V', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['hdt', 'diesel', 'Euro VI', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Conventional', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro I', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro II', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro III', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro IV', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro V', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['bus', 'diesel', 'Euro VI', beta_hdt_diesel, 1, 1, 1],  # Method for diesel heavy-duty vehicles and buses
        ['motorcycle', 'petrol', 'Conventional', 0, 1, 1, 1],  # Only hot emissions
        ['motorcycle', 'petrol', 'Euro 1', 0, 1, 1, 1],  # Only hot emissions
        ['motorcycle', 'petrol', 'Euro 2', 0, 1, 1, 1],  # Only hot emissions
        ['motorcycle', 'petrol', 'Euro 3', 0, 1, 1, 1],  # Only hot emissions
        ['motorcycle', 'petrol', 'Euro 4', 0, 1, 1, 1],  # Only hot emissions
        ['motorcycle', 'petrol', 'Euro 5', 0, 1, 1, 1],  # Only hot emissions
    ], columns=['vehicle_category', 'fuel', 'euro_standard', 'beta', 'bcCO', 'bcNOx', 'bcVOC'])

    # Add Euro 6 variations
    fractions = fractions.merge(pd.DataFrame([
        {'euro_standard': 'Euro 6', 'alternative': 'Euro 6 a/b/c'},
        {'euro_standard': 'Euro 6', 'alternative': 'Euro 6 d-temp'},
        {'euro_standard': 'Euro 6', 'alternative': 'Euro 6 d'},
        {'euro_standard': 'Euro VI', 'alternative': 'Euro VI A/B/C'},
        {'euro_standard': 'Euro VI', 'alternative': 'Euro VI D/E'},
    ]), how='outer', on='euro_standard').sort_values(['fuel', 'vehicle_category'])
    fractions.loc[~fractions['alternative'].isna(), 'euro_standard'] = \
        fractions.loc[~fractions['alternative'].isna(), 'alternative']

    return fractions.set_index(['vehicle_category', 'fuel', 'euro_standard']).drop(columns={'alternative'})


def calculate_emissions(fleet: pd.DataFrame, efs: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the emissions for each technology (a combination of vehicle category, fuel type and euro standard).

    :param fleet: The fleet mix with columns vehicle_category, fuel, euro_standard
    :param efs: The emission factors
    """

    # Input data validation
    if not fleet['vehicle_category'].isin(VEHICLE_CATEGORIES.keys()).all():
        raise ValueError(f'vehicle_category should be one of the values in {VEHICLE_CATEGORIES.keys()}')
    if not fleet['fuel'].isin(FUELS).all():
        raise ValueError(f'fuel should be one of the values in {FUELS}')
    if not fleet['euro_standard'].isin(EURO_STANDARDS).all():
        raise ValueError(f'euro_standard should be one of the values in {EURO_STANDARDS}')
    if 'N' not in fleet:
        raise ValueError('number of vehicles, N, for each technology should be provided')
    if 'M[km]' not in fleet:
        raise ValueError('mileage per vehicle [km], M, for each technology should be provided')

    # Set the technology as index
    fleet = fleet.set_index(['vehicle_category', 'fuel', 'euro_standard'])

    # Determine hot emission factors
    efs_hot = efs[efs['hot-cold-evaporation'] == 'Hot'].pivot(
        index=['vehicle_category', 'fuel', 'euro_standard'], columns='pollutant', values='e[g/km]')
    efs_hot = efs_hot[POLLUTANTS]
    efs_hot.columns = [f'e_hot{c}[g/km]' for c in efs_hot.columns]
    fleet = fleet.merge(efs_hot, how='left', left_index=True, right_index=True)

    # Add emissions (g) during stabilised (hot) engine operation
    for p in POLLUTANTS:
        fleet[f'E_hot{p}[g]'] = fleet['N'] * fleet['M[km]'] * fleet[f'e_hot{p}[g/km]']

    # Determine cold emission factors
    efs_cold = efs[efs['hot-cold-evaporation'] == 'Cold'].pivot(
        index=['vehicle_category', 'fuel', 'euro_standard'], columns='pollutant', values='e[g/km]')
    efs_cold = efs_cold[POLLUTANTS]
    efs_cold.columns = [f'e_cold{c}[g/km]' for c in efs_cold.columns]
    fleet = fleet.merge(efs_cold, how='left', left_index=True, right_index=True)

    # Determine fraction of cold mileage, beta, and beta reduction factor, bk
    beta = cold_mileage_fractions()
    fleet = fleet.merge(beta, how='left', left_index=True, right_index=True)

    # Add emissions (g) during transient thermal engine operation (cold start) if bc is known else assume 0
    for p in POLLUTANTS:
        if f'bc{p}' in fleet:
            fleet[f'E_cold{p}[g]'] = fleet[['beta', f'bc{p}', 'N', 'M[km]', f'e_cold{p}[g/km]']].product(axis=1)
        else:
            fleet[f'E_cold{p}[g]'] = 0

    # Calculate the total emissions (g)
    for p in POLLUTANTS:
        fleet[f'E{p}[g]'] = fleet[f'E_hot{p}[g]'] + fleet[f'E_cold{p}[g]']

    return fleet


def average_emission_factors(e: pd.DataFrame) -> pd.Series:
    # Determine the total emissions
    total_emissions = e[[f'E{p}[g]' for p in POLLUTANTS]].sum()

    # Determine the total mileage
    total_mileage = e[['N', 'M[km]']].product(axis=1).sum()

    # Calculate the average emission factors
    emission_factors = pd.Series({f'e{p}[g/km]': total_emissions[f'E{p}[g]'] / total_mileage for p in POLLUTANTS})

    return emission_factors
