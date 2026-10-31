"""Single-engine taxi of a departure, and the taxi BFFM2 index lookup.

- ``set_time_of_main_engine_start_before_takeoff_in_s`` = X: the main engines
  are started X s before take-off, so the aircraft taxis on
  ``taxi_engine_count`` engines before that point (block-off to total - X).
  The comparison was reversed: single-engine taxi was applied to the segments
  after that point, where all engines run.
- ``gate_emissions_code`` 0 leaves out the main engine start emissions. The
  start emissions of the single-engine-taxi engines were still added.
- BFFM2: when the engine has no index for the taxi thrust, the taxi loop
  raised UnboundLocalError (``mode_ei_``) instead of logging the missing
  index and returning no taxi emissions, as the bymode branch does.

No shipped fixture sets the main-engine-start times, so their results do not
change. The test uses departure oid 2 of training_v3 (A20N, gate to runway
route of 4 segments, 300 s block to runway time).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)
OID = 2  # A20N departure, 2 engines


@pytest.fixture(autouse=True)
def _restore_project_database():
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.tools.Singleton import Singleton

    previous = getattr(ProjectDatabase(), "path", None)
    Singleton.reset_all()
    yield
    Singleton.reset_all()
    ProjectDatabase().path = previous


def _movement(tmp_path, **columns):
    from open_alaqs.core.alaqsdblite import ProjectDatabase
    from open_alaqs.core.interfaces.Movement import MovementStore
    from open_alaqs.core.tools.Singleton import Singleton

    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        for col, val in columns.items():
            conn.execute(
                f"UPDATE user_aircraft_movements SET {col} = ? WHERE oid = ?",
                (val, OID),
            )
    Singleton.reset_all()  # a fresh MovementStore for each call
    ProjectDatabase().path = str(db)
    return MovementStore(str(db), show_progress=False).getObject(OID)


def _single_engine_segments(movement):
    """Run the taxi calculation; return the segment indices on single-engine taxi
    and the cumulative moving time at the end of each segment."""
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    calc = TaxiingEmissionCalculator(movement)
    inner = calc._apply_single_engine_taxiing_emissions_for_departure
    seen = []

    def spy(emission, index_segment, elapsed):
        n, ratio = inner(emission, index_segment, elapsed)
        seen.append((index_segment, elapsed, n))
        return n, ratio

    calc._apply_single_engine_taxiing_emissions_for_departure = spy
    calc.calculate_emissions()
    single = [i for i, _, n in seen if n is not None]
    ends = [e for _, e, _ in seen]
    return single, ends, calc


def _hc_kg(emissions):
    return sum(
        e.transposeToKilograms().getObject("hc_kg") or 0.0
        for d in emissions
        for e in d["emissions"]
    )


def test_before_takeoff_applies_single_engine_before_main_engine_start(tmp_path):
    x = 200.0
    m = _movement(
        tmp_path,
        taxi_engine_count=1,
        set_time_of_main_engine_start_before_takeoff_in_s=x,
    )
    single, ends, calc = _single_engine_segments(m)
    total = calc._total_taxiing_time
    assert total == pytest.approx(300.0)
    expected = [i for i, e in enumerate(ends) if e + x <= total]
    # Test premise: the main engine start splits the route.
    assert 0 < len(expected) < len(ends)
    assert single == expected
    assert 0 in single  # the first segment, from the gate, is on one engine


def test_before_takeoff_equals_after_block_off_at_the_same_instant(tmp_path):
    before, _, _ = _single_engine_segments(
        _movement(
            tmp_path / "a",
            taxi_engine_count=1,
            set_time_of_main_engine_start_before_takeoff_in_s=200.0,
        )
    )
    after, _, _ = _single_engine_segments(
        _movement(
            tmp_path / "b",
            taxi_engine_count=1,
            set_time_of_main_engine_start_after_block_off_in_s=100.0,
        )
    )
    assert before == after


@pytest.mark.parametrize(
    "time_column",
    [
        "set_time_of_main_engine_start_after_block_off_in_s",
        "set_time_of_main_engine_start_before_takeoff_in_s",
    ],
)
def test_gate_emissions_code_0_drops_single_engine_start_emissions(
    tmp_path, time_column
):
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    m = _movement(
        tmp_path,
        taxi_engine_count=1,
        gate_emissions_code=0,
        **{time_column: 200.0},
    )
    with_start = TaxiingEmissionCalculator(m)
    assert with_start._include_start_emissions  # test premise
    em_code0 = with_start.calculate_emissions()
    no_start = TaxiingEmissionCalculator(m)
    no_start._include_start_emissions = False
    em_none = no_start.calculate_emissions()
    assert _hc_kg(em_code0) == pytest.approx(_hc_kg(em_none), rel=1e-12)


def test_gate_emissions_code_1_keeps_single_engine_start_emissions(tmp_path):
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    m = _movement(
        tmp_path,
        taxi_engine_count=1,
        gate_emissions_code=1,
        set_time_of_main_engine_start_after_block_off_in_s=100.0,
    )
    calc = TaxiingEmissionCalculator(m)
    start_hc_kg = calc._start_emissions.transposeToKilograms().getObject("hc_kg")
    em = calc.calculate_emissions()
    no_start = TaxiingEmissionCalculator(m)
    no_start._include_start_emissions = False
    # Both engines started once each: one at the gate, one for single-engine taxi.
    assert _hc_kg(em) - _hc_kg(no_start.calculate_emissions()) == pytest.approx(
        2 * start_hc_kg, rel=1e-9
    )


def test_bffm2_taxi_without_index_returns_no_emissions(tmp_path):
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    m = _movement(tmp_path)
    ei = m.getAircraftEngine().getEmissionIndex()
    ei.getEmissionIndexByEngineState = lambda *a, **k: None
    calc = TaxiingEmissionCalculator(m, method={"name": "BFFM2", "config": {}})
    assert calc.calculate_emissions() == []
    assert calc._method["config"]["mach_number"] == 0.0


@pytest.mark.parametrize(
    "time_column, seconds",
    [
        # Shorter than the first segment (9.7 s): no segment ends in the window.
        ("set_time_of_main_engine_start_after_block_off_in_s", 5.0),
        # Main engine start before the end of the first segment.
        ("set_time_of_main_engine_start_before_takeoff_in_s", 295.0),
    ],
)
def test_every_engine_starts_once_when_no_segment_is_single_engine(
    tmp_path, time_column, seconds
):
    """Each engine starts once per departure. When no segment ends inside the
    single-engine window, the aircraft taxis on all engines from the gate, so
    all engines start on the first segment (the single-engine-taxi engines were
    not counted at all)."""
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    m = _movement(
        tmp_path, taxi_engine_count=1, gate_emissions_code=1, **{time_column: seconds}
    )
    single, _, _ = _single_engine_segments(m)
    assert single == []  # test premise
    calc = TaxiingEmissionCalculator(m)
    start_hc_kg = calc._start_emissions.transposeToKilograms().getObject("hc_kg")
    em = calc.calculate_emissions()
    no_start = TaxiingEmissionCalculator(m)
    no_start._include_start_emissions = False
    em_none = no_start.calculate_emissions()
    engines = m.getAircraft().getEngineCount()
    assert _hc_kg(em) - _hc_kg(em_none) == pytest.approx(
        engines * start_hc_kg, rel=1e-9
    )
    # On the first segment, from the gate.
    first = em[0]["emissions"][0].transposeToKilograms().getObject("hc_kg")
    first_none = em_none[0]["emissions"][0].transposeToKilograms().getObject("hc_kg")
    assert first - first_none == pytest.approx(engines * start_hc_kg, rel=1e-9)


def _last_segment_hc_kg(movement, n_segments):
    from open_alaqs.core.MovementEmissionCalculator import TaxiingEmissionCalculator

    calc = TaxiingEmissionCalculator(movement)
    calc._include_start_emissions = False
    em = calc.calculate_emissions()
    return em[n_segments - 1]["emissions"][0].transposeToKilograms().getObject("hc_kg")


@pytest.mark.parametrize(
    "time_column, seconds",
    [
        # Main engine start 200 s after block-off, inside the queue
        # (route 156.3 s, queue 143.7 s, block to runway 300 s).
        ("set_time_of_main_engine_start_after_block_off_in_s", 200.0),
        ("set_time_of_main_engine_start_before_takeoff_in_s", 100.0),
    ],
)
def test_queue_split_at_main_engine_start(tmp_path, time_column, seconds):
    """The queue is on taxi_engine_count engines (with taxi_fuel_ratio) up to
    the main engine start and on all engines after it. It was all charged
    with the last segment's engine count (one engine)."""
    ratio = 0.5
    single, ends, calc = _single_engine_segments(
        _movement(tmp_path / "probe", taxi_engine_count=1, **{time_column: seconds})
    )
    n = len(ends)
    route_end, total = ends[-1], calc._total_taxiing_time
    queue = total - route_end
    mes = 200.0
    assert single == list(range(n))  # test premise: the whole route single-engine
    assert route_end < mes < total  # test premise: the start falls in the queue
    t_last = ends[-1] - ends[-2]

    # HC per engine-second at taxi, from all-engine and single-engine runs
    # (main engines started at take-off) without taxi_fuel_ratio.
    all_eng = _last_segment_hc_kg(
        _movement(tmp_path / "a", taxi_engine_count=1, taxi_fuel_ratio=1.0), n
    )
    one_eng = _last_segment_hc_kg(
        _movement(
            tmp_path / "b",
            taxi_engine_count=1,
            taxi_fuel_ratio=1.0,
            set_time_of_main_engine_start_after_block_off_in_s=total,
        ),
        n,
    )
    rate = (all_eng - one_eng) / (t_last + queue)
    assert rate > 0

    got = _last_segment_hc_kg(
        _movement(
            tmp_path / "c",
            taxi_engine_count=1,
            taxi_fuel_ratio=ratio,
            **{time_column: seconds},
        ),
        n,
    )
    expected = rate * (
        t_last * 1 * ratio + (mes - route_end) * 1 * ratio + (total - mes) * 2
    )
    assert got == pytest.approx(expected, rel=1e-9)
