"""Regression: the standalone must look engines up the way the plugin does.

The plugin keys engine emission indices on ``engine_name``, falling back to
``engine_full_name`` only when ``engine_name`` is empty
(``EngineEmissionIndicesDatabase.initEmissionIndices``). The movement table's
``engine_name`` column holds that key.

The shipped ``default_aircraft_engine_ei`` table has ``engine_full_name`` equal
to ``engine_name`` on every row, so a lookup on either column gives the same
result there. Study databases that carry the real engine designation in
``engine_full_name`` (for example "CFM56-7B26" for engine "3CM033") are where
a lookup on the wrong column silently drops movements.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone import movements as mv
from openalaqs_standalone.compute_movements import compute_all_movements

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "training_v3.alaqs"


def _nox_by_oid(path, method="bymode"):
    with sqlite3.connect(path) as conn:
        res = compute_all_movements(conn, method=method, use_isa_meteo=True)
    return {oid: r["total_em_kg"]["nox"] for oid, r in res.items()}


@pytest.fixture
def fixture_copy(tmp_path):
    dst = tmp_path / "training_copy.alaqs"
    shutil.copy(FIXTURE, dst)
    return dst


@pytest.mark.parametrize("method", ["bymode", "bffm2_anchor", "bffm2_traj"])
def test_full_names_differing_from_engine_names_do_not_drop_movements(
    fixture_copy, method
):
    """Give every engine a full name different from its key: results must not change."""
    with sqlite3.connect(fixture_copy) as conn:
        conn.execute(
            "UPDATE default_aircraft_engine_ei "
            "SET engine_full_name = engine_full_name || ' (designation)' "
            "WHERE engine_name IS NOT NULL AND engine_name <> ''"
        )
    base = _nox_by_oid(FIXTURE, method)
    renamed = _nox_by_oid(fixture_copy, method)
    assert set(renamed) == set(
        base
    ), f"movements dropped: {sorted(set(base) - set(renamed))}"
    for oid, value in base.items():
        assert renamed[oid] == pytest.approx(value, rel=1e-12, abs=1e-15)


def test_empty_engine_name_falls_back_to_full_name(fixture_copy):
    """An engine whose engine_name is empty is keyed on engine_full_name (plugin rule)."""
    with sqlite3.connect(fixture_copy) as conn:
        key = conn.execute(
            "SELECT engine_name FROM user_aircraft_movements "
            "WHERE engine_name <> '' ORDER BY oid LIMIT 1"
        ).fetchone()[0]
        full = key + " (designation)"
        conn.execute(
            "UPDATE default_aircraft_engine_ei SET engine_full_name = ?, engine_name = '' "
            "WHERE engine_name = ?",
            (full, key),
        )
        conn.execute(
            "UPDATE user_aircraft_movements SET engine_name = ? WHERE engine_name = ?",
            (full, key),
        )
        conn.commit()
        assert set(mv.get_engine_ei(conn, full)) == {"TX", "AP", "CL", "TO"}
        assert mv.get_engine_ei(conn, key) == {}
