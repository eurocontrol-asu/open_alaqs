from pathlib import Path

import numpy as np
import pandas as pd
import constants as c
from database.scripts.update_default_aircraft_engine_ei_nvpm import update_default_aircraft_engine_ei_nvpm
from database.scripts._delete_update_emissions_based_on_eedb import compute_pm_volatile_ei, compute_pm_sul_ei, get_smoke_number, \
    get_gas_ei, get_fuel_flow

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
        "pm10_organic"
    ]]

    new_emissions.to_csv(default_aircraft_engine_ei_csv, sep=';', index=False)
