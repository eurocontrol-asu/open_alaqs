import datetime
from datetime import timedelta

import pytest

from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from tests.utils import (
    aggregate_emissions,
    compare_emissions_with_expected,
    get_data_path,
    load_expected_from_csv_single_row,
    load_expected_totals_from_csv,
)

# =============================================================================
# Test Configuration Constants
# =============================================================================

AIRPORT_A_GRID_CONFIG = {
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 1,
    "x_resolution": 100,
    "y_resolution": 100,
    "z_resolution": 100,
    "reference_latitude": 51.96,
    "reference_longitude": 4.44,
    "reference_altitude": 0.0,
}

ANP_GRID_CONFIG = {
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 1,
    "x_resolution": 100,
    "y_resolution": 100,
    "z_resolution": 100,
    "reference_latitude": 52.31,
    "reference_longitude": 4.77,
    "reference_altitude": -3.0,
}

# Relative tolerance for all of the tests that need this constant
REL_TOL = 1e-6


# =============================================================================
# Validation Tests
# =============================================================================


class TestEmissionCalculatorServiceValidation:
    """Tests for EmissionCalculatorService configuration validation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup service instance for each test."""
        self.service = EmissionCalculatorService()

    def test_validate_valid_config(self):
        """Test validation passes with valid config."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is True
        assert error_msg is None

    def test_validate_empty_db_path(self):
        """Test validation fails when db_path is empty."""
        config = EmissionCalculationConfig(
            db_path="",
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Database path is required" in error_msg

    def test_validate_start_after_end(self):
        """Test validation fails when start time is after end time."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 8, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Start datetime must be before end datetime" in error_msg

    def test_validate_zero_time_interval(self):
        """Test validation fails when time interval is zero."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=0),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Time interval must be positive" in error_msg

    def test_validate_invalid_pollutant(self):
        """Test validation fails for unsupported pollutant."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="INVALID",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Invalid pollutant" in error_msg

    def test_validate_invalid_method(self):
        """Test validation fails for unsupported method."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="invalid_method",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Invalid method" in error_msg

    def test_validate_missing_grid_config(self):
        """Test validation fails when grid config is missing."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=None,
        )

        is_valid, error_msg = self.service.validate_config(config)
        assert is_valid is False
        assert "Grid configuration is required" in error_msg

    def test_validate_all_supported_pollutants(self):
        """Test that all supported pollutants pass validation."""
        for pollutant in ["CO2", "CO", "HC", "NOx", "SOx", "PM10"]:
            config = EmissionCalculationConfig(
                db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
                start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
                end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
                time_interval=timedelta(seconds=3600),
                pollutant=pollutant,
                grid_config=AIRPORT_A_GRID_CONFIG,
            )

            is_valid, error_msg = self.service.validate_config(config)
            assert (
                is_valid is True
            ), f"Pollutant {pollutant} should be valid: {error_msg}"


# ==============================================================
# AIRPORT_A Dataset Tests - Verify output matches expected CSV values
# ==============================================================


class TestAirportAEmissions:
    """Tests using AIRPORT_A (Rotterdam) dataset to verify emissions match expected values."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup service instance for each test."""
        self.service = EmissionCalculatorService()

    def test_airport_a_co_emissions_match_expected(self):
        """Test AIRPORT_A CO emissions match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        # Load expected values from CSV
        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        # Compare CO emissions
        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co_kg"],
        )

    def test_airport_a_co2_emissions_match_expected(self):
        """Test AIRPORT_A CO2 emissions match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO2",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co2_kg"],
        )

    def test_airport_a_nox_emissions_match_expected(self):
        """Test AIRPORT_A NOx emissions match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["nox_kg"],
        )

    def test_airport_a_hc_emissions_match_expected(self):
        """Test AIRPORT_A HC emissions match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="HC",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["hc_kg"],
        )

    def test_airport_a_pm10_emissions_match_expected(self):
        """Test AIRPORT_A PM10 emissions match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="PM10",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["pm10_kg"],
        )

    def test_airport_a_all_pollutants_match_expected(self):
        """Test AIRPORT_A all pollutants match expected CSV values in a single calculation."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_from_csv_single_row(
            str(
                get_data_path(
                    "AIRPORT_A/AIRPORT_A_emissions_table_by_aggregation_co.csv"
                )
            )
        )
        calculated = aggregate_emissions(result.emissions_data)

        # Compare all main pollutants
        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co_kg", "co2_kg", "hc_kg", "nox_kg", "sox_kg", "pm10_kg"],
        )

    def test_airport_a_movement_source_only(self):
        """Test AIRPORT_A calculation with MovementSource only produces valid emissions."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="MovementSource",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        totals = aggregate_emissions(result.emissions_data)

        # Sanity check: all emissions should be non-negative
        for key, value in totals.items():
            assert value >= 0, f"{key} should be non-negative, got {value}"

        # MovementSource should produce some emissions
        assert totals["co_kg"] > 0, "MovementSource should produce CO emissions"
        assert totals["co2_kg"] > 0, "MovementSource should produce CO2 emissions"


# =============================================================
# ANP Dataset Tests - Verify output matches expected CSV values
# =============================================================


class TestANPEmissions:
    """Tests using ANP (Amsterdam) dataset to verify emissions match expected values."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup service instance for each test."""
        self.service = EmissionCalculatorService()

    def test_anp_co_emissions_match_expected(self):
        """Test ANP CO emissions over full time range match expected CSV totals."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 22, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=ANP_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        # Load expected totals (sum of all time periods)
        expected = load_expected_totals_from_csv(
            str(get_data_path("ANP/ANP_emissions_table_by_aggregation_co.csv"))
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co_kg"],
        )

    @pytest.mark.xfail(
        reason=(
            "ANP_emissions_table_by_aggregation_co.csv expected hc_kg values "
            "(3.768 over 16h, 2.502 single hour) were generated against "
            "pre-5.1.2 code where start emissions were keyed by engine. The "
            "5.1.2 fix keys start emissions by aircraft (which carries the "
            "group); two aircraft sharing an engine but in different ac_groups "
            "now correctly receive group-specific start-emission EIs. This "
            "shifts HC totals by ~0.93 kg over 16h on the ANP fixture (other "
            "pollutants unchanged: CO, CO2, NOx, SOx, PM10 match to 1e-6). "
            "Regenerating the CSV from the corrected pipeline closes this; "
            "tracked as 5.2.1 follow-up. See CHANGELOG [5.1.2] 'Fixed' > "
            "'MovementEmissionCalculator: start emissions are now keyed by "
            "aircraft instead of engine'."
        ),
        strict=True,
    )
    def test_anp_all_pollutants_match_expected(self):
        """Test ANP all pollutants match expected CSV values."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 22, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=ANP_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        expected = load_expected_totals_from_csv(
            str(get_data_path("ANP/ANP_emissions_table_by_aggregation_co.csv"))
        )
        calculated = aggregate_emissions(result.emissions_data)

        # Compare all main pollutants
        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co_kg", "co2_kg", "hc_kg", "nox_kg", "sox_kg", "pm10_kg"],
        )

    @pytest.mark.xfail(
        reason=(
            "ANP_emissions_table_by_aggregation_co.csv expected hc_kg for "
            "2023-03-01T06:00 (2.502 kg) was generated against pre-5.1.2 code "
            "where start emissions were keyed by engine. The 5.1.2 fix keys "
            "start emissions by aircraft; HC for the 06:00 hour shifts by "
            "+0.616 kg (other pollutants unchanged to 1e-6). Regenerating the "
            "CSV against the corrected pipeline closes this; tracked as 5.2.1 "
            "follow-up. See CHANGELOG [5.1.2] 'Fixed' > 'MovementEmissionCalculator: "
            "start emissions are now keyed by aircraft instead of engine'."
        ),
        strict=True,
    )
    def test_anp_single_hour_emissions(self):
        """Test ANP emissions for a single hour match expected CSV row."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=ANP_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        # Load expected values from first row (06:00-07:00)
        expected = load_expected_from_csv_single_row(
            str(get_data_path("ANP/ANP_emissions_table_by_aggregation_co.csv")),
            row_index=0,
        )
        calculated = aggregate_emissions(result.emissions_data)

        compare_emissions_with_expected(
            calculated=calculated,
            expected=expected,
            rel_tol=REL_TOL,
            pollutants=["co_kg", "co2_kg", "hc_kg", "nox_kg", "sox_kg", "pm10_kg"],
        )

    def test_anp_calculation_succeeds(self):
        """Test ANP calculation completes successfully."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=ANP_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True, f"Calculation failed: {result.error_message}"

        # Ensure emissions data is not empty
        assert result.emissions_data is not None
        assert len(result.emissions_data) > 0

        # Aggregate emissions to verify non-negativity
        totals = aggregate_emissions(result.emissions_data)
        for key, value in totals.items():
            assert value >= 0, f"{key} should be non-negative, got {value}"


# =========================
# Service Integration Tests
# =========================


class TestEmissionCalculatorServiceIntegration:
    """Integration tests for EmissionCalculatorService functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup service instance for each test."""
        self.service = EmissionCalculatorService()

    def test_metadata_returned_correctly(self):
        """Test that calculation result includes correct metadata."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method="bymode",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)

        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["pollutant"] == "CO"
        assert result.metadata["method"] == "bymode"
        assert result.metadata["source_type"] == "all"
        assert result.metadata["time_interval_seconds"] == 3600.0

    def test_invalid_db_path_fails_gracefully(self):
        """Test that calculation fails gracefully with invalid database path."""
        config = EmissionCalculationConfig(
            db_path="/nonexistent/path/to/database.alaqs",
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)

        # Should fail but not raise an exception
        assert result.success is False
        assert result.error_message is not None

    def test_service_getters(self):
        """Test service getter methods return correct values after calculation."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)

        # Verify all getters return expected values
        assert result.success is True
        assert self.service.get_calculation() is not None
        assert self.service.get_emissions() is not None
        assert self.service.get_emissions() == result.emissions_data
        assert self.service.get_3d_grid() is not None
        assert self.service.get_database_path() == str(
            get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"
        )

    def test_multiple_calculations_independent(self):
        """Test that multiple calculations are independent and don't share state."""
        # First calculation with AIRPORT_A
        config1 = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )
        result1 = self.service.calculate_emissions(config1)
        assert result1.success is True
        totals1 = aggregate_emissions(result1.emissions_data)

        # Second calculation with ANP (different dataset)
        config2 = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            grid_config=ANP_GRID_CONFIG,
        )
        result2 = self.service.calculate_emissions(config2)
        assert result2.success is True
        totals2 = aggregate_emissions(result2.emissions_data)

        # Results should be different (different datasets)
        assert totals1["co_kg"] != totals2["co_kg"]


# ==================
# BFFM2 Method Tests
# ==================


class TestEmissionCalculatorServiceBFFM2:
    """Tests for BFFM2 (Boeing Fuel Flow Method 2) calculations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup service instance for each test."""
        self.service = EmissionCalculatorService()

    def test_bffm2_produces_emissions(self):
        """Test emission calculation using BFFM2 method produces emissions."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="BFFM2",
            source_type="all",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)

        assert result.success is True
        assert result.emissions_data is not None

        totals = aggregate_emissions(result.emissions_data)
        assert totals["nox_kg"] > 0, "BFFM2 should produce NOx emissions"
        assert totals["co2_kg"] > 0, "BFFM2 should produce CO2 emissions"

    def test_bffm2_nox_corrections_warning(self):
        """Test that BFFM2 with NOx corrections generates a warning."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="BFFM2",
            should_apply_nox_corrections=True,
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        # NOx corrections are not applicable with BFFM2, should generate warning
        is_valid, _ = self.service.validate_config(config)

        assert is_valid is True
        assert len(self.service._warnings) > 0
        assert any("NOx corrections" in w for w in self.service._warnings)

    def test_bffm2_and_bymode_both_work(self):
        """Test that both BFFM2 and bymode methods successfully produce emissions."""
        # Calculate with bymode method
        config_bymode = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="bymode",
            source_type="MovementSource",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result_bymode = self.service.calculate_emissions(config_bymode)
        assert result_bymode.success is True
        totals_bymode = aggregate_emissions(result_bymode.emissions_data)

        # Calculate with BFFM2 method
        config_bffm2 = EmissionCalculationConfig(
            db_path=str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="BFFM2",
            source_type="MovementSource",
            grid_config=AIRPORT_A_GRID_CONFIG,
        )

        result_bffm2 = self.service.calculate_emissions(config_bffm2)
        assert result_bffm2.success is True
        totals_bffm2 = aggregate_emissions(result_bffm2.emissions_data)

        # Both methods should produce valid (non-negative) emissions
        assert totals_bymode["nox_kg"] >= 0, "bymode should produce valid NOx"
        assert totals_bffm2["nox_kg"] >= 0, "BFFM2 should produce valid NOx"

    def test_bffm2_anp_dataset(self):
        """Test BFFM2 method with ANP dataset."""
        config = EmissionCalculationConfig(
            db_path=str(get_data_path("ANP") / "ANP_out.alaqs"),
            start_dt_inclusive=datetime.datetime(2023, 3, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2023, 3, 1, 10, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="NOx",
            method="BFFM2",
            source_type="MovementSource",
            grid_config=ANP_GRID_CONFIG,
        )

        result = self.service.calculate_emissions(config)
        assert result.success is True

        totals = aggregate_emissions(result.emissions_data)
        assert totals["nox_kg"] >= 0, "BFFM2 should produce valid NOx for ANP"
