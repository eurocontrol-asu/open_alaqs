"""Wind direction handling in scripts/metar_to_alaqs_meteo.py.

Regression for two defects: hourly directions were averaged arithmetically
(010 and 360 gave 185), and 360 (north) was rejected by validation, so
northerly hours became variable (999) or kept only the other report.
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metar_to_alaqs_meteo as M  # noqa: E402

DAY = dt.date(2024, 1, 6)


def _obs(line, minute):
    o = M.parse_metar(line, DAY)
    o.time_utc = dt.datetime(2024, 1, 6, 0, minute)
    return o


def test_360_is_north():
    o = M.parse_metar("EHRD 060055Z AUTO 36005KT 9999 NSC 06/04 Q1004", DAY)
    assert o.wind_dir_deg == 0.0


def test_calm_and_vrb_have_no_direction():
    for line in (
        "EHRD 060055Z AUTO 00000KT 9999 NSC 06/04 Q1004",
        "EHRD 060055Z AUTO VRB02KT 9999 NSC 06/04 Q1004",
    ):
        assert M.parse_metar(line, DAY).wind_dir_deg is None


def test_hourly_direction_is_circular_mean():
    obs = [
        _obs("EHRD 060025Z AUTO 01009KT 9999 NSC 06/04 Q1004", 25),
        _obs("EHRD 060055Z AUTO 36005KT 9999 NSC 06/04 Q1004", 55),
    ]
    start = dt.datetime(2024, 1, 6, 0, 0)
    (row,) = list(M.hourly_average(obs, start, start))
    assert abs(row["wind_dir_deg"] - 5.0) < 1e-6


def test_circular_mean_across_north():
    assert round(M._circular_mean_deg([350.0, 10.0])) % 360 == 0
    assert abs(M._circular_mean_deg([80.0, 100.0]) - 90.0) < 1e-9
