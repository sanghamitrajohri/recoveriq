from versions import is_newer


def test_acceptance_major():
    assert is_newer("10.0.0", "9.99.99")
