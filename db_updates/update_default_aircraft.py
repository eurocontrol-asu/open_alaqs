from pathlib import Path
import sys

import pandas as pd
import numpy as np
import sqlalchemy   


MOST_FREQUENT_ENGINES_FILE = "most_freq_eng_per_aircraft_type.csv"
EMISSIONS_FILE = "EEA_AEM_Acft_Mapping_Eng_LTO_Indices_2022_02-05-2022_v4.xlsx"
AIRCRAFT_TO_ENGINE_TAB = "ACT_PRF.aircraft_engine.txt"
MANUFACTURER_INFO_TAB = "ICAO Doc 8643 - 04042022"
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
    db_url = "sqlite:///" + db_url + ".alaqs"

    return sqlalchemy.create_engine(db_url)


if __name__ == "__main__":
    """
    # NOTES
    # Only considered the most frequently used aircraft
    # used ICAO code for "icao" field
    # "ICAO Doc 8643 - 04042022" tab has several entries for same engine type. I have used the first
    entry to get manufacturer, name (model), wtc and class (description+wtc)
    # engine_name is taken from "ENGINES_ID_LIST" tab, field "MODEL_NAME"
    # engine_full_name and engine_name do not match with engine_name in both tables to change
    # Missing ac_group_code, ac_group, engine, mtow, depaurte_profile, arrival_profile, apu_id. Using
    old blank study to fill gaps. Not all are covered 
    """
    
    file_path = Path(__file__).parent

    # Check if user added right number of arguments when calling the function
    if len(sys.argv) != 3:
        raise Exception(
            "Wrong number of arguments. Correct call: `python update_default_aircraft_engine_ei old_url new_url`"
        )

    # Import relevant tabs
    most_frequent_engines = pd.read_csv(file_path / MOST_FREQUENT_ENGINES_FILE)
    aircraft_to_engine_number = pd.read_excel(
        file_path / EMISSIONS_FILE, 
        AIRCRAFT_TO_ENGINE_TAB
    )
    icao_doc_8643 = pd.read_excel(
        file_path / EMISSIONS_FILE,
        MANUFACTURER_INFO_TAB
    )
    icao_doc_8643 = icao_doc_8643.drop(columns="engine_count")
    engines_id_list = pd.read_excel(
        file_path / EMISSIONS_FILE,
        ENGINES_ID_LIST_TAB
    )

    # Include only the most frequent engines for each aircraft type
    most_frequent_engines = most_frequent_engines.loc[most_frequent_engines["MOST_FREQ"] == "*"]

    # Merge number of engines with most common engine types
    new_df = pd.merge(
        most_frequent_engines,
        aircraft_to_engine_number,
        left_on="ACFT_ID",
        right_on="ICAO",
        how="left"
    )

    # Merge manufacturer
    new_df = new_df.merge(icao_doc_8643.drop_duplicates("tdesig"), left_on="ACR", right_on="tdesig", how="left")

    # Merge engine names
    new_df = new_df.merge(
        engines_id_list[
            [
                "ENGINE_CODE",
                "MODEL_NAME1",
                "ENGINE_TYPE"
            ]
        ],
        left_on="ENGINE",
        right_on="ENGINE_CODE",
        how="left"
    )

    # Load missing fields from old blank study database
    with get_engine(sys.argv[1]).connect() as conn:
        old_blank_study = pd.read_sql("SELECT * FROM default_aircraft", con=conn)

    # Merge missing fields in Excel sheets
    new_df = new_df.merge(
        old_blank_study[
            [
                "icao",
                "ac_group_code", 
                "ac_group", 
                "mtow", 
                "departure_profile", 
                "arrival_profile", 
                "apu_id"
            ]
        ],
        left_on="ACR", 
        right_on="icao", 
        how="left"
    )

    # Create oid column
    new_df.index = np.arange(1, len(new_df) + 1)
    new_df = new_df.reset_index()
    new_df = rename_column(new_df, "index", "oid")

    # Create other new columns
    new_df = rename_column(new_df, "icao", "icao_delete")
    new_df = rename_column(new_df, "ACR", "icao")
    new_df = rename_column(new_df, "NUMBER_OF_ENGINES", "engine_count")
    new_df = rename_column(new_df, "BADA_TYPE", "bada_id")
    new_df = rename_column(new_df, "manufacturer_code", "manufacturer")
    new_df = rename_column(new_df, "model", "name")
    new_df = rename_column(new_df, "wtc", "wake_category")
    new_df = rename_column(new_df, "MODEL_NAME1", "engine_name")
    new_df = rename_column(new_df, "engine_type", "engine_type_delete")
    new_df = rename_column(new_df, "ENGINE_TYPE_y", "engine_type")
    new_df = rename_column(new_df, "ENGINE_CODE", "engine")

    # Create class column
    new_df["class"] = new_df["description"] + "/" + new_df["wake_category"] 

    # Save updated data
    with get_engine(sys.argv[2]).connect() as conn:

        # The lines above correspond to individual changes to specific aircraft
        # Remove military aircraft
        military = ["A178", "A22", "C1", "KC2", "T34T"]
        new_df = new_df.drop(new_df[new_df["icao"].isin(military)].index)

        # Add information
        # new_df.loc[new_df["icao"] == "A337", "mtow"] = 227000 # Wikipedia
        # new_df.loc[new_df["icao"] == "A338", "mtow"] = 251000 # https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=A338&GroupFilter=3

        default_aircraft = new_df[
            [
                "oid", 
                "icao", 
                "ac_group_code", 
                "ac_group", 
                "manufacturer",
                "name", 
                "class", 
                "mtow", 
                "engine_count", 
                "engine_name", 
                "engine", 
                "departure_profile", 
                "arrival_profile", 
                "bada_id", 
                "wake_category", 
                "apu_id"
            ]
        ]
        default_aircraft.to_sql("default_aircraft", con=conn, index = False, if_exists = 'replace')
