import logging
import shutil
from pathlib import Path

import pandas as pd
from sqlalchemy.exc import IntegrityError

from database.generate_templates import apply_sql, get_engine

logging.basicConfig(level=logging.DEBUG)

SRC_DIR = Path(__file__).parent / 'src'
SQL_DIR = Path(__file__).parent / 'sql'
DATA_DIR = Path(__file__).parent / 'data'
TEMPLATES_DIR = Path(__file__).parents[1] / 'alaqs_core/templates'
EXAMPLES_DIR = Path(__file__).parents[1] / 'example'

if __name__ == "__main__":
    """
    Build a new *.alaqs file based on the old study file and new inventory template. 
    """

    # Set the path to the original inventory database
    original_database = SRC_DIR / 'N06_E02A_B19_out.alaqs'

    # Set the path to the example
    example_path = EXAMPLES_DIR / 'forum.alaqs'
    example_out_path = EXAMPLES_DIR / 'forum_out.alaqs'
    example_movements_path = EXAMPLES_DIR / 'forum_movements.csv'
    example_meteo_path = EXAMPLES_DIR / 'forum_meteo.csv'

    # Duplicate the QGIS template to act as basis for the new project and inventory templates
    logging.info(f'duplicate {original_database.name}')
    shutil.copy(original_database, example_out_path)

    # Create the sqlite engines to the databases
    example_out_engine = get_engine(example_out_path)

    # Set the tables to keep (read: copy from original file)
    to_keep = [
        'shapes_aircraft_tracks',
        'shapes_area_sources',
        'shapes_buildings',
        'shapes_gates',
        'shapes_parking',
        'shapes_roadways',
        'shapes_runways',
        'shapes_taxiways',
        'shapes_point_sources',
        'tbl_InvActivityProfileList',
        'tbl_InvLog',
        'tbl_InvMeteo',
        'tbl_InvPeriod',
        'tbl_InvTime',
        'user_aircraft_movements',
        'user_stand_ef',
        'user_study_setup',
        'user_taxiroute_aircraft_group',
        'user_taxiroute_taxiways',
        'user_hour_profile',
        'user_day_profile',
        'user_month_profile',
    ]

    # Get the sql files to execute
    sql_files = list(f for f in SQL_DIR.glob('*.sql') if f.stem not in to_keep)

    # Execute the SQL queries in the files to the templates
    apply_sql(example_out_engine, sql_files, file_type='inventory')

    # Get the csv files to load
    csv_files = sorted(f for f in DATA_DIR.glob('*.csv') if f.stem not in to_keep)

    # Get the csv files to import
    for csv_path in csv_files:

        logging.debug(f'import {csv_path.stem}')

        # Get the contents of the table
        project_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", example_out_engine)

        # Read the .csv file
        data = pd.read_csv(csv_path)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(csv_path.stem, example_out_engine, index=False, if_exists='append')
                logging.debug(f'successfully imported {data.shape[0]} rows')
            except IntegrityError as e:
                logging.error(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")

    # Duplicate the QGIS template to act as basis for the new project and inventory templates
    logging.info(f'duplicate {example_out_path.name}')
    shutil.copy(example_out_path, example_path)

    # Create the sqlite engines to the databases
    example_engine = get_engine(example_path)

    # Set the input specific tables and truncate them
    inventory_tables = [
        "user_aircraft_movements",
    ]
    for inventory_table in inventory_tables:
        example_engine.execute(f'DELETE FROM "{inventory_table}";')

    # Get the inventory specific tables and drop them
    for sql_file in SQL_DIR.glob('tbl_*.sql'):
        inventory_table = sql_file.stem
        example_engine.execute(f'DROP TABLE IF EXISTS "{inventory_table}";')

    # Check if the files exist
    assert example_path.exists(), example_path
    assert example_out_path.exists(), example_out_path
    assert example_movements_path.exists(), example_movements_path
    assert example_meteo_path.exists(), example_meteo_path
