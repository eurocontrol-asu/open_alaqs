"""A taxi route without segments: the standalone does what the plugin does.

The plugin builds a route from the taxiways of its sequence that exist
(TaxiwayRoutesStore.initTaxiwayRoutes) and, when none exists,
TaxiingEmissionCalculator puts queuing, APU, engine start, stop-and-go and
brake wear on a stand-in segment of 0 m and 0 s at the gate (rc6 review M7,
tests/test_taxi_route_without_segments.py). The standalone treated such a
route as unresolved: its whole taxi time counted as natural taxiing (times
taxi_fuel_ratio) and the mass went to the runway intersection. Now the
natural time is the sum over the existing taxiways, 0 s when none exists,
so the whole taxi time is queuing (no fuel ratio), and distribute_to_grid
puts the stand phases over the gate polygon (rc7 review R4). A route with
some missing taxiways counts the existing ones, as the plugin does.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import geometry as _geo
from openalaqs_standalone import movements as _mv
from openalaqs_standalone.compute_movements import (
    _build_natural_taxi_times,
    build_context,
    compute_for_movement,
)
from openalaqs_standalone.distribute import _polygon_cell_fractions, distribute_to_grid

SRC = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"
OID = 1  # A20N arrival (brake wear applies), route G4/24/A/1


def _route_of(conn, oid):
    return conn.execute(
        "SELECT taxi_route FROM user_aircraft_movements WHERE oid = ?", (oid,)
    ).fetchone()[0]


@pytest.fixture
def studies(tmp_path):
    """(intact copy, copy whose route names only unknown taxiways, copy whose
    route keeps its first taxiway) with 2 stop-and-gos and APU on for OID."""
    paths = {}
    for name in ("intact", "empty", "partial"):
        db = tmp_path / f"{name}.alaqs"
        shutil.copy(SRC, db)
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE user_aircraft_movements SET number_of_stop_and_gos = 2, "
                "apu_code = 1, taxi_fuel_ratio = 0.5 WHERE oid = ?",
                (OID,),
            )
            route = _route_of(conn, OID)
            seq = conn.execute(
                "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name = ?",
                (route,),
            ).fetchone()[0]
            first = [s.strip() for s in seq.split(",") if s.strip()][0]
            if name == "empty":
                conn.execute(
                    "UPDATE user_taxiroute_taxiways SET sequence = 'NOPE1,NOPE2' "
                    "WHERE route_name = ?",
                    (route,),
                )
            elif name == "partial":
                conn.execute(
                    "UPDATE user_taxiroute_taxiways SET sequence = ? "
                    "WHERE route_name = ?",
                    (f"{first},NOPE1", route),
                )
        paths[name] = db
    return paths


def _result(db, method="bymode"):
    conn = sqlite3.connect(db)
    try:
        ctx = build_context(conn)
        return compute_for_movement(conn, OID, ctx, method=method, use_isa_meteo=False)
    finally:
        conn.close()


def test_route_without_segments_has_no_route_time(studies, caplog):
    with sqlite3.connect(studies["empty"]) as conn:
        route = _route_of(conn, OID)
        with caplog.at_level(logging.WARNING):
            natural = _build_natural_taxi_times(conn)
    assert natural[route] == 0.0
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("NOPE1, NOPE2" in w and "all queuing at the gate" in w for w in warnings)


def test_route_without_segments_keeps_the_stand_emissions(studies):
    intact, empty = _result(studies["intact"]), _result(studies["empty"])
    assert intact["queuing_time_s"] > 0
    # the whole taxi time (block to runway time less the landing roll, which
    # the arrival profile counts) is queuing, none is natural taxiing; with
    # the route, part of it is the runway stretch after the rollout, which an
    # unplaced route does not have
    assert empty["natural_taxi_time_s"] == 0.0
    assert empty["queuing_time_s"] == pytest.approx(empty["taxi_time_s"])
    assert empty["taxi_time_s"] == pytest.approx(intact["taxi_time_s"])
    assert all(v == 0.0 for v in empty["tx_em_kg"].values())
    # queuing (no fuel ratio), stop-and-go, APU, start and brake wear remain
    for key in ("queue_em_kg", "stop_em_kg", "apu_em_kg", "brake_wear_em_kg"):
        assert empty[key]["nox" if key != "brake_wear_em_kg" else "pm10"] > 0.0, key
    for key in ("stop_em_kg", "apu_em_kg", "start_em_kg", "brake_wear_em_kg"):
        assert empty[key] == intact[key], key
    # queuing burns at all engines with no taxi fuel ratio (as in the plugin):
    # queue + stop-and-go NOx scale with their times at the same rate
    per_s = empty["stop_em_kg"]["nox"] / (9.0 * 2)
    assert empty["queue_em_kg"]["nox"] == pytest.approx(
        per_s * empty["queuing_time_s"], rel=1e-9
    )


def test_partial_route_counts_the_existing_taxiways(studies):
    with sqlite3.connect(studies["partial"]) as conn:
        route = _route_of(conn, OID)
        natural = _build_natural_taxi_times(conn)
        first = (
            conn.execute(
                "SELECT sequence FROM user_taxiroute_taxiways WHERE route_name = ?",
                (route,),
            )
            .fetchone()[0]
            .split(",")[0]
        )
        with sqlite3.connect(studies["intact"]) as intact_conn:
            full = _build_natural_taxi_times(intact_conn)[route]
    assert 0.0 < natural[route] < full
    res = _result(studies["partial"])
    assert res["natural_taxi_time_s"] == pytest.approx(natural[route])
    assert first  # the existing one


def test_stand_emissions_go_to_the_gate_cells(studies):
    conn = sqlite3.connect(studies["empty"])
    try:
        ctx = build_context(conn)
        res = compute_for_movement(conn, OID, ctx, method="bymode", use_isa_meteo=False)
        bounds, grid_def = ctx["grid_bounds"], _mv.get_grid_definition(conn)
        gate = conn.execute(
            "SELECT geometry FROM shapes_gates WHERE gate_id = "
            "(SELECT gate FROM user_aircraft_movements WHERE oid = ?)",
            (OID,),
        ).fetchone()[0]
        gate_cells = _polygon_cell_fractions(
            _geo.spatialite_blob_to_shapely(gate), bounds, grid_def
        )
        grid = distribute_to_grid({OID: res}, conn, bounds, grid_def)
    finally:
        conn.close()
    # everything but the flight segments (the arrival's runway stretch and the
    # profile) is at the gate: the queuing NOx lands only in gate cells
    stand_nox = (
        res["queue_em_kg"]["nox"] + res["stop_em_kg"]["nox"] + res["apu_em_kg"]["nox"]
    )
    by_cell = grid[grid.pollutant == "nox"].groupby(["ix", "iy"])["kg"].sum()
    in_gate = sum(by_cell.get(cell, 0.0) for cell in gate_cells)
    assert in_gate >= stand_nox * (1 - 1e-9)
    # mass conserved
    assert by_cell.sum() == pytest.approx(res["total_em_kg"]["nox"], rel=1e-9)
