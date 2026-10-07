"""Natural taxi emission is split over the route's segments as the plugin does.

In the plugin's taxi loop (MovementEmissionCalculator), a segment's time is
its length divided by its own speed when the movement's taxi time exceeds the
route's time (the excess is queuing); otherwise every segment is driven at the
route's average speed. The natural taxi emission of a segment is therefore
proportional to length / speed in the first case and to length in the second.
distribute_to_grid used the length share in both cases, which moved mass from
slow apron segments to fast taxiway segments (EHRD, 5 August 2025: 0.91 kg
NOx moved between cells; totals unchanged).

Fixture: ``training_v3.alaqs`` (taxiways at 15 and 30 km/h; movements with
queuing).
"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import geometry as _geo
from openalaqs_standalone import movements as _mv
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


def _expected(conn, res, bounds, grid_def, by_time):
    route = _mv.get_movement(conn, res["oid"])["taxi_route"]
    seq = conn.execute(
        "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name=?", (route,)
    ).fetchone()[0]
    segs = []
    for tid in [t.strip() for t in seq.split(",") if t.strip()]:
        blob, speed = conn.execute(
            "SELECT geometry, speed FROM shapes_taxiways WHERE taxiway_id=?", (tid,)
        ).fetchone()
        g = _geo.spatialite_blob_to_shapely(blob)
        coords = list(g.coords)
        fr = (
            _segment_cell_fractions(coords[0], coords[-1], bounds, grid_def)
            if len(coords) == 2
            else _linestring_cell_fractions(coords, bounds, grid_def)
        )
        w = g.length / float(speed) if by_time else g.length
        segs.append((w, fr))
    tot = sum(w for w, _ in segs)
    out = {}
    for w, fr in segs:
        for cell, f in fr.items():
            out[cell] = out.get(cell, 0.0) + res["tx_em_kg"]["nox"] * w / tot * f
    return out


def test_taxi_split_by_segment_time_when_queuing():
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    conn = sqlite3.connect(SRC)
    results = compute_all_movements(conn, method="bymode", use_isa_meteo=False)
    ctx = build_context(conn)
    bounds, grid_def = ctx["grid_bounds"], _mv.get_grid_definition(conn)
    queued = [
        r for r in results.values() if r.get("queuing_time_s", 0) > 0 and r["segments"]
    ]
    assert queued, "fixture has no movement with queuing"
    res = queued[0]
    grid = distribute_to_grid({res["oid"]: _tx_only(res)}, conn, bounds, grid_def)
    got = grid[grid.pollutant == "nox"].groupby(["ix", "iy"])["kg"].sum().to_dict()
    want = _expected(conn, res, bounds, grid_def, by_time=True)
    by_length = _expected(conn, res, bounds, grid_def, by_time=False)
    assert set(got) == set(want)
    for cell, kg in want.items():
        assert got[cell] == pytest.approx(kg, rel=1e-9, abs=1e-15)
    # the two splits differ on this route (15 and 30 km/h segments)
    assert any(abs(want[c] - by_length.get(c, 0.0)) > 1e-9 for c in want)
