"""Route and profile check report: where a movement's taxi route and its flight profile disagree on the runway.

Nothing here blocks or changes the calculation. Each line names the route and profile pair, what was found, what
the calculation does about it, and the input change that would make the study realistic (by route name where
another route of the same stand and runway passes). One line per finding; pairs without a finding produce none.

Codes (severity):
  A0 error    arrival route does not meet the runway                   -> touchdown rule still applied
  A1 warning  arrival route meets the runway more than once or runs along it
  A2 error    arrival route meets the runway only before the touchdown (no exit)
  A3 warning  speed at the exit above EXIT_SPEED_LIMIT_KT (50 kt)
  A4 info     exit after the end of the rollout: stretch counted as taxiing
  A5 warning  rollout (after the cut at the exit) runs past the runway end
  T1 warning  Touchdown Offset gives a threshold crossing height outside 12 to 18 m
  D0 error    departure route does not meet the runway                 -> threshold used
  D1 error    lift-off past the runway end (line-up + ground roll > runway length)
  D2 info     line-up more than 300 m from the threshold (intersection take-off)
  D3 info     profile height over the runway end
  C1 info     ADS-B (CUSTOM) movement: start of roll (departure) or runway exit (arrival) more than 150 m from the
              route's line-up or exit; a start in the far half of the runway suggests the runway direction is wrong

Usage: python -m openalaqs_standalone.runway_checks <study.alaqs> <out.csv>
"""

from __future__ import annotations

import sys
from typing import Optional

import pandas as pd

from openalaqs_standalone import compute_movements as cm
from openalaqs_standalone import geometry as geo
from openalaqs_standalone import movements as mv
from openalaqs_standalone import runway_placement as rp

TCH_RANGE_M = (
    12.0,
    18.0,
)  # ICAO Annex 10, 3.1.5.1.4 to 3.1.5.1.6 (15 m +3 m; 12 m for code 1 and 2)
INTERSECTION_INFO_M = 300.0
CUSTOM_TOLERANCE_M = 150.0
COLUMNS = [
    "code",
    "severity",
    "departure_arrival",
    "runway",
    "taxi_route",
    "gate",
    "profile_id",
    "movements",
    "value",
    "message",
    "calculation",
    "suggestion",
]


def _z_at(traj, x: float) -> Optional[float]:
    for a, b in zip(traj, traj[1:]):
        if a[1] <= x <= b[1] and b[1] > a[1]:
            return a[3] + (x - a[1]) / (b[1] - a[1]) * (b[3] - a[3])
    return None


def _liftoff_x(traj) -> Optional[float]:
    for a, b in zip(traj, traj[1:]):
        if a[3] <= rp.GROUND_M < b[3]:
            return a[1] + (rp.GROUND_M - a[3]) * (b[1] - a[1]) / (b[3] - a[3])
    return None


def _first_x_at_or_below(traj, v_kt: float, x0: float = 0.0) -> Optional[float]:
    for a, b in zip(traj, traj[1:]):
        if b[1] < x0 or b[1] <= a[1]:
            continue
        if a[4] / rp.KT <= v_kt and a[1] >= x0:
            return a[1]
        if a[4] / rp.KT > v_kt >= b[4] / rp.KT:
            return a[1] + (a[4] - v_kt * rp.KT) / (a[4] - b[4]) * (b[1] - a[1])
    return None


class _Study:
    def __init__(self, conn):
        self.conn = conn
        self.ctx = cm.build_context(conn)
        self.routes = {
            r[0]: dict(gate=r[1], runway=str(r[2]), ad=r[3])
            for r in conn.execute(
                "SELECT route_name, gate, runway, departure_arrival FROM user_taxiroute_taxiways"
            )
        }
        self._cr, self._parts = {}, {}

    def runway(self, rd, des=None):
        """The runway of end `des` ("06L", "24"), else of the designator number
        `rd` when exactly one runway has that number (None otherwise: a
        plain number on parallel runways, see `movements.runway_of`)."""
        rw = self.ctx["runways"].get(des) if des else None
        if rw is not None:
            return rw
        by_number = {
            id(r): r for r in self.ctx["runways"].values() if rd in r["directions"]
        }
        return next(iter(by_number.values())) if len(by_number) == 1 else None

    def crossings(self, route, rd, des=None):
        key = (route, rd, des)
        if key not in self._cr:
            rw = self.runway(rd, des)
            parts = rp.route_parts_from_study(self.conn, route) if route else None
            self._parts[key] = parts
            self._cr[key] = (
                rp.route_crossings(rp.runway_frame(rw, rd), rw["geom_3857"], parts)
                if parts
                else []
            )
        return self._cr[key]

    def siblings(self, route, ad, rd, des=None):
        r = self.routes.get(route)
        if not r:
            return []
        return [
            n
            for n, q in self.routes.items()
            if n != route
            and q["gate"] == r["gate"]
            and q["ad"] == ad
            and (
                mv.runway_designator(q["runway"]) == des
                if des
                else q["runway"].lstrip("0") == str(rd)
            )
        ]

    def custom_anchor(self, route, rd, des=None):
        rw = self.runway(rd, des)
        parts = rp.route_parts_from_study(self.conn, route) if route else None
        p = None
        if parts:
            from shapely.geometry import MultiLineString

            lines = []
            for g in parts:
                lines.extend(getattr(g, "geoms", [g]))
            p = geo.runway_taxi_intersection_3857(
                rw["geom_3857"], MultiLineString(lines)
            )
        return p if p is not None else geo.runway_threshold_3857(rw, rd)


def _row(code, sev, mov, n, value, message, calc, sugg):
    return dict(
        code=code,
        severity=sev,
        departure_arrival=mov["departure_arrival"],
        runway=mov["runway_direction"],
        taxi_route=mov["taxi_route"],
        gate=mov.get("gate", ""),
        profile_id=mov["profile_id"],
        movements=n,
        value=value,
        message=message,
        calculation=calc,
        suggestion=sugg,
    )


def _arrival_anp(st, mov, traj, n):
    rd, route = mov["runway_direction"], mov["taxi_route"]
    des = mov.get("runway_designator")
    rw = st.runway(rd, des)
    frame = rp.runway_frame(rw, rd)
    out = []
    td, src = rp.arrival_touchdown_distance(rw, rd, traj)
    if src == "runway touchdown offset":
        z = _z_at(traj, -td)
        if z is not None and not (TCH_RANGE_M[0] <= z <= TCH_RANGE_M[1]):
            out.append(
                _row(
                    "T1",
                    "warning",
                    mov,
                    n,
                    round(z, 1),
                    f"Touchdown Offset {td:.0f} m puts this profile {z:.1f} m over the threshold",
                    "offset applied",
                    f"an offset giving 12 to 18 m; the profile's own is "
                    f"{rp.threshold_crossing_distance(traj) or 0:.0f} m",
                )
            )
    cr = st.crossings(route, rd, des)
    roll_end = traj[-1][1]
    if not cr:
        out.append(
            _row(
                "A0",
                "error",
                mov,
                n,
                None,
                "arrival route does not meet the runway",
                "touchdown at the landing threshold + Touchdown Offset (else the profile's "
                "50 ft crossing distance); taxiing starts at the route's first point",
                "fix the route geometry so that it meets the runway centreline",
            )
        )
        return out
    if len(cr) > 1 or any(c["along_runway"] for c in cr):
        out.append(
            _row(
                "A1",
                "warning",
                mov,
                n,
                ";".join(f"{c['s_mid']:.0f}" for c in cr),
                "route meets the runway more than once or runs along it (m from the threshold)",
                "exit = first crossing past the touchdown at or below the exit speed limit",
                "split the route at its exit",
            )
        )
    ex = rp.select_exit(cr, td, traj)

    def passing(cond):
        ok = []
        for s in st.siblings(route, "A", rd, des):
            e = rp.select_exit(st.crossings(s, rd, des), td, traj)
            if e is not None and cond(e):
                ok.append(s)
        return ok

    if ex is None:
        alt = passing(lambda e: True)
        out.append(
            _row(
                "A2",
                "error",
                mov,
                n,
                round(td),
                f"route meets the runway only before the touchdown ({td:.0f} m)",
                "rollout kept whole; taxiing starts at the route's first point",
                (
                    ("routes of the same stand that pass: " + ", ".join(alt))
                    if alt
                    else "check the runway direction, or whether this is a departure route"
                ),
            )
        )
        return out
    if ex["speed_kt"] > rp.EXIT_SPEED_LIMIT_KT:
        x_ok = _first_x_at_or_below(traj, rp.EXIT_SPEED_LIMIT_KT)
        alt = passing(lambda e: e["speed_kt"] <= rp.EXIT_SPEED_LIMIT_KT)
        out.append(
            _row(
                "A3",
                "warning",
                mov,
                n,
                round(ex["speed_kt"], 1),
                f"{ex['speed_kt']:.0f} kt at the exit ({ex['s_m']:.0f} m)",
                "rollout cut at the exit",
                (
                    f"the profile is at or below {rp.EXIT_SPEED_LIMIT_KT:.0f} kt from "
                    f"{td + x_ok:.0f} m"
                    if x_ok is not None
                    else ""
                )
                + (
                    ("; routes of the same stand that pass: " + ", ".join(alt))
                    if alt
                    else ""
                ),
            )
        )
    end_x = min(ex["x_m"], roll_end)
    if ex["x_m"] - roll_end > rp.STRETCH_MIN_M:
        gap = ex["x_m"] - roll_end
        alt = passing(lambda e: roll_end <= e["x_m"] < ex["x_m"])
        out.append(
            _row(
                "A4",
                "info",
                mov,
                n,
                round(gap),
                f"exit {gap:.0f} m after the end of the rollout",
                "runway stretch counted as taxiing",
                ("nearer exits of the same stand: " + ", ".join(alt)) if alt else "",
            )
        )
    if td + end_x > frame.length_m:
        out.append(
            _row(
                "A5",
                "warning",
                mov,
                n,
                round(td + end_x - frame.length_m),
                f"rollout ends {td + end_x - frame.length_m:.0f} m past the runway end",
                "kept",
                "another profile (stage, type) or runway",
            )
        )
    return out


def _departure_anp(st, mov, traj, n):
    rd, route = mov["runway_direction"], mov["taxi_route"]
    des = mov.get("runway_designator")
    frame = rp.runway_frame(st.runway(rd, des), rd)
    cr = st.crossings(route, rd, des)
    if not cr:
        return [
            _row(
                "D0",
                "error",
                mov,
                n,
                None,
                "departure route does not meet the runway",
                "brake release at the threshold",
                "fix the route geometry so that it meets the runway",
            )
        ]
    out = []
    lu = rp.lineup_distance(cr)
    lo = _liftoff_x(traj)
    if lo is not None and lu + lo > frame.length_m:
        fits = []
        for s in st.siblings(route, "D", rd, des):
            l2 = rp.lineup_distance(st.crossings(s, rd, des))
            if l2 is not None and l2 + lo <= frame.length_m:
                fits.append((l2, s))
        out.append(
            _row(
                "D1",
                "error",
                mov,
                n,
                round(lu + lo - frame.length_m),
                f"lift-off {lu + lo - frame.length_m:.0f} m past the runway end (line-up {lu:.0f} m)",
                "kept",
                (
                    ("largest entry that fits: " + max(fits)[1])
                    if fits
                    else "another runway or profile"
                ),
            )
        )
    if lu > INTERSECTION_INFO_M:
        out.append(
            _row(
                "D2",
                "info",
                mov,
                n,
                round(lu),
                f"line-up {lu:.0f} m from the threshold",
                "intersection take-off",
                "",
            )
        )
    z_end = _z_at(traj, frame.length_m - lu)
    if z_end is not None:
        out.append(
            _row(
                "D3",
                "info",
                mov,
                n,
                round(z_end, 1),
                f"{z_end:.1f} m over the runway end",
                "",
                "",
            )
        )
    return out


def _custom(st, mov, traj, n):
    rd, route = mov["runway_direction"], mov["taxi_route"]
    des = mov.get("runway_designator")
    rw = st.runway(rd, des)
    if rw is None or not route:
        return []
    frame = rp.runway_frame(rw, rd)
    anchor = st.custom_anchor(route, rd, des)
    utm = st.ctx["grid_bounds"]["utm_epsg"]

    def s_of(r):
        return rp.along(frame, geo.project_custom(anchor, utm, r[1], r[2]))[0]

    cr = st.crossings(route, rd, des)
    if mov["departure_arrival"] == "D":
        gnd = [r for r in traj if r[3] <= rp.GROUND_M]
        if not gnd or not cr:
            return []
        s_obs, s_route = s_of(gnd[0]), rp.lineup_distance(cr)
        what = "start of roll"
        near = lambda s: rp.lineup_distance(st.crossings(s, rd, des))  # noqa: E731
    else:
        air = [i for i, r in enumerate(traj) if r[3] > rp.GROUND_M]
        gnd = traj[(air[-1] + 1 if air else 0) :]
        if not gnd or not cr:
            return []
        s_obs = s_of(gnd[-1])
        s_td = s_of(gnd[0])
        past = [c for c in cr if c["s_mid"] > s_td] or cr
        s_route = past[0]["s_mid"]
        what = "runway exit"

        def near(s):
            c2 = [c for c in st.crossings(s, rd, des) if c["s_mid"] > s_td]
            return c2[0]["s_mid"] if c2 else None

    if abs(s_obs - s_route) <= CUSTOM_TOLERANCE_M:
        return []
    if mov["departure_arrival"] == "D" and s_obs > frame.length_m / 2:
        sugg = "start of roll in the far half of the runway: check the runway direction"
    else:
        cands = [
            (abs(v - s_obs), s)
            for s in st.siblings(route, mov["departure_arrival"], rd, des)
            for v in [near(s)]
            if v is not None
        ]
        best = min(cands) if cands else None
        sugg = (
            f"route of the same stand that matches: {best[1]}"
            if best and best[0] < abs(s_obs - s_route)
            else "no route of the same stand matches; add one"
        )
    return [
        _row(
            "C1",
            "info",
            mov,
            n,
            round(s_obs - s_route),
            f"ADS-B {what} at {s_obs:.0f} m, route's at {s_route:.0f} m",
            "ADS-B positions kept",
            sugg,
        )
    ]


def check_study(conn) -> pd.DataFrame:
    """The check report for the study's fixed-wing movements (one evaluation per distinct movement setting)."""
    st = _Study(conn)
    groups: dict = {}
    for oid in mv.get_movement_oids(conn):
        m = mv.get_movement(conn, oid)
        if (
            not m
            or not m.get("profile_id")
            or mv.get_helicopter(conn, m["aircraft"]) is not None
        ):
            continue  # helicopters fly their FOCA trajectory at the helipad: no runway placement
        key = (
            m["departure_arrival"],
            m["runway_direction"],
            m["taxi_route"],
            m["profile_id"],
            m.get("runway_designator"),
        )
        groups.setdefault(key, [m, 0])
        groups[key][1] += 1
    rows = []
    for (ad, rd, route, pid, des), (m, n) in sorted(
        groups.items(), key=lambda kv: tuple(map(str, kv[0]))
    ):
        traj = mv.get_trajectory(conn, pid)
        mv.runway_of(st.ctx["runways"], m)  # refuses an ambiguous or unknown end
        if not traj:
            continue
        m = dict(m, gate=st.routes.get(route, {}).get("gate", ""))
        if traj[0][6] == "CUSTOM":
            rows += _custom(st, m, traj, n)
        elif ad == "A":
            rows += _arrival_anp(st, m, traj, n)
        else:
            rows += _departure_anp(st, m, traj, n)
    return pd.DataFrame(rows, columns=COLUMNS)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    conn = mv.connect(argv[0])
    rep = check_study(conn)
    rep.to_csv(argv[1], index=False)
    print(
        rep.groupby(["code", "severity"])
        .movements.agg(["size", "sum"])
        .rename(columns={"size": "pairs", "sum": "movements"})
        .to_string()
        if len(rep)
        else "no findings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
