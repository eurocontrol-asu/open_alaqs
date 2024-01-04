import re
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect

from database.generate_templates import get_engine

SRC_DIR = Path(__file__).parents[1] / "src"
DATA_DIR = Path(__file__).parents[1] / "data"

if __name__ == "__main__":

    # Create the sqlite engine
    engine = get_engine(SRC_DIR / "new_blank_study.alaqs")

    # Get all tables
    tables = inspect(engine).get_table_names()

    # Get the tables with default data
    for table in tables:
        if re.search(r"(default)_(.*)", table) is not None:

            # Get the contents of the table
            data = pd.read_sql(f"SELECT * FROM {table}", engine)

            if not data.empty:

                # Write all tables to csv
                data.to_csv(DATA_DIR / f"{table}.csv", index=False)
