import shutil
import sys
from pathlib import Path
import pandas as pd
import math
import logging
from update_default_aircraft_engine_ei import get_engine


logging.getLogger().setLevel(logging.INFO)


# Source: Table D-1: Suggested SF values to predict missing SN in the ICAO EEDB, page 88
SCALING_FACTORS = {
    "non_dac": {"TX": 0.3, "TO": 1.0, "CL": 0.9, "AP": 0.3},
    "aviadvigatel": {"TX": 0.3, "TO": 1.0, "CL": 1.0, "AP": 0.8},
    "ge_cf34": {"TX": 0.3, "TO": 1.0, "CL": 0.4, "AP": 0.3},
    "textron_lycoming": {"TX": 0.3, "TO": 1.0, "CL": 1.0, "AP": 0.6},
    "cfm_dac": {"TX": 1.0, "TO": 0.3, "CL": 0.3, "AP": 0.3},
}


# Source: Table D-2. Representative AFRk listed by ICAO power settings (mode k), page 89
AIR_FUEL_RATIO = {"TX": 106, "TO": 45, "CL": 51, "AP": 83}


# Source: Table D-4. Standard values for GMDk listed by ICAO thrust settings (mode k), page 91
GEOMTRIC_MEAN_DIAMETERS = {"TX": 20, "TO": 40, "CL": 40, "AP": 20}


# Constants
NR = 10**24
STANDARD_DEVIATION_PM = 1.8
PARTICLE_EFFECTIVE_DENSITY = 1000


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
        * NR
        / (
            math.pi
            * PARTICLE_EFFECTIVE_DENSITY
            * ((GEOMTRIC_MEAN_DIAMETERS[db_line["mode"]]) ** 3)
            * math.exp(4.5 * (math.log(STANDARD_DEVIATION_PM)) ** 2)
        )
    )


def evalute_beta(old_line: pd.Series) -> float:
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


if __name__ == "__main__":
    """
    Script introduces calculations for engine exhaust particulate emissions in
    the form of emission indices (EI's). Based on 'First order Approximation
    V4.0 method for estimating particulate matter 'mass and number emissions
    from aircraft engines'.
    ICAO Doc 9889, second edition, 2020, Attachment D to Appendix 1, page.84

    Remark: all referenced equations and tables are in Attachment D, page:84

    """

    # Check if user added right number of arguments when calling the function
    if len(sys.argv) != 3:
        raise Exception(
            "Wrong number of arguments. Correct call: `python "
            f"{Path(__file__).name} sqlite:///old_url sqlite:///new_url`"
        )

    # Check if the input file exists and the output file does not exist
    path_1 = Path(sys.argv[1])
    path_2 = Path(sys.argv[2])

    if not path_1.exists():
        raise Exception(f"The input file that you try to use does not exist.\n{path_1}")

    if path_2.exists():
        raise Exception(f"The output file already exists.\n{path_2}")

    # Copy the file
    shutil.copy(str(path_1), str(path_2))

    # Load old table to update
    with get_engine(f"sqlite:///{path_1.absolute()}").connect() as conn:
        old_blank_study = pd.read_sql(
            "SELECT * FROM default_aircraft_engine_ei", con=conn
        )

    # Add 2 columns for nvpm mass and number with assigned default values
    old_blank_study["nvpm_ei"] = 0.0
    old_blank_study["nvpm_number_ei"] = 0.0

    # Loop over each row of the old table, calculate nvpm_ei mass and number and
    # add to the new columns
    for index, old_line in old_blank_study.iterrows():

        # Evaluate scaling factor based on engine type
        if "aviadvigatel" in old_line["manufacturer"]:
            engine_scaling_factor = SCALING_FACTORS["aviadgatel"][old_line["mode"]]
        elif "textron" in old_line["manufacturer"]:
            engine_scaling_factor = SCALING_FACTORS["textron"][old_line["mode"]]
        elif "cfm" in old_line["manufacturer"]:
            engine_scaling_factor = SCALING_FACTORS["cfm_dac"][old_line["mode"]]
        elif "CF34" in old_line["engine_full_name"]:
            engine_scaling_factor = SCALING_FACTORS["ge_cf34"][old_line["mode"]]
        else:
            engine_scaling_factor = SCALING_FACTORS["non_dac"][old_line["mode"]]

        smoke_number_k = calculate_smoke_number(old_line, engine_scaling_factor)

        nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(
            smoke_number_k
        )

        beta = evalute_beta(old_line)

        # Assign air fuel ratio based on engine mode
        engine_afr = AIR_FUEL_RATIO[old_line["mode"]]

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
        old_blank_study.loc[index, "nvpm_ei"] = round(ei_nvpm_mass_ek, 5)
        old_blank_study.loc[index, "nvpm_number_ei"] = ei_nvpm_number_ek

    # Log calculated values
    logging.info(
        f"nvpm_mass_ei calculated successfully for number of rows: {(old_blank_study['nvpm_ei'] != 0).sum()}"
    )

    logging.info(
        f"nvpm_mass_ei calculated successfully for number of rows: {(old_blank_study['nvpm_number_ei'] != 0).sum()}"
    )

    # Save updated database
    with get_engine(f"sqlite:///{path_2.absolute()}").connect() as conn:
        old_blank_study.to_sql(
            "default_aircraft_engine_ei", con=conn, index=False, if_exists="replace"
        )
