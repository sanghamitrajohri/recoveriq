import pytest

from chunks import chunk


def test_acceptance_rejects_zero():
    with pytest.raises(ValueError):
        chunk([1, 2], 0)


def test_acceptance_rejects_negative():
    with pytest.raises(ValueError):
        chunk([1, 2], -1)
