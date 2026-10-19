import pytest

from duration import parse_duration


def test_seconds():
    assert parse_duration("45s") == 45


def test_hours_minutes():
    assert parse_duration("1h30m") == 5400


def test_days():
    assert parse_duration("2d") == 172800


def test_invalid():
    with pytest.raises(ValueError):
        parse_duration("abc")
