import pytest

from convert import to_fahrenheit, to_kelvin


def test_fahrenheit_boiling():
    assert to_fahrenheit(100) == pytest.approx(212.0)


def test_kelvin_freezing():
    assert to_kelvin(0) == pytest.approx(273.15)
