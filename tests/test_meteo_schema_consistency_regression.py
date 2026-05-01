"""
Regression test for the meteorological CSV schema drift bug.

Symptom (reported by user):
  In the Generate Emission Inventory dialog, picking a meteo CSV that
  has the schema documented in the README (RelativeHumidity in 0-1
  fractions, SeaLevelPressure in Pa) triggers a "Headers of meteo csv
  file do not match.." warning popup. The status banner stays at
  "Meteorological file required" even though the file IS valid.

Root cause:
  The schema was duplicated. The loader at
  AmbientCondition.initAmbientCondition expected
  `RelativeHumidity(0-1)` and `SeaLevelPressure(Pa)` (fixed in session
  22 to align with the CAEP14 reference units). The GUI validator at
  openalaqsdialog.OpenAlaqsInventory.examine_met_file kept the OLD
  schema with `RelativeHumidity(%)` and `SeaLevelPressure(mb)`. Two
  copies of the same dict, only one was updated.

Fix:
  Hoist the schema to a module-level constant `METEO_CSV_HEADERS` in
  AmbientCondition.py and import it from openalaqsdialog. Single source
  of truth -- drift becomes impossible.
"""

import csv
import os
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_meteo_csv_headers_constant_exists_and_uses_si_units():
    """Pin the canonical schema. RelativeHumidity must be a fraction
    (0-1) not percent; SeaLevelPressure must be Pascals not millibars.
    These were the units fixed in session 22 to align with CAEP14
    reference values (the loader convention)."""
    from open_alaqs.core.interfaces.AmbientCondition import METEO_CSV_HEADERS

    expected_headers = {
        "Scenario",
        "DateTime(YYYY-mm-dd hh:mm:ss)",
        "Temperature(K)",
        "Humidity(kg_water/kg_dry_air)",
        "RelativeHumidity(0-1)",
        "SeaLevelPressure(Pa)",
        "WindSpeed(m/s)",
        "WindDirection(degrees)",
        "ObukhovLength(m)",
        "MixingHeight(m)",
    }
    assert set(METEO_CSV_HEADERS.keys()) == expected_headers, (
        f"METEO_CSV_HEADERS keys drifted from the canonical schema. "
        f"Expected: {expected_headers}; got: {set(METEO_CSV_HEADERS.keys())}"
    )

    # Anti-pattern check: the legacy stale strings must NOT be present.
    forbidden = {"RelativeHumidity(%)", "SeaLevelPressure(mb)"}
    leak = forbidden & set(METEO_CSV_HEADERS.keys())
    assert not leak, (
        f"METEO_CSV_HEADERS contains the legacy stale unit strings "
        f"that the session-22 fix removed: {leak}. Re-introducing "
        f"these breaks loading of CAEP14-format meteo CSVs."
    )


def test_loader_uses_shared_constant():
    """AmbientCondition.initAmbientCondition must import and use
    METEO_CSV_HEADERS rather than maintaining its own inline dict."""
    src = (
        REPO / "open_alaqs" / "core" / "interfaces" / "AmbientCondition.py"
    ).read_text()
    init_idx = src.find("def initAmbientCondition")
    assert init_idx != -1
    body = src[init_idx : init_idx + 2000]

    assert "headers_ = METEO_CSV_HEADERS" in body, (
        "initAmbientCondition does not assign headers_ from "
        "METEO_CSV_HEADERS. It must -- otherwise it drifts again."
    )
    # And it must NOT redefine the dict inline.
    # Look for the fingerprint of the inline dict (the canonical key).
    init_body_only = src[init_idx : src.find("\n    def ", init_idx + 1)]
    assert 'DateTime(YYYY-mm-dd hh:mm:ss)": "DateTime"' not in init_body_only, (
        "initAmbientCondition still has the inline dict alongside the "
        "import. Drop one or the other -- two copies will drift."
    )


def test_gui_validator_uses_shared_constant():
    """openalaqsdialog.examine_met_file must import and use
    METEO_CSV_HEADERS rather than maintaining its own inline dict."""
    src = (REPO / "open_alaqs" / "openalaqsdialog.py").read_text()
    exam_idx = src.find("def examine_met_file")
    assert exam_idx != -1
    next_def = src.find("\n    def ", exam_idx + 1)
    body = src[exam_idx:next_def] if next_def != -1 else src[exam_idx:]

    assert "METEO_CSV_HEADERS" in body, (
        "examine_met_file does not reference METEO_CSV_HEADERS. The "
        "GUI validator must use the same dict the loader uses; "
        "duplicating breaks every time the schema is updated."
    )
    # And it must NOT have the legacy stale strings inline.
    forbidden = ("RelativeHumidity(%)", "SeaLevelPressure(mb)")
    # Strip the comment block that intentionally documents the bug.
    body_minus_comments = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    for s in forbidden:
        assert s not in body_minus_comments, (
            f"examine_met_file still contains the legacy stale "
            f"string {s!r} outside of a comment. Schema drift is back."
        )


def test_canonical_meteo_csv_validates_through_gui_path():
    """End-to-end: a CSV matching the canonical schema must pass the
    headers check. Build a minimal in-memory CSV with the exact column
    set from METEO_CSV_HEADERS, run it through read_csv_to_dict, and
    assert sorted(csv.keys()) == sorted(headers_.keys()) -- the same
    comparison examine_met_file performs."""
    from open_alaqs.core.interfaces.AmbientCondition import METEO_CSV_HEADERS
    from open_alaqs.core.tools.csv_interface import read_csv_to_dict

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        # Header line with all required columns; one ISA-ish data row.
        cols = list(METEO_CSV_HEADERS.keys())
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            row = {
                "Scenario": "default",
                "DateTime(YYYY-mm-dd hh:mm:ss)": "2025-12-01 00:00:00",
                "Temperature(K)": "288.15",
                "Humidity(kg_water/kg_dry_air)": "0.00634",
                "RelativeHumidity(0-1)": "0.60",
                "SeaLevelPressure(Pa)": "101325",
                "WindSpeed(m/s)": "5.0",
                "WindDirection(degrees)": "180",
                "ObukhovLength(m)": "99999",
                "MixingHeight(m)": "914.4",
            }
            w.writerow([row[c] for c in cols])

        parsed = read_csv_to_dict(path)
        assert sorted(parsed.keys()) == sorted(METEO_CSV_HEADERS.keys()), (
            f"Canonical CSV failed the headers-match check. "
            f"Parsed keys: {sorted(parsed.keys())}; "
            f"Schema keys: {sorted(METEO_CSV_HEADERS.keys())}"
        )
    finally:
        os.unlink(path)
