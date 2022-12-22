import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

import database.scripts.constants as c

logging.getLogger().setLevel(logging.INFO)


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

        nvpm_mass_concentration_ck = calculate_nvpm_mass_concentration_ck(smoke_number_k)

        beta = evaluate_beta(old_line)

        # Assign air fuel ratio based on engine mode
        engine_afr = c.AIR_FUEL_RATIO[old_line["mode"]]

        exhaust_volume_qk = calculate_exhaust_volume_qk(engine_afr, beta)

        # Calculate EInvPMmass
        ei_nvpm_mass_k = calculate_nvpm_mass_ei(nvpm_mass_concentration_ck, exhaust_volume_qk)

        # Calculate loss correction factor
        loss_correction_factor_kslm_k = calculate_loss_correction_factor(nvpm_mass_concentration_ck, beta)

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
        f"PMnon_volatile_EI calculated successfully for number of rows: " \
        f"{(old_blank_study['PMnon_volatile_EI'] != 0).sum()}"
    )

    logging.info(
        f"PMnon_volatile_number_EI calculated successfully for number of rows: " \
        f"{(old_blank_study['PMnon_volatile_number_EI'] != 0).sum()}"
    )

    return old_blank_study


def compute_pm_volatile_ei(hc: float, mode: str) -> float:
    """_summary_

    Args:
        hc (float): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return c.REFERENCE_RATIO_PM_VOLATILE[mode] * hc / 1000


def compute_pm_sul_ei() -> float:
    """_summary_

    Returns:
        float: _description_
    """

    return (10 ** 6) * ((c.FSC * c.EPSILON * c.MW_OUT) / c.MW_SULPHUR) / 1000


def get_smoke_number(all_emissions: pd.DataFrame, row: pd.Series, mode: str) -> float:
    """_summary_

    Args:
        all_emissions (pd.DataFrame): _description_
        row (pd.Series): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[f"SN {mode}"].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


def get_gas_ei(all_emissions: pd.DataFrame, row: pd.Series, mode: str, gas: str) -> float:
    """_summary_

    Args:
        all_emissions (pd.DataFrame): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[f"{gas} EI {mode} (g/kg)"].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


def get_fuel_flow(all_emissions: pd.DataFrame, row: pd.Series, mode: str) -> float:
    """_summary_

    Args:
        row (pd.Series): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[f"Fuel Flow {mode} (kg/sec)_x"].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


if __name__ == "__main__":

    # Set the path to the file that's being updated
    default_aircraft_engine_ei_csv = Path(__file__).parents[1] / 'data/default_aircraft_engine_ei.csv'
    old_default_aircraft_engine_ei_csv = Path(__file__).parents[1] / 'src/default_aircraft_engine_ei.csv'

    # Get the relevant data from the source
    src_path = Path(__file__).parents[1] / 'src'

    gas_emissions = pd.read_excel(src_path / c.FILE_ICAO_EEDB, sheet_name=c.TAB_GAS_EMISSIONS)
    nvmp_emissions = pd.read_excel(src_path / c.FILE_ICAO_EEDB, sheet_name=c.TAB_NVPM_EMISSIONS)

    all_emissions = gas_emissions.merge(nvmp_emissions, how="outer", on=["UID No"])

    # Initialize new emissions dataframe
    emissions_df = pd.DataFrame()

    # Add engine names
    emissions_df[[
        "engine_full_name",
        "engine_name",
        "manufacturer",
        "status",
        "fuel_type",
        "eng_type",
        "bpr"
    ]] = all_emissions[[
        "Engine Identification_x",
        "UID No",
        "Manufacturer_x",
        "Current Engine Status",
        "Fuel Spec",
        "Eng Type_x",
        "B/P Ratio_x"
    ]]

    # Engine name type is a combination of Engine Identification and Combustor Description
    emissions_df["engine_name_type"] = \
        all_emissions["Engine Identification_x"] + all_emissions["Combustor Description_x"]

    # Engine type is J, since all engines in EEDB are jet engines
    emissions_df["engine_type"] = "J"

    # Source is EEDB
    emissions_df["source"] = "EEDB"

    # Remark, coolant, combustion_technology and technology_age columns are empty
    emissions_df[["remark", "coolant", "combustion_technology", "technology_age"]] = None

    # Doc 9889 defines SOX EI as 1 g per kg of fuel burnt for all jet engines
    emissions_df["SOX_EI"] = 1

    # Define the right parameters for each flight mode, according to old table
    flight_modes_parameters = {
        "T/O": [1, "TO"], "C/O": [0.85, "CL"], "App": [0.3, "AP"], "Idle": [0.07, "TX"]
    }

    _new_emissions = []
    for index, _row in emissions_df.iterrows():
        for mode, mode_values in flight_modes_parameters.items():
            row = _row.copy()
            row["thrust"] = mode_values[0]
            row["mode"] = mode_values[1]
            row["FUEL_FLOW"] = get_fuel_flow(all_emissions, row, mode)
            row["CO_EI"] = get_gas_ei(all_emissions, row, mode, "CO")
            row["HC_EI"] = get_gas_ei(all_emissions, row, mode, "HC")
            row["NOX_EI"] = get_gas_ei(all_emissions, row, mode, "NOx")
            row["smoke_number"] = get_smoke_number(all_emissions, row, mode)
            row["smoke_number_maximum"] = get_smoke_number(all_emissions, row, "Max")

            row["PM_SUL_EI"] = compute_pm_sul_ei()
            row["PM_volatile_EI"] = compute_pm_volatile_ei(row["HC_EI"], mode)

            _new_emissions.append(row)
    new_emissions = pd.DataFrame(_new_emissions)

    # Calculate nvPM EI
    new_emissions = update_default_aircraft_engine_ei_nvpm(new_emissions)

    new_emissions["PM_01_EI"] = new_emissions["PM_volatile_EI"] + new_emissions["PMnon_volatile_EI"]
    new_emissions["PM_02_EI"] = new_emissions["PM_01_EI"]
    new_emissions["PM_TOTAL_EI"] = new_emissions["PM_01_EI"] + new_emissions["PM_02_EI"]

    # Add missing columns
    new_emissions['oid'] = np.arange(1, new_emissions.shape[0] + 1)
    new_emissions[['pm10_prefoa3', 'pm10_nonvol', 'pm10_sul', 'pm10_organic']] = None

    # Rename columns
    new_emissions = new_emissions.rename(columns={
        "FUEL_FLOW": "fuel_kg_sec",
        "CO_EI": "co_ei",
        "HC_EI": "hc_ei",
        "NOX_EI": "nox_ei",
        "SOX_EI": "sox_ei",
        "PM_SUL_EI": "pm10_ei",
        "PM_01_EI": "p1_ei",
        "PM_02_EI": "p2_ei",
        "PMnon_volatile_EI": "nvpm_ei",
        "PMnon_volatile_number_EI": "nvpm_number_ei"
    })

    # Set the columns
    new_emissions = new_emissions[[
        "oid",
        "engine_type",
        "engine_full_name",
        "engine_name",
        "thrust",
        "mode",
        "fuel_kg_sec",
        "co_ei",
        "hc_ei",
        "nox_ei",
        "sox_ei",
        "pm10_ei",
        "p1_ei",
        "p2_ei",
        "smoke_number",
        "smoke_number_maximum",
        "fuel_type",
        "manufacturer",
        "source",
        "remark",
        "status",
        "engine_name_type",
        "coolant",
        "combustion_technology",
        "technology_age",
        "pm10_prefoa3",
        "pm10_nonvol",
        "pm10_sul",
        "pm10_organic",
        "eng_type",
        "bpr",
        "nvpm_ei",
        "nvpm_number_ei",
    ]]

    new_emissions.to_csv(default_aircraft_engine_ei_csv, index=False)
