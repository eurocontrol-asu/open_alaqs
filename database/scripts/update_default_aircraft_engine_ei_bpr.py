"""
TODO: This script needs to merged with update_default_aircraft_engine_ei.py
"""
import sys
import shutil
import pandas as pd
import logging

from update_default_aircraft_engine_ei import get_engine
from pathlib import Path

logging.getLogger().setLevel(logging.INFO)

ICAO_EEDB = "ICAO_EEDB.xlsx"

if __name__ == "__main__":
    """
    Script that updates .alaqs database file with missing columns: eng_type, b/p_ratio
    """

    file_path = Path(__file__).parent

    # Check if user added right number of arguments when calling the function
    if len(sys.argv) != 3:
        raise Exception(
            "Wrong number of arguments. Correct call: `python "
            f"{Path(__file__).name} old_url new_url`"
        )

    # Check if the input file exists and the output file does not exist
    path_1 = sys.argv[1]
    path_2 = sys.argv[2]

    if not Path(path_1 + ".alaqs").exists():
        raise Exception(f"The input file that you try to use does not exist.\n{path_1}")

    if Path(path_2 + ".alaqs").exists():
        raise Exception(f"The output file already exists.\n{path_2}")

    # Copy the file
    shutil.copy(str(Path(path_1 + ".alaqs")), str(Path(path_2 + ".alaqs")))

    # Import relevant tabs from Excel
    icao_eedb = pd.read_excel(file_path / ICAO_EEDB)

    # Load old table to update
    with get_engine(path_1).connect() as conn:
        old_blank_study = pd.read_sql(
            "SELECT * FROM default_aircraft_engine_ei", con=conn
        )

    # Add 2 columns for nvpm mass and number with assigned default values
    old_blank_study["eng_type"] = "TF"
    old_blank_study["bpr"] = 0.0

    updated_eng_type = 0
    updated_bpr = 0
    engines_not_found = 0

    # Loop over each row of the old table and update the values of the entries found there
    for index, old_line in old_blank_study.iterrows():
        engine_name = old_line["engine_name"]
        df_icao_eedb_engine = icao_eedb[(icao_eedb["UID No"] == engine_name)]

        try:
            # Pick up first line from filtered engines
            df_icao_eedb_line = df_icao_eedb_engine.iloc[0]

            # Assign engine type if value is different than TF
            if df_icao_eedb_line["Eng Type"] != "TF":
                old_blank_study.loc[index, "eng_type"] = df_icao_eedb_line["Eng Type"]
                updated_eng_type += 1

            # Assign B/P Ratio if value is not 0
            if df_icao_eedb_line["B/P Ratio"] != 0.0:
                old_blank_study.loc[index, "bpr"] = df_icao_eedb_line["B/P Ratio"]
                updated_bpr += 1

        except Exception:
            logging.error(f"Engine with name {engine_name} not found in ICAO EEDB.")
            engines_not_found += 1

    # Log the affected columns
    logging.info(f"Number of rows with updated eng_type: {updated_eng_type}")
    logging.info(f"Number of rows with updates BPR: {updated_bpr}")
    logging.info(f"Number of engines not found in ICAO EEDB: {engines_not_found}")

    # Save updated database
    with get_engine(path_2).connect() as conn:
        old_blank_study.to_sql(
            "default_aircraft_engine_ei", con=conn, index=False, if_exists="replace"
        )
