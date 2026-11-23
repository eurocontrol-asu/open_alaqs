"""
Regression test: Calculate Emissions Inventory writes the period row of
tbl_InvPeriod.

The inventory template ships tbl_InvPeriod empty and
create_output.inventory_update_tbl_inv_period ran an UPDATE on it, which
affects no row, so no inventory carried its period (min_time, max_time) and
settings. Readers of the row (the Dataiku recipe derives the study year from
min_time) then failed with "tbl_InvPeriod is empty".
"""

import sqlite3
from datetime import datetime

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.alaqs import inventory_creation_new  # noqa: E402
from open_alaqs.core.alaqsdblite import ProjectDatabase  # noqa: E402
from open_alaqs.core.tools.Singleton import Singleton  # noqa: E402
from tests.utils import get_data_path, get_tmp_path  # noqa: E402

MODEL_PARAMETERS = {
    "movement_path": str(get_data_path("AIRPORT_A") / "AIRPORT_A_movements.csv"),
    "study_start_date": "2025-12-01 06:00:00",
    "study_end_date": "2025-12-03 09:00:00",
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
    "use_fuel_flow": True,
    "use_3d_grid": True,
    "use_variable_mixing_height": False,
    "use_nox_correction": True,
    "use_copert": False,
    "use_smooth_and_shift": False,
}

STUDY_SETUP = {
    "oid": 1,
    "airport_id": 1,
    "alaqs_version": "0.0.1",
    "project_name": "OpenALAQS Training Course",
    "airport_name": "Rotterdam",
    "airport_code": "EHRD",
    "airport_country": "NL",
    "airport_latitude": 51.96,
    "airport_longitude": 4.44,
    "airport_elevation": -5,
    "airport_temperature": 15,
    "vertical_limit": 914.4,
    "roadway_method": "COPERT 5",
    "roadway_fleet_year": "2020",
    "roadway_country": "Netherlands",
    "parking_method": "Open-ALAQS",
    "study_info": "",
    "date_created": "2026-04-20 00:00:00",
    "date_modified": "2026-04-20 00:00:00",
}


def _period_rows(inventory_path):
    conn = sqlite3.connect(inventory_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM tbl_InvPeriod")]
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _fresh_singletons():
    # The stores (AmbientConditionStore, ...) are process-wide singletons
    # bound to the first inventory they open: reset them around this test so
    # it neither reads nor leaves another test's state.
    Singleton.reset_all()
    yield
    Singleton.reset_all()


def test_inventory_has_one_period_row():
    ProjectDatabase().path = str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs")
    inventory_path = str(get_tmp_path("inv_period_out.alaqs"))
    inventory_creation_new(
        inventory_path,
        MODEL_PARAMETERS,
        STUDY_SETUP,
        str(get_data_path("AIRPORT_A") / "AIRPORT_A_meteo.csv"),
    )

    rows = _period_rows(inventory_path)
    assert len(rows) == 1, rows
    row = rows[0]
    assert datetime.fromisoformat(row["min_time"]) == datetime(2025, 12, 1, 6)
    assert datetime.fromisoformat(row["max_time"]) == datetime(2025, 12, 3, 9)
    assert row["apt_elev"] == -5
    assert row["vert_limit"] == 914.4
    assert row["interval"] == 1 / 24
    assert (
        row["copert"],
        row["nox_corr"],
        row["ffm"],
        row["mix_height"],
        row["smsh"],
    ) == (
        0,
        1,
        1,
        0,
        0,
    )
