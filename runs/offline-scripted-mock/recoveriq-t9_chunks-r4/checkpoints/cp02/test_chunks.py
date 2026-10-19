from chunks import chunk


def test_even():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_partial_last_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_empty():
    assert chunk([], 3) == []
