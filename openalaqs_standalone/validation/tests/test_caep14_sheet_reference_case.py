"""BFFM2 emission-index step pinned to the CAEP validation.

The CAEP validation (EUROCONTROL's CAEP/14 engine-emissions calculation; the
results are reproduced here, the workbook itself is not distributed) takes the
engine fuel flow as an input and computes the BFFM2 reference fuel flow and the
ambient emission indices. Its worked case:

  USER INPUTS: engine 01P20CM127 (LEAP-1A24/24E1/23, lean burn), phase CLIMB TO
  CRUISE (NON_LTO), altitude 22 500 ft, dT 0 K, RH 60 %, TAS 428.49 kt
  (Mach 0.70456), engine fuel flow 1.1748989 kg/s;
  ambient from the sheet's atmosphere: Ta 243.573 K, Pa 41 888.29 Pa.
  Indices: HC 0.02/0.02/0.05/0.37, CO 0.24/0.41/3.53/23.79 at fuel flows
  0.745/0.616/0.219/0.087 kg/s (TO/CL/AP/Idle); NOx from the BFFM2 v2 lean-burn
  reference engine 01P20CM132, 59.74/32.35/9.95/4.85 at 1.062/0.869/0.284/0.098,
  p3t3 exponent 0.3.
  Outputs: reference fuel flow 1.657227 kg/s; EI NOx 60.20166,
  EI CO 0.4595307, EI HC 0.02827881 g/kg.

A second case exercises the sheet's LTO path (standard indices, exponent
0.5): the same engine and fuel flow with altitude 1 000 ft, phase CLIMB OUT,
TAS 180 kt (Mach 0.273059), recalculated in LibreOffice 24.2 headless from the
same workbook: ambient 286.1688 K, 97 716.57 Pa; reference fuel flow
1.204590 kg/s; EI NOx 17.65248 (take-off index 17.59, capped, times the
ambient factor), EI CO 0.3296544, EI HC 0.02028642 g/kg.

The humidity ratio from RH differs slightly between the code and the CAEP validation
(saturation-pressure formula), hence a 1e-6 tolerance on NOx from RH and an
exact check with the CAEP validation's own humidity ratio.

This pins the index step only. The CAEP validation does not model how a fuel flow is
obtained from a thrust; that step is checked against the CAEP14 reference
implementation (test_plugin_csv_vs_reference.py).
"""

import math

import pytest

from open_alaqs.core.tools.bffm2 import calculate_emission_index

AMBIENT = {
    "temperature_in_Kelvin": 243.57299857353598,
    "pressure_in_Pa": 41888.29383521342,
    "relative_humidity": 0.6,
    "mach_number": 0.7045643104991359,
}
FF_AMB = 1.1748989032322528
EEDB_LEAP_1A24 = {
    "CO": {
        "Idle": {0.087: 23.79},
        "Approach": {0.219: 3.53},
        "Climbout": {0.616: 0.41},
        "Takeoff": {0.745: 0.24},
    },
    "HC": {
        "Idle": {0.087: 0.37},
        "Approach": {0.219: 0.05},
        "Climbout": {0.616: 0.02},
        "Takeoff": {0.745: 0.02},
    },
}
EEDB_LEAN_BURN_V2_NOX = {
    "NOx": {
        "Idle": {0.098: 4.85},
        "Approach": {0.284: 9.95},
        "Climbout": {0.869: 32.35},
        "Takeoff": {1.062: 59.74},
    },
}


def test_reference_fuel_flow_matches_caep_validation():
    theta = AMBIENT["temperature_in_Kelvin"] / 288.15
    delta = AMBIENT["pressure_in_Pa"] / 101325.0
    ff_ref = FF_AMB / delta * theta**3.8 * math.exp(0.2 * AMBIENT["mach_number"] ** 2)
    assert ff_ref == pytest.approx(1.657227421557182, rel=1e-9)


def test_nox_lean_burn_non_lto_matches_caep_validation():
    # From RH: the humidity ratio comes from the code's own saturation-pressure
    # formula, 1.4e-7 relative from the sheet's (omega 0.00046567).
    ei = calculate_emission_index(
        "NOx", FF_AMB, EEDB_LEAN_BURN_V2_NOX, AMBIENT, p3t3_y_exponent=0.3
    )
    assert ei == pytest.approx(60.20165533995983, rel=1e-6)
    # With the sheet's humidity ratio the match is to 1e-12.
    amb = dict(AMBIENT, humidity_ratio_in_kg_water_per_kg_dry_air=0.0004656746875112539)
    ei = calculate_emission_index(
        "NOx", FF_AMB, EEDB_LEAN_BURN_V2_NOX, amb, p3t3_y_exponent=0.3
    )
    assert ei == pytest.approx(60.20165533995983, rel=1e-12)


def test_co_matches_caep_validation():
    ei = calculate_emission_index("CO", FF_AMB, EEDB_LEAP_1A24, AMBIENT)
    assert ei == pytest.approx(0.45953065979284796, rel=1e-9)


def test_hc_matches_caep_validation():
    ei = calculate_emission_index("HC", FF_AMB, EEDB_LEAP_1A24, AMBIENT)
    assert ei == pytest.approx(0.02827880983340602, rel=1e-9)


AMBIENT_LTO = {
    "temperature_in_Kelvin": 286.168799936602,
    "pressure_in_Pa": 97716.5670052416,
    "relative_humidity": 0.6,
    "mach_number": 0.273058616033938,
}
EEDB_LEAP_1A24_NOX = {
    "NOx": {
        "Idle": {0.087: 4.45},
        "Approach": {0.219: 8.02},
        "Climbout": {0.616: 9.41},
        "Takeoff": {0.745: 17.59},
    },
}


def test_lto_reference_fuel_flow_matches_caep_validation():
    theta = AMBIENT_LTO["temperature_in_Kelvin"] / 288.15
    delta = AMBIENT_LTO["pressure_in_Pa"] / 101325.0
    ff_ref = (
        FF_AMB / delta * theta**3.8 * math.exp(0.2 * AMBIENT_LTO["mach_number"] ** 2)
    )
    assert ff_ref == pytest.approx(1.20458957016014, rel=1e-9)


def test_lto_nox_standard_indices_matches_caep_validation():
    ei = calculate_emission_index("NOx", FF_AMB, EEDB_LEAP_1A24_NOX, AMBIENT_LTO)
    assert ei == pytest.approx(17.6524830760443, rel=1e-5)
    amb = dict(
        AMBIENT_LTO, humidity_ratio_in_kg_water_per_kg_dry_air=0.00577917625237145
    )
    ei = calculate_emission_index("NOx", FF_AMB, EEDB_LEAP_1A24_NOX, amb)
    assert ei == pytest.approx(17.6524830760443, rel=1e-12)


def test_lto_co_and_hc_match_caep_validation():
    assert calculate_emission_index(
        "CO", FF_AMB, EEDB_LEAP_1A24, AMBIENT_LTO
    ) == pytest.approx(0.329654351844037, rel=1e-9)
    assert calculate_emission_index(
        "HC", FF_AMB, EEDB_LEAP_1A24, AMBIENT_LTO
    ) == pytest.approx(0.0202864216519408, rel=1e-9)
