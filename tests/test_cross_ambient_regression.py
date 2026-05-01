"""
Cross-ambient regression tests.

Two layers of assertion:

  1. HARD checks (always required to pass):
     - Bymode gas-phase emissions must be identical across ambients.
       This is the critical contract: bymode bypasses ambient corrections,
       so if it ever starts responding to ambient, someone has accidentally
       wired the correction in and every historical bymode report is at
       risk.  Fuel burn, CO, CO2, HC, NOx, SOx all must be byte-identical.
     - Overriding a meteo row must actually reach EmissionCalculation
       (the plumbing check).

  2. XFAIL checks (currently not passing, document a known gap):
     - BFFM2 ambient sensitivity.  The ambient value IS being read
       (confirmed by the plumbing check) but BFFM2 is not shifting
       movement-level totals across a 40K temperature spread.  The root
       cause appears to be in fuel_flow propagation from segment config
       into the BFFM2 EI lookup.  Marked xfail(strict=False) so they
       surface in the test report but don't block CI.
"""

import datetime
import shutil
import sqlite3
from datetime import timedelta

import pytest

from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from tests.utils import aggregate_emissions, get_data_path

GRID_CONFIG = {
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


def _copy_db_with_overridden_meteo(
    src_db, dst_db, timestamp_iso, temperature_K, pressure_Pa
):
    """Copy AIRPORT_A test DB and overwrite a single meteo row."""
    shutil.copy(src_db, dst_db)
    conn = sqlite3.connect(dst_db)
    conn.execute(
        "UPDATE tbl_InvMeteo SET Temperature = ?, SeaLevelPressure = ? "
        "WHERE DateTime = ?",
        (temperature_K, pressure_Pa, timestamp_iso),
    )
    conn.commit()
    conn.close()


class TestCrossAmbientRegression:

    def _calc_with_ambient(self, tmp_path, temperature_K, pressure_Pa, method="BFFM2"):
        src = get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"
        dst = tmp_path / f"airport_a_T{int(temperature_K)}_P{int(pressure_Pa)}.alaqs"
        _copy_db_with_overridden_meteo(
            src, dst, "2025-12-01 06:00:00", temperature_K, pressure_Pa
        )
        cfg = EmissionCalculationConfig(
            db_path=str(dst),
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 6, 0, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 1, 7, 0, 0),
            time_interval=timedelta(seconds=3600),
            pollutant="CO",
            method=method,
            source_type="movement",
            grid_config=GRID_CONFIG,
        )
        svc = EmissionCalculatorService()
        result = svc.calculate_emissions(cfg)
        assert result.success, f"Calc failed: {result.error_message}"
        return aggregate_emissions(result.emissions_data)

    def test_bymode_invariant_under_ambient_change(self, tmp_path):
        """Plain bymode must NOT apply θ/δ corrections to gas-phase EI.
        Fuel burn and gas-phase totals must match to 1e-6 between any two
        ambients.  Guards against accidentally wiring ambient correction
        into the bymode path."""
        cold = self._calc_with_ambient(tmp_path, 263.0, 101325.0, method="bymode")
        hot = self._calc_with_ambient(tmp_path, 303.0, 101325.0, method="bymode")
        for pollutant in ("co_kg", "co2_kg", "hc_kg", "nox_kg", "sox_kg", "fuel_kg"):
            assert cold[pollutant] == pytest.approx(hot[pollutant], rel=1e-6), (
                f"bymode {pollutant} must not depend on ambient; "
                f"got cold={cold[pollutant]} hot={hot[pollutant]}"
            )

    def test_ambient_is_actually_read_from_db(self, tmp_path):
        """Overriding the meteo row must flow through to
        EmissionCalculation.getAmbientCondition."""
        from open_alaqs.core import EmissionCalculation as ECmod

        seen = []
        orig = ECmod.EmissionCalculation.getAmbientCondition

        def traced(self, t):
            ac = orig(self, t)
            T = ac.getTemperature()
            seen.append(float(T) if T is not None else None)
            return ac

        ECmod.EmissionCalculation.getAmbientCondition = traced
        try:
            self._calc_with_ambient(tmp_path, 270.0, 101325.0, method="bymode")
            assert any(abs((T or 0) - 270.0) < 0.01 for T in seen), (
                f"Expected ambient T=270 K to reach getAmbientCondition, "
                f"saw: {seen}"
            )
        finally:
            ECmod.EmissionCalculation.getAmbientCondition = orig

    def test_bffm2_nox_shifts_with_ambient(self, tmp_path):
        """BFFM2 θ/δ/Mach correction must shift NOx EI across ambients
        (colder/denser air → higher NOx). The 40K spread here should move
        NOx by at least 1%. Taxi-time emissions (often the dominant
        fuel-burn bucket) must honour the configured ambient, not fall
        back to EEDB ISA reference values — this test guards against
        regression of the taxi ambient bypass bug."""
        cold = self._calc_with_ambient(tmp_path, 263.0, 101325.0, method="BFFM2")
        hot = self._calc_with_ambient(tmp_path, 303.0, 101325.0, method="BFFM2")
        nox_cold = cold["nox_kg"]
        nox_hot = hot["nox_kg"]
        assert nox_hot > 0, "BFFM2 NOx output is zero"
        assert abs(nox_cold - nox_hot) / nox_hot > 0.01, (
            f"Expected NOx to shift by >1% across 40K spread; "
            f"got cold={nox_cold}, hot={nox_hot}"
        )

    def test_bffm2_fuel_shifts_with_ambient(self, tmp_path):
        """Taxi fuel flow under BFFM2 must shift with ambient (colder/denser
        air → higher fuel flow via δ/θ^3.8 factor). The taxi bucket is
        typically 70-85% of a short-haul inventory's total fuel, so this
        test effectively verifies that the dominant fuel contributor is
        ambient-sensitive."""
        cold = self._calc_with_ambient(tmp_path, 263.0, 101325.0, method="BFFM2")
        hot = self._calc_with_ambient(tmp_path, 303.0, 101325.0, method="BFFM2")
        assert abs(cold["fuel_kg"] - hot["fuel_kg"]) / hot["fuel_kg"] > 0.001, (
            f"Expected fuel burn to shift >0.1% across 40K ambient spread; "
            f"got cold={cold['fuel_kg']:.3f}, hot={hot['fuel_kg']:.3f}"
        )
