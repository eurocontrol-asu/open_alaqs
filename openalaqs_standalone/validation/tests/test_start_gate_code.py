"""compute_start_emissions_for_movement honours gate_emissions_code like the
plugin: 0 suppresses the start emissions; NULL, blank and unparseable values
count as 1 (Movement.__init__)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import compute_start_movements as cs
from openalaqs_standalone import movements as mv

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"


@pytest.fixture(scope="module")
def departure():
    if not FIXTURE.exists():
        pytest.skip(f"fixture not found: {FIXTURE}")
    conn = sqlite3.connect(FIXTURE)
    oid = conn.execute(
        "SELECT oid FROM user_aircraft_movements WHERE departure_arrival = 'D' "
        "AND profile_id IS NOT NULL AND profile_id <> '' ORDER BY oid LIMIT 1"
    ).fetchone()[0]
    mov = mv.get_movement(conn, oid)
    yield conn, mov
    conn.close()


@pytest.mark.parametrize(
    "code, suppressed",
    [(0, True), ("0", True), (1, False), (None, False), ("", False), ("x", False)],
)
def test_gate_emissions_code(departure, code, suppressed):
    conn, mov = departure
    em = cs.compute_start_emissions_for_movement(
        conn, {**mov, "gate_emissions_code": code}
    )
    if suppressed:
        assert all(v == 0.0 for v in em.values())
    else:
        assert em["hc"] > 0.0
