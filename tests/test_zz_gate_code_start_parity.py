"""Regression: gate_emissions_code 0 suppresses engine-start emissions in the
standalone, as in the plugin.

The plugin's ``_apply_start_engine_emissions`` returns early for a movement
whose gate_emissions_code is 0 (as its gate calculator does for GSE and GPU).
The standalone added the start emissions of every departure regardless, so
the two tools disagreed on departures with the code set to 0.

The test sets gate_emissions_code = 0 on every movement of the training
fixture and requires plugin and standalone to agree movement by movement.
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
POLLUTANTS = ("nox", "co", "hc")


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


@pytest.fixture
def study(tmp_path):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    dst = tmp_path / "training.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute("UPDATE user_aircraft_movements SET gate_emissions_code = 0")
        conn.commit()
    return str(dst)


def _plugin_totals(db):
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    with sqlite3.connect(db) as conn:
        g = conn.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, z_resolution, "
            "reference_latitude, reference_longitude FROM grid_3d_definition"
        ).fetchone()
    keys = (
        "x_cells",
        "y_cells",
        "z_cells",
        "x_resolution",
        "y_resolution",
        "z_resolution",
        "reference_latitude",
        "reference_longitude",
    )
    grid = dict(zip(keys, g), reference_altitude=0.0)
    ProjectDatabase().path = db
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=db,
            pollutant="NOx",
            source_type="movements",
            grid_config=grid,
            method="bymode",
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
            if not name.startswith("id "):
                continue
            oid = int(name.split(":")[0][3:])
            t = totals.setdefault(oid, {p: 0.0 for p in POLLUTANTS})
            for e in emissions:
                k = e.transposeToKilograms()
                for p in POLLUTANTS:
                    t[p] += k.getObject(f"{p}_kg") or 0.0
    return totals


def test_standalone_matches_plugin_with_gate_emissions_code_0(study):
    plugin = _plugin_totals(study)
    with sqlite3.connect(study) as conn:
        sa = compute_all_movements(conn, method="bymode", use_isa_meteo=False)
        departures = {
            r[0]
            for r in conn.execute(
                "SELECT oid FROM user_aircraft_movements WHERE departure_arrival = 'D'"
            )
        }
    assert departures, "test premise: the fixture has departures"
    for oid in sorted(departures & set(sa)):
        assert sa[oid]["start_em_kg"]["hc"] == 0.0, oid
        for p in POLLUTANTS:
            assert sa[oid]["total_em_kg"][p] == pytest.approx(
                plugin[oid][p], rel=1e-6, abs=1e-12
            ), (oid, p)
