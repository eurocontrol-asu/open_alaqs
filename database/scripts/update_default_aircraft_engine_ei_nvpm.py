"""
TODO: This script needs to merged with update_default_aircraft_engine_ei.py
"""
import shutil
import sys
from pathlib import Path
import pandas as pd
import math
import logging
import sqlalchemy

import database.scripts.constants as c


logging.getLogger().setLevel(logging.INFO)


def get_engine(db_url: str):
    """
    Returns the database engine
    """
    db_url = "sqlite:///" + db_url + ".alaqs"

    return sqlalchemy.create_engine(db_url)


def calculate_smoke_number(db_line: pd.Series, engine_scaling_factor: float) -> float:
    """
    Assign or if necessary calculate smoke number for engine

    Args:
        db_line (pd.Series): database line

    Returns:
        float: smoke number
    """

    # Assing smoke number and maximum smoke number to the variables
    smoke_number = db_line["smoke_number"]
    smoke_number_max = db_line["smoke_number_maximum"]

    # Smoke number calculation based on Eq.1
    if smoke_number == 0 and smoke_number_max != 0:
        smoke_number = smoke_number_max * engine_scaling_factor

    return smoke_number


def calculate_nvpm_mass_concentration_ck(smoke_number_k: float) -> float:
    """
    Calculate the estimated nvPM mass concentration at the instrument (Ck).
    Source: Eq.D-2, page 90.

    Args:
        smoke_number_k (float): smoke number

    Returns:
        float: nvPM mass concentration
    """

    return (648.4 * (math.exp(0.0766 * smoke_number_k))) / (
        1 + math.exp(-1.098 * (smoke_number_k - 3.064))
    )


def calculate_exhaust_volume_qk(engine_afr: int, beta: float) -> float:
    """
    Calculate engine exhaust volume Qk.
    Source: Eq.D-4, page 90.

    Args:
        engine_afr (int): air fuel ratio
        beta (float)

    Returns:
        float: exhaust volume
    """

    return 0.777 * engine_afr * (1 + beta) + 0.767


def calculate_nvpm_mass_ei(
    nvpm_mass_concentration: float, exhaust_volume: float
) -> float:
    """
    Calculate nvPMmass EI at the instrument (EInvPMmass,k).
    Source: Eq.D-3, page 90.

    Args:
        nvpm_mass_concentration (float)
        exhaust_volume (float)


    Returns:
        float: nvpm_mass_ei
    """
    return nvpm_mass_concentration * exhaust_volume / 1000


def calculate_loss_correction_factor(
    nvpm_mass_concentration: float, beta: float
) -> float:
    """
    Calculate the mode-dependent system loss correction factor for
     nvPMmass (kslm,k)
    Source: Eq.D-5, page 91.

    Args:
        nvpm_mass_concentration (float)
        beta (float)

    Returns:
        float: loss_correction_factor
    """

    return math.log(
        ((3.219 * nvpm_mass_concentration * (1 + beta)) + 312.5)
        / ((nvpm_mass_concentration * (1 + beta)) + 42.6)
    )


def calculate_nvpm_number_ei(ei_nvpm_mass: float, db_line: pd.Series) -> float:
    """
    Calculate the nvPMnumber EI at engine exit plane for a single mode of
     engine operation k
    Source: Eq.D-7, page 91.

    Args:
        ei_nvpm_mass (float)
        db_line (pd.Series)


    Returns:
        float: ei_nvpm_number
    """

    return (
        6
        * (ei_nvpm_mass / 1000)
        * c.NR
        / (
            math.pi
            * c.PARTICLE_EFFECTIVE_DENSITY
            * ((c.GEOMTRIC_MEAN_DIAMETERS[db_line["mode"]]) ** 3)
            * math.exp(4.5 * (math.log(c.STANDARD_DEVIATION_PM)) ** 2)
        )
    )


def evaluate_beta(old_line: pd.Series) -> float:
    """
    Function that evaluates beta factor based on engine type.

    Args:
        db_line (pd.Series): single row from database

    Returns:
        float: beta value
    """

    if old_line["eng_type"] == "MTF":
        return old_line["bpr"]
    else:
        return 0.0


def update_default_aircraft_engine_ei_nvpm(old_blank_study: pd.DataFrame) -> pd.DataFrame:
    """Adds nvPM EI to aircraft engines

    Args:
        old_blank_study (pd.DataFrame): dataframe with old .alaqs study data

    Returns:
        pd.DataFrame: dataframe with new columns added to .alaqs study
    """

    # Add 2 columns for nvpm mass and number with assigned default values
    old_blank_study["PMnon_volatile_EI"] = 0.0
    old_blank_study["PMnon_volatile_number_EI"] = 0.0

    # Loop over each row of the old table, calculate nvpm_ei mass and number and
    # add to the new columns
    for index, old_line in old_blank_study.iterrows():

        # Evaluate scaling factor based on engine type
        if old_line["manufacturer"] is None:
            engine_scaling_factor = c.SCALING_FACTORS["non_dac"][old_line["mode"]]
        else:
            if "aviadvigatel" in old_line["manufacturer"]:
                engine_scaling_factor = c.SCALING_FACTORS["aviadgatel"][old_line["mode"]]
            elif "textron" in old_line["manufacturer"]:
                engine_scaling_factor = c.SCALING_FACTORS["textron"][old_line["mode"]]
            elif "cfm" in old_line["manufacturer"]:
                engine_scaling_factor = c.SCALING_FACTORS["cfm_dac"][old_line["mode"]]
            elif "CF34" in old_line["engine_full_name"]:
                engine_scaling_factor = c.SCALING_FACTORS["ge_cf34"][old_line["mode"]]
            else:
                engine_scaling_factor = c.SCALING_FACTORS["non_dac"][old_line["mode"]]

        smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

        nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
            smoke_number_k
        )

        beta = evaluate_beta(old_line)

        # Assign air fuel ratio based on engine mode
        engine_afr = c.AIR_FUEL_RATIO[old_line["mode"]]

        exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

        # Calculate EInvPMmass
        ei_nvpm_mass_k = calculate_nvpm_mass_ei(
            nvpm_mass_concentration_ck, exhaust_volume_qk
        )

        # Calculate loss correction factor
        loss_correction_factor_kslm_k = calculate_loss_correction_factor(
            nvpm_mass_concentration_ck, beta
        )

        # Calculate the nvPMmass EIs for each engine mode at the engine exit
        # plane
        ei_nvpm_mass_ek = loss_correction_factor_kslm_k * ei_nvpm_mass_k

        # Calculate EInvPM number (#/kg fuel)
        ei_nvpm_number_ek = calculate_nvpm_number_ei(ei_nvpm_mass_ek, old_line)

        # Add calculated EInvPm to the table
        old_blank_study.loc[index, "PMnon_volatile_EI"] = round(ei_nvpm_mass_ek, 5)
        old_blank_study.loc[index, "PMnon_volatile_number_EI"] = ei_nvpm_number_ek

    # Log calculated values
    logging.info(
        f"PMnon_volatile_EI calculated successfully for number of rows: "\
            f"{(old_blank_study['PMnon_volatile_EI'] != 0).sum()}"
    )

    logging.info(
        f"PMnon_volatile_number_EI calculated successfully for number of rows: "\
            f"{(old_blank_study['PMnon_volatile_number_EI'] != 0).sum()}"
    )

    return old_blank_study
