"""
source_dynamics: standalone port of the plugin's smooth-and-shift
("source dynamics") geometry transformation.

The QGIS plugin, when the Calculate-Inventory dialog's "source dynamics"
dropdown is set to "default" or "smooth & shift", replaces each flight
emission's line geometry with a 3-D box ("volume source") via
``GeoTransformation.SmoothAndShiftTransformer`` /
``GeoTransformation.create_polygon_3d``. The box spreads the segment
horizontally to a width ``d_h`` and gives it a vertical envelope
(``vertical_shift`` + ``vertical_extension``) read, per aircraft group and
flight stage, from the ``default_emission_dynamics`` table.

Downstream, the plugin's 2-D grid output
(``GridOutputModule._process_grid``) apportions a polygon/volume emission by
``intersection.area / geom.area`` -- a purely horizontal (XY) operation that
ignores z. So for the inventory / 2-D gpkg output the only thing that changes
versus source_dynamics="none" is that each segment is apportioned by the area
of its footprint RECTANGLE instead of by its centreline LENGTH. The vertical
envelope matters only for the AUSTAL volume-source z extent.

This module is deliberately QGIS-free (pure Python + shapely) so it can be
unit-tested without a QGIS runtime. It provides:

  * ``dynamic_group_for(ac_group)``      -- the helicopter group renaming the
                                            plugin applies before the dynamics
                                            lookup (Aircraft.py).
  * ``load_emission_dynamics(conn)``     -- read default_emission_dynamics into
                                            {group: {stage: {method: params}}}.
  * ``resolve_method(source_dynamics)``  -- map the CLI/dialog string to the
                                            normalised method ("default"/"sas")
                                            or None when disabled.
  * ``sas_mode_for_segment(...)``        -- replicate the plugin's per-segment
                                            AP/TO/CL determination.
  * ``segment_footprint(...)``           -- the create_polygon_3d footprint + z
                                            envelope math, returning a shapely
                                            rectangle (EPSG:3857) and (z_min,
                                            z_max).

The footprint rectangle is fed to the existing
``distribute._polygon_cell_fractions`` (already area-weighted and plugin-
equivalent), so no new cell-apportionment code is needed.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

# Flight stages used by the smooth-and-shift lookup. TX (taxi) is in the
# table too but taxi emissions are handled by the standalone's separate
# taxi path; the flight-segment transform only ever resolves to AP/TO/CL.
_FLIGHT_STAGES = ("TX", "AP", "TO", "CL")

# Keys returned by EmissionDynamics.getEmissionDynamics(mode) in the plugin.
# horizontal_shift is always 0 there (the *_sas column does not exist), so we
# do not carry it.
_METHODS = ("default", "sas")


def dynamic_group_for(ac_group: Optional[str]) -> Optional[str]:
    """Map a default_aircraft.ac_group to the group key used in
    default_emission_dynamics.

    Mirrors Aircraft.py: helicopters are renamed; every other group is used
    verbatim. Returns None for a missing/empty group (caller treats that as
    "no dynamics -> fall back to line").
    """
    if not ac_group:
        return None
    if ac_group in ("HELICOPTER", "HELICOPTER LIGHT"):
        return "HELI SMALL"
    if ac_group in ("HELICOPTER HEAVY", "HELICOPTER LARGE", "HELICOPTER MEDIUM"):
        return "HELI LARGE"
    return ac_group


def resolve_method(source_dynamics: Optional[str]) -> Optional[str]:
    """Normalise the source-dynamics selector to a transform method.

    Plugin semantics (MovementSourceModule.smoothAndShiftEnabled +
    SmoothAndShiftTransformer.__init__):

        "none"          -> disabled               -> None
        "default"       -> enabled, method="default"
        "smooth & shift"-> enabled, method="sas"
        "sas"           -> enabled, method="sas"  (CLI convenience alias)

    Any other / falsy value disables the transform (returns None).
    """
    if not source_dynamics:
        return None
    s = source_dynamics.strip().lower()
    if s == "none":
        return None
    if s == "default":
        return "default"
    if s in ("smooth & shift", "smooth and shift", "sas"):
        return "sas"
    return None


def load_emission_dynamics(conn: sqlite3.Connection) -> dict:
    """Read default_emission_dynamics into a nested lookup.

    Returns::

        { dynamic_group: { flight_stage: { "default": {...}, "sas": {...} } } }

    where each leaf dict is::

        {"horizontal_extension": d_h,
         "vertical_shift":       s_v,
         "vertical_extension":   d_v}

    Rows with a NULL/empty ac_group or flight_stage are skipped, matching
    EmissionDynamicsStore.get_emissions_dynamics. NULL numeric columns are
    coerced to 0.0 (the plugin's ``db_row[...] or 0`` behaviour).
    """
    out: dict = {}
    rows = conn.execute(
        """
        SELECT ac_group, flight_stage,
               horizontal_extent_m, vertical_extent_m, vertical_shift_m,
               horizontal_extent_m_sas, vertical_extent_m_sas,
               vertical_shift_m_sas
        FROM default_emission_dynamics
        """
    ).fetchall()

    for group, stage, he, ve, vs, he_s, ve_s, vs_s in rows:
        # Plugin: `if not row.ac_group or not row.flight_stage: continue`
        if not group or not stage:
            continue
        stage_map = out.setdefault(group, {})
        stage_map[stage] = {
            "default": {
                "horizontal_extension": float(he or 0.0),
                "vertical_shift": float(vs or 0.0),
                "vertical_extension": float(ve or 0.0),
            },
            "sas": {
                "horizontal_extension": float(he_s or 0.0),
                "vertical_shift": float(vs_s or 0.0),
                "vertical_extension": float(ve_s or 0.0),
            },
        }
    return out


def sas_mode_for_segment(is_arrival: bool, z1: float, z2: float) -> str:
    """Per-segment flight stage used for the dynamics lookup.

    Replicates the combined logic of
    SmoothAndShiftTransformer.transform_emissions (which is called with
    lto_mode="") and create_polygon_3d's TO->CL reclassification:

        transform_emissions:  "AP" if arrival
                               else "TO" if start_z == 0 else "CL"
        create_polygon_3d:     if mode == "TO" and z2 > 0: mode = "CL"

    Net result:
        arrival                          -> "AP"
        departure, z1 == 0 and z2 == 0   -> "TO"
        departure, otherwise             -> "CL"

    The standalone's own per-trajectory-point mode field is intentionally NOT
    used here -- the plugin derives the SAS stage purely from arrival flag and
    altitudes, and we match that to keep the d_h/d_v/s_v lookup identical.
    """
    if is_arrival:
        return "AP"
    if z1 == 0:
        return "CL" if z2 > 0 else "TO"
    return "CL"


def lookup_params(
    dynamics: dict,
    dynamic_group: Optional[str],
    stage: str,
    method: str,
) -> Optional[dict]:
    """Fetch {horizontal_extension, vertical_shift, vertical_extension} for a
    (group, stage, method), or None if the group/stage is absent.

    A None return signals the caller to fall back to line apportionment
    (mirrors create_polygon_3d's "Using zero-extension defaults" branch, which
    collapses the box to the centreline when no dynamics row is found).
    """
    if dynamic_group is None:
        return None
    grp = dynamics.get(dynamic_group)
    if grp is None:
        return None
    st = grp.get(stage)
    if st is None:
        return None
    return st.get(method)


def _compute_z_envelope(method, s_v, d_v, z_ground):
    """Pure vertical-envelope formula. Mirror of
    ``open_alaqs.core.GeoTransformation._compute_z_envelope``.

    Returns ``(z_lower, z_upper)`` for one endpoint / stationary source at
    ground z = ``z_ground``, under smooth-and-shift ``method``
    (``"default"`` or ``"sas"``; any other value takes the no-shift
    fallback branch).

    Expressions and evaluation order preserved verbatim from the previous
    inline z-block of ``segment_footprint`` so the CAEP14 regression is
    byte-identical before and after this extraction. ``ver_ext = d_v``
    symbol identity from the original code is preserved rather than
    algebraically simplified. No z clamping applied here.
    """
    ver_ext = d_v  # preserved: plugin sets ver_ext = d_v after lookup

    if method == "default":
        z_lower = z_ground + s_v
        z_upper = z_lower + ver_ext
    elif method == "sas":
        z_lower = z_ground - (ver_ext + d_v) / 2.0
        z_upper = z_ground + ver_ext
    else:
        z_lower = z_ground
        z_upper = z_ground

    return z_lower, z_upper


def get_vertical_envelope(params, method, z_ground):
    """Convenience wrapper: (params, method, z_ground) -> (z_lower, z_upper).

    ``params`` is the pre-resolved dict from ``lookup_params`` or
    ``load_emission_dynamics``, with keys ``horizontal_extension``,
    ``vertical_shift``, ``vertical_extension``. Consumed by paths that need
    only the vertical envelope of a stationary source (engine-test
    emissions, phase 3), rather than a full footprint around a trajectory
    segment.

    Numerically equivalent to the plugin-side
    ``GeoTransformation.get_vertical_envelope`` for the same inputs; the
    signature differs only because the standalone resolves the DB lookup
    separately upstream in ``lookup_params``, whereas the plugin's wrapper
    performs the lookup itself from an ``Aircraft`` object.
    """
    return _compute_z_envelope(
        method, params["vertical_shift"], params["vertical_extension"], z_ground
    )


def segment_footprint(
    p1: tuple,
    p2: tuple,
    z1: float,
    z2: float,
    method: str,
    params: dict,
):
    """Build the 2-D footprint rectangle and vertical envelope for one
    smooth-and-shift segment.

    Ports the geometry of GeoTransformation.create_polygon_3d, keeping only
    what the 2-D grid apportionment and the AUSTAL z extent need:

      * the horizontal footprint, which is the box's bottom/top face (they
        coincide in XY): a rectangle of width ``d_h`` centred on the p1->p2
        centreline, built with the plugin's exact vertex order
        [start+, start-, end-, end+];
      * the vertical envelope (z_min, z_max), taken UNCLAMPED from the
        z_shifted / z_upper values the plugin returns from create_polygon_3d
        and folds into emission.setVerticalExtent. (The plugin clamps each
        polygon VERTEX to max(0, z) for the 3-D volume, but the returned
        envelope values are unclamped; we match the envelope.)

    Args:
        p1, p2: (x, y[, ...]) EPSG:3857 endpoints. Only x, y are read.
        z1, z2: trajectory altitudes (m) at the segment start/end.
        method: "default" or "sas" (already normalised by resolve_method).
        params: {"horizontal_extension", "vertical_shift",
                 "vertical_extension"} for the resolved (group, stage, method).

    Returns:
        (footprint, z_min, z_max) where footprint is a shapely Polygon in
        EPSG:3857, or (None, z1, z2) for a zero-length XY segment (degenerate;
        caller should fall back to the line/point path -- matching
        create_polygon_3d raising ValueError on length == 0, which
        transform_emissions catches and skips).

    Note: when ``params["horizontal_extension"]`` is 0 the rectangle collapses
    to a zero-area sliver. The plugin's flight-stage rows all carry a non-zero
    horizontal extent (>= 25 m), so this does not arise for real flight
    segments; the caller still guards on zero area for safety.
    """
    from shapely.geometry import Polygon

    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])

    dx = x2 - x1
    dy = y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0.0:
        # Degenerate XY segment: no footprint. Caller falls back.
        return None, z1, z2

    d_h = params["horizontal_extension"]
    s_v = params["vertical_shift"]
    d_v = params["vertical_extension"]

    hor_ext = d_h / 2.0  # half-width

    # Unit perpendicular in XY (plugin: perp_x = -dy/len, perp_y = dx/len).
    perp_x = -dy / length
    perp_y = dx / length

    # z-envelope per endpoint, delegated to _compute_z_envelope.
    z_shifted_start, z_upper_start = _compute_z_envelope(method, s_v, d_v, z1)
    z_shifted_end, z_upper_end = _compute_z_envelope(method, s_v, d_v, z2)

    # Fallback method (neither "default" nor "sas") also zeroes the
    # horizontal spread. Preserved from the previous inline else branch.
    if method not in ("default", "sas"):
        hor_ext = 0.0

    # Footprint rectangle, plugin bottom-face vertex order [0,1,2,3] =
    # [start+, start-, end-, end+].
    corners = [
        (x1 + hor_ext * perp_x, y1 + hor_ext * perp_y),  # start+
        (x1 - hor_ext * perp_x, y1 - hor_ext * perp_y),  # start-
        (x2 - hor_ext * perp_x, y2 - hor_ext * perp_y),  # end-
        (x2 + hor_ext * perp_x, y2 + hor_ext * perp_y),  # end+
    ]
    footprint = Polygon(corners)

    # Vertical envelope (unclamped, matching the plugin's setVerticalExtent).
    z_min = min(z_shifted_start, z_shifted_end)
    z_max = max(z_upper_start, z_upper_end)

    return footprint, z_min, z_max


# ---------------------------------------------------------------------------
# Self-test: validates the footprint/z math against hand-computed values
# without needing a QGIS runtime or a real .alaqs file. Run with:
#     python -m openalaqs_standalone.source_dynamics
# ---------------------------------------------------------------------------
def _self_test() -> None:
    pass

    failures = []

    def check(name, got, want, tol=1e-9):
        if isinstance(want, (int, float)):
            ok = abs(got - want) <= tol
        else:
            ok = got == want
        if not ok:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # --- resolve_method ---
    check("resolve none", resolve_method("none"), None)
    check("resolve None", resolve_method(None), None)
    check("resolve default", resolve_method("default"), "default")
    check("resolve s&s", resolve_method("smooth & shift"), "sas")
    check("resolve sas", resolve_method("sas"), "sas")
    check("resolve junk", resolve_method("wat"), None)

    # --- dynamic_group_for ---
    check("dg jet", dynamic_group_for("JET MEDIUM"), "JET MEDIUM")
    check("dg heli light", dynamic_group_for("HELICOPTER LIGHT"), "HELI SMALL")
    check("dg heli heavy", dynamic_group_for("HELICOPTER HEAVY"), "HELI LARGE")
    check("dg heli", dynamic_group_for("HELICOPTER"), "HELI SMALL")
    check("dg none", dynamic_group_for(None), None)

    # --- sas_mode_for_segment ---
    check("mode arrival", sas_mode_for_segment(True, 100, 50), "AP")
    check("mode dep ground", sas_mode_for_segment(False, 0, 0), "TO")
    check("mode dep liftoff", sas_mode_for_segment(False, 0, 30), "CL")
    check("mode dep climb", sas_mode_for_segment(False, 500, 900), "CL")

    # --- segment_footprint: JET MEDIUM TO, sas method ---
    # From default_emission_dynamics: JET MEDIUM TO sas
    #   h_ext=720, v_ext=180, v_shift=0.
    params_to_sas = {
        "horizontal_extension": 720.0,
        "vertical_shift": 0.0,
        "vertical_extension": 180.0,
    }
    # Horizontal segment along +x, 100 m long, on the ground.
    fp, zmin, zmax = segment_footprint(
        (0.0, 0.0), (100.0, 0.0), 0.0, 0.0, "sas", params_to_sas
    )
    # perp = (0, 1); hor_ext = 360. Corners:
    #   (0,360),(0,-360),(100,-360),(100,360). Area = 100 * 720 = 72000.
    check("sas TO area", fp.area, 72000.0, tol=1e-6)
    # Footprint width across the perpendicular = 720.
    minx, miny, maxx, maxy = fp.bounds
    check("sas TO width", maxy - miny, 720.0, tol=1e-6)
    check("sas TO length", maxx - minx, 100.0, tol=1e-6)
    # z envelope (sas): z_shifted = 0 - (180+180)/2 = -180; z_upper = 0+180 = 180.
    check("sas TO zmin", zmin, -180.0, tol=1e-9)
    check("sas TO zmax", zmax, 180.0, tol=1e-9)

    # --- segment_footprint: JET MEDIUM TO, default method ---
    # JET MEDIUM TO default: h_ext=50, v_ext=25, v_shift=0.
    params_to_def = {
        "horizontal_extension": 50.0,
        "vertical_shift": 0.0,
        "vertical_extension": 25.0,
    }
    fp2, zmin2, zmax2 = segment_footprint(
        (0.0, 0.0), (100.0, 0.0), 0.0, 0.0, "default", params_to_def
    )
    # hor_ext = 25; area = 100 * 50 = 5000.
    check("def TO area", fp2.area, 5000.0, tol=1e-6)
    # z (default): z_shifted = 0 + 0 = 0; z_upper = 0 + 25 = 25.
    check("def TO zmin", zmin2, 0.0, tol=1e-9)
    check("def TO zmax", zmax2, 25.0, tol=1e-9)

    # --- segment_footprint: AP (arrival), sas, with vertical shift ---
    # JET MEDIUM AP sas: h_ext=390, v_ext=100, v_shift=-138.
    params_ap_sas = {
        "horizontal_extension": 390.0,
        "vertical_shift": -138.0,
        "vertical_extension": 100.0,
    }
    # Diagonal segment to check the perpendicular orientation.
    fp3, zmin3, zmax3 = segment_footprint(
        (0.0, 0.0), (30.0, 40.0), 200.0, 100.0, "sas", params_ap_sas
    )
    # length = 50; hor_ext = 195; area = 50 * 390 = 19500.
    check("ap sas area", fp3.area, 19500.0, tol=1e-6)
    # z (sas): z_shifted_start = 200 - (100+100)/2 = 100;
    #          z_shifted_end   = 100 - 100 = 0;  zmin = min(100,0) = 0.
    #          z_upper_start = 200 + 100 = 300; z_upper_end = 100 + 100 = 200;
    #          zmax = 300.
    check("ap sas zmin", zmin3, 0.0, tol=1e-9)
    check("ap sas zmax", zmax3, 300.0, tol=1e-9)

    # --- degenerate (zero-length) segment ---
    fp4, _, _ = segment_footprint(
        (10.0, 10.0), (10.0, 10.0), 0.0, 0.0, "sas", params_to_sas
    )
    check("degenerate footprint", fp4, None)

    # --- footprint validity (no self-intersection) for the diagonal case ---
    check("ap sas valid", fp3.is_valid, True)

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("source_dynamics self-test: all checks passed")


if __name__ == "__main__":
    _self_test()
