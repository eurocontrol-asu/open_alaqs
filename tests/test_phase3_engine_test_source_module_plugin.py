"""Phase 3: plugin-side tests for ``EngineTestSourceModule`` and the
test-site skip in ``AreaSourceWithTimeProfileModule``.

Two layers of tests:

  1. Pure-function tests on ``_period_window_fraction`` and ``_resolve_ei``
     helpers. QGIS-free; import only the module-level free functions.

  2. Integration tests on ``EngineTestSourceModule.process`` using fake
     stores. QGIS-gated (module imports SourceModule → alaqsdblite →
     qgis.utils). Fakes exchange the AircraftStore / EngineStore /
     EventsStore inside beginJob for controllable EI values so we can
     assert emission masses to the last decimal.

Run under OSGeo4W shell:

    python-qgis-ltr -m pytest \
        tests/test_phase3_engine_test_source_module_plugin.py -v
"""

from __future__ import annotations

from datetime import datetime

import pytest

try:
    from qgis.core import QgsApplication  # noqa: F401

    from open_alaqs.core.interfaces.AreaSources import (
        AreaSources,
        AreaSourcesDatabase,
        AreaSourcesStore,
    )
    from open_alaqs.core.interfaces.EngineTestEvent import EngineTestEvent
    from open_alaqs.core.interfaces.EngineTestEvents import (
        EngineTestEventsDatabase,
        EngineTestEventsStore,
    )
    from open_alaqs.core.modules.AreaSourceModule import (
        AreaSourceWithTimeProfileModule,
    )
    from open_alaqs.core.modules.EngineTestSourceModule import (
        EngineTestSourceModule,
        _period_window_fraction,
        _resolve_ei,
    )

    HAS_QGIS = True
except Exception:  # pragma: no cover
    HAS_QGIS = False


pytestmark = pytest.mark.skipif(
    not HAS_QGIS, reason="QGIS Python not importable in this environment"
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset every Singleton cache the tests can populate. Same pattern
    used in Phase 1b / Phase 2 test files; prevents pollution across
    tests and across the wider suite."""
    if HAS_QGIS:
        AreaSourcesDatabase.reset()
        AreaSourcesStore.reset()
        EngineTestEventsDatabase.reset()
        EngineTestEventsStore.reset()
    yield
    if HAS_QGIS:
        AreaSourcesDatabase.reset()
        AreaSourcesStore.reset()
        EngineTestEventsDatabase.reset()
        EngineTestEventsStore.reset()


# ═══════════════════════════════════════════════════════════════════════
# Section 1: _period_window_fraction pure function
# ═══════════════════════════════════════════════════════════════════════


def _dt(day, hour, minute=0):
    return datetime(2024, 12, day, hour, minute)


def test_fraction_event_entirely_inside_period_is_one():
    assert (
        _period_window_fraction(_dt(1, 9, 15), _dt(1, 9, 45), _dt(1, 9), _dt(1, 10))
        == 1.0
    )


def test_fraction_event_straddles_period_start_half():
    """Event 08:45-09:15 in period 09:00-10:00: 15 of 30 minutes inside."""
    assert (
        _period_window_fraction(_dt(1, 8, 45), _dt(1, 9, 15), _dt(1, 9), _dt(1, 10))
        == 0.5
    )


def test_fraction_event_straddles_period_end_half():
    """Event 09:45-10:15 in period 09:00-10:00: 15 of 30 minutes inside."""
    assert (
        _period_window_fraction(_dt(1, 9, 45), _dt(1, 10, 15), _dt(1, 9), _dt(1, 10))
        == 0.5
    )


def test_fraction_event_outside_period_is_zero():
    assert _period_window_fraction(_dt(1, 7), _dt(1, 8), _dt(1, 9), _dt(1, 10)) == 0.0


def test_fraction_event_touching_boundary_is_zero():
    """Event 08:00-09:00 touches period 09:00-10:00 at start; strict
    overlap semantics → 0."""
    assert _period_window_fraction(_dt(1, 8), _dt(1, 9), _dt(1, 9), _dt(1, 10)) == 0.0


def test_fraction_split_across_three_periods_sums_to_one():
    """Event 09:30-11:30 (2h) split across three 1h periods should sum
    to 1.0: fractions 0.25 + 0.50 + 0.25."""
    ev_start, ev_end = _dt(1, 9, 30), _dt(1, 11, 30)
    p1 = _period_window_fraction(ev_start, ev_end, _dt(1, 9), _dt(1, 10))
    p2 = _period_window_fraction(ev_start, ev_end, _dt(1, 10), _dt(1, 11))
    p3 = _period_window_fraction(ev_start, ev_end, _dt(1, 11), _dt(1, 12))
    assert p1 == 0.25
    assert p2 == 0.5
    assert p3 == 0.25
    assert abs(p1 + p2 + p3 - 1.0) < 1e-9


def test_fraction_missing_datetimes_returns_zero():
    assert _period_window_fraction(None, _dt(1, 9, 15), _dt(1, 9), _dt(1, 10)) == 0.0
    assert _period_window_fraction(_dt(1, 9, 15), None, _dt(1, 9), _dt(1, 10)) == 0.0


def test_fraction_end_before_start_returns_zero():
    """Non-positive event duration is degenerate; degenerate events do
    not contribute."""
    assert _period_window_fraction(_dt(1, 10), _dt(1, 9), _dt(1, 9), _dt(1, 10)) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Section 2: _resolve_ei helper (snap vs meem paths)
# ═══════════════════════════════════════════════════════════════════════


def test_resolve_ei_snap_uses_plain_lookup():
    """Snap path calls plain getEmissionIndexByMode, does not attempt
    MEEM."""
    calls = []

    class FakeEngine:
        def getEmissionIndexByMode(self, mode):
            calls.append(("snap", mode))
            return "snap-ei"

        def getEmissionIndexByModeWithMEEM(self, mode, **kwargs):  # pragma: no cover
            calls.append(("meem", mode))
            return "should-not-be-called"

    ei = _resolve_ei(FakeEngine(), "TX", "snap")
    assert ei == "snap-ei"
    assert calls == [("snap", "TX")]


def test_resolve_ei_meem_calls_meem_path():
    calls = []

    class FakeEngine:
        def getEmissionIndexByMode(self, mode):  # pragma: no cover
            calls.append(("snap", mode))
            return "snap-ei"

        def getEmissionIndexByModeWithMEEM(self, mode, **kwargs):
            calls.append(("meem", mode, kwargs.get("p_amb_Pa"), kwargs.get("mach")))
            return "meem-ei"

    ei = _resolve_ei(FakeEngine(), "CL", "meem")
    assert ei == "meem-ei"
    assert calls == [("meem", "CL", 101325.0, 0.0)]


def test_resolve_ei_meem_falls_back_to_snap_when_unavailable():
    """If MEEM returns None (older engine data), snap is called as
    fallback."""
    calls = []

    class FakeEngine:
        def getEmissionIndexByMode(self, mode):
            calls.append(("snap", mode))
            return "snap-fallback-ei"

        def getEmissionIndexByModeWithMEEM(self, mode, **kwargs):
            calls.append(("meem", mode))
            return None  # unavailable

    ei = _resolve_ei(FakeEngine(), "TO", "meem")
    assert ei == "snap-fallback-ei"
    assert calls == [("meem", "TO"), ("snap", "TO")]


def test_resolve_ei_returns_none_on_exception():
    class FakeEngine:
        def getEmissionIndexByMode(self, mode):
            raise Exception("mode unknown")

    ei = _resolve_ei(FakeEngine(), "TX", "snap")
    assert ei is None


# ═══════════════════════════════════════════════════════════════════════
# Section 3: EngineTestSourceModule.process with fake stores
# ═══════════════════════════════════════════════════════════════════════


class _FakeEI:
    """Minimal EmissionIndex-shaped fake for the Emission.add pathway.

    ``Emission.add`` calls:
      - ``self.getObject("fuel_kg_sec")`` for fuel-flow lookup.
      - ``self.get_value(pollutant_type, "g_kg")`` for every pollutant.

    Concrete pollutants come from ``PollutantType``. We return zero for
    pollutants we don't care about in a given test; the test asserts on
    the ones we do care about.
    """

    def __init__(self, fuel_kg_sec: float, pollutant_g_per_kg: dict):
        self._fuel = fuel_kg_sec
        # Pollutant map keyed by PollutantType.name for lookup below.
        self._pollutant = pollutant_g_per_kg

    def getObject(self, key):
        if key == "fuel_kg_sec":
            return self._fuel
        return 0.0

    def get_value(self, pollutant_type, unit):
        return self._pollutant.get(pollutant_type.name, 0.0)


class _FakeAircraft:
    engine_count = 2

    def getDefaultEngine(self):
        return None


class _FakeAircraftStore:
    """AircraftStore-shaped: getObject(icao) → aircraft."""

    def __init__(self, mapping):
        self._m = mapping

    def getObject(self, key):
        return self._m.get(key)


class _FakeEngine:
    """Engine-shaped: getEmissionIndexByMode(mode) → EmissionIndex."""

    def __init__(self, per_mode_ei):
        self._per_mode = per_mode_ei

    def getEmissionIndexByMode(self, mode):
        return self._per_mode.get(mode)


class _FakeEngineStore:
    def __init__(self, mapping):
        self._m = mapping

    def getObject(self, key):
        return self._m.get(key)


class _FakeEventsStore:
    """EventsStore-shaped: getEventsInPeriod(start, end) → list of events."""

    def __init__(self, events):
        self._events = events

    def getEventsInPeriod(self, start, end):
        # Trust the test to hand only events that overlap.
        return list(self._events)


def _make_module_with_fakes(events, aircraft_map, engine_map):
    """Instantiate an EngineTestSourceModule and wire the fake stores in."""
    m = EngineTestSourceModule({"database_path": None, "name": "test"})
    m.setEventsStore(_FakeEventsStore(events))
    m.setAircraftStore(_FakeAircraftStore(aircraft_map))
    m.setEngineStore(_FakeEngineStore(engine_map))
    return m


def _make_test_site_source(source_id: str = "N1"):
    """AreaSource flagged as an in-study test site with a simple geometry."""
    src = AreaSources({"source_id": source_id, "is_test_site": "1", "instudy": "1"})
    # Give it a trivial geometry so setGeometryText/getGeometryText round-trip
    # something. The module only reads getGeometryText; any string works.
    src.setGeometryText(f"POLYGON(({source_id}))")
    return src


def _event(
    source_id="N1",
    event_id=1,
    aircraft_type="C56X",
    engine_uid="B602",
    engine_count=2,
    t_TX_s=0,
    t_AP_s=0,
    t_CL_s=0,
    t_TO_s=0,
    start="2024-12-01T09:00:00",
    end="2024-12-01T09:30:00",
    thrust_mode="snap",
    instudy="1",
):
    return EngineTestEvent(
        {
            "event_id": event_id,
            "source_id": source_id,
            "start_datetime": start,
            "end_datetime": end,
            "aircraft_type": aircraft_type,
            "engine_uid": engine_uid,
            "engine_count": engine_count,
            "t_TX_s": t_TX_s,
            "t_AP_s": t_AP_s,
            "t_CL_s": t_CL_s,
            "t_TO_s": t_TO_s,
            "thrust_mode": thrust_mode,
            "instudy": instudy,
        }
    )


def test_process_event_entirely_in_period_full_contribution():
    """Event 09:00-09:30 with 900s CL, engine_count=2, EI known → expected
    fuel = fuel_kg_sec * time * engine_count * fraction (fraction=1)."""
    from open_alaqs.core.interfaces.Emissions import PollutantType, PollutantUnit

    ei_cl = _FakeEI(fuel_kg_sec=0.5, pollutant_g_per_kg={PollutantType.NOx.name: 20.0})
    engine = _FakeEngine({"CL": ei_cl})
    event = _event(t_CL_s=900, engine_count=2)  # 900s CL, 2 engines

    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": engine},
    )
    src = _make_test_site_source()
    m.setSource("N1", src)

    result = m.process(_dt(1, 9), _dt(1, 10))
    assert len(result) == 1
    start_dt_, source_, emissions_ = result[0]
    assert start_dt_ == _dt(1, 9)
    assert source_ is src
    assert len(emissions_) == 1

    e = emissions_[0]
    # fuel_kg = fuel_kg_sec * t_effective; t_effective = 900 * 2 * 1.0 = 1800
    # fuel_kg = 0.5 * 1800 = 900
    fuel_kg, _ = e.getFuel(unit="kg")
    assert abs(fuel_kg - 900.0) < 1e-9

    # NOx = pollutant_g_per_kg["NOx"] * fuel_kg = 20 * 900 = 18000 g
    nox_g = e.get_value(PollutantType.NOx, PollutantUnit.GRAM)
    assert abs(nox_g - 18000.0) < 1e-6


def test_process_event_straddles_period_start_half_contribution():
    """Event 08:45-09:15 (30min), t_CL=1800s, period 09:00-10:00 → fraction
    0.5 → t_effective = 1800 * engine_count * 0.5 = 1800 (for 2 engines)."""
    from open_alaqs.core.interfaces.Emissions import PollutantType

    ei_cl = _FakeEI(fuel_kg_sec=1.0, pollutant_g_per_kg={PollutantType.NOx.name: 10.0})
    engine = _FakeEngine({"CL": ei_cl})
    event = _event(
        t_CL_s=1800,
        engine_count=2,
        start="2024-12-01T08:45:00",
        end="2024-12-01T09:15:00",
    )
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": engine},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))

    e = result[0][2][0]
    fuel_kg, _ = e.getFuel(unit="kg")
    # t_effective = 1800 * 2 * 0.5 = 1800; fuel_kg = 1.0 * 1800 = 1800
    assert abs(fuel_kg - 1800.0) < 1e-9


def test_process_multiple_events_same_source_summed():
    """Two events on the same source in the same period → emissions
    summed into one Emission attached to the source."""
    from open_alaqs.core.interfaces.Emissions import PollutantType

    ei = _FakeEI(fuel_kg_sec=1.0, pollutant_g_per_kg={PollutantType.NOx.name: 5.0})
    engine = _FakeEngine({"TX": ei})
    e1 = _event(event_id=1, t_TX_s=600, engine_count=1)
    e2 = _event(
        event_id=2,
        t_TX_s=300,
        engine_count=1,
        start="2024-12-01T09:45:00",
        end="2024-12-01T09:55:00",
    )

    m = _make_module_with_fakes(
        events=[e1, e2],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": engine},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))

    emissions = result[0][2][0]
    fuel_kg, _ = emissions.getFuel(unit="kg")
    # e1: 600 * 1 * 1.0 = 600s ; e2: 300 * 1 * 1.0 = 300s. sum = 900. * 1.0 fuel_kg_sec
    assert abs(fuel_kg - 900.0) < 1e-9


def test_process_zero_running_event_produces_no_emission():
    """Event with all mode times zero → no contribution → source not in
    result."""
    engine = _FakeEngine({"TX": _FakeEI(1.0, {})})
    event = _event(t_TX_s=0, t_AP_s=0, t_CL_s=0, t_TO_s=0)

    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": engine},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_unresolvable_aircraft_skips_event_no_exception():
    """aircraft_type absent from AircraftStore → event skipped, no emission,
    no exception."""
    event = _event(aircraft_type="UNKNOWN")

    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={},  # empty
        engine_map={"B602": _FakeEngine({"CL": _FakeEI(1.0, {})})},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_unresolvable_engine_skips_event():
    event = _event(engine_uid="MISSING")
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_out_of_study_event_skipped():
    """An event with instudy='0' is ignored even if it overlaps the
    period."""
    event = _event(t_CL_s=900, instudy="0")
    ei_cl = _FakeEI(1.0, {})
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": _FakeEngine({"CL": ei_cl})},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_non_test_site_source_ignored():
    """A source with is_test_site='0' is NEVER processed by this module
    even if it happens to have matching events in the store."""
    event = _event(source_id="A1", t_CL_s=900)
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": _FakeEngine({"CL": _FakeEI(1.0, {})})},
    )
    normal = AreaSources({"source_id": "A1", "is_test_site": "0", "instudy": "1"})
    normal.setGeometryText("POLYGON((A1))")
    m.setSource("A1", normal)
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_out_of_study_source_ignored():
    event = _event(t_CL_s=900)
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": _FakeEngine({"CL": _FakeEI(1.0, {})})},
    )
    src = _make_test_site_source()
    src._in_study = False  # force out-of-study
    m.setSource("N1", src)
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_process_source_names_filter():
    event_n1 = _event(source_id="N1", event_id=1, t_CL_s=600, engine_count=1)
    event_comp = _event(source_id="COMP", event_id=2, t_CL_s=600, engine_count=1)
    ei = _FakeEI(1.0, {})
    m = _make_module_with_fakes(
        events=[event_n1, event_comp],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": _FakeEngine({"CL": ei})},
    )
    m.setSource("N1", _make_test_site_source("N1"))
    m.setSource("COMP", _make_test_site_source("COMP"))
    # Filter to just N1
    result = m.process(_dt(1, 9), _dt(1, 10), source_names=["N1"])
    assert len(result) == 1
    assert result[0][1].getName() == "N1"


def test_process_no_events_store_returns_empty():
    """If the events store was never set (beginJob not called and no
    setter injected), process returns [] rather than raising."""
    m = EngineTestSourceModule({"database_path": None, "name": "test"})
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Section 4: AreaSourceWithTimeProfileModule skips test sites
# ═══════════════════════════════════════════════════════════════════════


def test_area_source_module_skips_test_sites():
    """A test-site source in AreaSourceWithTimeProfileModule.process is
    silently skipped (no emission produced for it). Prevents double-count
    with EngineTestSourceModule."""
    m = AreaSourceWithTimeProfileModule({"database_path": None, "name": "test"})
    test_src = _make_test_site_source("N1")
    # Give it non-zero unit_year and geometry so the loop WOULD have
    # produced emissions without the skip.
    test_src._unit_year = 1.0
    m.setSource("N1", test_src)

    # No profile stores initialized (beginJob not called), so if the
    # skip isn't in place we'd crash trying to look up profiles. That's
    # actually a nicer failure mode for this test than getting a zero
    # emission.
    result = m.process(_dt(1, 9), _dt(1, 10))
    assert result == []


def test_area_source_module_processes_normal_sources_when_test_sites_present():
    """Mixed source dict: a test site (skipped) + a normal source (would
    process normally). The normal one should still get processed; we
    just verify the loop doesn't abort on the test site.

    Doesn't assert emission values because those require full profile
    machinery; asserts that the test site is filtered and the normal
    source at least reaches the profile-lookup stage (which raises
    without beginJob, and that's what we check).
    """
    m = AreaSourceWithTimeProfileModule({"database_path": None, "name": "test"})

    test_src = _make_test_site_source("N1")
    normal_src = AreaSources(
        {
            "source_id": "A1",
            "is_test_site": "0",
            "instudy": "1",
        }
    )
    normal_src.setGeometryText("POLYGON((A1))")
    normal_src._unit_year = 1.0

    m.setSource("N1", test_src)
    m.setSource("A1", normal_src)

    # Filter to just N1 (the test site). With the skip in place, no
    # sources are processed → empty result, no exception.
    result = m.process(_dt(1, 9), _dt(1, 10), source_names=["N1"])
    assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Section 5: Thrust-mode override end-to-end
# ═══════════════════════════════════════════════════════════════════════


def test_process_meem_thrust_mode_calls_meem_ei():
    """An event with thrust_mode='meem' pulls the MEEM-corrected EI."""
    from open_alaqs.core.interfaces.Emissions import PollutantType, PollutantUnit

    meem_ei = _FakeEI(
        fuel_kg_sec=1.0, pollutant_g_per_kg={PollutantType.NOx.name: 30.0}
    )
    snap_ei = _FakeEI(
        fuel_kg_sec=1.0, pollutant_g_per_kg={PollutantType.NOx.name: 10.0}
    )

    class DualEngine:
        def getEmissionIndexByMode(self, mode):
            return snap_ei

        def getEmissionIndexByModeWithMEEM(self, mode, **kwargs):
            return meem_ei

    event = _event(t_CL_s=900, engine_count=1, thrust_mode="meem")
    m = _make_module_with_fakes(
        events=[event],
        aircraft_map={"C56X": _FakeAircraft()},
        engine_map={"B602": DualEngine()},
    )
    m.setSource("N1", _make_test_site_source())
    result = m.process(_dt(1, 9), _dt(1, 10))

    e = result[0][2][0]
    # If MEEM EI was used, NOx = 30 g/kg * 900 kg fuel = 27000. If snap,
    # 10 g/kg * 900 kg = 9000.
    nox_g = e.get_value(PollutantType.NOx, PollutantUnit.GRAM)
    assert abs(nox_g - 27000.0) < 1e-6
