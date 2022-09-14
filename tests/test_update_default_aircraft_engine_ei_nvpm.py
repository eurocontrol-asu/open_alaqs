from pathlib import Path

import pandas as pd
import pytest

from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import \
    SCALING_FACTORS, AIR_FUEL_RATIO
from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import \
    calculate_smoke_number, calculate_nvpm_mass_concentration_ck, \
    calculate_exhaust_volume_qk, calculate_nvpm_mass_ei, \
    calculate_nvpm_number_ei, calculate_loss_correction_factor

# Calculation constants
MODE = "TO"
ENGINE_SCALING_FACTOR = SCALING_FACTORS["non_dac"][MODE]
ENGINE_AFR = AIR_FUEL_RATIO[MODE]
BETA = 0


@pytest.fixture
def sample_data():

    # Set the path to the folder with data for testing
    folder = Path(__file__).parent / "data"

    # Set the path to the file with data for testing
    data_path = folder / "test_update_default_aircraft_engine_ei_nvpm_data.csv"

    return pd.read_csv(data_path)


def test_calculate_nvpm_mass_and_number_sn(sample_data: pd.DataFrame):
    """
    Example calculation for TFE731-2-2B, manufacturer ALLIED SIGNAL
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Use case with smoke number present in the database.
    """

    # Fetch 1'st use case
    old_line = sample_data.iloc[0]

    smoke_number_k = calculate_smoke_number(old_line, ENGINE_SCALING_FACTOR)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    exhaust_volume_qk = calculate_exhaust_volume_qk(ENGINE_AFR, BETA)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, BETA)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    # plane
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    assert ei_nvpm_mass_ek == 69.74889266719525
    assert ei_nvpm_number_ek == 4.0357537008181945e+34


def test_calculate_nvpm_mass_and_number_sn_max_only(sample_data: pd.DataFrame):
    """
    Example calculation for GE90-76B, manufacturer GE AIRCRAFT ENGINES
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Use case without smoke number present in the database, only smoke number maximum present.
    """

    # Fetch 2'nd use case
    old_line = sample_data.iloc[1]

    smoke_number_k = calculate_smoke_number(old_line, ENGINE_SCALING_FACTOR)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    exhaust_volume_qk = calculate_exhaust_volume_qk(ENGINE_AFR, BETA)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, BETA)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    # plane
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    assert ei_nvpm_mass_ek == 0.42757589969036314
    assert ei_nvpm_number_ek == 2.4740048960915522e+32


def test_calculate_nvpm_mass_and_number_no_sn(sample_data: pd.DataFrame):
    """
    Example calculation for Prop-200hp, manufacturer DIVERSE
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Use case without smoke number or smoke number maximum.
    """

    # Fetch 3'rd use case
    old_line = sample_data.iloc[2]

    smoke_number_k = calculate_smoke_number(old_line, ENGINE_SCALING_FACTOR)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    exhaust_volume_qk = calculate_exhaust_volume_qk(ENGINE_AFR, BETA)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, BETA)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    # plane
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

    assert ei_nvpm_mass_ek == 0.18651694460214496
    assert ei_nvpm_number_ek == 1.0792091754561153e+32
