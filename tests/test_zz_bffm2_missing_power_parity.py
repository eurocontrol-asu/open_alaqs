"""BFFM2 segments without power and fuel flow: standalone must mirror the plugin.

Under BFFM2, MovementEmissionCalculator falls back to Bymode emission indices for
a segment whose start point has neither a power setting nor a fuel flow (the
"Bug #22" guard). Piston and propeller ANP profiles often have no power. The
standalone (and the CAEP14 reference) used the mode-anchor fuel flow with the
BFFM2 ambient correction instead, so the two tools disagreed on such segments.

The test blanks power and fuel flow on one departure and one arrival profile of
the training fixture and requires plugin and standalone to agree on the movements
that use them, for both BFFM2 fuel-flow sources.
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
BLANKED = ("JET-SMALL-D-1", "JET-SMALL-A-1")


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
        conn.executemany(
            "UPDATE default_aircraft_profiles SET power = NULL, fuel_flow_kgm = NULL "
            "WHERE profile_id = ?",
            [(p,) for p in BLANKED],
        )
        conn.commit()
    return str(dst)


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


@pytest.mark.parametrize(
    "ff_source,method", [("mode_anchor", "bffm2_anchor"), ("trajectory", "bffm2_traj")]
)
def test_standalone_matches_plugin_when_power_missing(study, ff_source, method):
    plugin = _plugin_nox(study, ff_source)
    with sqlite3.connect(study) as conn:
        sa = compute_all_movements(conn, method=method, use_isa_meteo=False)
        affected = {
            r[0]
            for r in conn.execute(
                "SELECT oid FROM user_aircraft_movements WHERE profile_id IN (?, ?)",
                BLANKED,
            )
        }
    assert affected, "test premise: some movements must use the blanked profiles"
    for oid in sorted(affected):
        assert sa[oid]["total_em_kg"]["nox"] == pytest.approx(
            plugin[oid], rel=1e-6
        ), f"oid {oid}"
