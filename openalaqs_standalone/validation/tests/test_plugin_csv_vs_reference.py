"""The pinned plugin outputs equal the CAEP14 reference and the standalone.

`data/plugin_output/training_movements_<method>.csv` hold the plugin's
per-movement totals on `training_v3.alaqs` (re-exported headlessly with
`tools/regenerate_plugin_csvs.py`). The plugin applies the study meteo
(`tbl_InvMeteo`) to the BFFM2 ambient corrections, so the reference and the
standalone are run with `use_isa_meteo=False`. All 15 movements, including the
two helicopters, must agree for the three methods and for bymode with the
ICCAIA ambient NOx correction (take-off and climb-out segments).

Tolerance: 2e-4 relative. The CUSTOM (ADS-B) departure, movement 11, differs
by 1.3e-5 between the plugin and the Python implementations (projection of the
supplied track). With the NOx correction the six departures differ by 1e-6
to 3e-6 between the plugin and the reference. Every other row agrees to
floating-point noise.
"""

from __future__ import annotations

import csv
import importlib.util
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone.compute_movements import build_context, compute_for_movement

DATA = Path(__file__).resolve().parents[1] / "data"
FIXTURE = DATA / "training_v3.alaqs"
TOOLS = Path(__file__).resolve().parents[1] / "tools"
POLLUTANTS = ("co", "co2", "hc", "nox", "sox", "pm10")
METHODS = ("bymode", "bffm2_anchor", "bffm2_traj", "bymode_nox_corr")


def _plugin_totals(method: str) -> dict:
    totals = {}
    with open(DATA / "plugin_output" / f"training_movements_{method}.csv") as f:
        for row in csv.DictReader(f):
            m = re.match(r"id\s+(\d+):", row["source_name"])
            if m:
                oid = int(m.group(1))
                t = totals.setdefault(oid, {p: 0.0 for p in POLLUTANTS})
                for p in POLLUTANTS:
                    t[p] += float(row[f"{p}_kg"])
    return totals


@pytest.fixture(scope="module")
def ref():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    dst = tmp_path_factory.mktemp("caep14") / "study.alaqs"
    shutil.copy(FIXTURE, dst)
    return dst


@pytest.mark.parametrize("method", METHODS)
def test_plugin_equals_reference_and_standalone(study, ref, method):
    plugin = _plugin_totals(method)
    nox_corr = method.endswith("_nox_corr")
    method = method.replace("_nox_corr", "")
    assert len(plugin) == 15
    try:
        rconn = ref._connect(str(study))
    except Exception as exc:  # pragma: no cover - environment without SpatiaLite
        pytest.skip(f"CAEP14 reference needs mod_spatialite: {exc}")
    ctx_ref = {
        "runway": ref._get_runway(rconn),
        "grid_bounds": ref._grid_bounds_3857(rconn),
    }
    with sqlite3.connect(study) as conn:
        ctx_sa = build_context(conn)
        for oid, plg in sorted(plugin.items()):
            rr = ref.compute_for_movement(
                rconn,
                oid,
                ctx_ref,
                method=method,
                use_isa_meteo=False,
                apply_nox_corrections=nox_corr,
            )
            sa = compute_for_movement(
                conn,
                oid,
                ctx_sa,
                method=method,
                use_isa_meteo=False,
                apply_nox_corrections=nox_corr,
            )
            assert rr is not None and sa is not None, oid
            for p in POLLUTANTS:
                assert rr["total_em_kg"][p] == pytest.approx(
                    plg[p], rel=2e-4, abs=1e-9
                ), (oid, p, "reference")
                assert sa["total_em_kg"][p] == pytest.approx(
                    plg[p], rel=2e-4, abs=1e-9
                ), (oid, p, "standalone")
    rconn.close()
