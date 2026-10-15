"""BFFM2 segment Mach number: the flight Mach TAS / a(T).

SAE AIR-5715 / CAEP use the flight Mach in the BFFM2 conversion
Wf_ref = Wf / delta * theta^3.8 * e^(0.2 M^2). Until October 2026 the plugin,
the standalone and the CAEP14 reference multiplied TAS / a by
sqrt(288.15 / T), which is not a Mach number away from ISA. These tests pin
the flight Mach in the standalone and the reference; the plugin is pinned to
them through tests/test_plugin_csv_vs_reference.py (pinned plugin outputs,
2e-4).

The speed of sound is OpenALAQS's linear form a = 331.3 + 0.606 (T - 273.15)
m/s. Against the CAEP validation's two cases (sqrt(gamma R T)) the Mach
agrees to 0.16 % (22 500 ft, 243.6 K) and 0.02 % (1 000 ft, 286.2 K).
"""

import importlib.util
from pathlib import Path

import pytest

from openalaqs_standalone.compute_aircraft import _segment_mach

TOOLS = Path(__file__).resolve().parents[1] / "tools"
KT = 0.514444


@pytest.fixture(scope="module")
def ref_segment_mach():
    spec = importlib.util.spec_from_file_location(
        "compute_caep14_reference", TOOLS / "compute_caep14_reference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._segment_mach


@pytest.mark.parametrize("T_K", [243.573, 273.15, 288.15, 307.15])
def test_flight_mach_standalone_and_reference(ref_segment_mach, T_K):
    tas = 150 * KT
    a = 331.3 + 0.606 * (T_K - 273.15)
    assert _segment_mach(tas, 0.0, T_K) == pytest.approx(tas / a, rel=1e-15)
    assert ref_segment_mach(tas, 0.0, T_K) == pytest.approx(tas / a, rel=1e-15)


@pytest.mark.parametrize(
    "tas_kt, T_K, caep_mach, rel",
    [
        (428.49, 243.57299857353598, 0.7045643104991359, 2e-3),  # non-LTO case
        (180.0, 286.168799936602, 0.273058616033938, 3e-4),  # LTO case
    ],
)
def test_close_to_the_caep_validation_mach(tas_kt, T_K, caep_mach, rel):
    assert _segment_mach(tas_kt * KT, 0.0, T_K) == pytest.approx(caep_mach, rel=rel)
