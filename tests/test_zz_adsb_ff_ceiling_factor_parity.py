"""BFFM2 trajectory: a supplied fuel flow up to ADSB_FF_CEILING_FACTOR x the ICAO take-off
fuel flow is used as given, in the plugin and the standalone alike; above it, both fall
back to the mode anchor.

The ICAO take-off fuel flow is a static, sea-level value; in flight, a high-thrust
climb point can exceed it by a few percent, so the plausibility limit is a multiple of
it rather than the value itself.
"""

import datetime
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
from openalaqs_standalone.compute_movements import compute_all_movements  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)
PROFILE = "JET-SMALL-D-1"


@pytest.fixture(autouse=True)
def _isolate_singletons():
    from open_alaqs.core.alaqsdblite import ProjectDatabase, Singleton

    saved_path = getattr(ProjectDatabase(), "path", None)
    saved_instances = dict(Singleton._instances)
    Singleton._instances.clear()
    try:
        yield
    finally:
        Singleton._instances.clear()
        Singleton._instances.update(saved_instances)
        if saved_path is not None:
            ProjectDatabase().path = saved_path
        try:
            import open_alaqs.core.interfaces.Movement as _mov_mod

            if hasattr(_mov_mod, "_mem_traj_cache"):
                _mov_mod._mem_traj_cache.clear()
        except Exception:
            pass


def _plugin_nox(db, ff_source):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    with sqlite3.connect(db) as conn:
        g = conn.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, z_resolution, "
            "reference_latitude, reference_longitude FROM grid_3d_definition"
        ).fetchone()
    grid = dict(
        zip(
            [
                "x_cells",
                "y_cells",
                "z_cells",
                "x_resolution",
                "y_resolution",
                "z_resolution",
                "reference_latitude",
                "reference_longitude",
            ],
            g,
        ),
        reference_altitude=0.0,
    )
    ProjectDatabase().path = db
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="movements",
            grid_config=grid,
            method="BFFM2",
            bffm2_ff_source=ff_source,
            start_dt_inclusive=datetime.datetime(2025, 12, 1, 0),
            end_dt_inclusive=datetime.datetime(2025, 12, 4, 0),
            time_interval=timedelta(seconds=3600),
        )
    )
    assert result.success, result.error_message
    totals = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            name = str(source.getName())
            if name.startswith("id "):
                oid = int(name.split(":")[0][3:])
                totals[oid] = totals.get(oid, 0.0) + sum(
                    e.transposeToKilograms().getObject("nox_kg") or 0.0
                    for e in emissions
                )
    return totals


def _study(tmp_path, ratio):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    dst = tmp_path / f"training_{ratio}.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        engines = conn.execute(
            "SELECT DISTINCT m.engine_name FROM user_aircraft_movements m "
            "WHERE m.profile_id = ?",
            (PROFILE,),
        ).fetchall()
        engine = engines[0][0]
        oids = [
            r[0]
            for r in conn.execute(
                "SELECT oid FROM user_aircraft_movements WHERE profile_id = ? AND engine_name = ?",
                (PROFILE, engine),
            )
        ]
        n_eng = conn.execute(
            "SELECT a.engine_count FROM user_aircraft_movements m JOIN default_aircraft a "
            "ON a.icao = m.aircraft WHERE m.oid = ?",
            (oids[0],),
        ).fetchone()[0]
        to_ff = conn.execute(
            "SELECT fuel_kg_sec FROM default_aircraft_engine_ei WHERE engine_name = ? AND mode = 'TO'",
            (engine,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE default_aircraft_profiles SET fuel_flow_kgm = ? WHERE profile_id = ?",
            (ratio * float(n_eng) * float(to_ff), PROFILE),
        )
        conn.commit()
    return str(dst), oids


@pytest.mark.parametrize("ratio", [1.0, 1.3, 2.0])
def test_standalone_matches_plugin_around_the_ceiling(tmp_path, ratio):
    db, oids = _study(tmp_path, ratio)
    assert oids, "test premise: some movements must use the profile"
    plugin = _plugin_nox(db, "trajectory")
    with sqlite3.connect(db) as conn:
        sa = compute_all_movements(conn, method="bffm2_traj", use_isa_meteo=False)
    for oid in oids:
        assert sa[oid]["total_em_kg"]["nox"] == pytest.approx(
            plugin[oid], rel=1e-6
        ), f"oid {oid}"


def test_fuel_flow_between_take_off_and_ceiling_is_kept(tmp_path):
    """1.3 x take-off is kept (more NOx than 1.0 x); 2.0 x falls back to the anchor."""
    res = {}
    for ratio in (1.0, 1.3, 2.0):
        db, oids = _study(tmp_path, ratio)
        with sqlite3.connect(db) as conn:
            sa = compute_all_movements(conn, method="bffm2_traj", use_isa_meteo=False)
        res[ratio] = sum(sa[o]["total_em_kg"]["nox"] for o in oids)
    assert res[1.3] > res[1.0] * 1.2
    assert res[2.0] < res[1.0]
