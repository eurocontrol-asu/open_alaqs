"""Ambient conditions aloft from the hourly meteo row (core/tools/surface_layer_atmosphere.py).

The surface_layer model ports AUSTAL 3.3's BlmTemp, getTheta and the simple Prandtl profile
(StdUuPrandtl) used for the first estimate of u*. The reference values below were produced by
those C functions, copied verbatim from AUSTAL 3.3.0's TalBlm.c into a small harness and compiled
(single precision); the port (austal_exact=True) agrees to 6e-5 K and 2e-7 in u*. OpenALAQS
evaluates it with three documented departures (T* from the hour's temperature, no -30/+40 degC
limits, stability term capped at the mixing height), tested below.
"""

import math

import pytest

from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.MovementEmissionCalculator import (
    _LocalAmbient,
    local_ambient_conditions,
)
from open_alaqs.core.tools import surface_layer_atmosphere as sla

# (z0, d0, ha, ua, L, ta) -> u*, {h: T} from AUSTAL 3.3.0 C code
AUSTAL_C = [
    (
        (0.3, 1.2, 11.2, 4.0, -50.0, 291.15),
        0.5184082,
        {10: 290.1313, 100: 288.4775, 300: 286.4995, 914.4: 281.1897},
    ),
    (
        (0.3, 1.2, 11.2, 4.0, 30.0, 291.15),
        0.3123033,
        {10: 292.6177, 100: 298.422, 300: 301.3054, 914.4: 305.1967},
    ),
    (
        (0.2, 1.2, 11.2, 2.5, 200.0, 285.0),
        0.2405568,
        {10: 285.0198, 100: 284.3846, 300: 282.8133, 914.4: 277.968},
    ),
    (
        (0.5, 3.0, 13.0, 7.0, 99999.0, 300.0),
        0.9345148,
        {10: 299.9532, 100: 299.0783, 300: 297.2496, 914.4: 292.029},
    ),
]


@pytest.mark.parametrize("args, ust_c, temps_c", AUSTAL_C)
def test_friction_velocity_matches_austal(args, ust_c, temps_c):
    z0, d0, ha, ua, lm, _ = args
    assert sla.friction_velocity(ua, ha, z0, d0, lm) == pytest.approx(ust_c, rel=1e-6)


@pytest.mark.parametrize("args, ust_c, temps_c", AUSTAL_C)
def test_temperature_matches_austal_blmtemp(args, ust_c, temps_c):
    z0, d0, _, _, lm, ta = args
    for h, t_c in temps_c.items():
        assert sla.blm_temperature(
            h, z0, d0, ust_c, lm, ta, austal_exact=True
        ) == pytest.approx(t_c, abs=2e-4)


def test_openalaqs_departures_from_blmtemp():
    z0, d0, ust, lm = 0.3, 1.2, 0.3123033, 30.0
    # at ta = 283.15 K (AUSTAL's fixed value) T* is the same: identical within the limits
    assert sla.blm_temperature(300.0, z0, d0, ust, lm, 283.15) == pytest.approx(
        sla.blm_temperature(300.0, z0, d0, ust, lm, 283.15, austal_exact=True),
        abs=1e-12,
    )
    # T* scales with the hour's temperature: the stability term is ta / 283.15 times AUSTAL's
    # (ta 20 degC, below AUSTAL's +40 degC limit)
    ta = 293.15
    neutral = sla.blm_temperature(300.0, z0, d0, 0.0, lm, ta)
    exact = sla.blm_temperature(300.0, z0, d0, ust, lm, ta, austal_exact=True)
    ours = sla.blm_temperature(300.0, z0, d0, ust, lm, ta)
    assert (ours - neutral) == pytest.approx((exact - neutral) * ta / 283.15, rel=1e-9)
    # no -30 / +40 degC limits: a 43 degC ground temperature is not clipped aloft
    assert (
        sla.blm_temperature(50.0, z0, d0, 0.0, 99999.0, 316.15, austal_exact=True)
        == 313.15
    )
    assert sla.blm_temperature(50.0, z0, d0, 0.0, 99999.0, 316.15) < 316.15
    assert sla.blm_temperature(50.0, z0, d0, 0.0, 99999.0, 316.15) > 313.15 - 1.0


def test_stability_term_stops_at_the_mixing_height():
    # row mixing height 60 m, below AUSTAL's stable estimate for this hour (about 88 m)
    kw = dict(
        wind_speed_m_s=4.0,
        obukhov_length_m=30.0,
        airport_elevation_m=0.0,
        z0=0.3,
        d0=1.2,
        ha=11.2,
    )
    t_hm, _, _ = sla.local_state(
        "surface_layer", 293.15, 101325.0, 0.6, 60.0, mixing_height_m=60.0, **kw
    )
    t_cap, _, _ = sla.local_state(
        "surface_layer", 293.15, 101325.0, 0.6, 900.0, mixing_height_m=60.0, **kw
    )
    assert t_cap == pytest.approx(t_hm - 0.0085 * 840.0, abs=1e-9)
    # below the mixing height the cap changes nothing: the plain AUSTAL term
    ust = sla.friction_velocity(4.0, 11.2, 0.3, 1.2, 30.0)
    a, _, _ = sla.local_state(
        "surface_layer", 293.15, 101325.0, 0.6, 50.0, mixing_height_m=60.0, **kw
    )
    assert a == pytest.approx(
        sla.blm_temperature(50.0, 0.3, 1.2, ust, 30.0, 293.15), abs=1e-12
    )


def test_station_pressure_from_qnh():
    assert sla.station_pressure_from_qnh(101325.0, 0.0) == 101325.0
    # ISA: QNH 1013.25 hPa at 1,000 m gives the ISA pressure at 1,000 m
    assert sla.station_pressure_from_qnh(101325.0, 1000.0) == pytest.approx(
        89874.6, abs=0.5
    )
    # below sea level the station pressure is higher (-4.6 m)
    assert sla.station_pressure_from_qnh(101600.0, -4.6) > 101600.0


def test_ground_held_returns_the_row_at_every_height():
    for h in (0.0, 300.0, 914.4):
        assert sla.local_state(
            "ground_held", 291.15, 101600.0, 0.7, h, 4.0, -50.0, -4.6
        ) == (
            291.15,
            101600.0,
            0.7,
        )


def test_standard_lapse_is_isa_for_an_isa_row():
    t, p, _ = sla.local_state("standard_lapse", 288.15, 101325.0, 0.6, 914.4)
    assert t == pytest.approx(288.15 - 0.0065 * 914.4, abs=1e-9)
    assert p == pytest.approx(
        101325.0 * (1 - 0.0065 * 914.4 / 288.15) ** 5.25588, rel=1e-7
    )


@pytest.mark.parametrize("model", ["surface_layer", "standard_lapse"])
def test_ground_state_is_station_pressure_and_metar_temperature(model):
    t, p, rh = sla.local_state(model, 291.15, 101600.0, 0.7, 0.0, 4.0, -50.0, -4.6)
    assert t == 291.15
    assert p == pytest.approx(sla.station_pressure_from_qnh(101600.0, -4.6), rel=1e-12)
    assert rh == 0.7


def test_surface_layer_pressure_is_hydrostatic():
    """ln p falls by g/R * integral(1/T dz); checked against a fine independent integration."""
    args = ("surface_layer", 291.15, 101600.0, 0.7)
    kw = dict(
        wind_speed_m_s=4.0,
        obukhov_length_m=-50.0,
        airport_elevation_m=-4.6,
        z0=0.3,
        d0=1.2,
        ha=11.2,
    )
    ust = sla.friction_velocity(4.0, 11.2, 0.3, 1.2, -50.0)
    p0 = sla.station_pressure_from_qnh(101600.0, -4.6)
    h_top, n = 914.4, 20000
    integ = 0.0
    for i in range(n):
        a, b = h_top * i / n, h_top * (i + 1) / n
        ta = (
            291.15 if a <= 2.0 else sla.blm_temperature(a, 0.3, 1.2, ust, -50.0, 291.15)
        )
        tb = (
            291.15 if b <= 2.0 else sla.blm_temperature(b, 0.3, 1.2, ust, -50.0, 291.15)
        )
        # (no mixing height given: the stability term applies over the whole column)
        integ += 0.5 * (1 / ta + 1 / tb) * (b - a)
    p_ref = p0 * math.exp(-9.80665 / 287.053 * integ)
    t, p, _ = sla.local_state(*args, h_top, **kw)
    assert p == pytest.approx(p_ref, rel=2e-6)
    assert t == pytest.approx(
        sla.blm_temperature(h_top, 0.3, 1.2, ust, -50.0, 291.15), abs=1e-9
    )


@pytest.mark.parametrize("model", ["surface_layer", "standard_lapse"])
def test_humidity_ratio_is_conserved(model):
    p0 = sla.station_pressure_from_qnh(101600.0, -4.6)
    omega0 = sla.humidity_ratio(291.15, p0, 0.7)
    for h in (10.0, 300.0, 914.4):
        t, p, rh = sla.local_state(model, 291.15, 101600.0, 0.7, h, 4.0, -50.0, -4.6)
        assert sla.humidity_ratio(t, p, rh) == pytest.approx(omega0, rel=1e-12)


def test_missing_or_zero_obukhov_length_is_neutral():
    a = sla.local_state("surface_layer", 291.15, 101600.0, 0.7, 300.0, 4.0, None)
    b = sla.local_state("surface_layer", 291.15, 101600.0, 0.7, 300.0, 4.0, 0.0)
    c = sla.local_state("surface_layer", 291.15, 101600.0, 0.7, 300.0, 4.0, 99999.0)
    assert a == b == c


def test_negative_height_is_ground():
    assert sla.local_state(
        "surface_layer", 291.15, 101600.0, 0.7, -3.0, 4.0, -50.0
    ) == sla.local_state("surface_layer", 291.15, 101600.0, 0.7, 0.0, 4.0, -50.0)


def test_default_model_and_unknown_model():
    # 5.4.1: standard_lapse is the default (De Bilt sounding check, 24 Oct 2026)
    assert sla.normalise_model(None) == "standard_lapse"
    assert sla.normalise_model("") == "standard_lapse"
    assert sla.normalise_model("Surface_Layer") == "surface_layer"
    assert sla.normalise_model("Ground_Held") == "ground_held"
    with pytest.raises(ValueError):
        sla.normalise_model("isa")


def test_site_parameter_defaults_are_the_austal_defaults():
    # z0 0.1 m (TA Luft, airports), d0 6 z0, ha 10 m + d0, shared by the plugin's AUSTAL
    # module, the standalone and austal_prep (24 Oct 2026; 0.2 / 1.2 / 11.2 before)
    assert sla.site_parameters() == (0.1, 0.6, 10.6)
    assert sla.site_parameters(0.3, 1.2, 11.2) == (0.3, 1.2, 11.2)


def _ac():
    return AmbientCondition(
        {
            "id": 1,
            "Temperature": 291.15,
            "SeaLevelPressure": 101600.0,
            "RelativeHumidity": 0.7,
            "WindSpeed": 4.0,
            "ObukhovLength": -50.0,
            "MixingHeight": 800.0,
        }
    )


def test_plugin_local_ambient_conditions():
    cfg = {
        "ambient_conditions": _ac(),
        "airport_altitude": -4.6,
        "atmosphere_site": (0.3, 1.2, 11.2),
    }
    local = local_ambient_conditions(dict(cfg, atmosphere_model="surface_layer"), 300.0)
    t, p, rh = sla.local_state(
        "surface_layer",
        291.15,
        101600.0,
        0.7,
        300.0,
        4.0,
        -50.0,
        -4.6,
        0.3,
        1.2,
        11.2,
        mixing_height_m=800.0,
    )
    assert (
        local.getTemperature(),
        local.getPressure(),
        local.getRelativeHumidity(),
    ) == (t, p, rh)
    assert local.getMixingHeight() == 800.0
    # the period's row is untouched
    assert cfg["ambient_conditions"].getTemperature() == 291.15
    assert (
        local_ambient_conditions(dict(cfg, atmosphere_model="ground_held"), 300.0)
        is None
    )
    # without a model the plugin uses the default, standard_lapse
    t_d, p_d, rh_d = sla.local_state(
        "standard_lapse",
        291.15,
        101600.0,
        0.7,
        300.0,
        4.0,
        -50.0,
        -4.6,
        0.3,
        1.2,
        11.2,
        mixing_height_m=800.0,
    )
    default = local_ambient_conditions(cfg, 300.0)
    assert (
        default.getTemperature(),
        default.getPressure(),
        default.getRelativeHumidity(),
    ) == (t_d, p_d, rh_d)


def test_plugin_context_swaps_and_restores():
    ground = _ac()
    cfg = {"ambient_conditions": ground, "airport_altitude": -4.6}
    with _LocalAmbient(cfg, 500.0):
        assert cfg["ground_ambient_conditions"] is ground
        assert cfg["ambient_conditions"] is not ground
        assert cfg["ambient_conditions"].getTemperature() < 291.15
    assert cfg["ambient_conditions"] is ground
    assert "ground_ambient_conditions" not in cfg
    cfg["atmosphere_model"] = "ground_held"
    with _LocalAmbient(cfg, 500.0):
        assert cfg["ambient_conditions"] is ground
        assert "ground_ambient_conditions" not in cfg


def test_austal_stable_mixing_height():
    # AUSTAL getHm with f = 1.1e-4: 0.3 u*/f sqrt(f L / u*)
    ust, lm = 0.3123033, 30.0
    expected = 0.3 * ust / 1.1e-4 * math.sqrt(1.1e-4 * lm / ust)
    assert sla.austal_stable_mixing_height(ust, lm) == pytest.approx(
        expected, rel=1e-12
    )
    assert (
        sla.austal_stable_mixing_height(0.5, 99999.0) == 800.0
    )  # neutral: at most 800 m
    assert (
        sla.austal_stable_mixing_height(0.5, -50.0) is None
    )  # unstable: the row's value
    assert sla.austal_stable_mixing_height(0.001, 1.0) == 20.0  # at least 20 m


def test_icao_ceiling_row_gets_a_stable_layer_of_austal_depth():
    """A row whose MixingHeight is the ICAO 914.4 m: the stable term stops at AUSTAL's own
    stable mixing height instead of warming the air up to 914.4 m."""
    kw = dict(
        wind_speed_m_s=4.0,
        obukhov_length_m=30.0,
        airport_elevation_m=0.0,
        z0=0.3,
        d0=1.2,
        ha=11.2,
    )
    ust = sla.friction_velocity(4.0, 11.2, 0.3, 1.2, 30.0)
    hm = sla.austal_stable_mixing_height(ust, 30.0)
    t_icao, _, _ = sla.local_state(
        "surface_layer", 293.15, 101325.0, 0.6, 900.0, mixing_height_m=914.4, **kw
    )
    t_hm = sla.blm_temperature(hm, 0.3, 1.2, ust, 30.0, 293.15)
    assert t_icao == pytest.approx(t_hm - 0.0085 * (900.0 - hm), abs=1e-9)
    assert (
        t_icao - 293.15 < 1.0
    )  # was +13.9 K with the stability term extended to 900 m


def test_meem_v1_local_ambient():
    """MEEM V1 with the segment's local (T, p): the CAEP sheet's ISA + delta T reproduces the
    sheet; another state changes the EI; the reference implementation agrees."""
    from open_alaqs.core.tools import meem_v1
    from openalaqs_standalone.validation.tools import compute_caep14_reference as ref

    ts, mass, num = (
        [0.07, 0.30, 0.85, 1.00],
        [2.0, 8.0, 25.0, 35.0],
        [1e14, 3e14, 8e14, 1e15],
    )
    alt_ft, dt, tas_kt = 4000.0, 5.0, 200.0
    base = meem_v1.calculate_nvpm_ei(
        "CLIMB TO CRUISE", alt_ft, ts, mass, num, opr=30.0, tas_kt=tas_kt, delta_t=dt
    )
    same = meem_v1.calculate_nvpm_ei(
        "CLIMB TO CRUISE",
        alt_ft,
        ts,
        mass,
        num,
        opr=30.0,
        tas_kt=tas_kt,
        delta_t=dt,
        ambient=meem_v1.isa_ambient(alt_ft, dt),
    )
    assert same.nvpm_mass_ei_mgkg == pytest.approx(base.nvpm_mass_ei_mgkg, rel=1e-12)
    t, p, _ = sla.local_state(
        "surface_layer",
        295.15,
        101600.0,
        0.6,
        alt_ft * 0.3048,
        3.0,
        -50.0,
        mixing_height_m=1500.0,
    )
    loc = meem_v1.calculate_nvpm_ei(
        "CLIMB TO CRUISE",
        alt_ft,
        ts,
        mass,
        num,
        opr=30.0,
        tas_kt=tas_kt,
        delta_t=dt,
        ambient=(t, p),
    )
    assert loc.nvpm_mass_ei_mgkg != pytest.approx(base.nvpm_mass_ei_mgkg, rel=1e-4)
    points = list(zip(ts, mass))
    r = ref._meem_v1_mass_mgkg(
        alt_ft, tas_kt / 1.94384, True, points, 30.0, dt, ambient=(t, p)
    )
    assert r == pytest.approx(loc.nvpm_mass_ei_mgkg, rel=1e-6)
