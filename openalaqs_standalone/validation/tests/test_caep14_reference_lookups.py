"""The CAEP14 reference finds engines and helicopters the way the plugin and the standalone do.

Two rules of the reference held only on the training fixture until October 2026:
the engine was matched with `engine_full_name LIKE %engine_name%` (nothing found when
the table carries the real designation in `engine_full_name`, several rows found for a
short name), and a helicopter was a movement without a `profile_id`. Both are exercised
here by editing a copy of the fixture: the reference must still equal the standalone.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone.compute_movements import build_context, compute_for_movement

DATA = Path(__file__).resolve().parents[1] / "data"
FIXTURE = DATA / "training_v3.alaqs"
TOOLS = Path(__file__).resolve().parents[1] / "tools"
POLLUTANTS = ("co", "co2", "hc", "nox", "pm10")


@pytest.fixture(scope="module")
def ref():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _connect(ref, dst):
    try:
        rconn = ref._connect(str(dst))
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    ctx_ref = {
        "runway": ref._get_runway(rconn),
        "grid_bounds": ref._grid_bounds_3857(rconn),
    }
    return rconn, ctx_ref


def _assert_equal(ref, dst, oid, method="bymode"):
    rconn, ctx_ref = _connect(ref, dst)
    with sqlite3.connect(dst) as conn:
        ctx_sa = build_context(conn)
        sa = compute_for_movement(conn, oid, ctx_sa, method=method)
        rr = ref.compute_for_movement(rconn, oid, ctx_ref, method=method)
    rconn.close()
    assert sa is not None and rr is not None, oid
    for p in POLLUTANTS:
        assert rr["total_em_kg"][p] == pytest.approx(sa["total_em_kg"][p], rel=1e-9), (
            oid,
            p,
        )
    return rr


def test_engine_found_by_engine_name_when_full_name_is_the_designation(tmp_path, ref):
    """Movement 1 (A20N, 01P20CM128): the engine table says 'LEAP-1A26' in engine_full_name."""
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute(
            "UPDATE default_aircraft_engine_ei SET engine_full_name = 'LEAP-1A26' "
            "WHERE engine_name = '01P20CM128'"
        )
    rr = _assert_equal(ref, dst, 1)
    assert rr["total_em_kg"]["nox"] > 0


def test_short_engine_name_does_not_match_longer_names(tmp_path, ref):
    """An engine 'X-1' must not pick up the rows of 'X-10': exact match, as the plugin."""
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute(
            "UPDATE default_aircraft_engine_ei SET engine_name = 'X-1', engine_full_name = 'X-1' WHERE engine_name = '01P20CM128'"
        )
        conn.execute(
            "INSERT INTO default_aircraft_engine_ei (engine_type, engine_full_name, engine_name, thrust, mode, "
            "fuel_kg_sec, co_ei, hc_ei, nox_ei, sox_ei, pm10_ei) "
            "SELECT engine_type, 'X-10', 'X-10', thrust, mode, fuel_kg_sec * 3, co_ei, hc_ei, nox_ei * 3, sox_ei, pm10_ei "
            "FROM default_aircraft_engine_ei WHERE engine_name = 'X-1'"
        )
        conn.execute(
            "UPDATE user_aircraft_movements SET engine_name = 'X-1' WHERE oid = 1"
        )
    ei = ref._get_engine_ei(sqlite3.connect(dst), "X-1")
    assert set(ei) == {"TX", "AP", "CL", "TO"}
    _assert_equal(ref, dst, 1)


def test_helicopter_with_a_profile_id_is_still_a_helicopter(tmp_path, ref):
    """Movement 14 (AS50) given a profile_id: dispatch on default_helicopter, not on the blank."""
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute(
            "UPDATE user_aircraft_movements SET profile_id = 'HELIPROF-D-1-STANDARD' WHERE oid = 14"
        )
    rr = _assert_equal(ref, dst, 14)
    assert (
        "GI" in rr["traj_fuel_by_mode_kg"]
    )  # the FOCA result (ground idle), not the fixed-wing one
