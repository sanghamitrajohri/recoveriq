from wordfreq import top_words


def test_acceptance_n_larger_than_vocab():
    assert top_words("one two", 5) == [("one", 1), ("two", 1)]
