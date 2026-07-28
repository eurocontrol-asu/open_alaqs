"""Phase 1a T1a-4a: standalone-side tests for the extracted vertical
envelope helper.

Two goals:
  * Byte-identical equivalence between the refactored code and the
    pre-refactor inline formulas of segment_footprint.
  * Coverage across every populated (ac_group, flight_stage, method)
    combination in the training_v3 fixture.

QGIS-free; runs under plain python + shapely.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from openalaqs_standalone.source_dynamics import (
    _compute_z_envelope,
    get_vertical_envelope,
    load_emission_dynamics,
    segment_footprint,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "training_v3.alaqs"


# ---------------------------------------------------------------------------
# Reference formulas: copied verbatim from the pre-refactor inline z-block of
# segment_footprint (source_dynamics.py L268-L285 at 3f3e2af). Kept literal so
# the byte-identity of the refactor can be checked without re-reading history.
# ---------------------------------------------------------------------------
def _pre_refactor_z(method, s_v, d_v, z1, z2):
    """The four z values (z_shifted_start, z_shifted_end, z_upper_start,
    z_upper_end) as segment_footprint computed them before the refactor.
    """
    ver_ext = d_v
    if method == "default":
        z_shifted_start = z1 + s_v
        z_shifted_end = z2 + s_v
        z_upper_start = z_shifted_start + ver_ext
        z_upper_end = z_shifted_end + ver_ext
    elif method == "sas":
        z_shifted_start = z1 - (ver_ext + d_v) / 2.0
        z_shifted_end = z2 - (ver_ext + d_v) / 2.0
        z_upper_start = z1 + ver_ext
        z_upper_end = z2 + ver_ext
    else:
        z_shifted_start = z1
        z_shifted_end = z2
        z_upper_start = z1
        z_upper_end = z2
    return z_shifted_start, z_shifted_end, z_upper_start, z_upper_end


# ---------------------------------------------------------------------------
# Fixture: enumerate every populated (group, stage, method) triple from
# training_v3.alaqs. Skips the NULL sentinel rows the fixture contains.
# ---------------------------------------------------------------------------
def _fixture_triples():
    if not FIXTURE_PATH.exists():
        pytest.skip(f"fixture missing: {FIXTURE_PATH}")
    with sqlite3.connect(str(FIXTURE_PATH)) as conn:
        dyn = load_emission_dynamics(conn)
    out = []
    for group, stages in dyn.items():
        if group is None:
            continue
        for stage, methods in stages.items():
            if stage is None:
                continue
            for method in ("default", "sas"):
                params = methods.get(method)
                if params is None:
                    continue
                # Skip if all dynamics values are zero (indistinguishable from
                # the fallback branch and useless as a discriminating case).
                if (
                    params["vertical_shift"] == 0.0
                    and params["vertical_extension"] == 0.0
                    and params["horizontal_extension"] == 0.0
                ):
                    continue
                out.append((group, stage, method, params))
    return out


FIXTURE_TRIPLES = _fixture_triples()


# ---------------------------------------------------------------------------
# T1a-4a.1  Fixture-driven byte-identity for _compute_z_envelope.
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
    """For every populated (group, stage, method) in training_v3.alaqs and
    a range of ground z values, the refactored helper must return the same
    (z_lower, z_upper) as the pre-refactor inline formulas.

    A single endpoint is enough: _compute_z_envelope takes one z, so
    calling it once with z_ground reproduces the (z_shifted, z_upper) that
    segment_footprint would compute for that endpoint.
    """
    s_v = params["vertical_shift"]
    d_v = params["vertical_extension"]

    # Pre-refactor: pass z_ground as both endpoints, take (z_shifted_start,
    # z_upper_start). Guaranteed equal to the single-endpoint helper output.
    ref = _pre_refactor_z(method, s_v, d_v, z_ground, z_ground)
    expected = (ref[0], ref[2])

    got = _compute_z_envelope(method, s_v, d_v, z_ground)

    assert (
        got == expected
    ), f"{group}/{stage}/{method} at z={z_ground}: expected {expected}, got {got}"


# ---------------------------------------------------------------------------
# T1a-4a.2  segment_footprint end-to-end byte-identity.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("group,stage,method,params", FIXTURE_TRIPLES, ids=lambda v: "")
@pytest.mark.parametrize(
    "endpoints",
    [
        ((0.0, 0.0), (100.0, 0.0)),
        ((10.0, 20.0), (110.0, 220.0)),
        ((0.0, 0.0), (0.001, 0.001)),  # near-degenerate but non-zero
    ],
)
@pytest.mark.parametrize("zs", [(0.0, 0.0), (5.0, 15.0), (100.0, 50.0)])
def test_segment_footprint_zmin_zmax_pre_refactor(
    group, stage, method, params, endpoints, zs
):
    """segment_footprint's returned (z_min, z_max) equals the pre-refactor
    computation for the same params and endpoints.
    """
    p1, p2 = endpoints
    z1, z2 = zs
    zs_start, zs_end, zu_start, zu_end = _pre_refactor_z(
        method, params["vertical_shift"], params["vertical_extension"], z1, z2
    )
    expected_zmin = min(zs_start, zs_end)
    expected_zmax = max(zu_start, zu_end)

    _, zmin, zmax = segment_footprint(p1, p2, z1, z2, method, params)
    assert (zmin, zmax) == (expected_zmin, expected_zmax), (
        f"{group}/{stage}/{method} endpoints={endpoints} zs={zs}: "
        f"expected ({expected_zmin}, {expected_zmax}), got ({zmin}, {zmax})"
    )


# ---------------------------------------------------------------------------
# T1a-4a.3  Fallback branch coverage.
# ---------------------------------------------------------------------------
def test_compute_z_envelope_fallback_method():
    """A method other than 'default' or 'sas' returns (z_ground, z_ground)."""
    got = _compute_z_envelope("none", -100.0, 25.0, 42.0)
    assert got == (42.0, 42.0)


def test_compute_z_envelope_zero_dynamics():
    """Zero-dynamics inputs (the missing-mode fallback) collapse to the
    ground plane in both real methods."""
    for m in ("default", "sas"):
        got = _compute_z_envelope(m, 0.0, 0.0, 7.5)
        assert got == (7.5, 7.5), f"method={m}: got {got}"


# ---------------------------------------------------------------------------
# T1a-4a.4  get_vertical_envelope wrapper delegates correctly.
# ---------------------------------------------------------------------------
def test_get_vertical_envelope_wrapper():
    """The public wrapper reads (vertical_shift, vertical_extension) from
    the params dict and delegates to _compute_z_envelope.
    """
    params = {
        "horizontal_extension": 50.0,
        "vertical_shift": -100.0,
        "vertical_extension": 25.0,
    }
    for method in ("default", "sas", "none"):
        for z_g in (0.0, 3.0, 100.0):
            direct = _compute_z_envelope(
                method, params["vertical_shift"], params["vertical_extension"], z_g
            )
            via_wrapper = get_vertical_envelope(params, method, z_g)
            assert (
                direct == via_wrapper
            ), f"method={method} z={z_g}: direct={direct} wrapper={via_wrapper}"


# ---------------------------------------------------------------------------
# T1a-4a.5  segment_footprint degenerate-length branch untouched.
# ---------------------------------------------------------------------------
def test_segment_footprint_zero_length_returns_none_footprint():
    """A zero-length XY segment returns (None, z1, z2), unchanged by the
    refactor."""
    params = {
        "horizontal_extension": 50.0,
        "vertical_shift": -100.0,
        "vertical_extension": 25.0,
    }
    fp, zmin, zmax = segment_footprint(
        (0.0, 0.0), (0.0, 0.0), 5.0, 10.0, "default", params
    )
    assert fp is None
    assert zmin == 5.0
    assert zmax == 10.0
