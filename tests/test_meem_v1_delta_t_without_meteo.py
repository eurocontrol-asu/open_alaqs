"""Without meteo the temperature is ISA sea level (288.15 K), so the MEEM V1
delta T is 0.0065 K/m x airport elevation, not 0 (docstring and CHANGELOG)."""

import pytest

from open_alaqs.core.tools.meem_v1 import delta_t_from_ground


def test_delta_t_without_meteo_is_the_isa_lapse_times_elevation():
    assert delta_t_from_ground(288.15, 1655.0) == pytest.approx(10.7575)
    assert delta_t_from_ground(288.15, 0.0) == 0.0
    assert delta_t_from_ground(None, 1655.0) == 0.0
