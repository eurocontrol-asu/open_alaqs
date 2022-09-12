from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import calculate_smoke_number, calculate_nvpm_mass_concentration_ck, calculate_exhaust_volume_qk,calculate_nvpm_mass_ei, calculate_nvpm_number_ei, calculate_loss_correction_factor
import pandas as pd
from pathlib import Path
from open_alaqs.db_updates.update_default_aircraft_engine_ei_nvpm import SCALING_FACTORS, AIR_FUEL_RATIO, GEOMTRIC_MEAN_DIAMETERS, NR, STANDARD_DEVIATION_PM, PARTICLE_EFFECTIVE_DENSITY

#Get data for 
repository = Path(__file__).parents[1]
data = pd.read_csv(repository / "tests/data/test_update_default_aircraft_engine_ei_nvpm_data.csv")


def test_calculate_nvpm_mass_and_number_sn():
    """
    Example calculation for TFE731-2-2B, manufacturer ALLIED SIGNAL
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Use case with smoke number present in the database.
    """

    old_line = data.iloc[0]

    engine_scaling_factor = SCALING_FACTORS["non_dac"][old_line["mode"]]
    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    beta = 0

    # Assign air fuel ratio based on engine mode
    engine_afr = 45 
    
    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    # plane
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

   
    assert ei_nvpm_mass_ek == 69.74889266719525
    assert ei_nvpm_number_ek == 4.0357537008181945e+34


def test_calculate_nvpm_mass_and_number_no_sn():
    """
    Example calculation for TFE731-2-2B, manufacturer ALLIED SIGNAL
    from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

    Use case without smoke number present in the database, only smoke number maximum present.
    """

    old_line = data.iloc[1]
    engine_scaling_factor = SCALING_FACTORS["non_dac"][old_line["mode"]]
    smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

    nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
        smoke_number_k)

    beta = 0

    # Assign air fuel ratio based on engine mode
    engine_afr = 45 
    
    exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

    # Calculate EInvPMmass
    ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck,
                                            exhaust_volume_qk)

    # Calculate loss correction factor
    loss_correction_factor_kslm_k = calculate_loss_correction_factor(
        nvpm_mass_concentration_ck, beta)

    # Calculate the nvPMmass EIs for each engine mode at the engine exit
    # plane
    ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

    # Calculate EInvPM number (#/kg fuel)
    ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

   
    assert ei_nvpm_mass_ek == 0.42757589969036314
    assert ei_nvpm_number_ek == 2.4740048960915522e+32


# def test_calculate_nvpm_mass_and_number_no_sn():
#     """
#     Example calculation for TFE731-2-2B, manufacturer ALLIED SIGNAL
#     from Doc 9889 Airport Air Quality Manual Second Edition, 2020.

#     Use case without smoke number or smoke number maximum.
#     """

