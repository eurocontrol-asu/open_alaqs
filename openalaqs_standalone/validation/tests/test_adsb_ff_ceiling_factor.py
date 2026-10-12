"""BFFM2 trajectory: plausibility limit on a supplied (ADS-B / CUSTOM) fuel flow.

The ICAO take-off fuel flow is a static, sea-level value. In flight, at climb speed,
a high-thrust point can burn a few percent more than that, so the limit is a multiple
(ADSB_FF_CEILING_FACTOR) of the take-off value: below it the supplied fuel flow is
used; above it the point falls back to the mode anchor, as before.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import compute_aircraft as ca
from openalaqs_standalone import movements as mv

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"
ISA = {"T_K": 288.15, "P_Pa": 101325.0, "RH": 0.6}


@pytest.fixture
def setup(tmp_path):
    dst = tmp_path / "training_copy.alaqs"
    shutil.copy(FIXTURE, dst)
    conn = sqlite3.connect(dst)
    pid, point = conn.execute(
        "SELECT profile_id, point FROM default_aircraft_profiles ORDER BY oid LIMIT 1"
    ).fetchone()
    engine = conn.execute(
        "SELECT engine_name FROM default_aircraft_engine_ei WHERE mode='TO' "
        "AND fuel_kg_sec > 0 ORDER BY engine_name LIMIT 1"
    ).fetchone()[0]
    engine_ei = mv.get_engine_ei(conn, engine)
    yield conn, {"profile_id": pid}, (point,), engine_ei
    conn.close()


def _ff(conn, mov, pt, engine_ei, ff_total, n_eng=2, mode="CL"):
    conn.execute(
        "UPDATE default_aircraft_profiles SET fuel_flow_kgm=? WHERE profile_id=? AND point=?",
        (ff_total, mov["profile_id"], pt[0]),
    )
    return ca._bffm2_traj_ff_amb(
        conn, mov, pt, engine_ei[mode], engine_ei, ISA, 0.3, n_eng
    )


def test_factor_value():
    assert ca.ADSB_FF_CEILING_FACTOR == 1.5


@pytest.mark.parametrize("ratio", [0.5, 1.0, 1.06, 1.3, 1.49])
def test_plausible_fuel_flow_above_take_off_is_kept(setup, ratio):
    conn, mov, pt, ei = setup
    to = ei["TO"]["ff"]
    got = _ff(conn, mov, pt, ei, 2 * ratio * to)
    assert got == pytest.approx(ratio * to, rel=1e-12)


@pytest.mark.parametrize("ratio", [1.51, 2.0, 60.0])
def test_implausible_fuel_flow_falls_back_to_mode_anchor(setup, ratio):
    conn, mov, pt, ei = setup
    to = ei["TO"]["ff"]
    got = _ff(conn, mov, pt, ei, 2 * ratio * to)
    assert got == pytest.approx(ei["CL"]["ff"], rel=1e-12)


def test_reference_tool_uses_the_same_factor():
    from openalaqs_standalone.validation.tools import compute_caep14_reference as ref

    assert ref.ADSB_FF_CEILING_FACTOR == ca.ADSB_FF_CEILING_FACTOR
