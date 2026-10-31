"""Standalone BFFM2 segment fallbacks are logged, once per movement.

The plugin warns when a segment falls back from BFFM2: one summary warning
per movement for ADS-B fuel flows above the plausibility ceiling, and a
warning for segments without power and fuel flow (bymode EI). The standalone
applied the same fallbacks silently. Numbers are not changed by the logging.
"""

import logging
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone.compute_movements import compute_all_movements

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"
ADSB_OID = 11  # CUSTOM profile with fuel_flow_kgm
NO_POWER_PROFILE = "JET-SMALL-D-1"
NO_POWER_OID = 2
LOGGER = "openalaqs_standalone.compute_aircraft"


@pytest.fixture
def study(tmp_path):
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    dst = tmp_path / "training.alaqs"
    shutil.copy(FIXTURE, dst)
    return dst


def _run(db, oids, method="bffm2_traj"):
    with sqlite3.connect(db) as conn:
        return compute_all_movements(conn, method=method, oids=oids)


def _messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


def test_adsb_ceiling_fallback_one_warning(study, caplog):
    with sqlite3.connect(study) as conn:
        profile = conn.execute(
            "SELECT profile_id FROM user_aircraft_movements WHERE oid = ?", (ADSB_OID,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE default_aircraft_profiles SET fuel_flow_kgm = 100.0 "
            "WHERE profile_id = ? AND fuel_flow_kgm > 0",
            (profile,),
        )
        conn.commit()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        _run(study, [ADSB_OID])
    msgs = [m for m in _messages(caplog) if "plausibility ceiling" in m]
    assert len(msgs) == 1, msgs
    assert msgs[0].startswith(f"BFFM2 id {ADSB_OID}:")


def test_no_power_fallback_one_warning_numbers_unchanged(study, caplog):
    with sqlite3.connect(study) as conn:
        conn.execute(
            "UPDATE default_aircraft_profiles SET power = NULL, fuel_flow_kgm = NULL "
            "WHERE profile_id = ?",
            (NO_POWER_PROFILE,),
        )
        conn.commit()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        res = _run(study, [NO_POWER_OID])
    msgs = [m for m in _messages(caplog) if "no engine thrust or fuel flow" in m]
    assert len(msgs) == 1, msgs
    assert msgs[0].startswith(f"BFFM2 id {NO_POWER_OID}:")
    assert res[NO_POWER_OID]["total_em_kg"]["nox"] > 0.0


def test_no_warning_for_regular_movement(study, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        _run(study, [1])
    assert not [m for m in _messages(caplog) if m.startswith("BFFM2")]
