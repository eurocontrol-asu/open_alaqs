"""BFFM2 edge cases: the standalone and the CAEP14 reference give the plugin's result.

The plugin (open_alaqs/core) is canonical. Four cases where the standalone and
the reference differed from it:

1. BFFM2 taxi: the fuel flow is the twin-quadratic fit at the movement's
   engine_thrust_level_for_taxiing (0.07 when not given), scaled to the ground
   ambient. A thrust the fit rejects (7 typed for 7 %, -0.1) gives the bymode
   TX index (TaxiingEmissionCalculator). Both used the EEDB TX fuel flow
   whatever the thrust.
2. Flight segment power out of the fit range (bffm2_traj, no supplied fuel
   flow): 1.0 < P <= 1.05 is clamped to 1.0; above 1.05 and below 0 the
   segment takes the bymode index (_get_emission_index_bffm2).
3. A supplied fuel flow of zero or below is no fuel flow.
4. tow_ratio 0, negative or NaN is 1.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import shutil
import sqlite3
from pathlib import Path

import pytest

from open_alaqs.core.tools.twin_quadratic_fit_method import (
    calculate_fuel_flow_from_power_setting,
)
from openalaqs_standalone import compute_aircraft as ca
from openalaqs_standalone import movements as mv
from openalaqs_standalone import nox_correction as nc
from openalaqs_standalone.compute_movements import build_context, compute_for_movement

DATA = Path(__file__).resolve().parents[1] / "data"
FIXTURE = DATA / "training_v3.alaqs"
TOOLS = Path(__file__).resolve().parents[1] / "tools"
POLLUTANTS = ("co", "co2", "hc", "nox", "pm10", "sox")
DEP_OID = 2  # A20N departure, ANP profile JET-SMALL-D-1 (power, no fuel flow)
DEP_PROFILE = "JET-SMALL-D-1"
ADSB_OID = 11  # CUSTOM profile with power and fuel_flow_kgm
LOGGER = "openalaqs_standalone.compute_aircraft"

ENGINE_EI = {
    "TX": {"ff": 0.091},
    "AP": {"ff": 0.29},
    "CL": {"ff": 0.792},
    "TO": {"ff": 0.946},
}
PLUGIN_EEDB = {0.07: 0.091, 0.30: 0.29, 0.85: 0.792, 1.0: 0.946}


@pytest.fixture(scope="module")
def ref():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def study(tmp_path):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    return dst


def _edit(db, sql, params=()):
    with sqlite3.connect(db) as conn:
        conn.execute(sql, params)
        conn.commit()


def _standalone(db, oid, method):
    with sqlite3.connect(db) as conn:
        return compute_for_movement(conn, oid, build_context(conn), method=method)


def _reference(ref, db, oid, method):
    try:
        rconn = ref._connect(str(db))
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    ctx = {
        "runway": ref._get_runway(rconn),
        "grid_bounds": ref._grid_bounds_3857(rconn),
    }
    try:
        return ref.compute_for_movement(rconn, oid, ctx, method=method)
    finally:
        rconn.close()


def _taxi(res):
    return {
        p: res["tx_em_kg"][p] + res["queue_em_kg"][p] + res["stop_em_kg"][p]
        for p in POLLUTANTS
    }


def _flight(res):
    return {p: sum(s["em_kg"][p] for s in res["segments"]) for p in POLLUTANTS}


def _ref_flight(res):
    return {p: res["total_em_kg"][p] - res["tx_em_kg"][p] for p in POLLUTANTS}


def _approx(a, b, rel=1e-12):
    for p in POLLUTANTS:
        assert a[p] == pytest.approx(b[p], rel=rel, abs=1e-15), p


# ---------------------------------------------------------------------------
# The twin-quadratic fit: same values and same rejections as the plugin's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "power", [0.0, 0.03, 0.07, 0.3, 0.6, 0.85, 0.9, 1.0, 1.02, 1.05]
)
def test_fit_matches_plugin_in_range(power, ref):
    expected = calculate_fuel_flow_from_power_setting(power, PLUGIN_EEDB)
    assert ca._twin_quadratic_ff_from_power(power, ENGINE_EI) == pytest.approx(
        expected, rel=1e-14
    )
    assert ref._twin_quadratic_ff_from_power(power, ENGINE_EI) == pytest.approx(
        expected, rel=1e-14
    )


@pytest.mark.parametrize("power", [-0.1, -1e-9, 1.0500001, 1.4, 7.0, math.nan])
def test_fit_rejects_as_plugin(power, ref):
    with pytest.raises(ValueError):
        calculate_fuel_flow_from_power_setting(power, PLUGIN_EEDB)
    with pytest.raises(ValueError):
        ca._twin_quadratic_ff_from_power(power, ENGINE_EI)
    with pytest.raises(ValueError):
        ref._twin_quadratic_ff_from_power(power, ENGINE_EI)


# ---------------------------------------------------------------------------
# 1. BFFM2 taxi thrust
# ---------------------------------------------------------------------------


def test_taxi_ff_helper():
    ground = {"T_K": 300.0, "P_Pa": 95000.0}
    scale = 95000.0 / 101325.0 * math.sqrt(300.0 / 288.15)
    ff, bymode = ca._bffm2_taxi_ff(0.07, ENGINE_EI, ground)
    assert not bymode and ff == pytest.approx(0.091 * scale, rel=1e-14)
    ff, bymode = ca._bffm2_taxi_ff(0.30, ENGINE_EI, ground)
    assert not bymode and ff == pytest.approx(0.29 * scale, rel=1e-14)
    # 0 is a thrust (not "not given"): the fit floors it at idle
    ff, bymode = ca._bffm2_taxi_ff(0.0, ENGINE_EI, ground)
    assert not bymode and ff == pytest.approx(0.091 * scale, rel=1e-14)
    for bad in (7.0, -0.1):
        ff, bymode = ca._bffm2_taxi_ff(bad, ENGINE_EI, ground)
        assert bymode and ff == 0.091  # EEDB TX, unscaled


def test_movement_reads_taxi_thrust(study, ref):
    for value, expected in ((None, 0.07), ("", 0.07), (0, 0.0), (0.3, 0.3)):
        _edit(
            study,
            "UPDATE user_aircraft_movements SET engine_thrust_level_for_taxiing = ? "
            "WHERE oid = ?",
            (value, DEP_OID),
        )
        with sqlite3.connect(study) as conn:
            got = mv.get_movement(conn, DEP_OID)["engine_thrust_level_for_taxiing"]
        assert got == expected, value
        rconn = sqlite3.connect(study)
        try:
            got = ref._get_movement(rconn, DEP_OID)["engine_thrust_level_for_taxiing"]
        finally:
            rconn.close()
        assert got == expected, value


@pytest.mark.parametrize("method", ["bffm2_anchor", "bffm2_traj"])
def test_taxi_thrust_out_of_range_takes_bymode(study, ref, method, caplog):
    base_sa = _standalone(study, DEP_OID, "bymode")
    base_rr = _reference(ref, study, DEP_OID, "bymode")
    _edit(
        study,
        "UPDATE user_aircraft_movements SET engine_thrust_level_for_taxiing = 7.0 "
        "WHERE oid = ?",
        (DEP_OID,),
    )
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        sa = _standalone(study, DEP_OID, method)
    assert any(
        "engine_thrust_level_for_taxiing" in r.getMessage()
        for r in caplog.records
        if r.name == LOGGER
    )
    rr = _reference(ref, study, DEP_OID, method)
    _approx(_taxi(sa), _taxi(base_sa))
    assert sa["tx_fuel_kg"] == pytest.approx(base_sa["tx_fuel_kg"], rel=1e-14)
    _approx(rr["tx_em_kg"], base_rr["tx_em_kg"])
    for p in POLLUTANTS:
        assert rr["total_em_kg"][p] == pytest.approx(sa["total_em_kg"][p], rel=1e-9)


def test_taxi_thrust_sets_fit_point(study, ref):
    """Thrust 0.30: the taxi fuel is the approach fuel flow (scaled), not idle."""
    sa07 = _standalone(study, DEP_OID, "bffm2_traj")
    _edit(
        study,
        "UPDATE user_aircraft_movements SET engine_thrust_level_for_taxiing = NULL "
        "WHERE oid = ?",
        (DEP_OID,),
    )
    sa_null = _standalone(study, DEP_OID, "bffm2_traj")
    _approx(sa_null["total_em_kg"], sa07["total_em_kg"], rel=0.0)
    _edit(
        study,
        "UPDATE user_aircraft_movements SET engine_thrust_level_for_taxiing = 0.30 "
        "WHERE oid = ?",
        (DEP_OID,),
    )
    sa30 = _standalone(study, DEP_OID, "bffm2_traj")
    rr30 = _reference(ref, study, DEP_OID, "bffm2_traj")
    with sqlite3.connect(study) as conn:
        ei = mv.get_engine_ei(conn, "01P20CM128")
    assert sa30["tx_fuel_kg"] / sa07["tx_fuel_kg"] == pytest.approx(
        ei["AP"]["ff"] / ei["TX"]["ff"], rel=1e-12
    )
    for p in POLLUTANTS:
        assert rr30["total_em_kg"][p] == pytest.approx(sa30["total_em_kg"][p], rel=1e-9)


# ---------------------------------------------------------------------------
# 2. Flight segment power out of the fit range
# ---------------------------------------------------------------------------


def test_bymode_reason():
    f = ca._bffm2_point_bymode_reason
    assert f(None, None, "bffm2_traj") == "no_power"
    assert f(None, 0.0, "bffm2_anchor") == "no_power"
    assert f(None, -1.0, "bffm2_traj") == "no_power"
    assert f(2.0, None, "bffm2_traj") == "power_oor"
    assert f(-0.1, 0.0, "bffm2_traj") == "power_oor"
    assert f(1.05, None, "bffm2_traj") is None
    assert f(2.0, None, "bffm2_anchor") is None  # the anchor never calls the fit
    assert f(2.0, 1.2, "bffm2_traj") is None  # supplied fuel flow, fit not used


@pytest.mark.parametrize("power", [2.0, -0.1])
def test_power_out_of_range_takes_bymode(study, ref, power, caplog):
    base_sa = _standalone(study, DEP_OID, "bymode")
    base_rr = _reference(ref, study, DEP_OID, "bymode")
    _edit(
        study,
        "UPDATE default_aircraft_profiles SET power = ?, fuel_flow_kgm = NULL "
        "WHERE profile_id = ?",
        (power, DEP_PROFILE),
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        sa = _standalone(study, DEP_OID, "bffm2_traj")
    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == LOGGER and "twin-quadratic range" in r.getMessage()
    ]
    assert len(msgs) == 1, msgs
    rr = _reference(ref, study, DEP_OID, "bffm2_traj")
    _approx(_flight(sa), _flight(base_sa))
    _approx(_ref_flight(rr), _ref_flight(base_rr))
    for p in POLLUTANTS:
        assert rr["total_em_kg"][p] == pytest.approx(sa["total_em_kg"][p], rel=1e-9)


def test_power_overshoot_is_clamped(study, ref):
    _edit(
        study,
        "UPDATE default_aircraft_profiles SET power = 1.0 WHERE profile_id = ?",
        (DEP_PROFILE,),
    )
    sa_1 = _standalone(study, DEP_OID, "bffm2_traj")
    rr_1 = _reference(ref, study, DEP_OID, "bffm2_traj")
    _edit(
        study,
        "UPDATE default_aircraft_profiles SET power = 1.04 WHERE profile_id = ?",
        (DEP_PROFILE,),
    )
    sa_104 = _standalone(study, DEP_OID, "bffm2_traj")
    rr_104 = _reference(ref, study, DEP_OID, "bffm2_traj")
    _approx(sa_104["total_em_kg"], sa_1["total_em_kg"], rel=0.0)
    _approx(rr_104["total_em_kg"], rr_1["total_em_kg"], rel=0.0)


# ---------------------------------------------------------------------------
# 3. Supplied fuel flow of zero or below is no fuel flow
# ---------------------------------------------------------------------------


def test_supplied_ff_ok():
    assert ca._supplied_ff_ok(0.5)
    for v in (None, 0, 0.0, -1.0, math.nan):
        assert not ca._supplied_ff_ok(v), v


@pytest.mark.parametrize("method", ["bffm2_anchor", "bffm2_traj"])
@pytest.mark.parametrize("keep_power", [True, False])
def test_non_positive_fuel_flow_is_missing(study, ref, method, keep_power):
    with sqlite3.connect(study) as conn:
        profile = conn.execute(
            "SELECT profile_id FROM user_aircraft_movements WHERE oid = ?", (ADSB_OID,)
        ).fetchone()[0]
    if not keep_power:
        _edit(
            study,
            "UPDATE default_aircraft_profiles SET power = NULL WHERE profile_id = ?",
            (profile,),
        )
    _edit(
        study,
        "UPDATE default_aircraft_profiles SET fuel_flow_kgm = NULL WHERE profile_id = ?",
        (profile,),
    )
    sa_none = _standalone(study, ADSB_OID, method)
    rr_none = _reference(ref, study, ADSB_OID, method)
    for value in (0.0, -5.0):
        _edit(
            study,
            "UPDATE default_aircraft_profiles SET fuel_flow_kgm = ? WHERE profile_id = ?",
            (value, profile),
        )
        sa = _standalone(study, ADSB_OID, method)
        rr = _reference(ref, study, ADSB_OID, method)
        _approx(sa["total_em_kg"], sa_none["total_em_kg"], rel=0.0)
        _approx(rr["total_em_kg"], rr_none["total_em_kg"], rel=0.0)
        for p in POLLUTANTS:
            assert rr["total_em_kg"][p] == pytest.approx(sa["total_em_kg"][p], rel=1e-9)


# ---------------------------------------------------------------------------
# 4. tow_ratio 0, negative or NaN is 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tow", [0.0, -0.5, math.nan, None])
def test_tow_ratio_not_positive_is_one(ref, tow):
    meteo = {"T_K": 295.0, "P_Pa": 100000.0, "RH": 0.6}
    assert ref._nox_ambient_factor(meteo, 100.0, tow) == ref._nox_ambient_factor(
        meteo, 100.0, 1.0
    )
    kw = dict(
        temperature_k=295.0,
        pressure_pa=100000.0,
        relative_humidity=0.6,
        airport_elevation_m=100.0,
    )
    assert nc.correction_factor("TO", tow_ratio=tow, **kw) == nc.correction_factor(
        "TO", tow_ratio=1.0, **kw
    )
