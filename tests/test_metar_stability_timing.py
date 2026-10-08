"""Stability classification timing in scripts/metar_to_alaqs_meteo.py.

A row labelled hh:00 averages the reports of hh:00 to hh:59, so the solar
elevation used for its Pasquill-Gifford class must be taken at mid-hour,
not at hh:00.  Regression for hours around sunrise and sunset that were
classified with the sun of the previous half hour.
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metar_to_alaqs_meteo as M  # noqa: E402

LAT, LON = 51.95, 4.44


def _row(t, wind=1.5, oktas=0):
    return {"datetime": t, "wind_speed_ms": wind, "oktas": oktas}


def _first_hour_where_sun_crosses(day, rising=True):
    """First hour hh where the sun at hh:00 and at hh:30 are on opposite sides."""
    for h in range(24):
        t = dt.datetime(day.year, day.month, day.day, h)
        e0 = M.solar_elevation_deg(t.replace(tzinfo=dt.timezone.utc), LAT, LON)
        e30 = M.solar_elevation_deg(
            (t + dt.timedelta(minutes=30)).replace(tzinfo=dt.timezone.utc), LAT, LON
        )
        if (rising and e0 <= 0 < e30) or (not rising and e30 <= 0 < e0):
            return t, e30
    return None, None


def test_class_uses_mid_hour_sun():
    t = dt.datetime(2025, 7, 15, 10)
    e30 = M.solar_elevation_deg(
        (t + dt.timedelta(minutes=30)).replace(tzinfo=dt.timezone.utc), LAT, LON
    )
    L, MH, pg = M._per_row_l_and_mh(_row(t), LAT, LON, None)
    assert pg == M.pasquill_gifford(1.5, 0, e30)


def test_sunrise_hour_is_day_when_mid_hour_sun_is_up():
    # Search a few dates for an hour whose sun is down at hh:00 and up at hh:30.
    for day in range(1, 29):
        t, e30 = _first_hour_where_sun_crosses(dt.date(2025, 3, day), rising=True)
        if t is not None:
            break
    assert t is not None
    _, _, pg = M._per_row_l_and_mh(_row(t, wind=1.5, oktas=0), LAT, LON, None)
    # Night with 0 oktas and 1.5 m/s would be F; the day table never gives F.
    assert pg != "F"
    assert pg == M.pasquill_gifford(1.5, 0, e30)


def test_sunset_hour_is_night_when_mid_hour_sun_is_down():
    for day in range(1, 29):
        t, e30 = _first_hour_where_sun_crosses(dt.date(2025, 3, day), rising=False)
        if t is not None:
            break
    assert t is not None
    _, _, pg = M._per_row_l_and_mh(_row(t, wind=1.5, oktas=0), LAT, LON, None)
    assert pg == "F"
