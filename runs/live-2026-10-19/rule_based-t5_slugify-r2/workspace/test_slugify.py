from slugify import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_underscores_become_hyphens():
    assert slugify("snake_case title") == "snake-case-title"


def test_underscores_are_preserved():
    assert slugify("snake_case title") == "snake_case-title"
