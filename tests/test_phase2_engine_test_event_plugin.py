"""Phase 2: plugin-side tests for the ``EngineTestEvent`` dataclass,
``EngineTestEventsStore``, and the ``AreaSources.getEngineTestEvents``
convenience accessor.

Requires QGIS Python for the SQLSerializable-based instantiation of
``EngineTestEventsDatabase`` and ``AreaSourcesDatabase``, because
``SQLSerializable`` imports ``sql_interface`` which pulls in
``qgis.utils.spatialite_connect``. Run under OSGeo4W shell:

    python-qgis-ltr -m pytest tests/test_phase2_engine_test_event_plugin.py -v
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
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

    HAS_QGIS = True
except Exception:  # pragma: no cover
    HAS_QGIS = False


pytestmark = pytest.mark.skipif(
    not HAS_QGIS, reason="QGIS Python not importable in this environment"
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset the Singleton caches on every Database and Store class this
    test file touches, before AND after every test. Without this, a
    Database or Store created by an earlier test (in this file or the
    wider suite) is returned by the Singleton metaclass and still points
    at a now-deleted temp path, causing INSERT/SELECT against the current
    test's tempfile to see an empty database.
    """
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
# Section 1: EngineTestEvent dataclass
# ═══════════════════════════════════════════════════════════════════════


def _row(**kwargs):
    """Return a fully-populated event row dict, with sensible defaults so
    each test can override just the fields it cares about."""
    base = {
        "event_id": 1,
        "source_id": "N1",
        "test_id": "T-001",
        "start_datetime": "2024-12-01T09:00:00",
        "end_datetime": "2024-12-01T09:30:00",
        "aircraft_type": "C56X",
        "engine_uid": "B602",
        "engine_count": 2,
        "t_TX_s": 300,
        "t_AP_s": 0,
        "t_CL_s": 900,
        "t_TO_s": 0,
        "thrust_mode": "snap",
        "instudy": "1",
    }
    base.update(kwargs)
    return base


def test_event_field_parsing():
    e = EngineTestEvent(_row())
    assert e.getEventId() == 1
    assert e.getSourceId() == "N1"
    assert e.getTestId() == "T-001"
    assert e.getAircraftType() == "C56X"
    assert e.getEngineUid() == "B602"
    assert e.getEngineCount() == 2
    assert e.getThrustMode() == "snap"
    assert e.isInStudy() is True
    assert e.getStartDateTime() == datetime(2024, 12, 1, 9, 0, 0)
    assert e.getEndDateTime() == datetime(2024, 12, 1, 9, 30, 0)


def test_event_duration_and_running_seconds():
    e = EngineTestEvent(_row())  # 30-min window, 300+900 = 1200s running
    assert e.getDurationSeconds() == 30 * 60
    assert e.getRunningSeconds() == 300 + 900


def test_event_mode_times_dict():
    e = EngineTestEvent(_row(t_TX_s=100, t_AP_s=200, t_CL_s=300, t_TO_s=400))
    assert e.getModeTimes() == {"TX": 100, "AP": 200, "CL": 300, "TO": 400}


def test_event_null_engine_uid_and_count():
    """engine_uid=None and engine_count=None are represented as Python
    None on the dataclass, not empty string or 0."""
    e = EngineTestEvent(_row(engine_uid=None, engine_count=None))
    assert e.getEngineUid() is None
    assert e.getEngineCount() is None


def test_event_empty_string_engine_uid_treated_as_none():
    """Empty-string engine_uid is treated the same as NULL."""
    e = EngineTestEvent(_row(engine_uid=""))
    assert e.getEngineUid() is None


def test_event_instudy_zero_string():
    e = EngineTestEvent(_row(instudy="0"))
    assert e.isInStudy() is False


def test_event_thrust_mode_default_snap_on_empty():
    """Empty / missing thrust_mode falls back to 'snap'."""
    row = _row()
    row.pop("thrust_mode")
    e = EngineTestEvent(row)
    assert e.getThrustMode() == "snap"


# ── Consistency warnings ────────────────────────────────────────────────


def test_event_consistency_clean_row_no_warnings():
    e = EngineTestEvent(_row())
    assert e.getConsistencyWarnings() == []


def test_event_consistency_zero_running_flagged():
    e = EngineTestEvent(_row(t_TX_s=0, t_AP_s=0, t_CL_s=0, t_TO_s=0))
    assert "zero_running" in e.getConsistencyWarnings()


def test_event_consistency_negative_time_flagged():
    e = EngineTestEvent(_row(t_TX_s=-100))
    assert "negative_running" in e.getConsistencyWarnings()


def test_event_consistency_running_exceeds_window_flagged():
    """A 30-min window (1800s) with 2000s of running (200s > 60s tolerance)
    fires the warning."""
    e = EngineTestEvent(
        _row(
            start_datetime="2024-12-01T09:00:00",
            end_datetime="2024-12-01T09:30:00",
            t_TX_s=2000,
            t_AP_s=0,
            t_CL_s=0,
            t_TO_s=0,
        )
    )
    assert "running_exceeds_window" in e.getConsistencyWarnings()


def test_event_consistency_running_within_tolerance_no_warning():
    """Sub-tolerance overshoot (running - duration <= 60s) does not fire
    the warning. Justifies the tolerance value against the RTHA-style
    logbook precision."""
    e = EngineTestEvent(
        _row(
            start_datetime="2024-12-01T09:00:00",
            end_datetime="2024-12-01T09:30:00",  # 1800s window
            # Override all four mode times so the total running is what
            # the assertion expects. Leaving the _row() defaults in place
            # would add t_CL_s=900 on top of t_TX_s=1850 for a total of
            # 2750s (a 950s overshoot, well above the 60s tolerance).
            t_TX_s=1850,  # +50s over the window, within 60s tolerance
            t_AP_s=0,
            t_CL_s=0,
            t_TO_s=0,
        )
    )
    assert "running_exceeds_window" not in e.getConsistencyWarnings()


def test_event_consistency_end_before_start_flagged():
    e = EngineTestEvent(
        _row(
            start_datetime="2024-12-01T10:00:00",
            end_datetime="2024-12-01T09:30:00",
        )
    )
    assert "end_before_start" in e.getConsistencyWarnings()


def test_event_consistency_missing_aircraft_type_flagged():
    e = EngineTestEvent(_row(aircraft_type=""))
    assert "missing_aircraft_type" in e.getConsistencyWarnings()


def test_event_consistency_unparseable_datetime_flagged():
    e = EngineTestEvent(_row(start_datetime="not-a-date"))
    warnings = e.getConsistencyWarnings()
    assert "missing_start_datetime" in warnings


# ── Resolvers with mocks ────────────────────────────────────────────────


def test_event_get_aircraft_returns_from_store():
    class FakeStore:
        def getObject(self, key):
            return f"aircraft-for-{key}"

    e = EngineTestEvent(_row(aircraft_type="C56X"))
    assert e.getAircraft(FakeStore()) == "aircraft-for-C56X"


def test_event_get_aircraft_none_on_empty_type():
    class FakeStore:
        def getObject(self, key):  # pragma: no cover
            return "should-not-be-called"

    e = EngineTestEvent(_row(aircraft_type=""))
    assert e.getAircraft(FakeStore()) is None


def test_event_get_engine_uid_wins_over_aircraft_default():
    """When engine_uid is set on the row, the row's UID is looked up in
    the engine store; the aircraft's default engine is not consulted."""

    class FakeEngineStore:
        def getObject(self, key):
            return f"engine-{key}"

    class FakeAircraft:
        def getDefaultEngine(self):  # pragma: no cover
            return "aircraft-default-engine"

    e = EngineTestEvent(_row(engine_uid="B602"))
    assert e.getEngine(FakeEngineStore(), FakeAircraft()) == "engine-B602"


def test_event_get_engine_falls_back_to_aircraft_default_when_uid_missing():
    class FakeEngineStore:
        def getObject(self, key):  # pragma: no cover
            return "should-not-be-called"

    class FakeAircraft:
        def getDefaultEngine(self):
            return "aircraft-default-engine"

    e = EngineTestEvent(_row(engine_uid=None))
    assert e.getEngine(FakeEngineStore(), FakeAircraft()) == "aircraft-default-engine"


def test_event_get_engine_none_when_both_paths_unavailable():
    e = EngineTestEvent(_row(engine_uid=None))
    assert e.getEngine(engine_store=None, aircraft=None) is None


def test_event_resolve_engine_count_row_wins():
    class FakeAircraft:
        engine_count = 4

    e = EngineTestEvent(_row(engine_count=2))
    assert e.resolveEngineCount(FakeAircraft()) == 2


def test_event_resolve_engine_count_falls_back_to_aircraft_attribute():
    class FakeAircraft:
        engine_count = 4

    e = EngineTestEvent(_row(engine_count=None))
    assert e.resolveEngineCount(FakeAircraft()) == 4


def test_event_resolve_engine_count_falls_back_to_aircraft_method():
    class FakeAircraft:
        def getEngineCount(self):
            return 3

    e = EngineTestEvent(_row(engine_count=None))
    assert e.resolveEngineCount(FakeAircraft()) == 3


def test_event_resolve_engine_count_none_when_all_paths_unavailable():
    e = EngineTestEvent(_row(engine_count=None))
    assert e.resolveEngineCount(aircraft=None) is None


# ═══════════════════════════════════════════════════════════════════════
# Section 2: EngineTestEventsStore
# ═══════════════════════════════════════════════════════════════════════


def _seed_events_db(db_path: str, rows: list[dict]) -> None:
    """Directly insert engine_test_events rows into a scratch DB, bypassing
    the SQLSerializable layer. Used to construct fixtures for the store
    tests. The Store class picks the rows up on load."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS engine_test_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            test_id TEXT,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            aircraft_type TEXT NOT NULL,
            engine_uid TEXT,
            engine_count INTEGER,
            t_TX_s INTEGER NOT NULL DEFAULT 0,
            t_AP_s INTEGER NOT NULL DEFAULT 0,
            t_CL_s INTEGER NOT NULL DEFAULT 0,
            t_TO_s INTEGER NOT NULL DEFAULT 0,
            thrust_mode TEXT NOT NULL DEFAULT 'snap',
            instudy TEXT NOT NULL DEFAULT '1'
        )
        """
    )
    for r in rows:
        cols = ", ".join(r.keys())
        ph = ", ".join(["?"] * len(r))
        conn.execute(
            f"INSERT INTO engine_test_events ({cols}) VALUES ({ph})",
            list(r.values()),
        )
    conn.commit()
    conn.close()


def test_store_loads_events_from_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        _seed_events_db(
            tmp,
            [
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T09:00:00",
                    "end_datetime": "2024-12-01T09:30:00",
                    "aircraft_type": "C56X",
                },
                {
                    "source_id": "COMP",
                    "start_datetime": "2024-12-01T14:00:00",
                    "end_datetime": "2024-12-01T14:20:00",
                    "aircraft_type": "B738",
                },
            ],
        )
        store = EngineTestEventsStore(tmp)
        events = list(store._objects.values())
        assert len(events) == 2
        assert {e.getSourceId() for e in events} == {"N1", "COMP"}
    finally:
        os.unlink(tmp)


def test_store_get_events_by_source_id():
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        _seed_events_db(
            tmp,
            [
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T09:00:00",
                    "end_datetime": "2024-12-01T09:30:00",
                    "aircraft_type": "C56X",
                },
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-02T10:00:00",
                    "end_datetime": "2024-12-02T10:15:00",
                    "aircraft_type": "C56X",
                },
                {
                    "source_id": "COMP",
                    "start_datetime": "2024-12-01T14:00:00",
                    "end_datetime": "2024-12-01T14:20:00",
                    "aircraft_type": "B738",
                },
            ],
        )
        store = EngineTestEventsStore(tmp)
        n1_events = store.getEventsBySourceId("N1")
        assert len(n1_events) == 2
        assert all(e.getSourceId() == "N1" for e in n1_events)

        comp_events = store.getEventsBySourceId("COMP")
        assert len(comp_events) == 1

        assert store.getEventsBySourceId("UNKNOWN") == []
        assert store.getEventsBySourceId("") == []
    finally:
        os.unlink(tmp)


def test_store_get_events_in_period_overlap_semantics():
    """Interval-overlap check across all five topology cases."""
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        _seed_events_db(
            tmp,
            [
                # 0: entirely before window
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T08:00:00",
                    "end_datetime": "2024-12-01T08:30:00",
                    "aircraft_type": "C56X",
                },
                # 1: ending exactly at window start (touches; does NOT overlap)
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T08:30:00",
                    "end_datetime": "2024-12-01T09:00:00",
                    "aircraft_type": "C56X",
                },
                # 2: spanning window start
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T08:45:00",
                    "end_datetime": "2024-12-01T09:15:00",
                    "aircraft_type": "C56X",
                },
                # 3: entirely within window
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T09:15:00",
                    "end_datetime": "2024-12-01T09:45:00",
                    "aircraft_type": "C56X",
                },
                # 4: spanning window end
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T09:45:00",
                    "end_datetime": "2024-12-01T10:15:00",
                    "aircraft_type": "C56X",
                },
                # 5: starting exactly at window end (touches; does NOT overlap)
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T10:00:00",
                    "end_datetime": "2024-12-01T10:30:00",
                    "aircraft_type": "C56X",
                },
                # 6: entirely after window
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T11:00:00",
                    "end_datetime": "2024-12-01T11:30:00",
                    "aircraft_type": "C56X",
                },
            ],
        )
        store = EngineTestEventsStore(tmp)
        period_start = datetime(2024, 12, 1, 9, 0, 0)
        period_end = datetime(2024, 12, 1, 10, 0, 0)
        overlapping = store.getEventsInPeriod(period_start, period_end)

        # Expected: 2 (spanning start), 3 (in window), 4 (spanning end).
        # NOT expected: 0 (before), 1 (touches start), 5 (touches end), 6 (after).
        assert len(overlapping) == 3
        starts = sorted(e.getStartDateTime() for e in overlapping)
        assert starts == [
            datetime(2024, 12, 1, 8, 45),
            datetime(2024, 12, 1, 9, 15),
            datetime(2024, 12, 1, 9, 45),
        ]
    finally:
        os.unlink(tmp)


def test_store_get_events_in_period_none_period_returns_empty():
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        _seed_events_db(tmp, [])
        store = EngineTestEventsStore(tmp)
        assert store.getEventsInPeriod(None, None) == []
    finally:
        os.unlink(tmp)


def test_store_skips_events_with_unparseable_datetime_in_period_filter():
    """Events whose start / end failed to parse are not returned by the
    period filter (they surface via consistency warnings instead)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        _seed_events_db(
            tmp,
            [
                {
                    "source_id": "N1",
                    "start_datetime": "garbage",
                    "end_datetime": "also-garbage",
                    "aircraft_type": "C56X",
                },
                {
                    "source_id": "N1",
                    "start_datetime": "2024-12-01T09:15:00",
                    "end_datetime": "2024-12-01T09:45:00",
                    "aircraft_type": "C56X",
                },
            ],
        )
        store = EngineTestEventsStore(tmp)
        period_start = datetime(2024, 12, 1, 9, 0, 0)
        period_end = datetime(2024, 12, 1, 10, 0, 0)
        overlapping = store.getEventsInPeriod(period_start, period_end)
        assert len(overlapping) == 1
        assert overlapping[0].getStartDateTime() == datetime(2024, 12, 1, 9, 15)
    finally:
        os.unlink(tmp)


def test_store_tolerates_missing_table():
    """A DB with no engine_test_events table: store instantiates empty,
    no exception."""
    tmp = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    try:
        # Fresh empty DB, no CREATE TABLE
        store = EngineTestEventsStore(tmp)
        assert store.getEventsBySourceId("N1") == []
        assert (
            store.getEventsInPeriod(datetime(2024, 1, 1), datetime(2024, 12, 31)) == []
        )
    finally:
        os.unlink(tmp)


# ═══════════════════════════════════════════════════════════════════════
# Section 3: AreaSource.getEngineTestEvents accessor
# ═══════════════════════════════════════════════════════════════════════


def test_area_source_get_engine_test_events_returns_empty_for_normal_source():
    """A normal area source (is_test_site='0') returns [] even if there
    are events matching its source_id in the store."""

    class FakeStore:
        def getEventsBySourceId(self, source_id):  # pragma: no cover
            return ["should-not-be-returned"]

    src = AreaSources({"source_id": "A1", "is_test_site": "0"})
    assert src.getEngineTestEvents(FakeStore()) == []


def test_area_source_get_engine_test_events_returns_store_result_for_test_site():
    class FakeStore:
        def getEventsBySourceId(self, source_id):
            return [f"event-{source_id}-1", f"event-{source_id}-2"]

    src = AreaSources({"source_id": "N1", "is_test_site": "1"})
    result = src.getEngineTestEvents(FakeStore())
    assert result == ["event-N1-1", "event-N1-2"]


def test_area_source_get_engine_test_events_none_store_returns_empty():
    src = AreaSources({"source_id": "N1", "is_test_site": "1"})
    assert src.getEngineTestEvents(None) == []
