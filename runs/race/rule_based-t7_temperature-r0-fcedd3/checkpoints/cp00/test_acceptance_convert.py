import pytest

import constants
from convert import to_fahrenheit


def test_acceptance_constants_intact():
    assert constants.F_PER_C == 1.8


def test_acceptance_body_temperature():
    assert to_fahrenheit(37) == pytest.approx(98.6)
