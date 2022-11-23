from enum import unique
from pathlib import Path
import shutil
import sys
from typing import Tuple
import logging

import pandas as pd
import sqlalchemy

from update_default_aircraft_engine_ei_nvpm import update_default_aircraft_engine_ei_nvpm
import constants as c

logging.getLogger().setLevel(logging.INFO)


def get_engine(db_url: str):
    """
    Returns the database engine
    """
    db_url = "sqlite:///" + db_url + ".alaqs"

    return sqlalchemy.create_engine(db_url)


def get_gas_ei(all_emissions: pd.DataFrame, row: pd.Series, mode: str, gas: str) -> float:
    """_summary_

    Args:
        all_emissions (pd.DataFrame): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[
        f"{gas} EI {mode} (g/kg)"
    ].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


def get_fuel_flow(all_emissions: pd.DataFrame, row: pd.Series, mode: str) -> float:
    """_summary_

    Args:
        row (pd.Series): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[
        f"Fuel Flow {mode} (kg/sec)_x"
    ].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


def get_values_from_old_study(
    row: pd.Series, old_study: pd.DataFrame
) -> Tuple[float, float, float, float]:
    """_summary_

    Args:
        row (pd.Series): _description_
        old_study (pd.DataFrame): _description_

    Returns:
        Tuple[float, float, float, float]: _description_
    """

    try:
        values = old_study[
            ["eng_type", "bpr", "pm10_sul", "pm10_organic"]
        ].loc[old_study["engine_name"] == row["engine_name"]].iloc[0]

        return values["eng_type"], values["bpr"], values["pm10_sul"], values["pm10_organic"]

    except:
        return None, None, None, None, None


def get_smoke_number(all_emissions: pd.DataFrame, row: pd.Series, mode: str) -> float:
    """_summary_

    Args:
        all_emissions (pd.DataFrame): _description_
        row (pd.Series): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return all_emissions[
        f"SN {mode}"
    ].loc[all_emissions["UID No"] == row["engine_name"]].iloc[0]


def compute_pm_sul_ei() -> float:
    """_summary_

    Returns:
        float: _description_
    """
    
    return (10 ** 6) * ((c.FSC * c.EPSILON * c.MW_OUT) / c.MW_SULPHUR) / 1000


def compute_pm_volatile_ei(hc: float, mode: str) -> float:
    """_summary_

    Args:
        hc (float): _description_
        mode (str): _description_

    Returns:
        float: _description_
    """

    return c.REFERENCE_RATIO_PM_VOLATILE[mode] * hc / 1000


def update_emissions_based_on_eedb(old_database: str, new_database: str):
    """_summary_

    Args:
        old_database (str): _description_
        new_database (str): _description_
    """

    file_path = Path(__file__).parent / c.DATA_PATH

    gas_emissions = pd.read_excel(file_path / c.FILE_ICAO_EEDB, sheet_name=c.TAB_GAS_EMISSIONS)
    nvmp_emissions = pd.read_excel(file_path / c.FILE_ICAO_EEDB, sheet_name=c.TAB_NVPM_EMISSIONS)

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

    new_emissions = pd.DataFrame()

    for index, row in emissions_df.iterrows():
        for mode, mode_values in flight_modes_parameters.items():

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

            new_emissions = new_emissions.append(row, ignore_index=True)

    # Calculate nvPM EI
    new_emissions = update_default_aircraft_engine_ei_nvpm(new_emissions)

    new_emissions["PM_01_EI"] = new_emissions["PM_volatile_EI"] + new_emissions["PMnon_volatile_EI"]
    new_emissions["PM_02_EI"] = new_emissions["PM_01_EI"]
    new_emissions["PM_TOTAL_EI"] = new_emissions["PM_01_EI"] + new_emissions["PM_02_EI"]

    # Open new table
    with get_engine(new_database).connect() as conn:
        new_emissions.to_sql(
            "default_aircraft_engine_ei", con=conn, index=False, if_exists="replace"
        )

        new_engines = pd.read_sql("SELECT * FROM default_aircraft", con=conn)

    # Check which engines are not found in the new emissions table
    new_engines["FOUND"] = new_engines["engine"].isin(new_emissions["engine_name"].unique())
    nr_engines_not_found = len(new_engines[new_engines["FOUND"] == False])
    print(new_engines[new_engines["FOUND"] == False])

    logging.info(f"{nr_engines_not_found}/{len(new_engines)} engines from the aircraft table were "\
        "not found in the engine emissions table.")
