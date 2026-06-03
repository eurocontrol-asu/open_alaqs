"""
Per-category helicopter LTO trajectory generator.

Builds 3D trajectories (x, y, z in meters) for the departure and arrival
halves of an LTO, scaled per helicopter category.

Source data for per-category parameters is documented in
documents/TRAJECTORY_DATA_SOURCES.md. Core summary:

  - PISTON (R22):           500 ft/min climb at 60 kt,  75 kt cruise
  - SINGLE_TURBOSHAFT:     1000 ft/min climb at 60 kt, 120 kt cruise (FOCA Appx A)
  - TWIN_TURBOSHAFT_LIGHT: 1500 ft/min climb at 80 kt, 150 kt cruise
  - TWIN_TURBOSHAFT_HEAVY: 1920 ft/min climb at 70 kt, 139 kt cruise (AS332L1 manual)

LTO ceiling is 3000 ft AGL (ICAO LTO definition).

Coordinates are produced in a local metric frame (x along track, y
lateral, z AGL). The caller applies translation to the airport origin
and rotation to the runway heading. Both helpers are provided
(translate_and_rotate).
"""

import math
from dataclasses import dataclass
from typing import Optional

from open_alaqs.core.tools.foca_heli import HelicopterCategory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FT_PER_M = 3.28084
M_PER_FT = 1.0 / FT_PER_M
KT_TO_MS = 0.514444
M_PER_NM = 1852.0

LTO_CEILING_FT = 3000.0
LTO_CEILING_M = LTO_CEILING_FT * M_PER_FT

HOVER_ALT_FT = 5.0  # hover IGE altitude
HOVER_ALT_M = HOVER_ALT_FT * M_PER_FT

HOVER_DURATION_S = 18.0  # From Appendix A — assumed universal


# ---------------------------------------------------------------------------
# Per-category trajectory parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryParams:
    """Category-specific flight parameters for trajectory building.

    See documents/TRAJECTORY_DATA_SOURCES.md for per-field citations.
    """

    climb_roc_fpm: float  # rate of climb during TO mode
    climb_tas_kt: float  # climb TAS
    cruise_tas_kt: float  # reference cruise TAS
    approach_tas_initial_kt: float
    approach_tas_final_kt: float
    approach_rod_initial_fpm: float
    approach_rod_final_fpm: float
    approach_start_nm: float  # horizontal distance at start of approach


TRAJECTORY_PARAMS: dict[HelicopterCategory, TrajectoryParams] = {
    "PISTON": TrajectoryParams(
        climb_roc_fpm=500.0,
        climb_tas_kt=60.0,
        cruise_tas_kt=75.0,
        approach_tas_initial_kt=60.0,
        approach_tas_final_kt=30.0,
        approach_rod_initial_fpm=500.0,
        approach_rod_final_fpm=250.0,
        approach_start_nm=5.0,
    ),
    "SINGLE_TURBOSHAFT": TrajectoryParams(
        climb_roc_fpm=1000.0,  # FOCA Appendix A
        climb_tas_kt=60.0,  # FOCA Appendix A
        cruise_tas_kt=120.0,  # FOCA section 2.1 example
        approach_tas_initial_kt=60.0,  # FOCA Appendix A DCT row
        approach_tas_final_kt=30.0,
        approach_rod_initial_fpm=700.0,  # FOCA Appendix A
        approach_rod_final_fpm=250.0,
        approach_start_nm=5.0,
    ),
    "TWIN_TURBOSHAFT_LIGHT": TrajectoryParams(
        climb_roc_fpm=1500.0,
        climb_tas_kt=80.0,
        cruise_tas_kt=150.0,
        approach_tas_initial_kt=80.0,
        approach_tas_final_kt=40.0,
        approach_rod_initial_fpm=700.0,
        approach_rod_final_fpm=300.0,
        approach_start_nm=6.0,
    ),
    "TWIN_TURBOSHAFT_HEAVY": TrajectoryParams(
        climb_roc_fpm=1920.0,  # AS332L1 Technical Data ROC at 8000 kg, 70 kt
        climb_tas_kt=70.0,  # AS332L1 Technical Data Vy
        cruise_tas_kt=139.0,  # AS332L1 Technical Data rec. cruise at 8000 kg
        approach_tas_initial_kt=70.0,
        approach_tas_final_kt=40.0,
        approach_rod_initial_fpm=700.0,
        approach_rod_final_fpm=300.0,
        approach_start_nm=7.0,
    ),
}


# ---------------------------------------------------------------------------
# Trajectory point
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryPoint:
    """One point on a helicopter LTO trajectory, local metric frame.

    x: along-track ground distance (m) from takeoff/landing spot
    y: lateral offset (m), 0 for centerline
    z: altitude above ground level (m)
    tas_m_s: true airspeed at this point (m/s)
    mode: one of "GI", "GR", "HOV", "CL", "CR", "DESC", "FINAL", "TOUCH"
    t_s: elapsed time from start of half-LTO (s)
    """

    x_m: float
    y_m: float
    z_m: float
    tas_m_s: float
    mode: str
    t_s: float


# ---------------------------------------------------------------------------
# Departure trajectory builder
# ---------------------------------------------------------------------------


def build_departure(category: HelicopterCategory) -> list[TrajectoryPoint]:
    """Build the departure half-LTO trajectory for a category.

    Segment sequence:
        GI  (5 min × GI_DEPARTURE_FRACTION = 4 min): at stand, no motion
        HOV (18 s at HOVER_ALT_M): hover IGE
        CL  (TO mode): climb at climb_roc, climb_tas, until LTO ceiling
        CR  (remaining TO time, if any): level flight at cruise TAS

    Note: if the TO time-in-mode is less than the time needed to reach
    the LTO ceiling at climb_roc, we stop at whatever altitude the
    helicopter has actually reached. Emissions math is unaffected
    (TO time-in-mode × TO_FF × EI); only trajectory shape changes.
    """
    from open_alaqs.core.tools.foca_heli import (
        GI_DEPARTURE_FRACTION,
        PROFILES,
    )

    params = TRAJECTORY_PARAMS[category]
    profile = PROFILES[category]

    points: list[TrajectoryPoint] = []
    t = 0.0

    # GI: 4 min at origin (80% of 5 min)
    gi_dep_s = profile.gi_time_min * 60.0 * GI_DEPARTURE_FRACTION
    points.append(TrajectoryPoint(0.0, 0.0, 0.0, 0.0, "GI", t))
    t += gi_dep_s
    points.append(TrajectoryPoint(0.0, 0.0, 0.0, 0.0, "GI", t))

    # HOV: hover at 5 ft AGL for 18 s
    t += HOVER_DURATION_S
    points.append(TrajectoryPoint(0.0, 0.0, HOVER_ALT_M, 0.0, "HOV", t))

    # CL: climb at climb_roc + climb_tas until LTO ceiling or TO time expires
    roc_ms = params.climb_roc_fpm * M_PER_FT / 60.0
    tas_ms = params.climb_tas_kt * KT_TO_MS

    to_time_s = profile.to_time_min * 60.0
    climb_dz = LTO_CEILING_M - HOVER_ALT_M
    time_to_ceiling_s = climb_dz / roc_ms

    if time_to_ceiling_s <= to_time_s:
        # Reach ceiling within TO mode time
        climb_x = tas_ms * time_to_ceiling_s
        t += time_to_ceiling_s
        points.append(TrajectoryPoint(climb_x, 0.0, LTO_CEILING_M, tas_ms, "CL", t))

        # CR: remaining TO time at cruise altitude, cruise TAS
        cruise_ms = params.cruise_tas_kt * KT_TO_MS
        cruise_time_s = to_time_s - time_to_ceiling_s
        if cruise_time_s > 0:
            cruise_x = climb_x + cruise_ms * cruise_time_s
            t += cruise_time_s
            points.append(
                TrajectoryPoint(cruise_x, 0.0, LTO_CEILING_M, cruise_ms, "CR", t)
            )
    else:
        # Can't reach ceiling within TO time — climb what we can
        climb_dz_actual = roc_ms * to_time_s
        climb_x = tas_ms * to_time_s
        final_z = HOVER_ALT_M + climb_dz_actual
        t += to_time_s
        points.append(TrajectoryPoint(climb_x, 0.0, final_z, tas_ms, "CL", t))

    return points


# ---------------------------------------------------------------------------
# Arrival trajectory builder
# ---------------------------------------------------------------------------


def build_arrival(category: HelicopterCategory) -> list[TrajectoryPoint]:
    """Build the arrival half-LTO trajectory for a category.

    Segment sequence (chronological, origin = touchdown spot):
        CR    (initial segment): level flight at LTO ceiling inbound
        DESC  (initial descent): descent at approach_tas_initial,
              approach_rod_initial
        FINAL (final descent): slower descent at approach_tas_final,
              approach_rod_final, down to hover alt
        HOV   (18 s): hover IGE
        TOUCH (instant): touchdown at origin
        GI    (1 min = 20% of 5 min): at stand

    Coordinates: x increases from touchdown (0) outbound. The helicopter
    starts far from origin (high x) and moves toward origin (x=0).
    """
    from open_alaqs.core.tools.foca_heli import (
        GI_ARRIVAL_FRACTION,
        PROFILES,
    )

    params = TRAJECTORY_PARAMS[category]
    profile = PROFILES[category]

    ap_time_s = profile.ap_time_min * 60.0

    tas_init_ms = params.approach_tas_initial_kt * KT_TO_MS
    tas_final_ms = params.approach_tas_final_kt * KT_TO_MS
    rod_init_ms = params.approach_rod_initial_fpm * M_PER_FT / 60.0
    rod_final_ms = params.approach_rod_final_fpm * M_PER_FT / 60.0

    # Determine DESC and FINAL time allocation.
    # Strategy: final segment descends from some breakpoint altitude
    # (call it FINAL_START_ALT) to hover alt at slow TAS + slow ROD.
    # DESC segment descends from LTO ceiling to FINAL_START_ALT at
    # faster TAS + faster ROD. Break at 500 ft AGL (typical final).
    FINAL_BREAK_ALT_FT = 500.0
    FINAL_BREAK_ALT_M = FINAL_BREAK_ALT_FT * M_PER_FT

    # Segment altitude drops
    desc_dz = LTO_CEILING_M - FINAL_BREAK_ALT_M
    final_dz = FINAL_BREAK_ALT_M - HOVER_ALT_M

    # Segment times
    desc_time_s = desc_dz / rod_init_ms
    final_time_s = final_dz / rod_final_ms

    # If total descent time exceeds AP time budget, scale both segments
    # proportionally to fit. If it's less, the remainder goes to an
    # extra CR level-flight segment before DESC starts.
    total_descent_time_s = desc_time_s + final_time_s
    if total_descent_time_s > ap_time_s:
        scale = ap_time_s / total_descent_time_s
        desc_time_s *= scale
        final_time_s *= scale
        # ROD is unchanged (the helicopter still descends at published rates);
        # what changes is the starting altitude. Reset: the helicopter only
        # has ap_time_s to descend total. Recompute dz per segment.
        desc_dz_actual = rod_init_ms * desc_time_s
        rod_final_ms * final_time_s
        cr_time_s = 0.0
    else:
        desc_dz_actual = desc_dz
        cr_time_s = ap_time_s - total_descent_time_s

    # Segment horizontal extents
    desc_dx = tas_init_ms * desc_time_s
    final_dx = tas_final_ms * final_time_s
    cr_dx = tas_init_ms * cr_time_s  # level flight uses initial TAS

    # Build waypoints. Start at x = (cr_dx + desc_dx + final_dx), work inward.
    start_x = cr_dx + desc_dx + final_dx
    cr_end_x = desc_dx + final_dx
    desc_end_x = final_dx
    final_end_x = 0.0

    # Altitudes at each waypoint
    z_cr_end = LTO_CEILING_M
    z_desc_end = z_cr_end - desc_dz_actual
    z_final_end = HOVER_ALT_M

    points: list[TrajectoryPoint] = []
    t = 0.0

    # CR inbound (only if there's time allocated to it)
    if cr_time_s > 0:
        points.append(
            TrajectoryPoint(start_x, 0.0, LTO_CEILING_M, tas_init_ms, "CR", t)
        )
        t += cr_time_s
        points.append(TrajectoryPoint(cr_end_x, 0.0, z_cr_end, tas_init_ms, "CR", t))
    else:
        points.append(
            TrajectoryPoint(start_x, 0.0, LTO_CEILING_M, tas_init_ms, "DESC", t)
        )

    # DESC segment
    t += desc_time_s
    points.append(TrajectoryPoint(desc_end_x, 0.0, z_desc_end, tas_init_ms, "DESC", t))

    # FINAL segment
    t += final_time_s
    points.append(
        TrajectoryPoint(final_end_x, 0.0, z_final_end, tas_final_ms, "FINAL", t)
    )

    # HOV
    t += HOVER_DURATION_S
    points.append(TrajectoryPoint(0.0, 0.0, HOVER_ALT_M, 0.0, "HOV", t))

    # TOUCH (instant transition to ground)
    points.append(TrajectoryPoint(0.0, 0.0, 0.0, 0.0, "TOUCH", t))

    # GI at stand (20% of 5 min = 1 min)
    gi_arr_s = profile.gi_time_min * 60.0 * GI_ARRIVAL_FRACTION
    t += gi_arr_s
    points.append(TrajectoryPoint(0.0, 0.0, 0.0, 0.0, "GI", t))

    return points


# ---------------------------------------------------------------------------
# Frame transforms
# ---------------------------------------------------------------------------


def translate_and_rotate(
    points: list[TrajectoryPoint],
    origin_x_m: float = 0.0,
    origin_y_m: float = 0.0,
    heading_deg: float = 0.0,
) -> list[TrajectoryPoint]:
    """Translate to an airport origin and rotate to a runway heading.

    heading_deg is the compass heading of the helicopter's outbound
    direction in degrees (0 = north, 90 = east). The local frame's
    +x axis is rotated to match this heading.
    """
    hdg_rad = math.radians(heading_deg)
    cos_h = math.cos(hdg_rad)
    sin_h = math.sin(hdg_rad)

    out = []
    for p in points:
        # Rotate (x_local, y_local) by heading: compass heading of 0 means
        # +x_local maps to +north; heading 90 means +x_local maps to +east.
        # Standard math convention (CCW from +x axis) differs from compass
        # (CW from north), so adjust: compass_x = sin(hdg) * x - cos(hdg) * y
        # (compass_x = east, compass_y = north).
        # But for consistency with GIS conventions, we'll treat +x as east
        # and +y as north, so:
        new_x = sin_h * p.x_m + cos_h * p.y_m + origin_x_m
        new_y = cos_h * p.x_m - sin_h * p.y_m + origin_y_m
        out.append(
            TrajectoryPoint(
                x_m=new_x,
                y_m=new_y,
                z_m=p.z_m,
                tas_m_s=p.tas_m_s,
                mode=p.mode,
                t_s=p.t_s,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def to_wkt_linestring_2d(points: list[TrajectoryPoint]) -> str:
    """Export a trajectory as a 2D WKT LINESTRING (discards altitude)."""
    coords = ", ".join(f"{p.x_m:.3f} {p.y_m:.3f}" for p in points)
    return f"LINESTRING ({coords})"


def to_wkt_linestring_z(points: list[TrajectoryPoint]) -> str:
    """Export a trajectory as a 3D WKT LINESTRING Z."""
    coords = ", ".join(f"{p.x_m:.3f} {p.y_m:.3f} {p.z_m:.3f}" for p in points)
    return f"LINESTRING Z ({coords})"


def to_geojson_feature(
    points: list[TrajectoryPoint],
    properties: Optional[dict] = None,
) -> dict:
    """Export a trajectory as a GeoJSON Feature (LineString geometry, 3D)."""
    coords = [[p.x_m, p.y_m, p.z_m] for p in points]
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
        "properties": properties or {},
    }
