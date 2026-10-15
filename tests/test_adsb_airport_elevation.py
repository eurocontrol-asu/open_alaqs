"""ADS-B import: heights relative to the airport elevation.

ADS-B altitudes are MSL. Profile heights in OpenALAQS are relative to the
airport (ANP profiles start at 0 m; the grid's z origin is 0). The importer
subtracts `user_study_setup.airport_elevation`, so a track at an airport
below sea level (e.g. -15 ft) starts at 0 m, not at -4.572 m. A study with
elevation 0 imports exactly as before.
"""

import shutil
import sqlite3

import pytest
from qgis.testing import start_app

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.tools.ads_b import _airport_elevation_m, import_adsb_file
from tests.utils import get_data_path

start_app()

FT = 0.3048


def _import(tmp_path, elevation_m, profile_id):
    src = get_data_path("generic") / "generic_out.alaqs"
    dst = tmp_path / f"{profile_id}.alaqs"
    shutil.copy(src, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute(
            "UPDATE user_study_setup SET airport_elevation = ?", (elevation_m,)
        )
    ProjectDatabase().path = str(dst)
    csv_path = tmp_path / f"{profile_id}.csv"
    rows = ["flight_id,latitude,longitude,altitude,tas,power_setting,fuel_flow"]
    for i in range(5):  # departure from the runway at -15 ft MSL
        rows.append(
            f"{profile_id},{51.950 + 0.01 * i},4.44,{-15 + 400 * i},"
            f"{150 + 15 * i},{1.0 - 0.03 * i},{0.9 - 0.02 * i}"
        )
    csv_path.write_text("\n".join(rows) + "\n")
    ok, msg = import_adsb_file(str(csv_path), str(dst))
    assert ok, msg
    with sqlite3.connect(dst) as conn:
        z = [
            r[0]
            for r in conn.execute(
                "SELECT z_m FROM default_aircraft_profiles WHERE profile_id = ? "
                "ORDER BY point",
                (profile_id,),
            )
        ]
    return dst, z


@pytest.fixture(autouse=True)
def _reset_project_db():
    yield
    try:
        ProjectDatabase().path = None
    except Exception:
        pass
    try:
        from open_alaqs.core.tools.Singleton import Singleton

        Singleton.reset_all()
    except Exception:
        pass


def test_heights_relative_to_airport_elevation(tmp_path):
    dst, z = _import(tmp_path, -15 * FT, "ELEV01")
    assert _airport_elevation_m(str(dst)) == pytest.approx(-15 * FT)
    assert z[0] == pytest.approx(0.0, abs=1e-3)
    assert z[-1] == pytest.approx((-15 + 1600) * FT + 15 * FT, abs=1e-3)


def test_zero_elevation_unchanged(tmp_path):
    _, z = _import(tmp_path, 0.0, "ELEV02")
    assert z[0] == pytest.approx(-15 * FT, abs=1e-3)  # MSL, as before


def test_ground_run_within_half_an_altitude_step_is_ground(tmp_path):
    """EHRD: field elevation -5 m, the roll reports -15 ft (+0.43 m): height 0 and mode TO."""
    dst, z = _import(tmp_path, -5.0, "ELEV03")
    assert z[0] == 0.0
    assert z[1] == pytest.approx(385 * FT + 5.0, abs=1e-3)  # airborne point unchanged
    with sqlite3.connect(dst) as conn:
        modes = [
            r[0]
            for r in conn.execute(
                "SELECT mode FROM default_aircraft_profiles WHERE profile_id = 'ELEV03' "
                "ORDER BY point"
            )
        ]
    assert modes[0] == "TO" and set(modes[1:]) == {"CL"}


def test_snap_ground_heights_departure_and_arrival():
    from open_alaqs.core.tools.ads_b import GROUND_TOLERANCE_M, _snap_ground_heights

    tol = GROUND_TOLERANCE_M
    dep = _snap_ground_heights([0.43, -1.0, 3.0, 2.0, 50.0, 1.0], is_arrival=False)
    assert list(dep) == [0.0, 0.0, 0.0, 0.0, 50.0, 1.0]  # only the leading run
    arr = _snap_ground_heights([300.0, 2.0, 15.0, 3.5, -2.0], is_arrival=True)
    assert list(arr) == [300.0, 2.0, 15.0, 0.0, 0.0]  # only the trailing run
    assert list(_snap_ground_heights([tol + 0.01], False)) == [tol + 0.01]
