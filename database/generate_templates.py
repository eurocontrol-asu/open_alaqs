import re
import shutil
from pathlib import Path, PosixPath
from warnings import warn

import pandas as pd
import sqlalchemy
from pandas.errors import ParserError
from sqlalchemy.exc import IntegrityError

SRC_DIR = Path(__file__).parent / 'src'
SQL_DIR = Path(__file__).parent / 'sql'
DATA_DIR = Path(__file__).parent / 'data'
TEMPLATES_DIR = Path(__file__).parents[1] / 'alaqs_core/templates'

# Set the match patterns
MATCH_PATTERNS = {
    'project': r'(default|user)_(.*).sql',
    'inventory': r'(default|user|tbl)_(.*).sql'
}


def get_engine(p: Path) -> sqlalchemy.engine.Engine:
    if isinstance(p, PosixPath):
        uri = p.as_uri().replace("file://", "sqlite:///")
    else:
        uri = p.as_uri().replace("file://", "sqlite://")
    return sqlalchemy.create_engine(uri)


def get_data(p: Path, d: pd.DataFrame):
    # Read the .csv file with ';' as separator
    try:
        data1 = pd.read_csv(p, sep=';')
    except ParserError:
        data1 = pd.DataFrame()

    # Read the .csv file with ';' as separator
    try:
        data2 = pd.read_csv(p, sep=',')
    except ParserError:
        data2 = pd.DataFrame()

    # Check if there is data in the file
    if data1.empty and data2.empty:
        return

    # Check if the shapes are matching
    if data1.shape[1] == d.shape[1]:
        data = data1
        sep = ';'
    elif data2.shape[1] == d.shape[1]:
        data = data2
        sep = ','
    else:
        warn("The shapes are not matching!")
        return

    # Check if the headers are present
    if (data.columns == d.columns).all():
        return data

    # Fetch the data without headers
    data = pd.read_csv(p, sep=sep, header=None)

    # Add the column names
    data.columns = d.columns

    return data


def apply_sql(engine, sql_paths, file_type):
    if file_type not in ('project', 'inventory'):
        raise ValueError(f'{file_type} is not supported. It should be either \'project\' or \'inventory\'')

    # Determine the match pattern
    match_pattern = MATCH_PATTERNS[file_type]

    for sql_path in sql_paths:

        # Read the .sql file
        with sql_path.open() as file:
            sql = file.read()

        # Check if the SQL query should be executed to the file
        if re.search(match_pattern, sql_path.name) is not None:

            # Execute the SQL query
            for s in sql.split(';'):
                if len(s) > 0 and ("AddGeometryColumn" not in s) and (
                        file_type != 'inventory' or not s.strip().startswith("INSERT INTO ")):
                    engine.execute(f"{s};")


if __name__ == "__main__":
    """
    Build a new *.alaqs project template and a new *_out.alaqs inventory template. 
    """

    # Get the path to the project (*.alaqs) and inventory (*_out.alaqs) templates
    project_template = TEMPLATES_DIR / 'project.alaqs'
    inventory_template = TEMPLATES_DIR / 'inventory.alaqs'

    # Create the sqlite engines to the databases
    project_engine = get_engine(project_template)
    inventory_engine = get_engine(inventory_template)

    # Get the path to the QGIS template with editable layers (tables named shapes_*)
    editable_layers_template_path = SRC_DIR / 'editable_layers.sqlite'

    # Duplicate the QGIS template to act as basis for the new project and inventory templates
    print('duplicate', editable_layers_template_path.name)
    shutil.copy(editable_layers_template_path, project_template)
    shutil.copy(editable_layers_template_path, inventory_template)

    # Get the files containing SQL queries
    sql_files = list(SQL_DIR.glob('*.sql'))

    # Execute the SQL queries in the files to the templates
    apply_sql(project_engine, sql_files, file_type='project')
    apply_sql(inventory_engine, sql_files, file_type='inventory')

    # Get the csv files to import
    for csv_path in DATA_DIR.glob('*.csv'):

        print('import', csv_path.stem)

        # Get the contents of the table
        project_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", project_engine)

        # Read the .csv file (try ';' and ',' as separators)
        data = get_data(csv_path, project_data)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(csv_path.stem, project_engine, index=False, if_exists='append')
            except IntegrityError as e:
                warn(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")
