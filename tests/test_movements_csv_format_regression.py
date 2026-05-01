"""
Regression test for backward-compatible parsing of the movements CSV.

Pre-rebuild Open-ALAQS exported a 21-column movements CSV with a trailing
``domestic`` column that has since been dropped from the schema (it was
never read at runtime). The current export uses a 20-column header with
``gate_emissions_code`` at column 13 and no ``domestic`` column.

Users with a study built on the older plugin can have CSVs in any of these
shapes:

  1. 21-col with header (legacy + gate_emissions_code + domestic)
  2. 20-col with header (current shipped format)
  3. 19-col with no header (legacy positional, pre-gate_emissions_code)

This test locks the loader's behaviour for all three vintages so a future
refactor of ``inventory_insert_movements`` cannot silently start dropping
the user's ``gate_emissions_code`` value (which would produce surprising
emission inflation as default ``gate_emissions_code=1`` re-enables GSE).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from open_alaqs.core.tools.create_output import inventory_insert_movements

REPO = Path(__file__).resolve().parents[1]
INVENTORY_TEMPLATE = REPO / "open_alaqs" / "core" / "templates" / "inventory.alaqs"

LEGACY_HEADER_19 = (
    "runway_time;block_time;aircraft;gate;departure_arrival;runway;engine_name;"
    "profile_id;track_id;taxi_route;tow_ratio;apu_code;taxi_engine_count;"
    "set_time_of_main_engine_start_after_block_off_in_s;"
    "set_time_of_main_engine_start_before_takeoff_in_s;"
    "set_time_of_main_engine_off_after_runway_exit_in_s;"
    "engine_thrust_level_for_taxiing;taxi_fuel_ratio;number_of_stop_and_gos"
)

CURRENT_HEADER_20 = (
    "runway_time;block_time;aircraft;gate;departure_arrival;runway;engine_name;"
    "profile_id;track_id;taxi_route;tow_ratio;apu_code;gate_emissions_code;"
    "taxi_engine_count;set_time_of_main_engine_start_after_block_off_in_s;"
    "set_time_of_main_engine_start_before_takeoff_in_s;"
    "set_time_of_main_engine_off_after_runway_exit_in_s;"
    "engine_thrust_level_for_taxiing;taxi_fuel_ratio;number_of_stop_and_gos"
)

LEGACY_HEADER_21 = LEGACY_HEADER_19 + ";gate_emissions_code;domestic"

# Sample data row, 19 fields (legacy positional)
ROW_19_FIELDS = (
    "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
    "JET-SMALL-A-1;TRACK1;TR1;1;0;1;0;0;0;1.0;1.0;0"
)


@pytest.fixture
def inventory_db(tmp_path):
    """Per-test copy of the inventory template."""
    db = tmp_path / "test_inv.alaqs"
    shutil.copy(INVENTORY_TEMPLATE, db)
    return db


def _load_gec_values(db_path):
    """Read all gate_emissions_code values from the inventory DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        return [
            row[0]
            for row in conn.execute(
                "SELECT gate_emissions_code FROM user_aircraft_movements ORDER BY oid"
            )
        ]
    finally:
        conn.close()


def test_current_20col_csv_with_gec0_preserves_value(inventory_db, tmp_path):
    """The shipped current format must preserve the user's gec value
    verbatim. Regression guard against a refactor that would silently
    rewrite gec to the DB default of 1."""
    csv = tmp_path / "movements_20col.csv"
    csv.write_text(
        CURRENT_HEADER_20 + "\n"
        "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
        "JET-SMALL-A-1;TRACK1;TR1;1;0;0;1;0;0;0;1.0;1.0;0\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert _load_gec_values(inventory_db) == [0]


def test_legacy_21col_csv_strips_domestic_keeps_gec(inventory_db, tmp_path):
    """Pre-rebuild CSVs ended with a trailing 'domestic' column that
    was dropped from the schema. The loader must strip 'domestic'
    without losing the user's gate_emissions_code value (which sat
    just before 'domestic' at column 20)."""
    csv = tmp_path / "movements_21col.csv"
    csv.write_text(
        LEGACY_HEADER_21 + "\n"
        # gec=0, domestic=FALSE
        "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
        "JET-SMALL-A-1;TRACK1;TR1;1;0;1;0;0;0;1.0;1.0;0;0;FALSE\n"
        # gec=1, domestic=TRUE
        "2025-01-01 07:00:00;2025-01-01 07:30:00;A20N;G7;A;06;01P20CM128;"
        "JET-SMALL-A-1;TRACK1;TR1;1;0;1;0;0;0;1.0;1.0;0;1;TRUE\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert _load_gec_values(inventory_db) == [0, 1]


def test_legacy_21col_csv_uppercase_DOMESTIC_also_stripped(inventory_db, tmp_path):
    """Header detection should be case-insensitive on 'DOMESTIC'."""
    csv = tmp_path / "movements_21col_upper.csv"
    csv.write_text(
        LEGACY_HEADER_21.replace("domestic", "DOMESTIC") + "\n"
        "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
        "JET-SMALL-A-1;TRACK1;TR1;1;0;1;0;0;0;1.0;1.0;0;0;false\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert _load_gec_values(inventory_db) == [0]


def test_unrecognised_header_falls_back_to_19col_positional(inventory_db, tmp_path):
    """If the header is mangled or absent (e.g. the CSV was hand-written
    with non-standard column names), the loader falls back to legacy
    positional parsing of the first 19 columns. gate_emissions_code
    then takes the DB default (=1)."""
    csv = tmp_path / "movements_unknown.csv"
    csv.write_text(
        "col1;col2;col3;col4;col5;col6;col7;col8;col9;col10;"
        "col11;col12;col13;col14;col15;col16;col17;col18;col19\n" + ROW_19_FIELDS + "\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert _load_gec_values(inventory_db) == [1]
