"""Helicopters: standalone and CAEP14 reference agree under the vertical limit.

Since 5.3.2 the FOCA active mode (TO or AP) keeps only its part below the
period's mixing height and inside the grid, on the FOCA flight path placed at
the helicopter's gate centroid (helipad) or else the runway threshold. The
reference implements the path and the cut on its own
(`_heli_flight_path_local`, `_heli_active_fraction`); the standalone uses the
module shared with the plugin. The two must agree on the fixture's helicopters
(AS50 departure and arrival) at several mixing heights, with and without a
helipad gate. The plugin itself agrees with the reference on the fixture at
914.4 m and at 300 m with gate G4 (October 2026 run, see CAEP14_VALIDATION.md).
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone.compute_movements import build_context, compute_for_movement

DATA = Path(__file__).resolve().parents[1] / "data"
FIXTURE = DATA / "training_v3.alaqs"
TOOLS = Path(__file__).resolve().parents[1] / "tools"
POLLUTANTS = ("co", "co2", "hc", "nox", "pm10")
HELICOPTER_OIDS = (14, 15)


@pytest.fixture(scope="module")
def ref():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("gate", [None, "G4", "G7"])
@pytest.mark.parametrize("mixing_height", [914.4, 600.0, 300.0, 100.0])
def test_helicopter_standalone_equals_reference(tmp_path, ref, mixing_height, gate):
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (mixing_height,))
        if gate:
            conn.execute(
                "UPDATE user_aircraft_movements SET gate = ? WHERE oid IN (?, ?)",
                (gate, *HELICOPTER_OIDS),
            )
    try:
        rconn = ref._connect(str(dst))
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    ctx_ref = {
        "runway": ref._get_runway(rconn),
        "grid_bounds": ref._grid_bounds_3857(rconn),
    }
    with sqlite3.connect(dst) as conn:
        ctx_sa = build_context(conn)
        for oid in HELICOPTER_OIDS:
            sa = compute_for_movement(conn, oid, ctx_sa, method="bymode")
            rr = ref.compute_for_movement(rconn, oid, ctx_ref, method="bymode")
            assert sa is not None and rr is not None
            for p in POLLUTANTS:
                assert sa["total_em_kg"][p] == pytest.approx(
                    rr["total_em_kg"][p], rel=1e-9
                ), (oid, p)
    rconn.close()


def test_cut_reduces_the_active_mode_only(tmp_path, ref):
    """At 100 m the arrival keeps less of its approach than at 914.4 m; ground idle is untouched."""
    totals = {}
    for mh in (914.4, 100.0):
        dst = tmp_path / f"study_{mh}.alaqs"
        shutil.copy(FIXTURE, dst)
        with sqlite3.connect(dst) as conn:
            conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (mh,))
        try:
            rconn = ref._connect(str(dst))
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
        ctx_ref = {
            "runway": ref._get_runway(rconn),
            "grid_bounds": ref._grid_bounds_3857(rconn),
        }
        totals[mh] = {
            oid: ref.compute_for_movement(rconn, oid, ctx_ref, method="bymode")
            for oid in HELICOPTER_OIDS
        }
        rconn.close()
    for oid in HELICOPTER_OIDS:
        hi, lo = totals[914.4][oid], totals[100.0][oid]
        assert lo["total_em_kg"]["nox"] < hi["total_em_kg"]["nox"]
        assert lo["traj_fuel_by_mode_kg"]["GI"] == hi["traj_fuel_by_mode_kg"]["GI"]
