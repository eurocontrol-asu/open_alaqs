from pathlib import Path
import pandas as pd
import pytest

from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import \
    SCALING_FACTORS, AIR_FUEL_RATIO
from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import \
    calculate_smoke_number, calculate_nvpm_mass_concentration_ck, \
    calculate_exhaust_volume_qk, calculate_nvpm_mass_ei, \
    calculate_nvpm_number_ei, calculate_loss_correction_factor, evalute_beta

RESULT_TOLERANCE = 0.15
THEORETICAL_VALUES = {
    "TX": [181.0, 9.2*10**15],
    "TO": [207.0, 1.3*10**15],
    "CL": [212.0, 1.3*10**15],
    "AP": [142.0, 7.2*10**15]}

@pytest.fixture
def sample_data():

    # Set the path to the folder with data for testing
    folder = Path(__file__).parent / "data"

    # Set the path to the file with data for testing
    data_path = folder / "test_update_default_aircraft_engine_ei_nvpm_JT8D-217.csv"

    return pd.read_csv(data_path)

def apply_lower_limit(theoretical_value:float)->float:
    return theoretical_value*(1-RESULT_TOLERANCE)

def apply_upper_limit(theoretical_value:float)->float:
    return theoretical_value*(1+RESULT_TOLERANCE)

def test_calculate_nvpm_mass_and_number_tx(sample_data: pd.DataFrame):
    """
    Example calculation for JT8D-217, manufacturer Rollce-Royce
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020: Section 5.

    Use case with only maximum smoke number present in the database.

    Engine ID (ICAO EEDB) - 1PW018
    Mode: TX - Idle
    """

    # Fetch 1'st use case
    old_line = sample_data.iloc[0]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    # Evaluate beta
    beta = evalute_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)


#TODO: DELETE BELOW 
    # # In ICAO doc.9889 Section 5, value: 181
    # assert round(ei_nvpm_mass_ek, 1) == 174.81536

    # # In ICAO doc.9889 Section 5, value: 9.2*10^15 
    # assert round(ei_nvpm_number_ek, 1) == 8816272110116584.0

    theoretical_values = THEORETICAL_VALUES[mode]

    assert (apply_lower_limit(theoretical_values[0]) <= ei_nvpm_mass_ek <= apply_upper_limit(theoretical_values[0]))
    assert (apply_lower_limit(theoretical_values[1]) <= ei_nvpm_number_ek <= apply_upper_limit(theoretical_values[1]))

def test_calculate_nvpm_mass_and_number_to(sample_data: pd.DataFrame):
    """
    Example calculation for GE90-76B, manufacturer GE AIRCRAFT ENGINES
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.


    Engine ID (ICAO EEDB) - 1PW018
    Mode: TO - Take off
    """

    # Fetch 2'nd use case
    old_line = sample_data.iloc[1]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    # Evaluate beta
    beta = evalute_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    # # In ICAO doc.9889 Section 5, value: 207 
    # assert round(ei_nvpm_mass_ek, 5) == 202.37401 

    # # In ICAO value 1.3*10^15
    # assert round(ei_nvpm_number_ek, 5) == 1275763472297245.2

    
    theoretical_values = THEORETICAL_VALUES[mode]

    assert (apply_lower_limit(theoretical_values[0]) <= ei_nvpm_mass_ek <= apply_upper_limit(theoretical_values[0]))
    assert (apply_lower_limit(theoretical_values[1]) <= ei_nvpm_number_ek <= apply_upper_limit(theoretical_values[1]))

def test_calculate_nvpm_mass_and_number_ap(sample_data: pd.DataFrame):
    """
    Example calculation for Prop-200hp, manufacturer DIVERSE
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Engine ID (ICAO EEDB) - 1PW018
    Mode: AP = Approach
    """

    # Fetch 3'rd use case
    old_line = sample_data.iloc[2]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    # Evaluate beta
    beta = evalute_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    # # In ICAO doc.9889 Section 5, value: 142
    # assert round(ei_nvpm_mass_ek, 5) == 137.01267

    # # In ICAO value 7.2*10^15
    # assert round(ei_nvpm_number_ek, 5) == 6909810707895345.0


    theoretical_values = THEORETICAL_VALUES[mode]

    assert (apply_lower_limit(theoretical_values[0]) <= ei_nvpm_mass_ek <= apply_upper_limit(theoretical_values[0]))
    assert (apply_lower_limit(theoretical_values[1]) <= ei_nvpm_number_ek <= apply_upper_limit(theoretical_values[1]))


def test_calculate_nvpm_mass_and_number_cl(sample_data: pd.DataFrame):
    """
    Example calculation for Prop-200hp, manufacturer DIVERSE
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Engine ID (ICAO EEDB) - 1PW018
    Mode: CL = Climb out
    """

    # Fetch 4'th use case
    old_line = sample_data.iloc[3]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    # Evaluate beta
    beta = evalute_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    # # In ICAO doc.9889 Section 5, value: 212
    # assert round(ei_nvpm_mass_ek, 5) == 208.71973
    # # In ICAO value 1.3*10^15
    # assert round(ei_nvpm_number_ek, 5) == 1315766806745960.5

    theoretical_values = THEORETICAL_VALUES[mode]

    assert (apply_lower_limit(theoretical_values[0]) <= ei_nvpm_mass_ek <= apply_upper_limit(theoretical_values[0]))
    assert (apply_lower_limit(theoretical_values[1]) <= ei_nvpm_number_ek <= apply_upper_limit(theoretical_values[1]))