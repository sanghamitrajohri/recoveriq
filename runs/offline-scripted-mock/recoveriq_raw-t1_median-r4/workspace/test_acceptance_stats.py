from stats import median


def test_acceptance_median_floats():
    assert median([1.0, 2.0, 10.0, 20.0]) == 6.0


def test_acceptance_does_not_mutate():
    data = [3, 1, 2, 0]
    median(data)
    assert data == [3, 1, 2, 0]
