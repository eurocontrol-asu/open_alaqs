import sys

import pandas as pd
import numpy as np
import sqlalchemy   


EMISSIONS_FILE = "EEA_AEM_Acft_Mapping_Eng_LTO_Indices_2022_02-05-2022_v4.xlsx"
ENGINES_EMISSIONS_TAB = "AEM_ENGINE_LTO_VALUES.(v256)"
ENGINES_ID_LIST_TAB = "ENGINES_ID_LIST"


def rename_column(df: pd.DataFrame, name: str, new_name: str) -> pd.DataFrame:
    """
    Changes a single column of a dataframe
    """
    return df.rename(columns={name: new_name})


def get_engine(db_url: str):
    """
    Returns the database engine
    """
    return sqlalchemy.create_engine(db_url)


def update_database_value(df1: pd.DataFrame, df2: pd.DataFrame, field: str, new_value: float) -> pd.DataFrame:
    """
    Changes a single value in the old database and returns the updated dataframe
    """
    df1.loc[
        (df1["engine_full_name"] == df2["engine_full_name"]) &
        (df1["engine_name"] == df2["engine_name"]),
        field
    ] = new_value

    return df1


if __name__ == "__main__":
    """
    # NOTES
    # Assuming PM_SUL is PM_10
    # Check which other fields might be relevant
    # How to get the engine relationship between both tables?    
    """

    # Check if user added right number of arguments when calling the function
    if len(sys.argv) != 3:
        raise Exception(
            "Wrong number of arguments. Correct call: `python update_default_aircraft_engine_ei old_url new_url`"
        )

    # Import relevant tabs from Excel
    engines_id_list = pd.read_excel(
        EMISSIONS_FILE,
        ENGINES_ID_LIST_TAB
    )
    engine_emissions = pd.read_excel(
        EMISSIONS_FILE,
        ENGINES_EMISSIONS_TAB
    )

    # Merge IDs list with emissions
    new_df = pd.merge(
        engines_id_list,
        engine_emissions,
        left_on="ENGINE_CODE",
        right_on="ENGINE_ID",
        how="left"
    )

    # Load old table to update
    with get_engine(sys.argv[1]).connect() as conn:
        old_blank_study = pd.read_sql("SELECT * FROM default_aircraft_engine_ei", con=conn)

    # Define modes definitions
    modes = {"TO": "TAKEOFF", "CL": "CLIMBOUT", "TX": "IDLE", "AP": "APPROACH"}

    # Loop over each row of the old table and update the values of the entries found there
    for index, old_line in old_blank_study.iterrows():

        # Try to find a match between the engine in the old table and the new dataset. There are 2 
        # fields for engine names in the new database (MODEL_NAME1 and ENGINE_CODE). The match is 
        # done with both
        try:
            new_data = new_df.loc[
                (new_df["MODEL_NAME1"] == old_line["engine_full_name"]) & 
                (new_df["ENGINE_CODE"] == old_line["engine_name"])
            ].iloc[0]
            new_df.loc[
                (new_df["MODEL_NAME1"] == old_line["engine_full_name"]) & 
                (new_df["ENGINE_CODE"] == old_line["engine_name"]), 
                "STATUS"
            ] = "Found in old database"
        except:
            try:
                new_data = new_df.loc[
                    (new_df["SYNONYM"] == old_line["engine_full_name"]) &
                    (new_df["ENGINE_CODE"] == old_line["engine_name"])
                ].iloc[0]
                new_df.loc[
                    (new_df["SYNONYM"] == old_line["engine_full_name"]) &
                    (new_df["ENGINE_CODE"] == old_line["engine_name"]),
                    "STATUS"
                ] = "Found in old database"

            # If no match is found with any of the two fields, the engine is marked as not found in
            # the new database and the loop moves to the next line
            except:
                old_blank_study.loc[
                    (old_blank_study["engine_full_name"] == old_line["engine_full_name"]) &
                    (old_blank_study["engine_name"] == old_line["engine_name"]),
                    "STATUS"
                ] = "Not found in new database"
                continue

        # Mark when an engine is found in the new database
        old_blank_study.loc[
            (old_blank_study["engine_full_name"] == old_line["engine_full_name"]) &
            (old_blank_study["engine_name"] == old_line["engine_name"]), 
            "STATUS"
        ] = "Found in new database"

        # Get the flight mode to get the right emissions
        mode = old_line["mode"]

        # Update different fields in the old database's dataframe
        old_blank_study = update_database_value(old_blank_study, old_line, "fuel_kg_sec", new_data[f"FUEL_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "co_ei", new_data[f"CO_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "hc_ei", new_data[f"HC_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "nox_ei", new_data[f"NOX_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "pm10_ei", new_data[f"PM_SUL_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "p1_ei", new_data[f"PM_01_{modes[mode]}"])
        old_blank_study = update_database_value(old_blank_study, old_line, "p2_ei", new_data[f"PM_25_{modes[mode]}"])

    # Log the affected columns
    print("Original rows not updated:", (old_blank_study["STATUS"] == "Not found in new database").sum())
    print("Rows not found in original database:", (new_df["STATUS"] != "Found in old database").sum())

    # Get rows not found in original database
    new_df_rows_not_found = new_df.loc[new_df["STATUS"] != "Found in old database"]

    # Define the right parameters for each flight mode, according to old table
    flight_modes_parameters = {
        "TAKEOFF": [1, "TO"], "APPROACH": [0.85, "CL"], "IDLE": [0.3, "AP"], "CLIMBOUT": [0.07, "TX"]
    }

    # Get ID of the last engine in the database
    oid = old_blank_study["oid"].iloc[-1] + 1

    # Add rows not found to original database
    for ind, row in new_df_rows_not_found.iterrows():
        for mode, params in flight_modes_parameters.items():
            new_row = {
                "oid": oid,
                "engine_full_name": row["MODEL_NAME1"],
                "engine_name": row["ENGINE_CODE"],
                "engine_type": row["ENGINE_TYPE"],
                "thrust": params[0],
                "mode": params[1],
                "fuel_kg_sec": row[f"FUEL_{mode}"],
                "co_ei": row[f"CO_{mode}"],
                "hc_ei": row[f"HC_{mode}"],
                "nox_ei": row[f"NOX_{mode}"],
                "pm10_ei": row[f"PM_SUL_{mode}"],
                "p1_ei": row[f"PM_01_{mode}"],
                "p2_ei": row[f"PM_25_{mode}"]
            }
            old_blank_study = old_blank_study.append(new_row, ignore_index=True)
            oid += 1
    old_blank_study = old_blank_study.astype({"oid": int})

    # Save updated database
    with get_engine(sys.argv[2]).connect() as conn:
        old_blank_study = old_blank_study.drop(columns={"STATUS"})
        old_blank_study.to_sql("default_aircraft_engine_ei", con=conn, index = False, if_exists = 'replace')
