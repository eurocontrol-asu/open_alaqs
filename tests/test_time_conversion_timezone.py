"""Time strings must round-trip on machines that are not on UTC.

``convertTimeToSeconds`` reads a naive "YYYY-MM-DD HH:MM:SS" string as local
machine time (``datetime.timestamp()``), as do the period boundaries in the
calculation (``start_dt.timestamp()``), so emissions land in the right periods
on any machine. ``convertSecondsToTime`` must be its inverse; formatting the
seconds as UTC shifted every movement name and log line by the machine's UTC
offset (e.g. a 05:01 movement shown as 03:01 on a CEST machine), while the
emission table showed the correct hour (issue #110).
"""

import os
import time

import pytest

from open_alaqs.core.tools import conversion


@pytest.fixture(params=["Europe/Paris", "America/New_York", "Asia/Tokyo", "UTC"])
def machine_tz(request):
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset not available on this platform")
    old = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    yield request.param
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


@pytest.mark.parametrize(
    "stamp",
    ["2025-08-05 05:01:00", "2025-01-15 23:30:00", "2024-02-29 00:00:00"],
)
def test_time_string_round_trip(machine_tz, stamp):
    seconds = conversion.convertTimeToSeconds(stamp)
    assert conversion.convertSecondsToTimeString(seconds) == stamp


def test_seconds_to_string_agrees_with_seconds_to_datetime(machine_tz):
    seconds = conversion.convertTimeToSeconds("2025-08-05 05:01:00")
    as_dt = conversion.convertSecondsToDateTime(seconds)
    assert as_dt.strftime("%Y-%m-%d %H:%M:%S") == conversion.convertSecondsToTimeString(
        seconds
    )
