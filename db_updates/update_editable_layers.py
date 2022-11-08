import shutil
from pathlib import Path

import pandas as pd
import sqlalchemy


def get_engine(p: Path) -> sqlalchemy.engine.Engine:
    return sqlalchemy.create_engine(p.as_uri().replace("file://", "sqlite://"))


if __name__ == "__main__":
    """
    Make all layers editable again. 
    """

    # Set the path to the templates folder
    templates = Path(__file__).parents[1] / 'alaqs_core/templates'

    # Set the files to convert {destination: origin}
    convert = {
        templates / 'project.alaqs': templates / 'new_blank_study.alaqs',
        templates / 'inventory.alaqs': templates / 'inventory_template.alaqs',
    }

    # Set the path to the sql folder
    sql_folder = (Path(__file__).parents[1] / 'alaqs_core/sql')

    # Get the path to the editable layers template
    editable_layers_template_path = Path(
        __file__).parent / 'editable_layers.sqlite'

    for new_alaqs_path, old_alaqs_path in convert.items():

        print(old_alaqs_path, '\n\t->\t', new_alaqs_path)

        # Make sure that the new .alaqs file is empty
        new_alaqs_path.unlink(missing_ok=True)

        # Open the databases
        template_engine = get_engine(editable_layers_template_path)
        new_alaqs_engine = get_engine(new_alaqs_path)
        old_alaqs_engine = get_engine(old_alaqs_path)

        # Create the SQL query
        tables_sql = "SELECT name " \
                     "FROM sqlite_schema " \
                     "WHERE type='table' AND name NOT LIKE 'sqlite_%';"

        # Get the template with the correct tables for the editable layers
        template_tables = \
            pd.read_sql(tables_sql, template_engine).sort_values('name')
        template_tables['template'] = True
        template_tables = template_tables[
            template_tables['name'] == template_tables['name'].str.lower()]
        template_tables['count'] = template_tables['name'].apply(
            lambda n: pd.read_sql(f"SELECT COUNT(*) as count FROM {n};",
                                  template_engine).values[0, 0])

        # Get the old .alaqs data
        old_tables = pd.read_sql(tables_sql, old_alaqs_engine).sort_values(
            'name')
        old_tables['old'] = True
        old_tables['count'] = old_tables['name'].apply(
            lambda n: pd.read_sql(f"SELECT COUNT(*) as count FROM {n};",
                                  old_alaqs_engine).values[0, 0])

        # Duplicate the template to act as basis for the new .alaqs file
        shutil.copy(editable_layers_template_path, new_alaqs_path)

        # Get the sql files
        sql_paths = list(sql_folder.glob("*.sql"))
        sql_tables = pd.DataFrame(sql_paths, columns=['file'])
        sql_tables['name'] = sql_tables['file'].apply(lambda x: x.stem)
        sql_tables['sql'] = True

        # Determine the SQL to execute
        sql_to_execute = sql_tables \
            .merge(template_tables, how='outer', on='name',
                   suffixes=('_sql', '_template')) \
            .merge(old_tables, how='outer', on='name',
                   suffixes=('_sql', '_old')) \
            .fillna(False)

        sql_to_execute['to_execute'] = \
            sql_to_execute['sql'] & sql_to_execute['old'] & \
            ~sql_to_execute['template']

        # Copy the tables to the new .alaqs file
        print("Creating", sql_to_execute['to_execute'].sum(), "tables")
        for _, table_to_create in sql_to_execute.loc[
            sql_to_execute['to_execute'], 'name'].iteritems():

            print("*\tCreate", table_to_create)

            # Get the sql from the file
            sql_path = Path(__file__).parents[
                           1] / f'alaqs_core/sql/{table_to_create}.sql'

            # Read the sql query
            with sql_path.open() as file:
                sql = file.read()

            # Execute the sql query
            for s in sql.split(';'):
                if len(s) > 0 and "AddGeometryColumn" not in s:
                    new_alaqs_engine.execute(f"{s};")

        # Validate that all relevant tables are there
        new_tables = \
            pd.read_sql(tables_sql, new_alaqs_engine).sort_values('name')
        new_tables = \
            new_tables[new_tables['name'] == new_tables['name'].str.lower()]
        new_tables['new'] = True

        new_tables = new_tables.merge(
            old_tables, how='outer', on='name', suffixes=('_new', '_old')
        ).fillna(False)

        prefixes = ['default_', 'shapes_', 'user_']
        new_tables['relevant'] = pd.concat([
            new_tables['name'].str.startswith(p) for p in prefixes
        ], axis=1).any(axis=1)
        new_tables['missing'] = \
            new_tables['relevant'] & new_tables['old'] & ~new_tables['new']

        assert not new_tables['missing'].any()

        # Fill the database with default data
        new_tables['to_copy'] = new_tables['name'].str.startswith('default_')
        print("Copying", new_tables['to_copy'].sum(), "tables")
        for _, table_to_copy in new_tables.loc[
            new_tables['to_copy'], 'name'].iteritems():
            print("*\tCopy", table_to_copy)

            # Get the data
            data = \
                pd.read_sql(f"SELECT * FROM {table_to_copy}", old_alaqs_engine)

            # Write the data
            data.to_sql(table_to_copy, new_alaqs_engine,
                        if_exists="append", index=False)
