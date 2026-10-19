"""MEEM V1 above 3000 ft in the CAEP14 reference and the standalone.

The reference (`tools/compute_caep14_reference.py`, `_meem_v1_mass_mgkg`) is
written out from the MEEM_V1 tab of the CAEP14 FBE Engines Emissions
Calculation Sheet v14 without the plugin's code; the standalone
(`compute_aircraft._meem_v1_segment_ei`) uses the plugin's
`open_alaqs.core.tools.meem_v1`. Both must give the sheet's nvPM mass EI
(MEEM_V1!B119). The training_v3 fixture of the parity gate has no segment
above 3000 ft (mixing height 914.4 m), so this is checked here.

Sheet values: the stored example (01P20CM127, 22500 ft) and the sheet
recalculated in LibreOffice 24.2 for the other inputs (see
tests/test_meem_v1.py); ISA (delta T 0), cruise altitude 38000 ft.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from openalaqs_standalone.compute_aircraft import _meem_v1_segment_ei

TOOLS = Path(__file__).resolve().parents[1] / "tools"
FT2M = 0.3048000097536

_TS = (1.0, 0.85, 0.30, 0.07)
_ENGINES = {
    "01P20CM127": (
        30.0,
        (1.35458150221701, 1.03598718120316, 1.85003357629324, 0.788067430941943),
    ),
    "01P20CM128": (
        33.3,
        (1.6270256714414, 1.23517541065843, 2.98855587397408, 0.683860589780375),
    ),
    "11GE144": (
        27.2,
        (73.7415341769357, 53.301741608788, 2.79689622305639, 5.3325761855363),
    ),
}
# (engine, altitude ft, climbing, TAS kt) -> MEEM_V1!B119 (mg/kg)
_CASES = [
    (("01P20CM127", 22500, True, 428.49), 0.944536653843135),
    (("01P20CM127", 8000, True, 280), 1.169462798467009),
    (("01P20CM127", 12000, False, 300), 0.9340576233694476),
    (("11GE144", 4500, True, 220), 61.22075397785308),
    (("11GE144", 5000, False, 210), 5.588363301978656),
    (("01P20CM128", 3500, True, 200), 1.5260688609694564),
]


@pytest.fixture(scope="module")
def ref():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("inputs, expected", _CASES)
def test_reference_matches_sheet(ref, inputs, expected):
    engine, alt_ft, climbing, tas_kt = inputs
    opr, mass = _ENGINES[engine]
    v = ref._meem_v1_mass_mgkg(
        alt_ft, tas_kt / 1.94384, climbing, list(zip(_TS, mass)), opr
    )
    assert v == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("inputs, expected", _CASES)
def test_standalone_matches_sheet(inputs, expected):
    engine, alt_ft, climbing, tas_kt = inputs
    opr, mass = _ENGINES[engine]
    modes = ("TO", "CL", "AP", "TX")
    meem = {
        "pm10_nonvol": {m: v / 1000.0 for m, v in zip(modes, mass)},
        "nvpm_number": {m: 1.0e14 for m in modes},
        "press_ratio": opr,
        "m_f00": None,
        "m_max_mgkg": None,
        "n_f00": None,
        "n_max_nkg": None,
    }
    mode = "CL" if climbing else "AP"
    eng = {"pm10_ei": meem["pm10_nonvol"][mode] + 0.05}
    out = _meem_v1_segment_ei(
        eng, meem, mode, alt_ft * FT2M, tas_kt / 1.94384, climbing
    )
    assert out["pm10_ei"] - 0.05 == pytest.approx(expected / 1000.0, rel=1e-12)


def test_lto_unchanged(ref):
    """At or below 3000 ft above MSL the mode EI is used unchanged."""
    meem = {
        "pm10_nonvol": {"TO": 0.07, "CL": 0.05, "AP": 0.003, "TX": 0.005},
        "nvpm_number": {"TO": 1e14, "CL": 1e14, "AP": 1e14, "TX": 1e14},
        "press_ratio": 27.2,
        "m_f00": None,
        "m_max_mgkg": None,
        "n_f00": None,
        "n_max_nkg": None,
    }
    eng = {"pm10_ei": 0.1}
    assert _meem_v1_segment_ei(eng, meem, "CL", 914.4, 120.0, True) is eng
