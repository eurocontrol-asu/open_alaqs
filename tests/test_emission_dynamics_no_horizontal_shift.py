"""Smooth & shift has no horizontal shift (intended behaviour).

default_emission_dynamics carries horizontal_shift_m (240 m / 480 m on
TO and CL rows) but the plugin does not read it: the emission volume
stays centred laterally on the trajectory, in both methods.
"""

from open_alaqs.core.interfaces.EmissionDynamics import EmissionDynamics


def test_horizontal_shift_is_always_zero():
    row = {
        "dynamics_name": "JET MEDIUM TO",
        "ac_group": "JET MEDIUM",
        "flight_stage": "TO",
        "horizontal_extent_m": 50,
        "vertical_extent_m": 500,
        "exit_velocity_m_per_s": 0,
        "decay_time_s": 0,
        "horizontal_shift_m": 480,
        "vertical_shift_m": 0,
        "horizontal_extent_m_sas": 50,
        "vertical_extent_m_sas": 500,
        "vertical_shift_m_sas": 0,
    }
    ed = EmissionDynamics(row)
    for mode in ("default", "sas"):
        params = ed.getEmissionDynamics(mode)
        assert params["horizontal_shift"] == 0
        assert params["horizontal_extension"] == 50
