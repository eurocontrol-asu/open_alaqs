import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from open_alaqs.alaqs_core.tools.create_output import create_alaqs_output


def spatialite_installed():
    """Create and initialize a geodatabase"""
    try:
        con = sqlite3.connect(":memory:")
        con.enable_load_extension(True)

        # Next line is very important. Without it, mod_spatialite library will not find
        # dlls it depends on.
        # os.environ['PATH'] = SpatiaLitePath + ';' + os.environ['PATH']
        # con.load_extension(os.path.join(SpatiaLitePath, 'mod_spatialite'))
        cur = con.cursor()
        cur.execute("SELECT InitSpatialMetaData(1)")

        con.commit()
        con.close()

        # Spatialite has been installed properly
        installed = True

    except sqlite3.OperationalError:
        # Spatialite hasn't been installed
        installed = False

    return installed


@pytest.mark.skipif(not spatialite_installed(), reason="Spatialite is not available")
def test_create_output():
    # Get the example folder
    example_folder = Path(__file__).parents[1] / "example"

    # Test setup parameters
    test_output_path = example_folder / "test_.alaqs"
    test_movement_path = example_folder / "lfmn_movs.csv"

    # Model parameters come from the calculate UI but for testing, we define
    #  them ourselves
    test_model_parameters = {
        "use_fuel_flow": False,
        "include_parkings": True,
        "include_area_sources": True,
        "include_taxiway_queues": True,
        "use_3d_grid": False,
        "use_variable_mixing_height": False,
        "include_gates": True,
        "z_resolution": 10,
        "study_end_date": datetime(2000, 1, 2, 0, 41),
        "x_resolution": 250,
        "y_resolution": 250,
        "x_cells": 100,
        "include_building": True,
        "study_start_date": datetime(2000, 1, 1, 1, 41),
        "include_roadways": True,
        "towing_speed": 10.0,
        "vertical_limit": 914.4,
        "use_copert": False,
        "movement_path": test_movement_path,
        "z_cells": 100,
        "include_stationary_sources": True,
        "use_smooth_and_shift": True,
        "y_cells": 100,
        "use_nox_correction": False,
    }
    #
    # test_model_parameters["x_cells"] = 1
    # test_model_parameters["y_cells"] = 1
    # test_model_parameters["z_cells"] = 1
    #
    # test_model_parameters["x_resolution"] = 1000000
    # test_model_parameters["y_resolution"] = 1000000
    # test_model_parameters["z_resolution"] = 1000000

    test_study_setup = {
        "airport_latitude": 49.916667,
        "airport_country": "UK",
        "project_name": "CAEPPORT",
        "alaqs_version": "Open-ALAQS",
        "parking_method": "DEFAULT",
        "airport_code": "EGTE",
        "date_modified": "20xx-xx-xx xx:xx:xx",
        "oid": 1,
        "roadway_fleet_year": "2010",
        "airport_name": "CAEPport",
        "roadway_method": "ALAQS Method",
        "vertical_limit": 913,
        "airport_id": 1,
        "airport_longitude": -6.316667,
        "study_info": "test",
        "date_created": "20xx-xx-xx xx:xx:xx",
        "roadway_country": "UK",
        "airport_elevation": 300,
        "airport_temperature": 13,
    }

    create_alaqs_output(test_output_path, test_model_parameters, test_study_setup)
