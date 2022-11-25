import re
import unittest
from pathlib import Path
from warnings import warn

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from database.generate_templates import get_data, apply_sql, MATCH_PATTERNS

DB_DIR = Path(__file__).parents[1] / 'database'
SQL_DIR = DB_DIR / 'sql'
DATA_DIR = DB_DIR / 'data'


@pytest.fixture(scope="module")
def sql_files():
    # Get the files with SQL queries to execute
    return list(SQL_DIR.glob('*.sql'))


@pytest.fixture(scope="module")
def csv_files():
    # Get the files with SQL queries to execute
    return list(DATA_DIR.glob('*.csv'))


@pytest.mark.parametrize("template_type", ['project', 'inventory'])
def test_sql(sql_files: list, template_type: str):
    """
    Test if the sql files can be processed
    """

    # Create in-memory sqlite database
    engine = create_engine("sqlite:///:memory:")

    # Execute the SQL queries in the files to the templates
    apply_sql(engine, sql_files, file_type=template_type)

    # Get the SQL queries to execute
    for sql_path in sql_files:

        # Check if the SQL query should be executed to the project template
        if re.search(MATCH_PATTERNS[template_type], sql_path.name) is not None:
            # Check if the table is present
            assert sql_path.stem in engine.table_names()


@pytest.mark.parametrize("template_type", ['project', 'inventory'])
def test_csv(sql_files: list, csv_files: list, template_type: str):
    """
    Test if the csv files can be processed
    """

    # Create in-memory sqlite database
    engine = create_engine("sqlite:///:memory:")

    # Execute the SQL queries in the files to the templates
    apply_sql(engine, sql_files, file_type=template_type)

    # Get the csv files to import
    for csv_path in csv_files:

        print('import', csv_path.stem)

        # Get the contents of the table
        project_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", engine)

        # Read the .csv file (try ';' and ',' as separators)
        data = get_data(csv_path, project_data)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(csv_path.stem, engine, index=False, if_exists='append')
            except IntegrityError as e:
                warn(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")


def test_project_template():
    # todo Test if the project template is consistent with sql and csv files
    raise NotImplementedError


def test_inventory_template():
    # todo Test if the inventory template is consistent with sql files
    raise NotImplementedError
