import re
from pathlib import Path

from sqlalchemy import create_engine

SQL_DIR = Path(__file__).parents[1] / 'database/sql'


def test_sql():
    """
    Test if the sql files can be processed
    """

    # Create in-memory sqlite databases
    project_engine = create_engine("sqlite:///:memory:")
    inventory_engine = create_engine("sqlite:///:memory:")

    # Get the SQL queries to execute
    for sql_path in SQL_DIR.glob('*.sql'):

        print('create', sql_path.stem)

        # Read the .sql file
        with sql_path.open() as file:
            sql = file.read()

        # Check if the SQL query should be executed to the project template
        if re.search(r'(default|user)_(.*).sql', sql_path.name) is not None:

            # Execute the SQL query
            for s in sql.split(';'):
                if len(s) > 0 and ("AddGeometryColumn" not in s):
                    project_engine.execute(f"{s};")

            assert sql_path.stem in project_engine.table_names()

        # Check if the SQL query should be executed to the inventory template
        if re.search(r'(default|user|tbl)_(.*).sql', sql_path.name) is not None:

            # Execute the SQL query
            for s in sql.split(';'):
                if len(s) > 0 and ("AddGeometryColumn" not in s) and not s.strip().startswith("INSERT INTO "):
                    inventory_engine.execute(f"{s};")

            assert sql_path.stem in inventory_engine.table_names()


def test_csv():
    # todo Test if the csv files can be processed
    raise NotImplementedError


def test_project_template():
    # todo Test if the project template is consistent with sql and csv files
    raise NotImplementedError


def test_inventory_template():
    # todo Test if the inventory template is consistent with sql files
    raise NotImplementedError
