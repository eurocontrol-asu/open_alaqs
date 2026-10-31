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


# 20 fields in the documented order: gate_emissions_code=0 at column 13,
# taxi_engine_count=1 at column 14.
ROW_20_FIELDS = (
    "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
    "JET-SMALL-A-1;TRACK1;TR1;1;0;0;1;0;0;0;1.0;1.0;0"
)


def _load_cols(db_path, cols):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            f"SELECT {', '.join(cols)} FROM user_aircraft_movements ORDER BY oid"
        ).fetchall()
    finally:
        conn.close()


def test_misspelt_header_20col_row_read_in_documented_order(inventory_db, tmp_path):
    """A 20-column file with one misspelt header name is read by position
    in the documented 20-column order, not shifted from column 13 on."""
    csv = tmp_path / "movements_misspelt.csv"
    csv.write_text(
        CURRENT_HEADER_20.replace("taxi_route", "taxiroute")
        + "\n"
        + ROW_20_FIELDS
        + "\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    rows = _load_cols(
        inventory_db,
        [
            "taxi_route",
            "apu_code",
            "gate_emissions_code",
            "taxi_engine_count",
            "engine_thrust_level_for_taxiing",
            "taxi_fuel_ratio",
            "number_of_stop_and_gos",
        ],
    )
    assert len(rows) == 1
    route, apu, gec, n_eng, thrust, ratio, stops = rows[0]
    assert route == "TR1"
    assert int(apu) == 0
    assert int(gec) == 0
    assert int(n_eng) == 1
    assert float(thrust) == 1.0
    assert float(ratio) == 1.0
    assert int(stops) == 0


def test_positional_mixed_19_and_20_field_rows(inventory_db, tmp_path):
    """Rows are read per row: 20 fields in the documented order, 19 fields
    in the legacy order (gate_emissions_code then takes the default 1)."""
    csv = tmp_path / "movements_mixed.csv"
    csv.write_text("bad;header\n" + ROW_20_FIELDS + "\n" + ROW_19_FIELDS + "\n")
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    rows = _load_cols(inventory_db, ["gate_emissions_code", "taxi_engine_count"])
    assert [(int(g), int(n)) for g, n in rows] == [(0, 1), (1, 1)]


def test_positional_fallback_logs_warning_naming_headers(
    inventory_db, tmp_path, monkeypatch
):
    """Falling back to positional reading logs a warning that names the
    unknown and missing header(s)."""
    from open_alaqs.core.tools import create_output

    messages = []
    monkeypatch.setattr(
        create_output.logger,
        "warning",
        lambda msg, *args, **kw: messages.append(msg % args if args else msg),
    )
    csv = tmp_path / "movements_misspelt.csv"
    csv.write_text(
        CURRENT_HEADER_20.replace("taxi_route", "taxiroute")
        + "\n"
        + ROW_20_FIELDS
        + "\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert len(messages) == 1
    assert "taxiroute" in messages[0]
    assert "taxi_route" in messages[0]


def test_valid_header_logs_no_warning(inventory_db, tmp_path, monkeypatch):
    """Files with correct headers are read by name, without a warning."""
    from open_alaqs.core.tools import create_output

    messages = []
    monkeypatch.setattr(
        create_output.logger,
        "warning",
        lambda msg, *args, **kw: messages.append(msg),
    )
    csv = tmp_path / "movements_20col.csv"
    csv.write_text(CURRENT_HEADER_20 + "\n" + ROW_20_FIELDS + "\n")
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    assert messages == []
    assert _load_gec_values(inventory_db) == [0]


# Pre-rebuild layout without gate_emissions_code: legacy 19 columns, then
# `domestic` (20 fields). taxi_engine_count=2 at column 13.
ROW_19_PLUS_DOMESTIC = (
    "2025-01-01 06:00:00;2025-01-01 06:30:00;A20N;G7;A;06;01P20CM128;"
    "JET-SMALL-A-1;TRACK1;TR1;1;0;2;0;0;0;1.0;0.5;3;FALSE"
)


def test_misspelt_legacy_header_with_domestic_read_in_legacy_order(
    inventory_db, tmp_path
):
    """A legacy 19-column file followed by `domestic` (20 fields) with one
    misspelt header name is read in the legacy order, not as the documented
    20-column order (which would shift it from column 13 on)."""
    csv = tmp_path / "movements_legacy_domestic.csv"
    csv.write_text(
        (LEGACY_HEADER_19 + ";domestic").replace(
            "engine_thrust_level_for_taxiing", "engine_thrust_level_taxiing"
        )
        + "\n"
        + ROW_19_PLUS_DOMESTIC
        + "\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    rows = _load_cols(
        inventory_db,
        [
            "gate_emissions_code",
            "taxi_engine_count",
            "engine_thrust_level_for_taxiing",
            "taxi_fuel_ratio",
            "number_of_stop_and_gos",
        ],
    )
    assert len(rows) == 1
    gec, n_eng, thrust, ratio, stops = rows[0]
    assert int(gec) == 1
    assert int(n_eng) == 2
    assert float(thrust) == 1.0
    assert float(ratio) == 0.5
    assert int(stops) == 3


def test_misspelt_legacy_21col_header_keeps_trailing_gec(inventory_db, tmp_path):
    """A pre-rebuild 21-column file (legacy, gate_emissions_code, domestic)
    with one misspelt header name keeps gate_emissions_code from column 20."""
    csv = tmp_path / "movements_legacy21_misspelt.csv"
    csv.write_text(
        LEGACY_HEADER_21.replace("taxi_route", "taxiroute")
        + "\n"
        + ROW_19_PLUS_DOMESTIC.replace(";FALSE", ";0;FALSE")
        + "\n"
    )
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    rows = _load_cols(
        inventory_db, ["gate_emissions_code", "taxi_engine_count", "taxi_fuel_ratio"]
    )
    assert [(int(g), int(n), float(r)) for g, n, r in rows] == [(0, 2, 0.5)]


def test_headerless_file_keeps_first_movement(inventory_db, tmp_path, monkeypatch):
    """A movements file without a header line starts with a movement. That
    line is read as data (by position), with a warning, not dropped."""
    from open_alaqs.core.tools import create_output

    messages = []
    monkeypatch.setattr(
        create_output.logger,
        "warning",
        lambda msg, *args, **kw: messages.append(msg % args if args else msg),
    )
    csv = tmp_path / "movements_no_header.csv"
    csv.write_text("﻿" + ROW_20_FIELDS + "\n" + ROW_19_FIELDS + "\n")
    inventory_insert_movements(str(inventory_db), {"movement_path": str(csv)})
    rows = _load_cols(
        inventory_db, ["runway_time", "gate_emissions_code", "taxi_engine_count"]
    )
    assert [(t, int(g), int(n)) for t, g, n in rows] == [
        ("2025-01-01 06:00:00", 0, 1),
        ("2025-01-01 06:00:00", 1, 1),
    ]
    assert len(messages) == 1
    assert "no header line" in messages[0]


def test_file_check_counts_first_movement_of_headerless_file(tmp_path):
    """The file check in the Inventory dialog counts the first line of a
    header-less file as a movement and uses its date, like the reader."""
    from unittest.mock import MagicMock

    from open_alaqs.openalaqsdialog import OpenAlaqsInventory

    later = ROW_19_FIELDS.replace("2025-01-01 06:00:00", "2025-01-01 09:10:00", 1)
    for text, expected, expected_start in [
        (ROW_19_FIELDS + "\n" + later + "\n", "Total Movements: 2;", "06:00:00"),
        (LEGACY_HEADER_19 + "\n" + later + "\n", "Total Movements: 1;", "09:00:00"),
    ]:
        csv = tmp_path / "movements_check.csv"
        csv.write_text(text)
        dialog = MagicMock()
        assert OpenAlaqsInventory.examine_movements(dialog, str(csv)) is None
        summary = dialog.ui.movements_summary.setText.call_args[0][0]
        assert summary.startswith(expected), summary
        start = dialog.ui.study_start_date.setDateTime.call_args[0][0]
        assert start.toString("hh:mm:ss") == expected_start
