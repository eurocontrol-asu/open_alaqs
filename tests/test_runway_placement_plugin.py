"""Runway placement of flight profiles in the plugin (GeoTransformation.TrajectoryTransformer).

Synthetic runway "06/24" (2,200 m) and routes, ANP-style profiles. Checks the rules shared with the standalone
(open_alaqs.core.tools.runway_placement): arrival touchdown at the landing threshold + Touchdown Offset (else the
profile's 50 ft crossing distance), rollout cut at an early exit, runway stretch to a late exit, landing roll,
departure brake release at the line-up point; and the Runway Touchdown Offset per direction.
"""

import math
import sqlite3

import pyproj
import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.core.GeoTransformation import TrajectoryTransformer  # noqa: E402
from open_alaqs.core.interfaces.AircraftTrajectory import (  # noqa: E402
    AircraftTrajectory,
    AircraftTrajectoryPoint,
)
from open_alaqs.core.interfaces.Runway import Runway, RunwayDatabase  # noqa: E402
from open_alaqs.core.interfaces.Taxiway import (  # noqa: E402
    TaxiwayRoute,
    TaxiwaySegment,
)
from open_alaqs.core.tools import runway_placement as rp  # noqa: E402

GEOD = pyproj.Geod(ellps="WGS84")
TO_3857 = pyproj.Transformer.from_crs(4326, 3857, always_xy=True)
LON0, LAT0, AZ, LEN = 4.4370, 51.9500, 60.0, 2200.0
KT = 0.514444


def _pt(s, x=0.0):
    lon, lat, _ = GEOD.fwd(LON0, LAT0, AZ, s)
    if x:
        lon, lat, _ = GEOD.fwd(lon, lat, (AZ + 90.0) % 360.0, x)
    return TO_3857.transform(lon, lat)


def _wkt(*pts):
    return "LINESTRING(" + ", ".join(f"{x} {y}" for x, y in pts) + ")"


def _runway(touchdown=0, touchdown_2=None):
    return Runway(
        {
            "runway_id": "06/24",
            "touchdown": touchdown,
            "touchdown_2": touchdown_2,
            "geometry": _wkt(_pt(0.0), _pt(LEN)),
        }
    )


def _route(name, ad, *legs):
    r = TaxiwayRoute(
        {"route_name": name, "gate": "G1", "runway": "06", "departure_arrival": ad}
    )
    for i, leg in enumerate(legs):
        r.addSegment(
            TaxiwaySegment(
                {"taxiway_id": f"{name}_{i}", "speed": 30, "geometry": _wkt(*leg)}
            )
        )
    return r


def _arrival_profile():
    """3 degree approach to touchdown at x = 0 (140 kt), roll to 1,200 m (decelerating to 30 kt)."""
    t = math.tan(math.radians(3.0))
    traj = AircraftTrajectory({"profile_id": "TEST-A-1", "arrival_departure": "A"})
    for i, (x, v) in enumerate(
        [(-6000.0, 150), (-1000.0, 145), (0.0, 140), (600.0, 80), (1200.0, 30)]
    ):
        traj.addPoint(
            AircraftTrajectoryPoint(
                {
                    "id": i,
                    "x": x,
                    "y": 0.0,
                    "z": max(0.0, -x * t),
                    "tas_metres": v * KT,
                    "mode": "AP",
                    "course": "ANP",
                    "power": 0.3,
                }
            )
        )
    return traj


def _departure_profile():
    traj = AircraftTrajectory({"profile_id": "TEST-D-1", "arrival_departure": "D"})
    for i, (x, z, v) in enumerate(
        [(0.0, 0.0, 0.0), (1500.0, 0.0, 150), (6000.0, 300.0, 170)]
    ):
        traj.addPoint(
            AircraftTrajectoryPoint(
                {
                    "id": i,
                    "x": x,
                    "y": 0.0,
                    "z": z,
                    "tas_metres": v * KT,
                    "mode": "TO",
                    "course": "ANP",
                    "power": 1.0,
                }
            )
        )
    return traj


def _gate_wkt():
    a, b, c, d = (
        _pt(300.0, -420.0),
        _pt(320.0, -420.0),
        _pt(320.0, -400.0),
        _pt(300.0, -400.0),
    )
    return f"POLYGON(({a[0]} {a[1]}, {b[0]} {b[1]}, {c[0]} {c[1]}, {d[0]} {d[1]}, {a[0]} {a[1]}))"


def _place(runway, route, traj, ad):
    t = TrajectoryTransformer(
        traj,
        None,
        runway,
        "2025-01-01 00:00:00",
        "06",
        route,
        ad,
        gate_geometry_text=_gate_wkt(),
    )
    return t.runway_alignment()


def _s(p):
    frame = rp.frame_from_ends(6, _pt(0.0), _pt(LEN))
    return rp.along(frame, (p.getX(), p.getY()))[0]


def _touchdown_s(out):
    pts = out.getPoints()
    return next(_s(b) for a, b in zip(pts, pts[1:]) if a.getZ() > 0 >= b.getZ())


def test_touchdown_offset_per_direction():
    # Runway 2 is independent: empty = the profile's own distance (0), not the Runway 1 value.
    assert _runway(250).getTouchdownOffsetFor("24") == 0.0
    assert _runway(250).getTouchdownOffsetFor("06") == 250.0
    r = _runway(250, 300)
    assert (r.getTouchdownOffsetFor("06"), r.getTouchdownOffsetFor("24")) == (
        250.0,
        300.0,
    )
    assert _runway("", "").getTouchdownOffsetFor("06") == 0.0
    assert _runway(0, None).getTouchdownOffset2() is None


def test_old_study_without_touchdown_2_loads(tmp_path):
    db = tmp_path / "old.sqlite"
    with sqlite3.connect(db) as c:
        c.execute(
            "CREATE TABLE shapes_runways (oid INTEGER PRIMARY KEY NOT NULL, runway_id TEXT, capacity INT, "
            "touchdown INT, instudy DECIMAL, geometry TEXT)"
        )
    saved = RunwayDatabase.instance
    RunwayDatabase.reset()
    try:
        with sqlite3.connect(db) as c:
            c.execute(
                "INSERT INTO shapes_runways VALUES (1, '06/24', 30, 250, 1, NULL)"
            )
        rdb = RunwayDatabase(
            str(db)
        )  # would fail on "no such column: touchdown_2" without the filter
        rows = list(rdb.getEntries().values())
        assert (
            len(rows) == 1
            and rows[0]["touchdown"] == 250
            and "touchdown_2" not in rows[0]
        )
        r = Runway(rows[0])
        assert (
            r.getTouchdownOffsetFor("06") == 250.0
            and r.getTouchdownOffsetFor("24") == 0.0
            and r.getTouchdownOffset2() is None
        )
    finally:
        RunwayDatabase.instance = saved


def test_arrival_touchdown_at_threshold_plus_profile_distance():
    exit_late = _route(
        "G1/06/A/1",
        "A",
        [_pt(1900.0, 0.0), _pt(1950.0, -150.0)],
        [_pt(1950.0, -150.0), _pt(310.0, -400.0)],
    )
    out = _place(_runway(0), exit_late, _arrival_profile(), "A")
    assert _touchdown_s(out) == pytest.approx(
        50 * 0.3048 / math.tan(math.radians(3.0)), abs=0.5
    )  # 290.8 m
    pl = out.runway_placement
    assert pl["rollout_cut_m"] == 0.0
    assert pl["stretch"]["length_m"] == pytest.approx(1900.0 - 290.8 - 1200.0, abs=1.0)
    assert pl["stretch"]["time_s"] == pytest.approx(
        2 * pl["stretch"]["length_m"] / ((30 + 18) * KT), rel=1e-6
    )
    assert pl["rollout_time_s"] == pytest.approx(
        2 * 600 / (220 * KT) + 2 * 600 / (110 * KT), rel=1e-6
    )


def test_arrival_touchdown_offset_and_cut_at_early_exit():
    exit_early = _route(
        "G1/06/A/1",
        "A",
        [_pt(1000.0, 0.0), _pt(1050.0, -150.0)],
        [_pt(1050.0, -150.0), _pt(310.0, -400.0)],
    )
    out = _place(_runway(400), exit_early, _arrival_profile(), "A")
    assert _touchdown_s(out) == pytest.approx(400.0, abs=0.5)
    pl = out.runway_placement
    assert pl["rollout_cut_m"] == pytest.approx(1200.0 - 600.0, abs=0.5)
    assert max(_s(p) for p in out.getPoints()) == pytest.approx(1000.0, abs=0.5)
    assert pl["stretch"] is None


def test_departure_lineup_is_last_runway_contact():
    # route listed runway first, with a backtrack from the 300 m entry to 50 m: line-up at 50 m
    backtrack = _route(
        "G1/06/D/1",
        "D",
        [_pt(50.0, 0.0), _pt(300.0, 0.0)],
        [_pt(300.0, 0.0), _pt(300.0, -150.0)],
        [_pt(300.0, -150.0), _pt(310.0, -400.0)],
    )
    out = _place(_runway(0), backtrack, _departure_profile(), "D")
    assert _s(out.getPoints()[0]) == pytest.approx(50.0, abs=0.5)
    assert out.runway_placement["lineup_m"] == pytest.approx(50.0, abs=0.5)
