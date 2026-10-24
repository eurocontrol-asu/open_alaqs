"""BFFM2 trajectory fuel flow from the thrust share (ANP profiles).

The reference fuel flow read on the ICAO curve at the thrust share is scaled to
ambient with the corrected-parameter scaling of gas-turbine performance (the
corrected fuel flow, fuel flow / (delta * sqrt(theta)), as a function of the corrected
thrust, thrust / delta, and Mach), not with the inverse of the BFFM2 emission-index
conversion (delta / theta^3.8 / exp(0.2 M^2)). The plugin
(Engine.getEmissionIndexByEngineState) and the standalone trajectory path
(_bffm2_traj_ff_amb) are compared here; the taxi and engine-test paths of both use
the same delta * sqrt(theta) form and are covered by the plugin/standalone/reference
parity tests (openalaqs_standalone/validation/tests), not by this file.
"""

import math

import pytest

from open_alaqs.core.interfaces.Engine import EngineEmissionIndex
from open_alaqs.core.tools.twin_quadratic_fit_method import (
    calculate_fuel_flow_from_power_setting,
)
from openalaqs_standalone import compute_aircraft as ca

_FF = {"TO": 1.10, "CL": 0.90, "AP": 0.30, "TX": 0.10}
_TS = {"TO": 1.0, "CL": 0.85, "AP": 0.30, "TX": 0.07}
_NOX = {"TO": 30.0, "CL": 24.0, "AP": 11.0, "TX": 4.5}
_CO = {"TO": 0.3, "CL": 0.4, "AP": 2.5, "TX": 25.0}
_HC = {"TO": 0.05, "CL": 0.06, "AP": 0.1, "TX": 2.0}


class _Ambient:
    def __init__(self, t_k=288.15, p_pa=101325.0, rh=0.6):
        self._t, self._p, self._rh = t_k, p_pa, rh

    def getTemperature(self):
        return self._t

    def getPressure(self):
        return self._p

    def getRelativeHumidity(self):
        return self._rh


def _engine():
    eei = EngineEmissionIndex()
    for m in ("TO", "CL", "AP", "TX"):
        eei.setObject(
            m,
            {
                "mode": m,
                "thrust": _TS[m],
                "fuel_kg_sec": _FF[m],
                "co_ei": _CO[m],
                "hc_ei": _HC[m],
                "nox_ei": _NOX[m],
                "sox_ei": 1.0,
                "pm10_ei": 0.05,
                "p1_ei": 0.05,
                "p2_ei": 0.05,
            },
        )
    return eei


def _method(t_k=288.15, p_pa=101325.0, mach=0.0):
    return {
        "name": "BFFM2",
        "config": {
            "ambient_conditions": _Ambient(t_k, p_pa),
            "mach_number": mach,
            "installation_corrections": {},
        },
    }


def _ff_ref(power):
    eedb = {_TS[m]: _FF[m] for m in _FF}
    return calculate_fuel_flow_from_power_setting(power, eedb)


def _plugin_ff(power, **kw):
    ei = _engine().getEmissionIndexByEngineState(power, method=_method(**kw))
    return ei.getObject("fuel_kg_sec")


@pytest.mark.parametrize("power", [0.07, 0.3, 0.6, 0.85, 1.0])
def test_isa_static_equals_the_icao_curve(power):
    assert _plugin_ff(power) == pytest.approx(_ff_ref(power), rel=1e-12)


@pytest.mark.parametrize("t_k", [278.15, 298.15, 303.15])
@pytest.mark.parametrize("p_pa", [95000.0, 101325.0, 102300.0])
def test_ambient_scaling_is_delta_sqrt_theta(t_k, p_pa):
    expected = _ff_ref(0.6) * (p_pa / 101325.0) * math.sqrt(t_k / 288.15)
    assert _plugin_ff(0.6, t_k=t_k, p_pa=p_pa) == pytest.approx(expected, rel=1e-12)


def test_fuel_flow_rises_with_temperature():
    """At a fixed thrust share a hot day needs slightly more fuel (+1.7% at 25 C);
    the inverse BFFM2 conversion gave 12% less."""
    cold = _plugin_ff(0.6)
    hot = _plugin_ff(0.6, t_k=298.15)
    assert hot / cold == pytest.approx(math.sqrt(298.15 / 288.15), rel=1e-12)
    assert hot > cold


@pytest.mark.parametrize("mach", [0.0, 0.2, 0.4])
def test_no_mach_term(mach):
    assert _plugin_ff(0.85, mach=mach) == pytest.approx(_ff_ref(0.85), rel=1e-12)


def test_emission_index_is_bffm2_at_the_ambient_fuel_flow():
    """The emission indices are the standard BFFM2 lookup at the ambient fuel flow
    the engine branch returns (as for a supplied fuel flow)."""
    m = _method(t_k=298.15, p_pa=100500.0, mach=0.3)
    eng = _engine()
    a = eng.getEmissionIndexByEngineState(0.6, method=m)
    b = eng.getEmissionIndexByFuelFlow(a.getObject("fuel_kg_sec"), m)
    for k in ("nox_g_kg", "co_g_kg", "hc_g_kg"):
        assert a.getObject(k) == pytest.approx(b.getObject(k), rel=1e-12)


@pytest.mark.parametrize(
    "power, t_k, p_pa, mach",
    [
        (0.6, 288.15, 101325.0, 0.0),
        (0.85, 298.15, 101900.0, 0.25),
        (0.3, 293.0, 100800.0, 0.2),
        (0.05, 293.0, 101325.0, 0.2),
    ],
)
def test_standalone_matches_plugin(monkeypatch, power, t_k, p_pa, mach):
    monkeypatch.setattr(
        ca.mv, "get_trajectory_point_power_ff", lambda conn, pid, idx: (power, None)
    )
    engine_ei = {m: {"ff": _FF[m], "power": _TS[m]} for m in _FF}
    meteo = {"T_K": t_k, "P_Pa": p_pa, "RH": 0.6}
    got = ca._bffm2_traj_ff_amb(
        None,
        {"profile_id": "X"},
        (1,),
        engine_ei["CL"],
        engine_ei,
        meteo,
        mach,
        2,
    )
    assert got == pytest.approx(
        _plugin_ff(power, t_k=t_k, p_pa=p_pa, mach=mach), rel=1e-9
    )
