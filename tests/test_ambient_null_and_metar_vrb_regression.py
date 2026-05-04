"""Regression tests for `scripts/metar_to_alaqs_meteo.py` and
`open_alaqs/core/interfaces/AmbientCondition.py` joint behavior.

This file complements `test_metar_to_alaqs_meteo_regression.py` (which
pins headers and SI units). Here we pin:

  Bug:
    1. The METAR converter emitted empty string for the
       wind-direction column when the METAR reported VRB winds
       ('VRB05KT' or similar). The empty cell loaded into
       `tbl_InvMeteo` as NULL.
    2. `AmbientCondition.__init__` called `convertToFloat(val[X])`
       without an explicit default. The default of
       `convertToFloat()` itself is `None`, so an empty cell
       stored `self._wind_direction_degrees = None`.

  Symptom: AUSTAL run crashed at write time with

       TypeError: must be real number, not NoneType

       in `AUSTALOutputModule.writeTimeSeriesFile` formatting
       `%5.0f`.

Fix:
  - METAR writer: emit '999' (AUSTAL calm-variable convention)
    when wind_dir_deg is None. Numeric value, no NULL leakage.
  - AmbientCondition: pass the same numeric default to
    `convertToFloat` that's used in the `else` branch. None / empty
    / unparseable all become the documented default instead of
    Python None.

The two halves are independent fixes; either alone removes the
crash for the VRB case. Together they form a defense-in-depth: the
writer never emits empty, and even if some other CSV produced one
the loader would still cope.
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "metar_to_alaqs_meteo.py"


def _run_script(metar_lines, start, end, mixing_height=914.4):
    """Run scripts/metar_to_alaqs_meteo.py and return parsed CSV rows."""
    fd_in, in_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd_in)
    fd_out, out_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd_out)
    try:
        Path(in_path).write_text("\n".join(metar_lines) + "\n")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--start",
                start,
                "--end",
                end,
                "--scenario",
                "default",
                "--input",
                in_path,
                "--output",
                out_path,
                "--mixing-height",
                str(mixing_height),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            result.returncode == 0
        ), f"Script failed with code {result.returncode}: stderr={result.stderr}"
        with open(out_path, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        return reader.fieldnames, rows
    finally:
        os.unlink(in_path)
        os.unlink(out_path)


# ---------------------------------------------------------------------------
# METAR writer: VRB emits '999', not empty
# ---------------------------------------------------------------------------


class TestMetarWriterEmitsCalmVariableNumeric:
    def test_vrb_writes_999(self):
        """A METAR with VRB winds must produce '999' in the
        WindDirection column, not empty string."""
        metars = [
            "EHRD 010700Z VRB03KT 9999 SCT020 07/05 Q1016 NOSIG",
        ]
        _, rows = _run_script(metars, "2025-12-01T07:00", "2025-12-01T07:00")
        assert len(rows) == 1
        wd = rows[0]["WindDirection(degrees)"]
        assert wd == "999", (
            f"VRB METAR should yield WindDirection='999' (AUSTAL calm-"
            f"variable convention); got {wd!r}."
        )

    def test_numeric_dir_writes_as_normal(self):
        """A METAR with a numeric direction (e.g. 24010KT) must still
        write the numeric direction. Non-VRB path is unaffected by the
        VRB-handling change."""
        metars = [
            "EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
        ]
        _, rows = _run_script(metars, "2025-12-01T07:00", "2025-12-01T07:00")
        assert len(rows) == 1
        wd = rows[0]["WindDirection(degrees)"]
        # METAR 24010 → wind from 240°
        assert (
            wd == "240"
        ), f"Numeric METAR direction 24010 should yield '240'; got {wd!r}."

    def test_no_empty_cells_in_output(self):
        """Stronger property: for any mix of VRB and numeric, the
        WindDirection column must never contain empty cells."""
        metars = [
            "EHRD 010600Z VRB02KT 9999 SCT020 07/05 Q1016 NOSIG",
            "EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
            "EHRD 010800Z VRB04KT 9999 SCT020 08/06 Q1016 NOSIG",
        ]
        _, rows = _run_script(metars, "2025-12-01T06:00", "2025-12-01T08:00")
        assert len(rows) == 3
        wds = [r["WindDirection(degrees)"] for r in rows]
        assert "" not in wds, f"Empty WindDirection cells found: {wds}"
        # Verify each is parseable as a number (covers any future stub
        # that might yield 'N/A' or similar).
        for wd in wds:
            float(wd)


# ---------------------------------------------------------------------------
# AmbientCondition.__init__ defensive defaults
# ---------------------------------------------------------------------------
#
# Stub the qgis namespace so AmbientCondition.py can be imported
# standalone. Same pattern used by the other regression test files.


def _ensure_qgis_stubs():
    import sys
    import types

    if "qgis" not in sys.modules:
        sys.modules["qgis"] = types.ModuleType("qgis")

    qgis_utils = sys.modules.get("qgis.utils") or types.ModuleType("qgis.utils")

    def _spatialite_connect(db_name, *args, **kwargs):
        import sqlite3

        return sqlite3.connect(db_name)

    qgis_utils.spatialite_connect = _spatialite_connect
    sys.modules["qgis.utils"] = qgis_utils
    sys.modules["qgis"].utils = qgis_utils

    if "qgis.core" not in sys.modules:
        qgis_core = types.ModuleType("qgis.core")

        class _QgsStub:
            Info = Warning = Critical = 0

            def __getattr__(self, name):
                return _QgsStub()

            def __call__(self, *args, **kwargs):
                return None

        qgis_core.Qgis = _QgsStub()
        qgis_core.QgsMessageLog = _QgsStub()
        sys.modules["qgis.core"] = qgis_core
        sys.modules["qgis"].core = qgis_core


_ensure_qgis_stubs()

from open_alaqs.core.interfaces.AmbientCondition import (  # noqa: E402
    AmbientCondition,
)


class TestAmbientConditionEmptyHandling:
    """Empty / None / unparseable inputs must yield the documented
    numeric default for that field, not Python None.

    The list of fields we cover here is the meteo-CSV-driven set used
    by `AUSTALOutputModule.writeTimeSeriesFile`. AUSTAL formats them
    with `%5.0f` / `%5.2f` / etc., which raises TypeError on None.
    """

    def test_empty_wind_direction_yields_default(self):
        ac = AmbientCondition({"WindDirection": ""})
        assert ac._wind_direction_degrees == 0.0

    def test_none_wind_direction_yields_default(self):
        ac = AmbientCondition({"WindDirection": None})
        assert ac._wind_direction_degrees == 0.0

    def test_unparseable_wind_direction_yields_default(self):
        ac = AmbientCondition({"WindDirection": "not a number"})
        assert ac._wind_direction_degrees == 0.0

    def test_999_wind_direction_passes_through(self):
        """The METAR writer's calm-variable sentinel (999) must reach
        AmbientCondition unchanged. AUSTAL itself interprets 999 as
        variable wind."""
        ac = AmbientCondition({"WindDirection": "999"})
        assert ac._wind_direction_degrees == 999.0

    def test_empty_wind_speed_yields_default(self):
        ac = AmbientCondition({"WindSpeed": ""})
        assert ac._wind_speed_in_m_s == 0.0

    def test_empty_temperature_yields_default(self):
        ac = AmbientCondition({"Temperature": ""})
        assert ac._temperature_in_K == 288.15

    def test_empty_humidity_yields_default(self):
        ac = AmbientCondition({"Humidity": ""})
        assert ac._humidity == pytest.approx(0.00634)

    def test_empty_relative_humidity_yields_default(self):
        ac = AmbientCondition({"RelativeHumidity": ""})
        assert ac._relative_humidity == 0.6

    def test_empty_pressure_yields_default(self):
        ac = AmbientCondition({"SeaLevelPressure": ""})
        assert ac._sealevel_pressure_Pa == 1013.25 * 100.0

    def test_empty_obukhov_length_yields_default(self):
        ac = AmbientCondition({"ObukhovLength": ""})
        assert ac._obukhov_length == 99999.0

    def test_no_field_present_uses_full_iso_defaults(self):
        """If the dict is empty, every field falls through to the
        existing else-branch defaults. This pins the legacy behavior
        is preserved (the fix only changed the empty-cell path)."""
        ac = AmbientCondition({})
        assert ac._wind_direction_degrees == 0.0
        assert ac._wind_speed_in_m_s == 0.0
        assert ac._temperature_in_K == 288.15
        assert ac._relative_humidity == 0.6
        assert ac._humidity == pytest.approx(0.00634)
        assert ac._sealevel_pressure_Pa == 1013.25 * 100.0
        assert ac._obukhov_length == 99999.0
