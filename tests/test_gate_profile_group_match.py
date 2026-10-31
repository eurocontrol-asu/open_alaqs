"""Gate GSE and GPU: matching the aircraft group to a gate profile group.

An aircraft group without its own gate profile takes the closest profile group
name (difflib), with a warning that names the aircraft group and the group it
was matched to (the two were swapped in the message). A group with no close
name, such as PROPELLER, gets no GSE and no GPU emissions: this is intended
(piston aircraft use no GSE or GPU), so it is logged at debug level only.
"""

from unittest import mock

import pytest

from open_alaqs.core import MovementEmissionCalculator as mec

PROFILE_GROUPS = [
    "JET BUSINESS",
    "JET REGIONAL",
    "JET SMALL",
    "JET MEDIUM",
    "JET LARGE",
    "TURBOPROP",
]


def _calculator(ac_group):
    gate = mock.Mock()
    gate.getEmissionProfileGroups.return_value = PROFILE_GROUPS
    gate.getEmissionIndex.return_value = None
    aircraft = mock.Mock()
    aircraft.getGroup.return_value = ac_group
    return mec.GateEmissionCalculator(gate, aircraft, "D", gate_emissions_code=1)


def test_near_match_warning_names_groups_in_order():
    calc = _calculator("JET SMAL")
    with mock.patch.object(mec, "logger") as log:
        assert calc._get_aircraft_group_match("gse") == "JET SMALL"
    log.warning.assert_called_once()
    msg = log.warning.call_args[0][0]
    assert "source type 'gse' and aircraft group 'JET SMAL'" in msg
    assert "but matched to 'JET SMALL'" in msg


@pytest.mark.parametrize("source_type", ["gse", "gpu"])
def test_propeller_gets_no_ground_equipment_quietly(source_type):
    calc = _calculator("PROPELLER")
    with mock.patch.object(mec, "logger") as log:
        assert calc._get_aircraft_group_match(source_type) is None
        assert calc._calculate_ground_equipment_emissions(source_type) == {}
    log.warning.assert_not_called()
    log.error.assert_not_called()
    log.info.assert_not_called()
    calc._gate.getEmissionIndex.assert_not_called()


def test_propeller_calculate_emissions_is_empty():
    calc = _calculator("PROPELLER")
    with mock.patch.object(mec, "logger") as log:
        assert calc.calculate_emissions() == []
    log.warning.assert_not_called()
