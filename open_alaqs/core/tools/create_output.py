"""
This class is used to create an ALAQS output file from an existing ALAQS study.
"""

import os
import shutil
import sqlite3 as sqlite
from datetime import datetime, timedelta

from open_alaqs.core import alaqsdblite, alaqsutils
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import AmbientConditionStore
from open_alaqs.core.tools import sql_interface
from open_alaqs.core.tools.Grid3D import Grid3D

logger = get_logger(__name__)


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e)

    return wrapper


def create_alaqs_output(inventory_path, model_parameters, study_setup, met_csv_path=""):
    """
    This is the only function in this class that should be called by an external
     function. This function creates a new ALAQS output file based on the
     current study setup, vector layers, and aircraft movements.

    :param inventory_path: the path to the new inventory profile to be created
    :param model_parameters: a dictionary with parameters related to the calculation
    :param study_setup: a dictionary with parameters related to the airport model
    :param met_csv_path: the path to the meteorological data
    :type inventory_path: str
    """

    # model_parameters
    # {'use_fuel_flow': False,
    # 'include_parkings': True,
    # 'include_area_sources': True,
    # 'include_taxiway_queues': True,
    # 'use_3d_grid': False,
    # 'use_variable_mixing_height': False,
    # 'include_gates': True,
    # 'z_resolution': 10,
    # 'study_end_date': datetime.datetime(2000, 1, 2, 0, 41),
    # 'x_resolution': 250,
    # 'y_resolution': 250,
    # 'x_cells': 40,
    # 'include_building': True,
    # 'study_start_date': datetime.datetime(2000, 1, 1, 1, 41),
    # 'include_roadways': True,
    # 'towing_speed': 10.0,
    # 'vertical_limit': 914.4,
    # 'use_copert': False,
    # 'movement_path': os.path.join("..", "example", "movements_exeter.csv"),
    # 'z_cells': 20,
    # 'include_stationary_sources': True,
    # 'use_smooth_and_shift': False,
    # 'y_cells': 40,
    # 'use_nox_correction': False}

    # study_setup
    # {'airport_latitude': 50.734444,
    # 'airport_country': 'UK',
    # 'project_name': 'Exeter Airport',
    # 'alaqs_version': '0.0.1',
    # 'parking_method': 'DEFAULT',
    # 'airport_code': 'EGTE',
    # 'date_modified': '2014-01-24 14:37:57',
    # 'oid': 1,
    # 'roadway_fleet_year': '2010',
    # 'airport_name': 'Exeter',
    # 'roadway_method': 'ALAQS Method',
    # 'vertical_limit': 913,
    # 'airport_id': 1,
    # 'airport_longitude': -3.413889,
    # 'study_info': 'This is my demo project.',
    # 'date_created': '2014-01-24 14:35:32',
    # 'roadway_country': 'UK',
    # 'airport_elevation': 100,
    # 'airport_temperature': 15}

    result = inventory_create_blank(inventory_path)
    if result is False:
        pass

    inventory_update_tbl_inv_period(inventory_path, model_parameters, study_setup)
    inventory_update_tbl_inv_time(inventory_path, model_parameters)
    inventory_insert_movements(inventory_path, model_parameters)
    inventory_update_mixing_heights(inventory_path)
    inventory_copy_activity_profiles(inventory_path)
    inventory_copy_vector_layers(inventory_path)
    inventory_copy_aircraft(inventory_path)
    inventory_copy_aircraft_engine_ei(inventory_path)
    inventory_copy_gate_profiles(inventory_path)
    inventory_copy_aircraft_start_ef(inventory_path)
    inventory_copy_stationary_substance(inventory_path)
    inventory_copy_stationary_category(inventory_path)
    inventory_copy_aircraft_engine_mode(inventory_path)
    inventory_copy_aircraft_profiles(inventory_path)
    inventory_copy_taxiway_routes(inventory_path)
    inventory_copy_emission_dynamics(inventory_path)
    inventory_copy_study_setup(inventory_path)

    # Set the tables to copy
    copy_tables = [
        "default_airports",
        "default_stationary_ef",
        "default_apu_times",
        "default_vehicle_fleet_euro_standards",
        "default_aircraft_apu_ef",
        "default_vehicle_ef_copert5",
        # 5.2.0: helicopter catalog tables. The inventory template ships these
        # empty; populate from the source project so HelicopterStore can
        # resolve helicopter ICAOs/variant_labels during emission calculation.
        # Without these copies the helicopter dispatch path falls back to
        # AircraftStore, which can't find helicopter aircraft either since
        # the 5.2.0 default_aircraft.csv has no HELICOPTER rows -- net effect
        # is "Aircraft 'AS50' wasn't found in the DB" and the movement is
        # dropped from the inventory.
        "default_helicopter",
        "default_helicopter_engines",
    ]
    for table in copy_tables:
        inventory_copy_generic_table(inventory_path, table)

    # 3D Grid configuration
    grid_configuration_ = {
        "x_cells": 10,
        "y_cells": 10,
        "z_cells": 1,
        "x_resolution": 100,
        "y_resolution": 100,
        "z_resolution": 100,
        "reference_latitude": "0.0",  # airport_latitude
        "reference_longitude": "0.0",  # airport_longitude
    }

    grid_cells_header = [
        "x_resolution",
        "y_resolution",
        "z_resolution",
        "x_cells",
        "y_cells",
        "z_cells",
    ]
    for head in grid_cells_header:
        if head not in model_parameters:
            raise Exception("Did not find '%s' in '%s'." % (head, "model_parameters"))
        grid_configuration_[head] = model_parameters[head]

    grid_cells_header = ["airport_latitude", "airport_longitude"]
    for head in grid_cells_header:
        if head not in study_setup:
            raise Exception("Did not find '%s' in '%s'." % (head, "study_setup"))
        grid_configuration_[head.replace("airport", "reference")] = study_setup[head]

    # add grid configuration to sqlite database
    grid = Grid3D(inventory_path, grid_configuration_, deserialize=False)
    # add grid to the database
    grid.serialize()

    # save ambient conditions to database
    if met_csv_path:
        store = AmbientConditionStore(inventory_path, init_csv_path=met_csv_path)
        store.serialize()

    logger.info(
        "New output file with path '%s' has been created" % (str(inventory_path))
    )


@catch_errors
def inventory_create_blank(inventory_name):
    """
    Copy a blank version of the ALAQS inventory to the desired location
    :param inventory_name: the path where the inventory file is to be copied
    :return: None if successful, error otherwise
    """
    shutil.copy2(
        os.path.join(os.path.dirname(__file__), "../templates/inventory.alaqs"),
        inventory_name,
    )
    msg = "[+] Created a blank ALAQS output file"
    logger.info(msg)


@catch_errors
def inventory_copy_generic_table(inventory_path, table: str):
    """
    This function copies data from the currently active project to the inventory output file

    :param inventory_path:
    :param table:
    :return:
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    table_data = alaqsdblite.query_string(f"SELECT * FROM {table};")
    if len(table_data) > 0:
        column_count = len(table_data[0])
        cur.executemany(
            f'INSERT INTO {table} VALUES ({",".join(["?"] * column_count)});',
            table_data,
        )
        conn.commit()
    conn.close()
    msg = f"[+] Copied the {table} table"
    logger.info(msg)


@catch_errors
def inventory_update_tbl_inv_period(database_path, model_parameters, study_setup):
    """
    Add records to the study output that lists one-hour intervals for the whole of the user defined study duration
    :param database_path: the path to the study output file
    :param model_parameters: a list of model parameters used to generate an ALAQS output
    """

    try:
        min_time = datetime.strptime(
            model_parameters["study_start_date"], "%Y-%m-%d %H:%M:%S"
        )
        max_time = datetime.strptime(
            model_parameters["study_end_date"], "%Y-%m-%d %H:%M:%S"
        )
    except Exception:
        min_time = datetime.strftime(
            model_parameters["study_start_date"], "%Y-%m-%d %H:%M:%S"
        )
        max_time = datetime.strftime(
            model_parameters["study_end_date"], "%Y-%m-%d %H:%M:%S"
        )

    logger.info("Min time: %s" % min_time)
    logger.info("Max time: %s" % max_time)

    interval = 1 / 24
    temp_isa = 273.16 + 15 + study_setup["airport_elevation"] / 1000 * -6.5
    copert = 0
    nox_corr = 0
    ffm = 0
    mix_height = 0
    smsh = 0

    if model_parameters["use_copert"] is True:
        copert = 1
    if model_parameters["use_nox_correction"] is True:
        nox_corr = 1
    if model_parameters["use_fuel_flow"] is True:
        ffm = 1
    if model_parameters["use_smooth_and_shift"] is True:
        smsh = 1
    if model_parameters["use_variable_mixing_height"] is True:
        mix_height = 1

    sql_interface.query_text(
        database_path,
        "UPDATE tbl_InvPeriod SET interval=%d, temp_isa=%d, vert_limit=%d, apt_elev=%d, "
        'copert=%d, nox_corr=%d, ffm=%d, smsh=%d, mix_height=%d, min_time="%s", '
        'max_time="%s";'
        % (
            interval,
            temp_isa,
            model_parameters["vertical_limit"],
            study_setup["airport_elevation"],
            copert,
            nox_corr,
            ffm,
            smsh,
            mix_height,
            min_time,
            max_time,
        ),
    )
    msg = "[+] Updated the output inventory period"
    logger.info(msg)


@catch_errors
def inventory_update_tbl_inv_time(inventory_path, model_parameters):
    """
    Update the invTime table with hourly intervals based on the user study definitions
    :param inventory_path: a path to the alaqs study output file
    :param model_parameters: a dict of user defined parameters for the current output
    :return:
    """
    time_list = []
    hour_delta = timedelta(hours=1)
    try:
        start_time = datetime.strptime(
            model_parameters["study_start_date"], "%Y-%m-%d %H:%M:%S"
        )
        end_time = datetime.strptime(
            model_parameters["study_end_date"], "%Y-%m-%d %H:%M:%S"
        )
    except Exception:
        start_time = model_parameters["study_start_date"]
        end_time = model_parameters["study_end_date"]

    # Create a time stamp for the start of the first hour - kind of floor(start_time)
    current_hour = start_time - timedelta(
        minutes=start_time.minute % 60,
        seconds=start_time.second,
        microseconds=start_time.microsecond,
    )

    # Build a list of hours we need to model
    while current_hour <= end_time:
        interval_start = current_hour
        mix_height = "914.4"

        time_list.append([interval_start, mix_height])
        current_hour = current_hour + hour_delta

    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO tbl_InvTime (time, mix_height) VALUES (?,?);",
        time_list,
    )
    conn.commit()
    conn.close()
    msg = "[+] Updated the output time table"
    logger.info(msg)


@catch_errors
def inventory_insert_movements(inventory_name, model_parameters):
    """
    Insert user defined movement table into the alaqs output file
    :param inventory_name: path to the alaqs output file
    :param model_parameters: a list of user defined model parameters used to generate the study output
    """

    conn = sqlite.connect(inventory_name)
    cur = conn.cursor()

    # Movement CSVs may or may not include the optional gate_emissions_code
    # column, depending on when they were exported.  We detect the schema
    # from the header row rather than by column count alone, so custom
    # column orderings are tolerated too.
    LEGACY_COLS = [
        "runway_time",
        "block_time",
        "aircraft",
        "gate",
        "departure_arrival",
        "runway",
        "engine_name",
        "profile_id",
        "track_id",
        "taxi_route",
        "tow_ratio",
        "apu_code",
        "taxi_engine_count",
        "set_time_of_main_engine_start_after_block_off_in_s",
        "set_time_of_main_engine_start_before_takeoff_in_s",
        "set_time_of_main_engine_off_after_runway_exit_in_s",
        "engine_thrust_level_for_taxiing",
        "taxi_fuel_ratio",
        "number_of_stop_and_gos",
    ]

    with open(model_parameters["movement_path"], "rt") as movements:
        header = movements.readline().strip().split(";")
        # Strip BOM if present
        if header and header[0].startswith("\ufeff"):
            header[0] = header[0][1:]

        # Column names present in this CSV (excluding the synthetic oid)
        csv_cols = [h.strip() for h in header]

        # Backward compatibility: pre-rebuild CSVs ended with a `domestic`
        # column that has been dropped from the schema (it was unused at
        # runtime). Strip it both from the header and from each data row,
        # so we don't lose the user's `gate_emissions_code` (col 20 in
        # those files) by falling through to the legacy positional fallback.
        drop_trailing_domestic = (
            len(csv_cols) > 0 and csv_cols[-1].lower() == "domestic"
        )
        if drop_trailing_domestic:
            csv_cols = csv_cols[:-1]

        known_cols = set(LEGACY_COLS) | {"gate_emissions_code"}
        if not set(csv_cols).issubset(known_cols) or not set(LEGACY_COLS).issubset(
            set(csv_cols)
        ):
            # Fall back to legacy positional assumption when header is
            # missing/unexpected (preserves pre-rebuild behaviour).
            csv_cols = LEGACY_COLS[:]
            drop_trailing_domestic = False

        all_movements = []
        movement_line = 0
        for raw in movements:
            movement_line += 1
            fields = raw.strip().split(";")
            # Drop the trailing 'domestic' field if header had it.
            if drop_trailing_domestic and len(fields) > len(csv_cols):
                fields = fields[: len(csv_cols)]
            # Pad to header length in case of trailing empty fields trimmed
            # by strip()+split.
            if len(fields) < len(csv_cols):
                fields += [""] * (len(csv_cols) - len(fields))
            row_dict = dict(zip(csv_cols, fields))
            row_dict["oid"] = movement_line
            all_movements.append(row_dict)

    n_rows = len(all_movements)
    if n_rows > 0:
        # Explicit column list.  Includes gate_emissions_code only when the
        # source CSV had it; otherwise the DB column takes its DEFAULT 1.
        base_cols = ["oid"] + LEGACY_COLS
        if "gate_emissions_code" in csv_cols:
            base_cols.append("gate_emissions_code")

        placeholders = ",".join(["?"] * len(base_cols))
        values_list = [tuple(m.get(c, "") for c in base_cols) for m in all_movements]
        cur.executemany(
            f"INSERT INTO user_aircraft_movements ({', '.join(base_cols)}) "
            f"VALUES ({placeholders})",
            values_list,
        )
        conn.commit()
    msg = f"[+] Aircraft movements copied to output file ({n_rows} rows)"
    conn.close()
    logger.info(msg)


@catch_errors
def inventory_copy_study_setup(inventory_path):
    """
    This function copies data from the currently active project to the inventory output file

    :param inventory_path:
    :return:
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()

    study_setup_data = alaqsdblite.query_string("SELECT * FROM user_study_setup;")
    cur.execute(
        "INSERT INTO user_study_setup VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);",
        study_setup_data[0],
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied the study setup"
    logger.info(msg)


def inventory_update_mixing_heights(inventory_path):
    # fix_print_with_import
    print("Need to update mixing heights using study_setup")


@catch_errors
def inventory_copy_activity_profiles(inventory_path) -> None:
    """
    Copy all activity profiles from the currently active project database to the output file
    :param inventory_path: path ot the alaqs output file
    """

    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()

    # Get the hourly, daily and monthly activity profiles
    hourly_activity_profiles = alaqsdblite.query_string(
        "SELECT * FROM user_hour_profile;"
    )
    daily_activity_profiles = alaqsdblite.query_string(
        "SELECT * FROM user_day_profile;"
    )
    monthly_activity_profiles = alaqsdblite.query_string(
        "SELECT * FROM user_month_profile;"
    )

    # Set the hourly, daily and monthly activity profiles
    cur.executemany(
        "INSERT INTO user_hour_profile VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        hourly_activity_profiles,
    )
    cur.executemany(
        "INSERT INTO user_day_profile VALUES (?,?,?,?,?,?,?,?,?)",
        daily_activity_profiles,
    )
    cur.executemany(
        "INSERT INTO user_month_profile VALUES " "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        monthly_activity_profiles,
    )

    conn.commit()
    conn.close()

    logger.info("[+] Copied the activity profiles")


@catch_errors
def inventory_copy_gate_profiles(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    gate_profiles = alaqsdblite.query_string("SELECT * FROM default_gate_profiles;")
    cur.executemany(
        "INSERT INTO default_gate_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        gate_profiles,
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied the gate profiles"
    logger.info(msg)


@catch_errors
def inventory_copy_emission_dynamics(inventory_path):
    """
    Copy all emission_dynamics from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    emission_dynamics = alaqsdblite.query_string(
        "SELECT * FROM default_emission_dynamics;"
    )
    cur.executemany(
        "INSERT INTO default_emission_dynamics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        emission_dynamics,
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied the emission dynamics"
    logger.info(msg)


@catch_errors
def inventory_copy_taxiway_routes(inventory_path):
    """
    Copy all taxiway routes from the currently active project database to alaqs output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    gate_profiles = alaqsdblite.query_string("SELECT * FROM user_taxiroute_taxiways;")
    cur.executemany(
        "INSERT INTO user_taxiroute_taxiways VALUES (?,?,?,?,?,?,?,?)", gate_profiles
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied the taxiway routes"
    logger.info(msg)


def inventory_copy_vector_layers(inventory_path):
    """
    Copy all vector layers from the currently active alaqs project file to the output file
    :param inventory_path: path to the alaqs output file
    """

    try:
        conn = sql_interface.connect(inventory_path)
        curs = conn.cursor()

        try:
            area_sources = alaqsdblite.query_string(
                "SELECT * FROM shapes_area_sources;"
            )
            curs.executemany(
                "INSERT INTO shapes_area_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                area_sources,
            )
            conn.commit()
            msg = "[+] Area sources copied to output file"
            logger.info(msg)

        except Exception as e:
            # fix_print_with_import
            print(e)
            msg = "Problem copying area sources: %s" % e
            logger.error(msg)

        try:
            buildings = alaqsdblite.query_string("SELECT * FROM shapes_buildings;")
            curs.executemany(
                "INSERT INTO shapes_buildings VALUES (?,?,?,?,?)", buildings
            )
            conn.commit()
            msg = "[+] Buildings copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying buildings: %s" % e
            logger.error(msg)

        try:
            gates = alaqsdblite.query_string("SELECT * FROM shapes_gates;")
            curs.executemany("INSERT INTO shapes_gates VALUES (?,?,?,?,?,?)", gates)
            conn.commit()
            msg = "[+] Gates copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying gates: %s" % e
            logger.error(msg)

        try:
            parking = alaqsdblite.query_string("SELECT * FROM shapes_parking;")
            curs.executemany(
                "INSERT INTO shapes_parking VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                parking,
            )
            conn.commit()
            msg = "[+] Parkings copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying parking: %s" % e
            logger.error(msg)

        try:
            receptors = alaqsdblite.query_string(
                "SELECT * FROM shapes_receptor_points;"
            )
            curs.executemany(
                "INSERT INTO shapes_receptor_points VALUES (?,?,?,?,?,?,?)", receptors
            )
            conn.commit()
            msg = "[+] Receptor points copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying receptor points: %s" % e
            logger.error(msg)

        # try:
        #     receptors = alaqsdblite.query_string("SELECT * FROM shapes_receptors;")
        #     curs.executemany('INSERT INTO shapes_receptors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', receptors)
        #     conn.commit()
        #     msg = "[+] Receptors copied to output file"
        #     logger.info(msg)
        #
        # except Exception as e:
        #     msg = "Problem copying receptors: %s" % e
        #     logger.error(msg)

        try:
            roadways = alaqsdblite.query_string("SELECT * FROM shapes_roadways;")
            curs.executemany(
                "INSERT INTO shapes_roadways VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                roadways,
            )
            conn.commit()
            msg = "[+] Roadways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying roadways: %s" % e
            logger.error(msg)

        try:
            # Schema-robust copy: source projects predating the session-22
            # simplification still have 8 cols in shapes_runways (with
            # max_queue_speed and peak_queue_time, since dropped). Select only
            # the destination cols so legacy files copy cleanly.
            dst_cols = [r[1] for r in curs.execute("PRAGMA table_info(shapes_runways)")]
            src_db_path = alaqsdblite.ProjectDatabase().path
            with sqlite.connect(src_db_path) as src_conn:
                src_cols = [
                    r[1] for r in src_conn.execute("PRAGMA table_info(shapes_runways)")
                ]
            common = [c for c in dst_cols if c in src_cols]
            col_list = ", ".join(f'"{c}"' for c in common)
            placeholders = ",".join("?" * len(common))
            runways = alaqsdblite.query_string(
                f"SELECT {col_list} FROM shapes_runways;"
            )
            curs.executemany(
                f"INSERT INTO shapes_runways ({col_list}) VALUES ({placeholders})",
                runways,
            )
            conn.commit()
            msg = "[+] Runways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying runways: %s" % e
            logger.error(msg)

        try:
            # Use explicit column names in both SELECT and INSERT so the
            # copy is robust to schema-evolution column-order differences
            # between source and target (e.g. activity_unit was appended to
            # shapes_point_sources by ALTER TABLE on migrated v1 studies,
            # putting it after geometry, whereas the v2 template defines it
            # before geometry).
            _ps_cols = (
                "oid, source_id, height, category, point_type, substance, "
                "temperature, diameter, velocity, ops_year, "
                "hour_profile, daily_profile, month_profile, "
                "co_kg_k, hc_kg_k, nox_kg_k, sox_kg_k, pm10_kg_k, "
                "p1_kg_k, p2_kg_k, instudy, activity_unit, geometry"
            )
            _ps_placeholders = ",".join(["?"] * 23)
            point_sources = alaqsdblite.query_string(
                f"SELECT {_ps_cols} FROM shapes_point_sources;"
            )
            curs.executemany(
                f"INSERT INTO shapes_point_sources ({_ps_cols}) "
                f"VALUES ({_ps_placeholders})",
                point_sources,
            )
            conn.commit()
            msg = "[+] Point sources copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying point sources: %s" % e
            logger.error(msg)

        try:
            taxiways = alaqsdblite.query_string("SELECT * FROM shapes_taxiways;")
            curs.executemany(
                "INSERT INTO shapes_taxiways VALUES (?,?,?,?,?,?)", taxiways
            )
            conn.commit()
            msg = "[+] Taxiways copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying taxiways: %s" % e
            logger.error(msg)

        try:
            tracks = alaqsdblite.query_string("SELECT * FROM shapes_tracks;")
            curs.executemany("INSERT INTO shapes_tracks VALUES (?,?,?,?,?,?)", tracks)
            conn.commit()
            msg = "[+] Tracks copied to output file"
            logger.info(msg)

        except Exception as e:
            msg = "Problem copying tracks: %s" % e
            logger.error(msg)

        msg = "[+] Copied all vector layers"
        logger.info(msg)
    except Exception as e:
        error_msg = alaqsutils.print_error(
            inventory_copy_activity_profiles.__name__, Exception, e
        )
        logger.error(error_msg)
        return error_msg
    finally:
        conn.close()


@catch_errors
def inventory_copy_aircraft(inventory_path):
    """
    We only need to take forward data on the aircraft that are in the movement
     table.
    :param inventory_path: the path of the inventory file being written to
    """
    # Establish a connection
    conn = sqlite.connect(inventory_path)
    conn.text_factory = str
    cur = conn.cursor()

    data = alaqsdblite.query_string("SELECT * FROM default_aircraft;")
    cur.executemany(
        "INSERT INTO default_aircraft VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data
    )

    # movement_aircraft = alaqsdblite.query_string("SELECT DISTINCT aircraft FROM user_aircraft_movements;")
    # #for aircraft_name in movement_aircraft:
    #
    #    # Get details of this aircraft from the main project database
    #    sql_text = "SELECT * FROM default_aircraft WHERE icao=\"%s\";" % aircraft_name
    #    data = alaqsdblite.query_string(sql_text)
    #    # insert into the output
    #    curs.executemany('INSERT INTO default_aircraft VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', data)

    # House keeping
    conn.commit()
    conn.close()
    msg = "[+] Copied unique aircraft data"
    logger.info(msg)


@catch_errors
def inventory_copy_aircraft_engine_ei(inventory_path):
    """
    We only need to take forward data on the engine ei that are in the movement table.
    :param inventory_path: the path of the inventory file being written to
    """
    # Establish a connection
    conn = sqlite.connect(inventory_path)
    curs = conn.cursor()
    conn.text_factory = str

    # Schema-robust INSERT: read the destination schema first, then SELECT only
    # the matching columns from the source project DB. This works whether the
    # source has fewer or more columns than the destination (e.g. when MEEM
    # columns were added to the schema in 5.2.0 some user projects predate
    # them). Source-only columns are dropped, destination-only columns are left
    # NULL by SQLite.
    dst_cols = [
        r[1] for r in curs.execute("PRAGMA table_info(default_aircraft_engine_ei)")
    ]
    src_db_path = alaqsdblite.ProjectDatabase().path
    with sqlite.connect(src_db_path) as src_conn:
        src_cols = [
            r[1]
            for r in src_conn.execute("PRAGMA table_info(default_aircraft_engine_ei)")
        ]
    common_cols = [c for c in dst_cols if c in src_cols]
    col_list_sql = ", ".join(f'"{c}"' for c in common_cols)
    placeholders = ",".join("?" * len(common_cols))

    aircraft_engines = alaqsdblite.query_string(
        "SELECT DISTINCT engine_name FROM default_aircraft_engine_ei;"
    )

    # query_string returns a list of tuples like [(engine_name,), ...] -- unpack
    # the first element rather than f-string-formatting the tuple, which would
    # produce a literal "('engine_name',)" in the SQL and match zero rows.
    for row in aircraft_engines:
        engine = row[0] if row else None
        if not engine:
            continue
        # Use parameterized query (handles SQL injection and tuple formatting in one step).
        sql_text = (
            f"SELECT {col_list_sql} FROM default_aircraft_engine_ei "
            f"WHERE engine_name = ?;"
        )
        with sqlite.connect(src_db_path) as src_conn:
            data = src_conn.execute(sql_text, (engine,)).fetchall()
        curs.executemany(
            f"INSERT INTO default_aircraft_engine_ei ({col_list_sql}) "
            f"VALUES ({placeholders})",
            data,
        )
    # House keeping
    conn.commit()
    conn.close()

    msg = "[+] Copied unique aircraft engine data"
    logger.info(msg)


@catch_errors
def inventory_copy_aircraft_profiles(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    profiles = alaqsdblite.query_string("SELECT * FROM default_aircraft_profiles;")
    cur.executemany(
        "INSERT INTO default_aircraft_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        profiles,
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied aircraft profiles"
    logger.info(msg)


@catch_errors
def inventory_copy_aircraft_start_ef(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    start_ef = alaqsdblite.query_string("SELECT * FROM default_aircraft_start_ef;")
    cur.executemany(
        "INSERT INTO default_aircraft_start_ef VALUES (?,?,?,?,?,?,?,?,?,?,?)", start_ef
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied unique aircraft start emissions"
    logger.info(msg)


@catch_errors
def inventory_copy_stationary_substance(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    start_ef = alaqsdblite.query_string("SELECT * FROM default_stationary_substance;")
    cur.executemany("INSERT INTO default_stationary_substance VALUES (?,?,?)", start_ef)
    conn.commit()
    conn.close()
    msg = "[+] Copied stationary substances"
    logger.info(msg)


@catch_errors
def inventory_copy_stationary_category(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    start_ef = alaqsdblite.query_string("SELECT * FROM default_stationary_category;")
    cur.executemany("INSERT INTO default_stationary_category VALUES (?,?,?)", start_ef)
    conn.commit()
    conn.close()
    msg = "[+] Copied stationary categories"
    logger.info(msg)


@catch_errors
def inventory_copy_aircraft_engine_mode(inventory_path):
    """
    Copy all gate profiles from the currently active alaqs project database to the output file
    :param inventory_path: path to the alaqs output file
    """
    conn = sqlite.connect(inventory_path)
    cur = conn.cursor()
    start_ef = alaqsdblite.query_string("SELECT * FROM default_aircraft_engine_mode;")
    cur.executemany(
        "INSERT INTO default_aircraft_engine_mode VALUES (?,?,?,?)", start_ef
    )
    conn.commit()
    conn.close()
    msg = "[+] Copied unique aircraft engine modes"
    logger.info(msg)
