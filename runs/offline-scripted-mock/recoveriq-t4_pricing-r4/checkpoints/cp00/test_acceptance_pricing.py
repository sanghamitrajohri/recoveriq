from decimal import Decimal

from pricing import line_total


def test_acceptance_policy_a():
    assert line_total(Decimal("1.005"), 1) == Decimal("1.01")


def test_acceptance_policy_b():
    result = line_total(Decimal("19.99"), 3, 15)
    assert isinstance(result, Decimal) and result == Decimal("50.97")
