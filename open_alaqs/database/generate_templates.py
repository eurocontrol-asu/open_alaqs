import logging
import re
import shutil
from pathlib import Path, PosixPath

import pandas as pd
import sqlalchemy
from sqlalchemy.exc import IntegrityError

logging.basicConfig(level=logging.DEBUG)

SRC_DIR = Path(__file__).parent / "src"
SQL_DIR = Path(__file__).parent / "sql"
DATA_DIR = Path(__file__).parent / "data"
TEMPLATES_DIR = Path(__file__).parents[1] / "core/templates"

# Set the match patterns
MATCH_PATTERNS = {
    "project": r"(default|user)_(.*).sql",
    "inventory": r"(default|user|tbl)_(.*).sql",
}


def get_engine(p: Path) -> sqlalchemy.engine.Engine:
    if isinstance(p, PosixPath):
        uri = p.as_uri().replace("file://", "sqlite:///")
    else:
        uri = p.as_uri().replace("file://", "sqlite://")
    return sqlalchemy.create_engine(uri)


def apply_sql(engine, sql_paths, file_type):
    if file_type not in ("project", "inventory"):
        raise ValueError(
            f"{file_type} is not supported. It should be either 'project' or 'inventory'"
        )

    for sql_path in sql_paths:
        # Check if the SQL query should be executed to the file
        if re.search(MATCH_PATTERNS[file_type], sql_path.name) is None:
            continue

        # Read the .sql file
        with sql_path.open() as file:
            sql_queries = file.read()

        # Execute the SQL query
        for sql_query in sql_queries.split(";"):
            sql_query = sql_query.strip()

            # skip if empty query, adds geometry column or inserts in inventory table
            if (
                len(sql_query) == 0
                or "AddGeometryColumn" in sql_query
                or (file_type == "inventory" and sql_query.startswith("INSERT INTO "))
            ):
                continue

            with engine.connect() as conn:
                conn.execute(sqlalchemy.text(sql_query))


if __name__ == "__main__":
    """
    Build a new *.alaqs project template and a new *_out.alaqs inventory template.
    """

    # Get the path to the project (*.alaqs) and inventory (*_out.alaqs) templates
    project_template = TEMPLATES_DIR / "project.alaqs"
    inventory_template = TEMPLATES_DIR / "inventory.alaqs"

    # Get the path to the QGIS template with editable layers (tables named shapes_*)
    editable_layers_template_path = SRC_DIR / "editable_layers.sqlite"

    # Duplicate the QGIS template to act as basis for the new project and inventory templates
    logging.info(f"duplicate {editable_layers_template_path.name}")
    shutil.copy(editable_layers_template_path, project_template)
    shutil.copy(editable_layers_template_path, inventory_template)

    # Create the sqlite engines to the databases
    project_engine = get_engine(project_template)
    inventory_engine = get_engine(inventory_template)

    # Get the files containing SQL queries
    sql_files = list(SQL_DIR.glob("*.sql"))

    # Execute the SQL queries in the files to the templates
    apply_sql(project_engine, sql_files, file_type="project")
    apply_sql(inventory_engine, sql_files, file_type="inventory")

    # Get the csv files
    csv_files = sorted(DATA_DIR.glob("*.csv"))

    # Get the csv files to import
    for csv_path in csv_files:

        logging.debug(f"import {csv_path.stem}")

        # Get the contents of the table
        project_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", project_engine)

        # Read the .csv file
        data = pd.read_csv(csv_path)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(
                    csv_path.stem, project_engine, index=False, if_exists="append"
                )
                logging.debug(f"successfully imported {data.shape[0]} rows")
            except IntegrityError as e:
                logging.error(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")
