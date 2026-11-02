"""Single-engine taxi and taxi_fuel_ratio: plugin and standalone agree.

The plugin (MovementEmissionCalculator.TaxiingEmissionCalculator) runs a taxi
route segment on min(taxi_engine_count, engines) engines, with taxi_fuel_ratio,
only when a main engine start time (departures) or main engine off time
(arrivals) is set and the segment falls on the single-engine side of it; all
other taxi runs on all engines without the ratio. The standalone used all
engines everywhere and applied taxi_fuel_ratio to the whole route.

Each case changes the departures and arrivals of the training_v3 fixture
(1 to 3 December 2025, taxi times of 300 s) and compares, for the movements of
1 December 06:00 to 08:00, the per-movement totals of both pipelines (bymode),
and for one departure and one arrival the emission of each taxi route segment.
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

# Fixed-wing movements of 1 December 06:00 to 08:00: arrival 1, departure 2,
# arrival 3, departure 4.
OIDS = (1, 2, 3, 4)

CASES = {
    # main engine start 120 s after block-off on one engine; main engines off
    # 60 s after the runway exit
    "after_block_off": (
        dict(
            taxi_engine_count=1,
            set_time_of_main_engine_start_after_block_off_in_s=120,
            taxi_fuel_ratio=0.8,
        ),
        dict(
            taxi_engine_count=1,
            set_time_of_main_engine_off_after_runway_exit_in_s=60,
            taxi_fuel_ratio=0.7,
        ),
    ),
    # main engine start 200 s before take-off; the queue is split at it
    "before_takeoff": (
        dict(
            taxi_engine_count=1,
            set_time_of_main_engine_start_before_takeoff_in_s=200,
            taxi_fuel_ratio=0.9,
        ),
        dict(taxi_fuel_ratio=0.5),
    ),
    # a taxi fuel ratio without a main engine time has no effect
    "ratio_only": (dict(taxi_fuel_ratio=0.5), dict(taxi_fuel_ratio=0.5)),
    # the whole taxi on one engine, with stop-and-go
    "all_single": (
        dict(
            taxi_engine_count=1,
            set_time_of_main_engine_start_after_block_off_in_s=1000,
            taxi_fuel_ratio=0.6,
            number_of_stop_and_gos=2,
        ),
        dict(
            taxi_engine_count=1,
            set_time_of_main_engine_off_after_runway_exit_in_s=0,
            taxi_fuel_ratio=0.6,
            number_of_stop_and_gos=1,
        ),
    ),
    # values as text, read as the plugin reads them: "1.0" is no integer
    # (taxi_engine_count 2), -90 is 90 s, "0,8" is 0.8
    "text_values": (
        dict(
            taxi_engine_count="1.0",
            set_time_of_main_engine_start_after_block_off_in_s="-90",
            taxi_fuel_ratio="0,8",
        ),
        dict(
            taxi_engine_count="",
            set_time_of_main_engine_off_after_runway_exit_in_s="30",
            taxi_fuel_ratio=0.8,
        ),
    ),
}


@pytest.fixture(autouse=True)
def _isolate_singletons():
    """Same isolation as test_zz_movement_grouping_regression."""
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


def _prepare(tmp_path, case):
    if not SRC.exists():
        pytest.skip(f"training inventory not found at {SRC}")
    dep, arr = CASES[case]
    dst = tmp_path / f"{case}.alaqs"
    shutil.copy(SRC, dst)
    with sqlite3.connect(dst) as conn:
        for flag, changes in (("D", dep), ("A", arr)):
            conn.execute(
                "UPDATE user_aircraft_movements SET %s "
                "WHERE departure_arrival = ? AND aircraft <> 'AS50'"
                % ", ".join(f"{k} = ?" for k in changes),
                list(changes.values()) + [flag],
            )
        conn.commit()
    return str(dst)


def _plugin(db_path):
    """{oid: [emission objects in calculation order]} and {oid: totals}."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    ProjectDatabase().path = db_path
    cfg = EmissionCalculationConfig(
        db_path=db_path,
        pollutant="NOx",
        source_type="movements",
        grid_config=GRID_CONFIG,
        method="bymode",
        start_dt_inclusive=datetime.datetime(2025, 12, 1, 6),
        end_dt_inclusive=datetime.datetime(2025, 12, 1, 8),
        time_interval=timedelta(seconds=3600),
        should_apply_nox_corrections=False,
    )
    result = EmissionCalculatorService().calculate_emissions(cfg)
    assert result.success, result.error_message
    per_oid = {}
    for _, period in result.emissions_data.items():
        for source, emissions in period:
            oid = int(str(source.getName()).split(":")[0].split()[1])
            per_oid.setdefault(oid, []).extend(emissions)
    return per_oid


def _kg(emission, pollutant):
    return emission.transposeToKilograms().getObject(f"{pollutant}_kg") or 0.0


def _standalone(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return compute_all_movements(
            conn, method="bymode", use_isa_meteo=False, oids=list(OIDS)
        )
    finally:
        conn.close()


@pytest.mark.parametrize("case", sorted(CASES))
def test_movement_totals_match(tmp_path, case):
    db = _prepare(tmp_path, case)
    plugin = _plugin(db)
    standalone = _standalone(db)
    for oid in OIDS:
        for pollutant in ("nox", "co", "hc"):
            a = sum(_kg(e, pollutant) for e in plugin[oid])
            b = standalone[oid]["total_em_kg"][pollutant]
            assert b == pytest.approx(a, rel=1e-8), (case, oid, pollutant, a, b)


def _plugin_taxi_segments(emissions):
    """The plugin's taxi route segment emissions: ground line strings written
    with a Z (the flight segments are written without)."""
    return [
        e
        for e in emissions
        if str(e.getGeometryText()).upper().startswith("LINESTRING Z")
    ]


@pytest.mark.parametrize("case", ["after_block_off", "all_single"])
def test_taxi_segment_split_matches(tmp_path, case):
    db = _prepare(tmp_path, case)
    plugin = _plugin(db)
    standalone = _standalone(db)
    for oid in (1, 2):  # an arrival and a departure
        res = standalone[oid]
        weights = res["tx_segment_weights"]
        assert weights is not None
        segs = _plugin_taxi_segments(plugin[oid])
        assert len(segs) == len(weights)
        last = len(weights) - 1
        for i, (seg, w) in enumerate(zip(segs, weights)):
            want = res["tx_em_kg"]["nox"] * w
            if i == last:
                want += res["queue_em_kg"]["nox"] + res["stop_em_kg"]["nox"]
            if i == 0:
                for key in ("apu_em_kg", "start_em_kg", "brake_wear_em_kg"):
                    want += (res.get(key) or {}).get("nox", 0.0)
            assert _kg(seg, "nox") == pytest.approx(want, rel=1e-8), (case, oid, i)
