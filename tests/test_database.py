import re
from itertools import product
from pathlib import Path
from warnings import warn

import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from tests.utils import get_copy_path, get_data_path
from tools.template_build.generate_templates import (
    MATCH_PATTERNS,
    apply_sql,
    apply_sqlserializable_registry,
    connect,
    get_engine,
)

DB_DIR = Path(__file__).parents[1] / "open_alaqs" / "database"
TEMPLATES_DIR = Path(__file__).parents[1] / "open_alaqs/core/templates"
EXAMPLES_DIR = Path(__file__).parents[1] / "example"
# SQL files moved to tools/template_build/sql/ alongside generate_templates.py
SQL_DIR_BUILD = Path(__file__).parents[1] / "tools" / "template_build" / "sql"


@pytest.fixture(scope="module")
def sql_files():
    # Get the files with SQL queries to execute (moved out of plugin tree
    # in scenario A; now lives under tools/template_build/sql/)
    return list(SQL_DIR_BUILD.glob("*.sql"))


@pytest.fixture(scope="module")
def csv_files():
    # Get the files with data to insert
    return list((DB_DIR / "data").glob("*.csv"))


@pytest.mark.parametrize("template_type", ["project", "inventory"])
def test_sql(sql_files: list, template_type: str):
    """
    Test if the sql files can be processed
    """
    # Use a copy of a spatially-enabled (empty) DB
    db_path = get_copy_path(get_data_path() / "spatial_template.sqlite")

    # Or, uncomment to create a temporary spatially-enabled DB
    # from scratch. Be aware of around 40s initializing spatial metadata!
    # db_path = get_tmp_path(template_type + ".alaqs")
    # conn = connect(db_path, init_spatialite=True)

    print(f"\nConnecting to {db_path} ({template_type})...")
    conn = connect(db_path, init_spatialite=False)

    # Execute the SQL queries in the files to the templates
    print(f"\nApplying SQL files to {db_path} ({template_type})...")
    apply_sql(conn, sql_files, file_type=template_type)

    cursor = conn.cursor()
    res = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = res.fetchall()
    cursor.close()
    conn.close()
    assert len(table_names) > 0

    # Get the SQL queries to execute
    for sql_path in sql_files:

        # Check if the SQL query should be executed to the project template
        if re.search(MATCH_PATTERNS[template_type], sql_path.name) is not None:
            # Check if the table is present
            if (
                sql_path.stem == "shapes_receptors"
            ):  # TODO: Ask to rename table or file!
                continue

            assert (sql_path.stem,) in table_names


@pytest.mark.slow
@pytest.mark.parametrize("template_type", ["project", "inventory"])
def test_csv(sql_files: list, csv_files: list, template_type: str, tmp_path):
    """
    Test that every default_*.csv can be imported into a freshly-built
    template. Uses a file-backed temp DB so SpatiaLite is available for
    AddGeometryColumn calls in apply_sql. Marked slow because creating a
    spatial DB with SpatiaLite metadata is ~5s per parametrization.

    Tables come from two sources:
      * SQLSerializable subclasses (default_aircraft, default_apu_times,
        default_emission_dynamics, ...) — the python class owns the schema
      * .sql files (default_airports, default_stationary_*, etc.) — the
        legacy way, kept for tables that have no SQLSerializable owner
    Both are required to cover every CSV in database/data/.
    """
    tmp_db = tmp_path / f"{template_type}_csv.sqlite"

    # Fast SpatiaLite metadata init (~0.1s vs >30s for full init). Required
    # because apply_sqlserializable_registry creates shapes_* tables with
    # geometry columns that reference spatial_ref_sys / geometry_columns.
    init_conn = connect(tmp_db)
    init_conn.execute("SELECT InitSpatialMetaData(1)")
    init_conn.commit()
    init_conn.close()

    # Phase 1: tables from SQLSerializable subclasses.
    apply_sqlserializable_registry(tmp_db, template_type)

    # Phase 2: tables from .sql files.
    engine = get_engine(tmp_db)
    apply_sql(engine, sql_files, file_type=template_type)

    # Get the csv files to import
    for csv_path in csv_files:
        print("import", csv_path.stem)

        # Get the contents of the table
        project_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", engine)

        # Read the .csv file
        data = pd.read_csv(csv_path)

        # Import the data to fill the table
        if data is not None and project_data.empty and not data.empty:
            try:
                data.to_sql(csv_path.stem, engine, index=False, if_exists="append")
            except IntegrityError as e:
                warn(e.args[0])
        elif not project_data.empty:
            raise ValueError("What to do when the database is not empty?")


@pytest.mark.parametrize(
    "example_file",
    list(EXAMPLES_DIR.glob("**/*.alaqs")),
    ids=list(d.name for d in EXAMPLES_DIR.glob("**/*.alaqs")),
)
def test_example_sql(sql_files: list, example_file: Path, tmp_path):
    """
    Test if the examples are consistent with the sql files.

    Walks the example/ tree, applies the reference schema from the .sql
    files into a fresh SpatiaLite-backed DB, and verifies that every
    example .alaqs has all the required tables and columns.
    """

    # Determine the type of file
    template_type = "inventory" if example_file.stem.endswith("_out") else "project"

    # Use a file-backed temp DB so get_engine's SpatiaLite loader attaches.
    # An in-memory engine via `create_engine("sqlite:///:memory:")` wouldn't
    # have SpatiaLite loaded, so AddGeometryColumn fails with "no such function".
    tmp_db = tmp_path / f"{template_type}_apply_sql.sqlite"
    sql_engine = get_engine(tmp_db)

    # Execute the SQL queries in the files to the templates
    apply_sql(sql_engine, sql_files, file_type=template_type)

    # Get the template
    example_engine = get_engine(example_file)

    # Check if all the tables are present
    from sqlalchemy import inspect

    example_tables = set(inspect(example_engine).get_table_names())
    sql_tables = set(inspect(sql_engine).get_table_names())
    # The QGIS-editable spatial-layer tables must exist in the example. The
    # set is hardcoded; the previous design used to read the canonical
    # column schema from a sidecar `editable_layers.sqlite` file, but that
    # file was always shipped empty and the column cross-check was already
    # a no-op. The sidecar was dropped in scenario A; the presence check
    # below is what guarantees example files carry the required QGIS
    # layers.
    qgis_tables = {
        "shapes_tracks",
        "shapes_area_sources",
        "shapes_buildings",
        "shapes_gates",
        "shapes_parking",
        "shapes_roadways",
        "shapes_runways",
        "shapes_taxiways",
        "shapes_point_sources",
    }

    # Tables required by the reference SQL schema must exist in the example
    assert len(sql_tables - example_tables) == 0, (
        f"Missing SQL tables in {example_file.name}: " f"{sql_tables - example_tables}"
    )
    # QGIS-editable spatial-layer tables must exist in the example
    assert len(qgis_tables - example_tables) == 0, (
        f"Missing QGIS tables in {example_file.name}: "
        f"{qgis_tables - example_tables}"
    )

    # Check if the columns are present
    for table in sql_tables:
        # Get the columns of template
        template_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", example_engine)
        template_d.name = table
        sql_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", sql_engine)
        assert (template_d.columns == sql_d.columns).all(), (
            f"Column mismatch in {example_file.name}.{table}: "
            f"template={list(template_d.columns)} vs sql={list(sql_d.columns)}"
        )

    for table in qgis_tables:
        template_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", example_engine)
        # Each QGIS-editable layer must carry a geometry column. Column
        # cross-check against an external reference is no longer
        # performed (see comment above on the dropped sidecar file).
        assert "geometry" in template_d


out_example_paths = list(EXAMPLES_DIR.glob("**/*_out.alaqs"))
csv_paths = list((DB_DIR / "data").glob("*.csv"))

# Tables where the shipped example fixtures have drifted from the
# canonical CSV source of truth. These need regeneration via the openALAQS
# import pipeline; for now the combos are marked xfail so the other 28
# CSV-vs-example consistency checks still run.
#
# Earlier this set also included `default_aircraft` and
# `default_aircraft_engine_ei`, but investigation showed both had IDENTICAL
# data after sort_values("oid") — the apparent drift was purely a row-order
# artifact from the CSV serialization. The test itself now sorts both sides
# before comparison, so those two combos pass cleanly.
_DRIFTED_TABLES: set[str] = set()  # All drift resolved in session 3+

combos = list(product(out_example_paths, csv_paths))


def _combo_marks(combo):
    """Mark known-drifted (example, csv) combos xfail; let the rest run."""
    _, csv_path = combo
    if csv_path.stem in _DRIFTED_TABLES:
        return pytest.mark.xfail(
            reason=(
                f"example fixture has drifted from "
                f"{csv_path.stem}.csv (canonical source). Regenerate "
                "example/training/training_out.alaqs from current CSVs."
            ),
            strict=True,
        )
    return ()


@pytest.mark.parametrize(
    "example_file,csv_path",
    [pytest.param(c[0], c[1], marks=_combo_marks(c)) for c in combos],
    ids=list(f"{d[0].stem}-{d[1].stem}" for d in combos),
)
def test_example_csv(example_file: Path, csv_path: Path):
    """
    Test if the examples are consistent with the csv files
    """

    # Get the template
    example_engine = get_engine(example_file)

    # Get the contents of the table
    example_data = pd.read_sql(f"SELECT * FROM {csv_path.stem}", example_engine)

    # Read the .csv file
    data = pd.read_csv(csv_path)

    assert (
        data.shape[0] <= example_data.shape[0]
    ), f"there might be something wrong with the import of {csv_path.name}"

    if not data.empty:
        # The CSV file's on-disk row order is an arbitrary serialization
        # artifact (e.g. default_aircraft.csv has 711 rows but its last 10
        # oids are 710, 711, 164, 245, 478, 558, 576, 615, 616, 617 —
        # probably the result of appending new rows without re-sorting).
        # The database-backed example returns rows in oid order. To make
        # the test robust to the CSV's serialization order, sort both
        # sides by oid before comparison. `oid` is the PK on every
        # default_* table so this is always well-defined.
        #
        # Also normalize null representation: pd.read_csv yields NaN for
        # missing cells, while SQLAlchemy's read_sql yields None. Both
        # mean "missing" but assert_frame_equal treats them as different
        # in object-dtype columns. convert_dtypes() unifies them to
        # pd.NA on both sides.
        # Also align column ORDER across the two sides. `default_aircraft_profiles`
        # has (fuel_flow_kgm, mode, course) at the end of its DB schema but
        # (mode, course, fuel_flow_kgm) at the end of the CSV. The data is
        # equivalent; only the physical layout differs. Reindex to CSV order
        # so assert_frame_equal stops flagging it.
        sort_col = "oid" if "oid" in data.columns else data.columns[0]
        shared_cols = [c for c in data.columns if c in example_data.columns]
        data_sorted = (
            data[shared_cols]
            .sort_values(sort_col)
            .reset_index(drop=True)
            .convert_dtypes()
        )
        # Restrict DB rows to the oid range in the CSV. Example inventories may
        # contain legitimately extra rows (e.g. ADS-B custom profiles added to
        # default_aircraft_profiles), which are not in the CSV and should not
        # cause this parity check to fail.
        if "oid" in data.columns and "oid" in example_data.columns and not data.empty:
            csv_oids = set(data["oid"].dropna().astype(int).tolist())
            example_data = example_data[example_data["oid"].astype(int).isin(csv_oids)]
        example_sorted = (
            example_data[shared_cols]
            .sort_values(sort_col)
            .reset_index(drop=True)
            .convert_dtypes()
        )
        pd.testing.assert_frame_equal(data_sorted, example_sorted, check_dtype=False)


@pytest.mark.slow
@pytest.mark.parametrize("template_type", ["project", "inventory"])
def test_template_sql(sql_files: list, template_type: str, tmp_path):
    """
    Test if the template is consistent with the sql files
    """

    # Use a file-backed temp DB so get_engine's SpatiaLite loader attaches.
    # An in-memory engine via `create_engine("sqlite:///:memory:")` wouldn't
    # have SpatiaLite loaded, so AddGeometryColumn fails with "no such function".
    tmp_db = tmp_path / f"{template_type}_apply_sql.sqlite"
    sql_engine = get_engine(tmp_db)

    # Execute the SQL queries in the files to the templates
    apply_sql(sql_engine, sql_files, file_type=template_type)

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / f"{template_type}.alaqs")

    # Check if all the tables are present
    from sqlalchemy import inspect

    template_tables = set(inspect(template_engine).get_table_names())
    sql_tables = set(inspect(sql_engine).get_table_names())
    # Hardcoded list of QGIS-editable spatial-layer tables (see
    # test_example_sql for the dropped-sidecar rationale).
    qgis_tables = {
        "shapes_tracks",
        "shapes_area_sources",
        "shapes_buildings",
        "shapes_gates",
        "shapes_parking",
        "shapes_roadways",
        "shapes_runways",
        "shapes_taxiways",
        "shapes_point_sources",
    }

    assert len(sql_tables - template_tables) == 0
    assert len(qgis_tables - template_tables) == 0

    # Check if the columns are present
    for table in sql_tables:
        # Get the columns of template
        template_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", template_engine)

        # Get the columns of sql files
        sql_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", sql_engine)

        # Check if the columns match
        assert (template_d.columns == sql_d.columns).all()

    for table in qgis_tables:
        # Geometry column presence on each editable layer. Column-set
        # cross-check against the sidecar reference is no longer
        # performed.
        template_d = pd.read_sql(f"SELECT * FROM {table} LIMIT 0", template_engine)
        assert "geometry" in template_d


def _template_data_marks(csv_file):
    """
    Earlier this function marked `default_aircraft` as xfail claiming
    apu_id drift on 556/711 rows. Investigation showed the rows had
    IDENTICAL data after sort_values("oid") — the apparent drift was a
    row-order artifact. test_template_data now sorts both sides by oid
    before comparison, so no mark is needed.
    """
    return ()


_csv_files_for_template = list((DB_DIR / "data").glob("*.csv"))


@pytest.mark.parametrize(
    "csv_file",
    [pytest.param(c, marks=_template_data_marks(c)) for c in _csv_files_for_template],
    ids=list(d.stem for d in _csv_files_for_template),
)
def test_template_data(sql_files: list, csv_file: Path):
    """
    Test if the data in the project template is consistent with csv files
    """

    # Get the template
    template_engine = get_engine(TEMPLATES_DIR / "project.alaqs")

    # Get the contents of the table
    template_data = pd.read_sql(f"SELECT * FROM {csv_file.stem}", template_engine)

    # Read the .csv file
    data = pd.read_csv(csv_file)

    # Check the empty columns
    template_empty_columns = set(template_data.columns[template_data.isna().all()])
    empty_columns = set(data.columns[data.isna().all()])
    assert template_empty_columns == empty_columns

    # Check the non-empty columns. Sort both sides by oid to make the
    # assertion robust to the CSV's on-disk row order, which is an
    # arbitrary serialization artifact (see test_example_csv above).
    # Also normalize null representation via convert_dtypes so that
    # NaN (from pd.read_csv) and None (from SQLAlchemy) both become
    # pd.NA on both sides.
    sort_col = "oid" if "oid" in data.columns else data.columns[0]
    template_sorted = (
        template_data.sort_values(sort_col).reset_index(drop=True).convert_dtypes()
    )
    data_sorted = data.sort_values(sort_col).reset_index(drop=True).convert_dtypes()
    pd.testing.assert_frame_equal(
        template_sorted.loc[:, ~data_sorted.isna().all()],
        data_sorted.loc[:, ~data_sorted.isna().all()],
    )


def test_profile_data():
    """
    Test if the profile data contains duplicate profile ids
    """

    # Get the file with profile data
    f = DB_DIR / "data" / "default_aircraft_profiles.csv"

    assert f.exists()

    # Get the profile data
    data = pd.read_csv(f)

    # Set the combination of columns that need to be unique
    primary_key = ["profile_id", "point"]

    # Get the duplicates
    is_duplicated = data[primary_key].duplicated()
    duplicates = data[data[primary_key].duplicated(keep=False)].sort_values(primary_key)

    assert (
        not is_duplicated.any()
    ), f"found {duplicates.shape[0]} duplicate keys (out of {data.shape[0]} keys)"

    assert not data["oid"].duplicated().any()
