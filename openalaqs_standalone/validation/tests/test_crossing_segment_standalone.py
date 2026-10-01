"""Segments crossing the vertical limit: standalone and CAEP14 reference.

1. The standalone and the CAEP14 reference implementation agree movement by
   movement for all three methods, at the fixture's mixing height (914.4 m)
   and at a low one (300 m) where arrivals cross the limit as well. A change
   to the crossing rule in only one of them fails here.
2. Analytic check: a departure's counted ground distance ends exactly where
   its profile reaches the limit (altitude linear between profile points),
   not at the next profile point above it.
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
POLLUTANTS = ("co", "hc", "nox", "co2")


def _reference():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ref():
    return _reference()


@pytest.fixture(params=[None, 300.0], ids=["mh_fixture", "mh_300m"])
def study(request, tmp_path):
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    if request.param is not None:
        with sqlite3.connect(dst) as conn:
            conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (request.param,))
    return dst


def _fixed_wing_oids(conn):
    return [
        r[0]
        for r in conn.execute(
            "SELECT oid FROM user_aircraft_movements "
            "WHERE profile_id IS NOT NULL AND profile_id <> '' ORDER BY oid"
        )
    ]


@pytest.mark.parametrize("method", ["bymode", "bffm2_anchor", "bffm2_traj"])
def test_standalone_equals_reference(study, ref, method):
    try:
        rconn = ref._connect(str(study))  # loads mod_spatialite (ST_AsText)
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    with sqlite3.connect(study) as conn:
        ctx_sa = build_context(conn)
        ctx_ref = {
            "runway": ref._get_runway(rconn),
            "grid_bounds": ref._grid_bounds_3857(rconn),
        }
        oids = _fixed_wing_oids(conn)
        assert oids
        for oid in oids:
            sa = compute_for_movement(
                conn, oid, ctx_sa, method=method, use_isa_meteo=True
            )
            rf = ref.compute_for_movement(
                rconn, oid, ctx_ref, method=method, use_isa_meteo=True
            )
            for p in POLLUTANTS:
                # the reference covers taxi + trajectory only; the standalone
                # total also carries engine-start, gate (GSE) and APU parts
                extra = sum(
                    (sa.get(k) or {}).get(p, 0.0)
                    for k in ("start_em_kg", "gate_em_kg", "apu_em_kg")
                )
                assert sa["total_em_kg"][p] - extra == pytest.approx(
                    rf["total_em_kg"][p], rel=1e-9, abs=1e-12
                ), f"oid {oid} {p}"


def test_departure_counted_distance_ends_at_the_limit(tmp_path):
    limit = 300.0
    dst = tmp_path / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    with sqlite3.connect(dst) as conn:
        conn.execute("UPDATE tbl_InvMeteo SET MixingHeight = ?", (limit,))
        oid, profile = conn.execute(
            "SELECT oid, profile_id FROM user_aircraft_movements "
            "WHERE departure_arrival = 'D' AND profile_id LIKE 'JET-%' ORDER BY oid LIMIT 1"
        ).fetchone()
        pts = conn.execute(
            "SELECT x_m, z_m FROM default_aircraft_profiles "
            "WHERE profile_id = ? ORDER BY point",
            (profile,),
        ).fetchall()
        res = compute_for_movement(
            conn, oid, build_context(conn), method="bymode", use_isa_meteo=True
        )

    # Profile distance at which the altitude reaches the limit.
    x_cross = None
    for (xa, za), (xb, zb) in zip(pts, pts[1:]):
        if za < limit < zb:
            x_cross = xa + (limit - za) / (zb - za) * (xb - xa)
            x_next = xb
            break
    assert x_cross is not None, "test premise: the profile must cross the limit"
    counted = sum(s["ground_m"] for s in res["segments"])
    first_airborne_x = pts[0][0]
    assert counted == pytest.approx(x_cross - first_airborne_x, abs=0.5)
    assert counted < x_next - first_airborne_x - 1.0
