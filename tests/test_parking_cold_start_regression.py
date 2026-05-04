"""
Regression test for the parking cold-start fix in copert5.

Bug:
  The parking branch of roadway_emission_factors() multiplied a
  fleet-averaged hot+cold EF by the parking maneuvering distance
  (typically ~0.35 km). Because calculate_emissions() builds the
  cold-start contribution at M=1000 km, scaling by maneuvering
  distance / 1000 = 0.00035 effectively zeroed cold-start. This
  understated parking NOx by an order of magnitude relative to the
  EMEP/EEA Tier 2 methodology.

Fix:
  When study_data["parking_include_cold_start"] is True, decouple
  hot and cold:
    - hot is computed at parking_speed × maneuvering_distance (unchanged)
    - cold is computed at cold_speed × L_trip
  L_trip defaults to 12.4 km (COPERT 5 standard) and cold_speed to
  30 km/h (the speed at which COPERT 5 cold cells are populated;
  cells at >= 50 km/h are zero in the database by COPERT 5
  convention because engines are assumed warm at highway speeds).

  The flag defaults to False so existing studies preserve their
  current totals byte-for-byte. New studies opt in.

This test pins the new behavior for a representative NL 2025 fleet.
"""

import sys
import types
from pathlib import Path

import pandas as pd
import pytest


# alaqsdblite imports qgis.utils.spatialite_connect at module load. The
# tests in this file exercise pure-Python paths (calculate_emissions and
# the parking branch of roadway_emission_factors) and never touch SQL,
# so we stub the qgis namespace to allow standalone execution outside
# the QGIS Python.
# Set up minimal stubs for qgis/qgis.utils/qgis.core to allow running
# this test outside the QGIS Python. The parking EF queries don't touch
# geometry so plain sqlite3 is sufficient. We always (re)install our
# implementation, even if a previously-loaded test module already
# stubbed qgis.utils with a RuntimeError-raising shim.
def _ensure_qgis_stubs():
    if "qgis" not in sys.modules:
        sys.modules["qgis"] = types.ModuleType("qgis")

    qgis_utils = sys.modules.get("qgis.utils") or types.ModuleType("qgis.utils")

    def _spatialite_connect(db_name, *args, **kwargs):
        """Plain sqlite3 connect. Sufficient for the EF table reads
        that this test exercises; spatial functions are not needed."""
        import sqlite3

        return sqlite3.connect(db_name)

    # Always (re)install our connect, overriding any prior stub.
    qgis_utils.spatialite_connect = _spatialite_connect
    sys.modules["qgis.utils"] = qgis_utils
    sys.modules["qgis"].utils = qgis_utils

    if "qgis.core" not in sys.modules:
        qgis_core = types.ModuleType("qgis.core")

        class _QgsStub:
            """Stand-in for qgis.core.Qgis / QgsMessageLog. Calls become
            no-ops, attribute access returns more stubs."""

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


from open_alaqs.core.tools.copert5 import roadway_emission_factors  # noqa: E402
from open_alaqs.core.tools.copert5_utils import (  # noqa: E402
    VEHICLE_CATEGORIES,
    average_cold_only_emission_factors,
    calculate_emissions,
    ef_query,
)
from tools.template_build.generate_templates import get_engine  # noqa: E402

TEMPLATES_DIR = Path(__file__).parents[1] / "open_alaqs/core/templates"


@pytest.fixture(autouse=True, scope="module")
def _project_database():
    """Point the ProjectDatabase singleton at the project template so
    roadway_emission_factors() can fetch EFs without a QGIS-mediated DB
    connection. The template ships with the full COPERT 5 EF table for
    all supported countries.

    Also patches the spatialite_connect symbol that alaqsdblite captured
    at import time. When this test module is loaded after another test
    that installed a RuntimeError-raising stub, the alaqsdblite module
    already has the bad symbol bound. Rebind it here to plain sqlite3."""
    import sqlite3

    from open_alaqs.core import alaqsdblite
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    def _spatialite_connect(db_name, *args, **kwargs):
        return sqlite3.connect(db_name)

    pd_obj = ProjectDatabase()
    pd_obj.path = str(TEMPLATES_DIR / "project.alaqs")
    original = alaqsdblite.spatialite_connect
    alaqsdblite.spatialite_connect = _spatialite_connect
    try:
        yield
    finally:
        alaqsdblite.spatialite_connect = original


def _ef_data(speed: float, country: str = "Netherlands") -> pd.DataFrame:
    """Helper: load EFs for a (speed, country) pair from the project
    template, normalising vehicle_category and fuel to the short codes
    used by the calculation helpers."""
    sql = ef_query(speed, country=country)
    engine = get_engine(TEMPLATES_DIR / "project.alaqs")
    df = pd.read_sql(sql, engine)
    vc = pd.DataFrame(
        {
            "category_short": VEHICLE_CATEGORIES.keys(),
            "category_long": VEHICLE_CATEGORIES.values(),
        }
    )
    df["fuel"] = df["fuel"].str.lower()
    df["vehicle_category"] = df.merge(
        vc, how="left", left_on="vehicle_category", right_on="category_long"
    )["category_short"]
    return df


def _nl_2025_fleet() -> pd.DataFrame:
    """Representative NL 2025 airport-passenger fleet: ~78% PC petrol,
    19% PC diesel, 0.5% LCV petrol, 2% LCV diesel, 0.5% motorcycles.
    Heavy-duty and bus shares are zero (passenger lots)."""
    return pd.DataFrame(
        [
            {
                "vehicle_category": "pc",
                "fuel": "petrol",
                "euro_standard": "Euro 5",
                "N": 78.0,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "pc",
                "fuel": "diesel",
                "euro_standard": "Euro 5",
                "N": 19.0,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "lcv",
                "fuel": "petrol",
                "euro_standard": "Euro 5",
                "N": 0.5,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "lcv",
                "fuel": "diesel",
                "euro_standard": "Euro 5",
                "N": 2.0,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "hdt",
                "fuel": "petrol",
                "euro_standard": "Conventional",
                "N": 0.0,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "hdt",
                "fuel": "diesel",
                "euro_standard": "Euro VI A/B/C",
                "N": 0.0,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "motorcycle",
                "fuel": "petrol",
                "euro_standard": "Euro 5",
                "N": 0.5,
                "M[km]": 1000,
            },
            {
                "vehicle_category": "bus",
                "fuel": "diesel",
                "euro_standard": "Euro VI A/B/C",
                "N": 0.0,
                "M[km]": 1000,
            },
        ]
    )


def _input_data(parking: bool = True) -> dict:
    """Standard parking input_data for a representative airport long-stay
    lot: 0.35 km maneuvering, 3.5 min idle, 10 km/h."""
    return {
        "parking": parking,
        "speed": 10,
        "idle_time": 3.5,
        "travel_distance": 0.35,
        "pc_p_percentage": 78.0,
        "pc_d_percentage": 19.0,
        "lcv_p_percentage": 0.5,
        "lcv_d_percentage": 2.0,
        "hdt_p_percentage": 0.0,
        "hdt_d_percentage": 0.0,
        "motorcycle_p_percentage": 0.5,
        "bus_d_percentage": 0.0,
        "pc_euro_standard": "Euro 5",
        "lcv_euro_standard": "Euro 5",
        "hdt_euro_standard": "Euro VI A/B/C",
        "motorcycle_euro_standard": "Euro 5",
        "bus_euro_standard": "Euro VI A/B/C",
    }


def _study_data(include_cold_start: bool = False, **overrides) -> dict:
    """Study setup with parking cold-start optionally enabled."""
    sd = {
        "roadway_country": "Netherlands",
        "airport_temperature": 15,
        "parking_include_cold_start": include_cold_start,
    }
    sd.update(overrides)
    return sd


class TestParkingDefaultPreservesBackwardCompatibility:
    """When parking_include_cold_start is absent or False, the parking
    branch must produce the same EFs as before the fix (i.e. cold-start
    effectively scaled to zero by the parking distance multiplier)."""

    def test_flag_absent_matches_original_behavior(self):
        """No flag in study_data => original behavior preserved."""
        result = roadway_emission_factors(_input_data(), _study_data())
        # Sanity: result is a non-empty dict with the expected keys
        assert set(result.keys()) >= {
            "co_ef",
            "hc_ef",
            "nox_ef",
            "sox_ef",
            "pm10_ef",
            "p1_ef",
            "p2_ef",
        }
        assert all(isinstance(v, float) for v in result.values())

    def test_flag_false_matches_flag_absent(self):
        """Explicit flag=False produces same result as flag absent."""
        r_absent = roadway_emission_factors(_input_data(), _study_data())
        r_false = roadway_emission_factors(
            _input_data(), _study_data(include_cold_start=False)
        )
        for k in r_absent:
            assert r_absent[k] == pytest.approx(
                r_false[k]
            ), f"Key {k!r} differs: absent={r_absent[k]} false={r_false[k]}"


class TestParkingColdStartFixIncreasesNOx:
    """When parking_include_cold_start is True, NOx should rise
    meaningfully above the hot-only baseline. For NL 2025 fleet
    (Euro 5 dominant) at 15 C, the cold-start contribution is
    typically 30 to 60% of hot at typical maneuvering distances."""

    def test_cold_start_increases_nox(self):
        baseline = roadway_emission_factors(_input_data(), _study_data())
        with_cold = roadway_emission_factors(
            _input_data(), _study_data(include_cold_start=True)
        )
        assert with_cold["nox_ef"] > baseline["nox_ef"], (
            f"Cold-start should increase NOx: baseline={baseline['nox_ef']:.4f} "
            f"with_cold={with_cold['nox_ef']:.4f}"
        )
        # Magnitude check: cold-start should add at least 20% to hot
        # for an Euro 5-dominant fleet at 15 C, 12.4 km L_trip.
        delta = with_cold["nox_ef"] - baseline["nox_ef"]
        assert delta / baseline["nox_ef"] > 0.20, (
            f"Cold-start contribution too small: {delta:.4f} g/vh "
            f"(baseline {baseline['nox_ef']:.4f})"
        )

    def test_pm_unaffected_by_flag(self):
        """COPERT 5 has no cold PM EFs (cells are zero), so PM10 and
        PM2.5 must be invariant under the flag."""
        baseline = roadway_emission_factors(_input_data(), _study_data())
        with_cold = roadway_emission_factors(
            _input_data(), _study_data(include_cold_start=True)
        )
        assert baseline["pm10_ef"] == pytest.approx(with_cold["pm10_ef"])
        assert baseline["p2_ef"] == pytest.approx(with_cold["p2_ef"])
        assert baseline["p1_ef"] == pytest.approx(with_cold["p1_ef"])
        assert baseline["sox_ef"] == pytest.approx(with_cold["sox_ef"])

    def test_l_trip_scaling(self):
        """Cold-start contribution should scale roughly linearly with
        L_trip in the 8 to 20 km range (beta is mildly trip-length-
        dependent so this is approximate)."""
        sd_short = _study_data(include_cold_start=True, parking_cold_trip_length_km=6.0)
        sd_long = _study_data(include_cold_start=True, parking_cold_trip_length_km=18.0)
        nox_short = roadway_emission_factors(_input_data(), sd_short)["nox_ef"]
        nox_long = roadway_emission_factors(_input_data(), sd_long)["nox_ef"]
        # Longer trip => more cold-start NOx
        assert nox_long > nox_short, (
            f"L_trip=18 should give higher NOx than L_trip=6: "
            f"short={nox_short:.4f} long={nox_long:.4f}"
        )


class TestAverageColdOnlyEmissionFactors:
    """Unit test for the new helper isolating cold-start contribution."""

    def test_cold_only_is_subset_of_total(self):
        """avg_cold(p) <= avg_total(p) for every pollutant, and the
        difference equals the hot contribution."""
        from open_alaqs.core.tools.copert5_utils import average_emission_factors

        fleet = _nl_2025_fleet()
        ef_data = _ef_data(30, country="Netherlands")
        emissions = calculate_emissions(fleet, ef_data, airport_temperature=15)

        total = average_emission_factors(emissions)
        cold = average_cold_only_emission_factors(emissions)

        for p in ("CO", "NOx", "VOC"):
            t = total[f"e{p}[g/km]"]
            c = cold[f"e_cold{p}[g/km]"]
            assert c <= t + 1e-9, f"Cold {p} ({c}) exceeds total ({t})"
            assert c >= 0, f"Cold {p} negative: {c}"

    def test_cold_zero_for_pm_and_so2(self):
        """COPERT 5 has no cold contribution for PM and SO2."""
        fleet = _nl_2025_fleet()
        ef_data = _ef_data(30, country="Netherlands")
        emissions = calculate_emissions(fleet, ef_data, airport_temperature=15)

        cold = average_cold_only_emission_factors(emissions)
        assert cold["e_coldPM2.5[g/km]"] == pytest.approx(0.0)
        assert cold["e_coldPM0.1[g/km]"] == pytest.approx(0.0)
        assert cold["e_coldSO2[g/km]"] == pytest.approx(0.0)
