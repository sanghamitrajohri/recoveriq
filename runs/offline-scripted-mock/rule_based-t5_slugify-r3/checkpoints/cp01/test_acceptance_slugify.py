from slugify import slugify


def test_acceptance_punctuation():
    assert slugify("  C'est la vie!  ") == "c-est-la-vie"
