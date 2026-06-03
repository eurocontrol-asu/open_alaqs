"""Regression: movements.get_movement loads apu_code from the DB.

Before the fix, `get_movement` did not include `apu_code` in its
SELECT, so the returned dict had no `apu_code` key. `compute_apu_
movements` then fell back to its permissive default (apu_code = 1 =
"APU at stand only"), producing nonzero APU emissions even for
movements whose database row sets `apu_code = 0` ("suppress APU").

This test pins:
  1. get_movement returns an `apu_code` field whose value matches the
     `apu_code` column for that oid.
  2. When `apu_code = 0` on every movement, compute_all_movements
     emits zero APU mass (per pollutant, per movement).

The training_v3 fixture has `apu_code = 0` on all 15 movements, which
makes it a clean witness for this regression.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import compute_movements as cm
from openalaqs_standalone import movements as mv

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


@pytest.fixture(scope="module")
def conn():
    if not FIXTURE.exists():
        pytest.skip(f"fixture not present: {FIXTURE}")
    c = sqlite3.connect(str(FIXTURE))
    yield c
    c.close()


def test_get_movement_returns_apu_code_field(conn):
    """get_movement must include an `apu_code` key in its returned dict."""
    m = mv.get_movement(conn, 1)
    assert m is not None
    assert "apu_code" in m, (
        "get_movement should return an 'apu_code' field; "
        "before the fix the SELECT did not include the column."
    )


def test_apu_code_matches_db_value_for_every_movement(conn):
    """For every oid, the loaded apu_code matches the DB column."""
    rows = dict(conn.execute("SELECT oid, apu_code FROM user_aircraft_movements"))
    assert rows, "training_v3 must have movements"
    for oid, db_code in rows.items():
        loaded = mv.get_movement(conn, oid)["apu_code"]
        assert (
            loaded == db_code
        ), f"oid {oid}: DB apu_code={db_code!r} but loaded={loaded!r}"


def test_apu_code_zero_means_zero_apu_emissions(conn):
    """training_v3 has apu_code=0 everywhere; APU NOx total must be 0."""
    # Sanity guard: confirm the fixture is what this test assumes.
    distinct_codes = {
        r[0]
        for r in conn.execute("SELECT DISTINCT apu_code FROM user_aircraft_movements")
    }
    assert distinct_codes == {0}, (
        f"fixture invariant changed: apu_code values = {distinct_codes}; "
        f"this test assumes training_v3 has apu_code=0 on every row"
    )

    result = cm.compute_all_movements(
        conn,
        method="bymode",
        use_isa_meteo=True,
    )
    assert result, "compute_all_movements returned no movements"

    total_apu_nox = sum(
        (r.get("apu_em_kg") or {}).get("nox", 0.0) for r in result.values()
    )
    assert abs(total_apu_nox) < 1e-9, (
        f"APU NOx total should be 0.0 when every movement has apu_code=0; "
        f"got {total_apu_nox:.6f} kg. This means apu_code is being ignored."
    )

    # Pollutant-wise check too: any non-trivial pollutant should be zero.
    for pollutant in ("co", "hc", "nox", "sox", "pm10"):
        total = sum(
            (r.get("apu_em_kg") or {}).get(pollutant, 0.0) for r in result.values()
        )
        assert abs(total) < 1e-9, (
            f"APU {pollutant} total should be 0.0 with apu_code=0 everywhere; "
            f"got {total:.6f} kg"
        )
