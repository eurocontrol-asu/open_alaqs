"""Single-engine taxi: tx_em is placed on the route segments by their own
emission (time x engines x taxi_fuel_ratio), not by length or time alone.

Plugin parity of the totals and of the per-segment split is in
tests/test_zz_single_engine_taxi_parity.py (needs QGIS); this test checks that
distribute_to_grid uses the per-segment shares the compute returns.
"""

from __future__ import annotations

import copy
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import geometry as _geo
from openalaqs_standalone import movements as _mv
from openalaqs_standalone.compute_aircraft import _taxi_engine_split
from openalaqs_standalone.compute_movements import build_context, compute_all_movements
from openalaqs_standalone.distribute import (
    _linestring_cell_fractions,
    _segment_cell_fractions,
    distribute_to_grid,
)

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"


def _tx_only(res):
    r = copy.deepcopy(res)
    for k, v in list(r.items()):
        if k.endswith("_em_kg") and isinstance(v, dict) and k != "tx_em_kg":
            r[k] = {p: 0.0 for p in v}
    for s in r["segments"]:
        s["em_kg"] = {p: 0.0 for p in s["em_kg"]}
    return r


def test_departure_split_uses_segment_shares(tmp_path):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    db = tmp_path / "se.alaqs"
    shutil.copy(SRC, db)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE user_aircraft_movements SET taxi_engine_count = 1, "
        "set_time_of_main_engine_start_after_block_off_in_s = 120, "
        "taxi_fuel_ratio = 0.8 WHERE oid = 2"
    )
    conn.commit()
    res = compute_all_movements(conn, method="bymode", use_isa_meteo=False, oids=[2])[2]
    shares = res["tx_segment_weights"]
    assert shares is not None and sum(shares) == pytest.approx(1.0)
    # the route has single-engine and all-engine segments
    assert len(set(round(s, 12) for s in shares)) > 1

    ctx = build_context(conn)
    bounds, grid_def = ctx["grid_bounds"], _mv.get_grid_definition(conn)
    route = _mv.get_movement(conn, 2)["taxi_route"]
    seq = conn.execute(
        "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name=?", (route,)
    ).fetchone()[0]
    want = {}
    for share, tid in zip(shares, [t.strip() for t in seq.split(",") if t.strip()]):
        blob = conn.execute(
            "SELECT geometry FROM shapes_taxiways WHERE taxiway_id=?", (tid,)
        ).fetchone()[0]
        coords = list(_geo.spatialite_blob_to_shapely(blob).coords)
        fr = (
            _segment_cell_fractions(coords[0], coords[-1], bounds, grid_def)
            if len(coords) == 2
            else _linestring_cell_fractions(coords, bounds, grid_def)
        )
        for cell, f in fr.items():
            want[cell] = want.get(cell, 0.0) + res["tx_em_kg"]["nox"] * share * f
    grid = distribute_to_grid({2: _tx_only(res)}, conn, bounds, grid_def)
    got = grid[grid.pollutant == "nox"].groupby(["ix", "iy"])["kg"].sum().to_dict()
    assert set(got) == set(want)
    for cell, kg in want.items():
        assert got[cell] == pytest.approx(kg, rel=1e-9, abs=1e-15)


def _mov(**kw):
    m = dict(taxi_engine_count=1, taxi_fuel_ratio=0.5)
    m.update(kw)
    return m


SEGS = [(500.0, 18.0), (1000.0, 36.0), (500.0, 18.0)]  # 100 s each


def test_no_main_engine_time_ignores_ratio():
    out = _taxi_engine_split(_mov(), True, 2, SEGS, 300.0, 50.0, 350.0)
    assert out["natural_engine_s"] == pytest.approx(600.0)
    assert out["queue_engine_s"] == pytest.approx(100.0)
    assert out["last_engines"] == 2
    assert out["segment_weights"] is None


def test_departure_after_block_off():
    # segments end at 100, 200, 300 s; main engine start at 200 s; queue 50 s
    out = _taxi_engine_split(
        _mov(set_time_of_main_engine_start_after_block_off_in_s=200.0),
        True,
        2,
        SEGS,
        300.0,
        50.0,
        350.0,
    )
    assert out["natural_engine_s"] == pytest.approx(100 * 0.5 * 2 + 100 * 2)
    assert out["queue_engine_s"] == pytest.approx(50 * 2)
    assert out["last_engines"] == 2


def test_departure_before_takeoff_splits_queue():
    # main engine start 20 s before take-off of a 350 s taxi: at 330 s, so the
    # whole route and 30 s of the 50 s queue are single-engine
    out = _taxi_engine_split(
        _mov(set_time_of_main_engine_start_before_takeoff_in_s=20.0),
        True,
        2,
        SEGS,
        300.0,
        50.0,
        350.0,
    )
    assert out["natural_engine_s"] == pytest.approx(300 * 0.5)
    assert out["queue_engine_s"] == pytest.approx(30 * 0.5 + 20 * 2)
    assert out["last_engines"] == 1


def test_arrival_off_after_exit():
    # main engines off 150 s after the runway exit: the segments ending at 200
    # and 300 s are single-engine; the queue runs on the last segment's engines
    out = _taxi_engine_split(
        _mov(set_time_of_main_engine_off_after_runway_exit_in_s=150.0),
        False,
        2,
        SEGS,
        300.0,
        50.0,
        350.0,
    )
    assert out["natural_engine_s"] == pytest.approx(100 * 2 + 2 * 100 * 0.5)
    assert out["queue_engine_s"] == pytest.approx(50 * 1)
    assert out["last_engines"] == 1


def test_compressed_route_uses_average_speed():
    # 150 s of taxi on a 300 s route: segments of 37.5, 75, 37.5 s
    out = _taxi_engine_split(
        _mov(set_time_of_main_engine_start_after_block_off_in_s=40.0),
        True,
        2,
        SEGS,
        150.0,
        0.0,
        150.0,
    )
    assert out["natural_engine_s"] == pytest.approx(37.5 * 0.5 + 112.5 * 2)
