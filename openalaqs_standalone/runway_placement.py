"""Runway placement for the standalone: the shared rules of `open_alaqs.core.tools.runway_placement` (also used
by the plugin), with adapters for the standalone's runway dicts and study connection.

* `runway_frame(runway, runway_direction)`: the frame of a direction from a `movements.get_runways` runway dict.
* `arrival_touchdown_distance(runway, runway_direction, traj)`: touchdown distance with the runway's Touchdown
  Offset for that direction (`touchdown_offset_m`).
* `route_parts_from_study(conn, route_name)`: the route's taxiways in the direction of travel.
Everything else (crossings, exit, cut, stretch, landing roll, line-up) is the shared module; see its docstring.
"""

from __future__ import annotations

from typing import Optional

from open_alaqs.core.tools.runway_placement import *  # noqa: F401,F403
from open_alaqs.core.tools.runway_placement import RunwayFrame  # noqa: F401
from open_alaqs.core.tools.runway_placement import __all__ as _shared_all
from open_alaqs.core.tools.runway_placement import (  # noqa: F401
    chain_lines,
    frame_from_ends,
    orient_route,
    touchdown_distance,
)
from openalaqs_standalone import geometry as geo


def runway_frame(runway: dict, runway_direction: int) -> RunwayFrame:
    thr = geo.runway_threshold_3857(runway, runway_direction)
    other = [d for d in runway["directions"] if d != runway_direction]
    far = (
        geo.runway_threshold_3857(runway, other[0])
        if other
        else (runway["pt2_3857"] if thr == runway["pt1_3857"] else runway["pt1_3857"])
    )
    return frame_from_ends(runway_direction, thr, far)


def arrival_touchdown_distance(runway: dict, runway_direction: int, traj) -> tuple:
    """(touchdown distance from the landing threshold in m, source): the runway's Touchdown Offset for this
    direction if set, else the profile's own 50 ft crossing distance (shared `touchdown_distance`).
    """
    return touchdown_distance(
        (runway.get("touchdown_offset_m") or {}).get(runway_direction, 0.0), traj
    )


def route_parts_from_study(conn, route_name: str) -> Optional[list]:
    """The route's taxiway geometries (EPSG:3857 LineStrings) in the direction of travel: sequence order, each
    piece turned to follow on from the previous one, and the whole route turned to start at the stand for a
    departure route and at the runway for an arrival route. None if the route is unknown.
    """
    row = conn.execute(
        "SELECT sequence, gate, departure_arrival FROM user_taxiroute_taxiways WHERE route_name=?",
        (route_name,),
    ).fetchone()
    if not row or not row[0]:
        return None
    parts = []
    for name in row[0].split(","):
        sub = conn.execute(
            "SELECT geometry FROM shapes_taxiways WHERE taxiway_id=?", (name.strip(),)
        ).fetchone()
        if sub and sub[0]:
            g = geo.spatialite_blob_to_shapely(sub[0])
            if g is not None:
                parts.append(g)
    if not parts:
        return None
    gate = None
    if row[1]:
        g = conn.execute(
            "SELECT geometry FROM shapes_gates WHERE gate_id=?", (row[1],)
        ).fetchone()
        gate = geo.spatialite_blob_to_shapely(g[0]) if g and g[0] else None
    return orient_route(
        chain_lines(parts), gate, start_at_gate=str(row[2]).upper().startswith("D")
    )


__all__ = list(_shared_all) + [
    "runway_frame",
    "arrival_touchdown_distance",
    "route_parts_from_study",
]
