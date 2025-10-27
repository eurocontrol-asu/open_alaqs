import sqlite3 as sqlite
from pathlib import Path

import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.alaqs import inventory_creation_new
from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.tools.sql_interface import get_db_connection
from tests.utils import get_data_path, get_tmp_path

start_app()


@pytest.fixture(scope="module")
def plugin_instance():
    print("\nINFO: Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    plugin = OpenALAQS(get_iface())
    yield plugin

    print(" [INFO] Tearing down plugin instance")
    plugin.unload()


@pytest.fixture(scope="module")
def datasets_to_test():
    print("\nINFO: Get datasets to test...")
    return [
        {
            "title": "EHRD (Rotterdam, NL) Create Output test",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "expected_db_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "inventory_path": str(get_tmp_path("alaqs_out.alaqs")),
            "met_csv_path": str(get_data_path("EHRD") / "EHRD_meteo.csv"),
            "model_parameters": {
                "movement_path": str(get_data_path("EHRD") / "EHRD_movements.csv"),
                "study_start_date": "2025-12-01 06:00:00",
                "study_end_date": "2025-12-01 07:00:00",
                "towing_speed": 10.0,
                "vertical_limit": 914.4,
                "x_resolution": 250,
                "y_resolution": 250,
                "z_resolution": 10,
                "x_cells": 40,
                "y_cells": 40,
                "z_cells": 20,
                "include_stationary_sources": True,
                "include_parkings": True,
                "include_area_sources": True,
                "include_taxiway_queues": True,
                "include_gates": True,
                "include_building": True,
                "include_roadways": True,
                "use_fuel_flow": False,
                "use_3d_grid": True,
                "use_variable_mixing_height": False,
                "use_nox_correction": False,
                "use_copert": False,
                "use_smooth_and_shift": False,
            },
            "study_setup": {
                "oid": 1,
                "airport_id": 1,
                "alaqs_version": "0.0.1",
                "project_name": "OpenALAQS Training Course",
                "airport_name": "Rotterdam",
                "airport_code": "EHRD",
                "airport_country": "NL",
                "airport_latitude": 51.96,
                "airport_longitude": 4.44,
                "airport_elevation": 0,
                "airport_temperature": 15,
                "vertical_limit": 913,
                "roadway_method": "COPERT 5",
                "roadway_fleet_year": "2020",
                "roadway_country": "Netherlands",
                "parking_method": None,
                "study_info": "Not set",
                "date_created": "2025-05-05 09:06:07",
                "date_modified": "2025-05-12 08:32:45",
            },
        },
    ]


def test_create_output(plugin_instance, datasets_to_test):
    print(" [INFO] Validating Create ALAQS Output...")

    for dataset in datasets_to_test:
        # Check parameter completeness
        assert list(dataset.keys()) == [
            "title",
            "db_path",
            "expected_db_path",
            "inventory_path",
            "met_csv_path",
            "model_parameters",
            "study_setup",
        ]

        # Store the database in-memory for future use
        project_database = ProjectDatabase()
        project_database.path = dataset["db_path"]

        inventory_creation_new(
            dataset["inventory_path"],
            dataset["model_parameters"],
            dataset["study_setup"],
            dataset["met_csv_path"],
        )
        assert Path(dataset["inventory_path"]).exists()

        # Check expected data in the output .alaqs DB
        def get_table_data_from_db(
            db_path: str, table_name: str, fetchone=True
        ) -> list | dict:
            _rows = []
            with get_db_connection(db_path) as _conn:
                _conn.row_factory = sqlite.Row
                _cursor = _conn.cursor()
                _res = _cursor.execute(f"SELECT * FROM {table_name}")
                _rows = _res.fetchone() if fetchone else _res.fetchall()
                _cursor.close()

            return _rows

        # grid_3d_
        row = get_table_data_from_db(dataset["inventory_path"], "grid_3d_definition")
        assert row
        assert row["reference_latitude"] == dataset["study_setup"]["airport_latitude"]
        assert row["reference_longitude"] == dataset["study_setup"]["airport_longitude"]
        assert row["x_resolution"] == dataset["model_parameters"]["x_resolution"]  # 250
        assert row["y_resolution"] == dataset["model_parameters"]["y_resolution"]  # 250
        assert row["z_resolution"] == dataset["model_parameters"]["z_resolution"]  # 10
        assert row["x_cells"] == dataset["model_parameters"]["x_cells"]  # 40
        assert row["y_cells"] == dataset["model_parameters"]["y_cells"]  # 40
        assert row["z_cells"] == dataset["model_parameters"]["z_cells"]  # 20

        # user_ : aircraft_movements, study_setup, taxiroute_taxiways
        study_setup_new = get_table_data_from_db(
            dataset["inventory_path"], "user_study_setup"
        )
        study_setup_expected = get_table_data_from_db(
            dataset["expected_db_path"], "user_study_setup"
        )
        assert study_setup_new == study_setup_expected

        aircraft_movements_new = get_table_data_from_db(
            dataset["inventory_path"], "user_aircraft_movements", False
        )
        aircraft_movements_expected = get_table_data_from_db(
            dataset["expected_db_path"], "user_aircraft_movements", False
        )
        assert aircraft_movements_new == aircraft_movements_expected

        taxiroute_taxiways_new = get_table_data_from_db(
            dataset["inventory_path"], "user_taxiroute_taxiways", False
        )
        taxiroute_taxiways_expected = get_table_data_from_db(
            dataset["expected_db_path"], "user_taxiroute_taxiways", False
        )
        assert taxiroute_taxiways_new == taxiroute_taxiways_expected

        # shapes_
        shapes_area_sources_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_area_sources", False
        )
        shapes_area_sources_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_area_sources", False
        )
        assert shapes_area_sources_new == shapes_area_sources_expected

        shapes_gates_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_gates", False
        )
        shapes_gates_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_gates", False
        )
        assert shapes_gates_new == shapes_gates_expected

        shapes_parking_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_parking", False
        )
        shapes_parking_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_parking", False
        )
        assert shapes_parking_new == shapes_parking_expected

        shapes_point_sources_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_point_sources", False
        )
        shapes_point_sources_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_point_sources", False
        )
        assert shapes_point_sources_new == shapes_point_sources_expected

        shapes_roadways_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_roadways", False
        )
        shapes_roadways_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_roadways", False
        )
        assert shapes_roadways_new == shapes_roadways_expected

        shapes_runways_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_runways", False
        )
        shapes_runways_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_runways", False
        )
        assert shapes_runways_new == shapes_runways_expected

        shapes_taxiways_new = get_table_data_from_db(
            dataset["inventory_path"], "shapes_taxiways", False
        )
        shapes_taxiways_expected = get_table_data_from_db(
            dataset["expected_db_path"], "shapes_taxiways", False
        )
        assert shapes_taxiways_new == shapes_taxiways_expected

        # tbl_
        tbl_inv_meteo_new = get_table_data_from_db(
            dataset["inventory_path"], "tbl_invMeteo", False
        )
        tbl_inv_meteo_expected = get_table_data_from_db(
            dataset["expected_db_path"], "tbl_invMeteo", False
        )
        assert tbl_inv_meteo_new == tbl_inv_meteo_expected

        tbl_inv_time1 = get_table_data_from_db(
            dataset["inventory_path"], "tbl_invTime", False
        )
        tbl_inv_time2 = get_table_data_from_db(
            dataset["expected_db_path"], "tbl_invTime", False
        )
        assert tbl_inv_time1 == tbl_inv_time2

        plugin_instance.run_project_close()
