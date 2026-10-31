"""Engine tests (BFFM2): the meteo row nearest to the event midpoint.

The plugin's EngineTestSource looks up AmbientConditionStore.getNearestByTime
at the event midpoint. getNearestByTime mapped every row time to 0.0 (getDate()
returns seconds, not a datetime), so it always returned the last meteo row.
The standalone (compute_engine_test, movements.get_meteo_at with
period_row=False) took the latest row at or before the midpoint. Both now take
the row nearest to the midpoint, ties to the earlier row.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.interfaces.AmbientCondition import (  # noqa: E402
    AmbientCondition,
    AmbientConditionStore,
)
from openalaqs_standalone import movements as mv  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


@pytest.fixture(autouse=True)
def _fresh_store():
    # AmbientConditionStore is a Singleton (open_alaqs.core.tools.Singleton).
    saved = AmbientConditionStore.instance
    AmbientConditionStore.reset()
    try:
        yield
    finally:
        AmbientConditionStore.instance = saved


def _store(rows):
    store = AmbientConditionStore.__new__(AmbientConditionStore)
    from open_alaqs.core.interfaces.Store import Store

    Store.__init__(store)
    for i, (dt, t) in enumerate(rows):
        store.setObject(i, AmbientCondition({"DateTime": dt, "Temperature": t}))
    return store


@pytest.mark.parametrize(
    "midpoint,expected",
    [
        ("2025-01-01 09:05:00", 280.0),  # nearest is 09:00
        ("2025-01-01 09:40:00", 290.0),  # nearest is 10:00
        ("2025-01-01 09:30:00", 280.0),  # tie: the earlier row
        ("2025-01-01 07:00:00", 280.0),  # before the first row
        ("2025-01-01 13:00:00", 300.0),  # after the last row
    ],
)
def test_plugin_nearest_by_time(midpoint, expected):
    store = _store(
        [
            ("2025-01-01 09:00:00", 280.0),
            ("2025-01-01 10:00:00", 290.0),
            ("2025-01-01 11:00:00", 300.0),
        ]
    )
    ts = datetime.fromisoformat(midpoint).timestamp()
    assert store.getNearestByTime(ts).getTemperature() == expected


def test_plugin_and_standalone_pick_the_same_row(tmp_path):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    db = tmp_path / "training.alaqs"
    shutil.copy(FIXTURE, db)
    with sqlite3.connect(db) as conn:
        # varied temperatures, rows at hh:50 (METAR-like) and a gap
        conn.execute(
            "UPDATE tbl_InvMeteo SET "
            "Temperature = 260 + CAST(substr(DateTime, 12, 2) AS INTEGER), "
            "DateTime = substr(DateTime, 1, 14) || '50:00'"
        )
        conn.execute(
            "DELETE FROM tbl_InvMeteo WHERE DateTime BETWEEN "
            "'2025-12-01 10:00:00' AND '2025-12-01 13:59:59'"
        )
        conn.commit()
    with sqlite3.connect(db) as conn:
        # the plugin store built from the same rows (the DB-backed store
        # caches its database object across tests)
        store = _store(
            conn.execute("SELECT DateTime, Temperature FROM tbl_InvMeteo").fetchall()
        )
        for midpoint in (
            "2025-12-01 06:05:00",
            "2025-12-01 06:30:00",
            "2025-12-01 11:00:00",
            "2025-12-01 12:20:00",
            "2025-12-02 23:59:00",
        ):
            plugin = store.getNearestByTime(
                datetime.fromisoformat(midpoint).timestamp()
            ).getTemperature()
            standalone = mv.get_meteo_at(
                conn, midpoint, use_isa=False, period_row=False
            )["T_K"]
            assert standalone == pytest.approx(plugin), midpoint


def test_engine_test_exact_midpoint_tie_parity():
    """Event 10:00:00 to 11:00:01: the midpoint 10:30:00.5 is nearer to the
    11:00 row. The plugin looks up the exact midpoint; the standalone
    compute_engine_test must not truncate it to 10:30:00 (a tie, which
    goes to the 10:00 row)."""
    from openalaqs_standalone.compute_engine_test import (
        compute_engine_test_for_period,
    )

    rows = [
        ("2025-01-01 10:00:00", 278.15, 101325.0, 0.2, 0.001),
        ("2025-01-01 11:00:00", 303.15, 100000.0, 0.9, 0.020),
    ]
    start, end = datetime(2025, 1, 1, 10), datetime(2025, 1, 1, 11, 0, 1)
    midpoint = start + (end - start) / 2

    # The plugin's choice.
    store = _store([(r[0], r[1]) for r in rows])
    assert store.getNearestByTime(midpoint.timestamp()).getTemperature() == 303.15

    def conn_with(meteo_rows):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE tbl_InvMeteo (DateTime TEXT, Temperature REAL, "
            "SeaLevelPressure REAL, RelativeHumidity REAL, Humidity REAL)"
        )
        conn.executemany("INSERT INTO tbl_InvMeteo VALUES (?, ?, ?, ?, ?)", meteo_rows)
        return conn

    def ei(ff, nox):
        return {"fuel_kg_sec": ff, "nox_ei": nox, "co_ei": 1.0, "hc_ei": 0.1}

    ei_lookup = {
        ("B602", "TX"): ei(0.05, 5.0),
        ("B602", "AP"): ei(0.20, 10.0),
        ("B602", "CL"): ei(0.60, 20.0),
        ("B602", "TO"): ei(0.80, 25.0),
    }
    event = {
        "event_id": 1,
        "source_id": "N1",
        "start_datetime": start.isoformat(),
        "end_datetime": end.isoformat(),
        "aircraft_type": "C56X",
        "engine_uid": "B602",
        "engine_count": 1,
        "t_TX_s": 0,
        "t_AP_s": 0,
        "t_CL_s": 600,
        "t_TO_s": 0,
        "thrust_mode": "bffm2",
        "instudy": "1",
    }

    def nox(meteo_rows):
        totals = compute_engine_test_for_period(
            [event],
            start,
            start.replace(hour=12),
            ei_lookup,
            {"C56X": {"engine_count": 1, "engine_uid": "B602"}},
            conn=conn_with(meteo_rows),
        )
        return totals["N1"]["nox"]

    assert nox(rows) == pytest.approx(nox(rows[1:]))
    assert nox(rows) != pytest.approx(nox(rows[:1]))
