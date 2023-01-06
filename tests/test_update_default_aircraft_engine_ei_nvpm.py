from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from database.scripts.constants import SCALING_FACTORS, AIR_FUEL_RATIO
from database.scripts.update_default_aircraft_engine_ei_csv import (
    calculate_smoke_number,
    calculate_nvpm_mass_concentration_ck,
    calculate_exhaust_volume_qk,
    calculate_nvpm_mass_ei,
    calculate_nvpm_number_ei,
    calculate_loss_correction_factor,
    evaluate_beta,
)

RESULT_TOLERANCE = 0.15
THEORETICAL_VALUES = {
    "TX": [181.0, 9.2 * 10 ** 15],  # idle
    "TO": [207.0, 1.3 * 10 ** 15],  # take-off
    "CL": [212.0, 1.3 * 10 ** 15],  # climb-out
    "AP": [142.0, 7.2 * 10 ** 15],  # approach
}

EUROCONTROL_FOA4_VALUES = [
    {
        "mode": "TO",
        "C_k": 1782.2165,
        "Q_k": 96.2215,
        "k_slm_k": 1.1801,
        "EI_nvPMmass_k": 171.4875,
        "EI_nvPMmass_e_k": 202.3740,
        "EI_nvPMnumber_e_k": 1.276E+15
    }, {
        "mode": "CL",
        "C_k": 1621.8993,
        "Q_k": 108.9487,
        "k_slm_k": 1.1812,
        "EI_nvPMmass_k": 176.7038,
        "EI_nvPMmass_e_k": 208.7197,
        "EI_nvPMnumber_e_k": 1.316E+15
    }, {
        "mode": "AP",
        "C_k": 646.3601,
        "Q_k": 176.8274,
        "k_slm_k": 1.1988,
        "EI_nvPMmass_k": 114.2942,
        "EI_nvPMmass_e_k": 137.0127,
        "EI_nvPMnumber_e_k": 6.910E+15
    }, {
        "mode": "TX",
        "C_k": 646.3601,
        "Q_k": 225.6153,
        "k_slm_k": 1.1988,
        "EI_nvPMmass_k": 145.8287,
        "EI_nvPMmass_e_k": 174.8154,
        "EI_nvPMnumber_e_k": 8.816E+15
    }]


@pytest.fixture
def engine_data():
    # Set the path to the folder with data for testing
    folder = Path(__file__).parent / "data"

    # Set the path to the file with data for testing
    data_path = folder / "test_update_default_aircraft_engine_ei_nvpm_JT8D-217.csv"

    return pd.read_csv(data_path)


@pytest.mark.parametrize("case", EUROCONTROL_FOA4_VALUES,
                         ids=[f"mode={m.get('mode')}" for m in EUROCONTROL_FOA4_VALUES])
def test_calculate_nvpm_mass_and_number(case: dict, engine_data: pd.DataFrame, precision=1e-4):
    """
    Example calculation for JT8D-217, manufacturer Rolls-Royce
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020: Attachment D to Appendix 1 Section 5.

    Use case with only maximum smoke number present in the database.

    Compares the results with the values taken from the EUROCONTROL Excel file with the FOA4 calculation.

    Engine ID (ICAO EEDB): 1PW018
    """

    # Get the mode
    mode = case.get('mode')

    # Fetch relevant input data line (without nvPM)
    engine = engine_data[engine_data['mode'] == mode].iloc[0]

    # Get the engine scaling factor
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    # Calculate the smoke number
    smoke_number_k = calculate_smoke_number(engine, engine_scaling_factor)

    # Calculate the nvPM mass concentration
    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

    np.testing.assert_allclose(nvpm_mass_concentration_ck, case.get('C_k'), rtol=0, atol=precision)

    # Evaluate beta
    beta = evaluate_beta(engine)

    # Get the air fuel ratio (AFR_k)
    engine_afr = AIR_FUEL_RATIO[mode]

    # Calculate the specific exhaust volume (Q_k)
    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    np.testing.assert_allclose(exhaust_volume_qk, case.get('Q_k'), rtol=0, atol=precision)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

    np.testing.assert_allclose(ei_nvpm_mass_k, case.get("EI_nvPMmass_k"), rtol=0, atol=precision)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

    np.testing.assert_allclose(loss_correction_factor_kslm_k, case.get("k_slm_k"), rtol=0, atol=precision)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    np.testing.assert_allclose(ei_nvpm_mass_ek, case.get("EI_nvPMmass_e_k"), rtol=0, atol=precision)

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, engine)

    np.testing.assert_allclose(ei_nvpm_number_ek, case.get("EI_nvPMnumber_e_k"), rtol=0, atol=precision * 1e16)


@pytest.mark.skip(reason="Reference values from Doc 9889 are incorrect.")
def test_calculate_nvpm_mass_and_number_tx(engine_data):
    """
    Example calculation for JT8D-217, manufacturer Rolls-Royce
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020: Attachment D to Appendix 1 Section 5.

    Use case with only maximum smoke number present in the database.

    Engine ID (ICAO EEDB): 1PW018
    Mode: TX (Idle)
    """

    # Fetch 1'st use case
    old_line = engine_data.iloc[0]

    # Get the mode
    mode = old_line["mode"]

    assert mode == 'TX'

    # Get the engine scaling factor
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    # Calculate the smoke number
    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    # Check if the smoke number is equal to the value from Section 5.2
    assert smoke_number_k == 3.99

    # Calculate the nvPM mass concentration
    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

    np.testing.assert_allclose(nvpm_mass_concentration_ck, 646.3601331726754, rtol=0, atol=1e-4)

    # Evaluate beta
    beta = evaluate_beta(old_line)

    assert beta == 1.73

    # Get the air fuel ratio (AFR_k)
    engine_afr = AIR_FUEL_RATIO[mode]

    assert engine_afr == 106

    # Calculate the specific exhaust volume (Q_k)
    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    assert 225.61526

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

    assert ei_nvpm_mass_k == 0.1458287094993878 * 1000

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

    np.testing.assert_allclose(loss_correction_factor_kslm_k, 1.1987718817427515, rtol=0, atol=1e-4)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    assert ei_nvpm_mass_ek == 174.8153564986982

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    theoretical_values = THEORETICAL_VALUES[mode]

    assert ei_nvpm_mass_ek == theoretical_values[0]
    assert ei_nvpm_number_ek == theoretical_values[1]


@pytest.mark.skip(reason="Reference values from Doc 9889 are incorrect.")
def test_calculate_nvpm_mass_and_number_to(engine_data):
    """
    Example calculation for GE90-76B, manufacturer GE AIRCRAFT ENGINES
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.


    Engine ID (ICAO EEDB): 1PW018
    Mode: TO (Take-off)
    """

    # Fetch 2'nd use case
    old_line = engine_data.iloc[1]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

    # Evaluate beta
    beta = evaluate_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    theoretical_values = THEORETICAL_VALUES[mode]

    assert ei_nvpm_mass_ek == theoretical_values[0]
    assert ei_nvpm_number_ek == theoretical_values[1]


@pytest.mark.skip(reason="Reference values from Doc 9889 are incorrect.")
def test_calculate_nvpm_mass_and_number_ap(engine_data):
    """
    Example calculation for Prop-200hp, manufacturer DIVERSE
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Engine ID (ICAO EEDB): 1PW018
    Mode: AP (Approach)
    """

    # Fetch 3'rd use case
    old_line = engine_data.iloc[2]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

    # Evaluate beta
    beta = evaluate_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    theoretical_values = THEORETICAL_VALUES[mode]

    assert ei_nvpm_mass_ek == theoretical_values[0]
    assert ei_nvpm_number_ek == theoretical_values[1]


@pytest.mark.skip(reason="Reference values from Doc 9889 are incorrect.")
def test_calculate_nvpm_mass_and_number_cl(engine_data):
    """
    Example calculation for Prop-200hp, manufacturer DIVERSE
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Engine ID (ICAO EEDB): 1PW018
    Mode: CL (Climb-out)
    """

    # Fetch 4'th use case
    old_line = engine_data.iloc[3]

    mode = old_line["mode"]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][mode]

    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

    # Evaluate beta
    beta = evaluate_beta(old_line)

    # Evaluate air fuel ratio
    engine_afr = AIR_FUEL_RATIO[mode]

    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    theoretical_values = THEORETICAL_VALUES[mode]

    assert ei_nvpm_mass_ek == theoretical_values[0]
    assert ei_nvpm_number_ek == theoretical_values[1]
