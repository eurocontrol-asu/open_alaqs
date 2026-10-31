"""The worked example of documents/methods/AIRCRAFT_EMISSIONS.md
("Worked example: one segment, three methods") recomputed with the shared
code, so the page stays true when the methods change."""

import math

import pytest

from open_alaqs.core.tools.bffm2 import calculate_emission_index, speed_of_sound_m_s
from open_alaqs.core.tools.twin_quadratic_fit_method import (
    calculate_fuel_flow_from_power_setting,
)

# EEDB 01P20CM128 (LEAP-1A26) as in the training study
EEDB = {
    "Idle": (0.07, 0.091, {"NOx": 4.61, "CO": 21.63, "HC": 0.29}),
    "Approach": (0.30, 0.244, {"NOx": 8.75, "CO": 2.65, "HC": 0.04}),
    "Climbout": (0.85, 0.71, {"NOx": 13.38, "CO": 0.26, "HC": 0.02}),
    "Takeoff": (1.00, 0.861, {"NOx": 30.8, "CO": 0.24, "HC": 0.02}),
}
ICAO = {
    pol: {mode: {ff: eis[pol]} for mode, (_, ff, eis) in EEDB.items()}
    for pol in ("NOx", "CO", "HC")
}
INSTALLATION = {"Takeoff": 1.010, "Climbout": 1.013, "Approach": 1.020, "Idle": 1.100}
T, P_PA = 288.15, 101325.0
# JET-SMALL-A-1, points 8 to 9
POWER, TAS0, TAS1 = 0.186126415, 70.3244948, 68.5239408
DIST = -290.80968 - (-10579.18128)
N_ENG = 2


def _ambient():
    t_c = T - 273.15
    p_sat = 6.107 * 10 ** (7.5 * t_c / (237.3 + t_c))
    omega0 = 0.00634
    rh = omega0 * (P_PA / 100) / (p_sat * (0.62197058 + omega0))
    return {
        "temperature_in_Kelvin": T,
        "pressure_in_Pa": P_PA,
        "relative_humidity": rh,
        "mach_number": TAS0 / speed_of_sound_m_s(T),
    }


def _segment(wf):
    t_seg = 2 * DIST / (TAS0 + TAS1)
    fuel = wf * N_ENG * t_seg
    amb = _ambient()
    ei = {
        pol: calculate_emission_index(pol, wf, ICAO, amb, INSTALLATION)
        for pol in ("NOx", "CO", "HC")
    }
    return t_seg, fuel, ei


def test_segment_geometry():
    t_seg, _, _ = _segment(0.244)
    assert t_seg == pytest.approx(148.2, abs=0.05)
    assert _ambient()["relative_humidity"] == pytest.approx(0.60, abs=0.005)
    assert _ambient()["mach_number"] == pytest.approx(0.207, abs=0.0005)


def test_trajectory_source():
    wf = calculate_fuel_flow_from_power_setting(
        POWER, {p: ff for p, ff, _ in EEDB.values()}
    )
    wf *= 1.0 * math.sqrt(1.0)  # delta sqrt(theta) at ISA
    assert wf == pytest.approx(0.165, abs=0.0005)
    _, fuel, ei = _segment(wf)
    assert fuel == pytest.approx(49.0, abs=0.05)
    assert ei["NOx"] == pytest.approx(6.60, abs=0.005)
    assert ei["CO"] == pytest.approx(6.69, abs=0.005)
    assert ei["HC"] == pytest.approx(0.096, abs=0.0005)
    assert fuel * ei["NOx"] == pytest.approx(323, abs=0.5)
    assert fuel * ei["CO"] == pytest.approx(327, abs=0.5)


def test_mode_anchor_source():
    _, fuel, ei = _segment(0.244)
    assert fuel == pytest.approx(72.3, abs=0.05)
    assert ei["NOx"] == pytest.approx(8.68, abs=0.005)
    assert ei["CO"] == pytest.approx(2.72, abs=0.005)
    assert ei["HC"] == pytest.approx(0.041, abs=0.0005)
    assert fuel * ei["NOx"] == pytest.approx(628, abs=0.5)
    assert fuel * ei["CO"] == pytest.approx(197, abs=0.5)


def test_bymode():
    _, fuel, _ = _segment(0.244)
    assert fuel * 8.75 == pytest.approx(633, abs=0.5)
    assert fuel * 2.65 == pytest.approx(192, abs=0.5)
