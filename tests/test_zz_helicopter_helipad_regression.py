"""Regression: helicopter movements at a helipad gate.

Three defects on main (2e273d9) are covered:

1. A helicopter movement with a gate could not be computed. ``initMovements``
   rebuilds an empty taxi route as ``gate/runway/D|A/1``; when that route
   exists the movement reaches the fixed-wing ``TaxiingEmissionCalculator``,
   which fails with ``AttributeError: 'Helicopter' object has no attribute
   'getStartEmissions'``.
2. The FOCA half-LTO always started at the runway end, whatever the gate.
3. Ground idle (4 min of the departure, 1 min of the arrival) had no geometry
   of its own: the whole FOCA total was spread over the flight path by length,
   so most of the helicopter CO and HC ended up kilometres away and aloft.

Expected now: a helicopter with a gate starts / ends its trajectory at the
gate centroid, ground idle is a point emission at that spot, no taxi, gate or
APU emission is added, and the per-movement totals are those of the same
movement without a gate (FOCA totals do not depend on the geometry). Without a
gate the trajectory still starts at the runway end.

Fixture: ``training_v3.alaqs`` (two AS50 movements on runway 24, gates G2, G4,
G7 with taxi routes ``G*/24/D|A/1``).
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
    "x_cells": 100,
    "y_cells": 100,
    "z_cells": 1,
    "x_resolution": 100,
    "y_resolution": 100,
    "z_resolution": 100,
    "reference_latitude": 51.96,
    "reference_longitude": 4.44,
    "reference_altitude": 0.0,
}

# FOCA totals of the two AS50 movements on main, without a gate (kg).
MAIN_TOTALS = {
    "D": {"nox": 0.084562594, "co": 0.203242811, "hc": 0.158861834},
    "A": {"nox": 0.065300215, "co": 0.137020817, "hc": 0.108792975},
}

POLLUTANTS = ("nox", "co", "hc", "fuel")


@pytest.fixture(autouse=True)
def _isolate_singletons():
    """Same isolation as test_zz_bymode_analytical_regression: the stores are
    singletons keyed to the first database path they see."""
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


def _prepare(tmp_path, name, gate_d, gate_a, extra_departure_gate=None):
    """Copy the fixture and set the AS50 gates. Optionally add a second AS50
    departure, 15 min later (same hourly period), at another gate."""
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    dst = tmp_path / name
    shutil.copy(SRC, dst)
    with sqlite3.connect(dst) as conn:
        # Keep every helicopter flight path below the vertical limit and
        # inside the grid, so these tests see the placement only (the cut by
        # mixing height and grid is tested in test_zz_helicopter_vertical_limit).
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = 1000")
        conn.execute("UPDATE grid_3d_definition SET x_cells = 200, y_cells = 200")
        conn.execute(
            "UPDATE user_aircraft_movements SET gate = ?, gate_emissions_code = 1,"
            " apu_code = 1 WHERE aircraft = 'AS50' AND departure_arrival = 'D'",
            (gate_d,),
        )
        conn.execute(
            "UPDATE user_aircraft_movements SET gate = ?, gate_emissions_code = 1,"
            " apu_code = 1 WHERE aircraft = 'AS50' AND departure_arrival = 'A'",
            (gate_a,),
        )
        if extra_departure_gate is not None:
            cols = [
                r[1] for r in conn.execute("PRAGMA table_info(user_aircraft_movements)")
            ]
            row = dict(
                zip(
                    cols,
                    conn.execute(
                        "SELECT * FROM user_aircraft_movements "
                        "WHERE aircraft = 'AS50' AND departure_arrival = 'D'"
                    ).fetchone(),
                )
            )
            row["oid"] = conn.execute(
                "SELECT MAX(oid) + 1 FROM user_aircraft_movements"
            ).fetchone()[0]
            row["gate"] = extra_departure_gate
            row["runway_time"] = "2025-12-01 06:50:00"
            row["block_time"] = "2025-12-01 06:45:00"
            conn.execute(
                "INSERT INTO user_aircraft_movements (%s) VALUES (%s)"
                % (",".join(cols), ",".join("?" * len(cols))),
                [row[c] for c in cols],
            )
        conn.commit()
    return str(dst)


def _run(db_path, source_dynamics="none"):
    """Run the movement calculation; return {movement name: [(wkt, {pollutant: kg})]}
    for the AS50 movements, one entry per non-zero emission."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    ProjectDatabase().path = db_path
    cfg = EmissionCalculationConfig(
        db_path=db_path,
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="bymode",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 9),
        time_interval=timedelta(seconds=3600),
        source_dynamics=source_dynamics,
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    out = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            name = str(source.getName())
            if " AS50 " not in name:
                continue
            for e in emissions:
                k = e.transposeToKilograms()
                vals = {p: k.getObject(f"{p}_kg") or 0.0 for p in POLLUTANTS}
                if any(vals.values()):
                    out.setdefault(name, []).append((k.getGeometryText(), vals))
    return out


def _totals(emissions):
    return {p: sum(v[p] for _, v in emissions) for p in POLLUTANTS}


def _direction(name):
    return " D " if " D " in name else " A "


def _by_direction(run, direction):
    hits = [v for k, v in run.items() if f"AS50{direction}" in k]
    assert len(hits) == 1, f"expected one AS50{direction}movement in {list(run)}"
    return hits[0]


def _geometry(db_path, sql, args=()):
    """Read one SpatiaLite geometry with the pure-Python BLOB reader of the
    standalone (no SpatiaLite SQL functions needed: some plugin tests replace
    qgis.utils.spatialite_connect)."""
    from openalaqs_standalone.geometry import spatialite_blob_to_shapely

    with sqlite3.connect(db_path) as conn:
        (blob,) = conn.execute(sql, args).fetchone()
    return spatialite_blob_to_shapely(blob)


def _gate_centroid(db_path, gate):
    c = _geometry(
        db_path, "SELECT geometry FROM shapes_gates WHERE gate_id = ?", (gate,)
    ).centroid
    return c.x, c.y


def _runway_end_for_departure(db_path, heading_deg):
    """Runway end a departure with this heading starts from (EPSG:3857)."""
    coords = list(_geometry(db_path, "SELECT geometry FROM shapes_runways").coords)
    (x1, y1), (x2, y2) = coords[0][:2], coords[-1][:2]
    bearing_12 = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 360
    diff = min(abs(bearing_12 - heading_deg), 360 - abs(bearing_12 - heading_deg))
    return (x1, y1) if diff < 90 else (x2, y2)


def _point_xy(wkt):
    from shapely import wkt as _wkt

    g = _wkt.loads(wkt)
    return g.geom_type, g


def _expected_ground_idle_kg(db_path, departure):
    """FOCA ground-idle NOx/CO/HC of the AS50, computed with the FOCA helpers."""
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
    category = derive_category(eng_type, int(n_eng), float(mtow))
    profile = PROFILES[category]
    fraction = GI_DEPARTURE_FRACTION if departure else GI_ARRIVAL_FRACTION
    gi = _mode_result(
        "GI",
        profile.gi_power,
        profile.gi_time_min * fraction,
        compute_mode_emissions(category, float(shp), profile.gi_power),
        int(n_eng),
    )
    return {"nox": gi.nox_g / 1000.0, "co": gi.co_g / 1000.0, "hc": gi.hc_g / 1000.0}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("helipad")
    results = {}
    for key, args in {
        "no_gate": ("", ""),
        "gate": ("G2", "G4"),
        "two_gates": ("G2", "G4", "G7"),
    }.items():
        _reset_singletons()
        db = _prepare(tmp, f"{key}.alaqs", *args)
        results[key] = (db, _run(db))
    _reset_singletons()
    db = _prepare(tmp, "gate_sas.alaqs", "G2", "G4")
    results["gate_sas"] = (db, _run(db, source_dynamics="smooth & shift"))
    _reset_singletons()
    return results


def test_helicopter_with_gate_is_computed_with_unchanged_totals(runs):
    """Defect 1, plus no taxi/gate/APU emission for a helicopter at a gate
    (gate_emissions_code and apu_code are set to 1 on purpose)."""
    _, no_gate = runs["no_gate"]
    _, gate = runs["gate"]
    for d, key in ((" D ", "D"), (" A ", "A")):
        t_no_gate = _totals(_by_direction(no_gate, d))
        t_gate = _totals(_by_direction(gate, d))
        for p in POLLUTANTS:
            assert t_gate[p] == pytest.approx(t_no_gate[p], rel=1e-12), (d, p)
        for p, v in MAIN_TOTALS[key].items():
            assert t_no_gate[p] == pytest.approx(v, rel=1e-6), (d, p)


def test_ground_idle_is_a_point_at_the_gate(runs):
    """Defects 2 and 3 for a helicopter with a gate."""
    db, gate = runs["gate"]
    for d, gate_id in ((" D ", "G2"), (" A ", "G4")):
        cx, cy = _gate_centroid(db, gate_id)
        emissions = _by_direction(gate, d)
        points = [(w, v) for w, v in emissions if _point_xy(w)[0] == "Point"]
        lines = [(w, v) for w, v in emissions if _point_xy(w)[0] == "MultiLineString"]
        assert len(points) == 1 and len(lines) == 1, [w[:40] for w, _ in emissions]
        p = _point_xy(points[0][0])[1]
        assert p.x == pytest.approx(cx, abs=0.01) and p.y == pytest.approx(cy, abs=0.01)
        expected = _expected_ground_idle_kg(db, departure=d == " D ")
        for pol, v in expected.items():
            assert points[0][1][pol] == pytest.approx(v, rel=1e-9), (d, pol)
        # The flight path starts (departure) or ends (arrival) at the gate.
        line = _point_xy(lines[0][0])[1]
        coords = (
            list(line.geoms[0].coords) if d == " D " else list(line.geoms[-1].coords)
        )
        x, y = coords[0][:2] if d == " D " else coords[-1][:2]
        assert x == pytest.approx(cx, abs=0.01) and y == pytest.approx(cy, abs=0.01)


def test_without_gate_ground_idle_stays_at_the_runway_end(runs):
    db, no_gate = runs["no_gate"]
    rx, ry = _runway_end_for_departure(db, 240.0)
    emissions = _by_direction(no_gate, " D ")
    points = [w for w, _ in emissions if _point_xy(w)[0] == "Point"]
    assert len(points) == 1
    p = _point_xy(points[0])[1]
    assert p.x == pytest.approx(rx, abs=0.01) and p.y == pytest.approx(ry, abs=0.01)


def test_helicopters_at_different_gates_get_their_own_trajectory(runs):
    """Two AS50 departures at G2 and G7: both share runway, profile and engine,
    so without the gate in the grouping keys the second one would reuse the
    first one's trajectory."""
    db, two = runs["two_gates"]
    departures = {k: v for k, v in two.items() if " D " in k}
    assert len(departures) == 2, list(two)
    for name, emissions in departures.items():
        gate_id = "G7" if " G7 " in name else "G2"
        cx, cy = _gate_centroid(db, gate_id)
        points = [w for w, _ in emissions if _point_xy(w)[0] == "Point"]
        assert len(points) == 1
        p = _point_xy(points[0])[1]
        assert p.x == pytest.approx(cx, abs=0.01), (name, gate_id)
        assert p.y == pytest.approx(cy, abs=0.01), (name, gate_id)


def test_ground_idle_point_survives_smooth_and_shift(runs):
    """SmoothAndShiftTransformer widened every emission as a line; a point
    has no vertices to widen and must be kept as it is."""
    db, gate_sas = runs["gate_sas"]
    _, gate = runs["gate"]
    for d in (" D ", " A "):
        emissions = _by_direction(gate_sas, d)
        points = [(w, v) for w, v in emissions if _point_xy(w)[0] == "Point"]
        assert len(points) == 1
        t_sas = _totals(emissions)
        t_plain = _totals(_by_direction(gate, d))
        for p in POLLUTANTS:
            assert t_sas[p] == pytest.approx(t_plain[p], rel=1e-12), (d, p)
