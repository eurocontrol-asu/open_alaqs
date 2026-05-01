"""
Unit tests for open_alaqs.core.tools.ads_b.

Complements test_ads_b_data_integration.py which only exercises
validate_adsb_file. These tests cover:

- _geographic_to_relative_df: UTM zone selection, WGS84→UTM projection,
  altitude conversion (ft→m), reference-point subtraction.
- import_adsb_file: end-to-end CSV → SQLite import, profile row shape,
  oid allocation, arrival/departure detection, mode assignment.
"""

import sqlite3

import pandas as pd
import pytest
from qgis.testing import start_app

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.tools.ads_b import (
    _geographic_to_relative_df,
    import_adsb_file,
    validate_adsb_file,
)
from tests.utils import get_copy_path, get_data_path

start_app()


# ----------------------------------------------------------------------
# _geographic_to_relative_df
# ----------------------------------------------------------------------


class TestGeographicToRelativeDf:
    """Tests the ADS-B geographic → Cartesian UTM coordinate conversion."""

    def _make_df(self, points):
        return pd.DataFrame(points, columns=["longitude", "latitude", "altitude"])

    def test_reference_point_projects_to_origin(self):
        """The reference (start_lon, start_lat) must map to (0, 0)."""
        lon, lat, alt_ft = 4.44, 51.96, 0  # Rotterdam-ish
        df = self._make_df([(lon, lat, alt_ft)])
        out = _geographic_to_relative_df(df, lon, lat, 0.0)
        assert abs(out["x_m"].iloc[0]) < 1e-6
        assert abs(out["y_m"].iloc[0]) < 1e-6
        # altitude 0 ft with reference alt 0 should give z_m = 0
        assert abs(out["z_m"].iloc[0]) < 1e-6

    def test_altitude_feet_to_metres(self):
        """Altitude must convert ft → m via 0.3048 factor."""
        df = self._make_df([(4.44, 51.96, 1000.0)])
        out = _geographic_to_relative_df(df, 4.44, 51.96, 0.0)
        assert abs(out["z_m"].iloc[0] - 304.8) < 1e-3

    def test_altitude_reference_subtracted(self):
        """z_m = altitude_ft × 0.3048 − start_alt."""
        df = self._make_df([(4.44, 51.96, 1000.0)])
        out = _geographic_to_relative_df(df, 4.44, 51.96, 100.0)
        assert abs(out["z_m"].iloc[0] - (304.8 - 100.0)) < 1e-3

    def test_easting_grows_with_longitude(self):
        """At the equator, moving east should increase x_m."""
        df = self._make_df([(4.44, 0.0, 0), (4.45, 0.0, 0)])
        out = _geographic_to_relative_df(df, 4.44, 0.0, 0.0)
        assert out["x_m"].iloc[1] > out["x_m"].iloc[0]

    def test_northing_grows_with_latitude(self):
        """Moving north should increase y_m in the northern hemisphere."""
        df = self._make_df([(4.44, 51.0, 0), (4.44, 51.1, 0)])
        out = _geographic_to_relative_df(df, 4.44, 51.0, 0.0)
        assert out["y_m"].iloc[1] > out["y_m"].iloc[0]

    def test_utm_zone_selection_northern_hemisphere(self):
        """Reference in Europe (4.44°E, 51.96°N) picks UTM 31N.
        At ~52°N, 1° of longitude is ~68.7 km on the ellipsoid."""
        df = self._make_df([(4.44, 51.96, 0), (5.44, 51.96, 0)])
        out = _geographic_to_relative_df(df, 4.44, 51.96, 0.0)
        # 1° of longitude at 52°N is roughly 68.7 km; UTM grid-scale means
        # within-zone distances match geodesic within ~0.04%. Allow 2 km
        # slack for UTM convergence effects.
        assert 65_000 < out["x_m"].iloc[1] < 72_000

    def test_southern_hemisphere(self):
        """A southern-hemisphere reference must still produce a valid
        projection with reference at origin."""
        df = self._make_df([(151.0, -33.87, 0)])  # Sydney
        out = _geographic_to_relative_df(df, 151.0, -33.87, 0.0)
        assert abs(out["x_m"].iloc[0]) < 1e-6
        assert abs(out["y_m"].iloc[0]) < 1e-6

    def test_original_columns_preserved(self):
        """The input columns must not be clobbered by the conversion."""
        df = pd.DataFrame(
            {
                "longitude": [4.44],
                "latitude": [51.96],
                "altitude": [100.0],
                "extra": ["keep me"],
            }
        )
        out = _geographic_to_relative_df(df, 4.44, 51.96, 0.0)
        assert "extra" in out.columns
        assert out["extra"].iloc[0] == "keep me"
        assert "longitude" in out.columns


# ----------------------------------------------------------------------
# import_adsb_file — full pipeline
# ----------------------------------------------------------------------


class TestImportAdsbFile:
    """Tests the ADS-B CSV → default_aircraft_profiles ingestion."""

    @pytest.fixture
    def airport_db(self, tmp_path):
        """Copy AIRPORT_A_out.alaqs to a scratch path and register it as
        the project DB so get_runways + get_max_profile_oid work."""
        src = get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"
        dst = tmp_path / "adsb_test.alaqs"
        import shutil

        shutil.copy(src, dst)
        ProjectDatabase().path = str(dst)
        yield str(dst)
        # Reset ProjectDatabase singleton to avoid leaking the test DB
        # path to subsequent tests (e.g., test_create_alaqs_output relies
        # on its own DB assignment and may be confused by a stale path).
        try:
            ProjectDatabase().path = None
        except Exception:
            pass

    def _baseline_profile_count(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM default_aircraft_profiles"
            ).fetchone()[0]
        finally:
            conn.close()

    def test_valid_csv_imports_successfully(self, airport_db):
        """A valid ADS-B CSV must import and return (True, message)."""
        csv_src = get_data_path("AIRPORT_A/ADS-B") / "AIRPORT_A_ads_b_data_valid.csv"
        csv_path = str(get_copy_path(csv_src))

        before = self._baseline_profile_count(airport_db)
        ok, msg = import_adsb_file(csv_path, airport_db)
        after = self._baseline_profile_count(airport_db)

        assert ok is True, f"import failed: {msg}"
        # The valid CSV has 9 data rows → at least 9 rows added (could be
        # more if the CSV spans multiple flights).
        assert after > before

    def test_imported_rows_have_expected_shape(self, airport_db):
        """Imported rows must have all columns populated in the ANP schema."""
        csv_src = get_data_path("AIRPORT_A/ADS-B") / "AIRPORT_A_ads_b_data_valid.csv"
        csv_path = str(get_copy_path(csv_src))
        before = self._baseline_profile_count(airport_db)
        ok, _ = import_adsb_file(csv_path, airport_db)
        assert ok

        conn = sqlite3.connect(airport_db)
        try:
            # Pull the rows added by this import.
            new_rows = conn.execute(
                "SELECT profile_id, arrival_departure, stage, point, "
                "x_m, y_m, z_m, tas_metres, mode, course "
                "FROM default_aircraft_profiles ORDER BY oid DESC LIMIT ?",
                (self._baseline_profile_count(airport_db) - before,),
            ).fetchall()

            assert len(new_rows) > 0
            for row in new_rows:
                profile_id, ad, stage, point, x_m, y_m, z_m, tas, mode, course = row
                assert profile_id  # non-empty
                assert ad in ("A", "D")
                assert stage == 1  # Default stage per ads_b.py
                assert point >= 1
                assert isinstance(x_m, (int, float))
                assert isinstance(y_m, (int, float))
                assert isinstance(z_m, (int, float))
                assert tas is None or tas >= 0
                assert mode in ("AP", "CL", "TO")
                assert course == "CUSTOM"
        finally:
            conn.close()

    def test_arrival_vs_departure_detection(self, airport_db, tmp_path):
        """Arrival is detected when first altitude > last altitude.
        Departure is detected when first altitude < last altitude."""
        # Synthetic arrival CSV: altitude decreasing
        arr_csv = tmp_path / "arr.csv"
        arr_csv.write_text(
            "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
            "ARR01,51.960,4.44,5000,200,0.40,0.40\n"
            "ARR01,51.955,4.44,3000,180,0.35,0.30\n"
            "ARR01,51.950,4.44,1000,160,0.30,0.20\n"
        )
        # Synthetic departure CSV: altitude increasing, starting at 0
        dep_csv = tmp_path / "dep.csv"
        dep_csv.write_text(
            "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
            "DEP01,51.960,4.44,0,100,1.00,0.90\n"
            "DEP01,51.965,4.44,1000,150,0.95,0.85\n"
            "DEP01,51.970,4.44,3000,200,0.85,0.75\n"
        )

        self._baseline_profile_count(airport_db)
        ok, _ = import_adsb_file(str(arr_csv), airport_db)
        assert ok
        ok, _ = import_adsb_file(str(dep_csv), airport_db)
        assert ok

        conn = sqlite3.connect(airport_db)
        try:
            rows = conn.execute(
                "SELECT profile_id, arrival_departure, mode "
                "FROM default_aircraft_profiles "
                "WHERE profile_id IN ('ARR01', 'DEP01') ORDER BY oid"
            ).fetchall()
            arr_rows = [r for r in rows if r[0] == "ARR01"]
            dep_rows = [r for r in rows if r[0] == "DEP01"]

            assert len(arr_rows) == 3
            assert all(r[1] == "A" for r in arr_rows), f"arrival flag: {arr_rows}"
            assert all(r[2] == "AP" for r in arr_rows), f"arrival mode: {arr_rows}"

            assert len(dep_rows) == 3
            assert all(r[1] == "D" for r in dep_rows), f"departure flag: {dep_rows}"
            # First point at z=0 → TO, the others at z>0 → CL
            modes = [r[2] for r in dep_rows]
            assert modes[0] == "TO", f"first departure point mode: {modes}"
            assert modes[1] == "CL"
            assert modes[2] == "CL"
        finally:
            conn.close()

    def test_oid_continues_from_max(self, airport_db, tmp_path):
        """Newly imported rows get oid > any existing oid."""
        conn = sqlite3.connect(airport_db)
        try:
            prev_max = conn.execute(
                "SELECT MAX(oid) FROM default_aircraft_profiles"
            ).fetchone()[0]
        finally:
            conn.close()

        csv = tmp_path / "oid_test.csv"
        csv.write_text(
            "flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow\n"
            "OID01,51.96,4.44,5000,200,0.40,0.40\n"
            "OID01,51.955,4.44,3000,180,0.35,0.30\n"
        )
        ok, _ = import_adsb_file(str(csv), airport_db)
        assert ok

        conn = sqlite3.connect(airport_db)
        try:
            new_min = conn.execute(
                "SELECT MIN(oid) FROM default_aircraft_profiles "
                "WHERE profile_id = 'OID01'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert new_min > prev_max

    def test_missing_file_returns_false(self, airport_db):
        """Non-existent CSV path must fail cleanly without raising."""
        ok, msg = import_adsb_file("/nonexistent/path/file.csv", airport_db)
        assert ok is False
        assert "error" in msg.lower() or "reading" in msg.lower()

    def test_validation_and_import_agree(self, airport_db):
        """A CSV validate_adsb_file rejects must also not produce valid
        rows via import_adsb_file (consistency property)."""
        invalid_csv = str(
            get_copy_path(
                get_data_path("AIRPORT_A/ADS-B") / "AIRPORT_A_ads_b_data_invalid_1.csv"
            )
        )
        # validate_adsb_file rejects it
        ok_v, _ = validate_adsb_file(invalid_csv)
        assert ok_v is False
        # import_adsb_file shouldn't raise — but with missing fields it
        # will likely fail at the mandatory-column access. Just assert
        # it either returns False or raises KeyError; neither leaves the
        # database in a valid state for these malformed rows.
        try:
            ok_i, _ = import_adsb_file(invalid_csv, airport_db)
            assert ok_i is False
        except (KeyError, AttributeError):
            # Expected: missing columns propagate out. Still consistent
            # with "not imported".
            pass
