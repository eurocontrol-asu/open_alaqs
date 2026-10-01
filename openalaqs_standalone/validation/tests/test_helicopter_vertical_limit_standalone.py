"""Regression: the standalone cuts the helicopter active mode at the mixing
height and the grid, as the plugin does.

FOCA gives one mass for the whole climb (departure) or approach (arrival).
With a study context, `compute_helicopter` keeps the share of that mode's
time spent below the movement's mixing height and inside the grid, on the
same flight path the plugin builds. Ground idle is never cut. Without a
context (the reference's call) nothing changes.

Fixture: ``training_v3.alaqs`` (AS50 departure and arrival on runway 24).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from open_alaqs.core.tools.foca_heli import (
    GI_ARRIVAL_FRACTION,
    GI_DEPARTURE_FRACTION,
    PROFILES,
    derive_category,
)
from open_alaqs.core.tools.foca_heli_trajectory import build_arrival, build_departure
from open_alaqs.core.tools.foca_heli_utils import _mode_result, compute_mode_emissions
from openalaqs_standalone import compute_helicopter as ch
from openalaqs_standalone import movements as mv
from openalaqs_standalone.compute_movements import build_context

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"


def _db(tmp_path, mixing_height, cells=200):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    db = tmp_path / f"mh{mixing_height}_{cells}.alaqs"
    shutil.copy(SRC, db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (mixing_height,))
    conn.execute(
        "UPDATE grid_3d_definition SET x_cells = ?, y_cells = ?", (cells, cells)
    )
    conn.commit()
    return conn


def _as50(conn, direction):
    oid = conn.execute(
        "SELECT oid FROM user_aircraft_movements "
        "WHERE aircraft = 'AS50' AND departure_arrival = ?",
        (direction,),
    ).fetchone()[0]
    return mv.get_movement(conn, oid)


def _foca(conn, departure):
    heli = mv.get_helicopter(conn, "AS50")
    eng_type = mv.get_helicopter_engine_type(conn, heli["engine_name"])
    n = int(heli["engine_count"])
    shp = float(heli["max_shp_per_engine"])
    cat = derive_category(eng_type, n, float(heli["mtow_kg"]))
    p = PROFILES[cat]
    frac = GI_DEPARTURE_FRACTION if departure else GI_ARRIVAL_FRACTION
    gi = _mode_result(
        "GI",
        p.gi_power,
        p.gi_time_min * frac,
        compute_mode_emissions(cat, shp, p.gi_power),
        n,
    )
    power, minutes = (
        (p.to_power, p.to_time_min) if departure else (p.ap_power, p.ap_time_min)
    )
    act = _mode_result("A", power, minutes, compute_mode_emissions(cat, shp, power), n)
    return cat, gi.nox_g / 1000.0, act.nox_g / 1000.0


def _share_below(cat, departure, height):
    pts = build_departure(cat) if departure else build_arrival(cat)
    total = below = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        dt = b.t_s - a.t_s
        if dt <= 0 or a.x_m == b.x_m:
            continue
        total += dt
        lo, hi = sorted((a.z_m, b.z_m))
        below += (
            dt
            if hi <= height
            else (dt * (height - lo) / (hi - lo) if lo < height else 0.0)
        )
    return below / total


@pytest.mark.parametrize("height", [100.0, 400.0])
def test_active_mode_cut_at_mixing_height(tmp_path, height):
    conn = _db(tmp_path, height)
    ctx = build_context(conn)
    for departure, d in ((True, "D"), (False, "A")):
        cat, gi, act = _foca(conn, departure)
        share = _share_below(cat, departure, height)
        res = ch.compute_helicopter(conn, _as50(conn, d), ctx)
        assert res["total_em_kg"]["nox"] == pytest.approx(gi + share * act, rel=1e-9)


def test_no_cut_below_limit_and_inside_grid(tmp_path):
    conn = _db(tmp_path, 914.4)
    ctx = build_context(conn)
    for departure, d in ((True, "D"), (False, "A")):
        _, gi, act = _foca(conn, departure)
        res = ch.compute_helicopter(conn, _as50(conn, d), ctx)
        assert res["total_em_kg"]["nox"] == pytest.approx(gi + act, rel=1e-9)


def test_without_context_nothing_is_cut(tmp_path):
    conn = _db(tmp_path, 100.0)
    for departure, d in ((True, "D"), (False, "A")):
        _, gi, act = _foca(conn, departure)
        res = ch.compute_helicopter(conn, _as50(conn, d))
        assert res["total_em_kg"]["nox"] == pytest.approx(gi + act, rel=1e-9)


def test_small_grid_cuts_the_path(tmp_path):
    small, large = _db(tmp_path, 1000.0, cells=30), _db(tmp_path, 1000.0, cells=200)
    cs, cl = build_context(small), build_context(large)
    totals = [
        (
            ch.compute_helicopter(small, _as50(small, d), cs)["total_em_kg"]["nox"],
            ch.compute_helicopter(large, _as50(large, d), cl)["total_em_kg"]["nox"],
        )
        for d in ("D", "A")
    ]
    assert all(s <= big * (1 + 1e-12) for s, big in totals)
    assert any(s < big * (1 - 1e-6) for s, big in totals)
