import argparse
import logging
import re
import shutil
import sqlite3
from pathlib import Path, PosixPath

import pandas as pd
import sqlalchemy

# Track if QGIS libs were successfully imported
b_qgis_libs_imported = False

try:
    from open_alaqs.core.interfaces.Aircraft import AircraftDatabase
    from open_alaqs.core.interfaces.AircraftTrajectory import AircraftTrajectoryDatabase
    from open_alaqs.core.interfaces.AmbientCondition import AmbientConditionDatabaseSQL
    from open_alaqs.core.interfaces.APU import APUDatabase, APUtimes
    from open_alaqs.core.interfaces.AreaSources import AreaSourcesDatabase
    from open_alaqs.core.interfaces.EmissionDynamics import EmissionDynamicsDatabase
    from open_alaqs.core.interfaces.EngineDatabases import (
        EngineEmissionFactorsStartDatabase,
        EngineEmissionIndicesDatabase,
        EngineModeDatabase,
        HelicopterEngineEmissionIndicesDatabase,
    )
    from open_alaqs.core.interfaces.Gate import (
        DefaultGateEmissionProfileDatabase,
        GateDatabase,
    )
    from open_alaqs.core.interfaces.InventoryTimeSeries import (
        InventoryTimeSeriesDatabase,
    )
    from open_alaqs.core.interfaces.Movement import MovementDatabase
    from open_alaqs.core.interfaces.ParkingSources import ParkingSourcesDatabase
    from open_alaqs.core.interfaces.PointSources import PointSourcesDatabase
    from open_alaqs.core.interfaces.RoadwaySources import RoadwaySourcesDatabase
    from open_alaqs.core.interfaces.Runway import RunwayDatabase
    from open_alaqs.core.interfaces.SQLSerializable import SQLSerializable
    from open_alaqs.core.interfaces.Taxiway import (
        TaxiwayRouteDatabase,
        TaxiwaySegmentsDatabase,
    )
    from open_alaqs.core.interfaces.Track import TrackDatabase
    from open_alaqs.core.interfaces.UserTimeProfiles import (
        UserDayProfileDatabase,
        UserHourProfileDatabase,
        UserMonthProfileDatabase,
    )

    b_qgis_libs_imported = True
except ModuleNotFoundError as e:
    print(
        "\nError: Some plugin dependencies could not be imported.\n\n"
        "Tips:\n"
        "Make sure to install all plugin dependencies in your virtual environment.\n"
        "Run the script from the OSGeo4W Shell, using the 'python-qgis' command:\n"
        "  python-qgis -m open_alaqs.database.generate_templates [options]\n\n"
        f"Details: {e}\n"
    )

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


def get_sql_serializable_registry(file_type: str) -> list[SQLSerializable]:
    shared = [
        AircraftDatabase,
        AircraftTrajectoryDatabase,
        AmbientConditionDatabaseSQL,
        APUDatabase,
        APUtimes,
        AreaSourcesDatabase,
        DefaultGateEmissionProfileDatabase,
        EmissionDynamicsDatabase,
        EngineEmissionFactorsStartDatabase,
        EngineEmissionIndicesDatabase,
        EngineModeDatabase,
        GateDatabase,
        HelicopterEngineEmissionIndicesDatabase,
        InventoryTimeSeriesDatabase,
        MovementDatabase,
        ParkingSourcesDatabase,
        PointSourcesDatabase,
        RoadwaySourcesDatabase,
        RunwayDatabase,
        TaxiwayRouteDatabase,
        TaxiwaySegmentsDatabase,
        TrackDatabase,
        UserDayProfileDatabase,
        UserHourProfileDatabase,
        UserMonthProfileDatabase,
    ]
    sql_serializable_registry = {
        "project": [],
        "inventory": [],
    }
    return shared + sql_serializable_registry[file_type]


def check_no_duplicate_sql_definition() -> bool:
    sql_serializables = set(
        get_sql_serializable_registry("project")
        + get_sql_serializable_registry("inventory")
    )
    sql_serializable_tables = [
        serializable.TABLE_NAME for serializable in sql_serializables
    ]

    sql_file_names = [sql_file.stem for sql_file in list(SQL_DIR.glob("*.sql"))]

    duplicates = []
    for sql_serializable_table in sql_serializable_tables:
        if sql_serializable_table in sql_file_names:
            duplicates.append(str(SQL_DIR / (sql_serializable_table + ".sql")))

    return not bool(duplicates), duplicates


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
        conn.execute("SELECT InitSpatialMetaData()")  # Takes a while (>30s)

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


def main():
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

    ok, duplicates = check_no_duplicate_sql_definition()
    if not ok:
        print(duplicates)
        raise Exception(
            "The following SQL files already have a corresponding SQL Serializable class, which is redundant:\n\t{}".format(
                "\n\t".join(duplicates)
            )
        )

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

    # Create default_aircraft_profiles table from SQLSerializable subclass
    def recreate_table_from_sql_serializable(file_type, template_path):
        for sql_serializable_subclass in get_sql_serializable_registry(file_type):
            obj = sql_serializable_subclass(str(template_path), deserialize=False)
            obj.recreate_table(
                str(template_path)
            )  # The param is important, because of singletons

    recreate_table_from_sql_serializable("project", project_template)
    recreate_table_from_sql_serializable("inventory", inventory_template)

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

    # Close open DB connections
    project_conn.close()
    inventory_conn.close()


if __name__ == "__main__":
    if b_qgis_libs_imported:
        main()
