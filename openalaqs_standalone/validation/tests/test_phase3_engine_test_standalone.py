"""Phase 3 standalone tests: extract_engine_test_events + compute_engine_test.

QGIS-free. Uses raw sqlite3 fixtures for the extract tests and native
Python dicts for the compute tests.
"""

from __future__ import annotations

import io
import os
import sqlite3
import tempfile
from contextlib import redirect_stdout
from datetime import datetime

from openalaqs_standalone.compute_engine_test import (
    _period_window_fraction,
    compute_engine_test_for_period,
)
from openalaqs_standalone.extract_engine_test_events import (
    extract_engine_test_events,
)

# ═══════════════════════════════════════════════════════════════════════
# Fixtures: scratch SpatiaLite-free DBs
# ═══════════════════════════════════════════════════════════════════════


def _make_db_with_both_tables(area_rows, event_rows, include_is_test_site=True):
    """Create a scratch DB with shapes_area_sources + engine_test_events."""
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    conn = sqlite3.connect(path)

    if include_is_test_site:
        area_ddl = """
            CREATE TABLE shapes_area_sources (
                oid INTEGER PRIMARY KEY,
                source_id TEXT,
                height DECIMAL,
                instudy TEXT DEFAULT '1',
                is_test_site TEXT DEFAULT '0',
                geometry BLOB
            )
        """
    else:
        area_ddl = """
            CREATE TABLE shapes_area_sources (
                oid INTEGER PRIMARY KEY,
                source_id TEXT,
                height DECIMAL,
                instudy TEXT DEFAULT '1',
                geometry BLOB
            )
        """
    conn.execute(area_ddl)
    for r in area_rows:
        cols = ", ".join(r.keys())
        ph = ", ".join(["?"] * len(r))
        conn.execute(
            f"INSERT INTO shapes_area_sources ({cols}) VALUES ({ph})",
            list(r.values()),
        )

    conn.execute(
        """
        CREATE TABLE engine_test_events (
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
    for r in event_rows:
        cols = ", ".join(r.keys())
        ph = ", ".join(["?"] * len(r))
        conn.execute(
            f"INSERT INTO engine_test_events ({cols}) VALUES ({ph})",
            list(r.values()),
        )
    conn.commit()
    return path, conn


# ═══════════════════════════════════════════════════════════════════════
# Section 1: extract_engine_test_events
# ═══════════════════════════════════════════════════════════════════════


def test_extract_returns_events_for_test_site_parents():
    path, conn = _make_db_with_both_tables(
        area_rows=[
            {"source_id": "N1", "height": 3.0, "instudy": "1", "is_test_site": "1"},
            {"source_id": "A1", "height": 0.0, "instudy": "1", "is_test_site": "0"},
        ],
        event_rows=[
            {
                "source_id": "N1",
                "start_datetime": "2024-12-01T09:00:00",
                "end_datetime": "2024-12-01T09:30:00",
                "aircraft_type": "C56X",
            },
            {
                "source_id": "A1",
                "start_datetime": "2024-12-01T09:00:00",
                "end_datetime": "2024-12-01T09:30:00",
                "aircraft_type": "C56X",
            },
        ],
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            events = extract_engine_test_events(conn)
        conn.close()
        # A1 event skipped (parent not test site); only N1 event kept.
        assert len(events) == 1
        assert events[0]["source_id"] == "N1"
        assert events[0]["source_height_m"] == 3.0
        assert "1 event(s) skipped: parent source not flagged" in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_skips_orphan_events():
    path, conn = _make_db_with_both_tables(
        area_rows=[
            {"source_id": "N1", "height": 3.0, "instudy": "1", "is_test_site": "1"},
        ],
        event_rows=[
            {
                "source_id": "N1",
                "start_datetime": "2024-12-01T09:00:00",
                "end_datetime": "2024-12-01T09:30:00",
                "aircraft_type": "C56X",
            },
            {
                "source_id": "GHOST",
                "start_datetime": "2024-12-01T09:00:00",
                "end_datetime": "2024-12-01T09:30:00",
                "aircraft_type": "C56X",
            },
        ],
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            events = extract_engine_test_events(conn)
        conn.close()
        assert len(events) == 1
        assert "1 event(s) skipped: source_id not found" in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_skips_events_marked_out_of_study():
    path, conn = _make_db_with_both_tables(
        area_rows=[
            {"source_id": "N1", "height": 3.0, "instudy": "1", "is_test_site": "1"},
        ],
        event_rows=[
            {
                "source_id": "N1",
                "start_datetime": "2024-12-01T09:00:00",
                "end_datetime": "2024-12-01T09:30:00",
                "aircraft_type": "C56X",
                "instudy": "0",
            },
        ],
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            events = extract_engine_test_events(conn)
        conn.close()
        assert len(events) == 0
        assert "1 event(s) skipped: event out of study" in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_returns_empty_for_missing_engine_test_events_table():
    path = tempfile.NamedTemporaryFile(suffix=".alaqs", delete=False).name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE shapes_area_sources (source_id TEXT, is_test_site TEXT)")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            events = extract_engine_test_events(conn)
        conn.close()
        assert events == []
        assert "engine_test_events table absent" in buf.getvalue()
    finally:
        os.unlink(path)


def test_extract_returns_empty_for_pre_v1b_area_source_schema():
    """A DB where shapes_area_sources lacks is_test_site (pre-v1b)."""
    path, conn = _make_db_with_both_tables(
        area_rows=[{"source_id": "N1", "height": 0.0, "instudy": "1"}],
        event_rows=[],
        include_is_test_site=False,
    )
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            events = extract_engine_test_events(conn)
        conn.close()
        assert events == []
        assert "lacks is_test_site column" in buf.getvalue()
    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
# Section 2: _period_window_fraction
# ═══════════════════════════════════════════════════════════════════════


def _dt(day, hour, minute=0):
    return datetime(2024, 12, day, hour, minute)


def test_standalone_fraction_matches_plugin_math():
    """Sanity: standalone fraction implementation matches the plugin's
    for the same seven topology cases."""
    p_start, p_end = _dt(1, 9), _dt(1, 10)

    # Entirely inside
    assert _period_window_fraction(_dt(1, 9, 15), _dt(1, 9, 45), p_start, p_end) == 1.0
    # Straddles start
    assert _period_window_fraction(_dt(1, 8, 45), _dt(1, 9, 15), p_start, p_end) == 0.5
    # Straddles end
    assert _period_window_fraction(_dt(1, 9, 45), _dt(1, 10, 15), p_start, p_end) == 0.5
    # Outside
    assert _period_window_fraction(_dt(1, 7), _dt(1, 8), p_start, p_end) == 0.0
    # Touching start
    assert _period_window_fraction(_dt(1, 8), _dt(1, 9), p_start, p_end) == 0.0
    # Missing dt
    assert _period_window_fraction(None, _dt(1, 9, 15), p_start, p_end) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Section 3: compute_engine_test_for_period
# ═══════════════════════════════════════════════════════════════════════


def _ei(fuel_kg_sec, **kwargs):
    """Build an EI-row dict with fuel_flow and named pollutant EIs."""
    d = {"fuel_kg_sec": fuel_kg_sec}
    for k, v in kwargs.items():
        d[f"{k}_ei_g_kg_fuel"] = v
    return d


def _event_dict(**overrides):
    base = {
        "event_id": 1,
        "source_id": "N1",
        "start_datetime": "2024-12-01T09:00:00",
        "end_datetime": "2024-12-01T09:30:00",
        "aircraft_type": "C56X",
        "engine_uid": "B602",
        "engine_count": 2,
        "t_TX_s": 0,
        "t_AP_s": 0,
        "t_CL_s": 0,
        "t_TO_s": 0,
        "thrust_mode": "snap",
        "instudy": "1",
    }
    base.update(overrides)
    return base


def test_compute_matches_hand_calculation_full_period():
    """t_CL=900s, engine_count=2, FF=0.5 kg/s, NOx EI=20 g/kg, fraction=1
    → fuel = 900*2*1 * 0.5 = 900 kg; NOx = 20 * 900 = 18000 g."""
    ei_lookup = {
        ("B602", "CL"): _ei(fuel_kg_sec=0.5, nox=20.0),
    }
    aircraft_lookup = {"C56X": {"engine_count": 2, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=900)]

    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert set(totals.keys()) == {"N1"}
    assert abs(totals["N1"]["fuel"] - 900.0) < 1e-9
    assert abs(totals["N1"]["nox"] - 18000.0) < 1e-6


def test_compute_period_window_fraction_applied():
    """Event 08:45-09:15 (30min) with t_CL=1800s, period 09:00-10:00.
    fraction=0.5 → t_effective=1800*2*0.5=1800 → fuel=1800*1.0=1800 kg.
    """
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 2, "engine_uid": "B602"}}
    events = [
        _event_dict(
            t_CL_s=1800,
            start_datetime="2024-12-01T08:45:00",
            end_datetime="2024-12-01T09:15:00",
        )
    ]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert abs(totals["N1"]["fuel"] - 1800.0) < 1e-9


def test_compute_multiple_events_same_source_summed():
    """Two events on N1 summed: e1 t_TX=600s FF=1.0 → 600 kg fuel;
    e2 t_TX=300s → 300 kg fuel. Total 900 kg."""
    ei_lookup = {("B602", "TX"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [
        _event_dict(event_id=1, t_TX_s=600, engine_count=1),
        _event_dict(
            event_id=2,
            t_TX_s=300,
            engine_count=1,
            start_datetime="2024-12-01T09:45:00",
            end_datetime="2024-12-01T09:55:00",
        ),
    ]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert abs(totals["N1"]["fuel"] - 900.0) < 1e-9


def test_compute_multiple_sources_kept_separate():
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [
        _event_dict(source_id="N1", event_id=1, t_CL_s=100, engine_count=1),
        _event_dict(source_id="COMP", event_id=2, t_CL_s=200, engine_count=1),
    ]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert set(totals.keys()) == {"N1", "COMP"}
    assert abs(totals["N1"]["fuel"] - 100.0) < 1e-9
    assert abs(totals["COMP"]["fuel"] - 200.0) < 1e-9


def test_compute_zero_running_source_omitted():
    ei_lookup = {("B602", "TX"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_TX_s=0)]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert totals == {}


def test_compute_out_of_study_event_ignored():
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, instudy="0")]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert totals == {}


def test_compute_missing_ei_flagged_and_skipped():
    """No EI row for engine * mode → no contribution, diagnostic emitted."""
    ei_lookup = {}  # empty
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=900, engine_count=1)]
    diagnostics = []
    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
    )
    assert totals == {}
    assert any("no EI for engine" in msg for msg in diagnostics)


def test_compute_unresolvable_engine_count_flagged():
    """engine_count=None on event AND aircraft → skip with diagnostic."""
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_uid": "B602"}}  # no engine_count
    events = [_event_dict(t_CL_s=900, engine_count=None)]
    diagnostics = []
    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
    )
    assert totals == {}
    assert any("engine count unresolved" in msg for msg in diagnostics)


def test_compute_meem_produces_same_result_as_snap():
    """MEEM for engine-test events is numerically identical to snap
    because engine-test modes are always at ICAO EEDB anchor thrust
    settings, where MEEM V1's interpolation trivially returns the
    anchor value. See compute_engine_test.py module docstring."""
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0, nox=20.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}

    snap_events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="snap")]
    meem_events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="meem")]

    snap_totals = compute_engine_test_for_period(
        snap_events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    meem_totals = compute_engine_test_for_period(
        meem_events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    # Byte-identical results.
    assert snap_totals == meem_totals


def test_compute_meem_does_not_emit_diagnostic():
    """No diagnostic should be emitted for the meem thrust mode. The
    'not implemented' diagnostic was misleading (meem = snap at anchor
    thrust, so nothing is unimplemented in a way that changes results)
    and was removed in Phase 5a."""
    ei_lookup = {("B602", "CL"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="meem")]
    diagnostics = []
    compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
    )
    # The old diagnostic string must be absent.
    assert not any("not implemented" in msg for msg in diagnostics)
    # And no meem-specific diagnostic should be emitted at all.
    assert not any("meem" in msg.lower() for msg in diagnostics)


def test_compute_engine_uid_row_takes_precedence():
    """Row's engine_uid wins over aircraft default."""
    ei_lookup = {
        ("EXPLICIT_UID", "TX"): _ei(fuel_kg_sec=2.0),
        ("DEFAULT_UID", "TX"): _ei(fuel_kg_sec=1.0),
    }
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "DEFAULT_UID"}}
    events = [_event_dict(t_TX_s=100, engine_count=1, engine_uid="EXPLICIT_UID")]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    # Explicit UID used → fuel = 100*1*2 = 200 kg
    assert abs(totals["N1"]["fuel"] - 200.0) < 1e-9


def test_compute_engine_uid_falls_back_to_aircraft():
    ei_lookup = {("DEFAULT_UID", "TX"): _ei(fuel_kg_sec=1.0)}
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "DEFAULT_UID"}}
    events = [_event_dict(t_TX_s=100, engine_count=1, engine_uid=None)]
    totals = compute_engine_test_for_period(
        events, _dt(1, 9), _dt(1, 10), ei_lookup, aircraft_lookup
    )
    assert abs(totals["N1"]["fuel"] - 100.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════════
# Section 4: Phase 5b — BFFM2 thrust mode
# ═══════════════════════════════════════════════════════════════════════


def _build_engine_ei_lookup_all_modes(uid: str, nox_ei=20.0):
    """Build a 4-mode ei_lookup for one engine with plausible FFs and
    per-mode EIs, so BFFM2's icao_eedb builder can complete."""
    return {
        (uid, "TX"): _ei(fuel_kg_sec=0.05, nox=nox_ei, co=10.0, hc=5.0),
        (uid, "AP"): _ei(fuel_kg_sec=0.20, nox=nox_ei, co=1.0, hc=0.1),
        (uid, "CL"): _ei(fuel_kg_sec=0.60, nox=nox_ei, co=0.5, hc=0.05),
        (uid, "TO"): _ei(fuel_kg_sec=0.80, nox=nox_ei, co=0.5, hc=0.05),
    }


def _prep_bffm2_conn_with_meteo(t_K=298.15, p_Pa=100000.0, rh=0.7):
    """Create a scratch SQLite connection with a populated tbl_InvMeteo."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE tbl_InvMeteo (
            DateTime TEXT,
            Temperature REAL,
            SeaLevelPressure REAL,
            RelativeHumidity REAL,
            Humidity REAL
        )"""
    )
    conn.execute(
        "INSERT INTO tbl_InvMeteo VALUES (?, ?, ?, ?, ?)",
        ("2024-12-01 09:00:00", t_K, p_Pa, rh, 0.008),
    )
    conn.commit()
    return conn


def test_bffm2_without_conn_falls_back_to_snap_with_diagnostic():
    """bffm2 events without conn → warn once, treat as snap."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="bffm2")]
    diagnostics: list = []

    snap_totals = compute_engine_test_for_period(
        [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="snap")],
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
    )
    bffm2_totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
        conn=None,
    )

    # Same numerical output as snap (fell back).
    assert snap_totals == bffm2_totals
    # Diagnostic emitted once.
    n = sum(1 for msg in diagnostics if "conn=None" in msg)
    assert n == 1


def test_bffm2_no_conn_warning_logged_only_once():
    """Multiple bffm2 events with conn=None → warning fires only once."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [
        _event_dict(event_id=1, t_CL_s=100, engine_count=1, thrust_mode="bffm2"),
        _event_dict(
            event_id=2,
            t_CL_s=100,
            engine_count=1,
            thrust_mode="bffm2",
            start_datetime="2024-12-01T09:45:00",
            end_datetime="2024-12-01T09:55:00",
        ),
    ]
    diagnostics: list = []
    compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
        conn=None,
    )
    n = sum(1 for msg in diagnostics if "conn=None" in msg)
    assert n == 1


def test_bffm2_incomplete_engine_ei_falls_back_to_snap():
    """Engine missing one mode in ei_lookup → BFFM2 requires all 4 for
    the icao_eedb; falls back to snap with a per-event diagnostic."""
    # Only 3 modes present.
    ei_lookup = {
        ("B602", "TX"): _ei(fuel_kg_sec=0.05, nox=20.0, co=10.0, hc=5.0),
        ("B602", "AP"): _ei(fuel_kg_sec=0.20, nox=20.0, co=1.0, hc=0.1),
        ("B602", "CL"): _ei(fuel_kg_sec=0.60, nox=20.0, co=0.5, hc=0.05),
        # "TO" missing
    }
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="bffm2")]
    conn = _prep_bffm2_conn_with_meteo()
    diagnostics: list = []

    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
        conn=conn,
    )
    # Fell back to snap. CL fuel = 100 * 1 * 1.0 * 0.6 = 60 kg.
    assert abs(totals["N1"]["fuel"] - 60.0) < 1e-9
    # Diagnostic emitted.
    assert any("complete 4-mode" in msg for msg in diagnostics)


def test_bffm2_missing_tbl_invmeteo_falls_back_to_isa_with_diagnostic():
    """Conn provided but tbl_InvMeteo table doesn't exist → ISA
    fallback with diagnostic."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="bffm2")]
    conn = sqlite3.connect(":memory:")  # bare, no tbl_InvMeteo
    diagnostics: list = []

    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        diagnostics=diagnostics,
        conn=conn,
    )
    # BFFM2 with ISA ambient still produces numbers (not zero, not
    # snap-equivalent — BFFM2 gas correction with humidity 0.6 differs
    # from raw EEDB).
    assert totals["N1"]["fuel"] > 0
    # Diagnostic emitted.
    assert any("tbl_InvMeteo not in the DB" in msg for msg in diagnostics)


def test_bffm2_populated_meteo_produces_different_numbers_than_snap():
    """The whole point of BFFM2: different ambient → different NOx.
    High RH should REDUCE NOx compared to low RH (Boeing formula
    humidity correction dominates)."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="bffm2")]

    # High RH ambient
    conn_high = _prep_bffm2_conn_with_meteo(rh=0.95)
    totals_high = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        conn=conn_high,
    )
    # Low RH ambient
    conn_low = _prep_bffm2_conn_with_meteo(rh=0.1)
    totals_low = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        conn=conn_low,
    )

    # Different NOx between high and low RH.
    assert abs(totals_high["N1"]["nox"] - totals_low["N1"]["nox"]) > 1.0


def test_bffm2_uses_event_midpoint_for_meteo():
    """Two events at same period but different midpoints → different
    meteo lookups. Given a tbl_InvMeteo with time-varying data, results
    should differ."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE tbl_InvMeteo (
            DateTime TEXT, Temperature REAL, SeaLevelPressure REAL,
            RelativeHumidity REAL, Humidity REAL
        )"""
    )
    # Two meteo rows: 08:00 (cold, dry) and 09:20 (warm, humid).
    conn.execute(
        "INSERT INTO tbl_InvMeteo VALUES (?, ?, ?, ?, ?)",
        ("2024-12-01 08:00:00", 278.15, 101325.0, 0.2, 0.001),
    )
    conn.execute(
        "INSERT INTO tbl_InvMeteo VALUES (?, ?, ?, ?, ?)",
        ("2024-12-01 09:20:00", 303.15, 100000.0, 0.9, 0.020),
    )
    conn.commit()

    # Event A: 09:00-09:10 → midpoint 09:05 → uses 08:00 row (cold)
    ev_a = _event_dict(
        event_id=1,
        t_CL_s=60,
        engine_count=1,
        thrust_mode="bffm2",
        start_datetime="2024-12-01T09:00:00",
        end_datetime="2024-12-01T09:10:00",
    )
    # Event B: 09:30-09:40 → midpoint 09:35 → uses 09:20 row (warm)
    ev_b = _event_dict(
        event_id=2,
        t_CL_s=60,
        engine_count=1,
        thrust_mode="bffm2",
        source_id="N2",
        start_datetime="2024-12-01T09:30:00",
        end_datetime="2024-12-01T09:40:00",
    )

    totals = compute_engine_test_for_period(
        [ev_a, ev_b],
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        conn=conn,
    )
    # Different ambient → different NOx.
    assert abs(totals["N1"]["nox"] - totals["N2"]["nox"]) > 1.0


def test_bffm2_pm_and_sox_passthrough():
    """PM10 and SOx should use base EEDB values (Design A: BFFM2 gas + EEDB PM/SOx)."""
    # Give the engine distinct PM/SOx values so we can identify them
    # in the output.
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    for mode in ("TX", "AP", "CL", "TO"):
        ei_lookup[("B602", mode)]["pm10_ei_g_kg_fuel"] = 0.5
        ei_lookup[("B602", mode)]["sox_ei_g_kg_fuel"] = 1.0
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="bffm2")]
    conn = _prep_bffm2_conn_with_meteo()

    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
        conn=conn,
    )
    # PM10 and SOx should be non-zero and proportional to fuel burn.
    # We can't assert exact values without computing ff_amb ourselves,
    # but we can check the ratio pm10/sox = 0.5/1.0 = 0.5.
    ratio = totals["N1"]["pm10"] / totals["N1"]["sox"]
    assert abs(ratio - 0.5) < 1e-6


def test_bffm2_backward_compat_signature_without_conn():
    """The function without conn keyword should still work (snap-only
    callers)."""
    ei_lookup = _build_engine_ei_lookup_all_modes("B602")
    aircraft_lookup = {"C56X": {"engine_count": 1, "engine_uid": "B602"}}
    events = [_event_dict(t_CL_s=100, engine_count=1, thrust_mode="snap")]
    # Old-style call (no conn kwarg).
    totals = compute_engine_test_for_period(
        events,
        _dt(1, 9),
        _dt(1, 10),
        ei_lookup,
        aircraft_lookup,
    )
    assert totals["N1"]["fuel"] == 60.0  # CL: 100*1*1.0 * 0.6 kg/s = 60 kg
