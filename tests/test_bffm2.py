from dataclasses import FrozenInstanceError

import pytest

from open_alaqs.core.tools.bffm2 import constants


def test_epsilon():
    assert constants.epsilon == 1e-4


def test_epsilon_change():
    with pytest.raises(FrozenInstanceError):
        constants.epsilon = 1e-5
