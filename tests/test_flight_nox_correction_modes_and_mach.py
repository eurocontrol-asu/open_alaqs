"""FlightEmissionCalculator, live: the ICCAIA NOx correction and the segment Mach.

With the NOx ambient correction on, only take-off and climb-out segments are
corrected (NOX_CORRECTION_MODES); an arrival's approach (AP) segments keep the
uncorrected NOx. The segment Mach number handed to the emission index lookup
is TAS / a(T), a = sqrt(gamma R T) of the ambient temperature.
"""

import math
import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()


@pytest.fixture(autouse=True)
def _restore_project_database():
    """Leave the ProjectDatabase singleton (and its path) as other tests set it."""
    from open_alaqs.core.alaqsdblite import ProjectDatabase

    previous = getattr(ProjectDatabase(), "path", None)
    yield
    ProjectDatabase().path = previous


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)
T_K = 268.15  # cold, so that the NOx correction is not 1


@pytest.fixture
def movements(tmp_path_factory):
    # GeoTransformation before Movement: imported the other way round (Movement
    # imports it lazily) the process aborts at exit (free(): invalid pointer)
    # when this file runs alone.
    from open_alaqs.core import GeoTransformation  # noqa: F401
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore
    from open_alaqs.core.tools.Singleton import Singleton

    db = tmp_path_factory.mktemp("noxmodes") / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM user_aircraft_movements WHERE oid NOT IN (1, 2)")
        table = MovementStore._TRAJ_CACHE_TABLE
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?", (table,)
        ).fetchone():
            conn.execute(f"DELETE FROM {table}")
    Singleton.reset_all()
    previous = getattr(ProjectDatabase(), "path", None)
    ProjectDatabase().path = str(db)
    store = MovementStore(str(db), show_progress=False)
    by_flag = {m.getDepartureArrivalFlag(): m for m in store.getObjects().values()}
    yield by_flag
    import gc

    del store, by_flag
    Singleton.reset_all()
    gc.collect()
    ProjectDatabase().path = previous


def _run(movement, nox_corr, spy=None):
    from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
    from open_alaqs.core.interfaces.Emissions import PollutantType, PollutantUnit
    from open_alaqs.core.MovementEmissionCalculator import FlightEmissionCalculator

    method = {
        "name": "bymode",
        "config": {
            "apply_smooth_and_shift": "none",
            "apply_nox_corrections": nox_corr,
            "airport_altitude": -5.0,
            "installation_corrections": {},
            "ambient_conditions": AmbientCondition({"id": 1, "Temperature": T_K}),
            "meem_version": "v1",
            "bffm2_ff_source": "trajectory",
        },
    }
    calc = FlightEmissionCalculator(
        movement.getTrajectoryAtRunway(),
        movement.getAircraft(),
        movement.getAircraftEngine(),
        movement.getTakeoffWeightRatio(),
        movement.getDepartureArrivalFlag(),
        movement.getName(),
        at_runway=True,
        method=method,
        mode="",
        limit={"max_height": 914.4, "height_unit_in_feet": False},
    )
    if spy is not None:
        original = calc._get_emission_index

        def recording(mode, *args, **kwargs):
            spy.append(
                (
                    mode,
                    calc._segment_tas_m_s,
                    method["config"]["mach_number"],
                    method["config"]["ambient_conditions"].getTemperature(),
                )
            )
            return original(mode, *args, **kwargs)

        calc._get_emission_index = recording
    pairs = movement.getTrajectoryAtRunway().getPointPairs("")
    out = []
    for (start, _end), em in zip(pairs, calc.calculate_emissions()):
        e = em["emissions"][0]
        out.append(
            (start.getMode(), e.get_value(PollutantType.NOx, PollutantUnit.GRAM))
        )
    return out


def _nox_by_mode(rows):
    totals = {}
    for mode, nox in rows:
        totals[mode] = totals.get(mode, 0.0) + nox
    return totals


def test_arrival_approach_is_not_corrected(movements):
    arrival = movements["A"]
    plain = _run(arrival, nox_corr=False)
    corrected = _run(arrival, nox_corr=True)
    assert [m for m, _ in plain] == [m for m, _ in corrected]
    ap = [(a, b) for (m, a), (_, b) in zip(plain, corrected) if m == "AP"]
    assert ap and sum(a for a, _ in ap) > 0.0
    for a, b in ap:
        assert b == pytest.approx(a, rel=1e-12, abs=0.0)


def test_departure_take_off_and_climb_are_corrected(movements):
    departure = movements["D"]
    plain = _nox_by_mode(_run(departure, nox_corr=False))
    corrected = _nox_by_mode(_run(departure, nox_corr=True))
    for mode in ("TO", "CL"):
        assert plain.get(mode, 0.0) > 0.0
        assert corrected[mode] != pytest.approx(plain[mode], rel=1e-6)


def test_segment_mach_is_tas_over_speed_of_sound(movements):
    """Mach = TAS / a(T) with T the segment's local temperature (atmosphere_model,
    default surface_layer, 5.4.1): the hourly temperature at the ground, lower aloft."""
    seen = []
    _run(movements["D"], nox_corr=True, spy=seen)
    assert seen
    for _mode, tas, mach, t_local in seen:
        assert mach == pytest.approx(
            tas / math.sqrt(1.4 * 287.05287 * t_local), rel=1e-9
        )
    assert any(mach > 0.1 for _, _, mach, _ in seen)
    assert any(t_local < T_K - 1.0 for _, _, _, t_local in seen)
