from pathlib import Path

import constants as c
import numpy as np
import pandas as pd

if __name__ == "__main__":

    # Set the path to the file that's being updated
    default_aircraft_csv = Path(__file__).parents[1] / "data/default_aircraft.csv"
    old_default_aircraft_csv = Path(__file__).parents[1] / "src/default_aircraft.csv"

    # Get the relevant data from the source
    src_path = Path(__file__).parents[1] / "src"
    most_frequent_engines = pd.read_csv(src_path / c.FILE_MOST_FREQUENT_ENGINES)
    aircraft_to_engine_number = pd.read_excel(
        src_path / c.FILE_EMISSIONS, c.TAB_AIRCRAFT_TO_ENGINE
    )
    icao_doc_8643 = pd.read_excel(src_path / c.FILE_EMISSIONS, c.TAB_MANUFACTURER_INFO)
    icao_doc_8643 = icao_doc_8643.drop(columns="engine_count")
    engines_id_list = pd.read_excel(src_path / c.FILE_EMISSIONS, c.TAB_ENGINES_ID_LIST)
    aircraft_mtow = pd.read_excel(
        src_path / c.FILE_MTOW_INFORMATION, converters={"mtow": int}
    )[["icao", "mtow"]]

    # Include only the most frequent engines for each aircraft type
    most_frequent_engines = most_frequent_engines.loc[
        most_frequent_engines["MOST_FREQ"] == "*"
    ]

    # Merge number of engines with most common engine types
    new_df = pd.merge(
        most_frequent_engines,
        aircraft_to_engine_number,
        left_on="ACFT_ID",
        right_on="ICAO",
        how="left",
    )

    # Merge manufacturer
    new_df = new_df.merge(
        icao_doc_8643.drop_duplicates("tdesig"),
        left_on="ACR",
        right_on="tdesig",
        how="left",
    )

    # Merge engine names
    new_df = new_df.merge(
        engines_id_list[["ENGINE_CODE", "MODEL_NAME1", "ENGINE_TYPE"]],
        left_on="ENGINE",
        right_on="ENGINE_CODE",
        how="left",
    )

    # Load missing fields from old default aircraft
    old_default_aircraft = pd.read_csv(old_default_aircraft_csv, sep=";")

    # Merge missing fields in Excel sheets
    new_df = new_df.merge(
        old_default_aircraft[
            [
                "icao",
                "ac_group_code",
                "ac_group",
                "mtow",
                "departure_profile",
                "arrival_profile",
                "apu_id",
            ]
        ],
        left_on="ACR",
        right_on="icao",
        how="left",
    )

    # Create oid column
    # todo: Do we start from 1 or continue counting from the old data to respect backward compatibility?
    new_df.index = np.arange(1, len(new_df) + 1)
    new_df = new_df.reset_index()
    new_df = new_df.rename(columns={"index": "oid"})

    # Create other new columns
    new_df = new_df.rename(
        columns={
            "icao": "icao_delete",
            "ACR": "icao",
            "NUMBER_OF_ENGINES": "engine_count",
            "BADA_TYPE": "bada_id",
            "manufacturer_code": "manufacturer",
            "model": "name",
            "wtc": "wake_category",
            "MODEL_NAME1": "engine_name",
            "engine_type": "engine_type_delete",
            "ENGINE_TYPE_y": "engine_type",
            "ENGINE_CODE": "engine",
        }
    )

    # Create class column
    new_df["class"] = new_df["description"] + "/" + new_df["wake_category"]

    # The lines above correspond to individual changes to specific aircraft
    # Remove military aircraft
    military = ["A178", "A22", "C1", "KC2", "T34T", "D8"]
    new_df = new_df.drop(new_df[new_df["icao"].isin(military)].index)

    # Add MTOW information
    new_df.loc[new_df.icao.isin(aircraft_mtow.icao), ["mtow"]] = aircraft_mtow[
        ["mtow"]
    ].values

    # Set the relevant columns
    relevant_columns = [
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
        "apu_id",
    ]

    # Filter the relevant columns
    default_aircraft = new_df[relevant_columns]

    # Remove duplicate entries (check all relevant columns except oid)
    default_aircraft = default_aircraft.drop_duplicates(
        relevant_columns[1:], keep="first"
    )

    # Export as csv
    default_aircraft.to_csv(default_aircraft_csv, index=False)
