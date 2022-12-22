import re
from pathlib import Path
from warnings import warn

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from database.generate_templates import apply_sql, MATCH_PATTERNS, get_engine

DB_DIR = Path(__file__).parents[1] / 'database'
TEMPLATES_DIR = Path(__file__).parents[1] / 'alaqs_core/templates'
EXAMPLES_DIR = Path(__file__).parents[1] / 'example'


@pytest.fixture(scope="module")
def sql_files():
    # Get the files with SQL queries to execute
    return list((DB_DIR / 'sql').glob('*.sql'))


@pytest.fixture(scope="module")
def csv_files():
    # Get the files with data to insert
    return list((DB_DIR / 'data').glob('*.csv'))


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

        # Read the .csv file
        data = pd.read_csv(csv_path)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(csv_path.stem, engine, index=False, if_exists='append')
            except IntegrityError as e:
                warn(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")


@pytest.mark.parametrize("example_file",
                         list(EXAMPLES_DIR.glob('**/*.alaqs')),
                         ids=list(d.name for d in EXAMPLES_DIR.glob('**/*.alaqs'))
                         )
def test_example_sql(sql_files: list, example_file: Path):
    """
    Test if the examples are consistent with the sql files
    """

    # Determine the type of file
    template_type = 'inventory' if example_file.stem.endswith('_out') else 'project'

    # Create in-memory sqlite database
    sql_engine = create_engine("sqlite:///:memory:")

    # Execute the SQL queries in the files to the templates
    apply_sql(sql_engine, sql_files, file_type=template_type)

    # Get the template
    example_engine = get_engine(example_file)

    # Get the editable layers
    qgis_engine = get_engine(DB_DIR / f'src/editable_layers.sqlite')

    # Check if all the tables are present
    example_tables = set(example_engine.table_names())
    sql_tables = set(sql_engine.table_names())
    qgis_tables = {
        'shapes_tracks',
        'shapes_area_sources',
        'shapes_buildings',
        'shapes_gates',
        'shapes_parking',
        'shapes_roadways',
        'shapes_runways',
        'shapes_taxiways',
        'shapes_point_sources',
    }

    assert len(sql_tables - example_tables) == 0
    assert len(qgis_tables - example_tables) == 0

    # Check if the columns are present
    for table in sql_tables:
        # Get the columns of template
        template_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0',
                                 example_engine)

        # Get the columns of sql files
        sql_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0', sql_engine)

        # Check if the columns match
        assert (template_d.columns == sql_d.columns).all()

    for table in qgis_tables:
        # Get the columns of template
        template_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0',
                                 example_engine)

        # Get the columns of sql files
        qgis_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0', qgis_engine)

        # Check if the columns match
        assert (template_d.columns == qgis_d.columns).all()

        # Specifically check if the geometry column is present
        assert 'geometry' in template_d


@pytest.mark.parametrize("template_type", ['project', 'inventory'])
def test_template_sql(sql_files: list, template_type: str):
    """
    Test if the template is consistent with the sql files
    """

    # Create in-memory sqlite database
    sql_engine = create_engine("sqlite:///:memory:")

    # Execute the SQL queries in the files to the templates
    apply_sql(sql_engine, sql_files, file_type=template_type)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f'{template_type}.alaqs')

    # Get the editable layers
    qgis_engine = get_engine(DB_DIR / f'src/editable_layers.sqlite')

    # Check if all the tables are present
    template_tables = set(template_engine.table_names())
    sql_tables = set(sql_engine.table_names())
    qgis_tables = {
        'shapes_tracks',
        'shapes_area_sources',
        'shapes_buildings',
        'shapes_gates',
        'shapes_parking',
        'shapes_roadways',
        'shapes_runways',
        'shapes_taxiways',
        'shapes_point_sources',
    }

    assert len(sql_tables - template_tables) == 0
    assert len(qgis_tables - template_tables) == 0

    # Check if the columns are present
    for table in sql_tables:
        # Get the columns of template
        template_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0',
                                 template_engine)

        # Get the columns of sql files
        sql_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0', sql_engine)

        # Check if the columns match
        assert (template_d.columns == sql_d.columns).all()

    for table in qgis_tables:
        # Get the columns of template
        template_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0',
                                 template_engine)

        # Get the columns of sql files
        qgis_d = pd.read_sql(f'SELECT * FROM {table} LIMIT 0', qgis_engine)

        # Check if the columns match
        assert (template_d.columns == qgis_d.columns).all()

        # Specifically check if the geometry column is present
        assert 'geometry' in template_d


@pytest.mark.parametrize("csv_file", list((DB_DIR / 'data').glob('*.csv')),
                         ids=list(d.stem for d in (DB_DIR / 'data').glob('*.csv')))
def test_template_data(sql_files: list, csv_file: Path):
    """
    Test if the data in the project template is consistent with csv files
    """

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f'project.alaqs')

    # Get the contents of the table
    template_data = pd.read_sql(f"SELECT * FROM {csv_file.stem}", template_engine)

    # Read the .csv file
    data = pd.read_csv(csv_file)

    # Check the empty columns
    template_empty_columns = set(template_data.columns[template_data.isna().all()])
    empty_columns = set(data.columns[data.isna().all()])
    assert template_empty_columns == empty_columns

    # Check the non-empty columns
    pd.testing.assert_frame_equal(template_data.loc[:, ~data.isna().all()], data.loc[:, ~data.isna().all()])
