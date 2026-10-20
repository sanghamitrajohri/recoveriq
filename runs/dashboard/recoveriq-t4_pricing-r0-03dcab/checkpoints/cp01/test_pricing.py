import pytest

from pricing import line_total


def test_no_discount():
    assert line_total(10, 3) == 30


def test_ten_percent_discount():
    assert line_total(10, 3, 10) == 27


def test_invalid_discount():
    with pytest.raises(ValueError):
        line_total(10, 1, 150)
