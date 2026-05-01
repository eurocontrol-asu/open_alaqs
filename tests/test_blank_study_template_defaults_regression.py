"""
Regression test for the values shipped in the user_study_setup row of the
blank study templates.

The template DBs are pre-populated with one row of "sensible defaults"
that gets copied into a user's study DB at study creation time. Three
fields are anchored here:

  * `alaqs_version` — schema version. Must equal what the SQL template
    declares (currently '0.0.1' per tools/template_build/sql/user_study_setup.sql).
    Earlier this field carried a plugin-version label ('Open-ALAQS v2.0')
    in legacy templates, drifting from the SQL template's intent. The
    field is a schema migration counter, not a plugin release tag.

  * `vertical_limit` — the LTO ceiling the user sees in the study setup
    form. CAEP14 prescribes 3000 ft = 914.4 m. The legacy templates
    shipped with 913 m (a rounding artefact). Although the runtime LTO
    ceiling is hardcoded to 914.4 in EmissionCalculatorService
    post-session-21, the template value is what the user sees in the
    UI and what populates the Generate Inventory Output dialog, so the
    visible value must agree.

  * `airport_temperature` — ISA standard sea-level temperature, 15 °C.
    Locked here so a future template tweak doesn't silently shift the
    default away from the ICAO Standard Atmosphere reference.
"""

import re
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Templates that ship a populated user_study_setup row. The inventory
# template intentionally has the table empty (0 rows); see
# generate_templates.py for why - the inventory DB is populated at
# Generate Output time, not at template-creation time.
TEMPLATES = {
    "core/templates/project.alaqs": REPO / "open_alaqs/core/templates/project.alaqs",
    "gse_application example_db.alaqs": REPO / "gse_application/tests/example_db.alaqs",
}

SQL_TEMPLATE = REPO / "tools/template_build/sql/user_study_setup.sql"


def _shipped_value(db_path: Path, column: str):
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            f"SELECT {column} FROM user_study_setup"  # noqa: S608 - column is whitelisted in callers
        ).fetchall()
    finally:
        con.close()
    return rows


def _sql_default(column: str):
    """Parse the INSERT VALUES tuple from the .sql template and return the
    nth value matching the columns list. Stays robust to whitespace
    changes."""
    text = SQL_TEMPLATE.read_text()
    # Extract the column list and values list
    cols_m = re.search(
        r"INSERT INTO user_study_setup\s*\((.*?)\)",
        text,
        re.DOTALL,
    )
    vals_m = re.search(r"VALUES\s*\((.*?)\);", text, re.DOTALL)
    assert cols_m and vals_m, "Could not parse user_study_setup.sql INSERT"
    cols = [c.strip() for c in cols_m.group(1).split(",")]
    vals = [v.strip() for v in vals_m.group(1).split(",")]
    assert len(cols) == len(vals), (
        f"SQL template column/value count mismatch: "
        f"{len(cols)} cols vs {len(vals)} vals"
    )
    return vals[cols.index(column)]


@pytest.mark.parametrize("label,db_path", list(TEMPLATES.items()))
def test_template_alaqs_version_matches_sql_template(label, db_path):
    rows = _shipped_value(db_path, "alaqs_version")
    assert (
        len(rows) == 1
    ), f"{label}: expected exactly 1 row in user_study_setup, got {len(rows)}."
    sql_default = _sql_default("alaqs_version").strip("'")
    assert rows[0][0] == sql_default, (
        f"{label}: alaqs_version is {rows[0][0]!r}, expected {sql_default!r} "
        f"to match tools/template_build/sql/user_study_setup.sql. The field is a SCHEMA "
        f"version counter, not a plugin release tag."
    )


@pytest.mark.parametrize("label,db_path", list(TEMPLATES.items()))
def test_template_vertical_limit_is_caep_ceiling(label, db_path):
    rows = _shipped_value(db_path, "vertical_limit")
    assert (
        len(rows) == 1
    ), f"{label}: expected exactly 1 row in user_study_setup, got {len(rows)}."
    sql_default = float(_sql_default("vertical_limit"))
    assert (
        sql_default == 914.4
    ), f"SQL template vertical_limit drifted from CAEP 914.4 to {sql_default}."
    assert abs(rows[0][0] - 914.4) < 1e-6, (
        f"{label}: vertical_limit is {rows[0][0]}, expected 914.4 "
        f"(CAEP 3000 ft LTO ceiling). The runtime ceiling is hardcoded "
        f"to 914.4 in EmissionCalculatorService; the visible template "
        f"value must agree to avoid user confusion."
    )


@pytest.mark.parametrize("label,db_path", list(TEMPLATES.items()))
def test_template_airport_temperature_is_isa(label, db_path):
    rows = _shipped_value(db_path, "airport_temperature")
    assert (
        len(rows) == 1
    ), f"{label}: expected exactly 1 row in user_study_setup, got {len(rows)}."
    sql_default = float(_sql_default("airport_temperature"))
    assert (
        sql_default == 15.0
    ), f"SQL template airport_temperature drifted from ISA 15 to {sql_default}."
    assert rows[0][0] == 15, (
        f"{label}: airport_temperature is {rows[0][0]}, expected 15 (ISA "
        f"standard sea-level temperature)."
    )
