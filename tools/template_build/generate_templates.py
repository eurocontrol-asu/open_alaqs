import argparse
import logging
import re
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import sqlalchemy

logging.basicConfig(level=logging.DEBUG)

# Paths: this script now lives at <repo_root>/tools/template_build/.
# - SQL files moved alongside the script: tools/template_build/sql/
# - DATA stays where the runtime expects it: open_alaqs/database/data/
# - TEMPLATES stays where the runtime expects them: open_alaqs/core/templates/
# Hence the asymmetry below: SQL is local; DATA and TEMPLATES point back
# into open_alaqs/.
REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = Path(__file__).parent / "sql"
DATA_DIR = REPO_ROOT / "open_alaqs" / "database" / "data"
TEMPLATES_DIR = REPO_ROOT / "open_alaqs" / "core" / "templates"
BASE_TEMPLATE = Path(__file__).parent / "spatialite_base.alaqs"

# Set the match patterns
MATCH_PATTERNS = {
    "project": r"(shapes|default|user)_(.*).sql",
    "inventory": r"(shapes|default|user|tbl)_(.*).sql",
}


def get_sql_serializable_registry(file_type: str) -> list:
    """SQLSerializable subclasses that own table creation for either or both
    template files. Imports are deferred so this module can be imported by
    the test suite without QGIS libs available.

    Mirrors the registry pattern from upstream PR #303 (Schema streamlining,
    merged April 2026): table schemas live with their domain class, not in
    a separate .sql file. The .sql files in tools/template_build/sql/ now
    only define tables that have no SQLSerializable owner (default_airports,
    shapes_buildings, shapes_receptors, tbl_InvPeriod, user_study_setup, and
    the default_stationary_*, default_vehicle_* reference tables).
    """
    from open_alaqs.core.interfaces.Aircraft import AircraftDatabase
    from open_alaqs.core.interfaces.AircraftTrajectory import (
        AircraftTrajectoryDatabase,
    )
    from open_alaqs.core.interfaces.AmbientCondition import (
        AmbientConditionDatabaseSQL,
    )
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
    # Per-template extras: project-only and inventory-only tables.
    # Currently empty; reserved for future per-template-only schemas.
    template_specific = {
        "project": [],
        "inventory": [],
    }
    return shared + template_specific[file_type]


def check_no_duplicate_sql_definition() -> tuple:
    """Sanity check: a table must not be defined by both a .sql file AND a
    SQLSerializable subclass. Returns (ok, [paths_of_redundant_sql_files]).
    """
    sql_serializables = set(
        get_sql_serializable_registry("project")
        + get_sql_serializable_registry("inventory")
    )
    sql_serializable_tables = [s.TABLE_NAME for s in sql_serializables]
    sql_file_names = [p.stem for p in SQL_DIR.glob("*.sql")]

    duplicates = [
        str(SQL_DIR / f"{name}.sql")
        for name in sql_serializable_tables
        if name in sql_file_names
    ]
    return not bool(duplicates), duplicates


def apply_sqlserializable_registry(template_path: Path, file_type: str) -> None:
    """Create every table owned by a SQLSerializable subclass on
    `template_path`.

    SQLSerializable subclasses are Singletons (first call wins, until
    ``Singleton.reset_all()`` is called). When this helper is invoked from
    the test suite or from a Python session that already has live ``.alaqs``
    instances cached, those caches would point at a stale file. Reset
    Singletons both before AND after this function runs so:

      * the construction below sees a fresh registry (any cached instance
        from earlier in the process won't be reused with the wrong path);
      * downstream code that opens a different ``.alaqs`` file will not
        inherit the temporary-path instances we created here.
    """
    from open_alaqs.core.tools.Singleton import Singleton

    Singleton.reset_all()
    try:
        for cls in get_sql_serializable_registry(file_type):
            # deserialize=False so the constructor does not try to load rows
            # from a file that does not yet exist or is empty.
            instance = cls(str(template_path), deserialize=False)
            instance.recreate_table(str(template_path))
    finally:
        Singleton.reset_all()


def get_engine(p: Path) -> sqlalchemy.engine.Engine:
    # Path.as_uri() always returns 'file:///...' (three slashes), but it only
    # works on absolute paths — it raises ValueError on relative ones. Resolve
    # first so callers can pass either absolute or relative paths. Seven tests
    # (test_copert5, test_copert5_utils, test_template_sql) used to fail here
    # because they pass `Path(__file__).parents[1] / "core/templates" / ...`
    # which is relative at construction time.
    #
    # SQLAlchemy URI convention:
    #   sqlite:///relative/path  (3 slashes) — relative to CWD
    #   sqlite:////absolute/path (4 slashes) — absolute
    # Path.as_uri() produces file:///absolute/path (3 slashes), which after a
    # naive "file:" → "sqlite:" replace becomes sqlite:///absolute/path — which
    # SQLAlchemy interprets as a RELATIVE path, giving it twice the CWD prefix.
    # Build the URI explicitly to avoid that trap.
    p = Path(p).resolve()
    uri = (
        f"sqlite:///{p}" if not p.is_absolute() else f"sqlite:////{str(p).lstrip('/')}"
    )
    engine = sqlalchemy.create_engine(uri)

    # Attach a connection-level listener that loads SpatiaLite into every
    # fresh connection the engine opens. Without this, SELECTs that touch
    # any spatial function (AddGeometryColumn, ST_*, etc.) fail with
    # "no such function" even though the .alaqs file itself is SpatiaLite-
    # enabled. `load_extension` requires enable_load_extension(True) first;
    # best-effort so the engine still works on non-SpatiaLite builds.
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _load_spatialite(dbapi_connection, _connection_record):
        try:
            dbapi_connection.enable_load_extension(True)
            try:
                cur = dbapi_connection.cursor()
                cur.execute("SELECT load_extension('mod_spatialite')")
                cur.close()
            finally:
                dbapi_connection.enable_load_extension(False)
        except Exception:
            # SpatiaLite not available — engine still works for non-spatial queries.
            pass

    return engine


def connect(p: Path, init_spatialite: bool = False) -> sqlite3.Connection:
    logging.info("Connecting to %s...", p)

    conn = sqlite3.connect(p)

    conn.enable_load_extension(True)
    conn.execute("SELECT load_extension('mod_spatialite')")
    conn.enable_load_extension(False)

    if init_spatialite:
        conn.execute("SELECT InitSpatialMetaData()")  # Takes a while (>30s)

    return conn


def _execute_sql_queries(conn, sql_paths, file_type):
    """Execute SQL queries against a raw connection (sqlite3.Connection)."""
    for sql_path in sql_paths:
        if re.search(MATCH_PATTERNS[file_type], sql_path.name) is None:
            continue

        logging.info("Executing SQL file: %s", sql_path.name)

        with sql_path.open() as file:
            sql_queries = file.read()

        for sql_query in sql_queries.split(";"):
            sql_query = sql_query.strip()

            if not sql_query:
                continue

            # for inventory we should not run insert statements into user_ tables
            if (
                file_type == "inventory"
                and sql_path.name.startswith("user_")
                and sql_query.upper().startswith("INSERT INTO")
            ):
                continue

            conn.execute(sql_query)

    conn.commit()


def apply_sql(conn, sql_paths, file_type):
    """Execute SQL schema queries against either a sqlite3.Connection or a
    SQLAlchemy Engine/Connection.  Accepts both to remain compatible with the
    test suite (which uses SQLAlchemy) and the template generation scripts
    (which use sqlite3 directly).

    Args:
        conn: sqlite3.Connection **or** SQLAlchemy Engine/Connection.
        sql_paths: iterable of Path objects pointing to .sql files.
        file_type: 'project' or 'inventory'.
    """
    if file_type not in ("project", "inventory"):
        raise ValueError(
            f"{file_type} is not supported. It should be either 'project' or 'inventory'"
        )

    # Detect SQLAlchemy Engine (has a 'connect' method and no 'cursor' method)
    is_sqla_engine = hasattr(conn, "connect") and not hasattr(conn, "cursor")

    if is_sqla_engine:
        # SQLAlchemy engine -- open a connection and use text() for compatibility
        # with both 1.x and 2.x
        try:
            from sqlalchemy import text as _sa_text
        except ImportError:
            _sa_text = None

        with conn.connect() as sa_conn:
            # Initialize SpatiaLite metadata tables before executing any
            # SQL. Several schema files (shapes_buildings.sql,
            # shapes_receptors.sql) call `SELECT AddGeometryColumn(...)`
            # which requires the metadata tables (`geometry_columns`,
            # `spatial_ref_sys`, etc.) to exist. Without this, those calls
            # fail silently with "unexpected metadata layout" and the
            # resulting schema is missing geometry columns. The `1`
            # argument selects the fast/transaction-based init (~0.1s)
            # instead of the default full init (>30s). Calling it on an
            # already-initialized DB is a no-op, so this is safe.
            if _sa_text is not None:
                sa_conn.execute(_sa_text("SELECT InitSpatialMetaData(1)"))
            else:
                sa_conn.execute("SELECT InitSpatialMetaData(1)")

            for sql_path in sql_paths:
                if re.search(MATCH_PATTERNS[file_type], sql_path.name) is None:
                    continue

                logging.info("Executing SQL file: %s", sql_path.name)

                with sql_path.open() as file:
                    sql_queries = file.read()

                for sql_query in sql_queries.split(";"):
                    sql_query = sql_query.strip()

                    if not sql_query:
                        continue

                    if (
                        file_type == "inventory"
                        and sql_path.name.startswith("user_")
                        and sql_query.upper().startswith("INSERT INTO")
                    ):
                        continue

                    stmt = _sa_text(sql_query) if _sa_text else sql_query
                    sa_conn.execute(stmt)

            try:
                sa_conn.commit()
            except Exception:
                pass  # Some SQLAlchemy versions auto-commit
    else:
        # sqlite3.Connection (or any object with execute/commit)
        _execute_sql_queries(conn, sql_paths, file_type)


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

    # Defensive sanity check: refuse to build if the .sql / SQLSerializable
    # split has drifted into duplication (would cause silent CREATE TABLE
    # races).
    ok, duplicates = check_no_duplicate_sql_definition()
    if not ok:
        raise Exception(
            "The following SQL files have a corresponding SQLSerializable "
            "subclass; one of them is redundant:\n\t" + "\n\t".join(duplicates)
        )

    # Get the path to the project (*.alaqs) and inventory (*_out.alaqs) templates
    base_template = BASE_TEMPLATE
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

    # Phase 1: tables owned by SQLSerializable subclasses (default_aircraft*,
    # default_apu_times, default_emission_dynamics, default_gate_profiles,
    # default_helicopter_engine_ei, shapes_*, user_day/hour/month_profile,
    # user_taxiroute_taxiways, tbl_InvMeteo, tbl_InvTime).
    apply_sqlserializable_registry(project_template, "project")
    apply_sqlserializable_registry(inventory_template, "inventory")

    # Phase 2: remaining tables defined in .sql files (default_airports,
    # default_stationary_*, default_vehicle_*, shapes_buildings,
    # shapes_receptors, tbl_InvPeriod, user_study_setup).
    project_conn = connect(project_template)
    inventory_conn = connect(inventory_template)

    sql_files = list(SQL_DIR.glob("*.sql"))
    apply_sql(project_conn, sql_files, file_type="project")
    apply_sql(inventory_conn, sql_files, file_type="inventory")

    # Phase 3: load default reference data from the data/ CSV directory.
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
