"""Regression: the standalone places a helicopter with a gate at that gate.

The standalone keeps no trajectory segments for helicopters and releases the
whole FOCA total as a point. On main the point was always the runway
threshold. The plugin now starts a helicopter with a gate (its helipad) at the
gate centroid, so the standalone places the point there too. Without a gate
the threshold is kept, and the totals never change.

Fixture: ``training_v3.alaqs`` (AS50 departure and arrival on runway 24, gates
G2, G4, G7).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import movements as _mv
from openalaqs_standalone.compute_movements import compute_all_movements
from openalaqs_standalone.distribute import cell_index, distribute_to_grid
from openalaqs_standalone.geometry import grid_bounds_3857, runway_threshold_3857

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"

GRID = {"x_cells": 100, "y_cells": 100, "x_resolution": 100, "y_resolution": 100}
REF = (51.96, 4.44)


def _run(tmp_path, name, gate_d, gate_a):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    db = tmp_path / name
    shutil.copy(SRC, db)
    conn = sqlite3.connect(db)
    # Flight paths below the vertical limit and inside the grid: these tests
    # are about placement (the cut is tested in test_helicopter_vertical_limit).
    conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = 1000")
    conn.execute("UPDATE grid_3d_definition SET x_cells = 200, y_cells = 200")
    conn.execute(
        "UPDATE user_aircraft_movements SET gate = ? "
        "WHERE aircraft = 'AS50' AND departure_arrival = 'D'",
        (gate_d,),
    )
    conn.execute(
        "UPDATE user_aircraft_movements SET gate = ? "
        "WHERE aircraft = 'AS50' AND departure_arrival = 'A'",
        (gate_a,),
    )
    conn.commit()
    grid_def = {
        **_mv.get_grid_definition(conn),
        **GRID,
        "reference_latitude": REF[0],
        "reference_longitude": REF[1],
    }
    bounds = grid_bounds_3857(100, 100, 100, 100, *REF)
    results = compute_all_movements(conn, method="bymode", use_isa_meteo=False)
    heli = {
        oid: res
        for oid, res in results.items()
        if _mv.get_movement(conn, oid)["aircraft"] == "AS50"
    }
    grid = distribute_to_grid(heli, conn, bounds, grid_def)
    return conn, bounds, grid_def, heli, grid


def _cells(grid, pollutant="nox"):
    g = grid[grid.pollutant == pollutant]
    return sorted({(int(r.ix), int(r.iy)) for r in g.itertuples()})


def test_helicopter_with_gate_is_placed_at_the_gate(tmp_path):
    conn, bounds, grid_def, heli, grid = _run(tmp_path, "gate.alaqs", "G2", "G4")
    expected = []
    for gate_id in ("G2", "G4"):
        c = _mv.get_gate(conn, gate_id)["geom_3857"].centroid
        expected.append(cell_index(c.x, c.y, bounds, grid_def))
    assert _cells(grid) == sorted(expected)


def test_helicopter_without_gate_stays_at_the_threshold(tmp_path):
    conn, bounds, grid_def, heli, grid = _run(tmp_path, "nogate.alaqs", "", "")
    runway = _mv.get_runways(conn)[24]
    pos = runway_threshold_3857(runway, 24)
    assert _cells(grid) == [cell_index(pos[0], pos[1], bounds, grid_def)]


def test_gate_does_not_change_helicopter_totals(tmp_path):
    _, _, _, heli_gate, grid_gate = _run(tmp_path, "a.alaqs", "G2", "G4")
    _, _, _, heli_none, grid_none = _run(tmp_path, "b.alaqs", "", "")
    for oid in heli_none:
        for p in ("nox", "co", "hc"):
            assert heli_gate[oid]["total_em_kg"][p] == pytest.approx(
                heli_none[oid]["total_em_kg"][p], rel=1e-12
            )
    for p in ("nox", "co", "hc"):
        assert grid_gate[grid_gate.pollutant == p].kg.sum() == pytest.approx(
            grid_none[grid_none.pollutant == p].kg.sum(), rel=1e-12
        )
