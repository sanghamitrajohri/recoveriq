from duration import parse_duration


def test_acceptance_mixed_case_and_spaces():
    assert parse_duration(" 1H5M3S ") == 3903


def test_acceptance_minutes_only():
    assert parse_duration("90m") == 5400
