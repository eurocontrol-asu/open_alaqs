import argparse
import logging
import re
import shutil
import sqlite3
from pathlib import Path, PosixPath

import pandas as pd
import sqlalchemy

logging.basicConfig(level=logging.DEBUG)

SRC_DIR = Path(__file__).parent / "src"
SQL_DIR = Path(__file__).parent / "sql"
DATA_DIR = Path(__file__).parent / "data"
TEMPLATES_DIR = Path(__file__).parents[1] / "core/templates"

# Set the match patterns
MATCH_PATTERNS = {
    "project": r"(shapes|default|user)_(.*).sql",
    "inventory": r"(shapes|default|user|tbl)_(.*).sql",
}


def get_engine(p: Path) -> sqlalchemy.engine.Engine:
    if isinstance(p, PosixPath):
        uri = p.as_uri().replace("file://", "sqlite:///")
    else:
        uri = p.as_uri().replace("file://", "sqlite://")
    return sqlalchemy.create_engine(uri)


def connect(p: Path, init_spatialite: bool = False) -> sqlite3.Connection:
    logging.info("Connecting to %s...", p)

    conn = sqlite3.connect(p)

    conn.enable_load_extension(True)
    conn.execute("SELECT load_extension('mod_spatialite')")
    conn.enable_load_extension(False)

    if init_spatialite:
        conn.execute("SELECT InitSpatialMetaData()")

    return conn


def apply_sql(conn: sqlite3.Connection, sql_paths, file_type):
    if file_type not in ("project", "inventory"):
        raise ValueError(
            f"{file_type} is not supported. It should be either 'project' or 'inventory'"
        )

    for sql_path in sql_paths:
        # Check if the SQL query should be executed to the file
        if re.search(MATCH_PATTERNS[file_type], sql_path.name) is None:
            continue

        logging.info("Executing SQL file: %s", sql_path.name)

        # Read the .sql file
        with sql_path.open() as file:
            sql_queries = file.read()

        # Execute the SQL query
        for sql_query in sql_queries.split(";"):
            sql_query = sql_query.strip()

            if len(sql_query) == 0:
                continue

            # for inventory we should not run insert statements!
            if (
                file_type == "inventory"
                and sql_path.name.startswith("user_")
                and sql_query.upper().startswith("INSERT INTO")
            ):
                continue

            conn.execute(sql_query)

    conn.commit()


if __name__ == "__main__":
    """
    Build a new *.alaqs project template and a new *_out.alaqs inventory template.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full-recreate",
        help="recreate the Spatialite databases from scratch (slow, ~3 mins)",
        action="store_true",
    )
    args = parser.parse_args()

    # Get the path to the project (*.alaqs) and inventory (*_out.alaqs) templates
    base_template = TEMPLATES_DIR / "spatialite_base.alaqs"
    project_template = TEMPLATES_DIR / "project.alaqs"
    inventory_template = TEMPLATES_DIR / "inventory.alaqs"

    if args.full_recreate:
        logging.debug(
            'Overwrite the base template Spatialite file "%s"...', str(base_template)
        )

        base_template.unlink(missing_ok=True)

        connect(base_template, init_spatialite=True)

    logging.debug('Using the Spatialite file "%s" as base!', str(base_template))

    shutil.copyfile(base_template, project_template)
    shutil.copyfile(base_template, inventory_template)

    # Create the sqlite engines to the databases
    project_conn = connect(project_template)
    inventory_conn = connect(inventory_template)

    # Get the files containing SQL queries
    sql_files = list(SQL_DIR.glob("*.sql"))

    # Execute the SQL queries in the files to the templates
    apply_sql(project_conn, sql_files, file_type="project")
    apply_sql(inventory_conn, sql_files, file_type="inventory")

    # # Get the csv files
    csv_filenames = sorted(DATA_DIR.glob("*.csv"))

    # Get the csv files to import
    for csv_filename in csv_filenames:
        logging.debug('Importing CSV "%s"...', csv_filename.stem)

        alaqsdb_df = pd.read_sql(f"SELECT * FROM {csv_filename.stem}", project_conn)

        if not alaqsdb_df.empty:
            raise ValueError("What to do when the database is not empty?")

        csv_df = pd.read_csv(csv_filename)

        if csv_df.empty:
            logging.warning('Nothing to import from CSV "%s"', csv_filename.stem)

        try:
            csv_df.to_sql(
                csv_filename.stem,
                project_conn,
                index=False,
                if_exists="append",
            )

            logging.info(
                'Successfully imported %i rows from CSV "%s"',
                csv_df.shape[0],
                csv_filename.stem,
            )

        except sqlite3.IntegrityError as error:
            logging.error('Failed to import data from CSV "%s"', csv_filename.stem)

            raise error
