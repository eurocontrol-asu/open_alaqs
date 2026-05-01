"""
Regression tests for the simplified ADS-B CSV schema.

Session-22 changes:
  - Dropped columns: track, vertical_rate, groundspeed, nodes, taxi.
    None were ever read by the import code.
  - Renamed `thrust` → `power_setting` to match its semantics: the value
    is passed directly into BFFM2's twin-quadratic-fit, which expects an
    engine power-setting fraction (0-1). The old name suggested raw
    Newtons or similar, leading to silent data drift.
  - Added range validation: power_setting must be in [0, 1.5]. Values
    above 1.5 are almost certainly a unit error and are rejected to
    fail loud.
  - Back-compat: validator still accepts `thrust` as alias and emits a
    deprecation warning; values from the legacy column skip the range
    check (some legacy files have raw-Newton values that would be
    rejected by 0-1.5; the import passes those through to the trajectory
    DB unchanged, where they're either ignored if `fuel_flow` is also
    present or produce wrong but reproducible BFFM2 output).
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]


def _write_csv(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    Path(path).write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def fake_runways():
    """Patch get_runways so the validator's runway check passes without
    needing a real study DB."""
    with patch("open_alaqs.core.tools.ads_b.get_runways", return_value=[("06/24",)]):
        yield


def test_validator_accepts_minimal_schema_with_power_setting(fake_runways):
    """A CSV with only the new minimal column set must validate cleanly."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
        "F1,51.96,4.44,0,100,1.00,0.90\n"
        "F1,51.97,4.44,1000,150,0.95,0.80\n"
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert ok, f"Validator rejected the new minimal schema: {msg}"
    finally:
        os.unlink(path)


def test_validator_rejects_power_setting_above_15(fake_runways):
    """Values above 1.5 indicate the column contains the wrong unit
    (raw Newtons, percent-x-100, etc.)."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
        "F1,51.96,4.44,0,100,2480.1,0.90\n"  # raw Newtons-style value
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert not ok
        assert "power_setting" in msg.lower()
        assert (
            "1.5" in msg or "range" in msg.lower()
        ), f"Rejection message should mention the range: {msg}"
    finally:
        os.unlink(path)


def test_validator_rejects_negative_power_setting(fake_runways):
    """Negative power_setting is not physically meaningful."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
        "F1,51.96,4.44,0,100,-0.5,0.90\n"
    )
    try:
        ok, _msg = validate_adsb_file(path)
        assert not ok
    finally:
        os.unlink(path)


def test_validator_accepts_legacy_thrust_column_without_range_check(fake_runways):
    """Back-compat: files with the old `thrust` column name still parse,
    even with values that would fail the new power_setting range check.
    The deprecation is logged, not raised."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,thrust,fuel_flow\n"
        "F1,51.96,4.44,0,100,2480.1,0.90\n"  # Out-of-range for power_setting,
        "F1,51.97,4.44,1000,150,2300.0,0.80\n"  # but accepted under legacy alias.
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert ok, f"Legacy `thrust` column rejected: {msg}"
    finally:
        os.unlink(path)


def test_validator_rejects_when_neither_power_nor_fuel_flow_present(fake_runways):
    """At least one of power_setting / fuel_flow must be in the header."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas\n" "F1,51.96,4.44,0,100\n"
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert not ok
        assert "power_setting" in msg or "fuel_flow" in msg
    finally:
        os.unlink(path)


def test_test_fixtures_use_new_schema():
    """The 4 test fixtures in tests/data/AIRPORT_A/ADS-B must use the
    simplified column set."""
    fixtures_dir = REPO / "tests" / "data" / "AIRPORT_A" / "ADS-B"
    expected = {
        "AIRPORT_A_ads_b_data_valid.csv": {
            "flight_id",
            "timestamp",
            "latitude",
            "longitude",
            "altitude",
            "tas",
            "power_setting",
            "fuel_flow",
        },
        "AIRPORT_A_ads_b_data_invalid_2.csv": {
            "flight_id",
            "timestamp",
            "latitude",
            "longitude",
            "altitude",
            "tas",
            "power_setting",
            "fuel_flow",
        },
        "AIRPORT_A_ads_b_data_invalid_3.csv": {
            "flight_id",
            "timestamp",
            "latitude",
            "longitude",
            "altitude",
            "tas",
            "power_setting",
            "fuel_flow",
        },
        # invalid_1 deliberately drops `altitude` to test the validator's
        # missing-mandatory-field check.
        "AIRPORT_A_ads_b_data_invalid_1.csv": {
            "flight_id",
            "timestamp",
            "latitude",
            "longitude",
            "tas",
            "power_setting",
            "fuel_flow",
        },
    }
    forbidden = {"track", "vertical_rate", "groundspeed", "nodes", "taxi", "thrust"}
    for fname, exp_cols in expected.items():
        path = fixtures_dir / fname
        assert path.is_file(), f"Missing fixture: {path}"
        header = path.read_text().splitlines()[0]
        cols = set(header.split(","))
        assert cols == exp_cols, f"{fname} columns {cols} != expected {exp_cols}"
        leak = cols & forbidden
        assert not leak, f"{fname} still contains dropped column(s): {leak}"


def test_validator_accepts_extra_unrecognized_columns(fake_runways):
    """Real-world ADS-B exports often include columns we don't consume:
    aircraft type, registration, squawk, icao24, callsign, weather,
    custom annotations, etc. The validator must accept these gracefully
    so users don't have to hand-trim their files before import."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow,"
        "aircraft_type,registration,squawk,icao24,callsign,weather,custom\n"
        "F1,51.96,4.44,0,100,1.00,0.90,A20N,PH-EZA,1234,485789,KLM123,sunny,foo\n"
        "F1,51.97,4.44,1000,150,0.95,0.85,A20N,PH-EZA,1234,485789,KLM123,sunny,bar\n"
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert ok, (
            f"Validator must accept extra unrecognized columns "
            f"(real-world ADS-B exports include many): {msg}"
        )
    finally:
        os.unlink(path)


def test_validator_extra_columns_do_not_break_range_check(fake_runways):
    """Extra columns must not interfere with the power_setting [0, 1.5]
    range validation. A bad power_setting value must still be rejected
    even when surrounded by other columns."""
    from open_alaqs.core.tools.ads_b import validate_adsb_file

    path = _write_csv(
        "flight_id,latitude,longitude,altitude,tas,extra_a,power_setting,extra_b,fuel_flow\n"
        "F1,51.96,4.44,0,100,foo,5000,bar,0.90\n"  # power_setting=5000 is out of range
    )
    try:
        ok, msg = validate_adsb_file(path)
        assert not ok
        assert "power_setting" in msg.lower()
    finally:
        os.unlink(path)
