"""Placement of flight profiles on the runway, shared by the plugin and the standalone (QGIS-free).

Everything works on EPSG:3857 points and shapely geometries; distances along the runway are geodesic (WGS84).
Profile rows are tuples (point, x_m, y_m, z_m, tas_m_s, mode, course), x along the runway in the direction of
travel, x = 0 at the touchdown (arrivals) or the brake release (departures).

Runway frame of a direction: its threshold, the far end, azimuth and length (`frame_from_ends`,
`threshold_points`); `along` gives the distance along the runway from the threshold and the lateral offset of a
point, `point_at` the centreline point at a distance.

Taxi routes: `chain_lines` and `orient_route` put a route's taxiways in the direction of travel (from the stand
for a departure, to the stand for an arrival); `route_crossings` lists where it meets the runway, in that order.

Rules:
* arrival touchdown (`touchdown_distance`): landing threshold + the runway's Touchdown Offset for the direction
  if set, else the profile's own 50 ft (15.24 m, ILS reference datum height) crossing distance;
* arrival exit (`select_exit`): the first crossing past the touchdown at or below EXIT_SPEED_LIMIT_KT (50 kt,
  ICAO Doc 9157 Part 2, 1.3.4), else the first past the touchdown; the profile is cut there when the exit comes
  first (`truncate_after`); an exit past the rollout end leaves a runway stretch that is taxiing
  (`stretch_time_s`: 2 L / (v_end + v_x), v_x = min(v_end, 18 kt)), sharing the movement's taxi time with the
  route (`split_taxi_time`);
* landing roll (`rollout_duration_s`): the arrival runway time is the touchdown, so the roll is taken out of
  block - runway time;
* departure brake release (`lineup_distance`): where the route last meets the runway in the direction of travel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pyproj
from shapely.geometry import LineString, Point

GEOD = pyproj.Geod(ellps="WGS84")
TO_WGS84 = pyproj.Transformer.from_crs(3857, 4326, always_xy=True)
TO_3857 = pyproj.Transformer.from_crs(4326, 3857, always_xy=True)
RUNWAY_BUFFER_M = (
    1.0  # runway centreline buffer for taxi-route intersections (plugin and standalone)
)

MERGE_GAP_M = 5.0
ALONG_RUNWAY_M = 30.0


@dataclass(frozen=True)
class RunwayFrame:
    runway_direction: int
    threshold_3857: tuple
    far_end_3857: tuple
    threshold_lonlat: tuple
    azimuth_deg: float
    length_m: float


def bearing_deg(p1_3857, p2_3857) -> float:
    """Geodesic bearing (degrees, 0 to 360) from p1 to p2 (EPSG:3857 points)."""
    a = TO_WGS84.transform(*p1_3857)
    b = TO_WGS84.transform(*p2_3857)
    return GEOD.inv(a[0], a[1], b[0], b[1])[0] % 360.0


def threshold_points(pt1_3857, pt2_3857, directions) -> dict:
    """{designator: threshold point} for a runway drawn from pt1 to pt2: the designator whose nominal heading
    (designator x 10 degrees) is nearer the bearing pt1 -> pt2 has its threshold at pt1.
    """
    az = bearing_deg(pt1_3857, pt2_3857)
    diffs = {
        d: min(abs(az - (d * 10) % 360), 360 - abs(az - (d * 10) % 360))
        for d in directions
    }
    start = min(diffs, key=diffs.get)
    other = [d for d in directions if d != start]
    out = {start: tuple(pt1_3857)}
    if other:
        out[other[0]] = tuple(pt2_3857)
    return out


def frame_from_ends(runway_direction: int, threshold_3857, far_end_3857) -> RunwayFrame:
    """The runway frame of one direction from its threshold and the far end (EPSG:3857)."""
    thr_ll = TO_WGS84.transform(*threshold_3857)
    far_ll = TO_WGS84.transform(*far_end_3857)
    az, _, length = GEOD.inv(thr_ll[0], thr_ll[1], far_ll[0], far_ll[1])
    return RunwayFrame(
        runway_direction,
        tuple(threshold_3857),
        tuple(far_end_3857),
        tuple(thr_ll),
        az % 360.0,
        length,
    )


def along(frame: RunwayFrame, p_3857) -> tuple:
    lon, lat = TO_WGS84.transform(p_3857[0], p_3857[1])
    if (lon, lat) == frame.threshold_lonlat:
        return 0.0, 0.0
    az, _, d = GEOD.inv(frame.threshold_lonlat[0], frame.threshold_lonlat[1], lon, lat)
    a = math.radians(az - frame.azimuth_deg)
    return d * math.cos(a), d * math.sin(a)


def point_at(frame: RunwayFrame, s: float) -> tuple:
    az = frame.azimuth_deg if s >= 0 else (frame.azimuth_deg + 180.0) % 360.0
    lon, lat, _ = GEOD.fwd(
        frame.threshold_lonlat[0], frame.threshold_lonlat[1], az, abs(s)
    )
    return TO_3857.transform(lon, lat)


def _pieces(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, (LineString, Point)):
        return [geom]
    out = []
    for g in getattr(geom, "geoms", []):
        out.extend(_pieces(g))
    return out


def route_crossings(frame: RunwayFrame, runway_geom_3857, route_parts) -> list:
    """Crossings of a taxi route with the runway, in route order.

    `route_parts`: the route's taxiway geometries (EPSG:3857 LineStrings or MultiLineStrings) in the order of
    the route sequence. Each crossing is a dict with s_min, s_max, s_mid (m along the runway), point_3857 (the
    centreline point at s_mid), order (position along the route, for ordering) and along_runway (True when the
    route runs along the runway for more than ALONG_RUNWAY_M)."""
    buf = runway_geom_3857.buffer(RUNWAY_BUFFER_M, quad_segs=10)
    raw = []
    offset = 0.0
    for part in route_parts:
        for line in _pieces(part):
            for piece in _pieces(buf.intersection(line)):
                coords = (
                    list(piece.coords)
                    if not isinstance(piece, Point)
                    else [piece.coords[0]]
                )
                ss = [along(frame, c)[0] for c in coords]
                pos = [line.project(Point(c)) for c in coords]
                raw.append(
                    dict(
                        order=offset + line.project(piece.centroid),
                        s_min=min(ss),
                        s_max=max(ss),
                        s_end=ss[max(range(len(ss)), key=pos.__getitem__)],
                    )
                )
            offset += line.length
    raw.sort(key=lambda r: r["order"])
    merged = []
    for r in raw:
        if (
            merged
            and r["s_min"] <= merged[-1]["s_max"] + MERGE_GAP_M
            and r["s_max"] >= merged[-1]["s_min"] - MERGE_GAP_M
        ):
            m = merged[-1]
            m["s_min"], m["s_max"] = min(m["s_min"], r["s_min"]), max(
                m["s_max"], r["s_max"]
            )
            m["s_end"] = r["s_end"]
        else:
            merged.append(dict(r))
    for m in merged:
        m["s_mid"] = 0.5 * (m["s_min"] + m["s_max"])
        m["point_3857"] = point_at(frame, m["s_mid"])
        m["along_runway"] = (m["s_max"] - m["s_min"]) > ALONG_RUNWAY_M
    return merged


THRESHOLD_CROSSING_HEIGHT_M = (
    50 * 0.3048
)  # ILS reference datum height (ICAO Annex 10, 3.1.5.1.4): 15 m


def threshold_crossing_distance(traj) -> Optional[float]:
    """Distance (m) from the threshold to the touchdown implied by an arrival profile: minus the x where the
    profile last descends through 50 ft (Doc 29 approach profiles have x = 0 at the touchdown). None if the
    profile never descends through 50 ft. `traj` rows: (point, x_m, y_m, z_m, tas, mode, course).
    """
    h = THRESHOLD_CROSSING_HEIGHT_M
    found = None
    for a, b in zip(traj, traj[1:]):
        x1, z1, x2, z2 = a[1], a[3], b[1], b[3]
        if z1 >= h > z2:
            found = x1 + (h - z1) * (x2 - x1) / (z2 - z1)
    return None if found is None else -found


def touchdown_distance(offset_m, traj) -> tuple:
    """(distance from the landing threshold to the touchdown in m, source) for an ANP arrival.

    The runway's Touchdown Offset for this landing direction when set (> 0); else the profile's own threshold
    crossing distance; else 0 (touchdown at the threshold) when the profile has no 50 ft crossing.
    """
    offset = float(offset_m or 0.0)
    if offset > 0:
        return float(offset), "runway touchdown offset"
    d = threshold_crossing_distance(traj)
    if d is not None and d >= 0:
        return d, "profile 50 ft crossing"
    return 0.0, "threshold (profile has no 50 ft crossing)"


KT = 0.514444
EXIT_SPEED_LIMIT_KT = 50.0  # rapid-exit reference speed, code 3 and 4 (ICAO Doc 9157 Part 2, 1.3.4: 93 km/h)


def speed_at(traj, x: float) -> float:
    """Profile TAS (m/s) at profile distance x, linear between points; 0 beyond the last point."""
    for a, b in zip(traj, traj[1:]):
        if a[1] <= x <= b[1] and b[1] > a[1]:
            return a[4] + (x - a[1]) / (b[1] - a[1]) * (b[4] - a[4])
    return float(traj[-1][4]) if traj and abs(x - traj[-1][1]) < 1e-9 else 0.0


def select_exit(
    crossings: list, touchdown_m: float, traj, v_limit_kt: float = EXIT_SPEED_LIMIT_KT
):
    """The arrival's runway exit among a route's crossings: the first crossing past the touchdown where the
    profile is at or below v_limit_kt; if none is, the first crossing past the touchdown. None if the route
    does not meet the runway past the touchdown. Returns dict(s_m, x_m, speed_kt, rule).
    """
    past = [c for c in crossings if c["s_mid"] > touchdown_m]
    if not past:
        return None
    for c in past:
        v = speed_at(traj, c["s_mid"] - touchdown_m) / KT
        if v <= v_limit_kt:
            return dict(
                s_m=c["s_mid"],
                x_m=c["s_mid"] - touchdown_m,
                speed_kt=v,
                rule="first crossing at or below the limit",
            )
    c = past[0]
    return dict(
        s_m=c["s_mid"],
        x_m=c["s_mid"] - touchdown_m,
        speed_kt=speed_at(traj, c["s_mid"] - touchdown_m) / KT,
        rule="first crossing past the touchdown (above the limit)",
    )


def truncate_after(traj, x_cut: float) -> list:
    """Profile rows up to profile distance x_cut; the segment that straddles x_cut ends there (x, z and TAS
    interpolated; the new end row keeps the point index of the segment start, which only matters for a segment
    start, and this row is the last). A cut exactly on a profile row ends at that row (no zero-length end
    segment)."""
    out = []
    for a, b in zip(traj, traj[1:]):
        out.append(a)
        if b[1] > x_cut >= a[1]:
            if x_cut == a[1]:
                return out
            f = (x_cut - a[1]) / (b[1] - a[1])
            out.append(
                (
                    a[0],
                    x_cut,
                    a[2] + f * (b[2] - a[2]),
                    a[3] + f * (b[3] - a[3]),
                    a[4] + f * (b[4] - a[4]),
                    a[5],
                    a[6],
                )
            )
            return out
    out.append(traj[-1])
    return out


STRETCH_EXIT_SPEED_KT = 18.0  # speed where arrivals leave the runway: median 18 kt over 79 flights (1 s ADS-B tracks)
STRETCH_MIN_M = 0.5


def stretch_time_s(
    length_m: float, v_end_ms: float, v_exit_kt: float = STRETCH_EXIT_SPEED_KT
) -> float:
    """Time (s) to roll length_m from the rollout-end speed v_end_ms to the exit speed min(v_end, v_exit_kt),
    at constant deceleration: 2 L / (v_end + v_x), the rule used between profile points. A profile that ends
    at rest rolls the stretch at v_exit_kt."""
    if length_m <= 0:
        return 0.0
    v_x = v_exit_kt * KT
    if v_end_ms <= 0:
        return length_m / v_x
    v_x = min(v_end_ms, v_x)
    return 2.0 * length_m / (v_end_ms + v_x)


def split_taxi_time(total_s: float, route_s: float, stretch_s: float) -> tuple:
    """(route time, stretch time, queuing time) for a movement with total taxi time total_s.

    The route and the runway stretch keep their own times when they fit and the rest is queuing; when they do
    not fit, both are scaled down to the total (as the route alone is today) and there is no queuing. A
    negative total counts as 0 s.
    """
    total_s = max(0.0, total_s)
    need = route_s + stretch_s
    if need <= 0:
        return 0.0, 0.0, max(0.0, total_s)
    if need <= total_s:
        return route_s, stretch_s, total_s - need
    k = total_s / need
    return route_s * k, stretch_s * k, 0.0


GROUND_M = 0.5


def rollout_duration_s(traj) -> float:
    """Time (s) of the profile's landing roll: the rows after the last airborne row (z above GROUND_M), at
    the mean TAS of each step (the rule used for profile segments). 0 if the profile ends in the air.
    """
    last_air = max((i for i, r in enumerate(traj) if r[3] > GROUND_M), default=-1)
    t = 0.0
    for a, b in zip(traj[last_air + 1 :], traj[last_air + 2 :]):
        v = 0.5 * (a[4] + b[4])
        if v > 0:
            t += math.hypot(b[1] - a[1], b[2] - a[2]) / v
    return t


def lineup_distance(crossings: list) -> Optional[float]:
    """Departure brake release (line-up point): where the route last meets the runway, in route order. For a
    crossing that runs along the runway (backtracking) this is where the route leaves it, i.e. the turn onto
    the runway heading; for an ordinary crossing the centreline point. None if the route never meets it.
    """
    if not crossings:
        return None
    c = crossings[-1]
    return c["s_end"] if c["along_runway"] else c["s_mid"]


def chain_lines(parts) -> list:
    """The route's pieces as LineStrings in sequence order, each drawn in the direction of travel: a taxiway
    may be digitised either way, so each piece is turned to start where the previous one ends (the first is
    turned to end next to the second)."""
    lines = []
    for g in parts:
        lines.extend(
            x for x in _pieces(g) if isinstance(x, LineString) and len(x.coords) >= 2
        )
    if len(lines) < 2:
        return lines
    out = []
    for i, ln in enumerate(lines):
        a, b = Point(ln.coords[0]), Point(ln.coords[-1])
        if i == 0:
            nxt = lines[1]
            flip = min(
                a.distance(Point(nxt.coords[0])), a.distance(Point(nxt.coords[-1]))
            ) < min(b.distance(Point(nxt.coords[0])), b.distance(Point(nxt.coords[-1])))
        else:
            end = Point(out[-1].coords[-1])
            flip = b.distance(end) < a.distance(end)
        out.append(LineString(list(ln.coords)[::-1]) if flip else ln)
    return out


def orient_route(lines: list, gate_geom, start_at_gate: bool) -> list:
    """The route in the direction of travel: from the stand for a departure (start_at_gate), towards it for an
    arrival. Routes may be listed either way in user_taxiroute_taxiways; the end nearer the stand decides.
    Unchanged when the stand is unknown."""
    if not lines or gate_geom is None or gate_geom.is_empty:
        return lines
    d_first = gate_geom.distance(Point(lines[0].coords[0]))
    d_last = gate_geom.distance(Point(lines[-1].coords[-1]))
    if (start_at_gate and d_first > d_last) or (not start_at_gate and d_first < d_last):
        return [LineString(list(ln.coords)[::-1]) for ln in reversed(lines)]
    return lines


__all__ = [
    "RunwayFrame",
    "bearing_deg",
    "threshold_points",
    "frame_from_ends",
    "along",
    "point_at",
    "route_crossings",
    "chain_lines",
    "orient_route",
    "lineup_distance",
    "threshold_crossing_distance",
    "touchdown_distance",
    "speed_at",
    "select_exit",
    "truncate_after",
    "stretch_time_s",
    "split_taxi_time",
    "rollout_duration_s",
    "THRESHOLD_CROSSING_HEIGHT_M",
    "EXIT_SPEED_LIMIT_KT",
    "STRETCH_EXIT_SPEED_KT",
    "STRETCH_MIN_M",
    "GROUND_M",
    "KT",
    "MERGE_GAP_M",
    "ALONG_RUNWAY_M",
    "RUNWAY_BUFFER_M",
    "GEOD",
    "TO_WGS84",
    "TO_3857",
]
