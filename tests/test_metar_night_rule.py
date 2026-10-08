"""Night-time warm/humid correction of the stable classes in
scripts/metar_to_alaqs_meteo.py (--night-rule)."""

import datetime as dt
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import metar_to_alaqs_meteo as M  # noqa: E402

NIGHT, DAY = -10.0, 30.0


def test_default_is_sky_eps():
    assert M.DEFAULT_NIGHT_RULE == "sky_eps"


def test_emissivity_formula():
    # Brutsaert with Magnus vapour pressure, written out independently.
    t, td = 20.0, 15.0
    e = 6.112 * math.exp(17.625 * td / (243.04 + td))
    assert abs(M.clear_sky_emissivity(t, td) - 1.24 * (e / 293.15) ** (1 / 7)) < 1e-12


def _dew_for_eps(t, eps):
    """Dewpoint giving the requested emissivity at temperature t (bisection)."""
    lo, hi = -40.0, t
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if M.clear_sky_emissivity(t, mid) < eps:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@pytest.mark.parametrize(
    "eps, base, expected",
    [
        (0.84, "F", "F"),
        (0.86, "F", "E"),
        (0.93, "F", "D"),
        (0.86, "E", "D"),
        (0.93, "E", "D"),
    ],
)
def test_sky_eps_steps_and_floor(eps, base, expected):
    td = _dew_for_eps(35.0, eps)  # 0.92 is reachable only in very warm, moist air
    assert abs(M.clear_sky_emissivity(35.0, td) - eps) < 1e-6
    assert M.apply_night_rule(base, NIGHT, 35.0, td, "sky_eps") == expected


@pytest.mark.parametrize(
    "t, td, base, expected",
    [
        (20.0, 16.0, "F", "F"),  # T not above 20
        (21.0, 15.0, "F", "F"),  # Td not above 15
        (21.0, 16.0, "F", "E"),  # one class
        (25.0, 21.0, "F", "D"),  # two classes
        (25.0, 21.0, "E", "D"),
    ],  # never past D
)
def test_t20_td15(t, td, base, expected):
    assert M.apply_night_rule(base, NIGHT, t, td, "T20+Td15") == expected


def test_t20():
    assert M.apply_night_rule("F", NIGHT, 20.5, 5.0, "T20") == "E"
    assert M.apply_night_rule("F", NIGHT, 20.0, 5.0, "T20") == "F"


@pytest.mark.parametrize("rule", M.NIGHT_RULES)
def test_no_effect_by_day_on_neutral_or_without_dewpoint(rule):
    assert M.apply_night_rule("F", DAY, 30.0, 28.0, rule) == "F"
    assert M.apply_night_rule("D", NIGHT, 30.0, 28.0, rule) == "D"
    if rule != "T20":
        assert M.apply_night_rule("F", NIGHT, 30.0, None, rule) == "F"


def test_baseline_never_changes():
    assert M.apply_night_rule("F", NIGHT, 35.0, 30.0, "baseline") == "F"


def test_unknown_rule_rejected():
    with pytest.raises(ValueError):
        M.apply_night_rule("F", NIGHT, 25.0, 20.0, "nope")


def test_row_classification_uses_rule():
    # Clear, light-wind night: base class F; humid enough for sky_eps.
    row = {
        "datetime": dt.datetime(2025, 7, 15, 0),
        "wind_speed_ms": 1.5,
        "oktas": 0,
        "temp_c": 25.0,
        "dew_c": _dew_for_eps(25.0, 0.88),
    }
    _, _, base = M._per_row_l_and_mh(row, 51.95, 4.44, None, "baseline")
    _, _, eps = M._per_row_l_and_mh(row, 51.95, 4.44, None, "sky_eps")
    assert (base, eps) == ("F", "E")
