from wordfreq import top_words


def test_top_two():
    assert top_words("b a b c a b", 2) == [("b", 3), ("a", 2)]


def test_ties_alphabetical():
    assert top_words("z y x", 2) == [("x", 1), ("y", 1)]
