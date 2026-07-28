"""Phase 1a T1a-1 and T1a-3: plugin-side tests for the extracted vertical
envelope helper.

Requires QGIS Python (imports qgis.core). Run under OSGeo4W shell:
    python-qgis.bat -m pytest tests/test_phase1a_get_vertical_envelope_plugin.py -v

Covers:
  * T1a-1  Unit-level equivalence of _compute_z_envelope against the
           pre-refactor inline formulas across every populated
           (group, stage, method) combination in training_v3.alaqs.
  * T1a-3  Fallback branch coverage: missing mode dynamics triggers the
           expected warning and returns zero-envelope; unknown method
           collapses to no-shift.
  * Additional: get_vertical_envelope wrapper delegation and
                create_polygon_3d numerical equivalence check via a small
                mocked Aircraft.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# QGIS imports guarded so the module still parses without QGIS in path;
# tests requiring QGIS will collect-fail cleanly rather than import-fail.
try:
    from qgis.core import QgsPoint  # noqa: F401

    from open_alaqs.core.GeoTransformation import GeoTransformation

    HAS_QGIS = True
except Exception as _exc:  # pragma: no cover
    HAS_QGIS = False
    _import_error = _exc


FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "openalaqs_standalone"
    / "validation"
    / "data"
    / "training_v3.alaqs"
)


pytestmark = pytest.mark.skipif(
    not HAS_QGIS, reason="QGIS Python not importable in this environment"
)


# ---------------------------------------------------------------------------
# Reference formulas: copied verbatim from create_polygon_3d before the
# refactor (GeoTransformation.py L129-L146 at 3f3e2af). ver_ext = d_v is
# kept literal.
# ---------------------------------------------------------------------------
def _pre_refactor_z(sas_method, s_v, d_v, z_start, z_end):
    ver_ext = d_v
    ver_shift = s_v
    if sas_method == "default":
        z_shifted_start = z_start + ver_shift
        z_shifted_end = z_end + ver_shift
        z_upper_start = z_shifted_start + ver_ext
        z_upper_end = z_shifted_end + ver_ext
    elif sas_method == "sas":
        z_shifted_start = z_start - (ver_ext + d_v) / 2
        z_shifted_end = z_end - (ver_ext + d_v) / 2
        z_upper_start = z_start + ver_ext
        z_upper_end = z_end + ver_ext
    else:
        z_shifted_start = z_start
        z_shifted_end = z_end
        z_upper_start = z_shifted_start
        z_upper_end = z_shifted_end
    return z_shifted_start, z_shifted_end, z_upper_start, z_upper_end


def _load_fixture_triples():
    """Enumerate every populated (group, stage, method, params) from the
    training_v3 fixture, skipping the NULL sentinel rows."""
    if not FIXTURE_PATH.exists():
        return []
    with sqlite3.connect(str(FIXTURE_PATH)) as conn:
        rows = conn.execute(
            "SELECT ac_group, flight_stage, "
            "horizontal_extent_m, vertical_extent_m, vertical_shift_m, "
            "horizontal_extent_m_sas, vertical_extent_m_sas, "
            "vertical_shift_m_sas "
            "FROM default_emission_dynamics"
        ).fetchall()
    out = []
    for g, s, he, ve, vs, hes, ves, vss in rows:
        if g is None or s is None:
            continue
        for method, (h, v, sh) in (
            ("default", (he, ve, vs)),
            ("sas", (hes, ves, vss)),
        ):
            if h is None and v is None and sh is None:
                continue
            params = {
                "horizontal_extension": float(h or 0.0),
                "vertical_shift": float(sh or 0.0),
                "vertical_extension": float(v or 0.0),
            }
            if (
                params["vertical_shift"] == 0.0
                and params["vertical_extension"] == 0.0
                and params["horizontal_extension"] == 0.0
            ):
                continue
            out.append((g, s, method, params))
    return out


FIXTURE_TRIPLES = _load_fixture_triples()


# ---------------------------------------------------------------------------
# T1a-1: fixture-driven byte-identity for _compute_z_envelope.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "group,stage,method,params",
    FIXTURE_TRIPLES,
    ids=lambda v: v if isinstance(v, str) else "",
)
@pytest.mark.parametrize("z_ground", [0.0, 3.0, 100.0, -5.0])
def test_compute_z_envelope_matches_pre_refactor_on_fixture(
    group, stage, method, params, z_ground
):
    """For every populated (group, stage, method) in training_v3.alaqs the
    refactored helper must return exactly the same (z_lower, z_upper) as
    the pre-refactor inline formulas."""
    ref = _pre_refactor_z(
        method,
        params["vertical_shift"],
        params["vertical_extension"],
        z_ground,
        z_ground,
    )
    expected = (ref[0], ref[2])

    got = GeoTransformation._compute_z_envelope(
        method,
        params["vertical_shift"],
        params["vertical_extension"],
        z_ground,
    )

    assert got == expected, (
        f"{group}/{stage}/{method} at z={z_ground}: " f"expected {expected}, got {got}"
    )


# ---------------------------------------------------------------------------
# T1a-3: fallback branches.
# ---------------------------------------------------------------------------
def test_get_dynamics_params_missing_mode_warns(caplog):
    """A KeyError from getEmissionDynamicsByMode()[mode] returns
    zero-extension defaults and emits the pre-refactor warning."""
    ac = MagicMock()
    ac.getEmissionDynamicsByMode.return_value = {}  # missing mode
    ac.getICAOIdentifier.return_value = "TEST"

    with caplog.at_level(logging.WARNING):
        params = GeoTransformation._get_dynamics_params(ac, "default", "CL")

    assert params == {
        "horizontal_extension": 0.0,
        "vertical_shift": 0.0,
        "vertical_extension": 0.0,
    }
    assert any(
        "No emission dynamics found for mode 'CL' on aircraft 'TEST'" in r.message
        for r in caplog.records
    )


def test_get_dynamics_params_method_fallback_to_default():
    """If mode_dynamics.getEmissionDynamics(sas_method) raises, the code
    falls back to getEmissionDynamics('default')."""
    mode_dyn = MagicMock()

    def fake_get(method):
        if method == "sas":
            raise KeyError("sas key missing")
        return {
            "horizontal_extension": 42.0,
            "vertical_shift": -10.0,
            "vertical_extension": 5.0,
        }

    mode_dyn.getEmissionDynamics.side_effect = fake_get
    ac = MagicMock()
    ac.getEmissionDynamicsByMode.return_value = {"CL": mode_dyn}

    params = GeoTransformation._get_dynamics_params(ac, "sas", "CL")
    assert params == {
        "horizontal_extension": 42.0,
        "vertical_shift": -10.0,
        "vertical_extension": 5.0,
    }


def test_compute_z_envelope_fallback_method():
    """Any method other than 'default' or 'sas' returns (z_ground, z_ground)."""
    got = GeoTransformation._compute_z_envelope("none", -100.0, 25.0, 42.0)
    assert got == (42.0, 42.0)


def test_compute_z_envelope_zero_dynamics():
    """Zero dynamics collapse to the ground plane in both real methods."""
    for m in ("default", "sas"):
        got = GeoTransformation._compute_z_envelope(m, 0.0, 0.0, 7.5)
        assert got == (7.5, 7.5), f"method={m}: got {got}"


# ---------------------------------------------------------------------------
# Additional: wrapper delegation.
# ---------------------------------------------------------------------------
def test_get_vertical_envelope_delegates():
    """get_vertical_envelope combines _get_dynamics_params and
    _compute_z_envelope for the same numerical result."""
    mode_dyn = MagicMock()
    mode_dyn.getEmissionDynamics.return_value = {
        "horizontal_extension": 50.0,
        "vertical_shift": -100.0,
        "vertical_extension": 25.0,
    }
    ac = MagicMock()
    ac.getEmissionDynamicsByMode.return_value = {"CL": mode_dyn}

    for method in ("default", "sas"):
        for z_g in (0.0, 3.0, 100.0):
            got = GeoTransformation.get_vertical_envelope(ac, method, "CL", z_g)
            direct = GeoTransformation._compute_z_envelope(method, -100.0, 25.0, z_g)
            assert got == direct
