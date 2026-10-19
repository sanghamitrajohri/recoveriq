from versions import is_newer


def test_simple():
    assert is_newer("1.2.0", "1.1.9")


def test_multi_digit_component():
    assert is_newer("1.10.0", "1.9.3")


def test_missing_patch_component():
    assert not is_newer("2.0", "2.0.0")


def test_equal():
    assert not is_newer("3.1.4", "3.1.4")
