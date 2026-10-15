"""Runway frame and taxi-route crossings (openalaqs_standalone.runway_placement), on a synthetic runway."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString

from openalaqs_standalone import geometry as geo
from openalaqs_standalone import runway_placement as rp

LON0, LAT0, AZ, LEN = (
    4.4370,
    51.9500,
    60.0,
    2200.0,
)  # runway "06/24": 06 threshold at (LON0, LAT0)


def _pt(s, x=0.0):
    """EPSG:3857 point s metres along the runway from the 06 threshold and x metres to the right."""
    lon, lat, _ = geo.GEOD.fwd(LON0, LAT0, AZ, s)
    if x:
        lon, lat, _ = geo.GEOD.fwd(lon, lat, (AZ + 90.0) % 360.0, x)
    return geo.TO_3857.transform(lon, lat)


@pytest.fixture
def runway():
    p1, p2 = _pt(0.0), _pt(LEN)
    return {
        "runway_id": "06/24",
        "geom_3857": LineString([p1, p2]),
        "pt1_3857": p1,
        "pt2_3857": p2,
        "directions": [6, 24],
    }


def test_frame(runway):
    f06 = rp.runway_frame(runway, 6)
    f24 = rp.runway_frame(runway, 24)
    assert f06.length_m == pytest.approx(LEN, abs=0.01)
    assert f06.azimuth_deg == pytest.approx(AZ, abs=0.01)
    assert f24.azimuth_deg == pytest.approx((f06.azimuth_deg + 180.0) % 360.0, abs=0.05)
    s, x = rp.along(f06, _pt(700.0, 25.0))
    assert s == pytest.approx(700.0, abs=0.05) and x == pytest.approx(25.0, abs=0.05)
    s24, _ = rp.along(f24, _pt(700.0))
    assert s24 == pytest.approx(LEN - 700.0, abs=0.05)
    assert rp.along(f06, rp.point_at(f06, 1234.0))[0] == pytest.approx(1234.0, abs=0.01)


def test_single_crossing(runway):
    f = rp.runway_frame(runway, 6)
    route = [
        LineString([_pt(1200.0, -200.0), _pt(1200.0, 0.0)]),
        LineString([_pt(1200.0, 0.0), _pt(1300.0, 150.0)]),
    ]
    c = rp.route_crossings(f, runway["geom_3857"], route)
    assert len(c) == 1  # the two parts meeting on the centreline are one crossing
    assert c[0]["s_mid"] == pytest.approx(1200.0, abs=1.5) and not c[0]["along_runway"]


def test_two_crossings_in_route_order(runway):
    f = rp.runway_frame(runway, 6)
    route = [
        LineString(
            [
                _pt(1444.0, 0.0),
                _pt(1500.0, 150.0),
                _pt(450.0, 150.0),
                _pt(350.0, -150.0),
                _pt(0.0, -150.0),
            ]
        )
    ]
    c = rp.route_crossings(f, runway["geom_3857"], route)
    assert [round(k["s_mid"] / 10) * 10 for k in c] == [
        1440,
        400,
    ]  # second leg runs diagonally from 450 m to 350 m: centreline at 400 m
    assert (
        geo.runway_taxi_intersection_3857(runway["geom_3857"], route[0]) is not None
    )  # old centroid still there


def test_backtrack_is_along_runway(runway):
    f = rp.runway_frame(runway, 6)
    route = [LineString([_pt(800.0, -150.0), _pt(800.0, 0.0), _pt(0.0, 0.0)])]
    c = rp.route_crossings(f, runway["geom_3857"], route)
    assert len(c) == 1 and c[0]["along_runway"]
    assert c[0]["s_min"] == pytest.approx(0.0, abs=1.5) and c[0][
        "s_max"
    ] == pytest.approx(800.0, abs=1.5)


def test_no_crossing(runway):
    f = rp.runway_frame(runway, 6)
    assert (
        rp.route_crossings(
            f,
            runway["geom_3857"],
            [LineString([_pt(500.0, -300.0), _pt(900.0, -300.0)])],
        )
        == []
    )


def _approach(gamma_deg=3.0, roll=1200.0):
    """Synthetic arrival profile rows (point, x, y, z, tas, mode, course): 3° to touchdown at x = 0, then roll."""
    import math

    xs = [-20000.0, -5000.0, -1000.0, -291.0, -100.0, 0.0, roll]
    t = math.tan(math.radians(gamma_deg))
    return [(i, x, 0.0, max(0.0, -x * t), 70.0, "AP", "ANP") for i, x in enumerate(xs)]


def test_threshold_crossing_distance_3deg():
    d = rp.threshold_crossing_distance(_approach())
    assert d == pytest.approx(
        rp.THRESHOLD_CROSSING_HEIGHT_M
        / __import__("math").tan(__import__("math").radians(3.0)),
        abs=0.01,
    )
    assert d == pytest.approx(290.8, abs=0.1)


def test_touchdown_distance_precedence(runway):
    traj = _approach()
    assert rp.arrival_touchdown_distance(runway, 6, traj) == (
        pytest.approx(290.8, abs=0.1),
        "profile 50 ft crossing",
    )
    r = dict(runway, touchdown_offset_m={6: 400.0, 24: 0.0})
    assert rp.arrival_touchdown_distance(r, 6, traj) == (
        400.0,
        "runway touchdown offset",
    )
    assert rp.arrival_touchdown_distance(r, 24, traj)[1] == "profile 50 ft crossing"
    flat = [
        (0, -1000.0, 0.0, 10.0, 70.0, "AP", "ANP"),
        (1, 0.0, 0.0, 0.0, 70.0, "AP", "ANP"),
    ]
    assert rp.arrival_touchdown_distance(runway, 6, flat) == (
        0.0,
        "threshold (profile has no 50 ft crossing)",
    )


def test_get_runways_touchdown_columns(tmp_path):
    import sqlite3

    from openalaqs_standalone import movements as mv

    blob_src = sqlite3.connect(
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "data"
        / "training_v3.alaqs"
    )
    rid, geom = blob_src.execute(
        "SELECT runway_id, geometry FROM shapes_runways"
    ).fetchone()
    for cols, vals, expect in (
        (["touchdown"], [250], (250.0, 250.0)),
        (["touchdown", "touchdown_2"], [0, 300], (0.0, 300.0)),
    ):
        db = tmp_path / f"r{len(cols)}.sqlite"
        c = sqlite3.connect(db)
        c.execute(
            f"CREATE TABLE shapes_runways (runway_id TEXT, geometry BLOB, {', '.join(c_ + ' INT' for c_ in cols)})"
        )
        c.execute(
            f"INSERT INTO shapes_runways VALUES (?, ?, {', '.join('?' for _ in cols)})",
            (rid, geom, *vals),
        )
        c.commit()
        r = mv.get_runways(c)
        d1, d2 = r[r[list(r)[0]]["directions"][0]]["directions"]
        assert (
            r[d1]["touchdown_offset_m"][d1],
            r[d1]["touchdown_offset_m"][d2],
        ) == expect


def _rollout():
    """Touchdown at x = 0 at 140 kt, linear deceleration to 20 kt at x = 1500 m."""
    kt = rp.KT
    return [
        (0, -1000.0, 0.0, 52.4, 145 * kt, "AP", "ANP"),
        (1, 0.0, 0.0, 0.0, 140 * kt, "AP", "ANP"),
        (2, 1500.0, 0.0, 0.0, 20 * kt, "AP", "ANP"),
    ]


def test_select_exit():
    traj = _rollout()
    cr = [dict(s_mid=s) for s in (100.0, 900.0, 1400.0, 2000.0)]
    # touchdown 300 m past the threshold: crossings at x = 600 (92 kt), 1100 (52 kt), 1700 (beyond the profile, 0)
    e = rp.select_exit(cr, 300.0, traj)
    assert e["s_m"] == 2000.0 and e["rule"].startswith("first crossing at or below")
    e = rp.select_exit(cr, 300.0, traj, v_limit_kt=60.0)
    assert e["s_m"] == 1400.0 and e["speed_kt"] == pytest.approx(52.0, abs=0.01)
    # nothing at or below the limit: the first crossing past the touchdown
    e = rp.select_exit(cr[:2], 300.0, traj)
    assert e["s_m"] == 900.0 and e["x_m"] == 600.0 and "above the limit" in e["rule"]
    assert rp.select_exit([dict(s_mid=100.0)], 300.0, traj) is None


def test_truncate_after():
    traj = _rollout()
    t = rp.truncate_after(traj, 750.0)
    assert [r[1] for r in t] == [-1000.0, 0.0, 750.0]
    assert t[-1][4] / rp.KT == pytest.approx(80.0, abs=1e-6) and t[-1][3] == 0.0
    assert (
        rp.truncate_after(traj, 1500.0) == traj
        and rp.truncate_after(traj, 5000.0) == traj
    )


def test_stretch_time():
    kt = rp.KT
    # 737-800 at EHRD exit 2: 337 m from 30 kt to 18 kt -> 2 L / (v_end + v_x) = 27.3 s
    assert rp.stretch_time_s(337.0, 30 * kt) == pytest.approx(
        2 * 337.0 / (48 * kt), rel=1e-12
    )
    assert rp.stretch_time_s(337.0, 30 * kt) == pytest.approx(27.3, abs=0.05)
    # light aircraft ending at 10 kt: constant 10 kt (v_x = min(v_end, 18 kt))
    assert rp.stretch_time_s(1456.0, 10 * kt) == pytest.approx(
        1456.0 / (10 * kt), rel=1e-12
    )
    # profile ending at rest: 18 kt
    assert rp.stretch_time_s(100.0, 0.0) == pytest.approx(100.0 / (18 * kt), rel=1e-12)
    assert rp.stretch_time_s(0.0, 30 * kt) == 0.0


def test_split_taxi_time():
    assert rp.split_taxi_time(266.0, 181.0, 27.0) == (
        181.0,
        27.0,
        58.0,
    )  # fits: queuing shrinks
    nat, st, q = rp.split_taxi_time(
        150.0, 181.0, 27.0
    )  # does not fit: scaled, no queue
    assert (
        q == 0.0
        and nat + st == pytest.approx(150.0)
        and st / nat == pytest.approx(27.0 / 181.0)
    )
    assert rp.split_taxi_time(0.0, 181.0, 27.0) == (0.0, 0.0, 0.0)


def test_rollout_duration():
    kt = rp.KT
    traj = _rollout()  # 1,500 m from 140 kt to 20 kt: 2 L / (v1 + v2)
    assert rp.rollout_duration_s(traj) == pytest.approx(
        2 * 1500.0 / (160 * kt), rel=1e-12
    )
    assert rp.rollout_duration_s(rp.truncate_after(traj, 750.0)) == pytest.approx(
        2 * 750.0 / (220 * kt), rel=1e-12
    )
    assert (
        rp.rollout_duration_s(
            [
                (0, -100.0, 0.0, 5.0, 70.0, "AP", "ANP"),
                (1, 0.0, 0.0, 1.0, 70.0, "AP", "ANP"),
            ]
        )
        == 0.0
    )


def test_lineup_distance(runway):
    f = rp.runway_frame(runway, 6)
    # entry at 86 m: the centreline point
    c = rp.route_crossings(
        f, runway["geom_3857"], [LineString([_pt(86.0, -150.0), _pt(86.0, 0.0)])]
    )
    assert rp.lineup_distance(c) == pytest.approx(86.0, abs=1.5)
    # backtrack from an 800 m entry to the threshold: line-up at the threshold, not mid-way
    c = rp.route_crossings(
        f,
        runway["geom_3857"],
        [LineString([_pt(800.0, -150.0), _pt(800.0, 0.0), _pt(0.0, 0.0)])],
    )
    assert rp.lineup_distance(c) == pytest.approx(0.0, abs=1.5)
    assert (
        geo.runway_taxi_intersection_3857(
            runway["geom_3857"],
            LineString([_pt(800.0, -150.0), _pt(800.0, 0.0), _pt(0.0, 0.0)]),
        )
        is not None
    )
    # route crossing the runway on the way to an entry at 1,200 m: the last crossing in route order
    c = rp.route_crossings(
        f,
        runway["geom_3857"],
        [
            LineString(
                [
                    _pt(300.0, -150.0),
                    _pt(300.0, 150.0),
                    _pt(1200.0, 150.0),
                    _pt(1200.0, 0.0),
                ]
            )
        ],
    )
    assert rp.lineup_distance(c) == pytest.approx(1200.0, abs=1.5)
    assert rp.lineup_distance([]) is None


def test_check_report_runs_on_training_v3():
    import sqlite3

    from openalaqs_standalone import runway_checks as rc

    db = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "data"
        / "training_v3.alaqs"
    )
    rep = rc.check_study(sqlite3.connect(db))
    assert list(rep.columns) == rc.COLUMNS
    assert set(rep.code) <= {
        "A0",
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "T1",
        "D0",
        "D1",
        "D2",
        "D3",
        "C1",
    }
    assert set(rep.severity) <= {"error", "warning", "info"}


def test_route_order_independent_of_listing(runway):
    """An arrival route listed stand first, with a taxiway digitised backwards, gives the same crossings in the
    direction of travel as the same route listed runway first."""
    from shapely.geometry import box

    f = rp.runway_frame(runway, 6)
    gate = box(*_pt(300.0, -420.0), *_pt(320.0, -400.0))
    # travel: exit at 1,444 m -> taxi back along the far side -> cross the runway at 400 m -> stand near 300 m
    legs = [
        LineString([_pt(1444.0, 0.0), _pt(1500.0, 150.0)]),
        LineString([_pt(1500.0, 150.0), _pt(450.0, 150.0)]),
        LineString([_pt(450.0, 150.0), _pt(350.0, -150.0)]),
        LineString([_pt(350.0, -150.0), _pt(310.0, -400.0)]),
    ]
    runway_first = rp.orient_route(rp.chain_lines(legs), gate, start_at_gate=False)
    stand_first = [LineString(list(g.coords)[::-1]) for g in reversed(legs)]
    stand_first[1] = LineString(
        list(stand_first[1].coords)[::-1]
    )  # one taxiway drawn the other way
    oriented = rp.orient_route(rp.chain_lines(stand_first), gate, start_at_gate=False)
    c1 = rp.route_crossings(f, runway["geom_3857"], runway_first)
    c2 = rp.route_crossings(f, runway["geom_3857"], oriented)
    assert (
        [round(c["s_mid"] / 10) * 10 for c in c1]
        == [round(c["s_mid"] / 10) * 10 for c in c2]
        == [1440, 400]
    )
    # unoriented stand-first listing would put the 400 m crossing first
    c3 = rp.route_crossings(f, runway["geom_3857"], stand_first)
    assert round(c3[0]["s_mid"] / 10) * 10 == 400
    # a departure listed runway first is turned to start at the stand: line-up is the last contact
    dep = [
        LineString([_pt(86.0, 0.0), _pt(86.0, -150.0)]),
        LineString([_pt(86.0, -150.0), _pt(310.0, -400.0)]),
    ]
    o = rp.orient_route(rp.chain_lines(dep), gate, start_at_gate=True)
    assert rp.lineup_distance(
        rp.route_crossings(f, runway["geom_3857"], o)
    ) == pytest.approx(86.0, abs=1.5)
