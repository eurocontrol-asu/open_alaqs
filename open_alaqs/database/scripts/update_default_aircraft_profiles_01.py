import re
from pathlib import Path

import pandas as pd
from database.generate_templates import get_engine

SRC_DIR = Path(__file__).parents[1] / "src"
DATA_DIR = Path(__file__).parents[1] / "data"

# Set the combination of columns that need to be unique
primary_key = ["profile_id", "arrival_departure", "stage", "point"]

if __name__ == "__main__":
    """
    Get the data from the original alaqs v3.0 study
    """

    # Create the sqlite engine
    engine = get_engine(SRC_DIR / "new_blank_study.alaqs")

    # Get all tables
    tables = ["default_aircraft_profiles"]

    # Get the tables with default data
    for table in tables:
        if re.search(r"(default)_(.*)", table) is not None:

            # Get the contents of the table
            data = pd.read_sql(f"SELECT * FROM {table}", engine)

            assert not data["oid"].duplicated().any()

            # Remove duplicate profiles (keep the first one)
            oid_to_delete = []
            for case, case_data in data.groupby(primary_key[:-1]):
                if case_data.duplicated(primary_key).any():
                    oid_to_delete += case_data.loc[
                        case_data.duplicated(primary_key).cumsum() >= 1, "oid"
                    ].tolist()
            data = data[~data["oid"].isin(oid_to_delete)]

            if not data.empty:
                # Write all tables to csv
                data.to_csv(DATA_DIR / f"{table}.csv", index=False)
