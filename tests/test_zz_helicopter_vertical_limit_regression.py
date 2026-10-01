"""Regression: helicopter flight paths follow the vertical limit and the grid,
and arrivals approach from the correct side.

On 5.3.1 the FOCA climb (departure) and approach (arrival) were counted whole,
whatever the period's vertical limit (mixing height) and the grid, while
fixed-wing flight segments are cut at both. Now only the part of the flight
path below the limit and inside the grid is kept, and the FOCA active-mode
mass is scaled by the share of the mode's time spent on that part. Ground idle
is not affected. A point exactly at the limit is kept, so the FOCA level
flight at the LTO ceiling (914.4 m) is unchanged under the default 914.4 m
limit.

Also covered: the arrival flight path was laid out in the landing direction
from the touchdown point, so a runway-24 arrival came in from the south-west
(flying 060). It now comes in along the approach, from the north-east.

Fixture: ``training_v3.alaqs`` (AS50 departure and arrival on runway 24).
"""

import datetime
import math
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.EmissionCalculatorService import (  # noqa: E402
    EmissionCalculationConfig,
    EmissionCalculatorService,
)

SRC = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)

GRID_CONFIG = {
    "x_cells": 50,
    "y_cells": 50,
    "z_cells": 1,
    "x_resolution": 250,
    "y_resolution": 250,
    "z_resolution": 50,
    "reference_latitude": 51.9574278,
    "reference_longitude": 4.4417028,
    "reference_altitude": 0.0,
}


@pytest.fixture(autouse=True)
def _isolate_singletons():
    """Same isolation as test_zz_bymode_analytical_regression."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton

    saved_path = getattr(ProjectDatabase(), "path", None)
    saved_instances = dict(Singleton._instances)
    _reset_singletons()
    try:
        yield
    finally:
        _reset_singletons()
        Singleton._instances.update(saved_instances)
        if saved_path is not None:
            ProjectDatabase().path = saved_path


def _reset_singletons():
    from open_alaqs.core.alaqsdblite import Singleton

    Singleton._instances.clear()
    import open_alaqs.core.interfaces.Movement as _mov_mod

    if hasattr(_mov_mod, "_mem_traj_cache"):
        _mov_mod._mem_traj_cache.clear()


def _prepare(tmp_path, name, mixing_height, cells=200, gate_d="", gate_a=""):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    dst = tmp_path / name
    shutil.copy(SRC, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (mixing_height,))
        conn.execute(
            "UPDATE grid_3d_definition SET x_cells = ?, y_cells = ?", (cells, cells)
        )
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
    return str(dst)


def _run(db_path):
    """{movement oid: [(wkt, nox_kg)]} for the AS50 movements."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    _reset_singletons()
    ProjectDatabase().path = db_path
    cfg = EmissionCalculationConfig(
        db_path=db_path,
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="bymode",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 0),
        end_dt_inclusive=datetime.datetime(2025, 12, 2, 0),
        time_interval=timedelta(seconds=3600),
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    out = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            name = str(source.getName())
            if " AS50 " not in name:
                continue
            oid = int(name.split(":")[0][3:])
            for e in emissions:
                k = e.transposeToKilograms()
                nox = k.getObject("nox_kg") or 0.0
                if nox:
                    out.setdefault(oid, []).append((k.getGeometryText(), nox))
    return out


def _oid(db_path, direction):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT oid FROM user_aircraft_movements "
            "WHERE aircraft = 'AS50' AND departure_arrival = ?",
            (direction,),
        ).fetchone()[0]


def _foca(db_path, departure):
    """(category, ground-idle NOx kg, active-mode NOx kg) of the AS50."""
    from open_alaqs.core.tools.foca_heli import (
        GI_ARRIVAL_FRACTION,
        GI_DEPARTURE_FRACTION,
        PROFILES,
        derive_category,
    )
    from open_alaqs.core.tools.foca_heli_utils import (
        _mode_result,
        compute_mode_emissions,
    )

    with sqlite3.connect(db_path) as conn:
        mtow, n_eng, eng, shp = conn.execute(
            "SELECT mtow_kg, engine_count, engine_name, max_shp_per_engine "
            "FROM default_helicopter WHERE icao = 'AS50' OR variant_label = 'AS50' "
            "ORDER BY is_default DESC LIMIT 1"
        ).fetchone()
        (eng_type,) = conn.execute(
            "SELECT engine_type FROM default_helicopter_engines WHERE engine_name = ?",
            (eng,),
        ).fetchone()
    cat = derive_category(eng_type, int(n_eng), float(mtow))
    prof = PROFILES[cat]
    frac = GI_DEPARTURE_FRACTION if departure else GI_ARRIVAL_FRACTION
    gi = _mode_result(
        "GI",
        prof.gi_power,
        prof.gi_time_min * frac,
        compute_mode_emissions(cat, float(shp), prof.gi_power),
        int(n_eng),
    )
    power, minutes = (
        (prof.to_power, prof.to_time_min)
        if departure
        else (prof.ap_power, prof.ap_time_min)
    )
    act = _mode_result(
        "TO" if departure else "AP",
        power,
        minutes,
        compute_mode_emissions(cat, float(shp), power),
        int(n_eng),
    )
    return cat, gi.nox_g / 1000.0, act.nox_g / 1000.0


def _time_share_below(cat, departure, height):
    """Analytic share of the active-mode time below `height`: altitude is
    linear in time within each builder segment."""
    from open_alaqs.core.tools.foca_heli_trajectory import (
        build_arrival,
        build_departure,
    )

    pts = build_departure(cat) if departure else build_arrival(cat)
    total = below = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        dt = b.t_s - a.t_s
        if dt <= 0 or a.x_m == b.x_m:
            continue
        total += dt
        lo, hi = sorted((a.z_m, b.z_m))
        if hi <= height:
            below += dt
        elif lo < height:
            below += dt * (height - lo) / (hi - lo)
    return below / total


def _standalone_nox(db_path):
    from openalaqs_standalone import movements as _mv
    from openalaqs_standalone.compute_movements import compute_all_movements

    with sqlite3.connect(db_path) as conn:
        res = compute_all_movements(conn, method="bymode", use_isa_meteo=False)
        return {
            oid: r["total_em_kg"]["nox"]
            for oid, r in res.items()
            if _mv.get_movement(conn, oid)["aircraft"] == "AS50"
        }


@pytest.mark.parametrize("height", [100.0, 400.0])
def test_active_mode_is_cut_at_the_mixing_height(tmp_path, height):
    db = _prepare(tmp_path, f"mh{int(height)}.alaqs", height)
    run = _run(db)
    for departure, direction in ((True, "D"), (False, "A")):
        cat, gi, act = _foca(db, departure)
        share = _time_share_below(cat, departure, height)
        assert 0.0 < share < 1.0
        total = sum(v for _, v in run[_oid(db, direction)])
        assert total == pytest.approx(gi + share * act, rel=1e-9), direction
        points = [
            v for w, v in run[_oid(db, direction)] if w.upper().startswith("POINT")
        ]
        assert points == [pytest.approx(gi, rel=1e-9)], "ground idle must stay whole"


def test_no_cut_when_the_path_is_below_the_limit_and_inside_the_grid(tmp_path):
    """Default 914.4 m limit (the FOCA LTO ceiling) and a 50 km grid: the FOCA
    totals are those of 5.3.1, the level flight at 914.4 m included."""
    db = _prepare(tmp_path, "full.alaqs", 914.4)
    run = _run(db)
    for departure, direction in ((True, "D"), (False, "A")):
        _, gi, act = _foca(db, departure)
        total = sum(v for _, v in run[_oid(db, direction)])
        assert total == pytest.approx(gi + act, rel=1e-9), direction


def test_flight_path_is_cut_at_the_grid_edge(tmp_path):
    """A 7.5 km grid: the kept flight path lies inside the grid bounds and its
    mass is smaller than on the 50 km grid."""
    from open_alaqs.core.tools.Grid3D import Grid3D

    small = _prepare(tmp_path, "small.alaqs", 1000.0, cells=30)
    large = _prepare(tmp_path, "large.alaqs", 1000.0, cells=200)
    run_small, run_large = _run(small), _run(large)
    gb = Grid3D(small, {}, deserialize=True).getGridBounds()
    from shapely import wkt as _wkt

    cut = 0
    for oid, emissions in run_small.items():
        for w, _ in emissions:
            g = _wkt.loads(w)
            if g.geom_type == "MultiLineString":
                x0, y0, x1, y1 = g.bounds
                assert x0 >= gb["x_min"] - 1e-6 and x1 <= gb["x_max"] + 1e-6
                assert y0 >= gb["y_min"] - 1e-6 and y1 <= gb["y_max"] + 1e-6
        s = sum(v for _, v in emissions)
        l_ = sum(v for _, v in run_large[oid])
        assert s <= l_ * (1 + 1e-12)
        cut += s < l_ * (1 - 1e-6)
    assert cut >= 1, "test premise: the small grid must cut at least one path"


def test_arrival_comes_in_along_the_approach(tmp_path):
    """Runway 24 (landing heading about 240): the arrival path must start on
    the north-east side of the touchdown point and end there."""
    db = _prepare(tmp_path, "side.alaqs", 1000.0)
    run = _run(db)
    from shapely import wkt as _wkt

    (line,) = [
        _wkt.loads(w)
        for w, _ in run[_oid(db, "A")]
        if w.upper().startswith("MULTILINESTRING")
    ]
    start = line.geoms[0].coords[0]
    end = line.geoms[-1].coords[-1]
    bearing = math.degrees(math.atan2(start[0] - end[0], start[1] - end[1])) % 360
    assert abs(bearing - 60.0) < 15.0, bearing
    assert start[2] > end[2]


@pytest.mark.parametrize(
    "height, cells, gate_d, gate_a",
    [(100.0, 200, "", ""), (400.0, 30, "G2", "G4"), (914.4, 50, "", "")],
)
def test_plugin_equals_standalone(tmp_path, height, cells, gate_d, gate_a):
    db = _prepare(tmp_path, "p.alaqs", height, cells, gate_d, gate_a)
    run = _run(db)
    sa = _standalone_nox(db)
    for oid, emissions in run.items():
        assert sum(v for _, v in emissions) == pytest.approx(sa[oid], rel=1e-9), oid
