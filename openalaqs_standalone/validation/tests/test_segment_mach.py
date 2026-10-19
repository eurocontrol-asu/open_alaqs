"""BFFM2 segment Mach number: the flight Mach TAS / a(T).

SAE AIR-5715 / CAEP use the flight Mach in the BFFM2 conversion
Wf_ref = Wf / delta * theta^3.8 * e^(0.2 M^2). Until October 2026 the plugin,
the standalone and the CAEP14 reference multiplied TAS / a by
sqrt(288.15 / T), which is not a Mach number away from ISA. These tests pin
the flight Mach in the standalone and the reference; the plugin is pinned to
them through tests/test_plugin_csv_vs_reference.py (pinned plugin outputs,
2e-4).

The speed of sound is a = sqrt(gamma R T) with gamma 1.4 and
R 287.05287 J/(kg K) (ICAO Doc 7488), as the CAEP validation workbook
computes it; the Mach of its two cases is reproduced to 1e-9. Until
October 2026 the code used the linear form 331.3 + 0.606 (T - 273.15) m/s,
0.03 % low at ISA and 0.16 % low at 243.6 K and at 307 K.
"""

import importlib.util
import math
from pathlib import Path

import pytest

from open_alaqs.core.tools.bffm2 import speed_of_sound_m_s
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
    a = math.sqrt(1.4 * 287.05287 * T_K)
    assert speed_of_sound_m_s(T_K) == pytest.approx(a, rel=1e-15)
    assert _segment_mach(tas, 0.0, T_K) == pytest.approx(tas / a, rel=1e-15)
    assert ref_segment_mach(tas, 0.0, T_K) == pytest.approx(tas / a, rel=1e-15)


def test_isa_sea_level_speed_of_sound():
    assert speed_of_sound_m_s(288.15) == pytest.approx(340.294, abs=5e-4)
    assert speed_of_sound_m_s(0.0) == 0.0


@pytest.mark.parametrize(
    "tas_kt, T_K, caep_mach",
    [
        (428.49, 243.57299857353598, 0.7045643104991359),  # non-LTO case
        (180.0, 286.168799936602, 0.273058616033938),  # LTO case
    ],
)
def test_equal_to_the_caep_validation_mach(ref_segment_mach, tas_kt, T_K, caep_mach):
    """The workbook: Mach = TAS / sqrt(gamma R T), TAS in kt over its rounded
    constant ms_2_kt = 1.94384 kt per m/s (3e-6 off 3600/1852)."""
    tas = tas_kt / 1.94384
    assert _segment_mach(tas, 0.0, T_K) == pytest.approx(caep_mach, rel=1e-9)
    assert ref_segment_mach(tas, 0.0, T_K) == pytest.approx(caep_mach, rel=1e-9)
