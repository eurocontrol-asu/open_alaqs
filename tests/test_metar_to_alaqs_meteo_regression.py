"""
Regression test for `scripts/metar_to_alaqs_meteo.py`.

The plugin's `core/interfaces/AmbientCondition.py::initAmbientCondition`
reads the meteo CSV with strict header matching. The earlier version of
this script wrote headers without the `(unit)` suffixes (e.g.
`Temperature` instead of `Temperature(K)`) and used °C / hPa / 0-100 %
instead of K / Pa / 0-1. The plugin then rejected the file with a single
warning line and silently filled ambient conditions with defaults,
producing wrong NOx ambient corrections downstream.

This test pins:
  1. The header set the script emits MUST equal what AmbientCondition.py
     declares as the canonical mapping.
  2. The numeric values must be in the unit/range the plugin expects
     (K not °C, Pa not hPa, fraction not %, kg/kg not g/kg).
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "metar_to_alaqs_meteo.py"
AMBIENT_PY = REPO / "open_alaqs" / "core" / "interfaces" / "AmbientCondition.py"


def _plugin_expected_headers():
    """Read AmbientCondition.METEO_CSV_HEADERS to extract the canonical
    set of accepted CSV column names. The schema lives at module scope
    in AmbientCondition.py as the constant METEO_CSV_HEADERS (hoisted
    out of initAmbientCondition's body in session 23 so the GUI
    validator and the loader can share a single source of truth)."""
    from open_alaqs.core.interfaces.AmbientCondition import METEO_CSV_HEADERS

    return sorted(METEO_CSV_HEADERS.keys())


def _run_script(metar_lines, start, end, mixing_height=914.4):
    """Run the script with metar_lines as input, return parsed CSV rows."""
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


def test_script_output_headers_match_plugin_expectation():
    """The script's CSV header set must be exactly what
    AmbientCondition.initAmbientCondition expects. Any drift causes the
    plugin to log 'Headers of meteo csv file do not match' and reject
    the file silently."""
    metars = [
        "EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
    ]
    fieldnames, rows = _run_script(metars, "2025-12-01T07:00", "2025-12-01T07:00")
    assert sorted(fieldnames) == _plugin_expected_headers(), (
        f"Script emits headers {sorted(fieldnames)} but plugin expects "
        f"{_plugin_expected_headers()}. Drift causes silent rejection."
    )


def test_script_output_units_are_si():
    """Numeric values must be in plugin units: K not °C, Pa not hPa,
    fraction not percent, kg/kg not g/kg."""
    metars = [
        "EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
    ]
    _, rows = _run_script(metars, "2025-12-01T07:00", "2025-12-01T07:00")
    assert len(rows) == 1
    row = rows[0]

    # Temperature: METAR says 07°C → 280.15 K. Reject obvious °C output.
    T = float(row["Temperature(K)"])
    assert 250.0 < T < 320.0, (
        f"Temperature(K) = {T} is outside plausible Kelvin range; "
        f"likely still in °C."
    )
    # Specifically for 07°C:
    assert abs(T - 280.15) < 0.1, f"Expected ~280.15 K for METAR T=07°C; got {T}."

    # Pressure: METAR Q1016 → 101600 Pa. Reject hPa output.
    P = float(row["SeaLevelPressure(Pa)"])
    assert 80_000.0 < P < 110_000.0, (
        f"SeaLevelPressure(Pa) = {P} is outside plausible Pa range; "
        f"likely still in hPa."
    )
    assert abs(P - 101600.0) < 1.0, f"Expected 101600 Pa for METAR Q1016; got {P}."

    # Relative humidity: must be a fraction 0..1, not percent 0..100.
    RH = float(row["RelativeHumidity(0-1)"])
    assert 0.0 <= RH <= 1.0, (
        f"RelativeHumidity(0-1) = {RH} is outside 0..1; " f"likely still in percent."
    )
    # T=7, Td=5: Magnus gives RH ~0.87
    assert 0.80 < RH < 0.95, f"Expected RH near 0.87 for T=7,Td=5; got {RH}."

    # Specific humidity: typical values 0.001..0.030 kg/kg at sea level.
    q = float(row["Humidity(kg_water/kg_dry_air)"])
    assert 0.0 < q < 0.05, (
        f"Humidity(kg_water/kg_dry_air) = {q} is outside plausible range "
        f"for specific humidity; likely the wrong quantity."
    )


def test_script_output_loads_through_plugin_csv_reader():
    """End-to-end: the script's output must parse cleanly through the
    same `read_csv_to_dict` call AmbientCondition uses. Catches encoding
    or quoting drift that would slip past header-set comparison."""
    metars = [
        "EHRD 010600Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
        "EHRD 010700Z 24010KT 9999 SCT020 07/05 Q1016 NOSIG",
    ]
    fd, out_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        # Write output through the script
        Path(out_path).unlink()  # script will create it
        fd_in, in_path = tempfile.mkstemp(suffix=".txt")
        os.close(fd_in)
        try:
            Path(in_path).write_text("\n".join(metars) + "\n")
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--start",
                    "2025-12-01T06:00",
                    "--end",
                    "2025-12-01T07:00",
                    "--scenario",
                    "default",
                    "--input",
                    in_path,
                    "--output",
                    out_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert r.returncode == 0, r.stderr
        finally:
            os.unlink(in_path)

        # Now load through the plugin's reader
        sys.path.insert(0, str(REPO))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from open_alaqs.core.tools.csv_interface import read_csv_to_dict

        data = read_csv_to_dict(out_path)
        assert sorted(data.keys()) == _plugin_expected_headers(), (
            f"After running through read_csv_to_dict, columns are "
            f"{sorted(data.keys())} but plugin needs "
            f"{_plugin_expected_headers()}."
        )
        assert (
            len(data["Scenario"]) == 2
        ), f"Expected 2 hourly rows; got {len(data['Scenario'])}."
    finally:
        if Path(out_path).exists():
            os.unlink(out_path)
